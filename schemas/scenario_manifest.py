from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from schemas.fusion import JobType


class ScenarioEvalCase(BaseModel):
    case_id: str
    scenario_name: str
    trigger_content: str
    disaster_type: Optional[str] = None
    job_types: List[JobType] = Field(default_factory=list)
    target_crs: Optional[str] = None
    expected_phase: List[str] = Field(default_factory=lambda: ["succeeded", "partial"])
    tags: List[str] = Field(default_factory=list)
    notes: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ScenarioEvalManifest(BaseModel):
    manifest_id: str
    cases: List[ScenarioEvalCase] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ScenarioHarnessCaseResult(BaseModel):
    case_id: str
    scenario_id: Optional[str] = None
    phase: str = "failed"
    passed: bool = False
    output_dir: Optional[str] = None
    expected_phase: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    response: Dict[str, Any] = Field(default_factory=dict)


class ScenarioHarnessSummary(BaseModel):
    manifest_id: str
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    results: List[ScenarioHarnessCaseResult] = Field(default_factory=list)
    output_root: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
