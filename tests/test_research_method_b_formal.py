from pathlib import Path

from kg.inmemory_repository import InMemoryKGRepository
from schemas.research_case_manifest import load_research_case_manifest
from scripts.run_research_method_b_formal import CONDITIONS, REPLICATES, prepare_formal_inputs
from services.research_manifest_validation import validate_manifest_crosswalk


MANIFEST = Path(__file__).parents[1] / "docs" / "current" / "research-case-manifest-heldout-method-b-v1.json"


def test_heldout_manifest_is_frozen_and_crosswalk_closed() -> None:
    manifest = load_research_case_manifest(MANIFEST)
    assert manifest.status == "frozen"
    assert validate_manifest_crosswalk(manifest, InMemoryKGRepository(experience_policy="pinned_snapshot")) == []


def test_formal_inputs_are_54_calls_with_three_conditions_and_repetitions() -> None:
    schedule, prepared = prepare_formal_inputs(MANIFEST)

    assert len(schedule["items"]) == len(prepared) == 6 * len(CONDITIONS) * REPLICATES
    assert set(schedule["knowledge_conditions"]) == set(CONDITIONS)
    assert {item["replicate"] for item in schedule["items"]} == {1, 2, 3}
    assert all("gold_rubric" not in item["payload"] for item in prepared)
    assert all("gold_rubric" not in item["payload"].get("observable_facts", {}) for item in prepared)
