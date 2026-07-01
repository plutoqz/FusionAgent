from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from schemas.agent import RunCreateRequest, RunInputStrategy, RunTrigger, RunTriggerType
from schemas.scenario import ScenarioRunInspectionResponse, ScenarioRunListResponse, ScenarioRunRequest, ScenarioRunResponse
from schemas.ui_assets import MarkdownDocumentResponse, ScenarioDocumentListResponse
from api.routers.runs_v2 import _build_preflight_details
from services.aoi_resolution_service import AOIResolutionService, NominatimGeocoder
from services.scenario_document_service import ScenarioDocumentService
from services.scenario_output import resolve_scenario_output_root
from services.scenario_registry_service import ScenarioRegistryService
from services.scenario_run_service import build_child_run_specs, classify_scenario_request, scenario_run_service
from services.scenario_trigger_normalizer import normalize_scenario_trigger_text


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
    normalized_trigger = normalize_scenario_trigger_text(request.trigger_content)
    effective_spatial_extent = str(request.spatial_extent or normalized_trigger.normalized_location or "").strip()
    bbox = _parse_preflight_bbox(effective_spatial_extent)
    aoi_needs_resolution = bbox is None and bool(str(effective_spatial_extent or request.trigger_content).strip())
    resolved_aoi, aoi_error = _resolve_preflight_aoi(
        effective_spatial_extent or request.trigger_content,
        required=aoi_needs_resolution,
        skip=bool(bbox),
    )
    source_readiness = _scenario_source_readiness(child_preflights)
    aoi_blocked = bool(aoi_error and aoi_needs_resolution)
    allowed = decision["decision"] == "allow" and not aoi_blocked and not source_readiness["blocked_required_source"]
    return {
        "allowed": allowed,
        "decision": decision,
        "normalized_trigger": normalized_trigger.to_dict(),
        "normalized_location": normalized_trigger.normalized_location,
        "expected_child_count": 5 if str(normalized_trigger.disaster_type or request.disaster_type or "").strip().lower() in {"flood", "heavy_rainfall", "rainstorm"} else len(child_specs),
        "resolved_aoi": resolved_aoi,
        "aoi_confidence": resolved_aoi.get("confidence") if isinstance(resolved_aoi, dict) else None,
        "aoi_error": aoi_error,
        "source_readiness": source_readiness,
        "child_preflights": child_preflights,
    }


def _parse_preflight_bbox(spatial_extent: str | None) -> list[float] | None:
    from api.routers.runs_v2 import _parse_preflight_bbox as parse_bbox

    return parse_bbox(spatial_extent)


def _preflight_aoi_timeout_seconds() -> float:
    try:
        return max(0.1, float(os.getenv("GEOFUSION_PREFLIGHT_AOI_TIMEOUT_SECONDS", "3")))
    except ValueError:
        return 3.0


def _resolve_preflight_aoi(
    query: str,
    *,
    required: bool,
    skip: bool,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    if skip:
        return None, None
    cleaned = str(query or "").strip()
    if not cleaned:
        if required:
            return None, {
                "code": "AOI_RESOLUTION_REQUIRED",
                "message": "No spatial_extent or resolvable location text was provided.",
                "next_action": "Provide spatial_extent=bbox(minx,miny,maxx,maxy) or a resolvable location.",
            }
        return None, None

    service = AOIResolutionService(
        geocoder=NominatimGeocoder(
            timeout_seconds=max(1, int(_preflight_aoi_timeout_seconds())),
            max_retries=1,
        )
    )
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(service.resolve, cleaned)
    try:
        resolved = future.result(timeout=_preflight_aoi_timeout_seconds())
        return resolved.to_dict(), None
    except TimeoutError:
        future.cancel()
        return None, {
            "code": "GEOCODER_TIMEOUT",
            "message": f"AOI geocoder did not respond within {_preflight_aoi_timeout_seconds()} seconds.",
            "next_action": "Retry later, use a cached/fake geocoder, or provide spatial_extent=bbox(...).",
        }
    except Exception as exc:  # noqa: BLE001
        code = "AOI_RESOLUTION_REQUIRED" if required else "AOI_RESOLUTION_FAILED"
        return None, {
            "code": code,
            "message": str(exc),
            "next_action": "Provide spatial_extent=bbox(minx,miny,maxx,maxy) or a more specific location.",
        }
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _scenario_source_readiness(child_preflights: list[dict[str, object]]) -> dict[str, object]:
    blocked_required_source = False
    blocked_children: list[dict[str, object]] = []
    for child in child_preflights:
        degradation = child.get("degradation") if isinstance(child, dict) else {}
        coverage = child.get("component_coverage") if isinstance(child, dict) else {}
        if not isinstance(degradation, dict) or not isinstance(coverage, dict):
            continue
        partial_allowed = bool(coverage.get("partial_coverage_allowed"))
        components = coverage.get("components") if isinstance(coverage.get("components"), list) else []
        required_source_ids = list(coverage.get("required_source_ids") or [])
        missing_required = [
            str(item.get("source_id"))
            for item in components
            if isinstance(item, dict)
            and item.get("source_id") in required_source_ids
            and not bool(item.get("local_cache_available"))
            and not bool(item.get("auto_materializable"))
        ]
        complete_pair_required = degradation.get("state") == "preflight_complete_pair_required"
        if complete_pair_required and missing_required and not partial_allowed:
            blocked_required_source = True
            blocked_children.append(
                {
                    "task_kind": child.get("task_kind"),
                    "job_type": child.get("job_type"),
                    "reason_code": "MISSING_REQUIRED_SOURCE",
                    "missing_required_source_ids": missing_required,
                    "next_action": "Run scripts/materialize_source_assets.py for these sources or provide local Data files.",
                }
            )
    return {
        "blocked_required_source": blocked_required_source,
        "blocked_children": blocked_children,
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
async def inspect_scenario_run(
    scenario_id: str,
    output_root: Optional[str] = Query(default=None),
) -> ScenarioRunInspectionResponse:
    registry = ScenarioRegistryService(output_root=resolve_scenario_output_root(output_root))
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
