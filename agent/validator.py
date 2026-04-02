from __future__ import annotations

from typing import Dict, List

from kg.repository import KGRepository
from schemas.agent import (
    ValidationIssue,
    ValidationReport,
    WorkflowPlan,
    WorkflowTask,
    WorkflowTaskInput,
    WorkflowTaskOutput,
)


class WorkflowValidator:
    def __init__(self, kg_repo: KGRepository) -> None:
        self.kg_repo = kg_repo

    def validate_and_repair(self, plan: WorkflowPlan) -> WorkflowPlan:
        issues: List[ValidationIssue] = []
        inserted = 0
        output_tasks: List[WorkflowTask] = []
        step_map: Dict[int, int] = {}

        for task in sorted(plan.tasks, key=lambda t: t.step):
            original_step = task.step
            normalized_deps = [step_map[d] for d in task.depends_on if d in step_map]

            algo = self.kg_repo.get_algorithm(task.algorithm_id)
            if algo is None:
                task.kg_validated = False
                task.depends_on = normalized_deps
                task.step = len(output_tasks) + 1
                output_tasks.append(task)
                step_map[original_step] = task.step
                issues.append(
                    ValidationIssue(
                        code="UNKNOWN_ALGORITHM",
                        message=f"Algorithm not found in KG: {task.algorithm_id}",
                        step=task.step,
                    )
                )
                continue

            input_type = task.input.data_type_id
            expected_inputs = algo.input_types or []
            if input_type in expected_inputs:
                task.kg_validated = True
                task.depends_on = normalized_deps
                task.step = len(output_tasks) + 1
                output_tasks.append(task)
                step_map[original_step] = task.step
                continue

            transform_target = expected_inputs[0] if expected_inputs else input_type
            path = self.kg_repo.find_transform_path(from_type=input_type, to_type=transform_target, max_depth=3)
            if not path or len(path) < 2:
                task.kg_validated = False
                task.depends_on = normalized_deps
                task.step = len(output_tasks) + 1
                output_tasks.append(task)
                step_map[original_step] = task.step
                issues.append(
                    ValidationIssue(
                        code="NO_TRANSFORM_PATH",
                        message=f"No transform path from {input_type} to {transform_target} for {task.algorithm_id}",
                        step=task.step,
                    )
                )
                continue

            deps = normalized_deps
            for hop_idx in range(len(path) - 1):
                src = path[hop_idx]
                dst = path[hop_idx + 1]
                transform_task = WorkflowTask(
                    step=len(output_tasks) + 1,
                    name=f"transform_{src}_to_{dst}",
                    description=f"Auto inserted transform from {src} to {dst}",
                    algorithm_id=f"algo.transform.{src}_to_{dst}",
                    input=WorkflowTaskInput(
                        data_type_id=src,
                        data_source_id=task.input.data_source_id,
                        parameters={},
                    ),
                    output=WorkflowTaskOutput(
                        data_type_id=dst,
                        description=f"Transformed {src} to {dst}",
                    ),
                    depends_on=deps,
                    is_transform=True,
                    kg_validated=True,
                    alternatives=[],
                )
                output_tasks.append(transform_task)
                inserted += 1
                deps = [transform_task.step]

            task.input.data_type_id = transform_target
            task.depends_on = deps
            task.kg_validated = True
            task.step = len(output_tasks) + 1
            output_tasks.append(task)
            step_map[original_step] = task.step

        report = ValidationReport(valid=(len(issues) == 0), inserted_transform_steps=inserted, issues=issues)
        plan.tasks = output_tasks
        plan.validation = report
        return plan

