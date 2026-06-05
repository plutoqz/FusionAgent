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
    assert "self_intersection_count" in check_ids
    assert "sliver_polygon_count" in check_ids


def test_default_road_quality_policy_contains_line_topology_checks() -> None:
    policy = get_quality_policy(task_kind=TaskKind.road, policy_id=None)

    checks = {check.check_id: check for check in policy.checks}

    assert checks["zero_length_geometry_count"].operator == "eq"
    assert checks["zero_length_geometry_count"].threshold == 0
    assert checks["dangle_endpoint_count"].operator == "lte"


def test_default_water_polygon_quality_policy_contains_polygon_topology_checks() -> None:
    policy = get_quality_policy(task_kind=TaskKind.water_polygon, policy_id=None)

    checks = {check.check_id: check for check in policy.checks}

    assert checks["self_intersection_count"].operator == "eq"
    assert checks["self_intersection_count"].threshold == 0
    assert checks["sliver_polygon_count"].operator == "lte"


def test_default_waterways_quality_policy_contains_line_topology_checks() -> None:
    policy = get_quality_policy(task_kind=TaskKind.waterways, policy_id=None)

    checks = {check.check_id: check for check in policy.checks}

    assert checks["zero_length_geometry_count"].operator == "eq"
    assert checks["zero_length_geometry_count"].threshold == 0
    assert checks["dangle_endpoint_count"].operator == "lte"
    assert checks["dangle_endpoint_count"].threshold == 2


def test_default_poi_quality_policy_omits_topology_hard_checks() -> None:
    policy = get_quality_policy(task_kind=TaskKind.poi, policy_id=None)

    check_ids = {check.check_id for check in policy.checks}

    assert "zero_length_geometry_count" not in check_ids
    assert "dangle_endpoint_count" not in check_ids
    assert "self_intersection_count" not in check_ids
    assert "sliver_polygon_count" not in check_ids
