from agent.planner import WorkflowPlanner
from kg.inmemory_repository import InMemoryKGRepository
from kg.seed import (
    ALGORITHMS,
    CAN_TRANSFORM_TO,
    DATA_NEEDS,
    DATA_SOURCES,
    DATA_TYPES,
    OUTPUT_SCHEMA_POLICIES,
    OUTPUT_REQUIREMENTS,
    QOS_POLICIES,
    REPAIR_STRATEGIES,
    TASKS,
    TASK_BUNDLES,
    WORKFLOW_PATTERNS,
)
from llm.providers.base import LLMProvider
from schemas.agent import RunTrigger, RunTriggerType
from schemas.fusion import JobType
from services.kg_graph_service import build_overview_graph, build_run_path_graph


class _ClosureProvider(LLMProvider):
    def __init__(self) -> None:
        self.model = "closure-provider"

    def generate_workflow_plan(self, system_prompt: str, context: dict) -> dict:
        candidate = context["retrieval"]["candidate_patterns"][0]
        first_step = candidate["steps"][0]
        return {
            "workflow_id": "wf-closure",
            "trigger": context["intent"]["trigger"],
            "context": {"source": "closure-test"},
            "tasks": [
                {
                    "step": 1,
                    "name": first_step["name"],
                    "description": "closure task",
                    "algorithm_id": first_step["algorithm_id"],
                    "input": {
                        "data_type_id": first_step["input_data_type"],
                        "data_source_id": first_step["data_source_id"],
                        "parameters": {},
                    },
                    "output": {
                        "data_type_id": first_step["output_data_type"],
                        "description": "closure output",
                    },
                    "depends_on": [],
                    "is_transform": False,
                    "kg_validated": False,
                    "alternatives": [],
                }
            ],
            "expected_output": "closure result",
            "estimated_time": "5m",
        }


def test_kg_context_exposes_seeded_data_types() -> None:
    context = InMemoryKGRepository().build_context(job_type=JobType.building, disaster_type="flood")

    exposed = {item.type_id for item in context.data_types}

    assert "dt.building.bundle" in exposed
    assert "dt.building.fused" in exposed
    assert set(DATA_TYPES).issubset(exposed)


def test_seed_ontology_data_type_references_are_closed() -> None:
    known = set(DATA_TYPES)
    missing: list[str] = []

    for algorithm in ALGORITHMS.values():
        for type_id in [*algorithm.input_types, algorithm.output_type]:
            if type_id not in known:
                missing.append(f"algorithm:{algorithm.algo_id}:{type_id}")

    for source in DATA_SOURCES:
        for type_id in source.supported_types:
            if type_id not in known:
                missing.append(f"source:{source.source_id}:{type_id}")

    for pattern in WORKFLOW_PATTERNS:
        for step in pattern.steps:
            for type_id in [step.input_data_type, step.output_data_type]:
                if type_id not in known:
                    missing.append(f"pattern:{pattern.pattern_id}:{type_id}")

    for policy in OUTPUT_SCHEMA_POLICIES.values():
        if policy.output_type not in known:
            missing.append(f"schema_policy:{policy.policy_id}:{policy.output_type}")

    for from_type, to_types in CAN_TRANSFORM_TO.items():
        if from_type not in known:
            missing.append(f"transform:from:{from_type}")
        for to_type in to_types:
            if to_type not in known:
                missing.append(f"transform:to:{to_type}")

    assert missing == []


def test_water_seed_records_exist() -> None:
    assert "dt.water.bundle" in DATA_TYPES
    assert "dt.water.fused" in DATA_TYPES
    assert "task.water.fusion" in TASKS
    assert "algo.fusion.water.v1" in ALGORITHMS
    assert OUTPUT_SCHEMA_POLICIES["dt.water.fused"].policy_id == "osp.water.fused.v1"
    water_pattern = next(pattern for pattern in WORKFLOW_PATTERNS if pattern.job_type == JobType.water)
    assert water_pattern.metadata["input_strategy"] == "task_driven_auto_supported"
    assert water_pattern.metadata["source_family"] == "catalog_water_bundle"
    water_source = next(source for source in DATA_SOURCES if source.source_id == "catalog.flood.water")
    assert water_source.supported_types == ["dt.water.bundle"]
    assert water_source.metadata["component_source_ids"] == ["raw.osm.water", "raw.hydrolakes.water"]
    water_policy_note = OUTPUT_SCHEMA_POLICIES["dt.water.fused"].metadata["notes"]
    assert "uploaded-only" not in water_policy_note
    assert "shared bundle runtime" in water_policy_note


def test_poi_seed_records_exist() -> None:
    assert JobType.poi.value == "poi"
    assert "dt.poi.bundle" in DATA_TYPES
    assert "dt.poi.fused" in DATA_TYPES
    assert "task.poi.fusion" in TASKS
    assert "algo.fusion.poi.v1" in ALGORITHMS
    assert OUTPUT_SCHEMA_POLICIES["dt.poi.fused"].policy_id == "osp.poi.fused.v1"
    poi_pattern = next(pattern for pattern in WORKFLOW_PATTERNS if pattern.job_type == JobType.poi)
    assert poi_pattern.pattern_id == "wp.generic.poi.default"
    poi_source = next(source for source in DATA_SOURCES if source.source_id == "catalog.generic.poi")
    assert poi_source.supported_types == ["dt.poi.bundle"]
    assert poi_source.metadata["component_source_ids"] == ["raw.osm.poi", "raw.gns.poi"]


def test_trajectory_to_road_seam_seed_records_exist() -> None:
    assert "dt.trajectory.raw" in DATA_TYPES
    assert "dt.road.candidate" in DATA_TYPES
    assert "task.trajectory_to_road" in TASKS
    assert "algo.transform.trajectory_to_road_candidate" in ALGORITHMS
    assert "dt.trajectory.raw" in CAN_TRANSFORM_TO
    assert CAN_TRANSFORM_TO["dt.trajectory.raw"] == ["dt.road.candidate"]


def test_seed_ontology_closure_exposes_task_bundles_and_constraint_objects() -> None:
    assert "task_bundle.direct_request" in TASK_BUNDLES
    assert "or.building.fused.v1" in OUTPUT_REQUIREMENTS
    assert "qos.task.default.v1" in QOS_POLICIES
    assert any(item.need_id == "dn.task.building.fusion.input" for item in DATA_NEEDS)
    assert "repair.source_fallback.v1" in REPAIR_STRATEGIES

    direct = TASK_BUNDLES["task_bundle.direct_request"]
    assert "task.water.fusion" in direct.requested_tasks
    assert direct.qos_policy_id == "qos.task.default.v1"
    assert "repair.alternative_algorithm.v1" in direct.repair_strategy_ids


def test_track_a_closure_gate_covers_graph_api_and_planner_runtime_consumption() -> None:
    repo = InMemoryKGRepository()
    planner = WorkflowPlanner(repo, _ClosureProvider())
    trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="need building data for Gilgit, Pakistan",
    )

    plan = planner.create_plan(run_id="run-closure", job_type=JobType.building, trigger=trigger)
    overview = build_overview_graph(repo)
    runtime_graph = build_run_path_graph(plan)

    assert plan.task_bundle is not None
    assert plan.output_requirement is not None
    assert plan.qos_policy is not None
    assert plan.data_needs
    assert plan.repair_strategies
    assert all(task.task_id for task in plan.tasks)

    assert overview.meta["graph_type"] == "overview_closure_graph"
    assert runtime_graph.meta["graph_type"] == "runtime_path_graph"
    assert any(node.kind == "parameter_spec" for node in overview.nodes)
    assert any(node.kind == "output_schema_policy" for node in overview.nodes)
    assert any(edge.relationship == "has_parameter_spec" for edge in overview.edges)
    assert any(edge.relationship == "can_transform_to" for edge in overview.edges)
    assert any(item["layer_id"] == "validation_policy" for item in overview.meta["agent_structure"])
    assert runtime_graph.meta["selected_pattern_id"] == plan.context["selected_pattern_id"]
