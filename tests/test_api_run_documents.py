from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
import api.routers.runs_v2 as runs_v2_router


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(runs_v2_router, "agent_run_service", SimpleNamespace(base_dir=tmp_path))
    return TestClient(create_app())


def test_list_run_documents_returns_markdown_assets(tmp_path: Path, client: TestClient) -> None:
    _build_run_documents(tmp_path, run_id="run-docs")

    response = client.get("/api/v2/runs/run-docs/documents")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["run_id"] == "run-docs"
    assert [item["filename"] for item in payload["documents"]] == [
        "run_report.en.md",
        "run_report.zh.md",
    ]
    assert payload["documents"][0]["path"] == "/api/v2/runs/run-docs/documents/run_report.en.md"
    assert payload["documents"][0]["language"] == "en"


def test_get_run_document_returns_markdown_content(tmp_path: Path, client: TestClient) -> None:
    _build_run_documents(tmp_path, run_id="run-read")

    response = client.get("/api/v2/runs/run-read/documents/run_report.zh.md")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["run_id"] == "run-read"
    assert payload["filename"] == "run_report.zh.md"
    assert payload["language"] == "zh"
    assert payload["content"] == "# 中文运行报告\n"


def test_get_run_document_rejects_path_traversal(tmp_path: Path, client: TestClient) -> None:
    _build_run_documents(tmp_path, run_id="run-safe")
    (tmp_path / "run-safe" / "secret.md").write_text("# secret\n", encoding="utf-8")

    response = client.get("/api/v2/runs/run-safe/documents/%2E%2E/secret.md")

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found: ../secret.md"


def test_list_run_documents_rejects_backslash_path_traversal_in_run_id(
    tmp_path: Path, client: TestClient
) -> None:
    leak_target = _build_run_documents(tmp_path.parent, run_id=f"{tmp_path.name}-leak-target")

    response = client.get(f"/api/v2/runs/..%5C{leak_target.name}/documents")

    assert response.status_code == 404
    assert response.json()["detail"] == f"Run not found: ..\\{leak_target.name}"


def _build_run_documents(root: Path, *, run_id: str) -> Path:
    run_dir = root / run_id
    documents_dir = run_dir / "documents"
    documents_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text("{}", encoding="utf-8")
    (documents_dir / "run_report.zh.md").write_text("# 中文运行报告\n", encoding="utf-8")
    (documents_dir / "run_report.en.md").write_text("# English run report\n", encoding="utf-8")
    return run_dir
