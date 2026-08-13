import json
from pathlib import Path

from scripts.recover_research_llm_pilot_summary import recover_summary


def test_recover_summary_uses_raw_response_usage_without_mutating_result(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    result_path = run_dir / "result.json"
    result = {
        "run_id": "run-1",
        "success": False,
        "failure_class": "semantic_parse_error",
        "attempt": {
            "usage": None,
            "raw_response": json.dumps(
                {
                    "model": "deepseek-v4-flash",
                    "usage": {"total_tokens": 8202},
                    "choices": [{"finish_reason": "length", "message": {"content": ""}}],
                }
            ),
        },
    }
    result_path.write_text(json.dumps(result), encoding="utf-8")

    summary = recover_summary(tmp_path, source_commit="abc123")

    assert summary["main_call_count"] == 1
    assert summary["consumed_tokens"] == 8202
    assert summary["failure_counts"] == {"semantic_parse_error": 1}
    assert summary["summary_recovery"]["raw_result_files_modified"] is False
    assert json.loads(result_path.read_text(encoding="utf-8")) == result
