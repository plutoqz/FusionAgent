from scripts.analyze_research_llm_formal import _group_metrics


def _row(condition: str, case_id: str, score: float, *, passed: bool, tokens: int) -> dict:
    return {
        "knowledge_condition": condition,
        "case_id": case_id,
        "total_tokens": tokens,
        "evaluation": {
            "automatic_score": score,
            "automatic_checks": [{"check_id": "example", "passed": passed}],
        },
    }


def test_group_metrics_excludes_negative_control_from_positive_mean() -> None:
    rows = [
        _row("llm_only", "C01", 0.5, passed=False, tokens=10),
        _row("llm_only", "C03", 1.0, passed=True, tokens=20),
    ]

    metrics = _group_metrics(rows)[0]

    assert metrics["mean_automatic_score_all_cases"] == 0.75
    assert metrics["mean_automatic_score_positive_cases"] == 0.5
    assert metrics["negative_control_passed"] is True
    assert metrics["tokens"] == 30
