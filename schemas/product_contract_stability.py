from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


FORMAL_PLANNERS = {
    "fixed",
    "kg_only",
    "llm_only",
    "llm_capability_kg",
    "llm_full_contract_kg",
}
FORMAL_LLM_PLANNERS = {
    "llm_only",
    "llm_capability_kg",
    "llm_full_contract_kg",
}
REQUIRED_AUDIT_FIELDS = {
    "run_id",
    "case_id",
    "planner",
    "repetition_index",
    "input_variant",
    "outcome",
    "planning_model",
    "base_url_host",
    "prompt_hash",
    "context_hash",
    "token_usage",
    "planning_latency_ms",
    "planning_retry_count",
    "code_commit",
    "code_dirty",
    "artifacts",
    "previous_record_hash",
    "record_hash",
}


class StabilityScope(str, Enum):
    DEVELOPMENT = "development"
    FORMAL = "formal"


class RunOutcome(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class LLMStabilityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_model: str = Field(min_length=1)
    temperature: float
    response_format: Literal["json_object"]
    grounding_repair_retries: int = Field(ge=0)
    same_prompt_for_all_llm_baselines: Literal[True]
    same_provider_interface_for_all_llm_baselines: Literal[True]


class StabilityStatisticsProtocol(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_metric: Literal["overall_score"]
    descriptive_statistics: list[
        Literal["count", "mean", "median", "sample_sd", "minimum", "maximum"]
    ]
    validity_statistics: list[
        Literal["success_rate", "failure_rate", "repair_rate", "mean_retry_count"]
    ]
    semantic_stability_statistics: list[
        Literal[
            "strategy_mode_agreement",
            "priority_pairwise_jaccard",
            "initial_delivery_jaccard",
            "background_completion_jaccard",
            "not_delivered_jaccard",
            "planner_gap_jaccard",
            "exact_decision_signature_agreement",
        ]
    ]
    failed_run_policy: Literal[
        "no_imputation_report_success_metrics_with_failure_rate"
    ]
    comparison_unit: Literal["case_planner_repetition"]
    claim_boundary: Literal["formal_runs_required_for_research_claims"]


class StabilityProtocol(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: str = Field(min_length=1)
    status: Literal["frozen_before_formal_runs"]
    frozen_at: str = Field(min_length=1)
    case_ids: list[str] = Field(min_length=1)
    planners: list[str] = Field(min_length=1)
    llm_planners: list[str] = Field(min_length=1)
    formal_repetitions_per_case_planner: int = Field(ge=5)
    input_variants: list[int] = Field(min_length=1)
    variant_assignment: Literal[
        "input_variants[(repetition_index-1)%len(input_variants)]"
    ]
    schedule_seed: str = Field(min_length=1)
    schedule_policy: Literal["deterministic_seeded_shuffle"]
    gold_access_policy: Literal["post_planning_evaluation_only"]
    llm_calling_policy: LLMStabilityPolicy
    statistics: StabilityStatisticsProtocol
    required_audit_fields: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_formal_design(self) -> "StabilityProtocol":
        if len(self.case_ids) != len(set(self.case_ids)):
            raise ValueError("case_ids must be unique.")
        if len(self.planners) != len(set(self.planners)):
            raise ValueError("planners must be unique.")
        if len(self.llm_planners) != len(set(self.llm_planners)):
            raise ValueError("llm_planners must be unique.")
        if set(self.planners) != FORMAL_PLANNERS:
            raise ValueError("Formal stability protocol must contain all five baselines.")
        if set(self.llm_planners) != FORMAL_LLM_PLANNERS:
            raise ValueError("Formal stability protocol must contain all three LLM baselines.")
        if len(self.input_variants) != self.formal_repetitions_per_case_planner:
            raise ValueError(
                "The frozen balanced design requires one distinct input variant per repetition."
            )
        if len(self.input_variants) != len(set(self.input_variants)):
            raise ValueError("input_variants must be unique.")
        if set(self.required_audit_fields) != REQUIRED_AUDIT_FIELDS:
            raise ValueError("required_audit_fields must match the frozen audit record contract.")
        return self


class ArtifactDigest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relative_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)


class SemanticDecisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    strategy_id: str
    priority_precedence_pairs: list[list[str]]
    initial_delivery_layers: list[str]
    background_completion_layers: list[str]
    not_delivered_layers: list[str]
    planner_gap_keys: list[list[str]]


class StabilityAuditRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_type: Literal["product_contract_stability_run"]
    record_version: Literal["1"]
    run_id: str = Field(min_length=1)
    sequence_index: int = Field(ge=0)
    previous_record_hash: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    record_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    protocol_version: str
    protocol_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    scope: StabilityScope
    claim_eligible: bool
    case_id: str
    planner: str
    repetition_index: int = Field(ge=1)
    input_variant: int
    outcome: RunOutcome
    started_at: str
    completed_at: str
    duration_ms: float = Field(ge=0)
    case_input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    gold_label_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_commit: str
    code_dirty: bool
    implementation_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    planning_provider: str | None = None
    planning_model: str | None = None
    base_url_host: str | None = None
    prompt_version: str | None = None
    prompt_hash: str | None = None
    context_hash: str | None = None
    planning_retry_count: int = Field(ge=0)
    planning_latency_ms: float | None = Field(default=None, ge=0)
    token_usage: dict[str, int] | None = None
    metrics: dict[str, float] | None = None
    semantic_decision: SemanticDecisionRecord | None = None
    artifact_dir: str
    artifacts: list[ArtifactDigest]
    failure_type: str | None = None
    failure_reason: str | None = None

    @model_validator(mode="after")
    def validate_outcome_payload(self) -> "StabilityAuditRecord":
        if self.outcome == RunOutcome.SUCCEEDED:
            if self.metrics is None or self.semantic_decision is None:
                raise ValueError("Successful runs require metrics and semantic_decision.")
            if self.failure_type is not None or self.failure_reason is not None:
                raise ValueError("Successful runs must not contain failure fields.")
        else:
            if not self.failure_type or not self.failure_reason:
                raise ValueError("Failed runs require failure_type and failure_reason.")
        return self
