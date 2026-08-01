from __future__ import annotations

from typing import Any

from kg.policy_registry import KnowledgePolicyRegistry, default_policy_registry
from schemas.degradation import DegradationContext
from schemas.quality_policy import QualityPolicy, QualityPolicyCheck
from schemas.task_kind import TaskKind


def get_quality_policy(
    *,
    task_kind: TaskKind,
    policy_id: str | None = None,
    policy_registry: KnowledgePolicyRegistry | None = None,
) -> QualityPolicy:
    registry = policy_registry or default_policy_registry()
    record = registry.quality_policy(task_kind.value, policy_id)
    checks: list[QualityPolicyCheck] = []
    for template in registry.quality_check_templates(str(record["topology"])):
        payload = dict(template)
        threshold_ref = payload.pop("threshold_ref", None)
        if threshold_ref:
            payload["threshold"] = record[threshold_ref]
        checks.append(QualityPolicyCheck.model_validate(payload))
    return QualityPolicy(
        policy_id=str(record["policy_id"]),
        task_kind=task_kind,
        description=f"KG release quality policy for {task_kind.value}.",
        checks=checks,
        metadata={"knowledge_identity": registry.knowledge_identity()},
    )


def adapt_policy_for_degradation(
    policy: QualityPolicy,
    *,
    task_kind: TaskKind,
    component_coverage: dict[str, object] | None = None,
    degradation_context: DegradationContext | None = None,
    policy_registry: KnowledgePolicyRegistry | None = None,
) -> tuple[QualityPolicy, list[dict[str, Any]]]:
    """Return a runtime policy adapted to externally degraded source coverage."""
    if degradation_context is None or not degradation_context.external_only:
        return policy, []

    available_source_count = _available_source_count(component_coverage or {})
    adaptations: list[dict[str, Any]] = []
    adapted_checks: list[QualityPolicyCheck] = []
    missing_sources = list(degradation_context.external_uncontrollable_sources or degradation_context.missing_sources)

    adaptation_policy = (policy_registry or default_policy_registry()).quality_adaptation_policy()
    single_source_soft_checks = set(adaptation_policy["single_source_soft_checks"])
    single_source_line_soft_checks = set(adaptation_policy["single_source_line_soft_checks"])
    for check in policy.checks:
        adapted = check.model_copy(deep=True)
        if check.check_id in single_source_soft_checks and available_source_count < 2:
            adapted = _adapt_check_severity(
                adapted,
                severity="soft",
                reason="single_source_external_degradation",
                missing_sources=missing_sources,
                adaptations=adaptations,
            )
        elif (
            check.check_id in single_source_line_soft_checks
            and available_source_count < 2
            and task_kind in {TaskKind.road, TaskKind.waterways}
        ):
            adapted = _adapt_check_severity(
                adapted,
                severity="soft",
                reason="single_source_external_topology_unverifiable",
                missing_sources=missing_sources,
                adaptations=adaptations,
            )
        elif check.check_id == "source_contribution_balance" and available_source_count == 2:
            original_threshold = adapted.threshold
            widened = _widen_balance_threshold(
                original_threshold,
                minimum=float(adaptation_policy["reduced_mix_balance_threshold"]),
            )
            if widened != original_threshold:
                adapted.threshold = widened
                adapted.metadata = {
                    **adapted.metadata,
                    "adaptation_reason": "reduced_source_mix_external_degradation",
                    "original_threshold": original_threshold,
                }
                adaptations.append(
                    {
                        "check_id": check.check_id,
                        "reason": "reduced_source_mix_external_degradation",
                        "original_threshold": original_threshold,
                        "adapted_threshold": widened,
                        "original_severity": check.severity,
                        "adapted_severity": adapted.severity,
                        "missing_sources": missing_sources,
                    }
                )
        adapted_checks.append(adapted)

    if not adaptations:
        return policy, []
    adapted_policy = policy.model_copy(
        deep=True,
        update={
            "policy_id": f"{policy.policy_id}.adapted",
            "checks": adapted_checks,
            "metadata": {
                **policy.metadata,
                "adapted_from_policy_id": policy.policy_id,
                "adaptation_context": degradation_context.model_dump(mode="json"),
            },
        },
    )
    return adapted_policy, adaptations


def _adapt_check_severity(
    check: QualityPolicyCheck,
    *,
    severity: str,
    reason: str,
    missing_sources: list[str],
    adaptations: list[dict[str, Any]],
) -> QualityPolicyCheck:
    if check.severity == severity:
        return check
    original_severity = check.severity
    check.severity = severity
    check.metadata = {
        **check.metadata,
        "adaptation_reason": reason,
        "original_severity": original_severity,
    }
    adaptations.append(
        {
            "check_id": check.check_id,
            "reason": reason,
            "original_severity": original_severity,
            "adapted_severity": severity,
            "original_threshold": check.threshold,
            "adapted_threshold": check.threshold,
            "missing_sources": missing_sources,
        }
    )
    return check


def _widen_balance_threshold(threshold: object, *, minimum: float) -> float:
    try:
        current = float(threshold)
    except (TypeError, ValueError):
        current = 0.0
    return max(current, minimum)


def _available_source_count(component_coverage: dict[str, object]) -> int:
    available: set[str] = set()
    for source_id, payload in component_coverage.items():
        status = str(_coverage_value(payload, "coverage_status") or "").strip().lower()
        feature_count = _coverage_feature_count(payload)
        if status in {"available", "unknown_until_materialization"} or feature_count > 0:
            available.add(str(source_id))
    return len(available)


def _coverage_value(payload: object, field_name: str) -> object:
    if isinstance(payload, dict):
        return payload.get(field_name)
    if hasattr(payload, "model_dump"):
        dumped = payload.model_dump()
        if isinstance(dumped, dict):
            return dumped.get(field_name)
    return getattr(payload, field_name, None)


def _coverage_feature_count(payload: object) -> int:
    value = _coverage_value(payload, "feature_count")
    if isinstance(value, bool):
        return 0
    try:
        return int(float(value or 0))
    except (OverflowError, TypeError, ValueError):
        return 0
