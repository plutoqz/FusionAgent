from __future__ import annotations

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
        QualityPolicyCheck(check_id="multi_source_lineage", metric_name="multi_source_lineage", operator="eq", threshold=True),
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
