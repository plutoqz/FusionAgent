from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from schemas.scenario import ScenarioPhase


class ScenarioCheckpointChildSpec(BaseModel):
    job_type: str
    trigger_content: str
    disaster_type: str | None = None
    spatial_extent: str | None = None
    force_aoi_resolution: bool = False
    target_crs: str | None = None
    debug: bool = False
    task_kind: str | None = None
    task_family: str | None = None
    preferred_pattern_id: str | None = None
    output_data_type: str | None = None


class ScenarioCheckpointChildRun(BaseModel):
    run_id: str | None = None
    job_type: str
    task_kind: str | None = None
    task_family: str | None = None
    phase: str
    artifact_path: str | None = None
    error: str | None = None


class ScenarioCheckpoint(BaseModel):
    scenario_id: str
    phase: ScenarioPhase
    children_phase: ScenarioPhase | None = None
    request: dict[str, Any]
    child_specs: list[ScenarioCheckpointChildSpec] = Field(default_factory=list)
    child_runs: list[ScenarioCheckpointChildRun] = Field(default_factory=list)
    started_at: str
    updated_at: str
    resume_count: int = 0
