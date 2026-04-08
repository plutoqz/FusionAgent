from __future__ import annotations

from typing import Dict

from kg.repository import KGRepository
from schemas.agent import WorkflowPlan


def bind_plan_parameters(plan: WorkflowPlan, kg_repo: KGRepository) -> WorkflowPlan:
    for task in plan.tasks:
        if task.is_transform:
            continue
        specs = kg_repo.get_parameter_specs(task.algorithm_id)
        defaults: Dict[str, object] = {}
        for spec in specs:
            defaults[spec.key] = spec.default
        defaults.update(task.input.parameters or {})
        task.input.parameters = defaults
    return plan
