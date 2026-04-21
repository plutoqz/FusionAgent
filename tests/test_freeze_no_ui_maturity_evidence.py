import json
from pathlib import Path

from scripts.freeze_no_ui_maturity_evidence import freeze_no_ui_maturity_evidence


def test_freeze_no_ui_maturity_evidence_writes_json_and_markdown(tmp_path: Path) -> None:
    target = tmp_path / "target.md"
    target.write_text("# No-UI Maturity Target\n", encoding="utf-8")
    gap = tmp_path / "gap.md"
    gap.write_text("# No-UI Maturity Gap Ledger\n", encoding="utf-8")

    payload = freeze_no_ui_maturity_evidence(
        target_path=target,
        gap_ledger_path=gap,
        paper_evidence_path=tmp_path / "missing-paper.md",
        scenario_evidence_path=tmp_path / "missing-scenario.md",
        output_json=tmp_path / "freeze.json",
        output_markdown=tmp_path / "freeze.md",
    )

    assert payload["maturity_target_present"] is True
    assert payload["gap_ledger_present"] is True
    assert {
        "maturity_target_present",
        "gap_ledger_present",
        "paper_evidence_present",
        "scenario_evidence_present",
        "gates",
        "generated_at",
        "remaining_boundaries",
    }.issubset(payload)
    markdown = (tmp_path / "freeze.md").read_text(encoding="utf-8")
    assert "maturity_target_present" in markdown
    assert "# No-UI Maturity Evidence Freeze" in markdown
    assert "## Gate Status" in markdown
    assert "## Evidence Sources" in markdown
    assert "## Remaining Boundaries" in markdown


def test_freeze_no_ui_maturity_evidence_accepts_positional_args(tmp_path: Path) -> None:
    target = tmp_path / "target.md"
    target.write_text("# No-UI Maturity Target\n", encoding="utf-8")
    gap = tmp_path / "gap.md"
    gap.write_text("# No-UI Maturity Gap Ledger\n", encoding="utf-8")
    output_json = tmp_path / "freeze.json"
    output_markdown = tmp_path / "freeze.md"

    payload = freeze_no_ui_maturity_evidence(
        target,
        gap,
        tmp_path / "missing-paper.md",
        tmp_path / "missing-scenario.md",
        output_json,
        output_markdown,
    )

    assert payload["maturity_target_present"] is True
    assert payload["gap_ledger_present"] is True
    assert output_json.exists()
    assert output_markdown.exists()


def test_freeze_no_ui_maturity_evidence_blocks_readme_ready_from_pending_rows(tmp_path: Path) -> None:
    target = tmp_path / "target.md"
    target.write_text("# No-UI Maturity Target\n", encoding="utf-8")
    gap = tmp_path / "gap.md"
    gap.write_text("# No-UI Maturity Gap Ledger\n", encoding="utf-8")
    paper = tmp_path / "paper.md"
    paper.write_text("# Paper Evidence Freeze\n", encoding="utf-8")
    paper.with_suffix(".json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "row_id": "scenario_trigger_pending",
                        "expected_status": "passed",
                        "observed_status": "pending",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    scenario = tmp_path / "scenario.md"
    scenario.write_text("# Scenario Evidence Freeze\n", encoding="utf-8")
    scenario.with_suffix(".json").write_text(
        json.dumps({"scenario_count": 1, "scenarios": [{"scenario_name": "fixture"}]}),
        encoding="utf-8",
    )

    payload = freeze_no_ui_maturity_evidence(
        target,
        gap,
        paper,
        scenario,
        tmp_path / "freeze.json",
        tmp_path / "freeze.md",
    )

    assert payload["gates"]["paper_evidence_no_open_blockers"]["passed"] is False
    assert payload["gates"]["readme_repositioning_ready"]["passed"] is False
    assert payload["paper_blocking_rows"] == [
        {
            "row_id": "scenario_trigger_pending",
            "expected_status": "passed",
            "observed_status": "pending",
            "analysis": None,
        }
    ]
