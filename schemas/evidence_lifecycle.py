from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EvidenceArtifactRef(BaseModel):
    role: str
    path: str
    required: bool = True
    exists: bool = False
    retention_class: str = "transient"
    content_sha256: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceBundleManifest(BaseModel):
    bundle_id: str
    bundle_kind: str
    source_of_truth: list[str] = Field(default_factory=list)
    artifacts: list[EvidenceArtifactRef] = Field(default_factory=list)
    related_run_ids: list[str] = Field(default_factory=list)
    related_scenario_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidationSessionManifest(BaseModel):
    session_id: str
    matrix_path: str
    output_root: str
    case_result_paths: list[str] = Field(default_factory=list)
    summary_path: str | None = None
    markdown_summary_path: str | None = None
    created_at: str | None = None
    git_commit: str | None = None
    runtime: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
