from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from schemas.runtime_source_contract import RuntimeProviderStatus, RuntimeSourceContract


ExternalConfigProvider = Callable[[str], list[str]]


class RuntimeSourceContractService:
    def __init__(
        self,
        raw_source_service: object,
        input_bundle_providers: Iterable[object],
        external_config_provider: ExternalConfigProvider | None = None,
    ) -> None:
        self.raw_source_service = raw_source_service
        self.input_bundle_providers = list(input_bundle_providers)
        self.external_config_provider = external_config_provider or (lambda source_id: [])

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
        raw_supported = _safe_can_handle(self.raw_source_service, source_id)
        handling_providers = [
            provider
            for provider in self.input_bundle_providers
            if _safe_can_handle(provider, source_id)
        ]
        input_supported = bool(handling_providers)
        required_external_config = list(self.external_config_provider(source_id) or [])

        reasons: list[str] = []
        if required_external_config:
            status = RuntimeProviderStatus.requires_external_config
            reasons.append("source requires external configuration before autonomous materialization")
        elif input_supported:
            status = RuntimeProviderStatus.runtime_ready
        elif raw_supported:
            status = RuntimeProviderStatus.reservation_only
            reasons.append("raw source is known but no input bundle provider can materialize it")
        else:
            status = RuntimeProviderStatus.missing_provider
            reasons.append("source is not handled by raw source service or input bundle providers")

        return RuntimeSourceContract(
            source_id=source_id,
            catalog_selectable=True,
            raw_vector_supported=raw_supported,
            input_bundle_supported=input_supported,
            status=status,
            reasons=reasons,
            required_external_config=required_external_config,
            provider_names=[provider.__class__.__name__ for provider in handling_providers],
        )


def _safe_can_handle(provider: Any, source_id: str) -> bool:
    can_handle = getattr(provider, "can_handle", None)
    if not callable(can_handle):
        return False
    try:
        return bool(can_handle(source_id))
    except Exception:  # noqa: BLE001
        return False
