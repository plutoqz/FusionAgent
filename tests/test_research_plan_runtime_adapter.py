from pathlib import Path

from agent.tooling import build_default_tool_registry
from kg.inmemory_repository import InMemoryKGRepository
from schemas.research_case_manifest import load_research_case_manifest
from schemas.research_llm_pilot import ResearchPlanningDecision
from services.research_plan_runtime_adapter import ResearchPlanRuntimeAdapter


MANIFEST = Path(__file__).parents[1] / "docs" / "current" / "research-case-manifest-v1.json"


def _case(case_id: str):
    manifest = load_research_case_manifest(MANIFEST)
    return next(case for case in manifest.cases if case.case_id == case_id)


def _adapter() -> ResearchPlanRuntimeAdapter:
    return ResearchPlanRuntimeAdapter(
        InMemoryKGRepository(experience_policy="pinned_snapshot"),
        tool_registry=build_default_tool_registry(),
    )


def _decision(tasks, decision="plan") -> ResearchPlanningDecision:
    return ResearchPlanningDecision.model_validate(
        {"decision": decision, "tasks": tasks, "uncertainties": [], "evidence": ["test"]}
    )


def test_grounded_catalog_task_resolves_to_workflow_plan():
    result = _adapter().resolve(
        case=_case("C06"),
        condition="kg_only",
        decision=_decision(
            [
                {
                    "order": 1,
                    "task_kind": "road",
                    "source_ids": ["catalog.flood.road"],
                    "algorithm_id": "algo.fusion.road.conflation.v7",
                    "delivery_state": "degraded",
                    "rationale": "Observed recovery plan.",
                }
            ],
            decision="degraded",
        ),
    )

    assert result.status == "resolved"
    assert result.workflow_plan is not None
    assert result.workflow_plan.tasks[0].input.data_type_id == "dt.road.bundle"
    assert result.workflow_plan.tasks[0].task_id == "task.road.fusion"
    assert result.workflow_plan.product_contract.contract_id == "contract.product.road.v1"
    assert {
        "repair.artifact.schema_backfill.v1",
        "repair.artifact.road_name.v1",
    } <= {item.strategy_id for item in result.workflow_plan.repair_strategies}
    assert all(
        "task.road.fusion" in item.applies_to_task_ids
        for item in result.workflow_plan.repair_strategies
    )
    assert result.executed == {"status": "not_executed"}
    assert result.evaluated == {"status": "not_evaluated"}


def test_missing_algorithm_fails_closed_without_kg_inference():
    result = _adapter().resolve(
        case=_case("C04"),
        condition="rules_only",
        decision=_decision(
            [
                {
                    "order": 1,
                    "task_kind": "road",
                    "source_ids": ["catalog.typhoon.road"],
                    "algorithm_id": None,
                    "delivery_state": "provisional",
                    "rationale": "Rule selected a source only.",
                }
            ],
            decision="partial",
        ),
    )

    assert result.status == "rejected"
    assert result.workflow_plan is None
    assert "MISSING_ALGORITHM" in result.task_resolutions[0].reason_codes


def test_multiple_sources_fail_closed_without_implicit_selection():
    result = _adapter().resolve(
        case=_case("C06"),
        condition="llm_only",
        decision=_decision(
            [
                {
                    "order": 1,
                    "task_kind": "road",
                    "source_ids": ["raw.osm.road", "raw.microsoft.road"],
                    "algorithm_id": "algo.fusion.road.conflation.v7",
                    "delivery_state": "degraded",
                    "rationale": "Ambiguous recovery sources.",
                }
            ],
            decision="degraded",
        ),
    )

    assert result.workflow_plan is None
    assert "REQUIRES_SINGLE_EFFECTIVE_SOURCE" in result.task_resolutions[0].reason_codes


def test_gap_task_is_preserved_but_not_emitted_for_execution():
    result = _adapter().resolve(
        case=_case("C02"),
        condition="kg_only",
        decision=_decision(
            [
                {
                    "order": 1,
                    "task_kind": "building",
                    "source_ids": [],
                    "algorithm_id": "algo.fusion.building.v1",
                    "delivery_state": "gap",
                    "rationale": "No observed building source.",
                }
            ],
            decision="gap",
        ),
    )

    assert result.status == "not_executable"
    assert result.workflow_plan is None
    assert result.task_resolutions[0].resolution_status == "not_executable"
    assert result.task_resolutions[0].selected["delivery_state"] == "gap"


def test_raw_source_is_not_treated_as_algorithm_bundle_input():
    result = _adapter().resolve(
        case=_case("C06"),
        condition="kg_only",
        decision=_decision(
            [
                {
                    "order": 1,
                    "task_kind": "road",
                    "source_ids": ["raw.osm.road"],
                    "algorithm_id": "algo.fusion.road.conflation.v7",
                    "delivery_state": "degraded",
                    "rationale": "Raw recovery source.",
                }
            ],
            decision="degraded",
        ),
    )

    assert result.workflow_plan is None
    task = result.task_resolutions[0]
    assert "SOURCE_ALGORITHM_INPUT_TYPE_MISMATCH" in task.reason_codes
    assert task.resolved["effective_source_id"] == "raw.osm.road"
    assert task.resolved["effective_algorithm_id"] == "algo.fusion.road.conflation.v7"
