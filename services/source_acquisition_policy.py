from __future__ import annotations

from schemas.degradation import DegradationContext, DegradationLevel
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

SYSTEM_FAILURE_FAULTS = {"MISSING_PROVIDER", "ALGO_RUNTIME_ERROR", "PARAM_OUT_OF_RANGE", "CRS_MISMATCH"}

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

_SOURCE_COMPONENT_CANDIDATES = {
    "catalog.flood.building": [
        "raw.google.building",
        "raw.microsoft.building",
        "raw.osm.building",
        "raw.osm.road",
        "raw.openbuildingmap.building",
    ],
    "catalog.earthquake.building": [
        "raw.google.building",
        "raw.microsoft.building",
        "raw.osm.building",
        "raw.osm.road",
        "raw.openbuildingmap.building",
    ],
    "catalog.generic.poi": ["raw.gns.poi", "raw.google.poi", "raw.osm.poi"],
    "catalog.flood.water": ["raw.osm.water", "raw.hydrolakes.water", "raw.osm.waterways", "raw.hydrorivers.water"],
    "catalog.flood.waterways": ["raw.osm.waterways", "raw.hydrorivers.water", "raw.osm.water", "raw.hydrolakes.water"],
    "catalog.flood.road": ["raw.osm.road", "raw.microsoft.road"],
    "catalog.earthquake.road": ["raw.osm.road", "raw.microsoft.road"],
    "catalog.typhoon.road": ["raw.osm.road", "raw.microsoft.road"],
}

_REQUIRED_FULL_CLOSURE_SOURCE_IDS = {
    "catalog.flood.building": [
        "raw.google.building",
        "raw.microsoft.building",
        "raw.osm.building",
        "raw.osm.road",
    ],
    "catalog.earthquake.building": [
        "raw.google.building",
        "raw.microsoft.building",
        "raw.osm.building",
        "raw.osm.road",
    ],
    "catalog.generic.poi": ["raw.gns.poi", "raw.google.poi", "raw.osm.poi"],
    "catalog.flood.road": ["raw.osm.road", "raw.microsoft.road"],
    "catalog.earthquake.road": ["raw.osm.road", "raw.microsoft.road"],
    "catalog.typhoon.road": ["raw.osm.road", "raw.microsoft.road"],
    "catalog.flood.water": ["raw.osm.water", "raw.hydrolakes.water"],
    "catalog.flood.water_polygon": ["raw.osm.water", "raw.hydrolakes.water"],
    "catalog.flood.waterways": ["raw.osm.waterways", "raw.hydrorivers.water"],
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
    external_uncontrollable: bool | None = None,
    skill_id: str | None = None,
    skill_name: str | None = None,
    capability: str | None = None,
    metadata: dict[str, object] | None = None,
    normalize_status: bool = True,
) -> dict[str, object]:
    normalized_fault_class = str(fault_class or "") if fault_class else None
    normalized_status = _normalize_attempt_status(status=status, fault_class=normalized_fault_class) if normalize_status else status
    is_recoverable = is_recoverable_fault(normalized_fault_class or "") if recoverable is None else bool(recoverable)
    is_external_uncontrollable = (
        bool(external_uncontrollable)
        if external_uncontrollable is not None
        else normalized_fault_class in EXTERNAL_UNCONTROLLABLE_FAULTS
    )
    if next_retry_after_seconds is None and is_recoverable:
        next_retry_after_seconds = retry_schedule_seconds(attempt_no=attempt_no)
    payload = SourceAcquisitionAttempt(
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
        external_uncontrollable=is_external_uncontrollable,
        skill_id=skill_id,
        skill_name=skill_name,
        capability=capability,
        metadata=dict(metadata or {}),
    ).model_dump(mode="json")
    for optional_key in ("skill_id", "skill_name", "capability"):
        if payload.get(optional_key) is None:
            payload.pop(optional_key, None)
    if not payload.get("metadata"):
        payload.pop("metadata", None)
    return payload


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
    attempt_no: int = 1,
    channel: str | None = None,
    coverage_status: str | None = None,
    feature_count: int | None = None,
    selected_for_fusion: bool = False,
) -> dict[str, object]:
    return build_source_attempt(
        source_id=source_id,
        status=status,
        attempt_no=attempt_no,
        channel=channel,
        coverage_status=coverage_status,
        feature_count=feature_count,
        selected_for_fusion=selected_for_fusion,
        recoverable=False,
    )


def source_fallback_candidates(source_id: str) -> list[str]:
    return list(_SOURCE_FALLBACKS.get(str(source_id), []))


def source_component_candidates(source_id: str, default: list[str] | tuple[str, ...]) -> list[str]:
    return list(_SOURCE_COMPONENT_CANDIDATES.get(str(source_id), list(default)))


def required_full_closure_source_ids(source_id: str) -> list[str]:
    return list(_REQUIRED_FULL_CLOSURE_SOURCE_IDS.get(str(source_id), []))


def classify_component_degradation(component_coverage: dict[str, object]) -> DegradationContext:
    available_sources: list[str] = []
    missing_sources: list[str] = []
    external_sources: list[str] = []
    system_sources: list[str] = []

    if not component_coverage:
        return DegradationContext(
            degraded=True,
            level=DegradationLevel.partial_source,
            reason="no component coverage evidence",
        )

    for source_id, coverage in component_coverage.items():
        coverage_status = str(_coverage_value(coverage, "coverage_status") or "").strip().lower()
        feature_count = _coverage_feature_count(coverage)
        if coverage_status == "available" or feature_count > 0:
            available_sources.append(source_id)
            continue

        missing_sources.append(source_id)
        fault_class = str(_coverage_value(coverage, "fault_class") or "").strip().upper()
        external_uncontrollable = _coverage_bool(coverage, "external_uncontrollable")
        if external_uncontrollable or fault_class in EXTERNAL_UNCONTROLLABLE_FAULTS:
            external_sources.append(source_id)
        if fault_class in SYSTEM_FAILURE_FAULTS:
            system_sources.append(source_id)

    if not missing_sources:
        return DegradationContext(
            degraded=False,
            level=DegradationLevel.none,
            reason="all component sources have coverage",
            available_sources=available_sources,
            missing_sources=[],
        )

    if system_sources:
        level = DegradationLevel.system_failure
        reason = "component coverage degraded by system provider failure"
    elif len(external_sources) == len(missing_sources):
        level = DegradationLevel.external_uncontrollable
        reason = "component coverage degraded by external uncontrollable source failures"
    else:
        level = DegradationLevel.partial_source
        reason = "component coverage degraded by partial source coverage"

    return DegradationContext(
        degraded=True,
        level=level,
        reason=reason,
        available_sources=available_sources,
        missing_sources=missing_sources,
        external_uncontrollable_sources=external_sources,
        system_failure_sources=system_sources,
    )


def _coverage_value(coverage: object, field_name: str) -> object:
    if isinstance(coverage, dict):
        return coverage.get(field_name)
    if hasattr(coverage, "model_dump"):
        dumped = coverage.model_dump()
        if isinstance(dumped, dict):
            return dumped.get(field_name)
    return getattr(coverage, field_name, None)


def _coverage_feature_count(coverage: object) -> int:
    value = _coverage_value(coverage, "feature_count")
    if isinstance(value, bool):
        return 0
    try:
        return int(float(value or 0))
    except (OverflowError, TypeError, ValueError):
        return 0


def _coverage_bool(coverage: object, field_name: str) -> bool:
    value = _coverage_value(coverage, field_name)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


_PARTIAL_COVERAGE_ALLOWED_SOURCES = {
    "catalog.flood.road",
    "catalog.earthquake.road",
    "catalog.typhoon.road",
    "catalog.flood.water",
    "catalog.generic.poi",
}


def requires_complete_pair_coverage(source_id: str) -> bool:
    return str(source_id) not in _PARTIAL_COVERAGE_ALLOWED_SOURCES
