from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class RoadFusionParameters:
    angle_threshold_deg: int = 135
    snap_tolerance_m: float = 1.0
    match_buffer_m: float = 20.0
    max_hausdorff_m: float = 15.0
    dedupe_buffer_m: float = 15.0


def _to_target_crs(gdf: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        gdf = gdf.set_crs(target_crs)
    return gdf.to_crs(target_crs)


def _as_float(value: object, default: float) -> float:
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return default


def _as_int(value: object, default: int) -> int:
    try:
        return int(float(value))
    except Exception:  # noqa: BLE001
        return default


def _resolve_road_parameters(parameters: Dict[str, object] | None) -> RoadFusionParameters:
    parameters = parameters or {}
    return RoadFusionParameters(
        angle_threshold_deg=_as_int(parameters.get("angle_threshold_deg"), 135),
        snap_tolerance_m=_as_float(parameters.get("snap_tolerance_m"), 1.0),
        match_buffer_m=_as_float(parameters.get("match_buffer_m"), 20.0),
        max_hausdorff_m=_as_float(parameters.get("max_hausdorff_m"), 15.0),
        dedupe_buffer_m=_as_float(parameters.get("dedupe_buffer_m"), 15.0),
    )


def _apply_road_parameters(legacy_line: object, params: RoadFusionParameters) -> None:
    setattr(legacy_line, "ANGLE_THRESHOLD", params.angle_threshold_deg)
    setattr(legacy_line, "SNAP_TOLERANCE", params.snap_tolerance_m)
    setattr(legacy_line, "BUFFER_DIST", params.match_buffer_m)
    setattr(legacy_line, "MAX_HAUSDORFF", params.max_hausdorff_m)


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
    parameters: Dict[str, object] | None = None,
) -> Path:
    legacy_line = load_legacy_module("legacy_line", str(ROAD_ALGO_PATH))
    resolved_parameters = _resolve_road_parameters(parameters)
    _apply_road_parameters(legacy_line, resolved_parameters)

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
    osm_split = legacy_line.split_features_in_gdf(
        osm_processed,
        angle_threshold=resolved_parameters.angle_threshold_deg,
    )

    ref_processed = legacy_line.process_msft_data(ref_data)
    if "centroid" in ref_processed.columns:
        ref_processed = ref_processed.drop(columns=["centroid"], errors="ignore")
    ref_processed = ref_processed.set_geometry("geometry")
    ref_split = legacy_line.split_features_in_gdf(
        ref_processed,
        angle_threshold=resolved_parameters.angle_threshold_deg,
    )

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
        buffer_distance=resolved_parameters.dedupe_buffer_m,
    )

    final_output = output_dir / "fused_roads.shp"
    gdf = gpd.read_file(dedup_path)
    if gdf.crs is None:
        gdf = gdf.set_crs(target_crs)
    gdf.to_file(final_output)
    return final_output
