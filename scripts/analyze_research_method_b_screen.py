from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from schemas.research_case_manifest import load_research_case_manifest
from schemas.research_llm_pilot import ResearchPlanningDecision
from services.research_plan_evaluation import evaluate_research_plan


def analyze_screen(
    root: Path,
    *,
    manifest_path: Path,
    baseline_audit_path: Path,
) -> dict[str, Any]:
    schedule = _read_json(root / "schedule.json")
    prepared = _read_json(root / "prepared_inputs.json")
    baseline = _read_json(baseline_audit_path)
    manifest = load_research_case_manifest(manifest_path)
    cases = {case.case_id: case for case in manifest.cases}
    prepared_by_run = {item["schedule"]["run_id"]: item for item in prepared}
    schedule_by_run = {item["run_id"]: item for item in schedule["items"]}
    results = [
        _read_json(path)
        for path in sorted((root / "runs").glob("*/result.json"))
    ]
    rows = []
    for result in results:
        run_id = result["run_id"]
        scheduled = schedule_by_run[run_id]
        projection = prepared_by_run[run_id]
        plan = None
        failure_class = result.get("failure_class")
        if isinstance(result.get("plan"), dict):
            try:
                plan = ResearchPlanningDecision.model_validate(result["plan"])
            except ValidationError:
                failure_class = failure_class or "schema_validation_error"
        evaluation = evaluate_research_plan(
            cases[scheduled["case_id"]],
            plan,
            allowed_strings=set(_strings(projection["payload"])),
            failure_class=failure_class,
        )
        attempt = result.get("attempt") or {}
        usage = attempt.get("usage") or {}
        rows.append(
            {
                "run_id": run_id,
                "case_id": scheduled["case_id"],
                "success": result.get("success") is True,
                "failure_class": failure_class,
                "automatic_score": evaluation.automatic_score,
                "failed_checks": [
                    check.check_id for check in evaluation.automatic_checks if not check.passed
                ],
                "grounding_pass": evaluation.grounding_pass,
                "ungrounded_refs": evaluation.ungrounded_refs,
                "decision": plan.decision if plan else None,
                "task_order": [task.task_kind for task in plan.tasks] if plan else [],
                "delivery_states": {
                    task.task_kind: task.delivery_state for task in plan.tasks
                }
                if plan
                else {},
                "total_tokens": usage.get("total_tokens", 0),
                "input_bytes": len(
                    json.dumps(projection["payload"], ensure_ascii=False, sort_keys=True).encode("utf-8")
                ),
                "evaluation": evaluation.model_dump(mode="json"),
            }
        )

    baseline_cells = {
        item["case_id"]: item
        for item in baseline["cell_stability"]
        if item["knowledge_condition"] == "llm_full_contract_kg"
    }
    baseline_group = next(
        item
        for item in baseline["group_metrics"]
        if item["knowledge_condition"] == "llm_full_contract_kg"
    )
    baseline_mean = float(baseline_group["mean_automatic_score_all_runs"])
    expected_one_rep_tokens = float(baseline_group["tokens"]) / 5.0
    row_by_case = {row["case_id"]: row for row in rows}
    at_or_above = [
        case_id
        for case_id, row in row_by_case.items()
        if row["automatic_score"] >= float(baseline_cells[case_id]["automatic_score_mean"])
    ]
    mean_score = sum(row["automatic_score"] for row in rows) / len(rows) if rows else 0.0
    total_tokens = sum(int(row["total_tokens"] or 0) for row in rows)
    checks = {
        "all_six_calls_successful": len(rows) == 6 and all(row["success"] for row in rows),
        "grounding_failures_zero": all(row["grounding_pass"] for row in rows),
        "negative_control_minimum_score": row_by_case.get("C03", {}).get("automatic_score", 0) >= 0.875,
        "mean_score_strictly_above_full_contract_kg_90_run_mean": mean_score > baseline_mean,
        "at_least_four_cases_match_or_exceed_cell_mean": len(at_or_above) >= 4,
        "c01_and_c02_not_below_cell_mean": all(case_id in at_or_above for case_id in ("C01", "C02")),
        "total_tokens_below_full_contract_kg_one_repetition_equivalent": total_tokens < expected_one_rep_tokens,
    }
    return {
        "report_type": "method_b_development_screen_analysis",
        "protocol_id": schedule["protocol_id"],
        "screen_passed": all(checks.values()),
        "checks": checks,
        "method_b": {
            "runs": len(rows),
            "mean_automatic_score": mean_score,
            "total_tokens": total_tokens,
            "mean_input_bytes": sum(row["input_bytes"] for row in rows) / len(rows) if rows else 0,
            "cases_at_or_above_baseline_cell_mean": sorted(at_or_above),
        },
        "baseline": {
            "condition": "llm_full_contract_kg",
            "runs": baseline_group["calls"],
            "mean_automatic_score": baseline_mean,
            "one_repetition_equivalent_tokens": expected_one_rep_tokens,
        },
        "rows": sorted(rows, key=lambda item: item["case_id"]),
        "claim_boundary": (
            "Development-set mechanism screen only. This result can select method B for held-out evaluation "
            "but cannot establish superiority or statistical significance."
        ),
    }


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze the method B development screen.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO_ROOT / "docs" / "current" / "research-case-manifest-v1.json",
    )
    parser.add_argument(
        "--baseline-audit",
        type=Path,
        default=Path(
            r"D:\code\fusionagent-evidence\p3-planning-repeated\2026-08-15-deepseek-v4-flash-repeated-combined-v1\formal_combined_automatic_audit.json"
        ),
    )
    args = parser.parse_args()
    report = analyze_screen(
        args.root,
        manifest_path=args.manifest,
        baseline_audit_path=args.baseline_audit,
    )
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
