from __future__ import annotations

from services.source_field_profile_registry import SourceFieldProfileRegistry


def test_registry_resolves_building_height_profile_from_source_specific_id() -> None:
    registry = SourceFieldProfileRegistry()

    profile = registry.get("fields.building.microsoft")

    assert profile.profile_id == "fields.building.microsoft"
    assert profile.theme == "building"
    assert profile.canonical_fields["height_m"].meaning == "building height in meters"
    assert profile.provider_probe_order["height_m"] == ["height", "Height", "HEIGHT", "building_h", "bld_h"]


def test_registry_resolves_road_water_poi_profiles() -> None:
    registry = SourceFieldProfileRegistry()

    assert registry.get("fields.road.overture_transportation").canonical_fields["road_class"].required is True
    assert registry.get("fields.water.hydrorivers_line").canonical_fields["water_class"].meaning == (
        "water classification"
    )
    assert registry.get("fields.poi.gns").canonical_fields["admin_country"].required is False


def test_registry_lists_theme_profile_ids() -> None:
    registry = SourceFieldProfileRegistry()

    assert "fields.building.osm" in registry.profile_ids_for_theme("building")
    assert "fields.poi.gns" in registry.profile_ids_for_theme("poi")
