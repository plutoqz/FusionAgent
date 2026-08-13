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


class ResearchObservedFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_id: str
    task_kind: str
    failure_category: str
    quality_gate_accepted: Literal[False]
    recoverable: bool
    available_source_ids: list[str] = Field(default_factory=list)
    external_uncontrollable_source_ids: list[str] = Field(default_factory=list)
    system_failure_source_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_source_classification(self) -> "ResearchObservedFailure":
        source_groups = {
            "available_source_ids": self.available_source_ids,
            "external_uncontrollable_source_ids": self.external_uncontrollable_source_ids,
            "system_failure_source_ids": self.system_failure_source_ids,
        }
        for field_name, values in source_groups.items():
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} values must be unique")
        classified: dict[str, str] = {}
        for field_name, values in source_groups.items():
            for source_id in values:
                if source_id in classified:
                    raise ValueError(
                        f"source {source_id} is classified by both {classified[source_id]} and {field_name}"
                    )
                classified[source_id] = field_name
        return self


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
    planning_stage: Literal["initial_planning", "recovery_replan"] | None = None
    observed_failure: ResearchObservedFailure | None = None


class ResearchGoldRubric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_consequence: str
    expected_outcome_classes: list[str] = Field(min_length=1)
    unsupported_terms: list[str] = Field(default_factory=list)
    quality_policy_id: str | None = None
    semantic_guard: str | None = None
    allowed_decisions: list[
        Literal["plan", "reject", "partial", "gap", "degraded", "manual_intervention"]
    ] = Field(min_length=1)
    expected_task_kinds: list[str] = Field(default_factory=list)
    expected_gap_task_kinds: list[str] = Field(default_factory=list)
    required_precedence: list[tuple[str, str]] = Field(default_factory=list)
    allowed_delivery_states: dict[
        str,
        list[Literal["planned", "pending", "provisional", "degraded", "gap", "rejected"]],
    ] = Field(default_factory=dict)
    manual_review_items: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scoring_contract(self) -> "ResearchGoldRubric":
        for field_name in (
            "allowed_decisions",
            "expected_task_kinds",
            "expected_gap_task_kinds",
            "required_precedence",
            "manual_review_items",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} values must be unique")
        expected = set(self.expected_task_kinds)
        unknown_gaps = set(self.expected_gap_task_kinds) - expected
        if unknown_gaps:
            raise ValueError(f"expected_gap_task_kinds are not expected tasks: {sorted(unknown_gaps)}")
        unknown_states = set(self.allowed_delivery_states) - expected
        if unknown_states:
            raise ValueError(f"allowed_delivery_states reference unknown tasks: {sorted(unknown_states)}")
        missing_states = expected - set(self.allowed_delivery_states)
        if missing_states:
            raise ValueError(f"expected tasks lack allowed_delivery_states: {sorted(missing_states)}")
        empty_states = sorted(task for task, states in self.allowed_delivery_states.items() if not states)
        if empty_states:
            raise ValueError(f"allowed_delivery_states are empty for tasks: {empty_states}")
        for before, after in self.required_precedence:
            if before not in expected or after not in expected:
                raise ValueError(f"required_precedence references unknown task: {(before, after)}")
        return self


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
        if self.observations.planning_stage == "recovery_replan" and self.observations.observed_failure is None:
            raise ValueError(f"{self.case_id} recovery_replan requires observed_failure")
        if self.observations.observed_failure is not None and self.observations.planning_stage != "recovery_replan":
            raise ValueError(f"{self.case_id} observed_failure requires recovery_replan")
        failure = self.observations.observed_failure
        if failure is not None and failure.task_kind not in self.request_scope.task_kinds:
            raise ValueError(f"{self.case_id} observed_failure task is outside request scope")
        initial_sources = set(self.observations.initial_sources)
        if self.observations.recovery_source and self.observations.recovery_source not in initial_sources:
            raise ValueError(f"{self.case_id} recovery_source is not an initial source")
        if failure is not None:
            classified_sources = (
                set(failure.available_source_ids)
                | set(failure.external_uncontrollable_source_ids)
                | set(failure.system_failure_source_ids)
            )
            unknown_sources = classified_sources - initial_sources
            if unknown_sources:
                raise ValueError(f"{self.case_id} failure classifies unknown sources: {sorted(unknown_sources)}")
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
