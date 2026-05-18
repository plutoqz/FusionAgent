from __future__ import annotations

import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon

from services.track_b_source_normalization import normalize_track_b_source_frame


def test_track_b_normalization_maps_hydrorivers_profile_to_canonical_water_fields() -> None:
    frame = gpd.GeoDataFrame(
        {
            "HYRIV_ID": [11061859],
            "ORD_CLAS": [1],
            "ORD_FLOW": [4],
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


def test_track_b_normalization_computes_gns_poi_geohash_and_category() -> None:
    frame = gpd.GeoDataFrame(
        {
            "ufi": [6034032],
            "full_name": ["Usumbura"],
            "desig_cd": ["ADM1"],
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
    assert isinstance(normalized.iloc[0]["GeoHash"], str)
    assert len(normalized.iloc[0]["GeoHash"]) == 8


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
