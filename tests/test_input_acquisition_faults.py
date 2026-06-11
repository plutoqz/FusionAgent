from __future__ import annotations
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from schemas.agent import RunCreateRequest, RunInputStrategy, RunTrigger, RunTriggerType
from schemas.fusion import JobType
from services.artifact_registry import ArtifactRegistry
from services.input_acquisition_service import InputAcquisitionService
from services.source_asset_service import classify_source_fault


class _FaultingBundleProvider:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def can_handle(self, source_id: str) -> bool:
        return source_id == "catalog.flood.water"

    def current_version(self, source_id: str) -> str:
        assert source_id == "catalog.flood.water"
        return "fault-v1"

    def materialize(self, *, source_id: str, request_bbox, target_dir: Path, target_crs: str):
        assert source_id == "catalog.flood.water"
        raise self.exc


def _build_request() -> RunCreateRequest:
    return RunCreateRequest(
        job_type=JobType.water,
        trigger=RunTrigger(
            type=RunTriggerType.user_query,
            content="need water polygons",
            spatial_extent="bbox(10,10,11,11)",
        ),
        target_crs="EPSG:32643",
        field_mapping={},
        debug=False,
        input_strategy=RunInputStrategy.task_driven_auto,
    )


def test_missing_or_wrong_crs_source_produces_explicit_fault() -> None:
    assert classify_source_fault(
        source={"source_id": "catalog.building.benin.osm", "crs": "EPSG:4326"},
        expected_crs="EPSG:32631",
    ) == "CRS_MISMATCH"
    assert classify_source_fault(source={"source_id": "catalog.building.benin.osm", "path": None}) == "SOURCE_MISSING"


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (FileNotFoundError("No local or remote source asset path available for raw.osm.water"), "SOURCE_MISSING"),
        (RuntimeError("corrupted shapefile header"), "SOURCE_CORRUPTED"),
        (ValueError("CRS mismatch between EPSG:4326 and EPSG:32631"), "CRS_MISMATCH"),
    ],
)
def test_input_acquisition_wraps_faults_with_machine_readable_category(exc: Exception, expected: str, tmp_path: Path) -> None:
    service = InputAcquisitionService(
        registry=ArtifactRegistry(index_path=tmp_path / "artifact_registry.json"),
        providers=[_FaultingBundleProvider(exc)],
        cache_dir=tmp_path / "cache",
    )

    with pytest.raises(ValueError, match=expected):
        service.resolve_task_driven_inputs(
            request=_build_request(),
            source_id="catalog.flood.water",
            required_output_type="dt.water.bundle",
            input_dir=tmp_path / "run",
        )


def test_source_attempt_statuses_include_contract_states() -> None:
    from services.source_acquisition_policy import SOURCE_ATTEMPT_STATUSES

    assert {
        "attempted",
        "available",
        "empty",
        "no_coverage",
        "network_failed",
        "provider_failed",
        "unauthorized",
        "cache_reused",
        "materialized",
        "internal_failed",
    } <= SOURCE_ATTEMPT_STATUSES


@pytest.mark.parametrize(
    ("fault_class", "expected_status"),
    [
        ("SOURCE_DOWNLOAD_FAILED", "network_failed"),
        ("NO_OFFICIAL_COVERAGE", "no_coverage"),
        ("UNAUTHORIZED", "unauthorized"),
        ("PROVIDER_UNAVAILABLE", "provider_failed"),
    ],
)
def test_build_source_attempt_normalizes_external_fault_statuses(fault_class: str, expected_status: str) -> None:
    from services.source_acquisition_policy import build_source_attempt

    attempt = build_source_attempt(
        source_id="raw.google.building",
        status="attempted",
        fault_class=fault_class,
        fault_message="outside operator control",
        coverage_status="missing",
        feature_count=0,
    )

    assert attempt["source_id"] == "raw.google.building"
    assert attempt["status"] == expected_status
    assert attempt["fault_class"] == fault_class
    assert attempt["coverage_status"] == "missing"
    assert attempt["feature_count"] == 0
    assert attempt["external_uncontrollable"] is True


def test_build_source_attempt_preserves_contract_status() -> None:
    from services.source_acquisition_policy import build_source_attempt

    attempt = build_source_attempt(
        source_id="raw.google.building",
        status="no_coverage",
        fault_class="NO_OFFICIAL_COVERAGE",
    )

    assert attempt["status"] == "no_coverage"
    assert attempt["external_uncontrollable"] is True


def test_build_source_attempt_normalizes_other_faults_to_provider_failed() -> None:
    from services.source_acquisition_policy import build_source_attempt

    attempt = build_source_attempt(
        source_id="raw.osm.water",
        status="failed",
        fault_class="SOURCE_MISSING",
    )

    assert attempt["status"] == "provider_failed"
    assert attempt["external_uncontrollable"] is False

