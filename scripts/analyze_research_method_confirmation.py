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


PROTOCOL_ID = "fusionagent.method-b-independent-confirmation.v1"
METHOD_B_CONDITION = "task_conditioned_contract_aware_kg"
BASELINE_CONDITIONS = {"llm_only", "llm_full_contract_kg"}


def analyze_confirmation(
    *,
    root: Path,
    manifest_path: Path,
    output: Path,
) -> dict[str, Any]:
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite confirmation automatic analysis: {output}")
    manifest = load_research_case_manifest(manifest_path)
    cases = {case.case_id: case for case in manifest.cases}
    schedule = _read_json(root / "schedule.json")
    prepared = _read_json(root / "prepared_inputs.json")
    results = [_read_json(path) for path in sorted((root / "runs").glob("*/result.json"))]
    freeze_audit = _read_json(root / "freeze_audit.json")
    execution_config = _read_json(root / "execution_config.json")

    prepared_by_run = {item["schedule"]["run_id"]: item for item in prepared}
    schedule_by_run = {item["run_id"]: item for item in schedule["items"]}
    rows: list[dict[str, Any]] = []
    for result in results:
        run_id = result["run_id"]
        if run_id not in schedule_by_run or run_id not in prepared_by_run:
            raise RuntimeError(f"Result is not in frozen schedule: {run_id}")
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
        raw_response = attempt.get("raw_response")
        parsed_raw_response = _parse_raw_response(raw_response)
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
                "failed_checks": [
                    check.check_id
                    for check in evaluation.automatic_checks
                    if not check.passed
                ],
                "decision": plan.decision if plan else None,
                "task_order": [task.task_kind for task in plan.tasks] if plan else [],
                "delivery_states": {
                    task.task_kind: task.delivery_state for task in plan.tasks
                }
                if plan
                else {},
                "structural_signature": _structural_signature(plan),
                "total_tokens": usage.get("total_tokens", 0),
                "latency_ms": attempt.get("latency_ms"),
                "response_model": attempt.get("response_model"),
                "finish_reason": attempt.get("finish_reason") or _finish_reason(parsed_raw_response),
                "request_id": attempt.get("request_id"),
                "transport_retry_count": attempt.get("transport_retry_count"),
                "raw_request_payload_embedded": run_id in prepared_by_run,
                "raw_response_envelope_embedded": _has_response_envelope(parsed_raw_response),
                "manual_review_items": [
                    {"item_id": item.item_id, "status": item.status}
                    for item in evaluation.manual_review_items
                ],
                "evaluation": evaluation.model_dump(mode="json"),
            }
        )

    grouped = _group(rows)
    by_cell = {(item["case_id"], item["knowledge_condition"]): item for item in grouped}
    case_ids = sorted(cases)
    b_cells = [by_cell[(case_id, METHOD_B_CONDITION)] for case_id in case_ids]
    llm_cells = [by_cell[(case_id, "llm_only")] for case_id in case_ids]
    full_cells = [by_cell[(case_id, "llm_full_contract_kg")] for case_id in case_ids]
    b_rows = [row for row in rows if row["knowledge_condition"] == METHOD_B_CONDITION]

    execution_gates = {
        "freeze_audit_passed": freeze_audit.get("passed") is True,
        "complete_27_call_grid": len(rows) == 27
        and len(schedule.get("items", [])) == 27
        and all(item["calls"] == 3 for item in grouped),
        "all_calls_successful": len(rows) == 27 and all(row["success"] for row in rows),
        "exact_response_model": all(
            row["response_model"] == execution_config["requested_model"] for row in rows
        ),
        "all_finish_reason_stop": all(row["finish_reason"] == "stop" for row in rows),
        "unique_request_ids": len({row["request_id"] for row in rows}) == 27
        and all(row["request_id"] for row in rows),
        "usage_present": all(isinstance(row["total_tokens"], int) and row["total_tokens"] >= 0 for row in rows),
        "zero_transport_retries": all(row["transport_retry_count"] == 0 for row in rows),
        "raw_request_payloads_embedded": all(row["raw_request_payload_embedded"] for row in rows),
        "raw_response_envelopes_embedded": all(row["raw_response_envelope_embedded"] for row in rows),
        "historical_results_reused": _read_json(root / "formal_summary.json").get(
            "historical_results_reused"
        )
        == 0,
    }
    planning_gates = {
        "b_zero_grounding_failures": all(row["grounding_pass"] for row in b_rows),
        "b_zero_failed_automatic_checks": all(not row["failed_checks"] for row in b_rows),
        "b_mean_above_llm_only": _mean(item["mean_automatic_score"] for item in b_cells)
        > _mean(item["mean_automatic_score"] for item in llm_cells),
        "b_mean_above_full_kg": _mean(item["mean_automatic_score"] for item in b_cells)
        > _mean(item["mean_automatic_score"] for item in full_cells),
        "b_not_below_each_baseline_per_case": all(
            b["mean_automatic_score"] >= llm["mean_automatic_score"]
            and b["mean_automatic_score"] >= full["mean_automatic_score"]
            for b, llm, full in zip(b_cells, llm_cells, full_cells)
        ),
    }
    evidence_integrity_checks = {
        "freeze_audit_passed": execution_gates["freeze_audit_passed"],
        "complete_27_call_grid": execution_gates["complete_27_call_grid"],
        "all_calls_successful": execution_gates["all_calls_successful"],
        "exact_response_model": execution_gates["exact_response_model"],
        "all_finish_reason_stop": execution_gates["all_finish_reason_stop"],
        "unique_request_ids": execution_gates["unique_request_ids"],
        "usage_present": execution_gates["usage_present"],
        "zero_transport_retries": execution_gates["zero_transport_retries"],
        "raw_request_payloads_embedded": execution_gates["raw_request_payloads_embedded"],
        "raw_response_envelopes_embedded": execution_gates["raw_response_envelopes_embedded"],
        "historical_results_reused_zero": execution_gates["historical_results_reused"],
    }
    evidence_integrity_valid = all(evidence_integrity_checks.values())
    formal_execution_complete = evidence_integrity_valid and len(rows) == 27
    report = {
        "report_type": "method_b_independent_confirmation_automatic_analysis",
        "protocol_id": PROTOCOL_ID,
        "analysis_mode": "new_confirmation_only_no_historical_result_reuse",
        "evidence_root": str(root.resolve()),
        "manifest_path": str(manifest_path.resolve()),
        "execution_integrity": execution_gates,
        "evidence_integrity_checks": evidence_integrity_checks,
        "evidence_integrity_valid": evidence_integrity_valid,
        "formal_execution_complete": formal_execution_complete,
        "planning_automatic_gates": planning_gates,
        "automatic_gate_passed": all(execution_gates.values())
        and all(planning_gates.values()),
        "scheduled_calls": len(schedule.get("items", [])),
        "attempted_calls": len(rows),
        "successful_calls": sum(row["success"] for row in rows),
        "failed_calls": sum(not row["success"] for row in rows),
        "total_tokens": sum(row["total_tokens"] for row in rows),
        "manual_review_status": "pending",
        "manual_review_item_count": sum(len(row["manual_review_items"]) for row in rows),
        "claim_eligible": False,
        "grouped_cells": grouped,
        "rows": sorted(rows, key=lambda item: item["run_id"]),
        "claim_boundary": (
            "Automatic confirmation evidence alone does not establish superiority. A scoped planning claim "
            "requires the frozen two-reviewer blinded run-level manual metric and independent adjudication."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, report)
    return report


def _group(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["case_id"], row["knowledge_condition"])].append(row)
    result = []
    for (case_id, condition), items in sorted(groups.items()):
        result.append(
            {
                "case_id": case_id,
                "knowledge_condition": condition,
                "calls": len(items),
                "successful_calls": sum(item["success"] for item in items),
                "mean_automatic_score": _mean(item["automatic_score"] for item in items),
                "min_automatic_score": min(
                    (item["automatic_score"] for item in items), default=0
                ),
                "mean_tokens": _mean(item["total_tokens"] for item in items),
                "mean_latency_ms": _mean(item["latency_ms"] for item in items),
                "grounding_failures": sum(not item["grounding_pass"] for item in items),
                "failed_checks": sorted(
                    {check for item in items for check in item["failed_checks"]}
                ),
                "distinct_structure_signatures": len(
                    {item["structural_signature"] for item in items}
                ),
            }
        )
    return result


def _finish_reason(raw_response: Any) -> str | None:
    if not isinstance(raw_response, dict):
        return None
    choices = raw_response.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    return choices[0].get("finish_reason")


def _parse_raw_response(raw_response: Any) -> Any:
    if isinstance(raw_response, dict):
        return raw_response
    if isinstance(raw_response, str):
        try:
            parsed = json.loads(raw_response)
        except json.JSONDecodeError:
            return None
        return parsed
    return None


def _has_response_envelope(raw_response: Any) -> bool:
    if not isinstance(raw_response, dict):
        return False
    choices = raw_response.get("choices")
    return isinstance(choices, list) and bool(choices) and isinstance(choices[0], dict)


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


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze the independent 27-call method B confirmation batch."
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = analyze_confirmation(
        root=args.root,
        manifest_path=args.manifest,
        output=args.output,
    )
    return 0 if report["automatic_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
