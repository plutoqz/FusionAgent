from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from schemas.research_case_manifest import load_research_case_manifest
from schemas.research_llm_pilot import ResearchPlanningDecision
from services.research_plan_evaluation import evaluate_research_plan


def analyze_formal(root: Path, *, manifest_path: Path) -> dict[str, Any]:
    manifest = load_research_case_manifest(manifest_path)
    cases = {case.case_id: case for case in manifest.cases}
    schedule = _read_json(root / "schedule.json")
    prepared = _read_json(root / "prepared_inputs.json")
    prepared_by_run = {item["schedule"]["run_id"]: item for item in prepared}
    schedule_by_run = {item["run_id"]: item for item in schedule["items"]}
    results = [_read_json(path) for path in sorted((root / "runs").glob("*/result.json"))]
    rows = []
    for result in results:
        run_id = result["run_id"]
        item = schedule_by_run[run_id]
        projection = prepared_by_run[run_id]
        plan = None
        failure_class = result.get("failure_class")
        if isinstance(result.get("plan"), dict):
            try:
                plan = ResearchPlanningDecision.model_validate(result["plan"])
            except ValidationError:
                failure_class = failure_class or "schema_validation_error"
        evaluation = evaluate_research_plan(
            cases[item["case_id"]],
            plan,
            allowed_strings=set(_strings(projection["payload"])),
            failure_class=failure_class,
        )
        attempt = result.get("attempt") or {}
        usage = attempt.get("usage") or {}
        rows.append(
            {
                "run_id": run_id,
                "case_id": item["case_id"],
                "knowledge_condition": item["knowledge_condition"],
                "replicate": item["replicate"],
                "success": result.get("success") is True,
                "failure_class": failure_class,
                "automatic_score": evaluation.automatic_score,
                "grounding_pass": evaluation.grounding_pass,
                "ungrounded_refs": evaluation.ungrounded_refs,
                "failed_checks": [check.check_id for check in evaluation.automatic_checks if not check.passed],
                "decision": plan.decision if plan else None,
                "task_order": [task.task_kind for task in plan.tasks] if plan else [],
                "delivery_states": {task.task_kind: task.delivery_state for task in plan.tasks} if plan else {},
                "structural_signature": _structural_signature(plan),
                "total_tokens": usage.get("total_tokens", 0),
                "latency_ms": attempt.get("latency_ms"),
                "evaluation": evaluation.model_dump(mode="json"),
            }
        )
    groups = defaultdict(list)
    for row in rows:
        groups[(row["case_id"], row["knowledge_condition"])].append(row)
    grouped = []
    for (case_id, condition), items in sorted(groups.items()):
        grouped.append(
            {
                "case_id": case_id,
                "knowledge_condition": condition,
                "calls": len(items),
                "successful_calls": sum(item["success"] for item in items),
                "mean_automatic_score": _mean(item["automatic_score"] for item in items),
                "min_automatic_score": min((item["automatic_score"] for item in items), default=0),
                "mean_tokens": _mean(item["total_tokens"] for item in items),
                "mean_latency_ms": _mean(item["latency_ms"] for item in items),
                "grounding_failures": sum(not item["grounding_pass"] for item in items),
                "distinct_structure_signatures": len({item["structural_signature"] for item in items}),
                "failed_checks": sorted({check for item in items for check in item["failed_checks"]}),
            }
        )
    by_cell = {(item["case_id"], item["knowledge_condition"]): item for item in grouped}
    b_cells = [by_cell[(case_id, "task_conditioned_contract_aware_kg")] for case_id in cases if (case_id, "task_conditioned_contract_aware_kg") in by_cell]
    full_cells = [by_cell[(case_id, "llm_full_contract_kg")] for case_id in cases if (case_id, "llm_full_contract_kg") in by_cell]
    llm_cells = [by_cell[(case_id, "llm_only")] for case_id in cases if (case_id, "llm_only") in by_cell]
    checks = {
        "complete_54_call_grid": len(rows) == 54 and all(item["successful_calls"] == 3 for item in grouped),
        "grounding_failures_zero": all(item["grounding_failures"] == 0 for item in grouped),
        "b_not_below_full_contract_on_at_least_four_cases": sum(
            b["mean_automatic_score"] >= f["mean_automatic_score"]
            for b, f in zip(sorted(b_cells, key=lambda x: x["case_id"]), sorted(full_cells, key=lambda x: x["case_id"]))
        ) >= 4,
        "b_positive_mean_above_full_contract": _mean(item["mean_automatic_score"] for item in b_cells)
        > _mean(item["mean_automatic_score"] for item in full_cells),
        "b_positive_mean_not_below_llm_only": _mean(item["mean_automatic_score"] for item in b_cells)
        >= _mean(item["mean_automatic_score"] for item in llm_cells),
        "negative_control_b_rejects": _negative_control_rejects(rows),
    }
    return {
        "report_type": "method_b_heldout_formal_analysis",
        "protocol_id": schedule["protocol_id"],
        "automatic_checks": checks,
        "automatic_screen_passed": all(checks.values()),
        "manual_review_status": "pending",
        "claim_eligible": False,
        "grouped_cells": grouped,
        "rows": sorted(rows, key=lambda item: item["run_id"]),
        "claim_boundary": (
            "Held-out automatic planning evidence only. Superiority remains unclaimed until blinded manual review, "
            "stability audit, and any required end-to-end validation are complete."
        ),
    }


def _negative_control_rejects(rows: list[dict[str, Any]]) -> bool:
    selected = [row for row in rows if row["case_id"] == "H06" and row["knowledge_condition"] == "task_conditioned_contract_aware_kg"]
    return bool(selected) and all(row["decision"] == "reject" and not row["task_order"] for row in selected)


def _structural_signature(plan: ResearchPlanningDecision | None) -> str | None:
    if plan is None:
        return None
    return json.dumps(
        {
            "decision": plan.decision,
            "tasks": [
                {
                    "task_kind": task.task_kind,
                    "source_ids": task.source_ids,
                    "algorithm_id": task.algorithm_id,
                    "delivery_state": task.delivery_state,
                }
                for task in plan.tasks
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _mean(values: Iterable[Any]) -> float:
    numbers = [float(value) for value in values if isinstance(value, (int, float))]
    return sum(numbers) / len(numbers) if numbers else 0.0


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
    parser = argparse.ArgumentParser(description="Analyze method B held-out formal evidence.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = analyze_formal(args.root, manifest_path=args.manifest)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
