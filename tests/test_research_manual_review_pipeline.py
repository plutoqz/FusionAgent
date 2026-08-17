import json
from pathlib import Path

import pytest

from scripts.analyze_research_llm_repeated_formal import analyze_repeated_formal
from scripts.audit_research_manual_adjudication import audit_manual_adjudication
from scripts.audit_research_manual_review import audit_manual_review
from scripts.prepare_research_manual_adjudication import prepare_manual_adjudication
from scripts.prepare_research_manual_review import prepare_manual_review
from scripts.prepare_research_combined_manual_review import prepare_combined_manual_review
from test_analyze_research_llm_repeated_formal import _build_completed_root


def _prepare(tmp_path: Path):
    formal_root = _build_completed_root(tmp_path)
    audit_path = tmp_path / "formal-audit.json"
    audit_path.write_text(
        json.dumps(analyze_repeated_formal(formal_root), ensure_ascii=False),
        encoding="utf-8",
    )
    packet_root = tmp_path / "review"
    manifest = prepare_manual_review(
        formal_root=formal_root,
        audit_path=audit_path,
        output_root=packet_root,
    )
    return formal_root, audit_path, packet_root, manifest


def _complete_decisions(path: Path, *, disagreement_first: bool = False) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for index, record in enumerate(payload["records"]):
        record["decision"] = "fail" if disagreement_first and index == 0 else "pass"
        record["notes"] = "independent human decision fixture"
    payload["status"] = "human_review_complete"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_manual_review_packet_is_blinded_and_keeps_context_immutable(tmp_path: Path) -> None:
    _, _, packet_root, manifest = _prepare(tmp_path)

    assert manifest["item_count"] == 108
    assert manifest["human_review_required"] is True
    packet = json.loads((packet_root / "reviewer-a.packet.json").read_text(encoding="utf-8"))
    decisions = json.loads((packet_root / "reviewer-a.decisions.json").read_text(encoding="utf-8"))
    key = json.loads((packet_root / "blind-key.json").read_text(encoding="utf-8"))
    assert packet["status"] == "immutable_reviewer_context"
    assert "packet_seed" not in packet
    assert manifest["packet_seed"] == 20260815
    assert decisions["status"] == "awaiting_human_review"
    assert len(packet["records"]) == len(decisions["records"]) == len(key["mapping"]) == 108
    assert all("knowledge_condition" not in record for record in packet["records"])
    assert all("run_id" not in record and "replicate" not in record for record in packet["records"])
    assert all("automatic_score" not in json.dumps(record) for record in packet["records"])
    assert all(
        set(record) == {"packet_item_id", "rubric_item_id", "decision", "notes"}
        for record in decisions["records"]
    )


def test_manual_review_packet_refuses_incomplete_formal_batch(tmp_path: Path) -> None:
    formal_root = _build_completed_root(tmp_path)
    audit = analyze_repeated_formal(formal_root)
    audit["formal_execution_complete"] = False
    audit_path = tmp_path / "incomplete-audit.json"
    audit_path.write_text(json.dumps(audit), encoding="utf-8")

    with pytest.raises(RuntimeError, match="complete 54-call"):
        prepare_manual_review(
            formal_root=formal_root,
            audit_path=audit_path,
            output_root=tmp_path / "review",
        )


def test_manual_review_agreement_audit_passes_exact_independent_agreement(tmp_path: Path) -> None:
    _, _, packet_root, _ = _prepare(tmp_path)
    reviewer_a = packet_root / "reviewer-a.decisions.json"
    reviewer_b = packet_root / "reviewer-b.decisions.json"
    _complete_decisions(reviewer_a)
    _complete_decisions(reviewer_b)

    report = audit_manual_review(
        packet_manifest=packet_root / "packet-manifest.json",
        reviewer_a=reviewer_a,
        reviewer_b=reviewer_b,
        output=tmp_path / "agreement.json",
    )

    assert report["passed"] is True
    assert report["item_count"] == 108
    assert report["agreement"] == {"items": 108, "exact_agreement": 1.0, "cohen_kappa": 1.0}
    assert report["disagreement_count"] == 0


def test_manual_review_agreement_audit_preserves_disagreement(tmp_path: Path) -> None:
    _, _, packet_root, _ = _prepare(tmp_path)
    reviewer_a = packet_root / "reviewer-a.decisions.json"
    reviewer_b = packet_root / "reviewer-b.decisions.json"
    _complete_decisions(reviewer_a)
    _complete_decisions(reviewer_b, disagreement_first=True)

    report = audit_manual_review(
        packet_manifest=packet_root / "packet-manifest.json",
        reviewer_a=reviewer_a,
        reviewer_b=reviewer_b,
        output=tmp_path / "disagreement.json",
    )

    assert report["passed"] is False
    assert report["disagreement_count"] == 1
    assert report["checks"]["no_unresolved_disagreements"] is False


def test_combined_manual_review_routes_runs_across_two_evidence_roots(tmp_path: Path) -> None:
    base_root = tmp_path / "base"
    extension_root = tmp_path / "extension"
    rows = []
    for root, run_id, replicate in (
        (base_root, "formal-v3-c01-llm_only-r1", 1),
        (extension_root, "formal-ext-v1-c01-llm_only-r4", 4),
    ):
        root.mkdir()
        (root / "prepared_inputs.json").write_text(
            json.dumps(
                [
                    {
                        "schedule": {"run_id": run_id},
                        "payload": {"task": "visible planner input", "replicate": replicate},
                    }
                ]
            ),
            encoding="utf-8",
        )
        run_dir = root / "runs" / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "result.json").write_text(
            json.dumps({"run_id": run_id, "plan": {"decision": "plan", "tasks": []}}),
            encoding="utf-8",
        )
        rows.append(
            {
                "run_id": run_id,
                "case_id": "C01",
                "knowledge_condition": "llm_only",
                "replicate": replicate,
                "evaluation": {
                    "manual_review_items": [
                        {"item_id": "manual-fixture", "description": "review this plan"}
                    ]
                },
            }
        )
    audit_path = tmp_path / "combined-audit.json"
    audit_path.write_text(
        json.dumps(
            {
                "evidence_integrity_valid": True,
                "formal_execution_complete": True,
                "runs": rows,
            }
        ),
        encoding="utf-8",
    )

    output = tmp_path / "combined-review"
    manifest = prepare_combined_manual_review(
        base_root=base_root,
        extension_root=extension_root,
        audit_path=audit_path,
        output_root=output,
    )

    assert manifest["item_count"] == 2
    key = json.loads((output / "blind-key.json").read_text(encoding="utf-8"))
    assert {item["run_id"] for item in key["mapping"]} == {row["run_id"] for row in rows}


def test_manual_review_accepts_method_b_rows_field(tmp_path: Path) -> None:
    formal_root = tmp_path / "formal"
    run_id = "formal-heldout-repair-h01-method-b-r1"
    (formal_root / "runs" / run_id).mkdir(parents=True)
    (formal_root / "prepared_inputs.json").write_text(
        json.dumps([{"schedule": {"run_id": run_id}, "payload": {"task": "visible input"}}]),
        encoding="utf-8",
    )
    (formal_root / "runs" / run_id / "result.json").write_text(
        json.dumps({"run_id": run_id, "plan": {"decision": "partial", "tasks": []}}),
        encoding="utf-8",
    )
    audit_path = tmp_path / "method-b-audit.json"
    audit_path.write_text(
        json.dumps(
            {
                "evidence_integrity_valid": True,
                "formal_execution_complete": True,
                "rows": [
                    {
                        "run_id": run_id,
                        "case_id": "H01",
                        "knowledge_condition": "task_conditioned_contract_aware_kg",
                        "replicate": 1,
                        "evaluation": {
                            "manual_review_items": [
                                {"item_id": "manual-fixture", "description": "review this plan"}
                            ]
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    packet_root = tmp_path / "method-b-review"
    manifest = prepare_manual_review(
        formal_root=formal_root,
        audit_path=audit_path,
        output_root=packet_root,
    )

    assert manifest["item_count"] == 1
    packet = json.loads((packet_root / "reviewer-a.packet.json").read_text(encoding="utf-8"))
    assert "knowledge_condition" not in packet["records"][0]


def test_manual_adjudication_resolves_only_frozen_disagreements_without_unblinding(
    tmp_path: Path,
) -> None:
    _, _, packet_root, _ = _prepare(tmp_path)
    reviewer_a = packet_root / "reviewer-a.decisions.json"
    reviewer_b = packet_root / "reviewer-b.decisions.json"
    _complete_decisions(reviewer_a)
    _complete_decisions(reviewer_b, disagreement_first=True)
    agreement_path = packet_root / "manual-review-agreement-audit.json"
    agreement = audit_manual_review(
        packet_manifest=packet_root / "packet-manifest.json",
        reviewer_a=reviewer_a,
        reviewer_b=reviewer_b,
        output=agreement_path,
    )
    assert agreement["passed"] is False
    assert agreement["disagreement_count"] == 1

    adjudication_root = tmp_path / "adjudication"
    manifest = prepare_manual_adjudication(
        review_root=packet_root,
        output_root=adjudication_root,
    )
    packet = json.loads(
        (adjudication_root / "adjudicator-c.packet.json").read_text(encoding="utf-8")
    )
    assert manifest["item_count"] == len(packet["records"]) == 1
    assert "knowledge_condition" not in json.dumps(packet["records"][0])
    assert "decision_a" not in json.dumps(packet["records"][0])
    assert "decision_b" not in json.dumps(packet["records"][0])

    decisions_path = adjudication_root / "adjudicator-c.decisions.json"
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    decisions["records"][0]["decision"] = "pass"
    decisions["records"][0]["notes"] = "Independent adjudicator fixture decision."
    decisions["status"] = "human_adjudication_complete"
    decisions_path.write_text(json.dumps(decisions), encoding="utf-8")
    report = audit_manual_adjudication(
        adjudication_manifest=adjudication_root / "adjudication-manifest.json",
        adjudicator_decisions=decisions_path,
        output=adjudication_root / "adjudication-audit.json",
    )

    assert report["passed"] is True
    assert report["adjudicated_item_count"] == 1
    assert report["final_item_count"] == 108
    assert report["planning_claim_review_ready"] is True
    assert sum(report["final_decision_counts"].values()) == 108
