from __future__ import annotations

from schemas.task_kind import TaskKind
from services.quality_policy_service import get_quality_policy


def test_default_building_quality_policy_contains_spatial_checks() -> None:
    policy = get_quality_policy(task_kind=TaskKind.building, policy_id=None)

    check_ids = [check.check_id for check in policy.checks]

    assert policy.policy_id == "quality.default.building.v1"
    assert "duplicate_geometry_rate" in check_ids
    assert "invalid_geometry_rate" in check_ids
    assert "source_contribution_balance" in check_ids
