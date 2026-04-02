from __future__ import annotations

from pathlib import Path
from typing import Dict

import geopandas as gpd
import numpy as np
import pandas as pd
from rtree import index

from utils.field_mapping import apply_field_mapping
from utils.legacy_loader import load_legacy_module


ROOT = Path(__file__).resolve().parents[1]
ROAD_ALGO_PATH = ROOT / "Algorithm" / "line.py"


def _to_target_crs(gdf: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        gdf = gdf.set_crs(target_crs)
    return gdf.to_crs(target_crs)


def _prepare_osm_road(
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
        gdf["fclass"] = "osm_road"
    return gdf


def _prepare_ref_road(
    gdf: gpd.GeoDataFrame,
    target_crs: str,
    mapping: Dict[str, str] | None,
) -> gpd.GeoDataFrame:
    gdf = apply_field_mapping(gdf, mapping or {})
    gdf = _to_target_crs(gdf, target_crs)
    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()].copy()
    if "FID_1" not in gdf.columns:
        gdf["FID_1"] = np.arange(1, len(gdf) + 1)
    return gdf


def run_road_fusion(
    osm_shp: Path,
    ref_shp: Path,
    output_dir: Path,
    target_crs: str = "EPSG:32643",
    field_mapping: Dict[str, Dict[str, str]] | None = None,
    debug: bool = False,
) -> Path:
    legacy_line = load_legacy_module("legacy_line", str(ROAD_ALGO_PATH))

    osm_raw = gpd.read_file(osm_shp)
    ref_raw = gpd.read_file(ref_shp)
    osm_data = _prepare_osm_road(osm_raw, target_crs, (field_mapping or {}).get("osm"))
    ref_data = _prepare_ref_road(ref_raw, target_crs, (field_mapping or {}).get("ref"))

    if osm_data.empty and ref_data.empty:
        raise ValueError("Both OSM and reference road datasets are empty.")

    output_dir.mkdir(parents=True, exist_ok=True)
    intermediate_dir = output_dir.parent / "intermediate"
    intermediate_dir.mkdir(parents=True, exist_ok=True)

    if osm_data.empty:
        out = output_dir / "fused_roads.shp"
        ref_data.to_file(out)
        return out
    if ref_data.empty:
        out = output_dir / "fused_roads.shp"
        osm_data.to_file(out)
        return out

    osm_processed = legacy_line.process_osm_data(osm_data)
    if "centroid" in osm_processed.columns:
        osm_processed = osm_processed.drop(columns=["centroid"], errors="ignore")
    osm_processed = osm_processed.set_geometry("geometry")
    osm_split = legacy_line.split_features_in_gdf(osm_processed, angle_threshold=legacy_line.ANGLE_THRESHOLD)

    ref_processed = legacy_line.process_msft_data(ref_data)
    if "centroid" in ref_processed.columns:
        ref_processed = ref_processed.drop(columns=["centroid"], errors="ignore")
    ref_processed = ref_processed.set_geometry("geometry")
    ref_split = legacy_line.split_features_in_gdf(ref_processed, angle_threshold=legacy_line.ANGLE_THRESHOLD)

    rtree_idx = index.Index()
    fused_roads, _, _, _ = legacy_line.match_and_fuse(osm_split, ref_split, rtree_idx)
    if "FID_1" not in fused_roads.columns:
        fused_roads["FID_1"] = pd.NA

    fused_raw_path = intermediate_dir / "fused_roads_raw.shp"
    fused_roads.to_file(fused_raw_path)

    dedup_path = intermediate_dir / "fused_roads_dedup.shp"
    legacy_line.process_roads(
        input_path=str(fused_raw_path),
        output_path=str(dedup_path),
        buffer_distance=15,
    )

    final_output = output_dir / "fused_roads.shp"
    gdf = gpd.read_file(dedup_path)
    if gdf.crs is None:
        gdf = gdf.set_crs(target_crs)
    gdf.to_file(final_output)
    return final_output
