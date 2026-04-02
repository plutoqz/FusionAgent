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
import api.routers.fusion as fusion_router
import api.routers.jobs as jobs_router
from services.job_service import JobService


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


def _build_road_sample(tmp_path: Path) -> tuple[Path, Path]:
    from shapely.geometry import LineString

    osm = geopandas.GeoDataFrame(
        {
            "osm_id": [1, 2],
            "fclass": ["primary", "secondary"],
            "geometry": [
                LineString([(0, 0), (0.03, 0)]),
                LineString([(0, 0.01), (0.03, 0.01)]),
            ],
        },
        crs="EPSG:4326",
    )
    ref = geopandas.GeoDataFrame(
        {
            "FID_1": [1, 2],
            "geometry": [
                LineString([(0, 0), (0.031, 0.0002)]),
                LineString([(0, 0.01), (0.031, 0.0102)]),
            ],
        },
        crs="EPSG:4326",
    )

    osm_shp = tmp_path / "osm_road.shp"
    ref_shp = tmp_path / "ref_road.shp"
    osm.to_file(osm_shp)
    ref.to_file(ref_shp)
    return osm_shp, ref_shp


def _wait_job(client: TestClient, job_id: str, timeout_sec: float = 60.0) -> dict:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        resp = client.get(f"/api/v1/jobs/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        if data["status"] in {"succeeded", "failed"}:
            return data
        time.sleep(0.3)
    raise TimeoutError(f"Job timeout: {job_id}")


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    svc = JobService(base_dir=tmp_path / "jobs", max_workers=1)
    monkeypatch.setattr(fusion_router, "job_service", svc)
    monkeypatch.setattr(jobs_router, "job_service", svc)
    app = create_app()
    cli = TestClient(app)
    try:
        yield cli
    finally:
        svc.shutdown()


def test_building_api_integration(tmp_path: Path, client: TestClient) -> None:
    osm_shp, ref_shp = _build_building_sample(tmp_path)
    osm_zip = _zip_bundle(osm_shp, tmp_path / "osm_building.zip")
    ref_zip = _zip_bundle(ref_shp, tmp_path / "ref_building.zip")

    with osm_zip.open("rb") as f1, ref_zip.open("rb") as f2:
        resp = client.post(
            "/api/v1/fusion/building/jobs",
            files={
                "osm_zip": ("osm_building.zip", f1.read(), "application/zip"),
                "ref_zip": ("ref_building.zip", f2.read(), "application/zip"),
            },
            data={"target_crs": "EPSG:32643", "field_mapping": "{}", "debug": "false"},
        )
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]

    status = _wait_job(client, job_id)
    assert status["status"] == "succeeded", status.get("error")

    artifact_resp = client.get(f"/api/v1/jobs/{job_id}/artifact")
    assert artifact_resp.status_code == 200
    assert artifact_resp.content

    artifact_zip = tmp_path / "building_result.zip"
    artifact_zip.write_bytes(artifact_resp.content)
    extract_dir = tmp_path / "building_result"
    with zipfile.ZipFile(artifact_zip, "r") as zf:
        zf.extractall(extract_dir)
    result_shp = next(extract_dir.glob("*.shp"))
    result = geopandas.read_file(result_shp)
    assert len(result) > 0


def test_road_api_integration(tmp_path: Path, client: TestClient) -> None:
    osm_shp, ref_shp = _build_road_sample(tmp_path)
    osm_zip = _zip_bundle(osm_shp, tmp_path / "osm_road.zip")
    ref_zip = _zip_bundle(ref_shp, tmp_path / "ref_road.zip")

    with osm_zip.open("rb") as f1, ref_zip.open("rb") as f2:
        resp = client.post(
            "/api/v1/fusion/road/jobs",
            files={
                "osm_zip": ("osm_road.zip", f1.read(), "application/zip"),
                "ref_zip": ("ref_road.zip", f2.read(), "application/zip"),
            },
            data={"target_crs": "EPSG:32643", "field_mapping": "{}", "debug": "false"},
        )
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]

    status = _wait_job(client, job_id)
    assert status["status"] == "succeeded", status.get("error")

    artifact_resp = client.get(f"/api/v1/jobs/{job_id}/artifact")
    assert artifact_resp.status_code == 200
    assert artifact_resp.content

    artifact_zip = tmp_path / "road_result.zip"
    artifact_zip.write_bytes(artifact_resp.content)
    extract_dir = tmp_path / "road_result"
    with zipfile.ZipFile(artifact_zip, "r") as zf:
        zf.extractall(extract_dir)
    result_shp = next(extract_dir.glob("*.shp"))
    result = geopandas.read_file(result_shp)
    assert len(result) > 0
