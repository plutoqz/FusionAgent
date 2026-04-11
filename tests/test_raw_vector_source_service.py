from __future__ import annotations

import json
import zipfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point, Polygon

from services.artifact_registry import ArtifactRegistry
from services.raw_vector_source_service import RawVectorSourceService


def _write_frame(path: Path, gdf: gpd.GeoDataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path)


def _extract_bounds(bundle_zip: Path, *, output_crs: str = "EPSG:4326") -> list[float]:
    extract_dir = bundle_zip.parent / f"extract_{bundle_zip.stem}"
    with zipfile.ZipFile(bundle_zip, "r") as zf:
        zf.extractall(extract_dir)
    shp_path = next(extract_dir.glob("*.shp"))
    gdf = gpd.read_file(shp_path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    bounds = gdf.to_crs(output_crs).total_bounds.tolist()
    return [float(value) for value in bounds]


def _seed_raw_source_tree(root: Path) -> None:
    _write_frame(
        root / "Data" / "buildings" / "OSM" / "osm_buildings.shp",
        gpd.GeoDataFrame(
            {"osm_id": [1]},
            geometry=[Polygon([(0, 0), (0, 10), (10, 10), (10, 0)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        root / "Data" / "burundi-260127-free.shp" / "gis_osm_water_a_free_1.shp",
        gpd.GeoDataFrame(
            {"water_id": [10]},
            geometry=[Polygon([(1, 1), (1, 2), (2, 2), (2, 1)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        root / "Data" / "POI" / "sample_region" / "GNS.shp",
        gpd.GeoDataFrame(
            {"gns_id": [20]},
            geometry=[Point(1.5, 1.5)],
            crs="EPSG:4326",
        ),
    )


def test_raw_vector_source_service_supports_directory_exact_and_recursive_locators(tmp_path: Path) -> None:
    _seed_raw_source_tree(tmp_path)
    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    service = RawVectorSourceService(root_dir=tmp_path, registry=registry, cache_dir=tmp_path / "cache")

    building = service.resolve(
        source_id="raw.osm.building",
        request_bbox=None,
        target_path=tmp_path / "run" / "building.zip",
        target_crs="EPSG:4326",
    )
    water = service.resolve(
        source_id="raw.osm.water",
        request_bbox=None,
        target_path=tmp_path / "run" / "water.zip",
        target_crs="EPSG:4326",
    )
    poi = service.resolve(
        source_id="raw.gns.poi",
        request_bbox=None,
        target_path=tmp_path / "run" / "poi.zip",
        target_crs="EPSG:4326",
    )

    assert building.zip_path.exists()
    assert water.zip_path.exists()
    assert poi.zip_path.exists()
    assert building.source_mode == "downloaded"
    assert water.source_mode == "downloaded"
    assert poi.source_mode == "downloaded"


def test_raw_vector_source_service_reuses_cached_sources_when_version_matches_and_clips_bbox(tmp_path: Path) -> None:
    _seed_raw_source_tree(tmp_path)
    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    service = RawVectorSourceService(root_dir=tmp_path, registry=registry, cache_dir=tmp_path / "cache")

    initial = service.resolve(
        source_id="raw.osm.building",
        request_bbox=None,
        target_path=tmp_path / "run1" / "osm.zip",
        target_crs="EPSG:4326",
    )
    reused = service.resolve(
        source_id="raw.osm.building",
        request_bbox=(1.0, 1.0, 2.0, 2.0),
        target_path=tmp_path / "run2" / "osm.zip",
        target_crs="EPSG:4326",
    )

    assert initial.source_mode == "downloaded"
    assert reused.source_mode == "clip_reused"
    assert reused.cache_hit is True
    assert _extract_bounds(reused.zip_path) == [1.0, 1.0, 2.0, 2.0]

    payload = json.loads((tmp_path / "artifact_registry.json").read_text(encoding="utf-8"))
    raw_records = [
        record
        for record in payload.get("records", [])
        if record.get("meta", {}).get("artifact_role") == "raw_vector"
    ]
    assert len(raw_records) == 1
