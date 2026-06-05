from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from schemas.agent import RunCreateRequest, RunInputStrategy, RunTrigger, RunTriggerType
from schemas.scenario import ScenarioRunInspectionResponse, ScenarioRunListResponse, ScenarioRunRequest, ScenarioRunResponse
from schemas.ui_assets import MarkdownDocumentResponse, ScenarioDocumentListResponse
from api.routers.runs_v2 import _build_preflight_details
from services.scenario_document_service import ScenarioDocumentService
from services.scenario_output import resolve_scenario_output_root
from services.scenario_registry_service import ScenarioRegistryService
from services.scenario_run_service import build_child_run_specs, classify_scenario_request, scenario_run_service


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
        submit = getattr(scenario_run_service, "submit_scenario_run", None)
        if callable(submit):
            return submit(request)
        return scenario_run_service.create_scenario_run(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/scenario-runs/preflight")
async def preflight_scenario_run(request: ScenarioRunRequest) -> dict[str, object]:
    child_specs = build_child_run_specs(request)
    decision = classify_scenario_request(
        scenario_name=request.scenario_name,
        trigger_content=request.trigger_content,
        job_types=[spec.job_type for spec in child_specs],
        metadata=request.metadata,
    )
    child_preflights = []
    for spec in child_specs:
        run_request = RunCreateRequest(
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
        child_preflights.append(
            {
                "job_type": spec.job_type.value,
                "task_kind": spec.task_kind.value if spec.task_kind else spec.job_type.value,
                "task_family": spec.task_family or spec.job_type.value,
                "preferred_pattern_id": spec.preferred_pattern_id,
                "output_data_type": spec.output_data_type,
                **_build_preflight_details(run_request),
            }
        )
    return {
        "allowed": decision["decision"] == "allow",
        "decision": decision,
        "child_preflights": child_preflights,
    }


@router.post("/scenario-runs/{scenario_id}/resume", response_model=ScenarioRunResponse)
async def resume_scenario_run(scenario_id: str, retry_failed: bool = False) -> ScenarioRunResponse:
    try:
        return await run_in_threadpool(
            lambda: scenario_run_service.resume_scenario_run(scenario_id, retry_failed=retry_failed)
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Scenario run not found: {scenario_id}") from exc
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
