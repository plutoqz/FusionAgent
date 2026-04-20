from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Dict, List

import geopandas as gpd
import numpy as np
import pandas as pd

from utils.field_mapping import apply_field_mapping, ensure_numeric
from utils.legacy_loader import load_legacy_module


ROOT = Path(__file__).resolve().parents[1]
BUILD_ALGO_PATH = ROOT / "Algorithm" / "build.py"


@dataclass(frozen=True)
class BuildingFusionParameters:
    match_similarity_threshold: float = 0.3
    one_to_one_min_area_similarity: float = 0.3
    one_to_one_min_shape_similarity: float = 0.3
    one_to_one_min_overlap_similarity: float = 0.3


def _to_target_crs(gdf: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        gdf = gdf.set_crs(target_crs)
    return gdf.to_crs(target_crs)


def _as_float(value: object, default: float) -> float:
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return default


def _resolve_building_parameters(parameters: Dict[str, object] | None) -> BuildingFusionParameters:
    parameters = parameters or {}
    return BuildingFusionParameters(
        match_similarity_threshold=_as_float(parameters.get("match_similarity_threshold"), 0.3),
        one_to_one_min_area_similarity=_as_float(parameters.get("one_to_one_min_area_similarity"), 0.3),
        one_to_one_min_shape_similarity=_as_float(parameters.get("one_to_one_min_shape_similarity"), 0.3),
        one_to_one_min_overlap_similarity=_as_float(parameters.get("one_to_one_min_overlap_similarity"), 0.3),
    )


def _label_building_matches(
    similarity_gdf: gpd.GeoDataFrame,
    *,
    match_similarity_threshold: float,
) -> gpd.GeoDataFrame:
    if similarity_gdf.empty:
        similarity_gdf = similarity_gdf.copy()
        similarity_gdf["label"] = pd.Series(dtype=str)
        return similarity_gdf

    labeled = similarity_gdf.copy()
    labeled["label"] = pd.Series(pd.NA, index=labeled.index, dtype="object")
    labeled.loc[labeled["similarity"] > match_similarity_threshold, "label"] = "1"
    return labeled


def _split_building_one_to_one_by_thresholds(
    gdf_1to1_result: gpd.GeoDataFrame,
    params: BuildingFusionParameters,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    filtered = gdf_1to1_result[
        (gdf_1to1_result["sim_area"] < params.one_to_one_min_area_similarity)
        | (gdf_1to1_result["sim_shape"] < params.one_to_one_min_shape_similarity)
        | (gdf_1to1_result["sim_overlap"] < params.one_to_one_min_overlap_similarity)
    ].copy()
    accepted = gdf_1to1_result[
        (gdf_1to1_result["sim_area"] >= params.one_to_one_min_area_similarity)
        & (gdf_1to1_result["sim_shape"] >= params.one_to_one_min_shape_similarity)
        & (gdf_1to1_result["sim_overlap"] >= params.one_to_one_min_overlap_similarity)
    ].copy()
    return filtered, accepted


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
    gdf.loc[(gdf["confidence"] < 0) | (gdf["confidence"] > 1), "confidence"] = np.nan
    gdf["confidence"] = gdf["confidence"].fillna(1.0)

    if "area_in_me" not in gdf.columns:
        gdf["area_in_me"] = gdf.geometry.area
    else:
        gdf["area_in_me"] = gdf["area_in_me"].fillna(gdf.geometry.area)

    centroid_ll = gpd.GeoSeries(gdf.geometry.centroid, crs=target_crs).to_crs("EPSG:4326")
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


def _feature_count_from_path(path: Path) -> int:
    try:
        import pyogrio

        info = pyogrio.read_info(path)
        return int(info.get("features") or 0)
    except Exception:  # noqa: BLE001
        try:
            import fiona

            with fiona.open(path) as src:
                return len(src)
        except Exception:  # noqa: BLE001
            return int(len(gpd.read_file(path)))


def _legacy_feature_limit() -> int:
    raw = os.getenv("GEOFUSION_BUILDING_LEGACY_MAX_FEATURES", "250000")
    try:
        return max(0, int(raw))
    except Exception:  # noqa: BLE001
        return 250000


def _should_use_safe_building_algorithm(osm_shp: Path, ref_shp: Path) -> tuple[bool, int, int, int]:
    limit = _legacy_feature_limit()
    if limit <= 0:
        return False, 0, 0, limit
    osm_count = _feature_count_from_path(osm_shp)
    ref_count = _feature_count_from_path(ref_shp)
    return max(osm_count, ref_count) > limit, osm_count, ref_count, limit


def _finalize_building_output(frame: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
    output = frame.copy()
    if output.crs is None:
        output = output.set_crs(target_crs)
    else:
        output = output.to_crs(target_crs)
    output = output[~output.geometry.is_empty & output.geometry.notna()].copy()
    for column in ["osm_id", "fclass", "name", "type", "longitude", "latitude", "area_in_me", "confidence"]:
        if column not in output.columns:
            output[column] = np.nan
    return gpd.GeoDataFrame(
        output[["osm_id", "fclass", "name", "type", "longitude", "latitude", "area_in_me", "confidence", "geometry"]],
        geometry="geometry",
        crs=target_crs,
    )


def _build_unmatched_osm_frame(osm_data: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
    fallback = osm_data.copy()
    centroid_ll = gpd.GeoSeries(fallback.geometry.centroid, crs=target_crs).to_crs("EPSG:4326")
    fallback["longitude"] = centroid_ll.x
    fallback["latitude"] = centroid_ll.y
    fallback["area_in_me"] = fallback.geometry.area
    fallback["confidence"] = 1.0
    return _finalize_building_output(fallback, target_crs)


def _build_unmatched_ref_frame(ref_data: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
    fallback = ref_data.copy()
    fallback["osm_id"] = np.nan
    fallback["fclass"] = "ref_building"
    fallback["name"] = np.nan
    fallback["type"] = np.nan
    return _finalize_building_output(fallback, target_crs)


def run_building_fusion_safe(
    osm_shp: Path,
    ref_shp: Path,
    output_dir: Path,
    target_crs: str = "EPSG:32643",
    field_mapping: Dict[str, Dict[str, str]] | None = None,
    debug: bool = False,
    parameters: Dict[str, object] | None = None,
) -> Path:
    del debug
    resolved_parameters = _resolve_building_parameters(parameters)

    osm_raw = gpd.read_file(osm_shp)
    ref_raw = gpd.read_file(ref_shp)

    osm_data = _prepare_osm_building(osm_raw, target_crs, (field_mapping or {}).get("osm"))
    ref_data = _prepare_ref_building(ref_raw, target_crs, (field_mapping or {}).get("ref"))

    if osm_data.empty and ref_data.empty:
        raise ValueError("Both OSM and reference building datasets are empty.")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_shp = output_dir / "fused_buildings.shp"

    if osm_data.empty:
        _build_unmatched_ref_frame(ref_data, target_crs).to_file(output_shp)
        return output_shp

    if ref_data.empty:
        _build_unmatched_osm_frame(osm_data, target_crs).to_file(output_shp)
        return output_shp

    osm = osm_data.reset_index(drop=True).copy()
    ref = ref_data.reset_index(drop=True).copy()
    osm["_osm_row"] = np.arange(len(osm))
    ref["_ref_row"] = np.arange(len(ref))

    candidate_pairs = gpd.sjoin(
        osm[["_osm_row", "geometry"]],
        ref[["_ref_row", "geometry"]],
        how="inner",
        predicate="intersects",
    )

    matched_rows = pd.DataFrame(columns=["_osm_row", "_ref_row", "similarity"])
    if not candidate_pairs.empty:
        osm_rows = candidate_pairs["_osm_row"].to_numpy(dtype=int)
        ref_rows = candidate_pairs["_ref_row"].to_numpy(dtype=int)
        osm_geoms = gpd.GeoSeries(osm.geometry.iloc[osm_rows].reset_index(drop=True), crs=target_crs)
        ref_geoms = gpd.GeoSeries(ref.geometry.iloc[ref_rows].reset_index(drop=True), crs=target_crs)
        intersections = osm_geoms.intersection(ref_geoms)
        min_areas = np.minimum(osm_geoms.area.to_numpy(), ref_geoms.area.to_numpy())
        min_areas[min_areas == 0] = np.nan
        similarities = intersections.area.to_numpy() / min_areas
        matched_rows = pd.DataFrame(
            {
                "_osm_row": osm_rows,
                "_ref_row": ref_rows,
                "similarity": similarities,
            }
        )
        matched_rows = matched_rows[matched_rows["similarity"] >= resolved_parameters.match_similarity_threshold].copy()
        if not matched_rows.empty:
            matched_rows = matched_rows.sort_values("similarity", ascending=False)
            matched_rows = matched_rows.drop_duplicates(subset=["_osm_row"], keep="first")
            matched_rows = matched_rows.drop_duplicates(subset=["_ref_row"], keep="first")

    matched_osm_rows = matched_rows["_osm_row"].to_list() if not matched_rows.empty else []
    matched_ref_rows = matched_rows["_ref_row"].to_list() if not matched_rows.empty else []

    frames: List[gpd.GeoDataFrame] = []
    if matched_osm_rows:
        matched_osm = osm.iloc[matched_osm_rows].reset_index(drop=True).copy()
        matched_ref = ref.iloc[matched_ref_rows].reset_index(drop=True).copy()
        matched = gpd.GeoDataFrame(
            {
                "osm_id": matched_osm["osm_id"].values,
                "fclass": matched_osm["fclass"].values,
                "name": matched_osm["name"].values,
                "type": matched_osm["type"].values,
                "longitude": matched_ref["longitude"].values,
                "latitude": matched_ref["latitude"].values,
                "area_in_me": matched_ref["area_in_me"].values,
                "confidence": matched_ref["confidence"].values,
            },
            geometry=matched_osm.geometry.values,
            crs=target_crs,
        )
        frames.append(_finalize_building_output(matched, target_crs))

    unmatched_osm = osm[~osm["_osm_row"].isin(matched_osm_rows)].copy()
    if not unmatched_osm.empty:
        frames.append(_build_unmatched_osm_frame(unmatched_osm, target_crs))

    unmatched_ref = ref[~ref["_ref_row"].isin(matched_ref_rows)].copy()
    if not unmatched_ref.empty:
        frames.append(_build_unmatched_ref_frame(unmatched_ref, target_crs))

    combined = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry", crs=target_crs)
    combined = _finalize_building_output(combined, target_crs)
    combined.to_file(output_shp)
    return output_shp


def run_building_fusion(
    osm_shp: Path,
    ref_shp: Path,
    output_dir: Path,
    target_crs: str = "EPSG:32643",
    field_mapping: Dict[str, Dict[str, str]] | None = None,
    debug: bool = False,
    parameters: Dict[str, object] | None = None,
) -> Path:
    should_use_safe, osm_count, ref_count, limit = _should_use_safe_building_algorithm(osm_shp, ref_shp)
    if should_use_safe:
        raise RuntimeError(
            "Legacy building fusion skipped for large dataset "
            f"(osm={osm_count}, ref={ref_count}, limit={limit}); use safe fallback."
        )

    legacy_build = load_legacy_module("legacy_build", str(BUILD_ALGO_PATH))
    resolved_parameters = _resolve_building_parameters(parameters)

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
        centroid_ll = gpd.GeoSeries(fallback.geometry.centroid, crs=target_crs).to_crs("EPSG:4326")
        fallback["longitude"] = centroid_ll.x
        fallback["latitude"] = centroid_ll.y
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
    similarity_gdf = _label_building_matches(
        similarity_gdf,
        match_similarity_threshold=resolved_parameters.match_similarity_threshold,
    )
    matched_gdf = (
        similarity_gdf.loc[similarity_gdf.get("label") == "1"].copy()
        if "label" in similarity_gdf.columns
        else similarity_gdf.iloc[0:0].copy()
    )

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
            filter_1to1_gdf, gdf_1to1_result1 = _split_building_one_to_one_by_thresholds(
                gdf_1to1_result,
                resolved_parameters,
            )
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
