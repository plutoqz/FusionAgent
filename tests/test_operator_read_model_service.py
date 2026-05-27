from pathlib import Path

from services.operator_read_model_service import OperatorReadModelService
from services.scenario_registry_service import ScenarioRegistryService


def test_runtime_summary_includes_runtime_runs_and_scenarios(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GEOFUSION_KG_BACKEND", "memory")
    monkeypatch.setenv("GEOFUSION_LLM_PROVIDER", "mock")
    monkeypatch.setenv("GEOFUSION_CELERY_EAGER", "1")
    monkeypatch.setenv("GEOFUSION_API_PORT", "8000")
    monkeypatch.setenv("GEOFUSION_DATABASE_PASSWORD", "secret")

    run_dir = tmp_path / "runs" / "run-a"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        '{"run_id":"run-a","phase":"succeeded","job_type":"building"}',
        encoding="utf-8",
    )
    ScenarioRegistryService(output_root=tmp_path / "scenarios").record(
        {
            "scenario_id": "scenario-a",
            "phase": "succeeded",
            "output_dir": str(tmp_path / "scenarios" / "scenario-a"),
        }
    )

    summary = OperatorReadModelService(
        runs_root=tmp_path / "runs",
        scenario_output_root=tmp_path / "scenarios",
    ).runtime_summary(limit=10)

    assert summary["runtime"]["kg_backend"] == "memory"
    assert summary["runtime"]["llm_provider"] == "mock"
    assert summary["runtime"]["celery_eager"] == "1"
    assert summary["runtime"]["api_port"] == "8000"
    assert "GEOFUSION_DATABASE_PASSWORD" not in summary["runtime"]
    assert summary["recent_runs"][0]["run_id"] == "run-a"
    assert summary["recent_scenarios"][0]["scenario_id"] == "scenario-a"
    assert summary["evidence_gaps"] == []


def test_runtime_summary_reports_evidence_gaps_for_missing_read_models(tmp_path: Path) -> None:
    summary = OperatorReadModelService(
        runs_root=tmp_path / "runs",
        scenario_output_root=tmp_path / "scenarios",
    ).runtime_summary(limit=10)

    assert summary["recent_runs"] == []
    assert summary["recent_scenarios"] == []
    assert "No persisted runs found." in summary["evidence_gaps"]
    assert "No persisted scenario runs found." in summary["evidence_gaps"]


def test_runtime_summary_exposes_worker_controls_and_queue_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GEOFUSION_CELERY_BROKER", "redis://localhost:6379/9")
    monkeypatch.setenv("GEOFUSION_CELERY_BACKEND", "redis://localhost:6379/10")
    monkeypatch.setenv("GEOFUSION_RECOVERY_ENABLED", "1")
    monkeypatch.setenv("GEOFUSION_RECOVERY_STALE_SECONDS", "900")
    monkeypatch.setenv("GEOFUSION_RECOVERY_LIMIT", "5")
    monkeypatch.setenv("GEOFUSION_RECOVERY_LEASE_SECONDS", "120")
    monkeypatch.setenv(
        "GEOFUSION_SCHEDULED_RUNS",
        '[{"job_type":"building","osm_zip_path":"a.zip","ref_zip_path":"b.zip"}]',
    )

    running_dir = tmp_path / "runs" / "run-running"
    queued_dir = tmp_path / "runs" / "run-queued"
    running_dir.mkdir(parents=True)
    queued_dir.mkdir(parents=True)
    (running_dir / "run.json").write_text(
        '{"run_id":"run-running","phase":"running","job_type":"building"}',
        encoding="utf-8",
    )
    (queued_dir / "run.json").write_text(
        '{"run_id":"run-queued","phase":"queued","job_type":"road"}',
        encoding="utf-8",
    )

    summary = OperatorReadModelService(
        runs_root=tmp_path / "runs",
        scenario_output_root=tmp_path / "scenarios",
    ).runtime_summary(limit=10)

    assert summary["runtime"]["worker_controls"]["scheduled_tick"] == {
        "task": "geofusion.scheduled_tick",
        "configured_specs": 1,
        "enabled_specs": 1,
        "beat_entry": "scheduled-run-producer",
        "beat_interval_seconds": 3600.0,
    }
    assert summary["runtime"]["worker_controls"]["recovery_tick"] == {
        "task": "geofusion.recovery_tick",
        "enabled": True,
        "stale_after_seconds": 900,
        "limit": 5,
        "lease_seconds": 120,
        "beat_entry": "recovery-run-producer",
        "beat_interval_seconds": 60.0,
    }
    assert summary["runtime"]["queue_state"]["broker"] == "redis://localhost:6379/9"
    assert summary["runtime"]["queue_state"]["backend"] == "redis://localhost:6379/10"
    assert summary["runtime"]["queue_state"]["active_phase_counts"] == {
        "queued": 1,
        "running": 1,
    }
    assert sorted(record["run_id"] for record in summary["runtime"]["queue_state"]["active_runs"]) == [
        "run-queued",
        "run-running",
    ]
