from __future__ import annotations

from schemas.source_acquisition import SourceAcquisitionAttempt

_RECOVERABLE_FAULTS = {
    "SOURCE_DOWNLOAD_FAILED",
    "SOURCE_MISSING",
    "SOURCE_CORRUPTED",
    "CRS_MISMATCH",
}

_SOURCE_FALLBACKS = {
    "catalog.earthquake.building": ["catalog.flood.building"],
    "catalog.flood.waterways": ["catalog.flood.water"],
}


def retry_schedule_seconds(*, attempt_no: int) -> int:
    attempt_no = max(1, int(attempt_no))
    return min(900, 30 * (2 ** (attempt_no - 1)))


def is_recoverable_fault(fault_class: str) -> bool:
    return str(fault_class or "") in _RECOVERABLE_FAULTS


def build_failed_attempt(
    *,
    source_id: str,
    fault_class: str,
    fault_message: str,
    attempt_no: int,
    channel: str | None = None,
) -> dict[str, object]:
    recoverable = is_recoverable_fault(fault_class)
    return SourceAcquisitionAttempt(
        source_id=source_id,
        status="failed",
        attempt_no=attempt_no,
        channel=channel,
        fault_class=fault_class,
        fault_message=fault_message,
        recoverable=recoverable,
        next_retry_after_seconds=retry_schedule_seconds(attempt_no=attempt_no) if recoverable else None,
    ).model_dump(mode="json")


def build_success_attempt(*, source_id: str, status: str = "materialized", channel: str | None = None) -> dict[str, object]:
    return SourceAcquisitionAttempt(
        source_id=source_id,
        status=status,
        channel=channel,
        recoverable=False,
    ).model_dump(mode="json")


def source_fallback_candidates(source_id: str) -> list[str]:
    return list(_SOURCE_FALLBACKS.get(str(source_id), []))


_PARTIAL_COVERAGE_ALLOWED_SOURCES = {
    "catalog.flood.road",
    "catalog.earthquake.road",
    "catalog.typhoon.road",
    "catalog.flood.water",
    "catalog.generic.poi",
}


def requires_complete_pair_coverage(source_id: str) -> bool:
    return str(source_id) not in _PARTIAL_COVERAGE_ALLOWED_SOURCES
