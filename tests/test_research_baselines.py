from pathlib import Path

from kg.inmemory_repository import InMemoryKGRepository
from schemas.research_case_manifest import load_research_case_manifest
from services.research_baselines import BaselineGroup, CanonicalContextFactory, DeterministicBaselineRunner


MANIFEST = Path(__file__).parents[1] / "docs" / "current" / "research-case-manifest-v1.json"
GOLD_KEYS = {"expected_consequence", "expected_outcome_classes", "unsupported_terms", "quality_policy_id", "semantic_guard"}


def _nested_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _nested_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _nested_keys(item)


def test_baseline_projections_have_explicit_input_boundaries() -> None:
    manifest = load_research_case_manifest(MANIFEST)
    case = next(item for item in manifest.cases if item.case_id == "C02")
    repository = InMemoryKGRepository(experience_policy="pinned_snapshot")
    factory = CanonicalContextFactory(repository)
    context = factory.build(case)

    projections = {group: factory.project(context, group) for group in BaselineGroup}

    assert set(projections[BaselineGroup.fixed_workflow].payload) == {"request", "fixed_workflow"}
    assert set(projections[BaselineGroup.fixed_workflow].payload["request"]) == {"task_kinds"}
    assert "kg_query" not in projections[BaselineGroup.rules_only].payload
    assert projections[BaselineGroup.kg_only].payload["kg_query"]["mode"] == "graph_query"
    assert projections[BaselineGroup.kg_only].payload["kg_query"]["knowledge_identity"] == repository.get_knowledge_identity()
    assert "kg_capability" not in projections[BaselineGroup.llm_only].payload
    assert "kg_contract" not in projections[BaselineGroup.llm_capability_kg].payload
    assert "kg_contract" in projections[BaselineGroup.llm_full_contract_kg].payload

    hashes = {projection.input_hash for projection in projections.values()}
    assert len(hashes) == len(projections)


def test_deterministic_runner_uses_only_projection() -> None:
    manifest = load_research_case_manifest(MANIFEST)
    factory = CanonicalContextFactory(InMemoryKGRepository(experience_policy="pinned_snapshot"))
    runner = DeterministicBaselineRunner()
    case = next(item for item in manifest.cases if item.case_id == "C02")
    context = factory.build(case)

    fixed = runner.run(factory.project(context, BaselineGroup.fixed_workflow))
    rules = runner.run(factory.project(context, BaselineGroup.rules_only))
    kg = runner.run(factory.project(context, BaselineGroup.kg_only))

    assert fixed["decision"] == "execute_fixed_workflow"
    assert rules["decision"] == "plan_from_observable_facts"
    assert kg["decision"] == "plan_from_kg_query"
    assert kg["rationale"]["query_mode"] == "graph_query"


def test_rules_only_rejects_c03_from_frozen_general_rules_not_case_gold() -> None:
    manifest = load_research_case_manifest(MANIFEST)
    factory = CanonicalContextFactory(InMemoryKGRepository(experience_policy="pinned_snapshot"))
    runner = DeterministicBaselineRunner()
    case = next(item for item in manifest.cases if item.case_id == "C03")
    context = factory.build(case)
    context.observable_facts["observations"].pop("unsupported_terms", None)

    result = runner.run(factory.project(context, BaselineGroup.rules_only))

    assert result == {"decision": "reject_unsupported_disaster", "tasks": [], "rationale": "rules.general.v1"}


def test_projection_hash_is_stable_for_same_context() -> None:
    manifest = load_research_case_manifest(MANIFEST)
    case = next(item for item in manifest.cases if item.case_id == "C06")
    factory = CanonicalContextFactory(InMemoryKGRepository(experience_policy="pinned_snapshot"))

    first = factory.project(factory.build(case), BaselineGroup.kg_only)
    second = factory.project(factory.build(case), BaselineGroup.kg_only)

    assert first.input_hash == second.input_hash


def test_all_planning_projections_exclude_gold_rubric_fields() -> None:
    manifest = load_research_case_manifest(MANIFEST)
    factory = CanonicalContextFactory(InMemoryKGRepository(experience_policy="pinned_snapshot"))

    for case in manifest.cases:
        context = factory.build(case)
        assert GOLD_KEYS.isdisjoint(_nested_keys(context.observable_facts))
        for group in BaselineGroup:
            projection = factory.project(context, group)
            assert "gold_rubric" not in set(_nested_keys(projection.payload))
            assert GOLD_KEYS.isdisjoint(_nested_keys(projection.payload))


def test_observation_projection_does_not_invent_default_empty_facts() -> None:
    manifest = load_research_case_manifest(MANIFEST)
    factory = CanonicalContextFactory(InMemoryKGRepository(experience_policy="pinned_snapshot"))
    c03 = next(case for case in manifest.cases if case.case_id == "C03")
    c06 = next(case for case in manifest.cases if case.case_id == "C06")

    assert factory.build(c03).observable_facts["observations"] == {}
    assert set(factory.build(c06).observable_facts["observations"]) == {"initial_sources", "recovery_source"}
