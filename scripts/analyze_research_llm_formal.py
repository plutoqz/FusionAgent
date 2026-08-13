from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.analyze_research_llm_pilot import analyze_pilot


def analyze_formal(root: Path) -> dict[str, Any]:
    protocol = _read_json(root / "formal_protocol.json")
    freeze_audit = _read_json(root / "freeze_audit.json")
    execution = _read_json(root / "execution_config.json")
    summary = _read_json(root / "formal_summary.json")
    schedule = _read_json(root / "schedule.json")
    base = analyze_pilot(root)

    scheduled_ids = {item["run_id"] for item in schedule["items"]}
    result_ids = {item["run_id"] for item in base["runs"]}
    expected_model = protocol["provider"]["required_response_model_exact_match"]
    checks = {
        "freeze_audit_passed": freeze_audit.get("passed") is True,
        "formal_protocol_ready": protocol.get("formal_ready") is True
        and protocol.get("protocol_status") == "frozen",
        "protocol_id_match": execution.get("protocol_id") == protocol.get("protocol_id"),
        "model_revision_match": execution.get("model_revision")
        == protocol["provider"].get("model_revision"),
        "schedule_complete": len(scheduled_ids) == 18 and scheduled_ids == result_ids,
        "all_calls_succeeded": summary.get("successful_calls") == 18
        and summary.get("failed_calls") == 0,
        "response_model_exact_match": base["response_models"] == {expected_model: 18},
        "http_status_all_200": base["http_statuses"] == {"200": 18},
        "finish_reason_all_stop": base["finish_reasons"] == {"stop": 18},
        "strict_json_all_calls": all(_strict_json_result(root, run_id) for run_id in scheduled_ids),
        "input_leakage_zero": base["input_leakage"] is False,
        "ungrounded_reference_zero": base["grounding"]["runs_with_ungrounded_refs"] == 0,
        "failed_calls_not_replaced": summary.get("failed_calls_replaced") is False,
        "token_budget_respected": base["total_tokens"] <= protocol["budget"]["batch_token_budget"],
    }
    failed_automatic = [
        {"run_id": row["run_id"], "check_id": check["check_id"], "details": check["details"]}
        for row in base["runs"]
        for check in row["evaluation"]["automatic_checks"]
        if not check["passed"]
    ]
    manual_items = [
        {"run_id": row["run_id"], **item}
        for row in base["runs"]
        for item in row["evaluation"]["manual_review_items"]
    ]
    return {
        "report_type": "planning_only_formal_automatic_audit",
        "protocol_id": protocol["protocol_id"],
        "model": expected_model,
        "model_revision": protocol["provider"]["model_revision"],
        "execution_integrity_checks": checks,
        "formal_execution_valid": all(checks.values()),
        "automatic_evaluation_complete": True,
        "automatic_all_checks_passed": not failed_automatic,
        "comparative_claim_ready": all(checks.values()) and not manual_items,
        "manual_review_status": "pending" if manual_items else "complete",
        "manual_review_pending_count": len(manual_items),
        "manual_review_items": manual_items,
        "failed_automatic_check_count": len(failed_automatic),
        "failed_automatic_checks": failed_automatic,
        "call_count": base["call_count"],
        "successful_calls": base["successful_calls"],
        "failed_calls": base["failed_calls"],
        "total_tokens": base["total_tokens"],
        "group_metrics": _group_metrics(base["runs"]),
        "runs": base["runs"],
        "claim_boundary": (
            "Valid formal execution does not imply all rubric checks passed or that one condition is superior. "
            "Manual review and deterministic-baseline comparison remain required."
        ),
    }


def _group_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["knowledge_condition"]].append(row)
    metrics = []
    for condition, items in sorted(groups.items()):
        positive = [row for row in items if row["case_id"] != "C03"]
        metrics.append(
            {
                "knowledge_condition": condition,
                "calls": len(items),
                "mean_automatic_score_all_cases": _mean_score(items),
                "mean_automatic_score_positive_cases": _mean_score(positive),
                "runs_all_automatic_checks_passed": sum(
                    all(check["passed"] for check in row["evaluation"]["automatic_checks"])
                    for row in items
                ),
                "positive_case_count": len(positive),
                "negative_control_passed": all(
                    all(check["passed"] for check in row["evaluation"]["automatic_checks"])
                    for row in items
                    if row["case_id"] == "C03"
                ),
                "tokens": sum(row["total_tokens"] for row in items),
            }
        )
    return metrics


def _mean_score(rows: list[dict[str, Any]]) -> float | None:
    if not rows:
        return None
    return round(sum(row["evaluation"]["automatic_score"] for row in rows) / len(rows), 6)


def _strict_json_result(root: Path, run_id: str) -> bool:
    result = _read_json(root / "runs" / run_id / "result.json")
    return (result.get("attempt") or {}).get("parse_mode") == "strict_json"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a completed planning-only formal run.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = analyze_formal(args.root)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0 if report["formal_execution_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
