from __future__ import annotations

import geopandas as gpd
from shapely.geometry import Point, box

from services.postprocess_service import (
    STANDARD_FIELDS,
    _drop_empty_name_poi,
    _standardize_columns,
    _backfill_building_height,
)


def test_standardize_columns_keeps_pakistan_building_schema_order() -> None:
    frame = gpd.GeoDataFrame(
        {
            "source": ["MS"],
            "Height": [12.5],
            "extra": ["drop"],
            "name": ["A"],
        },
        geometry=[box(0, 0, 1, 1)],
        crs="EPSG:3857",
    )

    result = _standardize_columns(frame, "buildings")

    assert list(result.columns) == [*STANDARD_FIELDS["buildings"], "geometry"]
    assert result.loc[0, "Height"] == 12.5
    assert "extra" not in result.columns


def test_drop_empty_name_poi_removes_blank_and_null_names() -> None:
    frame = gpd.GeoDataFrame(
        {"name": ["Clinic", "", None, "  "]},
        geometry=[Point(0, 0), Point(1, 0), Point(2, 0), Point(3, 0)],
        crs="EPSG:4326",
    )

    result = _drop_empty_name_poi(frame)

    assert result["name"].tolist() == ["Clinic"]


def test_backfill_building_height_uses_best_overlapping_3dglobfp_height() -> None:
    buildings = gpd.GeoDataFrame(
        {"Height": [None], "H_Raster": [None]},
        geometry=[box(0, 0, 10, 10)],
        crs="EPSG:3857",
    )
    reference = gpd.GeoDataFrame(
        {"Height": [21.0]},
        geometry=[box(1, 1, 9, 9)],
        crs="EPSG:3857",
    )

    result, stats = _backfill_building_height(buildings, reference)

    assert result.loc[0, "Height"] == 21.0
    assert result.loc[0, "H_Raster"] == 21.0
    assert stats["filled_height"] == 1


def test_backfill_building_height_falls_back_to_reference_median() -> None:
    buildings = gpd.GeoDataFrame(
        {"Height": [None]},
        geometry=[box(100, 100, 101, 101)],
        crs="EPSG:3857",
    )
    reference = gpd.GeoDataFrame(
        {"Height": [10.0, 20.0, 30.0]},
        geometry=[box(0, 0, 1, 1), box(10, 0, 11, 1), box(20, 0, 21, 1)],
        crs="EPSG:3857",
    )

    result, stats = _backfill_building_height(buildings, reference)

    assert result.loc[0, "Height"] == 20.0
    assert stats["median_fallback_height"] == 1
    assert stats["remaining_missing_height"] == 0


def test_postprocess_script_exposes_country_choices() -> None:
    from scripts import postprocess_training_fusion_outputs

    assert sorted(postprocess_training_fusion_outputs.COUNTRY_CONFIGS) == ["mongolia", "nepal"]
