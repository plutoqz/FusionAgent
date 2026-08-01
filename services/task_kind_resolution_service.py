from __future__ import annotations

from kg.policy_registry import KnowledgePolicyRegistry, default_policy_registry
from kg.seed_provider import load_seed_data
from schemas.agent import RunCreateRequest, WorkflowPlan
from schemas.task_kind import TaskKind, expand_job_type_to_task_kinds


def resolve_task_kind(
    *,
    request: RunCreateRequest,
    plan: WorkflowPlan | None = None,
    policy_registry: KnowledgePolicyRegistry | None = None,
) -> TaskKind:
    registry = policy_registry or default_policy_registry()
    records = registry.task_records()
    candidates: list[tuple[str, str]] = []

    if plan is not None:
        task_ids = [
            str(task.task_id)
            for task in plan.tasks
            if not task.is_transform and task.task_id
        ]
        for task_id in dict.fromkeys(task_ids):
            matches = [
                str(record["task_kind"])
                for record in records
                if str(record.get("task_id") or "") == task_id
            ]
            if len(matches) != 1:
                raise ValueError(
                    f"KG task semantics cannot resolve task_id={task_id!r} to one task kind"
                )
            candidates.append((f"plan_task:{task_id}", matches[0]))

        output_types: list[str] = []
        if plan.output_requirement is not None and plan.output_requirement.output_type:
            output_types.append(str(plan.output_requirement.output_type))
        output_types.extend(
            str(task.output.data_type_id)
            for task in plan.tasks
            if not task.is_transform and task.output.data_type_id
        )
        for output_type in dict.fromkeys(output_types):
            matches = [
                str(record["task_kind"])
                for record in records
                if str(record.get("output_data_type") or "") == output_type
            ]
            if len(matches) != 1:
                raise ValueError(
                    f"KG task semantics cannot resolve output_data_type={output_type!r} to one task kind"
                )
            candidates.append((f"plan_output:{output_type}", matches[0]))

        if plan.product_contract is not None:
            contract_id = str(plan.product_contract.contract_id or "").strip()
            contract_matches = [
                str(record["task_kind"])
                for record in records
                if contract_id
                in {
                    str(registry.output_contract(str(record["task_kind"])).get("contract_id") or ""),
                    str(registry.output_contract(str(record["task_kind"])).get("product_contract_id") or ""),
                }
            ]
            if len(contract_matches) == 1:
                candidates.append((f"product_contract:{contract_id}", contract_matches[0]))
            elif len(contract_matches) > 1:
                raise ValueError(
                    f"KG output contracts resolve contract_id={contract_id!r} to multiple task kinds"
                )
            elif contract_id not in load_seed_data()["product_contracts"]:
                raise ValueError(f"Frozen KG has no product contract {contract_id!r}")

    preferred_pattern_id = str(request.preferred_pattern_id or "").strip()
    if preferred_pattern_id:
        matches = [
            str(record["task_kind"])
            for record in records
            if str(record.get("preferred_pattern_id") or "") == preferred_pattern_id
        ]
        if not matches:
            patterns = [
                pattern
                for pattern in load_seed_data()["patterns"]
                if pattern.pattern_id == preferred_pattern_id
            ]
            if len(patterns) == 1 and patterns[0].steps:
                output_type = max(patterns[0].steps, key=lambda step: step.order).output_data_type
                matches = [
                    str(record["task_kind"])
                    for record in records
                    if str(record.get("output_data_type") or "") == output_type
                ]
        if len(matches) != 1:
            raise ValueError(
                f"KG task semantics cannot resolve preferred_pattern_id={preferred_pattern_id!r} to one task kind"
            )
        candidates.append((f"preferred_pattern:{preferred_pattern_id}", matches[0]))

    expanded = expand_job_type_to_task_kinds(request.job_type)
    if len(expanded) == 1:
        candidates.append((f"job_type:{request.job_type.value}", expanded[0].value))
    elif not candidates:
        if len(expanded) != 1:
            raise ValueError(
                f"job_type={request.job_type.value!r} is ambiguous; a frozen plan output or exact preferred pattern is required"
            )

    resolved = {task_kind for _, task_kind in candidates}
    if len(resolved) != 1:
        evidence = ", ".join(f"{source}={task_kind}" for source, task_kind in candidates)
        raise ValueError(f"Task-kind evidence conflicts: {evidence}")
    return TaskKind(next(iter(resolved)))
