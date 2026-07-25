from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kg.seed_manifest import build_seed_manifest_payload
from schemas.contract_experiment import ContractExperimentManifest, ContractExperimentCase, ExperimentStageDeclaration
from services.contract_experiment_service import (
    build_external_input_evidence,
    evaluate_case_contract,
    load_experiment_manifest,
    prepare_stage_sources,
    sha256_file,
)
from scripts.freeze_experiment_evidence import freeze_experiment


DEFAULT_MANIFEST = REPO_ROOT / "docs" / "thesis" / "manifests" / "2026-07-20-c02-c04-c06-real-data.json"


def run_manifest(
    *,
    manifest_path: Path,
    experiment_dir: Path,
    api_base_url: str,
    start_server: bool,
    server_port: int,
    poll_seconds: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    manifest = load_experiment_manifest(manifest_path)
    experiment_dir = Path(experiment_dir).resolve()
    runtime_dir = experiment_dir / "runtime"
    data_root = runtime_dir / "data_repository"
    downloads_root = runtime_dir / "downloads"
    runs_root = runtime_dir / "runs"
    scenario_root = runtime_dir / "scenario_outputs"
    for directory in (runtime_dir, data_root, downloads_root, runs_root, scenario_root):
        directory.mkdir(parents=True, exist_ok=True)

    external_inputs = build_external_input_evidence(manifest)
    (experiment_dir / "external_inputs.json").write_text(
        json.dumps(external_inputs, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_runtime_metadata(manifest, manifest_path, experiment_dir, runtime_dir)

    server = None
    try:
        if start_server:
            server, api_base_url = _start_server(
                api_base_url=api_base_url,
                port=server_port,
                data_root=data_root,
                downloads_root=downloads_root,
                runs_root=runs_root,
                scenario_root=scenario_root,
                experiment_dir=experiment_dir,
            )
        _wait_for_api(api_base_url, timeout_seconds=60)
        case_results: list[dict[str, Any]] = []
        for case in manifest.cases:
            case_dir = experiment_dir / "cases" / case.case_id
            case_dir.mkdir(parents=True, exist_ok=True)
            stage_records: list[dict[str, Any]] = []
            scenario_id: str | None = None
            for stage in case.stages:
                prepared = prepare_stage_sources(
                    manifest=manifest,
                    stage=stage,
                    data_root=data_root,
                    evidence_dir=case_dir,
                )
                if stage.action == "create":
                    request = case.request.model_copy(
                        update={
                            "output_root": str(scenario_root),
                            "metadata": {
                                **case.request.metadata,
                                "case_id": case.case_id,
                                "experiment_id": manifest.experiment_id,
                                "stage_id": stage.stage_id,
                                "idempotency_key": f"{manifest.experiment_id}:{case.case_id}",
                            },
                        }
                    )
                    response = _post_json(api_base_url, "/api/v2/scenario-runs", request.model_dump(mode="json"), timeout=30)
                    scenario_id = str(response["scenario_id"])
                    final = _wait_for_scenario(
                        api_base_url,
                        scenario_id,
                        output_root=scenario_root,
                        timeout_seconds=timeout_seconds,
                        poll_seconds=poll_seconds,
                    )
                else:
                    if not scenario_id:
                        raise RuntimeError(f"{case.case_id}/{stage.stage_id} cannot resume without a scenario id")
                    response = _post_json(
                        api_base_url,
                        f"/api/v2/scenario-runs/{scenario_id}/resume",
                        None,
                        params={"retry_failed": str(stage.retry_failed).lower()},
                        timeout=timeout_seconds,
                    )
                    final = _wait_for_scenario(
                        api_base_url,
                        scenario_id,
                        output_root=scenario_root,
                        timeout_seconds=timeout_seconds,
                        poll_seconds=poll_seconds,
                    )
                summary_path = Path(str(final.get("output_dir") or "")) / "scenario_summary.json"
                summary_snapshot_path = case_dir / f"scenario_summary_{stage.stage_id}.json"
                summary_snapshot_path.write_text(
                    json.dumps(final, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                record = {
                    "case_id": case.case_id,
                    "stage_id": stage.stage_id,
                    "action": stage.action,
                    "scenario_id": scenario_id,
                    "api_response": response,
                    "summary_path": str(summary_snapshot_path.resolve()),
                    "runtime_summary_path": str(summary_path.resolve()),
                    "summary_phase": final.get("phase"),
                    "prepared_inputs": prepared,
                }
                (case_dir / f"api_{stage.stage_id}.json").write_text(
                    json.dumps(record, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                stage_records.append(record)
            case_results.append(
                evaluate_case_contract(
                    case=case,
                    stage_records=stage_records,
                    experiment_dir=experiment_dir,
                )
            )

        seed_payload = build_seed_manifest_payload()
        seed_hash = str(seed_payload["metadata"]["content_hash"])
        runtime_settings_hash = _runtime_settings_hash(manifest, runtime_dir)
        metric_path = (REPO_ROOT / manifest.metric_definition_path).resolve()
        metric_definition_hash = sha256_file(metric_path)
        freeze_path = experiment_dir / "experiment_evidence_manifest.json"
        result = {
            "experiment_id": manifest.experiment_id,
            "manifest_path": str(manifest_path.resolve()),
            "experiment_dir": str(experiment_dir),
            "case_results": case_results,
            "all_cases_passed": all(item.get("passed") is True for item in case_results),
            "evidence_manifest_path": str(freeze_path.resolve()),
        }
        (experiment_dir / "experiment_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        evidence_manifest = freeze_experiment(
            experiment_id=manifest.experiment_id,
            output_dir=experiment_dir,
            output_json=freeze_path,
            commit_sha=_git_commit_sha(),
            seed_hash=seed_hash,
            runtime_settings_hash=runtime_settings_hash,
            metric_definition_hash=metric_definition_hash,
            external_inputs=external_inputs,
        )
        result["evidence_manifest"] = evidence_manifest.model_dump(mode="json")
        return result
    finally:
        if server is not None:
            _stop_server(server)


def _start_server(
    *,
    api_base_url: str,
    port: int,
    data_root: Path,
    downloads_root: Path,
    runs_root: Path,
    scenario_root: Path,
    experiment_dir: Path,
):
    env = os.environ.copy()
    env.update(
        _server_environment_overrides(
            data_root=data_root,
            downloads_root=downloads_root,
            runs_root=runs_root,
            scenario_root=scenario_root,
            experiment_dir=experiment_dir,
            inherited_pythonpath=env.get("PYTHONPATH", ""),
        )
    )
    log_path = experiment_dir / "runtime" / "api_server.log"
    log_handle = log_path.open("w", encoding="utf-8")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.app:create_app", "--factory", "--host", "127.0.0.1", "--port", str(port)],
        cwd=REPO_ROOT,
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    return process, f"http://127.0.0.1:{port}"


def runtime_dir_for_env(experiment_dir: Path) -> Path:
    return Path(experiment_dir) / "runtime"


def _server_environment_overrides(
    *,
    data_root: Path,
    downloads_root: Path,
    runs_root: Path,
    scenario_root: Path,
    experiment_dir: Path,
    inherited_pythonpath: str,
) -> dict[str, str]:
    return {
        "GEOFUSION_KG_BACKEND": "memory",
        "GEOFUSION_LLM_PROVIDER": "mock",
        "GEOFUSION_CELERY_EAGER": "1",
        "GEOFUSION_SCENARIO_CHILD_MAX_WORKERS": "1",
        "GEOFUSION_LOCAL_ONLY": "1",
        "GEOFUSION_DISABLE_ARTIFACT_REUSE": "1",
        "GEOFUSION_DATA_REPOSITORY_ROOT": str(data_root),
        "GEOFUSION_DOWNLOAD_ROOT": str(downloads_root),
        "GEOFUSION_OUTPUT_ROOT": str(runtime_dir_for_env(experiment_dir) / "outputs"),
        "GEOFUSION_RUNS_ROOT": str(runs_root),
        "GEOFUSION_SCENARIO_OUTPUT_ROOT": str(scenario_root),
        "PYTHONPATH": str(REPO_ROOT) + os.pathsep + inherited_pythonpath,
    }


def _stop_server(process: subprocess.Popen[Any]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def _wait_for_api(api_base_url: str, *, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = ""
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{api_base_url}/api/v2/scenario-runs?limit=1", timeout=5)
            if response.status_code == 200:
                return
            last_error = f"HTTP {response.status_code}: {response.text[:300]}"
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(1)
    raise RuntimeError(f"Scenario API did not become ready: {last_error}")


def _post_json(
    api_base_url: str,
    path: str,
    payload: dict[str, Any] | None,
    *,
    params: dict[str, str] | None = None,
    timeout: float,
) -> dict[str, Any]:
    response = httpx.post(
        f"{api_base_url}{path}",
        json=payload,
        params=params,
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"{path} failed with HTTP {response.status_code}: {response.text[:1000]}")
    value = response.json()
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} returned a non-object payload")
    return value


def _wait_for_scenario(
    api_base_url: str,
    scenario_id: str,
    *,
    output_root: Path,
    timeout_seconds: float,
    poll_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    terminal = {"succeeded", "partial", "failed", "partial_provisional", "superseded", "retry_exhausted"}
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            response = httpx.get(
                f"{api_base_url}/api/v2/scenario-runs/{scenario_id}",
                params={"output_root": str(output_root)},
                timeout=30,
            )
            if response.status_code == 200:
                payload = response.json()
                summary = payload.get("summary") if isinstance(payload, dict) else {}
                if isinstance(summary, dict):
                    last = summary
                    if str(summary.get("phase")) in terminal:
                        return summary
        except httpx.HTTPError:
            # A synchronous child acquisition can temporarily starve the single API worker.
            # The persisted checkpoint remains authoritative; retry the inspection request.
            pass
        time.sleep(poll_seconds)
    raise TimeoutError(f"Scenario {scenario_id} did not reach a terminal phase; last={last}")


def _write_runtime_metadata(
    manifest: ContractExperimentManifest,
    manifest_path: Path,
    experiment_dir: Path,
    runtime_dir: Path,
) -> None:
    runtime_environment_path = experiment_dir / "runtime_environment.json"
    runtime_environment = _runtime_environment_snapshot(
        experiment_dir=experiment_dir,
        runtime_dir=runtime_dir,
    )
    runtime_environment_path.write_text(
        json.dumps(runtime_environment, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    git_state = _git_worktree_state()
    metadata = {
        "experiment_id": manifest.experiment_id,
        "manifest_path": str(manifest_path.resolve()),
        "data_boundary": manifest.data_boundary,
        "runtime": manifest.runtime,
        "execution": _execution_settings(),
        "api_execution": "/api/v2/scenario-runs",
        "runtime_dir": str(runtime_dir.resolve()),
        "git_commit_sha": _git_commit_sha(),
        "git_worktree_dirty": git_state["dirty"],
        "git_worktree_diff_sha256": git_state["diff_sha256"],
        "git_status_porcelain": git_state["status_porcelain"],
        "runtime_environment_path": str(runtime_environment_path.resolve()),
        "runtime_environment_sha256": sha256_file(runtime_environment_path),
    }
    (experiment_dir / "runtime_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _runtime_settings_hash(manifest: ContractExperimentManifest, runtime_dir: Path) -> str:
    runtime_environment_path = runtime_dir.parent / "runtime_environment.json"
    payload = {
        "manifest_runtime": manifest.runtime,
        "execution": _execution_settings(),
        "runtime_dir": str(runtime_dir.resolve()),
        "runtime_environment_sha256": (
            sha256_file(runtime_environment_path) if runtime_environment_path.exists() else "missing"
        ),
    }
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _execution_settings() -> dict[str, Any]:
    return {
        "kg_backend": "memory",
        "llm_provider": "mock",
        "celery_eager": True,
        "scenario_child_max_workers": 1,
        "local_only": True,
        "artifact_reuse_disabled": True,
    }


def _runtime_environment_snapshot(*, experiment_dir: Path, runtime_dir: Path) -> dict[str, Any]:
    packages: dict[str, str] = {}
    for distribution in importlib.metadata.distributions():
        name = str(distribution.metadata.get("Name") or "").strip()
        if name:
            packages[name.casefold()] = distribution.version

    geospatial_versions: dict[str, Any] = {
        name: _distribution_version(name)
        for name in ("fiona", "geopandas", "gdal", "pyogrio", "pyproj", "rasterio", "shapely")
    }
    try:
        import pyproj

        geospatial_versions["proj_runtime"] = pyproj.proj_version_str
    except Exception as exc:  # noqa: BLE001
        geospatial_versions["proj_runtime_error"] = f"{type(exc).__name__}: {exc}"
    try:
        import fiona

        geospatial_versions["gdal_runtime"] = str(fiona.gdal_version)
    except Exception as exc:  # noqa: BLE001
        geospatial_versions["gdal_runtime_error"] = f"{type(exc).__name__}: {exc}"

    requirements_path = REPO_ROOT / "requirements.txt"
    key_environment_names = (
        "GDAL_DATA",
        "GDAL_DRIVER_PATH",
        "PROJ_DATA",
        "PROJ_LIB",
        "PYTHONHASHSEED",
        "PYTHONUTF8",
    )
    server_environment = _server_environment_overrides(
        data_root=runtime_dir / "data_repository",
        downloads_root=runtime_dir / "downloads",
        runs_root=runtime_dir / "runs",
        scenario_root=runtime_dir / "scenario_outputs",
        experiment_dir=experiment_dir,
        inherited_pythonpath=os.environ.get("PYTHONPATH", ""),
    )
    return {
        "captured_at_unix_seconds": time.time(),
        "python": {
            "executable": sys.executable,
            "version": sys.version,
            "implementation": platform.python_implementation(),
            "compiler": platform.python_compiler(),
        },
        "operating_system": {
            "os_name": os.name,
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "platform": platform.platform(),
            "timezone": list(time.tzname),
        },
        "geospatial_runtime": geospatial_versions,
        "python_distributions": [
            {"name": name, "version": version}
            for name, version in sorted(packages.items())
        ],
        "requirements": {
            "path": str(requirements_path.resolve()),
            "sha256": sha256_file(requirements_path) if requirements_path.exists() else None,
        },
        "key_environment": {name: os.environ.get(name) for name in key_environment_names},
        "server_environment": server_environment,
    }


def _distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _git_commit_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _git_worktree_state() -> dict[str, Any]:
    try:
        status = subprocess.check_output(
            ["git", "status", "--porcelain=v1", "--untracked-files=normal"],
            cwd=REPO_ROOT,
            text=True,
        )
        diff = subprocess.check_output(["git", "diff", "--binary", "HEAD", "--"], cwd=REPO_ROOT)
    except Exception:  # noqa: BLE001
        return {"dirty": True, "diff_sha256": "unknown", "status_porcelain": "unavailable"}
    dirty = bool(status.strip())
    digest_payload = status.encode("utf-8") + b"\0" + diff
    return {
        "dirty": dirty,
        "diff_sha256": hashlib.sha256(digest_payload).hexdigest() if dirty else "",
        "status_porcelain": status.splitlines(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run declarative real-data contract cases through the Scenario API.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--experiment-dir", required=True)
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8019")
    parser.add_argument("--server-port", type=int, default=8019)
    parser.add_argument("--no-server", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    args = parser.parse_args(argv)
    result = run_manifest(
        manifest_path=Path(args.manifest),
        experiment_dir=Path(args.experiment_dir),
        api_base_url=args.api_base_url,
        start_server=not args.no_server,
        server_port=args.server_port,
        poll_seconds=args.poll_seconds,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("all_cases_passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
