from __future__ import annotations

from services.source_acquisition_policy import (
    build_failed_attempt,
    requires_complete_pair_coverage,
    retry_schedule_seconds,
    source_fallback_candidates,
)


def test_retry_schedule_uses_bounded_exponential_backoff() -> None:
    assert retry_schedule_seconds(attempt_no=1) == 30
    assert retry_schedule_seconds(attempt_no=2) == 60
    assert retry_schedule_seconds(attempt_no=5) == 480
    assert retry_schedule_seconds(attempt_no=99) == 900


def test_failed_attempt_records_recoverable_retry_metadata() -> None:
    attempt = build_failed_attempt(
        source_id="catalog.flood.water",
        fault_class="SOURCE_DOWNLOAD_FAILED",
        fault_message="network timeout",
        attempt_no=2,
        channel="provider",
    )

    assert attempt["source_id"] == "catalog.flood.water"
    assert attempt["status"] == "failed"
    assert attempt["recoverable"] is True
    assert attempt["next_retry_after_seconds"] == 60
    assert attempt["channel"] == "provider"


def test_source_fallback_candidates_are_source_specific() -> None:
    assert source_fallback_candidates("catalog.earthquake.building") == ["catalog.flood.building"]
    assert source_fallback_candidates("catalog.flood.waterways") == ["catalog.flood.water"]
    assert source_fallback_candidates("catalog.generic.poi") == []


def test_complete_pair_policy_requires_waterways_before_fallback() -> None:
    assert requires_complete_pair_coverage("catalog.flood.waterways") is True
    assert requires_complete_pair_coverage("catalog.flood.road") is False
