from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd

from fusion_algorithms.line_conflation_v7 import (
    LineConflationResult,
    LineConflationV7Config,
    run_line_conflation_v7,
)


@dataclass
class WaterwaysConflationV7Config(LineConflationV7Config):
    max_segment_length: float | None = 1000.0
    match_buffer_dist: float = 25.0
    max_hausdorff: float = 20.0
    loose_angle_threshold: float = 50.0
    min_len_similarity: float = 0.03
    min_supplement_coverage_for_matched: float = 0.80
    min_residual_length: float = 20.0
    duplicate_buffer_dist: float = 12.0
    duplicate_angle_threshold: float = 28.0
    duplicate_max_centerline_dist: float = 10.0
    group_duplicate_buffer_dist: float = 8.0
    group_duplicate_angle_threshold: float = 22.0
    group_duplicate_mean_distance: float = 5.0
    group_duplicate_p90_distance: float = 9.0
    duplicate_sample_step: float = 40.0
    near_base_return_endpoint_radius: float = 15.0
    near_base_return_corridor_dist: float = 15.0
    near_base_return_mean_distance: float = 7.0
    near_base_return_p90_distance: float = 12.0
    near_base_return_max_distance: float = 18.0
    near_base_return_sample_step: float = 40.0
    crossing_corridor_dist: float = 15.0
    crossing_mean_distance: float = 7.0
    crossing_p90_distance: float = 12.0
    crossing_max_distance: float = 20.0
    crossing_angle_threshold: float = 25.0
    crossing_sample_step: float = 40.0
    endpoint_snap_radius: float = 12.0
    max_endpoint_snap_bend_angle: float = 40.0
    enable_dangle_cleanup: bool = False
    cleanup_mode: str = "fast"


def _canonicalize_waterways_output(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    result = frame.copy()
    result["source_layer"] = result["source_layer"].replace({"osm": "base", "msft": "supplement"})
    residual_mask = result.get("residual_from_matched", pd.Series(False, index=result.index)).fillna(False).astype(bool)
    supplement_mask = result["source_layer"].eq("supplement")
    result["fusion_source"] = "base_osm_waterways"
    result.loc[supplement_mask & ~residual_mask, "fusion_source"] = "supplement_waterways"
    result.loc[supplement_mask & residual_mask, "fusion_source"] = "supplement_residual"
    result["match_role"] = "base"
    result.loc[supplement_mask & ~residual_mask, "match_role"] = "supplement_unmatched"
    result.loc[supplement_mask & residual_mask, "match_role"] = "supplement_uncovered_residual"
    result["matched_supplement_high"] = result.get("label1", "").fillna("")
    result["matched_supplement_loose"] = result.get("label2", "").fillna("")
    result["supplement_segment_id"] = ""
    if "label3" in result.columns:
        result.loc[supplement_mask, "supplement_segment_id"] = result.loc[supplement_mask, "label3"].fillna("").astype(str)
    result["matched_base_segment_id"] = ""
    if "residual_parent_FID_1" in result.columns:
        result.loc[residual_mask, "matched_base_segment_id"] = (
            result.loc[residual_mask, "residual_parent_FID_1"].fillna("").astype(str)
        )

    base_classes = result.get("fclass", pd.Series(["waterway"] * len(result), index=result.index, dtype="object"))
    supplement_classes = result.get("waterway", result.get("fclass", pd.Series(["waterway"] * len(result), index=result.index)))
    result["waterway_class"] = base_classes.astype(str)
    result.loc[supplement_mask, "waterway_class"] = supplement_classes.loc[supplement_mask].fillna("waterway").astype(str)
    if "source" in result.columns:
        result["supplement_source"] = result["source"]
    else:
        result["supplement_source"] = pd.NA
    for column in [
        "name_en",
        "name_ur",
        "width",
        "depth",
        "covered",
        "layer",
        "blockage",
        "tunnel",
        "natural",
        "water",
        "residual_from_matched",
        "residual_part",
        "residual_parent_FID_1",
    ]:
        if column not in result.columns:
            result[column] = pd.NA
    line_only = result[result.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
    return line_only.reset_index(drop=True)


def run_waterways_conflation_v7(
    base: gpd.GeoDataFrame | Path | str,
    supplement: gpd.GeoDataFrame | Path | str,
    *,
    config: WaterwaysConflationV7Config | None = None,
) -> LineConflationResult:
    resolved = config or WaterwaysConflationV7Config()
    result = run_line_conflation_v7(
        base,
        supplement,
        config=resolved,
        algorithm_id="algo.fusion.waterways.conflation.v7",
        base_id_candidates=("osm_id", "source_feature_id", "id", "objectid", "fid"),
        supplement_id_candidates=("FID_1", "osm_id", "source_feature_id", "id", "objectid", "fid"),
        base_class_candidates=("fclass", "waterway", "water_class"),
        supplement_class_candidates=("waterway", "fclass", "water_class"),
        default_base_class="waterway",
        default_supplement_class="waterway",
    )
    return LineConflationResult(
        frame=_canonicalize_waterways_output(result.frame),
        stats=result.stats,
        config=result.config,
        lineage=result.lineage,
        warnings=result.warnings,
    )
