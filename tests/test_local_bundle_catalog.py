from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

geopandas = pytest.importorskip("geopandas")
from shapely.geometry import LineString, Polygon

from kg.policy_registry import default_policy_registry
from schemas.agent import RunCreateRequest, RunInputStrategy, RunTrigger, RunTriggerType
from schemas.data_requirement import (
    BundleSlot,
    CompletenessPolicy,
    DataRequirementPlan,
    SourceCandidate,
    SourceRoleRequirement,
)
from schemas.fusion import JobType
from schemas.task_kind import TaskKind
from services.artifact_registry import ArtifactRegistry
from services.input_acquisition_service import InputAcquisitionService
from services.local_bundle_catalog import BundleMaterializationError, LocalBundleCatalogProvider
from services.raster_height_source_service import RasterHeightSourceService
from services.raw_vector_source_service import MaterializedRawVectorSource, RawVectorSourceService


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


class _BuildingBundlePolicyRegistry:
    def __init__(self, *, allows_partial_coverage: bool) -> None:
        self.allows_partial_coverage = allows_partial_coverage

    def source_bundle_policy(self, source_id: str, *, required: bool = False):
        assert source_id == "catalog.flood.building" or not required
        if source_id != "catalog.flood.building":
            return None
        return {
            "source_id": source_id,
            "component_candidates": [
                "raw.osm.building",
                "raw.microsoft.building",
                "raw.google.building",
            ],
            "required_full_closure": ["raw.osm.building", "raw.microsoft.building"],
            "allows_partial_coverage": self.allows_partial_coverage,
            "fallback_source_ids": [],
        }

    def failure_classification_policy(self):
        return default_policy_registry().failure_classification_policy()

    def source_mode_for_fault(self, fault_class: str) -> str:
        return default_policy_registry().source_mode_for_fault(fault_class)


def _building_data_requirements(
    *,
    reference_source_ids: tuple[str, ...] = ("raw.microsoft.building", "raw.google.building"),
    workflow_id: str = "workflow-k3",
) -> DataRequirementPlan:
    return DataRequirementPlan(
        task_kind=TaskKind.building,
        task_family="building",
        algorithm_id="algo.building.fusion",
        output_data_type="dt.building.bundle",
        roles=[
            SourceRoleRequirement(
                role_id="primary_footprint",
                required=True,
                bundle_slot=BundleSlot.primary,
                geometry_types=["Polygon", "MultiPolygon"],
                completeness_policy=CompletenessPolicy.required_non_empty,
                candidates=[
                    SourceCandidate(
                        source_id="raw.osm.building",
                        provider_family="osm",
                        priority=10,
                    )
                ],
            ),
            SourceRoleRequirement(
                role_id="reference_footprint",
                required=True,
                bundle_slot=BundleSlot.reference,
                distinct_from_role_ids=["primary_footprint"],
                geometry_types=["Polygon", "MultiPolygon"],
                completeness_policy=CompletenessPolicy.required_non_empty,
                candidates=[
                    SourceCandidate(
                        source_id=source_id,
                        provider_family="fixture",
                        priority=(index + 1) * 10,
                    )
                    for index, source_id in enumerate(reference_source_ids)
                ],
            ),
        ],
        evidence={
            "workflow_id": workflow_id,
            "resolver_version": "test",
            "basis": "frozen_kg_source_role_policy",
            "knowledge_identity": {
                "release_id": "fusionagent-kg-test",
                "semantic_hash": "sha256:" + "a" * 64,
            },
        },
    )


def _road_data_requirements() -> DataRequirementPlan:
    return DataRequirementPlan(
        task_kind=TaskKind.road,
        task_family="road",
        roles=[
            SourceRoleRequirement(
                role_id="base_network",
                required=True,
                bundle_slot=BundleSlot.primary,
                geometry_types=["LineString", "MultiLineString"],
                completeness_policy=CompletenessPolicy.required_non_empty,
                candidates=[
                    SourceCandidate(
                        source_id="raw.osm.road",
                        provider_family="osm",
                        priority=10,
                    )
                ],
            ),
            SourceRoleRequirement(
                role_id="reference_network",
                required=False,
                bundle_slot=BundleSlot.reference,
                distinct_from_role_ids=["base_network"],
                geometry_types=["LineString", "MultiLineString"],
                completeness_policy=CompletenessPolicy.optional_reference,
                candidates=[
                    SourceCandidate(
                        source_id="raw.microsoft.road",
                        provider_family="microsoft",
                        priority=10,
                    )
                ],
            ),
        ],
        evidence={
            "knowledge_identity": {
                "release_id": "fusionagent-kg-test",
                "semantic_hash": "sha256:" + "b" * 64,
            }
        },
    )


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


class _BuildingRawServiceWithRemoteBeforeOsm:
    local_source_ids = {"raw.osm.building", "raw.osm.road"}

    def __init__(self) -> None:
        self.resolved_source_ids: list[str] = []

    def resolve_local_source_path(self, source_id: str, *, resolved_aoi=None) -> Path:
        if source_id not in self.local_source_ids:
            raise FileNotFoundError(f"{source_id} is remote-only in this fixture")
        return Path(f"/fixture/{source_id.replace('.', '_')}.shp")

    def resolve(
        self,
        *,
        source_id: str,
        request_bbox,
        target_path: Path,
        target_crs: str,
        resolved_aoi=None,
    ):
        self.resolved_source_ids.append(source_id)
        if source_id not in self.local_source_ids:
            raise RuntimeError(f"slow remote source should not be resolved: {source_id}")

        target_path.parent.mkdir(parents=True, exist_ok=True)
        work_dir = target_path.parent / f"raw_{source_id.replace('.', '_')}"
        work_dir.mkdir(parents=True, exist_ok=True)
        shp_path = work_dir / "source.shp"
        if source_id == "raw.osm.road":
            frame = geopandas.GeoDataFrame(
                {"source": [source_id]},
                geometry=[LineString([(0, 0), (1, 1)])],
                crs="EPSG:4326",
            )
        else:
            frame = geopandas.GeoDataFrame(
                {"source": [source_id]},
                geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
                crs="EPSG:4326",
            )
        frame.to_file(shp_path)
        with zipfile.ZipFile(target_path, "w") as archive:
            for file in work_dir.glob("*"):
                archive.write(file, arcname=file.name)
        return MaterializedRawVectorSource(
            zip_path=target_path,
            bbox=request_bbox,
            target_crs=target_crs,
            source_id=source_id,
            source_mode="test_local_osm",
            cache_hit=False,
            version_token=f"{source_id}:test",
            feature_count=1,
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
    }
    assert [attempt["attempt_no"] for attempt in materialized.provider_attempts] == [1, 2, 3]


def test_local_bundle_catalog_building_bundle_does_not_accept_osm_only_shortcut(tmp_path: Path) -> None:
    raw_service = _BuildingRawServiceWithRemoteBeforeOsm()
    provider = LocalBundleCatalogProvider(tmp_path, raw_source_service=raw_service)

    with pytest.raises(BundleMaterializationError, match="required full closure") as exc_info:
        provider.materialize(
            source_id="catalog.flood.building",
            request_bbox=None,
            target_dir=tmp_path / "building_bundle_remote_before_osm",
            target_crs="EPSG:4326",
        )

    assert raw_service.resolved_source_ids == [
        "raw.osm.building",
        "raw.microsoft.building",
        "raw.google.building",
    ]
    assert exc_info.value.component_coverage["raw.osm.building"].feature_count == 1
    assert exc_info.value.component_coverage["raw.microsoft.building"].feature_count == 0


def test_local_bundle_catalog_adds_optional_preferred_building_height_raster(tmp_path: Path) -> None:
    _seed_local_catalog_tree(tmp_path)
    height_raster = tmp_path / "Data" / "buildings" / "height" / "OpenBuildings2_5D" / "height.tif"
    height_raster.parent.mkdir(parents=True, exist_ok=True)
    height_raster.write_bytes(b"fake-height-raster")
    provider = LocalBundleCatalogProvider(
        tmp_path,
        raw_source_service=RawVectorSourceService(
            root_dir=tmp_path,
            registry=ArtifactRegistry(index_path=tmp_path / "artifact_registry.json"),
            cache_dir=tmp_path / "raw-cache",
            source_asset_service=_NoRemoteSourceAssetService(),
        ),
        raster_height_source_service=RasterHeightSourceService(
            repo_root=tmp_path,
            cache_dir=tmp_path / "height-cache",
        ),
    )

    materialized = provider.materialize_with_fallback(
        source_id="catalog.flood.building",
        request_bbox=None,
        target_dir=tmp_path / "task6_building_bundle_with_height",
        target_crs="EPSG:4326",
    )

    coverage = materialized.component_coverage["raw.google.building_height.raster"]
    assert coverage["coverage_status"] == "available"
    assert coverage["path"] == str(height_raster)
    height_attempts = [
        attempt
        for attempt in materialized.provider_attempts
        if attempt["source_id"] == "raw.google.building_height.raster"
    ]
    assert height_attempts[0]["attempt_type"] == "skill"
    assert height_attempts[0]["skill_id"] == "skill.source_acquisition.building_height_raster"
    assert height_attempts[0]["selected_for_fusion"] is True
    assert [attempt["attempt_no"] for attempt in materialized.provider_attempts] == [1, 2, 3, 4]


def test_local_bundle_catalog_discovers_open_buildings_height_next_to_runtime_view(tmp_path: Path) -> None:
    runtime_view = tmp_path / "fusionagent_runtime_view"
    _seed_local_catalog_tree(runtime_view)
    height_raster = (
        tmp_path
        / "data"
        / "open_buildings_2_5d_2023_caracas_urban_height"
        / "height_8c2a4_2023_06_30_tile_Cqgsefqaijg.tif"
    )
    height_raster.parent.mkdir(parents=True, exist_ok=True)
    height_raster.write_bytes(b"fake-height-raster")
    provider = LocalBundleCatalogProvider(
        runtime_view,
        raw_source_service=RawVectorSourceService(
            root_dir=runtime_view,
            registry=ArtifactRegistry(index_path=tmp_path / "artifact_registry.json"),
            cache_dir=tmp_path / "raw-cache",
            source_asset_service=_NoRemoteSourceAssetService(),
        ),
        raster_height_source_service=RasterHeightSourceService(
            repo_root=runtime_view,
            cache_dir=tmp_path / "height-cache",
        ),
    )

    materialized = provider.materialize_with_fallback(
        source_id="catalog.earthquake.building",
        request_bbox=None,
        target_dir=tmp_path / "task6_building_bundle_with_caracas_height",
        target_crs="EPSG:4326",
    )

    coverage = materialized.component_coverage["raw.google.building_height.raster"]
    assert coverage["coverage_status"] == "available"
    assert coverage["path"] == str(height_raster)


def test_local_bundle_catalog_records_height_raster_degradation_without_blocking_building_bundle(tmp_path: Path) -> None:
    _seed_local_catalog_tree(tmp_path)
    provider = LocalBundleCatalogProvider(
        tmp_path,
        raw_source_service=RawVectorSourceService(
            root_dir=tmp_path,
            registry=ArtifactRegistry(index_path=tmp_path / "artifact_registry.json"),
            cache_dir=tmp_path / "raw-cache",
            source_asset_service=_NoRemoteSourceAssetService(),
        ),
        raster_height_source_service=RasterHeightSourceService(
            repo_root=tmp_path,
            cache_dir=tmp_path / "height-cache",
        ),
    )

    materialized = provider.materialize_with_fallback(
        source_id="catalog.flood.building",
        request_bbox=None,
        target_dir=tmp_path / "task6_building_bundle_without_height",
        target_crs="EPSG:4326",
    )

    assert materialized.osm_zip_path.exists()
    assert materialized.ref_zip_path.exists()
    assert materialized.component_coverage["raw.google.building_height.raster"]["coverage_status"] == "awaiting_external_config"
    attempts = {attempt["source_id"]: attempt for attempt in materialized.provider_attempts}
    assert attempts["raw.google.building_height.raster"]["attempt_type"] == "skill"
    assert attempts["raw.google.building_height.raster"]["status"] == "awaiting_external_config"


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
    }


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


def test_local_bundle_catalog_does_not_promote_local_overture_outside_kg_bundle_policy(tmp_path: Path) -> None:
    _seed_local_catalog_tree(tmp_path)
    microsoft_dir = tmp_path / "Data" / "roads" / "Microsoft"
    for path in microsoft_dir.glob("*"):
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
        target_dir=tmp_path / "road_bundle_overture_ref",
        target_crs="EPSG:4326",
    )

    assert materialized.source_id == "catalog.flood.road"
    assert materialized.component_coverage["raw.microsoft.road"].feature_count == 0
    assert "raw.overture.road" not in materialized.component_coverage
    assert [attempt["source_id"] for attempt in materialized.provider_attempts] == [
        "raw.osm.road",
        "raw.microsoft.road",
    ]
    ref_columns = _read_columns(materialized.ref_zip_path)
    assert "id" not in ref_columns
    assert "ms_road_id" not in ref_columns


def test_local_bundle_catalog_waterways_fails_when_strict_closure_is_incomplete(tmp_path: Path) -> None:
    provider = LocalBundleCatalogProvider(
        root_dir=tmp_path,
        raw_source_service=_RawServiceWithEmptyThenAvailableWater(),
    )

    with pytest.raises(BundleMaterializationError, match="did not satisfy its KG completeness contract"):
        provider.materialize_with_fallback(
            source_id="catalog.flood.waterways",
            request_bbox=(66.9, 24.8, 67.1, 25.0),
            target_dir=tmp_path / "bundle",
            target_crs="EPSG:4326",
        )


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


def test_role_candidate_priority_changes_materialized_reference(tmp_path: Path) -> None:
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

    microsoft_first = provider.materialize(
        source_id="catalog.flood.building",
        request_bbox=None,
        target_dir=tmp_path / "microsoft_first",
        target_crs="EPSG:4326",
        data_requirements=_building_data_requirements(),
    )
    google_first = provider.materialize(
        source_id="catalog.flood.building",
        request_bbox=None,
        target_dir=tmp_path / "google_first",
        target_crs="EPSG:4326",
        data_requirements=_building_data_requirements(
            reference_source_ids=("raw.google.building", "raw.microsoft.building")
        ),
    )

    assert "msft_id" in _read_columns(microsoft_first.ref_zip_path)
    assert "google_id" in _read_columns(google_first.ref_zip_path)
    assert microsoft_first.component_coverage["raw.microsoft.building"].selected_role_ids == (
        "reference_footprint",
    )
    assert google_first.component_coverage["raw.google.building"].selected_role_ids == (
        "reference_footprint",
    )


def test_required_role_missing_fails_even_when_bundle_allows_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_local_catalog_tree(tmp_path)
    for path in (tmp_path / "Data" / "roads" / "OSM").glob("*"):
        path.unlink()
    monkeypatch.setenv("GEOFUSION_LOCAL_ONLY", "1")
    provider = LocalBundleCatalogProvider(
        tmp_path,
        raw_source_service=RawVectorSourceService(
            root_dir=tmp_path,
            registry=ArtifactRegistry(index_path=tmp_path / "artifact_registry.json"),
            cache_dir=tmp_path / "raw-cache",
            source_asset_service=_NoRemoteSourceAssetService(),
        ),
    )

    with pytest.raises(BundleMaterializationError, match="required role base_network"):
        provider.materialize(
            source_id="catalog.flood.road",
            request_bbox=None,
            target_dir=tmp_path / "missing_required_road",
            target_crs="EPSG:4326",
            data_requirements=_road_data_requirements(),
        )


def test_allows_partial_coverage_switch_changes_full_closure_behavior(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_local_catalog_tree(tmp_path)
    for path in (tmp_path / "Data" / "buildings" / "Microsoft").glob("*"):
        path.unlink()
    monkeypatch.setenv("GEOFUSION_LOCAL_ONLY", "1")
    requirements = _building_data_requirements(
        reference_source_ids=("raw.google.building", "raw.microsoft.building")
    )

    strict_provider = LocalBundleCatalogProvider(
        tmp_path,
        raw_source_service=RawVectorSourceService(
            root_dir=tmp_path,
            registry=ArtifactRegistry(index_path=tmp_path / "strict_registry.json"),
            cache_dir=tmp_path / "strict-cache",
            source_asset_service=_NoRemoteSourceAssetService(),
        ),
        policy_registry=_BuildingBundlePolicyRegistry(allows_partial_coverage=False),
    )
    with pytest.raises(BundleMaterializationError, match="required full closure"):
        strict_provider.materialize(
            source_id="catalog.flood.building",
            request_bbox=None,
            target_dir=tmp_path / "strict_bundle",
            target_crs="EPSG:4326",
            data_requirements=requirements,
        )

    partial_provider = LocalBundleCatalogProvider(
        tmp_path,
        raw_source_service=RawVectorSourceService(
            root_dir=tmp_path,
            registry=ArtifactRegistry(index_path=tmp_path / "partial_registry.json"),
            cache_dir=tmp_path / "partial-cache",
            source_asset_service=_NoRemoteSourceAssetService(),
        ),
        policy_registry=_BuildingBundlePolicyRegistry(allows_partial_coverage=True),
    )
    partial = partial_provider.materialize(
        source_id="catalog.flood.building",
        request_bbox=None,
        target_dir=tmp_path / "partial_bundle",
        target_crs="EPSG:4326",
        data_requirements=requirements,
    )

    assert "google_id" in _read_columns(partial.ref_zip_path)
    assert partial.component_coverage["raw.microsoft.building"].feature_count == 0


def test_materialization_manifest_binds_kg_identity_and_component_roles(tmp_path: Path) -> None:
    _seed_local_catalog_tree(tmp_path)
    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    provider = LocalBundleCatalogProvider(
        tmp_path,
        raw_source_service=RawVectorSourceService(
            root_dir=tmp_path,
            registry=registry,
            cache_dir=tmp_path / "raw-cache",
            source_asset_service=_NoRemoteSourceAssetService(),
        ),
    )
    service = InputAcquisitionService(
        registry=registry,
        providers=[provider],
        cache_dir=tmp_path / "input-cache",
    )
    requirements = _building_data_requirements()
    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(
            type=RunTriggerType.user_query,
            content="materialize KG governed building inputs",
            spatial_extent="bbox(0,0,1,1)",
        ),
        target_crs="EPSG:4326",
        field_mapping={},
        input_strategy=RunInputStrategy.task_driven_auto,
    )

    resolved = service.resolve_task_driven_inputs(
        request=request,
        source_id="catalog.flood.building",
        required_output_type="dt.building.bundle",
        input_dir=tmp_path / "run",
        data_requirements=requirements,
    )

    manifest = json.loads(resolved.manifest_path.read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    assert manifest["knowledge_identity"] == requirements.evidence["knowledge_identity"]
    assert manifest["data_requirement_hash"].startswith("sha256:")
    assert manifest["component_coverage"]
    for component in manifest["component_coverage"].values():
        assert component["role_id"]
        assert component["role_contract"]["role_id"] == component["role_id"]
