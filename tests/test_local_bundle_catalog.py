from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

geopandas = pytest.importorskip("geopandas")
from shapely.geometry import LineString, Polygon

from services.local_bundle_catalog import LocalBundleCatalogProvider


def _write_frame(path: Path, gdf) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path)


def _seed_local_catalog_tree(root: Path) -> None:
    _write_frame(
        root / "Data" / "buildings" / "OSM" / "osm_buildings.shp",
        geopandas.GeoDataFrame(
            {"osm_id": [1]},
            geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        root / "Data" / "buildings" / "Google" / "google_buildings.shp",
        geopandas.GeoDataFrame(
            {"google_id": [101]},
            geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        root / "Data" / "buildings" / "Microsoft" / "microsoft_buildings.shp",
        geopandas.GeoDataFrame(
            {"msft_id": [202]},
            geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        root / "Data" / "roads" / "OSM" / "osm_roads.shp",
        geopandas.GeoDataFrame(
            {"road_id": [1]},
            geometry=[LineString([(0, 0), (1, 1)])],
            crs="EPSG:4326",
        ),
    )


def _read_columns(bundle_zip: Path) -> list[str]:
    extract_dir = bundle_zip.parent / f"extract_{bundle_zip.stem}"
    with zipfile.ZipFile(bundle_zip, "r") as zf:
        zf.extractall(extract_dir)
    shp_path = next(extract_dir.glob("*.shp"))
    frame = geopandas.read_file(shp_path)
    return list(frame.columns)


def test_local_bundle_catalog_supports_expanded_building_and_flood_road_sources(tmp_path: Path) -> None:
    _seed_local_catalog_tree(tmp_path)
    provider = LocalBundleCatalogProvider(tmp_path)

    for source_id in ["catalog.flood.building", "catalog.earthquake.building", "catalog.flood.road"]:
        assert provider.can_handle(source_id)
        materialized = provider.materialize(
            source_id=source_id,
            request_bbox=None,
            target_dir=tmp_path / source_id.replace(".", "_"),
            target_crs="EPSG:4326",
        )
        assert materialized.osm_zip_path.exists()
        assert materialized.ref_zip_path.exists()


def test_local_bundle_catalog_uses_google_and_microsoft_reference_layers_for_building_pairs(tmp_path: Path) -> None:
    _seed_local_catalog_tree(tmp_path)
    provider = LocalBundleCatalogProvider(tmp_path)

    google_bundle = provider.materialize(
        source_id="catalog.flood.building",
        request_bbox=None,
        target_dir=tmp_path / "google_bundle",
        target_crs="EPSG:4326",
    )
    microsoft_bundle = provider.materialize(
        source_id="catalog.earthquake.building",
        request_bbox=None,
        target_dir=tmp_path / "microsoft_bundle",
        target_crs="EPSG:4326",
    )

    assert "google_id" in _read_columns(google_bundle.ref_zip_path)
    assert "msft_id" in _read_columns(microsoft_bundle.ref_zip_path)
