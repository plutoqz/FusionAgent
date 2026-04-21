from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

geopandas = pytest.importorskip("geopandas")
from shapely.geometry import LineString, Polygon

from services.artifact_registry import ArtifactRegistry
from services.local_bundle_catalog import LocalBundleCatalogProvider
from services.raw_vector_source_service import RawVectorSourceService


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
    _write_frame(
        root / "Data" / "burundi-260127-free.shp" / "gis_osm_water_a_free_1.shp",
        geopandas.GeoDataFrame(
            {"osm_water_id": [301]},
            geometry=[Polygon([(0, 0), (0, 2), (2, 2), (2, 0)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        root / "Data" / "water" / "local_water.shp",
        geopandas.GeoDataFrame(
            {"local_water_id": [401]},
            geometry=[Polygon([(0.5, 0.5), (0.5, 1.5), (1.5, 1.5), (1.5, 0.5)])],
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
    provider = LocalBundleCatalogProvider(
        tmp_path,
        raw_source_service=RawVectorSourceService(
            root_dir=tmp_path,
            registry=ArtifactRegistry(index_path=tmp_path / "artifact_registry.json"),
            cache_dir=tmp_path / "raw-cache",
        ),
    )

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
    provider = LocalBundleCatalogProvider(
        tmp_path,
        raw_source_service=RawVectorSourceService(
            root_dir=tmp_path,
            registry=ArtifactRegistry(index_path=tmp_path / "artifact_registry.json"),
            cache_dir=tmp_path / "raw-cache",
        ),
    )

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


def test_local_bundle_catalog_materializes_flood_water_bundle_from_shared_provider_path(tmp_path: Path) -> None:
    _seed_local_catalog_tree(tmp_path)
    provider = LocalBundleCatalogProvider(
        tmp_path,
        raw_source_service=RawVectorSourceService(
            root_dir=tmp_path,
            registry=ArtifactRegistry(index_path=tmp_path / "artifact_registry.json"),
            cache_dir=tmp_path / "raw-cache",
        ),
    )

    materialized = provider.materialize(
        source_id="catalog.flood.water",
        request_bbox=(0.25, 0.25, 1.75, 1.75),
        target_dir=tmp_path / "water_bundle",
        target_crs="EPSG:4326",
    )

    assert provider.can_handle("catalog.flood.water")
    assert materialized.osm_zip_path.name == "osm.zip"
    assert materialized.ref_zip_path.name == "ref.zip"
    assert "osm_water_" in "".join(_read_columns(materialized.osm_zip_path))
    assert "local_wat" in "".join(_read_columns(materialized.ref_zip_path))


def test_local_bundle_catalog_water_bundle_raises_when_aoi_has_empty_component_coverage(tmp_path: Path) -> None:
    _seed_local_catalog_tree(tmp_path)
    provider = LocalBundleCatalogProvider(
        tmp_path,
        raw_source_service=RawVectorSourceService(
            root_dir=tmp_path,
            registry=ArtifactRegistry(index_path=tmp_path / "artifact_registry.json"),
            cache_dir=tmp_path / "raw-cache",
        ),
    )

    with pytest.raises(ValueError, match="catalog.flood.water"):
        provider.materialize(
            source_id="catalog.flood.water",
            request_bbox=(10.0, 10.0, 11.0, 11.0),
            target_dir=tmp_path / "water_bundle_empty",
            target_crs="EPSG:4326",
        )
