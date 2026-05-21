from __future__ import annotations

from schemas.agent import WorkflowPlan
from services.source_semantic_contract_service import SourceSemanticContract


def bind_source_semantic_parameters(plan: WorkflowPlan, contract: SourceSemanticContract) -> WorkflowPlan:
    for task in plan.tasks:
        if task.is_transform:
            continue
        params = dict(task.input.parameters or {})
        params["source_semantic_contract_path"] = "source_semantic_contract.json"

        if contract.job_type == "building":
            for key in ["height_output_field", "canonical_height_field", "positive_only"]:
                if key in contract.height_policy:
                    params[key] = contract.height_policy[key]
            priority = contract.parameter_hints.get("source_priority_order")
            if priority:
                params["source_priority_order"] = list(priority)
        elif contract.job_type == "poi":
            precision = contract.parameter_hints.get("geohash_precision")
            if precision is not None:
                params["geohash_precision"] = int(precision)

        task.input.parameters = params
    return plan
