from __future__ import annotations

import json
import logging
import os
import re
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional

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
from services.artifact_registry import ArtifactRecord, ArtifactRegistry
from services.artifact_reuse_policy import get_artifact_reuse_max_age_seconds
from services.artifact_reuse_service import ArtifactReuseService, ReuseResult
from services.aoi_resolution_service import AOIResolutionService, NominatimGeocoder, ResolvedAOI
from services.input_acquisition_service import InputAcquisitionService, ResolvedRunInputs
from services.local_bundle_catalog import LocalBundleCatalogProvider
from services.raw_vector_source_service import RawVectorSourceService
from utils.crs import normalize_target_crs
from utils.shp_zip import validate_zip_has_shapefile, zip_shapefile_bundle


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


class AgentRunService:
    def __init__(
        self,
        base_dir: Path,
        max_workers: int = 2,
        kg_repo: Optional[KGRepository] = None,
    ) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._runs: Dict[str, RunStatus] = {}
        self._lock = Lock()
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="agent-run")

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
        self.artifact_reuse_service = ArtifactReuseService(self.artifact_registry)
        self.planner = WorkflowPlanner(self.kg_repo, self.llm_provider, artifact_registry=self.artifact_registry)
        self.validator = WorkflowValidator(self.kg_repo)
        self.executor = WorkflowExecutor(self.kg_repo, planner=self.planner)
        self.policy_engine = PolicyEngine(policy_version="v2")

        self.dispatch_eager = _as_bool(os.getenv("GEOFUSION_CELERY_EAGER", "1"), default=True)
        # Total plan revisions allowed for a single run, including the initial revision.
        self.max_plan_revisions = max(1, _as_int(os.getenv("GEOFUSION_MAX_PLAN_REVISIONS"), default=2))

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True)
        close = getattr(self.kg_repo, "close", None)
        if callable(close):
            close()

    def create_run(
        self,
        request: RunCreateRequest,
        osm_zip_name: str | None,
        osm_zip_bytes: bytes | None,
        ref_zip_name: str | None,
        ref_zip_bytes: bytes | None,
    ) -> RunStatus:
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

        status = RunStatus(
            run_id=run_id,
            job_type=request.job_type,
            trigger=request.trigger,
            phase=RunPhase.queued,
            progress=0,
            target_crs=normalize_target_crs(request.target_crs),
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
            plan_revision=0,
            event_count=0,
            last_event=None,
            created_at=_utc_now(),
            started_at=None,
            finished_at=None,
        )
        with self._lock:
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
    ) -> None:
        logger = self._build_logger(run_id, log_dir / "run.log")
        plan: Optional[WorkflowPlan] = None
        repair_records: List[RepairRecord] = []

        try:
            self._update_status(
                run_id,
                RunPhase.planning,
                progress=5,
                started_at=_utc_now(),
                error=None,
                failure_summary=None,
                current_step=0,
                event_kind="run_started",
                event_message=f"Run started for job_type={request.job_type.value}.",
            )
            logger.info("Run started: %s (%s)", run_id, request.job_type.value)

            plan = self.run_planning_stage(run_id=run_id, request=request)
            logger.info("Planning stage completed with revision=%s", plan.context.get("plan_revision", 0))

            plan = self.run_validation_stage(run_id=run_id, plan=plan)
            logger.info("Validation stage completed; valid=%s", getattr(plan.validation, "valid", None))

            reuse_result = self._attempt_artifact_reuse(
                run_id=run_id,
                request=request,
                plan=plan,
                output_dir=output_dir,
            )
            if reuse_result is not None:
                artifact = reuse_result.artifact
                self._record_feedback(
                    run_id=run_id,
                    request=request,
                    plan=plan,
                    repair_records=repair_records,
                    success=True,
                    failure_reason=None,
                )
                self._register_artifact(
                    run_id=run_id,
                    request=request,
                    plan=plan,
                    artifact=artifact,
                    repair_records=repair_records,
                    extra_meta={
                        "reuse_mode": reuse_result.mode,
                        "parent_artifact_id": reuse_result.source_record.artifact_id,
                    },
                )
                self._update_status(
                    run_id,
                    RunPhase.succeeded,
                    progress=100,
                    finished_at=_utc_now(),
                    artifact=artifact,
                    repair_records=repair_records,
                    current_step=0,
                    attempt_no=self._max_attempt_no(repair_records),
                    healing_summary=self._build_healing_summary(repair_records),
                    failure_summary=None,
                    error=None,
                    plan_revision=self._extract_plan_revision(plan),
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
                request=request,
                plan=plan,
                input_dir=input_dir,
                osm_zip_path=osm_zip_path,
                ref_zip_path=ref_zip_path,
                resolved_aoi=resolved_aoi,
            )
            if resolved_inputs is not None:
                event_details = {
                    "input_strategy": request.input_strategy.value,
                    "source_mode": resolved_inputs.source_mode,
                    "source_id": resolved_inputs.source_id,
                    "cache_hit": resolved_inputs.cache_hit,
                    "version_token": resolved_inputs.version_token,
                    "osm_zip_name": resolved_inputs.osm_zip_path.name,
                    "ref_zip_name": resolved_inputs.ref_zip_path.name,
                }
                if resolved_aoi is not None:
                    event_details["resolved_aoi"] = {
                        "display_name": resolved_aoi.display_name,
                        "country_code": resolved_aoi.country_code,
                        "country_name": resolved_aoi.country_name,
                        "bbox": list(resolved_aoi.bbox),
                    }
                self._update_status(
                    run_id,
                    RunPhase.running,
                    progress=50,
                    plan_revision=self._extract_plan_revision(plan),
                    event_kind="task_inputs_resolved",
                    event_message="Task-driven input bundles prepared for execution.",
                    event_details=event_details,
                )
                logger.info(
                    "Task-driven inputs resolved: mode=%s source_id=%s cache_hit=%s",
                    resolved_inputs.source_mode,
                    resolved_inputs.source_id,
                    resolved_inputs.cache_hit,
                )

            while True:
                try:
                    fused_shp, repair_records = self.run_execution_stage(
                        run_id=run_id,
                        request=request,
                        plan=plan,
                        osm_zip_path=osm_zip_path,
                        ref_zip_path=ref_zip_path,
                        intermediate_dir=intermediate_dir,
                        output_dir=output_dir,
                        repair_records=repair_records,
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

                    replanned = self.planner.replan_from_error(
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
                        event_kind="replan_applied",
                        event_message=f"Applied replanned workflow revision {replanned_revision}.",
                        event_details={"failed_step": failed_step, "previous_revision": current_revision},
                    )
                    plan = self.run_validation_stage(run_id=run_id, plan=plan)
                    logger.info("Healing replan completed with revision=%s", self._extract_plan_revision(plan))
            logger.info("Execution stage completed: %s", fused_shp)

            artifact = self.run_writeback_stage(
                run_id=run_id,
                request=request,
                plan=plan,
                fused_shp=fused_shp,
                repair_records=repair_records,
                output_dir=output_dir,
            )

            self._update_status(
                run_id,
                RunPhase.succeeded,
                progress=100,
                finished_at=_utc_now(),
                artifact=artifact,
                repair_records=repair_records,
                current_step=self._count_executable_steps(plan),
                attempt_no=self._max_attempt_no(repair_records),
                healing_summary=self._build_healing_summary(repair_records),
                failure_summary=None,
                error=None,
                plan_revision=self._extract_plan_revision(plan),
                event_kind="run_succeeded",
                event_message="Run completed successfully and artifact is ready.",
            )
            logger.info("Run succeeded.")
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
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
                event_kind="run_failed",
                event_message="Run failed.",
                event_details={"error": err},
            )
            if plan is not None:
                self._record_feedback(
                    run_id=run_id,
                    request=request,
                    plan=plan,
                    repair_records=repair_records,
                    success=False,
                    failure_reason=err,
                )
        finally:
            for handler in list(logger.handlers):
                logger.removeHandler(handler)
                handler.close()

    def run_planning_stage(self, run_id: str, request: RunCreateRequest) -> WorkflowPlan:
        resolved_aoi: ResolvedAOI | None = None
        if self._should_resolve_aoi(request):
            try:
                resolved_aoi = self.aoi_resolution_service.resolve(request.trigger.content)
                self._update_status(
                    run_id,
                    RunPhase.planning,
                    progress=12,
                    event_kind="aoi_resolved",
                    event_message=f"Resolved AOI for {resolved_aoi.display_name}.",
                    event_details={
                        "query": resolved_aoi.query,
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
                    event_kind="aoi_resolution_failed",
                    event_message="AOI resolution failed before planning.",
                    event_details={
                        "query": request.trigger.content,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )
                raise

        previous_override = self.planner.context_builder.resolved_aoi_override
        self.planner.context_builder.resolved_aoi_override = resolved_aoi
        try:
            plan = self.planner.create_plan(run_id=run_id, job_type=request.job_type, trigger=request.trigger)
        finally:
            self.planner.context_builder.resolved_aoi_override = previous_override
        if resolved_aoi is not None:
            intent = dict(plan.context.get("intent", {}))
            if intent.get("resolved_aoi") is None:
                intent["resolved_aoi"] = resolved_aoi.to_dict()
                plan.context = {**plan.context, "intent": intent}
        planning_decisions = self._build_planning_decisions(plan)
        artifact_reuse = self._build_artifact_reuse_decision(plan)
        plan_path = self._plan_path(run_id)
        self._persist_plan(plan_path, plan)
        event_details = {
            "workflow_id": plan.workflow_id,
            "effective_parameters": self._extract_effective_parameters(plan),
            "selected_decisions": {
                decision.decision_type: decision.selected_id for decision in planning_decisions
            },
            "planning_mode": plan.context.get("planning_mode"),
            "profile_source": plan.context.get("intent", {}).get("profile_source"),
            "task_bundle": plan.context.get("intent", {}).get("task_bundle"),
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
    ) -> tuple[Path, List[RepairRecord]]:
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
            target_crs=normalize_target_crs(request.target_crs),
            field_mapping=request.field_mapping,
            debug=request.debug,
            alternative_data_sources=self._extract_alternative_sources(plan),
        )
        fused_shp = self.executor.execute_plan(plan=plan, context=context, repair_records=repair_records)
        self._update_status(
            run_id,
            RunPhase.running,
            progress=80,
            repair_records=repair_records,
            current_step=self._count_executable_steps(plan),
            attempt_no=self._max_attempt_no(repair_records),
            healing_summary=self._build_healing_summary(repair_records),
            plan_revision=self._extract_plan_revision(plan),
            event_kind="execution_completed",
            event_message="Execution stage completed and produced an output artifact.",
            event_details={"repair_count": len(repair_records)},
        )
        self._persist_plan(self._plan_path(run_id), plan)
        return fused_shp, repair_records

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

        source_id = self._resolve_task_driven_source_id(plan)
        if not source_id:
            raise ValueError("task-driven input strategy could not resolve a source_id from the plan")
        required_output_type = self._extract_required_input_data_type(plan)
        if not required_output_type:
            raise ValueError("task-driven input strategy could not resolve the required input data type")

        resolved = self.input_acquisition_service.resolve_task_driven_inputs(
            request=request,
            source_id=source_id,
            required_output_type=required_output_type,
            input_dir=input_dir,
            request_bbox=tuple(resolved_aoi.bbox) if resolved_aoi is not None else None,
            resolved_aoi=resolved_aoi,
        )
        return resolved.osm_zip_path, resolved.ref_zip_path, resolved

    def run_writeback_stage(
        self,
        run_id: str,
        request: RunCreateRequest,
        plan: WorkflowPlan,
        fused_shp: Path,
        repair_records: List[RepairRecord],
        output_dir: Path,
    ) -> RunArtifactMeta:
        artifact_zip = zip_shapefile_bundle(fused_shp, output_dir / f"{request.job_type.value}_fusion_result.zip")
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
            target_crs = normalize_target_crs(request.target_crs)
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

    def _dispatch_run(
        self,
        run_id: str,
        request: RunCreateRequest,
        osm_zip_path: Path | None,
        ref_zip_path: Path | None,
        intermediate_dir: Path,
        output_dir: Path,
        log_dir: Path,
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
            )
        except Exception:  # noqa: BLE001
            self._pool.submit(
                self.execute_run,
                run_id,
                request,
                osm_zip_path,
                ref_zip_path,
                intermediate_dir,
                output_dir,
                log_dir,
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
                target_crs=normalize_target_crs(request.target_crs),
                repaired=bool(repair_records),
                repair_count=len(repair_records),
                failure_reason=failure_reason,
                plan_revision=self._extract_plan_revision(plan),
                metadata=durable_metadata,
                created_at=_utc_now(),
            )
            self.kg_repo.record_durable_learning_record(durable_record)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("geofusion.run").warning("Failed to record execution feedback: %s", exc)

    def _update_status(
        self,
        run_id: str,
        phase: RunPhase,
        progress: Optional[int] = None,
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
        plan_revision: Optional[int] = None,
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
            current.phase = phase
            if progress is not None:
                current.progress = progress
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
            if plan_revision is not None:
                current.plan_revision = plan_revision
            if event_kind or phase != previous_phase:
                event = RunEvent(
                    timestamp=_utc_now(),
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
        path.write_text(json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")

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
        retrieval = plan.context.get("retrieval", {})
        candidates = retrieval.get("candidate_patterns", []) if isinstance(retrieval, dict) else []
        if candidates:
            return candidates[0].get("pattern_id")
        value = plan.context.get("pattern_id")
        return str(value) if value else None

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
    def _should_resolve_aoi(request: RunCreateRequest) -> bool:
        if request.input_strategy != RunInputStrategy.task_driven_auto:
            return False
        if request.trigger.type != RunTriggerType.user_query:
            return False
        if request.trigger.spatial_extent:
            return False
        content = (request.trigger.content or "").strip()
        if not content:
            return False
        return bool(re.search(r"\b(for|in|around|within)\b", content, flags=re.IGNORECASE))

    @staticmethod
    def _resolve_task_driven_source_id(plan: WorkflowPlan) -> Optional[str]:
        selected = AgentRunService._extract_selected_data_source(plan)
        if selected and selected != "upload.bundle":
            return selected
        alternatives = AgentRunService._extract_alternative_sources(plan)
        return alternatives[0] if alternatives else None

    @staticmethod
    def _extract_alternative_sources(plan: WorkflowPlan) -> List[str]:
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
        candidates: List[CandidateScoreInput] = []
        for raw in raw_patterns:
            if not isinstance(raw, dict):
                continue
            pattern_id = str(raw.get("pattern_id") or "").strip()
            if not pattern_id:
                continue
            success_rate = self._to_unit_interval(raw.get("success_rate"))
            candidates.append(
                CandidateScoreInput(
                    candidate_id=pattern_id,
                    success_rate=success_rate,
                    accuracy=success_rate,
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
        return decision.model_copy(
            update={"evidence_refs": ["context.retrieval.candidate_patterns", "policy:deterministic_weighted_sum"]}
        )

    def _build_data_source_selection_decision(self, plan: WorkflowPlan) -> Optional[DecisionRecord]:
        retrieval = plan.context.get("retrieval", {})
        raw_sources = retrieval.get("data_sources", []) if isinstance(retrieval, dict) else []
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
        decision = self.policy_engine.select("data_source_selection", candidates).model_copy(
            update={"evidence_refs": ["context.retrieval.data_sources", "policy:deterministic_weighted_sum"]}
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
            return error
        last = repair_records[-1]
        reason = last.reason_code or "unknown_reason"
        return f"{error} | last_repair={last.strategy}:{reason}"

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


agent_run_service = AgentRunService(base_dir=Path("runs"))
