from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

import sys

# This repo is not installed as a package in CI/dev by default. Ensure the
# project root is importable when pytest uses importlib import mode.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.planner import WorkflowPlanner
from kg.inmemory_repository import InMemoryKGRepository
from llm.providers.base import LLMProvider
from schemas.agent import RunTrigger, RunTriggerType
from schemas.fusion import JobType
from services.artifact_registry import ArtifactRecord, ArtifactRegistry


class CapturingProvider(LLMProvider):
    def __init__(self) -> None:
        self.last_context: Dict[str, Any] | None = None

    def generate_workflow_plan(self, system_prompt: str, context: Dict[str, Any]) -> Dict[str, Any]:
        self.last_context = context
        candidate = context["retrieval"]["candidate_patterns"][0]
        first_step = candidate["steps"][0]
        return {
            "workflow_id": "wf_reuse_ctx",
            "trigger": context["intent"]["trigger"],
            "context": {"legacy": "llm"},
            "tasks": [
                {
                    "step": 1,
                    "name": first_step["name"],
                    "description": "execute selected workflow",
                    "algorithm_id": first_step["algorithm_id"],
                    "input": {
                        "data_type_id": first_step["input_data_type"],
                        "data_source_id": first_step["data_source_id"],
                        "parameters": {},
                    },
                    "output": {
                        "data_type_id": first_step["output_data_type"],
                        "description": "selected output",
                    },
                    "depends_on": [],
                    "is_transform": False,
                    "kg_validated": False,
                    "alternatives": [],
                }
            ],
            "expected_output": "building fused shapefile",
            "estimated_time": "5m",
        }


def test_planner_context_includes_reusable_artifact_candidates(tmp_path: Path) -> None:
    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    now = datetime(2026, 4, 7, 0, 0, 0, tzinfo=timezone.utc)

    registry.register(
        ArtifactRecord(
            artifact_id="artifact-1",
            artifact_path=str(tmp_path / "artifact-1.zip"),
            job_type="building",
            disaster_type="flood",
            created_at=(now - timedelta(hours=1)).isoformat(),
            output_fields=["geom", "height"],
            bbox=(0.0, 0.0, 10.0, 10.0),
            output_data_type="dt.building.fused",
            target_crs="EPSG:32643",
            meta={"note": "fixture"},
        )
    )

    provider = CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider, artifact_registry=registry)
    trigger = RunTrigger(
        type=RunTriggerType.disaster_event,
        content="flood response building fusion",
        disaster_type="flood",
        spatial_extent="bbox(0,0,1,1)",
    )

    _plan = planner.create_plan(run_id="run-reuse", job_type=JobType.building, trigger=trigger)
    assert provider.last_context is not None
    retrieval = provider.last_context["retrieval"]
    assert "reusable_artifacts" in retrieval
    candidates = retrieval["reusable_artifacts"]
    assert any(item.get("artifact_id") == "artifact-1" for item in candidates)


def test_planner_context_applies_job_type_freshness_policy_and_exposes_reuse_metadata(tmp_path: Path) -> None:
    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    now = datetime(2026, 4, 9, 0, 0, 0, tzinfo=timezone.utc)

    registry.register(
        ArtifactRecord(
            artifact_id="artifact-road-stale",
            artifact_path=str(tmp_path / "artifact-road-stale.zip"),
            job_type="road",
            disaster_type="flood",
            created_at=(now - timedelta(days=2)).isoformat(),
            output_fields=["geometry", "osm_id"],
            bbox=(0.0, 0.0, 10.0, 10.0),
            output_data_type="dt.road.fused",
            target_crs="EPSG:32643",
            meta={"note": "should be filtered by freshness"},
        )
    )
    registry.register(
        ArtifactRecord(
            artifact_id="artifact-road-fresh",
            artifact_path=str(tmp_path / "artifact-road-fresh.zip"),
            job_type="road",
            disaster_type="flood",
            created_at=(now - timedelta(hours=6)).isoformat(),
            output_fields=["geometry", "osm_id"],
            bbox=(0.0, 0.0, 10.0, 10.0),
            output_data_type="dt.road.fused",
            target_crs="EPSG:32643",
            meta={"note": "fresh enough"},
        )
    )

    provider = CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider, artifact_registry=registry)
    trigger = RunTrigger(
        type=RunTriggerType.disaster_event,
        content="road flood response",
        disaster_type="flood",
        spatial_extent="bbox(0,0,1,1)",
    )

    _plan = planner.create_plan(run_id="run-road-reuse", job_type=JobType.road, trigger=trigger)
    assert provider.last_context is not None
    candidates = provider.last_context["retrieval"]["reusable_artifacts"]
    assert [item["artifact_id"] for item in candidates] == ["artifact-road-fresh"]
    assert candidates[0]["output_data_type"] == "dt.road.fused"
    assert candidates[0]["target_crs"] == "EPSG:32643"

