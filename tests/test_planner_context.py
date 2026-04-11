from typing import Any, Dict

from agent.planner import WorkflowPlanner
from kg.inmemory_repository import InMemoryKGRepository
from kg.models import DurableLearningRecord
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
    assert plan.context["planning_mode"] == "scenario_driven"
    assert plan.context["intent"]["profile_source"] == "disaster_type"


def test_planner_context_records_task_driven_mode_for_direct_data_request() -> None:
    provider = CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)
    trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="need building and road data for Gilgit, Pakistan",
    )

    plan = planner.create_plan(run_id="run-task-driven", job_type=JobType.building, trigger=trigger)

    assert provider.last_context is not None
    assert provider.last_context["intent"]["planning_mode"] == "task_driven"
    assert provider.last_context["intent"]["profile_source"] == "direct_task"
    assert plan.context["planning_mode"] == "task_driven"


def test_planner_context_exposes_task_bundle_task_nodes_and_scenario_profiles() -> None:
    provider = CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)
    trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="need building and road data for Gilgit, Pakistan",
    )

    _plan = planner.create_plan(run_id="run-task-bundle", job_type=JobType.building, trigger=trigger)

    assert provider.last_context is not None
    assert provider.last_context["intent"]["task_bundle"]["bundle_id"] == "task_bundle.direct_request"
    assert any(item["task_id"] == "task.building.fusion" for item in provider.last_context["retrieval"]["task_nodes"])
    assert any(
        item["profile_id"] == "scenario.default.task"
        for item in provider.last_context["retrieval"]["scenario_profiles"]
    )


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


def test_planner_context_surfaces_multiple_pattern_candidates_when_policy_choice_should_matter() -> None:
    provider = CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)
    trigger = RunTrigger(
        type=RunTriggerType.disaster_event,
        content="earthquake building fusion with fallback choice",
        disaster_type="earthquake",
    )

    _plan = planner.create_plan(run_id="run-earthquake", job_type=JobType.building, trigger=trigger)

    assert provider.last_context is not None
    patterns = provider.last_context["retrieval"]["candidate_patterns"]
    pattern_ids = [item["pattern_id"] for item in patterns]

    assert len(patterns) >= 3
    assert "wp.earthquake.building.default" in pattern_ids
    assert "wp.earthquake.building.safe" in pattern_ids
    assert any(item["metadata"].get("runtime_status") == "runtime_candidate" for item in patterns)


def test_planner_context_exposes_richer_algorithm_and_data_source_metadata() -> None:
    provider = CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)
    trigger = RunTrigger(
        type=RunTriggerType.disaster_event,
        content="earthquake building fusion with source choice",
        disaster_type="earthquake",
    )

    _plan = planner.create_plan(run_id="run-metadata", job_type=JobType.building, trigger=trigger)

    assert provider.last_context is not None
    algorithms = provider.last_context["retrieval"]["algorithms"]
    building_algo = algorithms["algo.fusion.building.v1"]
    assert building_algo["accuracy_score"] == 0.89
    assert building_algo["stability_score"] == 0.74
    assert building_algo["usage_mode"] == "throughput"
    assert building_algo["metadata"]["selection_profile"] == "primary"

    data_sources = provider.last_context["retrieval"]["data_sources"]
    source = next(item for item in data_sources if item["source_id"] == "catalog.earthquake.building")
    assert source["source_kind"] == "catalog"
    assert source["quality_tier"] == "curated"
    assert source["freshness_category"] == "event_snapshot"
    assert source["freshness_hours"] == 96
    assert source["freshness_score"] == 0.71
    assert source["supported_job_types"] == ["building"]
    assert source["supported_geometry_types"] == ["polygon"]


def test_planner_context_exposes_component_source_metadata_for_catalog_sources() -> None:
    provider = CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)
    trigger = RunTrigger(
        type=RunTriggerType.disaster_event,
        content="flood building fusion with source components",
        disaster_type="flood",
    )

    _plan = planner.create_plan(run_id="run-source-components", job_type=JobType.building, trigger=trigger)

    assert provider.last_context is not None
    data_sources = provider.last_context["retrieval"]["data_sources"]
    source = next(item for item in data_sources if item["source_id"] == "catalog.flood.building")
    assert source["metadata"]["component_source_ids"] == ["raw.osm.building", "raw.google.building"]
    assert source["metadata"]["bundle_strategy"] == "osm_ref_pair"
    assert source["metadata"]["provider_family"] == "local_bundle_catalog"


def test_planner_context_exposes_parameter_specs_and_output_schema_policy_metadata() -> None:
    provider = CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)
    trigger = RunTrigger(
        type=RunTriggerType.disaster_event,
        content="flood building fusion with schema expectations",
        disaster_type="flood",
    )

    _plan = planner.create_plan(run_id="run-schema-metadata", job_type=JobType.building, trigger=trigger)

    assert provider.last_context is not None
    parameter_specs = provider.last_context["retrieval"]["parameter_specs"]
    output_schema_policies = provider.last_context["retrieval"]["output_schema_policies"]

    building_safe_specs = parameter_specs["algo.fusion.building.safe"]
    match_spec = next(item for item in building_safe_specs if item["key"] == "match_similarity_threshold")
    assert match_spec["tunable"] is True
    assert "precision" in match_spec["optimization_tags"]

    building_output_policy = output_schema_policies["dt.building.fused"]
    assert building_output_policy["retention_mode"] == "preserve_listed"
    assert "geometry" in building_output_policy["required_fields"]
    assert "confidence" in building_output_policy["optional_fields"]
    assert building_output_policy["rename_hints"]["geometry_x"] == "geometry"


def test_planner_context_exposes_durable_learning_summaries() -> None:
    repo = InMemoryKGRepository()
    repo.record_durable_learning_record(
        DurableLearningRecord(
            record_id="dlr-summary-1",
            run_id="run-summary-1",
            job_type=JobType.building,
            trigger_type="disaster_event",
            success=True,
            disaster_type="flood",
            pattern_id="wp.flood.building.default",
            algorithm_id="algo.fusion.building.v1",
            selected_data_source="upload.bundle",
            output_data_type="dt.building.fused",
            target_crs="EPSG:32643",
            repaired=False,
            repair_count=0,
            plan_revision=1,
            created_at="2026-04-09T01:00:00+00:00",
        )
    )
    provider = CapturingProvider()
    planner = WorkflowPlanner(repo, provider)
    trigger = RunTrigger(
        type=RunTriggerType.disaster_event,
        content="flood building fusion with prior evidence",
        disaster_type="flood",
    )

    _plan = planner.create_plan(run_id="run-durable-summary", job_type=JobType.building, trigger=trigger)

    assert provider.last_context is not None
    durable = provider.last_context["retrieval"]["durable_learning_summaries"]
    assert durable["patterns"][0]["entity_id"] == "wp.flood.building.default"
    assert durable["patterns"][0]["total_runs"] == 1
    assert durable["patterns"][0]["success_count"] == 1
    assert durable["algorithms"][0]["entity_id"] == "algo.fusion.building.v1"
