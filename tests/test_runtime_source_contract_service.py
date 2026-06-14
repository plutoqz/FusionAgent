from __future__ import annotations

from schemas.runtime_source_contract import RuntimeProviderStatus, RuntimeSourceContract


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
