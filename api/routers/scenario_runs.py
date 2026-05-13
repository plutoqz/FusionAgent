from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from schemas.scenario import ScenarioRunInspectionResponse, ScenarioRunListResponse, ScenarioRunRequest, ScenarioRunResponse
from schemas.ui_assets import MarkdownDocumentResponse, ScenarioDocumentListResponse
from services.scenario_document_service import ScenarioDocumentService
from services.scenario_output import resolve_scenario_output_root
from services.scenario_registry_service import ScenarioRegistryService
from services.scenario_run_service import scenario_run_service


router = APIRouter(tags=["scenario-runs"])


@router.get("/scenario-runs", response_model=ScenarioRunListResponse)
async def list_scenario_runs(
    limit: int = Query(default=50, ge=1),
    phase: Optional[str] = None,
) -> ScenarioRunListResponse:
    registry = ScenarioRegistryService(output_root=resolve_scenario_output_root(None))
    return ScenarioRunListResponse(records=registry.list_records(limit=limit, phase=phase))


@router.post("/scenario-runs", response_model=ScenarioRunResponse)
async def create_scenario_run(request: ScenarioRunRequest) -> ScenarioRunResponse:
    try:
        return scenario_run_service.create_scenario_run(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/scenario-runs/{scenario_id}", response_model=ScenarioRunInspectionResponse)
async def inspect_scenario_run(scenario_id: str) -> ScenarioRunInspectionResponse:
    registry = ScenarioRegistryService(output_root=resolve_scenario_output_root(None))
    try:
        return ScenarioRunInspectionResponse(summary=registry.get_summary(scenario_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Scenario run not found: {scenario_id}") from exc


@router.get("/scenario-runs/{scenario_id}/documents", response_model=ScenarioDocumentListResponse)
async def list_scenario_documents(scenario_id: str) -> ScenarioDocumentListResponse:
    service = ScenarioDocumentService(output_root=resolve_scenario_output_root(None))
    try:
        documents = service.list_documents(scenario_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ScenarioDocumentListResponse(scenario_id=scenario_id, documents=documents)


@router.get("/scenario-runs/{scenario_id}/documents/{filename:path}", response_model=MarkdownDocumentResponse)
async def get_scenario_document(scenario_id: str, filename: str) -> MarkdownDocumentResponse:
    service = ScenarioDocumentService(output_root=resolve_scenario_output_root(None))
    try:
        return service.read_document(scenario_id, filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
