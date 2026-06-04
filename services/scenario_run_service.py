from __future__ import annotations

import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from schemas.agent import RunCreateRequest, RunInputStrategy, RunPhase, RunTrigger, RunTriggerType
from schemas.fusion import JobType
from schemas.scenario import ScenarioChildRunSpec, ScenarioPhase, ScenarioRunRequest, ScenarioRunResponse
from schemas.task_kind import TaskKind, task_kind_family
from services.agent_run_service import AgentRunService, agent_run_service
from services.artifact_evaluation_service import evaluate_agentic_run, evaluate_vector_artifact
from services.evidence_lifecycle_service import build_scenario_evidence_manifest
from services.kg_path_trace_service import build_kg_path_trace
from services.mission_compiler_service import compile_scenario_mission
from services.run_recovery_service import build_recovery_hint
from services.scenario_failure_handler_service import ScenarioFailureHandlerService
from services.scenario_output import resolve_scenario_output_root
from services.scenario_registry_service import ScenarioRegistryService
from services.scenario_report_service import render_scenario_reports
from services.workflow_trace_service import build_workflow_trace


def create_scenario_id() -> str:
    return f"scenario_{uuid.uuid4().hex}"


def scenario_output_dir(request: ScenarioRunRequest, scenario_id: str) -> Path:
    return resolve_scenario_output_root(request.output_root) / scenario_id


def build_child_run_specs(request: ScenarioRunRequest) -> list[ScenarioChildRunSpec]:
    mission = compile_scenario_mission(request)
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
        )
        for task in mission.child_tasks
    ]


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
    TERMINAL_RUN_PHASES = {RunPhase.succeeded.value, RunPhase.failed.value}
    CHILD_RUN_POLL_INTERVAL_SECONDS = 1.0
    CHILD_RUN_TERMINAL_WAIT_SECONDS = 900.0

    def __init__(self, *, agent_run_service: AgentRunService) -> None:
        self.agent_run_service = agent_run_service
        self.failure_handler = ScenarioFailureHandlerService()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scenario-run")

    def create_scenario_run(self, request: ScenarioRunRequest) -> ScenarioRunResponse:
        scenario_id = create_scenario_id()
        output_dir = scenario_output_dir(request, scenario_id)
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

        scenario_id = create_scenario_id()
        output_dir = scenario_output_dir(request, scenario_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "request.json").write_text(
            json.dumps(request.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
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
        self._executor.submit(self._execute_scenario_run, request=request, scenario_id=scenario_id, output_dir=output_dir)
        return ScenarioRunResponse(
            scenario_id=scenario_id,
            phase=ScenarioPhase.running,
            output_dir=str(output_dir),
            child_run_ids=[],
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

        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "request.json").write_text(
            json.dumps(request.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        started_child_results = [self._run_child(output_dir, spec) for spec in build_child_run_specs(request)]
        child_results = self._wait_for_started_child_results(started_child_results)
        summary = self._build_summary(request, scenario_id, output_dir, child_results)
        document_paths = render_scenario_reports(summary=summary, documents_dir=output_dir / "documents")
        summary["document_paths"] = document_paths
        summary["phase"] = _phase_from_child_results(child_results).value
        self._write_summary_files(output_dir, summary)
        phase = _phase_from_child_results(child_results)
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

    def _run_child(self, output_dir: Path, spec: ScenarioChildRunSpec) -> dict[str, Any]:
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
            status = self.agent_run_service.create_run(
                request=request,
                osm_zip_name=None,
                osm_zip_bytes=None,
                ref_zip_name=None,
                ref_zip_bytes=None,
            )
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
        return {
            "run_id": run_id,
            "job_type": spec.job_type.value,
            "task_kind": task_key,
            "task_family": task_family,
            "phase": phase,
            "status": status,
            "plan": self.agent_run_service.get_plan(run_id),
            "audit_events": self.agent_run_service.get_audit_events(run_id),
            "artifact_path": self.agent_run_service.get_artifact_path(run_id),
            "error": getattr(status, "error", None) if status is not None else None,
        }

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

    def _child_run_poll_interval_seconds(self) -> float:
        return _float_env("GEOFUSION_SCENARIO_CHILD_POLL_INTERVAL_SECONDS", self.CHILD_RUN_POLL_INTERVAL_SECONDS)

    def _child_run_terminal_wait_seconds(self) -> float:
        return _float_env("GEOFUSION_SCENARIO_CHILD_TERMINAL_WAIT_SECONDS", self.CHILD_RUN_TERMINAL_WAIT_SECONDS)

    def _build_summary(
        self,
        request: ScenarioRunRequest,
        scenario_id: str,
        output_dir: Path,
        child_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        mission = compile_scenario_mission(request)
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
        return {
            "scenario_id": scenario_id,
            "scenario_name": request.scenario_name,
            "trigger_content": request.trigger_content,
            "disaster_type": request.disaster_type,
            "output_dir": str(output_dir),
            "mission": {
                "scope_source": mission.scope_source,
                "task_kinds": [task.task_kind.value for task in mission.child_tasks],
                "task_families": mission.task_families,
                "unsupported_layers": mission.unsupported_layers,
            },
            "child_runs": [_child_summary(result) for result in child_results],
            "kg_path_traces": kg_path_traces,
            "workflow_traces": workflow_traces,
            "source_coverage": source_coverage,
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
            "failed_children.json": summary.get("failed_children", []),
        }
        for filename, payload in files.items():
            (output_dir / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest = build_scenario_evidence_manifest(output_dir)
        (output_dir / "scenario_artifact_manifest.json").write_text(
            json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _float_env(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.getenv(name, str(default))))
    except ValueError:
        return default


def _phase_from_child_results(child_results: list[dict[str, Any]]) -> ScenarioPhase:
    if not child_results:
        return ScenarioPhase.failed
    phases = [str(result.get("phase")) for result in child_results]
    if any(phase not in {RunPhase.succeeded.value, RunPhase.failed.value, ScenarioPhase.failed.value} for phase in phases):
        return ScenarioPhase.running
    if all(phase == RunPhase.succeeded.value for phase in phases):
        if any(_child_degradation(result).get("state") == "degraded" for result in child_results):
            return ScenarioPhase.partial
        return ScenarioPhase.succeeded
    if all(phase == RunPhase.failed.value or phase == ScenarioPhase.failed.value for phase in phases):
        return ScenarioPhase.failed
    return ScenarioPhase.partial


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
        if coverage_status in {"empty", "missing", "missing_optional_ref", "coverage_empty"} or feature_count == 0:
            degraded.append(str(source_id))
    return ("degraded" if degraded else "available", sorted(degraded))


def _child_degradation(result: dict[str, Any]) -> dict[str, Any]:
    degraded_components: set[str] = set()
    for event in result.get("audit_events") or []:
        if event.kind != "task_inputs_resolved":
            continue
        _state, components = _component_coverage_state(event.details.get("component_coverage", {}))
        degraded_components.update(components)
    if not degraded_components:
        return {"state": "none", "reason_code": None, "degraded_component_source_ids": []}
    return {
        "state": "degraded",
        "reason_code": "PARTIAL_SOURCE_COVERAGE",
        "degraded_component_source_ids": sorted(degraded_components),
    }


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
    return {
        "run_id": result.get("run_id"),
        "job_type": result.get("job_type"),
        "task_kind": result.get("task_kind") or result.get("job_type"),
        "task_family": result.get("task_family") or result.get("job_type"),
        "phase": result.get("phase"),
        "artifact_path": str(result.get("artifact_path")) if result.get("artifact_path") else None,
        "error": result.get("error"),
        "degradation": _child_degradation(result),
    }


def _task_identity(
    *,
    job_type: JobType,
    task_kind: TaskKind | None,
    task_family: str | None,
) -> tuple[str, str]:
    task_key = task_kind.value if task_kind else job_type.value
    family = task_family or (task_kind_family(task_kind) if task_kind else job_type.value)
    return task_key, family


scenario_run_service = ScenarioRunService(agent_run_service=agent_run_service)
