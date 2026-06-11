from __future__ import annotations

from pathlib import Path
import zipfile

import geopandas as gpd
from shapely.geometry import box

from kg.source_catalog import build_data_sources
from schemas.agent import (
    RunCreateRequest,
    RunInputStrategy,
    RunPhase,
    RunStatus,
    RunTrigger,
    RunTriggerType,
    ValidationReport,
    WorkflowPlan,
    WorkflowTask,
    WorkflowTaskInput,
    WorkflowTaskOutput,
)
from schemas.fusion import JobType
import services.domain_fusion_runners as domain_runners
from services.agent_run_service import AgentRunService
from services.input_acquisition_service import ResolvedRunInputs
from services.source_profile_service import SourceProfile
from services.tile_partition_service import TileManifest, TileSpec
from services.tiled_building_runtime_service import TiledMultiSourceBuildingRunResult


def _single_tile_manifest() -> TileManifest:
    return TileManifest(
        bbox=(0.0, 0.0, 1.0, 1.0),
        bbox_crs="EPSG:4326",
        working_crs="EPSG:3857",
        tile_width_m=1.0,
        tile_height_m=1.0,
        overlap_m=0.0,
        tiles=[
            TileSpec(
                tile_id="tile_000_000",
                bbox=(0.0, 0.0, 1.0, 1.0),
                buffered_bbox=(0.0, 0.0, 1.0, 1.0),
                working_bbox=(0.0, 0.0, 1.0, 1.0),
                working_buffered_bbox=(0.0, 0.0, 1.0, 1.0),
                row=0,
                col=0,
            )
        ],
    )


class _Repo:
    def list_data_sources(self):
        return build_data_sources()


def _plan() -> WorkflowPlan:
    return WorkflowPlan(
        workflow_id="wf",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        tasks=[
            WorkflowTask(
                step=1,
                name="building",
                description="building",
                algorithm_id="algo.fusion.building.v1",
                input=WorkflowTaskInput(
                    data_type_id="dt.building.bundle",
                    data_source_id="catalog.earthquake.building",
                    parameters={"source_priority_order": ["MS", "OSM"]},
                ),
                output=WorkflowTaskOutput(data_type_id="dt.building.fused"),
            )
        ],
        expected_output="dt.building.fused",
        validation=ValidationReport(valid=True),
    )


def _write_building(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame(
        {"id": ["building-1"], "source_id": ["raw.osm.building"], "HEIGHT": [9.0]},
        geometry=[box(0.2, 0.2, 0.8, 0.8)],
        crs="EPSG:4326",
    ).to_file(path, driver="GPKG")
    return path


def test_large_building_run_routes_to_multisource_runtime_when_semantics_exist(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    run_id = "run-building"
    run_dir = service.base_dir / run_id
    for name in ["intermediate", "output", "logs"]:
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    output_path = run_dir / "output" / "building_large_area_fused.gpkg"
    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building", spatial_extent="bbox(0,0,1,1)"),
        input_strategy=RunInputStrategy.task_driven_auto,
    )
    status = RunStatus(
        run_id=run_id,
        job_type=JobType.building,
        trigger=request.trigger,
        phase=RunPhase.running,
        progress=55,
        target_crs="EPSG:3857",
        checkpoint={"stage": "execution"},
        created_at="2026-05-20T00:00:00+00:00",
        updated_at="2026-05-20T00:00:00+00:00",
    )
    service._persist_status(status)
    monkeypatch.setattr(service.tile_partition_service, "partition_bbox", lambda **_kwargs: _single_tile_manifest())
    plan = _plan()
    captured: dict[str, object] = {}

    def fake_multisource(self, **kwargs):
        del self
        captured.update(kwargs)
        tile_output = kwargs["output_dir"] / "fused_buildings.gpkg"
        gpd.GeoDataFrame(
            {"canonical_id": ["building-1"], "height_final": [12.0]},
            geometry=[box(0.2, 0.2, 0.8, 0.8)],
            crs=kwargs["target_crs"],
        ).to_file(tile_output, driver="GPKG")
        return TiledMultiSourceBuildingRunResult(
            output_path=tile_output,
            tile_count=1,
            stitched_feature_count=1,
            tile_outputs=[],
        )

    monkeypatch.setattr(
        domain_runners.TiledBuildingRuntimeService,
        "run_tiled_multisource_building_job",
        fake_multisource,
    )

    try:
        result_path, repairs = service.run_multisource_building_execution_stage(
            run_id=run_id,
            request=request,
            plan=plan,
            intermediate_dir=run_dir / "intermediate",
            output_dir=run_dir / "output",
            vector_sources={"MS": tmp_path / "ms.gpkg", "OSM": tmp_path / "osm.gpkg"},
            raster_sources={"building_height": tmp_path / "height.tif"},
            resolved_aoi=None,
        )
    finally:
        service.shutdown()

    assert result_path == output_path
    assert result_path.exists()
    assert repairs == []
    assert captured["source_priority_order"] == ("MS", "OSM")
    assert "building_height" in captured["raster_sources"]
    events = service.get_audit_events(run_id)
    completed = [event for event in events if event.kind == "large_area_runtime_completed"]
    assert completed
    assert completed[-1].details["tile_count"] == 1
    assert completed[-1].details["stitched_feature_count"] == 1
    assert "stitched_artifact" in completed[-1].details["evidence_paths"]


def test_raster_paths_for_source_semantics_returns_existing_height_raster(tmp_path: Path) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    height_path = tmp_path / "Data" / "buildings" / "rasters" / "height.tif"
    height_path.parent.mkdir(parents=True, exist_ok=True)
    height_path.write_bytes(b"fake-raster")
    resolved = ResolvedRunInputs(
        osm_zip_path=tmp_path / "osm.zip",
        ref_zip_path=tmp_path / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.earthquake.building",
        cache_hit=False,
        version_token="v1",
        selected_source_id="catalog.earthquake.building",
        component_coverage={
            "raw.google.building_height.raster": {
                "path": str(height_path),
                "feature_count": None,
                "source_mode": "local_raster",
            }
        },
    )

    try:
        rasters = service._raster_paths_for_source_semantics(resolved)
    finally:
        service.shutdown()

    assert rasters == {"raw.google.building_height.raster": height_path}


def test_source_semantics_keeps_raster_out_of_vector_component_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs", kg_repo=_Repo())
    run_id = "run-raster-semantics"
    run_dir = service.base_dir / run_id
    for name in ["intermediate", "logs"]:
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        input_strategy=RunInputStrategy.task_driven_auto,
    )
    status = RunStatus(
        run_id=run_id,
        job_type=JobType.building,
        trigger=request.trigger,
        phase=RunPhase.running,
        progress=50,
        target_crs="EPSG:4326",
        checkpoint={"stage": "execution"},
        created_at="2026-05-20T00:00:00+00:00",
        updated_at="2026-05-20T00:00:00+00:00",
    )
    service._persist_status(status)
    vector_path = _write_building(tmp_path / "microsoft.gpkg")
    height_path = tmp_path / "height.tif"
    height_path.write_bytes(b"fake-raster")
    resolved = ResolvedRunInputs(
        osm_zip_path=tmp_path / "osm.zip",
        ref_zip_path=tmp_path / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.earthquake.building",
        cache_hit=False,
        version_token="v1",
        selected_source_id="catalog.earthquake.building",
        component_coverage={
            "raw.microsoft.building": {"path": str(vector_path), "feature_count": 1},
            "raw.google.building_height.raster": {
                "path": str(height_path),
                "feature_count": None,
                "source_mode": "local_raster",
            },
        },
    )

    def fake_profile_raster_source(**kwargs):
        return SourceProfile(
            source_id=kwargs["source_id"],
            canonical_path=str(kwargs["path"]),
            source_form="raster",
            runtime_status="runtime_candidate",
            selectable_now=True,
            crs="EPSG:4326",
            feature_count=None,
            height_semantics="estimated_height",
        )

    monkeypatch.setattr(
        service.source_semantic_contract_service.profile_service,
        "profile_raster_source",
        fake_profile_raster_source,
    )

    try:
        component_paths = service._source_component_paths_from_resolved_inputs(
            run_id=run_id,
            resolved_inputs=resolved,
        )
        _, contract = service._bind_source_semantics_for_resolved_inputs(
            run_id=run_id,
            request=request,
            plan=_plan(),
            resolved_inputs=resolved,
        )
    finally:
        service.shutdown()

    assert component_paths == {"raw.microsoft.building": vector_path}
    assert contract is not None
    assert "raw.microsoft.building" in contract.sources
    assert "raw.google.building_height.raster" not in contract.sources
    assert contract.height_policy["raster_height_sources"] == {
        "raw.google.building_height.raster": str(height_path)
    }


def test_building_multisource_runner_uses_working_bbox_for_inner_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    output_path = tmp_path / "tile" / "fused_buildings.gpkg"

    def fake_multisource(self, **kwargs):
        del self
        captured.update(kwargs)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        gpd.GeoDataFrame(
            {"canonical_id": ["building-1"]},
            geometry=[box(100.0, 200.0, 101.0, 201.0)],
            crs=kwargs["target_crs"],
        ).to_file(output_path, driver="GPKG")
        return TiledMultiSourceBuildingRunResult(
            output_path=output_path,
            tile_count=1,
            stitched_feature_count=1,
            tile_outputs=[],
        )

    monkeypatch.setattr(
        domain_runners.TiledBuildingRuntimeService,
        "run_tiled_multisource_building_job",
        fake_multisource,
    )
    outer_tile = TileSpec(
        tile_id="tile_000_000",
        bbox=(0.0, 0.0, 0.01, 0.01),
        buffered_bbox=(-0.01, -0.01, 0.02, 0.02),
        working_bbox=(100.0, 200.0, 110.0, 220.0),
        working_buffered_bbox=(95.0, 195.0, 115.0, 225.0),
        row=0,
        col=0,
    )
    runner = domain_runners.make_building_multisource_runner(
        raster_sources={},
        source_priority_order=("MS", "OSM"),
    )

    result_path, _ = runner(
        outer_tile,
        {"MS": tmp_path / "ms.gpkg", "OSM": tmp_path / "osm.gpkg"},
        tmp_path / "tile",
        "EPSG:3857",
        {},
    )

    manifest = captured["tile_manifest"]
    inner_tile = manifest.tiles[0]
    assert result_path == output_path
    assert manifest.bbox_crs == "EPSG:3857"
    assert manifest.working_crs == "EPSG:3857"
    assert manifest.bbox == outer_tile.working_bbox
    assert inner_tile.bbox == outer_tile.working_bbox
    assert inner_tile.buffered_bbox == outer_tile.working_buffered_bbox
    assert inner_tile.working_bbox == outer_tile.working_bbox
    assert inner_tile.working_buffered_bbox == outer_tile.working_buffered_bbox


def test_writeback_stage_zips_gpkg_artifact_as_single_gpkg_member(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    run_id = "run-writeback-gpkg"
    gpkg_path = tmp_path / "fused_buildings.gpkg"
    _write_building(gpkg_path)
    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        input_strategy=RunInputStrategy.task_driven_auto,
    )
    status = RunStatus(
        run_id=run_id,
        job_type=JobType.building,
        trigger=request.trigger,
        phase=RunPhase.running,
        progress=80,
        target_crs="EPSG:4326",
        planning_telemetry={
            "component_coverage": {
                "raw.osm.building": {"feature_count": 1, "coverage_status": "available"},
                "raw.microsoft.building": {"feature_count": 1, "coverage_status": "available"},
            }
        },
        checkpoint={"stage": "writeback"},
        created_at="2026-05-20T00:00:00+00:00",
        updated_at="2026-05-20T00:00:00+00:00",
    )
    service._persist_status(status)
    monkeypatch.setattr(
        "services.agent_run_service.zip_shapefile_bundle",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("GPKG writeback must not use shapefile bundling")),
    )

    try:
        artifact = service.run_writeback_stage(
            run_id=run_id,
            request=request,
            plan=_plan(),
            fused_shp=gpkg_path,
            repair_records=[],
            output_dir=tmp_path / "output",
        )
    finally:
        service.shutdown()

    archive_path = Path(artifact.path)
    assert artifact.filename == "building_fusion_result.zip"
    assert archive_path.exists()
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
    assert names == ["fused_buildings.gpkg"]
