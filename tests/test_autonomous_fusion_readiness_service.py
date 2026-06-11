from __future__ import annotations

import pytest

from services.autonomous_fusion_readiness_service import classify_autonomous_readiness


def test_building_full_closure_requires_google_ms_osm_and_road() -> None:
    result = classify_autonomous_readiness(
        job_type="building",
        component_coverage={
            "raw.google.building": {"coverage_status": "available", "feature_count": 10},
            "raw.microsoft.building": {"coverage_status": "available", "feature_count": 11},
            "raw.osm.building": {"coverage_status": "available", "feature_count": 12},
            "raw.osm.road": {"coverage_status": "available", "feature_count": 4},
        },
        source_attempts=[],
    )

    assert result["status"] == "full_autonomous_closure"
    assert result["missing_required_source_ids"] == []


def test_poi_missing_google_is_degraded_not_full_success() -> None:
    result = classify_autonomous_readiness(
        job_type="poi",
        component_coverage={
            "raw.gns.poi": {"coverage_status": "available", "feature_count": 5},
            "raw.osm.poi": {"coverage_status": "available", "feature_count": 5},
        },
        source_attempts=[
            {
                "source_id": "raw.google.poi",
                "status": "network_failed",
                "fault_class": "NETWORK_FAILED",
                "external_uncontrollable": True,
            }
        ],
    )

    assert result["status"] == "degraded_external"
    assert result["missing_required_source_ids"] == ["raw.google.poi"]
    assert result["external_uncontrollable_source_ids"] == ["raw.google.poi"]


def test_poi_missing_google_without_external_fault_is_system_failure() -> None:
    result = classify_autonomous_readiness(
        job_type="poi",
        component_coverage={
            "raw.gns.poi": {"coverage_status": "available", "feature_count": 5},
            "raw.osm.poi": {"coverage_status": "available", "feature_count": 5},
        },
        source_attempts=[],
    )

    assert result["status"] == "system_failure"
    assert result["missing_required_source_ids"] == ["raw.google.poi"]


def test_road_osm_and_microsoft_available_is_full_closure() -> None:
    result = classify_autonomous_readiness(
        job_type="road",
        component_coverage={
            "raw.osm.road": {"coverage_status": "available", "feature_count": 7},
            "raw.microsoft.road": {"coverage_status": "available", "feature_count": 3},
        },
        source_attempts=[],
    )

    assert result["status"] == "full_autonomous_closure"
    assert result["required_source_ids"] == ["raw.osm.road", "raw.microsoft.road"]


def test_water_polygon_uses_osm_water_and_hydrolakes_contract() -> None:
    result = classify_autonomous_readiness(
        job_type="water_polygon",
        component_coverage={
            "raw.osm.water": {"coverage_status": "available", "feature_count": 2},
            "raw.hydrolakes.water": {"coverage_status": "available", "feature_count": 1},
            "raw.hydrorivers.water": {"coverage_status": "missing", "feature_count": 0},
        },
        source_attempts=[],
    )

    assert result["status"] == "full_autonomous_closure"
    assert result["required_source_ids"] == ["raw.osm.water", "raw.hydrolakes.water"]


def test_geonames_alias_satisfies_gns_poi_requirement() -> None:
    result = classify_autonomous_readiness(
        job_type="poi",
        component_coverage={
            "raw.geonames.poi": {"coverage_status": "available", "feature_count": 4},
            "raw.google.poi": {"coverage_status": "available", "feature_count": 4},
            "raw.osm.poi": {"coverage_status": "available", "feature_count": 4},
        },
        source_attempts=[],
    )

    assert result["status"] == "full_autonomous_closure"
    assert result["missing_required_source_ids"] == []


def test_unknown_job_type_is_system_failure_not_full_closure() -> None:
    result = classify_autonomous_readiness(
        job_type="unknown_theme",
        component_coverage={},
        source_attempts=[],
    )

    assert result["status"] == "system_failure"
    assert result["required_source_ids"] == []
    assert result["missing_required_source_ids"] == ["<unknown_job_type:unknown_theme>"]


@pytest.mark.parametrize(
    ("job_type", "coverage", "required"),
    [
        (
            "catalog.generic.poi",
            {
                "raw.geonames.poi": {"coverage_status": "available", "feature_count": 4},
                "raw.google.poi": {"coverage_status": "available", "feature_count": 4},
                "raw.osm.poi": {"coverage_status": "available", "feature_count": 4},
            },
            ["raw.gns.poi", "raw.google.poi", "raw.osm.poi"],
        ),
        (
            "catalog.flood.road",
            {
                "raw.osm.road": {"coverage_status": "available", "feature_count": 4},
                "raw.microsoft.road": {"coverage_status": "available", "feature_count": 4},
            },
            ["raw.osm.road", "raw.microsoft.road"],
        ),
        (
            "catalog.flood.water",
            {
                "raw.osm.water": {"coverage_status": "available", "feature_count": 4},
                "raw.hydrolakes.water": {"coverage_status": "available", "feature_count": 4},
            },
            ["raw.osm.water", "raw.hydrolakes.water"],
        ),
        (
            "catalog.flood.waterways",
            {
                "raw.osm.waterways": {"coverage_status": "available", "feature_count": 4},
                "raw.hydrorivers.water": {"coverage_status": "available", "feature_count": 4},
            },
            ["raw.osm.waterways", "raw.hydrorivers.water"],
        ),
        (
            "catalog.flood.building",
            {
                "raw.google.building": {"coverage_status": "available", "feature_count": 4},
                "raw.microsoft.building": {"coverage_status": "available", "feature_count": 4},
                "raw.osm.building": {"coverage_status": "available", "feature_count": 4},
                "raw.osm.road": {"coverage_status": "available", "feature_count": 4},
            },
            ["raw.google.building", "raw.microsoft.building", "raw.osm.building", "raw.osm.road"],
        ),
    ],
)
def test_catalog_aliases_use_theme_required_source_contracts(
    job_type: str,
    coverage: dict[str, dict[str, object]],
    required: list[str],
) -> None:
    result = classify_autonomous_readiness(
        job_type=job_type,
        component_coverage=coverage,
        source_attempts=[],
    )

    assert result["status"] == "full_autonomous_closure"
    assert result["required_source_ids"] == required
    assert result["missing_required_source_ids"] == []
