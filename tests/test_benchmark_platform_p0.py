from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.audit_benchmark_platform_core import (
    AUDIT_PATH,
    BASELINE_PATH,
    EXPECTED_ACCOUNTING,
    EXPECTED_PLATFORM_TEST_COMMAND,
    P0_COMMIT,
    PROTOCOL_COMMIT,
    PROTOCOL_TAG,
    PROCESS_COMMAND_PATTERN,
    canonical_file_sha256,
    git_blob_sha256,
    is_allowed_p0_path,
    load_json,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE = REPO_ROOT / BASELINE_PATH


def test_bp0_machine_audit_is_frozen_at_p0_commit() -> None:
    audit_path = REPO_ROOT / AUDIT_PATH
    result = load_json(audit_path)
    assert result["overall_passed"] is True
    assert result["required_failures"] == []
    assert result["stage_status"] == "complete"
    assert result["next_stage"] == "P1/BP1"
    assert result["automatic_progression"] is False
    assert canonical_file_sha256(audit_path) == git_blob_sha256(REPO_ROOT, P0_COMMIT, AUDIT_PATH)


def test_protocol_tag_is_the_exact_starting_head() -> None:
    baseline = load_json(BASELINE)
    assert baseline["git"]["protocol_tag"] == PROTOCOL_TAG
    assert baseline["git"]["protocol_commit"] == PROTOCOL_COMMIT
    assert baseline["git"]["starting_head"] == PROTOCOL_COMMIT
    assert baseline["git"]["working_tree_clean_at_capture"] is True
    assert baseline["git"]["status_at_capture"] == []


def test_frozen_input_hashes_match_protocol_tag() -> None:
    baseline = load_json(BASELINE)
    for item in baseline["frozen_inputs"]:
        assert git_blob_sha256(REPO_ROOT, PROTOCOL_TAG, item["path"]) == item["sha256"]
        assert git_blob_sha256(REPO_ROOT, P0_COMMIT, item["path"]) == item["sha256"]
        if item["path"] != "requirements.txt":
            assert canonical_file_sha256(REPO_ROOT / item["path"]) == item["sha256"]


def test_p0_has_zero_calls_and_no_platform_artifacts() -> None:
    baseline = load_json(BASELINE)
    assert baseline["accounting"] == EXPECTED_ACCOUNTING
    assert baseline["paths"]["package_exists_at_capture"] is False
    assert subprocess.run(
        ["git", "cat-file", "-e", f"{P0_COMMIT}:benchmark_platform"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    ).returncode != 0
    assert baseline["paths"]["future_output_root_exists_at_capture"] is False
    assert not Path(baseline["paths"]["future_output_root"]).exists()


def test_p0_authorization_stops_before_p1() -> None:
    baseline = load_json(BASELINE)
    assert baseline["authorization"]["authorized_through"] == "P0/BP0"
    assert baseline["authorization"]["p1_automatic_progression"] is False
    assert baseline["authorization"]["provider_or_experiment_authorized"] is False
    assert baseline["next_stage"]["stage"] == "P1"
    assert baseline["next_stage"]["automatic_progression"] is False


def test_cross_platform_test_command_is_frozen_and_failed_glob_is_retained() -> None:
    baseline = load_json(BASELINE)
    assert baseline["validation_contract"]["commands"][0] == EXPECTED_PLATFORM_TEST_COMMAND
    assert baseline["validation_attempts"] == [
        {
            "attempt_id": "P0-TEST-01",
            "command": "python -m pytest tests/test_benchmark_platform_*.py -q --basetemp tmp/pytest-benchmark-platform-core",
            "status": "failed_retained",
            "exit_code": 4,
            "failure_class": "tooling.powershell_native_glob_not_expanded",
            "observed_output": "ERROR: file or directory not found: tests/test_benchmark_platform_*.py; no tests ran",
        },
        {
            "attempt_id": "P0-TEST-02",
            "command": "python -m pytest tests -q -k benchmark_platform --basetemp tmp/pytest-benchmark-platform-core",
            "status": "failed_retained",
            "exit_code": 1,
            "failure_class": "test_scope.protocol_freeze_tests_not_applicable_to_implementation_branch",
            "observed_output": "1 failed, 15 passed, 1478 deselected; protocol audit rejected the expected implementation directory and P0 change set",
        },
        {
            "attempt_id": "P0-TEST-03",
            "command": "python -m pytest tests -q -k \"benchmark_platform and not protocol\" --basetemp tmp/pytest-benchmark-platform-core",
            "status": "rejected_incomplete",
            "exit_code": 0,
            "failure_class": "test_scope.keyword_exclusion_dropped_p0_tests",
            "observed_output": "6 passed, 1488 deselected; two P0 tests containing protocol in their node IDs were not run",
        },
    ]


def test_process_probe_is_platform_scoped_and_false_positive_is_retained() -> None:
    baseline = load_json(BASELINE)
    assert baseline["process_probe"]["command_line_pattern"] == PROCESS_COMMAND_PATTERN
    assert baseline["process_probe"]["matching_processes_at_capture"] == []
    assert len(baseline["audit_attempts"]) == 1
    attempt = baseline["audit_attempts"][0]
    assert attempt["attempt_id"] == "P0-AUDIT-01"
    assert attempt["status"] == "failed_retained"
    assert attempt["failure_class"] == "tooling.process_probe_scope_false_positive"


def test_p0_path_allowlist_is_closed() -> None:
    assert is_allowed_p0_path(BASELINE_PATH)
    assert is_allowed_p0_path(AUDIT_PATH)
    assert is_allowed_p0_path("scripts/audit_benchmark_platform_core.py")
    assert is_allowed_p0_path("tests/test_benchmark_platform_p0.py")
    assert not is_allowed_p0_path("benchmark_platform/models.py")
    assert not is_allowed_p0_path("requirements.txt")
    assert not is_allowed_p0_path("docs/current/benchmark/v1/template.schema.json")


def test_tampered_starting_commit_blocks_bp0(tmp_path: Path) -> None:
    from scripts.audit_benchmark_platform_core import audit_p0

    baseline = load_json(BASELINE)
    baseline["git"]["starting_head"] = "0" * 40
    tampered = tmp_path / "p0_baseline.json"
    tampered.write_text(json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = audit_p0(REPO_ROOT, tampered, probe_processes=False)
    assert result["overall_passed"] is False
    assert "protocol_tag_inheritance" in result["required_failures"]
