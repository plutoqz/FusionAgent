import json
from pathlib import Path

import pytest


def test_national_source_matrix_locks_track_b_first_batch_sources() -> None:
    payload = json.loads(
        Path(
            "docs/superpowers/specs/2026-05-18-national-source-matrix.json"
        ).read_text(encoding="utf-8")
    )

    building = {item["source_id"]: item for item in payload["themes"]["building"]}
    road = {item["source_id"]: item for item in payload["themes"]["road"]}
    water = {item["source_id"]: item for item in payload["themes"]["water"]}
    poi = {item["source_id"]: item for item in payload["themes"]["poi"]}

    assert "next_implementation" in payload["delivery_stage_vocab"]
    assert "official_remote_supported" in payload["source_mode_vocab"]
    assert "claim_boundary" in payload["required_fields"]

    assert payload["bundle_targets"]["building"]["minimum_auto_sources"] == [
        "raw.osm.building",
        "raw.microsoft.building",
    ]
    assert payload["bundle_targets"]["road"]["minimum_sources"] == [
        "raw.osm.road",
        "raw.overture.transportation",
    ]
    assert payload["bundle_targets"]["water"]["line_sources"] == [
        "raw.osm.waterways",
        "raw.hydrorivers.water",
    ]
    assert payload["bundle_targets"]["water"]["polygon_sources"] == [
        "raw.osm.water",
        "raw.hydrolakes.water",
    ]
    assert payload["bundle_targets"]["poi"]["minimum_sources"] == [
        "raw.osm.poi",
        "raw.gns.poi",
    ]

    assert building["raw.osm.building"]["delivery_stage"] == "current_runtime"
    assert building["raw.microsoft.building"]["source_mode"] == "official_remote_supported"
    assert building["raw.google.building"]["source_mode"] == "manual_preload_required"
    assert building["raw.local.microsoft.building"]["claim_boundary"] == "local_reference_only"

    assert road["raw.overture.transportation"]["delivery_stage"] == "next_implementation"
    assert road["raw.overture.transportation"]["field_mapping_profile"] == "road.line.v1"

    assert water["raw.hydrorivers.water"]["delivery_stage"] == "next_implementation"
    assert water["raw.hydrolakes.water"]["delivery_stage"] == "next_implementation"
    assert water["raw.overture.water"]["delivery_stage"] == "deferred"

    assert poi["raw.gns.poi"]["claim_boundary"] == "bounded_runtime_now"
    assert poi["raw.rh.poi"]["delivery_stage"] == "optional_reference"
    assert poi["raw.overture.places"]["delivery_stage"] == "deferred"

    assert "building.vector.v1" in payload["field_mapping_profiles"]
    assert "road.line.v1" in payload["field_mapping_profiles"]
    assert "water.line_polygon.v1" in payload["field_mapping_profiles"]
    assert "poi.point.v1" in payload["field_mapping_profiles"]


def test_national_source_matrix_is_registered_in_live_specs_index() -> None:
    readme = Path("docs/superpowers/specs/README.md").read_text(encoding="utf-8")

    assert "2026-05-18-national-source-matrix.md" in readme
    assert "2026-05-18-national-source-matrix.json" in readme


def test_geonames_alias_is_documented_as_gns_poi_alias() -> None:
    from kg.track_b_source_contract import get_track_b_source_contract

    canonical = get_track_b_source_contract("raw.gns.poi")
    alias = get_track_b_source_contract("raw.geonames.poi")

    assert canonical is not None
    assert alias is not None
    assert alias.theme == "poi"
    assert alias.field_mapping_profile == canonical.field_mapping_profile
    assert "GNS" in alias.notes
    assert "GeoNames" in alias.notes


def test_runtime_alias_paths_rejects_duplicate_runtime_aliases() -> None:
    from services.runtime_source_aliases import POI_SOURCE_ALIASES, alias_paths

    with pytest.raises(ValueError, match=r"GNG.*raw\.gns\.poi.*raw\.geonames\.poi"):
        alias_paths(
            {
                "raw.gns.poi": Path("gns.gpkg"),
                "raw.geonames.poi": Path("geonames.gpkg"),
            },
            POI_SOURCE_ALIASES,
        )
