from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from schemas.fusion import JobType


@dataclass
class DataTypeNode:
    type_id: str
    theme: str
    geometry_type: str
    description: str


@dataclass
class AlgorithmNode:
    algo_id: str
    algo_name: str
    input_types: List[str]
    output_type: str
    task_type: str
    tool_ref: str
    success_rate: float = 0.9
    accuracy_score: Optional[float] = None
    stability_score: Optional[float] = None
    usage_mode: str = "balanced"
    metadata: Dict[str, Any] = field(default_factory=dict)
    alternatives: List[str] = field(default_factory=list)


@dataclass
class AlgorithmParameterSpec:
    spec_id: str
    algo_id: str
    key: str
    label: str
    param_type: str
    default: Optional[Any] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    unit: Optional[str] = None
    description: str = ""
    required: bool = False
    choices: Optional[List[Any]] = None
    tunable: bool = False
    optimization_tags: List[str] = field(default_factory=list)
    order: int = 0


@dataclass
class OutputSchemaPolicy:
    policy_id: str
    output_type: str
    job_type: JobType
    retention_mode: str
    required_fields: List[str] = field(default_factory=list)
    optional_fields: List[str] = field(default_factory=list)
    rename_hints: Dict[str, str] = field(default_factory=dict)
    compatibility_basis: str = "field_names"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DataSourceNode:
    source_id: str
    source_name: str
    supported_types: List[str]
    disaster_types: List[str]
    quality_score: float = 0.8
    source_kind: str = "catalog"
    quality_tier: str = "standard"
    freshness_category: str = "static"
    freshness_hours: Optional[int] = None
    freshness_score: Optional[float] = None
    supported_job_types: List[str] = field(default_factory=list)
    supported_geometry_types: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PatternStep:
    order: int
    name: str
    algorithm_id: str
    input_data_type: str
    output_data_type: str
    data_source_id: str = "upload.bundle"
    depends_on: List[int] = field(default_factory=list)
    is_optional: bool = False


@dataclass
class WorkflowPatternNode:
    pattern_id: str
    pattern_name: str
    job_type: JobType
    disaster_types: List[str]
    steps: List[PatternStep]
    success_rate: float = 0.8
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class ExecutionFeedback:
    run_id: str
    job_type: JobType
    trigger_type: str
    success: bool
    disaster_type: Optional[str] = None
    pattern_id: Optional[str] = None
    algorithm_id: Optional[str] = None
    selected_data_source: Optional[str] = None
    repaired: bool = False
    repair_count: int = 0
    failure_reason: Optional[str] = None


@dataclass
class DurableLearningRecord:
    record_id: str
    run_id: str
    job_type: JobType
    trigger_type: str
    success: bool
    disaster_type: Optional[str] = None
    pattern_id: Optional[str] = None
    algorithm_id: Optional[str] = None
    selected_data_source: Optional[str] = None
    output_data_type: Optional[str] = None
    target_crs: Optional[str] = None
    repaired: bool = False
    repair_count: int = 0
    failure_reason: Optional[str] = None
    plan_revision: int = 0
    created_at: Optional[str] = None


@dataclass
class DurableLearningSummary:
    entity_kind: str
    entity_id: str
    job_type: JobType
    disaster_type: Optional[str] = None
    total_runs: int = 0
    success_count: int = 0
    failure_count: int = 0
    repaired_count: int = 0
    last_run_at: Optional[str] = None
    last_failure_reason: Optional[str] = None


@dataclass
class KGContext:
    patterns: List[WorkflowPatternNode]
    algorithms: Dict[str, AlgorithmNode]
    parameter_specs: Dict[str, List[AlgorithmParameterSpec]] = field(default_factory=dict)
    data_sources: List[DataSourceNode] = field(default_factory=list)
    output_schema_policies: Dict[str, OutputSchemaPolicy] = field(default_factory=dict)
    durable_learning_summaries: Dict[str, List[DurableLearningSummary]] = field(default_factory=dict)
    disaster_type: Optional[str] = None
