from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.audit_benchmark_design_freeze import (
    EXPECTED_MANIFEST_FILES,
    HISTORICAL_CASE_IDS,
    audit_design,
    load_json,
    local_markdown_link_errors,
    local_schema_refs,
    manifest_file_map,
    manifest_hash_errors,
    milestone_state_matches_review,
    open_object_schema_paths,
    root_key_errors,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DESIGN_ROOT = REPO_ROOT / "docs" / "current" / "benchmark" / "v1"


def test_all_machine_checks_pass_and_only_explicit_human_gate_may_remain() -> None:
    result = audit_design(REPO_ROOT, DESIGN_ROOT)
    failures = set(result["required_failures"])
    assert failures <= {"human_protocol_review"}
    assert result["accounting"] == {
        "instances_generated": 0,
        "provider_calls": 0,
        "judge_calls": 0,
        "formal_result_roots_created": 0,
    }


def test_template_schema_refs_close_and_all_object_schemas_are_closed() -> None:
    schema = load_json(DESIGN_ROOT / "template.schema.json")
    definitions = set(schema["$defs"])
    assert local_schema_refs(schema) <= definitions
    assert open_object_schema_paths(schema) == []
    assert schema["$defs"]["variables"]["properties"]["maximum_causal_mutations_per_pair"]["const"] == 1


def test_template_schema_rejects_unknown_root_keys_by_contract() -> None:
    schema = load_json(DESIGN_ROOT / "template.schema.json")
    errors = root_key_errors(schema, {"unexpected": True})
    assert errors["unknown"] == ["unexpected"]
    assert set(errors["missing"]) == set(schema["required"])


def test_historical_cases_are_excluded_consistently() -> None:
    matrix = load_json(DESIGN_ROOT / "capability_matrix.json")
    selection = load_json(DESIGN_ROOT / "selection_governance.json")
    assert set(matrix["historical_exclusions"]["case_ids"]) == HISTORICAL_CASE_IDS
    assert set(selection["historical_exclusion"]["case_ids"]) == HISTORICAL_CASE_IDS
    assert selection["historical_exclusion"]["semantic_copy_forbidden_in_confirmation"] is True


def test_manifest_detects_tampered_design_asset(tmp_path: Path) -> None:
    manifest = load_json(DESIGN_ROOT / "freeze_manifest.json")
    copied_root = tmp_path / "repo"
    for item in manifest["files"]:
        source = REPO_ROOT / item["path"]
        target = copied_root / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    assert manifest_hash_errors(copied_root, manifest) == []

    charter = copied_root / "docs" / "current" / "benchmark" / "v1" / "benchmark_charter.md"
    charter.write_text(charter.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
    errors = manifest_hash_errors(copied_root, manifest)
    assert any(item["path"].endswith("benchmark_charter.md") and item["error"] == "hash mismatch" for item in errors)


def test_manifest_hashes_are_checkout_line_ending_stable(tmp_path: Path) -> None:
    manifest = load_json(DESIGN_ROOT / "freeze_manifest.json")
    copied_root = tmp_path / "repo"
    for item in manifest["files"]:
        source = REPO_ROOT / item["path"]
        target = copied_root / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())

    charter = copied_root / "docs" / "current" / "benchmark" / "v1" / "benchmark_charter.md"
    charter.write_bytes(charter.read_bytes().replace(b"\n", b"\r\n"))
    assert manifest_hash_errors(copied_root, manifest) == []


def test_manifest_file_set_is_complete_and_unique() -> None:
    manifest = load_json(DESIGN_ROOT / "freeze_manifest.json")
    file_map, duplicates = manifest_file_map(manifest)
    assert set(file_map) == EXPECTED_MANIFEST_FILES
    assert duplicates == []


def test_manifest_milestone_cannot_lag_an_approved_review() -> None:
    manifest = load_json(DESIGN_ROOT / "freeze_manifest.json")
    review = load_json(DESIGN_ROOT / "protocol_review.json")
    assert milestone_state_matches_review(manifest, review)

    approved_review = copy.deepcopy(review)
    approved_review["status"] = "approved"
    approved_review["decision"] = "approved"
    approved_review["reviewer"] = {
        "name": "independent reviewer",
        "role": "independent_reviewer",
        "independent_of_authoring": True,
        "reviewed_at": "2026-08-19T00:00:00Z",
    }
    for item in approved_review["checklist"]:
        item["decision"] = "approved"
    assert not milestone_state_matches_review(manifest, approved_review)

    complete_manifest = copy.deepcopy(manifest)
    complete_manifest["milestone"] = {
        "milestone_id": "M-BENCH-DESIGN-FREEZE-V1",
        "status": "complete",
        "complete": True,
        "blocking_gate": None,
    }
    assert milestone_state_matches_review(complete_manifest, approved_review)


def test_local_markdown_links_resolve() -> None:
    assert local_markdown_link_errors(sorted(DESIGN_ROOT.glob("*.md"))) == []


def test_selection_accounting_proves_zero_call_design_state() -> None:
    selection = load_json(DESIGN_ROOT / "selection_governance.json")
    accounting = selection["current_design_freeze_accounting"]
    assert accounting["instances_generated"] == 0
    assert accounting["provider_calls"] == 0
    assert accounting["judge_calls"] == 0
    assert accounting["formal_result_roots_created"] == 0
    assert accounting["confirmation_unsealed"] is False
    assert accounting["selective_e2e_selected"] is False


def test_json_assets_are_utf8_objects() -> None:
    for path in sorted(DESIGN_ROOT.glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(value, dict), path
