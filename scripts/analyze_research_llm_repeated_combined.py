from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.analyze_research_llm_repeated_formal import (
    _cell_stability,
    _complete_cell_grid,
    _file_hash,
    _group_metrics,
    _semantic_hash,
    analyze_repeated_formal,
)
from scripts.freeze_research_repeated_extension_protocol import (
    BASE_PROTOCOL_ID,
    COMBINED_PROTOCOL_ID,
    EXPECTED_CALL_COUNT,
    EXTENSION_REPLICATES,
    PROTOCOL_ID,
    verify_base_evidence_binding,
)


def analyze_repeated_combined(base_root: Path, extension_root: Path) -> dict[str, Any]:
    base_audit_path = base_root / "formal_automatic_audit.json"
    extension_audit_path = extension_root / "formal_automatic_audit.json"
    base_audit = _read_json(base_audit_path)
    recorded_extension_audit = _read_json(extension_audit_path)
    extension_protocol = _read_json(extension_root / "formal_protocol.json")
    base_binding = _read_json(extension_root / "base_evidence_binding.json")
    base_binding_report = verify_base_evidence_binding(base_binding, base_root)
    computed_extension_audit = analyze_repeated_formal(
        extension_root,
        expected_protocol_id=PROTOCOL_ID,
        expected_call_count=EXPECTED_CALL_COUNT,
        expected_replicates=set(EXTENSION_REPLICATES),
        evaluate_extension_gate=False,
    )
    base_rows = base_audit.get("runs", [])
    extension_rows = recorded_extension_audit.get("runs", [])
    rows = base_rows + extension_rows
    base_run_ids = {row["run_id"] for row in base_rows}
    run_ids = [row["run_id"] for row in rows]
    raw_by_id = _load_raw_results(base_root, base_rows) | _load_raw_results(
        extension_root, extension_rows
    )
    integrity_checks = {
        "base_binding_valid": base_binding_report["passed"],
        "base_protocol_expected": base_audit.get("protocol_id") == BASE_PROTOCOL_ID,
        "base_audit_complete": base_audit.get("evidence_integrity_valid") is True
        and base_audit.get("formal_execution_complete") is True
        and base_audit.get("scheduled_call_count") == 54,
        "base_audit_hash_bound": _file_hash(base_audit_path)
        == base_binding.get("formal_automatic_audit_sha256"),
        "extension_protocol_expected": extension_protocol.get("protocol_id") == PROTOCOL_ID
        and extension_protocol.get("combined_protocol_id") == COMBINED_PROTOCOL_ID,
        "extension_audit_complete": recorded_extension_audit.get("protocol_id") == PROTOCOL_ID
        and recorded_extension_audit.get("evidence_integrity_valid") is True
        and recorded_extension_audit.get("formal_execution_complete") is True
        and recorded_extension_audit.get("scheduled_call_count") == EXPECTED_CALL_COUNT,
        "extension_audit_reproducible": _semantic_hash(recorded_extension_audit)
        == _semantic_hash(computed_extension_audit),
        "model_identity_matches": base_audit.get("model")
        == recorded_extension_audit.get("model")
        == extension_protocol["provider"]["required_response_model_exact_match"]
        and base_audit.get("model_revision")
        == recorded_extension_audit.get("model_revision")
        == extension_protocol["provider"]["model_revision"],
        "run_ids_unique": len(run_ids) == len(set(run_ids)) == 90,
        "raw_results_complete": set(raw_by_id) == set(run_ids) and len(raw_by_id) == 90,
        "combined_cell_grid_complete": _complete_cell_grid(rows, {1, 2, 3, 4, 5}),
        "base_replicates_exact": _replicates(base_rows) == {1, 2, 3},
        "extension_replicates_exact": _replicates(extension_rows) == set(EXTENSION_REPLICATES),
        "full_grid_extension_fulfilled": extension_protocol["design"].get("extension_scope")
        == "all_cases_and_all_llm_conditions"
        and extension_protocol["design"].get("selective_reruns_allowed") is False
        and extension_protocol["design"].get("target_repetitions") == 5,
        "prior_v2_excluded": extension_protocol["design"].get(
            "prior_incomplete_v2_results_may_be_pooled"
        )
        is False,
    }
    evidence_integrity_valid = all(integrity_checks.values())
    failed_automatic = [
        {"run_id": row["run_id"], "check_id": check["check_id"], "details": check["details"]}
        for row in rows
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
        for row in rows
        for item in row["evaluation"]["manual_review_items"]
    ]
    return {
        "report_type": "planning_only_repeated_combined_five_repetition_automatic_audit",
        "protocol_id": COMBINED_PROTOCOL_ID,
        "source_protocol_ids": [BASE_PROTOCOL_ID, PROTOCOL_ID],
        "model": extension_protocol["provider"]["required_response_model_exact_match"],
        "model_revision": extension_protocol["provider"]["model_revision"],
        "evidence_manifest": {
            "base_root": str(base_root.resolve()),
            "extension_root": str(extension_root.resolve()),
            "base_audit": _profile(base_audit_path),
            "extension_audit": _profile(extension_audit_path),
            "base_binding": _profile(extension_root / "base_evidence_binding.json"),
            "base_result_manifest_sha256": base_binding["result_index_sha256"],
            "extension_result_manifest_sha256": recorded_extension_audit["evidence_manifest"]
            and _semantic_hash(recorded_extension_audit["evidence_manifest"]["result_files"]),
            "analyzer_source": _profile(Path(__file__)),
        },
        "evidence_integrity_checks": integrity_checks,
        "base_evidence_checks": base_binding_report,
        "evidence_integrity_valid": evidence_integrity_valid,
        "completion_checks": {
            "all_90_runs_present": len(rows) == 90,
            "all_18_cells_have_five_repetitions": _complete_cell_grid(
                rows, {1, 2, 3, 4, 5}
            ),
            "source_batches_complete": base_audit.get("formal_execution_complete") is True
            and recorded_extension_audit.get("formal_execution_complete") is True,
        },
        "formal_execution_complete": evidence_integrity_valid and len(rows) == 90,
        "scheduled_call_count": 90,
        "attempted_call_count": len(rows),
        "successful_calls": sum(row["success"] for row in rows),
        "failed_calls": sum(not row["success"] for row in rows),
        "failure_counts": _failure_counts(rows),
        "total_tokens": sum(row["total_tokens"] for row in rows),
        "automatic_evaluation_complete": len(rows) == 90,
        "automatic_all_checks_passed": not failed_automatic,
        "failed_automatic_check_count": len(failed_automatic),
        "failed_automatic_checks": failed_automatic,
        "manual_review_status": "pending",
        "manual_review_item_count": len(manual_items),
        "manual_review_items": manual_items,
        "comparative_claim_ready": False,
        "group_metrics": _group_metrics(rows, raw_by_id),
        "cell_stability": _cell_stability(rows),
        "extension_gate": {
            "status": "fulfilled" if evidence_integrity_valid and len(rows) == 90 else "incomplete",
            "base_repetitions": 3,
            "extension_repetitions": 2,
            "target_repetitions": 5,
            "scope": "all_cases_and_all_llm_conditions",
            "selective_reruns_allowed": False,
            "further_automatic_extension_registered": False,
        },
        "run_sources": [
            {
                "run_id": row["run_id"],
                "source_protocol_id": (
                    BASE_PROTOCOL_ID if row["run_id"] in base_run_ids else PROTOCOL_ID
                ),
            }
            for row in rows
        ],
        "runs": rows,
        "claim_boundary": (
            "The 90-run analysis combines only the immutable v3 repetitions 1-3 and the bound full-grid "
            "extension repetitions 4-5. The incomplete v2 batch is excluded. Completion, stability, and "
            "automatic scores do not establish superiority; blinded human review and deterministic comparison "
            "remain required."
        ),
    }


def _load_raw_results(root: Path, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        row["run_id"]: _read_json(root / "runs" / row["run_id"] / "result.json")
        for row in rows
    }


def _replicates(rows: list[dict[str, Any]]) -> set[int]:
    return {row["replicate"] for row in rows}


def _failure_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        if row.get("failure_class"):
            key = str(row["failure_class"])
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _profile(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "size_bytes": path.stat().st_size,
        "sha256": _file_hash(path),
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the combined v3 plus full-grid extension evidence.")
    parser.add_argument("--base-root", type=Path, required=True)
    parser.add_argument("--extension-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError(f"Refusing to overwrite combined repeated audit: {args.output}")
    report = analyze_repeated_combined(args.base_root, args.extension_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0 if report["formal_execution_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
