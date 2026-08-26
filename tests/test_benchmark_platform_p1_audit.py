from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_benchmark_platform_core import (
    P1_ACCOUNTING,
    P1_CHECKPOINT_PATH,
    audit_p1,
    load_json,
    package_import_errors,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = REPO_ROOT / P1_CHECKPOINT_PATH


def test_bp1_machine_audit_passes() -> None:
    result = audit_p1(REPO_ROOT, CHECKPOINT, probe_processes=False)
    assert result["overall_passed"] is True
    assert result["required_failures"] == []
    assert result["stage_status"] == "complete"
    assert result["next_stage"] == "P2/BP2"
    assert result["automatic_progression"] is False


def test_only_approved_dependency_was_added() -> None:
    result = audit_p1(REPO_ROOT, CHECKPOINT, probe_processes=False)
    check = next(item for item in result["checks"] if item["check_id"] == "p1_dependency_boundary")
    assert check["passed"] is True
    assert check["details"] == {
        "added": ["jsonschema>=4.23,<5"],
        "removed": [],
        "installed_jsonschema": "4.23.0",
    }


def test_package_has_no_legacy_network_or_llm_imports() -> None:
    assert package_import_errors(REPO_ROOT) == []


def test_p1_accounting_is_zero_call_and_stops_before_p2() -> None:
    checkpoint = load_json(CHECKPOINT)
    assert checkpoint["accounting"] == P1_ACCOUNTING
    assert checkpoint["accounting"]["platform_implementation_started"] is True
    assert checkpoint["next_stage"]["stage"] == "P2"
    assert checkpoint["next_stage"]["automatic_progression"] is False
    assert not Path(checkpoint["paths"]["future_output_root"]).exists()


def test_tampered_source_hash_blocks_bp1(tmp_path: Path) -> None:
    checkpoint = load_json(CHECKPOINT)
    checkpoint["files"][0]["sha256"] = "sha256:" + "0" * 64
    tampered = tmp_path / "p1_checkpoint.json"
    tampered.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = audit_p1(REPO_ROOT, tampered, probe_processes=False)
    assert result["overall_passed"] is False
    assert "p1_artifact_hashes" in result["required_failures"]
