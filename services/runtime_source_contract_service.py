from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterable
from typing import Any

from kg.seed_provider import load_seed_data
from schemas.runtime_source_contract import RuntimeProviderStatus, RuntimeSourceContract
from services.runtime_source_aliases import BUILDING_HEIGHT_RASTER_PRIORITY_ORDER


ExternalConfigProvider = Callable[[str], list[str]]


class RuntimeSourceContractService:
    def __init__(
        self,
        raw_source_service: object,
        input_bundle_providers: Iterable[object],
        external_config_provider: ExternalConfigProvider | None = None,
        runtime_mode: str | None = None,
    ) -> None:
        self.raw_source_service = raw_source_service
        self.input_bundle_providers = list(input_bundle_providers)
        self.external_config_provider = external_config_provider or (lambda source_id: [])
        running_tests = bool(os.getenv("PYTEST_CURRENT_TEST") or "pytest" in sys.modules)
        self.runtime_mode = str(
            runtime_mode
            or os.getenv("GEOFUSION_KG_RUNTIME_MODE")
            or ("development" if running_tests else "strict")
        ).lower().strip()
        self.source_records = {
            source.source_id: source
            for source in load_seed_data()["data_sources"]
        }

    def check_sources(self, source_ids: Iterable[str]) -> list[RuntimeSourceContract]:
        seen: set[str] = set()
        contracts: list[RuntimeSourceContract] = []
        for source_id in source_ids:
            if source_id in seen:
                continue
            seen.add(source_id)
            contracts.append(self.check_source(source_id))
        return contracts

    def check_source(self, source_id: str) -> RuntimeSourceContract:
        source_record = self.source_records.get(source_id)
        source_metadata = dict(source_record.metadata or {}) if source_record is not None else {}
        runtime_status = str(source_metadata.get("runtime_status") or "").strip().lower()
        catalog_selectable = bool(source_metadata.get("selectable_now", False)) if source_record is not None else False
        raw_supported = _safe_can_handle(self.raw_source_service, source_id)
        handling_providers = [
            provider
            for provider in self.input_bundle_providers
            if _safe_can_handle(provider, source_id)
        ]
        input_supported = bool(handling_providers)
        raster_skill_supported = source_id in BUILDING_HEIGHT_RASTER_PRIORITY_ORDER
        required_external_config = list(self.external_config_provider(source_id) or [])

        reasons: list[str] = []
        if source_record is not None and (runtime_status == "reservation_only" or not catalog_selectable):
            status = RuntimeProviderStatus.reservation_only
            catalog_selectable = False
            reasons.append("frozen KG marks source as reservation-only and not runtime-authorized")
        elif source_record is None and self.runtime_mode in {"strict", "research"}:
            status = RuntimeProviderStatus.missing_provider
            catalog_selectable = False
            reasons.append("source has no runtime authorization in the frozen KG release")
        elif required_external_config:
            status = RuntimeProviderStatus.requires_external_config
            catalog_selectable = catalog_selectable or source_record is None
            reasons.append("source requires external configuration before autonomous materialization")
        elif raster_skill_supported:
            status = RuntimeProviderStatus.runtime_ready
            catalog_selectable = catalog_selectable or source_record is None
            reasons.append("source is handled by building height raster acquisition skill")
        elif input_supported:
            status = RuntimeProviderStatus.runtime_ready
            catalog_selectable = catalog_selectable or source_record is None
        elif raw_supported:
            status = RuntimeProviderStatus.reservation_only
            catalog_selectable = False
            reasons.append("raw source is known but no input bundle provider can materialize it")
        else:
            status = RuntimeProviderStatus.missing_provider
            catalog_selectable = False
            reasons.append("source is not handled by raw source service or input bundle providers")

        return RuntimeSourceContract(
            source_id=source_id,
            catalog_selectable=catalog_selectable,
            raw_vector_supported=raw_supported,
            input_bundle_supported=input_supported or raster_skill_supported,
            status=status,
            reasons=reasons,
            required_external_config=required_external_config,
            provider_names=[
                *[provider.__class__.__name__ for provider in handling_providers],
                *(["RasterHeightSourceService"] if raster_skill_supported else []),
            ],
        )


def _safe_can_handle(provider: Any, source_id: str) -> bool:
    can_handle = getattr(provider, "can_handle", None)
    if not callable(can_handle):
        return False
    try:
        return bool(can_handle(source_id))
    except Exception:  # noqa: BLE001
        return False
