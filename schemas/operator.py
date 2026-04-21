from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class OperatorRunListResponse(BaseModel):
    records: List[Dict[str, Any]] = Field(default_factory=list)


class OperatorRuntimeSummaryResponse(BaseModel):
    runtime: Dict[str, Any] = Field(default_factory=dict)
    recent_runs: List[Dict[str, Any]] = Field(default_factory=list)
    recent_scenarios: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_gaps: List[str] = Field(default_factory=list)
