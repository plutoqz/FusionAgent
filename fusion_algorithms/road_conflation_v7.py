from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd

from fusion_algorithms.line_conflation_v7 import (
    LineConflationResult,
    LineConflationV7Config,
    run_line_conflation_v7,
)


_ROAD_PROFILE_OVERRIDES: dict[str, dict[str, object]] = {
    "balanced": {"cleanup_mode": "balanced", "run_second_clean_pass": True},
    "quality": {"cleanup_mode": "quality", "run_second_clean_pass": True},
    "fast": {"cleanup_mode": "fast", "run_second_clean_pass": False},
    "conservative": {
        "cleanup_mode": "quality",
        "run_second_clean_pass": True,
        "match_buffer_dist": 16.0,
        "max_hausdorff": 12.0,
        "duplicate_coverage_threshold": 0.95,
        "crossing_coverage_threshold": 0.9,
    },
}


@dataclass
class RoadConflationV7Config(LineConflationV7Config):
    profile: str = "balanced"

    def materialized(self) -> "RoadConflationV7Config":
        overrides = dict(_ROAD_PROFILE_OVERRIDES.get(self.profile, _ROAD_PROFILE_OVERRIDES["balanced"]))
        explicit = asdict(self)
        explicit.pop("profile", None)
        overrides.update(explicit)
        return RoadConflationV7Config(**overrides, profile=self.profile)


def _remap_source_layer(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    remapped = frame.copy()
    remapped["source_layer"] = remapped["source_layer"].replace({"osm": "base", "msft": "supplement"})
    return remapped


def _clean_name_values(values: pd.Series) -> pd.Series:
    cleaned = values.fillna("").astype(str)
    return cleaned.mask(cleaned.str.lower().isin({"nan", "none", "<na>"}), "")


def _coalesced_name_values(frame: gpd.GeoDataFrame) -> pd.Series:
    values = pd.Series([""] * len(frame), index=frame.index, dtype="object")
    for column in ("name", "Name", "NAME", "road_name", "osm_name", "name_en", "ref", "REF"):
        if column not in frame.columns:
            continue
        candidate = _clean_name_values(frame[column])
        values = values.mask(values.str.len().eq(0), candidate)
    return values


def _canonicalize_road_output(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    result = _remap_source_layer(frame)
    residual_mask = result.get("residual_from_matched", pd.Series(False, index=result.index)).fillna(False).astype(bool)
    supplement_mask = result["source_layer"].eq("supplement")
    result["fusion_source"] = "base_road_network"
    result.loc[supplement_mask & ~residual_mask, "fusion_source"] = "supplement_road"
    result.loc[supplement_mask & residual_mask, "fusion_source"] = "supplement_residual"
    result["match_role"] = "base"
    result.loc[supplement_mask & ~residual_mask, "match_role"] = "supplement_unmatched"
    result.loc[supplement_mask & residual_mask, "match_role"] = "supplement_uncovered_residual"
    result["matched_supplement_segment_id"] = result.get("label1", "").fillna("")
    result["supplement_segment_id"] = ""
    if "label3" in result.columns:
        result.loc[supplement_mask, "supplement_segment_id"] = result.loc[supplement_mask, "label3"].fillna("").astype(str)
    if "original_FID_1" in result.columns:
        original_ids = result.loc[supplement_mask, "original_FID_1"].fillna("").astype(str)
        original_ids = _clean_name_values(original_ids)
        populated_original = original_ids.str.len().gt(0)
        populated_index = original_ids.index[populated_original]
        result.loc[populated_index, "supplement_segment_id"] = original_ids.loc[populated_index]
        if "residual_part" in result.columns:
            residual_index = original_ids.index[populated_original & residual_mask.loc[original_ids.index]]
            residual_parts = (
                pd.to_numeric(result.loc[residual_index, "residual_part"], errors="coerce")
                .fillna(1)
                .astype(int)
                .astype(str)
            )
            result.loc[residual_index, "supplement_segment_id"] = (
                result.loc[residual_index, "supplement_segment_id"].astype(str)
                + "_res"
                + residual_parts
            )
    road_class = pd.Series(["road"] * len(result), index=result.index, dtype="object")
    for column in ("road_class", "fclass", "highway", "class"):
        if column in result.columns:
            road_class = road_class.where(result[column].isna(), result[column].astype(str))
    result["road_class"] = road_class.fillna("road")
    name_values = _coalesced_name_values(result)
    result["name"] = name_values.astype(str)
    result["osm_name"] = ""
    result.loc[~supplement_mask, "osm_name"] = name_values.loc[~supplement_mask].astype(str)
    result["road_name"] = name_values.astype(str)
    return result


def run_road_conflation_v7(
    base: gpd.GeoDataFrame | Path | str,
    supplement: gpd.GeoDataFrame | Path | str,
    *,
    config: RoadConflationV7Config | None = None,
) -> LineConflationResult:
    resolved = (config or RoadConflationV7Config()).materialized()
    result = run_line_conflation_v7(
        base,
        supplement,
        config=resolved,
        algorithm_id="algo.fusion.road.conflation.v7",
        base_id_candidates=("osm_id", "source_feature_id", "id", "objectid", "fid"),
        supplement_id_candidates=("FID_1", "FID", "source_feature_id", "id", "osm_id", "objectid", "fid"),
        base_class_candidates=("road_class", "fclass", "highway", "class"),
        supplement_class_candidates=("road_class", "fclass", "highway", "class"),
        default_base_class="road",
        default_supplement_class="road",
    )
    return LineConflationResult(
        frame=_canonicalize_road_output(result.frame),
        stats=result.stats,
        config=result.config,
        lineage={**result.lineage, "profile": resolved.profile},
        warnings=result.warnings,
    )
