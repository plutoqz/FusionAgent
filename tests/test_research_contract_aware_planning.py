import json
from pathlib import Path

from kg.inmemory_repository import InMemoryKGRepository
from schemas.research_case_manifest import load_research_case_manifest
from services.research_baselines import BaselineGroup, CanonicalContextFactory
from services.research_contract_aware_planning import build_contract_aware_projection


MANIFEST = Path(__file__).parents[1] / "docs" / "current" / "research-case-manifest-v1.json"
FORBIDDEN = {
    "expected_consequence",
    "expected_outcome_classes",
    "gold_rubric",
    "quality_policy_id",
    "semantic_guard",
    "unsupported_terms",
}


def _case(case_id):
    manifest = load_research_case_manifest(MANIFEST)
    return next(case for case in manifest.cases if case.case_id == case_id)


def _nested_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _nested_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _nested_keys(item)


def _rows(case_id):
    projection = build_contract_aware_projection(
        _case(case_id),
        InMemoryKGRepository(experience_policy="pinned_snapshot"),
    )
    context = projection.payload["contract_decision_context"]
    return projection, {row["task_kind"]: row for row in context["tasks"]}


def test_method_b_projection_excludes_gold_and_is_smaller_than_raw_contract_context() -> None:
    repository = InMemoryKGRepository(experience_policy="pinned_snapshot")
    case = _case("C02")
    method_b = build_contract_aware_projection(case, repository)
    raw = CanonicalContextFactory(repository).project(
        CanonicalContextFactory(repository).build(case),
        BaselineGroup.llm_full_contract_kg,
    )

    assert FORBIDDEN.isdisjoint(_nested_keys(method_b.payload))
    assert len(json.dumps(method_b.payload, sort_keys=True)) < len(json.dumps(raw.payload, sort_keys=True))


def test_method_b_c02_has_distinct_water_task_subgraphs_and_mission_priority() -> None:
    projection, rows = _rows("C02")
    context = projection.payload["contract_decision_context"]

    assert context["task_precedence"] == ["water_polygon", "waterways", "road", "building", "poi"]
    polygon_algorithms = {
        item["algorithm_id"] for item in rows["water_polygon"]["relevant_subgraph"]["algorithm_refs"]
    }
    waterways_algorithms = {
        item["algorithm_id"] for item in rows["waterways"]["relevant_subgraph"]["algorithm_refs"]
    }
    assert "algo.fusion.water_polygon.priority_merge.v2" in polygon_algorithms
    assert "algo.fusion.waterways.conflation.v7" in waterways_algorithms
    assert rows["building"]["decision_constraints"]["allowed_delivery_states"] == ["gap"]
    assert rows["poi"]["decision_constraints"]["allowed_delivery_states"] == ["gap"]


def test_method_b_c01_prioritizes_deliverable_road_and_constrains_building() -> None:
    projection, rows = _rows("C01")
    context = projection.payload["contract_decision_context"]

    assert context["task_precedence"] == ["road", "building"]
    assert rows["road"]["decision_constraints"]["preferred_delivery_state"] == "planned"
    assert rows["building"]["decision_constraints"]["allowed_delivery_states"] == ["pending", "gap"]
    assert rows["building"]["decision_constraints"]["preferred_delivery_state"] == "gap"
    assert rows["building"]["decision_constraints"]["allowed_source_ids"] == ["raw.osm.building"]
    assert rows["building"]["decision_constraints"]["delayed_source_ids"] == ["raw.microsoft.building"]
    assert context["overall_decision"]["allowed_decisions"] == ["partial", "gap"]


def test_method_b_c03_rejects_unsupported_empty_scope_without_materializing_tasks() -> None:
    projection, rows = _rows("C03")
    context = projection.payload["contract_decision_context"]

    assert rows == {}
    assert context["scenario"]["supported"] is False
    assert context["overall_decision"]["allowed_decisions"] == ["reject"]


def test_method_b_c06_uses_recovery_source_and_quality_failure_states() -> None:
    _, rows = _rows("C06")
    road = rows["road"]

    assert road["observed_source_state"]["available"] == ["raw.osm.road"]
    assert road["decision_constraints"]["allowed_delivery_states"] == [
        "provisional",
        "degraded",
        "gap",
    ]
    assert "observations.observed_failure" in road["evidence_refs"]["observation_paths"]
