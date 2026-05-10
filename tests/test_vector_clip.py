from __future__ import annotations

import zipfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

from utils.shp_zip import zip_shapefile_bundle
from utils.vector_clip import clip_zip_to_request_bbox


def _write_bundle_zip(path: Path, frame: gpd.GeoDataFrame) -> Path:
    bundle_dir = path.parent / path.stem
    bundle_dir.mkdir(parents=True, exist_ok=True)
    shp_path = bundle_dir / "artifact.shp"
    frame.to_file(shp_path)
    zip_shapefile_bundle(shp_path, path)
    return path


def _read_bundle(bundle_zip: Path) -> gpd.GeoDataFrame:
    extract_dir = bundle_zip.parent / f"extract_{bundle_zip.stem}"
    with zipfile.ZipFile(bundle_zip, "r") as archive:
        archive.extractall(extract_dir)
    shp_path = next(extract_dir.glob("*.shp"))
    return gpd.read_file(shp_path)


def test_clip_zip_to_request_bbox_drops_boundary_lines_for_polygon_bundle(tmp_path: Path) -> None:
    bundle_zip = _write_bundle_zip(
        tmp_path / "source.zip",
        gpd.GeoDataFrame(
            {"feature_id": [1]},
            geometry=[Polygon([(0, 0), (0, 2), (2, 2), (2, 0)])],
            crs="EPSG:4326",
        ),
    )

    clipped_zip = clip_zip_to_request_bbox(
        bundle_zip,
        tmp_path / "clipped.zip",
        request_bbox=(2.0, 0.0, 3.0, 2.0),
    )

    clipped = _read_bundle(clipped_zip)
    assert clipped.empty
