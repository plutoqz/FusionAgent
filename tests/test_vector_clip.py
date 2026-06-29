from __future__ import annotations

import zipfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon

from utils.shp_zip import zip_shapefile_bundle
from utils.vector_clip import clip_frame_to_request_bbox, clip_zip_to_request_bbox


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


def test_clip_zip_to_request_bbox_creates_missing_output_parent(tmp_path: Path) -> None:
    bundle_zip = _write_bundle_zip(
        tmp_path / "source.zip",
        gpd.GeoDataFrame(
            {"feature_id": [1]},
            geometry=[Point(0.5, 0.5)],
            crs="EPSG:4326",
        ),
    )

    clipped_zip = clip_zip_to_request_bbox(
        bundle_zip,
        tmp_path / "new" / "nested" / "clipped.zip",
        request_bbox=(0.0, 0.0, 1.0, 1.0),
    )

    assert clipped_zip.exists()
    assert len(_read_bundle(clipped_zip)) == 1


def test_clip_frame_to_request_bbox_repairs_invalid_polygon_and_keeps_polygon_family() -> None:
    invalid_bowtie = Polygon([(0, 0), (2, 2), (0, 2), (2, 0), (0, 0)])
    frame = gpd.GeoDataFrame(
        {"source_id": ["raw.microsoft.building"]},
        geometry=[invalid_bowtie],
        crs="EPSG:4326",
    )

    clipped = clip_frame_to_request_bbox(frame, (0.0, 0.0, 1.0, 1.0))

    assert len(clipped) == 1
    assert clipped.geometry.iloc[0].is_valid
    assert clipped.geometry.iloc[0].geom_type in {"Polygon", "MultiPolygon"}


def test_clip_frame_to_request_bbox_repairs_mixed_source_families_without_geometry_collection_leaks() -> None:
    frame = gpd.GeoDataFrame(
        {"source_id": ["raw.osm.road", "raw.gns.poi"]},
        geometry=[
            LineString([(-1.0, 0.5), (2.0, 0.5)]),
            Point(0.5, 0.5),
        ],
        crs="EPSG:4326",
    )

    clipped = clip_frame_to_request_bbox(frame, (0.0, 0.0, 1.0, 1.0))

    assert set(clipped.geometry.geom_type) == {"LineString", "Point"}


def test_clip_frame_to_request_bbox_accepts_crs84_wkt_source_crs() -> None:
    crs84_wkt = (
        'GEOGCS["GCS_WGS_84_CRS84",DATUM["WGS_1984",'
        'SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],'
        'AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0],'
        'UNIT["Degree",0.0174532925199433],AXIS["Longitude",EAST],AXIS["Latitude",NORTH]]'
    )
    frame = gpd.GeoDataFrame(
        {"source_id": ["raw.osm.road"]},
        geometry=[LineString([(-67.1, 10.4), (-67.0, 10.5)])],
        crs=crs84_wkt,
    )

    clipped = clip_frame_to_request_bbox(frame, (-67.17, 10.38, -66.86, 10.57))

    assert len(clipped) == 1
