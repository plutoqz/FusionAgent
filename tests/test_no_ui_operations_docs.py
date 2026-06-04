from __future__ import annotations

from pathlib import Path


def test_no_ui_runbook_documents_evidence_lifecycle_contract() -> None:
    text = Path("docs/no-ui-agent-operations.md").read_text(encoding="utf-8")

    assert "Evidence Lifecycle Contract" in text
    assert "scenario_artifact_manifest.json" in text
    assert "validation_session.json" in text
    assert "raw source caches are disposable" in text
