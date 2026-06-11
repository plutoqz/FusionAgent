from __future__ import annotations

from schemas.agent import WorkflowPlan
from services.conditional_parameter_service import ConditionalParameterContext, resolve_effective_parameters
from services.source_semantic_contract_service import SourceSemanticContract


def bind_source_semantic_parameters(plan: WorkflowPlan, contract: SourceSemanticContract, kg_repo=None) -> WorkflowPlan:
    for task in plan.tasks:
        if task.is_transform:
            continue
        params = dict(task.input.parameters or {})
        specs = _parameter_specs(task, kg_repo)
        allowed = _allowed_parameter_keys(specs)
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

        _bind_conditional_defaults(params, specs, contract)
        task.input.parameters = params
    return plan


def _parameter_specs(task, kg_repo) -> list | None:
    if kg_repo is None:
        return None
    get_parameter_specs = getattr(kg_repo, "get_parameter_specs", None)
    if not callable(get_parameter_specs):
        return None
    return list(get_parameter_specs(task.algorithm_id))


def _allowed_parameter_keys(specs: list | None) -> set[str] | None:
    if specs is None:
        return None
    return {spec.key for spec in specs}


def _set_if_allowed(params: dict, allowed: set[str] | None, key: str, value) -> None:
    if allowed is None or key in allowed:
        params[key] = value


def _bind_conditional_defaults(params: dict, specs: list | None, contract: SourceSemanticContract) -> None:
    if not specs:
        return

    metadata = getattr(contract, "metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    result = resolve_effective_parameters(
        specs,
        ConditionalParameterContext(
            source_ids=list(getattr(contract, "component_source_ids", []) or []),
            region_country_name=metadata.get("country_name"),
            region_country_code=metadata.get("country_code"),
            aoi_size_bucket=metadata.get("aoi_size_bucket"),
            quality_outcome=metadata.get("quality_outcome"),
            durable_learning_overrides=dict(metadata.get("durable_learning_overrides") or {}),
        ),
    )

    applied_provenance: dict = {}
    for key, value in result.values.items():
        if value is None:
            continue
        if key in params:
            continue
        params[key] = value
        applied_provenance[key] = result.provenance[key]

    if not applied_provenance:
        return

    existing_provenance = params.get("parameter_provenance")
    if not isinstance(existing_provenance, dict):
        existing_provenance = {}
    merged_provenance = dict(existing_provenance)
    for key, value in applied_provenance.items():
        merged_provenance.setdefault(key, value)
    params["parameter_provenance"] = merged_provenance
