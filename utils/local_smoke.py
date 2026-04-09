from __future__ import annotations

import io
import json
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


def build_run_request_from_case(case_dir: Path) -> dict[str, Any]:
    manifest_path = case_dir / "case.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    trigger = payload["trigger"]
    osm_zip_path = case_dir / payload["osm_zip"]
    ref_zip_path = case_dir / payload["ref_zip"]
    if not osm_zip_path.exists():
        raise FileNotFoundError(f"OSM zip not found: {osm_zip_path}")
    if not ref_zip_path.exists():
        raise FileNotFoundError(f"Reference zip not found: {ref_zip_path}")

    return {
        "case_id": payload.get("case_id", case_dir.name),
        "form": {
            "job_type": payload["job_type"],
            "trigger_type": trigger["type"],
            "trigger_content": trigger["content"],
            "disaster_type": trigger.get("disaster_type") or "",
            "spatial_extent": trigger.get("spatial_extent") or "",
            "temporal_start": trigger.get("temporal_start") or "",
            "temporal_end": trigger.get("temporal_end") or "",
            "target_crs": payload.get("target_crs", "EPSG:32643"),
            "field_mapping": json.dumps(payload.get("field_mapping", {}), ensure_ascii=False),
            "debug": str(bool(payload.get("debug", False))).lower(),
        },
        "osm_zip_path": osm_zip_path,
        "ref_zip_path": ref_zip_path,
        "expected_plan_checks": payload.get("expected_plan_checks", {}),
        "artifact_checks": payload.get("artifact_checks", {}),
    }


def _encode_multipart(form: dict[str, str], file_fields: dict[str, Path]) -> tuple[bytes, str]:
    boundary = f"----GeoFusionSmoke{int(time.time() * 1000)}"
    lines: list[bytes] = []

    for key, value in form.items():
        lines.extend(
            [
                f"--{boundary}".encode("utf-8"),
                f'Content-Disposition: form-data; name="{key}"'.encode("utf-8"),
                b"",
                str(value).encode("utf-8"),
            ]
        )

    for field_name, path in file_fields.items():
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        lines.extend(
            [
                f"--{boundary}".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="{field_name}"; filename="{path.name}"'
                ).encode("utf-8"),
                f"Content-Type: {content_type}".encode("utf-8"),
                b"",
                path.read_bytes(),
            ]
        )

    lines.append(f"--{boundary}--".encode("utf-8"))
    lines.append(b"")
    return b"\r\n".join(lines), boundary


def _json_request(
    method: str,
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout_sec: float = 30.0,
) -> Any:
    request = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {detail}") from exc


def _remaining_timeout_sec(deadline: float) -> float:
    return max(0.1, deadline - time.time())


def run_local_v2_smoke(case_dir: Path, *, base_url: str = "http://127.0.0.1:8000", timeout_sec: float = 180.0) -> dict[str, Any]:
    smoke_payload = build_run_request_from_case(case_dir)
    body, boundary = _encode_multipart(
        smoke_payload["form"],
        {
            "osm_zip": smoke_payload["osm_zip_path"],
            "ref_zip": smoke_payload["ref_zip_path"],
        },
    )

    deadline = time.time() + timeout_sec
    create_resp = _json_request(
        "POST",
        urllib.parse.urljoin(base_url.rstrip("/") + "/", "api/v2/runs"),
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        timeout_sec=_remaining_timeout_sec(deadline),
    )
    run_id = create_resp["run_id"]

    run_url = urllib.parse.urljoin(base_url.rstrip("/") + "/", f"api/v2/runs/{run_id}")
    plan_url = urllib.parse.urljoin(base_url.rstrip("/") + "/", f"api/v2/runs/{run_id}/plan")
    artifact_url = urllib.parse.urljoin(base_url.rstrip("/") + "/", f"api/v2/runs/{run_id}/artifact")

    while time.time() < deadline:
        status = _json_request("GET", run_url, timeout_sec=_remaining_timeout_sec(deadline))
        if status["phase"] == "failed":
            raise RuntimeError(f"Smoke run failed: {status.get('error')}")
        if status["phase"] == "succeeded":
            plan = _json_request("GET", plan_url, timeout_sec=_remaining_timeout_sec(deadline))["plan"]
            artifact_request = urllib.request.Request(artifact_url, method="GET")
            with urllib.request.urlopen(artifact_request, timeout=_remaining_timeout_sec(deadline)) as response:
                artifact_bytes = response.read()
            with zipfile.ZipFile(io.BytesIO(artifact_bytes), "r") as zf:
                artifact_entries = zf.namelist()
            return {
                "run_id": run_id,
                "status": status,
                "plan": plan,
                "artifact_size": len(artifact_bytes),
                "artifact_entries": artifact_entries,
            }
        time.sleep(1.0)

    raise TimeoutError(f"Timed out waiting for local smoke run: {run_id}")


def validate_smoke_result(
    result: dict[str, Any],
    *,
    expected_plan_checks: dict[str, Any] | None = None,
    artifact_checks: dict[str, Any] | None = None,
) -> None:
    expected_plan_checks = expected_plan_checks or {}
    artifact_checks = artifact_checks or {}
    plan = result["plan"]

    pattern_hint = expected_plan_checks.get("pattern_hint")
    if pattern_hint:
        candidates = plan.get("context", {}).get("retrieval", {}).get("candidate_patterns", [])
        pattern_ids = [candidate.get("pattern_id") for candidate in candidates]
        if pattern_hint not in pattern_ids:
            raise AssertionError(f"Expected pattern hint {pattern_hint!r}, got {pattern_ids!r}")

    required_algorithms = expected_plan_checks.get("required_algorithms", [])
    if required_algorithms:
        algorithm_ids: list[str] = []
        for task in plan.get("tasks", []):
            if not isinstance(task, dict):
                continue
            primary = task.get("algorithm_id")
            if primary:
                algorithm_ids.append(str(primary))
            alternatives = task.get("alternatives", [])
            if isinstance(alternatives, list):
                algorithm_ids.extend(str(algo) for algo in alternatives if algo)

        retrieval_algorithms = plan.get("context", {}).get("retrieval", {}).get("algorithms", {})
        if isinstance(retrieval_algorithms, dict):
            algorithm_ids.extend(str(algo_id) for algo_id in retrieval_algorithms.keys())

        missing = [algo for algo in required_algorithms if algo not in algorithm_ids]
        if missing:
            raise AssertionError(f"Missing expected algorithms: {missing!r}")

    required_output_type = expected_plan_checks.get("required_output_type")
    if required_output_type:
        output_types = [
            task.get("output", {}).get("data_type_id")
            for task in plan.get("tasks", [])
            if isinstance(task, dict)
        ]
        if required_output_type not in output_types and required_output_type not in str(plan.get("expected_output", "")):
            raise AssertionError(
                f"Expected output type {required_output_type!r}, got outputs {output_types!r}"
            )

    required_suffixes = artifact_checks.get("required_suffixes", [])
    if required_suffixes:
        entries = result.get("artifact_entries", [])
        missing_suffixes = [suffix for suffix in required_suffixes if not any(name.endswith(suffix) for name in entries)]
        if missing_suffixes:
            raise AssertionError(f"Artifact is missing required suffixes: {missing_suffixes!r}")
