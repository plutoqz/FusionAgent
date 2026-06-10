from __future__ import annotations

from pathlib import Path

from schemas.quality_gate import QualityGateReport
from schemas.task_kind import TaskKind
from services.artifact_evaluation_service import evaluate_vector_artifact
from services.output_contract_service import get_domain_output_contract
from services.quality_policy_service import get_quality_policy

_EXPECTED_GEOMETRIES = {
    TaskKind.building: {"Polygon", "MultiPolygon"},
    TaskKind.road: {"LineString", "MultiLineString"},
    TaskKind.water_polygon: {"Polygon", "MultiPolygon"},
    TaskKind.waterways: {"LineString", "MultiLineString"},
    TaskKind.poi: {"Point", "MultiPoint"},
}


class QualityGateService:
    def evaluate(
        self,
        *,
        artifact_path: Path,
        task_kind: TaskKind,
        required_fields: list[str],
        requested_bbox=None,
        component_coverage: dict[str, object] | None = None,
        quality_policy_id: str | None = None,
        contract_id: str | None = None,
        source_expected_null_rates: dict[str, float] | None = None,
    ) -> QualityGateReport:
        contract = (
            get_domain_output_contract(task_kind, source_expected_null_rates=source_expected_null_rates)
            if contract_id is not None
            else None
        )
        if contract is not None and contract.contract_id != contract_id:
            raise ValueError(
                f"Quality contract {contract.contract_id} for {task_kind.value} does not match requested {contract_id}"
            )
        effective_required_fields = _merge_fields(
            list(required_fields or []),
            contract.required_fields if contract is not None else [],
        )
        policy = get_quality_policy(task_kind=task_kind, policy_id=quality_policy_id)
        metrics = evaluate_vector_artifact(
            Path(artifact_path),
            required_fields=effective_required_fields,
            requested_bbox=requested_bbox,
        )
        checks = {
            "readable": {"passed": "error" not in metrics},
            "non_empty": {"passed": int(metrics.get("feature_count") or 0) > 0},
            "required_fields": {"passed": not metrics.get("missing_fields")},
            "geometry_type": {
                "passed": bool(set(metrics.get("geometry_types") or []) & _EXPECTED_GEOMETRIES[task_kind]),
                "expected": sorted(_EXPECTED_GEOMETRIES[task_kind]),
                "actual": metrics.get("geometry_types") or [],
            },
            "aoi_intersection": {
                "passed": bool(metrics.get("aoi_consistency", {}).get("artifact_intersects_aoi", requested_bbox is None)),
            },
            "source_lineage": {
                "passed": _lineage_present(
                    effective_required_fields,
                    metrics,
                    lineage_fields=(
                        {"source_id", "source_feature_id", "fusion_source", "source_layer"}
                        if contract is not None
                        else {"source_id"}
                    ),
                    require_required_field=contract is None,
                ),
            },
            "multi_source_lineage": {
                "passed": _multi_source_lineage_available(component_coverage or {}),
            },
        }
        if contract is not None:
            for field, threshold in contract.field_null_rate_thresholds.items():
                metric_name = f"{field}_null_rate"
                value = metrics.get(metric_name)
                checks[f"field_null_rate:{field}"] = {
                    "passed": _policy_check_passed(value, operator="lte", threshold=threshold),
                    "severity": "soft",
                    "operator": "lte",
                    "threshold": threshold,
                    "actual": value,
                    "metric_name": metric_name,
                }
        policy_metrics = {**metrics, **{name: check["passed"] for name, check in checks.items()}}
        for policy_check in policy.checks:
            if not policy_check.enabled:
                continue
            if policy_check.check_id in checks:
                passed = _policy_check_passed(
                    policy_metrics.get(policy_check.metric_name),
                    operator=policy_check.operator,
                    threshold=policy_check.threshold,
                )
                checks[policy_check.check_id] = {
                    **checks[policy_check.check_id],
                    "passed": passed,
                    "severity": policy_check.severity,
                    "operator": policy_check.operator,
                    "threshold": policy_check.threshold,
                }
                continue
            value = policy_metrics.get(policy_check.metric_name)
            checks[policy_check.check_id] = {
                "passed": _policy_check_passed(
                    value,
                    operator=policy_check.operator,
                    threshold=policy_check.threshold,
                ),
                "severity": policy_check.severity,
                "operator": policy_check.operator,
                "threshold": policy_check.threshold,
                "actual": value,
            }
        failure_reasons = [
            name
            for name, check in checks.items()
            if not check["passed"] and str(check.get("severity") or "hard") == "hard"
        ]
        soft_failure_reasons = [
            name
            for name, check in checks.items()
            if not check["passed"] and str(check.get("severity") or "hard") == "soft"
        ]
        return QualityGateReport(
            accepted=not failure_reasons,
            task_kind=task_kind,
            artifact_path=str(artifact_path),
            checks=checks,
            metrics=metrics,
            failure_reasons=failure_reasons,
            policy_id=policy.policy_id,
            soft_failure_reasons=soft_failure_reasons,
        )


def _multi_source_lineage_available(component_coverage: dict[str, object]) -> bool:
    available = []
    for source_id, payload in component_coverage.items():
        if isinstance(payload, dict):
            count = payload.get("feature_count")
            status = str(payload.get("coverage_status") or "")
            if status in {"available", "unknown_until_materialization"} or (count is not None and int(count) > 0):
                available.append(source_id)
    return len(set(available)) >= 2


def _merge_fields(primary: list[str], secondary: list[str]) -> list[str]:
    result: list[str] = []
    for field in [*primary, *secondary]:
        if field not in result:
            result.append(field)
    return result


def _lineage_present(
    required_fields: list[str],
    metrics: dict[str, object],
    *,
    lineage_fields: set[str],
    require_required_field: bool,
) -> bool:
    missing = set(metrics.get("missing_fields", []) or [])
    if not require_required_field:
        available_fields = set((metrics.get("field_null_rates") or {}).keys())
        return any(field in available_fields and field not in missing for field in lineage_fields)
    return any(field in required_fields and field not in missing for field in lineage_fields)


def _policy_check_passed(value, *, operator: str, threshold) -> bool:
    if operator == "eq":
        return value == threshold
    if value is None:
        return False
    try:
        actual = float(value)
        expected = float(threshold)
    except (TypeError, ValueError):
        return False
    if operator == "lte":
        return actual <= expected
    if operator == "lt":
        return actual < expected
    if operator == "gte":
        return actual >= expected
    if operator == "gt":
        return actual > expected
    return False
