from __future__ import annotations

import geopandas as gpd
from shapely.geometry import Point, Polygon

from services.postprocess_service import (
    _backfill_building_height,
    _drop_empty_name_poi,
    _mitigate_building_overlaps,
)


def test_postprocess_service_drops_blank_poi_names() -> None:
    frame = gpd.GeoDataFrame(
        {"name": ["Clinic", "", None, "  "]},
        geometry=[Point(0, 0), Point(1, 1), Point(2, 2), Point(3, 3)],
        crs="EPSG:4326",
    )

    result = _drop_empty_name_poi(frame)

    assert result["name"].tolist() == ["Clinic"]


def test_postprocess_service_backfills_height_from_overlap_and_median() -> None:
    buildings = gpd.GeoDataFrame(
        {"Height": [None, None], "H_Raster": [None, None]},
        geometry=[
            Polygon([(0, 0), (0, 10), (10, 10), (10, 0)]),
            Polygon([(100, 0), (100, 10), (110, 10), (110, 0)]),
        ],
        crs="EPSG:32645",
    )
    reference = gpd.GeoDataFrame(
        {"Height": [21.0, 30.0]},
        geometry=[
            Polygon([(0, 0), (0, 10), (10, 10), (10, 0)]),
            Polygon([(200, 0), (200, 10), (210, 10), (210, 0)]),
        ],
        crs="EPSG:32645",
    )

    result, stats = _backfill_building_height(buildings, reference)

    assert result.loc[0, "Height"] == 21.0
    assert result.loc[1, "Height"] == 25.5
    assert stats["filled_height"] == 1
    assert stats["median_fallback_height"] == 1
    assert stats["remaining_missing_height"] == 0


def test_postprocess_service_counts_missing_height_when_reference_has_no_valid_heights() -> None:
    buildings = gpd.GeoDataFrame(
        {"Height": [None, None]},
        geometry=[
            Polygon([(0, 0), (0, 10), (10, 10), (10, 0)]),
            Polygon([(100, 0), (100, 10), (110, 10), (110, 0)]),
        ],
        crs="EPSG:32645",
    )
    reference = gpd.GeoDataFrame(
        {"Height": [None]},
        geometry=[Polygon([(0, 0), (0, 10), (10, 10), (10, 0)])],
        crs="EPSG:32645",
    )

    _result, stats = _backfill_building_height(buildings, reference)

    assert stats["filled_height"] == 0
    assert stats["remaining_missing_height"] == 2


def test_postprocess_service_removes_remaining_building_overlaps() -> None:
    buildings = gpd.GeoDataFrame(
        {"Height": [10.0, 12.0]},
        geometry=[
            Polygon([(0, 0), (0, 10), (10, 10), (10, 0)]),
            Polygon([(1, 1), (1, 9), (9, 9), (9, 1)]),
        ],
        crs="EPSG:32645",
    )

    result, stats = _mitigate_building_overlaps(buildings)

    assert len(result) == 1
    assert stats["remaining_overlap_pairs"] == 0
