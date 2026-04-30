from __future__ import annotations

import geopandas as gpd

from fusion_algorithms.building_height import attach_source_heights_and_final
from fusion_algorithms.contracts import BuildingHeightParams, BuildingRasterPresenceParams, RasterSpec
from fusion_algorithms.fusioncode_loader import load_module


def _validate_existence_parallel(gdf: gpd.GeoDataFrame, raster_path: str, **kwargs):
    module = load_module("temporal_validator")
    return module.validate_existence_parallel(gdf, raster_path, **kwargs)


def _extract_height_parallel(gdf: gpd.GeoDataFrame, raster_path: str, n_jobs: int = -1):
    module = load_module("temporal_validator")
    return module.extract_height_parallel(gdf, raster_path, n_jobs=n_jobs)


def validate_presence_from_raster(
    gdf: gpd.GeoDataFrame,
    raster: RasterSpec,
    params: BuildingRasterPresenceParams | None = None,
) -> gpd.GeoDataFrame:
    params = params or BuildingRasterPresenceParams()
    validated = _validate_existence_parallel(
        gdf.copy(),
        str(raster.path),
        prob_threshold=params.prob_threshold,
        search_dist_m=params.search_dist_m,
        height_thresh=params.height_thresh,
        n_jobs=params.n_jobs,
        confirmed_score_threshold=params.confirmed_score_threshold,
        confirmed_p90_threshold=params.confirmed_p90_threshold,
        confirmed_support_threshold=params.confirmed_support_threshold,
        uncertain_score_threshold=params.uncertain_score_threshold,
        uncertain_max_threshold=params.uncertain_max_threshold,
        uncertain_support_threshold=params.uncertain_support_threshold,
    )
    if params.status_field != "exist_status" and "exist_status" in validated.columns:
        validated[params.status_field] = validated["exist_status"]
    if not params.keep_uncertain and params.status_field in validated.columns:
        validated = validated[validated[params.status_field].astype(str).str.lower() != "uncertain"].copy()
    return validated


def enrich_height_from_raster(
    gdf: gpd.GeoDataFrame,
    raster: RasterSpec,
    params: BuildingHeightParams | None = None,
) -> gpd.GeoDataFrame:
    params = params or BuildingHeightParams()
    enriched = _extract_height_parallel(gdf.copy(), str(raster.path), n_jobs=params.n_jobs)
    source_field = "H_Raster" if "H_Raster" in enriched.columns else params.height_output_field
    if params.positive_only and source_field in enriched.columns:
        enriched.loc[enriched[source_field].fillna(params.fallback_height) < 0, source_field] = params.fallback_height
    if source_field in enriched.columns and params.height_output_field != source_field:
        enriched[params.height_output_field] = enriched[source_field]
    return attach_source_heights_and_final(enriched, {}, params)
