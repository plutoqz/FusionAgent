from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kg.knowledge_release import semantic_hash
from kg.repository import KGRepository
from schemas.fusion import JobType
from schemas.research_case_manifest import ResearchCase


class BaselineGroup(str, Enum):
    fixed_workflow = "fixed_workflow"
    rules_only = "rules_only"
    kg_only = "kg_only"
    llm_only = "llm_only"
    llm_capability_kg = "llm_capability_kg"
    llm_full_contract_kg = "llm_full_contract_kg"


RULESET_GENERAL_V1: dict[str, Any] = {
    "ruleset_id": "rules.general.v1",
    "supported_disaster_types": ["earthquake", "flood", "generic", "typhoon"],
    "rule_ids": ["unsupported_disaster_reject", "observable_priority_order", "declare_uncertainty"],
}


class CanonicalResearchContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    request: dict[str, Any]
    observable_facts: dict[str, Any]
    fixed_workflow: dict[str, Any]
    kg_capability: dict[str, Any] = Field(default_factory=dict)
    kg_contract: dict[str, Any] = Field(default_factory=dict)
    kg_query: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaselineProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group: BaselineGroup
    payload: dict[str, Any]
    allowed_top_level_fields: list[str]
    forbidden_top_level_fields: list[str]
    input_hash: str

    @model_validator(mode="after")
    def validate_fields(self) -> "BaselineProjection":
        keys = set(self.payload)
        allowed = set(self.allowed_top_level_fields)
        forbidden = keys & set(self.forbidden_top_level_fields)
        if not keys.issubset(allowed):
            raise ValueError(f"{self.group.value} projection contains undeclared fields: {sorted(keys - allowed)}")
        if forbidden:
            raise ValueError(f"{self.group.value} projection contains forbidden fields: {sorted(forbidden)}")
        return self


class CanonicalContextFactory:
    """Build one canonical case context and project it into the six study groups."""

    def __init__(self, kg_repo: KGRepository) -> None:
        self.kg_repo = kg_repo

    def build(self, case: ResearchCase, *, request_overrides: Mapping[str, Any] | None = None) -> CanonicalResearchContext:
        request = {
            "case_id": case.case_id,
            "disaster_type": case.scenario.disaster_type,
            "task_kinds": list(case.request_scope.task_kinds),
            "contract_ids": list(case.request_scope.contract_ids),
            "resource_regime": case.request_scope.resource_regime,
        }
        if request_overrides:
            request.update(dict(request_overrides))
        observed = {
            "scenario": case.scenario.model_dump(mode="json"),
            "observations": case.observations.model_dump(mode="json"),
            "resource_regime": case.request_scope.resource_regime,
        }
        task_kind = _job_type(case.request_scope.task_kinds)
        kg_context = self.kg_repo.build_context(task_kind, case.scenario.disaster_type)
        kg_plain = _plain(kg_context)
        knowledge_identity = self.kg_repo.get_knowledge_identity()
        capability = {"knowledge_identity": knowledge_identity, **_capability_projection(kg_plain)}
        contract = {"knowledge_identity": knowledge_identity, **_contract_projection(kg_plain)}
        query = {
            "backend": type(self.kg_repo).__name__,
            "mode": "graph_query",
            "knowledge_identity": knowledge_identity,
            "query": {"job_type": task_kind.value, "disaster_type": case.scenario.disaster_type},
            "result": kg_plain,
        }
        return CanonicalResearchContext(
            case_id=case.case_id,
            request=request,
            observable_facts=observed,
            fixed_workflow={
                "workflow_id": "fixed.workflow.v1",
                "task_order": list(case.request_scope.task_kinds),
                "strategy": "fixed_order_fixed_strategy",
            },
            kg_capability=capability,
            kg_contract=contract,
            kg_query=query,
            metadata={"kg_identity": knowledge_identity, "kg_release": knowledge_identity["release_id"]},
        )

    def project(self, context: CanonicalResearchContext, group: BaselineGroup) -> BaselineProjection:
        common = {"request": context.request}
        if group is BaselineGroup.fixed_workflow:
            payload = {
                "request": {"task_kinds": list(context.request.get("task_kinds", []))},
                "fixed_workflow": context.fixed_workflow,
            }
            allowed = ["request", "fixed_workflow"]
            forbidden = ["observable_facts", "kg_capability", "kg_contract", "kg_query", "llm"]
        elif group is BaselineGroup.rules_only:
            payload = {
                **common,
                "observable_facts": context.observable_facts,
                "ruleset": RULESET_GENERAL_V1,
            }
            allowed = ["request", "observable_facts", "ruleset"]
            forbidden = ["kg_capability", "kg_contract", "kg_query", "llm"]
        elif group is BaselineGroup.kg_only:
            payload = {**common, "observable_facts": context.observable_facts, "kg_query": context.kg_query}
            allowed = ["request", "observable_facts", "kg_query"]
            forbidden = ["kg_capability", "kg_contract", "llm"]
        elif group is BaselineGroup.llm_only:
            payload = {**common, "observable_facts": context.observable_facts, "output_schema": _output_schema()}
            allowed = ["request", "observable_facts", "output_schema"]
            forbidden = ["kg_capability", "kg_contract", "kg_query"]
        elif group is BaselineGroup.llm_capability_kg:
            payload = {**common, "observable_facts": context.observable_facts, "kg_capability": context.kg_capability, "output_schema": _output_schema()}
            allowed = ["request", "observable_facts", "kg_capability", "output_schema"]
            forbidden = ["kg_contract", "kg_query"]
        else:
            payload = {**common, "observable_facts": context.observable_facts, "kg_capability": context.kg_capability, "kg_contract": context.kg_contract, "output_schema": _output_schema()}
            allowed = ["request", "observable_facts", "kg_capability", "kg_contract", "output_schema"]
            forbidden = ["kg_query"]
        return BaselineProjection(
            group=group,
            payload=payload,
            allowed_top_level_fields=allowed,
            forbidden_top_level_fields=forbidden,
            input_hash=semantic_hash(group.value, payload),
        )


def _job_type(task_kinds: list[str]) -> JobType:
    first = (task_kinds or ["road"])[0].lower()
    return JobType.water if first in {"water_polygon", "waterways", "water"} else JobType(first)


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return _plain(dataclasses.asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _capability_projection(kg: dict[str, Any]) -> dict[str, Any]:
    return {key: kg.get(key, {}) for key in ("patterns", "algorithms", "data_types", "data_sources", "task_nodes")}


def _contract_projection(kg: dict[str, Any]) -> dict[str, Any]:
    return {key: kg.get(key, {}) for key in ("scenario_profiles", "product_contracts", "task_bundles", "output_requirements", "qos_policies", "data_needs", "repair_strategies", "output_schema_policies")}


def _output_schema() -> dict[str, Any]:
    # Local import avoids a schema import cycle: the pilot schedule also names baseline groups.
    from schemas.research_llm_pilot import ResearchPlanningDecision

    return ResearchPlanningDecision.model_json_schema()


class DeterministicBaselineRunner:
    """Run the three non-LLM groups using only their already-materialized projection."""

    def run(self, projection: BaselineProjection) -> dict[str, Any]:
        if projection.group is BaselineGroup.fixed_workflow:
            workflow = projection.payload["fixed_workflow"]
            return {
                "decision": "execute_fixed_workflow",
                "tasks": list(workflow.get("task_order", [])),
                "selected_pattern_id": workflow.get("workflow_id"),
                "rationale": "fixed_order_fixed_strategy",
            }
        if projection.group is BaselineGroup.rules_only:
            request = projection.payload["request"]
            facts = projection.payload["observable_facts"]
            ruleset = projection.payload["ruleset"]
            scenario = facts.get("scenario", {})
            observations = facts.get("observations", {})
            supported = {str(value).casefold() for value in ruleset.get("supported_disaster_types", [])}
            disaster = str(scenario.get("disaster_type") or "").casefold()
            if disaster not in supported:
                return {"decision": "reject_unsupported_disaster", "tasks": [], "rationale": "rules.general.v1"}
            priority = observations.get("mission_priority")
            requested = list(request.get("task_kinds", []))
            ordered = [task for task in priority if task in requested] if isinstance(priority, list) else requested
            return {"decision": "plan_from_observable_facts", "tasks": ordered, "rationale": "rules.general.v1"}
        if projection.group is BaselineGroup.kg_only:
            query = projection.payload["kg_query"]
            result = query.get("result", {})
            patterns = result.get("patterns", [])
            if not patterns:
                return {"decision": "reject_no_kg_pattern", "tasks": [], "rationale": "kg_query_empty"}
            selected = sorted(
                patterns,
                key=lambda item: (-float(item.get("success_rate", 0.0)), str(item.get("pattern_id", ""))),
            )[0]
            tasks = [str(step.get("name")) for step in selected.get("steps", [])]
            return {
                "decision": "plan_from_kg_query",
                "tasks": tasks,
                "selected_pattern_id": selected.get("pattern_id"),
                "rationale": {"query_mode": query.get("mode"), "sort": ["success_rate_desc", "pattern_id_asc"]},
            }
        raise ValueError(f"DeterministicBaselineRunner does not support {projection.group.value}")
