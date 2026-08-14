from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import pyogrio
from pyproj import Transformer
from shapely import STRtree
from shapely.geometry import Point
from shapely.validation import explain_validity

from fusion_algorithms.quality import evaluate_feature_alignment
from kg.knowledge_release import KnowledgeReleaseError
from kg.policy_registry import KnowledgePolicyRegistry, default_policy_registry
from services.kg_path_trace_service import build_kg_path_trace


_FRAME_DERIVED_METRICS = (
    "total_area_sq_km",
    "total_length_km",
    "duplicate_geometry_rate",
    "invalid_geometry_rate",
    "source_feature_counts",
    "source_contribution_balance",
    "zero_length_geometry_count",
    "self_intersection_count",
    "sliver_polygon_count",
    "dangle_endpoint_count",
    "dangle_endpoint_rate_per_100km",
    "overlap_pair_count",
    "overlap_area_sq_m",
    "overlap_area_rate",
    "field_null_rates",
    "field_nonempty_counts",
)


def evaluate_vector_artifact(
    shp_path: Path,
    *,
    required_fields: list[str],
    requested_bbox: list[float] | tuple[float, float, float, float] | None = None,
    source_artifact_paths: dict[str, Path | str] | None = None,
    sliver_area_threshold_sq_m: float | None = None,
    metadata_only_threshold_bytes: int | None = None,
    policy_registry: KnowledgePolicyRegistry | None = None,
) -> dict[str, Any]:
    registry = policy_registry or default_policy_registry()
    evaluation_policy = registry.artifact_evaluation_policy()
    shp_path = Path(shp_path)
    _require_supported_vector_artifact(shp_path, evaluation_policy=evaluation_policy)
    if sliver_area_threshold_sq_m is None:
        sliver_area_threshold_sq_m = float(evaluation_policy["sliver_area_threshold_sq_m"])
    if metadata_only_threshold_bytes is None:
        metadata_only_threshold_bytes = int(evaluation_policy["metadata_only_threshold_bytes"])
    large_artifact_metrics = _large_artifact_metrics(
        shp_path,
        required_fields=required_fields,
        requested_bbox=requested_bbox,
        source_artifact_paths=source_artifact_paths,
        sliver_area_threshold_sq_m=sliver_area_threshold_sq_m,
        metadata_only_threshold_bytes=metadata_only_threshold_bytes,
        evaluation_policy=evaluation_policy,
    )
    if large_artifact_metrics is not None:
        return _with_evaluation_provenance(
            large_artifact_metrics,
            evaluation_policy=evaluation_policy,
            registry=registry,
        )

    frame = gpd.read_file(shp_path)
    metrics = _evaluate_loaded_frame(
        frame,
        artifact_path=shp_path,
        required_fields=required_fields,
        requested_bbox=requested_bbox,
        source_artifact_paths=source_artifact_paths,
        sliver_area_threshold_sq_m=sliver_area_threshold_sq_m,
    )
    metrics["evaluation_mode"] = "full"
    metrics["evaluation_status"] = "evaluated"
    return _with_evaluation_provenance(metrics, evaluation_policy=evaluation_policy, registry=registry)


def _evaluate_loaded_frame(
    frame: gpd.GeoDataFrame,
    *,
    artifact_path: Path,
    required_fields: list[str],
    requested_bbox: list[float] | tuple[float, float, float, float] | None,
    source_artifact_paths: dict[str, Path | str] | None,
    sliver_area_threshold_sq_m: float,
) -> dict[str, Any]:
    missing_fields = [
        field
        for field in required_fields
        if not _has_required_field(field=field, frame=frame, artifact_path=artifact_path)
    ]
    metrics = {
        "artifact_validity": artifact_path.exists() and not frame.empty and not missing_fields,
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
    metrics.update(_field_quality_metrics(frame))
    metrics["feature_alignment"] = _feature_alignment_metrics(frame, source_artifact_paths=source_artifact_paths)
    return metrics


def _large_artifact_metrics(
    artifact_path: Path,
    *,
    required_fields: list[str],
    requested_bbox: list[float] | tuple[float, float, float, float] | None,
    source_artifact_paths: dict[str, Path | str] | None,
    sliver_area_threshold_sq_m: float,
    metadata_only_threshold_bytes: int,
    evaluation_policy: dict[str, Any],
) -> dict[str, Any] | None:
    if metadata_only_threshold_bytes <= 0:
        return None
    if not artifact_path.exists() or artifact_path.stat().st_size < metadata_only_threshold_bytes:
        return None
    try:
        info = pyogrio.read_info(artifact_path)
    except Exception:  # noqa: BLE001
        return None

    mode = str(evaluation_policy.get("large_artifact_mode") or "").strip().lower()
    if mode == "metadata_only":
        return _metadata_only_metrics(
            artifact_path,
            info=info,
            required_fields=required_fields,
            requested_bbox=requested_bbox,
        )
    if mode == "sample":
        sampling_policy = _authorized_sampling_policy(
            artifact_path,
            evaluation_policy=evaluation_policy,
        )
        frame = gpd.read_file(artifact_path, rows=int(sampling_policy["max_features"]))
        metrics = _evaluate_loaded_frame(
            frame,
            artifact_path=artifact_path,
            required_fields=required_fields,
            requested_bbox=requested_bbox,
            source_artifact_paths=None,
            sliver_area_threshold_sq_m=sliver_area_threshold_sq_m,
        )
        sample_feature_count = metrics["feature_count"]
        metadata_feature_count = _metadata_feature_count(info)
        metrics.update(
            {
                "feature_count": int(metadata_feature_count or sample_feature_count),
                "sample_feature_count": sample_feature_count,
                "bbox": _metadata_bbox_wgs84(info, crs=str(info.get("crs") or "")) or metrics.get("bbox"),
                "evaluation_mode": "sampled",
                "evaluation_status": "sampled",
                "sampling": {
                    "authorized": True,
                    "strategy": sampling_policy["strategy"],
                    "max_features": int(sampling_policy["max_features"]),
                    "applicable_extensions": list(sampling_policy["applicable_extensions"]),
                },
                "metric_evaluation_status": {name: "sampled" for name in _FRAME_DERIVED_METRICS},
                "feature_alignment": _feature_alignment_not_available("sampled_evaluation"),
            }
        )
        return metrics
    raise KnowledgeReleaseError(
        "artifact_evaluation_policy.large_artifact_mode must be metadata_only or sample"
    )


def _metadata_only_metrics(
    artifact_path: Path,
    *,
    info: dict[str, Any],
    required_fields: list[str],
    requested_bbox: list[float] | tuple[float, float, float, float] | None,
) -> dict[str, Any]:

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
        "evaluation_status": "partial",
        "metric_evaluation_status": {name: "not_evaluated" for name in _FRAME_DERIVED_METRICS},
        "not_evaluated_metrics": list(_FRAME_DERIVED_METRICS),
        "feature_alignment": _feature_alignment_not_available("metadata_only_evaluation"),
        **{name: None for name in _FRAME_DERIVED_METRICS},
    }
    if requested_bbox is not None:
        metrics["aoi_consistency"] = _aoi_consistency(metrics.get("bbox"), requested_bbox)
    return metrics


def _require_supported_vector_artifact(
    artifact_path: Path,
    *,
    evaluation_policy: dict[str, Any],
) -> None:
    raw_extensions = evaluation_policy.get("supported_vector_extensions")
    if not isinstance(raw_extensions, list) or not raw_extensions:
        raise KnowledgeReleaseError(
            "artifact_evaluation_policy.supported_vector_extensions must be a non-empty list"
        )
    extensions = {
        value if value.startswith(".") else f".{value}"
        for item in raw_extensions
        if (value := str(item).strip().lower())
    }
    if artifact_path.suffix.lower() not in extensions:
        raise ValueError(
            f"Unsupported vector artifact extension {artifact_path.suffix or '<none>'}; "
            f"KG policy allows {sorted(extensions)}"
        )


def _authorized_sampling_policy(
    artifact_path: Path,
    *,
    evaluation_policy: dict[str, Any],
) -> dict[str, Any]:
    sampling = evaluation_policy.get("sampling_policy")
    if not isinstance(sampling, dict) or sampling.get("authorized") is not True:
        raise KnowledgeReleaseError(
            "Large-artifact sampling is not explicitly authorized by artifact_evaluation_policy"
        )
    strategy = str(sampling.get("strategy") or "").strip().lower()
    if strategy != "head":
        raise KnowledgeReleaseError("Authorized sampling_policy.strategy must be head")
    max_features = sampling.get("max_features")
    if isinstance(max_features, bool):
        raise KnowledgeReleaseError("Authorized sampling_policy.max_features must be a positive integer")
    try:
        max_features = int(max_features)
    except (TypeError, ValueError) as exc:
        raise KnowledgeReleaseError(
            "Authorized sampling_policy.max_features must be a positive integer"
        ) from exc
    if max_features <= 0:
        raise KnowledgeReleaseError("Authorized sampling_policy.max_features must be a positive integer")
    raw_extensions = sampling.get("applicable_extensions")
    if not isinstance(raw_extensions, list) or not raw_extensions:
        raise KnowledgeReleaseError(
            "Authorized sampling_policy.applicable_extensions must be a non-empty list"
        )
    applicable_extensions = [
        value if value.startswith(".") else f".{value}"
        for item in raw_extensions
        if (value := str(item).strip().lower())
    ]
    if artifact_path.suffix.lower() not in applicable_extensions:
        raise KnowledgeReleaseError(
            f"Sampling policy does not authorize extension {artifact_path.suffix.lower()}"
        )
    return {
        "authorized": True,
        "strategy": strategy,
        "max_features": max_features,
        "applicable_extensions": applicable_extensions,
    }


def _with_evaluation_provenance(
    metrics: dict[str, Any],
    *,
    evaluation_policy: dict[str, Any],
    registry: KnowledgePolicyRegistry,
) -> dict[str, Any]:
    metrics["evaluation_policy_id"] = str(evaluation_policy.get("policy_id") or "")
    metrics["knowledge_identity"] = registry.knowledge_identity()
    return metrics


def _feature_alignment_metrics(
    fused: gpd.GeoDataFrame,
    *,
    source_artifact_paths: dict[str, Path | str] | None,
) -> dict[str, Any]:
    if not source_artifact_paths:
        return _feature_alignment_not_available("source_artifact_paths_not_provided")
    sources: dict[str, gpd.GeoDataFrame] = {}
    skipped: dict[str, str] = {}
    for source_id, raw_path in source_artifact_paths.items():
        path = Path(raw_path)
        if not path.exists():
            skipped[source_id] = "path_missing"
            continue
        try:
            sources[source_id] = gpd.read_file(path)
        except Exception as exc:  # noqa: BLE001
            skipped[source_id] = f"read_failed:{type(exc).__name__}"
    if not sources:
        result = _feature_alignment_not_available("no_readable_source_artifacts")
        result["skipped_sources"] = skipped
        return result
    result = evaluate_feature_alignment(fused, sources)
    if skipped:
        result["skipped_sources"] = skipped
    return result


def _feature_alignment_not_available(reason: str) -> dict[str, Any]:
    return {
        "status": "not_available",
        "reason": reason,
    }


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


_PSEUDO_EMPTY_STRINGS = {"", "nan", "none", "<na>", "null"}


def _semantic_null_mask(series: Any) -> Any:
    values = series.astype("object")
    missing = values.map(pd.isna)
    text = values.fillna("").astype(str).str.strip().str.casefold()
    return missing | text.isin(_PSEUDO_EMPTY_STRINGS)


def _field_quality_metrics(frame: gpd.GeoDataFrame) -> dict[str, Any]:
    field_null_rates: dict[str, float] = {}
    field_nonempty_counts: dict[str, int] = {}
    field_distinct_nonempty_counts: dict[str, int] = {}
    total = int(len(frame))
    for column in frame.columns:
        if column == frame.geometry.name:
            continue
        null_mask = _semantic_null_mask(frame[column])
        null_count = int(null_mask.sum())
        field_null_rates[column] = null_count / total if total else 0.0
        field_nonempty_counts[column] = total - null_count
        field_distinct_nonempty_counts[column] = int(
            frame.loc[~null_mask, column].astype(str).str.strip().nunique()
        )
    flattened = {f"{column}_null_rate": value for column, value in field_null_rates.items()}
    return {
        "field_null_rates": field_null_rates,
        "field_nonempty_counts": field_nonempty_counts,
        "field_distinct_nonempty_counts": field_distinct_nonempty_counts,
        **flattened,
    }


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
    sliver_area_threshold_sq_m: float,
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
            "dangle_endpoint_rate_per_100km": 0.0,
            "overlap_pair_count": 0,
            "overlap_area_sq_m": 0.0,
            "overlap_area_rate": 0.0,
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
    sliver_area_threshold_sq_m: float,
) -> dict[str, Any]:
    measured = frame
    if measured.crs is not None and measured.crs.is_geographic:
        measured = measured.to_crs("EPSG:3857")

    zero_length_geometry_count = 0
    sliver_polygon_count = 0
    dangle_endpoints: dict[tuple[float, float], list[int]] = {}
    line_parts: list[Any] = []

    for geom in measured.geometry:
        for line in _line_parts(geom):
            if line.length == 0:
                zero_length_geometry_count += 1
                continue
            line_part_index = len(line_parts)
            line_parts.append(line)
            for endpoint in _line_endpoints(line):
                dangle_endpoints.setdefault(endpoint, []).append(line_part_index)
        for polygon in _polygon_parts(geom):
            if polygon.is_valid and polygon.area < sliver_area_threshold_sq_m:
                sliver_polygon_count += 1

    overlap_metrics = _polygon_overlap_metrics(measured)
    total_length_km = _line_length_km(measured)
    # An endpoint landing on another line's interior is a connected junction,
    # even when the target line has not been noded at that coordinate.
    dangle_endpoint_count = 0
    if line_parts and dangle_endpoints:
        line_tree = STRtree(line_parts)
        endpoint_keys = list(dangle_endpoints)
        endpoint_points = [Point(x, y) for x, y in endpoint_keys]
        endpoint_pairs = line_tree.query(endpoint_points, predicate="intersects")
        connected: set[int] = set()
        for point_index, line_index in zip(endpoint_pairs[0], endpoint_pairs[1]):
            endpoint = endpoint_keys[int(point_index)]
            owners = dangle_endpoints[endpoint]
            if any(int(line_index) != owner for owner in owners):
                connected.add(int(point_index))
        dangle_endpoint_count = sum(
            1
            for index, owners in enumerate(dangle_endpoints.values())
            if len(owners) == 1 and index not in connected
        )

    return {
        "zero_length_geometry_count": zero_length_geometry_count,
        "self_intersection_count": _self_intersection_count(frame),
        "sliver_polygon_count": sliver_polygon_count,
        "dangle_endpoint_count": dangle_endpoint_count,
        "dangle_endpoint_rate_per_100km": (dangle_endpoint_count / total_length_km * 100.0)
        if total_length_km > 0
        else 0.0,
        **overlap_metrics,
    }


def _line_length_km(frame: gpd.GeoDataFrame) -> float:
    total = 0.0
    for geom in frame.geometry:
        for line in _line_parts(geom):
            total += float(line.length)
    return total / 1000.0


def _polygon_overlap_metrics(frame: gpd.GeoDataFrame) -> dict[str, float | int]:
    polygons = []
    for index, geom in enumerate(frame.geometry):
        for polygon in _polygon_parts(geom):
            if polygon.is_empty or not polygon.is_valid:
                continue
            polygons.append((index, polygon))
    if not polygons:
        return {"overlap_pair_count": 0, "overlap_area_sq_m": 0.0, "overlap_area_rate": 0.0}

    polygon_frame = gpd.GeoDataFrame(
        {"_source_index": [item[0] for item in polygons]},
        geometry=[item[1] for item in polygons],
        crs=frame.crs,
    )
    total_area = float(polygon_frame.geometry.area.sum())
    pair_count = 0
    overlap_area = 0.0
    spatial_index = polygon_frame.sindex
    for left_pos, left in enumerate(polygon_frame.geometry):
        for right_pos in spatial_index.intersection(left.bounds):
            right_pos = int(right_pos)
            if right_pos <= left_pos:
                continue
            right = polygon_frame.geometry.iloc[right_pos]
            if not left.intersects(right):
                continue
            area = float(left.intersection(right).area)
            if area <= 0:
                continue
            pair_count += 1
            overlap_area += area
    return {
        "overlap_pair_count": pair_count,
        "overlap_area_sq_m": overlap_area,
        "overlap_area_rate": overlap_area / total_area if total_area > 0 else 0.0,
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
    source_column = next(
        (column for column in ("source_id", "primary_source") if column in frame.columns),
        None,
    )
    if source_column is None:
        return {}
    counts: dict[str, int] = {}
    for value in frame[source_column].dropna():
        source_ids = [item.strip() for item in str(value).split(";") if item.strip()]
        for source_id in source_ids:
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
