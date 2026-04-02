from __future__ import annotations

from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, Field


class JobType(str, Enum):
    building = "building"
    road = "road"


class JobState(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class FieldMapping(BaseModel):
    # Canonical field -> actual field in uploaded shapefile.
    osm: Dict[str, str] = Field(default_factory=dict)
    ref: Dict[str, str] = Field(default_factory=dict)


class FusionJobRequest(BaseModel):
    target_crs: str = "EPSG:32643"
    field_mapping: FieldMapping = Field(default_factory=FieldMapping)
    debug: bool = False


class FusionJobCreateResponse(BaseModel):
    job_id: str
    status: JobState


class FusionArtifactMeta(BaseModel):
    filename: str
    path: str
    size_bytes: int


class FusionJobStatus(BaseModel):
    job_id: str
    job_type: JobType
    status: JobState
    progress: int = 0
    target_crs: str
    debug: bool = False
    error: Optional[str] = None
    log_path: Optional[str] = None
    artifact: Optional[FusionArtifactMeta] = None
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

