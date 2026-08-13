from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from schemas.research_case_manifest import load_research_case_manifest
from schemas.research_llm_pilot import ResearchPlanningDecision
from services.research_plan_evaluation import EVALUATOR_ID, evaluate_research_plan


LEAKAGE_KEYS = {
    "expected_consequence",
    "expected_outcome_classes",
    "gold_rubric",
    "quality_policy_id",
    "semantic_guard",
    "unsupported_terms",
}

DEFAULT_MANIFEST = Path(__file__).parents[1] / "docs" / "current" / "research-case-manifest-v1.json"


def analyze_pilot(root: Path, *, manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    schedule = json.loads((root / "schedule.json").read_text(encoding="utf-8"))
    prepared = json.loads((root / "prepared_inputs.json").read_text(encoding="utf-8"))
    manifest = load_research_case_manifest(manifest_path)
    cases_by_id = {case.case_id: case for case in manifest.cases}
    schedule_by_run = {item["run_id"]: item for item in schedule["items"]}
    prepared_by_run = {item["schedule"]["run_id"]: item for item in prepared}
    results = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((root / "runs").glob("*/result.json"))
    ]

    rows: list[dict[str, Any]] = []
    leakage: list[dict[str, Any]] = []
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        run_id = result["run_id"]
        item = schedule_by_run[run_id]
        projection = prepared_by_run[run_id]
        attempt = result.get("attempt") or {}
        raw = _raw_payload(attempt.get("raw_response"))
        usage = attempt.get("usage") if isinstance(attempt.get("usage"), dict) else raw.get("usage")
        response_model = attempt.get("response_model") or raw.get("model")
        finish_reason = attempt.get("finish_reason") or _first_choice(raw).get("finish_reason")
        allowed_strings = set(_strings(projection["payload"]))
        refs = _plan_refs(result.get("plan"))
        plan = result.get("plan") if isinstance(result.get("plan"), dict) else None
        validated_plan = None
        validation_failure = result.get("failure_class")
        if plan is not None:
            try:
                validated_plan = ResearchPlanningDecision.model_validate(plan)
            except ValidationError:
                validation_failure = validation_failure or "schema_validation_error"
        evaluation = evaluate_research_plan(
            cases_by_id[item["case_id"]],
            validated_plan,
            allowed_strings=allowed_strings,
            failure_class=validation_failure,
        )
        row = {
            "run_id": run_id,
            "case_id": item["case_id"],
            "knowledge_condition": item["knowledge_condition"],
            "replicate": item["replicate"],
            "success": result.get("success") is True,
            "failure_class": result.get("failure_class"),
            "response_model": response_model,
            "http_status": attempt.get("http_status"),
            "finish_reason": finish_reason,
            "total_tokens": _total_tokens(usage),
            "ungrounded_refs": sorted(set(refs) - allowed_strings),
            "decision": plan.get("decision") if plan else None,
            "task_order": [task.get("task_kind") for task in plan.get("tasks", [])] if plan else None,
            "structural_signature": _structural_signature(plan),
            "evaluation": evaluation.model_dump(mode="json"),
        }
        rows.append(row)
        groups[(item["case_id"], item["knowledge_condition"])].append(row)
        for path, value in _key_occurrences(projection["payload"], LEAKAGE_KEYS):
            leakage.append({"run_id": run_id, "path": path, "value": value})

    grouped = []
    for (case_id, condition), items in sorted(groups.items()):
        successful = [item for item in items if item["success"]]
        grouped.append(
            {
                "case_id": case_id,
                "knowledge_condition": condition,
                "calls": len(items),
                "successful_calls": len(successful),
                "failed_calls": len(items) - len(successful),
                "tokens": sum(item["total_tokens"] for item in items),
                "decision_and_task_order_stable": len(successful) == len(items)
                and len({(item["decision"], tuple(item["task_order"] or [])) for item in successful}) == 1,
                "exact_structure_stable": len(successful) == len(items)
                and len({item["structural_signature"] for item in successful}) == 1,
            }
        )

    failure_counts = Counter(str(row["failure_class"]) for row in rows if row["failure_class"])
    blockers = []
    if leakage:
        blockers.append("evaluation_or_policy_hints_are_visible_to_llm_inputs")
    if any(row["finish_reason"] == "length" for row in rows):
        blockers.append("max_output_tokens_insufficient_for_all_pilot_inputs")
    if any(
        not check["passed"]
        for row in rows
        for check in row["evaluation"]["automatic_checks"]
    ):
        blockers.append("pilot_automatic_rubric_checks_failed")
    blockers.append("formal_protocol_and_evaluator_hash_not_frozen")
    return {
        "diagnostic_only": True,
        "input_leakage": bool(leakage),
        "claim_eligible": False,
        "evaluator_id": EVALUATOR_ID,
        "pilot_root": str(root.resolve()),
        "call_count": len(rows),
        "successful_calls": sum(row["success"] for row in rows),
        "failed_calls": sum(not row["success"] for row in rows),
        "failure_counts": dict(sorted(failure_counts.items())),
        "total_tokens": sum(row["total_tokens"] for row in rows),
        "response_models": dict(sorted(Counter(str(row["response_model"]) for row in rows).items())),
        "http_statuses": dict(sorted(Counter(str(row["http_status"]) for row in rows).items())),
        "finish_reasons": dict(sorted(Counter(str(row["finish_reason"]) for row in rows).items())),
        "grounding": {
            "runs_with_ungrounded_refs": sum(bool(row["ungrounded_refs"]) for row in rows),
            "details": [
                {"run_id": row["run_id"], "ungrounded_refs": row["ungrounded_refs"]}
                for row in rows
                if row["ungrounded_refs"]
            ],
        },
        "input_leakage_audit": {
            "affected_runs": len({item["run_id"] for item in leakage}),
            "keys": sorted({item["path"].split(".")[-1] for item in leakage}),
            "details": leakage,
        },
        "group_stability": grouped,
        "formal_ready": False,
        "formal_blockers": blockers,
        "parameter_observation": {
            "pilot_max_output_tokens": 8192,
            "candidate_max_output_tokens": 16384,
            "candidate_value_is_frozen": False,
            "same_18_call_conservative_bound_at_candidate": 549950,
            "minimum_candidate_batch_budget": 600000,
            "reason": "two C06 knowledge-augmented runs exhausted 8192 reasoning tokens with empty content",
        },
        "runs": rows,
    }


def _raw_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, str):
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _first_choice(payload: dict[str, Any]) -> dict[str, Any]:
    choices = payload.get("choices")
    return choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}


def _total_tokens(usage: Any) -> int:
    if not isinstance(usage, dict):
        return 0
    value = usage.get("total_tokens")
    return value if isinstance(value, int) and value >= 0 else 0


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


def _plan_refs(plan: Any) -> list[str]:
    if not isinstance(plan, dict):
        return []
    refs = []
    for task in plan.get("tasks", []):
        if not isinstance(task, dict):
            continue
        refs.extend(str(value) for value in task.get("source_ids", []))
        if task.get("algorithm_id"):
            refs.append(str(task["algorithm_id"]))
    return refs


def _structural_signature(plan: dict[str, Any] | None) -> str | None:
    if plan is None:
        return None
    structure = {
        "decision": plan.get("decision"),
        "tasks": [
            {
                "task_kind": task.get("task_kind"),
                "source_ids": task.get("source_ids", []),
                "algorithm_id": task.get("algorithm_id"),
                "delivery_state": task.get("delivery_state"),
            }
            for task in plan.get("tasks", [])
            if isinstance(task, dict)
        ],
    }
    return json.dumps(structure, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _key_occurrences(value: Any, keys: set[str], prefix: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if key in keys:
                yield path, item
            yield from _key_occurrences(item, keys, path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _key_occurrences(item, keys, f"{prefix}[{index}]")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a completed real-LLM research pilot.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    report = analyze_pilot(args.root, manifest_path=args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
