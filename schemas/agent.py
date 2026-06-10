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
    force_aoi_resolution: bool = False
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
    task_id: Optional[str] = None
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
    enforcement_mode: str = "report"
    rejected: bool = False


class TaskBundleRef(BaseModel):
    bundle_id: str
    requested_tasks: List[str] = Field(default_factory=list)
    requires_disaster_profile: bool = False
    output_requirement_id: Optional[str] = None
    qos_policy_id: Optional[str] = None
    data_need_ids: List[str] = Field(default_factory=list)
    repair_strategy_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OutputRequirementRef(BaseModel):
    requirement_id: str
    output_type: str
    schema_policy_id: str
    required_fields: List[str] = Field(default_factory=list)
    preferred_fields: List[str] = Field(default_factory=list)
    optional_fields: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class QoSPolicyRef(BaseModel):
    policy_id: str
    priority: Dict[str, float] = Field(default_factory=dict)
    max_latency_seconds: Optional[int] = None
    min_success_rate: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DataNeedRef(BaseModel):
    need_id: str
    task_id: str
    data_type_id: str
    direction: str
    required: bool = True
    description: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RepairStrategyRef(BaseModel):
    strategy_id: str
    reason_codes: List[str] = Field(default_factory=list)
    from_algorithm_id: Optional[str] = None
    to_algorithm_id: Optional[str] = None
    applies_to_task_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WorkflowPlan(BaseModel):
    workflow_id: str
    trigger: RunTrigger
    context: Dict[str, Any] = Field(default_factory=dict)
    tasks: List[WorkflowTask] = Field(default_factory=list)
    expected_output: str
    estimated_time: str = "unknown"
    task_bundle: Optional[TaskBundleRef] = None
    output_requirement: Optional[OutputRequirementRef] = None
    qos_policy: Optional[QoSPolicyRef] = None
    data_needs: List[DataNeedRef] = Field(default_factory=list)
    repair_strategies: List[RepairStrategyRef] = Field(default_factory=list)
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
    target_crs: Optional[str] = None
    field_mapping: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    debug: bool = False
    input_strategy: RunInputStrategy = RunInputStrategy.uploaded
    preferred_pattern_id: Optional[str] = None


class RunCreateResponse(BaseModel):
    run_id: str
    phase: RunPhase


class RunPreflightResponse(BaseModel):
    allowed: bool
    unsupported_intent: List[Dict[str, str]] = Field(default_factory=list)
    aoi: Dict[str, Any] = Field(default_factory=dict)
    source_selection: Dict[str, Any] = Field(default_factory=dict)
    component_coverage: Dict[str, Any] = Field(default_factory=dict)
    crs: Dict[str, Any] = Field(default_factory=dict)
    degradation: Dict[str, Any] = Field(default_factory=dict)


class OperatorRecoveryExecuteRequest(BaseModel):
    run_id: Optional[str] = None
    stale_after_seconds: int = 300
    limit: int = 20


class OperatorRecoveryExecuteResponse(BaseModel):
    enabled: bool = True
    result: Dict[str, Any] = Field(default_factory=dict)


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
    planning_telemetry: Dict[str, Any] = Field(default_factory=dict)
    plan_revision: int = 0
    event_count: int = 0
    last_event: Optional[RunEvent] = None
    checkpoint: Dict[str, Any] = Field(default_factory=dict)
    source_semantic_contract_path: Optional[str] = None
    source_semantic_summary: Dict[str, Any] = Field(default_factory=dict)
    document_paths: Dict[str, str] = Field(default_factory=dict)
    created_at: str
    updated_at: Optional[str] = None
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


class RunInspectionDigest(BaseModel):
    current_phase: Optional[str] = None
    failed_step: Optional[str] = None
    root_cause: Optional[str] = None
    recoverability: Optional[str] = None
    next_operator_action: Optional[str] = None


class RunInspectionResponse(BaseModel):
    run: RunStatus
    plan: Optional[WorkflowPlan] = None
    audit_events: List[RunEvent] = Field(default_factory=list)
    artifact: RunInspectionArtifact = Field(default_factory=RunInspectionArtifact)
    kg_path_trace: Dict[str, Any] = Field(default_factory=dict)
    tool_contract_report: Dict[str, Any] = Field(default_factory=dict)
    telemetry_summary: Dict[str, Any] = Field(default_factory=dict)
    recovery_hint: Dict[str, Any] = Field(default_factory=dict)
    large_area_runtime: Dict[str, Any] = Field(default_factory=dict)
    source_semantic_contract: Dict[str, Any] = Field(default_factory=dict)
    report_quality_summary: Dict[str, Any] = Field(default_factory=dict)
    evidence_readiness: Dict[str, Any] = Field(default_factory=dict)
    recovery_worker_evidence: Dict[str, Any] = Field(default_factory=dict)
    digest: RunInspectionDigest = Field(default_factory=RunInspectionDigest)


class RunComparisonResponse(BaseModel):
    left: RunInspectionResponse
    right: RunInspectionResponse
    differing_decisions: Dict[str, Dict[str, Optional[str]]] = Field(default_factory=dict)


class RuntimeMetadataResponse(BaseModel):
    kg_backend: Optional[str] = None
    llm_provider: Optional[str] = None
    celery_eager: Optional[str] = None
    api_port: Optional[str] = None
