from __future__ import annotations

import importlib
from pathlib import Path


def test_recovery_tick_delegates_to_executor(monkeypatch, tmp_path: Path) -> None:
    worker_tasks = importlib.import_module("worker.tasks")
    service_module = importlib.import_module("services.agent_run_service")
    calls: list[dict[str, object]] = []

    class StubService:
        base_dir = tmp_path

        def collect_recoverable_runs(self, stale_after_seconds: int):
            assert stale_after_seconds == 300
            return [{"run_id": "run-1", "recovery_action": "redispatch_full_run"}]

        def resume_run_from_checkpoint(self, run_id: str, recovery_action: str):
            calls.append({"run_id": run_id, "recovery_action": recovery_action})
            return {"run_id": run_id, "phase": "succeeded"}

    monkeypatch.setattr(service_module, "agent_run_service", StubService())
    monkeypatch.setenv("GEOFUSION_RECOVERY_ENABLED", "1")
    monkeypatch.setenv("GEOFUSION_RECOVERY_STALE_SECONDS", "300")

    result = worker_tasks.recovery_tick()

    assert result["enabled"] is True
    assert result["recovered"] == 1
    assert calls == [{"run_id": "run-1", "recovery_action": "redispatch_full_run"}]


def test_recovery_tick_can_be_disabled(monkeypatch) -> None:
    worker_tasks = importlib.import_module("worker.tasks")
    monkeypatch.setenv("GEOFUSION_RECOVERY_ENABLED", "0")

    result = worker_tasks.recovery_tick()

    assert result == {"enabled": False, "reason": "disabled"}


def test_celery_beat_registers_recovery_tick() -> None:
    module = importlib.import_module("worker.celery_app")

    assert "scheduled-run-producer" in module.celery_app.conf["beat_schedule"]
    assert module.celery_app.conf["beat_schedule"]["scheduled-run-producer"]["task"] == "geofusion.scheduled_tick"
    assert "recovery-run-producer" in module.celery_app.conf["beat_schedule"]
    assert module.celery_app.conf["beat_schedule"]["recovery-run-producer"]["task"] == "geofusion.recovery_tick"


def test_recovery_tick_control_state_reports_current_settings(monkeypatch) -> None:
    worker_tasks = importlib.import_module("worker.tasks")
    monkeypatch.setenv("GEOFUSION_RECOVERY_ENABLED", "1")
    monkeypatch.setenv("GEOFUSION_RECOVERY_STALE_SECONDS", "900")
    monkeypatch.setenv("GEOFUSION_RECOVERY_LIMIT", "5")
    monkeypatch.setenv("GEOFUSION_RECOVERY_LEASE_SECONDS", "120")

    control = worker_tasks.recovery_tick_control_state()

    assert control == {
        "task": "geofusion.recovery_tick",
        "enabled": True,
        "stale_after_seconds": 900,
        "limit": 5,
        "lease_seconds": 120,
    }
