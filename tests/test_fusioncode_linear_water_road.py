from __future__ import annotations

import geopandas as gpd
from shapely.geometry import LineString, box

from fusion_algorithms.contracts import RoadFusionParams, WaterPolygonFusionParams
from fusion_algorithms.road_fusion import (
    build_road_match_candidates,
    remove_duplicate_roads,
    run_road_segment_match_topology,
    split_features_in_gdf,
)
from fusion_algorithms.water_fusion import fuse_water_polygons, match_water_polygons


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


def test_run_road_segment_match_topology_returns_base_when_reference_is_empty() -> None:
    base = gpd.GeoDataFrame(
        {"id": [1, 2]},
        geometry=[LineString([(0, 0), (10, 0)]), LineString([(10, 0), (20, 0)])],
        crs="EPSG:3857",
    )
    empty_ref = gpd.GeoDataFrame({"id": []}, geometry=[], crs="EPSG:3857")

    result = run_road_segment_match_topology(base, empty_ref)

    assert len(result) == 2
    assert list(result["id"]) == [1, 2]
    assert set(result["SRC"]) == {"base"}


def test_run_road_segment_match_topology_keeps_unmatched_reference_segments() -> None:
    base = gpd.GeoDataFrame({"id": [1]}, geometry=[LineString([(0, 0), (10, 0)])], crs="EPSG:3857")
    reference = gpd.GeoDataFrame({"id": [2]}, geometry=[LineString([(0, 20), (10, 20)])], crs="EPSG:3857")

    result = run_road_segment_match_topology(base, reference)

    assert len(result) == 2
    assert set(result["SRC"]) == {"base", "target"}


def test_remove_duplicate_roads_drops_shorter_contained_segments_only() -> None:
    roads = gpd.GeoDataFrame(
        {"id": [1, 2, 3]},
        geometry=[
            LineString([(0, 0), (20, 0)]),
            LineString([(2, 0), (18, 0)]),
            LineString([(0, 50), (20, 50)]),
        ],
        crs="EPSG:3857",
    )

    result = remove_duplicate_roads(roads, RoadFusionParams(dedupe_buffer_m=1.0))

    assert list(result["id"]) == [1, 3]


def test_fuse_water_polygons_returns_empty_frame_when_both_inputs_are_empty() -> None:
    empty_base = gpd.GeoDataFrame({"id": []}, geometry=[], crs="EPSG:3857")
    empty_ref = gpd.GeoDataFrame({"id": []}, geometry=[], crs="EPSG:3857")

    result = fuse_water_polygons(empty_base, empty_ref)

    assert result.empty
    assert result.crs.to_epsg() == 3857
