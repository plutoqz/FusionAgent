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

    assert road.official_remote_source_ids == ("raw.osm.road", "raw.overture.transportation")
    assert "raw.overture.road" in road.manual_preload_source_ids

    assert water.official_remote_source_ids == (
        "raw.osm.water",
        "raw.hydrorivers.water",
        "raw.hydrolakes.water",
    )
    assert water.manual_preload_source_ids == ("raw.local.water",)
    assert water.reservation_only_source_ids == ("raw.overture.water",)

    assert poi.official_remote_source_ids == ("raw.osm.poi", "raw.gns.poi")
    assert poi.manual_preload_source_ids == ("raw.rh.poi",)
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
    assert sources["raw.hydrorivers.water"].metadata["acquisition_class"] == "official_remote_supported"
    assert sources["raw.hydrolakes.water"].metadata["runtime_status"] == "runtime_candidate"
    assert sources["raw.gns.poi"].metadata["acquisition_class"] == "official_remote_supported"
    assert sources["raw.rh.poi"].metadata["field_mapping_profile"] == "fields.poi.rh"

    flood_road = sources["catalog.flood.road"]
    flood_water = sources["catalog.flood.water"]
    generic_poi = sources["catalog.generic.poi"]

    assert flood_road.metadata["component_source_ids"] == ["raw.osm.road", "raw.overture.transportation"]
    assert "raw.overture.road" in flood_road.metadata["track_b_manual_preload_source_ids"]
    assert flood_water.metadata["track_b_manual_preload_source_ids"] == ["raw.local.water"]
    assert flood_water.metadata["track_b_official_remote_source_ids"] == [
        "raw.osm.water",
        "raw.hydrorivers.water",
        "raw.hydrolakes.water",
    ]
    assert generic_poi.metadata["track_b_official_remote_source_ids"] == ["raw.osm.poi", "raw.gns.poi"]
    assert "raw.overture.poi" in generic_poi.metadata["track_b_reservation_only_source_ids"] or "raw.overture.places" in generic_poi.metadata["track_b_reservation_only_source_ids"]


def test_track_b_live_spec_and_readme_index_exist() -> None:
    spec_path = Path(TRACK_B_SOURCE_CONTRACT_REF)
    text = spec_path.read_text(encoding="utf-8")
    readme = Path("docs/superpowers/specs/README.md").read_text(encoding="utf-8")

    assert "raw.overture.transportation" in text
    assert "raw.hydrorivers.water" in text
    assert "raw.hydrolakes.water" in text
    assert "raw.overture.poi" in text or "raw.overture.places" in text
    assert "Data/water/BDI.shp" in text
    assert "Data/water/布隆迪湖泊.shp" in text
    assert "geonames.nga.mil/geonames/GNSData/data/data.json" in text
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

    assert "raw.overture.transportation" in text
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

    assert freeze["tile_config_scope"] == "per_theme"
    assert freeze["theme_tile_metadata"]["road"]["tile_width_m"] == 20_000.0

    assert runs["road"]["claim_state"] == "national_scale_supported"
    assert runs["road"]["stitched_artifact"].endswith("road/stitched_artifact.json")
    assert runs["road"]["tile_count"] == 154
    assert runs["road"]["tile_width_m"] == 20_000.0
    assert runs["road"]["component_source_ids"] == ["raw.osm.road", "raw.overture.transportation"]
    road_coverage = runs["road"]["component_coverage"]
    assert road_coverage["raw.overture.transportation"]["feature_count"] > 0
    assert road_coverage["raw.overture.transportation"]["coverage_status"] == "available"
    assert "raw.overture.transportation" in runs["road"]["selected_normalized_sources"]
    assert runs["road"]["artifact_metrics"]["feature_count"] > 0

    assert runs["water"]["claim_state"] == "national_scale_supported"
    assert runs["water"]["stitched_artifact"].endswith("water/stitched_artifact.json")
    assert runs["water"]["component_source_ids"] == ["raw.osm.water", "raw.hydrolakes.water"]
    assert "raw.hydrolakes.water" in runs["water"]["selected_normalized_sources"]
    assert "raw.hydrorivers.water" in runs["water"]["supplemental_normalized_sources"]

    assert runs["poi"]["claim_state"] == "national_scale_supported"
    assert runs["poi"]["stitched_artifact"].endswith("poi/stitched_artifact.json")
    assert "raw.rh.poi" in runs["poi"]["supplemental_normalized_sources"]


def test_track_b_freezes_use_repo_relative_paths_and_cover_smoke_themes() -> None:
    national_freeze = json.loads(
        Path("docs/superpowers/specs/2026-05-18-track-b-national-scale-evidence-freeze.json").read_text(
            encoding="utf-8"
        )
    )
    assert national_freeze["evidence_root"].startswith("runs/")
    for run in national_freeze["runs"]:
        assert run["artifact_path"].startswith("runs/")
        assert run["stitched_artifact"].startswith("runs/")
        assert run["inspection_summary"].startswith("runs/")
        assert run["selected_sources"].startswith("runs/")
        assert run["source_profile_snapshot"].startswith("runs/")
        assert run["normalization_summary"].startswith("runs/")
        assert run["tile_manifest"].startswith("runs/")
        assert run["timing"].startswith("runs/")
        for coverage in run["component_coverage"].values():
            path = coverage.get("path")
            if path:
                assert str(path).startswith("runs/")
        for artifact_map in (run["selected_normalized_sources"], run["supplemental_normalized_sources"]):
            for item in artifact_map.values():
                artifact_path = item.get("artifact_path")
                if artifact_path:
                    assert str(artifact_path).startswith("runs/")

    smoke_freeze = json.loads(
        Path("docs/superpowers/specs/2026-05-18-track-b-smoke-evidence-freeze-8010.json").read_text(
            encoding="utf-8"
        )
    )
    smoke_runs = {item["theme"]: item for item in smoke_freeze["runs"]}
    assert {"building", "road", "water", "poi"}.issubset(smoke_runs)
    assert smoke_freeze["evidence_root"].startswith("runs/")
    for run in smoke_freeze["runs"]:
        assert run["evidence_dir"].startswith("runs/")
        assert run["inspection_summary"].startswith("runs/")
        assert str(run["artifact_path"]).startswith("runs")
