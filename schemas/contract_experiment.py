from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from schemas.scenario import ScenarioRunRequest


class ExternalSourceDeclaration(BaseModel):
    source_id: str
    product: str
    original_path: str
    runtime_relative_path: str
    original_layer: str | None = None
    preparation: Literal["copy", "vector_extract"] = "copy"
    clip_bbox: list[float] | None = None
    dataset_version: str
    observed_at: str
    freshness_status: str
    semantic_status: str
    expected_sha256: str | None = None
    enabled: bool = True

    @model_validator(mode="after")
    def validate_bbox(self) -> "ExternalSourceDeclaration":
        if self.clip_bbox is not None and len(self.clip_bbox) != 4:
            raise ValueError("clip_bbox must contain four coordinates")
        return self


class ExperimentStageDeclaration(BaseModel):
    stage_id: str
    action: Literal["create", "resume"]
    active_source_ids: list[str] = Field(default_factory=list)
    retry_failed: bool = False
    expected_phases: list[str] = Field(default_factory=list)
    expected_task_order: list[str] = Field(default_factory=list)
    assertions: dict[str, Any] = Field(default_factory=dict)


class ContractExperimentCase(BaseModel):
    case_id: str
    scenario_name: str
    description: str
    request: ScenarioRunRequest
    resource_regime: dict[str, Any] = Field(default_factory=dict)
    stages: list[ExperimentStageDeclaration]
    expected_layer_priority: list[str] = Field(default_factory=list)
    expected_delivery_strategy: str
    expected_gap_types: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_stages(self) -> "ContractExperimentCase":
        if not self.stages:
            raise ValueError("each case requires at least one stage")
        if self.stages[0].action != "create":
            raise ValueError("the first stage must create a scenario run")
        return self


class ContractExperimentManifest(BaseModel):
    schema_version: str
    experiment_id: str
    title: str
    data_boundary: dict[str, Any] = Field(default_factory=dict)
    runtime: dict[str, Any] = Field(default_factory=dict)
    sources: list[ExternalSourceDeclaration]
    cases: list[ContractExperimentCase]
    metric_definition_path: str

    @model_validator(mode="after")
    def validate_source_ids(self) -> "ContractExperimentManifest":
        source_ids = {source.source_id for source in self.sources}
        for case in self.cases:
            for stage in case.stages:
                unknown = sorted(set(stage.active_source_ids) - source_ids)
                if unknown:
                    raise ValueError(f"{case.case_id}/{stage.stage_id} references unknown sources: {unknown}")
        return self
