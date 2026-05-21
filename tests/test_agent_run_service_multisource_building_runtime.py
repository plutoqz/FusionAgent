from __future__ import annotations

from pathlib import Path

from schemas.agent import RunCreateRequest, RunInputStrategy, RunPhase, RunStatus, RunTrigger, RunTriggerType, WorkflowPlan
from schemas.fusion import JobType
from services.agent_run_service import AgentRunService
from services.tiled_building_runtime_service import TiledMultiSourceBuildingRunResult


def test_large_building_run_routes_to_multisource_runtime_when_semantics_exist(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    run_id = "run-building"
    run_dir = service.base_dir / run_id
    for name in ["intermediate", "output", "logs"]:
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    output_path = run_dir / "output" / "fused_buildings.gpkg"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"gpkg")
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
    plan = WorkflowPlan.model_validate(
        {
            "workflow_id": "wf",
            "trigger": request.trigger.model_dump(mode="json"),
            "tasks": [
                {
                    "step": 1,
                    "name": "building",
                    "description": "building",
                    "algorithm_id": "algo.fusion.building.v1",
                    "input": {
                        "data_type_id": "dt.building.bundle",
                        "data_source_id": "catalog.earthquake.building",
                        "parameters": {"source_priority_order": ["MS", "OSM"]},
                    },
                    "output": {"data_type_id": "dt.building.fused"},
                }
            ],
            "expected_output": "dt.building.fused",
        }
    )
    captured: dict[str, object] = {}

    def fake_multisource(**kwargs):
        captured.update(kwargs)
        return TiledMultiSourceBuildingRunResult(
            output_path=output_path,
            tile_count=1,
            stitched_feature_count=1,
            tile_outputs=[],
        )

    monkeypatch.setattr(service.tiled_building_runtime_service, "run_tiled_multisource_building_job", fake_multisource)

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
    assert repairs == []
    assert captured["source_priority_order"] == ("MS", "OSM")
    assert "building_height" in captured["raster_sources"]
