import json

from scripts.review_research_llm_formal import review_formal


def test_manual_review_preserves_fail_and_pending_boundaries(tmp_path):
    root = tmp_path / "formal"
    root.mkdir()
    payload = {
        "protocol_id": "fusionagent.planning-formal.v1",
        "runs": [
            {
                "run_id": "formal-c01-llm_only-r1",
                "case_id": "C01",
                "knowledge_condition": "llm_only",
                "evaluation": {"manual_review_items": [{"item_id": "no_invalid_partial_building_claim"}]},
            },
            {
                "run_id": "formal-c05-llm_only-r1",
                "case_id": "C05",
                "knowledge_condition": "llm_only",
                "evaluation": {
                    "manual_review_items": [
                        {"item_id": "provenance_complete"},
                        {"item_id": "conflict_aware_fusion"},
                    ]
                },
            },
        ],
    }
    (root / "formal_automatic_audit.json").write_text(json.dumps(payload), encoding="utf-8")

    report = review_formal(root)

    assert report["counts"] == {"pass": 1, "fail": 1, "pending": 1}
    assert report["claim_eligible"] is False
    assert report["status"] == "pending_execution_evidence"
