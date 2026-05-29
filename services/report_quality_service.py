from __future__ import annotations

from typing import Any

from schemas.agent import RunEvent


def build_report_quality_summary(
    *,
    job_type: str,
    audit_events: list[RunEvent],
    source_semantic_contract: dict[str, Any] | None,
    artifact_metrics: dict[str, Any],
    recovery_evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    contract = source_semantic_contract or {}
    recovery = recovery_evidence or {}
    height_sources = _height_raster_source_ids(contract=contract, audit_events=audit_events)
    source_download = _source_download_summary(audit_events)
    poi_boundary = _poi_boundary_summary(job_type=job_type, audit_events=audit_events, contract=contract)
    recovery_summary = _recovery_summary(recovery)
    checks = [
        bool(artifact_metrics.get("artifact_validity")),
        bool(source_download["has_task_inputs_resolved"]),
        bool(height_sources) if job_type == "building" else True,
        poi_boundary["bounded"] if job_type == "poi" else True,
        recovery_summary["operator_action_available"] or not recovery_summary["recoverable"],
    ]
    score = sum(1 for item in checks if item) / len(checks)

    return {
        "evidence_readiness_score": round(score, 3),
        "target_capability": {
            "target_1_unattended": {"supported": source_download["has_task_inputs_resolved"]},
            "target_2_building_height_raster": {
                "supported": job_type == "building",
                "raster_participated": bool(height_sources),
                "source_ids": height_sources,
            },
            "target_5_bounded_poi": poi_boundary,
            "target_7_auto_download": source_download,
            "target_8_report": {"supported": True, "sections": ["process", "result", "quality", "boundary"]},
            "target_9_recovery": recovery_summary,
        },
        "quality_boundary": {
            "poi": "bounded AOI OSM + GNS/GeoNames fusion; unbounded POI entity alignment is unsupported",
            "self_evolution": "bounded policy hints only; no automatic model, policy, or source catalog mutation",
            "download": "provider availability is external; manifests record cache, retry, and fault evidence",
        },
    }


def _height_raster_source_ids(*, contract: dict[str, Any], audit_events: list[RunEvent]) -> list[str]:
    source_ids: set[str] = set()
    height_policy = contract.get("height_policy")
    if isinstance(height_policy, dict):
        raster_sources = height_policy.get("raster_height_sources")
        if isinstance(raster_sources, dict):
            source_ids.update(str(key) for key in raster_sources if key)
    for event in audit_events:
        coverage = event.details.get("component_coverage") if event.kind == "task_inputs_resolved" else None
        if not isinstance(coverage, dict):
            continue
        for source_id, payload in coverage.items():
            if "raster" not in str(source_id) and "height" not in str(source_id):
                continue
            if isinstance(payload, dict) and (payload.get("path") or payload.get("raster_profile")):
                source_ids.add(str(source_id))
    return sorted(source_ids)


def _source_download_summary(audit_events: list[RunEvent]) -> dict[str, Any]:
    resolved = [event for event in audit_events if event.kind == "task_inputs_resolved"]
    modes = sorted(
        {
            str(event.details.get("source_mode"))
            for event in resolved
            if event.details.get("source_mode") is not None
        }
    )
    manifest_paths = [
        str(event.details.get("source_materialization_manifest_path"))
        for event in resolved
        if event.details.get("source_materialization_manifest_path")
    ]
    return {
        "supported": bool(resolved),
        "has_task_inputs_resolved": bool(resolved),
        "source_modes": modes,
        "manifest_paths": manifest_paths,
        "cache_hit_observed": any(bool(event.details.get("cache_hit")) for event in resolved),
    }


def _poi_boundary_summary(*, job_type: str, audit_events: list[RunEvent], contract: dict[str, Any]) -> dict[str, Any]:
    source_ids: set[str] = set()
    aoi_bound: list[float] | None = None
    for event in audit_events:
        if event.kind != "task_inputs_resolved":
            continue
        coverage = event.details.get("component_coverage")
        if isinstance(coverage, dict):
            source_ids.update(str(key) for key in coverage)
        resolved_aoi = event.details.get("resolved_aoi")
        if isinstance(resolved_aoi, dict) and isinstance(resolved_aoi.get("bbox"), list):
            aoi_bound = [float(value) for value in resolved_aoi["bbox"]]
    component_ids = contract.get("component_source_ids")
    if isinstance(component_ids, list):
        source_ids.update(str(item) for item in component_ids)
    bounded = job_type != "poi" or ({"raw.osm.poi", "raw.gns.poi"}.issubset(source_ids) and aoi_bound is not None)
    return {
        "supported": job_type == "poi",
        "bounded": bounded,
        "aoi_bound": aoi_bound,
        "source_ids": sorted(source_ids),
        "unsupported_boundary": "unbounded POI entity alignment is unsupported",
    }


def _recovery_summary(recovery: dict[str, Any]) -> dict[str, Any]:
    recoverable = bool(recovery.get("recoverable", False))
    operator_action = str(recovery.get("operator_action") or "").strip()
    return {
        "supported": True,
        "recoverable": recoverable,
        "recovery_action": recovery.get("recovery_action", "none"),
        "operator_action_available": bool(operator_action),
        "operator_action": operator_action or None,
        "failure_category": recovery.get("failure_category"),
    }
