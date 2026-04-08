from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from kg.repository import KGRepository
from schemas.agent import RepairRecord, WorkflowPlan, WorkflowTask
from schemas.fusion import JobType


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ExecutionContext:
    run_id: str
    job_type: JobType
    osm_shp: Path
    ref_shp: Path
    output_dir: Path
    target_crs: str
    field_mapping: Dict[str, Dict[str, str]] = field(default_factory=dict)
    debug: bool = False
    alternative_data_sources: List[str] = field(default_factory=list)
    # Bound at execution time for the currently active step.
    active_step: Optional[int] = None
    step_parameters: Dict[str, Any] = field(default_factory=dict)


class WorkflowExecutor:
    def __init__(
        self,
        kg_repo: KGRepository,
        planner: Optional[object] = None,
        algorithm_handlers: Optional[Dict[str, Callable[[ExecutionContext], Path]]] = None,
    ) -> None:
        self.kg_repo = kg_repo
        self.planner = planner
        self.algorithm_handlers = algorithm_handlers or {}
        self.algorithm_handlers.setdefault("algo.fusion.building.v1", self._handle_building)
        self.algorithm_handlers.setdefault("algo.fusion.building.safe", self._handle_building)
        self.algorithm_handlers.setdefault("algo.fusion.road.v1", self._handle_road)
        self.algorithm_handlers.setdefault("algo.fusion.road.safe", self._handle_road)

    def execute_plan(
        self,
        plan: WorkflowPlan,
        context: ExecutionContext,
        repair_records: List[RepairRecord],
    ) -> Path:
        last_output: Optional[Path] = None
        attempt_no = len(repair_records)

        for task in sorted(plan.tasks, key=lambda t: t.step):
            if task.is_transform or task.algorithm_id.startswith("algo.transform."):
                continue

            # Bind the step-scoped parameters so handlers/adapters can consume them.
            context.active_step = task.step
            context.step_parameters = dict(task.input.parameters or {})

            try:
                last_output = self._execute_algorithm(task.algorithm_id, context)
                continue
            except Exception as first_error:  # noqa: BLE001
                attempt_no += 1
                repair_records.append(
                    RepairRecord(
                        attempt_no=attempt_no,
                        strategy="alternative_source",
                        step=task.step,
                        message=f"Primary execution failed: {first_error}",
                        success=False,
                        timestamp=_utc_now(),
                        reason_code="primary_execution_failed",
                        from_algorithm=task.algorithm_id,
                    )
                )

            # Strategy 1: alternative source id fallback (metadata-level in MVP).
            if context.alternative_data_sources:
                attempt_no += 1
                task.input.data_source_id = context.alternative_data_sources[0]
                repair_records.append(
                    RepairRecord(
                        attempt_no=attempt_no,
                        strategy="alternative_source",
                        step=task.step,
                        message=f"Switched data source id to {task.input.data_source_id}",
                        success=True,
                        timestamp=_utc_now(),
                        reason_code="alternative_source_selected",
                        from_algorithm=task.algorithm_id,
                    )
                )

            # Strategy 2: alternative algorithm.
            alt_algos = [*task.alternatives]
            if not alt_algos:
                alt_algos = [a.algo_id for a in self.kg_repo.get_alternative_algorithms(task.algorithm_id, limit=3)]
            for alt_algo in alt_algos:
                try:
                    last_output = self._execute_algorithm(alt_algo, context)
                    attempt_no += 1
                    repair_records.append(
                        RepairRecord(
                            attempt_no=attempt_no,
                            strategy="alternative_algorithm",
                            step=task.step,
                            message=f"Recovered with alternative algorithm {alt_algo}",
                            success=True,
                            timestamp=_utc_now(),
                            reason_code="alternative_algorithm_succeeded",
                            from_algorithm=task.algorithm_id,
                            to_algorithm=alt_algo,
                        )
                    )
                    break
                except Exception as alt_error:  # noqa: BLE001
                    attempt_no += 1
                    repair_records.append(
                        RepairRecord(
                            attempt_no=attempt_no,
                            strategy="alternative_algorithm",
                            step=task.step,
                            message=f"Alternative algorithm {alt_algo} failed: {alt_error}",
                            success=False,
                            timestamp=_utc_now(),
                            reason_code="alternative_algorithm_failed",
                            from_algorithm=task.algorithm_id,
                            to_algorithm=alt_algo,
                        )
                    )
            if last_output is not None:
                continue

            # Strategy 3: transform insertion attempt.
            algo = self.kg_repo.get_algorithm(task.algorithm_id)
            expected_type = (algo.input_types[0] if algo and algo.input_types else task.input.data_type_id)
            transform_path = self.kg_repo.find_transform_path(task.input.data_type_id, expected_type, max_depth=3)
            if transform_path:
                task.input.data_type_id = expected_type
                try:
                    last_output = self._execute_algorithm(task.algorithm_id, context)
                    attempt_no += 1
                    repair_records.append(
                        RepairRecord(
                            attempt_no=attempt_no,
                            strategy="transform_insert",
                            step=task.step,
                            message=f"Recovered with transform path: {' -> '.join(transform_path)}",
                            success=True,
                            timestamp=_utc_now(),
                            reason_code="transform_insert_succeeded",
                            from_algorithm=task.algorithm_id,
                        )
                    )
                    continue
                except Exception as transform_error:  # noqa: BLE001
                    attempt_no += 1
                    repair_records.append(
                        RepairRecord(
                            attempt_no=attempt_no,
                            strategy="transform_insert",
                            step=task.step,
                            message=f"Transform path inserted but execution still failed: {transform_error}",
                            success=False,
                            timestamp=_utc_now(),
                            reason_code="transform_insert_failed",
                            from_algorithm=task.algorithm_id,
                        )
                    )
            else:
                attempt_no += 1
                repair_records.append(
                    RepairRecord(
                        attempt_no=attempt_no,
                        strategy="transform_insert",
                        step=task.step,
                        message="No transform path found.",
                        success=False,
                        timestamp=_utc_now(),
                        reason_code="transform_path_missing",
                        from_algorithm=task.algorithm_id,
                    )
                )

            # If still not recoverable after strategies, fail this run.
            raise RuntimeError(f"Task failed after healing strategies: step={task.step}, algo={task.algorithm_id}")

        if last_output is None:
            raise RuntimeError("Workflow finished without producing any output artifact.")
        return last_output

    def _execute_algorithm(self, algorithm_id: str, context: ExecutionContext) -> Path:
        handler = self.algorithm_handlers.get(algorithm_id)
        if handler is None:
            raise ValueError(f"No handler registered for algorithm: {algorithm_id}")
        return handler(context)

    @staticmethod
    def _handle_building(context: ExecutionContext) -> Path:
        from adapters.building_adapter import run_building_fusion

        return run_building_fusion(
            osm_shp=context.osm_shp,
            ref_shp=context.ref_shp,
            output_dir=context.output_dir,
            target_crs=context.target_crs,
            field_mapping=context.field_mapping,
            debug=context.debug,
            parameters=dict(context.step_parameters or {}),
        )

    @staticmethod
    def _handle_road(context: ExecutionContext) -> Path:
        from adapters.road_adapter import run_road_fusion

        return run_road_fusion(
            osm_shp=context.osm_shp,
            ref_shp=context.ref_shp,
            output_dir=context.output_dir,
            target_crs=context.target_crs,
            field_mapping=context.field_mapping,
            debug=context.debug,
            parameters=dict(context.step_parameters or {}),
        )
