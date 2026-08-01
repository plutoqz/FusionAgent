from __future__ import annotations

from kg.policy_registry import KnowledgePolicyRegistry, default_policy_registry
from schemas.degradation import DegradationContext, DegradationLevel
from schemas.source_acquisition import SourceAcquisitionAttempt

_POLICY_REGISTRY = default_policy_registry()
_FAULT_POLICY = _POLICY_REGISTRY.fault_policy()
_RECOVERABLE_FAULTS = set(_FAULT_POLICY["recoverable_faults"])
SOURCE_ATTEMPT_STATUSES = set(_FAULT_POLICY["source_attempt_statuses"])
EXTERNAL_UNCONTROLLABLE_FAULTS = set(_FAULT_POLICY["external_uncontrollable_faults"])
SYSTEM_FAILURE_FAULTS = set(_FAULT_POLICY["system_failure_faults"])
_FAULT_STATUS_NORMALIZATION = dict(_FAULT_POLICY["status_normalization"])
_FAULT_NORMALIZED_FROM_STATUSES = set(_FAULT_POLICY["normalization_input_statuses"])


def retry_schedule_seconds(
    *,
    attempt_no: int,
    policy_registry: KnowledgePolicyRegistry | None = None,
) -> int:
    attempt_no = max(1, int(attempt_no))
    retry_policy = (policy_registry or default_policy_registry()).fault_policy()["retry_policy"]
    return min(
        int(retry_policy["max_seconds"]),
        int(retry_policy["initial_seconds"]) * (int(retry_policy["multiplier"]) ** (attempt_no - 1)),
    )


def is_recoverable_fault(
    fault_class: str,
    *,
    policy_registry: KnowledgePolicyRegistry | None = None,
) -> bool:
    recoverable_faults = set(
        (policy_registry or default_policy_registry()).fault_policy()["recoverable_faults"]
    )
    return str(fault_class or "") in recoverable_faults


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


def source_fallback_candidates(
    source_id: str,
    *,
    policy_registry: KnowledgePolicyRegistry | None = None,
) -> list[str]:
    policy = (policy_registry or default_policy_registry()).source_bundle_policy(str(source_id), required=True)
    return [str(item) for item in policy.get("fallback_source_ids", [])]


def source_component_candidates(
    source_id: str,
    default: list[str] | tuple[str, ...],
    *,
    policy_registry: KnowledgePolicyRegistry | None = None,
) -> list[str]:
    policy = (policy_registry or default_policy_registry()).source_bundle_policy(str(source_id), required=True)
    return [str(item) for item in policy.get("component_candidates", [])]


def required_full_closure_source_ids(
    source_id: str,
    *,
    policy_registry: KnowledgePolicyRegistry | None = None,
) -> list[str]:
    policy = (policy_registry or default_policy_registry()).source_bundle_policy(str(source_id), required=True)
    return [str(item) for item in policy.get("required_full_closure", [])]


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


def requires_complete_pair_coverage(
    source_id: str,
    *,
    policy_registry: KnowledgePolicyRegistry | None = None,
) -> bool:
    policy = (policy_registry or default_policy_registry()).source_bundle_policy(str(source_id), required=True)
    return not bool(policy.get("allows_partial_coverage"))
