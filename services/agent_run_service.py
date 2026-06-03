from __future__ import annotations

import json
import logging
import os
import re
import traceback
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from agent.semantic_parameter_binding import bind_source_semantic_parameters
from agent.policy import CandidateScoreInput, PolicyEngine
from agent.executor import ExecutionContext, WorkflowExecutor
from agent.planner import WorkflowPlanner
from agent.validator import WorkflowValidator
from kg.factory import create_kg_repository
from kg.models import ExecutionFeedback
from kg.models import DurableLearningRecord
from kg.repository import KGRepository
from llm.factory import create_llm_provider
from schemas.agent import (
    ArtifactReuseDecision,
    DecisionRecord,
    RepairRecord,
    RunEvent,
    RunArtifactMeta,
    RunCreateRequest,
    RunInputStrategy,
    RunPhase,
    RunStatus,
    RunTriggerType,
    WorkflowPlan,
)
from schemas.failure_taxonomy import classify_failure_details
from schemas.fusion import JobType
from schemas.settings import EffectiveLLMSettings
from services.artifact_registry import ArtifactRecord, ArtifactRegistry
from services.artifact_reuse_policy import get_artifact_reuse_max_age_seconds
from services.artifact_reuse_service import ArtifactReuseService, ReuseResult
from services.artifact_evaluation_service import evaluate_vector_artifact
from services.aoi_resolution_service import AOIResolutionService, NominatimGeocoder, ResolvedAOI
from services.input_acquisition_service import InputAcquisitionService, ResolvedRunInputs
from services.local_bundle_catalog import LocalBundleCatalogProvider
from services.plan_grounding_service import ensure_plan_grounding_report
from services.raw_vector_source_service import RawVectorSourceService
from services.runtime_settings_service import RuntimeSettingsService
from services.run_recovery_service import collect_recoverable_runs
from services.run_report_service import build_run_report_summary, render_run_reports
from services.source_semantic_contract_service import SourceSemanticContractService
from services.tile_partition_service import TilePartitionService
from services.tiled_building_runtime_service import TiledBuildingRuntimeService
from services.unsupported_intent_guard import classify_unsupported_intent
from utils.crs import normalize_target_crs, resolve_target_crs
from utils.shp_zip import validate_zip_has_shapefile, zip_shapefile_bundle
from utils.vector_clip import clip_zip_to_request_bbox


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value.strip())
    except Exception:  # noqa: BLE001
        return default


def build_run_inspection_digest(
    *,
    current_phase: str | None,
    failed_step: str | None = None,
    root_cause: str | None = None,
    recoverability: str | None = None,
    next_operator_action: str | None = None,
) -> Dict[str, str | None]:
    return {
        "current_phase": current_phase,
        "failed_step": failed_step,
        "root_cause": root_cause,
        "recoverability": recoverability,
        "next_operator_action": next_operator_action,
    }


def derive_run_inspection_digest(status: RunStatus, audit_events: List[RunEvent]) -> Dict[str, str | None]:
    current_phase = _inspection_current_phase(status)
    failure_details = _inspection_failure_details(status, audit_events)
    root_cause = failure_details.get("root_cause")
    failure_category = failure_details.get("failure_category")
    recoverability = failure_details.get("suggested_action") or failure_details.get("action")
    return build_run_inspection_digest(
        current_phase=current_phase,
        failed_step=_inspection_failed_step(status, audit_events),
        root_cause=root_cause,
        recoverability=recoverability,
        next_operator_action=_inspection_next_operator_action(
            current_phase=current_phase,
            root_cause=root_cause,
            failure_category=failure_category,
            recoverability=recoverability,
        ),
    )


def _inspection_current_phase(status: RunStatus) -> str:
    checkpoint = dict(status.checkpoint or {})
    if status.phase == RunPhase.succeeded:
        return status.phase.value
    for key in ("resume_stage", "stage"):
        value = str(checkpoint.get(key) or "").strip().lower()
        if value:
            return value
    return status.phase.value


def _inspection_failed_step(status: RunStatus, audit_events: List[RunEvent]) -> str | None:
    for event in reversed(audit_events):
        if event.kind not in {"step_failed", "run_failed", "replan_requested", "replan_rejected"}:
            continue
        if event.current_step is not None:
            return f"step {event.current_step}"
    if status.current_step is not None:
        return f"step {status.current_step}"
    checkpoint = dict(status.checkpoint or {})
    current_step = checkpoint.get("current_step")
    if current_step is None:
        return None
    return f"step {current_step}"


def _inspection_failure_details(status: RunStatus, audit_events: List[RunEvent]) -> Dict[str, str]:
    for event in reversed(audit_events):
        if event.kind not in {"step_failed", "run_failed", "replan_requested", "replan_rejected"}:
            continue
        details = dict(event.details or {})
        if details:
            root_cause = str(details.get("root_cause") or "").strip().upper()
            failure_category = str(details.get("failure_category") or "").strip().upper()
            action = str(details.get("suggested_action") or details.get("action") or "").strip()
            recoverable = details.get("recoverable")
            payload: Dict[str, str] = {}
            if root_cause:
                payload["root_cause"] = root_cause
            if failure_category:
                payload["failure_category"] = failure_category
            if action:
                payload["suggested_action"] = action
            if recoverable is not None:
                payload["recoverable"] = "true" if bool(recoverable) else "false"
            if payload:
                return payload

    failure_summary = str(status.failure_summary or "").strip()
    if failure_summary:
        parsed = _parse_failure_summary_tokens(failure_summary)
        root_cause = parsed.get("root_cause") or parsed.get("failure_category")
        if root_cause:
            parsed["root_cause"] = root_cause.upper()
        if parsed:
            return parsed

    if status.error:
        details = classify_failure_details(error=status.error, reason_code=status.error)
        return {
            "root_cause": details.failure_category,
            "failure_category": details.failure_category,
            "suggested_action": details.suggested_action,
            "recoverable": "true" if details.recoverable else "false",
        }
    return {}


def _parse_failure_summary_tokens(summary: str) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for chunk in summary.split("|"):
        part = chunk.strip()
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if key and value:
            parsed[key] = value
    return parsed


def _inspection_next_operator_action(
    *,
    current_phase: str,
    root_cause: str | None,
    failure_category: str | None,
    recoverability: str | None,
) -> str | None:
    code = str(root_cause or failure_category or "").strip().upper()
    if code == "PARAM_OUT_OF_RANGE":
        return "adjust bound and rerun"
    if code == "SOURCE_MISSING":
        return "provide or materialize the required source, then rerun"
    if code == "SOURCE_CORRUPTED":
        return "repair or replace the corrupted source, then rerun"
    if code == "CRS_MISMATCH":
        return "align the source CRS with the requested target CRS, then rerun"
    if code == "ALGO_TIMEOUT":
        return "reduce the AOI or retry with a lighter workflow, then rerun"
    if code == "SUSPECT_OUTPUT":
        return "inspect the artifact and validator output before rerunning"
    if recoverability == "replan":
        return "review the failed step inputs and rerun"
    if current_phase in {"queued", "planning", "validation", "running", "execution", "healing"}:
        return "monitor progress"
    if current_phase == "succeeded":
        return "download the artifact or compare this run against a baseline"
    if current_phase == "failed":
        return "inspect the failure summary and rerun when the issue is resolved"
    return None


@dataclass(frozen=True)
class RuntimeDependencies:
    settings: EffectiveLLMSettings
    llm_provider: Any
    planner: WorkflowPlanner
    executor: WorkflowExecutor


class RuntimeSnapshotUnavailableError(RuntimeError):
    pass


class AgentRunService:
    def __init__(
        self,
        base_dir: Path,
        max_workers: int = 2,
        kg_repo: Optional[KGRepository] = None,
        runtime_settings_service: RuntimeSettingsService | None = None,
    ) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._runs: Dict[str, RunStatus] = {}
        self._lock = Lock()
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="agent-run")
        self.runtime_settings_service = runtime_settings_service or RuntimeSettingsService()

        self.kg_repo = kg_repo or self._create_kg_repo()
        self.llm_provider = create_llm_provider()
        self.artifact_registry = ArtifactRegistry(index_path=self.base_dir / "artifact_registry.json")
        self.aoi_resolution_service = AOIResolutionService(geocoder=self._build_geocoder())
        self.raw_vector_source_service = self._build_raw_vector_source_service()
        self.input_acquisition_service = InputAcquisitionService(
            registry=self.artifact_registry,
            providers=self._build_input_bundle_providers(),
            cache_dir=self.base_dir / "input_bundle_cache",
        )
        self.tile_partition_service = TilePartitionService()
        self.tiled_building_runtime_service = TiledBuildingRuntimeService(max_workers=max_workers)
        self.source_semantic_contract_service = SourceSemanticContractService(kg_repo=self.kg_repo)
        self.artifact_reuse_service = ArtifactReuseService(self.artifact_registry)
        self.validator = WorkflowValidator(self.kg_repo)
        self._apply_default_runtime(
            self._build_runtime_dependencies(
                settings=self._resolve_default_llm_settings(),
                llm_provider=self.llm_provider,
            )
        )
        self.policy_engine = PolicyEngine(policy_version="v2")

        self.dispatch_eager = _as_bool(os.getenv("GEOFUSION_CELERY_EAGER", "1"), default=True)
        # Total plan revisions allowed for a single run, including the initial revision.
        self.max_plan_revisions = max(1, _as_int(os.getenv("GEOFUSION_MAX_PLAN_REVISIONS"), default=2))

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True)
        close = getattr(self.kg_repo, "close", None)
        if callable(close):
            close()

    def refresh_runtime_dependencies(self, llm_settings: EffectiveLLMSettings) -> None:
        with self._lock:
            runtime = self._build_runtime_dependencies(settings=llm_settings)
            self._apply_default_runtime(runtime)

    def create_run(
        self,
        request: RunCreateRequest,
        osm_zip_name: str | None,
        osm_zip_bytes: bytes | None,
        ref_zip_name: str | None,
        ref_zip_bytes: bytes | None,
    ) -> RunStatus:
        issues = classify_unsupported_intent(request.trigger.content, job_type=request.job_type)
        if issues:
            raise ValueError(f"Unsupported intent: {json.dumps(issues, ensure_ascii=False)}")

        run_id = uuid.uuid4().hex
        run_dir = self.base_dir / run_id
        input_dir = run_dir / "input"
        intermediate_dir = run_dir / "intermediate"
        output_dir = run_dir / "output"
        log_dir = run_dir / "logs"
        for directory in [input_dir, intermediate_dir, output_dir, log_dir]:
            directory.mkdir(parents=True, exist_ok=True)

        osm_zip_path: Path | None = None
        ref_zip_path: Path | None = None
        if request.input_strategy == RunInputStrategy.uploaded:
            if not osm_zip_name or osm_zip_bytes is None or not ref_zip_name or ref_zip_bytes is None:
                raise ValueError("uploaded input strategy requires both osm/ref zip bundles")
            osm_zip_path = input_dir / (Path(osm_zip_name).name or "osm.zip")
            ref_zip_path = input_dir / (Path(ref_zip_name).name or "ref.zip")
            osm_zip_path.write_bytes(osm_zip_bytes)
            ref_zip_path.write_bytes(ref_zip_bytes)
        elif request.input_strategy == RunInputStrategy.task_driven_auto:
            if any(value is not None for value in (osm_zip_name, osm_zip_bytes, ref_zip_name, ref_zip_bytes)):
                raise ValueError("task_driven_auto input strategy does not accept uploaded zip bundles")
        else:
            raise ValueError(f"Unsupported input strategy: {request.input_strategy}")
        self._persist_request(run_dir / "request.json", request)

        created_at = _utc_now()
        status = RunStatus(
            run_id=run_id,
            job_type=request.job_type,
            trigger=request.trigger,
            phase=RunPhase.queued,
            progress=0,
            target_crs=resolve_target_crs(request.target_crs),
            debug=request.debug,
            error=None,
            log_path=str(log_dir / "run.log"),
            plan_path=None,
            validation_path=None,
            audit_path=str(run_dir / "audit.jsonl"),
            artifact=None,
            decision_records=[],
            artifact_reuse=None,
            repair_records=[],
            current_step=None,
            attempt_no=0,
            healing_summary={},
            failure_summary=None,
            planning_telemetry={},
            plan_revision=0,
            event_count=0,
            last_event=None,
            checkpoint=self._checkpoint(stage="queued", plan_revision=0),
            created_at=created_at,
            updated_at=created_at,
            started_at=None,
            finished_at=None,
        )
        with self._lock:
            runtime_settings = self._snapshot_default_runtime_settings()
            runtime_snapshot_id = self.runtime_settings_service.store_runtime_snapshot(runtime_settings)
            self._persist_run_runtime_snapshot_id(run_id, runtime_snapshot_id)
            self._append_audit_event(
                status,
                RunEvent(
                    timestamp=_utc_now(),
                    kind="run_created",
                    phase=RunPhase.queued,
                    message="Run created and input bundles persisted.",
                    plan_revision=0,
                    progress=0,
                    attempt_no=0,
                    current_step=None,
                    details={
                        "request_path": str(run_dir / "request.json"),
                        "input_strategy": request.input_strategy.value,
                        "osm_zip_name": osm_zip_path.name if osm_zip_path is not None else None,
                        "ref_zip_name": ref_zip_path.name if ref_zip_path is not None else None,
                    },
                ),
            )
            self._runs[run_id] = status
            self._persist_status(status)

        if self.dispatch_eager:
            self.execute_run(
                run_id=run_id,
                request=request,
                osm_zip_path=osm_zip_path,
                ref_zip_path=ref_zip_path,
                intermediate_dir=intermediate_dir,
                output_dir=output_dir,
                log_dir=log_dir,
                runtime_snapshot_id=runtime_snapshot_id,
            )
        else:
            self._dispatch_run(
                run_id=run_id,
                request=request,
                osm_zip_path=osm_zip_path,
                ref_zip_path=ref_zip_path,
                intermediate_dir=intermediate_dir,
                output_dir=output_dir,
                log_dir=log_dir,
                runtime_snapshot_id=runtime_snapshot_id,
            )
        return self.get_run(run_id) or status

    def execute_run(
        self,
        run_id: str,
        request: RunCreateRequest,
        osm_zip_path: Path | None,
        ref_zip_path: Path | None,
        intermediate_dir: Path,
        output_dir: Path,
        log_dir: Path,
        runtime_snapshot_id: str | None = None,
        runtime_settings: EffectiveLLMSettings | Dict[str, Any] | None = None,
    ) -> None:
        logger = self._build_logger(run_id, log_dir / "run.log")
        plan: Optional[WorkflowPlan] = None
        repair_records: List[RepairRecord] = []
        runtime_request = request
        source_semantic_contract = None
        multisource_building_sources: tuple[dict[str, Path], dict[str, Path]] | None = None

        try:
            runtime_dependencies = self._build_runtime_dependencies(
                settings=self._resolve_run_runtime_settings(
                    run_id=run_id,
                    runtime_snapshot_id=runtime_snapshot_id,
                    runtime_settings=runtime_settings,
                )
            )
            self._update_status(
                run_id,
                RunPhase.planning,
                progress=5,
                started_at=_utc_now(),
                error=None,
                failure_summary=None,
                current_step=0,
                checkpoint=self._checkpoint(stage="planning", plan_revision=0, current_step=0),
                event_kind="run_started",
                event_message=f"Run started for job_type={request.job_type.value}.",
            )
            logger.info("Run started: %s (%s)", run_id, request.job_type.value)

            plan = self.run_planning_stage(run_id=run_id, request=request, runtime_dependencies=runtime_dependencies)
            logger.info("Planning stage completed with revision=%s", plan.context.get("plan_revision", 0))

            plan = self.run_validation_stage(run_id=run_id, plan=plan)
            logger.info("Validation stage completed; valid=%s", getattr(plan.validation, "valid", None))
            runtime_request = self._request_with_effective_target_crs(run_id, request)

            reuse_result = self._attempt_artifact_reuse(
                run_id=run_id,
                request=runtime_request,
                plan=plan,
                output_dir=output_dir,
            )
            if reuse_result is not None:
                artifact = reuse_result.artifact
                self._record_feedback(
                    run_id=run_id,
                    request=runtime_request,
                    plan=plan,
                    repair_records=repair_records,
                    success=True,
                    failure_reason=None,
                )
                self._register_artifact(
                    run_id=run_id,
                    request=runtime_request,
                    plan=plan,
                    artifact=artifact,
                    repair_records=repair_records,
                    extra_meta={
                        "reuse_mode": reuse_result.mode,
                        "parent_artifact_id": reuse_result.source_record.artifact_id,
                    },
                )
                document_paths = self._generate_run_reports(
                    run_id=run_id,
                    status_artifact=artifact,
                    plan=plan,
                    artifact_path=Path(artifact.path),
                )
                self._update_status(
                    run_id,
                    RunPhase.succeeded,
                    progress=100,
                    finished_at=_utc_now(),
                    artifact=artifact,
                    document_paths=document_paths,
                    repair_records=repair_records,
                    current_step=0,
                    attempt_no=self._max_attempt_no(repair_records),
                    healing_summary=self._build_healing_summary(repair_records),
                    failure_summary=None,
                    error=None,
                    plan_revision=self._extract_plan_revision(plan),
                    checkpoint=self._checkpoint(
                        stage="completed",
                        plan_revision=self._extract_plan_revision(plan),
                        current_step=0,
                        attempt_no=self._max_attempt_no(repair_records),
                    ),
                    event_kind="run_succeeded",
                    event_message=f"Run completed successfully via {reuse_result.mode} artifact reuse.",
                )
                logger.info(
                    "Artifact reuse applied: mode=%s source=%s",
                    reuse_result.mode,
                    reuse_result.source_record.artifact_id,
                )
                return

            input_dir = intermediate_dir.parent / "input"
            resolved_aoi = self._extract_resolved_aoi(plan)
            osm_zip_path, ref_zip_path, resolved_inputs = self._resolve_execution_inputs(
                request=runtime_request,
                plan=plan,
                input_dir=input_dir,
                osm_zip_path=osm_zip_path,
                ref_zip_path=ref_zip_path,
                resolved_aoi=resolved_aoi,
            )
            if resolved_inputs is not None:
                self._record_task_inputs_resolved(
                    run_id,
                    request=runtime_request,
                    plan=plan,
                    resolved_inputs=resolved_inputs,
                    resolved_aoi=resolved_aoi,
                    progress=50,
                    message="Task-driven input bundles prepared for execution.",
                )
                logger.info(
                    "Task-driven inputs resolved: mode=%s source_id=%s cache_hit=%s",
                    resolved_inputs.source_mode,
                    resolved_inputs.source_id,
                    resolved_inputs.cache_hit,
                )
                plan, source_semantic_contract = self._bind_source_semantics_for_resolved_inputs(
                    run_id=run_id,
                    request=runtime_request,
                    plan=plan,
                    resolved_inputs=resolved_inputs,
                )
                if source_semantic_contract is not None:
                    multisource_building_sources = self._building_sources_from_semantic_contract(source_semantic_contract)
            should_tile = self._should_use_tiled_building_runtime(
                request=runtime_request,
                plan=plan,
                resolved_inputs=resolved_inputs,
                resolved_aoi=resolved_aoi,
            )
            should_use_large_area_runtime = self._should_use_large_area_runtime(
                request=runtime_request,
                plan=plan,
                resolved_inputs=resolved_inputs,
                resolved_aoi=resolved_aoi,
            )

            while True:
                try:
                    if (
                        multisource_building_sources is not None
                        and self._should_use_multisource_building_runtime(runtime_request, plan)
                        and len(multisource_building_sources[0]) >= 2
                    ):
                        fused_shp, repair_records = self.run_multisource_building_execution_stage(
                            run_id=run_id,
                            request=runtime_request,
                            plan=plan,
                            intermediate_dir=intermediate_dir,
                            output_dir=output_dir,
                            vector_sources=multisource_building_sources[0],
                            raster_sources=multisource_building_sources[1],
                            resolved_aoi=resolved_aoi,
                            repair_records=repair_records,
                        )
                    elif should_tile:
                        fused_shp, repair_records = self.run_tiled_execution_stage(
                            run_id=run_id,
                            request=runtime_request,
                            plan=plan,
                            osm_zip_path=osm_zip_path,
                            ref_zip_path=ref_zip_path,
                            intermediate_dir=intermediate_dir,
                            output_dir=output_dir,
                            repair_records=repair_records,
                            resolved_inputs=resolved_inputs,
                            resolved_aoi=resolved_aoi,
                        )
                    elif should_use_large_area_runtime and resolved_inputs is not None:
                        fused_shp, repair_records = self.run_large_area_execution_stage(
                            run_id=run_id,
                            request=runtime_request,
                            plan=plan,
                            intermediate_dir=intermediate_dir,
                            output_dir=output_dir,
                            resolved_inputs=resolved_inputs,
                            resolved_aoi=resolved_aoi,
                            repair_records=repair_records,
                        )
                    else:
                        fused_shp, repair_records = self.run_execution_stage(
                            run_id=run_id,
                            request=runtime_request,
                            plan=plan,
                            osm_zip_path=osm_zip_path,
                            ref_zip_path=ref_zip_path,
                            intermediate_dir=intermediate_dir,
                            output_dir=output_dir,
                            repair_records=repair_records,
                            runtime_dependencies=runtime_dependencies,
                        )
                    break
                except Exception as exec_error:  # noqa: BLE001
                    failed_step = self._infer_failed_step(repair_records)
                    current_revision = self._extract_plan_revision(plan)
                    failure_message = f"{type(exec_error).__name__}: {exec_error}"
                    can_replan = failed_step is not None and current_revision < self.max_plan_revisions
                    replan_decision = self._build_replan_decision(
                        can_replan=can_replan,
                        failed_step=failed_step,
                        current_revision=current_revision,
                        failure_message=failure_message,
                    )

                    if not can_replan:
                        self._update_status(
                            run_id,
                            RunPhase.healing,
                            progress=60,
                            repair_records=repair_records,
                            current_step=failed_step,
                            attempt_no=self._max_attempt_no(repair_records),
                            healing_summary=self._build_healing_summary(repair_records),
                            failure_summary=self._build_failure_summary(failure_message, repair_records),
                            plan_revision=current_revision,
                            append_decision_record=replan_decision,
                            checkpoint=self._checkpoint(
                                stage="healing",
                                plan_revision=current_revision,
                                current_step=failed_step,
                                attempt_no=self._max_attempt_no(repair_records),
                            ),
                            event_kind="replan_rejected",
                            event_message="Execution failed and policy selected fail (replan unavailable).",
                            event_details={
                                "selected_action": replan_decision.selected_id,
                                "failed_step": failed_step,
                                "error": failure_message,
                            },
                        )
                        if failed_step is None:
                            raise
                        raise RuntimeError(
                            "Execution failed after exhausting repair strategies and "
                            f"reaching max plan revisions ({self.max_plan_revisions}): {exec_error}"
                        ) from exec_error

                    self._update_status(
                        run_id,
                        RunPhase.healing,
                        progress=60,
                        repair_records=repair_records,
                        current_step=failed_step,
                        attempt_no=self._max_attempt_no(repair_records),
                        healing_summary=self._build_healing_summary(repair_records),
                        failure_summary=self._build_failure_summary(failure_message, repair_records),
                        plan_revision=current_revision,
                        append_decision_record=replan_decision,
                        checkpoint=self._checkpoint(
                            stage="healing",
                            resume_stage="replanning",
                            plan_revision=current_revision,
                            current_step=failed_step,
                            attempt_no=self._max_attempt_no(repair_records),
                        ),
                        event_kind="replan_requested",
                        event_message="Execution failed after exhausting repair strategies; requesting replanning.",
                        event_details={
                            "selected_action": replan_decision.selected_id,
                            "failed_step": failed_step,
                            "error": failure_message,
                        },
                    )
                    logger.warning(
                        "Execution failed on revision=%s step=%s; attempting replan: %s",
                        current_revision,
                        failed_step,
                        failure_message,
                    )

                    replanned = runtime_dependencies.planner.replan_from_error(
                        run_id=run_id,
                        job_type=request.job_type,
                        trigger=request.trigger,
                        previous_plan=plan,
                        failed_step=failed_step,
                        error_message=failure_message,
                    )
                    replanned_revision = self._extract_plan_revision(replanned)
                    if replanned_revision <= current_revision:
                        raise RuntimeError(
                            "Replan did not produce a newer plan revision after execution failure."
                        ) from exec_error

                    previous_input_signature = self._task_driven_input_signature(plan)
                    plan = replanned
                    plan_path = self._plan_path(run_id)
                    self._persist_plan(plan_path, plan)
                    self._update_status(
                        run_id,
                        RunPhase.healing,
                        progress=65,
                        plan_path=str(plan_path),
                        repair_records=repair_records,
                        current_step=failed_step,
                        attempt_no=self._max_attempt_no(repair_records),
                        healing_summary=self._build_healing_summary(repair_records),
                        failure_summary=self._build_failure_summary(failure_message, repair_records),
                        plan_revision=replanned_revision,
                        checkpoint=self._checkpoint(
                            stage="healing",
                            resume_stage="validation",
                            plan_revision=replanned_revision,
                            current_step=failed_step,
                            attempt_no=self._max_attempt_no(repair_records),
                        ),
                        event_kind="replan_applied",
                        event_message=f"Applied replanned workflow revision {replanned_revision}.",
                        event_details={"failed_step": failed_step, "previous_revision": current_revision},
                    )
                    plan = self.run_validation_stage(run_id=run_id, plan=plan)
                    if (
                        request.input_strategy == RunInputStrategy.task_driven_auto
                        and previous_input_signature != self._task_driven_input_signature(plan)
                    ):
                        resolved_aoi = self._extract_resolved_aoi(plan) or resolved_aoi
                        osm_zip_path, ref_zip_path, resolved_inputs = self._resolve_execution_inputs(
                            request=runtime_request,
                            plan=plan,
                            input_dir=input_dir,
                            osm_zip_path=None,
                            ref_zip_path=None,
                            resolved_aoi=resolved_aoi,
                        )
                        if resolved_inputs is not None:
                            self._record_task_inputs_resolved(
                                run_id,
                                request=runtime_request,
                                plan=plan,
                                resolved_inputs=resolved_inputs,
                                resolved_aoi=resolved_aoi,
                                progress=68,
                                message="Task-driven input bundles refreshed after replan.",
                            )
                            plan, source_semantic_contract = self._bind_source_semantics_for_resolved_inputs(
                                run_id=run_id,
                                request=runtime_request,
                                plan=plan,
                                resolved_inputs=resolved_inputs,
                            )
                            if source_semantic_contract is not None:
                                multisource_building_sources = self._building_sources_from_semantic_contract(
                                    source_semantic_contract
                                )
                    should_tile = self._should_use_tiled_building_runtime(
                        request=runtime_request,
                        plan=plan,
                        resolved_inputs=resolved_inputs,
                        resolved_aoi=resolved_aoi,
                    )
                    should_use_large_area_runtime = self._should_use_large_area_runtime(
                        request=runtime_request,
                        plan=plan,
                        resolved_inputs=resolved_inputs,
                        resolved_aoi=resolved_aoi,
                    )
                    logger.info("Healing replan completed with revision=%s", self._extract_plan_revision(plan))
            logger.info("Execution stage completed: %s", fused_shp)

            artifact = self.run_writeback_stage(
                run_id=run_id,
                request=runtime_request,
                plan=plan,
                fused_shp=fused_shp,
                repair_records=repair_records,
                output_dir=output_dir,
            )
            document_paths = self._generate_run_reports(
                run_id=run_id,
                status_artifact=artifact,
                plan=plan,
                artifact_path=Path(artifact.path),
            )

            self._update_status(
                run_id,
                RunPhase.succeeded,
                progress=100,
                finished_at=_utc_now(),
                artifact=artifact,
                document_paths=document_paths,
                repair_records=repair_records,
                current_step=self._count_executable_steps(plan),
                attempt_no=self._max_attempt_no(repair_records),
                healing_summary=self._build_healing_summary(repair_records),
                failure_summary=None,
                error=None,
                plan_revision=self._extract_plan_revision(plan),
                checkpoint=self._checkpoint(
                    stage="completed",
                    plan_revision=self._extract_plan_revision(plan),
                    current_step=self._count_executable_steps(plan),
                    attempt_no=self._max_attempt_no(repair_records),
                ),
                event_kind="run_succeeded",
                event_message="Run completed successfully and artifact is ready.",
            )
            logger.info("Run succeeded.")
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
            failure_details = classify_failure_details(error=err, reason_code=err)
            logger.error(err)
            logger.error(traceback.format_exc())
            self._update_status(
                run_id,
                RunPhase.failed,
                progress=100,
                finished_at=_utc_now(),
                repair_records=repair_records,
                attempt_no=self._max_attempt_no(repair_records),
                healing_summary=self._build_healing_summary(repair_records),
                failure_summary=self._build_failure_summary(err, repair_records),
                error=err,
                current_step=self._infer_failed_step(repair_records),
                plan_revision=self._extract_plan_revision(plan),
                checkpoint=self._checkpoint(
                    stage="failed",
                    plan_revision=self._extract_plan_revision(plan),
                    current_step=self._infer_failed_step(repair_records),
                    attempt_no=self._max_attempt_no(repair_records),
                ),
                event_kind="run_failed",
                event_message="Run failed.",
                event_details={
                    "error": err,
                    "failure_category": failure_details.failure_category,
                    "root_cause": failure_details.root_cause,
                    "recoverable": failure_details.recoverable,
                    "suggested_action": failure_details.suggested_action,
                },
            )
            if plan is not None:
                self._record_feedback(
                    run_id=run_id,
                    request=runtime_request,
                    plan=plan,
                    repair_records=repair_records,
                    success=False,
                    failure_reason=err,
                )
        finally:
            for handler in list(logger.handlers):
                logger.removeHandler(handler)
                handler.close()

    def run_planning_stage(
        self,
        run_id: str,
        request: RunCreateRequest,
        runtime_dependencies: RuntimeDependencies | None = None,
    ) -> WorkflowPlan:
        runtime = runtime_dependencies or self._bound_default_runtime()
        planner = runtime.planner
        resolved_aoi: ResolvedAOI | None = None
        aoi_query = self._aoi_resolution_query(request)
        if aoi_query is not None:
            try:
                resolved_aoi = self.aoi_resolution_service.resolve(aoi_query)
                self._update_status(
                    run_id,
                    RunPhase.planning,
                    progress=12,
                    checkpoint=self._checkpoint(stage="planning"),
                    event_kind="aoi_resolved",
                    event_message=f"Resolved AOI for {resolved_aoi.display_name}.",
                    event_details={
                        "query": aoi_query,
                        "display_name": resolved_aoi.display_name,
                        "country_name": resolved_aoi.country_name,
                        "country_code": resolved_aoi.country_code,
                        "bbox": list(resolved_aoi.bbox),
                        "selection_reason": resolved_aoi.selection_reason,
                        "confidence": resolved_aoi.confidence,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                self._update_status(
                    run_id,
                    RunPhase.planning,
                    progress=12,
                    checkpoint=self._checkpoint(stage="planning"),
                    event_kind="aoi_resolution_failed",
                    event_message="AOI resolution failed before planning.",
                    event_details={
                        "query": aoi_query,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )
                raise

        effective_target_crs = resolve_target_crs(
            request.target_crs,
            bbox=(resolved_aoi.bbox if resolved_aoi is not None else None),
        )
        if request.target_crs:
            target_crs_source = "explicit"
        elif resolved_aoi is not None:
            target_crs_source = "resolved_aoi_default"
        else:
            target_crs_source = "fallback_default"
        self._update_status(
            run_id,
            RunPhase.planning,
            progress=14,
            target_crs=effective_target_crs,
            checkpoint=self._checkpoint(stage="planning"),
            event_kind="target_crs_resolved",
            event_message=f"Resolved target CRS {effective_target_crs}.",
            event_details={
                "target_crs": effective_target_crs,
                "source": target_crs_source,
            },
        )

        previous_override = planner.context_builder.resolved_aoi_override
        previous_pattern_override = planner.context_builder.preferred_pattern_id_override
        planner.context_builder.resolved_aoi_override = resolved_aoi
        planner.context_builder.preferred_pattern_id_override = request.preferred_pattern_id
        try:
            plan = planner.create_plan(run_id=run_id, job_type=request.job_type, trigger=request.trigger)
        finally:
            planner.context_builder.resolved_aoi_override = previous_override
            planner.context_builder.preferred_pattern_id_override = previous_pattern_override
        intent = dict(plan.context.get("intent", {}))
        if intent.get("request_input_strategy") != request.input_strategy.value:
            intent["request_input_strategy"] = request.input_strategy.value
            plan.context = {**plan.context, "intent": intent}
        if resolved_aoi is not None:
            if intent.get("resolved_aoi") is None:
                intent["resolved_aoi"] = resolved_aoi.to_dict()
                plan.context = {**plan.context, "intent": intent}
        planning_decisions = self._build_planning_decisions(plan)
        artifact_reuse = self._build_artifact_reuse_decision(plan)
        grounding_report = ensure_plan_grounding_report(plan)
        planning_telemetry = dict(plan.context.get("planning_telemetry") or {})
        plan_path = self._plan_path(run_id)
        self._persist_plan(plan_path, plan)
        event_details = {
            "workflow_id": plan.workflow_id,
            "grounded": grounding_report["grounded"],
            "grounding_score": grounding_report["grounding_score"],
            "planning_telemetry": planning_telemetry,
            "effective_parameters": self._extract_effective_parameters(plan),
            "selected_decisions": {
                decision.decision_type: decision.selected_id for decision in planning_decisions
            },
            "planning_mode": plan.context.get("planning_mode"),
            "planning_source": plan.context.get("planning_source"),
            "profile_source": plan.context.get("intent", {}).get("profile_source"),
            "task_bundle": plan.context.get("intent", {}).get("task_bundle"),
            "selectable_source_ids": plan.context.get("execution_hints", {}).get("selectable_source_ids", []),
            "reserved_source_ids": plan.context.get("execution_hints", {}).get("reserved_source_ids", []),
            "required_reserved_capabilities": plan.context.get("execution_hints", {}).get(
                "required_reserved_capabilities",
                [],
            ),
        }
        if plan.context.get("intent", {}).get("resolved_aoi") is not None:
            event_details["resolved_aoi"] = plan.context["intent"]["resolved_aoi"]
        pattern_decision = next((item for item in planning_decisions if item.decision_type == "pattern_selection"), None)
        if pattern_decision is not None:
            event_details["selected_pattern"] = pattern_decision.selected_id
        event_details["artifact_reuse"] = artifact_reuse.model_dump(mode="json")
        self._update_status(
            run_id,
            RunPhase.validating,
            progress=25,
            plan_path=str(plan_path),
            plan_revision=self._extract_plan_revision(plan),
            decision_records=planning_decisions,
            artifact_reuse=artifact_reuse,
            planning_telemetry=planning_telemetry,
            checkpoint=self._checkpoint(stage="validation", plan_revision=self._extract_plan_revision(plan)),
            event_kind="plan_created",
            event_message=f"Workflow plan revision {self._extract_plan_revision(plan)} created.",
            event_details=event_details,
        )
        return plan

    def run_validation_stage(self, run_id: str, plan: WorkflowPlan) -> WorkflowPlan:
        validated = self.validator.validate_and_repair(plan)
        plan_path = self._plan_path(run_id)
        validation_path = self._validation_path(run_id)
        self._persist_plan(plan_path, validated)
        self._persist_validation(validation_path, validated)
        self._update_status(
            run_id,
            RunPhase.running,
            progress=45,
            plan_path=str(plan_path),
            validation_path=str(validation_path),
            plan_revision=self._extract_plan_revision(validated),
            checkpoint=self._checkpoint(stage="validation", plan_revision=self._extract_plan_revision(validated)),
            event_kind="plan_validated",
            event_message=f"Workflow plan revision {self._extract_plan_revision(validated)} validated.",
            event_details={
                "valid": bool(getattr(validated.validation, "valid", False)),
                "inserted_transform_steps": int(getattr(validated.validation, "inserted_transform_steps", 0)),
            },
        )
        return validated

    def run_execution_stage(
        self,
        run_id: str,
        request: RunCreateRequest,
        plan: WorkflowPlan,
        osm_zip_path: Path,
        ref_zip_path: Path,
        intermediate_dir: Path,
        output_dir: Path,
        repair_records: Optional[List[RepairRecord]] = None,
        runtime_dependencies: RuntimeDependencies | None = None,
    ) -> tuple[Path, List[RepairRecord]]:
        runtime = runtime_dependencies or self._bound_default_runtime()
        osm_extract = intermediate_dir / "osm"
        ref_extract = intermediate_dir / "ref"
        osm_shp = validate_zip_has_shapefile(osm_zip_path, osm_extract)
        ref_shp = validate_zip_has_shapefile(ref_zip_path, ref_extract)

        repair_records = repair_records if repair_records is not None else []
        context = ExecutionContext(
            run_id=run_id,
            job_type=request.job_type,
            osm_shp=osm_shp,
            ref_shp=ref_shp,
            output_dir=output_dir,
            target_crs=self._request_with_effective_target_crs(run_id, request).target_crs,
            field_mapping=request.field_mapping,
            debug=request.debug,
            alternative_data_sources=self._extract_alternative_sources(plan),
            named_vectors=self._extract_named_paths(plan, "named_vectors"),
            named_rasters=self._extract_named_paths(plan, "named_rasters"),
            context_vectors=self._extract_named_paths(plan, "context_vectors"),
        )
        self._update_status(
            run_id,
            RunPhase.running,
            progress=55,
            repair_records=repair_records,
            current_step=0,
            attempt_no=self._max_attempt_no(repair_records),
            healing_summary=self._build_healing_summary(repair_records),
            plan_revision=self._extract_plan_revision(plan),
            checkpoint=self._checkpoint(
                stage="execution",
                plan_revision=self._extract_plan_revision(plan),
                current_step=0,
                attempt_no=self._max_attempt_no(repair_records),
            ),
            event_kind="execution_started",
            event_message="Execution stage started.",
        )
        fused_shp = runtime.executor.execute_plan(
            plan=plan,
            context=context,
            repair_records=repair_records,
            on_step_event=lambda payload: self._record_execution_step_event(
                run_id=run_id,
                plan=plan,
                repair_records=repair_records,
                payload=payload,
            ),
        )
        self._update_status(
            run_id,
            RunPhase.running,
            progress=80,
            repair_records=repair_records,
            current_step=self._count_executable_steps(plan),
            attempt_no=self._max_attempt_no(repair_records),
            healing_summary=self._build_healing_summary(repair_records),
            plan_revision=self._extract_plan_revision(plan),
            checkpoint=self._checkpoint(
                stage="execution",
                plan_revision=self._extract_plan_revision(plan),
                current_step=self._count_executable_steps(plan),
                attempt_no=self._max_attempt_no(repair_records),
            ),
            event_kind="execution_completed",
            event_message="Execution stage completed and produced an output artifact.",
            event_details={"repair_count": len(repair_records)},
        )
        self._persist_plan(self._plan_path(run_id), plan)
        return fused_shp, repair_records

    def run_tiled_execution_stage(
        self,
        *,
        run_id: str,
        request: RunCreateRequest,
        plan: WorkflowPlan,
        osm_zip_path: Path,
        ref_zip_path: Path,
        intermediate_dir: Path,
        output_dir: Path,
        repair_records: Optional[List[RepairRecord]] = None,
        resolved_inputs: ResolvedRunInputs | None,
        resolved_aoi: ResolvedAOI | None,
    ) -> tuple[Path, List[RepairRecord]]:
        repair_records = repair_records if repair_records is not None else []
        request_bbox = self._resolve_request_bbox(request, resolved_aoi=resolved_aoi)
        if request_bbox is None:
            raise ValueError("Tiled building runtime requires an AOI bbox.")
        selected_source_id = None
        if resolved_inputs is not None:
            selected_source_id = resolved_inputs.selected_source_id or resolved_inputs.source_id
        target_crs = self._request_with_effective_target_crs(run_id, request).target_crs
        tile_manifest = self.tile_partition_service.partition_bbox(
            bbox=request_bbox,
            bbox_crs="EPSG:4326",
            working_crs=target_crs,
        )
        manifest_path = intermediate_dir / "tile_manifest.json"
        manifest_path.write_text(json.dumps(tile_manifest.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

        self._update_status(
            run_id,
            RunPhase.running,
            progress=55,
            repair_records=repair_records,
            current_step=0,
            attempt_no=self._max_attempt_no(repair_records),
            healing_summary=self._build_healing_summary(repair_records),
            plan_revision=self._extract_plan_revision(plan),
            checkpoint=self._checkpoint(
                stage="execution",
                plan_revision=self._extract_plan_revision(plan),
                current_step=0,
                attempt_no=self._max_attempt_no(repair_records),
            ),
            event_kind="execution_started",
            event_message="Execution stage started.",
        )
        self._update_status(
            run_id,
            RunPhase.running,
            progress=58,
            repair_records=repair_records,
            current_step=0,
            attempt_no=self._max_attempt_no(repair_records),
            healing_summary=self._build_healing_summary(repair_records),
            plan_revision=self._extract_plan_revision(plan),
            checkpoint=self._checkpoint(
                stage="execution",
                plan_revision=self._extract_plan_revision(plan),
                current_step=0,
                attempt_no=self._max_attempt_no(repair_records),
            ),
            event_kind="tile_manifest_created",
            event_message="Tile manifest created for tiled building execution.",
            event_details={
                "tile_count": len(tile_manifest.tiles),
                "tile_manifest_path": str(manifest_path),
                "selected_source_id": selected_source_id,
                "request_bbox": list(request_bbox),
            },
        )

        def _bundle_factory(source_zip: Path):
            def _factory(tile, target_path: Path) -> Path:
                return clip_zip_to_request_bbox(source_zip, target_path, request_bbox=tile.buffered_bbox)

            return _factory

        tile_parameters = self._extract_step_parameters(plan)
        result = self.tiled_building_runtime_service.run_tiled_building_job(
            run_id=run_id,
            tile_manifest=tile_manifest,
            osm_bundle_factory=_bundle_factory(osm_zip_path),
            ref_bundle_factory=_bundle_factory(ref_zip_path),
            output_dir=output_dir,
            target_crs=target_crs,
            field_mapping=request.field_mapping,
            debug=request.debug,
            parameters=tile_parameters,
            on_event=lambda kind, details: self._record_tiled_runtime_event(
                run_id=run_id,
                plan=plan,
                repair_records=repair_records,
                kind=kind,
                details=details,
            ),
        )
        fused_shp = result.output_shp
        self._update_status(
            run_id,
            RunPhase.running,
            progress=80,
            repair_records=repair_records,
            current_step=self._count_executable_steps(plan),
            attempt_no=self._max_attempt_no(repair_records),
            healing_summary=self._build_healing_summary(repair_records),
            plan_revision=self._extract_plan_revision(plan),
            checkpoint=self._checkpoint(
                stage="execution",
                plan_revision=self._extract_plan_revision(plan),
                current_step=self._count_executable_steps(plan),
                attempt_no=self._max_attempt_no(repair_records),
            ),
            event_kind="execution_completed",
            event_message="Execution stage completed and produced an output artifact.",
            event_details={
                "repair_count": len(repair_records),
                "tile_count": result.tile_count,
                "stitched_feature_count": result.stitched_feature_count,
            },
        )
        self._persist_plan(self._plan_path(run_id), plan)
        return fused_shp, repair_records

    def _record_execution_step_event(
        self,
        *,
        run_id: str,
        plan: WorkflowPlan,
        repair_records: List[RepairRecord],
        payload: Dict[str, object],
    ) -> None:
        raw_status = str(payload.get("status") or "").strip().lower()
        if raw_status not in {"started", "succeeded", "failed"}:
            return
        step = payload.get("step")
        current_step = int(step) if isinstance(step, int) else None
        event_details = dict(payload)
        if raw_status == "failed" and not str(event_details.get("error") or "").strip():
            event_details["error"] = self._summarize_step_failure(
                repair_records=repair_records,
                current_step=current_step,
            )
        if raw_status == "failed":
            event_details.update(self._build_step_failure_operator_note(repair_records=repair_records, current_step=current_step))
        if raw_status == "failed":
            event_message = f"Execution step failed: step={current_step}; error={event_details['error']}."
        else:
            event_message = f"Execution step {raw_status}: step={current_step}."
        self._update_status(
            run_id,
            RunPhase.running,
            repair_records=repair_records,
            current_step=current_step,
            attempt_no=self._max_attempt_no(repair_records),
            healing_summary=self._build_healing_summary(repair_records),
            plan_revision=self._extract_plan_revision(plan),
            checkpoint=self._checkpoint(
                stage="execution",
                plan_revision=self._extract_plan_revision(plan),
                current_step=current_step,
                attempt_no=self._max_attempt_no(repair_records),
            ),
            event_kind=f"step_{raw_status}",
            event_message=event_message,
            event_details=event_details,
        )

    def _resolve_execution_inputs(
        self,
        *,
        request: RunCreateRequest,
        plan: WorkflowPlan,
        input_dir: Path,
        osm_zip_path: Path | None,
        ref_zip_path: Path | None,
        resolved_aoi: ResolvedAOI | None = None,
    ) -> tuple[Path, Path, ResolvedRunInputs | None]:
        if osm_zip_path is not None and ref_zip_path is not None:
            return osm_zip_path, ref_zip_path, None
        if request.input_strategy == RunInputStrategy.uploaded:
            raise ValueError("uploaded input strategy requires persisted input bundles before execution")

        source_candidates = self._task_driven_source_candidates(plan)
        if not source_candidates:
            raise ValueError("task-driven input strategy could not resolve a source_id from the plan")
        required_output_type = self._extract_required_input_data_type(plan)
        if not required_output_type:
            raise ValueError("task-driven input strategy could not resolve the required input data type")

        request_bbox = self._resolve_request_bbox(request, resolved_aoi=resolved_aoi)
        last_error: ValueError | None = None
        source_id = source_candidates[0]
        for candidate_source_id in source_candidates:
            try:
                resolved = self.input_acquisition_service.resolve_task_driven_inputs(
                    request=request,
                    source_id=candidate_source_id,
                    required_output_type=required_output_type,
                    input_dir=input_dir,
                    request_bbox=request_bbox,
                    resolved_aoi=resolved_aoi,
                )
                if candidate_source_id != source_id and not resolved.fallback_from_source_id:
                    resolved = ResolvedRunInputs(
                        osm_zip_path=resolved.osm_zip_path,
                        ref_zip_path=resolved.ref_zip_path,
                        source_mode=resolved.source_mode,
                        source_id=resolved.source_id,
                        cache_hit=resolved.cache_hit,
                        version_token=resolved.version_token,
                        selected_source_id=resolved.selected_source_id or candidate_source_id,
                        fallback_from_source_id=source_id,
                        component_coverage=resolved.component_coverage,
                        manifest_path=resolved.manifest_path,
                    )
                return resolved.osm_zip_path, resolved.ref_zip_path, resolved
            except ValueError as exc:
                last_error = exc
                message = str(exc)
                if "SOURCE_MISSING" not in message and "empty source coverage" not in message:
                    raise
                if candidate_source_id == source_candidates[-1]:
                    raise

        if last_error is not None:
            raise last_error
        raise ValueError("task-driven input strategy could not materialize any candidate source")

    def _record_tiled_runtime_event(
        self,
        *,
        run_id: str,
        plan: WorkflowPlan,
        repair_records: List[RepairRecord],
        kind: str,
        details: Dict[str, object],
    ) -> None:
        progress_by_kind = {
            "tile_execution_started": 62,
            "tile_execution_completed": 72,
            "tile_stitch_completed": 78,
        }
        message_by_kind = {
            "tile_execution_started": "Tile execution started.",
            "tile_execution_completed": "Tile execution completed.",
            "tile_stitch_completed": "Tile stitch completed.",
        }
        self._update_status(
            run_id,
            RunPhase.running,
            progress=progress_by_kind.get(kind, 60),
            repair_records=repair_records,
            current_step=0,
            attempt_no=self._max_attempt_no(repair_records),
            healing_summary=self._build_healing_summary(repair_records),
            plan_revision=self._extract_plan_revision(plan),
            checkpoint=self._checkpoint(stage="execution", plan_revision=self._extract_plan_revision(plan)),
            event_kind=kind,
            event_message=message_by_kind.get(kind, kind),
            event_details=details,
        )

    def _record_large_area_runtime_completed(
        self,
        *,
        run_id: str,
        plan: WorkflowPlan,
        repair_records: List[RepairRecord],
        result: object,
    ) -> None:
        evidence_paths = {
            key: str(value)
            for key, value in dict(getattr(result, "evidence_paths", {}) or {}).items()
        }
        self._update_status(
            run_id,
            RunPhase.running,
            progress=80,
            repair_records=repair_records,
            current_step=self._count_executable_steps(plan),
            attempt_no=self._max_attempt_no(repair_records),
            healing_summary=self._build_healing_summary(repair_records),
            plan_revision=self._extract_plan_revision(plan),
            checkpoint=self._checkpoint(stage="execution", plan_revision=self._extract_plan_revision(plan)),
            event_kind="large_area_runtime_completed",
            event_message="Shared large-area runtime completed and produced an output artifact.",
            event_details={
                "tile_count": int(getattr(result, "tile_count", 0) or 0),
                "stitched_feature_count": int(getattr(result, "stitched_feature_count", 0) or 0),
                "evidence_paths": evidence_paths,
            },
        )

    def _record_task_inputs_resolved(
        self,
        run_id: str,
        *,
        request: RunCreateRequest,
        plan: WorkflowPlan,
        resolved_inputs: ResolvedRunInputs,
        resolved_aoi: ResolvedAOI | None,
        progress: int,
        message: str,
    ) -> None:
        event_details = {
            "input_strategy": request.input_strategy.value,
            "source_mode": resolved_inputs.source_mode,
            "source_id": resolved_inputs.source_id,
            "requested_source_id": resolved_inputs.source_id,
            "selected_source_id": resolved_inputs.selected_source_id or resolved_inputs.source_id,
            "fallback_from_source_id": resolved_inputs.fallback_from_source_id,
            "component_coverage": resolved_inputs.component_coverage,
            "cache_hit": resolved_inputs.cache_hit,
            "version_token": resolved_inputs.version_token,
            "osm_zip_name": resolved_inputs.osm_zip_path.name,
            "ref_zip_name": resolved_inputs.ref_zip_path.name,
            "target_crs": request.target_crs,
            "source_materialization_manifest_path": (
                str(resolved_inputs.manifest_path) if resolved_inputs.manifest_path is not None else None
            ),
        }
        if resolved_aoi is not None:
            event_details["resolved_aoi"] = {
                "display_name": resolved_aoi.display_name,
                "country_code": resolved_aoi.country_code,
                "country_name": resolved_aoi.country_name,
                "bbox": list(resolved_aoi.bbox),
            }
        if resolved_inputs.component_coverage:
            self._update_status(
                run_id,
                RunPhase.running,
                progress=max(0, progress - 3),
                plan_revision=self._extract_plan_revision(plan),
                checkpoint=self._checkpoint(stage="execution", plan_revision=self._extract_plan_revision(plan)),
                event_kind="source_coverage_checked",
                event_message="Source coverage was checked for task-driven inputs.",
                event_details={
                    "requested_source_id": resolved_inputs.source_id,
                    "selected_source_id": resolved_inputs.selected_source_id or resolved_inputs.source_id,
                    "component_coverage": resolved_inputs.component_coverage,
                },
            )
        if resolved_inputs.fallback_from_source_id:
            self._update_status(
                run_id,
                RunPhase.running,
                progress=max(0, progress - 2),
                plan_revision=self._extract_plan_revision(plan),
                checkpoint=self._checkpoint(stage="execution", plan_revision=self._extract_plan_revision(plan)),
                event_kind="source_fallback_selected",
                event_message="Selected fallback source after empty AOI coverage.",
                event_details={
                    "fallback_from_source_id": resolved_inputs.fallback_from_source_id,
                    "selected_source_id": resolved_inputs.selected_source_id or resolved_inputs.source_id,
                },
            )
        if "clip" in resolved_inputs.source_mode:
            self._update_status(
                run_id,
                RunPhase.running,
                progress=max(0, progress - 1),
                plan_revision=self._extract_plan_revision(plan),
                checkpoint=self._checkpoint(stage="execution", plan_revision=self._extract_plan_revision(plan)),
                event_kind="source_clipped",
                event_message="Source bundle was clipped to the requested AOI.",
                event_details={
                    "source_mode": resolved_inputs.source_mode,
                    "selected_source_id": resolved_inputs.selected_source_id or resolved_inputs.source_id,
                },
            )
        self._update_status(
            run_id,
            RunPhase.running,
            progress=max(0, progress - 1),
            plan_revision=self._extract_plan_revision(plan),
            checkpoint=self._checkpoint(stage="execution", plan_revision=self._extract_plan_revision(plan)),
            event_kind="input_bundle_created",
            event_message="Input bundle was created for execution.",
            event_details={
                "osm_zip_name": resolved_inputs.osm_zip_path.name,
                "ref_zip_name": resolved_inputs.ref_zip_path.name,
                "selected_source_id": resolved_inputs.selected_source_id or resolved_inputs.source_id,
            },
        )
        self._update_status(
            run_id,
            RunPhase.running,
            progress=progress,
            plan_revision=self._extract_plan_revision(plan),
            checkpoint=self._checkpoint(stage="execution", plan_revision=self._extract_plan_revision(plan)),
            event_kind="task_inputs_resolved",
            event_message=message,
            event_details=event_details,
        )

    def _bind_source_semantics_for_resolved_inputs(
        self,
        *,
        run_id: str,
        request: RunCreateRequest,
        plan: WorkflowPlan,
        resolved_inputs: ResolvedRunInputs,
    ) -> tuple[WorkflowPlan, object | None]:
        component_paths = self._source_component_paths_from_resolved_inputs(
            run_id=run_id,
            resolved_inputs=resolved_inputs,
        )
        if not component_paths:
            return plan, None
        try:
            contract = self.source_semantic_contract_service.build_contract(
                run_id=run_id,
                job_type=request.job_type.value,
                selected_source_id=resolved_inputs.selected_source_id or resolved_inputs.source_id,
                component_paths=component_paths,
                target_crs=resolve_target_crs(request.target_crs),
                raster_paths=self._raster_paths_for_source_semantics(resolved_inputs),
            )
        except Exception as exc:  # noqa: BLE001
            current = self.get_run(run_id)
            if current is not None:
                self._update_status(
                    run_id,
                    current.phase,
                    plan_revision=self._extract_plan_revision(plan),
                    checkpoint=self._checkpoint(stage="execution", plan_revision=self._extract_plan_revision(plan)),
                    event_kind="source_semantics_unavailable",
                    event_message="Source semantic contract could not be built for the resolved inputs.",
                    event_details={
                        "error": f"{type(exc).__name__}: {exc}",
                        "component_source_ids": sorted(component_paths),
                    },
                )
            return plan, None
        return self._persist_source_semantics(
            run_id=run_id,
            request=request,
            plan=plan,
            contract=contract,
        ), contract

    def _persist_source_semantics(
        self,
        *,
        run_id: str,
        request: RunCreateRequest,
        plan: WorkflowPlan,
        contract,
    ) -> WorkflowPlan:
        del request
        path = self.base_dir / run_id / "source_semantic_contract.json"
        path.write_text(json.dumps(contract.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        updated_plan = bind_source_semantic_parameters(plan, contract)
        self._persist_plan(self._plan_path(run_id), updated_plan)
        summary = {
            "job_type": contract.job_type,
            "component_source_ids": list(contract.component_source_ids),
            "valid": bool(contract.validation.get("valid")),
            "issue_count": len(contract.validation.get("issues") or []),
            "height_policy": dict(contract.height_policy),
        }
        current = self.get_run(run_id)
        if current is not None:
            current.source_semantic_contract_path = str(path)
            current.source_semantic_summary = summary
            self._runs[run_id] = current
            self._persist_status(current)
            self._update_status(
                run_id,
                current.phase,
                checkpoint=self._checkpoint(
                    stage="execution",
                    plan_revision=self._extract_plan_revision(updated_plan),
                ),
                event_kind="source_semantics_bound",
                event_message="Source semantic contract was bound to runtime parameters.",
                event_details={"source_semantic_contract_path": str(path), **summary},
            )
        return updated_plan

    def _source_component_paths_from_resolved_inputs(
        self,
        *,
        run_id: str,
        resolved_inputs: ResolvedRunInputs,
    ) -> dict[str, Path]:
        paths: dict[str, Path] = {}
        coverage = dict(resolved_inputs.component_coverage or {})
        for source_id, payload in coverage.items():
            if str(source_id).endswith(".raster"):
                continue
            path = self._component_path_from_payload(payload)
            if path is not None and path.exists():
                paths[source_id] = path

        if paths or coverage:
            return paths

        selected_source_id = resolved_inputs.selected_source_id or resolved_inputs.source_id
        component_ids = self._component_source_ids_for_selected_source(selected_source_id)
        zip_paths = [resolved_inputs.osm_zip_path, resolved_inputs.ref_zip_path]
        extracted_root = self.base_dir / run_id / "intermediate" / "source_semantics"
        for source_id, zip_path in zip(component_ids, zip_paths):
            if source_id in paths or not zip_path.exists():
                continue
            extracted = self._extract_vector_artifact_for_source_semantics(
                source_id=source_id,
                zip_path=zip_path,
                extracted_root=extracted_root,
            )
            if extracted is not None:
                paths[source_id] = extracted
        return paths

    def _component_paths_from_resolved_inputs_for_runtime(
        self,
        *,
        run_id: str,
        resolved_inputs: ResolvedRunInputs,
    ) -> dict[str, Path]:
        return self._source_component_paths_from_resolved_inputs(
            run_id=run_id,
            resolved_inputs=resolved_inputs,
        )

    @staticmethod
    def _component_path_from_payload(payload: object) -> Path | None:
        if isinstance(payload, dict):
            raw = payload.get("artifact_path") or payload.get("path") or payload.get("zip_path")
        else:
            raw = getattr(payload, "artifact_path", None) or getattr(payload, "path", None) or getattr(payload, "zip_path", None)
        if not raw:
            return None
        return Path(str(raw))

    @staticmethod
    def _component_source_ids_for_selected_source(selected_source_id: str | None) -> list[str]:
        try:
            from kg.source_catalog import get_catalog_bundle_spec

            return list(get_catalog_bundle_spec(str(selected_source_id)).component_source_ids)
        except Exception:  # noqa: BLE001
            return []

    @staticmethod
    def _extract_vector_artifact_for_source_semantics(
        *,
        source_id: str,
        zip_path: Path,
        extracted_root: Path,
    ) -> Path | None:
        extract_dir = extracted_root / source_id.replace(".", "_")
        try:
            return validate_zip_has_shapefile(zip_path, extract_dir)
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _raster_paths_for_source_semantics(resolved_inputs: ResolvedRunInputs) -> dict[str, Path]:
        rasters: dict[str, Path] = {}
        for source_id, payload in dict(resolved_inputs.component_coverage or {}).items():
            if not str(source_id).endswith(".raster"):
                continue
            path = AgentRunService._component_path_from_payload(payload)
            if path is not None and path.exists():
                rasters[str(source_id)] = path
        return rasters

    def run_writeback_stage(
        self,
        run_id: str,
        request: RunCreateRequest,
        plan: WorkflowPlan,
        fused_shp: Path,
        repair_records: List[RepairRecord],
        output_dir: Path,
    ) -> RunArtifactMeta:
        self._validate_output_artifact_against_schema_policy(
            run_id=run_id,
            request=request,
            plan=plan,
            fused_shp=fused_shp,
        )
        artifact_zip = self._zip_output_artifact(
            fused_shp,
            output_dir / f"{request.job_type.value}_fusion_result.zip",
        )
        artifact = RunArtifactMeta(
            filename=artifact_zip.name,
            path=str(artifact_zip),
            size_bytes=artifact_zip.stat().st_size,
        )
        self._record_feedback(
            run_id=run_id,
            request=request,
            plan=plan,
            repair_records=repair_records,
            success=True,
            failure_reason=None,
        )
        self._register_artifact(run_id=run_id, request=request, plan=plan, artifact=artifact, repair_records=repair_records)
        return artifact

    @staticmethod
    def _zip_output_artifact(artifact_path: Path, output_zip: Path) -> Path:
        artifact_path = Path(artifact_path)
        if artifact_path.suffix.lower() != ".gpkg":
            return zip_shapefile_bundle(artifact_path, output_zip)

        output_zip.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(artifact_path, arcname=artifact_path.name)
        return output_zip

    def _validate_output_artifact_against_schema_policy(
        self,
        *,
        run_id: str,
        request: RunCreateRequest,
        plan: WorkflowPlan,
        fused_shp: Path,
    ) -> None:
        output_data_type = self._extract_output_data_type(plan)
        raw_policy = ArtifactReuseService._output_schema_policy(plan, required_output_type=output_data_type)
        schema_policy = self.kg_repo.get_output_schema_policy(output_data_type) if output_data_type else None
        if raw_policy is not None:
            required_fields = raw_policy.get("required_fields", []) or ["geometry"]
            policy_id = raw_policy.get("policy_id")
        else:
            required_fields = schema_policy.required_fields if schema_policy is not None else ["geometry"]
            policy_id = schema_policy.policy_id if schema_policy is not None else None
        metrics = evaluate_vector_artifact(fused_shp, required_fields=required_fields)
        event_details = {
            "output_data_type": output_data_type,
            "policy_id": policy_id,
            "required_fields": required_fields,
            "missing_fields": metrics.get("missing_fields", []),
            "artifact_validity": bool(metrics.get("artifact_validity", False)),
        }
        self._update_status(
            run_id,
            RunPhase.running,
            progress=90,
            plan_revision=self._extract_plan_revision(plan),
            checkpoint=self._checkpoint(stage="writeback", plan_revision=self._extract_plan_revision(plan)),
            event_kind="output_schema_validated",
            event_message=(
                f"Artifact validated against policy {policy_id}."
                if policy_id is not None
                else "Artifact validated against default geometry-only contract."
            ),
            event_details=event_details,
        )
        if not metrics.get("artifact_validity", False):
            raise RuntimeError(
                "Artifact schema validation failed: "
                f"missing_fields={metrics.get('missing_fields', [])}"
            )

    def _register_artifact(
        self,
        *,
        run_id: str,
        request: RunCreateRequest,
        plan: WorkflowPlan,
        artifact: RunArtifactMeta,
        repair_records: List[RepairRecord],
        extra_meta: Optional[Dict[str, object]] = None,
    ) -> None:
        # Artifact registry writeback is best-effort; it should not fail a successful run.
        try:
            created_at = _utc_now()
            output_fields: List[str] = []
            if request.field_mapping:
                found = set()
                for mapping in request.field_mapping.values():
                    if isinstance(mapping, dict):
                        found.update(str(key) for key in mapping.keys() if str(key))
                output_fields = sorted(found)
            if "geometry" not in output_fields:
                output_fields.insert(0, "geometry")

            output_data_type = self._extract_output_data_type(plan)
            target_crs = self._request_with_effective_target_crs(run_id, request).target_crs
            schema_policy = self.kg_repo.get_output_schema_policy(output_data_type) if output_data_type else None

            meta: Dict[str, object] = {
                "run_id": run_id,
                "workflow_id": plan.workflow_id,
                "plan_revision": plan.context.get("plan_revision"),
                "pattern_id": self._extract_pattern_id(plan),
                "algorithm_id": self._extract_algorithm_id(plan, repair_records=repair_records),
                "selected_data_source": self._extract_selected_data_source(plan),
                "trigger_type": request.trigger.type.value,
                "output_data_type": output_data_type,
                "target_crs": target_crs,
                "schema_policy_id": schema_policy.policy_id if schema_policy else None,
                "compatibility_basis": schema_policy.compatibility_basis if schema_policy else None,
                "freshness_policy_seconds": get_artifact_reuse_max_age_seconds(request.job_type),
            }
            if extra_meta:
                meta.update(extra_meta)

            record = ArtifactRecord(
                artifact_id=run_id,
                artifact_path=artifact.path,
                job_type=request.job_type.value,
                disaster_type=request.trigger.disaster_type,
                created_at=created_at,
                output_fields=output_fields,
                output_data_type=output_data_type,
                target_crs=target_crs,
                schema_policy_id=schema_policy.policy_id if schema_policy else None,
                compatibility_basis=schema_policy.compatibility_basis if schema_policy else None,
                bbox=self._parse_bbox(request.trigger.spatial_extent),
                meta=meta,
            )
            self.artifact_registry.register(record)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("geofusion.run").warning("Failed to register artifact for reuse: %s", exc)

    def _generate_run_reports(
        self,
        *,
        run_id: str,
        status_artifact: RunArtifactMeta,
        plan: WorkflowPlan,
        artifact_path: Path,
    ) -> Dict[str, str]:
        current = self.get_run(run_id)
        if current is None:
            return {}
        status_for_report = current.model_copy(
            update={
                "phase": RunPhase.succeeded,
                "progress": 100,
                "artifact": status_artifact,
            }
        )
        audit_events = self.get_audit_events(run_id)
        source_semantic_contract = self._load_source_semantic_contract_for_report(status_for_report)
        summary = build_run_report_summary(
            status=status_for_report,
            plan=plan,
            audit_events=audit_events,
            artifact_path=artifact_path,
            source_semantic_contract=source_semantic_contract,
        )
        return render_run_reports(
            summary=summary,
            documents_dir=self.base_dir / run_id / "documents",
        )

    @staticmethod
    def _load_source_semantic_contract_for_report(status: RunStatus) -> Dict[str, Any]:
        path_text = str(status.source_semantic_contract_path or "").strip()
        if not path_text:
            return {}
        try:
            payload = json.loads(Path(path_text).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _parse_bbox(value: str | None):
        if not value:
            return None
        match = re.match(r"^bbox\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)\s*$", value)
        if not match:
            return None
        try:
            return (float(match.group(1)), float(match.group(2)), float(match.group(3)), float(match.group(4)))
        except Exception:  # noqa: BLE001
            return None

    def _request_with_effective_target_crs(self, run_id: str, request: RunCreateRequest) -> RunCreateRequest:
        status = self.get_run(run_id)
        target_crs = status.target_crs if status is not None else resolve_target_crs(request.target_crs)
        if request.target_crs == target_crs:
            return request
        return request.model_copy(update={"target_crs": target_crs})

    def _should_use_tiled_building_runtime(
        self,
        *,
        request: RunCreateRequest,
        plan: WorkflowPlan,
        resolved_inputs: ResolvedRunInputs | None,
        resolved_aoi: ResolvedAOI | None,
    ) -> bool:
        if request.job_type != JobType.building:
            return False
        if request.input_strategy != RunInputStrategy.task_driven_auto:
            return False
        if resolved_inputs is None:
            return False
        request_bbox = self._resolve_request_bbox(request, resolved_aoi=resolved_aoi)
        if request_bbox is None:
            return False
        selected_source_id = (
            resolved_inputs.selected_source_id
            or resolved_inputs.source_id
            or self._resolve_task_driven_source_id(plan)
        )
        if selected_source_id not in {"catalog.flood.building", "catalog.earthquake.building"}:
            return False
        threshold = self._read_env_int("GEOFUSION_BUILDING_TILING_MIN_FEATURES") or 250000
        return self._max_component_feature_count(resolved_inputs.component_coverage) >= threshold

    def _should_use_large_area_runtime(
        self,
        *,
        request: RunCreateRequest,
        plan: WorkflowPlan,
        resolved_inputs: ResolvedRunInputs | None,
        resolved_aoi: ResolvedAOI | None,
    ) -> bool:
        if request.input_strategy != RunInputStrategy.task_driven_auto:
            return False
        if request.job_type not in {JobType.road, JobType.water, JobType.poi}:
            return False
        if resolved_inputs is None:
            return False
        if self._resolve_request_bbox(request, resolved_aoi=resolved_aoi) is None:
            return False
        selected_source_id = (
            resolved_inputs.selected_source_id
            or resolved_inputs.source_id
            or self._resolve_task_driven_source_id(plan)
        )
        if not selected_source_id:
            return False
        return self._has_large_area_runtime_material(resolved_inputs, job_type=request.job_type)

    @classmethod
    def _has_large_area_runtime_material(cls, resolved_inputs: ResolvedRunInputs, *, job_type: JobType) -> bool:
        allowed_source_ids_by_job = {
            JobType.road: {"raw.osm.road", "raw.overture.transportation", "raw.overture.road"},
            JobType.water: {
                "raw.osm.water",
                "raw.hydrolakes.water",
                "raw.osm.waterways",
                "raw.hydrorivers.water",
            },
            JobType.poi: {"raw.osm.poi", "raw.gns.poi", "raw.geonames.poi"},
        }
        allowed_source_ids = allowed_source_ids_by_job.get(job_type, set())
        coverage = dict(resolved_inputs.component_coverage or {})
        for source_id, payload in coverage.items():
            if source_id not in allowed_source_ids:
                continue
            path = cls._component_path_from_payload(payload)
            if path is not None and path.exists():
                return True
        if coverage:
            return False
        return cls._has_legacy_input_bundle_path(resolved_inputs)

    @staticmethod
    def _has_legacy_input_bundle_path(resolved_inputs: ResolvedRunInputs) -> bool:
        return any(
            path is not None and Path(path).exists() and zipfile.is_zipfile(Path(path))
            for path in (resolved_inputs.osm_zip_path, resolved_inputs.ref_zip_path)
        )

    def _should_use_multisource_building_runtime(self, request: RunCreateRequest, plan: WorkflowPlan) -> bool:
        if request.job_type != JobType.building or request.input_strategy != RunInputStrategy.task_driven_auto:
            return False
        parameters = self._extract_step_parameters(plan)
        priority = parameters.get("source_priority_order")
        return isinstance(priority, list) and len(priority) >= 2

    def run_multisource_building_execution_stage(
        self,
        *,
        run_id: str,
        request: RunCreateRequest,
        plan: WorkflowPlan,
        intermediate_dir: Path,
        output_dir: Path,
        vector_sources: dict[str, Path],
        raster_sources: dict[str, Path] | None,
        resolved_aoi: ResolvedAOI | None,
        repair_records: Optional[List[RepairRecord]] = None,
    ) -> tuple[Path, List[RepairRecord]]:
        from services.domain_fusion_runners import make_building_multisource_runner
        from services.large_area_runtime_service import LargeAreaRuntimeService, LargeAreaSlice

        del intermediate_dir
        repair_records = repair_records if repair_records is not None else []
        request_bbox = self._resolve_request_bbox(request, resolved_aoi=resolved_aoi)
        if request_bbox is None:
            raise ValueError("Multi-source tiled building runtime requires an AOI bbox.")
        target_crs = self._request_with_effective_target_crs(run_id, request).target_crs
        tile_manifest = self.tile_partition_service.partition_bbox(
            bbox=request_bbox,
            bbox_crs="EPSG:4326",
            working_crs=target_crs,
        )
        parameters = self._extract_step_parameters(plan)
        priority = tuple(parameters.get("source_priority_order") or vector_sources.keys())
        result = LargeAreaRuntimeService(max_workers=1).run(
            run_id=run_id,
            job_type="building",
            tile_manifest=tile_manifest,
            slices=[
                LargeAreaSlice(
                    name="building",
                    geometry_family="building",
                    sources=vector_sources,
                    runner=make_building_multisource_runner(
                        raster_sources=raster_sources or {},
                        source_priority_order=priority,
                    ),
                )
            ],
            output_dir=output_dir,
            target_crs=target_crs,
            parameters=parameters,
            on_event=lambda kind, details: self._record_large_area_runtime_event(
                run_id=run_id,
                plan=plan,
                repair_records=repair_records,
                kind=kind,
                details=details,
            ),
        )
        self._record_large_area_runtime_completed(
            run_id=run_id,
            plan=plan,
            repair_records=repair_records,
            result=result,
        )
        return result.output_path, repair_records

    def run_large_area_execution_stage(
        self,
        *,
        run_id: str,
        request: RunCreateRequest,
        plan: WorkflowPlan,
        intermediate_dir: Path,
        output_dir: Path,
        resolved_inputs: ResolvedRunInputs,
        resolved_aoi: ResolvedAOI | None,
        repair_records: Optional[List[RepairRecord]] = None,
    ) -> tuple[Path, List[RepairRecord]]:
        from services.domain_fusion_runners import run_poi_tile, run_road_tile, run_water_polygon_tile, run_waterways_tile
        from services.large_area_runtime_service import LargeAreaRuntimeService, LargeAreaSlice

        del intermediate_dir
        repair_records = repair_records if repair_records is not None else []
        step = self._first_executable_step(plan)
        algorithm_id = self._algorithm_id_for_step(plan, step)
        request_bbox = self._resolve_request_bbox(request, resolved_aoi=resolved_aoi)
        if request_bbox is None:
            raise ValueError("Shared large-area runtime requires an AOI bbox.")
        target_crs = self._request_with_effective_target_crs(run_id, request).target_crs
        component_paths = self._component_paths_from_resolved_inputs_for_runtime(
            run_id=run_id,
            resolved_inputs=resolved_inputs,
        )
        tile_manifest = self.tile_partition_service.partition_bbox(
            bbox=request_bbox,
            bbox_crs="EPSG:4326",
            working_crs=target_crs,
        )
        if request.job_type == JobType.road:
            road_sources = {
                source_id: path
                for source_id, path in {
                    "raw.osm.road": component_paths.get("raw.osm.road"),
                    "raw.overture.transportation": component_paths.get("raw.overture.transportation"),
                }.items()
                if path is not None
            }
            slices = [
                LargeAreaSlice(
                    name="road",
                    geometry_family="line",
                    sources=road_sources,
                    runner=run_road_tile,
                )
            ]
        elif request.job_type == JobType.water:
            water_sources = {
                source_id: path
                for source_id, path in {
                    "raw.osm.water": component_paths.get("raw.osm.water"),
                    "raw.hydrolakes.water": component_paths.get("raw.hydrolakes.water"),
                }.items()
                if path is not None
            }
            slices = [
                LargeAreaSlice(
                    name="water_polygon",
                    geometry_family="polygon",
                    sources=water_sources,
                    runner=run_water_polygon_tile,
                )
            ]
            line_supplement = component_paths.get("raw.hydrorivers.water") or component_paths.get(
                "raw.local.pakistan.waterways"
            )
            if component_paths.get("raw.osm.waterways") is not None and line_supplement is not None:
                line_sources = {"raw.osm.waterways": component_paths["raw.osm.waterways"]}
                if component_paths.get("raw.hydrorivers.water") is not None:
                    line_sources["raw.hydrorivers.water"] = component_paths["raw.hydrorivers.water"]
                else:
                    line_sources["raw.local.pakistan.waterways"] = component_paths["raw.local.pakistan.waterways"]
                slices.append(
                    LargeAreaSlice(
                        name="waterways_line",
                        geometry_family="line",
                        sources=line_sources,
                        runner=run_waterways_tile,
                    )
                )
        elif request.job_type == JobType.poi:
            if component_paths.get("raw.osm.poi") is None:
                raise ValueError("POI large-area runtime requires raw.osm.poi")
            poi_sources = {"raw.osm.poi": component_paths["raw.osm.poi"]}
            if component_paths.get("raw.gns.poi") is not None:
                poi_sources["raw.gns.poi"] = component_paths["raw.gns.poi"]
            elif component_paths.get("raw.geonames.poi") is not None:
                poi_sources["raw.geonames.poi"] = component_paths["raw.geonames.poi"]
            else:
                raise ValueError("POI large-area runtime requires raw.gns.poi or raw.geonames.poi")
            slices = [
                LargeAreaSlice(
                    name="poi",
                    geometry_family="point",
                    sources=poi_sources,
                    runner=run_poi_tile,
                )
            ]
        else:
            raise ValueError(f"Shared large-area runtime not wired for job_type={request.job_type.value}")
        try:
            result = LargeAreaRuntimeService(max_workers=1).run(
                run_id=run_id,
                job_type=request.job_type.value,
                tile_manifest=tile_manifest,
                slices=slices,
                output_dir=output_dir,
                target_crs=target_crs,
                parameters=self._extract_step_parameters(plan),
                on_event=lambda kind, details: self._record_large_area_runtime_event(
                    run_id=run_id,
                    plan=plan,
                    repair_records=repair_records,
                    kind=kind,
                    details=details,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            repair_records.append(
                RepairRecord(
                    attempt_no=self._max_attempt_no(repair_records) + 1,
                    strategy="large_area_runtime_execution",
                    step=step,
                    message=(
                        "Shared large-area runtime failed "
                        f"for step={step}, algorithm_id={algorithm_id}: {type(exc).__name__}: {exc}"
                    ),
                    success=False,
                    timestamp=_utc_now(),
                    reason_code="large_area_runtime_failed",
                    from_algorithm=algorithm_id,
                    to_algorithm=None,
                )
            )
            raise RuntimeError(
                "large-area runtime failed "
                f"for step={step}, algorithm_id={algorithm_id}: {type(exc).__name__}: {exc}"
            ) from exc
        self._record_large_area_runtime_completed(
            run_id=run_id,
            plan=plan,
            repair_records=repair_records,
            result=result,
        )
        return result.output_path, repair_records

    def _record_large_area_runtime_event(
        self,
        *,
        run_id: str,
        plan: WorkflowPlan,
        repair_records: List[RepairRecord],
        kind: str,
        details: Dict[str, object],
    ) -> None:
        progress_by_kind = {
            "large_area_tile_started": 62,
            "large_area_tile_completed": 74,
        }
        message_by_kind = {
            "large_area_tile_started": "Large-area tile execution started.",
            "large_area_tile_completed": "Large-area tile execution completed.",
        }
        self._update_status(
            run_id,
            RunPhase.running,
            progress=progress_by_kind.get(kind, 65),
            repair_records=repair_records,
            current_step=self._count_executable_steps(plan),
            attempt_no=self._max_attempt_no(repair_records),
            healing_summary=self._build_healing_summary(repair_records),
            plan_revision=self._extract_plan_revision(plan),
            checkpoint=self._checkpoint(stage="execution", plan_revision=self._extract_plan_revision(plan)),
            event_kind=kind,
            event_message=message_by_kind.get(kind, kind),
            event_details=details,
        )

    @staticmethod
    def _building_sources_from_semantic_contract(contract) -> tuple[dict[str, Path], dict[str, Path]]:
        from services.runtime_source_aliases import BUILDING_SOURCE_ALIASES

        vectors: dict[str, Path] = {}
        for source_id, entry in contract.sources.items():
            alias = BUILDING_SOURCE_ALIASES.get(source_id)
            if alias:
                vectors[alias] = Path(entry.artifact_path)
        rasters = {
            "building_height": Path(path)
            for path in contract.height_policy.get("raster_height_sources", {}).values()
            if Path(path).exists()
        }
        return vectors, rasters

    @staticmethod
    def _resolve_request_bbox(
        request: RunCreateRequest,
        *,
        resolved_aoi: ResolvedAOI | None,
    ) -> tuple[float, float, float, float] | None:
        value = request.trigger.spatial_extent
        if value:
            match = re.match(r"^bbox\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)\s*$", value)
            if match:
                return (
                    float(match.group(1)),
                    float(match.group(2)),
                    float(match.group(3)),
                    float(match.group(4)),
                )
        if resolved_aoi is not None:
            return tuple(float(value) for value in resolved_aoi.bbox)
        return None

    @staticmethod
    def _max_component_feature_count(component_coverage: Dict[str, object]) -> int:
        counts: list[int] = []
        for raw in (component_coverage or {}).values():
            if isinstance(raw, dict):
                value = raw.get("feature_count")
            else:
                value = getattr(raw, "feature_count", None)
            try:
                if value is not None:
                    counts.append(int(value))
            except Exception:  # noqa: BLE001
                continue
        return max(counts) if counts else 0

    @staticmethod
    def _extract_step_parameters(plan: WorkflowPlan) -> Dict[str, object]:
        for task in sorted(plan.tasks, key=lambda item: item.step):
            if task.is_transform or task.algorithm_id.startswith("algo.transform."):
                continue
            return dict(task.input.parameters or {})
        return {}

    def _bound_default_runtime(self) -> RuntimeDependencies:
        return RuntimeDependencies(
            settings=self._snapshot_default_runtime_settings(),
            llm_provider=self.llm_provider,
            planner=self.planner,
            executor=self.executor,
        )

    def _apply_default_runtime(self, runtime: RuntimeDependencies) -> None:
        self._default_runtime = runtime
        self.llm_provider = runtime.llm_provider
        self.planner = runtime.planner
        self.executor = runtime.executor

    def _snapshot_default_runtime_settings(self) -> EffectiveLLMSettings:
        return self._default_runtime.settings.model_copy(deep=True)

    def _resolve_run_runtime_settings(
        self,
        *,
        run_id: str,
        runtime_snapshot_id: str | None = None,
        runtime_settings: EffectiveLLMSettings | Dict[str, Any] | None = None,
    ) -> EffectiveLLMSettings:
        if runtime_settings is not None:
            return EffectiveLLMSettings.model_validate(runtime_settings)
        if runtime_snapshot_id:
            snapshot_settings = self.runtime_settings_service.load_runtime_snapshot(runtime_snapshot_id)
            if snapshot_settings is None:
                raise RuntimeSnapshotUnavailableError(
                    f"Runtime snapshot unavailable for run {run_id}: {runtime_snapshot_id}"
                )
            return snapshot_settings
        persisted_snapshot_id = self._load_run_runtime_snapshot_id(run_id)
        if persisted_snapshot_id:
            snapshot_settings = self.runtime_settings_service.load_runtime_snapshot(persisted_snapshot_id)
            if snapshot_settings is None:
                raise RuntimeSnapshotUnavailableError(
                    f"Runtime snapshot unavailable for run {run_id}: {persisted_snapshot_id}"
                )
            return snapshot_settings
        legacy_settings = self._load_run_runtime_settings(run_id)
        if legacy_settings is not None:
            return legacy_settings
        with self._lock:
            return self._snapshot_default_runtime_settings()

    def _build_runtime_dependencies(
        self,
        *,
        settings: EffectiveLLMSettings,
        llm_provider: Any | None = None,
    ) -> RuntimeDependencies:
        current_default = getattr(self, "_default_runtime", None)
        if llm_provider is None and current_default is not None and settings == current_default.settings:
            return self._bound_default_runtime()
        provider = llm_provider if llm_provider is not None else create_llm_provider(settings)
        planner = WorkflowPlanner(self.kg_repo, provider, artifact_registry=self.artifact_registry)
        executor = WorkflowExecutor(self.kg_repo, planner=planner)
        return RuntimeDependencies(
            settings=settings.model_copy(deep=True),
            llm_provider=provider,
            planner=planner,
            executor=executor,
        )

    def _resolve_default_llm_settings(self) -> EffectiveLLMSettings:
        provider_name = (self._read_env_value("GEOFUSION_LLM_PROVIDER") or "").lower()
        api_key = self._read_env_value("OPENAI_API_KEY") or self._read_env_value("GEOFUSION_LLM_API_KEY")
        base_url = self._read_env_value("GEOFUSION_LLM_BASE_URL")
        model = self._read_env_value("GEOFUSION_LLM_MODEL")
        timeout_sec = self._read_env_int("GEOFUSION_LLM_TIMEOUT_SEC")

        if provider_name in {"", "auto"}:
            provider_name = "openai" if api_key else "mock"
        elif provider_name == "openai" and not api_key:
            provider_name = "mock"
        elif provider_name not in {"openai", "mock"}:
            provider_name = "mock"

        if provider_name == "openai":
            return EffectiveLLMSettings(
                provider="openai",
                base_url=base_url or "https://api.openai.com/v1",
                api_key=api_key,
                model=model or "gpt-5.4-mini",
                timeout_sec=timeout_sec or 60,
            )
        return EffectiveLLMSettings(
            provider="mock",
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_sec=timeout_sec,
        )

    def _load_run_runtime_settings(self, run_id: str) -> EffectiveLLMSettings | None:
        path = self._runtime_settings_path(run_id)
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        return EffectiveLLMSettings.model_validate(json.loads(raw))

    def _runtime_settings_path(self, run_id: str) -> Path:
        return self.base_dir / run_id / "runtime_settings.json"

    def _persist_run_runtime_snapshot_id(self, run_id: str, runtime_snapshot_id: str) -> None:
        path = self._runtime_snapshot_id_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(runtime_snapshot_id, encoding="utf-8")

    def _load_run_runtime_snapshot_id(self, run_id: str) -> str | None:
        path = self._runtime_snapshot_id_path(run_id)
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8").strip()
        return raw or None

    def _runtime_snapshot_id_path(self, run_id: str) -> Path:
        return self.base_dir / run_id / "runtime_snapshot_id.txt"

    @staticmethod
    def _read_env_value(name: str) -> str | None:
        value = os.getenv(name)
        if value is None:
            return None
        value = value.strip()
        return value or None

    @classmethod
    def _read_env_int(cls, name: str) -> int | None:
        value = cls._read_env_value(name)
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def get_run(self, run_id: str) -> Optional[RunStatus]:
        path = self.base_dir / run_id / "run.json"
        if path.exists():
            return self._load_status(run_id)
        with self._lock:
            return self._runs.get(run_id)

    def get_plan(self, run_id: str) -> Optional[WorkflowPlan]:
        path = self._plan_path(run_id)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return WorkflowPlan.model_validate(payload)

    def get_artifact_path(self, run_id: str) -> Optional[Path]:
        status = self.get_run(run_id)
        if not status or not status.artifact:
            return None
        return Path(status.artifact.path)

    def get_audit_events(self, run_id: str) -> List[RunEvent]:
        path = self._audit_path(run_id)
        if not path.exists():
            return []
        events: List[RunEvent] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw:
                continue
            events.append(RunEvent.model_validate(json.loads(raw)))
        return events

    def collect_recoverable_runs(self, stale_after_seconds: int = 300) -> list[dict[str, Any]]:
        return collect_recoverable_runs(
            runs_root=self.base_dir,
            stale_after_seconds=stale_after_seconds,
        )

    def resume_run_from_checkpoint(self, run_id: str, recovery_action: str) -> dict[str, object]:
        run_dir = self.base_dir / run_id
        request_path = run_dir / "request.json"
        if not request_path.exists():
            raise FileNotFoundError(f"Missing request.json for run {run_id}")
        request = RunCreateRequest.model_validate(json.loads(request_path.read_text(encoding="utf-8")))
        status = self.get_run(run_id)
        if status is None:
            raise KeyError(run_id)

        input_dir = run_dir / "input"
        intermediate_dir = run_dir / "intermediate"
        output_dir = run_dir / "output"
        log_dir = run_dir / "logs"
        for directory in [input_dir, intermediate_dir, output_dir, log_dir]:
            directory.mkdir(parents=True, exist_ok=True)

        uploaded_zips = sorted(input_dir.glob("*.zip"))
        osm_zip_path = uploaded_zips[0] if request.input_strategy == RunInputStrategy.uploaded and uploaded_zips else None
        ref_zip_path = (
            uploaded_zips[1]
            if request.input_strategy == RunInputStrategy.uploaded and len(uploaded_zips) > 1
            else None
        )
        previous_checkpoint = dict(status.checkpoint or {})
        resume_stage_by_action = {
            "redispatch_full_run": "planning",
            "redispatch_from_validation": "validation",
            "redispatch_from_execution": "execution",
        }
        self._update_status(
            run_id,
            RunPhase.queued,
            progress=0,
            checkpoint=self._checkpoint(
                stage="queued",
                resume_stage=resume_stage_by_action.get(recovery_action, "planning"),
                plan_revision=status.plan_revision,
            ),
            event_kind="recovery_redispatch_started",
            event_message="Recovery redispatch started from checkpoint.",
            event_details={
                "recovery_action": recovery_action,
                "previous_checkpoint": previous_checkpoint,
            },
        )
        runtime_snapshot_id = self._load_run_runtime_snapshot_id(run_id)
        self.execute_run(
            run_id=run_id,
            request=request,
            osm_zip_path=osm_zip_path,
            ref_zip_path=ref_zip_path,
            intermediate_dir=intermediate_dir,
            output_dir=output_dir,
            log_dir=log_dir,
            runtime_snapshot_id=runtime_snapshot_id,
        )
        current = self.get_run(run_id)
        return {
            "run_id": run_id,
            "recovery_action": recovery_action,
            "phase": current.phase.value if current else "unknown",
            "checkpoint": current.checkpoint if current else {},
        }

    def _dispatch_run(
        self,
        run_id: str,
        request: RunCreateRequest,
        osm_zip_path: Path | None,
        ref_zip_path: Path | None,
        intermediate_dir: Path,
        output_dir: Path,
        log_dir: Path,
        runtime_snapshot_id: str,
    ) -> None:
        try:
            from worker.tasks import execute_run_task

            execute_run_task.delay(
                run_id=run_id,
                request=request.model_dump(mode="json"),
                osm_zip_path=str(osm_zip_path) if osm_zip_path is not None else None,
                ref_zip_path=str(ref_zip_path) if ref_zip_path is not None else None,
                intermediate_dir=str(intermediate_dir),
                output_dir=str(output_dir),
                log_dir=str(log_dir),
                runtime_snapshot_id=runtime_snapshot_id,
            )
        except Exception:  # noqa: BLE001
            self._pool.submit(
                self.execute_run,
                run_id=run_id,
                request=request,
                osm_zip_path=osm_zip_path,
                ref_zip_path=ref_zip_path,
                intermediate_dir=intermediate_dir,
                output_dir=output_dir,
                log_dir=log_dir,
                runtime_snapshot_id=runtime_snapshot_id,
            )

    def _record_feedback(
        self,
        run_id: str,
        request: RunCreateRequest,
        plan: WorkflowPlan,
        repair_records: List[RepairRecord],
        success: bool,
        failure_reason: Optional[str],
    ) -> None:
        try:
            output_data_type = self._extract_output_data_type(plan)
            intent_context = plan.context.get("intent", {})
            durable_metadata = {
                "planning_mode": plan.context.get("planning_mode"),
                "profile_source": intent_context.get("profile_source"),
                "task_bundle": intent_context.get("task_bundle"),
            }
            durable_metadata = {key: value for key, value in durable_metadata.items() if value is not None}
            feedback = ExecutionFeedback(
                run_id=run_id,
                job_type=request.job_type,
                trigger_type=request.trigger.type.value,
                success=success,
                disaster_type=request.trigger.disaster_type,
                pattern_id=self._extract_pattern_id(plan),
                algorithm_id=self._extract_algorithm_id(plan, repair_records),
                selected_data_source=self._extract_selected_data_source(plan),
                repaired=bool(repair_records),
                repair_count=len(repair_records),
                failure_reason=failure_reason,
            )
            self.kg_repo.record_execution_feedback(feedback)
            durable_record = DurableLearningRecord(
                record_id=f"dlr.{run_id}",
                run_id=run_id,
                job_type=request.job_type,
                trigger_type=request.trigger.type.value,
                success=success,
                disaster_type=request.trigger.disaster_type,
                pattern_id=feedback.pattern_id,
                algorithm_id=feedback.algorithm_id,
                selected_data_source=feedback.selected_data_source,
                output_data_type=output_data_type,
                target_crs=self._request_with_effective_target_crs(run_id, request).target_crs,
                repaired=bool(repair_records),
                repair_count=len(repair_records),
                failure_reason=failure_reason,
                plan_revision=self._extract_plan_revision(plan),
                metadata=durable_metadata,
                created_at=_utc_now(),
            )
            self.kg_repo.record_durable_learning_record(durable_record)
            if success:
                current = self.get_run(run_id)
                if current is not None:
                    self._update_status(
                        run_id,
                        current.phase,
                        progress=current.progress,
                        plan_revision=self._extract_plan_revision(plan),
                        event_kind="durable_learning_recorded",
                        event_message="Durable learning record was written for this run.",
                        event_details={
                            "record_id": durable_record.record_id,
                            "pattern_id": durable_record.pattern_id,
                            "algorithm_id": durable_record.algorithm_id,
                            "selected_data_source": durable_record.selected_data_source,
                        },
                    )
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("geofusion.run").warning("Failed to record execution feedback: %s", exc)

    def _update_status(
        self,
        run_id: str,
        phase: RunPhase,
        progress: Optional[int] = None,
        target_crs: Optional[str] = None,
        error: Optional[str] = None,
        started_at: Optional[str] = None,
        finished_at: Optional[str] = None,
        artifact: Optional[RunArtifactMeta] = None,
        plan_path: Optional[str] = None,
        validation_path: Optional[str] = None,
        decision_records: Optional[List[DecisionRecord]] = None,
        append_decision_record: Optional[DecisionRecord] = None,
        artifact_reuse: Optional[ArtifactReuseDecision] = None,
        repair_records: Optional[List[RepairRecord]] = None,
        current_step: Optional[int] = None,
        attempt_no: Optional[int] = None,
        healing_summary: Optional[Dict[str, object]] = None,
        failure_summary: Optional[str] = None,
        planning_telemetry: Optional[Dict[str, object]] = None,
        plan_revision: Optional[int] = None,
        checkpoint: Optional[Dict[str, object]] = None,
        document_paths: Optional[Dict[str, str]] = None,
        event_kind: Optional[str] = None,
        event_message: Optional[str] = None,
        event_details: Optional[Dict[str, object]] = None,
    ) -> None:
        current = self.get_run(run_id)
        if current is None:
            raise KeyError(run_id)
        with self._lock:
            current = self._runs[run_id]
            previous_phase = current.phase
            status_updated_at = _utc_now()
            current.phase = phase
            if progress is not None:
                current.progress = progress
            if target_crs is not None:
                current.target_crs = normalize_target_crs(target_crs)
            if error is not None or phase == RunPhase.succeeded:
                current.error = error
            if started_at is not None:
                current.started_at = started_at
            if finished_at is not None:
                current.finished_at = finished_at
            if artifact is not None:
                current.artifact = artifact
            if plan_path is not None:
                current.plan_path = plan_path
            if validation_path is not None:
                current.validation_path = validation_path
            if decision_records is not None:
                current.decision_records = decision_records
            if append_decision_record is not None:
                current.decision_records = [*current.decision_records, append_decision_record]
            if artifact_reuse is not None:
                current.artifact_reuse = artifact_reuse
            if repair_records is not None:
                current.repair_records = repair_records
            if current_step is not None:
                current.current_step = current_step
            if attempt_no is not None:
                current.attempt_no = attempt_no
            if healing_summary is not None:
                current.healing_summary = healing_summary
            if failure_summary is not None or phase == RunPhase.succeeded:
                current.failure_summary = failure_summary
            if planning_telemetry is not None:
                current.planning_telemetry = dict(planning_telemetry)
            if plan_revision is not None:
                current.plan_revision = plan_revision
            if checkpoint is not None:
                current.checkpoint = dict(checkpoint)
            if document_paths is not None:
                current.document_paths = dict(document_paths)
            current.updated_at = status_updated_at
            if event_kind or phase != previous_phase:
                event = RunEvent(
                    timestamp=status_updated_at,
                    kind=event_kind or "status_updated",
                    phase=current.phase,
                    message=event_message or f"Run phase updated to {current.phase.value}.",
                    plan_revision=current.plan_revision,
                    progress=current.progress,
                    attempt_no=current.attempt_no,
                    current_step=current.current_step,
                    details=dict(event_details or {}),
                )
                self._append_audit_event(current, event)
            self._runs[run_id] = current
            self._persist_status(current)

    def _persist_status(self, status: RunStatus) -> None:
        run_dir = self.base_dir / status.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        data = status.model_dump(mode="json")
        (run_dir / "run.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_status(self, run_id: str) -> Optional[RunStatus]:
        path = self.base_dir / run_id / "run.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        status = RunStatus.model_validate(payload)
        with self._lock:
            self._runs[run_id] = status
        return status

    @staticmethod
    def _persist_request(path: Path, request: RunCreateRequest) -> None:
        path.write_text(json.dumps(request.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _persist_plan(path: Path, plan: WorkflowPlan) -> None:
        ensure_plan_grounding_report(plan)
        payload = json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2)
        path.write_text(payload, encoding="utf-8")
        revision = AgentRunService._extract_plan_revision(plan)
        if revision > 0:
            path.with_name(f"plan-revision-{revision}.json").write_text(payload, encoding="utf-8")

    @staticmethod
    def _persist_validation(path: Path, plan: WorkflowPlan) -> None:
        payload = plan.validation.model_dump(mode="json") if plan.validation is not None else {}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _plan_path(self, run_id: str) -> Path:
        return self.base_dir / run_id / "plan.json"

    def _validation_path(self, run_id: str) -> Path:
        return self.base_dir / run_id / "validation.json"

    def _audit_path(self, run_id: str) -> Path:
        return self.base_dir / run_id / "audit.jsonl"

    @staticmethod
    def _checkpoint(
        *,
        stage: str,
        resume_stage: Optional[str] = None,
        plan_revision: Optional[int] = None,
        current_step: Optional[int] = None,
        attempt_no: Optional[int] = None,
    ) -> Dict[str, object]:
        checkpoint: Dict[str, object] = {"stage": stage}
        if resume_stage is not None:
            checkpoint["resume_stage"] = resume_stage
        if plan_revision is not None:
            checkpoint["plan_revision"] = plan_revision
        if current_step is not None:
            checkpoint["current_step"] = current_step
        if attempt_no is not None:
            checkpoint["attempt_no"] = attempt_no
        return checkpoint

    @staticmethod
    def _summarize_step_failure(*, repair_records: List[RepairRecord], current_step: int | None) -> str:
        for record in reversed(repair_records):
            if current_step is not None and record.step != current_step:
                continue
            if record.message:
                return record.message
        if current_step is None:
            return "Execution step failed."
        return f"Execution step {current_step} failed."

    @staticmethod
    def _build_step_failure_operator_note(
        *, repair_records: List[RepairRecord], current_step: int | None
    ) -> Dict[str, object]:
        matching_records = [
            record
            for record in repair_records
            if current_step is None or record.step == current_step
        ]
        reason_code = "primary_execution_failed"
        for record in matching_records:
            if record.reason_code == "primary_execution_failed":
                reason_code = record.reason_code
                break
        else:
            for record in reversed(matching_records):
                if record.reason_code:
                    reason_code = record.reason_code
                    break
        details = classify_failure_details(reason_code=reason_code)
        return {
            "root_cause": details.root_cause,
            "failure_category": details.failure_category,
            "action": details.suggested_action,
            "recoverable": details.recoverable,
            "suggested_action": details.suggested_action,
        }

    def _append_audit_event(self, status: RunStatus, event: RunEvent) -> None:
        path = Path(status.audit_path) if status.audit_path else self._audit_path(status.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False))
            handle.write("\n")
        status.audit_path = str(path)
        status.event_count += 1
        status.last_event = event

    @staticmethod
    def _extract_plan_revision(plan: Optional[WorkflowPlan]) -> int:
        if plan is None:
            return 0
        value = plan.context.get("plan_revision", 0)
        try:
            return int(value)
        except Exception:  # noqa: BLE001
            return 0

    @staticmethod
    def _extract_effective_parameters(plan: WorkflowPlan) -> Dict[str, Dict[str, object]]:
        return {
            str(task.step): dict(task.input.parameters or {})
            for task in plan.tasks
            if not task.is_transform
        }

    @staticmethod
    def _extract_pattern_id(plan: WorkflowPlan) -> Optional[str]:
        explicit = plan.context.get("selected_pattern_id")
        if explicit:
            return str(explicit)
        retrieval = plan.context.get("retrieval", {})
        candidates = retrieval.get("candidate_patterns", []) if isinstance(retrieval, dict) else []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            pattern_id = str(candidate.get("pattern_id") or "").strip()
            if not pattern_id:
                continue
            steps = candidate.get("steps")
            if not isinstance(steps, list):
                continue
            if AgentRunService._candidate_pattern_matches_plan(plan, steps):
                return pattern_id
        if candidates:
            return candidates[0].get("pattern_id")
        value = plan.context.get("pattern_id")
        return str(value) if value else None

    @staticmethod
    def _candidate_pattern_matches_plan(plan: WorkflowPlan, steps: Any) -> bool:
        executable_tasks = [task for task in sorted(plan.tasks, key=lambda item: item.step) if not task.is_transform]
        if not executable_tasks:
            return False
        normalized_steps = [step for step in steps if isinstance(step, dict)]
        if len(normalized_steps) < len(executable_tasks):
            return False
        for task, step in zip(executable_tasks, normalized_steps):
            if str(step.get("algorithm_id") or "").strip() != task.algorithm_id:
                return False
            if str(step.get("input_data_type") or "").strip() != task.input.data_type_id:
                return False
            if str(step.get("data_source_id") or "").strip() != task.input.data_source_id:
                return False
            if str(step.get("output_data_type") or "").strip() != task.output.data_type_id:
                return False
        return True

    @staticmethod
    def _extract_algorithm_id(plan: WorkflowPlan, repair_records: List[RepairRecord]) -> Optional[str]:
        for record in reversed(repair_records):
            if record.success and record.to_algorithm:
                return record.to_algorithm
            if record.success and record.from_algorithm:
                return record.from_algorithm
        for task in sorted(plan.tasks, key=lambda item: item.step):
            if not task.is_transform:
                return task.algorithm_id
        return None

    @staticmethod
    def _first_executable_step(plan: WorkflowPlan) -> int:
        for task in sorted(plan.tasks, key=lambda item: item.step):
            if not task.is_transform:
                return int(task.step)
        return 0

    @staticmethod
    def _algorithm_id_for_step(plan: WorkflowPlan, step: int) -> str | None:
        for task in sorted(plan.tasks, key=lambda item: item.step):
            if int(task.step) == int(step):
                return task.algorithm_id
        return AgentRunService._extract_algorithm_id(plan, [])

    @staticmethod
    def _extract_selected_data_source(plan: WorkflowPlan) -> Optional[str]:
        for task in sorted(plan.tasks, key=lambda item: item.step):
            if not task.is_transform:
                return task.input.data_source_id
        return None

    @staticmethod
    def _extract_required_input_data_type(plan: WorkflowPlan) -> Optional[str]:
        for task in sorted(plan.tasks, key=lambda item: item.step):
            if task.is_transform:
                continue
            data_type = str(task.input.data_type_id or "").strip()
            if data_type:
                return data_type
        return None

    @staticmethod
    def _extract_output_data_type(plan: WorkflowPlan) -> Optional[str]:
        ordered_tasks = sorted(plan.tasks, key=lambda item: item.step)
        for task in reversed(ordered_tasks):
            output_type = str(task.output.data_type_id or "").strip()
            if output_type:
                return output_type
        return None

    @staticmethod
    def _extract_resolved_aoi(plan: WorkflowPlan) -> ResolvedAOI | None:
        intent = plan.context.get("intent", {})
        raw = intent.get("resolved_aoi") if isinstance(intent, dict) else None
        if not isinstance(raw, dict):
            return None
        try:
            return ResolvedAOI(
                query=str(raw.get("query") or ""),
                display_name=str(raw.get("display_name") or ""),
                country_name=raw.get("country_name"),
                country_code=raw.get("country_code"),
                bbox=tuple(raw.get("bbox") or ()),
                confidence=float(raw.get("confidence") or 0.0),
                selection_reason=str(raw.get("selection_reason") or ""),
                candidates=tuple(),
            )
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _aoi_resolution_query(request: RunCreateRequest) -> str | None:
        if request.input_strategy != RunInputStrategy.task_driven_auto:
            return None
        if request.trigger.type != RunTriggerType.user_query:
            return None

        spatial_extent = (request.trigger.spatial_extent or "").strip()
        if spatial_extent:
            if AgentRunService._parse_bbox(spatial_extent) is not None:
                if request.trigger.force_aoi_resolution:
                    content = (request.trigger.content or "").strip()
                    return content or None
                return None
            return spatial_extent

        content = (request.trigger.content or "").strip()
        if not content:
            return None
        if request.trigger.force_aoi_resolution:
            return content
        if re.search(r"\b(for|in|around|within)\b", content, flags=re.IGNORECASE):
            return content
        return None

    @staticmethod
    def _should_resolve_aoi(request: RunCreateRequest) -> bool:
        return AgentRunService._aoi_resolution_query(request) is not None

    @staticmethod
    def _resolve_task_driven_source_id(plan: WorkflowPlan) -> Optional[str]:
        compatible_sources = AgentRunService._filter_disaster_compatible_sources(
            AgentRunService._extract_task_driven_compatible_sources(plan),
            plan,
        )
        compatible_source_ids = [item["source_id"] for item in compatible_sources]
        selected = AgentRunService._extract_selected_data_source(plan)
        if selected and selected != "upload.bundle":
            if compatible_source_ids and selected not in compatible_source_ids:
                return compatible_source_ids[0]
            return selected
        if compatible_source_ids:
            return compatible_source_ids[0]
        alternatives = AgentRunService._extract_alternative_sources(plan)
        return alternatives[0] if alternatives else None

    @staticmethod
    def _task_driven_source_candidates(plan: WorkflowPlan) -> list[str]:
        ordered: list[str] = []
        for source_id in [
            AgentRunService._resolve_task_driven_source_id(plan),
            *AgentRunService._extract_alternative_sources(plan),
        ]:
            if source_id and source_id != "upload.bundle" and source_id not in ordered:
                ordered.append(source_id)
        return ordered

    @staticmethod
    def _task_driven_input_signature(plan: WorkflowPlan) -> tuple[Optional[str], Optional[str]]:
        return (
            AgentRunService._resolve_task_driven_source_id(plan),
            AgentRunService._extract_required_input_data_type(plan),
        )

    @staticmethod
    def _extract_alternative_sources(plan: WorkflowPlan) -> List[str]:
        compatible_sources = AgentRunService._extract_task_driven_compatible_sources(plan)
        if compatible_sources:
            selected = AgentRunService._extract_selected_data_source(plan)
            compatible_ids = [item["source_id"] for item in compatible_sources]
            return [source_id for source_id in compatible_ids if source_id != selected]
        retrieval = plan.context.get("retrieval", {})
        candidates = retrieval.get("data_sources", []) if isinstance(retrieval, dict) else []
        ordered: List[str] = []
        for candidate in candidates:
            source_id = candidate.get("source_id")
            if not source_id:
                continue
            if source_id not in ordered and source_id != "upload.bundle":
                ordered.append(source_id)
        return ordered

    @staticmethod
    def _extract_task_driven_compatible_sources(plan: WorkflowPlan) -> List[Dict[str, Any]]:
        intent = plan.context.get("intent", {})
        if not isinstance(intent, dict):
            return []
        request_input_strategy = str(intent.get("request_input_strategy") or "").strip()
        if request_input_strategy != RunInputStrategy.task_driven_auto.value:
            return []

        required_input_type = AgentRunService._extract_required_input_data_type(plan)
        if not required_input_type:
            return []

        retrieval = plan.context.get("retrieval", {})
        candidates = retrieval.get("data_sources", []) if isinstance(retrieval, dict) else []
        compatible: List[Dict[str, Any]] = []
        for raw in candidates:
            if not isinstance(raw, dict):
                continue
            source_id = str(raw.get("source_id") or "").strip()
            if not source_id or source_id == "upload.bundle":
                continue
            supported_types = raw.get("supported_types")
            if not isinstance(supported_types, list) or required_input_type not in supported_types:
                continue
            metadata = raw.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            if not metadata.get("selectable_now", False):
                continue
            if metadata.get("runtime_status", "runtime_candidate") == "reservation_only":
                continue
            compatible.append(raw)
        return compatible

    @staticmethod
    def _filter_disaster_compatible_sources(
        sources: list[Dict[str, Any]],
        plan: WorkflowPlan,
    ) -> list[Dict[str, Any]]:
        disaster_type = str(getattr(plan.trigger, "disaster_type", None) or "").strip().casefold()
        if not disaster_type or not sources:
            return sources

        exact = [
            source
            for source in sources
            if disaster_type in AgentRunService._source_disaster_types(source)
        ]
        if exact:
            return exact

        generic = [
            source
            for source in sources
            if "generic" in AgentRunService._source_disaster_types(source)
        ]
        pure_generic = [
            source
            for source in generic
            if AgentRunService._source_disaster_types(source) == {"generic"}
        ]
        return pure_generic or generic or sources

    @staticmethod
    def _source_disaster_types(source: Dict[str, Any]) -> set[str]:
        values: list[object] = []
        values.append(source.get("disaster_types"))
        metadata = source.get("metadata")
        if isinstance(metadata, dict):
            values.append(metadata.get("disaster_types"))
            values.append(metadata.get("scenario_focus"))
        source_id = str(source.get("source_id") or "").casefold()
        for token in ("flood", "earthquake", "typhoon", "generic"):
            if f".{token}." in source_id or source_id.startswith(f"{token}.") or source_id.endswith(f".{token}"):
                values.append(token)

        normalized: set[str] = set()
        for value in values:
            if isinstance(value, str):
                parts = [value]
            elif isinstance(value, list):
                parts = value
            elif isinstance(value, tuple):
                parts = list(value)
            elif isinstance(value, set):
                parts = list(value)
            else:
                continue
            for item in parts:
                text = str(item or "").strip().casefold()
                if text:
                    normalized.add(text)
        return normalized

    @staticmethod
    def _extract_named_paths(plan: WorkflowPlan, key: str) -> Dict[str, Path]:
        raw = plan.context.get(key, {})
        if not isinstance(raw, dict):
            return {}
        paths: Dict[str, Path] = {}
        for name, value in raw.items():
            if isinstance(name, str) and isinstance(value, (str, Path)) and str(value).strip():
                paths[name] = Path(value)
        return paths

    def _build_planning_decisions(self, plan: WorkflowPlan) -> List[DecisionRecord]:
        decisions: List[DecisionRecord] = []
        for builder in (
            self._build_pattern_selection_decision,
            self._build_data_source_selection_decision,
            self._build_artifact_reuse_selection_decision,
            self._build_parameter_strategy_decision,
            self._build_output_schema_policy_decision,
        ):
            decision = builder(plan)
            if decision is not None:
                decisions.append(decision)
        return decisions

    def _build_pattern_selection_decision(self, plan: WorkflowPlan) -> Optional[DecisionRecord]:
        retrieval = plan.context.get("retrieval", {})
        raw_patterns = retrieval.get("candidate_patterns", []) if isinstance(retrieval, dict) else []
        learning_summaries = self._durable_pattern_summaries_by_id(retrieval)
        actual_selected_pattern_id = str(plan.context.get("selected_pattern_id") or "").strip()
        if not actual_selected_pattern_id:
            for raw in raw_patterns:
                if not isinstance(raw, dict):
                    continue
                pattern_id = str(raw.get("pattern_id") or "").strip()
                steps = raw.get("steps")
                if pattern_id and isinstance(steps, list) and self._candidate_pattern_matches_plan(plan, steps):
                    actual_selected_pattern_id = pattern_id
                    break
        candidates: List[CandidateScoreInput] = []
        for raw in raw_patterns:
            if not isinstance(raw, dict):
                continue
            pattern_id = str(raw.get("pattern_id") or "").strip()
            if not pattern_id:
                continue
            success_rate = self._to_unit_interval(raw.get("success_rate"))
            learning_adjustment = self._pattern_learning_adjustment(pattern_id, learning_summaries)
            meta = {}
            if pattern_id in learning_summaries:
                meta["durable_learning_summary"] = learning_summaries[pattern_id]
            candidates.append(
                CandidateScoreInput(
                    candidate_id=pattern_id,
                    success_rate=success_rate,
                    accuracy=success_rate,
                    learning_adjustment=learning_adjustment,
                    meta=meta,
                )
            )
        if not candidates:
            fallback_pattern_id = self._extract_pattern_id(plan)
            if fallback_pattern_id:
                candidates.append(
                    CandidateScoreInput(candidate_id=fallback_pattern_id, success_rate=1.0, accuracy=1.0)
                )
        if not candidates:
            return None
        decision = self.policy_engine.select("pattern_selection", candidates)
        if actual_selected_pattern_id and any(
            candidate.candidate_id == actual_selected_pattern_id for candidate in decision.candidates
        ):
            selected = next(candidate for candidate in decision.candidates if candidate.candidate_id == actual_selected_pattern_id)
            decision = decision.model_copy(
                update={
                    "selected_id": selected.candidate_id,
                    "selected_score": selected.score,
                    "rationale": (
                        f"Selected '{selected.candidate_id}' because the executable plan resolves to that workflow pattern. "
                        f"Candidate scoring remains attached for audit comparison; policy-only winner before execution was "
                        f"'{decision.selected_id}'."
                    ),
                }
            )
        evidence_refs = ["context.retrieval.candidate_patterns", "policy:deterministic_weighted_sum"]
        if any(candidate.learning_adjustment is not None for candidate in candidates):
            evidence_refs.append("context.retrieval.durable_learning_summaries.patterns")
        return decision.model_copy(
            update={"evidence_refs": evidence_refs}
        )

    @staticmethod
    def _durable_pattern_summaries_by_id(retrieval: object) -> Dict[str, Dict[str, object]]:
        if not isinstance(retrieval, dict):
            return {}
        durable = retrieval.get("durable_learning_summaries")
        if not isinstance(durable, dict):
            return {}
        patterns = durable.get("patterns")
        if not isinstance(patterns, list):
            return {}
        summaries: Dict[str, Dict[str, object]] = {}
        for raw in patterns:
            if not isinstance(raw, dict):
                continue
            entity_id = str(raw.get("entity_id") or "").strip()
            if entity_id:
                summaries[entity_id] = dict(raw)
        return summaries

    @staticmethod
    def _pattern_learning_adjustment(pattern_id: str, summaries: Dict[str, Dict[str, object]]) -> Optional[float]:
        summary = summaries.get(pattern_id)
        if not summary:
            return None
        try:
            total_runs = int(summary.get("total_runs") or 0)
            success_count = int(summary.get("success_count") or 0)
        except (TypeError, ValueError):
            return None
        if total_runs < 2:
            return None
        success_ratio = max(0.0, min(1.0, success_count / total_runs))
        adjustment = (success_ratio - 0.5) * 0.2
        return round(max(-0.10, min(0.10, adjustment)), 6)

    def _build_data_source_selection_decision(self, plan: WorkflowPlan) -> Optional[DecisionRecord]:
        retrieval = plan.context.get("retrieval", {})
        raw_sources = retrieval.get("data_sources", []) if isinstance(retrieval, dict) else []
        compatible_task_driven_sources = self._extract_task_driven_compatible_sources(plan)
        if compatible_task_driven_sources:
            raw_sources = self._filter_disaster_compatible_sources(compatible_task_driven_sources, plan)
        candidates: List[CandidateScoreInput] = []
        for raw in raw_sources:
            if not isinstance(raw, dict):
                continue
            source_id = str(raw.get("source_id") or "").strip()
            if not source_id:
                continue
            candidates.append(
                CandidateScoreInput(
                    candidate_id=source_id,
                    data_quality=self._to_unit_interval(raw.get("quality_score")),
                    freshness=self._to_unit_interval(raw.get("freshness_score")),
                    meta={
                        "source_name": raw.get("source_name"),
                        "source_kind": raw.get("source_kind"),
                        "quality_tier": raw.get("quality_tier"),
                        "freshness_category": raw.get("freshness_category"),
                        "supported_types": raw.get("supported_types", []),
                    },
                )
            )
        if not candidates:
            fallback_source_id = self._extract_selected_data_source(plan)
            if not fallback_source_id:
                return None
            candidates.append(
                CandidateScoreInput(
                    candidate_id=fallback_source_id,
                    data_quality=1.0,
                    freshness=1.0,
                    meta={"selection_source": "task_input"},
                )
            )
        evidence_refs = ["context.retrieval.data_sources", "policy:deterministic_weighted_sum"]
        if str(getattr(plan.trigger, "disaster_type", None) or "").strip():
            evidence_refs.append("policy:disaster_source_compatibility")
        decision = self.policy_engine.select("data_source_selection", candidates).model_copy(
            update={"evidence_refs": evidence_refs}
        )
        for task in plan.tasks:
            if not task.is_transform:
                task.input.data_source_id = decision.selected_id
        return decision

    def _build_artifact_reuse_selection_decision(self, plan: WorkflowPlan) -> Optional[DecisionRecord]:
        retrieval = plan.context.get("retrieval", {})
        raw_candidates = retrieval.get("reusable_artifacts", []) if isinstance(retrieval, dict) else []
        candidates: List[CandidateScoreInput] = [
            CandidateScoreInput(
                candidate_id="fresh_execution",
                freshness=0.5,
                reuse=0.0,
                stability=0.8,
                meta={"selection_source": "fallback_when_no_safe_reuse_candidate"},
            )
        ]
        for raw in raw_candidates:
            if not isinstance(raw, dict):
                continue
            artifact_id = str(raw.get("artifact_id") or "").strip()
            if not artifact_id:
                continue
            candidates.append(
                CandidateScoreInput(
                    candidate_id=artifact_id,
                    freshness=0.9,
                    reuse=1.0,
                    stability=0.85,
                    meta={
                        "artifact_path": raw.get("artifact_path"),
                        "created_at": raw.get("created_at"),
                        "bbox": raw.get("bbox"),
                        "output_data_type": raw.get("output_data_type"),
                        "target_crs": raw.get("target_crs"),
                        "schema_policy_id": raw.get("schema_policy_id"),
                        "compatibility_basis": raw.get("compatibility_basis"),
                    },
                )
            )
        decision = self.policy_engine.select("artifact_reuse_selection", candidates)
        return decision.model_copy(
            update={"evidence_refs": ["context.retrieval.reusable_artifacts", "policy:deterministic_weighted_sum"]}
        )

    def _build_parameter_strategy_decision(self, plan: WorkflowPlan) -> Optional[DecisionRecord]:
        task_summaries: List[Dict[str, object]] = []
        total_specs = 0
        total_bound = 0
        overridden_keys: List[str] = []
        for task in sorted(plan.tasks, key=lambda item: item.step):
            if task.is_transform:
                continue
            specs = self.kg_repo.get_parameter_specs(task.algorithm_id)
            defaults = {spec.key: spec.default for spec in specs}
            bound = dict(task.input.parameters or {})
            total_specs += len(specs)
            total_bound += sum(1 for spec in specs if spec.key in bound and bound.get(spec.key) is not None)
            overridden = sorted(
                key for key, value in bound.items()
                if key in defaults and defaults.get(key) is not None and defaults.get(key) != value
            )
            overridden_keys.extend(overridden)
            task_summaries.append(
                {
                    "step": task.step,
                    "algorithm_id": task.algorithm_id,
                    "parameter_keys": sorted(bound.keys()),
                    "overridden_keys": overridden,
                }
            )
        if not task_summaries:
            return None
        completeness = 1.0 if total_specs == 0 else min(1.0, total_bound / total_specs)
        strategy = "kg_defaults_with_overrides" if overridden_keys else "kg_defaults_only"
        decision = self.policy_engine.select(
            "parameter_strategy",
            [
                CandidateScoreInput(
                    candidate_id=strategy,
                    success_rate=completeness,
                    stability=1.0 if completeness == 1.0 else 0.3,
                    meta={
                        "steps": task_summaries,
                        "overridden_keys": sorted(dict.fromkeys(overridden_keys)),
                        "total_specs": total_specs,
                        "total_bound": total_bound,
                    },
                )
            ],
        )
        return decision.model_copy(
            update={"evidence_refs": ["plan.tasks.input.parameters", "kg.parameter_specs", "policy:deterministic_weighted_sum"]}
        )

    def _build_output_schema_policy_decision(self, plan: WorkflowPlan) -> Optional[DecisionRecord]:
        retrieval = plan.context.get("retrieval", {})
        raw_policies = retrieval.get("output_schema_policies", {}) if isinstance(retrieval, dict) else {}
        if not isinstance(raw_policies, dict):
            raw_policies = {}
        if not raw_policies:
            for task in plan.tasks:
                if task.is_transform:
                    continue
                policy = self.kg_repo.get_output_schema_policy(task.output.data_type_id)
                if policy is None:
                    continue
                raw_policies[task.output.data_type_id] = {
                    "policy_id": policy.policy_id,
                    "output_type": policy.output_type,
                    "job_type": policy.job_type.value,
                    "retention_mode": policy.retention_mode,
                    "required_fields": policy.required_fields,
                    "optional_fields": policy.optional_fields,
                    "rename_hints": policy.rename_hints,
                    "compatibility_basis": policy.compatibility_basis,
                }
        candidates: List[CandidateScoreInput] = []
        for output_type, raw in raw_policies.items():
            if not isinstance(raw, dict):
                continue
            policy_id = str(raw.get("policy_id") or output_type).strip()
            candidates.append(
                CandidateScoreInput(
                    candidate_id=policy_id,
                    stability=1.0,
                    meta={
                        "output_type": output_type,
                        "retention_mode": raw.get("retention_mode"),
                        "required_fields": raw.get("required_fields", []),
                        "optional_fields": raw.get("optional_fields", []),
                        "rename_hints": raw.get("rename_hints", {}),
                        "compatibility_basis": raw.get("compatibility_basis"),
                    },
                )
            )
        if not candidates:
            return None
        decision = self.policy_engine.select("output_schema_policy", candidates)
        return decision.model_copy(
            update={"evidence_refs": ["context.retrieval.output_schema_policies", "policy:deterministic_weighted_sum"]}
        )

    def _build_artifact_reuse_decision(self, plan: WorkflowPlan) -> ArtifactReuseDecision:
        retrieval = plan.context.get("retrieval", {})
        raw_candidates = retrieval.get("reusable_artifacts", []) if isinstance(retrieval, dict) else []
        if raw_candidates:
            first = raw_candidates[0] if isinstance(raw_candidates[0], dict) else {}
            first_id = first.get("artifact_id")
            rationale = (
                f"Planner found {len(raw_candidates)} reusable artifact candidate(s)"
                + (f" (top={first_id})." if first_id else ".")
                + " Runtime will attempt reuse before falling back to fresh execution."
            )
            return ArtifactReuseDecision(
                reused=False,
                freshness_status="candidate_available",
                rationale=rationale,
            )
        return ArtifactReuseDecision(
            reused=False,
            freshness_status="not_available",
            rationale="No reusable artifact candidates were found in planner retrieval context.",
        )

    def _attempt_artifact_reuse(
        self,
        *,
        run_id: str,
        request: RunCreateRequest,
        plan: WorkflowPlan,
        output_dir: Path,
    ) -> Optional[ReuseResult]:
        try:
            reuse_result = self.artifact_reuse_service.try_reuse(request=request, plan=plan, output_dir=output_dir)
        except Exception as exc:  # noqa: BLE001
            self._update_status(
                run_id,
                RunPhase.running,
                progress=45,
                plan_revision=self._extract_plan_revision(plan),
                checkpoint=self._checkpoint(stage="execution", plan_revision=self._extract_plan_revision(plan)),
                event_kind="artifact_reuse_fallback",
                event_message="Artifact reuse candidate was available but reuse materialization failed; falling back to fresh execution.",
                event_details={"error": f"{type(exc).__name__}: {exc}"},
            )
            return None

        if reuse_result is None:
            return None

        decision = ArtifactReuseDecision(
            reused=True,
            artifact_id=reuse_result.source_record.artifact_id,
            freshness_status=f"{reuse_result.mode}_reused",
            rationale=(
                f"Reused artifact {reuse_result.source_record.artifact_id} via "
                f"{reuse_result.mode} materialization."
            ),
        )
        self._update_status(
            run_id,
            RunPhase.running,
            progress=75,
            artifact_reuse=decision,
            plan_revision=self._extract_plan_revision(plan),
            checkpoint=self._checkpoint(stage="execution", plan_revision=self._extract_plan_revision(plan)),
            event_kind="artifact_reuse_applied",
            event_message=f"Applied {reuse_result.mode} artifact reuse and skipped fresh execution.",
            event_details={
                "reuse_mode": reuse_result.mode,
                "source_artifact_id": reuse_result.source_record.artifact_id,
                "source_artifact_path": reuse_result.source_record.artifact_path,
            },
        )
        return reuse_result

    def _build_replan_decision(
        self,
        *,
        can_replan: bool,
        failed_step: Optional[int],
        current_revision: int,
        failure_message: str,
    ) -> DecisionRecord:
        if can_replan:
            candidates = [
                CandidateScoreInput(
                    candidate_id="replan",
                    success_rate=0.95,
                    accuracy=0.95,
                    data_quality=0.70,
                    stability=0.75,
                    freshness=0.60,
                    reuse=0.40,
                ),
                CandidateScoreInput(
                    candidate_id="fail",
                    success_rate=0.05,
                    accuracy=0.05,
                    data_quality=0.90,
                    stability=0.95,
                    freshness=0.80,
                    reuse=0.80,
                ),
            ]
        else:
            candidates = [
                CandidateScoreInput(
                    candidate_id="replan",
                    success_rate=0.05,
                    accuracy=0.05,
                    data_quality=0.20,
                    stability=0.20,
                    freshness=0.50,
                    reuse=0.40,
                ),
                CandidateScoreInput(
                    candidate_id="fail",
                    success_rate=0.95,
                    accuracy=0.95,
                    data_quality=0.90,
                    stability=0.95,
                    freshness=0.80,
                    reuse=0.80,
                ),
            ]
        decision = self.policy_engine.select("replan_or_fail", candidates)
        rationale = (
            f"{decision.rationale} failure_step={failed_step}; "
            f"current_revision={current_revision}; max_revisions={self.max_plan_revisions}; "
            f"error={failure_message}"
        )
        return decision.model_copy(
            update={
                "rationale": rationale,
                "evidence_refs": ["repair_records", "plan_revision_limit", "policy:deterministic_weighted_sum"],
            }
        )

    @staticmethod
    def _to_unit_interval(value: object) -> Optional[float]:
        try:
            numeric = float(value)
        except Exception:  # noqa: BLE001
            return None
        if numeric < 0.0:
            return 0.0
        if numeric > 1.0:
            return 1.0
        return numeric

    @staticmethod
    def _count_executable_steps(plan: WorkflowPlan) -> int:
        return sum(1 for task in plan.tasks if not task.is_transform)

    @staticmethod
    def _max_attempt_no(repair_records: List[RepairRecord]) -> int:
        return max((record.attempt_no for record in repair_records), default=0)

    @staticmethod
    def _build_healing_summary(repair_records: List[RepairRecord]) -> Dict[str, object]:
        if not repair_records:
            return {
                "attempted_repairs": 0,
                "successful_repairs": 0,
                "failed_repairs": 0,
                "last_reason_code": None,
                "strategies": [],
            }
        return {
            "attempted_repairs": len(repair_records),
            "successful_repairs": sum(1 for record in repair_records if record.success),
            "failed_repairs": sum(1 for record in repair_records if not record.success),
            "last_reason_code": repair_records[-1].reason_code,
            "strategies": list(dict.fromkeys(record.strategy for record in repair_records)),
        }

    @staticmethod
    def _build_failure_summary(error: str, repair_records: List[RepairRecord]) -> str:
        if not repair_records:
            details = classify_failure_details(error=error, reason_code=error)
            return (
                f"{error} | failure_category={details.failure_category}"
                f" | suggested_action={details.suggested_action}"
            )
        last = repair_records[-1]
        reason = last.reason_code or "unknown_reason"
        details = classify_failure_details(error=error, reason_code=last.reason_code)
        return (
            f"{error} | failure_category={details.failure_category}"
            f" | suggested_action={details.suggested_action}"
            f" | last_repair={last.strategy}:{reason}"
        )

    @staticmethod
    def _infer_failed_step(repair_records: List[RepairRecord]) -> Optional[int]:
        if not repair_records:
            return None
        return repair_records[-1].step

    @staticmethod
    def _build_logger(run_id: str, log_path: Path) -> logging.Logger:
        logger = logging.getLogger(f"agent_run_{run_id}")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        if logger.handlers:
            return logger

        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        return logger

    @staticmethod
    def _create_kg_repo() -> KGRepository:
        return create_kg_repository()

    @staticmethod
    def _build_geocoder() -> NominatimGeocoder:
        return NominatimGeocoder(
            user_agent=os.getenv("GEOFUSION_GEOCODER_USER_AGENT", "GeoFusion/1.0 (+https://openai.com/codex)"),
            max_retries=_as_int(os.getenv("GEOFUSION_GEOCODER_RETRIES"), default=3),
            timeout_seconds=_as_int(os.getenv("GEOFUSION_GEOCODER_TIMEOUT"), default=30),
        )

    def _build_raw_vector_source_service(self) -> RawVectorSourceService:
        project_root = Path(__file__).resolve().parents[1]
        return RawVectorSourceService(
            root_dir=project_root,
            registry=self.artifact_registry,
            cache_dir=self.base_dir / "raw_source_cache",
        )

    def _build_input_bundle_providers(self) -> list[object]:
        providers: list[object] = []
        try:
            providers.append(
                LocalBundleCatalogProvider(
                    Path(__file__).resolve().parents[1],
                    raw_source_service=self.raw_vector_source_service,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("geofusion.run").warning(
                "Failed to initialize local bundle catalog provider: %s",
                exc,
            )
        return providers


agent_run_service = AgentRunService(base_dir=Path(os.getenv("GEOFUSION_RUNS_ROOT", "runs")))
