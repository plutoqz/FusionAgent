from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from services.research_baselines import BaselineGroup


class ResearchPlanTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: int
    task_kind: Literal["building", "road", "water_polygon", "waterways", "poi"] = Field(
        description="Product task kind. Do not emit internal transform, validation, or workflow steps."
    )
    source_ids: list[str] = Field(default_factory=list)
    algorithm_id: str | None = None
    delivery_state: Literal["planned", "pending", "provisional", "degraded", "gap", "rejected"] = Field(
        description=(
            "Expected product delivery state after this plan executes: planned means unrestricted delivery is "
            "expected; use pending, provisional, degraded, gap, or rejected when an observed constraint prevents "
            "unrestricted delivery. This is not a workflow lifecycle status."
        )
    )
    rationale: str


class ResearchPlanningDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["plan", "reject", "partial", "gap", "degraded", "manual_intervention"] = Field(
        description=(
            "Overall expected product delivery posture. Use plan only when unrestricted delivery is expected; "
            "otherwise choose the applicable constrained posture."
        )
    )
    tasks: list[ResearchPlanTask] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_rejection(self) -> "ResearchPlanningDecision":
        if self.decision == "reject" and any(task.delivery_state != "rejected" for task in self.tasks):
            raise ValueError("rejected decisions cannot contain executable tasks")
        return self


class PilotScheduleItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    case_id: str
    knowledge_condition: Literal[
        "llm_only",
        "llm_capability_kg",
        "llm_full_contract_kg",
    ]
    replicate: int
    input_variant: str = "canonical_v3"

    @property
    def baseline_group(self) -> "BaselineGroup":
        from services.research_baselines import BaselineGroup

        return BaselineGroup(self.knowledge_condition)


class ResearchLLMPilotSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_id: str = "fusionagent.llm-pilot.v1"
    status: Literal["draft_preflight", "pilot_executed"] = "draft_preflight"
    cases: list[str]
    knowledge_conditions: list[str]
    replicates: int
    items: list[PilotScheduleItem]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_schedule(self) -> "ResearchLLMPilotSchedule":
        run_ids = [item.run_id for item in self.items]
        if len(run_ids) != len(set(run_ids)):
            raise ValueError("pilot run_id values must be unique")
        expected = len(self.cases) * len(self.knowledge_conditions) * self.replicates
        if len(self.items) != expected:
            raise ValueError(f"pilot schedule requires {expected} items, got {len(self.items)}")
        return self


def build_research_llm_pilot_schedule() -> ResearchLLMPilotSchedule:
    cases = ["C02", "C03", "C06"]
    conditions = ["llm_only", "llm_capability_kg", "llm_full_contract_kg"]
    items = [
        PilotScheduleItem(
            run_id=f"pilot-{case_id.lower()}-{condition}-r{replicate}",
            case_id=case_id,
            knowledge_condition=condition,
            replicate=replicate,
        )
        for case_id in cases
        for condition in conditions
        for replicate in range(1, 3)
    ]
    return ResearchLLMPilotSchedule(
        cases=cases,
        knowledge_conditions=conditions,
        replicates=2,
        items=items,
        metadata={
            "main_call_count": 18,
            "semantic_repairs": 0,
            "transport_retries": 0,
            "fallback": "forbidden",
        },
    )


def build_research_llm_formal_schedule(*, schedule_seed: int) -> ResearchLLMPilotSchedule:
    cases = [f"C{index:02d}" for index in range(1, 7)]
    conditions = ["llm_only", "llm_capability_kg", "llm_full_contract_kg"]
    items = [
        PilotScheduleItem(
            run_id=f"formal-{case_id.lower()}-{condition}-r1",
            case_id=case_id,
            knowledge_condition=condition,
            replicate=1,
        )
        for case_id in cases
        for condition in conditions
    ]
    random.Random(schedule_seed).shuffle(items)
    return ResearchLLMPilotSchedule(
        protocol_id="fusionagent.planning-formal.v1",
        status="draft_preflight",
        cases=cases,
        knowledge_conditions=conditions,
        replicates=1,
        items=items,
        metadata={
            "schedule_seed": schedule_seed,
            "main_call_count": 18,
            "semantic_repairs": 0,
            "transport_retries": 0,
            "fallback": "forbidden",
            "stability_claim_eligible": False,
        },
    )


def build_research_llm_repeated_schedule(
    *,
    schedule_seed: int,
    replicates: int = 3,
) -> ResearchLLMPilotSchedule:
    if replicates < 2:
        raise ValueError("Repeated formal schedule requires at least two replicates")
    cases = [f"C{index:02d}" for index in range(1, 7)]
    conditions = ["llm_only", "llm_capability_kg", "llm_full_contract_kg"]
    items = [
        PilotScheduleItem(
            run_id=f"formal-v2-{case_id.lower()}-{condition}-r{replicate}",
            case_id=case_id,
            knowledge_condition=condition,
            replicate=replicate,
        )
        for case_id in cases
        for condition in conditions
        for replicate in range(1, replicates + 1)
    ]
    random.Random(schedule_seed).shuffle(items)
    return ResearchLLMPilotSchedule(
        protocol_id="fusionagent.planning-repeated-formal.v2",
        status="draft_preflight",
        cases=cases,
        knowledge_conditions=conditions,
        replicates=replicates,
        items=items,
        metadata={
            "schedule_seed": schedule_seed,
            "main_call_count": len(items),
            "semantic_repairs": 0,
            "transport_retries": 0,
            "fallback": "forbidden",
            "stability_analysis_eligible": True,
            "statistical_significance_claim_eligible": False,
        },
    )
