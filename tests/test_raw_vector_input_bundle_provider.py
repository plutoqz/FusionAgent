from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Point

from schemas.data_requirement import (
    BundleSlot,
    CompletenessPolicy,
    DataRequirementPlan,
    SourceCandidate,
    SourceRoleRequirement,
)
from schemas.task_kind import TaskKind
from services.agent_run_service import AgentRunService
from services.raw_vector_source_service import MaterializedRawVectorSource
from utils.shp_zip import validate_zip_has_shapefile, zip_shapefile_bundle


class _FakeRawVectorSourceService:
    def __init__(self, *, raw_zip: Path | None = None) -> None:
        self.raw_zip = raw_zip
        self.current_version_calls: list[tuple[str, object, object]] = []
        self.resolve_calls: list[dict[str, object]] = []

    def can_handle(self, source_id: str) -> bool:
        return source_id == "raw.example.vector"

    def current_version(self, source_id: str, *, request_bbox=None, resolved_aoi=None) -> str:
        self.current_version_calls.append((source_id, request_bbox, resolved_aoi))
        return "raw-version-1"

    def resolve(self, *, source_id: str, request_bbox, target_path: Path, target_crs: str, resolved_aoi=None):
        self.resolve_calls.append(
            {
                "source_id": source_id,
                "request_bbox": request_bbox,
                "target_path": target_path,
                "target_crs": target_crs,
                "resolved_aoi": resolved_aoi,
            }
        )
        assert self.raw_zip is not None
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(self.raw_zip.read_bytes())
        return MaterializedRawVectorSource(
            zip_path=target_path,
            bbox=(0.0, 0.0, 6.0, 6.0),
            target_crs=target_crs,
            source_id=source_id,
            source_mode="local_data",
            cache_hit=False,
            version_token="raw-version-1",
            feature_count=7,
            coverage_status="available",
        )


def _write_raw_zip(tmp_path: Path) -> Path:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    frame = gpd.GeoDataFrame(
        {"value": list(range(7))},
        geometry=[Point(float(index), float(index)) for index in range(7)],
        crs="EPSG:4326",
    )
    shp_path = source_dir / "raw.shp"
    frame.to_file(shp_path)
    return zip_shapefile_bundle(shp_path, tmp_path / "raw.zip")


def _requirements(*, reference_required: bool) -> DataRequirementPlan:
    return DataRequirementPlan(
        task_kind=TaskKind.poi,
        task_family="poi",
        roles=[
            SourceRoleRequirement(
                role_id="base_poi",
                required=True,
                bundle_slot=BundleSlot.primary,
                geometry_types=["Point", "MultiPoint"],
                completeness_policy=CompletenessPolicy.required_non_empty,
                candidates=[
                    SourceCandidate(
                        source_id="raw.example.vector",
                        provider_family="fixture",
                        priority=10,
                    )
                ],
            ),
            SourceRoleRequirement(
                role_id="reference_poi",
                required=reference_required,
                bundle_slot=BundleSlot.reference,
                distinct_from_role_ids=["base_poi"],
                geometry_types=["Point", "MultiPoint"],
                completeness_policy=CompletenessPolicy.optional_reference,
                candidates=[
                    SourceCandidate(
                        source_id="raw.other.vector",
                        provider_family="fixture",
                        priority=10,
                    )
                ],
            ),
        ],
    )


def test_provider_only_handles_raw_sources_supported_by_raw_service() -> None:
    from services.raw_vector_input_bundle_provider import RawVectorInputBundleProvider

    provider = RawVectorInputBundleProvider(raw_source_service=_FakeRawVectorSourceService())

    assert provider.can_handle("raw.example.vector") is True
    assert provider.can_handle("catalog.example.bundle") is False
    assert provider.can_handle("raw.unknown.vector") is False


def test_current_version_delegates_to_raw_source_service() -> None:
    from services.raw_vector_input_bundle_provider import RawVectorInputBundleProvider

    raw_service = _FakeRawVectorSourceService()
    provider = RawVectorInputBundleProvider(raw_source_service=raw_service)
    request_bbox = (1.0, 2.0, 3.0, 4.0)

    assert provider.current_version("raw.example.vector", request_bbox=request_bbox) == "raw-version-1"
    assert raw_service.current_version_calls == [("raw.example.vector", request_bbox, None)]


def test_materialize_returns_bundle_with_raw_zip_empty_ref_coverage_and_attempt(tmp_path: Path) -> None:
    from services.raw_vector_input_bundle_provider import RawVectorInputBundleProvider

    raw_zip = _write_raw_zip(tmp_path)
    raw_service = _FakeRawVectorSourceService(raw_zip=raw_zip)
    provider = RawVectorInputBundleProvider(raw_source_service=raw_service)

    bundle = provider.materialize(
        source_id="raw.example.vector",
        request_bbox=(0.0, 0.0, 10.0, 10.0),
        target_dir=tmp_path / "inputs",
        target_crs="epsg:4326",
    )

    assert bundle.source_id == "raw.example.vector"
    assert raw_service.resolve_calls[0]["target_crs"] == "EPSG:4326"
    assert bundle.osm_zip_path.exists()
    assert bundle.ref_zip_path.exists()
    validate_zip_has_shapefile(bundle.osm_zip_path, tmp_path / "osm_extract")
    ref_shp = validate_zip_has_shapefile(bundle.ref_zip_path, tmp_path / "ref_extract")
    assert len(gpd.read_file(ref_shp)) == 0

    coverage = bundle.component_coverage["raw.example.vector"]
    assert coverage.feature_count == 7
    assert coverage.coverage_status == "available"
    assert coverage.path == bundle.osm_zip_path
    assert coverage.source_mode == "local_data"

    assert bundle.provider_attempts[0]["source_id"] == "raw.example.vector"
    assert bundle.provider_attempts[0]["status"] == "available"
    assert bundle.provider_attempts[0]["coverage_status"] == "available"
    assert bundle.provider_attempts[0]["feature_count"] == 7
    assert bundle.provider_attempts[0]["selected_for_fusion"] is True


def test_direct_raw_provider_records_kg_role_contract(tmp_path: Path) -> None:
    from services.raw_vector_input_bundle_provider import RawVectorInputBundleProvider

    provider = RawVectorInputBundleProvider(
        raw_source_service=_FakeRawVectorSourceService(raw_zip=_write_raw_zip(tmp_path))
    )
    bundle = provider.materialize(
        source_id="raw.example.vector",
        request_bbox=None,
        target_dir=tmp_path / "inputs-with-plan",
        target_crs="EPSG:4326",
        data_requirements=_requirements(reference_required=False),
    )

    coverage = bundle.component_coverage["raw.example.vector"]
    assert coverage["role_id"] == "base_poi"
    assert coverage["selected_role_ids"] == ["base_poi"]
    assert bundle.provider_attempts[0]["role_contract"]["bundle_slot"] == "primary"


def test_direct_raw_provider_rejects_unsatisfied_required_kg_role() -> None:
    from services.raw_vector_input_bundle_provider import RawVectorInputBundleProvider

    provider = RawVectorInputBundleProvider(raw_source_service=_FakeRawVectorSourceService())

    with pytest.raises(ValueError, match="reference_poi"):
        provider.current_version(
            "raw.example.vector",
            data_requirements=_requirements(reference_required=True),
        )


def test_agent_run_service_registers_raw_vector_input_bundle_provider(tmp_path: Path) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs", max_workers=1)
    try:
        providers = service._build_input_bundle_providers()
    finally:
        service.shutdown()

    names = [provider.__class__.__name__ for provider in providers]
    assert "RawVectorInputBundleProvider" in names
    if "LocalBundleCatalogProvider" in names:
        assert names.index("LocalBundleCatalogProvider") < names.index("RawVectorInputBundleProvider")
