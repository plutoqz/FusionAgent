from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


C3_ROW_ID = "c3_replan_fault_recovery"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _find_c3_row(paper_freeze: dict[str, Any]) -> dict[str, Any]:
    rows = paper_freeze.get("rows")
    if not isinstance(rows, list):
        raise ValueError("paper freeze must contain a rows list")
    for row in rows:
        if isinstance(row, dict) and row.get("row_id") == C3_ROW_ID:
            return row
    raise ValueError(f"paper freeze row not found: {C3_ROW_ID}")


def _verification_anchors(c3_row: dict[str, Any]) -> list[str]:
    anchors: list[str] = []
    for value in c3_row.get("evidence_paths") or []:
        if value:
            anchors.append(str(value))
    for value in c3_row.get("verification_command") or []:
        text = str(value)
        if "::" in text and text not in anchors:
            anchors.append(text)
    return anchors


def build_recovery_governance_report(
    paper_freeze_path: Path,
    *,
    output_json: Path,
    output_markdown: Path | None = None,
) -> dict[str, Any]:
    paper_freeze = _load_json(paper_freeze_path)
    c3_row = _find_c3_row(paper_freeze)
    metrics = c3_row.get("metrics") if isinstance(c3_row.get("metrics"), dict) else {}
    verification_anchors = _verification_anchors(c3_row)

    rows = [
        {
            "condition_id": "B0_no_repair_or_replan_boundary",
            "runtime_mode": "no_repair_or_replan",
            "evidence_role": "contrast_boundary",
            "repair_allowed": False,
            "replan_allowed": False,
            "observed_status": "not_promoted_as_independent_benchmark",
            "execution_outcome": "primary failure remains failed or requires manual intervention",
            "recovery_success_rate": "not_measured",
            "decision_trace_completeness": "not_applicable",
            "evidence_anchors": [
                "docs/superpowers/specs/2026-04-20-evaluation-contract-claim-lock.md",
                "tests/test_agent_run_service_enhancements.py::test_workflow_executor_emits_step_failed_before_final_step_error",
            ],
            "claim_boundary": "Use as a recovery contrast boundary, not as a frozen statistical baseline.",
        },
        {
            "condition_id": "B1_bounded_healing_replan_verified",
            "runtime_mode": "bounded_healing_and_replan",
            "evidence_role": "verified_recovery_row",
            "repair_allowed": True,
            "replan_allowed": True,
            "observed_status": c3_row.get("observed_status"),
            "execution_outcome": "failed execution re-enters through healing, applies revision 2, refreshes inputs when source changes, and succeeds",
            "recovery_success_rate": metrics.get("recovery_success_rate", "unknown"),
            "decision_trace_completeness": metrics.get("decision_trace_completeness", "unknown"),
            "execution_success_rate": metrics.get("execution_success_rate", "unknown"),
            "evidence_anchors": verification_anchors,
            "claim_boundary": "Supports bounded recovery under focused fault-injection regressions only.",
        },
        {
            "condition_id": "G1_replan_grounding_fail_closed",
            "runtime_mode": "bounded_healing_and_replan",
            "evidence_role": "safety_guard",
            "repair_allowed": True,
            "replan_allowed": True,
            "observed_status": "passed_regression",
            "execution_outcome": "ungrounded replanned workflow is rejected before execution",
            "recovery_success_rate": "guard_not_recovery_success",
            "decision_trace_completeness": "pass",
            "evidence_anchors": [
                "tests/test_agent_run_service_enhancements.py::test_replan_result_is_rejected_when_grounding_enforcement_fails",
                "docs/superpowers/plans/done/2026-06-04-plan-grounding-hard-gate.md",
            ],
            "claim_boundary": "Shows fail-closed governance; it should not be counted as a recovered success.",
        },
        {
            "condition_id": "G2_replan_limit_fail_closed",
            "runtime_mode": "bounded_healing_and_replan",
            "evidence_role": "safety_guard",
            "repair_allowed": True,
            "replan_allowed": "bounded_by_max_plan_revisions",
            "observed_status": "passed_regression",
            "execution_outcome": "run fails with replan_rejected after max plan revisions is reached",
            "recovery_success_rate": "guard_not_recovery_success",
            "decision_trace_completeness": "pass",
            "evidence_anchors": [
                "tests/test_agent_run_service_enhancements.py::test_agent_run_service_fails_when_replan_limit_is_reached",
            ],
            "claim_boundary": "Shows bounded retry governance; it prevents unlimited self-healing claims.",
        },
    ]

    payload = {
        "source": "recovery-governance-evidence",
        "scope": (
            "C3 recovery governance table derived from the frozen paper evidence row and focused "
            "regression anchors. It is a thesis evidence table, not a new statistical benchmark."
        ),
        "paper_freeze_path": str(Path(paper_freeze_path)).replace("\\", "/"),
        "c3_row_id": C3_ROW_ID,
        "verified_recovery_condition_count": sum(
            1 for row in rows if row["evidence_role"] == "verified_recovery_row"
        ),
        "safety_guard_condition_count": sum(
            1 for row in rows if row["evidence_role"] == "safety_guard"
        ),
        "contrast_boundary_count": sum(
            1 for row in rows if row["evidence_role"] == "contrast_boundary"
        ),
        "promotion_statement": (
            "C3 supports bounded healing/replan robustness under focused regressions; it does not "
            "support unconstrained self-healing, unlimited retries, or statistical superiority."
        ),
        "rows": rows,
    }

    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if output_markdown is not None:
        output_markdown = Path(output_markdown)
        output_markdown.parent.mkdir(parents=True, exist_ok=True)
        output_markdown.write_text(_render_markdown(payload), encoding="utf-8")
    return payload


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Recovery Governance Evidence",
        "",
        payload["scope"],
        "",
        f"- Paper freeze: `{payload['paper_freeze_path']}`",
        f"- C3 row: `{payload['c3_row_id']}`",
        f"- Verified recovery conditions: {payload['verified_recovery_condition_count']}",
        f"- Safety guard conditions: {payload['safety_guard_condition_count']}",
        f"- Promotion statement: {payload['promotion_statement']}",
        "",
        "| Condition | Role | Repair | Replan | Status | Outcome | Recovery | Trace |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload["rows"]:
        lines.append(
            "| {condition_id} | {evidence_role} | {repair_allowed} | {replan_allowed} | "
            "{observed_status} | {execution_outcome} | {recovery_success_rate} | "
            "{decision_trace_completeness} |".format(**row)
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export C3 recovery governance evidence table.")
    parser.add_argument("--paper-freeze", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-markdown", default="")
    args = parser.parse_args(argv)
    payload = build_recovery_governance_report(
        Path(args.paper_freeze),
        output_json=Path(args.output_json),
        output_markdown=Path(args.output_markdown) if args.output_markdown else None,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
