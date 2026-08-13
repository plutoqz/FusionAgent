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
    "source_task_markers": {
        "building": ["building"],
        "road": ["road"],
        "water_polygon": ["water_polygon", "hydrolakes"],
        "waterways": ["waterways", "hydrorivers"],
        "poi": ["poi"],
    },
}

DETERMINISTIC_OUTPUT_PROTOCOL_ID = "fusionagent.deterministic-planning-output.v1"


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
            "observations": case.observations.model_dump(
                mode="json",
                exclude_none=True,
                exclude_unset=True,
            ),
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
            "task_queries": [
                {
                    "task_kind": requested_task,
                    "job_type": _job_type_for_task(requested_task).value,
                    "result": _plain(
                        self.kg_repo.build_context(
                            _job_type_for_task(requested_task),
                            case.scenario.disaster_type,
                        )
                    ),
                }
                for requested_task in case.request_scope.task_kinds
            ],
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
    return _job_type_for_task(first)


def _job_type_for_task(task_kind: str) -> JobType:
    normalized = task_kind.lower()
    return JobType.water if normalized in {"water_polygon", "waterways", "water"} else JobType(normalized)


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

    def run_planning_decision(self, projection: BaselineProjection):
        """Return the versioned public plan using only fields visible in the projection."""
        if projection.group is BaselineGroup.fixed_workflow:
            return _fixed_workflow_decision(projection.payload)
        if projection.group is BaselineGroup.rules_only:
            return _rules_only_decision(projection.payload)
        if projection.group is BaselineGroup.kg_only:
            return _kg_only_decision(projection.payload)
        raise ValueError(f"Deterministic public output does not support {projection.group.value}")


def _fixed_workflow_decision(payload: dict[str, Any]):
    from schemas.research_llm_pilot import ResearchPlanTask, ResearchPlanningDecision

    requested = list(payload["fixed_workflow"].get("task_order", []))
    return ResearchPlanningDecision(
        decision="plan",
        tasks=[
            ResearchPlanTask(
                order=index,
                task_kind=task_kind,
                delivery_state="planned",
                rationale="fixed.workflow.v1 applies a fixed unrestricted delivery posture.",
            )
            for index, task_kind in enumerate(requested, start=1)
        ],
        evidence=[DETERMINISTIC_OUTPUT_PROTOCOL_ID, "fixed.workflow.v1"],
    )


def _rules_only_decision(payload: dict[str, Any]):
    from schemas.research_llm_pilot import ResearchPlanTask, ResearchPlanningDecision

    request = payload["request"]
    facts = payload["observable_facts"]
    observations = facts.get("observations", {})
    ruleset = payload["ruleset"]
    requested = list(request.get("task_kinds", []))
    supported = {str(value).casefold() for value in ruleset.get("supported_disaster_types", [])}
    disaster = str(facts.get("scenario", {}).get("disaster_type") or "").casefold()
    if disaster not in supported or not requested:
        return ResearchPlanningDecision(
            decision="reject",
            tasks=[],
            uncertainties=["The request is outside rules.general.v1 or has no product task."],
            evidence=[DETERMINISTIC_OUTPUT_PROTOCOL_ID, "rules.general.v1:unsupported_disaster_reject"],
        )

    priority = observations.get("mission_priority")
    ordered = [task for task in priority if task in requested] if isinstance(priority, list) else requested
    available = set(observations.get("available_sources", []))
    initial = set(observations.get("initial_sources", []))
    delayed = set(observations.get("delayed_sources", []))
    recovery_source = observations.get("recovery_source")
    markers = ruleset.get("source_task_markers", {})
    tasks = []
    for index, task_kind in enumerate(ordered, start=1):
        task_sources = sorted(
            source_id
            for source_id in available | initial
            if _source_matches_task(source_id, task_kind, markers)
        )
        delayed_sources = sorted(
            source_id for source_id in delayed if _source_matches_task(source_id, task_kind, markers)
        )
        state = "planned"
        rationale = "rules.general.v1 found an observable source for the requested product task."
        if recovery_source and task_kind in requested:
            task_sources = [recovery_source]
            state = "degraded"
            rationale = "rules.general.v1 uses the observed recovery source after a recoverable failure."
        elif not task_sources:
            state = "gap"
            rationale = "rules.general.v1 found no observable source for the requested product task."
        elif delayed_sources:
            state = "provisional"
            rationale = "rules.general.v1 found a current source while another task source is delayed."
        tasks.append(
            ResearchPlanTask(
                order=index,
                task_kind=task_kind,
                source_ids=task_sources,
                delivery_state=state,
                rationale=rationale,
            )
        )
    return ResearchPlanningDecision(
        decision=_decision_for_states([task.delivery_state for task in tasks]),
        tasks=tasks,
        uncertainties=[f"Delayed source: {source_id}" for source_id in sorted(delayed)],
        evidence=[DETERMINISTIC_OUTPUT_PROTOCOL_ID, "rules.general.v1:observable_priority_order"],
    )


def _kg_only_decision(payload: dict[str, Any]):
    from schemas.research_llm_pilot import ResearchPlanTask, ResearchPlanningDecision

    request = payload["request"]
    observations = payload["observable_facts"].get("observations", {})
    query = payload["kg_query"]
    requested = list(request.get("task_kinds", []))
    task_queries = {item["task_kind"]: item for item in query.get("task_queries", [])}
    available = set(observations.get("available_sources", []))
    initial = set(observations.get("initial_sources", []))
    delayed = set(observations.get("delayed_sources", []))
    recovery_source = observations.get("recovery_source")
    tasks = []
    uncertainties = []
    for index, task_kind in enumerate(requested, start=1):
        result = task_queries.get(task_kind, {}).get("result", {})
        patterns = [
            pattern
            for pattern in result.get("patterns", [])
            if pattern.get("job_type") == _job_type_for_task(task_kind).value
        ]
        selected = (
            sorted(
                patterns,
                key=lambda item: (-float(item.get("success_rate", 0.0)), str(item.get("pattern_id", ""))),
            )[0]
            if patterns
            else None
        )
        step = (selected.get("steps") or [{}])[0] if selected else {}
        source_id = step.get("data_source_id")
        algorithm_id = step.get("algorithm_id")
        state = "planned"
        selected_sources = [source_id] if source_id else []
        if recovery_source:
            selected_sources = [recovery_source]
            state = "degraded"
        elif selected is None:
            state = "gap"
        elif available or initial:
            selected_sources, state = _resolve_kg_source_state(
                source_id,
                result.get("data_sources", []),
                available | initial,
                delayed,
            )
        if state != "planned":
            uncertainties.append(f"{task_kind} delivery constrained by observable source state: {state}.")
        tasks.append(
            ResearchPlanTask(
                order=index,
                task_kind=task_kind,
                source_ids=selected_sources,
                algorithm_id=algorithm_id,
                delivery_state=state,
                rationale=(
                    f"KG-only selected {selected.get('pattern_id')} by success_rate_desc then pattern_id_asc."
                    if selected
                    else "KG-only found no matching workflow pattern for the requested task."
                ),
            )
        )
    if not requested:
        return ResearchPlanningDecision(
            decision="reject",
            tasks=[],
            uncertainties=["No requested product task is available for KG planning."],
            evidence=[DETERMINISTIC_OUTPUT_PROTOCOL_ID, str(query.get("knowledge_identity", {}))],
        )
    return ResearchPlanningDecision(
        decision=_decision_for_states([task.delivery_state for task in tasks]),
        tasks=tasks,
        uncertainties=uncertainties,
        evidence=[
            DETERMINISTIC_OUTPUT_PROTOCOL_ID,
            f"kg_release={query.get('knowledge_identity', {}).get('release_id')}",
        ],
    )


def _source_matches_task(source_id: str, task_kind: str, markers: dict[str, list[str]]) -> bool:
    lowered = source_id.casefold()
    return any(marker.casefold() in lowered for marker in markers.get(task_kind, [task_kind]))


def _resolve_kg_source_state(
    source_id: str | None,
    catalog: list[dict[str, Any]],
    available: set[str],
    delayed: set[str],
) -> tuple[list[str], str]:
    if source_id is None:
        return [], "gap"
    source = next((item for item in catalog if item.get("source_id") == source_id), None)
    components = set((source or {}).get("metadata", {}).get("component_source_ids", []))
    if source_id in available:
        return [source_id], "planned"
    available_components = sorted(components & available)
    delayed_components = components & delayed
    if available_components and delayed_components:
        return available_components, "provisional"
    if components and components.issubset(available):
        return sorted(components), "planned"
    return [], "gap"


def _decision_for_states(states: list[str]) -> str:
    if states and all(state == "planned" for state in states):
        return "plan"
    if any(state == "degraded" for state in states):
        return "degraded"
    if any(state in {"gap", "pending", "provisional"} for state in states):
        return "partial"
    return "manual_intervention"
