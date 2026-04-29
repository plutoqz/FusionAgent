from __future__ import annotations

import geopandas as gpd
from shapely.geometry import box

from fusion_algorithms.building_raster import enrich_height_from_raster, validate_presence_from_raster
from fusion_algorithms.contracts import BuildingHeightParams, BuildingRasterPresenceParams, RasterSpec


def _gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"id": [1]}, geometry=[box(0, 0, 1, 1)], crs="EPSG:4326")


def test_presence_wrapper_passes_decoupled_params(monkeypatch) -> None:
    captured = {}

    def fake_validate(gdf, raster_path, **kwargs):
        captured.update(kwargs)
        out = gdf.copy()
        out["exist_status"] = "confirmed"
        return out

    monkeypatch.setattr("fusion_algorithms.building_raster._validate_existence_parallel", fake_validate)
    result = validate_presence_from_raster(
        _gdf(),
        RasterSpec(kind="building_presence", path="presence.vrt"),
        BuildingRasterPresenceParams(prob_threshold=0.25, search_dist_m=6.0),
    )
    assert result.iloc[0]["exist_status"] == "confirmed"
    assert captured["prob_threshold"] == 0.25
    assert captured["search_dist_m"] == 6.0


def test_height_wrapper_maps_height_field(monkeypatch) -> None:
    def fake_height(gdf, raster_path, n_jobs):
        out = gdf.copy()
        out["H_Raster"] = [12.5]
        return out

    monkeypatch.setattr("fusion_algorithms.building_raster._extract_height_parallel", fake_height)
    result = enrich_height_from_raster(
        _gdf(),
        RasterSpec(kind="building_height", path="height.vrt"),
        BuildingHeightParams(height_output_field="height_m"),
    )
    assert float(result.iloc[0]["height_m"]) == 12.5
    assert float(result.iloc[0]["height"]) == 12.5
