from __future__ import annotations

from typing import Any

from schemas.degradation import DegradationContext
from schemas.quality_policy import QualityPolicy, QualityPolicyCheck
from schemas.task_kind import TaskKind


def get_quality_policy(*, task_kind: TaskKind, policy_id: str | None = None) -> QualityPolicy:
    policies = _default_policies()
    selected_id = policy_id or _DEFAULT_POLICY_BY_TASK_KIND[task_kind]
    if selected_id not in policies:
        raise ValueError(f"Unknown quality policy: {selected_id}")
    policy = policies[selected_id]
    if policy.task_kind != task_kind:
        raise ValueError(f"Quality policy {selected_id} is for {policy.task_kind.value}, not {task_kind.value}")
    return policy


def adapt_policy_for_degradation(
    policy: QualityPolicy,
    *,
    task_kind: TaskKind,
    component_coverage: dict[str, object] | None = None,
    degradation_context: DegradationContext | None = None,
) -> tuple[QualityPolicy, list[dict[str, Any]]]:
    """Return a runtime policy adapted to externally degraded source coverage."""
    if degradation_context is None or not degradation_context.external_only:
        return policy, []

    available_source_count = _available_source_count(component_coverage or {})
    adaptations: list[dict[str, Any]] = []
    adapted_checks: list[QualityPolicyCheck] = []
    missing_sources = list(degradation_context.external_uncontrollable_sources or degradation_context.missing_sources)

    for check in policy.checks:
        adapted = check.model_copy(deep=True)
        if check.check_id == "multi_source_lineage" and available_source_count < 2:
            adapted = _adapt_check_severity(
                adapted,
                severity="soft",
                reason="external_source_unavailable",
                missing_sources=missing_sources,
                adaptations=adaptations,
            )
        elif check.check_id == "source_contribution_balance" and available_source_count < 2:
            adapted = _adapt_check_severity(
                adapted,
                severity="soft",
                reason="single_source_external_degradation",
                missing_sources=missing_sources,
                adaptations=adaptations,
            )
        elif check.check_id == "source_contribution_balance" and available_source_count == 2:
            original_threshold = adapted.threshold
            widened = _widen_balance_threshold(original_threshold)
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


_DEFAULT_POLICY_BY_TASK_KIND = {
    TaskKind.building: "quality.default.building.v1",
    TaskKind.road: "quality.default.road.v1",
    TaskKind.water_polygon: "quality.default.water_polygon.v1",
    TaskKind.waterways: "quality.default.waterways.v1",
    TaskKind.poi: "quality.default.poi.v1",
}


def _default_policies() -> dict[str, QualityPolicy]:
    return {
        policy.policy_id: policy
        for policy in [
            _policy(TaskKind.building, "quality.default.building.v1", duplicate_threshold=0.0, balance_threshold=0.75),
            _policy(TaskKind.road, "quality.default.road.v1", duplicate_threshold=0.05, balance_threshold=0.85),
            _policy(TaskKind.water_polygon, "quality.default.water_polygon.v1", duplicate_threshold=0.05, balance_threshold=0.90),
            _policy(TaskKind.waterways, "quality.default.waterways.v1", duplicate_threshold=0.05, balance_threshold=0.90),
            _policy(TaskKind.poi, "quality.default.poi.v1", duplicate_threshold=0.10, balance_threshold=0.95),
        ]
    }


def _policy(
    task_kind: TaskKind,
    policy_id: str,
    *,
    duplicate_threshold: float,
    balance_threshold: float,
) -> QualityPolicy:
    checks = [
        QualityPolicyCheck(check_id="readable", metric_name="readable", operator="eq", threshold=True),
        QualityPolicyCheck(check_id="non_empty", metric_name="non_empty", operator="eq", threshold=True),
        QualityPolicyCheck(check_id="required_fields", metric_name="required_fields", operator="eq", threshold=True),
        QualityPolicyCheck(check_id="geometry_type", metric_name="geometry_type", operator="eq", threshold=True),
        QualityPolicyCheck(check_id="aoi_intersection", metric_name="aoi_intersection", operator="eq", threshold=True),
        QualityPolicyCheck(check_id="source_lineage", metric_name="source_lineage", operator="eq", threshold=True),
        QualityPolicyCheck(
            check_id="multi_source_lineage",
            metric_name="multi_source_lineage",
            operator="eq",
            threshold=True,
            metadata={"downgrade_to_soft_when_external_degraded_for_task_kinds": ["poi"]},
        ),
        QualityPolicyCheck(
            check_id="duplicate_geometry_rate",
            metric_name="duplicate_geometry_rate",
            operator="lte",
            threshold=duplicate_threshold,
        ),
        QualityPolicyCheck(
            check_id="invalid_geometry_rate",
            metric_name="invalid_geometry_rate",
            operator="lte",
            threshold=0.0,
        ),
        QualityPolicyCheck(
            check_id="source_contribution_balance",
            metric_name="source_contribution_balance",
            operator="lte",
            threshold=balance_threshold,
        ),
    ]
    checks.extend(_topology_policy_checks(task_kind))
    checks.extend(
        [
            QualityPolicyCheck(
                check_id="feature_retention_rate",
                metric_name="feature_retention_rate",
                severity="soft",
                operator="gte",
                threshold=0.5,
            ),
            QualityPolicyCheck(
                check_id="coverage_retention_rate",
                metric_name="coverage_retention_rate",
                severity="soft",
                operator="gte",
                threshold=0.5,
            ),
        ]
    )
    return QualityPolicy(
        policy_id=policy_id,
        task_kind=task_kind,
        description=f"Default {task_kind.value} quality policy.",
        checks=checks,
    )


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


def _widen_balance_threshold(threshold: object) -> float:
    try:
        current = float(threshold)
    except (TypeError, ValueError):
        current = 0.0
    return max(current, 0.95)


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


def _topology_policy_checks(task_kind: TaskKind) -> list[QualityPolicyCheck]:
    if task_kind in {TaskKind.road, TaskKind.waterways}:
        return [
            QualityPolicyCheck(
                check_id="zero_length_geometry_count",
                metric_name="zero_length_geometry_count",
                operator="eq",
                threshold=0,
            ),
            QualityPolicyCheck(
                check_id="dangle_endpoint_rate_per_100km",
                metric_name="dangle_endpoint_rate_per_100km",
                operator="lte",
                threshold=500.0,
                metadata={"normalization": "dangle endpoints per 100 km of line length"},
            ),
        ]
    if task_kind in {TaskKind.building, TaskKind.water_polygon}:
        return [
            QualityPolicyCheck(
                check_id="self_intersection_count",
                metric_name="self_intersection_count",
                operator="eq",
                threshold=0,
            ),
            QualityPolicyCheck(
                check_id="sliver_polygon_count",
                metric_name="sliver_polygon_count",
                operator="lte",
                threshold=0,
            ),
        ]
    return []
