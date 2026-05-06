from __future__ import annotations

import zipfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

from services.tile_partition_service import TilePartitionService
from services.tiled_building_runtime_service import TiledBuildingRuntimeService
from utils.shp_zip import zip_shapefile_bundle
from utils.vector_clip import clip_zip_to_request_bbox


def _write_bundle_zip(path: Path, frame: gpd.GeoDataFrame) -> Path:
    bundle_dir = path.parent / path.stem
    bundle_dir.mkdir(parents=True, exist_ok=True)
    shp_path = bundle_dir / "artifact.shp"
    frame.to_file(shp_path)
    zip_shapefile_bundle(shp_path, path)
    return path


def _read_feature_count(bundle_shp: Path) -> int:
    return int(len(gpd.read_file(bundle_shp).index))


def test_tiled_runtime_runs_tiles_and_stitches_outputs(tmp_path: Path) -> None:
    osm_zip = _write_bundle_zip(
        tmp_path / "osm_full.zip",
        gpd.GeoDataFrame(
            {"osm_id": [1, 2, 3]},
            geometry=[
                Polygon([(2.500, 9.250), (2.500, 9.255), (2.505, 9.255), (2.505, 9.250)]),
                Polygon([(2.555, 9.285), (2.555, 9.290), (2.560, 9.290), (2.560, 9.285)]),
                Polygon([(2.700, 9.360), (2.700, 9.365), (2.705, 9.365), (2.705, 9.360)]),
            ],
            crs="EPSG:4326",
        ),
    )
    ref_zip = _write_bundle_zip(
        tmp_path / "ref_full.zip",
        gpd.GeoDataFrame(
            {"confidence": [0.9, 0.8, 0.85]},
            geometry=[
                Polygon([(2.500, 9.250), (2.500, 9.255), (2.505, 9.255), (2.505, 9.250)]),
                Polygon([(2.555, 9.285), (2.555, 9.290), (2.560, 9.290), (2.560, 9.285)]),
                Polygon([(2.700, 9.360), (2.700, 9.365), (2.705, 9.365), (2.705, 9.360)]),
            ],
            crs="EPSG:4326",
        ),
    )

    manifest = TilePartitionService(tile_width_m=5000, tile_height_m=5000, overlap_m=128).partition_bbox(
        bbox=(2.48, 9.23, 2.77, 9.44),
        bbox_crs="EPSG:4326",
        working_crs="EPSG:32631",
    )

    def osm_bundle_factory(tile, target_path: Path) -> Path:
        return clip_zip_to_request_bbox(osm_zip, target_path, request_bbox=tile.buffered_bbox)

    def ref_bundle_factory(tile, target_path: Path) -> Path:
        return clip_zip_to_request_bbox(ref_zip, target_path, request_bbox=tile.buffered_bbox)

    service = TiledBuildingRuntimeService(max_workers=2)
    result = service.run_tiled_building_job(
        run_id="run-benin-tiled",
        tile_manifest=manifest,
        osm_bundle_factory=osm_bundle_factory,
        ref_bundle_factory=ref_bundle_factory,
        output_dir=tmp_path / "output",
        target_crs="EPSG:32631",
    )

    assert result.output_shp.exists()
    assert result.tile_count >= 2
    assert result.stitched_feature_count >= 3
    assert _read_feature_count(result.output_shp) == result.stitched_feature_count

    with zipfile.ZipFile(osm_zip, "r") as archive:
        assert "artifact.shp" in archive.namelist()
