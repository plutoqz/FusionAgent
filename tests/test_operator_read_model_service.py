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

    assert summary["runtime"] == {
        "kg_backend": "memory",
        "llm_provider": "mock",
        "celery_eager": "1",
        "api_port": "8000",
    }
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
