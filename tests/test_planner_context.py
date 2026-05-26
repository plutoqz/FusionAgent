import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Any, Dict

from agent.planner import WorkflowPlanner
from kg.inmemory_repository import InMemoryKGRepository
from kg.models import DurableLearningRecord
from llm.providers.base import LLMProvider
from schemas.agent import RunTrigger, RunTriggerType, WorkflowPlan
from schemas.fusion import JobType
from services.aoi_resolution_service import AOIResolutionService
from services.run_telemetry_service import estimate_json_size_bytes


class CapturingProvider(LLMProvider):
    def __init__(self) -> None:
        self.last_context: Dict[str, Any] | None = None
        self.model = "capturing-model"

    def generate_workflow_plan(self, system_prompt: str, context: Dict[str, Any]) -> Dict[str, Any]:
        self.last_context = context
        self.last_usage = {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}
        self.last_model = "capturing-plan-model"
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


class StubGeocoder:
    def __init__(self, results):
        self.results = results

    def search(self, query: str):
        return list(self.results)


class FailingProvider(LLMProvider):
    def __init__(self) -> None:
        self.model = "failing-model"

    def generate_workflow_plan(self, system_prompt: str, context: Dict[str, Any]) -> Dict[str, Any]:
        raise RuntimeError("simulated planning failure")


class SlowObservableProvider(CapturingProvider):
    def __init__(self) -> None:
        super().__init__()
        self._lock = Lock()
        self._active_calls = 0
        self.max_active_calls = 0
        self._call_no = 0

    def generate_workflow_plan(self, system_prompt: str, context: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            self._call_no += 1
            call_no = self._call_no
            self._active_calls += 1
            self.max_active_calls = max(self.max_active_calls, self._active_calls)
        try:
            time.sleep(0.05)
            self.last_context = context
            self.last_usage = {
                "prompt_tokens": call_no,
                "completion_tokens": call_no + 100,
                "total_tokens": call_no + 200,
            }
            self.last_model = f"observable-model-{call_no}"
            candidate = context["retrieval"]["candidate_patterns"][0]
            first_step = candidate["steps"][0]
            return {
                "workflow_id": f"wf_observable_{call_no}",
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
        finally:
            with self._lock:
                self._active_calls -= 1


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
    assert plan.context["planning_source"] == "llm"
    assert plan.context["planning_mode"] == "scenario_driven"
    assert plan.context["intent"]["profile_source"] == "disaster_type"
    assert plan.context["planning_telemetry"] == {
        "elapsed_ms": plan.context["planning_telemetry"]["elapsed_ms"],
        "context_size_bytes": estimate_json_size_bytes(provider.last_context),
        "provider": "capturing",
        "model": "capturing-plan-model",
        "llm_usage": {
            "prompt_tokens": 10,
            "completion_tokens": 4,
            "total_tokens": 14,
        },
    }
    assert isinstance(plan.context["planning_telemetry"]["elapsed_ms"], int)
    assert plan.context["planning_telemetry"]["elapsed_ms"] >= 0


def test_planner_serializes_shared_provider_usage_capture() -> None:
    provider = SlowObservableProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)
    triggers = [
        RunTrigger(
            type=RunTriggerType.disaster_event,
            content=f"flood response building fusion {idx}",
            disaster_type="flood",
        )
        for idx in range(2)
    ]

    with ThreadPoolExecutor(max_workers=2) as pool:
        plans = list(
            pool.map(
                lambda trigger: planner.create_plan(
                    run_id=f"run-{trigger.content[-1]}",
                    job_type=JobType.building,
                    trigger=trigger,
                ),
                triggers,
            )
        )

    assert provider.max_active_calls == 1
    for plan in plans:
        call_no = int(plan.workflow_id.rsplit("_", 1)[1])
        telemetry = plan.context["planning_telemetry"]
        assert telemetry["model"] == f"observable-model-{call_no}"
        assert telemetry["llm_usage"]["total_tokens"] == call_no + 200


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
    assert provider.last_context["intent"]["effective_scenario_profile_id"] == "scenario.default.task"
    assert "task.building.fusion" in provider.last_context["intent"]["effective_activated_tasks"]
    assert "task.road.fusion" in provider.last_context["intent"]["effective_activated_tasks"]
    assert provider.last_context["intent"]["effective_preferred_output_fields"] == ["geometry"]
    assert provider.last_context["intent"]["qos_policy"]["policy_id"] == "qos.task.default.v1"
    assert provider.last_context["retrieval"]["task_bundles"]
    assert provider.last_context["retrieval"]["output_requirements"]["dt.building.fused"]["requirement_id"] == (
        "or.building.fused.v1"
    )
    assert provider.last_context["retrieval"]["qos_policies"]["qos.task.default.v1"]["policy_name"] == (
        "Direct Task Default QoS"
    )
    assert any(
        item["need_id"] == "dn.task.building.fusion.input"
        for item in provider.last_context["retrieval"]["data_needs"]
    )
    assert any(
        item["strategy_id"] == "repair.source_fallback.v1"
        for item in provider.last_context["retrieval"]["repair_strategies"]
    )


def test_planner_context_exposes_data_types() -> None:
    provider = CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)
    trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="need building data for Gilgit, Pakistan",
    )

    _plan = planner.create_plan(run_id="run-data-types", job_type=JobType.building, trigger=trigger)

    assert provider.last_context is not None
    data_types = provider.last_context["retrieval"]["data_types"]
    assert any(item["type_id"] == "dt.building.bundle" for item in data_types)
    assert any(item["type_id"] == "dt.building.fused" for item in data_types)


def test_planner_context_exposes_water_metadata_and_builds_water_plan() -> None:
    provider = CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)
    trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="need water polygons for Nairobi, Kenya",
    )

    plan = planner.create_plan(run_id="run-water-context", job_type=JobType.water, trigger=trigger)

    assert provider.last_context is not None
    assert provider.last_context["intent"]["planning_mode"] == "task_driven"
    assert provider.last_context["intent"]["profile_source"] == "direct_task"
    retrieval = provider.last_context["retrieval"]
    pattern_ids = [item["pattern_id"] for item in retrieval["candidate_patterns"]]
    assert "wp.flood.water.default" in pattern_ids
    assert any(pattern_id in pattern_ids for pattern_id in ("wp.flood.waterways.default", "wp.waterways.fusioncode.conflation.v7"))
    default_pattern = next(item for item in retrieval["candidate_patterns"] if item["pattern_id"] == "wp.flood.water.default")
    assert default_pattern["metadata"]["input_strategy"] == "task_driven_auto_supported"
    assert default_pattern["metadata"]["source_family"] == "catalog_water_bundle"
    assert any(item["type_id"] == "dt.water.bundle" for item in retrieval["data_types"])
    assert any(item["type_id"] == "dt.water.fused" for item in retrieval["data_types"])
    assert "algo.fusion.water_polygon.priority_merge.v2" in retrieval["algorithms"]
    assert "dt.water.fused" in retrieval["output_schema_policies"]
    assert retrieval["transform_paths"]["dt.water.bundle"] == []
    water_source = next(item for item in retrieval["data_sources"] if item["source_id"] == "catalog.flood.water")
    assert water_source["metadata"]["component_source_ids"] == ["raw.osm.water", "raw.hydrolakes.water"]
    assert water_source["metadata"]["provider_family"] == "local_bundle_catalog"
    assert plan.tasks[0].algorithm_id == "algo.fusion.water_polygon.priority_merge.v2"
    assert plan.tasks[0].input.data_type_id == "dt.water.bundle"
    assert plan.tasks[0].input.data_source_id == "catalog.flood.water"
    assert plan.tasks[0].output.data_type_id == "dt.water.fused"


def test_planner_context_exposes_poi_metadata_and_builds_poi_plan() -> None:
    provider = CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)
    trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="show hospitals in Nairobi, Kenya",
    )

    plan = planner.create_plan(run_id="run-poi-context", job_type=JobType.poi, trigger=trigger)

    assert provider.last_context is not None
    assert provider.last_context["intent"]["planning_mode"] == "task_driven"
    assert provider.last_context["intent"]["profile_source"] == "direct_task"
    retrieval = provider.last_context["retrieval"]
    pattern_ids = [item["pattern_id"] for item in retrieval["candidate_patterns"]]
    assert "wp.generic.poi.default" in pattern_ids
    assert "wp.poi.fusioncode.geohash_priority.v1" in pattern_ids
    assert any(item["type_id"] == "dt.poi.bundle" for item in retrieval["data_types"])
    assert any(item["type_id"] == "dt.poi.fused" for item in retrieval["data_types"])
    assert "algo.fusion.poi.v1" in retrieval["algorithms"]
    assert "dt.poi.fused" in retrieval["output_schema_policies"]
    assert retrieval["transform_paths"]["dt.poi.bundle"] == ["dt.raw.vector", "dt.poi.bundle"]
    poi_source = next(item for item in retrieval["data_sources"] if item["source_id"] == "catalog.generic.poi")
    assert poi_source["metadata"]["component_source_ids"] == ["raw.osm.poi", "raw.gns.poi"]
    assert poi_source["metadata"]["provider_family"] == "local_bundle_catalog"
    assert plan.tasks[0].algorithm_id == "algo.fusion.poi.v1"
    assert plan.tasks[0].input.data_type_id == "dt.poi.bundle"
    assert plan.tasks[0].input.data_source_id == "catalog.generic.poi"
    assert plan.tasks[0].output.data_type_id == "dt.poi.fused"


def test_planner_context_preferred_pattern_override_reorders_candidates_and_selected_pattern() -> None:
    provider = CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)
    planner.context_builder.preferred_pattern_id_override = "wp.road.fusioncode.conflation.v7"
    trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="need road data for Gilgit city, Pakistan",
    )

    try:
        plan = planner.create_plan(run_id="run-road-override", job_type=JobType.road, trigger=trigger)
    finally:
        planner.context_builder.preferred_pattern_id_override = None

    assert provider.last_context is not None
    patterns = provider.last_context["retrieval"]["candidate_patterns"]
    assert patterns[0]["pattern_id"] == "wp.road.fusioncode.conflation.v7"
    assert plan.tasks[0].algorithm_id == "algo.fusion.road.conflation.v7"
    assert plan.context["execution_hints"]["preferred_pattern_id"] == "wp.road.fusioncode.conflation.v7"
    assert plan.context["selected_pattern_id"] == "wp.road.fusioncode.conflation.v7"


def test_planner_context_exposes_reserved_trajectory_to_road_seams_without_changing_default_runtime_plan() -> None:
    provider = CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)
    trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="need road data for Gilgit, Pakistan",
    )

    plan = planner.create_plan(run_id="run-trajectory-road-seam", job_type=JobType.road, trigger=trigger)

    assert provider.last_context is not None
    retrieval = provider.last_context["retrieval"]
    assert any(item["type_id"] == "dt.trajectory.raw" for item in retrieval["data_types"])
    assert any(item["type_id"] == "dt.road.candidate" for item in retrieval["data_types"])
    assert any(item["task_id"] == "task.trajectory_to_road" for item in retrieval["task_nodes"])
    assert "algo.transform.trajectory_to_road_candidate" in retrieval["algorithms"]
    assert retrieval["algorithms"]["algo.transform.trajectory_to_road_candidate"]["tool_ref"] == (
        "builtin:trajectory_pretransform_reserved"
    )
    assert plan.tasks[0].algorithm_id == "algo.fusion.road.conflation.v7"
    assert plan.tasks[0].input.data_type_id == "dt.road.bundle"
    assert plan.tasks[0].input.data_source_id == "catalog.flood.road"
    assert all(task.algorithm_id != "algo.transform.trajectory_to_road_candidate" for task in plan.tasks)


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
                    "algorithm_id": "algo.fusion.road.conflation.v7",
                    "input": {
                        "data_type_id": "dt.road.bundle",
                        "data_source_id": "catalog.flood.road",
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
    assert replanned.context["planning_telemetry"]["provider"] == "capturing"
    assert replanned.context["planning_telemetry"]["model"] == "capturing-plan-model"
    assert replanned.context["planning_telemetry"]["llm_usage"]["total_tokens"] == 14
    assert replanned.tasks[0].alternatives == []


def test_planner_fallback_context_records_telemetry_when_llm_call_fails() -> None:
    planner = WorkflowPlanner(InMemoryKGRepository(), FailingProvider())
    trigger = RunTrigger(
        type=RunTriggerType.disaster_event,
        content="flood response building fusion",
        disaster_type="flood",
    )

    plan = planner.create_plan(run_id="run-fallback-telemetry", job_type=JobType.building, trigger=trigger)

    telemetry = plan.context["planning_telemetry"]
    assert plan.context["llm_provider"] == "failing"
    assert plan.context["planning_source"] == "kg_fallback"
    assert telemetry["provider"] == "failing"
    assert telemetry["model"] == "failing-model"
    assert telemetry["context_size_bytes"] > 0
    assert telemetry["elapsed_ms"] >= 0
    assert telemetry["llm_usage"] == {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
    }


def test_replan_failure_preserves_previous_planning_telemetry_and_records_failed_attempt() -> None:
    planner = WorkflowPlanner(InMemoryKGRepository(), FailingProvider())
    trigger = RunTrigger(type=RunTriggerType.user_query, content="fuse roads")
    previous_telemetry = {
        "elapsed_ms": 7,
        "context_size_bytes": 123,
        "provider": "previous",
        "model": "previous-model",
        "llm_usage": {
            "prompt_tokens": 1,
            "completion_tokens": 2,
            "total_tokens": 3,
        },
    }
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
                "planning_telemetry": previous_telemetry,
            },
            "tasks": [
                {
                    "step": 1,
                    "name": "road_fusion",
                    "description": "execute road fusion",
                    "algorithm_id": "algo.fusion.road.conflation.v7",
                    "input": {
                        "data_type_id": "dt.road.bundle",
                        "data_source_id": "catalog.flood.road",
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
        run_id="run-replan-failed",
        job_type=JobType.road,
        trigger=trigger,
        previous_plan=previous_plan,
        failed_step=1,
        error_message="simulated execution failure",
    )

    assert replanned.context["planning_telemetry"] == previous_telemetry
    assert replanned.context["failed_replan_telemetry"]["provider"] == "failing"
    assert replanned.context["failed_replan_telemetry"]["model"] == "failing-model"
    assert replanned.context["failed_replan_telemetry"]["llm_usage"] == {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
    }


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


def test_planner_context_exposes_reserved_building_sources_and_execution_hints() -> None:
    provider = CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)
    trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="need building data for Benin",
    )

    plan = planner.create_plan(run_id="run-benin-reserved-sources", job_type=JobType.building, trigger=trigger)

    assert provider.last_context is not None
    retrieval = provider.last_context["retrieval"]
    data_sources = retrieval["data_sources"]
    source_ids = {item["source_id"] for item in data_sources}
    assert "raw.openbuildingmap.building" in source_ids
    assert "raw.local.microsoft.building" in source_ids
    assert "raw.google.open_buildings.vector" in source_ids
    assert "raw.google.building_presence.raster" in source_ids

    raster = next(item for item in data_sources if item["source_id"] == "raw.google.building_presence.raster")
    assert raster["metadata"]["runtime_status"] == "reservation_only"
    assert raster["metadata"]["selectable_now"] is False
    assert raster["metadata"]["source_form"] == "raster"
    assert raster["metadata"]["height_semantics"] == "presence_only"

    reserved_capabilities = {
        item["capability_id"] for item in retrieval["reserved_capability_hints"]
    }
    assert "algo.fusion.building.multi_source.decomposed.v1" in reserved_capabilities
    assert "algo.validate.building.presence_raster.v1" in reserved_capabilities
    assert "algo.enrich.building.height_from_raster.v1" in reserved_capabilities

    execution_hints = provider.last_context["execution_hints"]
    assert "raw.google.building_presence.raster" in execution_hints["reserved_source_ids"]
    assert "raw.google.building_presence.raster" not in execution_hints["selectable_source_ids"]
    assert "catalog.earthquake.building" in execution_hints["selectable_source_ids"]
    assert "algo.fusion.building.multi_source.decomposed.v1" in execution_hints["runtime_candidate_capabilities"]
    assert "algo.validate.building.presence_raster.v1" in execution_hints["runtime_candidate_capabilities"]
    assert "algo.enrich.building.height_from_raster.v1" in execution_hints["runtime_candidate_capabilities"]
    assert "algo.fusion.building.multi_source.decomposed.v1" not in execution_hints["required_reserved_capabilities"]
    assert plan.context["execution_hints"]["reserved_source_ids"] == execution_hints["reserved_source_ids"]


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


def test_planner_context_selects_effective_disaster_scenario_profile() -> None:
    provider = CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)
    trigger = RunTrigger(
        type=RunTriggerType.disaster_event,
        content="flood building fusion with active profile",
        disaster_type="flood",
    )

    plan = planner.create_plan(run_id="run-flood-profile", job_type=JobType.building, trigger=trigger)

    assert provider.last_context is not None
    assert provider.last_context["intent"]["effective_scenario_profile_id"] == "scenario.flood.default"
    assert "task.building.fusion" in provider.last_context["intent"]["effective_activated_tasks"]
    assert "confidence" in provider.last_context["intent"]["effective_preferred_output_fields"]
    assert plan.context["intent"]["effective_scenario_profile_id"] == "scenario.flood.default"


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


def test_planner_context_includes_resolved_aoi_and_source_coverage_hints() -> None:
    provider = CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)
    planner.context_builder.aoi_resolution_service = AOIResolutionService(
        geocoder=StubGeocoder(
            [
                {
                    "display_name": "Nairobi, Nairobi County, Kenya",
                    "lat": "-1.286389",
                    "lon": "36.817223",
                    "boundingbox": ["-1.45", "-1.10", "36.65", "37.10"],
                    "class": "boundary",
                    "type": "administrative",
                    "importance": 0.97,
                    "address": {
                        "city": "Nairobi",
                        "state": "Nairobi County",
                        "country": "Kenya",
                        "country_code": "ke",
                    },
                }
            ]
        )
    )
    trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="fuse building and road data for Nairobi, Kenya",
    )

    plan = planner.create_plan(run_id="run-nairobi", job_type=JobType.building, trigger=trigger)

    assert provider.last_context is not None
    assert provider.last_context["intent"]["location_query"] == "Nairobi, Kenya"
    assert provider.last_context["intent"]["resolved_aoi"]["country_code"] == "ke"
    assert provider.last_context["retrieval"]["source_coverage_hints"]
    assert plan.context["intent"]["resolved_aoi"]["country_code"] == "ke"
