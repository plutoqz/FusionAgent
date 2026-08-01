from __future__ import annotations

import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from datetime import timedelta
from pathlib import Path
from threading import Lock
from typing import Any

from kg.knowledge_release import KnowledgeReleaseError
from kg.policy_registry import KnowledgePolicyRegistry, default_policy_registry
from kg.repository import KGRepository
from kg.seed_provider import load_seed_data
from schemas.agent import RunCreateRequest, RunInputStrategy, RunPhase, RunTrigger, RunTriggerType
from schemas.failure_taxonomy import classify_failure_category
from schemas.fusion import JobType
from schemas.scenario import ScenarioChildRunSpec, ScenarioPhase, ScenarioRunRequest, ScenarioRunResponse
from schemas.scenario_checkpoint import (
    ScenarioCheckpoint,
    ScenarioCheckpointChildRun,
    ScenarioCheckpointChildSpec,
)
from schemas.task_kind import TaskKind, task_kind_family
from services.agent_run_service import AgentRunService, agent_run_service
from services.artifact_evaluation_service import evaluate_agentic_run, evaluate_vector_artifact
from services.evidence_lifecycle_service import build_scenario_evidence_manifest
from services.kg_path_trace_service import build_kg_path_trace
from services.mission_compiler_service import compile_scenario_mission
from services.run_recovery_service import build_recovery_hint
from services.scenario_checkpoint_service import checkpoint_path, load_scenario_checkpoint, write_scenario_checkpoint
from services.scenario_failure_handler_service import ScenarioFailureHandlerService
from services.scenario_output import resolve_scenario_output_root
from services.scenario_registry_service import ScenarioRegistryService
from services.scenario_report_service import render_scenario_reports
from services.workflow_trace_service import build_workflow_trace


TERMINAL_CHILD_PHASES = {
    RunPhase.succeeded.value,
    RunPhase.failed.value,
    ScenarioPhase.failed.value,
    ScenarioPhase.partial_provisional.value,
    ScenarioPhase.source_retrying.value,
    ScenarioPhase.awaiting_external_config.value,
    ScenarioPhase.full_rerun_queued.value,
    ScenarioPhase.superseded.value,
    ScenarioPhase.retry_exhausted.value,
    "skipped",
    "cancelled",
}

SCENARIO_SOURCE_RETRY_STATUS = "source_retrying"


def create_scenario_id() -> str:
    return f"scenario_{uuid.uuid4().hex}"


def scenario_output_dir(request: ScenarioRunRequest, scenario_id: str) -> Path:
    return resolve_scenario_output_root(request.output_root) / scenario_id


def _validate_scenario_child_run_root(agent_service: Any, request: ScenarioRunRequest) -> None:
    expected_runs_root = _expected_child_runs_root_for_scenario_output_root(
        resolve_scenario_output_root(request.output_root)
    )
    if expected_runs_root is None:
        return
    actual_runs_root = getattr(agent_service, "base_dir", None)
    if actual_runs_root is None:
        return
    actual = Path(actual_runs_root).expanduser().resolve()
    expected = expected_runs_root.expanduser().resolve()
    if actual == expected:
        return
    raise ValueError(
        "SCENARIO_RUNTIME_ROOT_MISMATCH: explicit scenario output root "
        f"{resolve_scenario_output_root(request.output_root)} requires child runs root {expected}, "
        f"but the active AgentRunService base_dir is {actual}. Restart the runtime with "
        f"GEOFUSION_RUNS_ROOT={expected} or use a scenario output root that matches the active runtime."
    )


def _expected_child_runs_root_for_scenario_output_root(output_root: Path) -> Path | None:
    root = Path(output_root)
    if root.name == "scenario_outputs":
        return root.parent / "runs"
    return None


def build_child_run_specs(
    request: ScenarioRunRequest,
    *,
    kg_repo: KGRepository | None = None,
    policy_registry: KnowledgePolicyRegistry | None = None,
) -> list[ScenarioChildRunSpec]:
    registry = policy_registry or default_policy_registry()
    mission = compile_scenario_mission(request, policy_registry=registry)
    contracts = _product_contracts_by_id(kg_repo)
    governance = {
        task.task_kind: _delivery_governance_for_task(
            task.task_kind,
            contracts=contracts,
            policy_registry=registry,
        )
        for task in mission.child_tasks
    }
    return [
        ScenarioChildRunSpec(
            job_type=task.job_type,
            trigger_content=task.trigger_content,
            disaster_type=task.disaster_type,
            spatial_extent=task.spatial_extent,
            force_aoi_resolution=task.force_aoi_resolution,
            target_crs=task.target_crs,
            debug=task.debug,
            task_kind=task.task_kind,
            task_family=task.task_family,
            preferred_pattern_id=task.preferred_pattern_id,
            output_data_type=task.output_data_type,
            product_contract_id=governance[task.task_kind]["product_contract_id"],
            provisional_when_degraded=governance[task.task_kind]["provisional_delivery_allowed"],
            final_output_may_supersede_provisional=governance[task.task_kind][
                "final_output_may_supersede_provisional"
            ],
        )
        for task in mission.child_tasks
    ]


def _product_contracts_by_id(kg_repo: KGRepository | None) -> dict[str, Any]:
    if kg_repo is not None:
        return {contract.contract_id: contract for contract in kg_repo.get_product_contracts(None)}
    return dict(load_seed_data()["product_contracts"])


def _delivery_governance_for_task(
    task_kind: TaskKind,
    *,
    contracts: dict[str, Any],
    policy_registry: KnowledgePolicyRegistry,
) -> dict[str, Any]:
    if _p3_variant() == "no_product_contract":
        return {
            "product_contract_id": None,
            "provisional_delivery_allowed": False,
            "final_output_may_supersede_provisional": False,
        }
    output_contract = policy_registry.output_contract(task_kind.value)
    contract_id = str(output_contract.get("product_contract_id") or "").strip()
    contract = contracts.get(contract_id)
    if contract is None:
        raise KnowledgeReleaseError(
            f"Product contract {contract_id or '<missing>'} for task {task_kind.value} is absent from the KG backend"
        )
    degradation_policy = getattr(contract, "degradation_policy", None)
    if not isinstance(degradation_policy, dict):
        raise KnowledgeReleaseError(f"Product contract {contract_id} has no degradation_policy")
    governance: dict[str, Any] = {"product_contract_id": contract_id}
    for field in ("provisional_delivery_allowed", "final_output_may_supersede_provisional"):
        value = degradation_policy.get(field)
        if not isinstance(value, bool):
            raise KnowledgeReleaseError(f"Product contract {contract_id} must declare boolean {field}")
        governance[field] = value
    return governance


def validate_mission_child_specs(
    request: ScenarioRunRequest,
    child_specs: list[ScenarioChildRunSpec],
    *,
    policy_registry: KnowledgePolicyRegistry | None = None,
) -> None:
    registry = policy_registry or default_policy_registry()
    mission = compile_scenario_mission(request, policy_registry=registry)
    expected_count = len(mission.child_tasks)
    actual_count = len(child_specs)
    if actual_count < expected_count:
        raise ValueError(
            "MISSION_CHILD_MISSING: scenario mission expected "
            f"{expected_count} child tasks, got {actual_count}"
        )
    if actual_count > expected_count:
        raise ValueError(
            "MISSION_CHILD_EXTRA: scenario mission expected "
            f"{expected_count} child tasks, got {actual_count}"
        )

    expected_task_ids = [
        _task_id_for_kind(task.task_kind, registry=registry)
        for task in mission.child_tasks
    ]
    actual_task_ids: list[str] = []
    for index, spec in enumerate(child_specs):
        if spec.task_kind is None:
            raise ValueError(
                f"MISSION_CHILD_TASK_ID_MISSING: child spec at index {index} has no task_kind"
            )
        actual_task_ids.append(_task_id_for_kind(spec.task_kind, registry=registry))

    duplicate_task_ids = sorted(
        task_id for task_id in set(actual_task_ids) if actual_task_ids.count(task_id) > 1
    )
    if duplicate_task_ids:
        raise ValueError(
            "MISSION_CHILD_DUPLICATE: duplicate child task IDs: "
            + ", ".join(duplicate_task_ids)
        )

    if actual_task_ids != expected_task_ids:
        if sorted(actual_task_ids) == sorted(expected_task_ids):
            raise ValueError(
                "MISSION_CHILD_ORDER_MISMATCH: expected task ID order "
                f"{expected_task_ids}, got {actual_task_ids}"
            )
        raise ValueError(
            "MISSION_CHILD_TASK_MISMATCH: expected task IDs "
            f"{expected_task_ids}, got {actual_task_ids}"
        )

    content_fields = (
        "job_type",
        "trigger_content",
        "disaster_type",
        "spatial_extent",
        "force_aoi_resolution",
        "target_crs",
        "debug",
        "task_family",
        "preferred_pattern_id",
        "output_data_type",
    )
    for index, (expected, actual) in enumerate(zip(mission.child_tasks, child_specs)):
        mismatches = [
            field
            for field in content_fields
            if getattr(actual, field) != getattr(expected, field)
        ]
        if mismatches:
            raise ValueError(
                "MISSION_CHILD_CONTENT_MISMATCH: child spec at index "
                f"{index} ({expected_task_ids[index]}) differs in fields {mismatches}"
            )


def _task_id_for_kind(
    task_kind: TaskKind,
    *,
    registry: KnowledgePolicyRegistry,
) -> str:
    task_id = str(registry.task_record(task_kind.value).get("task_id") or "").strip()
    if not task_id:
        raise KnowledgeReleaseError(f"KG task semantics for {task_kind.value} has no task_id")
    return task_id


def classify_scenario_request(
    *,
    scenario_name: str,
    trigger_content: str,
    job_types: list[JobType],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    combined_text = " ".join(
        part.strip().lower()
        for part in [scenario_name, trigger_content]
        if str(part or "").strip()
    )
    unsupported_layers = [
        str(item).strip().lower()
        for item in ((metadata or {}).get("unsupported_requested_layers") or [])
        if str(item).strip()
    ]
    if unsupported_layers:
        return {
            "decision": "clarify",
            "reason_code": "UNSUPPORTED_TASK_BUNDLE",
            "message": (
                "Scenario request includes unsupported layers: "
                + ", ".join(unsupported_layers)
                + ". Supported bounded layers are building, road, water, and bounded poi."
            ),
        }

    if any(
        keyword in combined_text
        for keyword in (
            "trajectory",
            "gps trajectory",
            "gps trace",
            "轨迹",
            "轨迹到道路",
        )
    ):
        return {
            "decision": "reject",
            "reason_code": "RESERVATION_ONLY_TRAJECTORY_TO_ROAD",
            "message": "Trajectory-to-road is reserved metadata only and is not an executable runtime path.",
        }

    if any(
        keyword in combined_text
        for keyword in (
            "entity resolution",
            "entity alignment",
            "all poi businesses",
            "global entity",
            "通用实体对齐",
        )
    ):
        return {
            "decision": "clarify",
            "reason_code": "unsupported_unbounded_poi_entity_alignment",
            "message": "POI fusion is bounded and does not support open-ended entity alignment.",
        }

    if any(
        keyword in combined_text
        for keyword in (
            "event-feed",
            "event feed",
            "telemetry replay",
            "live telemetry",
            "real-time feed",
            "streaming telemetry",
            "digital twin",
        )
    ):
        return {
            "decision": "reject",
            "reason_code": "UNSUPPORTED_EVENT_FEED_EXPECTATION",
            "message": "Scenario layer is bounded orchestration, not live event-feed or digital twin simulation.",
        }

    if any(
        keyword in combined_text
        for keyword in (
            "dependency reasoning",
            "cross-domain dependency",
            "cascading dependency",
            "upstream dependency",
            "downstream dependency",
        )
    ):
        return {
            "decision": "clarify",
            "reason_code": "UNSUPPORTED_DEPENDENCY_REASONING",
            "message": "Scenario dependency reasoning must stay within documented bounded task bundles.",
        }

    if any(
        keyword in combined_text
        for keyword in (
            "traffic telemetry",
            "digital twin outputs",
            "gdp",
            "population heatmap",
        )
    ):
        return {
            "decision": "reject",
            "reason_code": "UNSUPPORTED_TASK_BUNDLE",
            "message": "Scenario request exceeds the bounded building, road, water, and poi orchestration scope.",
        }

    return {
        "decision": "allow",
        "reason_code": "SUPPORTED_BOUNDED_SCENARIO",
        "message": "Scenario request stays within the bounded orchestration scope.",
        "job_types": list(dict.fromkeys(job_type.value for job_type in job_types)),
    }


class ScenarioRunService:
    TERMINAL_RUN_PHASES = TERMINAL_CHILD_PHASES
    CHILD_RUN_POLL_INTERVAL_SECONDS = 1.0
    CHILD_RUN_TERMINAL_WAIT_SECONDS = 900.0

    def __init__(self, *, agent_run_service: AgentRunService) -> None:
        self.agent_run_service = agent_run_service
        self.failure_handler = ScenarioFailureHandlerService()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scenario-run")

    def _build_child_run_specs(self, request: ScenarioRunRequest) -> list[ScenarioChildRunSpec]:
        repo = getattr(self.agent_run_service, "kg_repo", None)
        return build_child_run_specs(request, kg_repo=repo)

    def create_scenario_run(self, request: ScenarioRunRequest) -> ScenarioRunResponse:
        child_specs = self._build_child_run_specs(request)
        validate_mission_child_specs(request, child_specs)
        scenario_id = create_scenario_id()
        output_dir = scenario_output_dir(request, scenario_id)
        _validate_scenario_child_run_root(self.agent_run_service, request)
        return self._execute_scenario_run(request=request, scenario_id=scenario_id, output_dir=output_dir)

    def submit_scenario_run(self, request: ScenarioRunRequest) -> ScenarioRunResponse:
        decision = classify_scenario_request(
            scenario_name=request.scenario_name,
            trigger_content=request.trigger_content,
            job_types=request.job_types,
            metadata=request.metadata,
        )
        if decision["decision"] != "allow":
            raise ValueError(f'{decision["reason_code"]}: {decision["message"]}')
        child_specs = self._build_child_run_specs(request)
        validate_mission_child_specs(request, child_specs)

        scenario_id = create_scenario_id()
        output_dir = scenario_output_dir(request, scenario_id)
        _validate_scenario_child_run_root(self.agent_run_service, request)
        output_dir.mkdir(parents=True, exist_ok=True)
        _write_json_roundtrip(output_dir / "request.json", request.model_dump(mode="json"))
        _write_runtime_snapshot(output_dir)
        _write_preflight_snapshot(output_dir, request, child_specs=child_specs)
        _write_checkpoint(
            output_dir,
            _initial_checkpoint(
                request=request,
                scenario_id=scenario_id,
                phase=ScenarioPhase.running,
            ),
        )
        summary = {
            "scenario_id": scenario_id,
            "scenario_name": request.scenario_name,
            "trigger_content": request.trigger_content,
            "disaster_type": request.disaster_type,
            "phase": ScenarioPhase.running.value,
            "output_dir": str(output_dir),
            "child_runs": [],
            "kg_path_traces": [],
            "workflow_traces": [],
            "source_coverage": [],
            "source_acquisition_jobs": [],
            "rerun_status": {"state": "not_required"},
            "evaluation": {"agentic_metrics": {"manual_intervention_count": 0}, "data_fusion_metrics": []},
            "manual_interventions": 0,
            "final_outputs": [],
            "document_paths": {},
        }
        self._write_summary_files(output_dir, summary)
        ScenarioRegistryService(output_root=resolve_scenario_output_root(request.output_root)).record(
            {
                "scenario_id": scenario_id,
                "scenario_name": request.scenario_name,
                "phase": ScenarioPhase.running.value,
                "output_dir": str(output_dir),
                "child_run_ids": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "case_id": request.metadata.get("case_id"),
                "idempotency_key": request.metadata.get("idempotency_key"),
                "trigger_event": request.metadata.get("trigger_event"),
            }
        )
        future = self._executor.submit(
            self._execute_scenario_run,
            request=request,
            scenario_id=scenario_id,
            output_dir=output_dir,
        )
        future.add_done_callback(
            lambda completed: self._record_background_failure(
                completed,
                request=request,
                scenario_id=scenario_id,
                output_dir=output_dir,
            )
        )
        return ScenarioRunResponse(
            scenario_id=scenario_id,
            phase=ScenarioPhase.running,
            output_dir=str(output_dir),
            child_run_ids=[],
        )

    def _record_background_failure(
        self,
        future,
        *,
        request: ScenarioRunRequest,
        scenario_id: str,
        output_dir: Path,
    ) -> None:
        try:
            future.result()
            return
        except Exception as exc:  # noqa: BLE001
            error = f"SCENARIO_BACKGROUND_ERROR: {type(exc).__name__}: {exc}"

        try:
            checkpoint = load_scenario_checkpoint(checkpoint_path(output_dir))
        except Exception:  # noqa: BLE001
            checkpoint = _initial_checkpoint(request=request, scenario_id=scenario_id, phase=ScenarioPhase.running)

        child_specs = _child_specs_from_checkpoint(checkpoint)
        child_results = _child_results_from_checkpoint(checkpoint, child_specs) if checkpoint.child_runs else []
        if not child_results:
            child_results = [_failed_child_run_for_spec(spec, error=error) for spec in child_specs]
        child_results = [_terminalize_background_child_result(result, error=error) for result in child_results]
        phase = _phase_from_child_results(child_results)
        summary = self._build_summary(request, scenario_id, output_dir, child_results)
        summary["phase"] = phase.value
        summary["terminal_error"] = {
            "code": "SCENARIO_BACKGROUND_ERROR",
            "message": error,
            "next_action": "Inspect workflow_trace.json, failed_children.json, and child run logs.",
        }
        self._write_summary_files(output_dir, summary)
        _write_checkpoint(
            output_dir,
            _checkpoint_with_child_runs(checkpoint, child_results, phase=phase, children_phase=phase),
        )

    def resume_scenario_run(self, scenario_id: str, *, retry_failed: bool = False) -> ScenarioRunResponse:
        request, output_dir, checkpoint = _load_resume_checkpoint(scenario_id)
        if checkpoint.scenario_id != scenario_id:
            raise ValueError(f"Checkpoint scenario_id mismatch for {scenario_id}")

        child_specs = _child_specs_from_checkpoint(checkpoint)
        if not child_specs:
            child_specs = self._build_child_run_specs(request)

        child_results = _child_results_from_checkpoint(checkpoint, child_specs)
        previous_child_results = [dict(result) for result in child_results]
        while len(child_results) < len(child_specs):
            child_results.append(_queued_child_run_for_spec(child_specs[len(child_results)]))

        checkpoint = checkpoint.model_copy(
            update={
                "phase": ScenarioPhase.running,
                "children_phase": _phase_from_child_results(child_results),
                "request": request.model_dump(mode="json"),
                "child_specs": [_checkpoint_child_spec(spec) for spec in child_specs],
                "child_runs": [_checkpoint_child_run(result) for result in child_results],
                "resume_count": checkpoint.resume_count + 1,
            }
        )
        _write_checkpoint(output_dir, checkpoint)

        launch_indexes: list[int] = []
        launch_specs: list[ScenarioChildRunSpec] = []
        for index, (spec, result) in enumerate(zip(child_specs, child_results)):
            if _resume_result_is_completed_with_artifact(result):
                continue
            if _resume_result_is_failed(result) and not retry_failed:
                continue
            if _resume_result_should_launch(result, retry_failed=retry_failed):
                launch_indexes.append(index)
                launch_specs.append(spec)
                child_results[index] = _queued_child_run_for_spec(spec)
                continue
            if result.get("run_id"):
                child_results[index] = self._wait_for_child_result(run_id=str(result["run_id"]), spec=spec)

        checkpoint = _checkpoint_with_child_runs(
            checkpoint,
            child_results,
            phase=ScenarioPhase.running,
            children_phase=_phase_from_child_results(child_results),
        )
        _write_checkpoint(output_dir, checkpoint)

        def record_launched_child_result(launch_position: int, result: dict[str, Any]) -> None:
            nonlocal checkpoint
            child_results[launch_indexes[launch_position]] = result
            checkpoint = _checkpoint_with_child_runs(
                checkpoint,
                child_results,
                phase=ScenarioPhase.running,
                children_phase=_phase_from_child_results(child_results),
            )
            _write_checkpoint(output_dir, checkpoint)

        if launch_specs:
            launched_results = self._start_child_runs(
                output_dir,
                launch_specs,
                on_child_result=record_launched_child_result,
            )
            launched_results = self._wait_for_started_child_results(launched_results)
            launched_results = self._mark_nonterminal_children_timed_out(launched_results)
            for index, result in zip(launch_indexes, launched_results):
                child_results[index] = result

        superseded_outputs = _superseded_outputs(previous_child_results, child_results)
        if superseded_outputs:
            for result in child_results:
                matching = next(
                    (
                        item
                        for item in superseded_outputs
                        if item.get("superseded_by") == result.get("run_id")
                    ),
                    None,
                )
                if matching is not None:
                    result.setdefault("supersedes", []).append(matching)

        child_results = self._mark_nonterminal_children_timed_out(child_results)
        checkpoint = _checkpoint_with_child_runs(
            checkpoint,
            child_results,
            phase=ScenarioPhase.running,
            children_phase=_phase_from_child_results(child_results),
        )
        _write_checkpoint(output_dir, checkpoint)
        return self._finalize_scenario_run(
            request=request,
            scenario_id=scenario_id,
            output_dir=output_dir,
            child_results=child_results,
            checkpoint=checkpoint,
        )

    def _execute_scenario_run(
        self,
        *,
        request: ScenarioRunRequest,
        scenario_id: str,
        output_dir: Path,
    ) -> ScenarioRunResponse:
        decision = classify_scenario_request(
            scenario_name=request.scenario_name,
            trigger_content=request.trigger_content,
            job_types=request.job_types,
            metadata=request.metadata,
        )
        if decision["decision"] != "allow":
            raise ValueError(f'{decision["reason_code"]}: {decision["message"]}')

        child_specs = self._build_child_run_specs(request)
        validate_mission_child_specs(request, child_specs)

        output_dir.mkdir(parents=True, exist_ok=True)
        _write_json_roundtrip(output_dir / "request.json", request.model_dump(mode="json"))
        _write_runtime_snapshot(output_dir)
        _write_preflight_snapshot(output_dir, request, child_specs=child_specs)
        checkpoint = _initial_checkpoint(
            request=request,
            scenario_id=scenario_id,
            phase=ScenarioPhase.running,
        )
        _write_checkpoint(output_dir, checkpoint)

        checkpoint = _checkpoint_with_specs(checkpoint, child_specs)
        _write_checkpoint(output_dir, checkpoint)
        child_run_slots = [_queued_child_run_for_spec(spec) for spec in child_specs]
        checkpoint = _checkpoint_with_child_runs(checkpoint, child_run_slots, phase=ScenarioPhase.running)
        _write_checkpoint(output_dir, checkpoint)
        checkpoint_lock = Lock()

        def record_child_result(index: int, result: dict[str, Any]) -> None:
            nonlocal checkpoint
            with checkpoint_lock:
                child_run_slots[index] = result
                checkpoint = _checkpoint_with_child_runs(
                    checkpoint,
                    child_run_slots,
                    phase=ScenarioPhase.running,
                    children_phase=_phase_from_child_results(child_run_slots),
                )
                _write_checkpoint(output_dir, checkpoint)

        started_child_results = self._start_child_runs(output_dir, child_specs, on_child_result=record_child_result)
        child_results = self._wait_for_started_child_results(started_child_results)
        child_results = self._mark_nonterminal_children_timed_out(child_results)
        checkpoint = _checkpoint_with_child_runs(
            checkpoint,
            child_results,
            phase=ScenarioPhase.running,
            children_phase=_phase_from_child_results(child_results),
        )
        _write_checkpoint(output_dir, checkpoint)
        return self._finalize_scenario_run(
            request=request,
            scenario_id=scenario_id,
            output_dir=output_dir,
            child_results=child_results,
            checkpoint=checkpoint,
        )

    def _start_child_runs(
        self,
        output_dir: Path,
        child_specs: list[ScenarioChildRunSpec],
        *,
        on_child_result=None,
    ) -> list[dict[str, Any]]:
        max_workers = _scenario_child_max_workers()
        if max_workers == 1:
            child_results = []
            for index, spec in enumerate(child_specs):
                result = self._run_child(output_dir, spec)
                child_results.append(result)
                if on_child_result is not None:
                    on_child_result(index, result)
            return child_results
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="scenario-child-run") as child_executor:
            runtimes = self._build_isolated_child_runtimes(len(child_specs))
            future_indexes = {
                child_executor.submit(self._run_child, output_dir, spec, runtime_dependencies=runtime): index
                for index, (spec, runtime) in enumerate(zip(child_specs, runtimes))
            }
            child_results: list[dict[str, Any] | None] = [None] * len(child_specs)
            for future in as_completed(future_indexes):
                index = future_indexes[future]
                result = future.result()
                child_results[index] = result
                if on_child_result is not None:
                    on_child_result(index, result)
            return [result for result in child_results if result is not None]

    def _build_isolated_child_runtimes(self, child_count: int) -> list[Any | None]:
        if getattr(self.agent_run_service, "dispatch_eager", True) is False:
            return [None] * child_count
        build_runtime = getattr(self.agent_run_service, "build_isolated_runtime_dependencies", None)
        if not callable(build_runtime):
            return [None] * child_count
        return [build_runtime() for _ in range(child_count)]

    def _run_child(
        self,
        output_dir: Path,
        spec: ScenarioChildRunSpec,
        *,
        runtime_dependencies: Any | None = None,
    ) -> dict[str, Any]:
        request = RunCreateRequest(
            job_type=spec.job_type,
            trigger=RunTrigger(
                type=RunTriggerType.user_query,
                content=spec.trigger_content,
                disaster_type=spec.disaster_type,
                spatial_extent=spec.spatial_extent,
                force_aoi_resolution=spec.force_aoi_resolution,
            ),
            target_crs=spec.target_crs,
            field_mapping={},
            debug=spec.debug,
            input_strategy=RunInputStrategy.task_driven_auto,
            preferred_pattern_id=spec.preferred_pattern_id,
        )
        try:
            create_run_kwargs = {
                "request": request,
                "osm_zip_name": None,
                "osm_zip_bytes": None,
                "ref_zip_name": None,
                "ref_zip_bytes": None,
            }
            if runtime_dependencies is not None:
                create_run_kwargs["runtime_dependencies"] = runtime_dependencies
            status = self.agent_run_service.create_run(**create_run_kwargs)
            return self._inspect_child_result(run_id=status.run_id, spec=spec, fallback_status=status)
        except Exception as exc:  # noqa: BLE001
            task_key, task_family = _task_identity(
                job_type=spec.job_type,
                task_kind=spec.task_kind,
                task_family=spec.task_family,
            )
            error_path = output_dir / "child_runs" / f"{task_key}-failed.json"
            error_path.parent.mkdir(parents=True, exist_ok=True)
            error_payload = {
                "job_type": spec.job_type.value,
                "task_kind": task_key,
                "task_family": task_family,
                "error": f"{type(exc).__name__}: {exc}",
            }
            error_path.write_text(json.dumps(error_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return {
                "run_id": None,
                "job_type": spec.job_type.value,
                "task_kind": task_key,
                "task_family": task_family,
                "phase": ScenarioPhase.failed.value,
                "error": error_payload["error"],
                "plan": None,
                "audit_events": [],
                "artifact_path": None,
                "product_contract_id": spec.product_contract_id,
                "provisional_when_degraded": spec.provisional_when_degraded,
                "final_output_may_supersede_provisional": spec.final_output_may_supersede_provisional,
            }

    def _inspect_child_result(self, *, run_id: str, spec: ScenarioChildRunSpec, fallback_status=None) -> dict[str, Any]:
        get_run = getattr(self.agent_run_service, "get_run", None)
        status = get_run(run_id) if callable(get_run) else fallback_status
        if status is None:
            status = fallback_status
        phase = status.phase.value if status is not None else ScenarioPhase.failed.value
        task_key, task_family = _task_identity(
            job_type=spec.job_type,
            task_kind=spec.task_kind,
            task_family=spec.task_family,
        )
        audit_events = self.agent_run_service.get_audit_events(run_id)
        result = {
            "run_id": run_id,
            "job_type": spec.job_type.value,
            "task_kind": task_key,
            "task_family": task_family,
            "phase": phase,
            "status": status,
            "plan": self.agent_run_service.get_plan(run_id),
            "audit_events": audit_events,
            "artifact_path": self.agent_run_service.get_artifact_path(run_id),
            "error": getattr(status, "error", None) if status is not None else None,
            "product_contract_id": spec.product_contract_id,
            "provisional_when_degraded": spec.provisional_when_degraded,
            "final_output_may_supersede_provisional": spec.final_output_may_supersede_provisional,
        }
        return _mark_child_result_provisional_if_degraded(
            result,
            allowed=spec.provisional_when_degraded,
        )

    def _wait_for_child_result(self, *, run_id: str, spec: ScenarioChildRunSpec, fallback_status=None) -> dict[str, Any]:
        deadline = time.monotonic() + self._child_run_terminal_wait_seconds()
        result = self._inspect_child_result(run_id=run_id, spec=spec, fallback_status=fallback_status)
        while result.get("phase") not in self.TERMINAL_RUN_PHASES and time.monotonic() < deadline:
            time.sleep(self._child_run_poll_interval_seconds())
            result = self._inspect_child_result(run_id=run_id, spec=spec, fallback_status=result.get("status"))
        return result

    def _refresh_started_child_result(self, result: dict[str, Any]) -> dict[str, Any]:
        run_id = result.get("run_id")
        if not run_id:
            return result
        try:
            job_type = JobType(str(result.get("job_type")))
        except ValueError:
            return result
        task_kind_value = result.get("task_kind")
        try:
            task_kind = TaskKind(str(task_kind_value)) if task_kind_value else None
        except ValueError:
            return result
        spec = ScenarioChildRunSpec(
            job_type=job_type,
            trigger_content="",
            task_kind=task_kind,
            task_family=str(result.get("task_family") or (task_kind_family(task_kind) if task_kind else job_type.value)),
            provisional_when_degraded=result.get("provisional_when_degraded") is True,
            product_contract_id=(
                str(result.get("product_contract_id")) if result.get("product_contract_id") else None
            ),
            final_output_may_supersede_provisional=bool(
                result.get("final_output_may_supersede_provisional")
            ),
        )
        return self._inspect_child_result(run_id=str(run_id), spec=spec, fallback_status=result.get("status"))

    def _wait_for_started_child_results(self, child_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deadline = time.monotonic() + self._child_run_terminal_wait_seconds()
        current_results = [self._refresh_started_child_result(result) for result in child_results]
        while (
            any(result.get("phase") not in self.TERMINAL_RUN_PHASES for result in current_results)
            and time.monotonic() < deadline
        ):
            time.sleep(self._child_run_poll_interval_seconds())
            current_results = [self._refresh_started_child_result(result) for result in current_results]
        return current_results

    def _mark_nonterminal_children_timed_out(self, child_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            result
            if str(result.get("phase")) in self.TERMINAL_RUN_PHASES
            else _timed_out_child_result(result, timeout_seconds=self._child_run_terminal_wait_seconds())
            for result in child_results
        ]

    def _child_run_poll_interval_seconds(self) -> float:
        return _float_env("GEOFUSION_SCENARIO_CHILD_POLL_INTERVAL_SECONDS", self.CHILD_RUN_POLL_INTERVAL_SECONDS)

    def _child_run_terminal_wait_seconds(self) -> float:
        return _float_env("GEOFUSION_SCENARIO_CHILD_TERMINAL_WAIT_SECONDS", self.CHILD_RUN_TERMINAL_WAIT_SECONDS)

    def _finalize_scenario_run(
        self,
        *,
        request: ScenarioRunRequest,
        scenario_id: str,
        output_dir: Path,
        child_results: list[dict[str, Any]],
        checkpoint: ScenarioCheckpoint,
    ) -> ScenarioRunResponse:
        phase = _phase_from_child_results(child_results)
        checkpoint = _checkpoint_with_child_runs(checkpoint, child_results, phase=phase, children_phase=phase)
        _write_checkpoint(output_dir, checkpoint)
        summary = self._build_summary(request, scenario_id, output_dir, child_results)
        document_paths = render_scenario_reports(summary=summary, documents_dir=output_dir / "documents")
        summary["document_paths"] = document_paths
        summary["phase"] = phase.value
        self._write_summary_files(output_dir, summary)
        child_run_ids = [str(result["run_id"]) for result in child_results if result.get("run_id")]
        ScenarioRegistryService(output_root=resolve_scenario_output_root(request.output_root)).record(
            {
                "scenario_id": scenario_id,
                "scenario_name": request.scenario_name,
                "phase": phase.value,
                "output_dir": str(output_dir),
                "child_run_ids": child_run_ids,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "case_id": request.metadata.get("case_id"),
                "idempotency_key": request.metadata.get("idempotency_key"),
                "trigger_event": request.metadata.get("trigger_event"),
            }
        )

        return ScenarioRunResponse(
            scenario_id=scenario_id,
            phase=phase,
            output_dir=str(output_dir),
            child_run_ids=child_run_ids,
        )

    def _build_summary(
        self,
        request: ScenarioRunRequest,
        scenario_id: str,
        output_dir: Path,
        child_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        mission = compile_scenario_mission(request)
        expected_child_count = _expected_child_count_for_request(request, mission_child_count=len(mission.child_tasks))
        kg_path_traces = [
            build_kg_path_trace(result["plan"])
            for result in child_results
            if result.get("plan") is not None
        ]
        workflow_traces = [
            build_workflow_trace(result.get("audit_events") or [])
            for result in child_results
        ]
        source_coverage = _source_coverage_from_children(child_results)
        source_acquisition_jobs = _source_acquisition_jobs_from_children(
            scenario_id=scenario_id,
            child_results=child_results,
        )
        data_fusion_metrics = [_data_fusion_metrics_for_child(result) for result in child_results]
        quality = _quality_summary_from_children(child_results)
        failed_children = [
            self.failure_handler.build_child_failure_record(
                scenario_id=scenario_id,
                child_result=result,
                recovery_hint=build_recovery_hint(_run_payload_for_recovery(result)),
            ).model_dump(mode="json")
            for result in child_results
            if str(result.get("phase")) in {RunPhase.failed.value, ScenarioPhase.failed.value}
        ]
        agentic_metrics = _merge_agentic_metrics(
            [
                evaluate_agentic_run(
                    plan=result["plan"],
                    decision_records=getattr(result.get("status"), "decision_records", []),
                    audit_events=result.get("audit_events") or [],
                    durable_learning_summary=_durable_learning_summary(result["plan"]),
                    manual_intervention_count=0,
                )
                for result in child_results
                if result.get("plan") is not None
            ]
        )
        final_outputs = [str(result["artifact_path"]) for result in child_results if result.get("artifact_path")]
        superseded_outputs = [
            item
            for result in child_results
            for item in (result.get("supersedes") or [])
            if isinstance(item, dict)
        ]
        return {
            "scenario_id": scenario_id,
            "scenario_name": request.scenario_name,
            "trigger_content": request.trigger_content,
            "disaster_type": request.disaster_type,
            "output_dir": str(output_dir),
            "expected_child_count": expected_child_count,
            "mission": {
                "scope_source": mission.scope_source,
                "task_bundle_id": mission.task_bundle_id,
                "expected_child_count": expected_child_count,
                "task_kinds": [task.task_kind.value for task in mission.child_tasks],
                "task_families": mission.task_families,
                "unsupported_layers": mission.unsupported_layers,
                "knowledge_identity": mission.knowledge_identity,
                "knowledge_refs": mission.knowledge_refs,
            },
            "child_runs": [_child_summary(result) for result in child_results],
            "kg_path_traces": kg_path_traces,
            "workflow_traces": workflow_traces,
            "source_coverage": source_coverage,
            "source_acquisition_jobs": source_acquisition_jobs,
            "rerun_status": _rerun_status_from_source_jobs(source_acquisition_jobs),
            "quality": quality,
            "failed_children": failed_children,
            "evaluation": {
                "data_fusion_metrics": data_fusion_metrics,
                "agentic_metrics": agentic_metrics,
                "self_evolution": {
                    "record_written": bool(agentic_metrics.get("self_evolution_record_written")),
                    "hint_available": bool(agentic_metrics.get("self_evolution_hint_available")),
                    "hint_used": bool(agentic_metrics.get("self_evolution_hint_used")),
                    "policy_adjustment": agentic_metrics.get("self_evolution_policy_adjustment", 0.0),
                    "learning_opportunity_recorded": bool(agentic_metrics.get("self_evolution_learning_opportunity_recorded")),
                },
            },
            "manual_interventions": 0,
            "final_outputs": final_outputs,
            "superseded_outputs": superseded_outputs,
            "document_paths": {},
        }

    @staticmethod
    def _write_summary_files(output_dir: Path, summary: dict[str, Any]) -> None:
        files = {
            "scenario_summary.json": summary,
            "evaluation.json": summary["evaluation"],
            "kg_path_trace.json": summary["kg_path_traces"],
            "workflow_trace.json": summary["workflow_traces"],
            "source_coverage.json": summary["source_coverage"],
            "source_acquisition_jobs.json": summary.get("source_acquisition_jobs", []),
            "failed_children.json": summary.get("failed_children", []),
        }
        for filename, payload in files.items():
            _write_json_roundtrip(output_dir / filename, payload)
        manifest = build_scenario_evidence_manifest(output_dir)
        _write_json_roundtrip(output_dir / "scenario_artifact_manifest.json", manifest.model_dump(mode="json"))


def _float_env(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.getenv(name, str(default))))
    except ValueError:
        return default


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_runtime_snapshot(output_dir: Path) -> None:
    payload = {
        "timestamp": _utc_now_iso(),
        "kg_backend": os.getenv("GEOFUSION_KG_BACKEND"),
        "llm_provider": os.getenv("GEOFUSION_LLM_PROVIDER"),
        "celery_eager": os.getenv("GEOFUSION_CELERY_EAGER"),
        "api_port": os.getenv("GEOFUSION_API_PORT"),
        "scenario_child_max_workers": os.getenv("GEOFUSION_SCENARIO_CHILD_MAX_WORKERS"),
        "scenario_child_terminal_wait_seconds": os.getenv("GEOFUSION_SCENARIO_CHILD_TERMINAL_WAIT_SECONDS"),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json_roundtrip(output_dir / "runtime.json", payload)


def _write_preflight_snapshot(
    output_dir: Path,
    request: ScenarioRunRequest,
    *,
    child_specs: list[ScenarioChildRunSpec],
) -> None:
    expected_child_count = _expected_child_count_for_request(request, mission_child_count=len(child_specs))
    payload = {
        "timestamp": _utc_now_iso(),
        "allowed": True,
        "scenario_name": request.scenario_name,
        "trigger_content": request.trigger_content,
        "disaster_type": request.disaster_type,
        "spatial_extent": request.spatial_extent,
        "expected_child_count": expected_child_count,
        "child_specs": [_checkpoint_child_spec(spec).model_dump(mode="json") for spec in child_specs],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json_roundtrip(output_dir / "preflight.json", payload)


def _write_json_roundtrip(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if loaded != payload:
        raise RuntimeError(f"UTF8_JSON_ROUNDTRIP_FAILED: {path}")


def process_due_source_acquisition_reruns(
    *,
    output_root: str | Path | None = None,
    service: ScenarioRunService | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Resume scenarios whose missing-source retry window has a due retry.

    Configuration-missing jobs intentionally do not enter this path: they are
    waiting for an external URL/path/key change and should not consume attempts.
    """

    root = resolve_scenario_output_root(str(output_root) if output_root is not None else None)
    runner = service or scenario_run_service
    now = datetime.now(timezone.utc)
    summary: dict[str, Any] = {
        "scanned": 0,
        "queued": 0,
        "rerun": 0,
        "retry_exhausted": 0,
        "skipped": 0,
        "failed": 0,
        "records": [],
    }
    if not root.exists():
        return summary

    for scenario_dir in sorted(root.glob("scenario*")):
        if summary["queued"] >= max(0, int(limit)):
            break
        if not scenario_dir.is_dir():
            continue
        jobs_path = scenario_dir / "source_acquisition_jobs.json"
        scenario_summary_path = scenario_dir / "scenario_summary.json"
        if not jobs_path.exists() or not scenario_summary_path.exists():
            continue
        summary["scanned"] += 1
        try:
            jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
            scenario_summary = json.loads(scenario_summary_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            summary["failed"] += 1
            summary["records"].append(
                {"scenario_id": scenario_dir.name, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            )
            continue
        if not isinstance(jobs, list):
            summary["skipped"] += 1
            continue

        due_jobs, expired_jobs = _due_source_retry_jobs(jobs, now=now)
        scenario_id = str(scenario_summary.get("scenario_id") or scenario_dir.name)
        if expired_jobs and not due_jobs:
            updated_jobs = _mark_retry_exhausted_jobs(jobs, expired_jobs)
            scenario_summary["source_acquisition_jobs"] = updated_jobs
            scenario_summary["rerun_status"] = {"state": ScenarioPhase.retry_exhausted.value}
            _write_json_roundtrip(jobs_path, updated_jobs)
            _write_json_roundtrip(scenario_summary_path, scenario_summary)
            summary["retry_exhausted"] += 1
            summary["records"].append({"scenario_id": scenario_id, "status": ScenarioPhase.retry_exhausted.value})
            continue
        if not due_jobs:
            summary["skipped"] += 1
            continue

        scenario_summary["rerun_status"] = {
            "state": ScenarioPhase.full_rerun_queued.value,
            "queued_at": now.isoformat(),
            "due_source_ids": [str(job.get("source_id") or "") for job in due_jobs],
        }
        _write_json_roundtrip(scenario_summary_path, scenario_summary)
        summary["queued"] += 1
        try:
            response = runner.resume_scenario_run(scenario_id, retry_failed=True)
        except Exception as exc:  # noqa: BLE001
            summary["failed"] += 1
            summary["records"].append(
                {"scenario_id": scenario_id, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            )
            continue
        summary["rerun"] += 1
        summary["records"].append(
            {
                "scenario_id": scenario_id,
                "status": "rerun_started",
                "phase": response.phase.value,
                "child_run_ids": response.child_run_ids,
            }
        )
    return summary


def _due_source_retry_jobs(jobs: list[Any], *, now: datetime) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    due: list[dict[str, Any]] = []
    expired: list[dict[str, Any]] = []
    for raw_job in jobs:
        if not isinstance(raw_job, dict):
            continue
        if str(raw_job.get("status") or "").strip().lower() != SCENARIO_SOURCE_RETRY_STATUS:
            continue
        expires_at = _parse_iso_time(raw_job.get("retry_window_expires_at"))
        if expires_at is not None and expires_at <= now:
            expired.append(raw_job)
            continue
        next_retry_at = _parse_iso_time(raw_job.get("next_retry_at"))
        if next_retry_at is None or next_retry_at <= now:
            due.append(raw_job)
    return due, expired


def _mark_retry_exhausted_jobs(jobs: list[Any], expired_jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expired_ids = {str(job.get("job_id") or "") for job in expired_jobs}
    updated: list[dict[str, Any]] = []
    for raw_job in jobs:
        if not isinstance(raw_job, dict):
            continue
        job = dict(raw_job)
        if str(job.get("job_id") or "") in expired_ids:
            job["status"] = ScenarioPhase.retry_exhausted.value
        updated.append(job)
    return updated


def _parse_iso_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _initial_checkpoint(
    *,
    request: ScenarioRunRequest,
    scenario_id: str,
    phase: ScenarioPhase,
) -> ScenarioCheckpoint:
    now = _utc_now_iso()
    return ScenarioCheckpoint(
        scenario_id=scenario_id,
        phase=phase,
        request=request.model_dump(mode="json"),
        child_specs=[],
        child_runs=[],
        started_at=now,
        updated_at=now,
        resume_count=0,
    )


def _load_resume_checkpoint(scenario_id: str) -> tuple[ScenarioRunRequest, Path, ScenarioCheckpoint]:
    registry = ScenarioRegistryService(output_root=resolve_scenario_output_root(None))
    record = registry.find_by_scenario_id(scenario_id)
    if record is None:
        output_dir = registry.output_root / scenario_id
        if not checkpoint_path(output_dir).exists():
            summary = registry.get_summary(scenario_id)
            output_dir = Path(str(summary.get("output_dir") or registry.output_root / scenario_id))
    else:
        output_dir = Path(str(record.get("output_dir") or registry.output_root / scenario_id))
    checkpoint = load_scenario_checkpoint(checkpoint_path(output_dir))
    return ScenarioRunRequest(**checkpoint.request), output_dir, checkpoint


def _child_specs_from_checkpoint(checkpoint: ScenarioCheckpoint) -> list[ScenarioChildRunSpec]:
    specs: list[ScenarioChildRunSpec] = []
    for item in checkpoint.child_specs:
        try:
            task_kind = TaskKind(item.task_kind) if item.task_kind else None
            specs.append(
                ScenarioChildRunSpec(
                    job_type=JobType(item.job_type),
                    trigger_content=item.trigger_content,
                    disaster_type=item.disaster_type,
                    spatial_extent=item.spatial_extent,
                    force_aoi_resolution=item.force_aoi_resolution,
                    target_crs=item.target_crs,
                    debug=item.debug,
                    task_kind=task_kind,
                    task_family=item.task_family,
                    preferred_pattern_id=item.preferred_pattern_id,
                    output_data_type=item.output_data_type,
                    product_contract_id=item.product_contract_id,
                    provisional_when_degraded=item.provisional_when_degraded,
                    final_output_may_supersede_provisional=item.final_output_may_supersede_provisional,
                )
            )
        except ValueError as exc:
            raise ValueError(f"Invalid checkpoint child spec for scenario {checkpoint.scenario_id}: {exc}") from exc
    return specs


def _child_results_from_checkpoint(
    checkpoint: ScenarioCheckpoint,
    child_specs: list[ScenarioChildRunSpec],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, item in enumerate(checkpoint.child_runs):
        spec = child_specs[index] if index < len(child_specs) else None
        results.append(_checkpoint_run_to_child_result(item, spec))
    return results


def _checkpoint_run_to_child_result(
    item: ScenarioCheckpointChildRun,
    spec: ScenarioChildRunSpec | None,
) -> dict[str, Any]:
    if spec is not None:
        task_key, task_family = _task_identity(
            job_type=spec.job_type,
            task_kind=spec.task_kind,
            task_family=spec.task_family,
        )
        job_type = spec.job_type.value
    else:
        job_type = item.job_type
        task_key = item.task_kind or item.job_type
        task_family = item.task_family or task_key
    return {
        "run_id": item.run_id,
        "job_type": job_type,
        "task_kind": task_key,
        "task_family": task_family,
        "phase": item.phase,
        "artifact_path": item.artifact_path,
        "error": item.error,
        "plan": None,
        "audit_events": [],
        "status": None,
        "product_contract_id": spec.product_contract_id if spec is not None else None,
        "provisional_when_degraded": spec.provisional_when_degraded if spec is not None else False,
        "final_output_may_supersede_provisional": (
            spec.final_output_may_supersede_provisional if spec is not None else False
        ),
    }


def _resume_result_is_completed_with_artifact(result: dict[str, Any]) -> bool:
    return str(result.get("phase")) == RunPhase.succeeded.value and bool(result.get("artifact_path"))


def _resume_result_is_failed(result: dict[str, Any]) -> bool:
    return str(result.get("phase")) in {RunPhase.failed.value, ScenarioPhase.failed.value}


def _resume_result_should_launch(result: dict[str, Any], *, retry_failed: bool) -> bool:
    if str(result.get("phase")) == ScenarioPhase.partial_provisional.value:
        return True
    if _resume_result_is_failed(result):
        return retry_failed
    if not result.get("run_id"):
        return True
    return False


def _write_checkpoint(output_dir: Path, checkpoint: ScenarioCheckpoint) -> None:
    write_scenario_checkpoint(
        checkpoint_path(output_dir),
        checkpoint.model_copy(update={"updated_at": _utc_now_iso()}),
    )


def _checkpoint_with_specs(
    checkpoint: ScenarioCheckpoint,
    child_specs: list[ScenarioChildRunSpec],
) -> ScenarioCheckpoint:
    return checkpoint.model_copy(
        update={
            "child_specs": [_checkpoint_child_spec(spec) for spec in child_specs],
        }
    )


def _checkpoint_with_child_runs(
    checkpoint: ScenarioCheckpoint,
    child_results: list[dict[str, Any]],
    *,
    phase: ScenarioPhase,
    children_phase: ScenarioPhase | None = None,
) -> ScenarioCheckpoint:
    return checkpoint.model_copy(
        update={
            "phase": phase,
            "children_phase": children_phase,
            "child_runs": [_checkpoint_child_run(result) for result in child_results],
        }
    )


def _checkpoint_child_spec(spec: ScenarioChildRunSpec) -> ScenarioCheckpointChildSpec:
    return ScenarioCheckpointChildSpec(
        job_type=spec.job_type.value,
        trigger_content=spec.trigger_content,
        disaster_type=spec.disaster_type,
        spatial_extent=spec.spatial_extent,
        force_aoi_resolution=spec.force_aoi_resolution,
        target_crs=spec.target_crs,
        debug=spec.debug,
        task_kind=spec.task_kind.value if spec.task_kind else None,
        task_family=spec.task_family,
        preferred_pattern_id=spec.preferred_pattern_id,
        output_data_type=spec.output_data_type,
        product_contract_id=spec.product_contract_id,
        provisional_when_degraded=spec.provisional_when_degraded,
        final_output_may_supersede_provisional=spec.final_output_may_supersede_provisional,
    )


def _checkpoint_child_run(result: dict[str, Any]) -> ScenarioCheckpointChildRun:
    return ScenarioCheckpointChildRun(
        run_id=str(result["run_id"]) if result.get("run_id") else None,
        job_type=str(result.get("job_type") or ""),
        task_kind=str(result.get("task_kind")) if result.get("task_kind") else None,
        task_family=str(result.get("task_family")) if result.get("task_family") else None,
        phase=str(result.get("phase") or ""),
        artifact_path=str(result.get("artifact_path")) if result.get("artifact_path") else None,
        error=str(result.get("error")) if result.get("error") else None,
    )


def _queued_child_run_for_spec(spec: ScenarioChildRunSpec) -> dict[str, Any]:
    task_key, task_family = _task_identity(
        job_type=spec.job_type,
        task_kind=spec.task_kind,
        task_family=spec.task_family,
    )
    return {
        "run_id": None,
        "job_type": spec.job_type.value,
        "task_kind": task_key,
        "task_family": task_family,
        "phase": RunPhase.queued.value,
        "artifact_path": None,
        "error": None,
        "product_contract_id": spec.product_contract_id,
        "provisional_when_degraded": spec.provisional_when_degraded,
        "final_output_may_supersede_provisional": spec.final_output_may_supersede_provisional,
    }


def _failed_child_run_for_spec(spec: ScenarioChildRunSpec, *, error: str) -> dict[str, Any]:
    result = _queued_child_run_for_spec(spec)
    result.update(
        {
            "phase": ScenarioPhase.failed.value,
            "error": error,
            "failure_code": _classify_error_code(error),
            "next_action": _next_action_for_error(error),
        }
    )
    return result


def _timed_out_child_result(result: dict[str, Any], *, timeout_seconds: float) -> dict[str, Any]:
    timed_out = dict(result)
    timed_out["phase"] = RunPhase.failed.value
    timed_out["error"] = f"CHILD_RUN_TIMEOUT: child run exceeded {timeout_seconds:g}s without terminal status"
    timed_out["failure_code"] = "CHILD_RUN_TIMEOUT"
    timed_out["next_action"] = "Inspect child run logs, source materialization attempts, and worker health."
    return timed_out


def _terminalize_background_child_result(result: dict[str, Any], *, error: str) -> dict[str, Any]:
    if str(result.get("phase")) in TERMINAL_CHILD_PHASES:
        return result
    terminal = dict(result)
    terminal["phase"] = ScenarioPhase.failed.value
    terminal["error"] = error
    terminal["failure_code"] = "SCENARIO_BACKGROUND_ERROR"
    terminal["next_action"] = "Inspect scenario logs and retry after fixing the background exception."
    return terminal


def _scenario_child_max_workers() -> int:
    try:
        return max(1, int(os.getenv("GEOFUSION_SCENARIO_CHILD_MAX_WORKERS", "1")))
    except ValueError:
        return 1


def _phase_from_child_results(child_results: list[dict[str, Any]]) -> ScenarioPhase:
    if not child_results:
        return ScenarioPhase.failed
    phases = [str(result.get("phase")) for result in child_results]
    if any(phase not in TERMINAL_CHILD_PHASES for phase in phases):
        return ScenarioPhase.running
    if any(phase == ScenarioPhase.awaiting_external_config.value for phase in phases):
        return ScenarioPhase.awaiting_external_config
    if any(phase == ScenarioPhase.source_retrying.value for phase in phases):
        return ScenarioPhase.source_retrying
    if any(phase == ScenarioPhase.full_rerun_queued.value for phase in phases):
        return ScenarioPhase.full_rerun_queued
    if any(phase == ScenarioPhase.partial_provisional.value for phase in phases):
        return ScenarioPhase.partial_provisional
    if all(phase == ScenarioPhase.superseded.value for phase in phases):
        return ScenarioPhase.superseded
    if any(phase == ScenarioPhase.retry_exhausted.value for phase in phases):
        return ScenarioPhase.retry_exhausted
    if all(phase == RunPhase.succeeded.value for phase in phases):
        if any(_child_degradation(result).get("state") == "degraded" for result in child_results):
            return ScenarioPhase.partial
        return ScenarioPhase.succeeded
    if all(phase in {RunPhase.failed.value, ScenarioPhase.failed.value, "cancelled", "skipped"} for phase in phases):
        return ScenarioPhase.failed
    return ScenarioPhase.partial


def _expected_child_count_for_request(request: ScenarioRunRequest, *, mission_child_count: int) -> int:
    return mission_child_count


def _source_coverage_from_children(child_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for result in child_results:
        task_kind = result.get("task_kind") or result.get("job_type")
        task_family = result.get("task_family") or result.get("job_type")
        for event in result.get("audit_events") or []:
            if event.kind == "task_inputs_resolved":
                component_coverage = event.details.get("component_coverage", {})
                coverage_state, degraded_component_source_ids = _component_coverage_state(component_coverage)
                items.append(
                    {
                        "run_id": result.get("run_id"),
                        "job_type": result.get("job_type"),
                        "task_kind": task_kind,
                        "task_family": task_family,
                        "requested_source_id": event.details.get("requested_source_id") or event.details.get("source_id"),
                        "selected_source_id": event.details.get("selected_source_id") or event.details.get("source_id"),
                        "fallback_from_source_id": event.details.get("fallback_from_source_id"),
                        "coverage": component_coverage,
                        "coverage_state": coverage_state,
                        "degraded_component_source_ids": degraded_component_source_ids,
                    }
                )
    return items


def _source_acquisition_jobs_from_children(
    *,
    scenario_id: str,
    child_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for result in child_results:
        run_id = str(result.get("run_id") or "")
        task_kind = result.get("task_kind") or result.get("job_type")
        for attempt in _source_attempts_for_child(result):
            source_id = str(attempt.get("source_id") or "").strip()
            if not source_id:
                continue
            status = _source_job_status(attempt)
            if status == "available":
                continue
            retry_after = _safe_int(attempt.get("next_retry_after_seconds"), default=None)
            next_retry_at = (now + timedelta(seconds=retry_after)).isoformat() if retry_after is not None else None
            job = {
                "job_id": f"{scenario_id}:{run_id or task_kind}:{source_id}",
                "scenario_id": scenario_id,
                "run_id": run_id or None,
                "task_kind": task_kind,
                "source_id": source_id,
                "status": status,
                "attempt": _safe_int(attempt.get("attempt_no"), default=0) or 0,
                "next_retry_at": next_retry_at,
                "retry_window_expires_at": (now + timedelta(hours=24)).isoformat(),
                "fault_class": attempt.get("fault_class"),
                "fault_message": attempt.get("fault_message"),
                "missing_config": _missing_config_for_source(source_id) if status == "awaiting_external_config" else [],
                "metadata": dict(attempt.get("metadata") or {}) if isinstance(attempt.get("metadata"), dict) else {},
            }
            jobs.append(job)
    return jobs


def _source_attempts_for_child(result: dict[str, Any]) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for event in result.get("audit_events") or []:
        details = getattr(event, "details", {}) or {}
        if not isinstance(details, dict):
            continue
        raw_attempts = details.get("source_attempts") or details.get("provider_attempts")
        explicit_source_ids: set[str] = set()
        if isinstance(raw_attempts, list):
            for item in raw_attempts:
                if not isinstance(item, dict):
                    continue
                attempt = dict(item)
                source_id = str(attempt.get("source_id") or "").strip()
                if source_id:
                    explicit_source_ids.add(source_id)
                attempt["_explicit_attempt"] = True
                attempts.append(attempt)
        coverage = details.get("component_coverage")
        if isinstance(coverage, dict):
            for source_id, payload in coverage.items():
                if not isinstance(payload, dict):
                    continue
                if str(source_id) in explicit_source_ids:
                    continue
                status = str(payload.get("coverage_status") or "").strip().lower()
                if status in {"", "available"}:
                    continue
                attempts.append(
                    {
                        "source_id": source_id,
                        "status": status,
                        "attempt_no": 0,
                        "fault_class": payload.get("fault_class"),
                        "fault_message": payload.get("error"),
                        "coverage_status": status,
                    }
                )
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for attempt in attempts:
        key = (str(attempt.get("source_id") or ""), str(attempt.get("status") or attempt.get("coverage_status") or ""))
        attempt.pop("_explicit_attempt", None)
        deduped[key] = attempt
    return list(deduped.values())


def _source_job_status(attempt: dict[str, Any]) -> str:
    status = str(attempt.get("status") or attempt.get("coverage_status") or "").strip().lower()
    fault_class = str(attempt.get("fault_class") or "").strip().upper()
    if status == "awaiting_external_config" or fault_class == "CONFIG_MISSING":
        return "awaiting_external_config"
    if status in {"coverage_empty", "empty"}:
        return "coverage_empty"
    if status in {"network_failed", "failed"} and bool(attempt.get("recoverable", True)):
        return "source_retrying"
    if status in {"provider_failed", "missing", "no_coverage", "unauthorized", "internal_failed"}:
        return status
    return status or "unknown"


def _rerun_status_from_source_jobs(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    if not jobs:
        return {"state": "not_required"}
    if any(job.get("status") == "awaiting_external_config" for job in jobs):
        return {"state": "awaiting_external_config"}
    if any(job.get("status") == "source_retrying" for job in jobs):
        return {"state": "source_retrying"}
    if any(job.get("status") == "coverage_empty" for job in jobs):
        return {"state": "partial_provisional"}
    return {"state": "source_retrying"}


def _missing_config_for_source(source_id: str) -> list[str]:
    if source_id in {"raw.google.building", "raw.google.open_buildings.vector"}:
        return ["google_open_buildings_urls"]
    if source_id == "raw.google.poi":
        return ["GOOGLE_PLACES_API_KEY", "google_poi_authorization_manifest"]
    if "raster" in source_id:
        return ["GEOFUSION_HEIGHT_RASTER_PATHS", "GEOFUSION_HEIGHT_RASTER_URLS"]
    return []


def _safe_int(value: Any, *, default: int | None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _component_coverage_state(component_coverage: Any) -> tuple[str, list[str]]:
    if not isinstance(component_coverage, dict) or not component_coverage:
        return "unknown", []
    degraded: list[str] = []
    for source_id, payload in component_coverage.items():
        feature_count = None
        coverage_status = ""
        if isinstance(payload, dict):
            coverage_status = str(payload.get("coverage_status") or "").strip().lower()
            raw_count = payload.get("feature_count")
            try:
                feature_count = int(raw_count) if raw_count is not None else None
            except (TypeError, ValueError):
                feature_count = None
        if coverage_status in {"empty", "missing", "missing_optional_ref", "coverage_empty", "awaiting_external_config"} or feature_count == 0:
            degraded.append(str(source_id))
    return ("degraded" if degraded else "available", sorted(degraded))


def _child_degradation(result: dict[str, Any]) -> dict[str, Any]:
    degraded_components: set[str] = set()
    awaiting_config: set[str] = set()
    coverage_empty: set[str] = set()
    task_kind = str(result.get("task_kind") or "")
    for event in result.get("audit_events") or []:
        if event.kind != "task_inputs_resolved":
            continue
        coverage = event.details.get("component_coverage", {})
        relevant_coverage = _task_relevant_component_coverage(task_kind, coverage)
        _state, components = _component_coverage_state(relevant_coverage)
        degraded_components.update(components)
        if isinstance(relevant_coverage, dict):
            for source_id, payload in relevant_coverage.items():
                if not isinstance(payload, dict):
                    continue
                status = str(payload.get("coverage_status") or "").strip().lower()
                if status == "awaiting_external_config":
                    awaiting_config.add(str(source_id))
                if status == "coverage_empty" or int(payload.get("feature_count") or 0) == 0:
                    coverage_empty.add(str(source_id))
    if not degraded_components:
        return {"state": "none", "reason_code": None, "degraded_component_source_ids": []}
    return {
        "state": "degraded",
        "reason_code": "PARTIAL_SOURCE_COVERAGE",
        "degraded_component_source_ids": sorted(degraded_components),
        "awaiting_external_config_source_ids": sorted(awaiting_config),
        "coverage_empty_source_ids": sorted(coverage_empty),
    }


def _task_relevant_component_coverage(task_kind: str, coverage: Any) -> dict[str, Any]:
    if not isinstance(coverage, dict):
        return {}
    relevant_source_ids = {
        str(candidate.get("source_id") or "").strip()
        for role in default_policy_registry().source_role_policies(str(task_kind))
        for candidate in role.get("candidates", [])
        if isinstance(candidate, dict) and str(candidate.get("source_id") or "").strip()
    }
    if not relevant_source_ids:
        raise KnowledgeReleaseError(f"No source role candidates for task kind {task_kind}")
    return {
        str(source_id): payload
        for source_id, payload in coverage.items()
        if str(source_id) in relevant_source_ids
    }


def _mark_child_result_provisional_if_degraded(
    result: dict[str, Any],
    *,
    allowed: bool,
) -> dict[str, Any]:
    if str(result.get("phase")) != RunPhase.succeeded.value or not result.get("artifact_path"):
        return result
    degradation = _child_degradation(result)
    if degradation.get("state") != "degraded":
        return result
    if not allowed:
        return result
    provisional = dict(result)
    provisional["phase"] = ScenarioPhase.partial_provisional.value
    provisional["provisional"] = True
    provisional["fusion_mode"] = "single_source_degraded"
    provisional["missing_sources"] = degradation.get("degraded_component_source_ids", [])
    provisional["retry_status"] = (
        "awaiting_external_config"
        if degradation.get("awaiting_external_config_source_ids")
        else "source_retrying"
    )
    return provisional


def _superseded_outputs(
    previous_child_results: list[dict[str, Any]],
    current_child_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    superseded: list[dict[str, Any]] = []
    for old in previous_child_results:
        if str(old.get("phase")) != ScenarioPhase.partial_provisional.value:
            continue
        if old.get("final_output_may_supersede_provisional") is not True:
            continue
        task_key = old.get("task_kind") or old.get("job_type")
        replacement = next(
            (
                result
                for result in current_child_results
                if (result.get("task_kind") or result.get("job_type")) == task_key
                and result.get("run_id")
                and result.get("run_id") != old.get("run_id")
                and str(result.get("phase")) == RunPhase.succeeded.value
            ),
            None,
        )
        if replacement is None:
            continue
        superseded.append(
            {
                "run_id": old.get("run_id"),
                "task_kind": task_key,
                "artifact_path": old.get("artifact_path"),
                "phase": ScenarioPhase.superseded.value,
                "superseded_by": replacement.get("run_id"),
            }
        )
    return superseded


def _data_fusion_metrics_for_child(result: dict[str, Any]) -> dict[str, Any]:
    artifact_path = result.get("artifact_path")
    metrics: dict[str, Any]
    if artifact_path and Path(artifact_path).suffix.lower() == ".shp":
        try:
            metrics = evaluate_vector_artifact(Path(artifact_path), required_fields=["geometry"])
        except Exception as exc:  # noqa: BLE001
            metrics = {"artifact_validity": False, "error": f"{type(exc).__name__}: {exc}"}
    else:
        metrics = {
            "artifact_validity": bool(artifact_path and Path(artifact_path).exists()),
            "artifact_path": str(artifact_path) if artifact_path else None,
        }
    return {
        "run_id": result.get("run_id"),
        "job_type": result.get("job_type"),
        "task_kind": result.get("task_kind") or result.get("job_type"),
        "task_family": result.get("task_family") or result.get("job_type"),
        "metrics": metrics,
    }


def _load_child_quality_report(result: dict[str, Any]) -> dict[str, Any] | None:
    artifact_path = result.get("artifact_path")
    if not artifact_path:
        return None
    artifact = Path(artifact_path)
    candidates = [
        artifact.parent / "quality_report.json",
        artifact.parent / f"{artifact.stem}_quality_report.json",
    ]
    run_id = result.get("run_id")
    if run_id:
        candidates.append(artifact.parent / f"{run_id}_quality_report.json")
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(payload, dict):
            payload.setdefault("run_id", result.get("run_id"))
            payload.setdefault("job_type", result.get("job_type"))
            payload.setdefault("task_kind", result.get("task_kind") or result.get("job_type"))
            return payload
    return None


def _quality_summary_from_children(child_results: list[dict[str, Any]]) -> dict[str, Any]:
    reports = []
    for result in child_results:
        report = _load_child_quality_report(result)
        if report is not None:
            reports.append(report)
    return {
        "accepted_child_count": sum(1 for report in reports if report.get("accepted") is True),
        "rejected_child_count": sum(1 for report in reports if report.get("accepted") is False),
        "child_reports": reports,
    }


def _run_payload_for_recovery(result: dict[str, Any]) -> dict[str, Any]:
    status = result.get("status")
    if hasattr(status, "model_dump"):
        payload = status.model_dump(mode="json")
    else:
        payload = {}
    payload.setdefault("run_id", result.get("run_id"))
    payload["phase"] = str(result.get("phase") or payload.get("phase") or "")
    payload["error"] = payload.get("error") or result.get("error")
    checkpoint = payload.get("checkpoint")
    if not isinstance(checkpoint, dict):
        payload["checkpoint"] = {}
    if not payload.get("failure_summary") and status is not None:
        payload["failure_summary"] = getattr(status, "failure_summary", None)
    return payload


def _merge_agentic_metrics(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    if not metrics:
        return {"manual_intervention_count": 0}
    merged: dict[str, Any] = {}
    keys = set().union(*(item.keys() for item in metrics))
    for key in keys:
        values = [item.get(key) for item in metrics if item.get(key) is not None]
        if all(isinstance(value, bool) for value in values):
            merged[key] = any(values)
        elif all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
            merged[key] = sum(float(value) for value in values) / len(values)
        else:
            merged[key] = values[-1] if values else None
    merged["manual_intervention_count"] = int(sum(item.get("manual_intervention_count", 0) for item in metrics))
    return merged


def _durable_learning_summary(plan) -> dict[str, Any]:
    if plan is None:
        return {}
    retrieval = plan.context.get("retrieval", {}) if isinstance(plan.context, dict) else {}
    durable = retrieval.get("durable_learning_summaries", {}) if isinstance(retrieval, dict) else {}
    return durable if isinstance(durable, dict) else {}


def _child_summary(result: dict[str, Any]) -> dict[str, Any]:
    error = result.get("error")
    code = str(result.get("failure_code") or _classify_error_code(error))
    summary = {
        "run_id": result.get("run_id"),
        "job_type": result.get("job_type"),
        "task_kind": result.get("task_kind") or result.get("job_type"),
        "task_family": result.get("task_family") or result.get("job_type"),
        "phase": result.get("phase"),
        "artifact_path": str(result.get("artifact_path")) if result.get("artifact_path") else None,
        "error": error,
        "error_code": code if error else None,
        "next_action": result.get("next_action") or (_next_action_for_error(error) if error else None),
        "degradation": _child_degradation(result),
    }
    for key in ("provisional", "fusion_mode", "missing_sources", "retry_status", "supersedes"):
        if key in result:
            summary[key] = result[key]
    return summary


def _classify_error_code(error: Any) -> str:
    return classify_failure_category(str(error or ""), scope="scenario_child")


def _next_action_for_error(error: Any) -> str:
    code = _classify_error_code(error)
    actions = {
        "CONFIG_MISSING": "Fill 依赖.txt or switch to --mode fast for memory/mock/eager execution.",
        "PORT_CONFLICT": "Stop the conflicting service, pass --auto-port, or choose another --port.",
        "AOI_RESOLUTION_REQUIRED": "Provide spatial_extent=bbox(minx,miny,maxx,maxy) or a resolvable location.",
        "AOI_RESOLUTION_FAILED": "Use a more specific location, cached geocoder, or explicit spatial_extent.",
        "GEOCODER_TIMEOUT": "Retry later, use fake/cached geocoding, or provide explicit spatial_extent.",
        "SOURCE_FETCH_TIMEOUT": "Prefetch sources with scripts/materialize_source_assets.py or retry with a larger source timeout.",
        "MISSING_REQUIRED_SOURCE": "Materialize or configure the required raw source before rerunning.",
        "CHILD_RUN_TIMEOUT": "Inspect child run logs, source provider attempts, and worker health before retrying.",
    }
    return actions.get(code, "Inspect workflow_trace.json and child run logs, then rerun after fixing the root cause.")


def _task_identity(
    *,
    job_type: JobType,
    task_kind: TaskKind | None,
    task_family: str | None,
) -> tuple[str, str]:
    task_key = task_kind.value if task_kind else job_type.value
    family = task_family or (task_kind_family(task_kind) if task_kind else job_type.value)
    return task_key, family


def _p3_variant() -> str:
    return os.getenv("GEOFUSION_P3_VARIANT", "full_method").strip().lower()


scenario_run_service = ScenarioRunService(agent_run_service=agent_run_service)
