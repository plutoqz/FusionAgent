from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from schemas.agent import (
    RunAuditResponse,
    RunCreateRequest,
    RunCreateResponse,
    RunPhase,
    RunPlanResponse,
    RunStatus,
    RunTrigger,
    RunTriggerType,
)
from schemas.fusion import FieldMapping, JobType
from services.agent_run_service import agent_run_service
from utils.crs import normalize_target_crs


router = APIRouter(tags=["runs-v2"])


def _parse_field_mapping(raw_json: str) -> FieldMapping:
    try:
        payload = json.loads(raw_json) if raw_json else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"field_mapping must be valid JSON: {exc}") from exc
    try:
        return FieldMapping(**payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Invalid field_mapping structure: {exc}") from exc


@router.post("/runs", response_model=RunCreateResponse)
async def create_run(
    osm_zip: UploadFile = File(...),
    ref_zip: UploadFile = File(...),
    job_type: JobType = Form(...),
    trigger_type: RunTriggerType = Form(RunTriggerType.user_query),
    trigger_content: str = Form("manual trigger"),
    disaster_type: Optional[str] = Form(None),
    spatial_extent: Optional[str] = Form(None),
    temporal_start: Optional[str] = Form(None),
    temporal_end: Optional[str] = Form(None),
    target_crs: str = Form("EPSG:32643"),
    field_mapping: str = Form("{}"),
    debug: bool = Form(False),
) -> RunCreateResponse:
    if not osm_zip.filename or not osm_zip.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="osm_zip must be a .zip file")
    if not ref_zip.filename or not ref_zip.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="ref_zip must be a .zip file")

    try:
        normalized_crs = normalize_target_crs(target_crs)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    mapping = _parse_field_mapping(field_mapping)
    trigger = RunTrigger(
        type=trigger_type,
        content=trigger_content,
        disaster_type=disaster_type,
        spatial_extent=spatial_extent,
        temporal_start=temporal_start,
        temporal_end=temporal_end,
    )
    request = RunCreateRequest(
        job_type=job_type,
        trigger=trigger,
        target_crs=normalized_crs,
        field_mapping=mapping.model_dump() if hasattr(mapping, "model_dump") else mapping.dict(),
        debug=debug,
    )

    osm_bytes = await osm_zip.read()
    ref_bytes = await ref_zip.read()
    if not osm_bytes:
        raise HTTPException(status_code=400, detail="osm_zip is empty")
    if not ref_bytes:
        raise HTTPException(status_code=400, detail="ref_zip is empty")

    status = agent_run_service.create_run(
        request=request,
        osm_zip_name=osm_zip.filename,
        osm_zip_bytes=osm_bytes,
        ref_zip_name=ref_zip.filename,
        ref_zip_bytes=ref_bytes,
    )
    return RunCreateResponse(run_id=status.run_id, phase=status.phase)


@router.get("/runs/{run_id}", response_model=RunStatus)
async def get_run_status(run_id: str) -> RunStatus:
    status = agent_run_service.get_run(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return status


@router.get("/runs/{run_id}/plan", response_model=RunPlanResponse)
async def get_run_plan(run_id: str) -> RunPlanResponse:
    status = agent_run_service.get_run(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    plan = agent_run_service.get_plan(run_id)
    if plan is None:
        if status.phase in {RunPhase.queued, RunPhase.planning}:
            raise HTTPException(status_code=409, detail=f"Plan not ready yet: {status.phase.value}")
        raise HTTPException(status_code=404, detail="Plan not found")
    return RunPlanResponse(run_id=run_id, plan=plan)


@router.get("/runs/{run_id}/audit", response_model=RunAuditResponse)
async def get_run_audit(run_id: str) -> RunAuditResponse:
    status = agent_run_service.get_run(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return RunAuditResponse(run_id=run_id, events=agent_run_service.get_audit_events(run_id))


@router.get("/runs/{run_id}/artifact")
async def download_run_artifact(run_id: str) -> FileResponse:
    status = agent_run_service.get_run(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    if status.phase != RunPhase.succeeded:
        raise HTTPException(status_code=409, detail=f"Run is not succeeded yet: {status.phase.value}")
    artifact = agent_run_service.get_artifact_path(run_id)
    if artifact is None or not artifact.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path=str(artifact), filename=artifact.name, media_type="application/zip")
