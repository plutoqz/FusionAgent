from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import geopandas as gpd
import numpy as np
import pandas as pd

from utils.field_mapping import apply_field_mapping, ensure_numeric
from utils.legacy_loader import load_legacy_module


ROOT = Path(__file__).resolve().parents[1]
BUILD_ALGO_PATH = ROOT / "Algorithm" / "build.py"


def _to_target_crs(gdf: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        gdf = gdf.set_crs(target_crs)
    return gdf.to_crs(target_crs)


def _prepare_osm_building(
    gdf: gpd.GeoDataFrame,
    target_crs: str,
    mapping: Dict[str, str] | None,
) -> gpd.GeoDataFrame:
    gdf = apply_field_mapping(gdf, mapping or {})
    gdf = _to_target_crs(gdf, target_crs)
    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()].copy()

    if "osm_id" not in gdf.columns:
        gdf["osm_id"] = np.arange(1, len(gdf) + 1)
    if "fclass" not in gdf.columns:
        gdf["fclass"] = "building"
    if "name" not in gdf.columns:
        gdf["name"] = np.nan
    if "type" not in gdf.columns:
        gdf["type"] = np.nan

    keep_cols = ["osm_id", "fclass", "name", "type", "geometry"]
    return gpd.GeoDataFrame(gdf[keep_cols], geometry="geometry", crs=target_crs)


def _prepare_ref_building(
    gdf: gpd.GeoDataFrame,
    target_crs: str,
    mapping: Dict[str, str] | None,
) -> gpd.GeoDataFrame:
    gdf = apply_field_mapping(gdf, mapping or {})
    gdf = _to_target_crs(gdf, target_crs)
    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()].copy()

    if "confidence" not in gdf.columns:
        gdf["confidence"] = 1.0
    gdf = ensure_numeric(gdf, ["confidence", "area_in_me"])
    gdf["confidence"] = gdf["confidence"].fillna(1.0)

    if "area_in_me" not in gdf.columns:
        gdf["area_in_me"] = gdf.geometry.area
    else:
        gdf["area_in_me"] = gdf["area_in_me"].fillna(gdf.geometry.area)

    centroid_ll = gdf.to_crs("EPSG:4326").geometry.centroid
    if "longitude" not in gdf.columns:
        gdf["longitude"] = centroid_ll.x
    else:
        gdf["longitude"] = pd.to_numeric(gdf["longitude"], errors="coerce").fillna(centroid_ll.x)
    if "latitude" not in gdf.columns:
        gdf["latitude"] = centroid_ll.y
    else:
        gdf["latitude"] = pd.to_numeric(gdf["latitude"], errors="coerce").fillna(centroid_ll.y)

    keep_cols = ["longitude", "latitude", "area_in_me", "confidence", "geometry"]
    return gpd.GeoDataFrame(gdf[keep_cols], geometry="geometry", crs=target_crs)


def _as_geodf(df: pd.DataFrame, crs: str) -> gpd.GeoDataFrame:
    if isinstance(df, gpd.GeoDataFrame):
        if df.crs is None:
            return df.set_crs(crs)
        return df.to_crs(crs)
    if "geometry" not in df.columns:
        raise ValueError("Dataframe has no geometry column.")
    return gpd.GeoDataFrame(df.copy(), geometry="geometry", crs=crs)


def _non_empty_frames(frames: List[pd.DataFrame], crs: str) -> List[gpd.GeoDataFrame]:
    output: List[gpd.GeoDataFrame] = []
    for frame in frames:
        if frame is None:
            continue
        if len(frame) == 0:
            continue
        output.append(_as_geodf(frame, crs))
    return output


def run_building_fusion(
    osm_shp: Path,
    ref_shp: Path,
    output_dir: Path,
    target_crs: str = "EPSG:32643",
    field_mapping: Dict[str, Dict[str, str]] | None = None,
    debug: bool = False,
) -> Path:
    legacy_build = load_legacy_module("legacy_build", str(BUILD_ALGO_PATH))

    osm_raw = gpd.read_file(osm_shp)
    ref_raw = gpd.read_file(ref_shp)

    osm_data = _prepare_osm_building(osm_raw, target_crs, (field_mapping or {}).get("osm"))
    ref_data = _prepare_ref_building(ref_raw, target_crs, (field_mapping or {}).get("ref"))

    if osm_data.empty and ref_data.empty:
        raise ValueError("Both OSM and reference building datasets are empty.")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_shp = output_dir / "fused_buildings.shp"

    if osm_data.empty:
        fallback = ref_data.copy()
        fallback["fclass"] = fallback.get("fclass", "ref_building")
        fallback["type"] = fallback.get("type", np.nan)
        fallback["name"] = fallback.get("name", np.nan)
        fallback.to_file(output_shp)
        return output_shp

    if ref_data.empty:
        fallback = osm_data.copy()
        fallback["longitude"] = fallback.geometry.centroid.to_crs("EPSG:4326").x
        fallback["latitude"] = fallback.geometry.centroid.to_crs("EPSG:4326").y
        fallback["area_in_me"] = fallback.geometry.area
        fallback["confidence"] = 1.0
        fallback.to_file(output_shp)
        return output_shp

    gdf1_idx = legacy_build.add_index_column(osm_data.copy())
    gdf2_idx1 = legacy_build.add_index_column1(ref_data.copy())
    gdf1_idx = legacy_build.remove_duplicate_geometries_direct(gdf1_idx)
    gdf2_idx1 = legacy_build.remove_duplicate_geometries_direct(gdf2_idx1)

    new_osm_gdf = legacy_build.find_non_intersecting_buildings(gdf1_idx, gdf2_idx1)

    _, similarity_gdf = legacy_build.calculate_similarity(gdf1_idx, gdf2_idx1)
    if similarity_gdf.empty:
        similarity_gdf["label"] = pd.Series(dtype=str)
    else:
        similarity_gdf.loc[similarity_gdf["similarity"] > 0.3, "label"] = "1"
    matched_gdf = similarity_gdf.loc[similarity_gdf.get("label") == "1"].copy() if "label" in similarity_gdf.columns else similarity_gdf.iloc[0:0].copy()

    merged_gdf = gdf1_idx.merge(matched_gdf, on="idx", how="outer")
    merged_gdf = merged_gdf.merge(gdf2_idx1, on="idx1", how="outer")

    if "label" not in merged_gdf.columns:
        merged_gdf["label"] = np.nan

    merged_gdf1 = merged_gdf[merged_gdf["label"] == "1"].copy()
    if not merged_gdf1.empty:
        merged_gdf1 = legacy_build.get_data_var(merged_gdf1)

    unadjusted_buildings = merged_gdf[merged_gdf["label"] != "1"].copy()
    save_gg_gdf = legacy_build.filter_non_intersecting_osm(unadjusted_buildings)

    gdf_1to1_result2 = gdf_1to1_result3 = gdf_1ton_result = gdf_nto1_result = gdf_ntom_result = None
    if not merged_gdf1.empty:
        gdf_1to1, gdf_1ton, gdf_nto1, gdf_mton = legacy_build.split_relations(merged_gdf1)
        if not gdf_1to1.empty:
            sim_1to1_gdf = legacy_build.get_sim(gdf_1to1)
            gdf_1to1_result = sim_1to1_gdf[
                [
                    "idx1",
                    "idx",
                    "sim_location",
                    "sim_area",
                    "sim_orient",
                    "sim_shape",
                    "sim_overlap",
                    "fclass",
                    "name",
                    "type",
                    "geometry_x",
                    "label",
                    "latitude",
                    "longitude",
                    "confidence",
                    "geometry_y",
                    "area_in_me",
                ]
            ]
            filter_1to1_gdf = gdf_1to1_result[
                (gdf_1to1_result["sim_area"] < 0.3)
                | (gdf_1to1_result["sim_shape"] < 0.3)
                | (gdf_1to1_result["sim_overlap"] < 0.3)
            ]
            gdf_1to1_result1 = gdf_1to1_result[
                (gdf_1to1_result["sim_area"] >= 0.3)
                & (gdf_1to1_result["sim_shape"] >= 0.3)
                & (gdf_1to1_result["sim_overlap"] >= 0.3)
            ]
            if not gdf_1to1_result1.empty:
                gdf_1to1_result2 = legacy_build.attribute_fusion1(gdf_1to1_result1)
            if not filter_1to1_gdf.empty:
                gdf_1to1_result3 = legacy_build.attribute_fusion5(filter_1to1_gdf)

        if not gdf_1ton.empty:
            gdf_1ton_result = legacy_build.attribute_fusion2(gdf_1ton)
        if not gdf_nto1.empty:
            gdf_nto1_result = legacy_build.attribute_fusion3(gdf_nto1)
        if not gdf_mton.empty:
            gdf_ntom_result = legacy_build.attribute_fusion4(gdf_mton)

    frames = _non_empty_frames(
        [
            new_osm_gdf,
            save_gg_gdf,
            gdf_1to1_result3,
            gdf_1to1_result2,
            gdf_1ton_result,
            gdf_nto1_result,
            gdf_ntom_result,
        ],
        target_crs,
    )

    if not frames:
        fallback = ref_data.copy()
        fallback.to_file(output_shp)
        return output_shp

    combined = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry", crs=target_crs)
    combined = combined.to_crs(target_crs)
    for col in ["idx", "idx1", "osm_id", "label"]:
        if col in combined.columns:
            combined = combined.drop(columns=[col])

    combined.to_file(output_shp)
    return output_shp

