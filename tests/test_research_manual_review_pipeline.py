import json
from pathlib import Path

import pytest

from scripts.analyze_research_llm_repeated_formal import analyze_repeated_formal
from scripts.audit_research_manual_review import audit_manual_review
from scripts.prepare_research_manual_review import prepare_manual_review
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
