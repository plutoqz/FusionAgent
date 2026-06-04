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
