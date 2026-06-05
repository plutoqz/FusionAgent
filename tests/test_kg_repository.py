from kg.inmemory_repository import InMemoryKGRepository
from kg.models import AlgorithmNode, DataSourceNode
from schemas.fusion import JobType


def test_candidate_pattern_and_alternatives() -> None:
    repo = InMemoryKGRepository()
    patterns = repo.get_candidate_patterns(job_type=JobType.building, disaster_type="flood", limit=3)
    assert patterns
    assert patterns[0].job_type == JobType.building

    algo_id = patterns[0].steps[0].algorithm_id
    algorithm = repo.get_algorithm(algo_id)
    assert algorithm is not None
    assert algorithm.accuracy_score is not None
    assert algorithm.stability_score is not None
    assert algorithm.usage_mode == "throughput"

    alternatives = repo.get_alternative_algorithms(algo_id, limit=3)
    assert alternatives
    assert alternatives[0].usage_mode == "conservative"


def test_find_transform_path() -> None:
    repo = InMemoryKGRepository()
    path = repo.find_transform_path("dt.raw.vector", "dt.building.bundle", max_depth=3)
    assert path == ["dt.raw.vector", "dt.building.bundle"]


def test_repository_default_seed_matches_manifest_seed() -> None:
    default_repo = InMemoryKGRepository()
    manifest_repo = InMemoryKGRepository(seed_manifest_path="kg/seed_manifest.generated.json")

    assert [item.type_id for item in default_repo.list_data_types()] == [
        item.type_id for item in manifest_repo.list_data_types()
    ]
    assert [item.algo_id for item in default_repo.list_algorithms()] == [
        item.algo_id for item in manifest_repo.list_algorithms()
    ]
    assert [item.pattern_id for item in default_repo.list_workflow_patterns()] == [
        item.pattern_id for item in manifest_repo.list_workflow_patterns()
    ]
    assert [item.source_id for item in default_repo.list_data_sources()] == [
        item.source_id for item in manifest_repo.list_data_sources()
    ]
    assert set(default_repo.output_schema_policies) == set(manifest_repo.output_schema_policies)


def test_repository_manifest_seed_keeps_default_transform_edges() -> None:
    default_repo = InMemoryKGRepository()
    manifest_repo = InMemoryKGRepository(seed_manifest_path="kg/seed_manifest.generated.json")

    assert manifest_repo.list_transform_edges() == default_repo.list_transform_edges()


def test_repository_default_init_loads_seed_through_provider(monkeypatch) -> None:
    calls = []

    def fake_load_seed_data(seed_manifest_path=None):
        calls.append(seed_manifest_path)
        return {
            "algorithms": {},
            "patterns": [],
            "can_transform_to": {},
            "data_sources": [],
            "data_types": {},
            "parameter_specs": {},
            "output_schema_policies": {},
            "tasks": {},
            "scenario_profiles": [],
            "task_bundles": {},
            "output_requirements": {},
            "qos_policies": {},
            "data_needs": [],
            "repair_strategies": {},
        }

    monkeypatch.setattr("kg.inmemory_repository.load_seed_data", fake_load_seed_data)

    repo = InMemoryKGRepository()

    assert calls == [None]
    assert repo.list_algorithms() == []


def test_repository_constructor_override_wins_over_provider_seed() -> None:
    override = AlgorithmNode(
        algo_id="algo.override.only",
        algo_name="Override Only",
        input_types=["dt.raw.vector"],
        output_type="dt.building.fused",
        task_type="building_fusion",
        tool_ref="tests:override",
        success_rate=1.0,
        accuracy_score=1.0,
        stability_score=1.0,
        usage_mode="test",
    )

    repo = InMemoryKGRepository(
        algorithms={override.algo_id: override},
        seed_manifest_path="kg/seed_manifest.generated.json",
    )

    assert [item.algo_id for item in repo.list_algorithms()] == ["algo.override.only"]


def test_repository_list_and_transform_overrides_win_over_provider_seed() -> None:
    override_source = DataSourceNode(
        source_id="source.override.only",
        source_name="Override Only Source",
        supported_types=["dt.override.input"],
        disaster_types=["generic"],
        quality_score=1.0,
        source_kind="test",
        freshness_category="static",
    )

    repo = InMemoryKGRepository(
        data_sources=[override_source],
        can_transform_to={"dt.override.input": ["dt.override.output"]},
        seed_manifest_path="kg/seed_manifest.generated.json",
    )

    assert [item.source_id for item in repo.list_data_sources()] == ["source.override.only"]
    assert repo.list_transform_edges() == {"dt.override.input": ["dt.override.output"]}
