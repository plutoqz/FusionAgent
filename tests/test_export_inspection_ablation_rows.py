from __future__ import annotations

import json
from pathlib import Path

from scripts.export_inspection_ablation_rows import export_rows, extract_ablation_row


def _inspection_payload(*, valid: bool = True, phase: str = "succeeded") -> dict:
    return {
        "run": {
            "run_id": "run-1",
            "job_type": "poi",
            "phase": phase,
            "artifact": {"size_bytes": 128},
        },
        "plan": {
            "validation": {
                "valid": valid,
                "issues": [] if valid else [{"code": "SCENARIO_PROFILE_TASK_MISMATCH"}],
            }
        },
        "audit_events": [
            {
                "kind": "plan_created",
                "details": {"grounding_score": 0.75},
            },
            {"kind": "plan_validated"},
            {"kind": "run_succeeded"},
        ],
    }


def test_extract_ablation_row_from_inspection_payload(tmp_path: Path) -> None:
    path = tmp_path / "inspection.json"
    path.write_text(json.dumps(_inspection_payload(valid=False)), encoding="utf-8")

    row = extract_ablation_row(path)

    assert row["case_id"] == "inspection"
    assert row["variant"] == "A2c"
    assert row["planning_valid"] is False
    assert row["execution_success"] is True
    assert row["grounding_score"] == 0.75
    assert row["validator_rejected"] is True
    assert row["validation_issue_codes"] == ["SCENARIO_PROFILE_TASK_MISMATCH"]


def test_export_rows_writes_json_and_markdown(tmp_path: Path) -> None:
    path = tmp_path / "inspection.json"
    path.write_text(json.dumps(_inspection_payload()), encoding="utf-8")
    output_json = tmp_path / "rows.json"
    output_markdown = tmp_path / "rows.md"

    payload = export_rows([path], variant="A2c", output_json=output_json, output_markdown=output_markdown)

    saved = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["rows"][0]["planning_valid"] is True
    assert saved["scope"].startswith("partial full-runtime")
    assert "| inspection | A2c | poi | True | True | 0.75 | False |" in output_markdown.read_text(
        encoding="utf-8"
    )
