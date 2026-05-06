from __future__ import annotations

from kg.inmemory_repository import InMemoryKGRepository
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
