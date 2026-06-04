import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zipfile import ZipFile

import geopandas as gpd
import pytest
from shapely.geometry import LineString, box

from agent.executor import ExecutionContext, WorkflowExecutor
from schemas.agent import (
    RepairRecord,
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
from schemas.quality_gate import QualityGateReport
from schemas.task_kind import TaskKind
from services.artifact_registry import ArtifactLookupRequest, ArtifactRecord
from services.agent_run_service import AgentRunService
from services.aoi_resolution_service import ResolvedAOI
from services.input_acquisition_service import InputAcquisitionService
from services.local_bundle_catalog import LocalBundleCatalogProvider
from services.raw_vector_source_service import RawVectorSourceService
from services.source_asset_service import SourceAssetResolution
from services.input_acquisition_service import ResolvedRunInputs
from services.tiled_building_runtime_service import TiledBuildingRunResult


def _write_dummy_zip(path: Path) -> bytes:
    with ZipFile(path, "w") as zf:
        zf.writestr("dummy.shp", b"shp")
        zf.writestr("dummy.shx", b"shx")
        zf.writestr("dummy.dbf", b"dbf")
    return path.read_bytes()


def _write_polygon_bundle_zip(path: Path, geometries: list, *, crs: str = "EPSG:4326") -> Path:
    bundle_dir = path.parent / path.stem
    bundle_dir.mkdir(parents=True, exist_ok=True)
    shp_path = bundle_dir / "artifact.shp"
    gdf = gpd.GeoDataFrame({"feature_id": list(range(1, len(geometries) + 1))}, geometry=geometries, crs=crs)
    gdf.to_file(shp_path)
    with ZipFile(path, "w") as zf:
        for file in bundle_dir.iterdir():
            if file.is_file():
                zf.write(file, arcname=file.name)
    return path


def _write_frame(path: Path, frame: gpd.GeoDataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(path)


def _write_minimal_polygon_shapefile(path: Path, *, crs: str = "EPSG:4326", with_confidence: bool = False) -> Path:
    data = {"fid": [1]}
    if with_confidence:
        data["confidence"] = [0.9]
    frame = gpd.GeoDataFrame(data, geometry=[box(0, 0, 1, 1)], crs=crs)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(path)
    return path


def _iso_now_minus(*, days: int = 0, hours: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days, hours=hours)).isoformat()


def _build_plan(
    *,
    workflow_id: str,
    revision: int,
    algorithm_id: str = "algo.fusion.building.v1",
    include_reusable_artifacts: bool = False,
) -> WorkflowPlan:
    retrieval = {"candidate_patterns": [{"pattern_id": "wp.flood.building.default", "success_rate": 0.92}]}
    if include_reusable_artifacts:
        retrieval["reusable_artifacts"] = [
            {
                "artifact_id": "artifact-prior-1",
                "artifact_path": "/tmp/artifact-prior-1.zip",
                "created_at": "2026-04-06T00:00:00+00:00",
            }
        ]
    return WorkflowPlan(
        workflow_id=workflow_id,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        context={
            "intent": {
                "job_type": "building",
                "profile_source": "default_task",
                "effective_scenario_profile_id": "scenario.default.task",
                "effective_activated_tasks": ["task.building.fusion", "task.road.fusion", "task.poi.fusion", "task.vector.download"],
                "effective_preferred_output_fields": ["geometry"],
                "task_bundle": {
                    "bundle_id": "task_bundle.direct_request",
                    "requested_tasks": ["task.building.fusion"],
                    "requires_disaster_profile": False,
                },
            },
            "retrieval": retrieval,
            "selection_reason": "initial" if revision == 1 else "replanned_after_failure",
            "llm_provider": "mock",
            "plan_revision": revision,
            "planning_mode": "task_driven",
            "planning_source": "llm",
        },
        tasks=[
            WorkflowTask(
                step=1,
                name="building_fusion",
                description="building fusion",
                algorithm_id=algorithm_id,
                input=WorkflowTaskInput(data_type_id="dt.building.bundle", data_source_id="upload.bundle", parameters={}),
                output=WorkflowTaskOutput(data_type_id="dt.building.fused", description=""),
                depends_on=[],
                is_transform=False,
                kg_validated=True,
                alternatives=["algo.fusion.building.safe"],
            )
        ],
        expected_output="building result",
        validation=ValidationReport(valid=True, inserted_transform_steps=0, issues=[]),
    )


class _NoHealingKG:
    def get_alternative_algorithms(self, *_args, **_kwargs):
        return []

    def get_algorithm(self, *_args, **_kwargs):
        return None

    def find_transform_path(self, *_args, **_kwargs):
        return None


def _seed_run_status(service: AgentRunService, run_id: str, request: RunCreateRequest) -> None:
    run_dir = service.base_dir / run_id
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    status = RunStatus(
        run_id=run_id,
        job_type=request.job_type,
        trigger=request.trigger,
        phase=RunPhase.running,
        progress=40,
        target_crs=request.target_crs or "EPSG:4326",
        debug=request.debug,
        error=None,
        log_path=str(run_dir / "logs" / "run.log"),
        plan_path=None,
        validation_path=None,
        audit_path=str(run_dir / "audit.jsonl"),
        artifact=None,
        decision_records=[],
        artifact_reuse=None,
        repair_records=[],
        current_step=0,
        attempt_no=0,
        healing_summary={},
        failure_summary=None,
        planning_telemetry={},
        plan_revision=0,
        event_count=0,
        last_event=None,
        created_at=_iso_now_minus(),
        started_at=_iso_now_minus(),
        finished_at=None,
    )
    service._runs[run_id] = status
    service._persist_status(status)


def _build_auto_request(
    *,
    spatial_extent: Optional[str] = "bbox(0,0,1,1)",
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
        target_crs="EPSG:32643",
        field_mapping={},
        debug=False,
        input_strategy=RunInputStrategy.task_driven_auto,
    )


def _build_water_task_driven_plan(*, workflow_id: str = "wf_water_auto_inputs", revision: int = 1) -> WorkflowPlan:
    plan = _build_plan(
        workflow_id=workflow_id,
        revision=revision,
        algorithm_id="algo.fusion.water_polygon.priority_merge.v2",
    )
    plan.trigger = RunTrigger(type=RunTriggerType.user_query, content="need water polygons for Nairobi, Kenya")
    plan.context["intent"]["job_type"] = "water"
    plan.context["intent"]["profile_source"] = "direct_task"
    plan.context["retrieval"]["candidate_patterns"] = [{"pattern_id": "wp.flood.water.default", "success_rate": 0.84}]
    plan.tasks[0].name = "water_fusion"
    plan.tasks[0].description = "water fusion"
    plan.tasks[0].algorithm_id = "algo.fusion.water_polygon.priority_merge.v2"
    plan.tasks[0].input.data_type_id = "dt.water.bundle"
    plan.tasks[0].input.data_source_id = "catalog.flood.water"
    plan.tasks[0].output.data_type_id = "dt.water.fused"
    plan.tasks[0].alternatives = []
    plan.expected_output = "water result"
    return plan


def _build_poi_task_driven_plan(*, workflow_id: str = "wf_poi_auto_inputs", revision: int = 1) -> WorkflowPlan:
    plan = _build_plan(workflow_id=workflow_id, revision=revision, algorithm_id="algo.fusion.poi.v1")
    plan.trigger = RunTrigger(type=RunTriggerType.user_query, content="need poi data for Nairobi, Kenya")
    plan.context["intent"]["job_type"] = "poi"
    plan.context["intent"]["profile_source"] = "direct_task"
    plan.context["intent"]["task_bundle"]["requested_tasks"] = ["task.poi.fusion"]
    plan.context["retrieval"]["candidate_patterns"] = [{"pattern_id": "wp.generic.poi.default", "success_rate": 0.8}]
    plan.tasks[0].name = "poi_fusion"
    plan.tasks[0].description = "poi fusion"
    plan.tasks[0].algorithm_id = "algo.fusion.poi.v1"
    plan.tasks[0].input.data_type_id = "dt.poi.bundle"
    plan.tasks[0].input.data_source_id = "catalog.generic.poi"
    plan.tasks[0].output.data_type_id = "dt.poi.fused"
    plan.tasks[0].alternatives = []
    plan.expected_output = "poi result"
    return plan


def _build_road_task_driven_plan(*, workflow_id: str = "wf_road_auto_inputs", revision: int = 1) -> WorkflowPlan:
    plan = _build_plan(workflow_id=workflow_id, revision=revision, algorithm_id="algo.fusion.road.conflation.v7")
    plan.trigger = RunTrigger(type=RunTriggerType.user_query, content="need road data for Gilgit, Pakistan")
    plan.context["intent"]["job_type"] = "road"
    plan.context["intent"]["profile_source"] = "direct_task"
    plan.context["intent"]["task_bundle"]["requested_tasks"] = ["task.road.fusion"]
    plan.context["retrieval"]["candidate_patterns"] = [{"pattern_id": "wp.flood.road.default", "success_rate": 0.86}]
    plan.tasks[0].name = "road_fusion"
    plan.tasks[0].description = "road fusion"
    plan.tasks[0].algorithm_id = "algo.fusion.road.conflation.v7"
    plan.tasks[0].input.data_type_id = "dt.road.bundle"
    plan.tasks[0].input.data_source_id = "catalog.flood.road"
    plan.tasks[0].output.data_type_id = "dt.road.fused"
    plan.tasks[0].alternatives = []
    plan.expected_output = "road result"
    return plan


def _seed_water_runtime_tree(root: Path) -> None:
    _write_frame(
        root / "Data" / "burundi-260127-free.shp" / "gis_osm_water_a_free_1.shp",
        gpd.GeoDataFrame(
            {"osmw_id": [1]},
            geometry=[box(0.0, 0.0, 2.0, 2.0)],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        root / "Data" / "burundi-260127-free.shp" / "gis_osm_waterways_free_1.shp",
        gpd.GeoDataFrame(
            {"osmwl_id": [3], "fclass": ["river"]},
            geometry=[LineString([(0.25, 0.25), (1.75, 1.75)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        root / "Data" / "water" / "HydroRIVERS_v10.shp",
        gpd.GeoDataFrame(
            {"HYRIV_ID": [4]},
            geometry=[LineString([(0.25, 1.75), (1.75, 0.25)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        root / "Data" / "water" / "HydroLAKES_polys_v10.shp",
        gpd.GeoDataFrame(
            {"Hylak_id": [2]},
            geometry=[box(0.5, 0.5, 1.5, 1.5)],
            crs="EPSG:4326",
        ),
    )


def _seed_poi_runtime_tree(root: Path) -> None:
    _write_frame(
        root / "Data" / "burundi-260127-free.shp" / "gis_osm_pois_free_1.shp",
        gpd.GeoDataFrame(
            {"osm_pid": [1]},
            geometry=[box(36.80, -1.30, 36.8001, -1.2999).centroid],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        root / "Data" / "POI" / "Kenya" / "GNS.shp",
        gpd.GeoDataFrame(
            {"gns_id": [2]},
            geometry=[box(36.80005, -1.30005, 36.80015, -1.29995).centroid],
            crs="EPSG:4326",
        ),
    )


def _wire_real_water_acquisition_chain(
    service: AgentRunService,
    *,
    root_dir: Path,
    source_asset_service=None,
) -> None:
    raw_service = RawVectorSourceService(
        root_dir=root_dir,
        registry=service.artifact_registry,
        cache_dir=service.base_dir / "raw_source_cache",
        source_asset_service=source_asset_service,
    )
    service.raw_vector_source_service = raw_service
    service.input_acquisition_service = InputAcquisitionService(
        registry=service.artifact_registry,
        providers=[
            LocalBundleCatalogProvider(
                root_dir,
                raw_source_service=raw_service,
            )
        ],
        cache_dir=service.base_dir / "input_bundle_cache",
    )


def test_agent_run_service_allows_water_task_driven_auto_and_records_task_inputs_resolved(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "resolved_osm_water.shp"
    ref_shp = tmp_path / "resolved_ref_water.shp"
    fused_shp = tmp_path / "fused_water.shp"
    artifact_zip = tmp_path / "artifact_water.zip"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")
    _write_minimal_polygon_shapefile(fused_shp)
    artifact_zip.write_bytes(b"zip")

    plan = _build_water_task_driven_plan()
    prepared_dir = tmp_path / "prepared_water"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    resolved = ResolvedRunInputs(
        osm_zip_path=prepared_dir / "osm.zip",
        ref_zip_path=prepared_dir / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.flood.water",
        cache_hit=False,
        version_token="water-v1",
        manifest_path=prepared_dir / "source_materialization_manifest.json",
    )
    resolved.osm_zip_path.write_bytes(b"osm")
    resolved.ref_zip_path.write_bytes(b"ref")
    resolved.manifest_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(service.aoi_resolution_service, "resolve", lambda query: _resolved_nairobi_aoi())
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service, "_should_use_large_area_runtime", lambda **_kwargs: False)
    monkeypatch.setattr(service.input_acquisition_service, "resolve_task_driven_inputs", lambda **_kwargs: resolved)
    monkeypatch.setattr(
        "services.agent_run_service.validate_zip_has_shapefile",
        lambda zip_path, *_args, **_kwargs: osm_shp if Path(zip_path).name.startswith("osm") else ref_shp,
    )
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: fused_shp)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    status = service.create_run(
        request=_build_auto_request(
            spatial_extent=None,
            job_type=JobType.water,
            content="need water polygons for Nairobi, Kenya",
        ),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    resolved_event = next(event for event in service.get_audit_events(status.run_id) if event.kind == "task_inputs_resolved")
    assert resolved_event.details["source_materialization_manifest_path"] == str(resolved.manifest_path)


def test_agent_run_service_writes_data_requirements_before_materialization(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    captured: dict[str, object] = {}
    plan = _build_plan(workflow_id="wf_data_requirements", revision=1)
    plan.tasks[0].input.data_source_id = "catalog.flood.building"

    def fake_resolve_task_driven_inputs(**kwargs):
        data_requirements_path = Path(kwargs["input_dir"]) / "data_requirements.json"
        captured["exists_before_materialization"] = data_requirements_path.exists()
        raise ValueError("stop after requirement evidence")

    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service, "_attempt_artifact_reuse", lambda **_kwargs: None)
    monkeypatch.setattr(service.input_acquisition_service, "resolve_task_driven_inputs", fake_resolve_task_driven_inputs)

    status = service.create_run(
        request=_build_auto_request(
            spatial_extent="bbox(0,0,1,1)",
            job_type=JobType.building,
            content="need building data for Nairobi",
        ),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.failed
    assert captured["exists_before_materialization"] is True


def test_agent_run_service_rejects_unsupported_intent_before_creating_run_dirs(tmp_path: Path) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    existing_children = sorted(path.name for path in service.base_dir.iterdir())

    with pytest.raises(ValueError, match="OFF_DOMAIN_REQUEST"):
        service.create_run(
            request=_build_auto_request(content="请融合建筑数据，同时给我某国家GDP数据"),
            osm_zip_name=None,
            osm_zip_bytes=None,
            ref_zip_name=None,
            ref_zip_bytes=None,
        )

    assert sorted(path.name for path in service.base_dir.iterdir()) == existing_children


def test_agent_run_service_water_task_driven_auto_uses_real_shared_acquisition_chain(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root_dir = tmp_path / "runtime_root"
    _seed_water_runtime_tree(root_dir)

    service = AgentRunService(base_dir=tmp_path / "runs")
    _wire_real_water_acquisition_chain(service, root_dir=root_dir)

    fused_shp = tmp_path / "fused_water_real.shp"
    _write_frame(
        fused_shp,
        gpd.GeoDataFrame(
            {"fid": [1]},
            geometry=[box(0.25, 0.25, 1.75, 1.75)],
            crs="EPSG:4326",
        ),
    )

    plan = _build_water_task_driven_plan(workflow_id="wf_water_real_chain")
    plan.trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="need water polygons",
        spatial_extent="bbox(0.25,0.25,1.75,1.75)",
    )

    captured: dict[str, object] = {}

    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service, "_should_use_large_area_runtime", lambda **_kwargs: False)

    def fake_execute_plan(*, context, **_kwargs):
        captured["osm_shp"] = context.osm_shp
        captured["ref_shp"] = context.ref_shp
        captured["osm_frame"] = gpd.read_file(context.osm_shp)
        captured["ref_frame"] = gpd.read_file(context.ref_shp)
        return fused_shp

    monkeypatch.setattr(service.executor, "execute_plan", fake_execute_plan)

    status = service.create_run(
        request=_build_auto_request(
            spatial_extent="bbox(0.25,0.25,1.75,1.75)",
            job_type=JobType.water,
            content="need water polygons",
        ),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert Path(captured["osm_shp"]).exists()
    assert Path(captured["ref_shp"]).exists()
    assert list(captured["osm_frame"].columns)[:1] == ["osmw_id"]
    assert list(captured["ref_frame"].columns)[:1] == ["Hylak_id"]
    assert str(captured["osm_frame"].crs) == "EPSG:32643"
    assert str(captured["ref_frame"].crs) == "EPSG:32643"
    expected_osm_bounds = (
        gpd.GeoSeries([box(0.25, 0.25, 1.75, 1.75)], crs="EPSG:4326").to_crs("EPSG:32643").total_bounds.tolist()
    )
    expected_ref_bounds = (
        gpd.GeoSeries([box(0.5, 0.5, 1.5, 1.5)], crs="EPSG:4326").to_crs("EPSG:32643").total_bounds.tolist()
    )
    assert captured["osm_frame"].total_bounds.tolist() == pytest.approx(expected_osm_bounds)
    assert captured["ref_frame"].total_bounds.tolist() == pytest.approx(expected_ref_bounds)

    audit_events = service.get_audit_events(status.run_id)
    resolved_event = next(event for event in audit_events if event.kind == "task_inputs_resolved")
    assert resolved_event.details["source_id"] == "catalog.flood.water"
    assert resolved_event.details["source_mode"] == "downloaded"
    assert resolved_event.details["cache_hit"] is False


def test_agent_run_service_poi_task_driven_auto_uses_real_shared_acquisition_chain(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root_dir = tmp_path / "runtime_root_poi"
    _seed_poi_runtime_tree(root_dir)

    service = AgentRunService(base_dir=tmp_path / "runs")
    _wire_real_water_acquisition_chain(service, root_dir=root_dir)

    fused_shp = tmp_path / "fused_poi_real.shp"
    _write_frame(
        fused_shp,
        gpd.GeoDataFrame(
            {"fid": [1]},
            geometry=[box(36.80002, -1.30002, 36.80003, -1.30001).centroid],
            crs="EPSG:4326",
        ),
    )

    plan = _build_poi_task_driven_plan(workflow_id="wf_poi_real_chain")
    plan.trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="need poi data",
        spatial_extent="bbox(36.79,-1.31,36.81,-1.29)",
    )

    captured: dict[str, object] = {}

    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service, "_should_use_large_area_runtime", lambda **_kwargs: False)

    def fake_execute_plan(*, context, **_kwargs):
        captured["osm_shp"] = context.osm_shp
        captured["ref_shp"] = context.ref_shp
        captured["osm_frame"] = gpd.read_file(context.osm_shp)
        captured["ref_frame"] = gpd.read_file(context.ref_shp)
        return fused_shp

    monkeypatch.setattr(service.executor, "execute_plan", fake_execute_plan)

    status = service.create_run(
        request=_build_auto_request(
            spatial_extent="bbox(36.79,-1.31,36.81,-1.29)",
            job_type=JobType.poi,
            content="need poi data",
        ),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert Path(captured["osm_shp"]).exists()
    assert Path(captured["ref_shp"]).exists()
    assert list(captured["osm_frame"].columns)[:1] == ["osm_pid"]
    assert list(captured["ref_frame"].columns)[:1] == ["gns_id"]
    assert str(captured["osm_frame"].crs) == "EPSG:32643"
    assert str(captured["ref_frame"].crs) == "EPSG:32643"

    audit_events = service.get_audit_events(status.run_id)
    resolved_event = next(event for event in audit_events if event.kind == "task_inputs_resolved")
    assert resolved_event.details["source_id"] == "catalog.generic.poi"
    assert resolved_event.details["source_mode"] == "downloaded"
    assert resolved_event.details["cache_hit"] is False


def test_agent_run_service_water_task_driven_auto_fails_at_materialization_time_when_bundle_is_empty(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root_dir = tmp_path / "runtime_root_empty"
    root_dir.mkdir(parents=True, exist_ok=True)

    empty_osm = root_dir / "empty_osm.shp"
    empty_ref = root_dir / "empty_ref.shp"
    empty_frame = gpd.GeoDataFrame({"wid": []}, geometry=[], crs="EPSG:4326")
    _write_frame(empty_osm, empty_frame)
    _write_frame(empty_ref, empty_frame)

    class _EmptyWaterSourceAssetService:
        def can_materialize(self, source_id: str) -> bool:
            return source_id in {"raw.osm.water", "raw.hydrolakes.water"}

        def resolve_raw_source_path(self, source_id: str, *, request_bbox=None, aoi=None):
            path = empty_osm if source_id == "raw.osm.water" else empty_ref
            return SourceAssetResolution(
                source_id=source_id,
                path=path,
                source_mode="coverage_empty",
                cache_hit=True,
                version_token=f"empty:{source_id}",
                bbox=None,
                feature_count=0,
            )

    service = AgentRunService(base_dir=tmp_path / "runs")
    _wire_real_water_acquisition_chain(
        service,
        root_dir=root_dir,
        source_asset_service=_EmptyWaterSourceAssetService(),
    )

    plan = _build_water_task_driven_plan(workflow_id="wf_water_materialization_failure")
    plan.trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="need water polygons",
        spatial_extent="bbox(10,10,11,11)",
    )

    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service, "_should_use_large_area_runtime", lambda **_kwargs: False)
    monkeypatch.setattr(
        service.executor,
        "execute_plan",
        lambda **_kwargs: pytest.fail("execution should not run when water bundle materialization fails"),
    )

    status = service.create_run(
        request=_build_auto_request(
            spatial_extent="bbox(10,10,11,11)",
            job_type=JobType.water,
            content="need water polygons",
        ),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.failed
    assert latest.error is not None
    assert "task-driven input materialization failed for catalog.flood.water" in latest.error
    assert "failure_category=SOURCE_MISSING" in (latest.failure_summary or "")
    assert "suggested_action=replan" in (latest.failure_summary or "")
    audit_events = service.get_audit_events(status.run_id)
    assert not any(event.kind == "task_inputs_resolved" for event in audit_events)
    assert audit_events[-1].kind == "run_failed"
    assert audit_events[-1].details["failure_category"] == "SOURCE_MISSING"
    assert audit_events[-1].details["suggested_action"] == "replan"


def test_agent_run_service_retries_task_driven_source_alternative_after_source_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "fallback_osm.shp"
    ref_shp = tmp_path / "fallback_ref.shp"
    fused_shp = tmp_path / "fallback_fused.shp"
    artifact_zip = tmp_path / "fallback_artifact.zip"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")
    _write_minimal_polygon_shapefile(fused_shp)
    artifact_zip.write_bytes(b"zip")

    plan = _build_plan(workflow_id="wf_source_fallback", revision=1)
    plan.trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="Karachi flood building fusion",
        disaster_type="flood",
    )
    plan.context["intent"]["request_input_strategy"] = RunInputStrategy.task_driven_auto.value
    plan.context["retrieval"]["data_sources"] = [
        {
            "source_id": "catalog.flood.building",
            "supported_types": ["dt.building.bundle"],
            "disaster_types": ["flood"],
            "quality_score": 0.95,
            "freshness_score": 0.9,
            "metadata": {"selectable_now": True, "runtime_status": "runtime_candidate"},
        },
        {
            "source_id": "catalog.generic.building",
            "supported_types": ["dt.building.bundle"],
            "disaster_types": ["generic"],
            "quality_score": 0.75,
            "freshness_score": 0.6,
            "metadata": {"selectable_now": True, "runtime_status": "runtime_candidate"},
        },
    ]

    prepared_dir = tmp_path / "prepared_fallback"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    resolved_inputs = ResolvedRunInputs(
        osm_zip_path=prepared_dir / "osm.zip",
        ref_zip_path=prepared_dir / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.generic.building",
        cache_hit=False,
        version_token="generic-v1",
    )
    resolved_inputs.osm_zip_path.write_bytes(b"osm")
    resolved_inputs.ref_zip_path.write_bytes(b"ref")
    attempted: list[str] = []

    def fake_resolve_task_driven_inputs(**kwargs):
        attempted.append(kwargs["source_id"])
        if kwargs["source_id"] == "catalog.flood.building":
            raise ValueError("SOURCE_MISSING: empty source coverage for catalog.flood.building")
        return resolved_inputs

    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service.input_acquisition_service, "resolve_task_driven_inputs", fake_resolve_task_driven_inputs)
    monkeypatch.setattr(
        "services.agent_run_service.validate_zip_has_shapefile",
        lambda zip_path, *_args, **_kwargs: osm_shp if Path(zip_path).name.startswith("osm") else ref_shp,
    )
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: fused_shp)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    status = service.create_run(
        request=_build_auto_request(
            spatial_extent="bbox(66.2,24.4,67.6,25.7)",
            job_type=JobType.building,
            content="Karachi flood building fusion",
        ),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert attempted == ["catalog.flood.building", "catalog.generic.building"]

    audit_events = service.get_audit_events(status.run_id)
    fallback_event = next(event for event in audit_events if event.kind == "source_fallback_selected")
    assert fallback_event.details["fallback_from_source_id"] == "catalog.flood.building"
    assert fallback_event.details["selected_source_id"] == "catalog.generic.building"
    resolved_event = next(event for event in audit_events if event.kind == "task_inputs_resolved")
    assert resolved_event.details["source_id"] == "catalog.generic.building"
    assert resolved_event.details["fallback_from_source_id"] == "catalog.flood.building"


def test_agent_run_service_road_task_driven_auto_keeps_trajectory_seam_reserved(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    fused_shp = tmp_path / "fused_road_reserved.shp"
    artifact_zip = tmp_path / "artifact_road_reserved.zip"
    _write_minimal_polygon_shapefile(fused_shp)
    artifact_zip.write_bytes(b"zip")

    plan = _build_road_task_driven_plan()
    plan.context["retrieval"]["algorithms"] = {
        "algo.transform.trajectory_to_road_candidate": {
            "algo_id": "algo.transform.trajectory_to_road_candidate",
            "tool_ref": "builtin:trajectory_pretransform_reserved",
        }
    }

    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service, "_should_use_large_area_runtime", lambda **_kwargs: False)
    monkeypatch.setattr(
        service.executor,
        "execute_plan",
        lambda **_kwargs: fused_shp,
    )
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    captured: dict[str, object] = {}

    def fake_resolve_task_driven_inputs(**kwargs):
        captured["source_id"] = kwargs["source_id"]
        captured["required_output_type"] = kwargs["required_output_type"]
        captured["request_content"] = kwargs["request"].trigger.content
        osm_zip = tmp_path / "catalog_flood_road_osm.zip"
        ref_zip = tmp_path / "catalog_flood_road_ref.zip"
        _write_dummy_zip(osm_zip)
        _write_dummy_zip(ref_zip)
        return ResolvedRunInputs(
            osm_zip_path=osm_zip,
            ref_zip_path=ref_zip,
            source_mode="generated",
            source_id=kwargs["source_id"],
            cache_hit=False,
            version_token="road-v1",
        )

    monkeypatch.setattr(service.input_acquisition_service, "resolve_task_driven_inputs", fake_resolve_task_driven_inputs)
    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda zip_path, *_args, **_kwargs: Path(str(zip_path) + ".shp"))

    status = service.create_run(
        request=_build_auto_request(
            spatial_extent="bbox(74.1,35.8,74.3,36.0)",
            job_type=JobType.road,
            content="need road data for Gilgit, Pakistan",
        ),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert captured["source_id"] == "catalog.flood.road"
    assert captured["required_output_type"] == "dt.road.bundle"

    saved_plan = service.get_plan(status.run_id)
    assert saved_plan is not None
    assert saved_plan.tasks[0].algorithm_id == "algo.fusion.road.conflation.v7"
    assert all(task.algorithm_id != "algo.transform.trajectory_to_road_candidate" for task in saved_plan.tasks)


def test_agent_run_service_road_task_driven_auto_uses_real_shared_acquisition_chain(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root_dir = tmp_path / "runtime_root_road"
    _write_frame(
        root_dir / "Data" / "roads" / "OSM" / "osm_roads.shp",
        gpd.GeoDataFrame(
            {"road_id": [1]},
            geometry=[box(74.10, 35.80, 74.30, 36.00).boundary],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        root_dir / "Data" / "roads" / "Overture" / "overture_roads.shp",
        gpd.GeoDataFrame(
            {"id": ["seg-1"], "class": ["primary"], "surface": ["paved"], "lane_count": [2]},
            geometry=[box(74.12, 35.82, 74.28, 35.98).boundary],
            crs="EPSG:4326",
        ),
    )

    service = AgentRunService(base_dir=tmp_path / "runs")
    raw_service = RawVectorSourceService(
        root_dir=root_dir,
        registry=service.artifact_registry,
        cache_dir=service.base_dir / "raw_source_cache",
    )
    service.raw_vector_source_service = raw_service
    service.input_acquisition_service = InputAcquisitionService(
        registry=service.artifact_registry,
        providers=[LocalBundleCatalogProvider(root_dir, raw_source_service=raw_service)],
        cache_dir=service.base_dir / "input_bundle_cache",
    )

    fused_shp = tmp_path / "fused_road_real.shp"
    _write_frame(
        fused_shp,
        gpd.GeoDataFrame(
            {"fid": [1]},
            geometry=[box(74.10, 35.80, 74.30, 36.00)],
            crs="EPSG:4326",
        ),
    )

    plan = _build_road_task_driven_plan(workflow_id="wf_road_real_chain")
    plan.trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="need road data",
        spatial_extent="bbox(74.1,35.8,74.3,36.0)",
    )

    captured: dict[str, object] = {}

    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service, "_should_use_large_area_runtime", lambda **_kwargs: False)

    def fake_execute_plan(*, context, **_kwargs):
        captured["osm_shp"] = context.osm_shp
        captured["ref_shp"] = context.ref_shp
        captured["osm_frame"] = gpd.read_file(context.osm_shp)
        captured["ref_frame"] = gpd.read_file(context.ref_shp)
        return fused_shp

    monkeypatch.setattr(service.executor, "execute_plan", fake_execute_plan)

    status = service.create_run(
        request=_build_auto_request(
            spatial_extent="bbox(74.1,35.8,74.3,36.0)",
            job_type=JobType.road,
            content="need road data",
        ),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert Path(captured["osm_shp"]).exists()
    assert Path(captured["ref_shp"]).exists()
    assert list(captured["osm_frame"].columns)[:1] == ["road_id"]
    assert list(captured["ref_frame"].columns)[:1] == ["id"]
    assert str(captured["osm_frame"].crs) == "EPSG:32643"
    assert str(captured["ref_frame"].crs) == "EPSG:32643"

    audit_events = service.get_audit_events(status.run_id)
    resolved_event = next(event for event in audit_events if event.kind == "task_inputs_resolved")
    assert resolved_event.details["source_id"] == "catalog.flood.road"
    assert resolved_event.details["source_mode"] == "downloaded"
    assert resolved_event.details["cache_hit"] is False


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


def test_agent_run_service_updates_status_and_records_feedback(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")

    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    fused_shp = tmp_path / "fused.shp"
    artifact_zip = tmp_path / "artifact.zip"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")
    _write_minimal_polygon_shapefile(fused_shp)

    plan = WorkflowPlan(
        workflow_id="wf_service",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        context={
            "intent": {
                "job_type": "building",
                "profile_source": "default_task",
                "task_bundle": {
                    "bundle_id": "task_bundle.direct_request",
                    "requested_tasks": ["task.building.fusion"],
                    "requires_disaster_profile": False,
                },
            },
            "retrieval": {
                "candidate_patterns": [{"pattern_id": "wp.flood.building.default", "success_rate": 0.90}],
                "reusable_artifacts": [
                    {
                        "artifact_id": "artifact-prior-1",
                        "artifact_path": "/tmp/artifact-prior-1.zip",
                        "created_at": "2026-04-06T00:00:00+00:00",
                    }
                ],
            },
            "selection_reason": "initial",
            "llm_provider": "mock",
            "plan_revision": 1,
            "planning_mode": "task_driven",
            "planning_source": "llm",
        },
        tasks=[
            WorkflowTask(
                step=1,
                name="building_fusion",
                description="building fusion",
                algorithm_id="algo.fusion.building.v1",
                input=WorkflowTaskInput(
                    data_type_id="dt.building.bundle",
                    data_source_id="upload.bundle",
                    parameters={
                        "match_similarity_threshold": 0.5,
                        "one_to_one_min_overlap_similarity": 0.3,
                    },
                ),
                output=WorkflowTaskOutput(data_type_id="dt.building.fused", description=""),
                depends_on=[],
                is_transform=False,
                kg_validated=True,
                alternatives=["algo.fusion.building.safe"],
            )
        ],
        expected_output="building result",
        validation=ValidationReport(valid=True, inserted_transform_steps=0, issues=[]),
    )

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: osm_shp)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)

    def fake_execute_plan(*, plan, context, repair_records, **_kwargs):
        repair_records.append(
            RepairRecord(
                attempt_no=1,
                strategy="alternative_algorithm",
                step=1,
                message="Recovered with safe algorithm",
                success=True,
                timestamp="2026-04-01T00:00:00+00:00",
                reason_code="alternative_algorithm_succeeded",
                from_algorithm="algo.fusion.building.v1",
                to_algorithm="algo.fusion.building.safe",
            )
        )
        return fused_shp

    monkeypatch.setattr(service.executor, "execute_plan", fake_execute_plan)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)
    artifact_zip.write_bytes(b"zip")

    osm_zip = tmp_path / "osm.zip"
    ref_zip = tmp_path / "ref.zip"
    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        target_crs="EPSG:32643",
        field_mapping={},
        debug=False,
    )

    status = service.create_run(
        request=request,
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(osm_zip),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(ref_zip),
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert latest.plan_revision == 1
    assert latest.attempt_no == 1
    assert latest.audit_path
    assert latest.event_count >= 5
    assert latest.last_event is not None
    assert latest.last_event.kind == "run_succeeded"
    assert latest.decision_records
    assert latest.decision_records[0].decision_type == "pattern_selection"
    assert latest.decision_records[0].selected_id == "wp.flood.building.default"
    decision_types = {record.decision_type for record in latest.decision_records}
    assert {
        "pattern_selection",
        "data_source_selection",
        "artifact_reuse_selection",
        "parameter_strategy",
        "output_schema_policy",
    } <= decision_types
    for record in latest.decision_records:
        assert record.candidates
        assert set(record.candidates[0].evidence.keys()) == {"metrics", "meta"}
    assert latest.artifact_reuse is not None
    assert latest.artifact_reuse.reused is False
    assert latest.artifact_reuse.freshness_status == "candidate_available"
    assert latest.healing_summary["successful_repairs"] == 1
    assert latest.healing_summary["last_reason_code"] == "alternative_algorithm_succeeded"
    assert service.kg_repo.feedback_history[-1].pattern_id == "wp.flood.building.default"
    assert service.kg_repo.durable_learning_records[-1].run_id == status.run_id
    assert service.kg_repo.durable_learning_records[-1].success is True
    assert service.kg_repo.durable_learning_records[-1].output_data_type == "dt.building.fused"
    assert service.kg_repo.durable_learning_records[-1].metadata["planning_mode"] == "task_driven"
    assert service.kg_repo.durable_learning_records[-1].metadata["profile_source"] == "default_task"
    assert (
        service.kg_repo.durable_learning_records[-1].metadata["task_bundle"]["bundle_id"]
        == "task_bundle.direct_request"
    )
    audit_events = service.get_audit_events(status.run_id)
    plan_created = next(event for event in audit_events if event.kind == "plan_created")
    assert plan_created.details["effective_parameters"]["1"]["match_similarity_threshold"] == 0.5
    assert plan_created.details["effective_parameters"]["1"]["one_to_one_min_overlap_similarity"] == 0.3
    assert plan_created.details["planning_mode"] == "task_driven"
    assert plan_created.details["planning_source"] == "llm"
    assert plan_created.details["profile_source"] == "default_task"
    assert plan_created.details["task_bundle"]["bundle_id"] == "task_bundle.direct_request"
    registry_path = (tmp_path / "runs" / "artifact_registry.json")
    assert registry_path.exists()
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    assert any(record.get("artifact_id") == status.run_id for record in records)
    record = service.artifact_registry.find_reusable(
        ArtifactLookupRequest(job_type="building", required_artifact_role="fusion_result")
    )
    assert record is not None
    assert record.meta["artifact_role"] == "fusion_result"


def test_run_status_records_planning_mode_and_profile_source(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    fused_shp = tmp_path / "fused.shp"
    artifact_zip = tmp_path / "artifact.zip"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")
    _write_minimal_polygon_shapefile(fused_shp)
    artifact_zip.write_bytes(b"zip")

    plan = _build_plan(workflow_id="wf_task_mode", revision=1)

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: osm_shp)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: fused_shp)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(type=RunTriggerType.user_query, content="need building and road data for Gilgit, Pakistan"),
            target_crs="EPSG:32643",
            field_mapping={},
            debug=False,
        ),
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(tmp_path / "osm.zip"),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(tmp_path / "ref.zip"),
    )

    saved_plan = service.get_plan(status.run_id)
    assert saved_plan is not None
    assert saved_plan.context["planning_mode"] == "task_driven"
    assert saved_plan.context["intent"]["profile_source"] == "default_task"
    assert saved_plan.context["intent"]["task_bundle"]["bundle_id"] == "task_bundle.direct_request"
    assert saved_plan.context["intent"]["effective_scenario_profile_id"] == "scenario.default.task"
    durable_record = service.kg_repo.durable_learning_records[-1]
    assert durable_record.metadata["planning_mode"] == "task_driven"
    assert durable_record.metadata["profile_source"] == "default_task"
    assert durable_record.metadata["task_bundle"]["bundle_id"] == "task_bundle.direct_request"


def test_agent_run_service_rejects_artifact_when_output_schema_required_fields_are_missing(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    fused_shp = tmp_path / "fused_missing_confidence.shp"
    artifact_zip = tmp_path / "artifact.zip"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")
    artifact_zip.write_bytes(b"zip")

    frame = gpd.GeoDataFrame(
        {"fid": [1]},
        geometry=[box(0, 0, 1, 1)],
        crs="EPSG:4326",
    )
    frame.to_file(fused_shp)

    plan = _build_plan(workflow_id="wf_schema_gate", revision=1)
    plan.context["retrieval"]["output_schema_policies"] = {
        "dt.building.fused": {
            "policy_id": "osp.building.fused.v1",
            "output_type": "dt.building.fused",
            "job_type": "building",
            "retention_mode": "preserve_listed",
            "required_fields": ["geometry", "confidence"],
            "optional_fields": [],
            "rename_hints": {},
            "compatibility_basis": "field_names",
        }
    }

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: osm_shp)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: fused_shp)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
            target_crs="EPSG:32643",
            field_mapping={},
            debug=False,
        ),
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(tmp_path / "osm.zip"),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(tmp_path / "ref.zip"),
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.failed
    assert latest.error is not None
    assert "Artifact schema validation failed" in latest.error
    audit_events = service.get_audit_events(status.run_id)
    assert any(event.kind == "run_failed" for event in audit_events)


def test_agent_run_service_writes_quality_report_for_gpkg_output(tmp_path: Path) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(
            type=RunTriggerType.user_query,
            content="building",
            spatial_extent="bbox(0,0,1,1)",
        ),
        target_crs="EPSG:4326",
        field_mapping={},
        debug=False,
    )
    plan = _build_plan(workflow_id="wf_quality_gate", revision=1)
    plan.context["quality_policy_id"] = "quality.default.building.v1"
    run_id = "run-quality-gate"
    _seed_run_status(service, run_id, request)
    status = service.get_run(run_id)
    assert status is not None
    status.checkpoint = {
        "stage": "execution",
        "component_coverage": {
            "raw.osm.building": {"feature_count": 1, "coverage_status": "available"},
            "raw.microsoft.building": {"feature_count": 1, "coverage_status": "available"},
        },
    }
    service._runs[run_id] = status
    service._persist_status(status)

    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    fused_gpkg = output_dir / "building_fusion_result.gpkg"
    gpd.GeoDataFrame(
        {
            "fid": [1],
            "source_id": ["raw.osm.building"],
            "source_count": [2],
        },
        geometry=[box(0.1, 0.1, 0.9, 0.9)],
        crs="EPSG:4326",
    ).to_file(fused_gpkg, driver="GPKG")

    service.run_writeback_stage(
        run_id=run_id,
        request=request,
        plan=plan,
        fused_shp=fused_gpkg,
        repair_records=[],
        output_dir=output_dir,
    )

    quality_report_path = output_dir / "quality_report.json"
    assert quality_report_path.exists()
    payload = json.loads(quality_report_path.read_text(encoding="utf-8"))
    assert payload["accepted"] is True
    assert payload["task_kind"] == "building"
    assert payload["policy_id"] == "quality.default.building.v1"


def test_agent_run_service_passes_plan_quality_policy_id_to_quality_gate(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building", spatial_extent="bbox(0,0,1,1)"),
        target_crs="EPSG:4326",
        field_mapping={},
        debug=False,
    )
    plan = _build_plan(workflow_id="wf_quality_policy_capture", revision=1)
    plan.context["quality_policy_id"] = "quality.default.building.v1"
    run_id = "run-quality-policy-capture"
    _seed_run_status(service, run_id, request)
    output_dir = tmp_path / "output-capture"
    output_dir.mkdir(parents=True, exist_ok=True)
    fused_gpkg = output_dir / "building_fusion_result.gpkg"
    gpd.GeoDataFrame(
        {"fid": [1], "source_id": ["raw.osm.building"]},
        geometry=[box(0.1, 0.1, 0.9, 0.9)],
        crs="EPSG:4326",
    ).to_file(fused_gpkg, driver="GPKG")
    captured: dict[str, object] = {}

    class FakeQualityGate:
        def evaluate(self, *, quality_policy_id, **kwargs):
            captured["quality_policy_id"] = quality_policy_id
            return QualityGateReport(
                accepted=True,
                task_kind=TaskKind.building,
                artifact_path=str(kwargs["artifact_path"]),
                policy_id=quality_policy_id,
            )

    service.quality_gate_service = FakeQualityGate()

    service.run_writeback_stage(
        run_id=run_id,
        request=request,
        plan=plan,
        fused_shp=fused_gpkg,
        repair_records=[],
        output_dir=output_dir,
    )

    assert captured["quality_policy_id"] == "quality.default.building.v1"


def test_record_feedback_includes_quality_and_latency_metadata(tmp_path: Path) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building", spatial_extent="bbox(0,0,1,1)"),
        target_crs="EPSG:4326",
        field_mapping={},
        debug=False,
    )
    run_id = "run-quality-learning-metadata"
    _seed_run_status(service, run_id, request)
    status = service.get_run(run_id)
    assert status is not None
    status.started_at = "2026-06-01T00:00:00+00:00"
    status.finished_at = "2026-06-01T00:00:15+00:00"
    service._runs[run_id] = status
    service._persist_status(status)
    service._update_status(
        run_id,
        RunPhase.running,
        event_kind="quality_gate_evaluated",
        event_message="quality gate",
        event_details={"accepted": True, "failure_reasons": ["soft_warning"]},
    )
    plan = _build_plan(workflow_id="wf_quality_learning_metadata", revision=1)
    plan.context["intent"]["aoi_class"] = "small_city"
    plan.context["intent"]["region_group"] = "africa"

    service._record_feedback(
        run_id=run_id,
        request=request,
        plan=plan,
        repair_records=[],
        success=True,
        failure_reason=None,
    )

    metadata = service.kg_repo.durable_learning_records[-1].metadata
    assert metadata["quality_gate_accepted"] is True
    assert metadata["quality_gate_failure_reasons"] == ["soft_warning"]
    assert metadata["latency_seconds"] == 15.0
    assert metadata["aoi_class"] == "small_city"
    assert metadata["region_group"] == "africa"


def test_agent_run_service_task_driven_auto_prepares_inputs_before_execution(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "resolved_osm.shp"
    ref_shp = tmp_path / "resolved_ref.shp"
    fused_shp = tmp_path / "fused.shp"
    artifact_zip = tmp_path / "artifact.zip"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")
    _write_minimal_polygon_shapefile(fused_shp)
    artifact_zip.write_bytes(b"zip")

    plan = _build_plan(workflow_id="wf_auto_inputs", revision=1)
    plan.tasks[0].input.data_source_id = "catalog.flood.building"

    prepared_dir = tmp_path / "prepared"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    resolved = ResolvedRunInputs(
        osm_zip_path=prepared_dir / "osm.zip",
        ref_zip_path=prepared_dir / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.flood.building",
        cache_hit=False,
        version_token="v1",
    )
    resolved.osm_zip_path.write_bytes(b"osm")
    resolved.ref_zip_path.write_bytes(b"ref")

    captured: dict[str, object] = {}

    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)

    def fake_resolve_task_driven_inputs(**kwargs):
        captured.update(kwargs)
        return resolved

    monkeypatch.setattr(service.input_acquisition_service, "resolve_task_driven_inputs", fake_resolve_task_driven_inputs)
    monkeypatch.setattr(
        "services.agent_run_service.validate_zip_has_shapefile",
        lambda zip_path, *_args, **_kwargs: osm_shp if Path(zip_path).name.startswith("osm") else ref_shp,
    )
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: fused_shp)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    status = service.create_run(
        request=_build_auto_request(),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert captured["source_id"] == "catalog.flood.building"
    assert captured["required_output_type"] == "dt.building.bundle"
    assert Path(captured["input_dir"]).name == "input"

    audit_events = service.get_audit_events(status.run_id)
    created = next(event for event in audit_events if event.kind == "run_created")
    assert created.details["input_strategy"] == "task_driven_auto"
    assert created.details["osm_zip_name"] is None
    assert created.details["ref_zip_name"] is None

    resolved_event = next(event for event in audit_events if event.kind == "task_inputs_resolved")
    assert resolved_event.details["input_strategy"] == "task_driven_auto"
    assert resolved_event.details["source_mode"] == "downloaded"
    assert resolved_event.details["source_id"] == "catalog.flood.building"
    assert resolved_event.details["cache_hit"] is False
    assert resolved_event.details["version_token"] == "v1"
    assert resolved_event.details["osm_zip_name"] == "osm.zip"
    assert resolved_event.details["ref_zip_name"] == "ref.zip"


def test_task_driven_building_source_selection_prefers_bundle_compatible_catalog_source(tmp_path: Path) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    plan = _build_plan(workflow_id="wf_task_driven_catalog_only", revision=1)
    plan.trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="Karachi flood building fusion",
        disaster_type="flood",
    )
    plan.context["intent"]["request_input_strategy"] = "task_driven_auto"
    plan.context["retrieval"]["data_sources"] = [
        {
            "source_id": "upload.bundle",
            "supported_types": ["dt.building.bundle"],
            "quality_score": 1.0,
            "freshness_score": 1.0,
            "source_name": "Uploaded Bundle",
            "source_kind": "local_upload",
            "quality_tier": "operator_provided",
            "freshness_category": "request_bound",
            "metadata": {
                "selectable_now": True,
                "runtime_status": "runtime_candidate",
            },
        },
        {
            "source_id": "raw.microsoft.building",
            "supported_types": ["dt.raw.vector"],
            "quality_score": 0.88,
            "freshness_score": 0.59,
            "source_name": "Microsoft Building Footprints",
            "source_kind": "open_data",
            "quality_tier": "provider_curated",
            "freshness_category": "sample_snapshot",
            "metadata": {
                "selectable_now": True,
                "runtime_status": "runtime_candidate",
            },
        },
        {
            "source_id": "catalog.earthquake.building",
            "supported_types": ["dt.building.bundle"],
            "quality_score": 0.88,
            "freshness_score": 0.71,
            "source_name": "Earthquake Building Bundle (OSM + Microsoft)",
            "source_kind": "catalog",
            "quality_tier": "curated",
            "freshness_category": "event_snapshot",
            "metadata": {
                "selectable_now": True,
                "runtime_status": "runtime_candidate",
            },
        },
        {
            "source_id": "catalog.flood.building",
            "supported_types": ["dt.building.bundle"],
            "quality_score": 0.86,
            "freshness_score": 0.74,
            "source_name": "Flood Building Bundle (OSM + Google)",
            "source_kind": "catalog",
            "quality_tier": "curated",
            "freshness_category": "event_snapshot",
            "metadata": {
                "selectable_now": True,
                "runtime_status": "runtime_candidate",
            },
        },
    ]

    decisions = service._build_planning_decisions(plan)
    selected = next(item for item in decisions if item.decision_type == "data_source_selection")

    assert selected.selected_id == "catalog.flood.building"
    assert service._resolve_task_driven_source_id(plan) == "catalog.flood.building"
    assert service._extract_alternative_sources(plan) == ["catalog.earthquake.building"]
    assert selected.evidence_refs == [
        "context.retrieval.data_sources",
        "policy:deterministic_weighted_sum",
        "policy:disaster_source_compatibility",
    ]


def test_agent_run_service_allows_generic_source_when_disaster_specific_source_missing(tmp_path: Path) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    plan = _build_plan(workflow_id="wf_generic_source_for_flood", revision=1)
    plan.trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="Karachi flood building fusion",
        disaster_type="flood",
    )
    plan.context["intent"]["request_input_strategy"] = RunInputStrategy.task_driven_auto.value
    plan.context["intent"]["expected_output_type"] = "dt.building.fused"
    plan.context["retrieval"]["data_sources"] = [
        {
            "source_id": "catalog.generic.building",
            "supported_types": ["dt.building.bundle"],
            "disaster_types": ["generic"],
            "quality_score": 0.80,
            "freshness_score": 0.60,
            "source_name": "Generic Building Bundle",
            "source_kind": "catalog",
            "quality_tier": "curated",
            "freshness_category": "snapshot",
            "metadata": {"selectable_now": True, "runtime_status": "runtime_candidate"},
        },
        {
            "source_id": "catalog.earthquake.building",
            "supported_types": ["dt.building.bundle"],
            "disaster_types": ["earthquake", "generic"],
            "quality_score": 0.95,
            "freshness_score": 0.90,
            "source_name": "Earthquake Building Bundle",
            "source_kind": "catalog",
            "quality_tier": "curated",
            "freshness_category": "event_snapshot",
            "metadata": {"selectable_now": True, "runtime_status": "runtime_candidate"},
        },
    ]

    decisions = service._build_planning_decisions(plan)
    selected = next(item for item in decisions if item.decision_type == "data_source_selection")

    assert selected.selected_id == "catalog.generic.building"
    assert service._resolve_task_driven_source_id(plan) == "catalog.generic.building"


def test_agent_run_service_resolves_nairobi_before_input_materialization(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "resolved_osm.shp"
    ref_shp = tmp_path / "resolved_ref.shp"
    fused_shp = tmp_path / "fused.shp"
    artifact_zip = tmp_path / "artifact.zip"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")
    _write_minimal_polygon_shapefile(fused_shp)
    artifact_zip.write_bytes(b"zip")

    plan = _build_plan(workflow_id="wf_nairobi_auto", revision=1)
    plan.trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="fuse building and road data for Nairobi, Kenya",
    )
    plan.tasks[0].input.data_source_id = "catalog.earthquake.building"

    prepared_dir = tmp_path / "prepared"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    resolved_inputs = ResolvedRunInputs(
        osm_zip_path=prepared_dir / "osm.zip",
        ref_zip_path=prepared_dir / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.earthquake.building",
        cache_hit=False,
        version_token="ke-v1",
    )
    resolved_inputs.osm_zip_path.write_bytes(b"osm")
    resolved_inputs.ref_zip_path.write_bytes(b"ref")

    captured: dict[str, object] = {}
    resolved_aoi = _resolved_nairobi_aoi()

    monkeypatch.setattr(service.aoi_resolution_service, "resolve", lambda query: resolved_aoi)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)

    def fake_resolve_task_driven_inputs(**kwargs):
        captured.update(kwargs)
        return resolved_inputs

    monkeypatch.setattr(service.input_acquisition_service, "resolve_task_driven_inputs", fake_resolve_task_driven_inputs)
    monkeypatch.setattr(
        "services.agent_run_service.validate_zip_has_shapefile",
        lambda zip_path, *_args, **_kwargs: osm_shp if Path(zip_path).name.startswith("osm") else ref_shp,
    )
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: fused_shp)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(
                type=RunTriggerType.user_query,
                content="fuse building and road data for Nairobi, Kenya",
            ),
            target_crs="EPSG:32643",
            field_mapping={},
            debug=False,
            input_strategy=RunInputStrategy.task_driven_auto,
        ),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert captured["source_id"] == "catalog.earthquake.building"
    assert captured["required_output_type"] == "dt.building.bundle"
    assert captured["resolved_aoi"] == resolved_aoi
    assert captured["request_bbox"] == resolved_aoi.bbox

    audit_events = service.get_audit_events(status.run_id)
    aoi_event = next(event for event in audit_events if event.kind == "aoi_resolved")
    assert aoi_event.details["display_name"] == "Nairobi, Nairobi County, Kenya"
    assert aoi_event.details["country_code"] == "ke"
    assert aoi_event.details["bbox"] == [36.65, -1.45, 37.10, -1.10]

    resolved_event = next(event for event in audit_events if event.kind == "task_inputs_resolved")
    assert resolved_event.details["resolved_aoi"]["country_code"] == "ke"
    assert resolved_event.details["resolved_aoi"]["display_name"] == "Nairobi, Nairobi County, Kenya"


def test_agent_run_service_resolves_named_spatial_extent_before_input_materialization(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "karachi_osm.shp"
    ref_shp = tmp_path / "karachi_ref.shp"
    fused_shp = tmp_path / "karachi_fused.shp"
    artifact_zip = tmp_path / "karachi_artifact.zip"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")
    _write_minimal_polygon_shapefile(fused_shp)
    artifact_zip.write_bytes(b"zip")

    plan = _build_plan(workflow_id="wf_karachi_named_spatial_extent", revision=1)
    plan.trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="巴基斯坦卡拉奇市发生洪涝灾害，请执行地理空间矢量数据融合。",
        disaster_type="flood",
        spatial_extent="Karachi, Pakistan",
    )
    plan.context["intent"]["request_input_strategy"] = RunInputStrategy.task_driven_auto.value
    plan.tasks[0].input.data_source_id = "catalog.flood.building"

    prepared_dir = tmp_path / "prepared_karachi"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    resolved_inputs = ResolvedRunInputs(
        osm_zip_path=prepared_dir / "osm.zip",
        ref_zip_path=prepared_dir / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.flood.building",
        cache_hit=False,
        version_token="pk-karachi-v1",
    )
    resolved_inputs.osm_zip_path.write_bytes(b"osm")
    resolved_inputs.ref_zip_path.write_bytes(b"ref")

    karachi_aoi = ResolvedAOI(
        query="Karachi, Pakistan",
        display_name="Karachi Division, Sindh, Pakistan",
        country_name="Pakistan",
        country_code="pk",
        bbox=(66.2862312, 24.4273517, 67.5827753, 25.676796),
        confidence=0.657,
        selection_reason="single_candidate",
        candidates=tuple(),
    )
    resolve_queries: list[str] = []
    captured: dict[str, object] = {}

    def fake_resolve(query: str) -> ResolvedAOI:
        resolve_queries.append(query)
        return karachi_aoi

    def fake_resolve_task_driven_inputs(**kwargs):
        captured.update(kwargs)
        return resolved_inputs

    monkeypatch.setattr(service.aoi_resolution_service, "resolve", fake_resolve)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service.input_acquisition_service, "resolve_task_driven_inputs", fake_resolve_task_driven_inputs)
    monkeypatch.setattr(
        "services.agent_run_service.validate_zip_has_shapefile",
        lambda zip_path, *_args, **_kwargs: osm_shp if Path(zip_path).name.startswith("osm") else ref_shp,
    )
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: fused_shp)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(
                type=RunTriggerType.user_query,
                content="巴基斯坦卡拉奇市发生洪涝灾害，请执行地理空间矢量数据融合。",
                disaster_type="flood",
                spatial_extent="Karachi, Pakistan",
            ),
            target_crs="EPSG:32643",
            field_mapping={},
            debug=False,
            input_strategy=RunInputStrategy.task_driven_auto,
        ),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert resolve_queries == ["Karachi, Pakistan"]
    assert captured["resolved_aoi"] == karachi_aoi
    assert captured["request_bbox"] == karachi_aoi.bbox

    audit_events = service.get_audit_events(status.run_id)
    aoi_event = next(event for event in audit_events if event.kind == "aoi_resolved")
    assert aoi_event.details["query"] == "Karachi, Pakistan"
    resolved_event = next(event for event in audit_events if event.kind == "task_inputs_resolved")
    assert resolved_event.details["resolved_aoi"]["country_code"] == "pk"


def test_agent_run_service_prefers_explicit_spatial_extent_but_still_records_aoi_resolution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "resolved_osm_bbox.shp"
    ref_shp = tmp_path / "resolved_ref_bbox.shp"
    fused_shp = tmp_path / "fused_bbox.shp"
    artifact_zip = tmp_path / "artifact_bbox.zip"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")
    _write_minimal_polygon_shapefile(fused_shp)
    artifact_zip.write_bytes(b"zip")

    plan = _build_plan(workflow_id="wf_nairobi_explicit_bbox", revision=1)
    plan.trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="need building data for Nairobi, Kenya",
        spatial_extent="bbox(36.79,-1.31,36.81,-1.29)",
        force_aoi_resolution=True,
    )
    plan.tasks[0].input.data_source_id = "catalog.earthquake.building"

    prepared_dir = tmp_path / "prepared_bbox"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    resolved_inputs = ResolvedRunInputs(
        osm_zip_path=prepared_dir / "osm.zip",
        ref_zip_path=prepared_dir / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.earthquake.building",
        cache_hit=False,
        version_token="ke-v1",
    )
    resolved_inputs.osm_zip_path.write_bytes(b"osm")
    resolved_inputs.ref_zip_path.write_bytes(b"ref")

    captured: dict[str, object] = {}
    resolved_aoi = _resolved_nairobi_aoi()

    monkeypatch.setattr(service.aoi_resolution_service, "resolve", lambda query: resolved_aoi)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)

    def fake_resolve_task_driven_inputs(**kwargs):
        captured.update(kwargs)
        return resolved_inputs

    monkeypatch.setattr(service.input_acquisition_service, "resolve_task_driven_inputs", fake_resolve_task_driven_inputs)
    monkeypatch.setattr(
        "services.agent_run_service.validate_zip_has_shapefile",
        lambda zip_path, *_args, **_kwargs: osm_shp if Path(zip_path).name.startswith("osm") else ref_shp,
    )
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: fused_shp)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(
                type=RunTriggerType.user_query,
                content="need building data for Nairobi, Kenya",
                spatial_extent="bbox(36.79,-1.31,36.81,-1.29)",
                force_aoi_resolution=True,
            ),
            target_crs="EPSG:32643",
            field_mapping={},
            debug=False,
            input_strategy=RunInputStrategy.task_driven_auto,
        ),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert captured["resolved_aoi"] == resolved_aoi
    assert captured["request_bbox"] == (36.79, -1.31, 36.81, -1.29)

    audit_events = service.get_audit_events(status.run_id)
    aoi_event = next(event for event in audit_events if event.kind == "aoi_resolved")
    assert aoi_event.details["display_name"] == "Nairobi, Nairobi County, Kenya"
    resolved_event = next(event for event in audit_events if event.kind == "task_inputs_resolved")
    assert resolved_event.details["resolved_aoi"]["country_code"] == "ke"


def test_agent_run_service_direct_bbox_run_does_not_force_aoi_resolution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    fused_shp = tmp_path / "fused_road_direct_bbox.shp"
    artifact_zip = tmp_path / "artifact_road_direct_bbox.zip"
    _write_minimal_polygon_shapefile(fused_shp)
    artifact_zip.write_bytes(b"zip")

    plan = _build_road_task_driven_plan()
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service, "_should_use_large_area_runtime", lambda **_kwargs: False)
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: fused_shp)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)
    monkeypatch.setattr(
        service.aoi_resolution_service,
        "resolve",
        lambda _query: pytest.fail("direct bbox run should not force AOI resolution"),
    )

    def fake_resolve_task_driven_inputs(**kwargs):
        osm_zip = tmp_path / "road_bbox_osm.zip"
        ref_zip = tmp_path / "road_bbox_ref.zip"
        _write_dummy_zip(osm_zip)
        _write_dummy_zip(ref_zip)
        return ResolvedRunInputs(
            osm_zip_path=osm_zip,
            ref_zip_path=ref_zip,
            source_mode="generated",
            source_id=kwargs["source_id"],
            cache_hit=False,
            version_token="road-v1",
        )

    monkeypatch.setattr(service.input_acquisition_service, "resolve_task_driven_inputs", fake_resolve_task_driven_inputs)
    monkeypatch.setattr(
        "services.agent_run_service.validate_zip_has_shapefile",
        lambda zip_path, *_args, **_kwargs: Path(str(zip_path) + ".shp"),
    )

    status = service.create_run(
        request=_build_auto_request(
            spatial_extent="bbox(74.1,35.8,74.3,36.0)",
            job_type=JobType.road,
            content="need road data for Gilgit, Pakistan",
        ),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert not any(event.kind == "aoi_resolved" for event in service.get_audit_events(status.run_id))


def test_agent_run_service_auto_selects_target_crs_from_nairobi_aoi_when_omitted(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "resolved_osm_auto.shp"
    ref_shp = tmp_path / "resolved_ref_auto.shp"
    fused_shp = tmp_path / "fused_auto.shp"
    artifact_zip = tmp_path / "artifact_auto.zip"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")
    _write_minimal_polygon_shapefile(fused_shp)
    artifact_zip.write_bytes(b"zip")

    plan = _build_plan(workflow_id="wf_nairobi_auto_crs", revision=1)
    plan.trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="fuse building and road data for Nairobi, Kenya",
    )
    plan.tasks[0].input.data_source_id = "catalog.earthquake.building"

    prepared_dir = tmp_path / "prepared_auto"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    resolved_inputs = ResolvedRunInputs(
        osm_zip_path=prepared_dir / "osm.zip",
        ref_zip_path=prepared_dir / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.earthquake.building",
        cache_hit=False,
        version_token="ke-v1",
    )
    resolved_inputs.osm_zip_path.write_bytes(b"osm")
    resolved_inputs.ref_zip_path.write_bytes(b"ref")

    captured: dict[str, object] = {}
    resolved_aoi = _resolved_nairobi_aoi()

    monkeypatch.setattr(service.aoi_resolution_service, "resolve", lambda query: resolved_aoi)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)

    def fake_resolve_task_driven_inputs(**kwargs):
        captured.update(kwargs)
        return resolved_inputs

    monkeypatch.setattr(service.input_acquisition_service, "resolve_task_driven_inputs", fake_resolve_task_driven_inputs)
    monkeypatch.setattr(
        "services.agent_run_service.validate_zip_has_shapefile",
        lambda zip_path, *_args, **_kwargs: osm_shp if Path(zip_path).name.startswith("osm") else ref_shp,
    )
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: fused_shp)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(
                type=RunTriggerType.user_query,
                content="fuse building and road data for Nairobi, Kenya",
            ),
            target_crs=None,
            field_mapping={},
            debug=False,
            input_strategy=RunInputStrategy.task_driven_auto,
        ),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.target_crs == "EPSG:32737"
    assert captured["resolved_aoi"] == resolved_aoi

    audit_events = service.get_audit_events(status.run_id)
    resolved_event = next(event for event in audit_events if event.kind == "task_inputs_resolved")
    assert resolved_event.details["target_crs"] == "EPSG:32737"


def test_agent_run_service_preserves_explicit_target_crs_override(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "resolved_osm_override.shp"
    ref_shp = tmp_path / "resolved_ref_override.shp"
    fused_shp = tmp_path / "fused_override.shp"
    artifact_zip = tmp_path / "artifact_override.zip"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")
    _write_minimal_polygon_shapefile(fused_shp)
    artifact_zip.write_bytes(b"zip")

    plan = _build_plan(workflow_id="wf_nairobi_override_crs", revision=1)
    plan.trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="fuse building and road data for Nairobi, Kenya",
    )
    plan.tasks[0].input.data_source_id = "catalog.earthquake.building"

    prepared_dir = tmp_path / "prepared_override"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    resolved_inputs = ResolvedRunInputs(
        osm_zip_path=prepared_dir / "osm.zip",
        ref_zip_path=prepared_dir / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.earthquake.building",
        cache_hit=False,
        version_token="ke-v1",
    )
    resolved_inputs.osm_zip_path.write_bytes(b"osm")
    resolved_inputs.ref_zip_path.write_bytes(b"ref")

    monkeypatch.setattr(service.aoi_resolution_service, "resolve", lambda query: _resolved_nairobi_aoi())
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service.input_acquisition_service, "resolve_task_driven_inputs", lambda **kwargs: resolved_inputs)
    monkeypatch.setattr(
        "services.agent_run_service.validate_zip_has_shapefile",
        lambda zip_path, *_args, **_kwargs: osm_shp if Path(zip_path).name.startswith("osm") else ref_shp,
    )
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: fused_shp)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(
                type=RunTriggerType.user_query,
                content="fuse building and road data for Nairobi, Kenya",
            ),
            target_crs="EPSG:4326",
            field_mapping={},
            debug=False,
            input_strategy=RunInputStrategy.task_driven_auto,
        ),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.target_crs == "EPSG:4326"


def test_agent_run_service_directly_reuses_existing_artifact(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")

    reusable_created_at = _iso_now_minus(hours=1)
    source_artifact = _write_polygon_bundle_zip(tmp_path / "artifact-source.zip", [box(0, 0, 1, 1)], crs="EPSG:32643")
    service.artifact_registry.register(
        ArtifactRecord(
            artifact_id="artifact-source",
            artifact_path=str(source_artifact),
            job_type="building",
            disaster_type="flood",
            created_at=reusable_created_at,
            output_fields=[],
            bbox=(0.0, 0.0, 1.0, 1.0),
            output_data_type="dt.building.fused",
            target_crs="EPSG:32643",
            meta={"note": "direct"},
        )
    )

    plan = _build_plan(workflow_id="wf_direct", revision=1)
    plan.context["retrieval"]["reusable_artifacts"] = [
        {
            "artifact_id": "artifact-source",
            "artifact_path": str(source_artifact),
            "created_at": reusable_created_at,
            "bbox": [0.0, 0.0, 1.0, 1.0],
        }
    ]

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: osm_shp)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)

    def fail_execute_plan(**_kwargs):
        raise AssertionError("executor should not run when direct reuse succeeds")

    monkeypatch.setattr(service.executor, "execute_plan", fail_execute_plan)

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(
                type=RunTriggerType.disaster_event,
                content="building",
                disaster_type="flood",
                spatial_extent="bbox(0,0,1,1)",
            ),
            target_crs="EPSG:32643",
            field_mapping={},
            debug=False,
        ),
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(tmp_path / "osm.zip"),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(tmp_path / "ref.zip"),
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert latest.artifact is not None
    assert Path(latest.artifact.path).exists()
    assert Path(latest.artifact.path).parent.name == "output"
    assert latest.artifact_reuse is not None
    assert latest.artifact_reuse.reused is True
    assert latest.artifact_reuse.artifact_id == "artifact-source"
    assert latest.artifact_reuse.freshness_status == "direct_reused"
    audit_events = service.get_audit_events(status.run_id)
    plan_created = next(event for event in audit_events if event.kind == "plan_created")
    assert "effective_parameters" in plan_created.details
    reuse_event = next(event for event in audit_events if event.kind == "artifact_reuse_applied")
    assert reuse_event.details["reuse_mode"] == "direct"
    assert reuse_event.details["source_artifact_id"] == "artifact-source"


def test_agent_run_service_clips_reused_artifact_when_request_bbox_is_smaller(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")

    reusable_created_at = _iso_now_minus(hours=1)
    source_artifact = _write_polygon_bundle_zip(
        tmp_path / "artifact-clip-source.zip",
        [box(0, 0, 4, 4)],
        crs="EPSG:32643",
    )
    service.artifact_registry.register(
        ArtifactRecord(
            artifact_id="artifact-clip-source",
            artifact_path=str(source_artifact),
            job_type="building",
            disaster_type="flood",
            created_at=reusable_created_at,
            output_fields=[],
            bbox=(0.0, 0.0, 4.0, 4.0),
            output_data_type="dt.building.fused",
            target_crs="EPSG:32643",
            meta={"note": "clip"},
        )
    )

    plan = _build_plan(workflow_id="wf_clip", revision=1)
    plan.context["retrieval"]["reusable_artifacts"] = [
        {
            "artifact_id": "artifact-clip-source",
            "artifact_path": str(source_artifact),
            "created_at": reusable_created_at,
            "bbox": [0.0, 0.0, 4.0, 4.0],
        }
    ]

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: osm_shp)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)

    def fail_execute_plan(**_kwargs):
        raise AssertionError("executor should not run when clip reuse succeeds")

    monkeypatch.setattr(service.executor, "execute_plan", fail_execute_plan)

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(
                type=RunTriggerType.disaster_event,
                content="building",
                disaster_type="flood",
                spatial_extent="bbox(1,1,2,2)",
            ),
            target_crs="EPSG:32643",
            field_mapping={},
            debug=False,
        ),
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(tmp_path / "osm.zip"),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(tmp_path / "ref.zip"),
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert latest.artifact is not None
    clipped_zip = Path(latest.artifact.path)
    assert clipped_zip.exists()
    clipped_extract = tmp_path / "clipped_extract"
    with ZipFile(clipped_zip, "r") as zf:
        zf.extractall(clipped_extract)
    clipped_gdf = gpd.read_file(clipped_extract / "artifact.shp")
    bounds = clipped_gdf.total_bounds.tolist()
    assert bounds == [1.0, 1.0, 2.0, 2.0]
    assert latest.artifact_reuse is not None
    assert latest.artifact_reuse.reused is True
    assert latest.artifact_reuse.artifact_id == "artifact-clip-source"
    assert latest.artifact_reuse.freshness_status == "clip_reused"
    audit_events = service.get_audit_events(status.run_id)
    reuse_event = next(event for event in audit_events if event.kind == "artifact_reuse_applied")
    assert reuse_event.details["reuse_mode"] == "clip"
    assert reuse_event.details["source_artifact_id"] == "artifact-clip-source"


def test_agent_run_service_falls_back_to_fresh_execution_when_clip_reuse_materialization_fails(
    tmp_path: Path, monkeypatch
) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    fused_shp = tmp_path / "fresh-fused.shp"
    artifact_zip = tmp_path / "artifact.zip"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")
    _write_minimal_polygon_shapefile(fused_shp)
    artifact_zip.write_bytes(b"zip")

    # Deliberately lie in the registry bbox so candidate selection passes but clipping fails.
    reusable_created_at = _iso_now_minus(hours=1)
    source_artifact = _write_polygon_bundle_zip(
        tmp_path / "artifact-fallback-source.zip",
        [box(0, 0, 1, 1)],
        crs="EPSG:32643",
    )
    service.artifact_registry.register(
        ArtifactRecord(
            artifact_id="artifact-fallback-source",
            artifact_path=str(source_artifact),
            job_type="building",
            disaster_type="flood",
            created_at=reusable_created_at,
            output_fields=[],
            bbox=(0.0, 0.0, 4.0, 4.0),
            output_data_type="dt.building.fused",
            target_crs="EPSG:32643",
            meta={"note": "fallback"},
        )
    )

    plan = _build_plan(workflow_id="wf_fallback", revision=1)
    plan.context["retrieval"]["reusable_artifacts"] = [
        {
            "artifact_id": "artifact-fallback-source",
            "artifact_path": str(source_artifact),
            "created_at": reusable_created_at,
            "bbox": [0.0, 0.0, 4.0, 4.0],
        }
    ]

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: osm_shp)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)

    execute_calls = {"count": 0}

    def fake_execute_plan(**_kwargs):
        execute_calls["count"] += 1
        return fused_shp

    monkeypatch.setattr(service.executor, "execute_plan", fake_execute_plan)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(
                type=RunTriggerType.disaster_event,
                content="building",
                disaster_type="flood",
                spatial_extent="bbox(3,3,4,4)",
            ),
            target_crs="EPSG:32643",
            field_mapping={},
            debug=False,
        ),
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(tmp_path / "osm.zip"),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(tmp_path / "ref.zip"),
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert execute_calls["count"] == 1
    assert latest.artifact_reuse is not None
    assert latest.artifact_reuse.reused is False
    assert latest.artifact_reuse.freshness_status == "candidate_available"
    audit_events = service.get_audit_events(status.run_id)
    fallback_event = next(event for event in audit_events if event.kind == "artifact_reuse_fallback")
    assert "clip produced no features" in fallback_event.details["error"]


def test_agent_run_service_skips_stale_reuse_candidates_using_job_type_policy(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    fused_shp = tmp_path / "fresh-road.shp"
    artifact_zip = tmp_path / "road-artifact.zip"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")
    _write_minimal_polygon_shapefile(fused_shp)
    artifact_zip.write_bytes(b"zip")

    source_artifact = _write_polygon_bundle_zip(
        tmp_path / "artifact-road-stale.zip",
        [box(0, 0, 1, 1)],
        crs="EPSG:32643",
    )
    service.artifact_registry.register(
        ArtifactRecord(
            artifact_id="artifact-road-stale",
            artifact_path=str(source_artifact),
            job_type="road",
            disaster_type="flood",
            created_at="2026-04-07T00:00:00+00:00",
            output_fields=["geometry", "osm_id"],
            bbox=(0.0, 0.0, 1.0, 1.0),
            output_data_type="dt.road.fused",
            target_crs="EPSG:32643",
            meta={"note": "should be too old for road reuse"},
        )
    )

    plan = _build_plan(workflow_id="wf_road_stale", revision=1, algorithm_id="algo.fusion.road.conflation.v7")
    plan.tasks[0].output.data_type_id = "dt.road.fused"
    plan.context["retrieval"]["reusable_artifacts"] = [
        {
            "artifact_id": "artifact-road-stale",
            "artifact_path": str(source_artifact),
            "created_at": "2026-04-07T00:00:00+00:00",
            "bbox": [0.0, 0.0, 1.0, 1.0],
            "output_data_type": "dt.road.fused",
            "target_crs": "EPSG:32643",
        }
    ]

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: osm_shp)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)

    execute_calls = {"count": 0}

    def fake_execute_plan(**_kwargs):
        execute_calls["count"] += 1
        return fused_shp

    monkeypatch.setattr(service.executor, "execute_plan", fake_execute_plan)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.road,
            trigger=RunTrigger(
                type=RunTriggerType.disaster_event,
                content="road",
                disaster_type="flood",
                spatial_extent="bbox(0,0,1,1)",
            ),
            target_crs="EPSG:32643",
            field_mapping={},
            debug=False,
        ),
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(tmp_path / "osm.zip"),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(tmp_path / "ref.zip"),
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert execute_calls["count"] == 1
    assert latest.artifact_reuse is not None
    assert latest.artifact_reuse.reused is False
    assert latest.artifact_reuse.freshness_status == "candidate_available"
    audit_events = service.get_audit_events(status.run_id)
    assert not any(event.kind == "artifact_reuse_applied" for event in audit_events)


def test_agent_run_service_skips_reuse_candidates_with_unsafe_crs(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    fused_shp = tmp_path / "fresh-crs.shp"
    artifact_zip = tmp_path / "artifact.zip"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")
    _write_minimal_polygon_shapefile(fused_shp)
    artifact_zip.write_bytes(b"zip")

    reusable_created_at = _iso_now_minus(hours=1)
    source_artifact = _write_polygon_bundle_zip(tmp_path / "artifact-crs-mismatch.zip", [box(0, 0, 1, 1)])
    service.artifact_registry.register(
        ArtifactRecord(
            artifact_id="artifact-crs-mismatch",
            artifact_path=str(source_artifact),
            job_type="building",
            disaster_type="flood",
            created_at=reusable_created_at,
            output_fields=["geometry", "confidence"],
            bbox=(0.0, 0.0, 1.0, 1.0),
            output_data_type="dt.building.fused",
            target_crs="EPSG:4326",
            meta={"note": "unsafe target CRS mismatch"},
        )
    )

    plan = _build_plan(workflow_id="wf_crs_mismatch", revision=1)
    plan.context["retrieval"]["reusable_artifacts"] = [
        {
            "artifact_id": "artifact-crs-mismatch",
            "artifact_path": str(source_artifact),
            "created_at": reusable_created_at,
            "bbox": [0.0, 0.0, 1.0, 1.0],
            "output_data_type": "dt.building.fused",
            "target_crs": "EPSG:4326",
        }
    ]

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: osm_shp)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)

    execute_calls = {"count": 0}

    def fake_execute_plan(**_kwargs):
        execute_calls["count"] += 1
        return fused_shp

    monkeypatch.setattr(service.executor, "execute_plan", fake_execute_plan)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(
                type=RunTriggerType.disaster_event,
                content="building",
                disaster_type="flood",
                spatial_extent="bbox(0,0,1,1)",
            ),
            target_crs="EPSG:32643",
            field_mapping={},
            debug=False,
        ),
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(tmp_path / "osm.zip"),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(tmp_path / "ref.zip"),
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert execute_calls["count"] == 1
    assert latest.artifact_reuse is not None
    assert latest.artifact_reuse.reused is False
    assert latest.artifact_reuse.freshness_status == "candidate_available"
    audit_events = service.get_audit_events(status.run_id)
    assert not any(event.kind == "artifact_reuse_applied" for event in audit_events)


def test_saved_plan_contains_bound_effective_parameters(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    initial_plan = _build_plan(workflow_id="wf_initial", revision=1)
    initial_plan.tasks[0].input.parameters = {
        "match_similarity_threshold": 0.52,
        "one_to_one_min_overlap_similarity": 0.31,
    }

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: tmp_path / "osm.shp")
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: initial_plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: tmp_path / "fused.shp")
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: tmp_path / "artifact.zip")

    (tmp_path / "osm.shp").write_text("x", encoding="utf-8")
    (tmp_path / "ref.shp").write_text("x", encoding="utf-8")
    (tmp_path / "fused.shp").write_text("x", encoding="utf-8")
    (tmp_path / "artifact.zip").write_bytes(b"zip")

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
            target_crs="EPSG:32643",
            field_mapping={},
            debug=False,
        ),
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(tmp_path / "osm.zip"),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(tmp_path / "ref.zip"),
    )

    saved = service.get_plan(status.run_id)
    assert saved is not None
    assert saved.tasks[0].input.parameters["match_similarity_threshold"] == 0.52
    assert saved.tasks[0].input.parameters["one_to_one_min_overlap_similarity"] == 0.31
    audit_events = service.get_audit_events(status.run_id)
    plan_created = next(event for event in audit_events if event.kind == "plan_created")
    assert plan_created.details["effective_parameters"]["1"]["match_similarity_threshold"] == 0.52
    assert plan_created.details["effective_parameters"]["1"]["one_to_one_min_overlap_similarity"] == 0.31


def test_agent_run_service_replans_after_execution_failure(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    service.max_plan_revisions = 2

    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    fused_shp = tmp_path / "fused.shp"
    artifact_zip = tmp_path / "artifact.zip"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")
    _write_minimal_polygon_shapefile(fused_shp)

    initial_plan = _build_plan(workflow_id="wf_initial", revision=1, include_reusable_artifacts=True)
    replanned_plan = _build_plan(workflow_id="wf_replanned", revision=2, algorithm_id="algo.fusion.building.safe")

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: osm_shp)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: initial_plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)

    replan_calls: list[tuple[int, str]] = []

    def fake_replan(**kwargs):
        replan_calls.append((kwargs["failed_step"], kwargs["error_message"]))
        return replanned_plan.model_copy(deep=True)

    monkeypatch.setattr(service.planner, "replan_from_error", fake_replan)

    execute_calls = {"count": 0}

    def fake_execute_plan(*, plan, context, repair_records, **_kwargs):
        execute_calls["count"] += 1
        if execute_calls["count"] == 1:
            repair_records.extend(
                [
                    RepairRecord(
                        attempt_no=1,
                        strategy="alternative_source",
                        step=1,
                        message="Primary execution failed",
                        success=False,
                        timestamp="2026-04-02T00:00:00+00:00",
                        reason_code="primary_execution_failed",
                        from_algorithm="algo.fusion.building.v1",
                    ),
                    RepairRecord(
                        attempt_no=2,
                        strategy="alternative_algorithm",
                        step=1,
                        message="Alternative algorithm failed",
                        success=False,
                        timestamp="2026-04-02T00:00:01+00:00",
                        reason_code="alternative_algorithm_failed",
                        from_algorithm="algo.fusion.building.v1",
                        to_algorithm="algo.fusion.building.safe",
                    ),
                    RepairRecord(
                        attempt_no=3,
                        strategy="transform_insert",
                        step=1,
                        message="No transform path found.",
                        success=False,
                        timestamp="2026-04-02T00:00:02+00:00",
                        reason_code="transform_path_missing",
                        from_algorithm="algo.fusion.building.v1",
                    ),
                ]
            )
            raise RuntimeError("exhausted repairs")
        return fused_shp

    monkeypatch.setattr(service.executor, "execute_plan", fake_execute_plan)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)
    artifact_zip.write_bytes(b"zip")

    phase_history: list[RunPhase] = []
    original_update_status = service._update_status

    def tracking_update_status(*args, **kwargs):
        phase = args[1] if len(args) > 1 else kwargs["phase"]
        phase_history.append(phase)
        return original_update_status(*args, **kwargs)

    monkeypatch.setattr(service, "_update_status", tracking_update_status)

    osm_zip = tmp_path / "osm.zip"
    ref_zip = tmp_path / "ref.zip"
    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        target_crs="EPSG:32643",
        field_mapping={},
        debug=False,
    )

    status = service.create_run(
        request=request,
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(osm_zip),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(ref_zip),
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert latest.plan_revision == 2
    assert RunPhase.healing in phase_history
    assert replan_calls and replan_calls[0][0] == 1
    saved_plan = service.get_plan(status.run_id)
    assert saved_plan is not None
    assert saved_plan.workflow_id == "wf_replanned"
    assert saved_plan.context["plan_revision"] == 2
    revision_1 = json.loads((tmp_path / "runs" / status.run_id / "plan-revision-1.json").read_text(encoding="utf-8"))
    revision_2 = json.loads((tmp_path / "runs" / status.run_id / "plan-revision-2.json").read_text(encoding="utf-8"))
    assert revision_1["workflow_id"] == "wf_initial"
    assert revision_2["workflow_id"] == "wf_replanned"
    replan_decisions = [record for record in latest.decision_records if record.decision_type == "replan_or_fail"]
    assert replan_decisions
    assert replan_decisions[-1].selected_id == "replan"
    assert latest.repair_records[-1].reason_code == "transform_path_missing"
    audit_events = service.get_audit_events(status.run_id)
    assert [event.kind for event in audit_events if event.kind in {"replan_requested", "replan_applied"}] == [
        "replan_requested",
        "replan_applied",
    ]
    assert audit_events[-1].kind == "run_succeeded"
    assert audit_events[-1].plan_revision == 2


def test_replan_result_is_rejected_when_grounding_enforcement_fails(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    service.max_plan_revisions = 2
    monkeypatch.setenv("GEOFUSION_PLAN_GROUNDING_MODE", "enforce")

    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")

    initial_plan = _build_plan(workflow_id="wf_initial", revision=1, include_reusable_artifacts=True)
    initial_plan.context["retrieval"] = {
        "candidate_patterns": [
            {
                "pattern_id": "wp.flood.building.default",
                "steps": [
                    {
                        "algorithm_id": "algo.fusion.building.v1",
                        "input_data_type": "dt.building.bundle",
                        "data_source_id": "upload.bundle",
                        "output_data_type": "dt.building.fused",
                    }
                ],
            }
        ],
        "data_sources": [{"source_id": "upload.bundle"}],
        "algorithms": {"algo.fusion.building.v1": {"tool_ref": "builtin:building"}},
        "output_schema_policies": {"dt.building.fused": {"policy_id": "schema.building.fused"}},
        "reusable_artifacts": [
            {
                "artifact_id": "artifact-prior-1",
                "artifact_path": "/tmp/artifact-prior-1.zip",
                "created_at": "2026-04-06T00:00:00+00:00",
            }
        ],
    }
    replanned_plan = _build_plan(workflow_id="wf_replanned_ungrounded", revision=2)
    replanned_plan.context["retrieval"] = {
        "candidate_patterns": [],
        "data_sources": [],
        "algorithms": {},
        "output_schema_policies": {},
    }

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: osm_shp)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: initial_plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service.planner, "replan_from_error", lambda **_kwargs: replanned_plan.model_copy(deep=True))

    def fake_execute_plan(*, repair_records, **_kwargs):
        repair_records.extend(
            [
                RepairRecord(
                    attempt_no=1,
                    strategy="alternative_source",
                    step=1,
                    message="Primary execution failed",
                    success=False,
                    timestamp="2026-04-02T00:00:00+00:00",
                    reason_code="primary_execution_failed",
                    from_algorithm="algo.fusion.building.v1",
                ),
                RepairRecord(
                    attempt_no=2,
                    strategy="alternative_algorithm",
                    step=1,
                    message="Alternative algorithm failed",
                    success=False,
                    timestamp="2026-04-02T00:00:01+00:00",
                    reason_code="alternative_algorithm_failed",
                    from_algorithm="algo.fusion.building.v1",
                    to_algorithm="algo.fusion.building.safe",
                ),
                RepairRecord(
                    attempt_no=3,
                    strategy="transform_insert",
                    step=1,
                    message="No transform path found.",
                    success=False,
                    timestamp="2026-04-02T00:00:02+00:00",
                    reason_code="transform_path_missing",
                    from_algorithm="algo.fusion.building.v1",
                ),
            ]
        )
        raise RuntimeError("exhausted repairs")

    monkeypatch.setattr(service.executor, "execute_plan", fake_execute_plan)
    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        target_crs="EPSG:32643",
        field_mapping={},
        debug=False,
    )

    status = service.create_run(
        request=request,
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(tmp_path / "osm.zip"),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(tmp_path / "ref.zip"),
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.failed
    assert "PLAN_GROUNDING_FAILED" in (latest.error or "")
    saved_plan = service.get_plan(status.run_id)
    assert saved_plan is not None
    assert saved_plan.workflow_id == "wf_replanned_ungrounded"
    assert saved_plan.context["grounding_gate"]["allowed"] is False
    audit_events = service.get_audit_events(status.run_id)
    assert any(event.kind == "replan_requested" for event in audit_events)
    assert any(
        event.kind == "plan_grounding_rejected" and event.details.get("stage") == "replan"
        for event in audit_events
    )


def test_agent_run_service_copies_planning_telemetry_to_status_and_audit(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")

    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    fused_shp = tmp_path / "fused.shp"
    artifact_zip = tmp_path / "artifact.zip"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")
    _write_minimal_polygon_shapefile(fused_shp)
    artifact_zip.write_bytes(b"zip")

    plan = _build_plan(workflow_id="wf_telemetry", revision=1)
    plan.context["planning_telemetry"] = {
        "elapsed_ms": 12,
        "context_size_bytes": 345,
        "provider": "capturing",
        "model": "telemetry-model",
        "llm_usage": {
            "prompt_tokens": 10,
            "completion_tokens": 4,
            "total_tokens": 14,
        },
    }

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: osm_shp)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: fused_shp)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
            target_crs="EPSG:32643",
            field_mapping={},
            debug=False,
        ),
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(tmp_path / "osm.zip"),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(tmp_path / "ref.zip"),
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.planning_telemetry == plan.context["planning_telemetry"]
    audit_events = service.get_audit_events(status.run_id)
    plan_created = next(event for event in audit_events if event.kind == "plan_created")
    assert plan_created.details["planning_telemetry"] == plan.context["planning_telemetry"]
    assert plan_created.details["planning_source"] == "llm"


def test_plan_created_audit_includes_selectable_and_reserved_capability_hints(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")

    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    fused_shp = tmp_path / "fused.shp"
    artifact_zip = tmp_path / "artifact.zip"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")
    _write_minimal_polygon_shapefile(fused_shp)
    artifact_zip.write_bytes(b"zip")

    plan = _build_plan(workflow_id="wf_reserved_hints", revision=1)
    plan.context["execution_hints"] = {
        "preferred_pattern_id": "wp.flood.building.default",
        "fallback_pattern_ids": ["wp.flood.building.safe"],
        "available_data_source_ids": [
            "catalog.flood.building",
            "raw.openbuildingmap.building",
            "raw.google.building_presence.raster",
        ],
        "selectable_source_ids": ["catalog.flood.building"],
        "reserved_source_ids": [
            "raw.openbuildingmap.building",
            "raw.google.building_presence.raster",
        ],
        "required_reserved_capabilities": [
            "algo.fusion.building.multi_source.reserved",
            "algo.enrich.building.height_from_raster.reserved",
        ],
    }

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: osm_shp)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: fused_shp)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
            target_crs="EPSG:32643",
            field_mapping={},
            debug=False,
        ),
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(tmp_path / "osm.zip"),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(tmp_path / "ref.zip"),
    )

    audit_events = service.get_audit_events(status.run_id)
    plan_created = next(event for event in audit_events if event.kind == "plan_created")
    assert plan_created.details["selectable_source_ids"] == ["catalog.flood.building"]
    assert plan_created.details["reserved_source_ids"] == [
        "raw.openbuildingmap.building",
        "raw.google.building_presence.raster",
    ]
    assert plan_created.details["required_reserved_capabilities"] == [
        "algo.fusion.building.multi_source.reserved",
        "algo.enrich.building.height_from_raster.reserved",
    ]


def test_agent_run_service_routes_large_building_runs_to_tiled_runtime(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")

    osm_bundle = _write_polygon_bundle_zip(
        tmp_path / "prepared" / "osm.zip",
        [box(2.500, 9.250, 2.505, 9.255), box(2.700, 9.360, 2.705, 9.365)],
    )
    ref_bundle = _write_polygon_bundle_zip(
        tmp_path / "prepared" / "ref.zip",
        [box(2.500, 9.250, 2.505, 9.255), box(2.700, 9.360, 2.705, 9.365)],
    )
    fused_shp = tmp_path / "tiled-output" / "fused_buildings.shp"
    fused_shp.parent.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame(
        {"osm_id": [1], "confidence": [1.0]},
        geometry=[box(2.500, 9.250, 2.505, 9.255)],
        crs="EPSG:32631",
    ).to_file(fused_shp)
    artifact_zip = tmp_path / "artifact.zip"
    artifact_zip.write_bytes(b"zip")

    plan = _build_plan(workflow_id="wf_tiled", revision=1)
    plan.tasks[0].input.data_source_id = "catalog.flood.building"

    resolved = ResolvedRunInputs(
        osm_zip_path=osm_bundle,
        ref_zip_path=ref_bundle,
        source_mode="downloaded",
        source_id="catalog.flood.building",
        cache_hit=False,
        version_token="v1",
        selected_source_id="catalog.flood.building",
        component_coverage={
            "raw.osm.building": {"feature_count": 300000, "coverage_status": "available"},
            "raw.google.building": {"feature_count": 520000, "coverage_status": "available"},
        },
    )

    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(
        service.input_acquisition_service,
        "resolve_task_driven_inputs",
        lambda **_kwargs: resolved,
    )
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)
    monkeypatch.setattr(
        service,
        "run_execution_stage",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("direct execution path should not be used")),
    )

    def fake_tiled_run(**kwargs):
        on_event = kwargs["on_event"]
        on_event("tile_execution_started", {"tile_id": "tile_000_000"})
        on_event("tile_execution_completed", {"tile_id": "tile_000_000", "feature_count": 1})
        on_event(
            "tile_stitch_completed",
            {
                "tile_count": len(kwargs["tile_manifest"].tiles),
                "stitched_feature_count": 1,
                "output_shp": str(fused_shp),
            },
        )
        return TiledBuildingRunResult(
            output_shp=fused_shp,
            tile_count=len(kwargs["tile_manifest"].tiles),
            stitched_feature_count=1,
            tile_outputs=[],
        )

    monkeypatch.setattr(service.tiled_building_runtime_service, "run_tiled_building_job", fake_tiled_run)

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(
                type=RunTriggerType.user_query,
                content="need building data for Benin",
                spatial_extent="bbox(2.48,9.23,2.77,9.44)",
            ),
            target_crs="EPSG:32631",
            field_mapping={},
            debug=False,
            input_strategy=RunInputStrategy.task_driven_auto,
        ),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    audit_events = service.get_audit_events(status.run_id)
    event_kinds = [event.kind for event in audit_events]
    assert "tile_manifest_created" in event_kinds
    assert "tile_execution_started" in event_kinds
    assert "tile_execution_completed" in event_kinds
    assert "tile_stitch_completed" in event_kinds


def test_workflow_executor_emits_step_lifecycle_events_for_executable_tasks(tmp_path: Path) -> None:
    output_path = tmp_path / "fused.shp"
    output_path.write_text("dummy", encoding="utf-8")
    plan = _build_plan(workflow_id="wf_step_callback", revision=1)
    plan.tasks.insert(
        0,
        WorkflowTask(
            step=0,
            name="reserved_transform",
            description="reserved transform",
            algorithm_id="algo.transform.trajectory_to_road_candidate",
            input=WorkflowTaskInput(data_type_id="dt.trajectory.raw", data_source_id="catalog.trajectory", parameters={}),
            output=WorkflowTaskOutput(data_type_id="dt.road.candidate", description=""),
            depends_on=[],
            is_transform=True,
            kg_validated=True,
            alternatives=[],
        ),
    )
    executor = WorkflowExecutor(
        _NoHealingKG(),
        algorithm_handlers={"algo.fusion.building.v1": lambda _context: output_path},
    )
    context = ExecutionContext(
        run_id="run-step-callback",
        job_type=JobType.building,
        osm_shp=tmp_path / "osm.shp",
        ref_shp=tmp_path / "ref.shp",
        output_dir=tmp_path,
        target_crs="EPSG:32643",
    )
    events: list[dict[str, object]] = []

    result = executor.execute_plan(plan=plan, context=context, repair_records=[], on_step_event=events.append)

    assert result == output_path
    assert [event["status"] for event in events] == ["started", "succeeded"]
    assert all(event["step"] == 1 for event in events)
    assert all(event["algorithm_id"] == "algo.fusion.building.v1" for event in events)
    assert all(event["data_source_id"] == "upload.bundle" for event in events)


def test_workflow_executor_emits_step_failed_before_final_step_error(tmp_path: Path) -> None:
    plan = _build_plan(workflow_id="wf_step_failure_callback", revision=1)
    plan.tasks[0].alternatives = []

    def failing_handler(_context):
        raise RuntimeError("primary failed")

    executor = WorkflowExecutor(
        _NoHealingKG(),
        algorithm_handlers={"algo.fusion.building.v1": failing_handler},
    )
    context = ExecutionContext(
        run_id="run-step-failure-callback",
        job_type=JobType.building,
        osm_shp=tmp_path / "osm.shp",
        ref_shp=tmp_path / "ref.shp",
        output_dir=tmp_path,
        target_crs="EPSG:32643",
    )
    events: list[dict[str, object]] = []

    with pytest.raises(RuntimeError, match="Task failed after healing strategies"):
        executor.execute_plan(plan=plan, context=context, repair_records=[], on_step_event=events.append)

    assert [event["status"] for event in events] == ["started", "failed"]
    assert events[-1]["step"] == 1
    assert events[-1]["algorithm_id"] == "algo.fusion.building.v1"
    assert events[-1]["data_source_id"] == "upload.bundle"
    assert events[-1]["error"] == "RuntimeError: primary failed"


def test_execution_stage_writes_step_started_and_succeeded_audit_events(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    run_id = "run-step-audit-success"
    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        target_crs="EPSG:32643",
        field_mapping={},
        debug=False,
    )
    _seed_run_status(service, run_id, request)

    plan = _build_plan(workflow_id="wf_step_audit_success", revision=1)
    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    fused_shp = tmp_path / "fused.shp"
    for path in [osm_shp, ref_shp, fused_shp]:
        path.write_text("dummy", encoding="utf-8")

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda zip_path, *_args, **_kwargs: osm_shp if Path(zip_path).name.startswith("osm") else ref_shp)

    def fake_execute_plan(*, plan, context, repair_records, on_step_event):
        task = plan.tasks[0]
        payload = {
            "status": "started",
            "step": task.step,
            "algorithm_id": task.algorithm_id,
            "data_source_id": task.input.data_source_id,
        }
        on_step_event(payload)
        on_step_event({**payload, "status": "succeeded", "effective_algorithm_id": "algo.fusion.building.safe"})
        return fused_shp

    monkeypatch.setattr(service.executor, "execute_plan", fake_execute_plan)

    service.run_execution_stage(
        run_id=run_id,
        request=request,
        plan=plan,
        osm_zip_path=tmp_path / "osm.zip",
        ref_zip_path=tmp_path / "ref.zip",
        intermediate_dir=tmp_path / "intermediate",
        output_dir=tmp_path / "output",
        repair_records=[],
    )

    step_events = [event for event in service.get_audit_events(run_id) if event.kind.startswith("step_")]
    assert [event.kind for event in step_events] == ["step_started", "step_succeeded"]
    assert [event.current_step for event in step_events] == [1, 1]
    assert step_events[0].details == {
        "status": "started",
        "step": 1,
        "algorithm_id": "algo.fusion.building.v1",
        "data_source_id": "upload.bundle",
    }
    assert step_events[1].details["effective_algorithm_id"] == "algo.fusion.building.safe"


def test_execution_stage_writes_step_failed_audit_event_before_raising(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    run_id = "run-step-audit-failure"
    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        target_crs="EPSG:32643",
        field_mapping={},
        debug=False,
    )
    _seed_run_status(service, run_id, request)

    plan = _build_plan(workflow_id="wf_step_audit_failure", revision=1)
    plan.tasks[0].alternatives = []
    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda zip_path, *_args, **_kwargs: osm_shp if Path(zip_path).name.startswith("osm") else ref_shp)

    service.executor = WorkflowExecutor(
        _NoHealingKG(),
        algorithm_handlers={
            "algo.fusion.building.v1": lambda _context: (_ for _ in ()).throw(RuntimeError("primary failed"))
        },
    )

    with pytest.raises(RuntimeError, match="Task failed after healing strategies"):
        service.run_execution_stage(
            run_id=run_id,
            request=request,
            plan=plan,
            osm_zip_path=tmp_path / "osm.zip",
            ref_zip_path=tmp_path / "ref.zip",
            intermediate_dir=tmp_path / "intermediate",
            output_dir=tmp_path / "output",
            repair_records=[],
        )

    audit_events = service.get_audit_events(run_id)
    step_failed = next(event for event in audit_events if event.kind == "step_failed")
    assert step_failed.current_step == 1
    assert step_failed.details == {
        "status": "failed",
        "step": 1,
        "algorithm_id": "algo.fusion.building.v1",
        "data_source_id": "upload.bundle",
        "error": "RuntimeError: primary failed",
        "root_cause": "PRIMARY_EXECUTION_FAILED",
        "failure_category": "ALGO_RUNTIME_ERROR",
        "action": "replan",
        "recoverable": True,
        "suggested_action": "replan",
    }
    assert not any(event.kind == "execution_completed" for event in audit_events)


def test_task_driven_replan_refreshes_inputs_when_source_changes(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    service.max_plan_revisions = 2

    fused_shp = tmp_path / "fused.shp"
    artifact_zip = tmp_path / "artifact.zip"
    _write_minimal_polygon_shapefile(fused_shp)
    artifact_zip.write_bytes(b"zip")

    initial_plan = _build_plan(workflow_id="wf_initial", revision=1)
    initial_plan.tasks[0].input.data_source_id = "catalog.flood.building"
    replanned_plan = _build_plan(workflow_id="wf_replanned", revision=2)
    replanned_plan.tasks[0].input.data_source_id = "catalog.earthquake.building"

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda zip_path, *_args, **_kwargs: Path(str(zip_path) + ".shp"))
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: initial_plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service.planner, "replan_from_error", lambda **_kwargs: replanned_plan.model_copy(deep=True))
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    resolve_calls: list[str] = []

    def fake_resolve_task_driven_inputs(**kwargs):
        source_id = kwargs["source_id"]
        resolve_calls.append(source_id)
        osm_zip = tmp_path / f"{source_id.replace('.', '_')}_osm.zip"
        ref_zip = tmp_path / f"{source_id.replace('.', '_')}_ref.zip"
        _write_dummy_zip(osm_zip)
        _write_dummy_zip(ref_zip)
        return ResolvedRunInputs(
            osm_zip_path=osm_zip,
            ref_zip_path=ref_zip,
            source_mode="generated",
            source_id=source_id,
            cache_hit=False,
            version_token=f"version:{source_id}",
        )

    monkeypatch.setattr(service.input_acquisition_service, "resolve_task_driven_inputs", fake_resolve_task_driven_inputs)

    execute_calls = {"count": 0}

    def fake_execute_plan(*, plan, context, repair_records, **_kwargs):
        execute_calls["count"] += 1
        if execute_calls["count"] == 1:
            repair_records.append(
                RepairRecord(
                    attempt_no=1,
                    strategy="alternative_source",
                    step=1,
                    message="Primary source failed.",
                    success=False,
                    timestamp="2026-04-02T00:00:00+00:00",
                    reason_code="primary_source_failed",
                    from_source="catalog.flood.building",
                    to_source="catalog.earthquake.building",
                )
            )
            raise RuntimeError("source failed")
        assert plan.workflow_id == "wf_replanned"
        return fused_shp

    monkeypatch.setattr(service.executor, "execute_plan", fake_execute_plan)

    status = service.create_run(
        request=_build_auto_request(),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert latest.plan_revision == 2
    assert resolve_calls == ["catalog.flood.building", "catalog.earthquake.building"]
    audit_events = service.get_audit_events(status.run_id)
    resolved_events = [event for event in audit_events if event.kind == "task_inputs_resolved"]
    assert [event.details["source_id"] for event in resolved_events] == [
        "catalog.flood.building",
        "catalog.earthquake.building",
    ]
    assert resolved_events[-1].plan_revision == 2


def test_pattern_selection_uses_durable_learning_summaries_as_policy_hints(tmp_path: Path) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    plan = _build_plan(workflow_id="wf_learning_hints", revision=1)
    plan.context["retrieval"]["candidate_patterns"] = [
        {"pattern_id": "wp.historically.weak", "success_rate": 0.90},
        {"pattern_id": "wp.historically.strong", "success_rate": 0.86},
    ]
    plan.context["retrieval"]["durable_learning_summaries"] = {
        "patterns": [
            {
                "entity_kind": "pattern",
                "entity_id": "wp.historically.weak",
                "job_type": "building",
                "disaster_type": "flood",
                "total_runs": 4,
                "success_count": 1,
                "failure_count": 3,
                "repaired_count": 0,
                "last_run_at": "2026-04-20T00:00:00+00:00",
                "last_failure_reason": "source failed",
            },
            {
                "entity_kind": "pattern",
                "entity_id": "wp.historically.strong",
                "job_type": "building",
                "disaster_type": "flood",
                "total_runs": 4,
                "success_count": 4,
                "failure_count": 0,
                "repaired_count": 0,
                "last_run_at": "2026-04-20T00:00:00+00:00",
                "last_failure_reason": None,
            },
        ]
    }

    decision = service._build_pattern_selection_decision(plan)

    assert decision is not None
    assert decision.selected_id == "wp.historically.strong"
    selected = next(candidate for candidate in decision.candidates if candidate.candidate_id == decision.selected_id)
    weak = next(candidate for candidate in decision.candidates if candidate.candidate_id == "wp.historically.weak")
    assert selected.evidence["metrics"]["learning_adjustment"] == 0.10
    assert weak.evidence["metrics"]["learning_adjustment"] < 0
    assert "context.retrieval.durable_learning_summaries.patterns" in decision.evidence_refs


def test_pattern_selection_uses_summary_adjustment_before_count_fallback(tmp_path: Path) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    plan = _build_plan(workflow_id="wf_learning_adjustment", revision=1)
    plan.context["retrieval"]["candidate_patterns"] = [{"pattern_id": "wp.preferred", "success_rate": 0.80}]
    plan.context["retrieval"]["durable_learning_summaries"] = {
        "patterns": [
            {
                "entity_id": "wp.preferred",
                "total_runs": 10,
                "success_count": 1,
                "adjustment": 0.08,
            }
        ]
    }

    decision = service._build_pattern_selection_decision(plan)

    assert decision is not None
    selected = next(candidate for candidate in decision.candidates if candidate.candidate_id == "wp.preferred")
    assert selected.evidence["metrics"]["learning_adjustment"] == 0.08


def test_agent_run_service_fails_when_replan_limit_is_reached(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    service.max_plan_revisions = 2

    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")

    initial_plan = _build_plan(workflow_id="wf_initial", revision=1)
    replanned_plan = _build_plan(workflow_id="wf_replanned", revision=2, algorithm_id="algo.fusion.building.safe")

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: osm_shp)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: initial_plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service.planner, "replan_from_error", lambda **_kwargs: replanned_plan.model_copy(deep=True))

    execute_calls = {"count": 0}

    def fake_execute_plan(*, plan, context, repair_records, **_kwargs):
        execute_calls["count"] += 1
        repair_records.append(
            RepairRecord(
                attempt_no=len(repair_records) + 1,
                strategy="alternative_algorithm",
                step=1,
                message=f"Attempt {execute_calls['count']} failed",
                success=False,
                timestamp="2026-04-02T00:00:00+00:00",
                reason_code="alternative_algorithm_failed",
                from_algorithm=plan.tasks[0].algorithm_id,
                to_algorithm="algo.fusion.building.safe",
            )
        )
        raise RuntimeError(f"still failing #{execute_calls['count']}")

    monkeypatch.setattr(service.executor, "execute_plan", fake_execute_plan)

    phase_history: list[RunPhase] = []
    original_update_status = service._update_status

    def tracking_update_status(*args, **kwargs):
        phase = args[1] if len(args) > 1 else kwargs["phase"]
        phase_history.append(phase)
        return original_update_status(*args, **kwargs)

    monkeypatch.setattr(service, "_update_status", tracking_update_status)

    osm_zip = tmp_path / "osm.zip"
    ref_zip = tmp_path / "ref.zip"
    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        target_crs="EPSG:32643",
        field_mapping={},
        debug=False,
    )

    status = service.create_run(
        request=request,
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(osm_zip),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(ref_zip),
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.failed
    assert latest.plan_revision == 2
    assert RunPhase.healing in phase_history
    assert "max plan revisions (2)" in (latest.error or "")
    assert "max plan revisions (2)" in (latest.failure_summary or "")
    saved_plan = service.get_plan(status.run_id)
    assert saved_plan is not None
    assert saved_plan.workflow_id == "wf_replanned"
    assert saved_plan.context["plan_revision"] == 2
    replan_decisions = [record for record in latest.decision_records if record.decision_type == "replan_or_fail"]
    assert replan_decisions
    assert replan_decisions[-1].selected_id == "fail"
    assert latest.artifact_reuse is not None
    assert latest.artifact_reuse.reused is False
    assert latest.artifact_reuse.freshness_status == "not_available"
    audit_events = service.get_audit_events(status.run_id)
    assert any(event.kind == "replan_requested" for event in audit_events)
    assert any(event.kind == "replan_rejected" for event in audit_events)
    assert audit_events[-1].kind == "run_failed"
    assert audit_events[-1].details["error"] == latest.error


def test_update_status_loads_run_from_disk_when_worker_process_is_fresh(tmp_path: Path) -> None:
    base_dir = tmp_path / "runs"
    run_status = RunStatus(
        run_id="run-from-disk",
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        phase=RunPhase.queued,
        progress=0,
        target_crs="EPSG:32643",
        debug=False,
        error=None,
        log_path=str(base_dir / "run-from-disk" / "logs" / "run.log"),
        plan_path=None,
        validation_path=None,
        artifact=None,
        repair_records=[],
        current_step=None,
        attempt_no=0,
        healing_summary={},
        failure_summary=None,
        plan_revision=0,
        created_at="2026-04-02T00:00:00+00:00",
        started_at=None,
        finished_at=None,
    )

    writer = AgentRunService(base_dir=base_dir)
    writer._persist_status(run_status)

    worker_side = AgentRunService(base_dir=base_dir)
    worker_side._runs.clear()

    worker_side._update_status(
        "run-from-disk",
        RunPhase.planning,
        progress=5,
        started_at="2026-04-02T00:00:01+00:00",
    )

    updated = worker_side.get_run("run-from-disk")
    assert updated is not None
    assert updated.phase == RunPhase.planning
    assert updated.progress == 5
    assert updated.started_at == "2026-04-02T00:00:01+00:00"


def test_get_run_refreshes_stale_cached_status_from_disk(tmp_path: Path) -> None:
    base_dir = tmp_path / "runs"

    api_side = AgentRunService(base_dir=base_dir)
    worker_side = AgentRunService(base_dir=base_dir)

    run_status = RunStatus(
        run_id="shared-run",
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        phase=RunPhase.queued,
        progress=0,
        target_crs="EPSG:32643",
        debug=False,
        error=None,
        log_path=str(base_dir / "shared-run" / "logs" / "run.log"),
        plan_path=None,
        validation_path=None,
        artifact=None,
        repair_records=[],
        current_step=None,
        attempt_no=0,
        healing_summary={},
        failure_summary=None,
        plan_revision=0,
        created_at="2026-04-02T00:00:00+00:00",
        started_at=None,
        finished_at=None,
    )

    api_side._persist_status(run_status)
    api_side._runs["shared-run"] = run_status

    worker_side._update_status(
        "shared-run",
        RunPhase.failed,
        progress=100,
        error="RuntimeError: boom",
        finished_at="2026-04-02T00:00:02+00:00",
        failure_summary="RuntimeError: boom",
    )

    refreshed = api_side.get_run("shared-run")
    assert refreshed is not None
    assert refreshed.phase == RunPhase.failed
    assert refreshed.error == "RuntimeError: boom"
    assert refreshed.finished_at == "2026-04-02T00:00:02+00:00"


def test_agent_run_service_enforces_plan_grounding_before_validation(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    monkeypatch.setenv("GEOFUSION_PLAN_GROUNDING_MODE", "enforce")
    ungrounded_plan = _build_plan(workflow_id="wf_ungrounded", revision=1)
    ungrounded_plan.context["retrieval"] = {
        "candidate_patterns": [],
        "data_sources": [],
        "algorithms": {},
        "output_schema_policies": {},
    }
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: ungrounded_plan.model_copy(deep=True))

    status = service.create_run(
        request=_build_auto_request(),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.failed
    assert "PLAN_GROUNDING_FAILED" in (latest.error or "")
    saved_plan = service.get_plan(status.run_id)
    assert saved_plan is not None
    assert saved_plan.context["grounding_gate"]["mode"] == "enforce"
    assert saved_plan.context["grounding_gate"]["allowed"] is False
    events = service.get_audit_events(status.run_id)
    assert any(event.kind == "plan_grounding_rejected" for event in events)
    assert not any(event.kind == "plan_validated" for event in events)


def test_agent_run_service_records_grounding_gate_in_report_mode(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    plan = _build_plan(workflow_id="wf_report_mode", revision=1)
    plan.context["retrieval"] = {
        "candidate_patterns": [],
        "data_sources": [],
        "algorithms": {},
        "output_schema_policies": {},
    }
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service, "run_validation_stage", lambda run_id, plan: plan)
    monkeypatch.setattr(service, "_attempt_artifact_reuse", lambda **_kwargs: None)
    monkeypatch.setattr(service, "_resolve_execution_inputs", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("stop")))

    status = service.create_run(
        request=_build_auto_request(),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    saved_plan = service.get_plan(status.run_id)
    assert saved_plan is not None
    assert saved_plan.context["grounding_gate"]["mode"] == "report"
    assert saved_plan.context["grounding_gate"]["allowed"] is True
