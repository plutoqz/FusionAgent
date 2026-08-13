from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResearchScenario(BaseModel):
    model_config = ConfigDict(extra="allow")

    disaster_type: str
    profile_id: str | None = None
    task_bundle_id: str | None = None


class ResearchRequestScope(BaseModel):
    model_config = ConfigDict(extra="allow")

    task_kinds: list[str] = Field(default_factory=list)
    contract_ids: list[str] = Field(default_factory=list)
    resource_regime: str = "unspecified"


class ResearchObservations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available_sources: list[str] = Field(default_factory=list)
    delayed_sources: list[str] = Field(default_factory=list)
    initial_sources: list[str] = Field(default_factory=list)
    recovery_source: str | None = None
    mission_priority: list[str] = Field(default_factory=list)
    semantic_risk_sources: list[str] = Field(default_factory=list)
    building_partial_coverage_allowed: bool | None = None
    catalog_source_id: str | None = None
    source_conflict: dict[str, Any] | None = None


class ResearchGoldRubric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_consequence: str
    expected_outcome_classes: list[str] = Field(min_length=1)
    unsupported_terms: list[str] = Field(default_factory=list)
    quality_policy_id: str | None = None
    semantic_guard: str | None = None


class ResearchKGCrosswalk(BaseModel):
    model_config = ConfigDict(extra="allow")

    crosswalk_status: str
    source_catalog_ids: list[str] = Field(default_factory=list)
    algorithm_ids: list[str] = Field(default_factory=list)
    quality_policy_ids: list[str] = Field(default_factory=list)


class ResearchCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    version: str
    status: str
    mechanism: str
    research_questions: list[str] = Field(default_factory=list)
    scenario: ResearchScenario
    request_scope: ResearchRequestScope
    observations: ResearchObservations = Field(default_factory=ResearchObservations)
    gold_rubric: ResearchGoldRubric
    kg_crosswalk: ResearchKGCrosswalk
    end_to_end: bool = False
    end_to_end_checkpoints: list[str] = Field(default_factory=list)
    excluded_from_positive_quality_average: bool = False

    @model_validator(mode="after")
    def validate_case(self) -> "ResearchCase":
        if self.end_to_end and not self.end_to_end_checkpoints:
            raise ValueError(f"{self.case_id} requires end_to_end_checkpoints")
        if self.scenario.disaster_type.strip() == "":
            raise ValueError(f"{self.case_id} has an empty disaster_type")
        return self

class ResearchCaseManifest(BaseModel):
    model_config = ConfigDict(extra="allow")

    manifest_id: str
    manifest_version: str
    status: Literal["draft_before_formal_freeze", "frozen"]
    kg_release: str
    case_selection_basis: str
    positive_case_ids: list[str] = Field(default_factory=list)
    negative_control_case_ids: list[str] = Field(default_factory=list)
    planning_only_case_ids: list[str] = Field(default_factory=list)
    end_to_end_case_ids: list[str] = Field(default_factory=list)
    cases: list[ResearchCase]

    @model_validator(mode="after")
    def validate_partitions(self) -> "ResearchCaseManifest":
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case_id values must be unique")
        known = set(case_ids)
        for field_name in (
            "positive_case_ids",
            "negative_control_case_ids",
            "planning_only_case_ids",
            "end_to_end_case_ids",
        ):
            unknown = sorted(set(getattr(self, field_name)) - known)
            if unknown:
                raise ValueError(f"{field_name} references unknown cases: {unknown}")
        overlap = set(self.positive_case_ids) & set(self.negative_control_case_ids)
        if overlap:
            raise ValueError(f"positive and negative case sets overlap: {sorted(overlap)}")
        if not set(self.end_to_end_case_ids).issubset(self.planning_only_case_ids):
            raise ValueError("end_to_end_case_ids must be a subset of planning_only_case_ids")
        by_id = {case.case_id: case for case in self.cases}
        for case_id in self.end_to_end_case_ids:
            if not by_id[case_id].end_to_end:
                raise ValueError(f"{case_id} is listed as end-to-end but case.end_to_end is false")
        for case_id in self.negative_control_case_ids:
            if not by_id[case_id].excluded_from_positive_quality_average:
                raise ValueError(f"negative control {case_id} must be excluded from positive averages")
        return self


def load_research_case_manifest(path: str | Path) -> ResearchCaseManifest:
    manifest_path = Path(path)
    payload: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    return ResearchCaseManifest.model_validate(payload)
