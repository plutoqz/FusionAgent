from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from schemas.fusion import FusionJobStatus, JobState
from services.job_service import job_service


router = APIRouter(tags=["jobs"])


@router.get("/jobs/{job_id}", response_model=FusionJobStatus)
async def get_job_status(job_id: str) -> FusionJobStatus:
    status = job_service.get_job(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return status


@router.get("/jobs/{job_id}/artifact")
async def download_artifact(job_id: str) -> FileResponse:
    status = job_service.get_job(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    if status.status != JobState.succeeded:
        raise HTTPException(status_code=409, detail=f"Job is not succeeded yet: {status.status.value}")
    artifact = job_service.get_artifact_path(job_id)
    if artifact is None or not artifact.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path=str(artifact), filename=artifact.name, media_type="application/zip")

