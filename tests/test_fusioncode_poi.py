from __future__ import annotations

import geopandas as gpd
from shapely.geometry import Point

from fusion_algorithms.contracts import ConflictDetectionParams, PoiFusionParams
from fusion_algorithms.poi_fusion import build_geohash_candidates, match_poi_neighbors
from fusion_algorithms.quality import detect_spatial_conflicts


def test_poi_geohash_candidates_match_same_hash() -> None:
    base = gpd.GeoDataFrame({"GeoHash": ["abc"], "name": ["Clinic"]}, geometry=[Point(0, 0)], crs="EPSG:4326")
    target = gpd.GeoDataFrame({"GeoHash": ["abc"], "name": ["Clinic"]}, geometry=[Point(0, 0)], crs="EPSG:4326")
    candidates = build_geohash_candidates(base, target, PoiFusionParams(name_similarity_threshold=0.8))
    assert len(candidates) == 1
    assert candidates.iloc[0]["name_score"] == 1.0


def test_poi_distance_fallback_when_geohash_missing() -> None:
    base = gpd.GeoDataFrame({"name": ["Clinic"]}, geometry=[Point(0, 0)], crs="EPSG:3857")
    target = gpd.GeoDataFrame({"name": ["Clinic"]}, geometry=[Point(1, 0)], crs="EPSG:3857")
    matches = match_poi_neighbors(base, target, PoiFusionParams(duplicate_distance_m=5.0))
    assert len(matches) == 1


def test_conflict_detection_reports_polygon_overlap() -> None:
    gdf = gpd.GeoDataFrame({"id": [1, 2]}, geometry=[Point(0, 0).buffer(2), Point(1, 0).buffer(2)], crs="EPSG:3857")
    conflicts = detect_spatial_conflicts(gdf, ConflictDetectionParams(overlap_area_min=0.1))
    assert len(conflicts) == 1
    assert conflicts[0]["overlap_area"] > 0.1
