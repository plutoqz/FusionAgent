from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from api.app import create_app


def _write_frontend_dist(dist_dir: Path) -> Path:
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text(
        "<!doctype html><html><body><div id='root'>frontend shell</div></body></html>",
        encoding="utf-8",
    )
    (assets_dir / "app.js").write_text("console.log('frontend asset');", encoding="utf-8")
    return dist_dir


def test_create_app_allows_default_local_frontend_origin() -> None:
    client = TestClient(create_app())

    response = client.options(
        "/api/v2/settings/llm",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200, response.text
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_create_app_serves_frontend_index_at_root(tmp_path: Path) -> None:
    dist_dir = _write_frontend_dist(tmp_path / "dist")
    client = TestClient(create_app(frontend_dist_dir=dist_dir))

    response = client.get("/")

    assert response.status_code == 200, response.text
    assert "frontend shell" in response.text
    assert response.headers["content-type"].startswith("text/html")


def test_create_app_serves_frontend_assets_and_spa_fallback(tmp_path: Path) -> None:
    dist_dir = _write_frontend_dist(tmp_path / "dist")
    client = TestClient(create_app(frontend_dist_dir=dist_dir))

    asset_response = client.get("/assets/app.js")
    route_response = client.get("/runs/create")

    assert asset_response.status_code == 200, asset_response.text
    assert "frontend asset" in asset_response.text
    assert route_response.status_code == 200, route_response.text
    assert "frontend shell" in route_response.text
