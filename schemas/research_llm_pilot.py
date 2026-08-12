from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from services.research_baselines import BaselineGroup


class ResearchPlanTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: int
    task_kind: str
    source_ids: list[str] = Field(default_factory=list)
    algorithm_id: str | None = None
    delivery_state: Literal["planned", "pending", "provisional", "degraded", "gap", "rejected"]
    rationale: str


class ResearchPlanningDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["plan", "reject", "partial", "gap", "degraded", "manual_intervention"]
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
    input_variant: str = "canonical_v1"

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
