from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

import pytest

from scripts.run_product_contract_experiment import (
    DEFAULT_CASES_PATH,
    DEFAULT_GOLD_PATH,
    LLM_CALLING_POLICY,
    LLM_PLANNERS,
    VALID_PLANNERS,
    find_case,
    find_gold,
    load_cases,
    load_gold,
    main,
    run_product_contract_experiment,
)


def _c02_decision() -> dict:
    return {
        "strategy_id": "critical_first_degraded_delivery",
        "priority_tiers": [
            ["road", "water_type_2", "water_type_1"],
            ["building"],
        ],
        "initial_delivery_layers": [
            "water_type_1",
            "water_type_2",
            "road",
            "building",
        ],
        "background_completion_layers": ["water_type_1", "water_type_2"],
        "not_delivered_layers": [],
        "layer_decisions": [
            {
                "layer": "water_type_1",
                "selected_algorithm": "algo.fusion.water_type_1.v1",
                "selected_sources": ["raw.hydrolakes.water"],
                "delivery_mode": "degraded",
            },
            {
                "layer": "water_type_2",
                "selected_algorithm": "algo.fusion.water_type_2.v1",
                "selected_sources": ["raw.hydrorivers.water"],
                "delivery_mode": "degraded",
            },
            {
                "layer": "road",
                "selected_algorithm": "algo.fusion.road.v1",
                "selected_sources": ["raw.osm.road"],
                "delivery_mode": "provisional",
            },
            {
                "layer": "building",
                "selected_algorithm": "algo.fusion.building.v1",
                "selected_sources": ["raw.osm.building"],
                "delivery_mode": "provisional",
            },
        ],
        "planner_gap_proposal": [
            {
                "layer": "water_type_1",
                "gap_type": "source_mismatch",
                "source_id": "raw.hydrolakes.water",
                "reason": "The polygon source has a grounded semantic mismatch.",
            },
            {
                "layer": "water_type_2",
                "gap_type": "source_mismatch",
                "source_id": "raw.hydrorivers.water",
                "reason": "The waterway source is grounded as stale.",
            },
        ],
        "supersession_plan": [
            {
                "layer": "water_type_1",
                "target_delivery_mode": "final",
                "trigger_source_ids": ["raw.hydrolakes.water"],
                "condition": "A current semantically suitable source passes quality gates.",
            },
            {
                "layer": "water_type_2",
                "target_delivery_mode": "final",
                "trigger_source_ids": ["raw.hydrorivers.water"],
                "condition": "A fresh waterway source passes quality gates.",
            },
        ],
        "rationale": "Flood urgency prioritizes water and road while preserving explicit gaps.",
    }


class _DecisionLLMProvider:
    last_model = "test-model"
    last_usage = {"prompt_tokens": 10, "completion_tokens": 5}

    def __init__(self, decision: dict | None = None) -> None:
        self.decision = decision or _c02_decision()
        self.context = None
        self.system_prompt = None

    @property
    def provider_name(self) -> str:
        return "decision_llm"

    def generate_workflow_plan(self, system_prompt, context):
        assert "expected_" not in system_prompt
        self.system_prompt = system_prompt
        self.context = context
        return copy.deepcopy(self.decision)


class _SequenceLLMProvider(_DecisionLLMProvider):
    def __init__(self, decisions: list[dict]) -> None:
        super().__init__(decisions[0])
        self.decisions = decisions
        self.call_count = 0

    def generate_workflow_plan(self, system_prompt, context):
        assert "expected_" not in system_prompt
        self.system_prompt = system_prompt
        self.context = context
        decision = self.decisions[self.call_count]
        self.call_count += 1
        return copy.deepcopy(decision)


def _run_c02(
    output_dir: Path,
    *,
    planner: str = "llm_full_contract_kg",
    provider: _DecisionLLMProvider | None = None,
    input_variant: int = 0,
) -> dict:
    case = find_case(load_cases(DEFAULT_CASES_PATH), "C02")
    gold = find_gold(load_gold(DEFAULT_GOLD_PATH), "C02")
    return run_product_contract_experiment(
        case=case,
        planner=planner,
        output_dir=output_dir,
        llm_provider=provider,
        gold=gold,
        input_variant=input_variant,
    )


def test_product_contract_experiment_writes_structured_artifacts_without_gold_leak() -> None:
    provider = _DecisionLLMProvider()

    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        summary = _run_c02(output_dir, provider=provider)

        expected_files = {
            "product_contract.json",
            "resource_regime.json",
            "planning_context.json",
            "planning_decision.json",
            "planner_gap_proposal.json",
            "quality_gate_result.json",
            "gap_verification.json",
            "evidence_trace.json",
            "gap_declaration.json",
            "delivery_manifest.json",
            "experiment_summary.json",
            "evaluation_result.json",
            "run_report.md",
        }
        assert expected_files == {path.name for path in output_dir.iterdir()}
        assert summary["case_id"] == "C02"
        assert summary["planner"] == "llm_full_contract_kg"
        assert summary["planning_provider"] == "decision_llm"
        assert summary["duration_ms"] >= 0
        assert summary["started_at"].endswith("Z")
        assert summary["completed_at"].endswith("Z")

        decision = json.loads((output_dir / "planning_decision.json").read_text("utf-8"))
        final_gaps = json.loads((output_dir / "gap_declaration.json").read_text("utf-8"))
        manifest = json.loads((output_dir / "delivery_manifest.json").read_text("utf-8"))

        assert decision["priority_tiers"][0] == ["road", "water_type_2", "water_type_1"]
        assert {gap["gap_type"] for gap in final_gaps["gaps"]} == {"source_mismatch"}
        assert manifest["satisfaction_state"] == "degraded_but_usable"

        serialized_context = json.dumps(provider.context, ensure_ascii=False)
        assert "expected_" not in serialized_context
        assert "acceptable_strategy_ids" not in serialized_context
        assert "must_not_do" not in serialized_context


def test_case_inputs_and_gold_labels_are_physically_separated() -> None:
    case = find_case(load_cases(DEFAULT_CASES_PATH), "C02")
    gold = find_gold(load_gold(DEFAULT_GOLD_PATH), "C02")

    assert not any(key.startswith("expected_") for key in case)
    assert "must_not_do" not in case
    assert gold["priority_tiers"][0] == ["water_type_1", "water_type_2", "road"]
    assert gold["acceptable_strategy_ids"] == ["critical_first_degraded_delivery"]


def test_all_five_baselines_run_with_frozen_llm_protocol() -> None:
    assert VALID_PLANNERS == {
        "fixed",
        "kg_only",
        "llm_only",
        "llm_capability_kg",
        "llm_full_contract_kg",
    }
    assert LLM_PLANNERS == {
        "llm_only",
        "llm_capability_kg",
        "llm_full_contract_kg",
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        summaries = {
            "fixed": _run_c02(root / "fixed", planner="fixed"),
            "kg_only": _run_c02(root / "kg_only", planner="kg_only"),
        }
        providers = {}
        decisions = {}
        for planner in sorted(LLM_PLANNERS):
            provider = _DecisionLLMProvider()
            providers[planner] = provider
            summaries[planner] = _run_c02(
                root / planner,
                planner=planner,
                provider=provider,
            )
            decisions[planner] = json.loads(
                (root / planner / "planning_decision.json").read_text("utf-8")
            )

    assert set(summaries) == VALID_PLANNERS
    assert len({provider.system_prompt for provider in providers.values()}) == 1
    assert len({decision["prompt_hash"] for decision in decisions.values()}) == 1
    assert {
        json.dumps(decision["calling_policy"], sort_keys=True)
        for decision in decisions.values()
    } == {json.dumps(LLM_CALLING_POLICY, sort_keys=True)}


def test_llm_baselines_differ_only_by_declared_knowledge_layers() -> None:
    providers = {}
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        for planner in sorted(LLM_PLANNERS):
            provider = _DecisionLLMProvider()
            providers[planner] = provider
            _run_c02(root / planner, planner=planner, provider=provider, input_variant=2)

    contexts = {planner: provider.context for planner, provider in providers.items()}
    llm_only = contexts["llm_only"]
    capability = contexts["llm_capability_kg"]
    full = contexts["llm_full_contract_kg"]

    def common_context(context: dict) -> dict:
        return {
            key: value
            for key, value in context.items()
            if key not in {"context_id", "knowledge_profile", "kg_retrieval"}
        }

    assert common_context(llm_only) == common_context(capability) == common_context(full)
    for context in contexts.values():
        serialized = json.dumps(context, ensure_ascii=False)
        assert "expected_" not in serialized
        assert "acceptable_strategy_ids" not in serialized
        assert "must_not_do" not in serialized

    assert llm_only["kg_retrieval"] == {}
    assert set(capability["kg_retrieval"]) == {"capability_kg"}
    assert set(full["kg_retrieval"]) == {"capability_kg", "full_contract_kg"}
    assert (
        capability["kg_retrieval"]["capability_kg"]
        == full["kg_retrieval"]["capability_kg"]
    )
    assert full["knowledge_profile"]["kg_layers"] == ["L1", "L2", "L3", "L4", "L6"]


def test_input_variants_reorder_context_without_changing_kg_semantics() -> None:
    with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
        first_dir = Path(first)
        second_dir = Path(second)
        _run_c02(first_dir, planner="kg_only", input_variant=0)
        _run_c02(second_dir, planner="kg_only", input_variant=1)

        context_0 = json.loads((first_dir / "planning_context.json").read_text("utf-8"))
        context_1 = json.loads((second_dir / "planning_context.json").read_text("utf-8"))
        decision_0 = json.loads((first_dir / "planning_decision.json").read_text("utf-8"))
        decision_1 = json.loads((second_dir / "planning_decision.json").read_text("utf-8"))

        assert (
            context_0["kg_retrieval"]["capability_kg"]["sources"]
            != context_1["kg_retrieval"]["capability_kg"]["sources"]
        )
        assert (
            context_0["kg_retrieval"]["capability_kg"]["algorithms"]
            != context_1["kg_retrieval"]["capability_kg"]["algorithms"]
        )
        assert (
            context_0["kg_retrieval"]["full_contract_kg"]["product_contract"]
            ["required_layers"]
            != context_1["kg_retrieval"]["full_contract_kg"]["product_contract"]
            ["required_layers"]
        )
        for field in (
            "priority_tiers",
            "initial_delivery_layers",
            "background_completion_layers",
            "not_delivered_layers",
            "layer_decisions",
            "planner_gap_proposal",
            "supersession_plan",
        ):
            assert decision_0[field] == decision_1[field]


def test_priority_scoring_tolerates_within_tier_permutations() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        summary = _run_c02(Path(temp_dir), provider=_DecisionLLMProvider())

    assert summary["evaluation"]["priority_pairwise_precedence_accuracy"] == 1.0


@pytest.mark.parametrize(
    "mutator",
    [
        lambda decision: decision.update(
            {"priority_tiers": [["water_type_1", "road"], ["building"]]}
        ),
        lambda decision: decision.update(
            {
                "priority_tiers": [
                    ["water_type_1", "water_type_1", "road"],
                    ["water_type_2", "building"],
                ]
            }
        ),
        lambda decision: decision["layer_decisions"].append(
            copy.deepcopy(decision["layer_decisions"][0])
        ),
    ],
)
def test_missing_or_duplicate_layers_fail_grounding(mutator) -> None:
    decision = _c02_decision()
    mutator(decision)
    with tempfile.TemporaryDirectory() as temp_dir, pytest.raises(ValueError):
        _run_c02(Path(temp_dir), provider=_DecisionLLMProvider(decision))


def test_unsupported_gap_proposal_fails_grounding() -> None:
    decision = _c02_decision()
    decision["planner_gap_proposal"][0]["gap_type"] = "quality_failed"

    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        with pytest.raises(ValueError, match="unsupported"):
            _run_c02(output_dir, provider=_DecisionLLMProvider(decision))
        failure = json.loads((output_dir / "planning_failure.json").read_text("utf-8"))

    assert failure["failure_type"] == "LLMPlanningFailure"
    assert len(failure["raw_llm_responses"]) == 2
    assert "expected_" not in json.dumps(failure, ensure_ascii=False)


def test_invalid_first_response_uses_explicit_recorded_repair_retry() -> None:
    invalid = _c02_decision()
    invalid["background_completion_layers"] = ["water_type_1"]
    provider = _SequenceLLMProvider([invalid, _c02_decision()])

    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        _run_c02(output_dir, provider=provider)
        decision = json.loads((output_dir / "planning_decision.json").read_text("utf-8"))

    assert provider.call_count == 2
    assert decision["planning_retry_count"] == 1
    assert len(decision["raw_llm_responses"]) == 2
    assert len(decision["grounding_failures_before_success"]) == 1
    assert [item["status"] for item in decision["planning_attempts"]] == [
        "grounding_failed",
        "grounded",
    ]
    assert decision["planning_usage_total"] == {
        "prompt_tokens": 20,
        "completion_tokens": 10,
    }


def test_missing_planner_gap_reduces_recall_but_final_declaration_stays_correct() -> None:
    decision = _c02_decision()
    decision["planner_gap_proposal"] = decision["planner_gap_proposal"][:1]

    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        summary = _run_c02(output_dir, provider=_DecisionLLMProvider(decision))
        final_gaps = json.loads((output_dir / "gap_declaration.json").read_text("utf-8"))
        verification = json.loads((output_dir / "gap_verification.json").read_text("utf-8"))

    assert summary["evaluation"]["planner_gap_recall"] == 0.5
    assert {(gap["layer"], gap["gap_type"]) for gap in final_gaps["gaps"]} == {
        ("water_type_1", "source_mismatch"),
        ("water_type_2", "source_mismatch"),
    }
    assert len(verification["unproposed_observable_gaps"]) == 1


def test_fixed_kg_and_full_contract_llm_receive_different_scores() -> None:
    scores = {}
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        scores["fixed"] = _run_c02(root / "fixed", planner="fixed")["evaluation"]["overall_score"]
        scores["kg_only"] = _run_c02(root / "kg", planner="kg_only")["evaluation"]["overall_score"]
        scores["llm_full_contract_kg"] = _run_c02(
            root / "llm", provider=_DecisionLLMProvider()
        )["evaluation"]["overall_score"]

    assert scores["fixed"] < scores["kg_only"] < scores["llm_full_contract_kg"]


def test_supersession_and_delivery_set_inconsistency_fails_validation() -> None:
    decision = _c02_decision()
    decision["background_completion_layers"] = ["water_type_1"]

    with tempfile.TemporaryDirectory() as temp_dir, pytest.raises(
        ValueError, match="supersession_plan"
    ):
        _run_c02(Path(temp_dir), provider=_DecisionLLMProvider(decision))


def test_fixed_planner_uses_global_singleton_tiers() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        _run_c02(output_dir, planner="fixed")
        decision = json.loads((output_dir / "planning_decision.json").read_text("utf-8"))

    assert decision["priority_tiers"][0] == ["building"]
    assert "fixed global ordering" in decision["rationale"]
    assert decision["planner_gap_proposal"] == []


def test_product_contract_experiment_cli_records_input_variant() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        exit_code = main(
            [
                "--case",
                "C06",
                "--planner",
                "kg_only",
                "--output-dir",
                str(output_dir),
                "--input-variant",
                "3",
            ]
        )

        assert exit_code == 0
        gaps = json.loads((output_dir / "gap_declaration.json").read_text("utf-8"))
        summary = json.loads((output_dir / "experiment_summary.json").read_text("utf-8"))
        assert gaps["gaps"][0]["gap_type"] == "quality_failed"
        assert summary["input_variant"] == 3
