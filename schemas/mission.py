from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from schemas.fusion import JobType
from schemas.task_kind import TaskKind


class MissionTaskSpec(BaseModel):
    task_kind: TaskKind
    task_family: str
    job_type: JobType
    trigger_content: str
    disaster_type: Optional[str] = None
    spatial_extent: Optional[str] = None
    force_aoi_resolution: bool = False
    target_crs: Optional[str] = None
    debug: bool = False
    preferred_pattern_id: Optional[str] = None
    output_data_type: str


class MissionSpec(BaseModel):
    scope_source: str
    child_tasks: List[MissionTaskSpec] = Field(default_factory=list)
    task_families: List[str] = Field(default_factory=list)
    unsupported_layers: List[str] = Field(default_factory=list)
