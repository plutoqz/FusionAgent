from __future__ import annotations

import json
import logging
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Dict, Optional

from adapters.building_adapter import run_building_fusion
from adapters.road_adapter import run_road_fusion
from schemas.fusion import (
    FusionArtifactMeta,
    FusionJobRequest,
    FusionJobStatus,
    JobState,
    JobType,
)
from utils.crs import normalize_target_crs
from utils.shp_zip import validate_zip_has_shapefile, zip_shapefile_bundle


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobService:
    def __init__(self, base_dir: Path, max_workers: int = 2) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._jobs: Dict[str, FusionJobStatus] = {}
        self._lock = Lock()
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="fusion-job")

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True)

    def create_job(
        self,
        job_type: JobType,
        request: FusionJobRequest,
        osm_zip_name: str,
        osm_zip_bytes: bytes,
        ref_zip_name: str,
        ref_zip_bytes: bytes,
    ) -> FusionJobStatus:
        job_id = uuid.uuid4().hex
        target_crs = normalize_target_crs(request.target_crs)
        job_dir = self.base_dir / job_id
        input_dir = job_dir / "input"
        intermediate_dir = job_dir / "intermediate"
        output_dir = job_dir / "output"
        log_dir = job_dir / "logs"
        for d in [input_dir, intermediate_dir, output_dir, log_dir]:
            d.mkdir(parents=True, exist_ok=True)

        osm_zip_path = input_dir / (Path(osm_zip_name).name or "osm.zip")
        ref_zip_path = input_dir / (Path(ref_zip_name).name or "ref.zip")
        osm_zip_path.write_bytes(osm_zip_bytes)
        ref_zip_path.write_bytes(ref_zip_bytes)

        status = FusionJobStatus(
            job_id=job_id,
            job_type=job_type,
            status=JobState.queued,
            progress=0,
            target_crs=target_crs,
            debug=request.debug,
            error=None,
            log_path=str(log_dir / "job.log"),
            artifact=None,
            created_at=_utc_now(),
            started_at=None,
            finished_at=None,
        )
        with self._lock:
            self._jobs[job_id] = status
            self._persist_status(status)

        self._pool.submit(
            self._run_job,
            status,
            request,
            osm_zip_path,
            ref_zip_path,
            job_dir,
            intermediate_dir,
            output_dir,
            log_dir,
        )
        return status

    def get_job(self, job_id: str) -> Optional[FusionJobStatus]:
        with self._lock:
            status = self._jobs.get(job_id)
        if status is not None:
            return status
        return self._load_status(job_id)

    def get_artifact_path(self, job_id: str) -> Optional[Path]:
        status = self.get_job(job_id)
        if not status or not status.artifact:
            return None
        return Path(status.artifact.path)

    def _run_job(
        self,
        status: FusionJobStatus,
        request: FusionJobRequest,
        osm_zip_path: Path,
        ref_zip_path: Path,
        job_dir: Path,
        intermediate_dir: Path,
        output_dir: Path,
        log_dir: Path,
    ) -> None:
        logger = self._build_logger(status.job_id, log_dir / "job.log")
        try:
            self._update_status(status.job_id, JobState.running, progress=5, started_at=_utc_now(), error=None)
            logger.info("Job started: %s (%s)", status.job_id, status.job_type.value)

            osm_extract = intermediate_dir / "osm"
            ref_extract = intermediate_dir / "ref"
            osm_shp = validate_zip_has_shapefile(osm_zip_path, osm_extract)
            ref_shp = validate_zip_has_shapefile(ref_zip_path, ref_extract)
            self._update_status(status.job_id, JobState.running, progress=25)
            logger.info("Input ZIP validated and extracted.")

            field_mapping = request.field_mapping.model_dump() if hasattr(request.field_mapping, "model_dump") else request.field_mapping.dict()
            if status.job_type == JobType.building:
                fused_shp = run_building_fusion(
                    osm_shp=osm_shp,
                    ref_shp=ref_shp,
                    output_dir=output_dir,
                    target_crs=status.target_crs,
                    field_mapping=field_mapping,
                    debug=request.debug,
                )
            elif status.job_type == JobType.road:
                fused_shp = run_road_fusion(
                    osm_shp=osm_shp,
                    ref_shp=ref_shp,
                    output_dir=output_dir,
                    target_crs=status.target_crs,
                    field_mapping=field_mapping,
                    debug=request.debug,
                )
            else:
                raise ValueError(f"Unsupported job type: {status.job_type}")

            self._update_status(status.job_id, JobState.running, progress=85)
            logger.info("Fusion finished, generating artifact ZIP...")

            artifact_zip = zip_shapefile_bundle(fused_shp, output_dir / f"{status.job_type.value}_fusion_result.zip")
            artifact = FusionArtifactMeta(
                filename=artifact_zip.name,
                path=str(artifact_zip),
                size_bytes=artifact_zip.stat().st_size,
            )
            self._update_status(
                status.job_id,
                JobState.succeeded,
                progress=100,
                finished_at=_utc_now(),
                artifact=artifact,
            )
            logger.info("Job succeeded.")
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
            tb = traceback.format_exc()
            logger.error(err)
            logger.error(tb)
            self._update_status(
                status.job_id,
                JobState.failed,
                progress=100,
                finished_at=_utc_now(),
                error=err,
            )
        finally:
            for handler in list(logger.handlers):
                logger.removeHandler(handler)
                handler.close()

    def _update_status(
        self,
        job_id: str,
        state: JobState,
        progress: Optional[int] = None,
        error: Optional[str] = None,
        started_at: Optional[str] = None,
        finished_at: Optional[str] = None,
        artifact: Optional[FusionArtifactMeta] = None,
    ) -> None:
        with self._lock:
            current = self._jobs[job_id]
            current.status = state
            if progress is not None:
                current.progress = progress
            if error is not None or state == JobState.succeeded:
                current.error = error
            if started_at is not None:
                current.started_at = started_at
            if finished_at is not None:
                current.finished_at = finished_at
            if artifact is not None:
                current.artifact = artifact
            self._jobs[job_id] = current
            self._persist_status(current)

    def _persist_status(self, status: FusionJobStatus) -> None:
        job_dir = self.base_dir / status.job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        data = status.model_dump(mode="json") if hasattr(status, "model_dump") else status.dict()
        (job_dir / "job.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_status(self, job_id: str) -> Optional[FusionJobStatus]:
        path = self.base_dir / job_id / "job.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        status = FusionJobStatus.model_validate(payload)
        with self._lock:
            self._jobs[job_id] = status
        return status

    @staticmethod
    def _build_logger(job_id: str, log_path: Path) -> logging.Logger:
        logger = logging.getLogger(f"fusion_job_{job_id}")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        if logger.handlers:
            return logger

        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        return logger


job_service = JobService(base_dir=Path("jobs"))
