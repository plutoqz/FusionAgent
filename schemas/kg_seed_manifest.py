from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class KgSeedManifestMetadata(BaseModel):
    schema_version: str
    generated_from: str = "kg.seed"
    source_modules: list[str] = Field(default_factory=list)
    content_hash: str
    generated_at: str | None = None
    notes: list[str] = Field(default_factory=list)


class KgSeedManifest(BaseModel):
    metadata: KgSeedManifestMetadata
    data_types: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    scenario_profiles: list[dict[str, Any]] = Field(default_factory=list)
    task_bundles: list[dict[str, Any]] = Field(default_factory=list)
    output_requirements: list[dict[str, Any]] = Field(default_factory=list)
    qos_policies: list[dict[str, Any]] = Field(default_factory=list)
    data_needs: list[dict[str, Any]] = Field(default_factory=list)
    repair_strategies: list[dict[str, Any]] = Field(default_factory=list)
    algorithms: list[dict[str, Any]] = Field(default_factory=list)
    parameter_specs: list[dict[str, Any]] = Field(default_factory=list)
    workflow_patterns: list[dict[str, Any]] = Field(default_factory=list)
    data_sources: list[dict[str, Any]] = Field(default_factory=list)
    output_schema_policies: list[dict[str, Any]] = Field(default_factory=list)
