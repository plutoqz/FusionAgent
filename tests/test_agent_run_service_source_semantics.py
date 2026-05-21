from __future__ import annotations

import json
from pathlib import Path

from schemas.agent import RunCreateRequest, RunInputStrategy, RunPhase, RunStatus, RunTrigger, RunTriggerType, WorkflowPlan
from schemas.fusion import JobType
from services.agent_run_service import AgentRunService


def test_agent_run_service_persists_source_semantic_contract(tmp_path: Path) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    run_id = "run-semantic"
    run_dir = service.base_dir / run_id
    for name in ["input", "intermediate", "output", "logs"]:
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(
            type=RunTriggerType.user_query,
            content="building",
            spatial_extent="bbox(0,0,1,1)",
        ),
        input_strategy=RunInputStrategy.task_driven_auto,
    )
    status = RunStatus(
        run_id=run_id,
        job_type=JobType.building,
        trigger=request.trigger,
        phase=RunPhase.running,
        progress=50,
        target_crs="EPSG:4326",
        checkpoint={"stage": "execution", "plan_revision": 0},
        created_at="2026-05-20T00:00:00+00:00",
        updated_at="2026-05-20T00:00:00+00:00",
    )
    service._persist_status(status)
    plan = WorkflowPlan.model_validate(
        {
            "workflow_id": "wf",
            "trigger": request.trigger.model_dump(mode="json"),
            "tasks": [
                {
                    "step": 1,
                    "name": "building",
                    "description": "building",
                    "algorithm_id": "algo.fusion.building.v1",
                    "input": {
                        "data_type_id": "dt.building.bundle",
                        "data_source_id": "catalog.earthquake.building",
                        "parameters": {},
                    },
                    "output": {"data_type_id": "dt.building.fused"},
                }
            ],
            "expected_output": "dt.building.fused",
        }
    )

    class Contract:
        job_type = "building"
        height_policy = {
            "height_output_field": "height_raster",
            "canonical_height_field": "height",
            "positive_only": True,
        }
        parameter_hints = {"source_priority_order": ["MS", "OSM"]}
        validation = {"valid": True, "issues": []}
        component_source_ids = ["raw.microsoft.building", "raw.osm.building"]

        def to_dict(self):
            return {
                "job_type": self.job_type,
                "component_source_ids": self.component_source_ids,
                "height_policy": self.height_policy,
                "parameter_hints": self.parameter_hints,
                "validation": self.validation,
                "sources": {},
            }

    try:
        updated = service._persist_source_semantics(
            run_id=run_id,
            request=request,
            plan=plan,
            contract=Contract(),
        )
    finally:
        service.shutdown()

    contract_path = run_dir / "source_semantic_contract.json"
    assert contract_path.exists()
    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    assert payload["height_policy"]["height_output_field"] == "height_raster"
    assert updated.tasks[0].input.parameters["source_priority_order"] == ["MS", "OSM"]
