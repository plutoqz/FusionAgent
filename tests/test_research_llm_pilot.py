import json
from pathlib import Path
import sys

from schemas.research_llm_pilot import (
    ResearchLLMPilotSchedule,
    ResearchPlanningDecision,
    build_research_llm_pilot_schedule,
)
import pytest

from scripts.run_research_llm_pilot import (
    FORBIDDEN_PLANNER_KEYS,
    _attempt_total_tokens,
    _conservative_token_estimate,
    _select_pilot_subset,
    _validate_batch_token_budget,
    prepare_pilot,
)


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


def test_pilot_schedule_is_complete_18_call_cross_product() -> None:
    schedule = build_research_llm_pilot_schedule()

    assert len(schedule.items) == 18
    assert {(item.case_id, item.knowledge_condition, item.replicate) for item in schedule.items} == {
        (case_id, condition, replicate)
        for case_id in ("C02", "C03", "C06")
        for condition in ("llm_only", "llm_capability_kg", "llm_full_contract_kg")
        for replicate in (1, 2)
    }
    assert schedule.metadata["fallback"] == "forbidden"


def test_pilot_preflight_materializes_isolated_hashed_inputs() -> None:
    schedule, prepared = prepare_pilot(MANIFEST)

    assert len(prepared) == len(schedule.items) == 18
    assert all(item["input_hash"].startswith("sha256:") for item in prepared)
    for item in prepared:
        condition = item["schedule"]["knowledge_condition"]
        payload = item["payload"]
        assert GOLD_KEYS == FORBIDDEN_PLANNER_KEYS - {"gold_rubric"}
        assert FORBIDDEN_PLANNER_KEYS.isdisjoint(_nested_keys(payload))
        assert payload["output_schema"] == ResearchPlanningDecision.model_json_schema()
        if condition == "llm_only":
            assert "kg_capability" not in payload and "kg_contract" not in payload
        elif condition == "llm_capability_kg":
            assert "kg_capability" in payload and "kg_contract" not in payload
        else:
            assert "kg_capability" in payload and "kg_contract" in payload


def test_pilot_token_estimate_is_conservative_for_utf8_payload() -> None:
    estimate = _conservative_token_estimate("system", {"message": "test"})

    assert estimate >= 10


def test_pilot_batch_budget_must_cover_all_bounded_requests() -> None:
    prepared = [{"payload": {"message": "test"}} for _ in range(18)]

    bound = _validate_batch_token_budget(
        prepared,
        max_output_tokens=8192,
        token_budget=500_000,
    )

    assert bound < 500_000
    with pytest.raises(RuntimeError, match="below the conservative batch bound"):
        _validate_batch_token_budget(
            prepared,
            max_output_tokens=8192,
            token_budget=100,
        )


def test_attempt_total_tokens_tolerates_missing_usage() -> None:
    assert _attempt_total_tokens(None) == 0
    assert _attempt_total_tokens({"usage": None}) == 0
    assert _attempt_total_tokens({"usage": {"total_tokens": 42}}) == 42


def test_pilot_subset_selects_case_and_replicate_without_changing_conditions() -> None:
    schedule, prepared = prepare_pilot(MANIFEST)

    selected = _select_pilot_subset(prepared, case_ids=["C06"], replicates=[1])

    assert len(schedule.items) == 18
    assert len(selected) == 3
    assert {item["schedule"]["knowledge_condition"] for item in selected} == {
        "llm_only",
        "llm_capability_kg",
        "llm_full_contract_kg",
    }
    assert {item["schedule"]["case_id"] for item in selected} == {"C06"}
    assert {item["schedule"]["replicate"] for item in selected} == {1}


def test_pilot_subset_rejects_unknown_selection() -> None:
    _, prepared = prepare_pilot(MANIFEST)

    with pytest.raises(ValueError, match="Unknown pilot case IDs"):
        _select_pilot_subset(prepared, case_ids=["C99"], replicates=[1])


def test_subset_schedule_remains_schema_valid(tmp_path: Path) -> None:
    from scripts.run_research_llm_pilot import main

    output = tmp_path / "subset"
    original_argv = sys.argv
    try:
        sys.argv = [
            "run_research_llm_pilot.py",
            "--manifest",
            str(MANIFEST),
            "--output",
            str(output),
            "--case-id",
            "C06",
            "--replicate",
            "1",
        ]
        assert main() == 0
    finally:
        sys.argv = original_argv

    payload = json.loads((output / "schedule.json").read_text(encoding="utf-8"))
    schedule = ResearchLLMPilotSchedule.model_validate(payload)
    assert schedule.cases == ["C06"]
    assert schedule.replicates == 1
    assert len(schedule.items) == 3
