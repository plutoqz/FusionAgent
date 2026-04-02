from __future__ import annotations

import os

import pytest

from agent.planner import WorkflowPlanner
from kg.inmemory_repository import InMemoryKGRepository
from llm.providers.openai_compatible import OpenAICompatibleProvider
from schemas.agent import RunTrigger, RunTriggerType
from schemas.fusion import JobType


def _live_smoke_enabled() -> bool:
    return os.getenv("GEOFUSION_LIVE_SMOKE", "").strip() == "1"


@pytest.mark.skipif(not _live_smoke_enabled(), reason="live smoke disabled")
def test_live_llm_planner_smoke_for_building_and_road() -> None:
    provider = OpenAICompatibleProvider.from_env()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)

    cases = [
        (
            "live-building",
            JobType.building,
            RunTrigger(
                type=RunTriggerType.disaster_event,
                content="flood building fusion live smoke",
                disaster_type="flood",
            ),
        ),
        (
            "live-road",
            JobType.road,
            RunTrigger(
                type=RunTriggerType.disaster_event,
                content="earthquake road fusion live smoke",
                disaster_type="earthquake",
            ),
        ),
    ]

    for run_id, job_type, trigger in cases:
        plan = planner.create_plan(run_id=run_id, job_type=job_type, trigger=trigger)
        assert plan.tasks
        assert plan.context["plan_revision"] == 1
        assert plan.context["llm_provider"] == provider.provider_name
        assert plan.context["retrieval"]["candidate_patterns"]
