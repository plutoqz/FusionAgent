from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.audit_benchmark_platform_p7 import REVIEW_ITEMS, audit_p7, load


ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION = ROOT / "docs/current/benchmark/platform/v1/implementation"
MANIFEST = IMPLEMENTATION / "implementation_manifest.json"
REVIEW = IMPLEMENTATION / "p7_review.json"
CHECKPOINT = IMPLEMENTATION / "p7_checkpoint.json"


def test_p7_machine_checks_pass_and_human_review_remains() -> None:
    result = audit_p7(ROOT, MANIFEST, REVIEW, CHECKPOINT)
    assert result["machine_checks_passed"] is True
    assert result["machine_required_failures"] == []
    assert result["required_failures"] == ["human_implementation_review"]
    assert result["overall_passed"] is False
    assert result["stage_status"] == "awaiting_human_review"
    assert result["freeze_authorized"] is False


def test_manifest_file_categories_are_complete_and_hash_bound() -> None:
    result = audit_p7(ROOT, MANIFEST, REVIEW, CHECKPOINT)
    check = next(item for item in result["checks"] if item["check_id"] == "implementation_file_sets_and_hashes")
    assert check["passed"] is True
    assert check["details"]["errors"] == []
    assert check["details"]["category_counts"]["source"] == 10


def test_manifest_tamper_blocks_machine_gate(tmp_path: Path) -> None:
    manifest = load(MANIFEST)
    manifest["files"]["source"][0]["sha256"] = "sha256:" + "0" * 64
    tampered = tmp_path / "implementation_manifest.json"
    tampered.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = audit_p7(ROOT, tampered, REVIEW, CHECKPOINT)
    assert result["machine_checks_passed"] is False
    assert "implementation_file_sets_and_hashes" in result["machine_required_failures"]


def test_explicit_approved_review_would_open_freeze_gate(tmp_path: Path) -> None:
    review = copy.deepcopy(load(REVIEW))
    review["status"] = "approved"
    review["reviewer"] = {"name": "human-reviewer", "role": "user_or_independent_reviewer", "reviewed_at": "2026-08-30T00:00:00+08:00"}
    for item in review["checklist"]:
        item["decision"] = "approved"
        item["comment"] = "Reviewed against the implementation manifest and audit evidence."
    review["decision"] = "approved"
    review["overall_comment"] = "All bounded offline implementation checks are approved."
    approved = tmp_path / "p7_review.json"
    approved.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = audit_p7(ROOT, MANIFEST, approved, CHECKPOINT)
    assert {item["item_id"] for item in review["checklist"]} == REVIEW_ITEMS
    assert result["overall_passed"] is True
    assert result["required_failures"] == []
    assert result["freeze_authorized"] is True


def test_p7_accounting_and_next_action_remain_bounded() -> None:
    checkpoint = load(CHECKPOINT)
    assert checkpoint["accounting"]["provider_calls"] == 0
    assert checkpoint["accounting"]["judge_calls"] == 0
    assert checkpoint["accounting"]["benchmark_instances_generated"] == 0
    assert checkpoint["freeze"]["tag_created"] is False
    assert checkpoint["governance"]["updated"] is False
    assert checkpoint["next_action"] == "explicit_human_implementation_review"
