from pathlib import Path


def test_consolidation_backlog_prioritizes_core_next_work() -> None:
    text = Path(
        "docs/superpowers/specs/2026-05-06-consolidation-backlog.md"
    ).read_text(encoding="utf-8")

    assert "P0" in text
    assert "ToolSpec registry" in text
    assert "KG grounding report" in text
    assert "unsupported-intent rejection" in text
    assert "telemetry" in text
    assert "checkpoint recovery inspection" in text

