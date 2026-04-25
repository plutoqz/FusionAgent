from __future__ import annotations

import time
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
geopandas = pytest.importorskip("geopandas")
pytest.importorskip("shapely")
from fastapi.testclient import TestClient

from api.app import create_app
import api.routers.runs_v2 as runs_v2_router
from schemas.agent import (
    RunTrigger,
    RunTriggerType,
    ValidationReport,
    WorkflowPlan,
    WorkflowTask,
    WorkflowTaskInput,
    WorkflowTaskOutput,
)
from services.agent_run_service import AgentRunService
from services.aoi_resolution_service import ResolvedAOI
from services.input_acquisition_service import ResolvedRunInputs


def _zip_bundle(shp_path: Path, out_zip: Path) -> Path:
    base = shp_path.with_suffix("")
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in shp_path.parent.glob(f"{base.name}.*"):
            zf.write(file, arcname=file.name)
    return out_zip


def _build_building_sample(tmp_path: Path) -> tuple[Path, Path]:
    from shapely.geometry import Polygon

    osm = geopandas.GeoDataFrame(
        {
            "osm_id": [1, 2],
            "fclass": ["building", "building"],
            "name": ["b1", "b2"],
            "type": ["res", "res"],
            "geometry": [
                Polygon([(0, 0), (0, 0.01), (0.01, 0.01), (0.01, 0)]),
                Polygon([(0.02, 0.02), (0.02, 0.03), (0.03, 0.03), (0.03, 0.02)]),
            ],
        },
        crs="EPSG:4326",
    )
    ref = geopandas.GeoDataFrame(
        {
            "confidence": [0.9, 0.95],
            "area_in_me": [100.0, 100.0],
            "longitude": [0.005, 0.025],
            "latitude": [0.005, 0.025],
            "geometry": [
                Polygon([(0, 0), (0, 0.011), (0.011, 0.011), (0.011, 0)]),
                Polygon([(0.02, 0.02), (0.02, 0.031), (0.031, 0.031), (0.031, 0.02)]),
            ],
        },
        crs="EPSG:4326",
    )
    osm_shp = tmp_path / "osm_building.shp"
    ref_shp = tmp_path / "ref_building.shp"
    osm.to_file(osm_shp)
    ref.to_file(ref_shp)
    return osm_shp, ref_shp


def _build_water_sample(tmp_path: Path) -> tuple[Path, Path]:
    from shapely.geometry import Polygon

    osm = geopandas.GeoDataFrame(
        {
            "osm_id": [11, 12],
            "fclass": ["water", "water"],
            "name": ["lake-a", "lake-b"],
            "geometry": [
                Polygon([(0, 0), (0, 0.02), (0.02, 0.02), (0.02, 0)]),
                Polygon([(0.03, 0.03), (0.03, 0.05), (0.05, 0.05), (0.05, 0.03)]),
            ],
        },
        crs="EPSG:4326",
    )
    ref = geopandas.GeoDataFrame(
        {
            "new_id": [101, 102],
            "name": ["lake-a-ref", "lake-c-ref"],
            "geometry": [
                Polygon([(0.001, 0.001), (0.001, 0.021), (0.021, 0.021), (0.021, 0.001)]),
                Polygon([(0.06, 0.06), (0.06, 0.08), (0.08, 0.08), (0.08, 0.06)]),
            ],
        },
        crs="EPSG:4326",
    )
    osm_shp = tmp_path / "osm_water.shp"
    ref_shp = tmp_path / "ref_water.shp"
    osm.to_file(osm_shp)
    ref.to_file(ref_shp)
    return osm_shp, ref_shp


def _build_task_driven_plan() -> WorkflowPlan:
    return WorkflowPlan(
        workflow_id="wf_task_driven_auto",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="need building data"),
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
                "candidate_patterns": [
                    {
                        "pattern_id": "wp.flood.building.default",
                        "success_rate": 0.91,
                        "steps": [
                            {
                                "algorithm_id": "algo.fusion.building.v1",
                                "input_data_type": "dt.building.bundle",
                                "output_data_type": "dt.building.fused",
                                "data_source_id": "catalog.flood.building",
                            }
                        ],
                    }
                ],
                "data_sources": [{"source_id": "catalog.flood.building"}],
                "algorithms": {"algo.fusion.building.v1": {"tool_ref": "builtin:building"}},
                "output_schema_policies": {"dt.building.fused": {"policy_id": "schema.building.fused"}},
            },
            "selection_reason": "initial",
            "llm_provider": "mock",
            "plan_revision": 1,
            "planning_mode": "task_driven",
        },
        tasks=[
            WorkflowTask(
                step=1,
                name="building_fusion",
                description="building fusion",
                algorithm_id="algo.fusion.building.v1",
                input=WorkflowTaskInput(
                    data_type_id="dt.building.bundle",
                    data_source_id="catalog.flood.building",
                    parameters={},
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


def _build_task_driven_water_plan() -> WorkflowPlan:
    return WorkflowPlan(
        workflow_id="wf_water_task_driven_auto",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="need water polygons for Nairobi, Kenya"),
        context={
            "intent": {
                "job_type": "water",
                "profile_source": "direct_task",
                "task_bundle": {
                    "bundle_id": "task_bundle.direct_request",
                    "requested_tasks": ["task.water.fusion"],
                    "requires_disaster_profile": False,
                },
            },
            "retrieval": {
                "candidate_patterns": [{"pattern_id": "wp.flood.water.default", "success_rate": 0.84}],
                "data_sources": [{"source_id": "catalog.flood.water"}],
            },
            "selection_reason": "initial",
            "llm_provider": "mock",
            "plan_revision": 1,
            "planning_mode": "task_driven",
        },
        tasks=[
            WorkflowTask(
                step=1,
                name="water_fusion",
                description="water fusion",
                algorithm_id="algo.fusion.water.v1",
                input=WorkflowTaskInput(
                    data_type_id="dt.water.bundle",
                    data_source_id="catalog.flood.water",
                    parameters={},
                ),
                output=WorkflowTaskOutput(data_type_id="dt.water.fused", description=""),
                depends_on=[],
                is_transform=False,
                kg_validated=True,
                alternatives=[],
            )
        ],
        expected_output="water result",
        validation=ValidationReport(valid=True, inserted_transform_steps=0, issues=[]),
    )


def _build_task_driven_poi_plan() -> WorkflowPlan:
    return WorkflowPlan(
        workflow_id="wf_poi_task_driven_auto",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="need poi data for Nairobi, Kenya"),
        context={
            "intent": {
                "job_type": "poi",
                "profile_source": "direct_task",
                "task_bundle": {
                    "bundle_id": "task_bundle.direct_request",
                    "requested_tasks": ["task.poi.fusion"],
                    "requires_disaster_profile": False,
                },
            },
            "retrieval": {
                "candidate_patterns": [{"pattern_id": "wp.generic.poi.default", "success_rate": 0.8}],
                "data_sources": [{"source_id": "catalog.generic.poi"}],
            },
            "selection_reason": "initial",
            "llm_provider": "mock",
            "plan_revision": 1,
            "planning_mode": "task_driven",
        },
        tasks=[
            WorkflowTask(
                step=1,
                name="poi_fusion",
                description="poi fusion",
                algorithm_id="algo.fusion.poi.v1",
                input=WorkflowTaskInput(
                    data_type_id="dt.poi.bundle",
                    data_source_id="catalog.generic.poi",
                    parameters={},
                ),
                output=WorkflowTaskOutput(data_type_id="dt.poi.fused", description=""),
                depends_on=[],
                is_transform=False,
                kg_validated=True,
                alternatives=[],
            )
        ],
        expected_output="poi result",
        validation=ValidationReport(valid=True, inserted_transform_steps=0, issues=[]),
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


def _wait_run(client: TestClient, run_id: str, timeout_sec: float = 60.0) -> dict:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        resp = client.get(f"/api/v2/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        if data["phase"] in {"succeeded", "failed"}:
            return data
        time.sleep(0.25)
    raise TimeoutError(f"Run timeout: {run_id}")


def _bind_current_default_runtime(service: AgentRunService, monkeypatch: pytest.MonkeyPatch) -> None:
    original_build_runtime_dependencies = service._build_runtime_dependencies

    def _build_runtime_dependencies(*, settings, llm_provider=None):
        if settings == service._default_runtime.settings:
            return service._default_runtime
        return original_build_runtime_dependencies(settings=settings, llm_provider=llm_provider)

    monkeypatch.setattr(service, "_build_runtime_dependencies", _build_runtime_dependencies)


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GEOFUSION_KG_BACKEND", "memory")
    monkeypatch.setenv("GEOFUSION_LLM_PROVIDER", "mock")
    monkeypatch.setenv("GEOFUSION_CELERY_EAGER", "1")
    monkeypatch.setenv("GEOFUSION_API_PORT", "8000")

    svc = AgentRunService(base_dir=tmp_path / "runs")
    _bind_current_default_runtime(svc, monkeypatch)
    monkeypatch.setattr(runs_v2_router, "agent_run_service", svc)
    app = create_app()
    return TestClient(app)


def test_v2_runtime_metadata_endpoint_reports_current_environment(client: TestClient) -> None:
    resp = client.get("/api/v2/runtime")

    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "kg_backend": "memory",
        "llm_provider": "mock",
        "celery_eager": "1",
        "api_port": "8000",
    }


def test_v2_run_building_integration(tmp_path: Path, client: TestClient) -> None:
    osm_shp, ref_shp = _build_building_sample(tmp_path)
    osm_zip = _zip_bundle(osm_shp, tmp_path / "osm_building.zip")
    ref_zip = _zip_bundle(ref_shp, tmp_path / "ref_building.zip")

    with osm_zip.open("rb") as f1, ref_zip.open("rb") as f2:
        resp = client.post(
            "/api/v2/runs",
            files={
                "osm_zip": ("osm_building.zip", f1.read(), "application/zip"),
                "ref_zip": ("ref_building.zip", f2.read(), "application/zip"),
            },
            data={
                "job_type": "building",
                "trigger_type": "user_query",
                "trigger_content": "融合建筑",
                "target_crs": "EPSG:32643",
                "field_mapping": "{}",
                "debug": "false",
            },
        )
    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]

    status = _wait_run(client, run_id)
    assert status["phase"] == "succeeded", status.get("error")

    plan_resp = client.get(f"/api/v2/runs/{run_id}/plan")
    assert plan_resp.status_code == 200
    plan = plan_resp.json()["plan"]
    assert plan["tasks"]
    assert isinstance(plan["tasks"][0]["kg_validated"], bool)

    audit_resp = client.get(f"/api/v2/runs/{run_id}/audit")
    assert audit_resp.status_code == 200
    audit = audit_resp.json()
    assert audit["run_id"] == run_id
    assert audit["events"]
    assert audit["events"][-1]["kind"] == "run_succeeded"

    inspection_resp = client.get(f"/api/v2/runs/{run_id}/inspection")
    assert inspection_resp.status_code == 200
    inspection = inspection_resp.json()
    assert inspection["run"]["run_id"] == run_id
    assert inspection["plan"]["workflow_id"] == plan["workflow_id"]
    assert inspection["audit_events"][-1]["kind"] == "run_succeeded"
    assert inspection["artifact"]["available"] is True
    assert inspection["artifact"]["download_path"] == f"/api/v2/runs/{run_id}/artifact"

    artifact_resp = client.get(f"/api/v2/runs/{run_id}/artifact")
    assert artifact_resp.status_code == 200
    assert artifact_resp.content


def test_v2_run_water_uploaded_integration(tmp_path: Path, client: TestClient) -> None:
    osm_shp, ref_shp = _build_water_sample(tmp_path)
    osm_zip = _zip_bundle(osm_shp, tmp_path / "osm_water.zip")
    ref_zip = _zip_bundle(ref_shp, tmp_path / "ref_water.zip")

    with osm_zip.open("rb") as f1, ref_zip.open("rb") as f2:
        resp = client.post(
            "/api/v2/runs",
            files={
                "osm_zip": ("osm_water.zip", f1.read(), "application/zip"),
                "ref_zip": ("ref_water.zip", f2.read(), "application/zip"),
            },
            data={
                "job_type": "water",
                "trigger_type": "user_query",
                "trigger_content": "融合水体面数据",
                "disaster_type": "flood",
                "target_crs": "EPSG:32643",
                "field_mapping": "{}",
                "debug": "false",
            },
        )
    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]

    status = _wait_run(client, run_id)
    assert status["phase"] == "succeeded", status.get("error")

    plan_resp = client.get(f"/api/v2/runs/{run_id}/plan")
    assert plan_resp.status_code == 200
    plan = plan_resp.json()["plan"]
    assert plan["tasks"]
    assert plan["tasks"][0]["algorithm_id"] == "algo.fusion.water.v1"
    assert plan["tasks"][0]["input"]["data_type_id"] == "dt.water.bundle"
    assert plan["tasks"][0]["output"]["data_type_id"] == "dt.water.fused"

    inspection_resp = client.get(f"/api/v2/runs/{run_id}/inspection")
    assert inspection_resp.status_code == 200
    inspection = inspection_resp.json()
    assert inspection["run"]["job_type"] == "water"
    assert inspection["artifact"]["available"] is True

    artifact_resp = client.get(f"/api/v2/runs/{run_id}/artifact")
    assert artifact_resp.status_code == 200
    assert artifact_resp.content


def test_v2_run_water_task_driven_auto_integration(
    tmp_path: Path,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = runs_v2_router.agent_run_service
    osm_shp = tmp_path / "resolved_osm_water.shp"
    ref_shp = tmp_path / "resolved_ref_water.shp"
    fused_shp = tmp_path / "fused_water.shp"
    artifact_zip = tmp_path / "artifact_water.zip"
    for path in [osm_shp, ref_shp, fused_shp]:
        path.write_text("dummy", encoding="utf-8")
    artifact_zip.write_bytes(b"zip")

    prepared_dir = tmp_path / "prepared_water"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    resolved = ResolvedRunInputs(
        osm_zip_path=prepared_dir / "osm.zip",
        ref_zip_path=prepared_dir / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.flood.water",
        cache_hit=False,
        version_token="water-v1",
    )
    resolved.osm_zip_path.write_bytes(b"osm")
    resolved.ref_zip_path.write_bytes(b"ref")

    monkeypatch.setattr(service.aoi_resolution_service, "resolve", lambda _query: _resolved_nairobi_aoi())
    monkeypatch.setattr(
        service.planner,
        "create_plan",
        lambda **_kwargs: _build_task_driven_water_plan().model_copy(deep=True),
    )
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service.input_acquisition_service, "resolve_task_driven_inputs", lambda **_kwargs: resolved)
    monkeypatch.setattr(
        "services.agent_run_service.validate_zip_has_shapefile",
        lambda zip_path, *_args, **_kwargs: osm_shp if Path(zip_path).name.startswith("osm") else ref_shp,
    )
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: fused_shp)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    resp = client.post(
        "/api/v2/runs",
        data={
            "job_type": "water",
            "trigger_type": "user_query",
            "trigger_content": "need water polygons for Nairobi, Kenya",
            "input_strategy": "task_driven_auto",
            "field_mapping": "{}",
            "debug": "false",
        },
    )

    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]

    status = _wait_run(client, run_id)
    assert status["phase"] == "succeeded", status.get("error")

    inspection_resp = client.get(f"/api/v2/runs/{run_id}/inspection")
    assert inspection_resp.status_code == 200
    inspection = inspection_resp.json()
    assert inspection["run"]["job_type"] == "water"
    resolved_event = next(event for event in inspection["audit_events"] if event["kind"] == "task_inputs_resolved")
    assert resolved_event["details"]["source_id"] == "catalog.flood.water"
    assert resolved_event["details"]["version_token"] == "water-v1"
    assert resolved_event["details"]["resolved_aoi"]["country_code"] == "ke"


def test_v2_run_poi_task_driven_auto_integration(
    tmp_path: Path,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = runs_v2_router.agent_run_service
    osm_shp = tmp_path / "resolved_osm_poi.shp"
    ref_shp = tmp_path / "resolved_ref_poi.shp"
    fused_shp = tmp_path / "fused_poi.shp"
    artifact_zip = tmp_path / "artifact_poi.zip"
    for path in [osm_shp, ref_shp, fused_shp]:
        path.write_text("dummy", encoding="utf-8")
    artifact_zip.write_bytes(b"zip")

    prepared_dir = tmp_path / "prepared_poi"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    resolved = ResolvedRunInputs(
        osm_zip_path=prepared_dir / "osm.zip",
        ref_zip_path=prepared_dir / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.generic.poi",
        cache_hit=False,
        version_token="poi-v1",
    )
    resolved.osm_zip_path.write_bytes(b"osm")
    resolved.ref_zip_path.write_bytes(b"ref")

    monkeypatch.setattr(service.aoi_resolution_service, "resolve", lambda _query: _resolved_nairobi_aoi())
    monkeypatch.setattr(
        service.planner,
        "create_plan",
        lambda **_kwargs: _build_task_driven_poi_plan().model_copy(deep=True),
    )
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service.input_acquisition_service, "resolve_task_driven_inputs", lambda **_kwargs: resolved)
    monkeypatch.setattr(
        "services.agent_run_service.validate_zip_has_shapefile",
        lambda zip_path, *_args, **_kwargs: osm_shp if Path(zip_path).name.startswith("osm") else ref_shp,
    )
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: fused_shp)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    resp = client.post(
        "/api/v2/runs",
        data={
            "job_type": "poi",
            "trigger_type": "user_query",
            "trigger_content": "need poi data for Nairobi, Kenya",
            "input_strategy": "task_driven_auto",
            "field_mapping": "{}",
            "debug": "false",
        },
    )

    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]

    status = _wait_run(client, run_id)
    assert status["phase"] == "succeeded", status.get("error")

    inspection_resp = client.get(f"/api/v2/runs/{run_id}/inspection")
    assert inspection_resp.status_code == 200
    inspection = inspection_resp.json()
    assert inspection["run"]["job_type"] == "poi"
    resolved_event = next(event for event in inspection["audit_events"] if event["kind"] == "task_inputs_resolved")
    assert resolved_event["details"]["source_id"] == "catalog.generic.poi"
    assert resolved_event["details"]["version_token"] == "poi-v1"
    assert resolved_event["details"]["resolved_aoi"]["country_code"] == "ke"


def test_v2_run_scheduled_trigger(tmp_path: Path, client: TestClient) -> None:
    osm_shp, ref_shp = _build_building_sample(tmp_path)
    osm_zip = _zip_bundle(osm_shp, tmp_path / "osm_building2.zip")
    ref_zip = _zip_bundle(ref_shp, tmp_path / "ref_building2.zip")

    with osm_zip.open("rb") as f1, ref_zip.open("rb") as f2:
        resp = client.post(
            "/api/v2/runs",
            files={
                "osm_zip": ("osm_building2.zip", f1.read(), "application/zip"),
                "ref_zip": ("ref_building2.zip", f2.read(), "application/zip"),
            },
            data={
                "job_type": "building",
                "trigger_type": "scheduled",
                "trigger_content": "cron job",
                "target_crs": "EPSG:32643",
                "field_mapping": "{}",
                "debug": "false",
            },
        )
    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]
    status = _wait_run(client, run_id)
    assert status["phase"] == "succeeded", status.get("error")
    assert status["trigger"]["type"] == "scheduled"


def test_v2_task_driven_run_allows_missing_uploads_when_auto_acquire_is_requested(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_create_run(**kwargs):
        captured.update(kwargs)
        return type("CreatedRun", (), {"run_id": "run-auto", "phase": "queued"})()

    monkeypatch.setattr(runs_v2_router.agent_run_service, "create_run", fake_create_run)

    resp = client.post(
        "/api/v2/runs",
        data={
            "job_type": "building",
            "trigger_type": "user_query",
            "trigger_content": "need building data for bbox(29,40,30,41)",
            "spatial_extent": "bbox(29,40,30,41)",
            "target_crs": "EPSG:32643",
            "input_strategy": "task_driven_auto",
            "field_mapping": "{}",
            "debug": "false",
        },
    )

    assert resp.status_code == 200, resp.text
    request = captured["request"]
    assert request.input_strategy == "task_driven_auto"
    assert captured["osm_zip_name"] is None
    assert captured["osm_zip_bytes"] is None
    assert captured["ref_zip_name"] is None
    assert captured["ref_zip_bytes"] is None


def test_v2_run_rejects_unsupported_intent_with_structured_422(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(**_kwargs):
        raise AssertionError("agent_run_service.create_run should not be called for unsupported intent")

    monkeypatch.setattr(runs_v2_router.agent_run_service, "create_run", fail_if_called)

    resp = client.post(
        "/api/v2/runs",
        data={
            "job_type": "building",
            "trigger_type": "user_query",
            "trigger_content": "请融合建筑数据，同时给我某国家GDP数据",
            "input_strategy": "task_driven_auto",
            "field_mapping": "{}",
            "debug": "false",
        },
    )

    assert resp.status_code == 422
    assert resp.json() == {
        "detail": {
            "unsupported_intent": [
                {
                    "code": "OFF_DOMAIN_REQUEST",
                    "message": "Request includes off-domain content that the fusion workflow does not support.",
                    "matched_keyword": "gdp",
                    "job_type": "building",
                }
            ]
        }
    }


def test_v2_run_task_driven_auto_input_integration(
    tmp_path: Path,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = runs_v2_router.agent_run_service
    osm_shp = tmp_path / "resolved_osm.shp"
    ref_shp = tmp_path / "resolved_ref.shp"
    fused_shp = tmp_path / "fused.shp"
    artifact_zip = tmp_path / "artifact.zip"
    for path in [osm_shp, ref_shp, fused_shp]:
        path.write_text("dummy", encoding="utf-8")
    artifact_zip.write_bytes(b"zip")

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

    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: _build_task_driven_plan().model_copy(deep=True))
    def _validated_plan(input_plan: WorkflowPlan) -> WorkflowPlan:
        validated = input_plan.model_copy(deep=True)
        validated.tasks[0].step = 2
        validated.context["grounding_report"] = {
            "grounded": True,
            "grounded_step_count": 1,
            "total_step_count": 1,
            "grounding_score": 1.0,
            "steps": [
                {
                    "step": 1,
                    "algorithm_id": "algo.fusion.building.v1",
                    "input_data_type": "dt.building.bundle",
                    "data_source_id": "catalog.flood.building",
                    "output_data_type": "dt.building.fused",
                    "algorithm_grounded": True,
                    "algorithm_known": True,
                    "data_source_known": True,
                    "output_type_matches_intent": True,
                    "schema_policy_known": True,
                    "pattern_ids": ["wp.flood.building.default"],
                    "issue_codes": [],
                    "evidence_refs": ["plan.task(step=1).algorithm_id"],
                }
            ],
        }
        return validated

    monkeypatch.setattr(service.validator, "validate_and_repair", _validated_plan)
    monkeypatch.setattr(service.input_acquisition_service, "resolve_task_driven_inputs", lambda **_kwargs: resolved)
    monkeypatch.setattr(
        "services.agent_run_service.validate_zip_has_shapefile",
        lambda zip_path, *_args, **_kwargs: osm_shp if Path(zip_path).name.startswith("osm") else ref_shp,
    )
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: fused_shp)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    resp = client.post(
        "/api/v2/runs",
        data={
            "job_type": "building",
            "trigger_type": "user_query",
            "trigger_content": "need building data",
            "spatial_extent": "bbox(0,0,1,1)",
            "target_crs": "EPSG:32643",
            "input_strategy": "task_driven_auto",
            "field_mapping": "{}",
            "debug": "false",
        },
    )

    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]

    status = _wait_run(client, run_id)
    assert status["phase"] == "succeeded", status.get("error")

    inspection_resp = client.get(f"/api/v2/runs/{run_id}/inspection")
    assert inspection_resp.status_code == 200
    inspection = inspection_resp.json()
    created = next(event for event in inspection["audit_events"] if event["kind"] == "run_created")
    assert created["details"]["input_strategy"] == "task_driven_auto"
    resolved_event = next(event for event in inspection["audit_events"] if event["kind"] == "task_inputs_resolved")
    assert resolved_event["details"]["source_mode"] == "downloaded"
    assert resolved_event["details"]["source_id"] == "catalog.flood.building"
    assert resolved_event["details"]["cache_hit"] is False
    assert resolved_event["details"]["version_token"] == "v1"
    plan_grounding = inspection["plan"]["context"]["grounding_report"]
    assert plan_grounding["grounded"] is True
    assert plan_grounding["steps"][0]["step"] == 2
    assert plan_grounding["steps"][0]["evidence_refs"][0] == "plan.task(step=2).algorithm_id"
    assert inspection["kg_path_trace"]["grounding_report"] == plan_grounding
    assert inspection["kg_path_trace"]["chains"][0]["task_step"] == 2
    plan_created = next(event for event in inspection["audit_events"] if event["kind"] == "plan_created")
    assert plan_created["details"]["grounded"] is True
    assert plan_created["details"]["grounding_score"] == 1.0


def test_v2_run_task_driven_auto_nairobi_query_records_aoi_resolution(
    tmp_path: Path,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = runs_v2_router.agent_run_service
    osm_shp = tmp_path / "resolved_osm.shp"
    ref_shp = tmp_path / "resolved_ref.shp"
    fused_shp = tmp_path / "fused.shp"
    artifact_zip = tmp_path / "artifact.zip"
    for path in [osm_shp, ref_shp, fused_shp]:
        path.write_text("dummy", encoding="utf-8")
    artifact_zip.write_bytes(b"zip")

    plan = _build_task_driven_plan()
    plan.trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="fuse building and road data for Nairobi, Kenya",
    )
    plan.tasks[0].input.data_source_id = "catalog.earthquake.building"

    prepared_dir = tmp_path / "prepared"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    resolved = ResolvedRunInputs(
        osm_zip_path=prepared_dir / "osm.zip",
        ref_zip_path=prepared_dir / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.earthquake.building",
        cache_hit=False,
        version_token="ke-v1",
    )
    resolved.osm_zip_path.write_bytes(b"osm")
    resolved.ref_zip_path.write_bytes(b"ref")

    monkeypatch.setattr(service.aoi_resolution_service, "resolve", lambda _query: _resolved_nairobi_aoi())
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service.input_acquisition_service, "resolve_task_driven_inputs", lambda **_kwargs: resolved)
    monkeypatch.setattr(
        "services.agent_run_service.validate_zip_has_shapefile",
        lambda zip_path, *_args, **_kwargs: osm_shp if Path(zip_path).name.startswith("osm") else ref_shp,
    )
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: fused_shp)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    resp = client.post(
        "/api/v2/runs",
        data={
            "job_type": "building",
            "trigger_type": "user_query",
            "trigger_content": "fuse building and road data for Nairobi, Kenya",
            "target_crs": "EPSG:32643",
            "input_strategy": "task_driven_auto",
            "field_mapping": "{}",
            "debug": "false",
        },
    )

    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]

    status = _wait_run(client, run_id)
    assert status["phase"] == "succeeded", status.get("error")

    inspection_resp = client.get(f"/api/v2/runs/{run_id}/inspection")
    assert inspection_resp.status_code == 200
    inspection = inspection_resp.json()
    aoi_event = next(event for event in inspection["audit_events"] if event["kind"] == "aoi_resolved")
    assert aoi_event["details"]["country_code"] == "ke"
    assert aoi_event["details"]["display_name"] == "Nairobi, Nairobi County, Kenya"
    resolved_event = next(event for event in inspection["audit_events"] if event["kind"] == "task_inputs_resolved")
    assert resolved_event["details"]["resolved_aoi"]["country_code"] == "ke"
    assert resolved_event["details"]["source_id"] == "catalog.earthquake.building"


def test_v2_run_task_driven_auto_nairobi_query_uses_auto_target_crs_when_omitted(
    tmp_path: Path,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = runs_v2_router.agent_run_service
    osm_shp = tmp_path / "resolved_osm_auto.shp"
    ref_shp = tmp_path / "resolved_ref_auto.shp"
    fused_shp = tmp_path / "fused_auto.shp"
    artifact_zip = tmp_path / "artifact_auto.zip"
    for path in [osm_shp, ref_shp, fused_shp]:
        path.write_text("dummy", encoding="utf-8")
    artifact_zip.write_bytes(b"zip")

    plan = _build_task_driven_plan()
    plan.trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="fuse building and road data for Nairobi, Kenya",
    )
    plan.tasks[0].input.data_source_id = "catalog.earthquake.building"

    prepared_dir = tmp_path / "prepared_auto"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    resolved = ResolvedRunInputs(
        osm_zip_path=prepared_dir / "osm.zip",
        ref_zip_path=prepared_dir / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.earthquake.building",
        cache_hit=False,
        version_token="ke-v1",
    )
    resolved.osm_zip_path.write_bytes(b"osm")
    resolved.ref_zip_path.write_bytes(b"ref")

    monkeypatch.setattr(service.aoi_resolution_service, "resolve", lambda _query: _resolved_nairobi_aoi())
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service.input_acquisition_service, "resolve_task_driven_inputs", lambda **_kwargs: resolved)
    monkeypatch.setattr(
        "services.agent_run_service.validate_zip_has_shapefile",
        lambda zip_path, *_args, **_kwargs: osm_shp if Path(zip_path).name.startswith("osm") else ref_shp,
    )
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: fused_shp)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    resp = client.post(
        "/api/v2/runs",
        data={
            "job_type": "building",
            "trigger_type": "user_query",
            "trigger_content": "fuse building and road data for Nairobi, Kenya",
            "input_strategy": "task_driven_auto",
            "field_mapping": "{}",
            "debug": "false",
        },
    )

    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]

    status = _wait_run(client, run_id)
    assert status["phase"] == "succeeded", status.get("error")

    inspection_resp = client.get(f"/api/v2/runs/{run_id}/inspection")
    assert inspection_resp.status_code == 200
    inspection = inspection_resp.json()
    assert inspection["run"]["target_crs"] == "EPSG:32737"


def test_v2_compare_runs_exposes_both_inspections(tmp_path: Path, client: TestClient) -> None:
    osm_shp, ref_shp = _build_building_sample(tmp_path)
    osm_zip = _zip_bundle(osm_shp, tmp_path / "osm_compare.zip")
    ref_zip = _zip_bundle(ref_shp, tmp_path / "ref_compare.zip")

    run_ids: list[str] = []
    for trigger_type, trigger_content in [("user_query", "compare left"), ("scheduled", "compare right")]:
        with osm_zip.open("rb") as f1, ref_zip.open("rb") as f2:
            resp = client.post(
                "/api/v2/runs",
                files={
                    "osm_zip": ("osm_compare.zip", f1.read(), "application/zip"),
                    "ref_zip": ("ref_compare.zip", f2.read(), "application/zip"),
                },
                data={
                    "job_type": "building",
                    "trigger_type": trigger_type,
                    "trigger_content": trigger_content,
                    "target_crs": "EPSG:32643",
                    "field_mapping": "{}",
                    "debug": "false",
                },
            )
        assert resp.status_code == 200, resp.text
        run_ids.append(resp.json()["run_id"])

    left_run_id, right_run_id = run_ids
    left_status = _wait_run(client, left_run_id)
    right_status = _wait_run(client, right_run_id)
    assert left_status["phase"] == "succeeded", left_status.get("error")
    assert right_status["phase"] == "succeeded", right_status.get("error")

    compare_resp = client.get(f"/api/v2/runs/{left_run_id}/compare/{right_run_id}")
    assert compare_resp.status_code == 200
    compare = compare_resp.json()
    assert compare["left"]["run"]["run_id"] == left_run_id
    assert compare["right"]["run"]["run_id"] == right_run_id
    assert compare["left"]["artifact"]["available"] is True
    assert compare["right"]["artifact"]["available"] is True
    assert compare["left"]["audit_events"][-1]["kind"] == "run_succeeded"
    assert compare["right"]["audit_events"][-1]["kind"] == "run_succeeded"
