from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.tile_partition_service import TilePartitionService


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Submit a task-driven natural-language region run and wait for the final result."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL.")
    parser.add_argument("--query", required=True, help="Natural-language region request.")
    parser.add_argument(
        "--job-type",
        choices=["building", "road", "water", "poi"],
        required=True,
        help="Fusion job type.",
    )
    parser.add_argument("--target-crs", default="", help="Optional explicit target CRS override.")
    parser.add_argument(
        "--preferred-pattern-id",
        default="",
        help="Optional workflow pattern id override for bounded smoke verification.",
    )
    parser.add_argument("--timeout", type=float, default=1200.0, help="Overall timeout in seconds.")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Polling interval in seconds.")
    parser.add_argument("--output-json", default="", help="Optional path to save the final inspection payload.")
    parser.add_argument(
        "--evidence-dir",
        default="",
        help="Optional directory to write Track B smoke evidence bundle outputs.",
    )
    return parser.parse_args(argv)


def build_create_run_form(args: argparse.Namespace) -> dict[str, str]:
    payload = {
        "job_type": args.job_type,
        "trigger_type": "user_query",
        "trigger_content": args.query,
        "input_strategy": "task_driven_auto",
        "field_mapping": "{}",
        "debug": "false",
    }
    if args.target_crs:
        payload["target_crs"] = args.target_crs
    if args.preferred_pattern_id:
        payload["preferred_pattern_id"] = args.preferred_pattern_id
    return payload


def _json_request(
    method: str,
    url: str,
    *,
    form_data: dict[str, str] | None = None,
    timeout_sec: float = 30.0,
) -> Any:
    data = None
    headers: dict[str, str] = {}
    if form_data is not None:
        data = urllib.parse.urlencode(form_data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {detail}") from exc


def _extract_event(events: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    for event in events:
        if event.get("kind") == kind:
            return event
    return None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _claim_state_for_job_type(job_type: str) -> str:
    return "bounded_supported" if job_type == "poi" else "runtime_supported"


def _resolved_aoi_payload(inspection: dict[str, Any]) -> dict[str, Any]:
    audit_events = inspection.get("audit_events", [])
    source_event = _extract_event(audit_events, "task_inputs_resolved")
    if source_event is not None:
        source_details = source_event.get("details", {})
        if isinstance(source_details, dict):
            resolved_aoi = source_details.get("resolved_aoi")
            if isinstance(resolved_aoi, dict) and resolved_aoi.get("bbox"):
                return dict(resolved_aoi)
    aoi_event = _extract_event(audit_events, "aoi_resolved")
    if aoi_event is not None:
        details = aoi_event.get("details", {})
        if isinstance(details, dict) and details.get("bbox"):
            return dict(details)
    plan_aoi = inspection.get("plan", {}).get("context", {}).get("intent", {}).get("resolved_aoi")
    if isinstance(plan_aoi, dict):
        return dict(plan_aoi)
    return {}


def _retrieved_source_profiles(inspection: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = inspection.get("plan", {}).get("context", {}).get("retrieval", {}).get("data_sources", [])
    if not isinstance(profiles, list):
        return []
    return [dict(item) for item in profiles if isinstance(item, dict)]


def _selected_source_details(inspection: dict[str, Any]) -> dict[str, Any]:
    source_event = _extract_event(inspection.get("audit_events", []), "task_inputs_resolved")
    if source_event is None:
        return {}
    details = source_event.get("details", {})
    return dict(details) if isinstance(details, dict) else {}


def _selected_source_profile(inspection: dict[str, Any], selected_source_id: str) -> dict[str, Any] | None:
    for profile in _retrieved_source_profiles(inspection):
        if str(profile.get("source_id") or "") == selected_source_id:
            return profile
    return None


def _build_selected_sources_payload(inspection: dict[str, Any]) -> dict[str, Any]:
    source_details = _selected_source_details(inspection)
    selected_source_id = str(source_details.get("selected_source_id") or source_details.get("source_id") or "")
    selected_profile = _selected_source_profile(inspection, selected_source_id) or {}
    metadata = selected_profile.get("metadata", {}) if isinstance(selected_profile, dict) else {}
    component_source_ids = metadata.get("component_source_ids", [])
    if not isinstance(component_source_ids, list):
        component_source_ids = []
    return {
        "run_id": inspection.get("run", {}).get("run_id"),
        "job_type": inspection.get("run", {}).get("job_type"),
        "requested_source_id": source_details.get("requested_source_id"),
        "selected_source_id": selected_source_id or None,
        "source_id": source_details.get("source_id"),
        "fallback_from_source_id": source_details.get("fallback_from_source_id"),
        "source_mode": source_details.get("source_mode"),
        "cache_hit": bool(source_details.get("cache_hit", False)),
        "target_crs": source_details.get("target_crs") or inspection.get("run", {}).get("target_crs"),
        "component_source_ids": component_source_ids,
        "component_coverage": source_details.get("component_coverage") or {},
        "selected_profile": selected_profile or None,
    }


def _build_source_profile_snapshot(inspection: dict[str, Any]) -> dict[str, Any]:
    selected_sources = _build_selected_sources_payload(inspection)
    profiles = _retrieved_source_profiles(inspection)
    return {
        "snapshot_mode": "task_driven_retrieval_snapshot",
        "run_id": inspection.get("run", {}).get("run_id"),
        "job_type": inspection.get("run", {}).get("job_type"),
        "selected_source_id": selected_sources.get("selected_source_id"),
        "profile_count": len(profiles),
        "profiles": profiles,
        "selected_profile": selected_sources.get("selected_profile"),
    }


def _build_tile_manifest_payload(inspection: dict[str, Any]) -> dict[str, Any]:
    resolved_aoi = _resolved_aoi_payload(inspection)
    bbox = resolved_aoi.get("bbox")
    target_crs = (
        _selected_source_details(inspection).get("target_crs")
        or inspection.get("run", {}).get("target_crs")
        or "EPSG:4326"
    )
    if not isinstance(bbox, list) or len(bbox) != 4:
        return {
            "manifest_mode": "single_request_aoi",
            "tile_count": 0,
            "bbox": [],
            "bbox_crs": "EPSG:4326",
            "working_crs": target_crs,
            "tiles": [],
        }
    manifest = TilePartitionService(
        tile_width_m=10_000_000.0,
        tile_height_m=10_000_000.0,
        overlap_m=0.0,
    ).partition_bbox(
        bbox=tuple(float(value) for value in bbox),
        bbox_crs="EPSG:4326",
        working_crs=str(target_crs),
    )
    payload = manifest.to_dict()
    payload["manifest_mode"] = "single_request_aoi"
    payload["tile_count"] = len(manifest.tiles)
    return payload


def _build_inspection_summary(inspection: dict[str, Any]) -> dict[str, Any]:
    run = inspection.get("run", {})
    job_type = str(run.get("job_type") or "")
    resolved_aoi = _resolved_aoi_payload(inspection)
    selected_sources = _build_selected_sources_payload(inspection)
    tile_manifest = _build_tile_manifest_payload(inspection)
    output_schema_event = _extract_event(inspection.get("audit_events", []), "output_schema_validated")
    output_schema = output_schema_event.get("details", {}) if output_schema_event is not None else {}
    artifact = inspection.get("artifact", {}) or run.get("artifact", {})
    return {
        "mode": "task_driven_smoke_inspection",
        "claim_state": _claim_state_for_job_type(job_type),
        "run_type": "bounded_smoke_utility",
        "job_type": job_type,
        "run_id": run.get("run_id"),
        "workflow_id": inspection.get("kg_path_trace", {}).get("workflow_id"),
        "selected_pattern_id": inspection.get("kg_path_trace", {}).get("selected_pattern_id"),
        "bbox": resolved_aoi.get("bbox", []),
        "target_crs": run.get("target_crs"),
        "tile_count": tile_manifest.get("tile_count", 0),
        "selected_sources": {
            "requested_source_id": selected_sources.get("requested_source_id"),
            "selected_source_id": selected_sources.get("selected_source_id"),
            "component_source_ids": selected_sources.get("component_source_ids", []),
        },
        "evidence": {
            "inspection": "inspection.json",
            "source_profile_snapshot": "source_profile_snapshot.json",
            "selected_sources": "selected_sources.json",
            "tile_manifest": "tile_manifest.json",
            "artifact_path": artifact.get("path"),
        },
        "artifact_metrics": output_schema,
        "operator_readable_summary": {
            "aoi_display_name": resolved_aoi.get("display_name"),
            "selected_source_id": selected_sources.get("selected_source_id"),
            "source_mode": selected_sources.get("source_mode"),
            "cache_hit": selected_sources.get("cache_hit"),
            "component_source_count": len(selected_sources.get("component_source_ids", [])),
            "artifact_validity": bool(output_schema.get("artifact_validity", False)),
            "artifact_path": artifact.get("path"),
            "tile_count": tile_manifest.get("tile_count", 0),
        },
        "large_area_runtime": inspection.get("large_area_runtime", {}),
        "source_semantic_contract": inspection.get("source_semantic_contract", {}),
        "documents": inspection.get("documents", {}),
    }


def _write_evidence_bundle(evidence_dir: Path, inspection: dict[str, Any]) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    _write_json(evidence_dir / "inspection.json", inspection)
    _write_json(evidence_dir / "selected_sources.json", _build_selected_sources_payload(inspection))
    _write_json(evidence_dir / "source_profile_snapshot.json", _build_source_profile_snapshot(inspection))
    _write_json(evidence_dir / "tile_manifest.json", _build_tile_manifest_payload(inspection))
    _write_json(evidence_dir / "inspection_summary.json", _build_inspection_summary(inspection))


def run_smoke(
    *,
    base_url: str,
    query: str,
    job_type: str,
    target_crs: str,
    preferred_pattern_id: str,
    timeout_sec: float,
    poll_interval_sec: float,
) -> dict[str, Any]:
    create_url = urllib.parse.urljoin(base_url.rstrip("/") + "/", "api/v2/runs")
    create_payload = {
        "job_type": job_type,
        "trigger_type": "user_query",
        "trigger_content": query,
        "input_strategy": "task_driven_auto",
        "field_mapping": "{}",
        "debug": "false",
    }
    if target_crs:
        create_payload["target_crs"] = target_crs
    if preferred_pattern_id:
        create_payload["preferred_pattern_id"] = preferred_pattern_id
    created = _json_request("POST", create_url, form_data=create_payload, timeout_sec=timeout_sec)
    run_id = created["run_id"]

    deadline = time.time() + timeout_sec
    status_url = urllib.parse.urljoin(base_url.rstrip("/") + "/", f"api/v2/runs/{run_id}")
    inspection_url = urllib.parse.urljoin(base_url.rstrip("/") + "/", f"api/v2/runs/{run_id}/inspection")

    while time.time() < deadline:
        status = _json_request("GET", status_url, timeout_sec=30.0)
        if status["phase"] == "failed":
            raise RuntimeError(f"Run failed: {status.get('error')}")
        if status["phase"] == "succeeded":
            inspection = _json_request("GET", inspection_url, timeout_sec=30.0)
            return {
                "run_id": run_id,
                "status": status,
                "inspection": inspection,
            }
        time.sleep(max(0.2, poll_interval_sec))
    raise TimeoutError(f"Timed out waiting for run {run_id}")


def _print_summary(result: dict[str, Any]) -> None:
    def _safe_text(value: object) -> str:
        text = "" if value is None else str(value)
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        return text.encode(encoding, errors="backslashreplace").decode(encoding, errors="ignore")

    inspection = result["inspection"]
    audit_events = inspection.get("audit_events", [])
    aoi_event = _extract_event(audit_events, "aoi_resolved")
    source_event = _extract_event(audit_events, "task_inputs_resolved")
    artifact = inspection.get("artifact", {})

    print(f"run_id={result['run_id']}")
    print(f"phase={result['status']['phase']}")
    if aoi_event is not None:
        details = aoi_event.get("details", {})
        print(f"aoi={_safe_text(details.get('display_name'))}")
        print(f"aoi_country={_safe_text(details.get('country_code'))}")
    if source_event is not None:
        details = source_event.get("details", {})
        print(f"source_id={_safe_text(details.get('source_id'))}")
        print(f"source_mode={_safe_text(details.get('source_mode'))}")
    print(f"artifact_path={_safe_text(artifact.get('path'))}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_smoke(
        base_url=args.base_url,
        query=args.query,
        job_type=args.job_type,
        target_crs=args.target_crs,
        preferred_pattern_id=args.preferred_pattern_id,
        timeout_sec=args.timeout,
        poll_interval_sec=args.poll_interval,
    )
    if args.output_json:
        output_path = Path(args.output_json).resolve()
        _write_json(output_path, result["inspection"])
    if args.evidence_dir:
        _write_evidence_bundle(Path(args.evidence_dir).resolve(), result["inspection"])
    _print_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
