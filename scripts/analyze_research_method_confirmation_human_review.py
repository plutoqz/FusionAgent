from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROTOCOL_ID = "fusionagent.method-b-independent-confirmation.v1"
METRIC_ID = "blinded_manual_run_pass_rate.v1"
METHOD_B_CONDITION = "task_conditioned_contract_aware_kg"
LLM_ONLY_CONDITION = "llm_only"
FULL_KG_CONDITION = "llm_full_contract_kg"
EXPECTED_CASES = ("H07", "H08", "H09")
EXPECTED_CONDITIONS = (
    METHOD_B_CONDITION,
    LLM_ONLY_CONDITION,
    FULL_KG_CONDITION,
)
ALLOWED_DECISIONS = {"pass", "fail", "not_assessable"}


def analyze_confirmation_human_review(
    *,
    automatic_analysis_path: Path,
    review_root: Path,
    output: Path,
    adjudication_root: Path | None = None,
) -> dict[str, Any]:
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite confirmation human analysis: {output}")

    automatic = _read_json(automatic_analysis_path)
    evidence_root = Path(automatic["evidence_root"])
    protocol_path = evidence_root / "formal_protocol.json"
    protocol = _read_json(protocol_path)
    packet_manifest_path = review_root / "packet-manifest.json"
    blind_key_path = review_root / "blind-key.json"
    agreement_path = review_root / "manual-review-agreement-audit.json"
    reviewer_a_path = review_root / "reviewer-a.decisions.json"
    reviewer_b_path = review_root / "reviewer-b.decisions.json"
    packet_manifest = _read_json(packet_manifest_path)
    blind_key = _read_json(blind_key_path)
    agreement = _read_json(agreement_path)

    mapping = blind_key.get("mapping", [])
    mapping_by_id = {item.get("packet_item_id"): item for item in mapping}
    automatic_rows = automatic.get("rows", [])
    automatic_by_run = {item.get("run_id"): item for item in automatic_rows}
    expected_cells = {
        (case_id, condition, replicate)
        for case_id in EXPECTED_CASES
        for condition in EXPECTED_CONDITIONS
        for replicate in (1, 2, 3)
    }
    automatic_cells = {
        (
            item.get("case_id"),
            item.get("knowledge_condition"),
            item.get("replicate"),
        )
        for item in automatic_rows
    }
    expected_manual_pairs = {
        (row.get("run_id"), item.get("item_id"))
        for row in automatic_rows
        for item in row.get("manual_review_items", [])
    }
    mapped_manual_pairs = {
        (item.get("run_id"), item.get("rubric_item_id")) for item in mapping
    }
    agreement_checks = agreement.get("checks", {})
    agreement_integrity_checks = {
        key: value
        for key, value in agreement_checks.items()
        if key != "no_unresolved_disagreements"
    }
    checks = {
        "protocol_id_frozen": protocol.get("protocol_id") == PROTOCOL_ID
        and protocol.get("protocol_status") == "frozen",
        "primary_metric_frozen": protocol.get("primary_metric", {}).get("metric_id")
        == METRIC_ID,
        "automatic_protocol_bound": automatic.get("protocol_id") == PROTOCOL_ID,
        "automatic_evidence_integrity_valid": automatic.get("evidence_integrity_valid")
        is True,
        "automatic_execution_complete": automatic.get("formal_execution_complete") is True,
        "packet_source_automatic_bound": packet_manifest.get("source_audit_sha256")
        == _file_hash(automatic_analysis_path),
        "blind_key_source_automatic_bound": blind_key.get("source_audit_sha256")
        == _file_hash(automatic_analysis_path),
        "packet_ids_bound": packet_manifest.get("packet_id") == blind_key.get("packet_id")
        == agreement.get("packet_id"),
        "agreement_packet_manifest_bound": agreement.get(
            "source_packet_manifest", {}
        ).get("sha256")
        == _file_hash(packet_manifest_path),
        "agreement_integrity_complete": bool(agreement_integrity_checks)
        and all(agreement_integrity_checks.values()),
        "automatic_run_grid": len(automatic_by_run) == len(automatic_rows) == 27,
        "automatic_cell_grid_matches_protocol": automatic_cells == expected_cells,
        "automatic_manual_rubrics_match_protocol": all(
            row.get("case_id") in protocol.get("manual_review", {}).get("rubric", {})
            and {
                item.get("item_id") for item in row.get("manual_review_items", [])
            }
            == set(
                protocol["manual_review"]["rubric"][row["case_id"]]
            )
            for row in automatic_rows
        ),
        "blind_mapping_unique": len(mapping_by_id) == len(mapping) == 63,
        "blind_mapping_matches_automatic_rubric": mapped_manual_pairs
        == expected_manual_pairs,
        "blind_mapping_run_metadata_matches": all(
            item.get("run_id") in automatic_by_run
            and item.get("case_id") == automatic_by_run[item["run_id"]].get("case_id")
            and item.get("knowledge_condition")
            == automatic_by_run[item["run_id"]].get("knowledge_condition")
            and item.get("replicate")
            == automatic_by_run[item["run_id"]].get("replicate")
            for item in mapping
        ),
    }

    final_records, resolution, resolution_checks, source_files = _resolve_final_records(
        review_root=review_root,
        agreement=agreement,
        agreement_path=agreement_path,
        reviewer_a_path=reviewer_a_path,
        reviewer_b_path=reviewer_b_path,
        adjudication_root=adjudication_root,
        expected_packet_id=packet_manifest.get("packet_id"),
    )
    checks.update(resolution_checks)
    final_by_id = {item.get("packet_item_id"): item for item in final_records}
    checks.update(
        {
            "final_decision_ids_unique": len(final_by_id) == len(final_records) == 63,
            "final_decision_set_matches_blind_key": set(final_by_id)
            == set(mapping_by_id),
            "final_decisions_allowed": all(
                item.get("decision") in ALLOWED_DECISIONS
                for item in final_records
            ),
            "final_rubric_ids_match_blind_key": all(
                item_id in mapping_by_id
                and record.get("rubric_item_id")
                == mapping_by_id[item_id].get("rubric_item_id")
                for item_id, record in final_by_id.items()
            ),
        }
    )
    if not all(checks.values()):
        raise RuntimeError(f"Confirmation human-review unblinding gate failed: {checks}")

    metric = evaluate_confirmation_metric(
        automatic_rows=automatic_rows,
        blind_mapping=mapping,
        final_records=final_records,
    )
    automatic_gate_passed = automatic.get("automatic_gate_passed") is True
    claim_evaluable = metric["all_27_runs_final_assessable"]
    claim_supported = (
        automatic_gate_passed
        and claim_evaluable
        and metric["primary_metric_passed"]
    )
    if not claim_evaluable:
        claim_status = "ineligible_not_assessable"
    elif claim_supported:
        claim_status = "passed_scoped_planning_superiority"
    else:
        claim_status = "failed_confirmation_no_superiority_claim"

    report = {
        "report_type": "method_b_independent_confirmation_human_analysis",
        "protocol_id": PROTOCOL_ID,
        "primary_metric_id": METRIC_ID,
        "source_files": {
            "automatic_analysis": _profile(automatic_analysis_path),
            "formal_protocol": _profile(protocol_path),
            "packet_manifest": _profile(packet_manifest_path),
            "blind_key": _profile(blind_key_path),
            "agreement_audit": _profile(agreement_path),
            **source_files,
        },
        "unblinding_gate": checks,
        "resolution": {
            "mode": resolution,
            "agreement": agreement.get("agreement"),
            "disagreement_count": agreement.get("disagreement_count"),
            "adjudicated_item_count": sum(
                item.get("resolution_source") == "independent_adjudicator_c"
                for item in final_records
            ),
        },
        "automatic_gate_passed": automatic_gate_passed,
        **metric,
        "claim_evaluable": claim_evaluable,
        "claim_supported": claim_supported,
        "claim_eligible": claim_supported,
        "claim_status": claim_status,
        "claim": (
            "Under the frozen provider and protocol, method B outperformed LLM-only and Full KG for planning "
            "on the three pre-registered confirmation mechanisms."
            if claim_supported
            else None
        ),
        "claim_boundary": (
            "This is a descriptive bounded planning-method comparison across H07-H09 under the frozen "
            "provider and protocol. It does not establish end-to-end product quality, cross-AOI validity, "
            "provider-independent generality, population-level statistical significance, or universal "
            "superiority. If the claim is not supported, retain H01-H06 only as post-held-out mechanism "
            "support and repair validation."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, report)
    return report


def evaluate_confirmation_metric(
    *,
    automatic_rows: list[dict[str, Any]],
    blind_mapping: list[dict[str, Any]],
    final_records: list[dict[str, Any]],
) -> dict[str, Any]:
    mapping_by_id = {item["packet_item_id"]: item for item in blind_mapping}
    decisions_by_id = {item["packet_item_id"]: item for item in final_records}
    item_rows = []
    for packet_item_id in sorted(mapping_by_id):
        mapping = mapping_by_id[packet_item_id]
        decision = decisions_by_id[packet_item_id]
        item_rows.append(
            {
                "packet_item_id": packet_item_id,
                "run_id": mapping["run_id"],
                "case_id": mapping["case_id"],
                "knowledge_condition": mapping["knowledge_condition"],
                "replicate": mapping["replicate"],
                "rubric_item_id": mapping["rubric_item_id"],
                "decision": decision["decision"],
                "resolution_source": decision.get("resolution_source"),
            }
        )

    by_run_items: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in item_rows:
        by_run_items[row["run_id"]].append(row)
    run_rows = []
    for automatic_row in sorted(automatic_rows, key=lambda item: item["run_id"]):
        items = by_run_items[automatic_row["run_id"]]
        decisions = [item["decision"] for item in items]
        run_rows.append(
            {
                "run_id": automatic_row["run_id"],
                "case_id": automatic_row["case_id"],
                "knowledge_condition": automatic_row["knowledge_condition"],
                "replicate": automatic_row["replicate"],
                "rubric_item_count": len(items),
                "assessable": bool(items)
                and all(decision != "not_assessable" for decision in decisions),
                "run_pass": bool(items)
                and all(decision == "pass" for decision in decisions),
                "item_decisions": {
                    item["rubric_item_id"]: item["decision"] for item in items
                },
            }
        )

    by_condition = _summarize_runs(run_rows, ("knowledge_condition",))
    by_case_condition = _summarize_runs(
        run_rows, ("case_id", "knowledge_condition")
    )
    condition_lookup = {
        row["knowledge_condition"]: row for row in by_condition
    }
    case_condition_lookup = {
        (row["case_id"], row["knowledge_condition"]): row
        for row in by_case_condition
    }
    expected_cells = {
        (case_id, condition, replicate)
        for case_id in EXPECTED_CASES
        for condition in EXPECTED_CONDITIONS
        for replicate in (1, 2, 3)
    }
    actual_cells = {
        (row["case_id"], row["knowledge_condition"], row["replicate"])
        for row in run_rows
    }
    complete_grid = (
        len(run_rows) == 27
        and len(actual_cells) == 27
        and actual_cells == expected_cells
        and {row["case_id"] for row in run_rows} == set(EXPECTED_CASES)
        and {row["knowledge_condition"] for row in run_rows}
        == set(EXPECTED_CONDITIONS)
        and all(row["runs"] == 9 for row in by_condition)
        and all(row["runs"] == 3 for row in by_case_condition)
    )
    b = condition_lookup[METHOD_B_CONDITION]
    llm_only = condition_lookup[LLM_ONLY_CONDITION]
    full_kg = condition_lookup[FULL_KG_CONDITION]
    primary_metric_gates = {
        "b_pass_rate_strictly_above_llm_only": b["pass_rate"]
        > llm_only["pass_rate"],
        "b_pass_rate_strictly_above_full_kg": b["pass_rate"]
        > full_kg["pass_rate"],
        "b_not_below_each_comparator_per_case": all(
            case_condition_lookup[(case_id, METHOD_B_CONDITION)]["passed_runs"]
            >= case_condition_lookup[(case_id, comparator)]["passed_runs"]
            for case_id in EXPECTED_CASES
            for comparator in (LLM_ONLY_CONDITION, FULL_KG_CONDITION)
        ),
        "all_27_runs_final_assessable": complete_grid
        and all(row["assessable"] for row in run_rows),
    }
    decision_counts = Counter(row["decision"] for row in item_rows)
    return {
        "manual_item_count": len(item_rows),
        "manual_item_decision_counts": {
            decision: decision_counts.get(decision, 0)
            for decision in ("pass", "fail", "not_assessable")
        },
        "run_count": len(run_rows),
        "run_grid_complete": complete_grid,
        "all_27_runs_final_assessable": primary_metric_gates[
            "all_27_runs_final_assessable"
        ],
        "primary_metric_gates": primary_metric_gates,
        "primary_metric_passed": complete_grid
        and all(primary_metric_gates.values()),
        "by_condition": by_condition,
        "by_case_condition": by_case_condition,
        "run_rows": run_rows,
        "item_rows": item_rows,
    }


def _resolve_final_records(
    *,
    review_root: Path,
    agreement: dict[str, Any],
    agreement_path: Path,
    reviewer_a_path: Path,
    reviewer_b_path: Path,
    adjudication_root: Path | None,
    expected_packet_id: str | None,
) -> tuple[list[dict[str, Any]], str, dict[str, bool], dict[str, Any]]:
    disagreement_count = agreement.get("disagreement_count")
    if disagreement_count == 0:
        reviewer_a = _read_json(reviewer_a_path)
        reviewer_b = _read_json(reviewer_b_path)
        a_by_id = {
            item.get("packet_item_id"): item for item in reviewer_a.get("records", [])
        }
        b_by_id = {
            item.get("packet_item_id"): item for item in reviewer_b.get("records", [])
        }
        final_records = [
            {
                "packet_item_id": item_id,
                "rubric_item_id": record.get("rubric_item_id"),
                "decision": record.get("decision"),
                "resolution_source": "reviewer_a_b_agreement",
            }
            for item_id, record in sorted(a_by_id.items())
        ]
        checks = {
            "zero_disagreement_agreement_audit_passed": agreement.get("passed") is True,
            "reviewer_files_match_agreement_audit": _reviewer_profiles_match(
                agreement, (reviewer_a_path, reviewer_b_path)
            ),
            "reviewer_final_sets_match": set(a_by_id) == set(b_by_id),
            "reviewer_final_decisions_agree": all(
                item_id in b_by_id
                and record.get("rubric_item_id")
                == b_by_id[item_id].get("rubric_item_id")
                and record.get("decision") == b_by_id[item_id].get("decision")
                for item_id, record in a_by_id.items()
            ),
        }
        return (
            final_records,
            "two_reviewer_consensus_no_adjudication",
            checks,
            {
                "reviewer_a_decisions": _profile(reviewer_a_path),
                "reviewer_b_decisions": _profile(reviewer_b_path),
                "adjudication_manifest": None,
                "adjudication_audit": None,
            },
        )

    if not isinstance(disagreement_count, int) or disagreement_count <= 0:
        raise RuntimeError("Agreement audit has an invalid disagreement count.")
    if adjudication_root is None:
        raise RuntimeError(
            "Frozen reviewer disagreements require --adjudication-root before unblinding."
        )
    manifest_path = adjudication_root / "adjudication-manifest.json"
    audit_path = adjudication_root / "adjudication-audit.json"
    manifest = _read_json(manifest_path)
    audit = _read_json(audit_path)
    checks = {
        "adjudication_audit_passed": audit.get("passed") is True,
        "adjudication_review_packet_bound": manifest.get("source_review_packet_id")
        == expected_packet_id,
        "adjudication_source_agreement_bound": manifest.get(
            "source_agreement_audit", {}
        ).get("sha256")
        == _file_hash(agreement_path),
        "adjudication_audit_agreement_bound": audit.get(
            "source_agreement_audit", {}
        ).get("sha256")
        == _file_hash(agreement_path),
        "adjudication_audit_manifest_bound": audit.get(
            "source_adjudication_manifest", {}
        ).get("sha256")
        == _file_hash(manifest_path),
        "adjudication_reviewer_files_unchanged": _reviewer_profiles_match(
            {"reviewer_files": audit.get("source_reviewer_files", [])},
            (reviewer_a_path, reviewer_b_path),
        ),
        "adjudication_final_count_complete": audit.get("final_item_count") == 63,
        "adjudication_resolves_exact_disagreement_count": audit.get(
            "adjudicated_item_count"
        )
        == disagreement_count,
    }
    return (
        audit.get("final_blinded_decisions", []),
        "independent_third_reviewer_adjudication",
        checks,
        {
            "reviewer_a_decisions": _profile(reviewer_a_path),
            "reviewer_b_decisions": _profile(reviewer_b_path),
            "adjudication_manifest": _profile(manifest_path),
            "adjudication_audit": _profile(audit_path),
        },
    )


def _reviewer_profiles_match(
    agreement: dict[str, Any], reviewer_paths: tuple[Path, Path]
) -> bool:
    profiles = agreement.get("reviewer_files", [])
    return len(profiles) == len(reviewer_paths) and all(
        recorded.get("sha256") == _file_hash(path)
        for recorded, path in zip(profiles, reviewer_paths)
    )


def _summarize_runs(
    rows: list[dict[str, Any]], group_fields: tuple[str, ...]
) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[field] for field in group_fields)].append(row)
    summaries = []
    for key, items in sorted(groups.items(), key=lambda item: item[0]):
        passed = sum(item["run_pass"] for item in items)
        summaries.append(
            {
                **dict(zip(group_fields, key)),
                "runs": len(items),
                "assessable_runs": sum(item["assessable"] for item in items),
                "passed_runs": passed,
                "failed_runs": len(items) - passed,
                "pass_rate": round(passed / len(items), 6),
            }
        )
    return summaries


def _profile(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "size_bytes": path.stat().st_size,
        "sha256": _file_hash(path),
    }


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the frozen manual metric for the 27-call independent confirmation."
    )
    parser.add_argument("--automatic-analysis", type=Path, required=True)
    parser.add_argument("--review-root", type=Path, required=True)
    parser.add_argument("--adjudication-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = analyze_confirmation_human_review(
        automatic_analysis_path=args.automatic_analysis,
        review_root=args.review_root,
        adjudication_root=args.adjudication_root,
        output=args.output,
    )
    return 0 if report["claim_supported"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
