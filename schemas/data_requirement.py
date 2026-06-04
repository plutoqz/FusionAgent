from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from schemas.task_kind import TaskKind


class CompletenessPolicy(str, Enum):
    required_non_empty = "required_non_empty"
    required_query_with_sparse_allowed = "required_query_with_sparse_allowed"
    optional_reference = "optional_reference"
    optional_when_requirement_absent = "optional_when_requirement_absent"


class SourceCandidate(BaseModel):
    source_id: str
    provider_family: str
    priority: int
    role: Optional[str] = None
    requires_auth: bool = False
    materialization_scope: str = "aoi"
    notes: List[str] = Field(default_factory=list)


class SourceRoleRequirement(BaseModel):
    role_id: str
    required: bool = True
    geometry_types: List[str] = Field(default_factory=list)
    completeness_policy: CompletenessPolicy
    candidates: List[SourceCandidate] = Field(default_factory=list)
    fallback_role_ids: List[str] = Field(default_factory=list)


class DataRequirementPlan(BaseModel):
    task_kind: TaskKind
    task_family: str
    algorithm_id: Optional[str] = None
    output_data_type: Optional[str] = None
    roles: List[SourceRoleRequirement] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
