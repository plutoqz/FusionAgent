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
    waterways = TRACK_B_THEME_CONTRACTS["waterways"]
    poi = TRACK_B_THEME_CONTRACTS["poi"]

    assert building.official_remote_source_ids == (
        "raw.google.building",
        "raw.osm.building",
        "raw.microsoft.building",
    )
    assert "raw.google.building" not in building.manual_preload_source_ids
    assert "raw.openbuildingmap.building" in building.manual_preload_source_ids
    assert "raw.google.open_buildings.vector" in building.manual_preload_source_ids

    assert road.official_remote_source_ids == ("raw.osm.road", "raw.microsoft.road")
    assert "raw.overture.road" in road.manual_preload_source_ids
    assert "raw.overture.transportation" in road.reservation_only_source_ids

    assert water.official_remote_source_ids == ("raw.osm.water", "raw.hydrolakes.water")
    assert water.manual_preload_source_ids == ("raw.local.water",)
    assert water.reservation_only_source_ids == ("raw.overture.water",)
    assert waterways.official_remote_source_ids == ("raw.osm.waterways", "raw.hydrorivers.water")
    assert waterways.manual_preload_source_ids == ("raw.local.pakistan.waterways",)

    assert poi.official_remote_source_ids == ("raw.gns.poi", "raw.google.poi", "raw.osm.poi")
    assert poi.manual_preload_source_ids == ("raw.rh.poi",)
    assert "raw.overture.poi" in poi.reservation_only_source_ids or "raw.overture.places" in poi.reservation_only_source_ids


def test_source_catalog_metadata_carries_track_b_b1_contract_for_live_sources() -> None:
    sources = {source.source_id: source for source in build_data_sources()}

    assert sources["raw.osm.building"].metadata["acquisition_class"] == "official_remote_supported"
    assert sources["raw.google.building"].metadata["acquisition_class"] == "official_remote_supported"
    assert sources["raw.google.building"].metadata["supports_aoi"] is True
    assert sources["raw.google.building"].metadata["materialization_scope"] == "resolved_aoi_clip"
    assert sources["raw.google.building"].metadata["selectable_now"] is True
    assert sources["raw.microsoft.building"].metadata["field_mapping_profile"] == "fields.building.microsoft"
    assert sources["raw.openbuildingmap.building"].metadata["acquisition_class"] == "manual_preload_required"
    assert sources["raw.google.open_buildings.vector"].metadata["acquisition_class"] == "manual_preload_required"

    assert sources["raw.osm.road"].metadata["track_b_theme"] == "road"
    assert sources["raw.microsoft.road"].metadata["acquisition_class"] == "manual_preload_required"
    assert sources["raw.microsoft.road"].metadata["field_mapping_profile"] == "fields.road.osm"
    assert sources["raw.overture.road"].metadata["acquisition_class"] == "manual_preload_required"
    assert sources["raw.overture.transportation"].metadata["acquisition_class"] == "reservation_only"
    assert sources["raw.local.water"].metadata["acquisition_class"] == "manual_preload_required"
    assert sources["raw.osm.waterways"].metadata["field_mapping_profile"] == "fields.waterways.osm"
    assert sources["raw.local.pakistan.waterways"].metadata["field_mapping_profile"] == "fields.waterways.local_osm_like"
    assert sources["raw.hydrorivers.water"].metadata["acquisition_class"] == "official_remote_supported"
    assert sources["raw.hydrolakes.water"].metadata["runtime_status"] == "runtime_candidate"
    assert sources["raw.gns.poi"].metadata["acquisition_class"] == "official_remote_supported"
    assert sources["raw.google.poi"].metadata["acquisition_class"] == "authorized_remote_supported"
    assert sources["raw.google.poi"].metadata["field_mapping_profile"] == "fields.poi.google"
    assert sources["raw.rh.poi"].metadata["field_mapping_profile"] == "fields.poi.rh"

    flood_road = sources["catalog.flood.road"]
    flood_water = sources["catalog.flood.water"]
    flood_waterways = sources["catalog.flood.waterways"]
    generic_poi = sources["catalog.generic.poi"]

    assert flood_road.metadata["component_source_ids"] == ["raw.osm.road", "raw.microsoft.road"]
    assert "raw.overture.road" in flood_road.metadata["track_b_manual_preload_source_ids"]
    assert "raw.overture.transportation" in flood_road.metadata["track_b_reservation_only_source_ids"]
    assert flood_water.metadata["track_b_manual_preload_source_ids"] == ["raw.local.water"]
    assert flood_water.metadata["track_b_official_remote_source_ids"] == ["raw.osm.water", "raw.hydrolakes.water"]
    assert flood_waterways.metadata["track_b_official_remote_source_ids"] == [
        "raw.osm.waterways",
        "raw.hydrorivers.water",
    ]
    assert flood_waterways.metadata["track_b_manual_preload_source_ids"] == ["raw.local.pakistan.waterways"]
    assert generic_poi.metadata["track_b_official_remote_source_ids"] == [
        "raw.gns.poi",
        "raw.google.poi",
        "raw.osm.poi",
    ]
    assert "raw.overture.poi" in generic_poi.metadata["track_b_reservation_only_source_ids"] or "raw.overture.places" in generic_poi.metadata["track_b_reservation_only_source_ids"]


def test_track_b_live_spec_and_readme_index_exist() -> None:
    spec_path = Path(TRACK_B_SOURCE_CONTRACT_REF)
    text = spec_path.read_text(encoding="utf-8")
    readme = Path("docs/superpowers/specs/README.md").read_text(encoding="utf-8")

    assert "raw.overture.transportation" in text
    assert "raw.hydrorivers.water" in text
    assert "raw.hydrolakes.water" in text
    assert "raw.local.pakistan.waterways" in text
    assert "raw.overture.poi" in text or "raw.overture.places" in text
    assert "Data/water/BDI.shp" in text
    assert "Data/water/布隆迪湖泊.shp" in text
    assert "Data/water/Pakistan_Waterways_Data.shp" in text
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
        if source_id in {"raw.overture.transportation", "raw.overture.places", "raw.google.poi", "raw.microsoft.road"}:
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
    assert "raw.osm.waterways" in sources
    assert "raw.local.pakistan.waterways" in sources
    assert "raw.google.poi" in sources


def test_track_b_national_scale_freeze_captures_current_claim_boundary() -> None:
    freeze = json.loads(
        Path("docs/superpowers/specs/2026-05-18-track-b-national-scale-evidence-freeze.json").read_text(
            encoding="utf-8"
        )
    )
    runs = {item["theme"]: item for item in freeze["runs"]}

    assert freeze["tile_config_scope"] == "per_theme"
    assert freeze["theme_tile_metadata"]["road"]["tile_width_m"] == 20_000.0

    assert runs["road"]["claim_state"] == "superseded_historical_evidence"
    assert runs["road"]["stitched_artifact"].endswith("road/stitched_artifact.json")
    assert runs["road"]["tile_count"] == 154
    assert runs["road"]["tile_width_m"] == 20_000.0
    assert runs["road"]["component_source_ids"] == ["raw.osm.road", "raw.microsoft.road"]
    assert runs["road"]["historical_component_source_ids"] == [
        "raw.osm.road",
        "raw.overture.transportation",
    ]
    assert runs["road"]["contract_superseded_by"] == "2026-06-11 autonomous road source contract"
    assert "current road full closure targets OSM+Microsoft road" in runs["road"]["claim_boundary"]
    road_coverage = runs["road"]["component_coverage"]
    assert road_coverage["raw.overture.transportation"]["feature_count"] > 0
    assert road_coverage["raw.overture.transportation"]["coverage_status"] == "compatibility_historical"
    assert (
        road_coverage["raw.overture.transportation"]["source_mode"]
        == "reservation_only_historical_evidence"
    )
    overture_selection = runs["road"]["selected_normalized_sources"]["raw.overture.transportation"]
    assert overture_selection["compatibility_only"] is True
    assert "historical evidence only" in overture_selection["claim_boundary"]
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
