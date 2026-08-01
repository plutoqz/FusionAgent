from __future__ import annotations

from typing import Any

from kg.policy_registry import KnowledgePolicyRegistry, default_policy_registry
from kg.seed_provider import load_seed_data
from schemas.agent import WorkflowPlan
from schemas.data_requirement import (
    BundleSlot,
    CompletenessPolicy,
    DataRequirementPlan,
    SourceCandidate,
    SourceRoleRequirement,
)
from schemas.task_kind import TaskKind, task_kind_family


class DataRequirementResolverService:
    def __init__(self, policy_registry: KnowledgePolicyRegistry | None = None) -> None:
        self.policy_registry = policy_registry or default_policy_registry()

    def resolve(
        self,
        *,
        task_kind: TaskKind,
        plan: WorkflowPlan,
        mission_requirements: dict[str, Any] | None = None,
    ) -> DataRequirementPlan:
        algorithm_id = _selected_algorithm_id(plan)
        output_data_type = _selected_output_type(plan)
        mission_requirements = dict(mission_requirements or {})
        roles = _roles_from_kg(
            self.policy_registry,
            task_kind=task_kind,
            requirements=mission_requirements,
            algorithm_id=algorithm_id,
        )
        return DataRequirementPlan(
            task_kind=task_kind,
            task_family=task_kind_family(task_kind),
            algorithm_id=algorithm_id,
            output_data_type=output_data_type,
            roles=roles,
            evidence={
                "resolver_version": "kg-v1.0.0",
                "basis": "frozen_kg_source_role_policy",
                "workflow_id": plan.workflow_id,
                "knowledge_identity": self.policy_registry.knowledge_identity(),
            },
        )


def _selected_algorithm_id(plan: WorkflowPlan) -> str | None:
    for task in plan.tasks:
        if not task.is_transform:
            return task.algorithm_id
    return None


def _selected_output_type(plan: WorkflowPlan) -> str | None:
    for task in plan.tasks:
        if not task.is_transform:
            return task.output.data_type_id
    return None


def _roles_from_kg(
    registry: KnowledgePolicyRegistry,
    *,
    task_kind: TaskKind,
    requirements: dict[str, Any],
    algorithm_id: str | None,
) -> list[SourceRoleRequirement]:
    roles: list[SourceRoleRequirement] = []
    source_by_id = {
        source.source_id: source
        for source in load_seed_data()["data_sources"]
    }
    for record in registry.source_role_policies(task_kind.value):
        condition = record.get("condition")
        if condition == "building_height_or_height_algorithm":
            wants_height = bool(requirements.get("building_height")) or "height" in str(algorithm_id or "").casefold()
            if not wants_height:
                continue
        elif condition is not None:
            raise ValueError(
                f"KG source role {record.get('role_id')} has unsupported condition {condition!r}"
            )
        if "required" not in record:
            raise ValueError(f"KG source role {record.get('role_id')} must declare required")
        if "bundle_slot" not in record:
            raise ValueError(f"KG source role {record.get('role_id')} must declare bundle_slot")
        candidates: list[SourceCandidate] = []
        for item in record.get("candidates", []):
            candidate = SourceCandidate.model_validate(item)
            source = source_by_id.get(candidate.source_id)
            if source is None:
                raise ValueError(
                    f"KG source role {record.get('role_id')} references unknown source {candidate.source_id}"
                )
            metadata = dict(source.metadata or {})
            provider_family = str(metadata.get("provider_family") or "")
            if provider_family and candidate.provider_family != provider_family:
                raise ValueError(
                    f"KG source role {record.get('role_id')} provider_family mismatch for "
                    f"{candidate.source_id}: {candidate.provider_family!r} != {provider_family!r}"
                )
            if (
                str(metadata.get("runtime_status") or "runtime_candidate")
                in {"reservation_only", "deprecated"}
                or metadata.get("selectable_now") is not True
            ):
                continue
            candidates.append(candidate)
        if not candidates:
            raise ValueError(f"KG source role {record.get('role_id')} has no executable candidates")
        completeness_policy = CompletenessPolicy(str(record["completeness_policy"]))
        roles.append(
            SourceRoleRequirement(
                role_id=str(record["role_id"]),
                required=bool(record["required"]),
                bundle_slot=BundleSlot(str(record["bundle_slot"])),
                geometry_types=[str(item) for item in record.get("geometry_types", [])],
                completeness_policy=completeness_policy,
                candidates=candidates,
                fallback_role_ids=[str(item) for item in record.get("fallback_role_ids", [])],
                distinct_from_role_ids=[
                    str(item) for item in record.get("distinct_from_role_ids", [])
                ],
            )
        )
    role_ids = [role.role_id for role in roles]
    if len(role_ids) != len(set(role_ids)):
        raise ValueError(f"KG source role policy has duplicate role IDs for {task_kind.value}")
    for role in roles:
        unknown_distinct_roles = sorted(set(role.distinct_from_role_ids) - set(role_ids))
        if unknown_distinct_roles:
            raise ValueError(
                f"KG source role {role.role_id} references unknown distinct roles: "
                + ", ".join(unknown_distinct_roles)
            )
    vector_roles = [
        role
        for role in roles
        if not any(str(item).casefold() == "raster" for item in role.geometry_types)
    ]
    primary_roles = [role.role_id for role in vector_roles if role.bundle_slot == BundleSlot.primary]
    reference_roles = [role.role_id for role in vector_roles if role.bundle_slot == BundleSlot.reference]
    if len(primary_roles) != 1:
        raise ValueError(
            f"KG source roles for {task_kind.value} must declare exactly one vector primary slot"
        )
    if len(reference_roles) > 1:
        raise ValueError(
            f"KG source roles for {task_kind.value} must declare at most one vector reference slot"
        )
    return roles
