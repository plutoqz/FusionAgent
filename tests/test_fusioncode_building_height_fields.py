from __future__ import annotations

import geopandas as gpd
from shapely.geometry import box

from fusion_algorithms.building_height import attach_source_heights_and_final
from fusion_algorithms.contracts import BuildingHeightParams


def _frame(values: list[float], *, field: str = "height") -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {field: values},
        geometry=[box(0, 0, 1, 1) for _ in values],
        crs="EPSG:3857",
    )


def test_attach_source_heights_preserves_each_source_and_prefers_raster_final() -> None:
    fused = gpd.GeoDataFrame(
        {"H_Raster": [8.0], "height_fused": [6.0]},
        geometry=[box(0, 0, 1, 1)],
        crs="EPSG:3857",
    )

    result = attach_source_heights_and_final(
        fused,
        {
            "OSM": _frame([0.0]),
            "MS": _frame([4.0]),
            "OBM": _frame([6.0]),
            "GG": _frame([0.0], field="Height"),
        },
        BuildingHeightParams(height_output_field="height_raster"),
    )

    assert float(result.loc[0, "height_osm"]) == 0.0
    assert float(result.loc[0, "height_ms"]) == 4.0
    assert float(result.loc[0, "height_obm"]) == 6.0
    assert float(result.loc[0, "height_google"]) == 0.0
    assert float(result.loc[0, "height_raster"]) == 8.0
    assert float(result.loc[0, "height_vector_fused"]) == 6.0
    assert float(result.loc[0, "height_final"]) == 8.0
    assert result.loc[0, "height_final_source"] == "raster"


def test_attach_source_heights_uses_vector_max_when_raster_missing() -> None:
    fused = gpd.GeoDataFrame(
        {"height_fused": [5.0]},
        geometry=[box(0, 0, 1, 1)],
        crs="EPSG:3857",
    )

    result = attach_source_heights_and_final(
        fused,
        {"MS": _frame([4.0]), "OBM": _frame([9.0])},
        BuildingHeightParams(),
    )

    assert float(result.loc[0, "height_ms"]) == 4.0
    assert float(result.loc[0, "height_obm"]) == 9.0
    assert float(result.loc[0, "height_vector_fused"]) == 9.0
    assert float(result.loc[0, "height_final"]) == 9.0
    assert result.loc[0, "height_final_source"] == "height_obm"
