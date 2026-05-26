# -*- coding: utf-8 -*-
"""
River/waterway fusion entry point based on the V7 road-fusion logic.

Base layer:
    H:/pakistan-260319-free.shp/gis_osm_waterways_free_1.shp

Supplement layer:
    D:/xwechat_files/.../Pakistan_Waterways_Data.shp

The geometry logic is the same as V7 roads: match supplement lines against the
base network, keep unmatched supplement lines, and keep uncovered residual
parts of partially matched supplement lines. Attribute reading is deliberately
not column-limited so useful waterway fields from both sources are carried into
the final GeoPackage.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

from road_fusion_optimized_v7 import RoadFusionConfig, fuse_roads_pipeline, write_gdf


BASE_WATERWAYS = r"H:\pakistan-260319-free.shp\gis_osm_waterways_free_1.shp"
SUPPLEMENT_WATERWAYS = (
    r"D:\xwechat_files\wxid_sgg5tnl3zf2v22_9249\msg\file\2026-05"
    r"\Pak_Waterways_Shp\Pak_Waterways_Shp\Pakistan_Waterways_Data.shp"
)
OUTPUT_PATH = r"C:\Users\10537\Documents\New project\waterways_fusion_v7\pakistan_waterways_fused_v7.gpkg"
FINAL_OUTPUT_PATH = (
    r"C:\Users\10537\Documents\New project\waterways_fusion_v7"
    r"\pakistan_waterways_fused_v7_final.gpkg"
)


def polish_waterway_attributes(raw_output_path: str, final_output_path: str, cfg: RoadFusionConfig) -> None:
    gdf = gpd.read_file(raw_output_path)

    is_supplement = gdf["source_layer"].eq("msft") if "source_layer" in gdf.columns else pd.Series(False, index=gdf.index)
    if "residual_from_matched" in gdf.columns:
        residual_text = gdf["residual_from_matched"].fillna(False).astype(str).str.lower()
        is_residual = residual_text.isin({"true", "1", "yes"})
    else:
        is_residual = pd.Series(False, index=gdf.index)

    gdf["fusion_source"] = "base_osm_waterways"
    gdf.loc[is_supplement & ~is_residual, "fusion_source"] = "supplement_waterways"
    gdf.loc[is_supplement & is_residual, "fusion_source"] = "supplement_residual"
    gdf["match_role"] = "base"
    gdf.loc[is_supplement & ~is_residual, "match_role"] = "supplement_unmatched"
    gdf.loc[is_supplement & is_residual, "match_role"] = "supplement_uncovered_residual"
    gdf["matched_supplement_high"] = gdf["label1"] if "label1" in gdf.columns else ""
    gdf["matched_supplement_loose"] = gdf["label2"] if "label2" in gdf.columns else ""
    gdf["supplement_segment_id"] = ""
    if "label3" in gdf.columns:
        gdf.loc[is_supplement, "supplement_segment_id"] = gdf.loc[is_supplement, "label3"]
    gdf["matched_base_segment_id"] = ""
    if "residual_parent_FID_1" in gdf.columns:
        gdf.loc[is_residual, "matched_base_segment_id"] = gdf.loc[is_residual, "residual_parent_FID_1"]
    for col in [
        "matched_supplement_high",
        "matched_supplement_loose",
        "supplement_segment_id",
        "matched_base_segment_id",
    ]:
        gdf[col] = gdf[col].fillna("").astype(str).replace({"<NA>": "", "nan": "", "None": ""})

    gdf["waterway_class"] = pd.NA
    if "waterway" in gdf.columns:
        gdf.loc[is_supplement, "waterway_class"] = gdf.loc[is_supplement, "waterway"]
    if "fclass" in gdf.columns:
        gdf.loc[~is_supplement, "waterway_class"] = gdf.loc[~is_supplement, "fclass"]
    gdf["waterway_class"] = gdf["waterway_class"].fillna("waterway")

    if "source" in gdf.columns:
        gdf["supplement_source"] = gdf["source"]

    keep_cols = [
        "fusion_source",
        "match_role",
        "matched_supplement_high",
        "matched_supplement_loose",
        "supplement_segment_id",
        "matched_base_segment_id",
        "waterway_class",
        "name",
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
        "supplement_source",
        "osm_old",
        "osm_id",
        "osm_type",
        "source_layer",
        "label1",
        "label2",
        "label3",
        "msft_uid",
        "original_FID_1",
        "residual_from_matched",
        "residual_part",
        "residual_parent_FID_1",
        "geometry",
    ]
    keep_cols = [c for c in keep_cols if c in gdf.columns]
    final_gdf = gdf[keep_cols].copy()
    write_gdf(final_gdf, final_output_path, layer="waterways", cfg=cfg)


def main() -> None:
    cfg = RoadFusionConfig(
        target_crs="EPSG:32643",
        do_split_by_angle=True,
        angle_threshold=135.0,
        max_segment_length=1000.0,
        match_buffer_dist=25.0,
        max_hausdorff=20.0,
        loose_angle_threshold=50.0,
        min_len_similarity=0.03,
        min_msft_coverage_for_matched=0.80,
        preserve_matched_msft_residuals=True,
        min_residual_length=20.0,
        assume_missing_crs_as_target=False,
        duplicate_buffer_dist=12.0,
        duplicate_coverage_threshold=0.92,
        duplicate_angle_threshold=28.0,
        duplicate_max_centerline_dist=10.0,
        enable_group_duplicate_removal=True,
        group_duplicate_buffer_dist=8.0,
        group_duplicate_coverage_threshold=0.90,
        group_duplicate_angle_threshold=22.0,
        group_duplicate_mean_distance=5.0,
        group_duplicate_p90_distance=9.0,
        duplicate_sample_step=40.0,
        enable_near_base_return_pruning=True,
        near_base_return_endpoint_radius=15.0,
        near_base_return_corridor_dist=15.0,
        near_base_return_coverage_threshold=0.85,
        near_base_return_mean_distance=7.0,
        near_base_return_p90_distance=12.0,
        near_base_return_max_distance=18.0,
        near_base_return_sample_step=40.0,
        enable_crossing_duplicate_pruning=True,
        crossing_corridor_dist=15.0,
        crossing_coverage_threshold=0.82,
        crossing_mean_distance=7.0,
        crossing_p90_distance=12.0,
        crossing_max_distance=20.0,
        crossing_angle_threshold=25.0,
        crossing_touch_tolerance=1.0,
        crossing_sample_step=40.0,
        endpoint_snap_radius=12.0,
        min_length_after_snap=1.0,
        max_endpoint_snap_bend_angle=40.0,
        enable_dangle_cleanup=False,
        cleanup_mode="fast",
        run_second_clean_pass=False,
        use_pyogrio_io=True,
        read_only_needed_columns=False,
        preclip_to_bounds_intersection=True,
        preclip_margin_degrees=0.02,
        use_prepared_cache=False,
        output_crs="EPSG:4326",
    )

    fuse_roads_pipeline(
        osm_path=BASE_WATERWAYS,
        msft_path=SUPPLEMENT_WATERWAYS,
        output_path=OUTPUT_PATH,
        cfg=cfg,
    )
    polish_waterway_attributes(OUTPUT_PATH, FINAL_OUTPUT_PATH, cfg)


if __name__ == "__main__":
    main()
