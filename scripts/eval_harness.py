from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

import geopandas as gpd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.source_asset_service import SourceAssetService
from utils.local_smoke import build_run_request_from_case, run_local_v2_smoke, validate_smoke_result
from utils.shp_zip import zip_shapefile_bundle
from utils.vector_clip import clip_frame_to_request_bbox


RequestBuilder = Callable[[Path], dict[str, Any]]
Runner = Callable[..., dict[str, Any]]
Validator = Callable[..., None]


def _detect_git_commit_sha() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:  # noqa: BLE001
        return None
    value = completed.stdout.strip()
    return value or None


def _fetch_runtime_environment(base_url: str) -> dict[str, Any]:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", "api/v2/runtime")
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        "kg_backend": payload.get("kg_backend"),
        "llm_provider": payload.get("llm_provider"),
        "celery_eager": payload.get("celery_eager"),
    }


def _build_source_asset_service() -> SourceAssetService:
    return SourceAssetService(repo_root=REPO_ROOT, cache_dir=REPO_ROOT / "runs" / "source-assets")


def _build_summary_metadata(*, base_url: str, timeout_sec: float, command_mode: str) -> dict[str, Any]:
    environment = {
        "kg_backend": os.getenv("GEOFUSION_KG_BACKEND"),
        "llm_provider": os.getenv("GEOFUSION_LLM_PROVIDER"),
        "celery_eager": os.getenv("GEOFUSION_CELERY_EAGER"),
    }
    runtime_environment = _fetch_runtime_environment(base_url)
    for key, value in runtime_environment.items():
        if value is not None:
            environment[key] = value
    return {
        "command_mode": command_mode,
        "base_url": base_url,
        "timeout_sec": float(timeout_sec),
        "commit_sha": _detect_git_commit_sha(),
        "environment": environment,
    }


def _resolve_case_timeout_sec(case: dict[str, Any], *, default_timeout_sec: float) -> float:
    raw = case.get("timeout_sec")
    if raw is None:
        return float(default_timeout_sec)
    return float(raw)


def _is_runnable_manifest_case(case: dict[str, Any]) -> bool:
    return str(case.get("execution_mode") or "") == "agent" and str(case.get("readiness") or "") == "agent-ready"


def _preflight_manifest_api(base_url: str) -> None:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", "api/v2/runs")
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5):
            return
    except urllib.error.HTTPError:
        # Any HTTP response means the API endpoint is reachable even if the method is not allowed.
        return
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Manifest preflight API reachability check failed for {url}: {exc}") from exc


def _preflight_manifest_case_inputs(case: dict[str, Any]) -> None:
    inputs = case.get("inputs") or {}
    _preflight_manifest_input(case, inputs, path_key="osm", source_key="osm_source_id", label="OSM")
    _preflight_manifest_input(case, inputs, path_key="reference", source_key="reference_source_id", label="reference")


def _preflight_manifest_input(
    case: dict[str, Any],
    inputs: dict[str, Any],
    *,
    path_key: str,
    source_key: str,
    label: str,
) -> None:
    raw_path = str(inputs.get(path_key) or "").strip()
    source_id = str(inputs.get(source_key) or "").strip()
    if raw_path and source_id:
        raise ValueError(
            f"Manifest preflight input for {label} must not set both 'inputs.{path_key}' and 'inputs.{source_key}'"
        )
    if raw_path:
        candidate = Path(raw_path)
        if not candidate.exists():
            raise FileNotFoundError(f"Manifest preflight {label} shapefile not found: {candidate}")
        return
    if source_id:
        service = _build_source_asset_service()
        if not service.can_materialize(source_id):
            raise ValueError(
                f"Manifest preflight {label} source id is not materializable in this repo: {source_id}"
            )
        return
    if path_key == "osm":
        raise ValueError(f"Manifest preflight missing required input path 'inputs.osm' for case {case.get('case_id')!r}")
    raise ValueError(
        f"Manifest preflight missing required input path 'inputs.reference' for case {case.get('case_id')!r}"
    )


def discover_case_dirs(cases_root: Path, selected_cases: list[str] | None = None) -> list[Path]:
    case_files = sorted(cases_root.glob("*/case.json"))
    case_dirs = [case_file.parent.resolve() for case_file in case_files]
    if not selected_cases:
        return case_dirs

    selected = set(selected_cases)
    filtered: list[Path] = []
    for case_dir in case_dirs:
        case_id = _read_case_id(case_dir)
        if case_id in selected or case_dir.name in selected:
            filtered.append(case_dir)
    return filtered


def load_manifest_cases(manifest_path: Path, selected_cases: list[str] | None = None) -> list[dict[str, Any]]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("Manifest 'cases' must be a list.")
    if not selected_cases:
        return [case for case in cases if isinstance(case, dict)]

    selected = set(selected_cases)
    filtered: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        case_id = str(case.get("case_id") or "")
        if case_id in selected:
            filtered.append(case)
    return filtered


def evaluate_cases(
    case_dirs: list[Path],
    *,
    base_url: str,
    timeout_sec: float,
    request_builder: RequestBuilder = build_run_request_from_case,
    runner: Runner = run_local_v2_smoke,
    validator: Validator = validate_smoke_result,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for case_dir in case_dirs:
        results.append(
            _evaluate_single_case(
                case_dir=case_dir,
                base_url=base_url,
                timeout_sec=timeout_sec,
                request_builder=request_builder,
                runner=runner,
                validator=validator,
            )
        )

    passed = sum(1 for item in results if item["status"] == "passed")
    failed = len(results) - passed
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **_build_summary_metadata(base_url=base_url, timeout_sec=timeout_sec, command_mode="golden-case"),
        "totals": {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "skipped": 0,
        },
        "all_passed": failed == 0,
        "cases": results,
    }


def evaluate_manifest_cases(
    cases: list[dict[str, Any]],
    *,
    base_url: str,
    timeout_sec: float,
    runner: Runner = run_local_v2_smoke,
    validator: Validator = validate_smoke_result,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    runnable_cases = [case for case in cases if isinstance(case, dict) and _is_runnable_manifest_case(case)]
    api_preflight_error: str | None = None
    if runnable_cases:
        try:
            _preflight_manifest_api(base_url)
        except Exception as exc:  # noqa: BLE001
            api_preflight_error = f"{type(exc).__name__}: {exc}"

    for case in cases:
        effective_timeout_sec = _resolve_case_timeout_sec(case, default_timeout_sec=timeout_sec)
        execution_mode = str(case.get("execution_mode") or "")
        readiness = str(case.get("readiness") or "")
        blockers = case.get("blockers") or []
        if execution_mode != "agent":
            results.append(
                _skipped_manifest_case(
                    case,
                    f"execution_mode={execution_mode} is not runnable by eval_harness",
                    timeout_sec=effective_timeout_sec,
                )
            )
            continue
        if readiness != "agent-ready":
            reason = f"readiness={readiness or 'unknown'} is not runnable yet"
            if blockers:
                reason = f"{reason}; blockers={'; '.join(map(str, blockers))}"
            results.append(_skipped_manifest_case(case, reason, timeout_sec=effective_timeout_sec))
            continue
        if api_preflight_error is not None:
            results.append(_failed_manifest_case(case, api_preflight_error, timeout_sec=effective_timeout_sec))
            continue
        try:
            _preflight_manifest_case_inputs(case)
        except Exception as exc:  # noqa: BLE001
            results.append(
                _failed_manifest_case(case, f"{type(exc).__name__}: {exc}", timeout_sec=effective_timeout_sec)
            )
            continue
        results.append(
            _evaluate_single_manifest_case(
                case=case,
                base_url=base_url,
                timeout_sec=effective_timeout_sec,
                runner=runner,
                validator=validator,
            )
        )

    passed = sum(1 for item in results if item["status"] == "passed")
    failed = sum(1 for item in results if item["status"] == "failed")
    skipped = sum(1 for item in results if item["status"] == "skipped")
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **_build_summary_metadata(base_url=base_url, timeout_sec=timeout_sec, command_mode="manifest"),
        "totals": {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
        },
        "all_passed": failed == 0,
        "cases": results,
    }


def _evaluate_single_case(
    *,
    case_dir: Path,
    base_url: str,
    timeout_sec: float,
    request_builder: RequestBuilder,
    runner: Runner,
    validator: Validator,
) -> dict[str, Any]:
    started = time.perf_counter()
    case_id = _read_case_id(case_dir)
    try:
        payload = request_builder(case_dir)
        case_id = payload.get("case_id", case_id)
        result = runner(case_dir, base_url=base_url, timeout_sec=timeout_sec)
        validator(
            result,
            expected_plan_checks=payload.get("expected_plan_checks"),
            artifact_checks=payload.get("artifact_checks"),
        )
        status = "passed"
        error = None
        run_id = result.get("run_id")
        artifact_size = result.get("artifact_size")
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"
        run_id = None
        artifact_size = None

    duration_ms = int((time.perf_counter() - started) * 1000)
    return {
        "case_id": case_id,
        "case_dir": str(case_dir),
        "status": status,
        "duration_ms": duration_ms,
        "run_id": run_id,
        "artifact_size": artifact_size,
        "error": error,
        "timeout_sec": float(timeout_sec),
    }


def _evaluate_single_manifest_case(
    *,
    case: dict[str, Any],
    base_url: str,
    timeout_sec: float,
    runner: Runner,
    validator: Validator,
) -> dict[str, Any]:
    started = time.perf_counter()
    case_id = str(case.get("case_id") or "unknown_case")
    try:
        with tempfile.TemporaryDirectory(prefix=f"eval-{case_id}-") as td:
            case_dir = _materialize_manifest_case(case, Path(td))
            payload = build_run_request_from_case(case_dir)
            result = runner(case_dir, base_url=base_url, timeout_sec=timeout_sec)
            validator(
                result,
                expected_plan_checks=payload.get("expected_plan_checks"),
                artifact_checks=payload.get("artifact_checks"),
            )
        status = "passed"
        error = None
        run_id = result.get("run_id")
        artifact_size = result.get("artifact_size")
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"
        run_id = None
        artifact_size = None

    duration_ms = int((time.perf_counter() - started) * 1000)
    return {
        "case_id": case_id,
        "case_dir": None,
        "status": status,
        "duration_ms": duration_ms,
        "run_id": run_id,
        "artifact_size": artifact_size,
        "error": error,
        "timeout_sec": float(timeout_sec),
    }


def _skipped_manifest_case(case: dict[str, Any], reason: str, *, timeout_sec: float) -> dict[str, Any]:
    return {
        "case_id": str(case.get("case_id") or "unknown_case"),
        "case_dir": None,
        "status": "skipped",
        "duration_ms": 0,
        "run_id": None,
        "artifact_size": None,
        "error": reason,
        "timeout_sec": float(timeout_sec),
    }


def _failed_manifest_case(case: dict[str, Any], reason: str, *, timeout_sec: float) -> dict[str, Any]:
    return {
        "case_id": str(case.get("case_id") or "unknown_case"),
        "case_dir": None,
        "status": "failed",
        "duration_ms": 0,
        "run_id": None,
        "artifact_size": None,
        "error": reason,
        "timeout_sec": float(timeout_sec),
    }


def _parse_clip_bbox(case: dict[str, Any]) -> tuple[float, float, float, float] | None:
    raw = case.get("clip_bbox")
    if not isinstance(raw, list) or len(raw) != 4:
        return None
    try:
        minx, miny, maxx, maxy = (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Invalid clip_bbox for case {case.get('case_id')!r}: {raw!r}") from exc
    if maxx < minx or maxy < miny:
        raise ValueError(f"Invalid clip_bbox ordering for case {case.get('case_id')!r}: {raw!r}")
    return (minx, miny, maxx, maxy)


def _bbox_to_text(bbox: tuple[float, float, float, float]) -> str:
    return f"bbox({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]})"


def _zip_manifest_input(source_path: Path, output_zip: Path, *, clip_bbox: tuple[float, float, float, float] | None) -> None:
    if clip_bbox is None:
        zip_shapefile_bundle(source_path, output_zip)
        return

    gdf = gpd.read_file(source_path)
    clipped = clip_frame_to_request_bbox(gdf, clip_bbox)
    if clipped.empty:
        raise ValueError(f"clip_bbox produced no features for source {source_path}")
    clip_dir = output_zip.parent / f"_clip_{source_path.stem}"
    clip_dir.mkdir(parents=True, exist_ok=True)
    clipped_shp = clip_dir / source_path.name
    clipped.to_file(clipped_shp)
    zip_shapefile_bundle(clipped_shp, output_zip)


def _resolve_manifest_input_path(
    *,
    inputs: dict[str, Any],
    path_key: str,
    source_key: str,
    request_bbox: tuple[float, float, float, float] | None,
) -> Path:
    raw_path = str(inputs.get(path_key) or "").strip()
    source_id = str(inputs.get(source_key) or "").strip()
    if raw_path and source_id:
        raise ValueError(f"Manifest input must not set both 'inputs.{path_key}' and 'inputs.{source_key}'")
    if raw_path:
        candidate = Path(raw_path)
        if not candidate.exists():
            raise FileNotFoundError(f"Manifest input shapefile not found: {candidate}")
        return candidate
    if source_id:
        return _build_source_asset_service().resolve_raw_source_path(source_id, request_bbox=request_bbox).path
    raise ValueError(f"Manifest input must set one of 'inputs.{path_key}' or 'inputs.{source_key}'")


def _materialize_manifest_case(case: dict[str, Any], root: Path) -> Path:
    case_id = str(case.get("case_id") or "manifest_case")
    theme = str(case.get("theme") or "")
    if theme not in {"building", "road"}:
        raise ValueError(f"Unsupported manifest theme for agent execution: {theme}")

    inputs = case.get("inputs") or {}
    case_dir = root / case_id
    input_dir = case_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    clip_bbox = _parse_clip_bbox(case)
    osm_path = _resolve_manifest_input_path(
        inputs=inputs,
        path_key="osm",
        source_key="osm_source_id",
        request_bbox=clip_bbox,
    )
    ref_path = _resolve_manifest_input_path(
        inputs=inputs,
        path_key="reference",
        source_key="reference_source_id",
        request_bbox=clip_bbox,
    )
    _zip_manifest_input(osm_path, input_dir / "osm.zip", clip_bbox=clip_bbox)
    _zip_manifest_input(ref_path, input_dir / "ref.zip", clip_bbox=clip_bbox)

    payload = {
        "case_id": case_id,
        "job_type": theme,
        "trigger": {
            "type": "user_query",
            "content": f"real data evaluation for {case_id}",
        },
        "osm_zip": "input/osm.zip",
        "ref_zip": "input/ref.zip",
        "expected_plan_checks": {
            "required_output_type": f"dt.{theme}.fused",
        },
        "artifact_checks": {
            "required_suffixes": [".shp", ".shx", ".dbf"],
        },
    }
    if theme == "building":
        payload["expected_plan_checks"]["required_algorithms"] = [
            "algo.fusion.building.v1",
            "algo.fusion.building.safe",
        ]
    if theme == "road":
        payload["expected_plan_checks"]["required_algorithms"] = [
            "algo.fusion.road.v1",
            "algo.fusion.road.safe",
        ]
    if clip_bbox is not None:
        payload["trigger"]["spatial_extent"] = _bbox_to_text(clip_bbox)

    (case_dir / "case.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return case_dir


def _read_case_id(case_dir: Path) -> str:
    manifest_path = case_dir / "case.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return case_dir.name
    value = payload.get("case_id")
    return str(value) if value else case_dir.name


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run FusionAgent evaluation harness across golden cases.")
    parser.add_argument("--manifest", default="", help="Optional manifest JSON for real-data evaluation cases.")
    parser.add_argument(
        "--cases-root",
        default=str(REPO_ROOT / "tests" / "golden_cases"),
        help="Directory containing case subfolders with case.json.",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Run only the selected case id or directory name (can be provided multiple times).",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL for evaluation runs.")
    parser.add_argument("--timeout", type=float, default=180.0, help="Per-case timeout in seconds.")
    parser.add_argument("--output-json", default="", help="Optional path to write summary JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    summary: dict[str, Any]
    selected_cases = list(args.case)
    if args.manifest:
        manifest_path = Path(args.manifest).resolve()
        manifest_cases = load_manifest_cases(manifest_path=manifest_path, selected_cases=selected_cases or None)
        summary = evaluate_manifest_cases(
            cases=manifest_cases,
            base_url=args.base_url,
            timeout_sec=args.timeout,
        )
        summary["manifest"] = str(manifest_path)
        if not manifest_cases:
            summary["warning"] = f"No cases found in manifest {manifest_path}"
    else:
        cases_root = Path(args.cases_root).resolve()
        case_dirs = discover_case_dirs(cases_root=cases_root, selected_cases=selected_cases or None)
        summary = evaluate_cases(
            case_dirs=case_dirs,
            base_url=args.base_url,
            timeout_sec=args.timeout,
        )
        summary["cases_root"] = str(cases_root)
        if not case_dirs:
            summary["warning"] = f"No cases found under {cases_root}"

    summary["selected_cases"] = list(args.case)

    output = json.dumps(summary, ensure_ascii=False, indent=2)
    print(output)

    if args.output_json:
        output_path = Path(args.output_json).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")

    if summary["totals"]["failed"] > 0:
        return 1
    if summary["totals"]["total"] == 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
