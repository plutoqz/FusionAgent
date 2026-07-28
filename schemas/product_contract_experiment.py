from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DeliveryMode(str, Enum):
    FINAL = "final"
    PROVISIONAL = "provisional"
    DEGRADED = "degraded"
    BACKGROUND_PENDING = "background_pending"
    NOT_DELIVERED = "not_delivered"


class GapType(str, Enum):
    DATA_ABSENT = "data_absent"
    SOURCE_UNAVAILABLE = "source_unavailable"
    SOURCE_MISMATCH = "source_mismatch"
    QUALITY_FAILED = "quality_failed"
    CONTRACT_NOT_SATISFIED = "contract_not_satisfied"


class LayerPlanningDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: str = Field(min_length=1)
    selected_algorithm: str = Field(min_length=1)
    selected_sources: list[str]
    delivery_mode: DeliveryMode


class PlannerGapProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: str = Field(min_length=1)
    gap_type: GapType
    source_id: str | None = None
    reason: str = Field(min_length=1)


class SupersessionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: str = Field(min_length=1)
    target_delivery_mode: DeliveryMode = DeliveryMode.FINAL
    trigger_source_ids: list[str] = Field(default_factory=list)
    condition: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_target_mode(self) -> "SupersessionPlan":
        if self.target_delivery_mode in {
            DeliveryMode.BACKGROUND_PENDING,
            DeliveryMode.NOT_DELIVERED,
        }:
            raise ValueError("Supersession target must be a delivered product mode.")
        if len(self.trigger_source_ids) != len(set(self.trigger_source_ids)):
            raise ValueError("Supersession trigger_source_ids must not contain duplicates.")
        return self


class StructuredPlanningDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str = Field(min_length=1)
    priority_tiers: list[list[str]] = Field(min_length=1)
    initial_delivery_layers: list[str]
    background_completion_layers: list[str]
    not_delivered_layers: list[str]
    layer_decisions: list[LayerPlanningDecision] = Field(min_length=1)
    planner_gap_proposal: list[PlannerGapProposal]
    supersession_plan: list[SupersessionPlan]
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_internal_structure(self) -> "StructuredPlanningDecision":
        flattened_tiers = [layer for tier in self.priority_tiers for layer in tier]
        if any(not tier for tier in self.priority_tiers):
            raise ValueError("priority_tiers must not contain an empty tier.")
        if len(flattened_tiers) != len(set(flattened_tiers)):
            raise ValueError("priority_tiers must contain each layer at most once.")

        decision_layers = [item.layer for item in self.layer_decisions]
        if len(decision_layers) != len(set(decision_layers)):
            raise ValueError("layer_decisions must contain each layer at most once.")

        for field_name in (
            "initial_delivery_layers",
            "background_completion_layers",
            "not_delivered_layers",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must not contain duplicates.")

        initial = set(self.initial_delivery_layers)
        not_delivered = set(self.not_delivered_layers)
        if initial & not_delivered:
            raise ValueError(
                "initial_delivery_layers and not_delivered_layers must be disjoint."
            )

        background = set(self.background_completion_layers)
        supersession_layers = {item.layer for item in self.supersession_plan}
        if not supersession_layers <= background:
            raise ValueError(
                "Every supersession_plan layer must appear in background_completion_layers."
            )

        gap_keys = [(item.layer, item.gap_type) for item in self.planner_gap_proposal]
        if len(gap_keys) != len(set(gap_keys)):
            raise ValueError("planner_gap_proposal must not contain duplicate layer/gap pairs.")
        return self


class DeliveryExpectations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_initial: list[str] = Field(default_factory=list)
    allowed_initial: list[str] = Field(default_factory=list)
    required_background: list[str] = Field(default_factory=list)
    allowed_background: list[str] = Field(default_factory=list)
    required_not_delivered: list[str] = Field(default_factory=list)
    allowed_not_delivered: list[str] = Field(default_factory=list)
    required_supersession: list[str] = Field(default_factory=list)
    allowed_delivery_modes: dict[str, list[DeliveryMode]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_required_sets(self) -> "DeliveryExpectations":
        pairs = (
            ("initial", self.required_initial, self.allowed_initial),
            ("background", self.required_background, self.allowed_background),
            (
                "not_delivered",
                self.required_not_delivered,
                self.allowed_not_delivered,
            ),
        )
        for name, required, allowed in pairs:
            if not set(required) <= set(allowed):
                raise ValueError(f"required_{name} must be a subset of allowed_{name}.")
        if any(not modes for modes in self.allowed_delivery_modes.values()):
            raise ValueError("Each allowed_delivery_modes entry must contain at least one mode.")
        return self


class ExpectedGapProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: str = Field(min_length=1)
    gap_type: GapType


class ProductContractGold(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    priority_tiers: list[list[str]] = Field(min_length=1)
    acceptable_strategy_ids: list[str] = Field(min_length=1)
    delivery_expectations: DeliveryExpectations
    expected_gap_proposals: list[ExpectedGapProposal]

    @model_validator(mode="after")
    def validate_gold_structure(self) -> "ProductContractGold":
        flattened_tiers = [layer for tier in self.priority_tiers for layer in tier]
        if any(not tier for tier in self.priority_tiers):
            raise ValueError("Gold priority_tiers must not contain an empty tier.")
        if len(flattened_tiers) != len(set(flattened_tiers)):
            raise ValueError("Gold priority_tiers must contain each layer exactly once.")
        if len(self.acceptable_strategy_ids) != len(set(self.acceptable_strategy_ids)):
            raise ValueError("acceptable_strategy_ids must not contain duplicates.")
        gap_keys = [(item.layer, item.gap_type) for item in self.expected_gap_proposals]
        if len(gap_keys) != len(set(gap_keys)):
            raise ValueError("expected_gap_proposals must not contain duplicates.")
        return self
