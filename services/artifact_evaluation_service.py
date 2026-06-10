from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import pyogrio
from pyproj import Transformer
from shapely.validation import explain_validity

from services.kg_path_trace_service import build_kg_path_trace


_DEFAULT_SLIVER_AREA_THRESHOLD_SQ_M = 1.0
_DEFAULT_METADATA_ONLY_THRESHOLD_BYTES = 512 * 1024 * 1024


def evaluate_vector_artifact(
    shp_path: Path,
    *,
    required_fields: list[str],
    requested_bbox: list[float] | tuple[float, float, float, float] | None = None,
    sliver_area_threshold_sq_m: float = _DEFAULT_SLIVER_AREA_THRESHOLD_SQ_M,
    metadata_only_threshold_bytes: int = _DEFAULT_METADATA_ONLY_THRESHOLD_BYTES,
) -> dict[str, Any]:
    shp_path = Path(shp_path)
    metadata_metrics = _metadata_only_metrics(
        shp_path,
        required_fields=required_fields,
        requested_bbox=requested_bbox,
        metadata_only_threshold_bytes=metadata_only_threshold_bytes,
    )
    if metadata_metrics is not None:
        return metadata_metrics

    frame = gpd.read_file(shp_path)
    missing_fields = [
        field
        for field in required_fields
        if not _has_required_field(field=field, frame=frame, artifact_path=shp_path)
    ]
    metrics = {
        "artifact_validity": shp_path.exists() and not frame.empty and not missing_fields,
        "feature_count": int(len(frame)),
        "crs": str(frame.crs),
        "geometry_types": sorted(str(value) for value in frame.geometry.geom_type.dropna().unique()),
        "missing_fields": missing_fields,
        "bbox": [float(value) for value in frame.to_crs("EPSG:4326").total_bounds] if len(frame) else None,
    }
    if requested_bbox is not None:
        metrics["aoi_consistency"] = _aoi_consistency(metrics.get("bbox"), requested_bbox)
    metrics.update(_geometry_measurements(frame))
    metrics.update(_geometry_quality_metrics(frame, sliver_area_threshold_sq_m=sliver_area_threshold_sq_m))
    return metrics


def _metadata_only_metrics(
    artifact_path: Path,
    *,
    required_fields: list[str],
    requested_bbox: list[float] | tuple[float, float, float, float] | None,
    metadata_only_threshold_bytes: int,
) -> dict[str, Any] | None:
    if metadata_only_threshold_bytes <= 0:
        return None
    if not artifact_path.exists() or artifact_path.stat().st_size < metadata_only_threshold_bytes:
        return None
    try:
        info = pyogrio.read_info(artifact_path)
    except Exception:  # noqa: BLE001
        return None

    feature_count = _metadata_feature_count(info)
    crs = str(info.get("crs") or "")
    geometry_types = _metadata_geometry_types(info)
    raw_fields = info.get("fields")
    fields = {str(field) for field in list(raw_fields) if field is not None} if raw_fields is not None else set()
    missing_fields = [
        field
        for field in required_fields
        if field != "geometry" and not (field == "fid" and artifact_path.suffix.lower() == ".gpkg") and field not in fields
    ]
    bbox = _metadata_bbox_wgs84(info, crs=crs)
    metrics: dict[str, Any] = {
        "artifact_validity": artifact_path.exists() and bool(feature_count) and not missing_fields,
        "feature_count": int(feature_count or 0),
        "crs": crs,
        "geometry_types": geometry_types,
        "missing_fields": missing_fields,
        "bbox": bbox,
        "evaluation_mode": "metadata_only",
        "total_area_sq_km": 0.0,
        "total_length_km": 0.0,
        "duplicate_geometry_rate": 0.0,
        "invalid_geometry_rate": 0.0,
        "source_feature_counts": {},
        "source_contribution_balance": 0.0,
        "zero_length_geometry_count": 0,
        "self_intersection_count": 0,
        "sliver_polygon_count": 0,
        "dangle_endpoint_count": 0,
    }
    if requested_bbox is not None:
        metrics["aoi_consistency"] = _aoi_consistency(metrics.get("bbox"), requested_bbox)
    return metrics


def _metadata_feature_count(info: dict[str, Any]) -> int | None:
    value = info.get("features")
    if value is None:
        return None
    try:
        count = int(value)
    except Exception:  # noqa: BLE001
        return None
    return count if count >= 0 else None


def _metadata_geometry_types(info: dict[str, Any]) -> list[str]:
    value = info.get("geometry_type")
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return sorted(str(item) for item in value if item)
    text = str(value)
    return [text] if text else []


def _metadata_bbox_wgs84(info: dict[str, Any], *, crs: str) -> list[float] | None:
    bounds = info.get("total_bounds")
    if bounds is None:
        return None
    values = [float(value) for value in list(bounds)]
    if len(values) != 4:
        return None
    if not crs or crs.upper() == "EPSG:4326":
        return values
    try:
        transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        minx, miny, maxx, maxy = values
        xs, ys = transformer.transform([minx, minx, maxx, maxx], [miny, maxy, miny, maxy])
        return [float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))]
    except Exception:  # noqa: BLE001
        return values


def _has_required_field(*, field: str, frame: gpd.GeoDataFrame, artifact_path: Path) -> bool:
    if field == "geometry":
        return True
    if field in frame.columns:
        return True
    return field == "fid" and artifact_path.suffix.lower() == ".gpkg"


def _aoi_consistency(artifact_bbox: list[float] | None, requested_bbox) -> dict[str, Any]:
    requested = [float(value) for value in requested_bbox]
    if artifact_bbox is None:
        return {
            "requested_bbox": requested,
            "artifact_intersects_aoi": False,
            "artifact_bbox": None,
        }
    aminx, aminy, amaxx, amaxy = artifact_bbox
    rminx, rminy, rmaxx, rmaxy = requested
    intersects = not (amaxx < rminx or aminx > rmaxx or amaxy < rminy or aminy > rmaxy)
    return {
        "requested_bbox": requested,
        "artifact_intersects_aoi": intersects,
        "artifact_bbox": artifact_bbox,
    }


def evaluate_agentic_run(
    *,
    plan,
    decision_records,
    audit_events,
    durable_learning_summary,
    manual_intervention_count: int,
) -> dict[str, Any]:
    learning_adjustments = [
        _candidate_evidence(candidate).get("metrics", {}).get("learning_adjustment")
        for record in decision_records
        for candidate in getattr(record, "candidates", [])
        if _candidate_evidence(candidate).get("metrics", {}).get("learning_adjustment") is not None
    ]
    numeric_adjustments = [_safe_float(value) for value in learning_adjustments]
    numeric_adjustments = [value for value in numeric_adjustments if value is not None]
    durable_candidate_summaries = [
        _candidate_evidence(candidate).get("meta", {}).get("durable_learning_summary")
        for record in decision_records
        for candidate in getattr(record, "candidates", [])
        if isinstance(_candidate_evidence(candidate).get("meta", {}).get("durable_learning_summary"), dict)
    ]
    summary_patterns = (durable_learning_summary or {}).get("patterns") if isinstance(durable_learning_summary, dict) else None
    if isinstance(summary_patterns, list):
        durable_candidate_summaries.extend(item for item in summary_patterns if isinstance(item, dict))
    quality_pass_rates = [
        _safe_float(summary.get("quality_gate_pass_rate"))
        for summary in durable_candidate_summaries
        if summary.get("quality_gate_pass_rate") is not None
    ]
    quality_pass_rates = [value for value in quality_pass_rates if value is not None]
    return {
        "planning_validity_rate": _planning_validity_rate(plan, audit_events),
        "kg_path_trace_completeness": _kg_path_trace_completeness(plan),
        "decision_trace_completeness": _decision_trace_completeness(decision_records),
        "plan_decision_materialization_consistency": _plan_decision_materialization_consistency(plan, audit_events),
        "source_coverage_resolution_rate": _source_coverage_resolution_rate(audit_events),
        "fallback_success_rate": _fallback_success_rate(audit_events),
        "autonomy_ratio": 1.0 if manual_intervention_count == 0 else 0.0,
        "manual_intervention_count": manual_intervention_count,
        "recovery_success_rate": _recovery_success_rate(audit_events),
        "evidence_completeness_rate": _evidence_completeness_rate(audit_events),
        "self_evolution_record_written": any(event.kind == "durable_learning_recorded" for event in audit_events),
        "self_evolution_hint_available": bool((durable_learning_summary or {}).get("patterns")),
        "self_evolution_hint_used": any(value not in (None, 0, 0.0) for value in numeric_adjustments),
        "self_evolution_policy_adjustment": max(numeric_adjustments, default=0.0),
        "self_evolution_trend": _first_summary_value(durable_candidate_summaries, "trend", default="stable"),
        "self_evolution_quality_gate_pass_rate": max(quality_pass_rates, default=0.0),
        "self_evolution_learning_opportunity_recorded": any(event.kind in {"run_succeeded", "run_failed"} for event in audit_events),
    }


def _geometry_measurements(frame: gpd.GeoDataFrame) -> dict[str, float]:
    if frame.empty:
        return {"total_area_sq_km": 0.0, "total_length_km": 0.0}
    measured = frame
    if measured.crs is not None and measured.crs.is_geographic:
        measured = measured.to_crs("EPSG:3857")
    geom_types = set(str(value) for value in measured.geometry.geom_type.dropna().unique())
    metrics = {"total_area_sq_km": 0.0, "total_length_km": 0.0}
    if geom_types & {"Polygon", "MultiPolygon"}:
        metrics["total_area_sq_km"] = float(measured.geometry.area.sum() / 1_000_000.0)
    if geom_types & {"LineString", "MultiLineString"}:
        metrics["total_length_km"] = float(measured.geometry.length.sum() / 1000.0)
    return metrics


def _geometry_quality_metrics(
    frame: gpd.GeoDataFrame,
    *,
    sliver_area_threshold_sq_m: float = _DEFAULT_SLIVER_AREA_THRESHOLD_SQ_M,
) -> dict[str, Any]:
    if frame.empty:
        return {
            "duplicate_geometry_rate": 0.0,
            "invalid_geometry_rate": 0.0,
            "source_feature_counts": {},
            "source_contribution_balance": 0.0,
            "zero_length_geometry_count": 0,
            "self_intersection_count": 0,
            "sliver_polygon_count": 0,
            "dangle_endpoint_count": 0,
        }
    geometries = [geom for geom in frame.geometry if geom is not None]
    total = len(geometries)
    duplicate_count = total - len({geom.wkb_hex for geom in geometries})
    invalid_count = sum(1 for geom in geometries if not geom.is_valid)
    source_counts = _source_feature_counts(frame)
    return {
        "duplicate_geometry_rate": duplicate_count / total if total else 0.0,
        "invalid_geometry_rate": invalid_count / total if total else 0.0,
        "source_feature_counts": source_counts,
        "source_contribution_balance": _gini(list(source_counts.values())),
        **_topology_quality_metrics(frame, sliver_area_threshold_sq_m=sliver_area_threshold_sq_m),
    }


def _topology_quality_metrics(
    frame: gpd.GeoDataFrame,
    *,
    sliver_area_threshold_sq_m: float = _DEFAULT_SLIVER_AREA_THRESHOLD_SQ_M,
) -> dict[str, int]:
    measured = frame
    if measured.crs is not None and measured.crs.is_geographic:
        measured = measured.to_crs("EPSG:3857")

    zero_length_geometry_count = 0
    sliver_polygon_count = 0
    dangle_endpoints: dict[tuple[float, float], int] = {}

    for geom in measured.geometry:
        for line in _line_parts(geom):
            if line.length == 0:
                zero_length_geometry_count += 1
                continue
            for endpoint in _line_endpoints(line):
                dangle_endpoints[endpoint] = dangle_endpoints.get(endpoint, 0) + 1
        for polygon in _polygon_parts(geom):
            if polygon.is_valid and polygon.area < sliver_area_threshold_sq_m:
                sliver_polygon_count += 1

    return {
        "zero_length_geometry_count": zero_length_geometry_count,
        "self_intersection_count": _self_intersection_count(frame),
        "sliver_polygon_count": sliver_polygon_count,
        "dangle_endpoint_count": sum(1 for count in dangle_endpoints.values() if count == 1),
    }


def _self_intersection_count(frame: gpd.GeoDataFrame) -> int:
    count = 0
    for geom in frame.geometry:
        for polygon in _polygon_parts(geom):
            if polygon.is_valid:
                continue
            if _is_self_intersection_reason(explain_validity(polygon)):
                count += 1
    return count


def _is_self_intersection_reason(reason: str) -> bool:
    return "self-intersection" in reason.lower()


def _polygon_parts(geom) -> list[Any]:
    if geom is None or geom.is_empty:
        return []
    geom_type = getattr(geom, "geom_type", "")
    if geom_type == "Polygon":
        return [geom]
    if geom_type == "MultiPolygon":
        return list(geom.geoms)
    if geom_type == "GeometryCollection":
        parts: list[Any] = []
        for part in geom.geoms:
            parts.extend(_polygon_parts(part))
        return parts
    return []


def _line_parts(geom) -> list[Any]:
    if geom is None or geom.is_empty:
        return []
    geom_type = getattr(geom, "geom_type", "")
    if geom_type == "LineString":
        return [geom]
    if geom_type == "MultiLineString":
        return list(geom.geoms)
    if geom_type == "GeometryCollection":
        parts: list[Any] = []
        for part in geom.geoms:
            parts.extend(_line_parts(part))
        return parts
    return []


def _line_endpoints(line) -> list[tuple[float, float]]:
    coords = list(line.coords)
    if not coords:
        return []
    return [_endpoint_key(coords[0]), _endpoint_key(coords[-1])]


def _endpoint_key(coord) -> tuple[float, float]:
    return (float(coord[0]), float(coord[1]))


def _source_feature_counts(frame: gpd.GeoDataFrame) -> dict[str, int]:
    if "source_id" not in frame.columns:
        return {}
    counts: dict[str, int] = {}
    for value in frame["source_id"].dropna():
        source_id = str(value)
        counts[source_id] = counts.get(source_id, 0) + 1
    return counts


def _gini(values: list[int]) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    total = sum(ordered)
    if total <= 0:
        return 0.0
    n = len(ordered)
    weighted = sum((index + 1) * value for index, value in enumerate(ordered))
    return float((2 * weighted) / (n * total) - (n + 1) / n)


def _candidate_evidence(candidate) -> dict[str, Any]:
    evidence = getattr(candidate, "evidence", {})
    return evidence if isinstance(evidence, dict) else {}


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return None


def _first_summary_value(summaries: list[dict[str, Any]], key: str, *, default: Any = None) -> Any:
    for summary in summaries:
        value = summary.get(key)
        if value not in (None, ""):
            return value
    return default


def _planning_validity_rate(plan, audit_events) -> float:
    validation = getattr(plan, "validation", None)
    if validation is not None:
        return 1.0 if bool(getattr(validation, "valid", False)) else 0.0
    return 1.0 if any(event.kind == "plan_validated" for event in audit_events) else 0.0


def _kg_path_trace_completeness(plan) -> float:
    trace = build_kg_path_trace(plan)
    return 1.0 if trace.get("chains") and trace.get("selected_pattern_id") else 0.0


def _decision_trace_completeness(decision_records) -> float:
    if not decision_records:
        return 0.0
    complete = sum(1 for record in decision_records if getattr(record, "selected_id", None) and getattr(record, "candidates", None))
    return complete / len(decision_records)


def _plan_decision_materialization_consistency(plan, audit_events) -> float:
    planned_sources = {task.input.data_source_id for task in getattr(plan, "tasks", []) if not task.is_transform}
    selected_sources = {
        event.details.get("selected_source_id") or event.details.get("source_id")
        for event in audit_events
        if event.kind == "task_inputs_resolved"
    }
    selected_sources.discard(None)
    if not planned_sources or not selected_sources:
        return 0.0
    return 1.0 if planned_sources & selected_sources else 0.0


def _source_coverage_resolution_rate(audit_events) -> float:
    resolved = [event for event in audit_events if event.kind == "task_inputs_resolved"]
    if not resolved:
        return 0.0
    with_coverage = [event for event in resolved if event.details.get("component_coverage") is not None]
    return len(with_coverage) / len(resolved)


def _fallback_success_rate(audit_events) -> float:
    fallback_events = [event for event in audit_events if event.kind == "source_fallback_selected"]
    if not fallback_events:
        return 1.0
    succeeded = any(event.kind == "run_succeeded" for event in audit_events)
    return 1.0 if succeeded else 0.0


def _recovery_success_rate(audit_events) -> float:
    failures = [event for event in audit_events if event.kind in {"replan_requested", "run_failed"}]
    if not failures:
        return 1.0
    return 1.0 if any(event.kind == "run_succeeded" for event in audit_events) else 0.0


def _evidence_completeness_rate(audit_events) -> float:
    required = {"plan_created", "plan_validated", "task_inputs_resolved"}
    seen = {event.kind for event in audit_events}
    return len(required & seen) / len(required)
