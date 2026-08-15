from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.analyze_research_llm_pilot import analyze_pilot


PROTOCOL_ID = "fusionagent.planning-repeated-formal.v2"
EXPECTED_CALL_COUNT = 54
EXPECTED_REPLICATES = {1, 2, 3}


def analyze_repeated_formal(
    root: Path,
    *,
    expected_protocol_id: str = PROTOCOL_ID,
    expected_call_count: int = EXPECTED_CALL_COUNT,
    expected_replicates: set[int] | frozenset[int] = frozenset(EXPECTED_REPLICATES),
    evaluate_extension_gate: bool = True,
) -> dict[str, Any]:
    protocol = _read_json(root / "formal_protocol.json")
    freeze_audit = _read_json(root / "freeze_audit.json")
    execution = _read_json(root / "execution_config.json")
    identity = _read_json(root / "execution_identity.json")
    summary = _read_json(root / "formal_summary.json")
    revision_evidence = _read_json(root / "model_revision_evidence.json")
    base_binding_path = root / "base_evidence_binding.json"
    base_binding = _read_json(base_binding_path) if base_binding_path.exists() else None
    schedule = _read_json(root / "schedule.json")
    prepared = _read_json(root / "prepared_inputs.json")
    base = analyze_pilot(root)

    schedule_items = schedule["items"]
    schedule_ids = [item["run_id"] for item in schedule_items]
    result_paths = sorted((root / "runs").glob("*/result.json"))
    raw_results = [_read_json(path) for path in result_paths]
    raw_by_id = {item["run_id"]: item for item in raw_results}
    result_ids = set(raw_by_id)
    prepared_by_id = {item["schedule"]["run_id"]: item for item in prepared}
    attempted_count = len(raw_results)
    attempted_prefix = set(schedule_ids[:attempted_count])
    expected_model = protocol["provider"]["required_response_model_exact_match"]
    observed_tokens = sum(_attempt_total_tokens(item.get("attempt")) for item in raw_results)

    integrity_checks = {
        "freeze_audit_passed": freeze_audit.get("passed") is True,
        "freeze_audit_checks_all_true": bool(freeze_audit.get("checks"))
        and all(freeze_audit["checks"].values()),
        "formal_protocol_ready": protocol.get("formal_ready") is True
        and protocol.get("protocol_status") == "frozen",
        "protocol_id_match": (
            protocol.get("protocol_id") == execution.get("protocol_id") == expected_protocol_id
        ),
        "schedule_protocol_id_match": schedule.get("protocol_id") == expected_protocol_id,
        "model_revision_match": execution.get("model_revision")
        == protocol["provider"].get("model_revision"),
        "copied_schedule_hash_matches_protocol": (
            protocol["identities"]["schedule_sha256"] == _semantic_hash(schedule)
        ),
        "copied_prepared_inputs_hash_matches_protocol": (
            protocol["identities"]["prepared_inputs_sha256"] == _semantic_hash(prepared)
        ),
        "copied_model_revision_evidence_hash_matches_protocol": (
            protocol["provider"]["model_revision_evidence_sha256"]
            == _semantic_hash(revision_evidence)
        ),
        "execution_provider_matches_protocol": execution.get("requested_model")
        == protocol["provider"]["requested_model"]
        and execution.get("base_url_host") == protocol["provider"]["base_url_host"],
        "execution_generation_matches_protocol": execution.get("temperature")
        == protocol["generation"]["temperature"]
        and execution.get("response_format") == protocol["generation"]["response_format"]
        and execution.get("max_output_tokens") == protocol["generation"]["max_output_tokens"]
        and execution.get("token_budget") == protocol["budget"]["batch_token_budget"]
        and execution.get("transport_retries") == protocol["generation"]["transport_retries"]
        and execution.get("semantic_repairs") == protocol["generation"]["semantic_repairs"]
        and execution.get("json_salvage") == protocol["generation"]["json_salvage"]
        and execution.get("fallback") == protocol["generation"]["fallback"],
        "execution_timeout_matches_protocol": (
            "request_timeout_seconds" not in protocol["generation"]
            or execution.get("request_timeout_seconds")
            == protocol["generation"]["request_timeout_seconds"]
        ),
        "old_v1_pooling_forbidden": protocol["design"].get("old_v1_results_may_be_pooled")
        is False,
        "execution_identity_matches": identity.get("protocol_id") == expected_protocol_id
        and identity.get("frozen_implementation_commit") == protocol.get("implementation_commit")
        and identity.get("execution_commit_descends_from_frozen_implementation") is True
        and identity.get("worktree_clean_at_start") is True
        and identity.get("execute_provider_calls") is True,
        "schedule_count_and_ids_unique": len(schedule_ids) == expected_call_count
        and len(set(schedule_ids)) == expected_call_count,
        "prepared_inputs_match_schedule": set(prepared_by_id) == set(schedule_ids)
        and len(prepared) == expected_call_count,
        "result_run_ids_unique": len(raw_by_id) == len(raw_results),
        "attempted_results_form_schedule_prefix": result_ids == attempted_prefix,
        "result_input_hashes_match_frozen_inputs": all(
            run_id in prepared_by_id
            and item.get("input_hash") == prepared_by_id[run_id].get("input_hash")
            for run_id, item in raw_by_id.items()
        ),
        "successful_response_models_match": all(
            (item.get("attempt") or {}).get("response_model") == expected_model
            for item in raw_results
            if item.get("success") is True
        ),
        "successful_results_are_strict_json": all(
            (item.get("attempt") or {}).get("parse_mode") == "strict_json"
            for item in raw_results
            if item.get("success") is True
        ),
        "successful_results_retain_raw_response": all(
            isinstance((item.get("attempt") or {}).get("raw_response"), str)
            and bool((item.get("attempt") or {}).get("raw_response"))
            for item in raw_results
            if item.get("success") is True
        ),
        "transport_retries_zero": all(
            (item.get("attempt") or {}).get("transport_retry_count", 0) == 0
            for item in raw_results
        ),
        "failed_calls_not_replaced": summary.get("failed_calls_replaced") is False,
        "summary_matches_results": summary.get("executed_calls") == attempted_count
        and summary.get("successful_calls") == sum(item.get("success") is True for item in raw_results)
        and summary.get("failed_calls") == sum(item.get("success") is not True for item in raw_results)
        and summary.get("consumed_tokens") == observed_tokens,
        "token_budget_respected": observed_tokens <= protocol["budget"]["batch_token_budget"],
        "input_leakage_zero": base["input_leakage"] is False,
        "base_evidence_binding_matches_protocol": (
            (base_binding is None and "base_evidence" not in protocol)
            or (
                base_binding is not None
                and protocol.get("base_evidence") == base_binding
                and protocol.get("identities", {}).get("base_evidence_binding_sha256")
                == _semantic_hash(base_binding)
                and execution.get("base_audit_sha256")
                == base_binding.get("formal_automatic_audit_sha256")
            )
        ),
    }
    evidence_integrity_valid = all(integrity_checks.values())
    completion_checks = {
        "all_scheduled_runs_attempted": attempted_count == expected_call_count
        and result_ids == set(schedule_ids),
        "summary_scheduled_count": summary.get("scheduled_calls") == expected_call_count,
        "all_case_condition_replicates_present": _complete_cell_grid(
            base["runs"], expected_replicates
        ),
    }
    formal_execution_complete = evidence_integrity_valid and all(completion_checks.values())

    cells = _cell_stability(base["runs"])
    extension_reasons = (
        _extension_reasons(cells)
        if formal_execution_complete and evaluate_extension_gate
        else []
    )
    if evaluate_extension_gate:
        extension_gate = {
            "status": "evaluated" if formal_execution_complete else "not_evaluable_batch_incomplete",
            "extension_required": bool(extension_reasons) if formal_execution_complete else None,
            "target_repetitions": (5 if extension_reasons else 3) if formal_execution_complete else None,
            "scope": "all_cases_and_all_llm_conditions" if extension_reasons else None,
            "reasons": extension_reasons,
            "selective_reruns_allowed": False,
        }
    else:
        extension_gate = {
            "status": "not_applicable_extension_batch",
            "extension_required": False,
            "target_repetitions": max(expected_replicates),
            "scope": None,
            "reasons": [],
            "selective_reruns_allowed": False,
        }
    failed_automatic = [
        {"run_id": row["run_id"], "check_id": check["check_id"], "details": check["details"]}
        for row in base["runs"]
        for check in row["evaluation"]["automatic_checks"]
        if not check["passed"]
    ]
    manual_items = [
        {
            "run_id": row["run_id"],
            "case_id": row["case_id"],
            "knowledge_condition": row["knowledge_condition"],
            "replicate": row["replicate"],
            **item,
        }
        for row in base["runs"]
        for item in row["evaluation"]["manual_review_items"]
    ]
    return {
        "report_type": "planning_only_repeated_formal_automatic_audit",
        "protocol_id": expected_protocol_id,
        "model": expected_model,
        "model_revision": protocol["provider"]["model_revision"],
        "evidence_manifest": _evidence_manifest(root, result_paths),
        "evidence_integrity_checks": integrity_checks,
        "evidence_integrity_valid": evidence_integrity_valid,
        "completion_checks": completion_checks,
        "formal_execution_complete": formal_execution_complete,
        "attempted_call_count": attempted_count,
        "scheduled_call_count": expected_call_count,
        "successful_calls": base["successful_calls"],
        "failed_calls": base["failed_calls"],
        "failure_counts": base["failure_counts"],
        "total_tokens": observed_tokens,
        "automatic_evaluation_complete": attempted_count == len(base["runs"]),
        "automatic_all_checks_passed": not failed_automatic,
        "failed_automatic_check_count": len(failed_automatic),
        "failed_automatic_checks": failed_automatic,
        "manual_review_status": "pending",
        "manual_review_item_count": len(manual_items),
        "manual_review_items": manual_items,
        "comparative_claim_ready": False,
        "group_metrics": _group_metrics(base["runs"], raw_by_id),
        "cell_stability": cells,
        "extension_gate": extension_gate,
        "runs": base["runs"],
        "claim_boundary": (
            "Formal completion and evidence integrity do not imply superiority. Automatic failures are retained "
            "as outcomes; manual review, deterministic comparison, and bounded claim audit remain required."
        ),
    }


def _complete_cell_grid(
    rows: list[dict[str, Any]],
    expected_replicates: set[int] | frozenset[int] = frozenset(EXPECTED_REPLICATES),
) -> bool:
    grouped: dict[tuple[str, str], set[int]] = defaultdict(set)
    for row in rows:
        grouped[(row["case_id"], row["knowledge_condition"])].add(row["replicate"])
    return len(grouped) == 18 and all(
        replicates == set(expected_replicates) for replicates in grouped.values()
    )


def _cell_stability(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["case_id"], row["knowledge_condition"])].append(row)
    cells = []
    for (case_id, condition), items in sorted(grouped.items()):
        successful = [item for item in items if item["success"]]
        scores = [item["evaluation"]["automatic_score"] for item in items]
        structures = {
            _signature_hash(item["structural_signature"])
            for item in successful
            if item["structural_signature"] is not None
        }
        decision_order = {
            json.dumps(
                {"decision": item["decision"], "task_order": item["task_order"]},
                sort_keys=True,
                separators=(",", ":"),
            )
            for item in successful
        }
        cells.append(
            {
                "case_id": case_id,
                "knowledge_condition": condition,
                "replicates_observed": sorted(item["replicate"] for item in items),
                "calls": len(items),
                "successful_calls": len(successful),
                "failed_calls": len(items) - len(successful),
                "failure_classes": dict(
                    sorted(Counter(str(item["failure_class"]) for item in items if item["failure_class"]).items())
                ),
                "distinct_plan_structure_signatures": len(structures),
                "plan_structure_signature_hashes": sorted(structures),
                "distinct_decision_task_order_signatures": len(decision_order),
                "automatic_score_min": min(scores) if scores else None,
                "automatic_score_max": max(scores) if scores else None,
                "automatic_score_range": round(max(scores) - min(scores), 6) if scores else None,
                "automatic_score_mean": round(statistics.fmean(scores), 6) if scores else None,
            }
        )
    return cells


def _extension_reasons(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reasons = []
    for cell in cells:
        identity = {
            "case_id": cell["case_id"],
            "knowledge_condition": cell["knowledge_condition"],
        }
        if cell["failed_calls"]:
            reasons.append({**identity, "trigger": "observed_provider_or_schema_failure"})
        if cell["distinct_plan_structure_signatures"] > 1:
            reasons.append({**identity, "trigger": "multiple_plan_structure_signatures"})
        if (cell["automatic_score_range"] or 0.0) >= 0.25:
            reasons.append(
                {
                    **identity,
                    "trigger": "automatic_score_range_gte_0.25",
                    "value": cell["automatic_score_range"],
                }
            )
    return reasons


def _group_metrics(
    rows: list[dict[str, Any]],
    raw_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["knowledge_condition"]].append(row)
    metrics = []
    for condition, items in sorted(grouped.items()):
        positive = [row for row in items if row["case_id"] != "C03"]
        latencies = [
            int((raw_by_id[row["run_id"]].get("attempt") or {}).get("latency_ms", 0))
            for row in items
            if isinstance((raw_by_id[row["run_id"]].get("attempt") or {}).get("latency_ms"), int)
        ]
        metrics.append(
            {
                "knowledge_condition": condition,
                "calls": len(items),
                "successful_calls": sum(row["success"] for row in items),
                "failed_calls": sum(not row["success"] for row in items),
                "mean_automatic_score_all_runs": _mean_score(items),
                "mean_automatic_score_positive_runs": _mean_score(positive),
                "runs_all_automatic_checks_passed": sum(
                    all(check["passed"] for check in row["evaluation"]["automatic_checks"])
                    for row in items
                ),
                "negative_control_runs_all_checks_passed": sum(
                    all(check["passed"] for check in row["evaluation"]["automatic_checks"])
                    for row in items
                    if row["case_id"] == "C03"
                ),
                "tokens": sum(row["total_tokens"] for row in items),
                "mean_latency_ms": round(statistics.fmean(latencies), 3) if latencies else None,
            }
        )
    return metrics


def _mean_score(rows: list[dict[str, Any]]) -> float | None:
    if not rows:
        return None
    return round(statistics.fmean(row["evaluation"]["automatic_score"] for row in rows), 6)


def _signature_hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _evidence_manifest(root: Path, result_paths: list[Path]) -> dict[str, Any]:
    fixed_files = [
        "formal_protocol.json",
        "freeze_audit.json",
        "schedule.json",
        "prepared_inputs.json",
        "model_revision_evidence.json",
        "execution_config.json",
        "execution_identity.json",
        "formal_summary.json",
    ]
    if (root / "base_evidence_binding.json").exists():
        fixed_files.append("base_evidence_binding.json")
    return {
        "root": str(root.resolve()),
        "fixed_files": [_file_profile(root / name) for name in fixed_files],
        "result_files": [
            {"run_id": path.parent.name, **_file_profile(path)} for path in result_paths
        ],
        "analyzer_source": _file_profile(Path(__file__)),
    }


def _file_profile(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "size_bytes": path.stat().st_size,
        "sha256": _file_hash(path),
    }


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _semantic_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _attempt_total_tokens(attempt: Any) -> int:
    if not isinstance(attempt, dict):
        return 0
    usage = attempt.get("usage")
    if not isinstance(usage, dict):
        return 0
    value = usage.get("total_tokens")
    return value if isinstance(value, int) and value >= 0 else 0


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a completed 54-call repeated planning batch.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-protocol-id", default=PROTOCOL_ID)
    parser.add_argument("--expected-call-count", type=int, default=EXPECTED_CALL_COUNT)
    parser.add_argument("--expected-replicates", default="1,2,3")
    parser.add_argument("--skip-extension-gate", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError(f"Refusing to overwrite repeated formal audit: {args.output}")
    report = analyze_repeated_formal(
        args.root,
        expected_protocol_id=args.expected_protocol_id,
        expected_call_count=args.expected_call_count,
        expected_replicates={int(value) for value in args.expected_replicates.split(",")},
        evaluate_extension_gate=not args.skip_extension_gate,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0 if report["formal_execution_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
