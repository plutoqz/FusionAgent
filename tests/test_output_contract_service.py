from __future__ import annotations

from schemas.task_kind import TaskKind
from services.output_contract_service import get_domain_output_contract


def test_road_contract_requires_runtime_lineage_and_name_fields() -> None:
    contract = get_domain_output_contract(TaskKind.road)

    assert contract.contract_id == "contract.road.fused.v1"
    assert contract.required_fields == [
        "geometry",
        "fusion_source",
        "match_role",
        "road_class",
        "source_layer",
        "name",
        "osm_name",
        "road_name",
    ]
    assert contract.preserve_if_present == ["source_feature_id", "surface", "lanes", "ref"]
    assert contract.field_null_rate_thresholds["name"] == 0.80
    assert contract.field_null_rate_thresholds["osm_name"] == 0.90
    assert contract.field_null_rate_thresholds["road_name"] == 0.90


def test_building_contract_tracks_height_completeness() -> None:
    contract = get_domain_output_contract(TaskKind.building)

    assert "geometry" in contract.required_fields
    assert contract.field_null_rate_thresholds["height_m"] == 0.50
    assert contract.field_null_rate_thresholds["Height"] == 0.50


def test_contract_applies_source_expected_null_rate_as_threshold_override() -> None:
    contract = get_domain_output_contract(
        TaskKind.road,
        source_expected_null_rates={"name": 0.95},
    )

    assert contract.field_null_rate_thresholds["name"] == 0.95
