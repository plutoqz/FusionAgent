from __future__ import annotations

from fastapi import APIRouter, HTTPException

from kg.factory import create_kg_repository
from schemas.agent import RunPhase, RunStatus
from schemas.kg_graph import KgGraphResponse
from services.agent_run_service import agent_run_service
from services.kg_graph_service import build_overview_graph, build_run_path_graph


router = APIRouter(tags=["kg"])


def _require_run_status(run_id: str) -> RunStatus:
    status = agent_run_service.get_run(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return status


def _require_run_plan(run_id: str, status: RunStatus):
    plan = agent_run_service.get_plan(run_id)
    if plan is None:
        if status.phase in {RunPhase.queued, RunPhase.planning}:
            raise HTTPException(status_code=409, detail=f"Plan not ready yet: {status.phase.value}")
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.get("/kg/overview", response_model=KgGraphResponse)
async def get_kg_overview() -> KgGraphResponse:
    repo = create_kg_repository()
    try:
        return build_overview_graph(repo)
    finally:
        close = getattr(repo, "close", None)
        if callable(close):
            close()


@router.get("/kg/runs/{run_id}/runtime-path", response_model=KgGraphResponse)
async def get_runtime_path_graph(run_id: str) -> KgGraphResponse:
    status = _require_run_status(run_id)
    plan = _require_run_plan(run_id, status)
    return build_run_path_graph(plan)
