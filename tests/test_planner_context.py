from typing import Any, Dict

from agent.planner import WorkflowPlanner
from kg.inmemory_repository import InMemoryKGRepository
from llm.providers.base import LLMProvider
from schemas.agent import RunTrigger, RunTriggerType, WorkflowPlan
from schemas.fusion import JobType


class CapturingProvider(LLMProvider):
    def __init__(self) -> None:
        self.last_context: Dict[str, Any] | None = None

    def generate_workflow_plan(self, system_prompt: str, context: Dict[str, Any]) -> Dict[str, Any]:
        self.last_context = context
        candidate = context["retrieval"]["candidate_patterns"][0]
        first_step = candidate["steps"][0]
        return {
            "workflow_id": "wf_live_context",
            "trigger": context["intent"]["trigger"],
            "context": {"legacy": "llm"},
            "tasks": [
                {
                    "step": 1,
                    "name": first_step["name"],
                    "description": "execute selected workflow",
                    "algorithm_id": first_step["algorithm_id"],
                    "input": {
                        "data_type_id": first_step["input_data_type"],
                        "data_source_id": first_step["data_source_id"],
                        "parameters": {},
                    },
                    "output": {
                        "data_type_id": first_step["output_data_type"],
                        "description": "selected output",
                    },
                    "depends_on": [],
                    "is_transform": False,
                    "kg_validated": False,
                    "alternatives": [],
                }
            ],
            "expected_output": "building fused shapefile",
            "estimated_time": "5m",
        }


def test_planner_builds_stable_context_fields() -> None:
    provider = CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)
    trigger = RunTrigger(
        type=RunTriggerType.disaster_event,
        content="flood response building fusion",
        disaster_type="flood",
        spatial_extent="bbox(0,0,1,1)",
    )

    plan = planner.create_plan(run_id="run-ctx", job_type=JobType.building, trigger=trigger)

    assert provider.last_context is not None
    assert set(provider.last_context.keys()) == {"intent", "retrieval", "constraints", "execution_hints"}
    assert set(plan.context.keys()) >= {"intent", "retrieval", "selection_reason", "llm_provider", "plan_revision"}
    assert plan.context["plan_revision"] == 1
    assert plan.context["llm_provider"] == "capturing"


def test_planner_injects_kg_parameter_defaults_into_task_inputs() -> None:
    provider = CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)
    trigger = RunTrigger(type=RunTriggerType.user_query, content="fuse roads")

    plan = planner.create_plan(run_id="run-param-defaults", job_type=JobType.road, trigger=trigger)

    assert plan.tasks
    params = plan.tasks[0].input.parameters
    assert params["angle_threshold_deg"] == 135
    assert "dedupe_buffer_m" in params


def test_replan_increments_plan_revision() -> None:
    provider = CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)
    trigger = RunTrigger(type=RunTriggerType.user_query, content="fuse roads")
    previous_plan = WorkflowPlan.model_validate(
        {
            "workflow_id": "wf_prev",
            "trigger": trigger.model_dump(),
            "context": {
                "intent": {"job_type": "road"},
                "retrieval": {"candidate_patterns": []},
                "selection_reason": "initial",
                "llm_provider": "capturing",
                "plan_revision": 1,
            },
            "tasks": [
                {
                    "step": 1,
                    "name": "road_fusion",
                    "description": "execute road fusion",
                    "algorithm_id": "algo.fusion.road.v1",
                    "input": {
                        "data_type_id": "dt.road.bundle",
                        "data_source_id": "upload.bundle",
                        "parameters": {},
                    },
                    "output": {"data_type_id": "dt.road.fused", "description": "road output"},
                    "depends_on": [],
                    "is_transform": False,
                    "kg_validated": True,
                    "alternatives": [],
                }
            ],
            "expected_output": "road fused shapefile",
            "estimated_time": "5m",
        }
    )

    replanned = planner.replan_from_error(
        run_id="run-ctx",
        job_type=JobType.road,
        trigger=trigger,
        previous_plan=previous_plan,
        failed_step=1,
        error_message="simulated failure",
    )

    assert replanned.context["plan_revision"] == 2
    assert replanned.context["selection_reason"] == "replanned_after_failure"
    assert replanned.context["failed_step"] == 1
    assert "algo.fusion.road.safe" in replanned.tasks[0].alternatives
