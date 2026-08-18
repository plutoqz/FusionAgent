import hashlib
import json
from pathlib import Path

from scripts.analyze_research_method_confirmation_human_review import (
    FULL_KG_CONDITION,
    LLM_ONLY_CONDITION,
    METHOD_B_CONDITION,
    analyze_confirmation_human_review,
    evaluate_confirmation_metric,
    _resolve_final_records,
)


RUBRICS = {
    "H07": [
        "task_contract_and_state_isolation",
        "mission_priority_and_building_gap_trace",
    ],
    "H08": [
        "polygon_and_line_source_semantics_separated",
        "delayed_waterways_source_not_claimed_current",
    ],
    "H09": [
        "poi_recovery_trace",
        "prior_poi_failure_preserved",
        "declared_recovery_source_only",
    ],
}
CONDITIONS = (
    METHOD_B_CONDITION,
    LLM_ONLY_CONDITION,
    FULL_KG_CONDITION,
)


def _fixture(pass_counts=None):
    pass_counts = pass_counts or {
        METHOD_B_CONDITION: {"H07": 3, "H08": 3, "H09": 3},
        LLM_ONLY_CONDITION: {"H07": 2, "H08": 2, "H09": 2},
        FULL_KG_CONDITION: {"H07": 1, "H08": 1, "H09": 1},
    }
    automatic_rows = []
    mapping = []
    decisions = []
    item_number = 0
    for case_id, rubric_ids in RUBRICS.items():
        for condition in CONDITIONS:
            for replicate in (1, 2, 3):
                run_id = f"confirmation-{case_id.lower()}-{condition}-r{replicate}"
                automatic_rows.append(
                    {
                        "run_id": run_id,
                        "case_id": case_id,
                        "knowledge_condition": condition,
                        "replicate": replicate,
                        "manual_review_items": [
                            {"item_id": rubric_id, "status": "pending"}
                            for rubric_id in rubric_ids
                        ],
                    }
                )
                run_passes = replicate <= pass_counts[condition][case_id]
                for rubric_index, rubric_id in enumerate(rubric_ids):
                    item_number += 1
                    packet_item_id = f"review-{item_number:03d}"
                    mapping.append(
                        {
                            "packet_item_id": packet_item_id,
                            "run_id": run_id,
                            "case_id": case_id,
                            "knowledge_condition": condition,
                            "replicate": replicate,
                            "rubric_item_id": rubric_id,
                        }
                    )
                    decisions.append(
                        {
                            "packet_item_id": packet_item_id,
                            "rubric_item_id": rubric_id,
                            "decision": (
                                "pass" if run_passes or rubric_index > 0 else "fail"
                            ),
                            "resolution_source": "reviewer_a_b_agreement",
                        }
                    )
    return automatic_rows, mapping, decisions


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_confirmation_manual_metric_passes_all_registered_success_rules() -> None:
    automatic_rows, mapping, decisions = _fixture()

    report = evaluate_confirmation_metric(
        automatic_rows=automatic_rows,
        blind_mapping=mapping,
        final_records=decisions,
    )

    assert report["manual_item_count"] == 63
    assert report["run_count"] == 27
    assert report["run_grid_complete"] is True
    assert report["all_27_runs_final_assessable"] is True
    assert report["primary_metric_passed"] is True
    by_condition = {
        row["knowledge_condition"]: row for row in report["by_condition"]
    }
    assert by_condition[METHOD_B_CONDITION]["passed_runs"] == 9
    assert by_condition[LLM_ONLY_CONDITION]["passed_runs"] == 6
    assert by_condition[FULL_KG_CONDITION]["passed_runs"] == 3


def test_confirmation_run_requires_every_rubric_item_to_pass() -> None:
    automatic_rows, mapping, decisions = _fixture()
    target = next(
        item
        for item in decisions
        if item["rubric_item_id"] == "mission_priority_and_building_gap_trace"
        and next(
            key for key in mapping if key["packet_item_id"] == item["packet_item_id"]
        )["run_id"].endswith(f"{METHOD_B_CONDITION}-r1")
    )
    target["decision"] = "fail"

    report = evaluate_confirmation_metric(
        automatic_rows=automatic_rows,
        blind_mapping=mapping,
        final_records=decisions,
    )

    b = next(
        row
        for row in report["by_condition"]
        if row["knowledge_condition"] == METHOD_B_CONDITION
    )
    assert b["passed_runs"] == 8
    assert report["primary_metric_passed"] is True


def test_confirmation_not_assessable_makes_claim_metric_ineligible() -> None:
    automatic_rows, mapping, decisions = _fixture()
    decisions[0]["decision"] = "not_assessable"

    report = evaluate_confirmation_metric(
        automatic_rows=automatic_rows,
        blind_mapping=mapping,
        final_records=decisions,
    )

    assert report["all_27_runs_final_assessable"] is False
    assert report["primary_metric_passed"] is False
    assert report["manual_item_decision_counts"]["not_assessable"] == 1


def test_confirmation_per_case_gate_blocks_overall_only_advantage() -> None:
    automatic_rows, mapping, decisions = _fixture(
        {
            METHOD_B_CONDITION: {"H07": 2, "H08": 3, "H09": 3},
            LLM_ONLY_CONDITION: {"H07": 3, "H08": 1, "H09": 1},
            FULL_KG_CONDITION: {"H07": 1, "H08": 1, "H09": 1},
        }
    )

    report = evaluate_confirmation_metric(
        automatic_rows=automatic_rows,
        blind_mapping=mapping,
        final_records=decisions,
    )

    gates = report["primary_metric_gates"]
    assert gates["b_pass_rate_strictly_above_llm_only"] is True
    assert gates["b_pass_rate_strictly_above_full_kg"] is True
    assert gates["b_not_below_each_comparator_per_case"] is False
    assert report["primary_metric_passed"] is False


def test_confirmation_final_analyzer_accepts_frozen_two_reviewer_consensus(
    tmp_path: Path,
) -> None:
    automatic_rows, mapping, decisions = _fixture()
    evidence_root = tmp_path / "evidence"
    review_root = tmp_path / "review"
    protocol_path = evidence_root / "formal_protocol.json"
    _write_json(
        protocol_path,
        {
            "protocol_id": "fusionagent.method-b-independent-confirmation.v1",
            "protocol_status": "frozen",
            "primary_metric": {"metric_id": "blinded_manual_run_pass_rate.v1"},
            "manual_review": {
                "rubric": {
                    case_id: {rubric_id: "fixture" for rubric_id in rubric_ids}
                    for case_id, rubric_ids in RUBRICS.items()
                }
            },
        },
    )
    automatic_path = evidence_root / "automatic_analysis_v2.json"
    _write_json(
        automatic_path,
        {
            "protocol_id": "fusionagent.method-b-independent-confirmation.v1",
            "evidence_root": str(evidence_root),
            "evidence_integrity_valid": True,
            "formal_execution_complete": True,
            "automatic_gate_passed": True,
            "rows": automatic_rows,
        },
    )
    packet_id = "packet-confirmation-fixture"
    packet_manifest_path = review_root / "packet-manifest.json"
    _write_json(
        packet_manifest_path,
        {
            "packet_id": packet_id,
            "source_audit_sha256": _hash(automatic_path),
        },
    )
    _write_json(
        review_root / "blind-key.json",
        {
            "packet_id": packet_id,
            "source_audit_sha256": _hash(automatic_path),
            "mapping": mapping,
        },
    )
    reviewer_records = [
        {
            "packet_item_id": item["packet_item_id"],
            "rubric_item_id": item["rubric_item_id"],
            "decision": item["decision"],
            "notes": "independent human review fixture",
        }
        for item in decisions
    ]
    reviewer_a_path = review_root / "reviewer-a.decisions.json"
    reviewer_b_path = review_root / "reviewer-b.decisions.json"
    _write_json(reviewer_a_path, {"records": reviewer_records})
    _write_json(reviewer_b_path, {"records": reviewer_records})
    agreement_path = review_root / "manual-review-agreement-audit.json"
    _write_json(
        agreement_path,
        {
            "packet_id": packet_id,
            "source_packet_manifest": {"sha256": _hash(packet_manifest_path)},
            "reviewer_files": [
                {"sha256": _hash(reviewer_a_path)},
                {"sha256": _hash(reviewer_b_path)},
            ],
            "checks": {
                "decisions_complete_a": True,
                "decisions_complete_b": True,
                "no_unresolved_disagreements": True,
            },
            "passed": True,
            "agreement": {"exact_agreement": 1.0, "cohen_kappa": 1.0},
            "disagreement_count": 0,
        },
    )

    report = analyze_confirmation_human_review(
        automatic_analysis_path=automatic_path,
        review_root=review_root,
        output=tmp_path / "final-analysis.json",
    )

    assert report["resolution"]["mode"] == "two_reviewer_consensus_no_adjudication"
    assert report["claim_evaluable"] is True
    assert report["claim_supported"] is True
    assert report["claim_status"] == "passed_scoped_planning_superiority"


def test_confirmation_final_analyzer_requires_and_accepts_frozen_adjudication(
    tmp_path: Path,
) -> None:
    _, _, decisions = _fixture()
    review_root = tmp_path / "review"
    reviewer_a_path = review_root / "reviewer-a.decisions.json"
    reviewer_b_path = review_root / "reviewer-b.decisions.json"
    reviewer_a_records = [dict(item) for item in decisions]
    reviewer_b_records = [dict(item) for item in decisions]
    reviewer_b_records[0]["decision"] = "fail"
    _write_json(reviewer_a_path, {"records": reviewer_a_records})
    _write_json(reviewer_b_path, {"records": reviewer_b_records})
    agreement_path = review_root / "manual-review-agreement-audit.json"
    _write_json(agreement_path, {"disagreement_count": 1})

    adjudication_root = tmp_path / "adjudication"
    manifest_path = adjudication_root / "adjudication-manifest.json"
    _write_json(
        manifest_path,
        {
            "source_review_packet_id": "packet-confirmation-fixture",
            "source_agreement_audit": {"sha256": _hash(agreement_path)},
        },
    )
    final_records = [dict(item) for item in decisions]
    final_records[0]["resolution_source"] = "independent_adjudicator_c"
    _write_json(
        adjudication_root / "adjudication-audit.json",
        {
            "passed": True,
            "source_agreement_audit": {"sha256": _hash(agreement_path)},
            "source_adjudication_manifest": {"sha256": _hash(manifest_path)},
            "source_reviewer_files": [
                {"sha256": _hash(reviewer_a_path)},
                {"sha256": _hash(reviewer_b_path)},
            ],
            "final_item_count": 63,
            "adjudicated_item_count": 1,
            "final_blinded_decisions": final_records,
        },
    )

    resolved, mode, checks, _ = _resolve_final_records(
        review_root=review_root,
        agreement={"disagreement_count": 1},
        agreement_path=agreement_path,
        reviewer_a_path=reviewer_a_path,
        reviewer_b_path=reviewer_b_path,
        adjudication_root=adjudication_root,
        expected_packet_id="packet-confirmation-fixture",
    )

    assert mode == "independent_third_reviewer_adjudication"
    assert all(checks.values())
    assert len(resolved) == 63
    assert resolved[0]["resolution_source"] == "independent_adjudicator_c"
