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
    assert "maturity_target_present" in (tmp_path / "freeze.md").read_text(encoding="utf-8")
