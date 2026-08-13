from pathlib import Path

from scripts.audit_research_deterministic_readiness import audit_deterministic_readiness


MANIFEST = Path(__file__).parents[1] / "docs" / "current" / "research-case-manifest-v1.json"


def test_current_deterministic_outputs_are_reported_as_not_comparison_ready() -> None:
    report = audit_deterministic_readiness(MANIFEST)

    assert report["run_count"] == 18
    assert report["shared_schema_valid_count"] == 0
    assert report["shared_schema_invalid_count"] == 18
    assert report["comparison_ready"] is False
    assert "six_group_common_evaluator_contract_not_satisfied" in report["blockers"]
