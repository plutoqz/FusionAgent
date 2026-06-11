from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


TRACK_B_SOURCE_CONTRACT_REF = "docs/superpowers/specs/2026-05-18-track-b-national-source-matrix.md"


@dataclass(frozen=True)
class TrackBSourceContract:
    source_id: str
    theme: str
    role: str
    acquisition_class: str
    format_hint: str
    clip_strategy: str
    field_mapping_profile: str
    license_boundary: str
    runtime_status: str
    notes: str = ""


@dataclass(frozen=True)
class TrackBThemeContract:
    theme: str
    official_remote_source_ids: Tuple[str, ...]
    manual_preload_source_ids: Tuple[str, ...]
    reservation_only_source_ids: Tuple[str, ...]
    current_catalog_source_ids: Tuple[str, ...]
    implementation_goal: str


TRACK_B_THEME_CONTRACTS: Dict[str, TrackBThemeContract] = {
    "building": TrackBThemeContract(
        theme="building",
        official_remote_source_ids=("raw.google.building", "raw.osm.building", "raw.microsoft.building"),
        manual_preload_source_ids=(
            "raw.openbuildingmap.building",
            "raw.google.open_buildings.vector",
            "raw.local.microsoft.building",
        ),
        reservation_only_source_ids=(),
        current_catalog_source_ids=("catalog.flood.building", "catalog.earthquake.building"),
        implementation_goal="Expand the current building path from OSM plus one reference into a locked multi-source national workflow.",
    ),
    "road": TrackBThemeContract(
        theme="road",
        official_remote_source_ids=("raw.osm.road", "raw.overture.transportation"),
        manual_preload_source_ids=("raw.overture.road",),
        reservation_only_source_ids=(),
        current_catalog_source_ids=("catalog.flood.road", "catalog.earthquake.road", "catalog.typhoon.road"),
        implementation_goal="Upgrade the current OSM-only road baseline to a dual-source national fusion path with Overture Transportation as the locked second-source target.",
    ),
    "water": TrackBThemeContract(
        theme="water",
        official_remote_source_ids=("raw.osm.water", "raw.hydrolakes.water"),
        manual_preload_source_ids=("raw.local.water",),
        reservation_only_source_ids=("raw.overture.water",),
        current_catalog_source_ids=("catalog.flood.water", "catalog.flood.water_polygon"),
        implementation_goal="Keep polygon water fusion explicit, with OSM water polygons plus HydroLAKES as the active national polygon route.",
    ),
    "waterways": TrackBThemeContract(
        theme="waterways",
        official_remote_source_ids=("raw.osm.waterways", "raw.hydrorivers.water"),
        manual_preload_source_ids=("raw.local.pakistan.waterways",),
        reservation_only_source_ids=(),
        current_catalog_source_ids=("catalog.flood.waterways",),
        implementation_goal="Keep line waterways separate from polygon water, with OSM waterways as the base and Pakistan local waterways as the first manual supplement contract.",
    ),
    "poi": TrackBThemeContract(
        theme="poi",
        official_remote_source_ids=("raw.osm.poi", "raw.gns.poi"),
        manual_preload_source_ids=("raw.rh.poi",),
        reservation_only_source_ids=("raw.overture.poi",),
        current_catalog_source_ids=("catalog.generic.poi",),
        implementation_goal="Keep OSM plus GNS as the first national POI pair, with RH as a manual local supplement and Overture Places deferred until field alignment work is complete.",
    ),
}


TRACK_B_SOURCE_CONTRACTS: Dict[str, TrackBSourceContract] = {
    "raw.osm.building": TrackBSourceContract(
        source_id="raw.osm.building",
        theme="building",
        role="primary",
        acquisition_class="official_remote_supported",
        format_hint="geofabrik_shapefile_bundle",
        clip_strategy="country_bundle_then_clip",
        field_mapping_profile="fields.building.osm",
        license_boundary="ODbL-derived community vector source; preserve attribution in evidence and outputs.",
        runtime_status="runtime_candidate",
        notes="Primary automated building source for both direct AOI and large-area tiling runs.",
    ),
    "raw.microsoft.building": TrackBSourceContract(
        source_id="raw.microsoft.building",
        theme="building",
        role="reference_primary",
        acquisition_class="official_remote_supported",
        format_hint="microsoft_global_buildings_tiles",
        clip_strategy="country_tiles_then_clip",
        field_mapping_profile="fields.building.microsoft",
        license_boundary="Provider-published building footprints; preserve provider attribution and keep runtime claims bounded to checked evidence.",
        runtime_status="runtime_candidate",
        notes="Official remote building reference already used by the shared runtime.",
    ),
    "raw.google.building": TrackBSourceContract(
        source_id="raw.google.building",
        theme="building",
        role="reference_remote",
        acquisition_class="official_remote_supported",
        format_hint="google_open_buildings_csv_wkt",
        clip_strategy="resolved_aoi_clip",
        field_mapping_profile="fields.building.google",
        license_boundary="Google Open Buildings attribution and CC-BY-4.0 terms apply; preserve provider attribution and keep runtime claims tied to checked AOI clip evidence.",
        runtime_status="runtime_candidate",
        notes="Promoted Google Open Buildings target with bounded URL-index materialization and AOI clip support.",
    ),
    "raw.openbuildingmap.building": TrackBSourceContract(
        source_id="raw.openbuildingmap.building",
        theme="building",
        role="reference_manual",
        acquisition_class="manual_preload_required",
        format_hint="shapefile_bundle",
        clip_strategy="local_national_clip_then_aoi_clip",
        field_mapping_profile="fields.building.openbuildingmap",
        license_boundary="Manual reference preload only; preserve source attribution and keep capability claims bounded until runtime evidence exists.",
        runtime_status="reservation_only",
        notes="Locked into the national matrix as a preload-only reference, not as a promoted runtime source.",
    ),
    "raw.google.open_buildings.vector": TrackBSourceContract(
        source_id="raw.google.open_buildings.vector",
        theme="building",
        role="reference_manual",
        acquisition_class="manual_preload_required",
        format_hint="shapefile_bundle",
        clip_strategy="local_national_clip_then_aoi_clip",
        field_mapping_profile="fields.building.google_open_buildings_vector",
        license_boundary="Manual reference preload only; keep provider attribution and do not market it as remote automation support.",
        runtime_status="reservation_only",
        notes="Acts as a reserved national clip input until later building source-set work promotes it.",
    ),
    "raw.local.microsoft.building": TrackBSourceContract(
        source_id="raw.local.microsoft.building",
        theme="building",
        role="national_cache",
        acquisition_class="manual_preload_required",
        format_hint="shapefile_bundle",
        clip_strategy="local_cached_national_clip_then_aoi_clip",
        field_mapping_profile="fields.building.microsoft",
        license_boundary="Local cache of a provider source; keep attribution and treat it as an operational cache rather than a new public source.",
        runtime_status="reservation_only",
        notes="Preferred fallback when repeated Microsoft country-tile downloads are too expensive for national runs.",
    ),
    "raw.osm.road": TrackBSourceContract(
        source_id="raw.osm.road",
        theme="road",
        role="primary",
        acquisition_class="official_remote_supported",
        format_hint="geofabrik_shapefile_bundle",
        clip_strategy="country_bundle_then_clip",
        field_mapping_profile="fields.road.osm",
        license_boundary="ODbL-derived community road source; preserve attribution in evidence and operator outputs.",
        runtime_status="runtime_candidate",
        notes="Current automated road baseline.",
    ),
    "raw.overture.road": TrackBSourceContract(
        source_id="raw.overture.road",
        theme="road",
        role="reference_manual",
        acquisition_class="manual_preload_required",
        format_hint="parquet_or_geoparquet_extract",
        clip_strategy="national_extract_then_aoi_clip",
        field_mapping_profile="fields.road.overture_transportation",
        license_boundary="Optional local preload alias for the promoted Overture transportation source; keep attribution and treat it as an operator cache rather than a separate public source claim.",
        runtime_status="reservation_only",
        notes="Kept as a manual cache alias for operators who want to avoid repeated Overture downloads during national validation runs.",
    ),
    "raw.overture.transportation": TrackBSourceContract(
        source_id="raw.overture.transportation",
        theme="road",
        role="reference_remote",
        acquisition_class="official_remote_supported",
        format_hint="geojson_extract",
        clip_strategy="theme_partition_then_clip",
        field_mapping_profile="fields.road.overture_transportation",
        license_boundary="Bounded Overture transportation materialization path for the promoted B2 road second source; keep attribution and runtime claims tied to checked evidence.",
        runtime_status="runtime_candidate",
        notes="Promoted B2 road second-source id that resolves from local preload first and can fall back to the Overture download path.",
    ),
    "raw.osm.water": TrackBSourceContract(
        source_id="raw.osm.water",
        theme="water",
        role="primary",
        acquisition_class="official_remote_supported",
        format_hint="geofabrik_shapefile_bundle",
        clip_strategy="country_bundle_then_clip",
        field_mapping_profile="fields.water.osm_polygon",
        license_boundary="ODbL-derived community water source; preserve attribution and separate line/polygon semantics in downstream claims.",
        runtime_status="runtime_candidate",
        notes="Current automated water source.",
    ),
    "raw.osm.waterways": TrackBSourceContract(
        source_id="raw.osm.waterways",
        theme="waterways",
        role="primary",
        acquisition_class="official_remote_supported",
        format_hint="geofabrik_shapefile_bundle",
        clip_strategy="country_bundle_then_clip",
        field_mapping_profile="fields.waterways.osm",
        license_boundary="ODbL-derived community waterways line source; preserve attribution and keep line semantics explicit in downstream claims.",
        runtime_status="runtime_candidate",
        notes="OSM waterways line layer materialized from the Geofabrik bundle for national waterways fusion.",
    ),
    "raw.local.pakistan.waterways": TrackBSourceContract(
        source_id="raw.local.pakistan.waterways",
        theme="waterways",
        role="supplement_line",
        acquisition_class="manual_preload_required",
        format_hint="shapefile_bundle",
        clip_strategy="local_national_clip_then_aoi_clip",
        field_mapping_profile="fields.waterways.local_osm_like",
        license_boundary="Manual local waterways preload only; keep it clearly separated from HydroRIVERS claims and preserve local source attribution in evidence.",
        runtime_status="runtime_candidate",
        notes="Pakistan-local waterways supplement contract for preloaded OSM-like line data.",
    ),
    "raw.local.water": TrackBSourceContract(
        source_id="raw.local.water",
        theme="water",
        role="reference_manual",
        acquisition_class="manual_preload_required",
        format_hint="shapefile_bundle",
        clip_strategy="local_national_clip_then_aoi_clip",
        field_mapping_profile="fields.water.local_reference",
        license_boundary="Manual local hydro cache; keep it clearly marked as preload-only evidence rather than remote automation.",
        runtime_status="runtime_candidate",
        notes="Retained as an operator cache fallback after the HydroRIVERS plus HydroLAKES remote pair was promoted.",
    ),
    "raw.hydrorivers.water": TrackBSourceContract(
        source_id="raw.hydrorivers.water",
        theme="waterways",
        role="reference_remote",
        acquisition_class="official_remote_supported",
        format_hint="shapefile_bundle",
        clip_strategy="national_line_clip_then_bundle_normalization",
        field_mapping_profile="fields.waterways.hydrorivers",
        license_boundary="Provider-published hydro line source; preserve upstream attribution and keep runtime claims tied to checked line-style evidence.",
        runtime_status="runtime_candidate",
        notes="HydroRIVERS remains a remote waterways line reference, separate from local Pakistan waterways supplements.",
    ),
    "raw.hydrolakes.water": TrackBSourceContract(
        source_id="raw.hydrolakes.water",
        theme="water",
        role="reference_remote",
        acquisition_class="official_remote_supported",
        format_hint="shapefile_bundle",
        clip_strategy="national_polygon_clip_then_bundle_normalization",
        field_mapping_profile="fields.water.hydrolakes_polygon",
        license_boundary="Provider-published hydro polygon source; preserve upstream attribution and keep runtime claims tied to checked polygon-style evidence.",
        runtime_status="runtime_candidate",
        notes="Promoted B2 polygon-style water reference with bounded remote download plus clip support.",
    ),
    "raw.overture.water": TrackBSourceContract(
        source_id="raw.overture.water",
        theme="water",
        role="deferred_alternative",
        acquisition_class="reservation_only",
        format_hint="parquet_or_geoparquet_extract",
        clip_strategy="deferred",
        field_mapping_profile="fields.water.overture",
        license_boundary="Alternative future candidate only; not part of the first implementation wave.",
        runtime_status="reservation_only",
        notes="Explicitly deferred while HydroRIVERS and HydroLAKES remain the locked B1 target pair.",
    ),
    "raw.osm.poi": TrackBSourceContract(
        source_id="raw.osm.poi",
        theme="poi",
        role="primary",
        acquisition_class="official_remote_supported",
        format_hint="geofabrik_shapefile_bundle",
        clip_strategy="country_bundle_then_clip",
        field_mapping_profile="fields.poi.osm",
        license_boundary="ODbL-derived community POI source; preserve attribution in fused outputs and evidence packages.",
        runtime_status="runtime_candidate",
        notes="Current automated POI source.",
    ),
    "raw.gns.poi": TrackBSourceContract(
        source_id="raw.gns.poi",
        theme="poi",
        role="reference_remote",
        acquisition_class="official_remote_supported",
        format_hint="country_zip_tabular_export",
        clip_strategy="country_zip_then_aoi_clip",
        field_mapping_profile="fields.poi.gns",
        license_boundary="Official GNS gazetteer export; keep name and identifier provenance visible in normalized POI outputs and evidence bundles.",
        runtime_status="runtime_candidate",
        notes="Promoted B5 POI reference source with bounded country-zip discovery and AOI clip support.",
    ),
    "raw.geonames.poi": TrackBSourceContract(
        source_id="raw.geonames.poi",
        theme="poi",
        role="reference_remote_alias",
        acquisition_class="official_remote_supported",
        format_hint="country_zip_tabular_export",
        clip_strategy="country_zip_then_aoi_clip",
        field_mapping_profile="fields.poi.gns",
        license_boundary="Alias for raw.gns.poi; preserve GNS / GeoNames gazetteer attribution.",
        runtime_status="runtime_candidate",
        notes="Canonical GNS alias for operators who request GeoNames POI; runtime materialization reuses raw.gns.poi.",
    ),
    "raw.rh.poi": TrackBSourceContract(
        source_id="raw.rh.poi",
        theme="poi",
        role="reference_manual_optional",
        acquisition_class="manual_preload_required",
        format_hint="shapefile_bundle",
        clip_strategy="country_shapefile_then_aoi_clip",
        field_mapping_profile="fields.poi.rh",
        license_boundary="Manual local sample source; keep it out of promoted national claims unless explicit evidence is added.",
        runtime_status="runtime_candidate",
        notes="Optional local supplement that can support field-alignment work.",
    ),
    "raw.overture.poi": TrackBSourceContract(
        source_id="raw.overture.poi",
        theme="poi",
        role="deferred_optional_third_source",
        acquisition_class="reservation_only",
        format_hint="parquet_or_geoparquet_extract",
        clip_strategy="deferred",
        field_mapping_profile="fields.poi.overture_places",
        license_boundary="Optional future third source only; do not claim support before field-alignment and materialization work lands.",
        runtime_status="reservation_only",
        notes="Explicitly deferred until the OSM plus GNS path is stable.",
    ),
    "raw.overture.places": TrackBSourceContract(
        source_id="raw.overture.places",
        theme="poi",
        role="deferred_optional_third_source",
        acquisition_class="reservation_only",
        format_hint="parquet_or_geoparquet_extract",
        clip_strategy="deferred",
        field_mapping_profile="fields.poi.overture_places",
        license_boundary="Optional future third source only; do not claim support before field-alignment and materialization work lands.",
        runtime_status="reservation_only",
        notes="Promoted naming used by the B2 live national source matrix while the actual source remains deferred.",
    ),
}


def get_track_b_source_contract(source_id: str) -> TrackBSourceContract | None:
    return TRACK_B_SOURCE_CONTRACTS.get(source_id)


def get_track_b_theme_contract(theme: str) -> TrackBThemeContract | None:
    return TRACK_B_THEME_CONTRACTS.get(theme)


def track_b_source_metadata(source_id: str) -> dict[str, object]:
    contract = get_track_b_source_contract(source_id)
    if contract is None:
        return {}
    return {
        "track_b_theme": contract.theme,
        "track_b_role": contract.role,
        "acquisition_class": contract.acquisition_class,
        "format_hint": contract.format_hint,
        "clip_strategy": contract.clip_strategy,
        "field_mapping_profile": contract.field_mapping_profile,
        "license_boundary": contract.license_boundary,
        "source_matrix_stage": "track_b_b1_locked",
        "source_contract_ref": TRACK_B_SOURCE_CONTRACT_REF,
        "track_b_notes": contract.notes,
    }


def track_b_theme_metadata(theme: str) -> dict[str, object]:
    contract = get_track_b_theme_contract(theme)
    if contract is None:
        return {}
    return {
        "track_b_theme": contract.theme,
        "track_b_official_remote_source_ids": list(contract.official_remote_source_ids),
        "track_b_manual_preload_source_ids": list(contract.manual_preload_source_ids),
        "track_b_reservation_only_source_ids": list(contract.reservation_only_source_ids),
        "track_b_current_catalog_source_ids": list(contract.current_catalog_source_ids),
        "track_b_implementation_goal": contract.implementation_goal,
        "source_matrix_stage": "track_b_b1_locked",
        "source_contract_ref": TRACK_B_SOURCE_CONTRACT_REF,
    }
