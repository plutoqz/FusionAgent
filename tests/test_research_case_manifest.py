import json
from pathlib import Path

import pytest

from schemas.research_case_manifest import ResearchCaseManifest, load_research_case_manifest
from kg.inmemory_repository import InMemoryKGRepository
from services.research_manifest_validation import validate_manifest_crosswalk


MANIFEST = Path(__file__).parents[1] / "docs" / "current" / "research-case-manifest-v1.json"


def test_research_case_manifest_is_valid_and_closed() -> None:
    manifest = load_research_case_manifest(MANIFEST)

    assert isinstance(manifest, ResearchCaseManifest)
    assert [case.case_id for case in manifest.cases] == ["C01", "C02", "C03", "C04", "C05", "C06"]
    assert set(manifest.end_to_end_case_ids) == {"C02", "C04", "C06"}
    assert set(manifest.negative_control_case_ids) == {"C03"}


def test_manifest_rejects_unknown_partition_case() -> None:
    payload = load_research_case_manifest(MANIFEST).model_dump(mode="json")
    payload["end_to_end_case_ids"].append("C99")

    with pytest.raises(ValueError, match="unknown cases"):
        ResearchCaseManifest.model_validate(payload)


def test_manifest_rejects_negative_control_in_positive_average() -> None:
    payload = load_research_case_manifest(MANIFEST).model_dump(mode="json")
    payload["cases"][2]["excluded_from_positive_quality_average"] = False

    with pytest.raises(ValueError, match="excluded from positive averages"):
        ResearchCaseManifest.model_validate(payload)


def test_manifest_crosswalk_is_closed_against_frozen_kg() -> None:
    manifest = load_research_case_manifest(MANIFEST)
    failures = validate_manifest_crosswalk(
        manifest,
        InMemoryKGRepository(experience_policy="pinned_snapshot"),
    )

    assert failures == []


def test_manifest_crosswalk_reports_unknown_kg_id() -> None:
    payload = load_research_case_manifest(MANIFEST).model_dump(mode="json")
    payload["cases"][0]["kg_crosswalk"]["algorithm_ids"].append("algo.unknown.v1")
    manifest = ResearchCaseManifest.model_validate(payload)

    failures = validate_manifest_crosswalk(
        manifest,
        InMemoryKGRepository(experience_policy="pinned_snapshot"),
    )

    assert "C01.algorithm_ids references unknown KG id: algo.unknown.v1" in failures


def test_manifest_rejects_gold_fields_inside_runtime_observations(tmp_path: Path) -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    payload["cases"][0]["observations"]["expected_consequence"] = "leaked answer"
    candidate = tmp_path / "manifest.json"
    candidate.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="expected_consequence"):
        load_research_case_manifest(candidate)


def test_manifest_rejects_legacy_top_level_expected_outcomes(tmp_path: Path) -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    payload["cases"][0]["expected_outcome_classes"] = ["legacy_leak"]
    candidate = tmp_path / "manifest.json"
    candidate.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="expected_outcome_classes"):
        load_research_case_manifest(candidate)


def test_manifest_rejects_incomplete_scoring_contract() -> None:
    payload = load_research_case_manifest(MANIFEST).model_dump(mode="json")
    del payload["cases"][0]["gold_rubric"]["allowed_delivery_states"]["building"]

    with pytest.raises(ValueError, match="lack allowed_delivery_states"):
        ResearchCaseManifest.model_validate(payload)


def test_manifest_rejects_duplicate_scoring_items() -> None:
    payload = load_research_case_manifest(MANIFEST).model_dump(mode="json")
    payload["cases"][0]["gold_rubric"]["expected_task_kinds"].append("road")

    with pytest.raises(ValueError, match="expected_task_kinds values must be unique"):
        ResearchCaseManifest.model_validate(payload)
