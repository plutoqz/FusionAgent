from __future__ import annotations

from schemas.agent import WorkflowPlan
from services.source_semantic_contract_service import SourceSemanticContract


def bind_source_semantic_parameters(plan: WorkflowPlan, contract: SourceSemanticContract, kg_repo=None) -> WorkflowPlan:
    for task in plan.tasks:
        if task.is_transform:
            continue
        params = dict(task.input.parameters or {})
        allowed = _allowed_parameter_keys(task, kg_repo)
        _set_if_allowed(params, allowed, "source_semantic_contract_path", "source_semantic_contract.json")

        if contract.job_type == "building":
            for key in ["height_output_field", "canonical_height_field", "positive_only"]:
                if key in contract.height_policy:
                    _set_if_allowed(params, allowed, key, contract.height_policy[key])
            priority = contract.parameter_hints.get("source_priority_order")
            if priority:
                _set_if_allowed(params, allowed, "source_priority_order", list(priority))
        elif contract.job_type == "poi":
            precision = contract.parameter_hints.get("geohash_precision")
            if precision is not None:
                _set_if_allowed(params, allowed, "geohash_precision", int(precision))

        task.input.parameters = params
    return plan


def _allowed_parameter_keys(task, kg_repo) -> set[str] | None:
    if kg_repo is None:
        return None
    get_parameter_specs = getattr(kg_repo, "get_parameter_specs", None)
    if not callable(get_parameter_specs):
        return None
    return {spec.key for spec in get_parameter_specs(task.algorithm_id)}


def _set_if_allowed(params: dict, allowed: set[str] | None, key: str, value) -> None:
    if allowed is None or key in allowed:
        params[key] = value
