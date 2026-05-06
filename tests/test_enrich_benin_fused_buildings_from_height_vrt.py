from __future__ import annotations

import json
import os
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from scripts.enrich_benin_fused_buildings_from_height_vrt import (
    EnrichedTileArtifact,
    TileJob,
    compute_tile_height_metrics,
    enrich_tile_gpkg,
    managed_rasterio_env,
    run_height_enrichment,
    stitch_enriched_tiles,
)


def _write_test_raster(path: Path, band2: np.ndarray, *, nodata: float = -99.0) -> Path:
    band2 = band2.astype("float32")
    height, width = band2.shape
    band1 = np.zeros((height, width), dtype="float32")
    band3 = np.zeros((height, width), dtype="float32")
    transform = from_origin(0, float(height), 1.0, 1.0)
    with managed_rasterio_env():
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=width,
            height=height,
            count=3,
            dtype="float32",
            crs="EPSG:3857",
            transform=transform,
            nodata=nodata,
        ) as dataset:
            dataset.write(band1, 1)
            dataset.write(band2, 2)
            dataset.write(band3, 3)
            dataset.set_band_description(1, "building_fractional_count")
            dataset.set_band_description(2, "building_height")
            dataset.set_band_description(3, "building_presence")
    return path


def _single_building_frame() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"fid": [1]},
        geometry=[box(1.0, 1.0, 4.0, 4.0)],
        crs="EPSG:3857",
    )


def _write_tile_gpkg(path: Path, frame: gpd.GeoDataFrame, *, layer_name: str = "fused_buildings") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(path, driver="GPKG", layer=layer_name)
    return path


def test_managed_rasterio_env_restores_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROJ_LIB", r"E:\bad\proj")
    monkeypatch.setenv("GDAL_DATA", r"E:\bad\gdal")

    with managed_rasterio_env():
        assert "rasterio\\proj_data" in (os.environ.get("PROJ_LIB") or "").lower()
        assert "rasterio\\gdal_data" in (os.environ.get("GDAL_DATA") or "").lower()

    assert os.environ.get("PROJ_LIB") == r"E:\bad\proj"
    assert os.environ.get("GDAL_DATA") == r"E:\bad\gdal"


def test_compute_tile_height_metrics_adds_expected_statistics(tmp_path: Path) -> None:
    band2 = np.array(
        [
            [0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0],
            [0, 1, 2, 3, 0, 0],
            [0, 3, 2, 3, 0, 0],
            [0, 3, 1, 3, 0, 0],
            [0, 0, 0, 0, 0, 0],
        ],
        dtype="float32",
    )
    raster_path = _write_test_raster(tmp_path / "height.tif", band2)

    result = compute_tile_height_metrics(
        _single_building_frame(),
        raster_path,
        height_band=2,
        processing_bbox=(0.0, 0.0, 6.0, 6.0),
        subtile_size_m=4.0,
    )

    row = result.iloc[0]
    assert float(row["height_raster_max"]) == 3.0
    assert float(row["height_raster_min"]) == 1.0
    assert float(row["height_raster_centroid"]) == 2.0
    assert float(row["height_raster_dominant"]) == 3.0


def test_compute_tile_height_metrics_filters_zero_and_nodata(tmp_path: Path) -> None:
    band2 = np.array(
        [
            [0, 0, 0, 0, 0, 0],
            [0, -99, 0, -99, 0, 0],
            [0, 0, -99, 0, 0, 0],
            [0, -99, 0, -99, 0, 0],
            [0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0],
        ],
        dtype="float32",
    )
    raster_path = _write_test_raster(tmp_path / "height_zero_nodata.tif", band2)

    result = compute_tile_height_metrics(
        _single_building_frame(),
        raster_path,
        height_band=2,
        processing_bbox=(0.0, 0.0, 6.0, 6.0),
        subtile_size_m=4.0,
    )

    row = result.iloc[0]
    assert pd.isna(row["height_raster_max"])
    assert pd.isna(row["height_raster_min"])
    assert pd.isna(row["height_raster_centroid"])
    assert pd.isna(row["height_raster_dominant"])


def test_compute_tile_height_metrics_keeps_null_centroid_with_valid_area_pixels(tmp_path: Path) -> None:
    band2 = np.array(
        [
            [0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0],
            [0, 1, 1, 1, 0, 0],
            [0, 2, 0, 2, 0, 0],
            [0, 2, 2, 2, 0, 0],
            [0, 0, 0, 0, 0, 0],
        ],
        dtype="float32",
    )
    raster_path = _write_test_raster(tmp_path / "height_centroid_null.tif", band2)

    result = compute_tile_height_metrics(
        _single_building_frame(),
        raster_path,
        height_band=2,
        processing_bbox=(0.0, 0.0, 6.0, 6.0),
        subtile_size_m=4.0,
    )

    row = result.iloc[0]
    assert pd.isna(row["height_raster_centroid"])
    assert float(row["height_raster_min"]) == 1.0
    assert float(row["height_raster_max"]) == 2.0
    assert float(row["height_raster_dominant"]) == 2.0


def test_compute_tile_height_metrics_breaks_dominant_ties_toward_higher_height(tmp_path: Path) -> None:
    band2 = np.array(
        [
            [0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0],
            [0, 1, 1, 2, 0, 0],
            [0, 2, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0],
        ],
        dtype="float32",
    )
    raster_path = _write_test_raster(tmp_path / "height_tie.tif", band2)
    buildings = gpd.GeoDataFrame(
        {"fid": [1]},
        geometry=[box(1.0, 2.0, 4.0, 4.0)],
        crs="EPSG:3857",
    )

    result = compute_tile_height_metrics(
        buildings,
        raster_path,
        height_band=2,
        processing_bbox=(0.0, 0.0, 6.0, 6.0),
        subtile_size_m=4.0,
    )

    assert float(result.iloc[0]["height_raster_dominant"]) == 2.0


def test_stitch_enriched_tiles_filters_by_owner_bbox_and_preserves_feature_count(tmp_path: Path) -> None:
    geometry = box(0.2, 0.2, 0.8, 0.8)
    tile_a_path = _write_tile_gpkg(
        tmp_path / "tile_000_000.gpkg",
        gpd.GeoDataFrame(
            {
                "fid": [1],
                "height_raster_max": [5.0],
                "height_raster_min": [1.0],
                "height_raster_centroid": [3.0],
                "height_raster_dominant": [5.0],
            },
            geometry=[geometry],
            crs="EPSG:3857",
        ),
    )
    tile_b_path = _write_tile_gpkg(
        tmp_path / "tile_000_001.gpkg",
        gpd.GeoDataFrame(
            {
                "fid": [1],
                "height_raster_max": [9.0],
                "height_raster_min": [9.0],
                "height_raster_centroid": [9.0],
                "height_raster_dominant": [9.0],
            },
            geometry=[geometry],
            crs="EPSG:3857",
        ),
    )

    output_path = stitch_enriched_tiles(
        [
            EnrichedTileArtifact(
                tile_id="tile_000_000",
                output_path=tile_a_path,
                working_bbox=(0.0, 0.0, 1.0, 1.0),
                working_buffered_bbox=(0.0, 0.0, 1.1, 1.1),
            ),
            EnrichedTileArtifact(
                tile_id="tile_000_001",
                output_path=tile_b_path,
                working_bbox=(1.0, 0.0, 2.0, 1.0),
                working_buffered_bbox=(0.9, 0.0, 2.0, 1.1),
            ),
        ],
        tmp_path / "stitched.gpkg",
        target_crs="EPSG:3857",
    )

    stitched = gpd.read_file(output_path)
    assert len(stitched) == 1
    assert float(stitched.iloc[0]["height_raster_max"]) == 5.0


def test_run_height_enrichment_raises_when_output_feature_count_differs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_gpkg = _write_tile_gpkg(
        tmp_path / "input.gpkg",
        gpd.GeoDataFrame(
            {"fid": [1, 2]},
            geometry=[box(0.0, 0.0, 1.0, 1.0), box(2.0, 2.0, 3.0, 3.0)],
            crs="EPSG:3857",
        ),
    )
    vrt_path = _write_test_raster(tmp_path / "height_for_run.tif", np.full((4, 4), 5.0, dtype="float32"))
    tile_output_path = _write_tile_gpkg(
        tmp_path / "height_enrichment_tmp" / "tiles" / "tile_000_000" / "fused_buildings_height.gpkg",
        gpd.GeoDataFrame(
            {"fid": [1], "height_raster_max": [5.0]},
            geometry=[box(0.0, 0.0, 1.0, 1.0)],
            crs="EPSG:3857",
        ),
    )

    def _fake_load_tile_jobs(**_: object) -> list[TileJob]:
        return [
            TileJob(
                tile_id="tile_000_000",
                tile_input_path=tmp_path / "unused_input.gpkg",
                tile_output_path=tile_output_path,
                working_bbox=(0.0, 0.0, 2.0, 2.0),
                working_buffered_bbox=(0.0, 0.0, 2.0, 2.0),
            )
        ]

    def _fake_run_tile_job(job: TileJob, **_: object) -> EnrichedTileArtifact:
        return EnrichedTileArtifact(
            tile_id=job.tile_id,
            output_path=job.tile_output_path,
            working_bbox=job.working_bbox,
            working_buffered_bbox=job.working_buffered_bbox,
        )

    def _fake_stitch(tile_artifacts: list[EnrichedTileArtifact], output_path: Path, **_: object) -> Path:
        assert len(tile_artifacts) == 1
        gpd.read_file(tile_artifacts[0].output_path).to_file(output_path, driver="GPKG", layer="fused_buildings")
        return output_path

    class _ImmediateFuture:
        def __init__(self, value: object) -> None:
            self._value = value

        def result(self) -> object:
            return self._value

    class _ImmediateExecutor:
        def __init__(self, **_: object) -> None:
            pass

        def __enter__(self) -> "_ImmediateExecutor":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def submit(self, fn, *args, **kwargs) -> _ImmediateFuture:
            return _ImmediateFuture(fn(*args, **kwargs))

    monkeypatch.setattr(
        "scripts.enrich_benin_fused_buildings_from_height_vrt._load_tile_jobs",
        _fake_load_tile_jobs,
    )
    monkeypatch.setattr(
        "scripts.enrich_benin_fused_buildings_from_height_vrt._run_tile_job",
        _fake_run_tile_job,
    )
    monkeypatch.setattr(
        "scripts.enrich_benin_fused_buildings_from_height_vrt.stitch_enriched_tiles",
        _fake_stitch,
    )
    monkeypatch.setattr(
        "scripts.enrich_benin_fused_buildings_from_height_vrt.ProcessPoolExecutor",
        _ImmediateExecutor,
    )

    with pytest.raises(ValueError, match="feature count"):
        run_height_enrichment(
            input_gpkg=input_gpkg,
            input_layer="fused_buildings",
            tile_root=tmp_path / "tiles",
            tile_manifest_path=tmp_path / "tile_manifest.json",
            vrt_path=vrt_path,
            height_band=2,
            output_gpkg=tmp_path / "output.gpkg",
            tmp_root=tmp_path / "height_enrichment_tmp",
            workers=1,
            subtile_size_m=2048.0,
            resume=True,
            overwrite_output=False,
        )


@pytest.mark.realdata
def test_enrich_tile_gpkg_real_benin_smoke(tmp_path: Path) -> None:
    tile_path = Path(
        r"E:\fyx\data\Benin\final_shp\fusionbuildings\runtime_output\tiles\tile_000_003\fused_buildings.gpkg"
    )
    vrt_path = Path(r"E:\fyx\data\Benin\google_open_buildings_temporal_2023\google_open_buildings_temporal_2023.vrt")
    manifest_path = Path(r"E:\fyx\data\Benin\final_shp\fusionbuildings\tile_manifest.json")
    if not tile_path.exists() or not vrt_path.exists() or not manifest_path.exists():
        pytest.skip("real Benin tile inputs not available")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tile_meta = next(item for item in manifest["tiles"] if item["tile_id"] == "tile_000_003")
    output_path = tmp_path / "tile_000_003_height.gpkg"

    enrich_tile_gpkg(
        tile_input_path=tile_path,
        tile_output_path=output_path,
        vrt_path=vrt_path,
        height_band=2,
        working_buffered_bbox=tuple(tile_meta["working_buffered_bbox"]),
        subtile_size_m=2048.0,
        target_crs="EPSG:32631",
    )

    enriched = gpd.read_file(output_path)
    assert output_path.exists()
    assert "height_raster_max" in enriched.columns
    assert "height_raster_min" in enriched.columns
    assert "height_raster_centroid" in enriched.columns
    assert "height_raster_dominant" in enriched.columns
    assert int(enriched["height_raster_max"].notna().sum()) > 0
