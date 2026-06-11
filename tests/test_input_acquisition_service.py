from __future__ import annotations

import json
import zipfile
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from schemas.agent import RunCreateRequest, RunInputStrategy, RunTrigger, RunTriggerType
from schemas.fusion import JobType
from services.aoi_resolution_service import ResolvedAOI
from services.artifact_registry import ArtifactLookupRequest, ArtifactRecord, ArtifactRegistry
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
            geometry=[Polygon([(-180, -90), (-180, 90), (180, 90), (180, -90)])],
            crs="EPSG:4326",
        ).to_crs(target_crs)
        ref = gpd.GeoDataFrame(
            {"confidence": [0.9]},
            geometry=[Polygon([(-180, -90), (-180, 90), (180, 90), (180, -90)])],
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


class _AttemptRecordingBundleProvider(_StubBundleProvider):
    def materialize(self, *, source_id: str, request_bbox, target_dir: Path, target_crs: str):
        bundle = super().materialize(
            source_id=source_id,
            request_bbox=request_bbox,
            target_dir=target_dir,
            target_crs=target_crs,
        )
        from services.input_acquisition_service import MaterializedInputBundle

        return MaterializedInputBundle(
            osm_zip_path=bundle.osm_zip_path,
            ref_zip_path=bundle.ref_zip_path,
            bbox=bundle.bbox,
            target_crs=bundle.target_crs,
            source_id="catalog.flood.building",
            fallback_from="catalog.earthquake.building",
            attempted_sources=["catalog.earthquake.building", "catalog.flood.building"],
            component_coverage={
                "raw.osm.building": {
                    "source_id": "raw.osm.building",
                    "source_mode": "downloaded",
                    "feature_count": 1,
                    "coverage_status": "available",
                }
            },
        )


class _PoiSourceAttemptsBundleProvider(_StubBundleProvider):
    def materialize(self, *, source_id: str, request_bbox, target_dir: Path, target_crs: str):
        bundle = super().materialize(
            source_id=source_id,
            request_bbox=request_bbox,
            target_dir=target_dir,
            target_crs=target_crs,
        )
        from services.input_acquisition_service import MaterializedInputBundle

        component_coverage = {
            source_id: {
                "source_id": source_id,
                "source_mode": "downloaded",
                "feature_count": index + 1,
                "coverage_status": "available",
            }
            for index, source_id in enumerate(("raw.osm.poi", "raw.google.poi", "raw.gns.poi"))
        }

        return MaterializedInputBundle(
            osm_zip_path=bundle.osm_zip_path,
            ref_zip_path=bundle.ref_zip_path,
            bbox=bundle.bbox,
            target_crs=bundle.target_crs,
            source_id=source_id,
            component_coverage=component_coverage,
            provider_attempts=[
                {"source_id": source_id, "status": "available"}
                for source_id in ("raw.osm.poi", "raw.google.poi", "raw.gns.poi")
            ],
        )


class _CoverageOnlyPoiBundleProvider(_StubBundleProvider):
    def materialize(self, *, source_id: str, request_bbox, target_dir: Path, target_crs: str):
        bundle = super().materialize(
            source_id=source_id,
            request_bbox=request_bbox,
            target_dir=target_dir,
            target_crs=target_crs,
        )
        from services.input_acquisition_service import MaterializedInputBundle

        return MaterializedInputBundle(
            osm_zip_path=bundle.osm_zip_path,
            ref_zip_path=bundle.ref_zip_path,
            bbox=bundle.bbox,
            target_crs=bundle.target_crs,
            source_id=source_id,
            component_coverage={
                "raw.osm.poi": {
                    "source_id": "raw.osm.poi",
                    "source_mode": "downloaded",
                    "feature_count": 3,
                    "coverage_status": "available",
                },
                "raw.gns.poi": {
                    "source_id": "raw.gns.poi",
                    "source_mode": "downloaded",
                    "feature_count": 0,
                    "coverage_status": "empty",
                },
            },
        )


class _DegradedExternalAttemptBundleProvider(_StubBundleProvider):
    def materialize(self, *, source_id: str, request_bbox, target_dir: Path, target_crs: str):
        bundle = super().materialize(
            source_id=source_id,
            request_bbox=request_bbox,
            target_dir=target_dir,
            target_crs=target_crs,
        )
        from services.input_acquisition_service import MaterializedInputBundle

        return MaterializedInputBundle(
            osm_zip_path=bundle.osm_zip_path,
            ref_zip_path=bundle.ref_zip_path,
            bbox=bundle.bbox,
            target_crs=bundle.target_crs,
            source_id=source_id,
            component_coverage={
                "raw.osm.poi": {
                    "source_id": "raw.osm.poi",
                    "source_mode": "downloaded",
                    "feature_count": 2,
                    "coverage_status": "available",
                },
                "raw.google.poi": {
                    "source_id": "raw.google.poi",
                    "source_mode": "downloaded",
                    "feature_count": 0,
                    "coverage_status": "missing",
                },
            },
            provider_attempts=[
                {"source_id": "raw.osm.poi", "status": "available", "feature_count": 2},
                {
                    "source_id": "raw.google.poi",
                    "status": "attempted",
                    "fault_class": "NETWORK_FAILED",
                    "fault_message": "network down",
                    "feature_count": 0,
                },
            ],
        )


class _FaultingBundleProvider:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def can_handle(self, source_id: str) -> bool:
        return source_id == "catalog.flood.water"

    def current_version(self, source_id: str) -> str:
        assert source_id == "catalog.flood.water"
        return "fault-v1"

    def materialize(self, *, source_id: str, request_bbox, target_dir: Path, target_crs: str):
        assert source_id == "catalog.flood.water"
        raise self.exc


def _build_request(
    *,
    spatial_extent: str = "bbox(0,0,10,10)",
    target_crs: str = "EPSG:4326",
    job_type: JobType = JobType.building,
    content: str = "need building data",
) -> RunCreateRequest:
    return RunCreateRequest(
        job_type=job_type,
        trigger=RunTrigger(
            type=RunTriggerType.user_query,
            content=content,
            spatial_extent=spatial_extent,
        ),
        target_crs=target_crs,
        field_mapping={},
        debug=False,
        input_strategy=RunInputStrategy.task_driven_auto,
    )


def _resolved_nairobi_aoi() -> ResolvedAOI:
    return ResolvedAOI(
        query="Nairobi, Kenya",
        display_name="Nairobi, Nairobi County, Kenya",
        country_name="Kenya",
        country_code="ke",
        bbox=(36.65, -1.45, 37.10, -1.10),
        confidence=0.97,
        selection_reason="single_high_confidence_candidate",
        candidates=(),
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
    same_bbox_reused = service.resolve_task_driven_inputs(
        request=_build_request(),
        source_id="catalog.task.building.default",
        required_output_type="dt.building.bundle",
        input_dir=tmp_path / "run2",
    )
    reused = service.resolve_task_driven_inputs(
        request=_build_request(spatial_extent="bbox(1,1,2,2)"),
        source_id="catalog.task.building.default",
        required_output_type="dt.building.bundle",
        input_dir=tmp_path / "run3",
    )

    assert initial.source_mode == "downloaded"
    assert same_bbox_reused.source_mode == "cache_reused"
    assert same_bbox_reused.cache_hit is True
    assert same_bbox_reused.manifest_path is not None
    same_bbox_manifest = json.loads(same_bbox_reused.manifest_path.read_text(encoding="utf-8"))
    assert same_bbox_manifest["source_mode"] == "cache_reused"
    assert same_bbox_manifest["cache_hit"] is True
    assert same_bbox_manifest["requested_bbox"] == [0.0, 0.0, 10.0, 10.0]
    assert same_bbox_manifest["clipped_to_aoi"] is False
    assert reused.source_mode == "clip_reused"
    assert reused.cache_hit is True
    assert reused.version_token == "v1"
    assert reused.manifest_path is not None
    reused_manifest = json.loads(reused.manifest_path.read_text(encoding="utf-8"))
    assert reused_manifest["source_mode"] == "clip_reused"
    assert reused_manifest["cache_hit"] is True
    assert reused_manifest["requested_bbox"] == [1.0, 1.0, 2.0, 2.0]
    assert reused_manifest["materialized_bbox"] == [1.0, 1.0, 2.0, 2.0]
    assert reused_manifest["clipped_to_aoi"] is True
    assert reused_manifest["source_attempts_path"] == "source_attempts.json"
    reused_attempts = json.loads((reused.manifest_path.parent / "source_attempts.json").read_text(encoding="utf-8"))
    assert reused_attempts["coverage_state"] == "missing"
    assert reused_attempts["attempts"][0]["status"] == "cache_reused"
    assert reused_manifest["provider_attempts"] == [
        {
            "source_id": "catalog.task.building.default",
            "status": "cache_reused",
            "attempt_type": "provider",
            "recoverable": False,
        }
    ]
    assert provider.download_calls == 1
    assert _extract_bounds(reused.osm_zip_path) == [1.0, 1.0, 2.0, 2.0]
    assert _extract_bounds(reused.ref_zip_path) == [1.0, 1.0, 2.0, 2.0]

    records = registry.list_reusable(
        ArtifactLookupRequest(required_artifact_role="input_bundle"),
        limit=10,
    )
    assert records
    assert records[0].artifact_role == "input_bundle"


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
    assert resolved.manifest_path is not None
    manifest = json.loads(resolved.manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_id"] == "catalog.task.building.default"
    assert manifest["selected_source_id"] == "catalog.task.building.default"
    assert manifest["source_mode"] == "downloaded"
    assert manifest["cache_hit"] is False
    assert manifest["version_token"] == "v2"
    assert manifest["target_crs"] == "EPSG:4326"
    assert manifest["requested_bbox"] == [0.0, 0.0, 10.0, 10.0]
    assert manifest["materialized_bbox"] == [0.0, 0.0, 10.0, 10.0]
    assert manifest["clipped_to_aoi"] is True
    assert manifest["provider_attempts"] == [
        {
            "source_id": "catalog.task.building.default",
            "status": "materialized",
            "attempt_type": "provider",
            "recoverable": False,
        }
    ]
    assert manifest["fault"] is None
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


def test_input_acquisition_supports_catalog_flood_water_source_and_preserves_version_token(tmp_path: Path) -> None:
    from services.input_acquisition_service import InputAcquisitionService

    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    provider = _StubBundleProvider(
        version_token="water-osm-v1|water-ref-v1",
        supported_source_ids={"catalog.flood.water"},
    )
    service = InputAcquisitionService(registry=registry, providers=[provider], cache_dir=tmp_path / "cache")

    resolved = service.resolve_task_driven_inputs(
        request=_build_request(
            job_type=JobType.water,
            content="need water data",
        ),
        source_id="catalog.flood.water",
        required_output_type="dt.water.bundle",
        input_dir=tmp_path / "run",
    )

    assert resolved.source_id == "catalog.flood.water"
    assert resolved.source_mode == "downloaded"
    assert resolved.cache_hit is False
    assert resolved.version_token == "water-osm-v1|water-ref-v1"


def test_input_acquisition_sanitizes_composite_version_tokens_for_cache_paths(tmp_path: Path) -> None:
    from services.input_acquisition_service import InputAcquisitionService

    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    provider = _StubBundleProvider(
        version_token="57bc0c18328c05e1f7af0bcb38669c0981ea6306|20c32cf4490675d928294532486a20438cde6d73",
        supported_source_ids={"catalog.earthquake.building"},
    )
    service = InputAcquisitionService(registry=registry, providers=[provider], cache_dir=tmp_path / "cache")

    resolved = service.resolve_task_driven_inputs(
        request=_build_request(),
        source_id="catalog.earthquake.building",
        required_output_type="dt.building.bundle",
        input_dir=tmp_path / "run",
    )

    assert resolved.source_mode == "downloaded"
    assert resolved.cache_hit is False
    assert provider.download_calls == 1
    assert resolved.osm_zip_path.exists()
    assert resolved.ref_zip_path.exists()
    assert all("|" not in str(path) for path in (resolved.osm_zip_path, resolved.ref_zip_path))
    assert not any("|" in str(path) for path in (tmp_path / "cache").rglob("*"))


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


def test_input_acquisition_uses_resolved_aoi_bbox_when_trigger_has_no_spatial_extent(tmp_path: Path) -> None:
    from services.input_acquisition_service import InputAcquisitionService

    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    provider = _StubBundleProvider(version_token="v1")
    service = InputAcquisitionService(registry=registry, providers=[provider], cache_dir=tmp_path / "cache")

    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="need building data for Nairobi, Kenya"),
        target_crs="EPSG:4326",
        field_mapping={},
        debug=False,
        input_strategy=RunInputStrategy.task_driven_auto,
    )

    resolved = service.resolve_task_driven_inputs(
        request=request,
        source_id="catalog.task.building.default",
        required_output_type="dt.building.bundle",
        input_dir=tmp_path / "run",
        request_bbox=_resolved_nairobi_aoi().bbox,
        resolved_aoi=_resolved_nairobi_aoi(),
    )

    assert resolved.source_mode == "downloaded"
    assert resolved.cache_hit is False
    assert provider.download_calls == 1
    assert _extract_bounds(resolved.osm_zip_path) == pytest.approx([36.65, -1.45, 37.10, -1.10], abs=1e-3)
    assert _extract_bounds(resolved.ref_zip_path) == pytest.approx([36.65, -1.45, 37.10, -1.10], abs=1e-3)


def test_input_acquisition_manifest_records_provider_attempts_and_component_coverage(tmp_path: Path) -> None:
    from services.input_acquisition_service import InputAcquisitionService

    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    provider = _AttemptRecordingBundleProvider(
        version_token="fallback-v1",
        supported_source_ids={"catalog.earthquake.building"},
    )
    service = InputAcquisitionService(registry=registry, providers=[provider], cache_dir=tmp_path / "cache")

    resolved = service.resolve_task_driven_inputs(
        request=_build_request(),
        source_id="catalog.earthquake.building",
        required_output_type="dt.building.bundle",
        input_dir=tmp_path / "run",
    )

    assert resolved.manifest_path is not None
    manifest = json.loads(resolved.manifest_path.read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 2
    assert manifest["artifact_role"] == "input_bundle"
    assert manifest["selected_source_id"] == "catalog.flood.building"
    assert manifest["component_coverage"]["raw.osm.building"]["coverage_status"] == "available"
    assert manifest["provider_attempts"][0]["attempt_type"] == "provider"
    assert manifest["provider_attempts"] == [
        {
            "source_id": "catalog.earthquake.building",
            "status": "attempted",
            "attempt_type": "provider",
            "recoverable": False,
        },
        {
            "source_id": "catalog.flood.building",
            "status": "materialized",
            "attempt_type": "provider",
            "recoverable": False,
        },
    ]


def test_input_acquisition_writes_structured_source_attempts_evidence(tmp_path: Path) -> None:
    from services.input_acquisition_service import InputAcquisitionService

    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    provider = _PoiSourceAttemptsBundleProvider(
        version_token="poi-v1",
        supported_source_ids={"catalog.generic.poi"},
    )
    service = InputAcquisitionService(registry=registry, providers=[provider], cache_dir=tmp_path / "cache")

    resolved = service.resolve_task_driven_inputs(
        request=_build_request(job_type=JobType.poi, content="need poi data"),
        source_id="catalog.generic.poi",
        required_output_type="dt.poi.bundle",
        input_dir=tmp_path / "run-input",
        request_bbox=(0, 0, 1, 1),
    )

    assert resolved.manifest_path is not None
    source_attempts_path = resolved.manifest_path.parent / "source_attempts.json"
    assert source_attempts_path.exists()

    payload = json.loads(source_attempts_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["coverage_state"] == "complete"
    assert [attempt["source_id"] for attempt in payload["attempts"]] == [
        "raw.osm.poi",
        "raw.google.poi",
        "raw.gns.poi",
    ]
    assert payload["component_coverage"]["raw.google.poi"]["coverage_status"] == "available"

    manifest = json.loads(resolved.manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_attempts_path"] == "source_attempts.json"
    assert manifest["coverage_state"] == "complete"
    assert manifest["degradation"] == {
        "degraded_source_ids": [],
        "external_uncontrollable_source_ids": [],
    }


def test_input_acquisition_synthesizes_source_attempts_from_component_coverage(tmp_path: Path) -> None:
    from services.input_acquisition_service import InputAcquisitionService

    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    provider = _CoverageOnlyPoiBundleProvider(
        version_token="poi-coverage-v1",
        supported_source_ids={"catalog.generic.poi"},
    )
    service = InputAcquisitionService(registry=registry, providers=[provider], cache_dir=tmp_path / "cache")

    resolved = service.resolve_task_driven_inputs(
        request=_build_request(job_type=JobType.poi, content="need poi data"),
        source_id="catalog.generic.poi",
        required_output_type="dt.poi.bundle",
        input_dir=tmp_path / "run",
        request_bbox=(0, 0, 1, 1),
    )

    assert resolved.manifest_path is not None
    payload = json.loads((resolved.manifest_path.parent / "source_attempts.json").read_text(encoding="utf-8"))
    attempts = {attempt["source_id"]: attempt for attempt in payload["attempts"]}
    assert attempts["raw.osm.poi"]["status"] == "available"
    assert attempts["raw.osm.poi"]["feature_count"] == 3
    assert attempts["raw.osm.poi"]["selected_for_fusion"] is True
    assert attempts["raw.gns.poi"]["status"] == "empty"
    assert attempts["raw.gns.poi"]["feature_count"] == 0
    assert attempts["raw.gns.poi"]["selected_for_fusion"] is False
    assert payload["degradation"]["degraded_source_ids"] == ["raw.gns.poi"]


def test_input_acquisition_cache_reuse_preserves_raw_degraded_external_attempts(tmp_path: Path) -> None:
    from services.input_acquisition_service import InputAcquisitionService

    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    provider = _DegradedExternalAttemptBundleProvider(
        version_token="poi-degraded-v1",
        supported_source_ids={"catalog.generic.poi"},
    )
    service = InputAcquisitionService(registry=registry, providers=[provider], cache_dir=tmp_path / "cache")

    service.resolve_task_driven_inputs(
        request=_build_request(job_type=JobType.poi, content="need poi data"),
        source_id="catalog.generic.poi",
        required_output_type="dt.poi.bundle",
        input_dir=tmp_path / "run1",
    )
    reused = service.resolve_task_driven_inputs(
        request=_build_request(job_type=JobType.poi, content="need poi data"),
        source_id="catalog.generic.poi",
        required_output_type="dt.poi.bundle",
        input_dir=tmp_path / "run2",
    )

    assert reused.source_mode == "cache_reused"
    assert reused.manifest_path is not None
    payload = json.loads((reused.manifest_path.parent / "source_attempts.json").read_text(encoding="utf-8"))
    attempts = {attempt["source_id"]: attempt for attempt in payload["attempts"]}
    assert set(attempts) == {"raw.osm.poi", "raw.google.poi"}
    assert attempts["raw.osm.poi"]["status"] == "cache_reused"
    assert attempts["raw.google.poi"]["status"] == "network_failed"
    assert attempts["raw.google.poi"]["external_uncontrollable"] is True
    assert payload["degradation"]["degraded_source_ids"] == ["raw.google.poi"]
    assert payload["degradation"]["external_uncontrollable_source_ids"] == ["raw.google.poi"]


def test_input_acquisition_writes_manifest_for_failed_provider(tmp_path: Path) -> None:
    from services.input_acquisition_service import InputAcquisitionService

    service = InputAcquisitionService(
        registry=ArtifactRegistry(index_path=tmp_path / "artifact_registry.json"),
        providers=[_FaultingBundleProvider(FileNotFoundError("missing source asset"))],
        cache_dir=tmp_path / "cache",
    )

    with pytest.raises(ValueError, match="SOURCE_MISSING"):
        service.resolve_task_driven_inputs(
            request=_build_request(job_type=JobType.water, content="need water data"),
            source_id="catalog.flood.water",
            required_output_type="dt.water.bundle",
            input_dir=tmp_path / "run",
        )

    manifest = json.loads((tmp_path / "run" / "source_materialization_manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 2
    assert manifest["artifact_role"] == "input_bundle"
    assert manifest["source_id"] == "catalog.flood.water"
    assert manifest["source_mode"] == "failed"
    assert manifest["cache_hit"] is False
    assert manifest["source_attempts_path"] == "source_attempts.json"
    source_attempts = json.loads((tmp_path / "run" / "source_attempts.json").read_text(encoding="utf-8"))
    assert source_attempts["coverage_state"] == "missing"
    assert source_attempts["attempts"][0]["status"] == "provider_failed"
    assert manifest["fault"]["fault_class"] == "SOURCE_MISSING"
    assert manifest["fault"]["recoverable"] is True
    attempt = manifest["provider_attempts"][0]
    assert attempt["source_id"] == "catalog.flood.water"
    assert attempt["status"] == "failed"
    assert attempt["fault_class"] == "SOURCE_MISSING"
    assert attempt["recoverable"] is True
    assert attempt["next_retry_after_seconds"] == 30
    assert attempt["channel"] == "provider"


def test_input_acquisition_failed_provider_records_external_normalized_source_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.input_acquisition_service as input_acquisition_service
    from services.input_acquisition_service import InputAcquisitionService

    monkeypatch.setattr(input_acquisition_service, "classify_source_fault", lambda **_: "NETWORK_FAILED")
    service = InputAcquisitionService(
        registry=ArtifactRegistry(index_path=tmp_path / "artifact_registry.json"),
        providers=[_FaultingBundleProvider(RuntimeError("temporary network outage"))],
        cache_dir=tmp_path / "cache",
    )

    with pytest.raises(ValueError, match="NETWORK_FAILED"):
        service.resolve_task_driven_inputs(
            request=_build_request(job_type=JobType.water, content="need water data"),
            source_id="catalog.flood.water",
            required_output_type="dt.water.bundle",
            input_dir=tmp_path / "run",
        )

    source_attempts = json.loads((tmp_path / "run" / "source_attempts.json").read_text(encoding="utf-8"))
    assert source_attempts["attempts"][0]["status"] == "network_failed"
    assert source_attempts["attempts"][0]["external_uncontrollable"] is True
    assert source_attempts["degradation"] == {
        "degraded_source_ids": ["catalog.flood.water"],
        "external_uncontrollable_source_ids": ["catalog.flood.water"],
    }
    manifest = json.loads((tmp_path / "run" / "source_materialization_manifest.json").read_text(encoding="utf-8"))
    assert manifest["degradation"] == source_attempts["degradation"]
