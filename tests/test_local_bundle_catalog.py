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
        root / "Data" / "roads" / "Microsoft" / "microsoft_roads.shp",
        geopandas.GeoDataFrame(
            {"ms_road_id": [901], "ms_class": ["collector"]},
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
    _write_frame(
        root / "Data" / "water" / "HydroRIVERS_v10.shp",
        geopandas.GeoDataFrame(
            {"HYRIV_ID": [601]},
            geometry=[LineString([(0.1, 0.1), (1.9, 1.9)])],
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


class _RawServiceWithEmptyThenAvailableWater:
    def resolve(
        self,
        *,
        source_id: str,
        request_bbox,
        target_path: Path,
        target_crs: str,
        resolved_aoi=None,
    ):
        target_path.parent.mkdir(parents=True, exist_ok=True)
        work_dir = target_path.parent / f"raw_{source_id.replace('.', '_')}"
        work_dir.mkdir(parents=True, exist_ok=True)
        shp_path = work_dir / "source.shp"
        if source_id in {"raw.osm.waterways", "raw.local.pakistan.waterways"}:
            frame = geopandas.GeoDataFrame({"source": []}, geometry=[], crs="EPSG:4326")
            feature_count = 0
        else:
            frame = geopandas.GeoDataFrame(
                {"source": [source_id]},
                geometry=[
                    Polygon([(66.95, 24.85), (66.95, 24.95), (67.05, 24.95), (67.05, 24.85)])
                ],
                crs="EPSG:4326",
            )
            feature_count = 1
        frame.to_file(shp_path)
        with zipfile.ZipFile(target_path, "w") as archive:
            for file in work_dir.glob("*"):
                archive.write(file, arcname=file.name)
        from services.raw_vector_source_service import MaterializedRawVectorSource

        return MaterializedRawVectorSource(
            zip_path=target_path,
            bbox=request_bbox,
            target_crs=target_crs,
            source_id=source_id,
            source_mode="test_fixture",
            cache_hit=False,
            version_token=f"{source_id}:test",
            feature_count=feature_count,
        )


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


def test_local_bundle_catalog_materializes_flood_road_bundle_from_osm_and_microsoft(tmp_path: Path) -> None:
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
    ref_columns = _read_columns(materialized.ref_zip_path)
    assert "ms_road_id" in ref_columns
    assert "id" not in ref_columns


def test_local_bundle_catalog_records_task6_building_candidate_attempts(tmp_path: Path) -> None:
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

    materialized = provider.materialize_with_fallback(
        source_id="catalog.flood.building",
        request_bbox=None,
        target_dir=tmp_path / "task6_building_bundle",
        target_crs="EPSG:4326",
    )

    assert materialized.osm_zip_path.name == "osm.zip"
    assert materialized.ref_zip_path.name == "ref.zip"
    assert set(materialized.component_coverage) >= {
        "raw.google.building",
        "raw.microsoft.building",
        "raw.osm.building",
        "raw.osm.road",
        "raw.openbuildingmap.building",
    }
    assert [attempt["attempt_no"] for attempt in materialized.provider_attempts] == [1, 2, 3, 4, 5]


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
    assert set(materialized.component_coverage) >= {
        "raw.osm.water",
        "raw.hydrolakes.water",
        "raw.osm.waterways",
        "raw.hydrorivers.water",
    }
    assert materialized.component_coverage["raw.osm.waterways"].feature_count == 1
    assert materialized.component_coverage["raw.hydrorivers.water"].feature_count == 1


def test_local_bundle_catalog_materializes_flood_road_bundle_with_microsoft_reference(tmp_path: Path) -> None:
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
    assert "ms_road_id" in ref_columns
    assert "ms_class" in ref_columns


def test_local_bundle_catalog_road_bundle_uses_microsoft_when_overture_absent(tmp_path: Path) -> None:
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
    assert materialized.component_coverage["raw.microsoft.road"].feature_count == 1
    ref_columns = _read_columns(materialized.ref_zip_path)
    assert "ms_road_id" in ref_columns
    assert "id" not in ref_columns


def test_local_bundle_catalog_uses_policy_fallback_for_waterways(tmp_path: Path) -> None:
    provider = LocalBundleCatalogProvider(
        root_dir=tmp_path,
        raw_source_service=_RawServiceWithEmptyThenAvailableWater(),
    )

    bundle = provider.materialize_with_fallback(
        source_id="catalog.flood.waterways",
        request_bbox=(66.9, 24.8, 67.1, 25.0),
        target_dir=tmp_path / "bundle",
        target_crs="EPSG:4326",
    )

    assert bundle.fallback_from == "catalog.flood.waterways"
    assert bundle.source_id == "catalog.flood.water"
    assert bundle.attempted_sources == ["catalog.flood.waterways", "catalog.flood.water"]


def test_local_bundle_catalog_current_version_ignores_missing_overture_compatibility_source(tmp_path: Path) -> None:
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
    assert "missing:raw.microsoft.road" not in version
    assert "|" in version


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
