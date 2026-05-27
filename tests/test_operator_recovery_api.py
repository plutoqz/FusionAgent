from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from api.app import create_app
import api.routers.runs_v2 as runs_v2_router
from services.agent_run_service import AgentRunService


def test_operator_recovery_endpoint_lists_stale_recoverable_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "run-stale"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": "run-stale",
                "phase": "running",
                "job_type": "building",
                "updated_at": "2026-04-23T00:00:00+00:00",
                "checkpoint": {
                    "stage": "execution",
                    "plan_revision": 1,
                    "current_step": 2,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    service = AgentRunService(base_dir=runs_root)
    monkeypatch.setattr(runs_v2_router, "agent_run_service", service)

    try:
        response = TestClient(create_app()).get(
            "/api/v2/operator/recovery?stale_after_seconds=300"
        )
    finally:
        service.shutdown()

    assert response.status_code == 200
    payload = response.json()
    assert payload["records"][0]["run_id"] == "run-stale"
    assert payload["records"][0]["recovery_action"] == "redispatch_from_execution"


def test_operator_recovery_post_executes_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    class StubExecutor:
        def __init__(self, **_kwargs):
            pass

        def recover_stale_runs(self, *, stale_after_seconds: int, limit: int):
            calls.append({"stale_after_seconds": stale_after_seconds, "limit": limit})
            return {"attempted": 1, "recovered": 1}

    monkeypatch.setattr(runs_v2_router, "RunRecoveryExecutor", StubExecutor)

    response = TestClient(create_app()).post(
        "/api/v2/operator/recovery",
        json={"stale_after_seconds": 300, "limit": 5},
    )

    assert response.status_code == 200
    assert response.json()["result"]["recovered"] == 1
    assert calls == [{"stale_after_seconds": 300, "limit": 5}]


def test_operator_recovery_endpoint_lists_failed_timeout_run_as_recoverable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "run-failed-timeout"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": "run-failed-timeout",
                "phase": "failed",
                "job_type": "building",
                "updated_at": "2026-04-23T00:00:00+00:00",
                "checkpoint": {
                    "stage": "execution",
                    "plan_revision": 1,
                    "current_step": 2,
                },
                "failure_summary": (
                    "download timed out while materializing inputs"
                    " | failure_category=ALGO_TIMEOUT"
                ),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    service = AgentRunService(base_dir=runs_root)
    monkeypatch.setattr(runs_v2_router, "agent_run_service", service)

    try:
        response = TestClient(create_app()).get(
            "/api/v2/operator/recovery?stale_after_seconds=300"
        )
    finally:
        service.shutdown()

    assert response.status_code == 200
    payload = response.json()
    assert payload["records"][0]["run_id"] == "run-failed-timeout"
    assert payload["records"][0]["recovery_action"] == "redispatch_from_execution"
    assert payload["records"][0]["failure_category"] == "ALGO_TIMEOUT"
