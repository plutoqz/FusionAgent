from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
geopandas = pytest.importorskip("geopandas")
pytest.importorskip("shapely")
from fastapi.testclient import TestClient
from shapely.geometry import Polygon

from api.app import create_app
import api.routers.runs_v2 as runs_v2_router
from schemas.agent import RunArtifactMeta, RunPhase, RunStatus, RunTrigger, RunTriggerType
from schemas.fusion import JobType


class _FakeRunService:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._runs: dict[str, RunStatus] = {}
        self._artifacts: dict[str, Path] = {}

    def register_run(self, *, run_id: str, phase: RunPhase, artifact_path: Path | None) -> None:
        artifact = None
        if artifact_path is not None:
            artifact = RunArtifactMeta(
                filename=artifact_path.name,
                path=str(artifact_path),
                size_bytes=artifact_path.stat().st_size,
            )
            self._artifacts[run_id] = artifact_path
        self._runs[run_id] = RunStatus(
            run_id=run_id,
            job_type=JobType.building,
            trigger=RunTrigger(type=RunTriggerType.user_query, content="preview"),
            phase=phase,
            progress=100 if phase == RunPhase.succeeded else 50,
            target_crs="EPSG:4326",
            artifact=artifact,
            created_at="2026-04-25T00:00:00+00:00",
        )

    def get_run(self, run_id: str) -> RunStatus | None:
        return self._runs.get(run_id)

    def get_artifact_path(self, run_id: str) -> Path | None:
        return self._artifacts.get(run_id)


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    service = _FakeRunService(tmp_path / "runs")
    monkeypatch.setattr(runs_v2_router, "agent_run_service", service)
    app = create_app()
    return TestClient(app)


def test_run_preview_metadata_endpoint_returns_preview_summary(tmp_path: Path, client: TestClient) -> None:
    service = runs_v2_router.agent_run_service
    artifact_zip = _build_polygon_zip(tmp_path, count=3)
    service.register_run(run_id="run-preview", phase=RunPhase.succeeded, artifact_path=artifact_zip)

    response = client.get("/api/v2/runs/run-preview/preview")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["run_id"] == "run-preview"
    assert payload["geojson_path"] == "/api/v2/runs/run-preview/preview.geojson"
    assert payload["feature_count"] == 3
    assert payload["preview_feature_count"] == 3
    assert payload["bbox"] == [0.0, 0.0, 2.01, 2.01]
    assert payload["geometry_types"] == ["Polygon"]
    assert "artifact_zip" not in payload
    assert "output_dir" not in payload
    assert "geojson_file_path" not in payload


def test_run_preview_geojson_endpoint_serves_generated_geojson(tmp_path: Path, client: TestClient) -> None:
    service = runs_v2_router.agent_run_service
    artifact_zip = _build_polygon_zip(tmp_path, count=2)
    service.register_run(run_id="run-geojson", phase=RunPhase.succeeded, artifact_path=artifact_zip)

    response = client.get("/api/v2/runs/run-geojson/preview.geojson")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/geo+json")
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    assert len(payload["features"]) == 2


def test_run_preview_geojson_endpoint_serves_cached_preview_file(tmp_path: Path, client: TestClient) -> None:
    service = runs_v2_router.agent_run_service
    artifact_zip = _build_polygon_zip(tmp_path, count=2)
    service.register_run(run_id="run-geojson-cached", phase=RunPhase.succeeded, artifact_path=artifact_zip)

    preview_response = client.get("/api/v2/runs/run-geojson-cached/preview")

    assert preview_response.status_code == 200, preview_response.text
    assert "geojson_file_path" not in preview_response.json()

    response = client.get("/api/v2/runs/run-geojson-cached/preview.geojson")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/geo+json")


def test_run_preview_endpoint_rebuilds_cache_when_artifact_changes(tmp_path: Path, client: TestClient) -> None:
    service = runs_v2_router.agent_run_service
    first_artifact = _build_polygon_zip(tmp_path / "first", count=1)
    service.register_run(run_id="run-preview-refresh", phase=RunPhase.succeeded, artifact_path=first_artifact)

    first_response = client.get("/api/v2/runs/run-preview-refresh/preview")

    assert first_response.status_code == 200, first_response.text
    assert first_response.json()["feature_count"] == 1

    second_artifact = _build_polygon_zip(tmp_path / "second", count=3)
    service.register_run(run_id="run-preview-refresh", phase=RunPhase.succeeded, artifact_path=second_artifact)

    second_response = client.get("/api/v2/runs/run-preview-refresh/preview")

    assert second_response.status_code == 200, second_response.text
    assert second_response.json()["feature_count"] == 3
    assert second_response.json()["preview_feature_count"] == 3


def test_run_preview_geojson_endpoint_rebuilds_when_metadata_points_outside_preview_dir(
    tmp_path: Path, client: TestClient
) -> None:
    service = runs_v2_router.agent_run_service
    artifact_zip = _build_polygon_zip(tmp_path / "artifact", count=2)
    service.register_run(run_id="run-geojson-safe", phase=RunPhase.succeeded, artifact_path=artifact_zip)

    preview_dir = service.base_dir / "run-geojson-safe" / "preview"
    preview_dir.mkdir(parents=True, exist_ok=True)
    external_geojson = tmp_path / "outside.geojson"
    external_geojson.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"source": "tampered"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (preview_dir / "preview_metadata.json").write_text(
        json.dumps(
            {
                "run_id": "run-geojson-safe",
                "geojson_path": "/api/v2/runs/run-geojson-safe/preview.geojson",
                "geojson_file_path": str(external_geojson),
                "feature_count": 1,
                "preview_feature_count": 1,
            }
        ),
        encoding="utf-8",
    )

    response = client.get("/api/v2/runs/run-geojson-safe/preview.geojson")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["features"]) == 2
    assert all(feature["properties"].get("source") != "tampered" for feature in payload["features"])


def test_run_preview_endpoint_treats_invalid_metadata_as_cache_miss(tmp_path: Path, client: TestClient) -> None:
    service = runs_v2_router.agent_run_service
    artifact_zip = _build_polygon_zip(tmp_path / "artifact-invalid", count=2)
    service.register_run(run_id="run-preview-invalid-metadata", phase=RunPhase.succeeded, artifact_path=artifact_zip)

    preview_dir = service.base_dir / "run-preview-invalid-metadata" / "preview"
    preview_dir.mkdir(parents=True, exist_ok=True)
    (preview_dir / "preview_metadata.json").write_text("{not-json", encoding="utf-8")

    response = client.get("/api/v2/runs/run-preview-invalid-metadata/preview")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["feature_count"] == 2
    assert payload["preview_feature_count"] == 2


def test_run_preview_endpoint_rejects_unsucceeded_runs(tmp_path: Path, client: TestClient) -> None:
    service = runs_v2_router.agent_run_service
    artifact_zip = _build_polygon_zip(tmp_path, count=1)
    service.register_run(run_id="run-pending", phase=RunPhase.running, artifact_path=artifact_zip)

    response = client.get("/api/v2/runs/run-pending/preview")

    assert response.status_code == 409
    assert response.json()["detail"] == "Run is not succeeded yet: running"


def _build_polygon_zip(tmp_path: Path, *, count: int) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    frame = geopandas.GeoDataFrame(
        {"fid": list(range(count))},
        geometry=[
            Polygon(
                [
                    (idx, idx),
                    (idx, idx + 0.01),
                    (idx + 0.01, idx + 0.01),
                    (idx + 0.01, idx),
                ]
            )
            for idx in range(count)
        ],
        crs="EPSG:4326",
    )
    shp_path = tmp_path / "sample.shp"
    frame.to_file(shp_path)
    return _zip_bundle(shp_path, tmp_path / "artifact.zip")


def _zip_bundle(shp_path: Path, out_zip: Path) -> Path:
    base = shp_path.with_suffix("")
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in shp_path.parent.glob(f"{base.name}.*"):
            zf.write(file, arcname=file.name)
    return out_zip
