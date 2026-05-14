from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from schemas.fusion import JobType


class ScenarioPhase(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    partial = "partial"
    failed = "failed"


class ScenarioRunRequest(BaseModel):
    scenario_name: str = "scenario run"
    trigger_content: str
    disaster_type: Optional[str] = None
    job_types: List[JobType] = Field(default_factory=list)
    spatial_extent: Optional[str] = None
    force_aoi_resolution: bool = False
    output_root: Optional[str] = None
    target_crs: Optional[str] = None
    debug: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ScenarioChildRunSpec(BaseModel):
    job_type: JobType
    trigger_content: str
    disaster_type: Optional[str] = None
    spatial_extent: Optional[str] = None
    force_aoi_resolution: bool = False
    target_crs: Optional[str] = None
    debug: bool = False


class ScenarioRunResponse(BaseModel):
    scenario_id: str
    phase: ScenarioPhase
    output_dir: str
    child_run_ids: List[str] = Field(default_factory=list)


class ScenarioRunListResponse(BaseModel):
    records: List[Dict[str, Any]] = Field(default_factory=list)


class ScenarioRunInspectionResponse(BaseModel):
    summary: Dict[str, Any] = Field(default_factory=dict)
