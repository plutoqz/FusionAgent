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


def test_no_ui_runbook_documents_durable_learning_v2_policy_hints() -> None:
    text = Path("docs/no-ui-agent-operations.md").read_text(encoding="utf-8")

    assert "bounded policy hint" in text
    assert "condition_key" in text
    assert "time_decayed_score" in text
    assert "quality_gate_pass_rate" in text
    assert "avg_latency_seconds" in text
    assert "trend" in text
    assert "adjustment" in text
    assert "not autonomous self-optimization" in text


def test_no_ui_runbook_documents_kg_seed_manifest_governance() -> None:
    text = Path("docs/no-ui-agent-operations.md").read_text(encoding="utf-8")

    assert "kg/seed.py" in text
    assert "kg/seed_manifest.generated.json" in text
    assert "schema_version" in text
    assert "content_hash" in text
    assert "scripts/export_kg_seed_manifest.py --check" in text
    assert "runtime default has not been flipped" in text
