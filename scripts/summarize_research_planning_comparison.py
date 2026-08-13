from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def summarize_comparison(llm_path: Path, deterministic_path: Path) -> dict[str, Any]:
    llm = _read_json(llm_path)
    deterministic = _read_json(deterministic_path)
    rows = []
    for run in llm["runs"]:
        rows.append(_row(run["case_id"], run["knowledge_condition"], run["evaluation"], "llm"))
    for run in deterministic["runs"]:
        rows.append(_row(run["case_id"], run["group"], run["evaluation"], "deterministic"))
    groups = []
    for condition in sorted({row["condition"] for row in rows}):
        selected = [row for row in rows if row["condition"] == condition]
        positive = [row for row in selected if row["case_id"] != "C03"]
        groups.append(
            {
                "condition": condition,
                "source": selected[0]["source"],
                "calls": len(selected),
                "mean_automatic_score_all_cases": _mean(selected),
                "mean_automatic_score_positive_cases": _mean(positive),
                "all_checks_passed": sum(row["all_checks_passed"] for row in selected),
                "positive_cases": len(positive),
                "negative_control_all_checks_passed": all(
                    row["all_checks_passed"] for row in selected if row["case_id"] == "C03"
                ),
            }
        )
    return {
        "report_type": "descriptive_six_group_planning_comparison",
        "llm_protocol_id": llm["protocol_id"],
        "deterministic_protocol_id": deterministic["protocol_id"],
        "llm_execution_valid": llm["formal_execution_valid"],
        "deterministic_execution_valid": not deterministic["implementation_dirty"]
        and deterministic["run_count"] == 18,
        "same_implementation_commit": False,
        "claim_eligible": False,
        "groups": groups,
        "case_rows": sorted(rows, key=lambda row: (row["case_id"], row["condition"])),
        "boundaries": [
            "The deterministic output contract was frozen after the LLM formal batch; the batches have different implementation commits.",
            "One repetition per case-condition does not support stability or significance claims.",
            "Automatic scores include observed failures; no result was imputed, repaired, or replaced.",
            "C03 is a negative control and is excluded from positive-case means.",
            "Manual review remains required for the LLM batch and is not replaced by automatic scores.",
        ],
    }


def _row(case_id: str, condition: str, evaluation: dict[str, Any], source: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "condition": condition,
        "source": source,
        "automatic_score": evaluation["automatic_score"],
        "all_checks_passed": all(check["passed"] for check in evaluation["automatic_checks"]),
        "decision": evaluation.get("decision_valid"),
        "grounding": evaluation.get("grounding_pass"),
        "gap_f1": evaluation["gap_metrics"]["f1"],
    }


def _mean(rows: list[dict[str, Any]]) -> float | None:
    return round(sum(row["automatic_score"] for row in rows) / len(rows), 6) if rows else None


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a bounded descriptive six-group planning comparison.")
    parser.add_argument("--llm", type=Path, required=True)
    parser.add_argument("--deterministic", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = summarize_comparison(args.llm, args.deterministic)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
