from __future__ import annotations

from agent.tooling import build_default_tool_registry
from fusion_algorithms.registry_metadata import FUSIONCODE_ALGORITHMS
from kg.inmemory_repository import InMemoryKGRepository
from kg.seed_manifest import build_seed_manifest_payload
from schemas.fusion import JobType


def test_decomposed_building_algorithms_are_registered() -> None:
    repo = InMemoryKGRepository()
    required = [
        "algo.preprocess.building.source_normalize.v1",
        "algo.validate.building.presence_raster.v1",
        "algo.match.building.v8_candidate_graph.v1",
        "algo.match.building.v8_component_solver.v1",
        "algo.fusion.building.cascade_geometry_priority.v1",
        "algo.optimize.building.conflict_graph.v1",
        "algo.enrich.building.height_from_raster.v1",
        "algo.assess.building.quality_metrics.v1",
    ]
    missing = [algo_id for algo_id in required if repo.get_algorithm(algo_id) is None]
    assert missing == []


def test_executable_replacements_for_reserved_capabilities_exist() -> None:
    repo = InMemoryKGRepository()
    multi_source = repo.get_algorithm("algo.fusion.building.multi_source.decomposed.v1")
    height = repo.get_algorithm("algo.enrich.building.height_from_raster.v1")
    assert multi_source is not None
    assert multi_source.metadata["runtime_status"] == "runtime_candidate"
    assert height is not None
    assert height.metadata["runtime_status"] == "runtime_candidate"


def test_v8_matching_parameters_are_queryable() -> None:
    repo = InMemoryKGRepository()
    keys = {spec.key for spec in repo.get_parameter_specs("algo.match.building.v8_component_solver.v1")}
    assert {"weak_min_cover", "weak_min_iou", "thresh_1_to_1", "thresh_1_to_N", "thresh_M_to_N"} <= keys


def test_decomposed_building_workflow_has_ordered_steps() -> None:
    repo = InMemoryKGRepository()
    patterns = repo.get_candidate_patterns(job_type=JobType.building, disaster_type="generic", limit=20)
    pattern = next(p for p in patterns if p.pattern_id == "wp.building.drs4br.decomposed.v1")
    assert [step.order for step in pattern.steps] == list(range(1, len(pattern.steps) + 1))
    assert pattern.steps[0].algorithm_id == "algo.preprocess.building.source_normalize.v1"
    assert pattern.steps[-1].algorithm_id == "algo.assess.building.quality_metrics.v1"


def test_generated_manifest_fusioncode_algorithms_are_auditable_against_tool_registry() -> None:
    payload = build_seed_manifest_payload()
    tool_registry = build_default_tool_registry()
    manifest_algorithms = {
        item["algo_id"]: item
        for item in payload["algorithms"]
        if item["algo_id"] in FUSIONCODE_ALGORITHMS
    }

    assert set(manifest_algorithms) == set(FUSIONCODE_ALGORITHMS)

    missing_provenance: list[str] = []
    contract_mismatches: dict[str, dict[str, object]] = {}
    for algo_id, algorithm in manifest_algorithms.items():
        metadata = algorithm.get("metadata") or {}
        if (
            not metadata.get("algorithm_family")
            or not metadata.get("handler_name")
            or not algorithm.get("tool_ref")
        ):
            missing_provenance.append(algo_id)

        tool_spec = tool_registry.require(algo_id)
        expected_tool_ref = f"fusion_algorithms:{tool_spec.handler_name}"
        actual_contract = {
            "input_types": tuple(algorithm["input_types"]),
            "output_type": algorithm["output_type"],
            "handler_name": metadata.get("handler_name"),
            "tool_ref": algorithm["tool_ref"],
        }
        expected_contract = {
            "input_types": tool_spec.input_types,
            "output_type": tool_spec.output_type,
            "handler_name": tool_spec.handler_name,
            "tool_ref": expected_tool_ref,
        }
        if actual_contract != expected_contract:
            contract_mismatches[algo_id] = {
                "actual": actual_contract,
                "expected": expected_contract,
            }

    assert missing_provenance == []
    assert contract_mismatches == {}
