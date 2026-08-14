from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, Polygon

from schemas.quality_gate import QualityGateReport
from schemas.task_kind import TaskKind
from services.artifact_repair_service import ArtifactRepairService
from services.artifact_evaluation_service import evaluate_vector_artifact
from services.quality_gate_service import QualityGateService


ROAD_ARTIFACT_REPAIRS = [
    "repair.artifact.schema_backfill.v1",
    "repair.artifact.road_name.v1",
    "repair.artifact.line_topology.v1",
    "repair.artifact.geometry_validity.v1",
]
BUILDING_ARTIFACT_REPAIRS = [
    "repair.artifact.schema_backfill.v1",
    "repair.artifact.geometry_validity.v1",
]


def test_artifact_repair_backfills_road_contract_fields_and_drops_zero_length_lines(tmp_path: Path) -> None:
    artifact_path = tmp_path / "road_bad.gpkg"
    gpd.GeoDataFrame(
        {
            "source_layer": ["base", "supplement"],
            "name": ["Main Road", ""],
            "ref": ["MR-1", "Side Road"],
        },
        geometry=[
            LineString([(0, 0), (1000, 0)]),
            LineString([(10, 10), (10, 10)]),
        ],
        crs="EPSG:32631",
    ).to_file(artifact_path, driver="GPKG")
    required_fields = [
        "geometry",
        "fusion_source",
        "match_role",
        "road_class",
        "source_layer",
        "name",
        "osm_name",
        "road_name",
    ]
    report = QualityGateService().evaluate(
        artifact_path=artifact_path,
        task_kind=TaskKind.road,
        required_fields=["geometry"],
        component_coverage={
            "raw.osm.road": {"feature_count": 1, "coverage_status": "available"},
            "raw.microsoft.road": {"feature_count": 1, "coverage_status": "available"},
        },
        contract_id="contract.road.fused.v1",
    )

    result = ArtifactRepairService().repair(
        artifact_path=artifact_path,
        task_kind=TaskKind.road,
        quality_report=report,
        required_fields=required_fields,
        output_dir=tmp_path,
        repair_records=[],
        source_artifact_paths={"raw.osm.road": artifact_path},
        authorized_strategy_ids=ROAD_ARTIFACT_REPAIRS,
        available_strategy_ids=ROAD_ARTIFACT_REPAIRS,
    )

    metrics = evaluate_vector_artifact(result.output_path, required_fields=required_fields)
    repaired = gpd.read_file(result.output_path)
    assert result.changed is True
    assert {
        "repair.artifact.schema_backfill.v1",
        "repair.artifact.road_name.v1",
        "repair.artifact.line_topology.v1",
    } <= set(result.applied_strategies)
    assert metrics["missing_fields"] == []
    assert metrics["zero_length_geometry_count"] == 0
    assert len(repaired) == 1
    assert repaired.iloc[0]["road_name"] == "Main Road"
    assert repaired.iloc[0]["osm_name"] == "Main Road"
    assert result.repair_records[-1].reason_code == "quality_line_topology_failed"


def test_artifact_repair_returns_unchanged_when_no_strategy_applies(tmp_path: Path) -> None:
    artifact_path = tmp_path / "road_good.gpkg"
    gpd.GeoDataFrame(
        {
            "fusion_source": ["base_road_network"],
            "match_role": ["base"],
            "road_class": ["primary"],
            "source_layer": ["base"],
            "name": ["Main Road"],
            "osm_name": ["Main Road"],
            "road_name": ["Main Road"],
        },
        geometry=[LineString([(0, 0), (1000, 0)])],
        crs="EPSG:32631",
    ).to_file(artifact_path, driver="GPKG")
    report = QualityGateReport(
        accepted=False,
        task_kind=TaskKind.road,
        artifact_path=str(artifact_path),
        metrics=evaluate_vector_artifact(artifact_path, required_fields=["geometry"]),
        failure_reasons=["source_contribution_balance"],
    )

    result = ArtifactRepairService().repair(
        artifact_path=artifact_path,
        task_kind=TaskKind.road,
        quality_report=report,
        required_fields=["geometry"],
        output_dir=tmp_path,
        repair_records=[],
        authorized_strategy_ids=ROAD_ARTIFACT_REPAIRS,
        available_strategy_ids=ROAD_ARTIFACT_REPAIRS,
    )

    assert result.changed is False
    assert result.output_path == artifact_path
    assert result.repair_records == []


def test_artifact_repair_does_not_apply_road_name_strategy_for_topology_failure(tmp_path: Path) -> None:
    artifact_path = tmp_path / "road_dangle.gpkg"
    gpd.GeoDataFrame(
        {
            "fusion_source": ["base_road_network"],
            "match_role": ["base"],
            "road_class": ["road"],
            "source_layer": ["base"],
            "name": [""],
            "osm_name": [""],
            "road_name": [""],
        },
        geometry=[LineString([(0, 0), (1000, 0)])],
        crs="EPSG:32631",
    ).to_file(artifact_path, driver="GPKG")
    report = QualityGateReport(
        accepted=False,
        task_kind=TaskKind.road,
        artifact_path=str(artifact_path),
        metrics=evaluate_vector_artifact(artifact_path, required_fields=["geometry"]),
        failure_reasons=["dangle_endpoint_rate_per_100km"],
    )

    result = ArtifactRepairService().repair(
        artifact_path=artifact_path,
        task_kind=TaskKind.road,
        quality_report=report,
        required_fields=["geometry"],
        output_dir=tmp_path,
        repair_records=[],
        authorized_strategy_ids=ROAD_ARTIFACT_REPAIRS,
        available_strategy_ids=ROAD_ARTIFACT_REPAIRS,
    )

    road_name_report = next(
        item for item in result.report["strategy_reports"]
        if item["strategy_id"] == "repair.artifact.road_name.v1"
    )
    assert result.changed is False
    assert road_name_report["skipped"] == "failure_reason_not_applicable"


def test_artifact_repair_fixes_invalid_building_geometry(tmp_path: Path) -> None:
    artifact_path = tmp_path / "building_invalid.gpkg"
    invalid_bowtie = Polygon([(0, 0), (10, 10), (10, 0), (0, 10), (0, 0)])
    gpd.GeoDataFrame(
        {"source_id": ["raw.osm.building"], "source_feature_id": ["b-1"]},
        geometry=[invalid_bowtie],
        crs="EPSG:32631",
    ).to_file(artifact_path, driver="GPKG")
    report = QualityGateReport(
        accepted=False,
        task_kind=TaskKind.building,
        artifact_path=str(artifact_path),
        metrics=evaluate_vector_artifact(artifact_path, required_fields=["geometry"]),
        failure_reasons=["invalid_geometry"],
    )

    result = ArtifactRepairService().repair(
        artifact_path=artifact_path,
        task_kind=TaskKind.building,
        quality_report=report,
        required_fields=["geometry", "source_id", "source_feature_id"],
        output_dir=tmp_path,
        repair_records=[],
        authorized_strategy_ids=BUILDING_ARTIFACT_REPAIRS,
        available_strategy_ids=BUILDING_ARTIFACT_REPAIRS,
    )

    repaired = gpd.read_file(result.output_path)
    assert result.changed is True
    assert "repair.artifact.geometry_validity.v1" in result.applied_strategies
    assert result.repair_records[-1].reason_code == "quality_invalid_geometry"
    assert repaired.geometry.is_valid.all()
    assert not repaired.empty


def test_artifact_repair_fails_closed_without_contract_authorization(tmp_path: Path) -> None:
    artifact_path = tmp_path / "building_unauthorized.gpkg"
    invalid_bowtie = Polygon([(0, 0), (10, 10), (10, 0), (0, 10), (0, 0)])
    gpd.GeoDataFrame(
        {"source_id": ["raw.osm.building"]},
        geometry=[invalid_bowtie],
        crs="EPSG:32631",
    ).to_file(artifact_path, driver="GPKG")
    report = QualityGateReport(
        accepted=False,
        task_kind=TaskKind.building,
        artifact_path=str(artifact_path),
        metrics=evaluate_vector_artifact(artifact_path, required_fields=["geometry"]),
        failure_reasons=["invalid_geometry"],
    )

    result = ArtifactRepairService().repair(
        artifact_path=artifact_path,
        task_kind=TaskKind.building,
        quality_report=report,
        required_fields=["geometry"],
        output_dir=tmp_path,
        repair_records=[],
        authorized_strategy_ids=[],
        available_strategy_ids=BUILDING_ARTIFACT_REPAIRS,
    )

    assert result.changed is False
    assert result.applied_strategies == []
    assert result.report["authorized_strategy_ids"] == []
