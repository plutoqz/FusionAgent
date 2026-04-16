from __future__ import annotations

from enum import Enum
import math
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from schemas.fusion import JobType


class RunTriggerType(str, Enum):
    user_query = "user_query"
    disaster_event = "disaster_event"
    scheduled = "scheduled"


class RunPhase(str, Enum):
    queued = "queued"
    planning = "planning"
    validating = "validating"
    running = "running"
    healing = "healing"
    succeeded = "succeeded"
    failed = "failed"


class RunInputStrategy(str, Enum):
    uploaded = "uploaded"
    task_driven_auto = "task_driven_auto"


class RunTrigger(BaseModel):
    type: RunTriggerType
    content: str
    disaster_type: Optional[str] = None
    spatial_extent: Optional[str] = None
    temporal_start: Optional[str] = None
    temporal_end: Optional[str] = None


class WorkflowTaskInput(BaseModel):
    data_type_id: str
    data_source_id: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class WorkflowTaskOutput(BaseModel):
    data_type_id: str
    description: Optional[str] = None


class WorkflowTask(BaseModel):
    step: int
    name: str
    description: str
    algorithm_id: str
    input: WorkflowTaskInput
    output: WorkflowTaskOutput
    depends_on: List[int] = Field(default_factory=list)
    is_transform: bool = False
    kg_validated: bool = False
    alternatives: List[str] = Field(default_factory=list)


class ValidationIssue(BaseModel):
    code: str
    message: str
    step: Optional[int] = None


class ValidationReport(BaseModel):
    valid: bool
    inserted_transform_steps: int = 0
    issues: List[ValidationIssue] = Field(default_factory=list)


class WorkflowPlan(BaseModel):
    workflow_id: str
    trigger: RunTrigger
    context: Dict[str, Any] = Field(default_factory=dict)
    tasks: List[WorkflowTask] = Field(default_factory=list)
    expected_output: str
    estimated_time: str = "unknown"
    validation: Optional[ValidationReport] = None


class RepairRecord(BaseModel):
    attempt_no: int
    strategy: str
    step: int
    message: str
    success: bool
    timestamp: str
    reason_code: Optional[str] = None
    from_algorithm: Optional[str] = None
    to_algorithm: Optional[str] = None


class DecisionCandidate(BaseModel):
    candidate_id: str
    score: float
    reason: str
    evidence: Dict[str, Any] = Field(default_factory=dict)


class DecisionRecord(BaseModel):
    decision_type: str
    selected_id: str
    selected_score: float
    rationale: str
    candidates: List[DecisionCandidate] = Field(default_factory=list)
    policy_version: str = "v2"
    evidence_refs: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_selected_candidate_consistency(self) -> "DecisionRecord":
        candidates = self.candidates or []
        if candidates:
            if not any(
                cand.candidate_id == self.selected_id
                and math.isclose(
                    cand.score, self.selected_score, rel_tol=1e-9, abs_tol=1e-9
                )
                for cand in candidates
            ):
                raise ValueError("A candidate must match the selected_id and selected_score.")
        return self


class ArtifactReuseDecision(BaseModel):
    reused: bool
    artifact_id: Optional[str] = None
    freshness_status: str
    rationale: str

    @model_validator(mode="after")
    def ensure_artifact_id_when_reused(self) -> "ArtifactReuseDecision":
        if self.reused and not self.artifact_id:
            raise ValueError("artifact_id is required when reused is True.")
        return self


class RunArtifactMeta(BaseModel):
    filename: str
    path: str
    size_bytes: int


class RunEvent(BaseModel):
    timestamp: str
    kind: str
    phase: RunPhase
    message: str
    plan_revision: int = 0
    progress: int = 0
    attempt_no: int = 0
    current_step: Optional[int] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class RunCreateRequest(BaseModel):
    job_type: JobType
    trigger: RunTrigger
    target_crs: str = "EPSG:32643"
    field_mapping: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    debug: bool = False
    input_strategy: RunInputStrategy = RunInputStrategy.uploaded


class RunCreateResponse(BaseModel):
    run_id: str
    phase: RunPhase


class RunStatus(BaseModel):
    run_id: str
    job_type: JobType
    trigger: RunTrigger
    phase: RunPhase
    progress: int = 0
    target_crs: str
    debug: bool = False
    error: Optional[str] = None
    log_path: Optional[str] = None
    plan_path: Optional[str] = None
    validation_path: Optional[str] = None
    audit_path: Optional[str] = None
    artifact: Optional[RunArtifactMeta] = None
    decision_records: List[DecisionRecord] = Field(default_factory=list)
    artifact_reuse: Optional[ArtifactReuseDecision] = None
    repair_records: List[RepairRecord] = Field(default_factory=list)
    current_step: Optional[int] = None
    attempt_no: int = 0
    healing_summary: Dict[str, Any] = Field(default_factory=dict)
    failure_summary: Optional[str] = None
    plan_revision: int = 0
    event_count: int = 0
    last_event: Optional[RunEvent] = None
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class RunPlanResponse(BaseModel):
    run_id: str
    plan: WorkflowPlan


class RunAuditResponse(BaseModel):
    run_id: str
    events: List[RunEvent] = Field(default_factory=list)


class RunInspectionArtifact(BaseModel):
    available: bool = False
    filename: Optional[str] = None
    path: Optional[str] = None
    size_bytes: Optional[int] = None
    download_path: Optional[str] = None


class RunInspectionResponse(BaseModel):
    run: RunStatus
    plan: Optional[WorkflowPlan] = None
    audit_events: List[RunEvent] = Field(default_factory=list)
    artifact: RunInspectionArtifact = Field(default_factory=RunInspectionArtifact)


class RunComparisonResponse(BaseModel):
    left: RunInspectionResponse
    right: RunInspectionResponse
    differing_decisions: Dict[str, Dict[str, Optional[str]]] = Field(default_factory=dict)


class RuntimeMetadataResponse(BaseModel):
    kg_backend: Optional[str] = None
    llm_provider: Optional[str] = None
    celery_eager: Optional[str] = None
    api_port: Optional[str] = None
