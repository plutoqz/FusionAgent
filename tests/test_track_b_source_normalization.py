from __future__ import annotations

import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon

from services.track_b_source_normalization import normalize_track_b_source_frame


def test_track_b_normalization_maps_building_profiles_to_canonical_height_and_confidence() -> None:
    frame = gpd.GeoDataFrame(
        {
            "id": ["ms-1"],
            "height": [12.5],
            "confidence": [0.92],
        },
        geometry=[Polygon([(30.3, -2.4), (30.3, -2.3), (30.4, -2.3), (30.4, -2.4)])],
        crs="EPSG:4326",
    )

    normalized = normalize_track_b_source_frame(
        "raw.microsoft.building",
        frame,
        target_crs="EPSG:32735",
    )

    assert normalized.iloc[0]["source_feature_id"] == "ms-1"
    assert float(normalized.iloc[0]["height_m"]) == 12.5
    assert float(normalized.iloc[0]["confidence"]) == 0.92
    assert normalized.iloc[0]["source_id"] == "raw.microsoft.building"


def test_track_b_normalization_maps_google_open_buildings_fields() -> None:
    frame = gpd.GeoDataFrame(
        {
            "latitude": [0.5],
            "longitude": [0.5],
            "area_in_meters": [100.0],
            "confidence": [0.93],
        },
        geometry=[Polygon([(0.1, 0.1), (0.1, 0.9), (0.9, 0.9), (0.9, 0.1)])],
        crs="EPSG:4326",
    )

    normalized = normalize_track_b_source_frame(
        "raw.google.building",
        frame,
        target_crs="EPSG:4326",
    )

    assert normalized.iloc[0]["source_id"] == "raw.google.building"
    assert normalized.iloc[0]["source_feature_id"] == "0.5,0.5"
    assert float(normalized.iloc[0]["confidence"]) == 0.93


def test_track_b_normalization_maps_hydrorivers_profile_to_canonical_water_fields() -> None:
    frame = gpd.GeoDataFrame(
        {
            "HYRIV_ID": [11061859],
            "ORD_STRA": [1],
            "DIS_AV_CMS": [4.5],
        },
        geometry=[LineString([(30.42, -2.33), (30.44, -2.32)])],
        crs="EPSG:4326",
    )

    normalized = normalize_track_b_source_frame(
        "raw.hydrorivers.water",
        frame,
        target_crs="EPSG:32735",
    )

    assert normalized.iloc[0]["source_feature_id"] == "11061859"
    assert normalized.iloc[0]["fclass"] == "river"
    assert normalized.iloc[0]["water_ty"] == "line"
    assert normalized.iloc[0]["feature_kind"] == "line"
    assert normalized.iloc[0]["water_class"] == "1"
    assert float(normalized.iloc[0]["perennial_flag"]) == 4.5
    assert normalized.iloc[0]["source_id"] == "raw.hydrorivers.water"


def test_track_b_normalization_maps_hydrolakes_profile_to_canonical_water_fields() -> None:
    frame = gpd.GeoDataFrame(
        {
            "Hylak_id": [1598],
            "Lake_name": ["Rweru"],
            "Lake_type": [1],
        },
        geometry=[Polygon([(30.3, -2.4), (30.3, -2.3), (30.4, -2.3), (30.4, -2.4)])],
        crs="EPSG:4326",
    )

    normalized = normalize_track_b_source_frame(
        "raw.hydrolakes.water",
        frame,
        target_crs="EPSG:32735",
    )

    assert normalized.iloc[0]["source_feature_id"] == "1598"
    assert normalized.iloc[0]["name"] == "Rweru"
    assert normalized.iloc[0]["fclass"] == "lake"
    assert normalized.iloc[0]["water_ty"] == "1"
    assert normalized.iloc[0]["feature_kind"] == "polygon"
    assert normalized.iloc[0]["water_class"] == "1"


def test_track_b_normalization_computes_gns_poi_geohash_and_category() -> None:
    frame = gpd.GeoDataFrame(
        {
            "ufi": [6034032],
            "full_name": ["Usumbura"],
            "desig_cd": ["ADM1"],
            "CC1": ["BI"],
        },
        geometry=[Point(29.256944, -3.333333)],
        crs="EPSG:4326",
    )

    normalized = normalize_track_b_source_frame(
        "raw.gns.poi",
        frame,
        target_crs="EPSG:4326",
    )

    assert normalized.iloc[0]["source_feature_id"] == "6034032"
    assert normalized.iloc[0]["name"] == "Usumbura"
    assert normalized.iloc[0]["category"] == "ADM1"
    assert normalized.iloc[0]["admin_country"] == "BI"
    assert isinstance(normalized.iloc[0]["GeoHash"], str)
    assert len(normalized.iloc[0]["GeoHash"]) == 8


def test_track_b_normalization_maps_gns_remote_country_code_from_cc_ft() -> None:
    frame = gpd.GeoDataFrame(
        {
            "ufi": [6034032],
            "full_name": ["Usumbura"],
            "desig_cd": ["ADM1"],
            "cc_ft": ["BDI,RWA"],
        },
        geometry=[Point(29.256944, -3.333333)],
        crs="EPSG:4326",
    )

    normalized = normalize_track_b_source_frame(
        "raw.gns.poi",
        frame,
        target_crs="EPSG:4326",
    )

    assert normalized.iloc[0]["admin_country"] == "BDI"


def test_track_b_normalization_preserves_rh_poi_geohash_and_name_aliases() -> None:
    frame = gpd.GeoDataFrame(
        {
            "id": [3],
            "alternaten": ["Alt Clinic"],
            "GeoHash": ["kxm1xp8"],
            "type": ["clinic"],
        },
        geometry=[Point(29.34526, -3.36058)],
        crs="EPSG:4326",
    )

    normalized = normalize_track_b_source_frame(
        "raw.rh.poi",
        frame,
        target_crs="EPSG:4326",
    )

    assert normalized.iloc[0]["source_feature_id"] == "3"
    assert normalized.iloc[0]["name"] == "Alt Clinic"
    assert normalized.iloc[0]["GeoHash"] == "kxm1xp8"
    assert normalized.iloc[0]["category"] == "clinic"


def test_track_b_normalization_maps_google_poi_profile_to_canonical_fields() -> None:
    frame = gpd.GeoDataFrame(
        {
            "place_id": ["google-place-1"],
            "name": ["Nairobi Hospital"],
            "primary_type": ["hospital"],
        },
        geometry=[Point(36.806, -1.296)],
        crs="EPSG:4326",
    )

    normalized = normalize_track_b_source_frame(
        "raw.google.poi",
        frame,
        target_crs="EPSG:4326",
    )

    assert normalized.iloc[0]["source_id"] == "raw.google.poi"
    assert normalized.iloc[0]["field_mapping_profile"] == "fields.poi.google"
    assert normalized.iloc[0]["source_feature_id"] == "google-place-1"
    assert normalized.iloc[0]["name"] == "Nairobi Hospital"
    assert normalized.iloc[0]["category"] == "hospital"
    assert isinstance(normalized.iloc[0]["GeoHash"], str)
    assert len(normalized.iloc[0]["GeoHash"]) == 8


def test_track_b_normalization_maps_google_poi_camel_case_and_types_fallback() -> None:
    frame = gpd.GeoDataFrame(
        {
            "place_id": ["google-place-2"],
            "name": ["Unnamed Google Place"],
            "primaryType": [None],
            "types": ["library,point_of_interest"],
        },
        geometry=[Point(36.806, -1.296)],
        crs="EPSG:4326",
    )

    normalized = normalize_track_b_source_frame(
        "raw.google.poi",
        frame,
        target_crs="EPSG:4326",
    )

    assert normalized.iloc[0]["source_feature_id"] == "google-place-2"
    assert normalized.iloc[0]["category"] == "library"


def test_track_b_normalization_prefers_google_display_name_over_resource_name() -> None:
    frame = gpd.GeoDataFrame(
        {
            "name": ["places/abc123"],
            "displayName.text": ["Readable Cafe"],
            "formattedAddress": ["Readable Street"],
            "primaryType": ["cafe"],
            "types": ["cafe,food"],
        },
        geometry=[Point(36.806, -1.296)],
        crs="EPSG:4326",
    )

    normalized = normalize_track_b_source_frame(
        "raw.google.poi",
        frame,
        target_crs="EPSG:4326",
    )

    assert normalized.iloc[0]["source_feature_id"] == "places/abc123"
    assert normalized.iloc[0]["name"] == "Readable Cafe"
    assert normalized.iloc[0]["name_alt"] == "Readable Street"
    assert normalized.iloc[0]["category"] == "cafe"


def test_track_b_normalization_maps_overture_road_surface_and_lanes() -> None:
    frame = gpd.GeoDataFrame(
        {
            "id": ["seg-1"],
            "class": ["primary"],
            "surface": ["paved"],
            "lane_count": [2],
        },
        geometry=[LineString([(30.42, -2.33), (30.44, -2.32)])],
        crs="EPSG:4326",
    )

    normalized = normalize_track_b_source_frame(
        "raw.overture.transportation",
        frame,
        target_crs="EPSG:32735",
    )

    assert normalized.iloc[0]["road_class"] == "primary"
    assert normalized.iloc[0]["surface"] == "paved"
    assert normalized.iloc[0]["lanes"] == 2
