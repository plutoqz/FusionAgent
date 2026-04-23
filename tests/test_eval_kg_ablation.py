from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.eval_kg_ablation import main, summarize_ablation_results


def _complete_row(**overrides) -> dict:
    row = {
        "case_id": "building_alpha",
        "variant": "kg_llm",
        "planning_valid": True,
        "unknown_algorithms": [],
        "execution_success": True,
        "grounding_score": 1.0,
    }
    row.update(overrides)
    return row


def test_summarize_ablation_results_aggregates_supplied_variants_only() -> None:
    rows = [
        {
            "case_id": "building_alpha",
            "variant": "kg_llm",
            "planning_valid": True,
            "unknown_algorithms": [],
            "execution_success": True,
            "grounding_score": 1.0,
        },
        {
            "case_id": "road_beta",
            "variant": "kg_llm",
            "planning_valid": False,
            "unknown_algorithms": ["algo.missing"],
            "execution_success": True,
            "grounding_score": 0.5,
        },
        {
            "case_id": "building_alpha",
            "variant": "no_kg_llm",
            "planning_valid": False,
            "unknown_algorithms": 2.0,
            "execution_success": False,
            "grounding_score": 0.0,
        },
    ]

    summary = summarize_ablation_results(rows)

    assert summary["supported_variants"] == ["kg_llm", "kg_top_pattern", "no_schema_hints", "no_kg_llm"]
    by_variant = {item["variant"]: item for item in summary["variants"]}

    assert by_variant["kg_llm"] == {
        "variant": "kg_llm",
        "label": "current full system",
        "status": "evaluated",
        "case_count": 2,
        "planning_valid_rate": 0.5,
        "unknown_algorithm_rate": 0.5,
        "execution_success_rate": 1.0,
        "average_grounding_score": 0.75,
    }
    assert by_variant["no_kg_llm"] == {
        "variant": "no_kg_llm",
        "label": "experimental baseline",
        "status": "evaluated",
        "case_count": 1,
        "planning_valid_rate": 0.0,
        "unknown_algorithm_rate": 1.0,
        "execution_success_rate": 0.0,
        "average_grounding_score": 0.0,
    }

    for missing_variant in ["kg_top_pattern", "no_schema_hints"]:
        assert by_variant[missing_variant]["status"] == "skipped"
        assert by_variant[missing_variant]["case_count"] == 0
        assert by_variant[missing_variant]["planning_valid_rate"] is None
        assert by_variant[missing_variant]["unknown_algorithm_rate"] is None
        assert by_variant[missing_variant]["execution_success_rate"] is None
        assert by_variant[missing_variant]["average_grounding_score"] is None


def test_main_reads_object_rows_and_writes_json_and_markdown(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "rows.json"
    output_json = tmp_path / "summary.json"
    output_markdown = tmp_path / "summary.md"
    input_path.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "case_id": "water_gamma",
                        "variant": "kg_top_pattern",
                        "planning_valid": True,
                        "unknown_algorithms": 0,
                        "execution_success": True,
                        "grounding_score": 0.8,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    code = main(
        [
            "--input-json",
            str(input_path),
            "--output-json",
            str(output_json),
            "--output-markdown",
            str(output_markdown),
        ]
    )

    assert code == 0
    saved = json.loads(output_json.read_text(encoding="utf-8"))
    assert saved["variants"][1]["variant"] == "kg_top_pattern"
    assert saved["variants"][1]["case_count"] == 1

    markdown = output_markdown.read_text(encoding="utf-8")
    assert "| kg_top_pattern | KG skeleton fallback | evaluated | 1 | 1.0 | 0.0 | 1.0 | 0.8 |" in markdown
    printed = json.loads(capsys.readouterr().out)
    assert printed["total_input_rows"] == 1


def test_summarize_ablation_results_rejects_rows_missing_required_metric_fields() -> None:
    row = _complete_row()
    del row["execution_success"]

    with pytest.raises(ValueError, match="execution_success"):
        summarize_ablation_results([row])


@pytest.mark.parametrize("invalid_count", [0.9, -1, -1.0, True, False, float("inf"), float("nan")])
def test_summarize_ablation_results_rejects_invalid_numeric_unknown_algorithm_counts(invalid_count) -> None:
    with pytest.raises(ValueError, match="unknown_algorithms"):
        summarize_ablation_results([_complete_row(unknown_algorithms=invalid_count)])
