from __future__ import annotations

from scripts.audit_development_member_materializer import audit


def test_member_materializer_audit_is_in_memory_and_fail_closed() -> None:
    report = audit()
    assert report["family_count"] == 15
    assert report["instances_generated"] == 0
    assert report["provider_calls"] == report["judge_calls"] == 0
    assert report["status"] == "passed_with_semantic_blockers"
    assert report["blocked_family_count"] > 0
    assert all(row["status"] in {"materializable", "blocked_fail_closed"} for row in report["rows"])

