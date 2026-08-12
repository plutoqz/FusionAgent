from pathlib import Path

from schemas.research_llm_pilot import ResearchPlanningDecision, build_research_llm_pilot_schedule
from scripts.run_research_llm_pilot import prepare_pilot


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
