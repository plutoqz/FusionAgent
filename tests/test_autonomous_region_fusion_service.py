from __future__ import annotations

from pathlib import Path

import pytest

from schemas.fusion import JobType
from schemas.task_kind import FULL_DISASTER_TASK_KINDS, TaskKind
from services.autonomous_region_fusion_service import AutonomousRegionFusionService


class _FakeScenarioRunService:
    def __init__(self) -> None:
        self.requests = []

    def create_scenario_run(self, request):
        self.requests.append(request)
        return {"scenario_id": "scenario-test", "phase": "queued"}


def test_autonomous_region_fusion_service_builds_general_five_task_request(tmp_path: Path) -> None:
    scenario_service = _FakeScenarioRunService()
    service = AutonomousRegionFusionService(scenario_run_service=scenario_service)

    result = service.run_autonomous_fusion_region(
        region_name="Generic City, Generic Country",
        output_dir=tmp_path / "region",
        task_kinds=list(FULL_DISASTER_TASK_KINDS),
    )

    assert result["scenario_id"] == "scenario-test"
    assert scenario_service.requests[0].spatial_extent == "Generic City, Generic Country"
    assert scenario_service.requests[0].force_aoi_resolution is True
    assert scenario_service.requests[0].job_types == [
        JobType.building,
        JobType.road,
        JobType.water,
        JobType.poi,
    ]
    assert scenario_service.requests[0].metadata["requested_task_kinds"] == [
        task_kind.value for task_kind in FULL_DISASTER_TASK_KINDS
    ]
    assert scenario_service.requests[0].output_root == str(tmp_path / "region")
    assert scenario_service.requests[0].metadata["degradation_policy"] == "evidence_preserving"
    assert scenario_service.requests[0].metadata["entrypoint"] == "run_autonomous_fusion_region"


def test_autonomous_region_fusion_service_rejects_empty_task_kinds(tmp_path: Path) -> None:
    scenario_service = _FakeScenarioRunService()
    service = AutonomousRegionFusionService(scenario_run_service=scenario_service)

    with pytest.raises(ValueError, match="task_kinds must include at least one task kind"):
        service.run_autonomous_fusion_region(
            region_name="Generic City, Generic Country",
            output_dir=tmp_path / "region",
            task_kinds=[],
        )

    assert scenario_service.requests == []
