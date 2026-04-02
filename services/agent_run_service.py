from __future__ import annotations

import json
import logging
import os
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional

from agent.executor import ExecutionContext, WorkflowExecutor
from agent.planner import WorkflowPlanner
from agent.validator import WorkflowValidator
from kg.factory import create_kg_repository
from kg.models import ExecutionFeedback
from kg.repository import KGRepository
from llm.factory import create_llm_provider
from schemas.agent import (
    RepairRecord,
    RunArtifactMeta,
    RunCreateRequest,
    RunPhase,
    RunStatus,
    WorkflowPlan,
)
from utils.crs import normalize_target_crs
from utils.shp_zip import validate_zip_has_shapefile, zip_shapefile_bundle


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
        self.planner = WorkflowPlanner(self.kg_repo, self.llm_provider)
        self.validator = WorkflowValidator(self.kg_repo)
        self.executor = WorkflowExecutor(self.kg_repo, planner=self.planner)

        self.dispatch_eager = _as_bool(os.getenv("GEOFUSION_CELERY_EAGER", "1"), default=True)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True)
        close = getattr(self.kg_repo, "close", None)
        if callable(close):
            close()

    def create_run(
        self,
        request: RunCreateRequest,
        osm_zip_name: str,
        osm_zip_bytes: bytes,
        ref_zip_name: str,
        ref_zip_bytes: bytes,
    ) -> RunStatus:
        run_id = uuid.uuid4().hex
        run_dir = self.base_dir / run_id
        input_dir = run_dir / "input"
        intermediate_dir = run_dir / "intermediate"
        output_dir = run_dir / "output"
        log_dir = run_dir / "logs"
        for directory in [input_dir, intermediate_dir, output_dir, log_dir]:
            directory.mkdir(parents=True, exist_ok=True)

        osm_zip_path = input_dir / (Path(osm_zip_name).name or "osm.zip")
        ref_zip_path = input_dir / (Path(ref_zip_name).name or "ref.zip")
        osm_zip_path.write_bytes(osm_zip_bytes)
        ref_zip_path.write_bytes(ref_zip_bytes)
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
            artifact=None,
            repair_records=[],
            current_step=None,
            attempt_no=0,
            healing_summary={},
            failure_summary=None,
            plan_revision=0,
            created_at=_utc_now(),
            started_at=None,
            finished_at=None,
        )
        with self._lock:
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
        osm_zip_path: Path,
        ref_zip_path: Path,
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
            )
            logger.info("Run started: %s (%s)", run_id, request.job_type.value)

            plan = self.run_planning_stage(run_id=run_id, request=request)
            logger.info("Planning stage completed with revision=%s", plan.context.get("plan_revision", 0))

            plan = self.run_validation_stage(run_id=run_id, plan=plan)
            logger.info("Validation stage completed; valid=%s", getattr(plan.validation, "valid", None))

            fused_shp, repair_records = self.run_execution_stage(
                run_id=run_id,
                request=request,
                plan=plan,
                osm_zip_path=osm_zip_path,
                ref_zip_path=ref_zip_path,
                intermediate_dir=intermediate_dir,
                output_dir=output_dir,
            )
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
        plan = self.planner.create_plan(run_id=run_id, job_type=request.job_type, trigger=request.trigger)
        plan_path = self._plan_path(run_id)
        self._persist_plan(plan_path, plan)
        self._update_status(
            run_id,
            RunPhase.validating,
            progress=25,
            plan_path=str(plan_path),
            plan_revision=self._extract_plan_revision(plan),
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
    ) -> tuple[Path, List[RepairRecord]]:
        osm_extract = intermediate_dir / "osm"
        ref_extract = intermediate_dir / "ref"
        osm_shp = validate_zip_has_shapefile(osm_zip_path, osm_extract)
        ref_shp = validate_zip_has_shapefile(ref_zip_path, ref_extract)

        repair_records: List[RepairRecord] = []
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
        )
        self._persist_plan(self._plan_path(run_id), plan)
        return fused_shp, repair_records

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
        return artifact

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

    def _dispatch_run(
        self,
        run_id: str,
        request: RunCreateRequest,
        osm_zip_path: Path,
        ref_zip_path: Path,
        intermediate_dir: Path,
        output_dir: Path,
        log_dir: Path,
    ) -> None:
        try:
            from worker.tasks import execute_run_task

            execute_run_task.delay(
                run_id=run_id,
                request=request.model_dump(mode="json"),
                osm_zip_path=str(osm_zip_path),
                ref_zip_path=str(ref_zip_path),
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
        repair_records: Optional[List[RepairRecord]] = None,
        current_step: Optional[int] = None,
        attempt_no: Optional[int] = None,
        healing_summary: Optional[Dict[str, object]] = None,
        failure_summary: Optional[str] = None,
        plan_revision: Optional[int] = None,
    ) -> None:
        current = self.get_run(run_id)
        if current is None:
            raise KeyError(run_id)
        with self._lock:
            current = self._runs[run_id]
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


agent_run_service = AgentRunService(base_dir=Path("runs"))
