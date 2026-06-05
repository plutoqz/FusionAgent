from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from schemas.engineering_validation import ValidationSessionListResponse, ValidationSessionRecord
from services.validation_session_read_model_service import ValidationSessionReadModelService


router = APIRouter(tags=["validation-sessions"])


@router.get("/validation/sessions", response_model=ValidationSessionListResponse)
async def list_validation_sessions(limit: int = Query(default=50, ge=1, le=100)) -> ValidationSessionListResponse:
    service = ValidationSessionReadModelService()
    return ValidationSessionListResponse(records=service.list_sessions(limit=limit))


@router.get("/validation/sessions/{session_id}", response_model=ValidationSessionRecord)
async def get_validation_session(session_id: str) -> ValidationSessionRecord:
    service = ValidationSessionReadModelService()
    try:
        return ValidationSessionRecord.model_validate(service.get_session(session_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Validation session not found: {session_id}") from exc
