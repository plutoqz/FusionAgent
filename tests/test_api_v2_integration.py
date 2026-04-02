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
