from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, MultiLineString

from fusion_algorithms.road_conflation_v7 import RoadConflationV7Config, run_road_conflation_v7
from services.artifact_evaluation_service import evaluate_vector_artifact


def test_run_road_conflation_v7_returns_frame_and_stats() -> None:
    base = gpd.GeoDataFrame(
        {"osm_id": [1], "fclass": ["primary"], "name": ["Main Road"]},
        geometry=[LineString([(0, 0), (10, 0)])],
        crs="EPSG:3857",
    )
    supplement = gpd.GeoDataFrame(
        {"id": [2], "road_class": ["secondary"]},
        geometry=[LineString([(0, 30), (10, 30)])],
        crs="EPSG:3857",
    )

    result = run_road_conflation_v7(
        base,
        supplement,
        config=RoadConflationV7Config(
            target_crs="EPSG:3857",
            do_split_by_angle=False,
            max_segment_length=None,
            enable_dangle_cleanup=False,
        ),
    )

    assert len(result.frame) == 2
    assert result.stats["base_segments"] == 1
    assert result.stats["supplement_segments"] == 1
    assert result.stats["unmatched_supplement_segments"] == 1
    assert result.frame.crs.to_epsg() == 3857
    assert {"fusion_source", "match_role", "road_class", "supplement_segment_id"} <= set(result.frame.columns)
    base_rows = result.frame[result.frame["source_layer"] == "base"]
    assert base_rows.iloc[0]["name"] == "Main Road"
    assert base_rows.iloc[0]["osm_name"] == "Main Road"
    assert base_rows.iloc[0]["road_name"] == "Main Road"
    supplement_rows = result.frame[result.frame["source_layer"] == "supplement"]
    assert supplement_rows.iloc[0]["osm_name"] == ""
    assert supplement_rows.iloc[0]["road_name"] == ""


def test_run_road_conflation_v7_keeps_uncovered_residual_from_matched_supplement() -> None:
    base = gpd.GeoDataFrame(
        {"osm_id": [10], "fclass": ["primary"]},
        geometry=[LineString([(0, 0), (10, 0)])],
        crs="EPSG:3857",
    )
    supplement = gpd.GeoDataFrame(
        {"id": [20], "road_class": ["primary"]},
        geometry=[LineString([(0, 0), (15, 0)])],
        crs="EPSG:3857",
    )

    result = run_road_conflation_v7(
        base,
        supplement,
        config=RoadConflationV7Config(
            target_crs="EPSG:3857",
            do_split_by_angle=False,
            max_segment_length=None,
            match_buffer_dist=0.5,
            max_hausdorff=0.5,
            min_supplement_coverage_for_matched=0.6,
            min_residual_length=1.0,
            enable_dangle_cleanup=False,
        ),
    )

    residual_rows = result.frame[result.frame["residual_from_matched"].fillna(False).astype(bool)]
    assert len(residual_rows) == 1
    assert result.stats["matched_supplement_segments"] == 1
    assert result.stats["residual_supplement_segments"] == 1
    assert residual_rows.iloc[0]["match_role"] == "supplement_uncovered_residual"
    assert residual_rows.iloc[0].geometry.length > 4.0


def test_run_road_conflation_v7_prunes_duplicate_supplements() -> None:
    base = gpd.GeoDataFrame(
        {"osm_id": [1], "fclass": ["primary"]},
        geometry=[LineString([(0, 0), (10, 0)])],
        crs="EPSG:3857",
    )
    supplement = gpd.GeoDataFrame(
        {"id": [2, 3], "road_class": ["service", "service"]},
        geometry=[
            LineString([(0, 40), (10, 40)]),
            LineString([(0, 40.1), (10, 40.1)]),
        ],
        crs="EPSG:3857",
    )

    result = run_road_conflation_v7(
        base,
        supplement,
        config=RoadConflationV7Config(
            target_crs="EPSG:3857",
            do_split_by_angle=False,
            max_segment_length=None,
            duplicate_buffer_dist=1.0,
            duplicate_max_centerline_dist=1.0,
            duplicate_coverage_threshold=0.9,
            enable_group_duplicate_removal=False,
            enable_near_base_return_pruning=False,
            enable_crossing_duplicate_pruning=False,
            enable_dangle_cleanup=False,
        ),
    )

    supplement_rows = result.frame[result.frame["source_layer"] == "supplement"]
    assert len(supplement_rows) == 1
    assert result.stats["duplicate_removed_before_snap"] == 1


def test_run_road_conflation_v7_preserves_uppercase_fid_supplement_id() -> None:
    base = gpd.GeoDataFrame(
        {"osm_id": [1], "fclass": ["primary"]},
        geometry=[LineString([(0, 0), (10, 0)])],
        crs="EPSG:3857",
    )
    supplement = gpd.GeoDataFrame(
        {"FID": [12345]},
        geometry=[LineString([(0, 30), (10, 30)])],
        crs="EPSG:3857",
    )

    result = run_road_conflation_v7(
        base,
        supplement,
        config=RoadConflationV7Config(
            target_crs="EPSG:3857",
            do_split_by_angle=False,
            max_segment_length=None,
            enable_dangle_cleanup=False,
        ),
    )

    supplement_rows = result.frame[result.frame["source_layer"] == "supplement"]
    assert supplement_rows.iloc[0]["supplement_segment_id"] == "12345"


def test_run_road_conflation_v7_cleans_pseudo_empty_name_values() -> None:
    base = gpd.GeoDataFrame(
        {"osm_id": [1], "fclass": ["primary"], "name": ["<NA>"]},
        geometry=[LineString([(0, 0), (10, 0)])],
        crs="EPSG:3857",
    )
    supplement = gpd.GeoDataFrame(
        {"id": [2]},
        geometry=[LineString([(0, 30), (10, 30)])],
        crs="EPSG:3857",
    )

    result = run_road_conflation_v7(
        base,
        supplement,
        config=RoadConflationV7Config(
            target_crs="EPSG:3857",
            do_split_by_angle=False,
            max_segment_length=None,
            enable_dangle_cleanup=False,
        ),
    )

    base_rows = result.frame[result.frame["source_layer"] == "base"]
    assert base_rows.iloc[0]["name"] == ""
    assert base_rows.iloc[0]["osm_name"] == ""
    assert base_rows.iloc[0]["road_name"] == ""


def test_run_road_conflation_v7_preserves_osm_name_from_common_alias_columns() -> None:
    base = gpd.GeoDataFrame(
        {"osm_id": [1], "fclass": ["primary"], "Name": ["Ring Road"]},
        geometry=[LineString([(0, 0), (10, 0)])],
        crs="EPSG:3857",
    )
    supplement = gpd.GeoDataFrame(
        {"id": [2], "road_class": ["secondary"]},
        geometry=[LineString([(0, 30), (10, 30)])],
        crs="EPSG:3857",
    )

    result = run_road_conflation_v7(
        base,
        supplement,
        config=RoadConflationV7Config(
            target_crs="EPSG:3857",
            do_split_by_angle=False,
            max_segment_length=None,
            enable_dangle_cleanup=False,
        ),
    )

    base_rows = result.frame[result.frame["source_layer"] == "base"]
    assert base_rows.iloc[0]["name"] == "Ring Road"
    assert base_rows.iloc[0]["osm_name"] == "Ring Road"
    assert base_rows.iloc[0]["road_name"] == "Ring Road"


def test_run_road_conflation_v7_accepts_paths_and_multiline_inputs(tmp_path: Path) -> None:
    base = gpd.GeoDataFrame(
        {"osm_id": [1], "fclass": ["residential"]},
        geometry=[MultiLineString([[(0, 0), (5, 0)], [(5, 0), (10, 0)]])],
        crs="EPSG:3857",
    )
    supplement = gpd.GeoDataFrame(
        {"id": [2], "road_class": ["residential"]},
        geometry=[MultiLineString([[(0, 10), (5, 10)], [(5, 10), (10, 10)]])],
        crs="EPSG:3857",
    )
    base_path = tmp_path / "base.gpkg"
    supplement_path = tmp_path / "supplement.gpkg"
    base.to_file(base_path, driver="GPKG")
    supplement.to_file(supplement_path, driver="GPKG")

    result = run_road_conflation_v7(
        base_path,
        supplement_path,
        config=RoadConflationV7Config(
            target_crs="EPSG:3857",
            do_split_by_angle=False,
            max_segment_length=None,
            enable_dangle_cleanup=False,
        ),
    )

    assert not result.frame.empty
    assert set(result.frame.geom_type.unique()) <= {"LineString"}
    assert result.stats["base_segments"] == 2
    assert result.stats["supplement_segments"] == 2


def test_road_conflation_v7_golden_metrics_remain_stable(tmp_path: Path) -> None:
    base = gpd.GeoDataFrame(
        {"osm_id": [1], "fclass": ["primary"], "name": ["Main Road"]},
        geometry=[LineString([(0, 0), (10, 0)])],
        crs="EPSG:3857",
    )
    supplement = gpd.GeoDataFrame(
        {"id": [2], "road_class": ["secondary"]},
        geometry=[LineString([(0, 30), (10, 30)])],
        crs="EPSG:3857",
    )
    result = run_road_conflation_v7(
        base,
        supplement,
        config=RoadConflationV7Config(
            target_crs="EPSG:3857",
            do_split_by_angle=False,
            max_segment_length=None,
            enable_dangle_cleanup=False,
        ),
    )
    output_path = tmp_path / "road_v7.gpkg"
    result.frame.to_file(output_path, driver="GPKG")

    metrics = evaluate_vector_artifact(output_path, required_fields=["fusion_source", "source_layer"])

    assert result.stats["base_segments"] == 1
    assert result.stats["supplement_segments"] == 1
    assert metrics["artifact_validity"] is True
    assert metrics["invalid_geometry_rate"] == 0.0
    assert metrics["zero_length_geometry_count"] == 0
