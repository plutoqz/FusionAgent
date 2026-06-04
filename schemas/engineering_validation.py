from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EngineeringValidationCase(BaseModel):
    case_id: str
    region_group: str
    aoi_class: str
    scenario_name: str
    disaster_type: str
    spatial_extent: str
    default_task_bundle: list[str] = Field(default_factory=list)
    output_format: str = "GPKG"
    purpose: str = ""
    expected_phase: list[str] = Field(default_factory=lambda: ["succeeded", "partial"])
    expected_min_succeeded_children: int = 1
    expected_required_tasks: list[str] = Field(default_factory=list)
    quality_policy_id: str | None = None
    timeout_sec: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EngineeringValidationCaseResult(BaseModel):
    case_id: str
    passed: bool
    phase: str
    scenario_id: str | None = None
    output_dir: str | None = None
    summary_path: str | None = None
    failure_reasons: list[str] = Field(default_factory=list)
    observed: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class EngineeringValidationSummary(BaseModel):
    session_id: str
    matrix_path: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    results: list[EngineeringValidationCaseResult] = Field(default_factory=list)
    output_root: str
    metadata: dict[str, Any] = Field(default_factory=dict)
