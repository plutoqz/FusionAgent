from __future__ import annotations

import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, Polygon

from fusion_algorithms.waterways_conflation_v7 import (
    WaterwaysConflationV7Config,
    run_waterways_conflation_v7,
)
from services.artifact_evaluation_service import evaluate_vector_artifact


def test_run_waterways_conflation_v7_emits_canonical_schema() -> None:
    base = gpd.GeoDataFrame(
        {"osm_id": [1], "fclass": ["river"], "name": ["Base River"]},
        geometry=[LineString([(0, 0), (10, 0)])],
        crs="EPSG:3857",
    )
    supplement = gpd.GeoDataFrame(
        {
            "osm_id": [101],
            "waterway": ["stream"],
            "name": ["Supplement Stream"],
            "name_en": ["Supplement Stream"],
            "name_ur": ["سپلیمنٹ"],
            "source": ["local_manual"],
        },
        geometry=[LineString([(0, 40), (10, 40)])],
        crs="EPSG:3857",
    )

    result = run_waterways_conflation_v7(
        base,
        supplement,
        config=WaterwaysConflationV7Config(
            target_crs="EPSG:3857",
            do_split_by_angle=False,
            max_segment_length=None,
            enable_dangle_cleanup=False,
        ),
    )

    expected_columns = {
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
        "supplement_source",
        "source_layer",
        "residual_from_matched",
        "residual_part",
        "residual_parent_FID_1",
        "geometry",
    }
    assert expected_columns <= set(result.frame.columns)
    assert result.stats["base_segments"] == 1
    assert result.stats["supplement_segments"] == 1
    assert set(result.frame.geom_type.unique()) <= {"LineString", "MultiLineString"}
    assert result.frame.loc[result.frame["source_layer"] == "supplement", "waterway_class"].iloc[0] == "stream"


def test_run_waterways_conflation_v7_keeps_line_geometries_only() -> None:
    base = gpd.GeoDataFrame(
        {"osm_id": [1], "fclass": ["river"]},
        geometry=[MultiLineString([[(0, 0), (5, 0)], [(5, 0), (10, 0)]])],
        crs="EPSG:3857",
    )
    supplement = gpd.GeoDataFrame(
        {"osm_id": [2], "waterway": ["canal"]},
        geometry=[LineString([(0, 10), (10, 10)])],
        crs="EPSG:3857",
    )

    result = run_waterways_conflation_v7(
        base,
        supplement,
        config=WaterwaysConflationV7Config(
            target_crs="EPSG:3857",
            do_split_by_angle=False,
            max_segment_length=None,
            enable_dangle_cleanup=False,
        ),
    )

    assert set(result.frame.geom_type.unique()) <= {"LineString"}


def test_run_waterways_conflation_v7_rejects_polygon_features_during_normalized_output() -> None:
    base = gpd.GeoDataFrame(
        {"osm_id": [1], "fclass": ["river"]},
        geometry=[LineString([(0, 0), (10, 0)])],
        crs="EPSG:3857",
    )
    supplement = gpd.GeoDataFrame(
        {"osm_id": [2], "waterway": ["stream"]},
        geometry=[Polygon([(0, 10), (2, 10), (2, 12), (0, 12)])],
        crs="EPSG:3857",
    )

    result = run_waterways_conflation_v7(
        base,
        supplement,
        config=WaterwaysConflationV7Config(
            target_crs="EPSG:3857",
            do_split_by_angle=False,
            max_segment_length=None,
            enable_dangle_cleanup=False,
        ),
    )

    assert len(result.frame) == 1
    assert result.stats["supplement_segments"] == 0


def test_waterways_conflation_v7_golden_metrics_remain_stable(tmp_path) -> None:
    base = gpd.GeoDataFrame(
        {"osm_id": [1], "fclass": ["river"], "name": ["Base River"]},
        geometry=[LineString([(0, 0), (10, 0)])],
        crs="EPSG:3857",
    )
    supplement = gpd.GeoDataFrame(
        {"osm_id": [101], "waterway": ["stream"], "name": ["Supplement Stream"]},
        geometry=[LineString([(0, 40), (10, 40)])],
        crs="EPSG:3857",
    )
    result = run_waterways_conflation_v7(
        base,
        supplement,
        config=WaterwaysConflationV7Config(
            target_crs="EPSG:3857",
            do_split_by_angle=False,
            max_segment_length=None,
            enable_dangle_cleanup=False,
        ),
    )
    output_path = tmp_path / "waterways_v7.gpkg"
    result.frame.to_file(output_path, driver="GPKG")

    metrics = evaluate_vector_artifact(output_path, required_fields=["fusion_source", "source_layer"])

    assert result.stats["base_segments"] == 1
    assert result.stats["supplement_segments"] == 1
    assert metrics["artifact_validity"] is True
    assert metrics["invalid_geometry_rate"] == 0.0
    assert set(metrics["geometry_types"]) <= {"LineString", "MultiLineString"}
