from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point, Polygon

from schemas.task_kind import TaskKind
from services.quality_gate_service import QualityGateService


def test_quality_gate_accepts_multisource_building_gpkg(tmp_path: Path) -> None:
    path = tmp_path / "building.gpkg"
    frame = gpd.GeoDataFrame(
        {"source_id": ["raw.osm.building", "raw.microsoft.building"], "confidence": [0.9, 0.8]},
        geometry=[
            Polygon([(0, 0), (0, 1), (1, 1), (1, 0)]),
            Polygon([(2, 0), (2, 1), (3, 1), (3, 0)]),
        ],
        crs="EPSG:4326",
    )
    frame.to_file(path, driver="GPKG")

    report = QualityGateService().evaluate(
        artifact_path=path,
        task_kind=TaskKind.building,
        required_fields=["geometry", "source_id"],
        requested_bbox=(-1, -1, 4, 2),
        component_coverage={
            "raw.osm.building": {"feature_count": 1, "coverage_status": "available"},
            "raw.microsoft.building": {"feature_count": 1, "coverage_status": "available"},
        },
    )

    assert report.accepted is True
    assert report.checks["non_empty"]["passed"] is True
    assert report.checks["multi_source_lineage"]["passed"] is True


def test_quality_gate_rejects_wrong_geometry_for_waterways(tmp_path: Path) -> None:
    path = tmp_path / "waterways.gpkg"
    frame = gpd.GeoDataFrame({"source_id": ["raw.osm.waterways"]}, geometry=[Point(0, 0)], crs="EPSG:4326")
    frame.to_file(path, driver="GPKG")

    report = QualityGateService().evaluate(
        artifact_path=path,
        task_kind=TaskKind.waterways,
        required_fields=["geometry", "source_id"],
        requested_bbox=(-1, -1, 1, 1),
        component_coverage={"raw.osm.waterways": {"feature_count": 1, "coverage_status": "available"}},
    )

    assert report.accepted is False
    assert report.checks["geometry_type"]["passed"] is False


def test_quality_gate_rejects_duplicate_geometry_above_policy_threshold(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.gpkg"
    polygon = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
    frame = gpd.GeoDataFrame(
        {"source_id": ["raw.osm.building", "raw.microsoft.building"]},
        geometry=[polygon, polygon],
        crs="EPSG:4326",
    )
    frame.to_file(path, driver="GPKG")

    report = QualityGateService().evaluate(
        artifact_path=path,
        task_kind=TaskKind.building,
        required_fields=["geometry", "source_id"],
        requested_bbox=(-1, -1, 2, 2),
        component_coverage={
            "raw.osm.building": {"feature_count": 1, "coverage_status": "available"},
            "raw.microsoft.building": {"feature_count": 1, "coverage_status": "available"},
        },
        quality_policy_id="quality.default.building.v1",
    )

    assert report.accepted is False
    assert report.policy_id == "quality.default.building.v1"
    assert "duplicate_geometry_rate" in report.failure_reasons


def test_quality_gate_rejects_building_self_intersection_and_sliver_polygons(tmp_path: Path) -> None:
    path = tmp_path / "bad_building.gpkg"
    frame = gpd.GeoDataFrame(
        {"source_id": ["raw.osm.building", "raw.microsoft.building"]},
        geometry=[
            Polygon([(0, 0), (10, 10), (10, 0), (0, 10)]),
            Polygon([(0, 0), (0, 0.000001), (0.000001, 0.000001), (0.000001, 0)]),
        ],
        crs="EPSG:4326",
    )
    frame.to_file(path, driver="GPKG")

    report = QualityGateService().evaluate(
        artifact_path=path,
        task_kind=TaskKind.building,
        required_fields=["geometry", "source_id"],
        requested_bbox=(-1, -1, 11, 11),
        component_coverage={
            "raw.osm.building": {"feature_count": 1, "coverage_status": "available"},
            "raw.microsoft.building": {"feature_count": 1, "coverage_status": "available"},
        },
        quality_policy_id="quality.default.building.v1",
    )

    assert report.accepted is False
    assert "self_intersection_count" in report.failure_reasons
    assert "sliver_polygon_count" in report.failure_reasons


def test_quality_gate_rejects_road_zero_length_geometry(tmp_path: Path) -> None:
    path = tmp_path / "bad_road.gpkg"
    frame = gpd.GeoDataFrame(
        {"source_id": ["raw.osm.road", "raw.ms.road"]},
        geometry=[
            LineString([(0, 0), (1, 0)]),
            LineString([(1, 0), (1, 0)]),
        ],
        crs="EPSG:4326",
    )
    frame.to_file(path, driver="GPKG")

    report = QualityGateService().evaluate(
        artifact_path=path,
        task_kind=TaskKind.road,
        required_fields=["geometry", "source_id"],
        requested_bbox=(-1, -1, 2, 1),
        component_coverage={
            "raw.osm.road": {"feature_count": 1, "coverage_status": "available"},
            "raw.ms.road": {"feature_count": 1, "coverage_status": "available"},
        },
        quality_policy_id="quality.default.road.v1",
    )

    assert report.accepted is False
    assert "zero_length_geometry_count" in report.failure_reasons


def test_quality_gate_rejects_water_polygon_self_intersection_and_sliver_polygons(tmp_path: Path) -> None:
    path = tmp_path / "bad_water_polygon.gpkg"
    frame = gpd.GeoDataFrame(
        {"source_id": ["raw.osm.water", "raw.ms.water"]},
        geometry=[
            Polygon([(0, 0), (10, 10), (10, 0), (0, 10)]),
            Polygon([(0, 0), (0, 0.000001), (0.000001, 0.000001), (0.000001, 0)]),
        ],
        crs="EPSG:4326",
    )
    frame.to_file(path, driver="GPKG")

    report = QualityGateService().evaluate(
        artifact_path=path,
        task_kind=TaskKind.water_polygon,
        required_fields=["geometry", "source_id"],
        requested_bbox=(-1, -1, 11, 11),
        component_coverage={
            "raw.osm.water": {"feature_count": 1, "coverage_status": "available"},
            "raw.ms.water": {"feature_count": 1, "coverage_status": "available"},
        },
        quality_policy_id="quality.default.water_polygon.v1",
    )

    assert report.accepted is False
    assert "self_intersection_count" in report.failure_reasons
    assert "sliver_polygon_count" in report.failure_reasons


def test_quality_gate_rejects_waterways_zero_length_geometry(tmp_path: Path) -> None:
    path = tmp_path / "bad_waterways.gpkg"
    frame = gpd.GeoDataFrame(
        {"source_id": ["raw.osm.waterways", "raw.ms.waterways"]},
        geometry=[
            LineString([(0, 0), (1, 0)]),
            LineString([(1, 0), (1, 0)]),
        ],
        crs="EPSG:4326",
    )
    frame.to_file(path, driver="GPKG")

    report = QualityGateService().evaluate(
        artifact_path=path,
        task_kind=TaskKind.waterways,
        required_fields=["geometry", "source_id"],
        requested_bbox=(-1, -1, 2, 1),
        component_coverage={
            "raw.osm.waterways": {"feature_count": 1, "coverage_status": "available"},
            "raw.ms.waterways": {"feature_count": 1, "coverage_status": "available"},
        },
        quality_policy_id="quality.default.waterways.v1",
    )

    assert report.accepted is False
    assert "zero_length_geometry_count" in report.failure_reasons


def test_quality_gate_rejects_waterways_dangle_endpoint_rate_above_threshold(tmp_path: Path) -> None:
    path = tmp_path / "dangling_waterways.gpkg"
    frame = gpd.GeoDataFrame(
        {"source_id": ["raw.osm.waterways", "raw.ms.waterways", "raw.local.waterways"]},
        geometry=[
            LineString([(500000, 0), (500001, 0)]),
            LineString([(500002, 0), (500003, 0)]),
            LineString([(500004, 0), (500005, 0)]),
        ],
        crs="EPSG:32631",
    )
    frame.to_file(path, driver="GPKG")

    report = QualityGateService().evaluate(
        artifact_path=path,
        task_kind=TaskKind.waterways,
        required_fields=["geometry", "source_id"],
        requested_bbox=(2.9, -0.1, 3.1, 0.1),
        component_coverage={
            "raw.osm.waterways": {"feature_count": 1, "coverage_status": "available"},
            "raw.ms.waterways": {"feature_count": 1, "coverage_status": "available"},
            "raw.local.waterways": {"feature_count": 1, "coverage_status": "available"},
        },
        quality_policy_id="quality.default.waterways.v1",
    )

    assert report.accepted is False
    assert report.metrics["zero_length_geometry_count"] == 0
    assert report.metrics["dangle_endpoint_count"] == 6
    assert report.metrics["dangle_endpoint_rate_per_100km"] > 500.0
    assert "zero_length_geometry_count" not in report.failure_reasons
    assert "dangle_endpoint_rate_per_100km" in report.failure_reasons
    assert "dangle_endpoint_count" not in report.failure_reasons


def test_quality_gate_preserves_source_id_lineage_requirement_without_contract(tmp_path: Path) -> None:
    path = tmp_path / "building_feature_id_only.gpkg"
    frame = gpd.GeoDataFrame(
        {"source_feature_id": ["building-1"]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
        crs="EPSG:4326",
    )
    frame.to_file(path, driver="GPKG")

    report = QualityGateService().evaluate(
        artifact_path=path,
        task_kind=TaskKind.building,
        required_fields=["geometry", "source_feature_id"],
        requested_bbox=(-1, -1, 2, 2),
        component_coverage={
            "raw.osm.building": {"feature_count": 1, "coverage_status": "available"},
            "raw.microsoft.building": {"feature_count": 1, "coverage_status": "available"},
        },
    )

    assert report.accepted is False
    assert report.checks["source_lineage"]["passed"] is False
    assert "source_lineage" in report.failure_reasons


def test_quality_gate_uses_road_contract_required_fields_when_enabled(tmp_path: Path) -> None:
    path = tmp_path / "road_missing_contract_fields.gpkg"
    frame = gpd.GeoDataFrame(
        {"fusion_source": ["base_road_network"], "match_role": ["base"], "road_class": ["primary"]},
        geometry=[LineString([(0, 0), (1, 0)])],
        crs="EPSG:4326",
    )
    frame.to_file(path, driver="GPKG")

    report = QualityGateService().evaluate(
        artifact_path=path,
        task_kind=TaskKind.road,
        required_fields=["geometry"],
        requested_bbox=(-1, -1, 2, 1),
        component_coverage={"raw.osm.road": {"feature_count": 1, "coverage_status": "available"}},
        contract_id="contract.road.fused.v1",
    )

    assert report.accepted is False
    assert "name" in report.metrics["missing_fields"]
    assert "osm_name" in report.metrics["missing_fields"]
    assert "road_name" in report.metrics["missing_fields"]


def test_quality_gate_rejects_field_null_rate_above_contract_threshold(tmp_path: Path) -> None:
    path = tmp_path / "road_empty_names.gpkg"
    frame = gpd.GeoDataFrame(
        {
            "fusion_source": ["base_road_network"] * 5,
            "match_role": ["base"] * 5,
            "road_class": ["primary"] * 5,
            "source_layer": ["base"] * 5,
            "name": ["", "", "", "", ""],
            "osm_name": ["", "", "", "", ""],
            "road_name": ["", "", "", "", ""],
        },
        geometry=[LineString([(idx, 0), (idx + 1, 0)]) for idx in range(5)],
        crs="EPSG:4326",
    )
    frame.to_file(path, driver="GPKG")

    report = QualityGateService().evaluate(
        artifact_path=path,
        task_kind=TaskKind.road,
        required_fields=["geometry"],
        requested_bbox=(-1, -1, 6, 1),
        component_coverage={
            "raw.osm.road": {"feature_count": 5, "coverage_status": "available"},
            "raw.overture.road": {"feature_count": 5, "coverage_status": "available"},
        },
        contract_id="contract.road.fused.v1",
    )

    assert report.accepted is True
    assert "field_null_rate:name" in report.soft_failure_reasons
    assert report.checks["field_null_rate:name"]["actual"] == 1.0
    assert report.checks["field_null_rate:name"]["operator"] == "lte"
    assert report.checks["field_null_rate:name"]["threshold"] == 0.80


def test_quality_gate_accepts_country_expected_high_road_name_null_rate(tmp_path: Path) -> None:
    path = tmp_path / "nepal_road_names.gpkg"
    frame = gpd.GeoDataFrame(
        {
            "fusion_source": ["base_road_network"] * 5,
            "match_role": ["base"] * 5,
            "road_class": ["primary"] * 5,
            "source_layer": ["base"] * 5,
            "name": ["A", "", "", "", ""],
            "osm_name": ["A", "", "", "", ""],
            "road_name": ["A", "", "", "", ""],
        },
        geometry=[LineString([(idx, 0), (idx + 1, 0)]) for idx in range(5)],
        crs="EPSG:4326",
    )
    frame.to_file(path, driver="GPKG")

    report = QualityGateService().evaluate(
        artifact_path=path,
        task_kind=TaskKind.road,
        required_fields=["geometry"],
        requested_bbox=(-1, -1, 6, 1),
        component_coverage={
            "raw.osm.road": {"feature_count": 5, "coverage_status": "available"},
            "raw.overture.road": {"feature_count": 5, "coverage_status": "available"},
        },
        contract_id="contract.road.fused.v1",
        source_expected_null_rates={"name": 0.95},
    )

    assert "field_null_rate:name" not in report.soft_failure_reasons
    assert report.checks["field_null_rate:name"]["passed"] is True
    assert report.checks["field_null_rate:name"]["threshold"] == 0.95


def test_quality_gate_rejects_mismatched_contract_id(tmp_path: Path) -> None:
    path = tmp_path / "road_contract_mismatch.gpkg"
    frame = gpd.GeoDataFrame(
        {"source_id": ["raw.osm.road"]},
        geometry=[LineString([(0, 0), (1, 0)])],
        crs="EPSG:4326",
    )
    frame.to_file(path, driver="GPKG")

    with pytest.raises(ValueError, match="does not match"):
        QualityGateService().evaluate(
            artifact_path=path,
            task_kind=TaskKind.road,
            required_fields=["geometry", "source_id"],
            requested_bbox=(-1, -1, 2, 1),
            component_coverage={
                "raw.osm.road": {"feature_count": 1, "coverage_status": "available"},
                "raw.overture.road": {"feature_count": 1, "coverage_status": "available"},
            },
            contract_id="contract.poi.fused.v1",
        )
