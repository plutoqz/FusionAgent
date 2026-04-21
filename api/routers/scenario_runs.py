from __future__ import annotations

from fastapi import APIRouter

from schemas.scenario import ScenarioRunRequest, ScenarioRunResponse
from services.scenario_run_service import scenario_run_service


router = APIRouter(tags=["scenario-runs"])


@router.post("/scenario-runs", response_model=ScenarioRunResponse)
async def create_scenario_run(request: ScenarioRunRequest) -> ScenarioRunResponse:
    return scenario_run_service.create_scenario_run(request)
