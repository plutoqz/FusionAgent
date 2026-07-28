from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExperimentExecutionMode(str, Enum):
    PLANNING_ONLY = "planning_only"
    END_TO_END = "end_to_end"


class RuntimeSourceStatus(str, Enum):
    MATERIALIZED = "materialized"
    SKIPPED_KNOWN_UNUSABLE = "skipped_known_unusable"
    FAILED = "failed"


class RuntimeLayerStatus(str, Enum):
    SUCCEEDED = "succeeded"
    SKIPPED = "skipped"
    FAILED = "failed"


class RuntimeSourceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    observed_status: str = Field(min_length=1)
    status: RuntimeSourceStatus
    artifact_path: str | None = None
    vector_path: str | None = None
    feature_count: int | None = None
    coverage_status: str | None = None
    source_mode: str | None = None
    sha256: str | None = None
    error: str | None = None


class RuntimeAlgorithmResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_algorithm_id: str = Field(min_length=1)
    resolved_algorithm_id: str | None = None
    selected_algorithm_executed: bool = False
    execution_kind: str = Field(min_length=1)
    status: str = Field(min_length=1)
    output_path: str | None = None
    output_sha256: str | None = None
    fallback_reason: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class RuntimeWritebackResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(min_length=1)
    artifact_id: str | None = None
    registry_path: str | None = None
    error: str | None = None


class RuntimeLayerExecution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: str = Field(min_length=1)
    task_kind: str = Field(min_length=1)
    delivery_mode: str = Field(min_length=1)
    selected_sources: list[str]
    status: RuntimeLayerStatus
    source_results: list[RuntimeSourceResult] = Field(default_factory=list)
    algorithm_result: RuntimeAlgorithmResult
    quality_report: dict[str, Any] | None = None
    quality_report_path: str | None = None
    writeback: RuntimeWritebackResult
    started_at: str
    completed_at: str


class ProductContractRuntimeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_id: str = Field(min_length=1)
    execution_mode: ExperimentExecutionMode = ExperimentExecutionMode.END_TO_END
    case_id: str = Field(min_length=1)
    planner: str = Field(min_length=1)
    status: str = Field(min_length=1)
    target_crs: str = Field(min_length=1)
    artifact_registry_path: str
    layer_results: list[RuntimeLayerExecution]
    errors: list[str] = Field(default_factory=list)
    started_at: str
    completed_at: str
