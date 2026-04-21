from __future__ import annotations

import json
from pathlib import Path

from scripts.freeze_scenario_evidence import freeze_scenario_evidence


def test_freeze_scenario_evidence_writes_json_and_markdown(tmp_path: Path):
    scenario_dir = tmp_path / "scenario-a"
    scenario_dir.mkdir()
    (scenario_dir / "scenario_summary.json").write_text(
        json.dumps(
            {
                "scenario_id": "scenario-a",
                "scenario_name": "Parakou earthquake",
                "evaluation": {
                    "agentic_metrics": {"manual_intervention_count": 0},
                    "self_evolution": {"hint_available": True},
                },
                "kg_path_traces": [{"workflow_id": "wf-building"}],
                "workflow_traces": [{"steps": [{"step_name": "plan", "status": "ok"}]}],
                "document_paths": {"en": "documents/scenario_report.en.md"},
            }
        ),
        encoding="utf-8",
    )
    output_json = tmp_path / "freeze.json"
    output_markdown = tmp_path / "freeze.md"

    payload = freeze_scenario_evidence([scenario_dir], output_json, output_markdown)
    markdown = output_markdown.read_text(encoding="utf-8")

    assert payload["scenario_count"] == 1
    assert "Parakou earthquake" in markdown
    assert "manual_intervention_count" in markdown
