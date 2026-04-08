from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils.local_smoke import build_run_request_from_case, run_local_v2_smoke, validate_smoke_result
from utils.shp_zip import zip_shapefile_bundle


RequestBuilder = Callable[[Path], dict[str, Any]]
Runner = Callable[..., dict[str, Any]]
Validator = Callable[..., None]


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
    for case in cases:
        execution_mode = str(case.get("execution_mode") or "")
        readiness = str(case.get("readiness") or "")
        blockers = case.get("blockers") or []
        if execution_mode != "agent":
            results.append(_skipped_manifest_case(case, f"execution_mode={execution_mode} is not runnable by eval_harness"))
            continue
        if readiness != "agent-ready":
            reason = f"readiness={readiness or 'unknown'} is not runnable yet"
            if blockers:
                reason = f"{reason}; blockers={'; '.join(map(str, blockers))}"
            results.append(_skipped_manifest_case(case, reason))
            continue
        results.append(
            _evaluate_single_manifest_case(
                case=case,
                base_url=base_url,
                timeout_sec=timeout_sec,
                runner=runner,
                validator=validator,
            )
        )

    passed = sum(1 for item in results if item["status"] == "passed")
    failed = sum(1 for item in results if item["status"] == "failed")
    skipped = sum(1 for item in results if item["status"] == "skipped")
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
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
    }


def _skipped_manifest_case(case: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "case_id": str(case.get("case_id") or "unknown_case"),
        "case_dir": None,
        "status": "skipped",
        "duration_ms": 0,
        "run_id": None,
        "artifact_size": None,
        "error": reason,
    }


def _materialize_manifest_case(case: dict[str, Any], root: Path) -> Path:
    case_id = str(case.get("case_id") or "manifest_case")
    theme = str(case.get("theme") or "")
    if theme not in {"building", "road"}:
        raise ValueError(f"Unsupported manifest theme for agent execution: {theme}")

    inputs = case.get("inputs") or {}
    osm_path = Path(str(inputs.get("osm") or ""))
    ref_path = Path(str(inputs.get("reference") or ""))
    if not osm_path.exists():
        raise FileNotFoundError(f"OSM shapefile not found: {osm_path}")
    if not ref_path.exists():
        raise FileNotFoundError(f"Reference shapefile not found: {ref_path}")

    case_dir = root / case_id
    input_dir = case_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    zip_shapefile_bundle(osm_path, input_dir / "osm.zip")
    zip_shapefile_bundle(ref_path, input_dir / "ref.zip")

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
