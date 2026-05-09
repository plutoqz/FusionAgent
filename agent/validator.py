from __future__ import annotations

import math
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
        if hasattr(kg_repo, "list_data_sources"):
            self._data_sources = {source.source_id: source for source in kg_repo.list_data_sources()}
        else:
            self._data_sources = {}

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

            source = self._data_sources.get(task.input.data_source_id)
            if source is None:
                task.kg_validated = False
                task.depends_on = normalized_deps
                task.step = len(output_tasks) + 1
                output_tasks.append(task)
                step_map[original_step] = task.step
                issues.append(
                    ValidationIssue(
                        code="UNKNOWN_DATA_SOURCE",
                        message=f"Data source not found in KG: {task.input.data_source_id}",
                        step=task.step,
                    )
                )
                continue

            if self._is_reservation_only(source.metadata):
                task.kg_validated = False
                task.depends_on = normalized_deps
                task.step = len(output_tasks) + 1
                output_tasks.append(task)
                step_map[original_step] = task.step
                issues.append(
                    ValidationIssue(
                        code="UNSELECTABLE_DATA_SOURCE",
                        message=f"Data source is reservation_only and cannot execute now: {task.input.data_source_id}",
                        step=task.step,
                    )
                )
                continue

            if self._is_reservation_only(algo.metadata):
                task.kg_validated = False
                task.depends_on = normalized_deps
                task.step = len(output_tasks) + 1
                output_tasks.append(task)
                step_map[original_step] = task.step
                issues.append(
                    ValidationIssue(
                        code="RESERVED_ALGORITHM",
                        message=f"Algorithm is reservation_only and cannot execute now: {task.algorithm_id}",
                        step=task.step,
                    )
                )
                continue

            if task.output.data_type_id != algo.output_type:
                task.kg_validated = False
                task.depends_on = normalized_deps
                task.step = len(output_tasks) + 1
                output_tasks.append(task)
                step_map[original_step] = task.step
                issues.append(
                    ValidationIssue(
                        code="TOOL_OUTPUT_TYPE_MISMATCH",
                        message=(
                            f"Task declares output {task.output.data_type_id} but "
                            f"tool registry expects {algo.output_type} for {task.algorithm_id}"
                        ),
                        step=task.step,
                    )
                )
                continue

            parameter_issue = self._validate_parameters(task)
            if parameter_issue is not None:
                task.kg_validated = False
                task.depends_on = normalized_deps
                task.step = len(output_tasks) + 1
                output_tasks.append(task)
                step_map[original_step] = task.step
                parameter_issue.step = task.step
                issues.append(parameter_issue)
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

    @staticmethod
    def _is_reservation_only(metadata: Dict[str, object] | None) -> bool:
        return str((metadata or {}).get("runtime_status") or "").lower() == "reservation_only"

    def _validate_parameters(self, task: WorkflowTask) -> ValidationIssue | None:
        specs = {spec.key: spec for spec in self.kg_repo.get_parameter_specs(task.algorithm_id)}
        for key, value in (task.input.parameters or {}).items():
            spec = specs.get(key)
            if spec is None:
                continue
            if spec.required and value is None:
                return ValidationIssue(
                    code="PARAM_REQUIRED_MISSING",
                    message=f"Required parameter {key} is missing for {task.algorithm_id}",
                )
            numeric_value = self._coerce_numeric(value)
            if numeric_value is None:
                continue
            if spec.min_value is not None and numeric_value < spec.min_value:
                return ValidationIssue(
                    code="PARAM_OUT_OF_RANGE",
                    message=f"Parameter {key}={numeric_value} is below min {spec.min_value} for {task.algorithm_id}",
                )
            if spec.max_value is not None and numeric_value > spec.max_value:
                return ValidationIssue(
                    code="PARAM_OUT_OF_RANGE",
                    message=f"Parameter {key}={numeric_value} exceeds max {spec.max_value} for {task.algorithm_id}",
                )
        return None

    @staticmethod
    def _coerce_numeric(value: object) -> float | None:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(numeric):
            return None
        return numeric
