from __future__ import annotations

import json
from pathlib import Path

from scripts.export_trace_backed_ablation_evidence import (
    export_trace_evidence,
    summarize_inspection_trace,
)


def _inspection_payload(artifact_path: Path) -> dict:
    return {
        "run": {
            "run_id": "run-1",
            "job_type": "road",
            "phase": "succeeded",
            "artifact": {
                "path": str(artifact_path),
                "size_bytes": 256,
            },
            "decision_records": [{"decision_type": "pattern_selection"}],
        },
        "plan": {
            "validation": {"valid": True, "issues": []},
        },
        "audit_events": [
            {"kind": "run_created"},
            {"kind": "plan_created", "details": {"grounding_score": 0.5}},
            {"kind": "plan_validated"},
            {"kind": "task_inputs_resolved"},
            {"kind": "execution_completed"},
            {"kind": "output_schema_validated"},
            {"kind": "run_succeeded"},
        ],
        "kg_path_trace": {
            "selected_pattern_id": "wp.road.fusioncode.v1",
            "grounding_report": {"grounding_score": 1.0},
            "chains": [{"task_step": 1}],
        },
    }


def test_summarize_inspection_trace_reports_trace_completeness_and_artifact_presence(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifact.zip"
    artifact.write_bytes(b"zip")
    inspection = tmp_path / "inspection.json"
    inspection.write_text(json.dumps(_inspection_payload(artifact)), encoding="utf-8")

    row = summarize_inspection_trace(inspection)

    assert row["case_id"] == "inspection"
    assert row["validation_valid"] is True
    assert row["grounding_score"] == 1.0
    assert row["kg_trace_chain_count"] == 1
    assert row["artifact_declared"] is True
    assert row["artifact_path_exists_in_workspace"] is True
    assert row["inspection_trace_complete"] is True
    assert row["inspection_sha256"]


def test_export_trace_evidence_writes_summary_and_preserves_missing_artifact_boundary(
    tmp_path: Path,
) -> None:
    missing_artifact = tmp_path / "missing.zip"
    inspection = tmp_path / "inspection.json"
    inspection.write_text(json.dumps(_inspection_payload(missing_artifact)), encoding="utf-8")
    output_json = tmp_path / "trace.json"
    output_markdown = tmp_path / "trace.md"

    payload = export_trace_evidence(
        [inspection],
        output_json=output_json,
        output_markdown=output_markdown,
    )

    assert payload["case_count"] == 1
    assert payload["inspection_trace_complete_case_count"] == 1
    assert payload["artifact_declared_case_count"] == 1
    assert payload["artifact_file_present_case_count"] == 0
    saved = json.loads(output_json.read_text(encoding="utf-8"))
    assert saved["rows"][0]["artifact_path_exists_in_workspace"] is False
    markdown = output_markdown.read_text(encoding="utf-8")
    assert "Trace-Backed A2c Ablation Evidence" in markdown
    assert "| inspection | road | succeeded | True | 1.0 | 7 | 1 | True | False | True |" in markdown
