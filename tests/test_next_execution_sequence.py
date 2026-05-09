from pathlib import Path


def test_next_sequence_orders_work_from_core_next_to_optional() -> None:
    text = Path(
        "docs/superpowers/specs/2026-05-06-next-execution-sequence.md"
    ).read_text(encoding="utf-8")

    assert "Stage 1" in text
    assert "Stage 2" in text
    assert "Stage 3" in text
    assert "Do not start P1 before P0 evidence closes" in text

