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
from services.agent_run_service import AgentRunService


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


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GEOFUSION_KG_BACKEND", "memory")
    monkeypatch.setenv("GEOFUSION_LLM_PROVIDER", "mock")
    monkeypatch.setenv("GEOFUSION_CELERY_EAGER", "1")

    svc = AgentRunService(base_dir=tmp_path / "runs")
    monkeypatch.setattr(runs_v2_router, "agent_run_service", svc)
    app = create_app()
    return TestClient(app)


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
