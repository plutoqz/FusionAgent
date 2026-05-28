from __future__ import annotations

import pytest

from schemas.fusion import JobType
from schemas.scenario import ScenarioRunRequest
from services.scenario_run_service import ScenarioRunService, classify_scenario_request
from tests.test_scenario_run_service import _FakeAgentRunService


def test_out_of_scope_scenario_request_is_rejected_or_clarified() -> None:
    decision = classify_scenario_request(
        scenario_name="Global traffic telemetry replay",
        trigger_content="simulate live event-feed with full digital twin outputs",
        job_types=[JobType.road],
    )

    assert decision["decision"] in {"reject", "clarify"}
    assert decision["reason_code"] == "UNSUPPORTED_EVENT_FEED_EXPECTATION"


def test_scenario_run_service_rejects_out_of_scope_request_before_creating_child_runs(tmp_path) -> None:
    service = ScenarioRunService(agent_run_service=_FakeAgentRunService(tmp_path))

    with pytest.raises(ValueError, match="UNSUPPORTED_EVENT_FEED_EXPECTATION"):
        service.create_scenario_run(
            ScenarioRunRequest(
                scenario_name="Global traffic telemetry replay",
                trigger_content="simulate live event-feed with full digital twin outputs",
                disaster_type="flood",
                job_types=[JobType.road],
                output_root=str(tmp_path / "scenarios"),
            )
        )


def test_scenario_guard_rejects_trajectory_to_road_execution_request() -> None:
    decision = classify_scenario_request(
        scenario_name="Road trajectory ingestion",
        trigger_content="ingest GPS trajectory and produce road network",
        job_types=[JobType.road],
    )

    assert decision["decision"] == "reject"
    assert decision["reason_code"] == "RESERVATION_ONLY_TRAJECTORY_TO_ROAD"


def test_scenario_guard_clarifies_unbounded_poi_entity_alignment() -> None:
    decision = classify_scenario_request(
        scenario_name="Global POI entity alignment",
        trigger_content="merge all POI businesses with global entity resolution",
        job_types=[JobType.poi],
    )

    assert decision["decision"] == "clarify"
    assert decision["reason_code"] == "unsupported_unbounded_poi_entity_alignment"
