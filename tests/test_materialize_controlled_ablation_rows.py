from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.materialize_controlled_ablation_rows import materialize_controlled_ablation_rows


def _base_payload() -> dict:
    return {
        "source": "inspection-derived-ablation-input",
        "rows": [
            {
                "case_id": "building-case",
                "variant": "A2c",
                "planning_valid": True,
                "unknown_algorithms": [],
                "execution_success": True,
                "grounding_score": 0.0,
                "validator_rejected": False,
                "kg_fallback_used": False,
                "llm_plan_valid_before_fallback": True,
                "fallback_plan_quality_delta": 0.0,
                "job_type": "building",
            },
            {
                "case_id": "water-case",
                "variant": "A2c",
                "planning_valid": False,
                "unknown_algorithms": [],
                "execution_success": True,
                "grounding_score": 1.0,
                "validator_rejected": True,
                "kg_fallback_used": False,
                "llm_plan_valid_before_fallback": False,
                "fallback_plan_quality_delta": 0.0,
                "job_type": "water",
                "validation_issue_codes": ["SCENARIO_PROFILE_TASK_MISMATCH"],
            },
        ],
    }


def test_materialize_controlled_ablation_rows_completes_all_variants(tmp_path: Path) -> None:
    input_json = tmp_path / "partial.json"
    output_json = tmp_path / "full.json"
    output_markdown = tmp_path / "full.md"
    input_json.write_text(json.dumps(_base_payload()), encoding="utf-8")

    payload = materialize_controlled_ablation_rows(
        input_json=input_json,
        output_json=output_json,
        output_markdown=output_markdown,
    )

    assert payload["source_a2c_case_count"] == 2
    assert payload["row_count"] == 10
    assert {row["variant"] for row in payload["rows"]} == {"A0", "A1", "A2a", "A2b", "A2c"}

    by_variant = {item["variant"]: item for item in payload["summary"]["variants"]}
    assert by_variant["A0"]["case_count"] == 2
    assert by_variant["A0"]["planning_valid_rate"] == 0.5
    assert by_variant["A0"]["unknown_algorithm_rate"] == 0.5
    assert by_variant["A2b"]["kg_fallback_rate"] == 0.5
    assert by_variant["A2c"]["execution_success_rate"] == 1.0

    saved = json.loads(output_json.read_text(encoding="utf-8"))
    assert saved["protocol_version"] == "controlled-ablation-counterfactual-v1"
    markdown = output_markdown.read_text(encoding="utf-8")
    assert "| A2b | 2 | 0.5 | 0.0 | 1.0 | 0.5 | 0.5 |" in markdown


def test_materialize_controlled_ablation_rows_requires_a2c_source_rows(tmp_path: Path) -> None:
    input_json = tmp_path / "no-a2c.json"
    input_json.write_text(json.dumps({"rows": [{"variant": "A1"}]}), encoding="utf-8")

    with pytest.raises(ValueError, match="requires at least one A2c"):
        materialize_controlled_ablation_rows(
            input_json=input_json,
            output_json=tmp_path / "out.json",
        )
