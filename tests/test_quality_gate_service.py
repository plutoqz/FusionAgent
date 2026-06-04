from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point, Polygon

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
