import json
from pathlib import Path

from scripts.analyze_research_llm_pilot import analyze_pilot


def test_analyzer_recovers_usage_and_detects_input_leakage(tmp_path: Path) -> None:
    (tmp_path / "runs" / "run-1").mkdir(parents=True)
    (tmp_path / "schedule.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "run_id": "run-1",
                        "case_id": "C06",
                        "knowledge_condition": "llm_only",
                        "replicate": 1,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "prepared_inputs.json").write_text(
        json.dumps(
            [
                {
                    "schedule": {"run_id": "run-1"},
                    "payload": {
                        "observable_facts": {"observations": {"expected_consequence": "answer"}}
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    raw_response = {
        "model": "deepseek-v4-flash",
        "usage": {"total_tokens": 8202},
        "choices": [{"finish_reason": "length", "message": {"content": ""}}],
    }
    (tmp_path / "runs" / "run-1" / "result.json").write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "success": False,
                "failure_class": "semantic_parse_error",
                "attempt": {"http_status": 200, "raw_response": json.dumps(raw_response)},
            }
        ),
        encoding="utf-8",
    )

    report = analyze_pilot(tmp_path)

    assert report["total_tokens"] == 8202
    assert report["response_models"] == {"deepseek-v4-flash": 1}
    assert report["diagnostic_only"] is True
    assert report["input_leakage"] is True
    assert report["claim_eligible"] is False
    assert report["input_leakage_audit"]["affected_runs"] == 1
    assert "expected_consequence" in report["input_leakage_audit"]["keys"]
    assert report["runs"][0]["evaluation"]["pre_fallback_valid"] is False
    assert report["formal_ready"] is False
