from __future__ import annotations

from pathlib import Path

import geopandas as gpd
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


def test_quality_gate_rejects_waterways_dangle_endpoint_count_above_threshold(tmp_path: Path) -> None:
    path = tmp_path / "dangling_waterways.gpkg"
    frame = gpd.GeoDataFrame(
        {"source_id": ["raw.osm.waterways", "raw.ms.waterways", "raw.local.waterways"]},
        geometry=[
            LineString([(0, 0), (1, 0)]),
            LineString([(2, 0), (3, 0)]),
            LineString([(4, 0), (5, 0)]),
        ],
        crs="EPSG:4326",
    )
    frame.to_file(path, driver="GPKG")

    report = QualityGateService().evaluate(
        artifact_path=path,
        task_kind=TaskKind.waterways,
        required_fields=["geometry", "source_id"],
        requested_bbox=(-1, -1, 6, 1),
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
    assert "zero_length_geometry_count" not in report.failure_reasons
    assert "dangle_endpoint_count" in report.failure_reasons
