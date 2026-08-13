from scripts.summarize_research_planning_comparison import summarize_comparison


def test_comparison_summary_keeps_cross_commit_claim_boundary(tmp_path):
    llm = {
        "protocol_id": "llm.v1",
        "formal_execution_valid": True,
        "runs": [
            {
                "case_id": "C01",
                "knowledge_condition": "llm_only",
                "evaluation": {
                    "automatic_score": 0.5,
                    "automatic_checks": [{"passed": True}],
                    "decision_valid": True,
                    "grounding_pass": True,
                    "gap_metrics": {"f1": 0.0},
                },
            },
            {
                "case_id": "C03",
                "knowledge_condition": "llm_only",
                "evaluation": {
                    "automatic_score": 1.0,
                    "automatic_checks": [{"passed": True}],
                    "decision_valid": True,
                    "grounding_pass": True,
                    "gap_metrics": {"f1": 1.0},
                },
            },
        ],
    }
    deterministic = {
        "protocol_id": "det.v1",
        "implementation_dirty": False,
        "run_count": 2,
        "runs": [
            {
                "case_id": "C01",
                "group": "rules_only",
                "evaluation": {
                    "automatic_score": 1.0,
                    "automatic_checks": [{"passed": True}],
                    "decision_valid": True,
                    "grounding_pass": True,
                    "gap_metrics": {"f1": 1.0},
                },
            },
            {
                "case_id": "C03",
                "group": "rules_only",
                "evaluation": {
                    "automatic_score": 1.0,
                    "automatic_checks": [{"passed": True}],
                    "decision_valid": True,
                    "grounding_pass": True,
                    "gap_metrics": {"f1": 1.0},
                },
            },
        ],
    }
    import json
    llm_path = tmp_path / "llm.json"
    deterministic_path = tmp_path / "det.json"
    llm_path.write_text(json.dumps(llm), encoding="utf-8")
    deterministic_path.write_text(json.dumps(deterministic), encoding="utf-8")

    report = summarize_comparison(llm_path, deterministic_path)

    assert report["claim_eligible"] is False
    assert report["same_implementation_commit"] is False
    assert report["groups"][0]["positive_cases"] == 1
