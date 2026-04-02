from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from schemas.fusion import FieldMapping, FusionJobCreateResponse, FusionJobRequest, JobType
from services.job_service import job_service
from utils.crs import normalize_target_crs


router = APIRouter(tags=["fusion"])


def _parse_field_mapping(raw_json: str) -> FieldMapping:
    try:
        payload = json.loads(raw_json) if raw_json else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"field_mapping must be valid JSON: {exc}") from exc

    try:
        return FieldMapping(**payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Invalid field_mapping structure: {exc}") from exc


async def _create_job(
    job_type: JobType,
    osm_zip: UploadFile,
    ref_zip: UploadFile,
    target_crs: str,
    field_mapping: str,
    debug: bool,
) -> FusionJobCreateResponse:
    if not osm_zip.filename or not osm_zip.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="osm_zip must be a .zip file")
    if not ref_zip.filename or not ref_zip.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="ref_zip must be a .zip file")

    try:
        normalized_crs = normalize_target_crs(target_crs)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    mapping = _parse_field_mapping(field_mapping)
    request = FusionJobRequest(target_crs=normalized_crs, field_mapping=mapping, debug=debug)

    osm_bytes = await osm_zip.read()
    ref_bytes = await ref_zip.read()
    if not osm_bytes:
        raise HTTPException(status_code=400, detail="osm_zip is empty")
    if not ref_bytes:
        raise HTTPException(status_code=400, detail="ref_zip is empty")

    status = job_service.create_job(
        job_type=job_type,
        request=request,
        osm_zip_name=osm_zip.filename,
        osm_zip_bytes=osm_bytes,
        ref_zip_name=ref_zip.filename,
        ref_zip_bytes=ref_bytes,
    )
    return FusionJobCreateResponse(job_id=status.job_id, status=status.status)


@router.post("/fusion/building/jobs", response_model=FusionJobCreateResponse)
async def create_building_job(
    osm_zip: UploadFile = File(...),
    ref_zip: UploadFile = File(...),
    target_crs: str = Form("EPSG:32643"),
    field_mapping: str = Form("{}"),
    debug: bool = Form(False),
) -> FusionJobCreateResponse:
    return await _create_job(JobType.building, osm_zip, ref_zip, target_crs, field_mapping, debug)


@router.post("/fusion/road/jobs", response_model=FusionJobCreateResponse)
async def create_road_job(
    osm_zip: UploadFile = File(...),
    ref_zip: UploadFile = File(...),
    target_crs: str = Form("EPSG:32643"),
    field_mapping: str = Form("{}"),
    debug: bool = Form(False),
) -> FusionJobCreateResponse:
    return await _create_job(JobType.road, osm_zip, ref_zip, target_crs, field_mapping, debug)

