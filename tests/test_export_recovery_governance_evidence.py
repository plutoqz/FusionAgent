from __future__ import annotations

import json
from pathlib import Path

from scripts.export_recovery_governance_evidence import build_recovery_governance_report


def _paper_freeze_payload() -> dict:
    return {
        "rows": [
            {
                "row_id": "c3_replan_fault_recovery",
                "observed_status": "passed",
                "metrics": {
                    "recovery_success_rate": "pass",
                    "decision_trace_completeness": "pass",
                    "execution_success_rate": "pass",
                },
                "verification_command": [
                    "python",
                    "-m",
                    "pytest",
                    "-q",
                    "tests/test_agent_run_service_enhancements.py::test_agent_run_service_replans_after_execution_failure",
                ],
                "evidence_paths": [
                    "tests/test_agent_run_service_enhancements.py",
                    "tests/test_agent_run_service_enhancements.py::test_task_driven_replan_refreshes_inputs_when_source_changes",
                ],
            }
        ]
    }


def test_build_recovery_governance_report_derives_c3_table(tmp_path: Path) -> None:
    paper_freeze = tmp_path / "paper-freeze.json"
    paper_freeze.write_text(json.dumps(_paper_freeze_payload()), encoding="utf-8")
    output_json = tmp_path / "recovery.json"
    output_markdown = tmp_path / "recovery.md"

    payload = build_recovery_governance_report(
        paper_freeze,
        output_json=output_json,
        output_markdown=output_markdown,
    )

    assert payload["verified_recovery_condition_count"] == 1
    assert payload["safety_guard_condition_count"] == 2
    assert payload["contrast_boundary_count"] == 1
    by_condition = {row["condition_id"]: row for row in payload["rows"]}
    assert by_condition["B0_no_repair_or_replan_boundary"]["recovery_success_rate"] == "not_measured"
    assert by_condition["B1_bounded_healing_replan_verified"]["recovery_success_rate"] == "pass"
    assert by_condition["B1_bounded_healing_replan_verified"]["execution_success_rate"] == "pass"
    assert by_condition["G1_replan_grounding_fail_closed"]["evidence_role"] == "safety_guard"
    assert by_condition["G2_replan_limit_fail_closed"]["replan_allowed"] == "bounded_by_max_plan_revisions"

    saved = json.loads(output_json.read_text(encoding="utf-8"))
    assert saved["c3_row_id"] == "c3_replan_fault_recovery"
    markdown = output_markdown.read_text(encoding="utf-8")
    assert "Recovery Governance Evidence" in markdown
    assert "B1_bounded_healing_replan_verified" in markdown
