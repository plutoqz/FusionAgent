import json
from pathlib import Path


def test_thesis_related_work_matrix_covers_live_papers_and_fields() -> None:
    payload = json.loads(
        Path(
            "docs/superpowers/specs/2026-05-13-thesis-related-work-matrix.json"
        ).read_text(encoding="utf-8")
    )

    assert "Geo-Agent" in payload["papers"]
    assert "CyVerACT" in payload["papers"]
    assert "OntoLLM" in payload["papers"]
    assert "PathMind" in payload["papers"]
    assert "UniAI-GraphRAG" in payload["papers"]
    assert "closest_overlap" in payload["fields"]
    assert "our_difference" in payload["fields"]
    assert "borrowed_idea" in payload["fields"]
    assert "non_comparable_boundary" in payload["fields"]


def test_thesis_related_work_markdown_keeps_boundary_language() -> None:
    text = Path(
        "docs/superpowers/specs/2026-05-13-thesis-related-work-matrix.md"
    ).read_text(encoding="utf-8")

    assert "Geo-Agent" in text
    assert "CyVerACT" in text
    assert "UniAI-GraphRAG" in text
    assert "Non-comparable boundary" in text
    assert "do not position FusionAgent as a general GIS copilot" in text
