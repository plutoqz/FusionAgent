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
    order: int = 0


@dataclass
class DataSourceNode:
    source_id: str
    source_name: str
    supported_types: List[str]
    disaster_types: List[str]
    quality_score: float = 0.8
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
class KGContext:
    patterns: List[WorkflowPatternNode]
    algorithms: Dict[str, AlgorithmNode]
    data_sources: List[DataSourceNode] = field(default_factory=list)
    disaster_type: Optional[str] = None
