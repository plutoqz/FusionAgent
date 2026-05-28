from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from schemas.agent import (
    OperatorRecoveryExecuteRequest,
    OperatorRecoveryExecuteResponse,
    RunAuditResponse,
    RunCreateRequest,
    RunCreateResponse,
    RunComparisonResponse,
    RunInputStrategy,
    RunInspectionArtifact,
    RunInspectionResponse,
    RunPhase,
    RunPreflightResponse,
    RuntimeMetadataResponse,
    RunPlanResponse,
    RunStatus,
    RunTrigger,
    RunTriggerType,
)
from schemas.fusion import FieldMapping, JobType
from schemas.kg_graph import KgGraphResponse
from schemas.operator import (
    OperatorRecoveryResponse,
    OperatorRunListResponse,
    OperatorRuntimeSummaryResponse,
)
from schemas.ui_assets import ArtifactPreviewResponse
from schemas.ui_assets import RunDocumentListResponse, RunMarkdownDocumentResponse
from services.agent_run_service import agent_run_service, derive_run_inspection_digest
from services.artifact_preview_service import build_artifact_preview
from services.kg_graph_service import build_run_path_graph
from services.kg_path_trace_service import build_kg_path_trace
from services.operator_read_model_service import OperatorReadModelService
from services.run_recovery_service import build_recovery_hint
from services.run_recovery_executor import RunRecoveryExecutor
from services.run_document_service import RunDocumentService
from services.run_registry_service import RunRegistryService
from services.run_telemetry_service import build_run_telemetry_summary
from services.scenario_output import resolve_scenario_output_root
from services.tool_contract_report_service import build_tool_contract_report
from services.unsupported_intent_guard import classify_unsupported_intent
from utils.crs import normalize_explicit_target_crs


router = APIRouter(tags=["runs-v2"])


def _build_runtime_metadata_response() -> RuntimeMetadataResponse:
    return RuntimeMetadataResponse(
        kg_backend=os.getenv("GEOFUSION_KG_BACKEND"),
        llm_provider=os.getenv("GEOFUSION_LLM_PROVIDER"),
        celery_eager=os.getenv("GEOFUSION_CELERY_EAGER"),
        api_port=os.getenv("GEOFUSION_API_PORT"),
    )


def _parse_field_mapping(raw_json: str) -> FieldMapping:
    try:
        payload = json.loads(raw_json) if raw_json else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"field_mapping must be valid JSON: {exc}") from exc
    try:
        return FieldMapping(**payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Invalid field_mapping structure: {exc}") from exc


def _build_run_inspection_response(run_id: str, status: RunStatus) -> RunInspectionResponse:
    plan = agent_run_service.get_plan(run_id)
    audit_events = agent_run_service.get_audit_events(run_id)
    artifact_path = agent_run_service.get_artifact_path(run_id)
    source_semantic_contract = _load_source_semantic_contract(status)
    report_summary = _load_report_summary(run_id)
    large_area_runtime = _dict_from_mapping(report_summary.get("large_area_runtime"))
    report_source_semantic_contract = _dict_from_mapping(report_summary.get("source_semantic_contract"))
    if report_source_semantic_contract:
        source_semantic_contract = report_source_semantic_contract
    recovery_worker_evidence = _load_recovery_worker_evidence(run_id)
    artifact = RunInspectionArtifact(
        available=bool(artifact_path and artifact_path.exists()),
        filename=(artifact_path.name if artifact_path and artifact_path.exists() else None),
        path=(str(artifact_path) if artifact_path and artifact_path.exists() else None),
        size_bytes=(artifact_path.stat().st_size if artifact_path and artifact_path.exists() else None),
        download_path=(f"/api/v2/runs/{run_id}/artifact" if artifact_path and artifact_path.exists() else None),
    )
    return RunInspectionResponse(
        run=status,
        plan=plan,
        audit_events=audit_events,
        artifact=artifact,
        kg_path_trace=build_kg_path_trace(plan) if plan is not None else {},
        tool_contract_report=build_tool_contract_report(plan) if plan is not None else {},
        telemetry_summary=build_run_telemetry_summary(
            status=status,
            audit_events=audit_events,
            plan=plan,
        ),
        recovery_hint=build_recovery_hint(status.model_dump(mode="json")),
        large_area_runtime=large_area_runtime,
        source_semantic_contract=source_semantic_contract,
        recovery_worker_evidence=recovery_worker_evidence,
        digest=derive_run_inspection_digest(status, audit_events),
    )


def _load_report_summary(run_id: str) -> dict[str, object]:
    summary_path = Path(getattr(agent_run_service, "base_dir", Path("runs"))) / run_id / "documents" / "run_report_summary.json"
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _dict_from_mapping(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _load_source_semantic_contract(status: RunStatus) -> dict[str, object]:
    path_text = str(status.source_semantic_contract_path or "").strip()
    if not path_text:
        return {}
    path = Path(path_text)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_recovery_worker_evidence(run_id: str) -> dict[str, object]:
    history_path = Path(getattr(agent_run_service, "base_dir", Path("runs"))) / run_id / "recovery.history.jsonl"
    if not history_path.exists():
        return {}
    records: list[dict[str, object]] = []
    try:
        lines = history_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    for line in lines[-20:]:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    if not records:
        return {}
    return {"history_path": str(history_path), "records": records, "last_record": records[-1]}


def _selected_decisions(status: RunStatus) -> dict[str, str]:
    return {record.decision_type: record.selected_id for record in status.decision_records}


def _require_run_status(run_id: str) -> RunStatus:
    status = agent_run_service.get_run(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return status


def _require_run_plan(run_id: str, status: RunStatus) -> "WorkflowPlan":
    plan = agent_run_service.get_plan(run_id)
    if plan is None:
        if status.phase in {RunPhase.queued, RunPhase.planning}:
            raise HTTPException(status_code=409, detail=f"Plan not ready yet: {status.phase.value}")
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


def _require_succeeded_artifact(run_id: str) -> Path:
    status = _require_run_status(run_id)
    if status.phase != RunPhase.succeeded:
        raise HTTPException(status_code=409, detail=f"Run is not succeeded yet: {status.phase.value}")
    artifact = agent_run_service.get_artifact_path(run_id)
    if artifact is None or not artifact.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return artifact


def _preview_output_dir(run_id: str) -> Path:
    base_dir = Path(getattr(agent_run_service, "base_dir", Path("runs")))
    return base_dir / run_id / "preview"


def _preview_metadata_path(run_id: str) -> Path:
    return _preview_output_dir(run_id) / "preview_metadata.json"


def _preview_route_path(run_id: str) -> str:
    return f"/api/v2/runs/{run_id}/preview.geojson"


def _build_public_preview_payload(payload: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in payload.items()
        if key not in {"artifact_zip", "output_dir", "geojson_filename", "artifact_identity"}
    }


def _artifact_identity(artifact: Path) -> dict[str, object]:
    stat = artifact.stat()
    return {
        "path": str(artifact.resolve()),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _read_preview_metadata(metadata_path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _resolve_preview_geojson_path(payload: dict[str, object], preview_dir: Path) -> Path | None:
    geojson_filename = payload.get("geojson_filename")
    if not isinstance(geojson_filename, str) or not geojson_filename:
        return None
    normalized = PurePosixPath(geojson_filename.replace("\\", "/"))
    if normalized.is_absolute() or len(normalized.parts) != 1:
        return None
    filename = normalized.parts[0]
    if filename in {"", ".", ".."} or Path(filename).suffix.lower() != ".geojson":
        return None
    candidate = (preview_dir / filename).resolve()
    try:
        candidate.relative_to(preview_dir)
    except ValueError:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


def _payload_matches_artifact(payload: dict[str, object], artifact_identity: dict[str, object]) -> bool:
    cached_identity = payload.get("artifact_identity")
    return isinstance(cached_identity, dict) and cached_identity == artifact_identity


def _load_run_preview_payload(run_id: str) -> dict[str, object]:
    artifact = _require_succeeded_artifact(run_id).resolve()
    preview_dir = _preview_output_dir(run_id)
    preview_dir.mkdir(parents=True, exist_ok=True)
    preview_dir = preview_dir.resolve()
    metadata_path = _preview_metadata_path(run_id)
    artifact_identity = _artifact_identity(artifact)
    if metadata_path.exists():
        payload = _read_preview_metadata(metadata_path)
        if payload is not None:
            geojson_path = _resolve_preview_geojson_path(payload, preview_dir)
            if geojson_path is not None and _payload_matches_artifact(payload, artifact_identity):
                payload["geojson_filename"] = geojson_path.name
                return payload

    preview = build_artifact_preview(artifact, output_dir=preview_dir)
    geojson_filename = Path(preview["geojson_path"]).name
    payload = {
        "run_id": run_id,
        **preview,
        "artifact_identity": artifact_identity,
        "geojson_path": _preview_route_path(run_id),
        "geojson_filename": geojson_filename,
    }
    metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _load_run_preview(run_id: str) -> ArtifactPreviewResponse:
    payload = _load_run_preview_payload(run_id)
    return ArtifactPreviewResponse.model_validate(_build_public_preview_payload(payload))


@router.get("/runs", response_model=OperatorRunListResponse)
async def list_runs(
    limit: int = Query(default=50, ge=1, le=100),
    phase: Optional[str] = None,
    job_type: Optional[str] = None,
) -> OperatorRunListResponse:
    records = RunRegistryService(runs_root=Path("runs")).list_records(
        limit=limit,
        phase=phase,
        job_type=job_type,
    )
    return OperatorRunListResponse(records=records)


@router.post("/runs", response_model=RunCreateResponse)
async def create_run(
    osm_zip: Optional[UploadFile] = File(None),
    ref_zip: Optional[UploadFile] = File(None),
    job_type: JobType = Form(...),
    trigger_type: RunTriggerType = Form(RunTriggerType.user_query),
    trigger_content: str = Form("manual trigger"),
    disaster_type: Optional[str] = Form(None),
    spatial_extent: Optional[str] = Form(None),
    temporal_start: Optional[str] = Form(None),
    temporal_end: Optional[str] = Form(None),
    target_crs: Optional[str] = Form(None),
    field_mapping: str = Form("{}"),
    debug: bool = Form(False),
    input_strategy: RunInputStrategy = Form(RunInputStrategy.uploaded),
    preferred_pattern_id: Optional[str] = Form(None),
) -> RunCreateResponse:
    if input_strategy == RunInputStrategy.uploaded:
        if osm_zip is None or ref_zip is None:
            raise HTTPException(status_code=400, detail="uploaded mode requires osm_zip and ref_zip")
        if not osm_zip.filename or not osm_zip.filename.lower().endswith(".zip"):
            raise HTTPException(status_code=400, detail="osm_zip must be a .zip file")
        if not ref_zip.filename or not ref_zip.filename.lower().endswith(".zip"):
            raise HTTPException(status_code=400, detail="ref_zip must be a .zip file")
    else:
        if osm_zip is not None or ref_zip is not None:
            raise HTTPException(status_code=400, detail="task_driven_auto mode does not accept uploaded files")

    try:
        normalized_crs = normalize_explicit_target_crs(target_crs)
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
        input_strategy=input_strategy,
        preferred_pattern_id=preferred_pattern_id,
    )

    issues = classify_unsupported_intent(request.trigger.content, job_type=request.job_type)
    if issues:
        raise HTTPException(status_code=422, detail={"unsupported_intent": issues})

    osm_bytes = await osm_zip.read() if osm_zip is not None else None
    ref_bytes = await ref_zip.read() if ref_zip is not None else None
    if input_strategy == RunInputStrategy.uploaded:
        if not osm_bytes:
            raise HTTPException(status_code=400, detail="osm_zip is empty")
        if not ref_bytes:
            raise HTTPException(status_code=400, detail="ref_zip is empty")

    status = agent_run_service.create_run(
        request=request,
        osm_zip_name=(osm_zip.filename if osm_zip is not None else None),
        osm_zip_bytes=osm_bytes,
        ref_zip_name=(ref_zip.filename if ref_zip is not None else None),
        ref_zip_bytes=ref_bytes,
    )
    return RunCreateResponse(run_id=status.run_id, phase=status.phase)


@router.post("/runs/preflight", response_model=RunPreflightResponse)
async def preflight_run(request: RunCreateRequest) -> RunPreflightResponse:
    issues = classify_unsupported_intent(
        request.trigger.content,
        job_type=request.job_type,
    )
    return RunPreflightResponse(allowed=not issues, unsupported_intent=issues)


@router.get("/operator/recovery", response_model=OperatorRecoveryResponse)
async def get_operator_recovery(
    stale_after_seconds: int = Query(default=300, ge=1, le=86400),
) -> OperatorRecoveryResponse:
    records = agent_run_service.collect_recoverable_runs(
        stale_after_seconds=stale_after_seconds,
    )
    return OperatorRecoveryResponse(records=records)


@router.post("/operator/recovery", response_model=OperatorRecoveryExecuteResponse)
async def execute_operator_recovery(request: OperatorRecoveryExecuteRequest) -> OperatorRecoveryExecuteResponse:
    executor = RunRecoveryExecutor(
        runs_root=agent_run_service.base_dir,
        agent_run_service=agent_run_service,
    )
    if request.run_id:
        status = agent_run_service.get_run(request.run_id)
        if status is None:
            raise HTTPException(status_code=404, detail=f"Run not found: {request.run_id}")
        hint = build_recovery_hint(status.model_dump(mode="json"))
        action = str(hint.get("recovery_action") or "")
        if action == "none":
            return OperatorRecoveryExecuteResponse(
                enabled=True,
                result={"status": "skipped", "reason": "not_recoverable"},
            )
        result = executor.recover_run(run_id=request.run_id, recovery_action=action)
    else:
        result = executor.recover_stale_runs(
            stale_after_seconds=request.stale_after_seconds,
            limit=request.limit,
        )
    return OperatorRecoveryExecuteResponse(enabled=True, result=result)


@router.get("/runs/{run_id}", response_model=RunStatus)
async def get_run_status(run_id: str) -> RunStatus:
    return _require_run_status(run_id)


@router.get("/runs/{run_id}/plan", response_model=RunPlanResponse)
async def get_run_plan(run_id: str) -> RunPlanResponse:
    status = _require_run_status(run_id)
    plan = _require_run_plan(run_id, status)
    return RunPlanResponse(run_id=run_id, plan=plan)


@router.get("/runs/{run_id}/audit", response_model=RunAuditResponse)
async def get_run_audit(run_id: str) -> RunAuditResponse:
    status = _require_run_status(run_id)
    return RunAuditResponse(run_id=run_id, events=agent_run_service.get_audit_events(run_id))


@router.get("/runs/{run_id}/inspection", response_model=RunInspectionResponse)
async def get_run_inspection(run_id: str) -> RunInspectionResponse:
    status = _require_run_status(run_id)
    return _build_run_inspection_response(run_id, status)


@router.get("/runs/{run_id}/kg-graph", response_model=KgGraphResponse)
async def get_run_kg_graph(run_id: str) -> KgGraphResponse:
    status = _require_run_status(run_id)
    plan = _require_run_plan(run_id, status)
    return build_run_path_graph(plan)


@router.get("/runs/{run_id}/preview", response_model=ArtifactPreviewResponse)
async def get_run_preview(run_id: str) -> ArtifactPreviewResponse:
    return _load_run_preview(run_id)


@router.get("/runs/{run_id}/preview.geojson")
async def get_run_preview_geojson(run_id: str) -> FileResponse:
    preview = _load_run_preview_payload(run_id)
    geojson_path = _resolve_preview_geojson_path(preview, _preview_output_dir(run_id).resolve())
    if geojson_path is None:
        raise HTTPException(status_code=404, detail="Preview GeoJSON not found")
    return FileResponse(path=str(geojson_path), filename=geojson_path.name, media_type="application/geo+json")


@router.get("/runs/{run_id}/documents", response_model=RunDocumentListResponse)
async def list_run_documents(run_id: str) -> RunDocumentListResponse:
    service = RunDocumentService(runs_root=Path(getattr(agent_run_service, "base_dir", Path("runs"))))
    try:
        documents = service.list_documents(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RunDocumentListResponse(run_id=run_id, documents=documents)


@router.get("/runs/{run_id}/documents/{filename:path}", response_model=RunMarkdownDocumentResponse)
async def get_run_document(run_id: str, filename: str) -> RunMarkdownDocumentResponse:
    service = RunDocumentService(runs_root=Path(getattr(agent_run_service, "base_dir", Path("runs"))))
    try:
        return service.read_document(run_id, filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runtime", response_model=RuntimeMetadataResponse)
async def get_runtime_metadata() -> RuntimeMetadataResponse:
    return _build_runtime_metadata_response()


@router.get("/operator/summary", response_model=OperatorRuntimeSummaryResponse)
async def get_operator_summary(limit: int = Query(default=10, ge=1, le=100)) -> OperatorRuntimeSummaryResponse:
    service = OperatorReadModelService(
        runs_root=Path(getattr(agent_run_service, "base_dir", Path("runs"))),
        scenario_output_root=resolve_scenario_output_root(None),
    )
    return OperatorRuntimeSummaryResponse(**service.runtime_summary(limit=limit))


@router.get("/runs/{left_run_id}/compare/{right_run_id}", response_model=RunComparisonResponse)
async def compare_runs(left_run_id: str, right_run_id: str) -> RunComparisonResponse:
    left = agent_run_service.get_run(left_run_id)
    if left is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {left_run_id}")
    right = agent_run_service.get_run(right_run_id)
    if right is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {right_run_id}")

    left_decisions = _selected_decisions(left)
    right_decisions = _selected_decisions(right)
    differing_decisions = {
        decision_type: {
            "left": left_decisions.get(decision_type),
            "right": right_decisions.get(decision_type),
        }
        for decision_type in sorted(set(left_decisions) | set(right_decisions))
        if left_decisions.get(decision_type) != right_decisions.get(decision_type)
    }
    return RunComparisonResponse(
        left=_build_run_inspection_response(left_run_id, left),
        right=_build_run_inspection_response(right_run_id, right),
        differing_decisions=differing_decisions,
    )


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
