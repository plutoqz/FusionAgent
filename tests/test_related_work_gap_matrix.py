import json
from pathlib import Path


def test_related_work_matrix_covers_target_papers_and_gap_fields() -> None:
    payload = json.loads(
        Path(
            "docs/superpowers/specs/2026-05-06-related-work-gap-matrix.json"
        ).read_text(encoding="utf-8")
    )

    assert "Geo-Agent" in payload["papers"]
    assert "CyVerACT" in payload["papers"]
    assert "OntoLLM" in payload["papers"]
    assert "PathMind" in payload["papers"]
    assert "UniAI-GraphRAG" in payload["papers"]
    assert "our_advantage" in payload["fields"]
    assert "borrow_direction" in payload["fields"]

