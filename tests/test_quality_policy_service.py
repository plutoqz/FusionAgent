from __future__ import annotations

from schemas.task_kind import TaskKind
from schemas.degradation import DegradationContext, DegradationLevel
from services.quality_policy_service import adapt_policy_for_degradation, get_quality_policy


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
    assert checks["dangle_endpoint_rate_per_100km"].operator == "lte"
    assert checks["dangle_endpoint_rate_per_100km"].threshold == 500.0


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
    assert checks["dangle_endpoint_rate_per_100km"].operator == "lte"
    assert checks["dangle_endpoint_rate_per_100km"].threshold == 500.0


def test_default_poi_quality_policy_omits_topology_hard_checks() -> None:
    policy = get_quality_policy(task_kind=TaskKind.poi, policy_id=None)

    check_ids = {check.check_id for check in policy.checks}

    assert "zero_length_geometry_count" not in check_ids
    assert "dangle_endpoint_rate_per_100km" not in check_ids
    assert "self_intersection_count" not in check_ids
    assert "sliver_polygon_count" not in check_ids


def test_adapt_policy_for_external_single_source_degradation_softens_lineage_and_balance() -> None:
    policy = get_quality_policy(task_kind=TaskKind.road)
    context = DegradationContext(
        degraded=True,
        level=DegradationLevel.external_uncontrollable,
        available_sources=["raw.osm.road"],
        missing_sources=["raw.microsoft.road"],
        external_uncontrollable_sources=["raw.microsoft.road"],
    )

    adapted, adaptations = adapt_policy_for_degradation(
        policy,
        task_kind=TaskKind.road,
        component_coverage={
            "raw.osm.road": {"feature_count": 10, "coverage_status": "available"},
            "raw.microsoft.road": {
                "feature_count": 0,
                "coverage_status": "missing",
                "external_uncontrollable": True,
            },
        },
        degradation_context=context,
    )

    checks = {check.check_id: check for check in adapted.checks}
    assert adapted.policy_id == "quality.default.road.v1.adapted"
    assert checks["multi_source_lineage"].severity == "soft"
    assert checks["source_contribution_balance"].severity == "soft"
    assert checks["duplicate_geometry_rate"].severity == "hard"
    assert checks["invalid_geometry_rate"].severity == "hard"
    assert {item["check_id"] for item in adaptations} == {"multi_source_lineage", "source_contribution_balance"}


def test_adapt_policy_for_external_two_source_degradation_widens_balance_only() -> None:
    policy = get_quality_policy(task_kind=TaskKind.building)
    context = DegradationContext(
        degraded=True,
        level=DegradationLevel.external_uncontrollable,
        available_sources=["raw.osm.building", "raw.microsoft.building"],
        missing_sources=["raw.google.building"],
        external_uncontrollable_sources=["raw.google.building"],
    )

    adapted, adaptations = adapt_policy_for_degradation(
        policy,
        task_kind=TaskKind.building,
        component_coverage={
            "raw.osm.building": {"feature_count": 10, "coverage_status": "available"},
            "raw.microsoft.building": {"feature_count": 3, "coverage_status": "available"},
            "raw.google.building": {
                "feature_count": 0,
                "coverage_status": "missing",
                "external_uncontrollable": True,
            },
        },
        degradation_context=context,
    )

    checks = {check.check_id: check for check in adapted.checks}
    assert checks["multi_source_lineage"].severity == "hard"
    assert checks["source_contribution_balance"].severity == "hard"
    assert checks["source_contribution_balance"].threshold == 0.95
    assert adaptations == [
        {
            "check_id": "source_contribution_balance",
            "reason": "reduced_source_mix_external_degradation",
            "original_threshold": 0.75,
            "adapted_threshold": 0.95,
            "original_severity": "hard",
            "adapted_severity": "hard",
            "missing_sources": ["raw.google.building"],
        }
    ]
