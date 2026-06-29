from __future__ import annotations

from schemas.runtime_source_contract import RuntimeProviderStatus, RuntimeSourceContract
from services.runtime_source_contract_service import RuntimeSourceContractService


class _FakeRawService:
    def __init__(self, supported: set[str]) -> None:
        self.supported = supported

    def can_handle(self, source_id: str) -> bool:
        return source_id in self.supported


class _FakeProvider:
    def __init__(self, supported: set[str]) -> None:
        self.supported = supported

    def can_handle(self, source_id: str) -> bool:
        return source_id in self.supported


def test_runtime_source_contract_records_provider_readiness() -> None:
    contract = RuntimeSourceContract(
        source_id="raw.example.source",
        catalog_selectable=True,
        raw_vector_supported=True,
        input_bundle_supported=False,
        status=RuntimeProviderStatus.reservation_only,
        reasons=["source is known but no input bundle provider can materialize it"],
        required_external_config=["EXAMPLE_API_KEY"],
    )

    assert contract.source_id == "raw.example.source"
    assert contract.status == RuntimeProviderStatus.reservation_only
    assert contract.catalog_selectable is True
    assert contract.raw_vector_supported is True
    assert contract.input_bundle_supported is False
    assert contract.required_external_config == ["EXAMPLE_API_KEY"]


def test_runtime_source_contract_serializes_status_as_json_string() -> None:
    contract = RuntimeSourceContract(
        source_id="raw.example.source",
        status=RuntimeProviderStatus.runtime_ready,
    )

    payload = contract.model_dump(mode="json")

    assert payload["status"] == "runtime_ready"
    assert type(payload["status"]) is str


def test_runtime_source_contract_default_lists_are_isolated() -> None:
    first = RuntimeSourceContract(
        source_id="raw.example.first",
        status=RuntimeProviderStatus.runtime_ready,
    )
    second = RuntimeSourceContract(
        source_id="raw.example.second",
        status=RuntimeProviderStatus.runtime_ready,
    )

    first.reasons.append("first-only reason")

    assert first.reasons == ["first-only reason"]
    assert second.reasons == []


def test_runtime_source_contract_service_marks_missing_input_provider() -> None:
    service = RuntimeSourceContractService(
        raw_source_service=_FakeRawService({"raw.known"}),
        input_bundle_providers=[_FakeProvider({"catalog.bundle"})],
        external_config_provider=lambda source_id: [],
    )

    contracts = service.check_sources(["raw.known", "catalog.bundle", "raw.unknown"])
    by_id = {contract.source_id: contract for contract in contracts}

    assert by_id["raw.known"].raw_vector_supported is True
    assert by_id["raw.known"].input_bundle_supported is False
    assert by_id["raw.known"].status.value == "reservation_only"
    assert by_id["raw.known"].reasons == ["raw source is known but no input bundle provider can materialize it"]
    assert by_id["catalog.bundle"].status.value == "runtime_ready"
    assert by_id["raw.unknown"].status.value == "missing_provider"
    assert by_id["raw.unknown"].reasons == [
        "source is not handled by raw source service or input bundle providers"
    ]


def test_runtime_source_contract_service_marks_external_config_requirements() -> None:
    service = RuntimeSourceContractService(
        raw_source_service=_FakeRawService({"raw.google.poi"}),
        input_bundle_providers=[_FakeProvider({"raw.google.poi"})],
        external_config_provider=lambda source_id: ["GOOGLE_PLACES_API_KEY"] if source_id == "raw.google.poi" else [],
    )

    contract = service.check_sources(["raw.google.poi"])[0]

    assert contract.status.value == "requires_external_config"
    assert contract.required_external_config == ["GOOGLE_PLACES_API_KEY"]
    assert contract.reasons == ["source requires external configuration before autonomous materialization"]


def test_runtime_source_contract_service_marks_height_rasters_as_skill_ready() -> None:
    service = RuntimeSourceContractService(
        raw_source_service=_FakeRawService(set()),
        input_bundle_providers=[],
        external_config_provider=lambda source_id: [],
    )

    contract = service.check_source("raw.google.open_buildings_2_5d.height_raster")

    assert contract.status == RuntimeProviderStatus.runtime_ready
    assert contract.input_bundle_supported is True
    assert contract.provider_names == ["RasterHeightSourceService"]
    assert contract.reasons == ["source is handled by building height raster acquisition skill"]


def test_runtime_source_contract_service_deduplicates_sources_deterministically() -> None:
    service = RuntimeSourceContractService(
        raw_source_service=_FakeRawService({"raw.known"}),
        input_bundle_providers=[_FakeProvider({"catalog.ready"})],
        external_config_provider=lambda source_id: [],
    )

    contracts = service.check_sources(["catalog.ready", "raw.known", "catalog.ready", "raw.known"])

    assert [contract.source_id for contract in contracts] == ["catalog.ready", "raw.known"]
    assert [contract.status for contract in contracts] == [
        RuntimeProviderStatus.runtime_ready,
        RuntimeProviderStatus.reservation_only,
    ]
