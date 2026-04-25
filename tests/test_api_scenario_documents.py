from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("GEOFUSION_SCENARIO_OUTPUT_ROOT", str(tmp_path))
    app = create_app()
    return TestClient(app)


def test_list_scenario_documents_returns_markdown_assets(tmp_path: Path, client: TestClient) -> None:
    scenario_dir = _build_scenario_documents(tmp_path, scenario_id="scenario-docs")

    response = client.get("/api/v2/scenario-runs/scenario-docs/documents")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["scenario_id"] == "scenario-docs"
    assert [item["filename"] for item in payload["documents"]] == [
        "scenario_report.en.md",
        "scenario_report.zh.md",
    ]
    assert payload["documents"][0]["path"] == "/api/v2/scenario-runs/scenario-docs/documents/scenario_report.en.md"
    assert payload["documents"][0]["size_bytes"] > 0
    assert scenario_dir.exists()


def test_get_scenario_document_returns_markdown_content(tmp_path: Path, client: TestClient) -> None:
    _build_scenario_documents(tmp_path, scenario_id="scenario-read")

    response = client.get("/api/v2/scenario-runs/scenario-read/documents/scenario_report.zh.md")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["scenario_id"] == "scenario-read"
    assert payload["filename"] == "scenario_report.zh.md"
    assert payload["language"] == "zh"
    assert payload["content"] == "# 中文报告\n"


def test_get_scenario_document_rejects_path_traversal(tmp_path: Path, client: TestClient) -> None:
    _build_scenario_documents(tmp_path, scenario_id="scenario-safe")
    (tmp_path / "scenario-safe" / "secret.md").write_text("# secret\n", encoding="utf-8")

    response = client.get("/api/v2/scenario-runs/scenario-safe/documents/%2E%2E/secret.md")

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found: ../secret.md"


def test_get_scenario_document_returns_404_when_missing(tmp_path: Path, client: TestClient) -> None:
    _build_scenario_documents(tmp_path, scenario_id="scenario-missing")

    response = client.get("/api/v2/scenario-runs/scenario-missing/documents/not-found.md")

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found: not-found.md"


def test_list_scenario_documents_rejects_backslash_path_traversal_in_scenario_id(
    tmp_path: Path, client: TestClient
) -> None:
    leak_target = _build_scenario_documents(tmp_path.parent, scenario_id=f"{tmp_path.name}-leak-target")

    response = client.get(f"/api/v2/scenario-runs/..%5C{leak_target.name}/documents")

    assert response.status_code == 404
    assert response.json()["detail"] == f"Scenario run not found: ..\\{leak_target.name}"


def _build_scenario_documents(root: Path, *, scenario_id: str) -> Path:
    scenario_dir = root / scenario_id
    documents_dir = scenario_dir / "documents"
    documents_dir.mkdir(parents=True, exist_ok=True)
    (scenario_dir / "scenario_summary.json").write_text("{}", encoding="utf-8")
    (documents_dir / "scenario_report.zh.md").write_text("# 中文报告\n", encoding="utf-8")
    (documents_dir / "scenario_report.en.md").write_text("# English report\n", encoding="utf-8")
    return scenario_dir
