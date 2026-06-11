from __future__ import annotations

from schemas.source_acquisition import SourceAcquisitionAttempt

_RECOVERABLE_FAULTS = {
    "SOURCE_DOWNLOAD_FAILED",
    "SOURCE_MISSING",
    "SOURCE_CORRUPTED",
    "CRS_MISMATCH",
}

SOURCE_ATTEMPT_STATUSES = {
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
}

EXTERNAL_UNCONTROLLABLE_FAULTS = {
    "SOURCE_DOWNLOAD_FAILED",
    "NETWORK_FAILED",
    "PROVIDER_UNAVAILABLE",
    "NO_OFFICIAL_COVERAGE",
    "UNAUTHORIZED",
}

_FAULT_STATUS_NORMALIZATION = {
    "SOURCE_DOWNLOAD_FAILED": "network_failed",
    "NETWORK_FAILED": "network_failed",
    "PROVIDER_UNAVAILABLE": "provider_failed",
    "NO_OFFICIAL_COVERAGE": "no_coverage",
    "UNAUTHORIZED": "unauthorized",
}

_FAULT_NORMALIZED_FROM_STATUSES = {
    "attempted",
    "failed",
    "provider_failed",
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


def build_source_attempt(
    *,
    source_id: str,
    status: str,
    attempt_type: str = "provider",
    attempt_no: int = 1,
    channel: str | None = None,
    fault_class: str | None = None,
    fault_message: str | None = None,
    recoverable: bool | None = None,
    next_retry_after_seconds: int | None = None,
    coverage_status: str | None = None,
    feature_count: int | None = None,
    selected_for_fusion: bool = False,
    normalize_status: bool = True,
) -> dict[str, object]:
    normalized_fault_class = str(fault_class or "") if fault_class else None
    normalized_status = _normalize_attempt_status(status=status, fault_class=normalized_fault_class) if normalize_status else status
    is_recoverable = is_recoverable_fault(normalized_fault_class or "") if recoverable is None else bool(recoverable)
    if next_retry_after_seconds is None and is_recoverable:
        next_retry_after_seconds = retry_schedule_seconds(attempt_no=attempt_no)
    return SourceAcquisitionAttempt(
        source_id=source_id,
        status=normalized_status,
        attempt_type=attempt_type,
        attempt_no=attempt_no,
        channel=channel,
        fault_class=normalized_fault_class,
        fault_message=fault_message,
        recoverable=is_recoverable,
        next_retry_after_seconds=next_retry_after_seconds,
        coverage_status=coverage_status,
        feature_count=feature_count,
        selected_for_fusion=selected_for_fusion,
        external_uncontrollable=normalized_fault_class in EXTERNAL_UNCONTROLLABLE_FAULTS,
    ).model_dump(mode="json")


def _normalize_attempt_status(*, status: str, fault_class: str | None) -> str:
    normalized_status = str(status or "").strip() or "attempted"
    if normalized_status in SOURCE_ATTEMPT_STATUSES and normalized_status not in _FAULT_NORMALIZED_FROM_STATUSES:
        return normalized_status
    if fault_class in _FAULT_STATUS_NORMALIZATION:
        return _FAULT_STATUS_NORMALIZATION[fault_class]
    if fault_class and normalized_status in _FAULT_NORMALIZED_FROM_STATUSES:
        return "provider_failed"
    return normalized_status if normalized_status in SOURCE_ATTEMPT_STATUSES else "internal_failed"


def build_failed_attempt(
    *,
    source_id: str,
    fault_class: str,
    fault_message: str,
    attempt_no: int,
    channel: str | None = None,
) -> dict[str, object]:
    recoverable = is_recoverable_fault(fault_class)
    return build_source_attempt(
        source_id=source_id,
        status="failed",
        attempt_no=attempt_no,
        channel=channel,
        fault_class=fault_class,
        fault_message=fault_message,
        recoverable=recoverable,
        next_retry_after_seconds=retry_schedule_seconds(attempt_no=attempt_no) if recoverable else None,
        normalize_status=False,
    )


def build_success_attempt(
    *,
    source_id: str,
    status: str = "materialized",
    channel: str | None = None,
    coverage_status: str | None = None,
    feature_count: int | None = None,
    selected_for_fusion: bool = False,
) -> dict[str, object]:
    return build_source_attempt(
        source_id=source_id,
        status=status,
        channel=channel,
        coverage_status=coverage_status,
        feature_count=feature_count,
        selected_for_fusion=selected_for_fusion,
        recoverable=False,
    )


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
