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
        root / "Data" / "roads" / "Overture" / "overture_roads.shp",
        geopandas.GeoDataFrame(
            {"id": ["seg-1"], "class": ["primary"], "surface": ["paved"], "lane_count": [2]},
            geometry=[LineString([(0, 0), (1, 1)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        root / "Data" / "burundi-260127-free.shp" / "gis_osm_water_a_free_1.shp",
        geopandas.GeoDataFrame(
            {"osmw_id": [301]},
            geometry=[Polygon([(0, 0), (0, 2), (2, 2), (2, 0)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        root / "Data" / "burundi-260127-free.shp" / "gis_osm_waterways_free_1.shp",
        geopandas.GeoDataFrame(
            {"osmwl_id": [302], "fclass": ["river"]},
            geometry=[LineString([(0, 0), (1, 1)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        root / "Data" / "water" / "local_water.shp",
        geopandas.GeoDataFrame(
            {"locw_id": [401]},
            geometry=[Polygon([(0.5, 0.5), (0.5, 1.5), (1.5, 1.5), (1.5, 0.5)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        root / "Data" / "water" / "HydroLAKES_polys_v10.shp",
        geopandas.GeoDataFrame(
            {"Hylak_id": [501]},
            geometry=[Polygon([(0.25, 0.25), (0.25, 1.75), (1.75, 1.75), (1.75, 0.25)])],
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


class _NoRemoteSourceAssetService:
    def can_materialize(self, _source_id: str) -> bool:
        return False


def test_local_bundle_catalog_supports_expanded_building_and_flood_road_sources(tmp_path: Path) -> None:
    _seed_local_catalog_tree(tmp_path)
    provider = LocalBundleCatalogProvider(
        tmp_path,
        raw_source_service=RawVectorSourceService(
            root_dir=tmp_path,
            registry=ArtifactRegistry(index_path=tmp_path / "artifact_registry.json"),
            cache_dir=tmp_path / "raw-cache",
            source_asset_service=_NoRemoteSourceAssetService(),
        ),
    )

    for source_id in [
        "catalog.flood.building",
        "catalog.earthquake.building",
        "catalog.flood.road",
        "catalog.earthquake.road",
        "catalog.typhoon.road",
    ]:
        assert provider.can_handle(source_id)
        materialized = provider.materialize(
            source_id=source_id,
            request_bbox=None,
            target_dir=tmp_path / source_id.replace(".", "_"),
            target_crs="EPSG:4326",
        )
        assert materialized.osm_zip_path.exists()
        assert materialized.ref_zip_path.exists()


def test_local_bundle_catalog_materializes_flood_road_bundle_from_osm_and_overture(tmp_path: Path) -> None:
    _seed_local_catalog_tree(tmp_path)
    provider = LocalBundleCatalogProvider(
        tmp_path,
        raw_source_service=RawVectorSourceService(
            root_dir=tmp_path,
            registry=ArtifactRegistry(index_path=tmp_path / "artifact_registry.json"),
            cache_dir=tmp_path / "raw-cache",
            source_asset_service=_NoRemoteSourceAssetService(),
        ),
    )

    materialized = provider.materialize(
        source_id="catalog.flood.road",
        request_bbox=None,
        target_dir=tmp_path / "road_bundle",
        target_crs="EPSG:4326",
    )

    assert provider.can_handle("catalog.flood.road")
    assert "road_id" in _read_columns(materialized.osm_zip_path)
    assert "id" in _read_columns(materialized.ref_zip_path)


def test_local_bundle_catalog_uses_microsoft_reference_layer_for_default_building_pairs(tmp_path: Path) -> None:
    _seed_local_catalog_tree(tmp_path)
    provider = LocalBundleCatalogProvider(
        tmp_path,
        raw_source_service=RawVectorSourceService(
            root_dir=tmp_path,
            registry=ArtifactRegistry(index_path=tmp_path / "artifact_registry.json"),
            cache_dir=tmp_path / "raw-cache",
        ),
    )

    flood_bundle = provider.materialize(
        source_id="catalog.flood.building",
        request_bbox=None,
        target_dir=tmp_path / "flood_bundle",
        target_crs="EPSG:4326",
    )
    microsoft_bundle = provider.materialize(
        source_id="catalog.earthquake.building",
        request_bbox=None,
        target_dir=tmp_path / "microsoft_bundle",
        target_crs="EPSG:4326",
    )

    assert "msft_id" in _read_columns(flood_bundle.ref_zip_path)
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
    assert "osmw_id" in _read_columns(materialized.osm_zip_path)
    assert "Hylak_id" in _read_columns(materialized.ref_zip_path)


def test_local_bundle_catalog_materializes_flood_road_bundle_with_overture_reference(tmp_path: Path) -> None:
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
        source_id="catalog.flood.road",
        request_bbox=None,
        target_dir=tmp_path / "road_bundle",
        target_crs="EPSG:4326",
    )

    assert "road_id" in _read_columns(materialized.osm_zip_path)
    ref_columns = _read_columns(materialized.ref_zip_path)
    assert "id" in ref_columns
    assert "class" in ref_columns


def test_local_bundle_catalog_road_bundle_tolerates_missing_manual_overture_reference(tmp_path: Path) -> None:
    _seed_local_catalog_tree(tmp_path)
    overture_dir = tmp_path / "Data" / "roads" / "Overture"
    for path in overture_dir.glob("*"):
        path.unlink()

    provider = LocalBundleCatalogProvider(
        tmp_path,
        raw_source_service=RawVectorSourceService(
            root_dir=tmp_path,
            registry=ArtifactRegistry(index_path=tmp_path / "artifact_registry.json"),
            cache_dir=tmp_path / "raw-cache",
            source_asset_service=_NoRemoteSourceAssetService(),
        ),
    )

    materialized = provider.materialize_with_fallback(
        source_id="catalog.flood.road",
        request_bbox=None,
        target_dir=tmp_path / "road_bundle_missing_ref",
        target_crs="EPSG:4326",
    )

    assert materialized.source_id == "catalog.flood.road"
    assert materialized.component_coverage["raw.overture.transportation"].feature_count == 0
    assert materialized.component_coverage["raw.overture.transportation"].source_mode == "missing_optional_ref"


def test_local_bundle_catalog_current_version_tolerates_missing_manual_overture_reference(tmp_path: Path) -> None:
    _seed_local_catalog_tree(tmp_path)
    overture_dir = tmp_path / "Data" / "roads" / "Overture"
    for path in overture_dir.glob("*"):
        path.unlink()

    provider = LocalBundleCatalogProvider(
        tmp_path,
        raw_source_service=RawVectorSourceService(
            root_dir=tmp_path,
            registry=ArtifactRegistry(index_path=tmp_path / "artifact_registry.json"),
            cache_dir=tmp_path / "raw-cache",
            source_asset_service=_NoRemoteSourceAssetService(),
        ),
    )

    version = provider.current_version("catalog.flood.road")

    assert version
    assert "|missing:raw.overture.transportation" in version


def test_local_bundle_catalog_water_bundle_raises_when_aoi_has_empty_component_coverage(tmp_path: Path) -> None:
    _seed_local_catalog_tree(tmp_path)
    class _NoFallbackSourceAssetService:
        def can_materialize(self, _source_id: str) -> bool:
            return False

    provider = LocalBundleCatalogProvider(
        tmp_path,
        raw_source_service=RawVectorSourceService(
            root_dir=tmp_path,
            registry=ArtifactRegistry(index_path=tmp_path / "artifact_registry.json"),
            cache_dir=tmp_path / "raw-cache",
            source_asset_service=_NoFallbackSourceAssetService(),
        ),
    )

    with pytest.raises(ValueError, match="catalog.flood.water"):
        provider.materialize(
            source_id="catalog.flood.water",
            request_bbox=(10.0, 10.0, 11.0, 11.0),
            target_dir=tmp_path / "water_bundle_empty",
            target_crs="EPSG:4326",
        )
