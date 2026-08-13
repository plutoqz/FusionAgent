from pathlib import Path

from scripts.audit_research_deterministic_readiness import audit_deterministic_readiness


MANIFEST = Path(__file__).parents[1] / "docs" / "current" / "research-case-manifest-v1.json"


def test_deterministic_outputs_share_the_frozen_planning_contract() -> None:
    report = audit_deterministic_readiness(MANIFEST)

    assert report["run_count"] == 18
    assert report["shared_schema_valid_count"] == 18
    assert report["shared_schema_invalid_count"] == 0
    assert report["comparison_ready"] is True
    assert report["blockers"] == []
