import json
from pathlib import Path

from kg.source_catalog import build_data_sources
from kg.track_b_source_contract import (
    TRACK_B_SOURCE_CONTRACT_REF,
    TRACK_B_SOURCE_CONTRACTS,
    TRACK_B_THEME_CONTRACTS,
)


def test_track_b_theme_contract_locks_first_wave_source_matrix() -> None:
    building = TRACK_B_THEME_CONTRACTS["building"]
    road = TRACK_B_THEME_CONTRACTS["road"]
    water = TRACK_B_THEME_CONTRACTS["water"]
    poi = TRACK_B_THEME_CONTRACTS["poi"]

    assert building.official_remote_source_ids == ("raw.osm.building", "raw.microsoft.building")
    assert "raw.google.building" in building.manual_preload_source_ids
    assert "raw.openbuildingmap.building" in building.manual_preload_source_ids

    assert road.official_remote_source_ids == ("raw.osm.road",)
    assert "raw.overture.road" in road.manual_preload_source_ids

    assert water.official_remote_source_ids == ("raw.osm.water",)
    assert "raw.hydrorivers.water" in water.manual_preload_source_ids
    assert "raw.hydrolakes.water" in water.manual_preload_source_ids
    assert water.reservation_only_source_ids == ("raw.overture.water",)

    assert poi.official_remote_source_ids == ("raw.osm.poi",)
    assert poi.manual_preload_source_ids == ("raw.gns.poi", "raw.rh.poi")
    assert "raw.overture.poi" in poi.reservation_only_source_ids or "raw.overture.places" in poi.reservation_only_source_ids


def test_source_catalog_metadata_carries_track_b_b1_contract_for_live_sources() -> None:
    sources = {source.source_id: source for source in build_data_sources()}

    assert sources["raw.osm.building"].metadata["acquisition_class"] == "official_remote_supported"
    assert sources["raw.google.building"].metadata["acquisition_class"] == "manual_preload_required"
    assert sources["raw.microsoft.building"].metadata["field_mapping_profile"] == "fields.building.microsoft"

    assert sources["raw.osm.road"].metadata["track_b_theme"] == "road"
    assert sources["raw.overture.road"].metadata["acquisition_class"] == "manual_preload_required"
    assert sources["raw.overture.transportation"].metadata["acquisition_class"] == "official_remote_supported"
    assert sources["raw.local.water"].metadata["acquisition_class"] == "manual_preload_required"
    assert sources["raw.hydrorivers.water"].metadata["runtime_status"] == "runtime_candidate"
    assert sources["raw.hydrolakes.water"].metadata["runtime_status"] == "runtime_candidate"
    assert sources["raw.gns.poi"].metadata["acquisition_class"] == "manual_preload_required"
    assert sources["raw.rh.poi"].metadata["field_mapping_profile"] == "fields.poi.rh"

    flood_road = sources["catalog.flood.road"]
    flood_water = sources["catalog.flood.water"]
    generic_poi = sources["catalog.generic.poi"]

    assert flood_road.metadata["component_source_ids"] == ["raw.osm.road", "raw.overture.transportation"]
    assert "raw.overture.road" in flood_road.metadata["track_b_manual_preload_source_ids"]
    assert flood_water.metadata["track_b_manual_preload_source_ids"] == [
        "raw.local.water",
        "raw.hydrorivers.water",
        "raw.hydrolakes.water",
    ]
    assert "raw.overture.poi" in generic_poi.metadata["track_b_reservation_only_source_ids"] or "raw.overture.places" in generic_poi.metadata["track_b_reservation_only_source_ids"]


def test_track_b_live_spec_and_readme_index_exist() -> None:
    spec_path = Path(TRACK_B_SOURCE_CONTRACT_REF)
    text = spec_path.read_text(encoding="utf-8")
    readme = Path("docs/superpowers/specs/README.md").read_text(encoding="utf-8")

    assert "raw.overture.road" in text
    assert "raw.hydrorivers.water" in text
    assert "raw.hydrolakes.water" in text
    assert "raw.overture.poi" in text or "raw.overture.places" in text
    assert "Data/water/BDI.shp" in text
    assert "Data/water/布隆迪湖泊.shp" in text
    assert "Data/POI/**/GNS.shp" in text
    assert "Data/POI/**/RH.shp" in text
    assert "official_remote_supported" in text
    assert "manual_preload_required" in text
    assert "reservation_only" in text
    assert "2026-05-18-track-b-national-source-matrix.md" in readme
    assert "2026-05-18-track-b-national-scale-evidence-freeze.json" in readme


def test_track_b_live_spec_covers_all_locked_source_contracts() -> None:
    text = Path(TRACK_B_SOURCE_CONTRACT_REF).read_text(encoding="utf-8")

    for source_id in TRACK_B_SOURCE_CONTRACTS:
        if source_id in {"raw.overture.transportation", "raw.overture.places"}:
            continue
        assert source_id in text


def test_track_b_operations_doc_mentions_manual_preload_source_asset_support() -> None:
    text = Path("docs/v2-operations.md").read_text(encoding="utf-8")

    assert "raw.overture.road" in text
    assert "raw.hydrorivers.water" in text
    assert "raw.hydrolakes.water" in text
    assert "raw.gns.poi" in text
    assert "manual-preload" in text


def test_source_catalog_exposes_locked_track_b_b2_raw_sources() -> None:
    sources = {source.source_id for source in build_data_sources()}

    assert "raw.overture.road" in sources
    assert "raw.overture.transportation" in sources
    assert "raw.hydrorivers.water" in sources
    assert "raw.hydrolakes.water" in sources


def test_track_b_national_scale_freeze_captures_current_claim_boundary() -> None:
    freeze = json.loads(
        Path("docs/superpowers/specs/2026-05-18-track-b-national-scale-evidence-freeze.json").read_text(
            encoding="utf-8"
        )
    )
    runs = {item["theme"]: item for item in freeze["runs"]}

    assert runs["road"]["claim_state"] == "national_scale_partial_reference"
    assert runs["road"]["stitched_artifact"].endswith("road/stitched_artifact.json")
    road_coverage = runs["road"]["component_coverage"]
    road_ref_id = "raw.overture.transportation" if "raw.overture.transportation" in road_coverage else "raw.overture.road"
    assert road_coverage[road_ref_id]["source_mode"] == "missing_optional_ref"

    assert runs["water"]["claim_state"] == "national_scale_supported"
    assert runs["water"]["stitched_artifact"].endswith("water/stitched_artifact.json")
    assert "raw.hydrorivers.water" in runs["water"]["supplemental_normalized_sources"]
    assert "raw.hydrolakes.water" in runs["water"]["supplemental_normalized_sources"]

    assert runs["poi"]["claim_state"] == "national_scale_supported"
    assert runs["poi"]["stitched_artifact"].endswith("poi/stitched_artifact.json")
    assert "raw.rh.poi" in runs["poi"]["supplemental_normalized_sources"]
