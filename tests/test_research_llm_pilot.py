from pathlib import Path

from schemas.research_llm_pilot import ResearchPlanningDecision, build_research_llm_pilot_schedule
import pytest

from scripts.run_research_llm_pilot import (
    _conservative_token_estimate,
    _validate_batch_token_budget,
    prepare_pilot,
)


MANIFEST = Path(__file__).parents[1] / "docs" / "current" / "research-case-manifest-v1.json"


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
