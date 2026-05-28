from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point, Polygon

import services.large_area_runtime_service as large_area_runtime_service
from schemas.agent import (
    RepairRecord,
    RunCreateRequest,
    RunInputStrategy,
    RunPhase,
    RunStatus,
    RunTrigger,
    RunTriggerType,
    WorkflowPlan,
)
from schemas.fusion import JobType
from services.agent_run_service import AgentRunService
from services.input_acquisition_service import ResolvedRunInputs
from services.tile_partition_service import TileManifest, TileSpec


def _single_tile_manifest() -> TileManifest:
    return TileManifest(
        bbox=(0.0, 0.0, 2.0, 1.0),
        bbox_crs="EPSG:4326",
        working_crs="EPSG:3857",
        tile_width_m=1.0,
        tile_height_m=1.0,
        overlap_m=0.0,
        tiles=[
            TileSpec(
                tile_id="tile_000_000",
                bbox=(0.0, 0.0, 2.0, 1.0),
                buffered_bbox=(0.0, 0.0, 2.0, 1.0),
                working_bbox=(0.0, 0.0, 2.0, 1.0),
                working_buffered_bbox=(0.0, 0.0, 2.0, 1.0),
                row=0,
                col=0,
            )
        ],
    )


def _request(job_type: JobType) -> RunCreateRequest:
    return RunCreateRequest(
        job_type=job_type,
        trigger=RunTrigger(
            type=RunTriggerType.user_query,
            content=job_type.value,
            spatial_extent="bbox(0,0,2,1)",
        ),
        input_strategy=RunInputStrategy.task_driven_auto,
        target_crs="EPSG:3857",
    )


def _status(run_id: str, request: RunCreateRequest) -> RunStatus:
    return RunStatus(
        run_id=run_id,
        job_type=request.job_type,
        trigger=request.trigger,
        phase=RunPhase.running,
        progress=55,
        target_crs=request.target_crs,
        checkpoint={"stage": "execution"},
        created_at="2026-05-28T00:00:00+00:00",
        updated_at="2026-05-28T00:00:00+00:00",
    )


def _plan(source_id: str, input_type: str, output_type: str, algorithm_id: str) -> WorkflowPlan:
    return WorkflowPlan.model_validate(
        {
            "workflow_id": "wf",
            "trigger": {"type": "user_query", "content": "runtime"},
            "tasks": [
                {
                    "step": 1,
                    "name": "fusion",
                    "description": "fusion",
                    "algorithm_id": algorithm_id,
                    "input": {
                        "data_type_id": input_type,
                        "data_source_id": source_id,
                        "parameters": {},
                    },
                    "output": {"data_type_id": output_type},
                }
            ],
            "expected_output": output_type,
        }
    )


def _write(path: Path, frame: gpd.GeoDataFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(path, driver="GPKG")
    return path


def test_road_task_driven_run_uses_shared_large_area_runtime(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    run_id = "road-run"
    request = _request(JobType.road)
    run_dir = service.base_dir / run_id
    for name in ["intermediate", "output", "logs"]:
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    service._persist_status(_status(run_id, request))
    monkeypatch.setattr(service.tile_partition_service, "partition_bbox", lambda **_kwargs: _single_tile_manifest())

    osm = _write(
        tmp_path / "osm_road.gpkg",
        gpd.GeoDataFrame(
            {"osm_id": [1], "fclass": ["primary"]},
            geometry=[LineString([(0, 0), (2, 0)])],
            crs="EPSG:3857",
        ),
    )
    overture = _write(
        tmp_path / "overture_road.gpkg",
        gpd.GeoDataFrame(
            {"id": ["o1"], "class": ["primary"]},
            geometry=[LineString([(0, 0.1), (2, 0.1)])],
            crs="EPSG:3857",
        ),
    )
    resolved = ResolvedRunInputs(
        osm_zip_path=tmp_path / "osm.zip",
        ref_zip_path=tmp_path / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.flood.road",
        cache_hit=False,
        version_token="v1",
        selected_source_id="catalog.flood.road",
        component_coverage={
            "raw.osm.road": {"path": str(osm), "feature_count": 1},
            "raw.overture.transportation": {"path": str(overture), "feature_count": 1},
        },
    )

    try:
        path, repairs = service.run_large_area_execution_stage(
            run_id=run_id,
            request=request,
            plan=_plan(
                "catalog.flood.road",
                "dt.road.bundle",
                "dt.road.fused",
                "algo.fusion.road.conflation.v7",
            ),
            intermediate_dir=run_dir / "intermediate",
            output_dir=run_dir / "output",
            resolved_inputs=resolved,
            resolved_aoi=None,
        )
    finally:
        service.shutdown()

    assert repairs == []
    assert path.exists()
    assert (run_dir / "output" / "stitched_artifact.json").exists()


def test_water_task_driven_run_outputs_polygon_and_line_slices(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    run_id = "water-run"
    request = _request(JobType.water)
    run_dir = service.base_dir / run_id
    for name in ["intermediate", "output", "logs"]:
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    service._persist_status(_status(run_id, request))
    monkeypatch.setattr(service.tile_partition_service, "partition_bbox", lambda **_kwargs: _single_tile_manifest())

    osm_water = _write(
        tmp_path / "osm_water.gpkg",
        gpd.GeoDataFrame(
            {"osm_id": [1]},
            geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
            crs="EPSG:3857",
        ),
    )
    hydrolakes = _write(
        tmp_path / "hydrolakes.gpkg",
        gpd.GeoDataFrame(
            {"Hylak_id": [11]},
            geometry=[Polygon([(0.2, 0.2), (0.2, 0.8), (0.8, 0.8), (0.8, 0.2)])],
            crs="EPSG:3857",
        ),
    )
    osm_waterways = _write(
        tmp_path / "osm_waterways.gpkg",
        gpd.GeoDataFrame(
            {"osm_id": [2], "fclass": ["river"]},
            geometry=[LineString([(0, 0.5), (2, 0.5)])],
            crs="EPSG:3857",
        ),
    )
    hydrorivers = _write(
        tmp_path / "hydrorivers.gpkg",
        gpd.GeoDataFrame(
            {"HYRIV_ID": [22]},
            geometry=[LineString([(0, 0.55), (2, 0.55)])],
            crs="EPSG:3857",
        ),
    )
    resolved = ResolvedRunInputs(
        osm_zip_path=tmp_path / "osm.zip",
        ref_zip_path=tmp_path / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.flood.water",
        cache_hit=False,
        version_token="v1",
        selected_source_id="catalog.flood.water",
        component_coverage={
            "raw.osm.water": {"path": str(osm_water), "feature_count": 1},
            "raw.hydrolakes.water": {"path": str(hydrolakes), "feature_count": 1},
            "raw.osm.waterways": {"path": str(osm_waterways), "feature_count": 1},
            "raw.hydrorivers.water": {"path": str(hydrorivers), "feature_count": 1},
        },
    )

    try:
        path, repairs = service.run_large_area_execution_stage(
            run_id=run_id,
            request=request,
            plan=_plan(
                "catalog.flood.water",
                "dt.water.bundle",
                "dt.water.fused",
                "algo.fusion.water_polygon.priority_merge.v2",
            ),
            intermediate_dir=run_dir / "intermediate",
            output_dir=run_dir / "output",
            resolved_inputs=resolved,
            resolved_aoi=None,
        )
    finally:
        service.shutdown()

    fused = gpd.read_file(path)
    assert repairs == []
    assert {"polygon", "line"}.issubset(set(fused["feature_kind"]))


def test_task5_large_area_runtime_claims_road_and_water_but_not_poi(tmp_path: Path) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    resolved = ResolvedRunInputs(
        osm_zip_path=tmp_path / "osm.zip",
        ref_zip_path=tmp_path / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.flood.water",
        cache_hit=False,
        version_token="v1",
        selected_source_id="catalog.flood.water",
        component_coverage={
            "raw.osm.water": {"path": str(tmp_path / "water.gpkg"), "feature_count": 1},
            "raw.hydrolakes.water": {"path": str(tmp_path / "hydrolakes.gpkg"), "feature_count": 1},
        },
    )

    try:
        water = service._should_use_large_area_runtime(
            request=_request(JobType.water),
            plan=_plan("catalog.flood.water", "dt.water.bundle", "dt.water.fused", "algo.fusion.water.v1"),
            resolved_inputs=resolved,
            resolved_aoi=None,
        )
        poi = service._should_use_large_area_runtime(
            request=_request(JobType.poi),
            plan=_plan("catalog.generic.poi", "dt.poi.bundle", "dt.poi.fused", "algo.fusion.poi.geohash_neighbor_match.v1"),
            resolved_inputs=resolved,
            resolved_aoi=None,
        )
    finally:
        service.shutdown()

    assert water is True
    assert poi is False


def test_road_large_area_runtime_allows_partial_component_paths_without_keyerror(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    run_id = "road-partial-run"
    request = _request(JobType.road)
    run_dir = service.base_dir / run_id
    for name in ["intermediate", "output", "logs"]:
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    service._persist_status(_status(run_id, request))
    monkeypatch.setattr(service.tile_partition_service, "partition_bbox", lambda **_kwargs: _single_tile_manifest())
    osm = _write(
        tmp_path / "osm_road.gpkg",
        gpd.GeoDataFrame(
            {"osm_id": [1], "fclass": ["primary"]},
            geometry=[LineString([(0, 0), (2, 0)])],
            crs="EPSG:3857",
        ),
    )
    resolved = ResolvedRunInputs(
        osm_zip_path=tmp_path / "osm.zip",
        ref_zip_path=tmp_path / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.flood.road",
        cache_hit=False,
        version_token="v1",
        selected_source_id="catalog.flood.road",
        component_coverage={
            "raw.osm.road": {"path": str(osm), "feature_count": 1},
            "raw.overture.transportation": {"feature_count": 0},
        },
    )

    try:
        path, repairs = service.run_large_area_execution_stage(
            run_id=run_id,
            request=request,
            plan=_plan(
                "catalog.flood.road",
                "dt.road.bundle",
                "dt.road.fused",
                "algo.fusion.road.conflation.v7",
            ),
            intermediate_dir=run_dir / "intermediate",
            output_dir=run_dir / "output",
            resolved_inputs=resolved,
            resolved_aoi=None,
        )
    finally:
        service.shutdown()

    fused = gpd.read_file(path)
    assert repairs == []
    assert path.exists()
    assert fused.empty


def test_large_area_runtime_failure_records_repair_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    run_id = "road-failure-run"
    request = _request(JobType.road)
    run_dir = service.base_dir / run_id
    for name in ["intermediate", "output", "logs"]:
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    service._persist_status(_status(run_id, request))
    monkeypatch.setattr(service.tile_partition_service, "partition_bbox", lambda **_kwargs: _single_tile_manifest())
    osm = _write(
        tmp_path / "osm_road.gpkg",
        gpd.GeoDataFrame(
            {"osm_id": [1], "fclass": ["primary"]},
            geometry=[LineString([(0, 0), (2, 0)])],
            crs="EPSG:3857",
        ),
    )
    overture = _write(
        tmp_path / "overture_road.gpkg",
        gpd.GeoDataFrame(
            {"id": ["o1"], "class": ["primary"]},
            geometry=[LineString([(0, 0.1), (2, 0.1)])],
            crs="EPSG:3857",
        ),
    )
    resolved = ResolvedRunInputs(
        osm_zip_path=tmp_path / "osm.zip",
        ref_zip_path=tmp_path / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.flood.road",
        cache_hit=False,
        version_token="v1",
        selected_source_id="catalog.flood.road",
        component_coverage={
            "raw.osm.road": {"path": str(osm), "feature_count": 1},
            "raw.overture.transportation": {"path": str(overture), "feature_count": 1},
        },
    )

    class FailingLargeAreaRuntimeService:
        def __init__(self, *, max_workers: int = 1) -> None:
            del max_workers

        def run(self, **_kwargs):
            raise RuntimeError("runner failed")

    monkeypatch.setattr(large_area_runtime_service, "LargeAreaRuntimeService", FailingLargeAreaRuntimeService)
    repair_records: list[RepairRecord] = []

    try:
        with pytest.raises(RuntimeError, match="large-area runtime failed.*step=1.*algo.fusion.road.conflation.v7"):
            service.run_large_area_execution_stage(
                run_id=run_id,
                request=request,
                plan=_plan(
                    "catalog.flood.road",
                    "dt.road.bundle",
                    "dt.road.fused",
                    "algo.fusion.road.conflation.v7",
                ),
                intermediate_dir=run_dir / "intermediate",
                output_dir=run_dir / "output",
                resolved_inputs=resolved,
                resolved_aoi=None,
                repair_records=repair_records,
            )
    finally:
        service.shutdown()

    assert service._infer_failed_step(repair_records) == 1
    assert repair_records[-1].strategy == "large_area_runtime_execution"
    assert repair_records[-1].reason_code == "large_area_runtime_failed"
