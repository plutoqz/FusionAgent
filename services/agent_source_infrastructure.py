from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from services.aoi_resolution_service import AOIResolutionService, AdminBoundaryResolver, NominatimGeocoder
from services.artifact_registry import ArtifactRegistry
from services.input_acquisition_service import InputAcquisitionService
from services.local_bundle_catalog import LocalBundleCatalogProvider
from services.raster_height_source_service import RasterHeightSourceService
from services.raw_vector_input_bundle_provider import RawVectorInputBundleProvider
from services.raw_vector_source_service import RawVectorSourceService
from services.runtime_source_contract_service import ExternalConfigProvider, RuntimeSourceContractService


@dataclass(frozen=True)
class SourceProviderContract:
    """Factory contract for AOI and source acquisition dependencies."""

    geocoder_factory: Callable[[], object]
    raw_vector_source_factory: Callable[[], object]
    input_bundle_provider_factory: Callable[[object], Iterable[object]]
    external_config_provider: ExternalConfigProvider

    def build(self, *, registry: ArtifactRegistry, cache_root: Path) -> AgentSourceInfrastructure:
        raw_source_service = self.raw_vector_source_factory()
        providers = list(self.input_bundle_provider_factory(raw_source_service))
        repo_root = Path(getattr(raw_source_service, "root_dir", cache_root))
        input_acquisition_service = InputAcquisitionService(
            registry=registry,
            providers=providers,
            cache_dir=cache_root / "input_bundle_cache",
        )
        return AgentSourceInfrastructure(
            aoi_resolution_service=AOIResolutionService(
                geocoder=self.geocoder_factory(),
                admin_boundary_resolver=AdminBoundaryResolver(
                    repo_root=repo_root,
                    cache_dir=cache_root / "aoi_resolution_cache",
                ),
            ),
            raw_vector_source_service=raw_source_service,
            input_acquisition_service=input_acquisition_service,
            runtime_source_contract_service=RuntimeSourceContractService(
                raw_source_service=raw_source_service,
                input_bundle_providers=input_acquisition_service.providers,
                external_config_provider=self.external_config_provider,
            ),
            provider_contract=self,
        )


@dataclass(frozen=True)
class AgentSourceInfrastructure:
    aoi_resolution_service: AOIResolutionService
    raw_vector_source_service: object
    input_acquisition_service: InputAcquisitionService
    runtime_source_contract_service: RuntimeSourceContractService
    provider_contract: SourceProviderContract | None = None


def default_source_provider_contract(
    *,
    project_root: Path,
    cache_root: Path,
    registry: ArtifactRegistry,
) -> SourceProviderContract:
    return SourceProviderContract(
        geocoder_factory=build_default_geocoder,
        raw_vector_source_factory=lambda: RawVectorSourceService(
            root_dir=project_root,
            registry=registry,
            cache_dir=cache_root / "raw_source_cache",
        ),
        input_bundle_provider_factory=lambda raw_source_service: build_default_input_bundle_providers(
            project_root=project_root,
            cache_root=cache_root,
            raw_source_service=raw_source_service,
        ),
        external_config_provider=source_required_external_config,
    )


def build_default_geocoder() -> NominatimGeocoder:
    return NominatimGeocoder(
        user_agent=os.getenv("GEOFUSION_GEOCODER_USER_AGENT", "GeoFusion/1.0 (+https://openai.com/codex)"),
        max_retries=_as_int(os.getenv("GEOFUSION_GEOCODER_RETRIES"), default=3),
        timeout_seconds=_as_int(os.getenv("GEOFUSION_GEOCODER_TIMEOUT"), default=30),
    )


def build_default_input_bundle_providers(
    *,
    project_root: Path,
    cache_root: Path | None = None,
    raw_source_service: object,
) -> list[object]:
    providers: list[object] = []
    try:
        raster_service = (
            RasterHeightSourceService(
                repo_root=project_root,
                cache_dir=Path(cache_root) / "height_raster_cache",
            )
            if cache_root is not None
            else None
        )
        providers.append(
            LocalBundleCatalogProvider(
                project_root,
                raw_source_service=raw_source_service,
                raster_height_source_service=raster_service,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("geofusion.run").warning(
            "Failed to initialize local bundle catalog provider: %s",
            exc,
        )
    providers.append(RawVectorInputBundleProvider(raw_source_service=raw_source_service))
    return providers


def source_required_external_config(source_id: str) -> list[str]:
    if source_id == "raw.google.poi":
        return ["GOOGLE_PLACES_API_KEY", "google_poi_authorization_manifest"]
    if source_id in {"raw.google.building", "raw.google.open_buildings.vector"}:
        return ["google_open_buildings_urls"]
    return []


def _as_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value.strip())
    except Exception:  # noqa: BLE001
        return default
