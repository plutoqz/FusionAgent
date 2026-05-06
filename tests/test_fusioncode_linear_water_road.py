from __future__ import annotations

import geopandas as gpd
from shapely.geometry import LineString, box

from fusion_algorithms.contracts import RoadFusionParams, WaterPolygonFusionParams
from fusion_algorithms.road_fusion import build_road_match_candidates, split_features_in_gdf
from fusion_algorithms.water_fusion import match_water_polygons


def test_road_match_candidates_use_decoupled_thresholds() -> None:
    base = gpd.GeoDataFrame({"id": [1]}, geometry=[LineString([(0, 0), (10, 0)])], crs="EPSG:3857")
    target = gpd.GeoDataFrame({"id": [2]}, geometry=[LineString([(0, 0.5), (10, 0.5)])], crs="EPSG:3857")
    candidates = build_road_match_candidates(
        base,
        target,
        RoadFusionParams(buffer_dist_m=2.0, max_hausdorff_m=2.0, angle_diff_max_deg=5.0),
    )
    assert len(candidates) == 1


def test_split_features_respects_angle_threshold() -> None:
    gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[LineString([(0, 0), (1, 0), (1, 1)])], crs="EPSG:3857")
    split = split_features_in_gdf(gdf, RoadFusionParams(angle_threshold_deg=135))
    assert len(split) == 2


def test_water_polygon_overlap_threshold_is_parameterized() -> None:
    base = gpd.GeoDataFrame({"id": [1]}, geometry=[box(0, 0, 2, 2)], crs="EPSG:3857")
    target = gpd.GeoDataFrame({"id": [2]}, geometry=[box(1, 1, 3, 3)], crs="EPSG:3857")
    loose = match_water_polygons(base, target, WaterPolygonFusionParams(overlap_threshold=0.2))
    strict = match_water_polygons(base, target, WaterPolygonFusionParams(overlap_threshold=0.5))
    assert len(loose) == 1
    assert strict.empty
