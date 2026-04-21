import json
from pathlib import Path

from schemas.fusion import JobType
from schemas.scenario import ScenarioPhase, ScenarioRunRequest
from services.scenario_run_service import ScenarioRunService
from tests.test_scenario_run_service import _FakeAgentRunService


def test_parakou_scenario_generates_kg_trace_workflow_trace_metrics_and_bilingual_reports(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOFUSION_SCENARIO_OUTPUT_ROOT", str(tmp_path))
    service = ScenarioRunService(agent_run_service=_FakeAgentRunService(tmp_path))

    response = service.create_scenario_run(
        ScenarioRunRequest(
            scenario_name="Parakou earthquake",
            trigger_content="fuse building and road data for Parakou, Benin after an earthquake",
            disaster_type="earthquake",
            job_types=[JobType.building, JobType.road],
        )
    )

    scenario_dir = Path(response.output_dir)
    summary = json.loads((scenario_dir / "scenario_summary.json").read_text(encoding="utf-8"))
    assert response.phase in {ScenarioPhase.succeeded, ScenarioPhase.partial}
    assert (scenario_dir / "documents" / "scenario_report.zh.md").exists()
    assert (scenario_dir / "documents" / "scenario_report.en.md").exists()
    assert summary["kg_path_traces"]
    assert summary["workflow_traces"]
    assert summary["evaluation"]["agentic_metrics"]["manual_intervention_count"] == 0
    assert summary["evaluation"]["self_evolution"]["learning_opportunity_recorded"] is True
