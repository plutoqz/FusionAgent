from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from agent.tooling import ToolRegistry, build_default_tool_registry
from kg.repository import KGRepository
from schemas.agent import RepairRecord, WorkflowPlan, WorkflowTask
from schemas.fusion import JobType
from services.runtime_contract_service import RuntimeContractService


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
    named_vectors: Dict[str, Path] = field(default_factory=dict)
    named_rasters: Dict[str, Path] = field(default_factory=dict)
    context_vectors: Dict[str, Path] = field(default_factory=dict)
    intermediate_artifacts: Dict[str, Path] = field(default_factory=dict)
    # Bound at execution time for the currently active step.
    active_step: Optional[int] = None
    step_parameters: Dict[str, Any] = field(default_factory=dict)


class WorkflowExecutor:
    def __init__(
        self,
        kg_repo: KGRepository,
        planner: Optional[object] = None,
        algorithm_handlers: Optional[Dict[str, Callable[[ExecutionContext], Path]]] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ) -> None:
        self.kg_repo = kg_repo
        self.planner = planner
        self.algorithm_handlers = dict(algorithm_handlers or {})
        self.tool_registry = tool_registry or build_default_tool_registry()
        self.runtime_contract = RuntimeContractService(self.kg_repo, tool_registry=self.tool_registry)

    def execute_plan(
        self,
        plan: WorkflowPlan,
        context: ExecutionContext,
        repair_records: List[RepairRecord],
        on_step_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Path:
        last_output: Optional[Path] = None
        attempt_no = len(repair_records)

        for task in sorted(plan.tasks, key=lambda t: t.step):
            if task.is_transform or task.algorithm_id.startswith("algo.transform."):
                continue

            step_output: Optional[Path] = None
            failure_error_summary: Optional[str] = None

            # Bind the step-scoped parameters so handlers/adapters can consume them.
            context.active_step = task.step
            context.step_parameters = dict(task.input.parameters or {})
            self._emit_step_event(on_step_event, task=task, status="started")

            try:
                step_output = self._execute_algorithm(task.algorithm_id, context)
                last_output = step_output
                context.intermediate_artifacts[f"step:{task.step}"] = step_output
                context.intermediate_artifacts[f"algorithm:{task.algorithm_id}"] = step_output
                self._emit_step_event(on_step_event, task=task, status="succeeded", output_path=step_output)
                continue
            except Exception as first_error:  # noqa: BLE001
                attempt_no += 1
                failure_error_summary = self._summarize_error(first_error)
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
            candidate_alt_algos = [*task.alternatives]
            if not candidate_alt_algos:
                candidate_alt_algos = [a.algo_id for a in self.kg_repo.get_alternative_algorithms(task.algorithm_id, limit=3)]
            alt_filter = self.runtime_contract.filter_algorithm_ids(candidate_alt_algos, surface="executor_healing")
            alt_algos = alt_filter.allowed_ids
            candidate_actions = [{"algorithm_id": item} for item in dict.fromkeys(candidate_alt_algos)]
            skipped_actions = alt_filter.skipped
            if candidate_alt_algos and not alt_algos:
                attempt_no += 1
                repair_records.append(
                    RepairRecord(
                        attempt_no=attempt_no,
                        strategy="alternative_algorithm",
                        step=task.step,
                        message="All alternative algorithms were rejected by runtime contract.",
                        success=False,
                        timestamp=_utc_now(),
                        reason_code="alternative_algorithm_contract_rejected",
                        from_algorithm=task.algorithm_id,
                        policy_source="runtime_contract",
                        policy_decision_basis={"surface": "executor_healing"},
                        candidate_actions=candidate_actions,
                        skipped_actions=skipped_actions,
                    )
                )
            for alt_algo in alt_algos:
                try:
                    step_output = self._execute_algorithm(alt_algo, context)
                    last_output = step_output
                    context.intermediate_artifacts[f"step:{task.step}"] = step_output
                    context.intermediate_artifacts[f"algorithm:{alt_algo}"] = step_output
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
                            policy_source="runtime_contract",
                            policy_decision_basis={"surface": "executor_healing"},
                            candidate_actions=candidate_actions,
                            selected_action={"algorithm_id": alt_algo},
                            skipped_actions=skipped_actions,
                        )
                    )
                    self._emit_step_event(
                        on_step_event,
                        task=task,
                        status="succeeded",
                        effective_algorithm_id=alt_algo,
                        output_path=step_output,
                    )
                    break
                except Exception as alt_error:  # noqa: BLE001
                    attempt_no += 1
                    failure_error_summary = self._summarize_error(alt_error)
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
                            policy_source="runtime_contract",
                            policy_decision_basis={"surface": "executor_healing"},
                            candidate_actions=candidate_actions,
                            selected_action={"algorithm_id": alt_algo},
                            skipped_actions=skipped_actions,
                        )
                    )
            if step_output is not None:
                continue

            # Strategy 3: transform insertion attempt.
            algo = self.kg_repo.get_algorithm(task.algorithm_id)
            expected_type = (algo.input_types[0] if algo and algo.input_types else task.input.data_type_id)
            transform_path = self.kg_repo.find_transform_path(task.input.data_type_id, expected_type, max_depth=3)
            if transform_path:
                task.input.data_type_id = expected_type
                try:
                    step_output = self._execute_algorithm(task.algorithm_id, context)
                    last_output = step_output
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
                    self._emit_step_event(on_step_event, task=task, status="succeeded")
                    continue
                except Exception as transform_error:  # noqa: BLE001
                    attempt_no += 1
                    failure_error_summary = self._summarize_error(transform_error)
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
                if failure_error_summary is None:
                    failure_error_summary = "RuntimeError: No transform path found."

            # If still not recoverable after strategies, fail this run.
            self._emit_step_event(
                on_step_event,
                task=task,
                status="failed",
                error=failure_error_summary or "RuntimeError: Step failed during execution.",
            )
            raise RuntimeError(f"Task failed after healing strategies: step={task.step}, algo={task.algorithm_id}")

        if last_output is None:
            raise RuntimeError("Workflow finished without producing any output artifact.")
        return last_output

    def _execute_algorithm(self, algorithm_id: str, context: ExecutionContext) -> Path:
        decision = self.runtime_contract.evaluate_algorithm(algorithm_id, surface="executor")
        if not decision.allowed:
            raise ValueError(f"{decision.reason_code}: {decision.message}")
        spec = self.tool_registry.require(algorithm_id)
        handler = self.algorithm_handlers.get(algorithm_id)
        if handler is None:
            handler = getattr(self, spec.handler_name, None)
        if handler is None:
            raise ValueError(f"No handler registered for algorithm: {algorithm_id}")
        return handler(context)

    @staticmethod
    def _emit_step_event(
        on_step_event: Optional[Callable[[Dict[str, Any]], None]],
        *,
        task: WorkflowTask,
        status: str,
        effective_algorithm_id: Optional[str] = None,
        error: Optional[str] = None,
        output_path: Optional[Path] = None,
    ) -> None:
        if on_step_event is None:
            return
        payload: Dict[str, Any] = {
            "status": status,
            "step": task.step,
            "algorithm_id": task.algorithm_id,
            "data_source_id": task.input.data_source_id,
        }
        if effective_algorithm_id and effective_algorithm_id != task.algorithm_id:
            payload["effective_algorithm_id"] = effective_algorithm_id
        if error:
            payload["error"] = error
        if output_path is not None:
            payload["output_path"] = str(output_path)
        on_step_event(payload)

    @staticmethod
    def _summarize_error(error: Exception) -> str:
        return f"{type(error).__name__}: {error}"

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
    def _handle_building_safe(context: ExecutionContext) -> Path:
        from adapters.building_adapter import run_building_fusion_safe

        return run_building_fusion_safe(
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

    @staticmethod
    def _handle_water(context: ExecutionContext) -> Path:
        from adapters.water_adapter import run_water_fusion

        return run_water_fusion(
            osm_shp=context.osm_shp,
            ref_shp=context.ref_shp,
            output_dir=context.output_dir,
            target_crs=context.target_crs,
            field_mapping=context.field_mapping,
            debug=context.debug,
            parameters=dict(context.step_parameters or {}),
        )

    @staticmethod
    def _handle_poi(context: ExecutionContext) -> Path:
        from adapters.poi_adapter import run_poi_fusion

        return run_poi_fusion(
            osm_shp=context.osm_shp,
            ref_shp=context.ref_shp,
            output_dir=context.output_dir,
            target_crs=context.target_crs,
            field_mapping=context.field_mapping,
            debug=context.debug,
            parameters=dict(context.step_parameters or {}),
        )

    @staticmethod
    def _handle_reserved_trajectory_pretransform(context: ExecutionContext) -> Path:
        raise RuntimeError(
            "Trajectory-to-road pretransform is a reserved seam in Phase 4 and is not executable at runtime."
        )

    @staticmethod
    def _handle_building_source_normalize(context: ExecutionContext) -> Path:
        from adapters.fusioncode_building_adapter import run_building_source_normalize

        return run_building_source_normalize(context)

    @staticmethod
    def _handle_building_obm_attributes(context: ExecutionContext) -> Path:
        from adapters.fusioncode_building_adapter import run_passthrough_latest_vector

        return run_passthrough_latest_vector(context, "building_obm_attributes")

    @staticmethod
    def _handle_building_presence_raster(context: ExecutionContext) -> Path:
        from adapters.fusioncode_building_adapter import run_building_presence_raster

        return run_building_presence_raster(context)

    @staticmethod
    def _handle_building_v8_candidate_graph(context: ExecutionContext) -> Path:
        from adapters.fusioncode_building_adapter import run_building_v8_candidate_graph

        return run_building_v8_candidate_graph(context)

    @staticmethod
    def _handle_building_v8_component_solver(context: ExecutionContext) -> Path:
        from adapters.fusioncode_building_adapter import run_passthrough_latest_vector

        return run_passthrough_latest_vector(context, "building_v8_component_solver")

    @staticmethod
    def _handle_building_cascade_fusion(context: ExecutionContext) -> Path:
        from adapters.fusioncode_building_adapter import run_building_multi_source_decomposed

        return run_building_multi_source_decomposed(context)

    @staticmethod
    def _handle_building_residual_priority(context: ExecutionContext) -> Path:
        from adapters.fusioncode_building_adapter import run_passthrough_latest_vector

        return run_passthrough_latest_vector(context, "building_residual_priority")

    @staticmethod
    def _handle_building_road_topology(context: ExecutionContext) -> Path:
        from adapters.fusioncode_building_adapter import run_building_road_topology

        return run_building_road_topology(context)

    @staticmethod
    def _handle_building_conflict_graph(context: ExecutionContext) -> Path:
        from adapters.fusioncode_building_adapter import run_building_conflict_graph

        return run_building_conflict_graph(context)

    @staticmethod
    def _handle_building_post_conflict_shrink(context: ExecutionContext) -> Path:
        from adapters.fusioncode_building_adapter import run_building_post_conflict_shrink

        return run_building_post_conflict_shrink(context)

    @staticmethod
    def _handle_building_road_tail(context: ExecutionContext) -> Path:
        from adapters.fusioncode_building_adapter import run_building_road_tail

        return run_building_road_tail(context)

    @staticmethod
    def _handle_building_height_from_raster(context: ExecutionContext) -> Path:
        from adapters.fusioncode_building_adapter import run_building_height_from_raster

        return run_building_height_from_raster(context)

    @staticmethod
    def _handle_building_quality_metrics(context: ExecutionContext) -> Path:
        from adapters.fusioncode_building_adapter import run_building_quality_metrics

        return run_building_quality_metrics(context)

    @staticmethod
    def _handle_building_multi_source_decomposed(context: ExecutionContext) -> Path:
        from adapters.fusioncode_building_adapter import run_building_multi_source_decomposed

        return run_building_multi_source_decomposed(context)

    @staticmethod
    def _handle_road_conflation_v7(context: ExecutionContext) -> Path:
        from adapters.fusioncode_linear_adapter import run_road_conflation_v7

        return run_road_conflation_v7(context)

    @staticmethod
    def _handle_waterways_conflation_v7(context: ExecutionContext) -> Path:
        from adapters.fusioncode_linear_adapter import run_waterways_conflation_v7

        return run_waterways_conflation_v7(context)

    @staticmethod
    def _handle_road_segment_match_topology(context: ExecutionContext) -> Path:
        from adapters.fusioncode_linear_adapter import run_road_segment_topology

        return run_road_segment_topology(context)

    @staticmethod
    def _handle_water_line_three_source(context: ExecutionContext) -> Path:
        from adapters.fusioncode_linear_adapter import run_water_line_three_source

        return run_water_line_three_source(context)

    @staticmethod
    def _handle_water_polygon_priority_merge(context: ExecutionContext) -> Path:
        from adapters.fusioncode_polygon_adapter import run_water_polygon_priority_merge

        return run_water_polygon_priority_merge(context)

    @staticmethod
    def _handle_poi_geohash_neighbor_match(context: ExecutionContext) -> Path:
        from adapters.fusioncode_poi_adapter import run_poi_geohash_neighbor_match

        return run_poi_geohash_neighbor_match(context)

    @staticmethod
    def _handle_spatial_conflicts(context: ExecutionContext) -> Path:
        from adapters.fusioncode_building_adapter import run_building_quality_metrics

        return run_building_quality_metrics(context)
