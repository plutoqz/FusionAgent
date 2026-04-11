from __future__ import annotations

import zipfile
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from schemas.agent import RunCreateRequest, RunInputStrategy, RunTrigger, RunTriggerType
from schemas.fusion import JobType
from services.artifact_registry import ArtifactRecord, ArtifactRegistry
from utils.shp_zip import zip_shapefile_bundle


class _StubBundleProvider:
    def __init__(self, *, version_token: str, supported_source_ids: set[str] | None = None) -> None:
        self.version_token = version_token
        self.download_calls = 0
        self.supported_source_ids = supported_source_ids or {"catalog.task.building.default"}

    def can_handle(self, source_id: str) -> bool:
        return source_id in self.supported_source_ids

    def current_version(self, source_id: str) -> str:
        assert self.can_handle(source_id)
        return self.version_token

    def materialize(self, *, source_id: str, request_bbox, target_dir: Path, target_crs: str):
        assert self.can_handle(source_id)
        self.download_calls += 1
        target_dir.mkdir(parents=True, exist_ok=True)
        osm_dir = target_dir / "osm"
        ref_dir = target_dir / "ref"
        osm_dir.mkdir(parents=True, exist_ok=True)
        ref_dir.mkdir(parents=True, exist_ok=True)

        osm = gpd.GeoDataFrame(
            {"osm_id": [1]},
            geometry=[Polygon([(0, 0), (0, 10), (10, 10), (10, 0)])],
            crs="EPSG:4326",
        ).to_crs(target_crs)
        ref = gpd.GeoDataFrame(
            {"confidence": [0.9]},
            geometry=[Polygon([(0, 0), (0, 10), (10, 10), (10, 0)])],
            crs="EPSG:4326",
        ).to_crs(target_crs)

        osm_shp = osm_dir / "osm.shp"
        ref_shp = ref_dir / "ref.shp"
        osm.to_file(osm_shp)
        ref.to_file(ref_shp)

        from services.input_acquisition_service import MaterializedInputBundle

        return MaterializedInputBundle(
            osm_zip_path=zip_shapefile_bundle(osm_shp, target_dir / "osm.zip"),
            ref_zip_path=zip_shapefile_bundle(ref_shp, target_dir / "ref.zip"),
            bbox=(0.0, 0.0, 10.0, 10.0),
            target_crs=target_crs,
        )


def _build_request(*, spatial_extent: str = "bbox(0,0,10,10)", target_crs: str = "EPSG:4326") -> RunCreateRequest:
    return RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(
            type=RunTriggerType.user_query,
            content="need building data",
            spatial_extent=spatial_extent,
        ),
        target_crs=target_crs,
        field_mapping={},
        debug=False,
        input_strategy=RunInputStrategy.task_driven_auto,
    )


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


def test_input_acquisition_reuses_cached_bundle_when_version_matches_and_clips_to_request_bbox(tmp_path: Path) -> None:
    from services.input_acquisition_service import InputAcquisitionService

    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    provider = _StubBundleProvider(version_token="v1")
    service = InputAcquisitionService(registry=registry, providers=[provider], cache_dir=tmp_path / "cache")

    initial = service.resolve_task_driven_inputs(
        request=_build_request(),
        source_id="catalog.task.building.default",
        required_output_type="dt.building.bundle",
        input_dir=tmp_path / "run1",
    )
    reused = service.resolve_task_driven_inputs(
        request=_build_request(spatial_extent="bbox(1,1,2,2)"),
        source_id="catalog.task.building.default",
        required_output_type="dt.building.bundle",
        input_dir=tmp_path / "run2",
    )

    assert initial.source_mode == "downloaded"
    assert reused.source_mode == "clip_reused"
    assert reused.cache_hit is True
    assert reused.version_token == "v1"
    assert provider.download_calls == 1
    assert _extract_bounds(reused.osm_zip_path) == [1.0, 1.0, 2.0, 2.0]
    assert _extract_bounds(reused.ref_zip_path) == [1.0, 1.0, 2.0, 2.0]


def test_input_acquisition_redownloads_bundle_when_cached_version_is_stale(tmp_path: Path) -> None:
    from services.input_acquisition_service import InputAcquisitionService

    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    provider = _StubBundleProvider(version_token="v2")
    service = InputAcquisitionService(registry=registry, providers=[provider], cache_dir=tmp_path / "cache")

    stale_dir = tmp_path / "stale_bundle"
    stale_initial = _StubBundleProvider(version_token="v1").materialize(
        source_id="catalog.task.building.default",
        request_bbox=None,
        target_dir=stale_dir,
        target_crs="EPSG:4326",
    )
    registry.register(
        ArtifactRecord(
            artifact_id="cached-stale",
            artifact_path=str(stale_dir),
            job_type="building",
            created_at="2026-04-11T00:00:00+00:00",
            output_data_type="dt.building.bundle",
            target_crs="EPSG:4326",
            bbox=stale_initial.bbox,
            meta={
                "artifact_role": "input_bundle",
                "source_id": "catalog.task.building.default",
                "source_version": "v1",
            },
        )
    )

    resolved = service.resolve_task_driven_inputs(
        request=_build_request(),
        source_id="catalog.task.building.default",
        required_output_type="dt.building.bundle",
        input_dir=tmp_path / "run",
    )

    assert resolved.source_mode == "downloaded"
    assert resolved.cache_hit is False
    assert resolved.version_token == "v2"
    assert provider.download_calls == 1


def test_input_acquisition_supports_catalog_earthquake_building_source(tmp_path: Path) -> None:
    from services.input_acquisition_service import InputAcquisitionService

    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    provider = _StubBundleProvider(
        version_token="v1",
        supported_source_ids={"catalog.earthquake.building"},
    )
    service = InputAcquisitionService(registry=registry, providers=[provider], cache_dir=tmp_path / "cache")

    resolved = service.resolve_task_driven_inputs(
        request=_build_request(),
        source_id="catalog.earthquake.building",
        required_output_type="dt.building.bundle",
        input_dir=tmp_path / "run",
    )

    assert resolved.source_id == "catalog.earthquake.building"
    assert resolved.source_mode == "downloaded"
    assert resolved.cache_hit is False
    assert resolved.version_token == "v1"


def test_input_acquisition_clip_reuse_transforms_request_bbox_into_cached_dataset_crs(tmp_path: Path) -> None:
    from services.input_acquisition_service import InputAcquisitionService

    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    provider = _StubBundleProvider(version_token="v1")
    service = InputAcquisitionService(registry=registry, providers=[provider], cache_dir=tmp_path / "cache")

    initial = service.resolve_task_driven_inputs(
        request=_build_request(target_crs="EPSG:3857"),
        source_id="catalog.task.building.default",
        required_output_type="dt.building.bundle",
        input_dir=tmp_path / "run1",
    )
    reused = service.resolve_task_driven_inputs(
        request=_build_request(spatial_extent="bbox(1,1,2,2)", target_crs="EPSG:3857"),
        source_id="catalog.task.building.default",
        required_output_type="dt.building.bundle",
        input_dir=tmp_path / "run2",
    )

    assert initial.source_mode == "downloaded"
    assert reused.source_mode == "clip_reused"
    assert reused.cache_hit is True
    assert provider.download_calls == 1
    assert _extract_bounds(reused.osm_zip_path) == pytest.approx([1.0, 1.0, 2.0, 2.0], abs=1e-3)
    assert _extract_bounds(reused.ref_zip_path) == pytest.approx([1.0, 1.0, 2.0, 2.0], abs=1e-3)
