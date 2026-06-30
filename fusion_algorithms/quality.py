from __future__ import annotations

from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from fusion_algorithms.contracts import ConflictDetectionParams


def detect_spatial_conflicts(
    gdf: gpd.GeoDataFrame,
    params: ConflictDetectionParams | None = None,
) -> list[dict[str, Any]]:
    params = params or ConflictDetectionParams()
    frame = gdf.copy()
    if params.buffer_distance_m:
        frame["geometry"] = frame.geometry.buffer(params.buffer_distance_m)
    conflicts: list[dict[str, Any]] = []
    geoms = list(frame.geometry)
    for i, geom_a in enumerate(geoms):
        if geom_a is None or geom_a.is_empty:
            continue
        for j in range(i + 1, len(geoms)):
            geom_b = geoms[j]
            if geom_b is None or geom_b.is_empty:
                continue
            if not geom_a.intersects(geom_b):
                continue
            inter = geom_a.intersection(geom_b)
            if params.touch_policy == "ignore_touches" and inter.area <= 0:
                continue
            if inter.area < params.overlap_area_min:
                continue
            conflicts.append(
                {
                    "left_id": int(frame.index[i]) if hasattr(frame.index[i], "__int__") else str(frame.index[i]),
                    "right_id": int(frame.index[j]) if hasattr(frame.index[j], "__int__") else str(frame.index[j]),
                    "overlap_area": float(inter.area),
                }
            )
    return conflicts


_DEFAULT_ALIGNMENT_ID_FIELDS = (
    "source_feature_id",
    "matched_source_feature_id",
    "matched_base_segment_id",
    "matched_supplement_segment_id",
    "matched_supplement_high",
    "matched_supplement_loose",
    "osm_id",
    "FID_1",
    "fid",
    "id",
)

_DEFAULT_ATTRIBUTE_GROUPS = (
    ("name", "road_name", "osm_name", "canonical_name", "name_en"),
    ("type", "category", "class", "road_class", "waterway_class", "fclass"),
)


def evaluate_feature_alignment(
    fused: gpd.GeoDataFrame,
    sources: dict[str, gpd.GeoDataFrame],
    *,
    id_fields: tuple[str, ...] = _DEFAULT_ALIGNMENT_ID_FIELDS,
    attribute_groups: tuple[tuple[str, ...], ...] = _DEFAULT_ATTRIBUTE_GROUPS,
    max_match_distance_m: float = 25.0,
) -> dict[str, Any]:
    if not sources:
        return {"status": "not_available", "reason": "source_artifact_paths_not_provided"}
    if fused.empty:
        source_count = sum(int(len(frame)) for frame in sources.values())
        return {
            "status": "available",
            "source_count": len(sources),
            "source_feature_count": source_count,
            "fused_feature_count": 0,
            "matched_source_count": 0,
            "matched_fused_count": 0,
            "unmatched_source_count": source_count,
            "unmatched_fused_count": 0,
            "match_recall": 0.0 if source_count else 1.0,
            "match_precision_proxy": 1.0,
            "attribute_agreement": None,
            "geometry_deviation_p50_m": None,
            "geometry_deviation_p95_m": None,
            "source_summaries": _empty_source_summaries(sources),
        }

    measured_fused, measured_sources = _alignment_measurement_frames(fused, sources)
    matches = _alignment_matches(
        measured_fused,
        measured_sources,
        id_fields=id_fields,
        attribute_groups=attribute_groups,
        max_match_distance_m=max_match_distance_m,
    )
    source_feature_count = sum(int(len(frame)) for frame in measured_sources.values())
    fused_feature_count = int(len(measured_fused))
    matched_source_keys = {(match["source_id"], int(match["source_index"])) for match in matches}
    matched_fused_indexes = {int(match["fused_index"]) for match in matches}
    geometry_deviations = [float(match["geometry_deviation_m"]) for match in matches]
    attribute_values = [
        float(match["attribute_agreement"])
        for match in matches
        if match.get("attribute_agreement") is not None
    ]

    return {
        "status": "available",
        "source_count": len(measured_sources),
        "source_feature_count": source_feature_count,
        "fused_feature_count": fused_feature_count,
        "matched_source_count": len(matched_source_keys),
        "matched_fused_count": len(matched_fused_indexes),
        "unmatched_source_count": max(0, source_feature_count - len(matched_source_keys)),
        "unmatched_fused_count": max(0, fused_feature_count - len(matched_fused_indexes)),
        "match_recall": _safe_ratio(len(matched_source_keys), source_feature_count),
        "match_precision_proxy": _safe_ratio(len(matched_fused_indexes), fused_feature_count),
        "attribute_agreement": float(np.mean(attribute_values)) if attribute_values else None,
        "geometry_deviation_p50_m": _percentile(geometry_deviations, 50),
        "geometry_deviation_p95_m": _percentile(geometry_deviations, 95),
        "source_summaries": _source_alignment_summaries(measured_sources, matches),
    }


def _alignment_matches(
    fused: gpd.GeoDataFrame,
    sources: dict[str, gpd.GeoDataFrame],
    *,
    id_fields: tuple[str, ...],
    attribute_groups: tuple[tuple[str, ...], ...],
    max_match_distance_m: float,
) -> list[dict[str, Any]]:
    id_index = _fused_id_index(fused, id_fields)
    spatial_index = fused.sindex
    matches: list[dict[str, Any]] = []
    for source_id, source in sources.items():
        for source_pos, (_, source_row) in enumerate(source.iterrows()):
            source_geom = source_row.geometry
            if source_geom is None or source_geom.is_empty:
                continue
            fused_pos = _match_by_id(source_row, id_fields=id_fields, id_index=id_index)
            method = "id" if fused_pos is not None else "spatial"
            if fused_pos is None:
                fused_pos = _match_by_spatial_proximity(
                    source_geom,
                    fused,
                    spatial_index=spatial_index,
                    max_match_distance_m=max_match_distance_m,
                )
            if fused_pos is None:
                continue
            fused_row = fused.iloc[int(fused_pos)]
            fused_geom = fused_row.geometry
            distance = float(source_geom.distance(fused_geom))
            try:
                deviation = float(source_geom.hausdorff_distance(fused_geom))
            except Exception:  # noqa: BLE001
                deviation = distance
            matches.append(
                {
                    "source_id": source_id,
                    "source_index": int(source_pos),
                    "fused_index": int(fused_pos),
                    "match_method": method,
                    "distance_m": distance,
                    "geometry_deviation_m": deviation,
                    "attribute_agreement": _attribute_agreement(source_row, fused_row, attribute_groups),
                }
            )
    return matches


def _alignment_measurement_frames(
    fused: gpd.GeoDataFrame,
    sources: dict[str, gpd.GeoDataFrame],
) -> tuple[gpd.GeoDataFrame, dict[str, gpd.GeoDataFrame]]:
    target_crs = _measurement_crs(fused, sources)
    measured_fused = _to_alignment_crs(fused, target_crs)
    measured_sources = {
        source_id: _to_alignment_crs(frame, target_crs)
        for source_id, frame in sources.items()
    }
    return measured_fused, measured_sources


def _measurement_crs(fused: gpd.GeoDataFrame, sources: dict[str, gpd.GeoDataFrame]) -> str:
    for frame in [fused, *sources.values()]:
        crs = getattr(frame, "crs", None)
        if crs is not None and not crs.is_geographic:
            return str(crs)
    return "EPSG:3857"


def _to_alignment_crs(frame: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
    copied = frame.copy()
    if copied.crs is None:
        copied = copied.set_crs(target_crs, allow_override=True)
        return copied
    if str(copied.crs) == str(target_crs):
        return copied
    return copied.to_crs(target_crs)


def _fused_id_index(fused: gpd.GeoDataFrame, id_fields: tuple[str, ...]) -> dict[str, int]:
    index: dict[str, int] = {}
    for pos, (_, row) in enumerate(fused.iterrows()):
        for field in id_fields:
            if field not in fused.columns:
                continue
            for value in _split_identifier_values(row.get(field)):
                index.setdefault(value, int(pos))
    return index


def _match_by_id(row: pd.Series, *, id_fields: tuple[str, ...], id_index: dict[str, int]) -> int | None:
    for field in id_fields:
        if field not in row.index:
            continue
        for value in _split_identifier_values(row.get(field)):
            if value in id_index:
                return id_index[value]
    return None


def _match_by_spatial_proximity(
    source_geom: Any,
    fused: gpd.GeoDataFrame,
    *,
    spatial_index,
    max_match_distance_m: float,
) -> int | None:
    search_geom = source_geom.buffer(max(0.0, float(max_match_distance_m)))
    candidate_positions = list(spatial_index.intersection(search_geom.bounds))
    best: tuple[float, float, int] | None = None
    for candidate_pos in candidate_positions:
        candidate_pos = int(candidate_pos)
        fused_geom = fused.geometry.iloc[candidate_pos]
        if fused_geom is None or fused_geom.is_empty:
            continue
        distance = float(source_geom.distance(fused_geom))
        if distance > max_match_distance_m and not source_geom.intersects(fused_geom):
            continue
        try:
            deviation = float(source_geom.hausdorff_distance(fused_geom))
        except Exception:  # noqa: BLE001
            deviation = distance
        score = (distance, deviation, candidate_pos)
        if best is None or score < best:
            best = score
    return best[2] if best is not None else None


def _attribute_agreement(
    source_row: pd.Series,
    fused_row: pd.Series,
    attribute_groups: tuple[tuple[str, ...], ...],
) -> float | None:
    compared = 0
    agreed = 0
    for group in attribute_groups:
        source_value = _first_nonempty(source_row, group)
        fused_value = _first_nonempty(fused_row, group)
        if source_value is None or fused_value is None:
            continue
        compared += 1
        if _normalize_text(source_value) == _normalize_text(fused_value):
            agreed += 1
    if compared == 0:
        return None
    return agreed / compared


def _first_nonempty(row: pd.Series, fields: tuple[str, ...]) -> object | None:
    for field in fields:
        if field not in row.index:
            continue
        value = row.get(field)
        if _normalize_text(value):
            return value
    return None


def _split_identifier_values(value: object) -> list[str]:
    if value is None or pd.isna(value):
        return []
    text = str(value).strip()
    if not text:
        return []
    parts = [text]
    for delimiter in ("|", ",", ";"):
        if delimiter in text:
            parts.extend(item.strip() for item in text.split(delimiter))
    return [_normalize_text(item) for item in parts if _normalize_text(item)]


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:  # noqa: BLE001
        pass
    text = str(value).strip().casefold()
    return "" if text in {"", "nan", "none", "<na>", "null"} else text


def _safe_ratio(numerator: int, denominator: int) -> float:
    return float(numerator / denominator) if denominator else 1.0


def _percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    return float(np.percentile(values, percentile))


def _empty_source_summaries(sources: dict[str, gpd.GeoDataFrame]) -> dict[str, dict[str, Any]]:
    return {
        source_id: {
            "source_feature_count": int(len(frame)),
            "matched_source_count": 0,
            "match_recall": 0.0 if len(frame) else 1.0,
        }
        for source_id, frame in sources.items()
    }


def _source_alignment_summaries(
    sources: dict[str, gpd.GeoDataFrame],
    matches: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    matched_by_source: dict[str, set[int]] = {}
    for match in matches:
        matched_by_source.setdefault(str(match["source_id"]), set()).add(int(match["source_index"]))
    return {
        source_id: {
            "source_feature_count": int(len(frame)),
            "matched_source_count": len(matched_by_source.get(source_id, set())),
            "match_recall": _safe_ratio(len(matched_by_source.get(source_id, set())), int(len(frame))),
        }
        for source_id, frame in sources.items()
    }
