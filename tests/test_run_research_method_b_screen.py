from pathlib import Path

from scripts.run_research_method_b_screen import prepare_method_b_screen


MANIFEST = Path(__file__).parents[1] / "docs" / "current" / "research-case-manifest-v1.json"


def test_method_b_screen_prepares_exactly_one_call_per_development_case() -> None:
    schedule, prepared = prepare_method_b_screen(MANIFEST)

    assert len(schedule["items"]) == len(prepared) == 6
    assert {item["schedule"]["case_id"] for item in prepared} == {
        "C01",
        "C02",
        "C03",
        "C04",
        "C05",
        "C06",
    }
    assert len({item["input_hash"] for item in prepared}) == 6
    assert all(
        item["schedule"]["knowledge_condition"] == "task_conditioned_contract_aware_kg"
        for item in prepared
    )
