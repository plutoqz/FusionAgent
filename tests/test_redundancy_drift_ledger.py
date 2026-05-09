from pathlib import Path


def test_redundancy_ledger_lists_action_for_each_drift_candidate() -> None:
    text = Path(
        "docs/superpowers/specs/2026-05-06-redundancy-and-drift-ledger.md"
    ).read_text(encoding="utf-8")

    assert "artifact reuse branches" in text
    assert "Benin script sprawl" in text
    assert "trajectory-to-road wording" in text
    assert "Action:" in text

