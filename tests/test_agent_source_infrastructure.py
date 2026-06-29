from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Optional

import geopandas as gpd
import pytest
from shapely.geometry import box

from kg.inmemory_repository import InMemoryKGRepository
from schemas.agent import RunCreateRequest, RunInputStrategy, RunTrigger, RunTriggerType
from schemas.fusion import JobType
from schemas.runtime_source_contract import RuntimeProviderStatus
from services.agent_run_service import AgentRunService
from services.agent_source_infrastructure import SourceProviderContract
from services.aoi_resolution_service import ResolvedAOI
from services.input_acquisition_service import BBox, MaterializedInputBundle
from services.source_asset_service import SourceCoverageStatus
from utils.shp_zip import validate_zip_has_shapefile, zip_shapefile_bundle


class DeterministicGeocoder:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, query: str) -> Iterable[dict[str, Any]]:
        self.queries.append(query)
        return [
            {
                "display_name": "Fixture City, Testland",
                "boundingbox": ["1.0", "2.0", "10.0", "20.0"],
                "address": {"city": "Fixture City", "country": "Testland", "country_code": "tl"},
                "importance": 0.99,
                "source": "fixture",
            }
        ]


class FixtureRawSourceService:
    def __init__(self, supported: set[str]) -> None:
        self.supported = supported

    def can_handle(self, source_id: str) -> bool:
        return source_id in self.supported


class FixtureInputBundleProvider:
    def __init__(self, supported: set[str]) -> None:
        self.supported = supported
        self.materialize_calls: list[dict[str, object]] = []

    def can_handle(self, source_id: str) -> bool:
        return source_id in self.supported

    def current_version(
        self,
        source_id: str,
        *,
        request_bbox: Optional[BBox] = None,
        resolved_aoi: ResolvedAOI | None = None,
    ) -> str:
        bbox_token = ",".join(str(value) for value in request_bbox or ())
        aoi_token = resolved_aoi.country_code if resolved_aoi is not None else "no-aoi"
        return f"fixture:{source_id}:{bbox_token}:{aoi_token}"

    def materialize(
        self,
        *,
        source_id: str,
        request_bbox: Optional[BBox],
        resolved_aoi: ResolvedAOI | None = None,
        target_dir: Path,
        target_crs: str,
    ) -> MaterializedInputBundle:
        self.materialize_calls.append(
            {
                "source_id": source_id,
                "request_bbox": request_bbox,
                "resolved_aoi": resolved_aoi,
                "target_crs": target_crs,
            }
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        bbox_values = request_bbox or (0.0, 0.0, 1.0, 1.0)
        geometry = box(*bbox_values)
        osm_zip = _write_fixture_bundle(target_dir / "osm_src" / "osm.shp", target_dir / "osm.zip", geometry)
        ref_zip = _write_fixture_bundle(target_dir / "ref_src" / "ref.shp", target_dir / "ref.zip", geometry)
        coverage = {
            source_id: SourceCoverageStatus(
                source_id=source_id,
                source_mode="fixture",
                feature_count=1,
                coverage_status="available",
                path=osm_zip,
            )
        }
        return MaterializedInputBundle(
            osm_zip_path=osm_zip,
            ref_zip_path=ref_zip,
            bbox=tuple(float(value) for value in bbox_values),
            target_crs=target_crs,
            source_id=source_id,
            attempted_sources=[source_id],
            component_coverage=coverage,
            provider_attempts=[
                {
                    "source_id": source_id,
                    "status": "available",
                    "coverage_status": "available",
                    "feature_count": 1,
                    "selected_for_fusion": True,
                }
            ],
        )


def _write_fixture_bundle(shp_path: Path, zip_path: Path, geometry) -> Path:
    shp_path.parent.mkdir(parents=True, exist_ok=True)
    frame = gpd.GeoDataFrame({"fixture_id": [1]}, geometry=[geometry], crs="EPSG:4326")
    frame.to_file(shp_path)
    return zip_shapefile_bundle(shp_path, zip_path)


def _fixture_source_provider_contract(
    *,
    geocoder: DeterministicGeocoder | None = None,
    provider: FixtureInputBundleProvider | None = None,
    raw_service: FixtureRawSourceService | None = None,
) -> SourceProviderContract:
    geocoder = geocoder or DeterministicGeocoder()
    provider = provider or FixtureInputBundleProvider({"catalog.fixture.building"})
    raw_service = raw_service or FixtureRawSourceService({"raw.fixture.building"})
    return SourceProviderContract(
        geocoder_factory=lambda: geocoder,
        raw_vector_source_factory=lambda: raw_service,
        input_bundle_provider_factory=lambda _raw_source_service: [provider],
        external_config_provider=lambda source_id: ["FIXTURE_TOKEN"] if source_id == "raw.fixture.remote" else [],
    )


def test_agent_run_service_accepts_deterministic_source_provider_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEOFUSION_LLM_PROVIDER", "mock")
    geocoder = DeterministicGeocoder()
    provider = FixtureInputBundleProvider({"catalog.fixture.building"})

    def fail_default_source_build(*_args, **_kwargs):
        raise AssertionError("default remote/local source builder should not run for injected contract")

    monkeypatch.setattr(AgentRunService, "_build_geocoder", fail_default_source_build)
    monkeypatch.setattr(AgentRunService, "_build_raw_vector_source_service", fail_default_source_build)
    monkeypatch.setattr(AgentRunService, "_build_input_bundle_providers", fail_default_source_build)

    service = AgentRunService(
        base_dir=tmp_path / "runs",
        kg_repo=InMemoryKGRepository(),
        max_workers=1,
        source_provider_contract=_fixture_source_provider_contract(geocoder=geocoder, provider=provider),
    )
    try:
        assert service.aoi_resolution_service.resolve("Fixture City").display_name == "Fixture City, Testland"
        assert geocoder.queries == ["Fixture City"]

        contract = service.runtime_source_contract_service.check_source("catalog.fixture.building")
        assert contract.status == RuntimeProviderStatus.runtime_ready
        assert contract.provider_names == ["FixtureInputBundleProvider"]
    finally:
        service.shutdown()


def test_fixture_provider_contract_materializes_stable_bundle_without_remote_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEOFUSION_LLM_PROVIDER", "mock")
    geocoder = DeterministicGeocoder()
    provider = FixtureInputBundleProvider({"catalog.fixture.building"})
    service = AgentRunService(
        base_dir=tmp_path / "runs",
        kg_repo=InMemoryKGRepository(),
        max_workers=1,
        source_provider_contract=_fixture_source_provider_contract(geocoder=geocoder, provider=provider),
    )
    try:
        request = RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(type=RunTriggerType.user_query, content="buildings in Fixture City"),
            target_crs="EPSG:4326",
            field_mapping={},
            debug=False,
            input_strategy=RunInputStrategy.task_driven_auto,
        )
        resolved_aoi = service.aoi_resolution_service.resolve("Fixture City")
        resolved = service.input_acquisition_service.resolve_task_driven_inputs(
            request=request,
            source_id="catalog.fixture.building",
            required_output_type="dt.building.bundle",
            input_dir=tmp_path / "input",
            request_bbox=None,
            resolved_aoi=resolved_aoi,
        )

        assert resolved.source_mode == "downloaded"
        assert resolved.source_id == "catalog.fixture.building"
        assert resolved.cache_hit is False
        assert resolved.component_coverage["catalog.fixture.building"]["coverage_status"] == "available"
        assert resolved.manifest_path is not None
        assert resolved.manifest_path.exists()
        assert validate_zip_has_shapefile(resolved.osm_zip_path, tmp_path / "osm_extract").exists()
        assert validate_zip_has_shapefile(resolved.ref_zip_path, tmp_path / "ref_extract").exists()
        assert provider.materialize_calls[0]["request_bbox"] == resolved_aoi.bbox
    finally:
        service.shutdown()


def test_fixture_provider_contract_makes_readiness_statuses_deterministic(tmp_path: Path) -> None:
    service = AgentRunService(
        base_dir=tmp_path / "runs",
        kg_repo=InMemoryKGRepository(),
        max_workers=1,
        source_provider_contract=_fixture_source_provider_contract(),
    )
    try:
        contracts = service.runtime_source_contract_service.check_sources(
            [
                "catalog.fixture.building",
                "raw.fixture.building",
                "raw.fixture.remote",
                "raw.fixture.unknown",
            ]
        )
        by_id = {contract.source_id: contract for contract in contracts}

        assert by_id["catalog.fixture.building"].status == RuntimeProviderStatus.runtime_ready
        assert by_id["raw.fixture.building"].status == RuntimeProviderStatus.reservation_only
        assert by_id["raw.fixture.remote"].status == RuntimeProviderStatus.requires_external_config
        assert by_id["raw.fixture.remote"].required_external_config == ["FIXTURE_TOKEN"]
        assert by_id["raw.fixture.unknown"].status == RuntimeProviderStatus.missing_provider
    finally:
        service.shutdown()
