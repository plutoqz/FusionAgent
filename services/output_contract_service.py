from __future__ import annotations

from dataclasses import dataclass, field

from kg.policy_registry import KnowledgePolicyRegistry, default_policy_registry
from schemas.task_kind import TaskKind


@dataclass(frozen=True)
class DomainOutputContract:
    contract_id: str
    task_kind: TaskKind
    required_fields: list[str]
    preserve_if_present: list[str] = field(default_factory=list)
    field_null_rate_thresholds: dict[str, float] = field(default_factory=dict)
    soft_field_null_rate_thresholds: dict[str, float] = field(default_factory=dict)
    allowed_geometry_types: list[str] = field(default_factory=list)
    lineage_fields: list[str] = field(default_factory=list)
    uncontracted_lineage_fields: list[str] = field(default_factory=list)


def get_domain_output_contract(
    task_kind: TaskKind,
    *,
    policy_registry: KnowledgePolicyRegistry | None = None,
) -> DomainOutputContract:
    registry = policy_registry or default_policy_registry()
    record = registry.output_contract(task_kind.value)
    thresholds = {str(key): float(value) for key, value in record.get("field_null_rate_thresholds", {}).items()}
    allowed_geometry_types = [str(item) for item in record.get("allowed_geometry_types", [])]
    lineage_fields = [str(item) for item in record.get("lineage_fields", [])]
    uncontracted_lineage_fields = [str(item) for item in record.get("uncontracted_lineage_fields", [])]
    if not allowed_geometry_types or not lineage_fields or not uncontracted_lineage_fields:
        raise ValueError(f"KG output contract for {task_kind.value} lacks geometry or lineage constraints")
    return DomainOutputContract(
        contract_id=str(record["contract_id"]),
        task_kind=task_kind,
        required_fields=[str(item) for item in record.get("required_fields", [])],
        preserve_if_present=[str(item) for item in record.get("preserve_if_present", [])],
        field_null_rate_thresholds=thresholds,
        soft_field_null_rate_thresholds={
            str(key): float(value) for key, value in record.get("soft_field_null_rate_thresholds", {}).items()
        },
        allowed_geometry_types=allowed_geometry_types,
        lineage_fields=lineage_fields,
        uncontracted_lineage_fields=uncontracted_lineage_fields,
    )
