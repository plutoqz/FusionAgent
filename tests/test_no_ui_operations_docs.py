from __future__ import annotations

from pathlib import Path


def test_no_ui_runbook_documents_evidence_lifecycle_contract() -> None:
    text = Path("docs/no-ui-agent-operations.md").read_text(encoding="utf-8")

    assert "Evidence Lifecycle Contract" in text
    assert "scenario_artifact_manifest.json" in text
    assert "validation_session.json" in text
    assert "raw source caches are disposable" in text


def test_no_ui_runbook_documents_grounding_gate_modes() -> None:
    text = Path("docs/no-ui-agent-operations.md").read_text(encoding="utf-8")

    assert "GEOFUSION_PLAN_GROUNDING_MODE" in text
    assert "`report`" in text
    assert "`warn`" in text
    assert "`enforce`" in text
    assert "plan_grounding_rejected" in text


def test_no_ui_runbook_documents_quality_policy_outputs() -> None:
    text = Path("docs/no-ui-agent-operations.md").read_text(encoding="utf-8")

    assert "quality_policy_id" in text
    assert "duplicate_geometry_rate" in text
    assert "invalid_geometry_rate" in text
    assert "source_contribution_balance" in text
