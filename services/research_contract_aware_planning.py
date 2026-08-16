from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict

from kg.knowledge_release import semantic_hash
from kg.repository import KGRepository
from schemas.fusion import JobType
from schemas.research_case_manifest import ResearchCase
from services.research_baselines import CanonicalContextFactory


METHOD_B_ID = "fusionagent.task-conditioned-contract-aware-kg-planning.v1"
PRECEDENCE_POLICY = [
    "observable_runtime_facts",
    "source_availability",
    "product_contract",
    "capability_prior",
]

TASK_IDS = {
    "building": "task.building.fusion",
    "road": "task.road.fusion",
    "water_polygon": "task.water.fusion",
    "waterways": "task.waterways.fusion",
    "poi": "task.poi.fusion",
}


class ContractAwareProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method_id: str = METHOD_B_ID
    payload: dict[str, Any]
    allowed_top_level_fields: list[str]
    forbidden_top_level_fields: list[str]
    input_hash: str


def build_contract_aware_projection(
    case: ResearchCase,
    repository: KGRepository,
) -> ContractAwareProjection:
    canonical = CanonicalContextFactory(repository).build(case)
    observations = canonical.observable_facts["observations"]
    requested_tasks = list(case.request_scope.task_kinds)
    scenario_supported, scenario_refs = _scenario_support(
        repository,
        disaster_type=case.scenario.disaster_type,
    )
    task_rows = (
        [
            _compile_task_row(
                task_kind,
                request_contract_ids=set(case.request_scope.contract_ids),
                disaster_type=case.scenario.disaster_type,
                observations=observations,
                repository=repository,
            )
            for task_kind in requested_tasks
        ]
        if scenario_supported
        else []
    )
    ordered_tasks = (
        _ordered_tasks(requested_tasks, observations, task_rows)
        if scenario_supported
        else []
    )
    overall = _overall_decision_constraints(
        scenario_supported=scenario_supported,
        requested_tasks=requested_tasks,
        task_rows=task_rows,
    )
    decision_context = {
        "compiler_id": METHOD_B_ID,
        "constraint_precedence": PRECEDENCE_POLICY,
        "knowledge_identity": repository.get_knowledge_identity(),
        "scenario": {
            "disaster_type": case.scenario.disaster_type,
            "supported": scenario_supported,
            "kg_node_refs": scenario_refs,
        },
        "overall_decision": overall,
        "task_precedence": ordered_tasks,
        "tasks": sorted(task_rows, key=lambda item: ordered_tasks.index(item["task_kind"])),
        "generation_contract": {
            "single_generation": True,
            "retry_repair_fallback": "forbidden",
            "use_only_listed_source_and_algorithm_ids": True,
            "preserve_observation_and_kg_refs_in_evidence": True,
            "unsupported_scenario_requires_reject_with_no_tasks": True,
        },
    }
    payload = {
        "request": canonical.request,
        "observable_facts": canonical.observable_facts,
        "contract_decision_context": decision_context,
        "output_schema": _output_schema(),
    }
    return ContractAwareProjection(
        payload=payload,
        allowed_top_level_fields=list(payload),
        forbidden_top_level_fields=["kg_capability", "kg_contract", "kg_query", "gold_rubric"],
        input_hash=semantic_hash(METHOD_B_ID, payload),
    )


def _compile_task_row(
    task_kind: str,
    *,
    request_contract_ids: set[str],
    disaster_type: str,
    observations: dict[str, Any],
    repository: KGRepository,
) -> dict[str, Any]:
    task_id = TASK_IDS[task_kind]
    job_type = _job_type(task_kind)
    context = _plain(repository.build_context(job_type, disaster_type))
    patterns = [
        item for item in context.get("patterns", []) if _pattern_supports_task(item, task_kind)
    ]
    algorithm_ids = _ordered_unique(
        step["algorithm_id"]
        for pattern in patterns
        for step in pattern.get("steps", [])
        if _step_supports_task(step, task_kind)
    )
    algorithms = context.get("algorithms", {})
    algorithm_refs = [
        {
            "algorithm_id": algorithm_id,
            "input_types": algorithms[algorithm_id].get("input_types", []),
            "output_type": algorithms[algorithm_id].get("output_type"),
            "success_rate": algorithms[algorithm_id].get("success_rate"),
            "claim_state": algorithms[algorithm_id].get("metadata", {}).get("claim_state"),
        }
        for algorithm_id in algorithm_ids
        if algorithm_id in algorithms
    ]
    contracts = [
        item
        for item in context.get("product_contracts", [])
        if item.get("contract_id") in request_contract_ids and task_id in item.get("task_ids", [])
    ]
    output_requirement_ids = _ordered_unique(
        requirement_id
        for contract in contracts
        for requirement_id in contract.get("output_requirement_ids", [])
        if _requirement_supports_task(
            context.get("output_requirements", {}).get(requirement_id),
            task_kind,
        )
    )
    source_nodes = [
        _plain(source)
        for source in repository.list_data_sources()
        if _source_supports_task(_plain(source), task_kind)
        and _source_supports_disaster(_plain(source), disaster_type)
    ]
    source_state = _observed_source_state(task_kind, observations, source_nodes)
    delivery = _delivery_constraints(task_kind, observations, source_state, contracts)
    relevant_source_ids = set(source_state["available"] + source_state["delayed"] + source_state["risk"])
    source_refs = [
        {
            "source_id": source["source_id"],
            "component_source_ids": source.get("metadata", {}).get("component_source_ids", []),
            "supported_types": source.get("supported_types", []),
            "quality_tier": source.get("quality_tier"),
        }
        for source in source_nodes
        if source["source_id"] in relevant_source_ids
        or relevant_source_ids.intersection(source.get("metadata", {}).get("component_source_ids", []))
    ]
    return {
        "task_kind": task_kind,
        "task_id": task_id,
        "observed_source_state": source_state,
        "decision_constraints": delivery,
        "relevant_subgraph": {
            "pattern_refs": [
                {
                    "pattern_id": item["pattern_id"],
                    "success_rate": item.get("success_rate"),
                    "algorithm_ids": [
                        step["algorithm_id"]
                        for step in item.get("steps", [])
                        if _step_supports_task(step, task_kind)
                    ],
                }
                for item in patterns
            ],
            "algorithm_refs": algorithm_refs,
            "source_refs": source_refs,
            "contract_refs": [
                {
                    "contract_id": item["contract_id"],
                    "satisfaction_states": item.get("satisfaction_states", []),
                    "degradation_policy": item.get("degradation_policy", {}),
                    "gap_declaration_policy": item.get("gap_declaration_policy", {}),
                    "delivery_policy": item.get("delivery_policy", {}),
                    "evidence_requirements": item.get("evidence_requirements", []),
                }
                for item in contracts
            ],
            "output_requirement_refs": output_requirement_ids,
        },
        "evidence_refs": {
            "observation_paths": delivery["observation_refs"],
            "kg_node_ids": _ordered_unique(
                [task_id]
                + [item["pattern_id"] for item in patterns]
                + algorithm_ids
                + [item["contract_id"] for item in contracts]
                + output_requirement_ids
            ),
        },
    }


def _scenario_support(repository: KGRepository, *, disaster_type: str) -> tuple[bool, list[str]]:
    profiles = [
        profile
        for profile in repository.get_scenario_profiles(disaster_type)
        if disaster_type in profile.disaster_types
    ]
    refs = [profile.profile_id for profile in profiles]
    return bool(refs), refs


def _observed_source_state(
    task_kind: str,
    observations: dict[str, Any],
    source_nodes: list[dict[str, Any]],
) -> dict[str, list[str]]:
    source_index = {source["source_id"]: source for source in source_nodes}
    planning_stage = observations.get("planning_stage")
    if planning_stage == "recovery_replan" and observations.get("recovery_source"):
        candidates = [str(observations["recovery_source"])]
    else:
        candidates = [
            *observations.get("available_sources", []),
            *observations.get("initial_sources", []),
        ]
    observed_failure = observations.get("observed_failure") or {}
    if planning_stage != "recovery_replan":
        candidates.extend(observed_failure.get("available_source_ids", []))
    delayed = observations.get("delayed_sources", [])
    risk = observations.get("semantic_risk_sources", [])
    return {
        "available": _ordered_unique(
            source_id
            for source_id in candidates
            if _observed_source_supports_task(source_id, task_kind, source_index)
        ),
        "delayed": _ordered_unique(
            source_id
            for source_id in delayed
            if _observed_source_supports_task(source_id, task_kind, source_index)
        ),
        "risk": _ordered_unique(
            source_id
            for source_id in risk
            if _observed_source_supports_task(source_id, task_kind, source_index)
        ),
    }


def _delivery_constraints(
    task_kind: str,
    observations: dict[str, Any],
    source_state: dict[str, list[str]],
    contracts: list[dict[str, Any]],
) -> dict[str, Any]:
    observation_refs: list[str] = []
    reason_codes: list[str] = []
    allowed: list[str]
    preferred: str
    observed_failure = observations.get("observed_failure") or {}
    task_failure = observed_failure.get("task_kind") == task_kind
    partial_key = f"{task_kind}_partial_coverage_allowed"

    if task_failure and observed_failure.get("quality_gate_accepted") is False:
        allowed = ["provisional", "degraded", "gap"]
        preferred = "degraded"
        reason_codes.append("observed_quality_gate_rejection")
        observation_refs.append("observations.observed_failure")
    elif not source_state["available"]:
        allowed = ["gap"]
        preferred = "gap"
        reason_codes.append("no_observed_available_source")
        observation_refs.append("observations.available_sources")
    elif observations.get(partial_key) is False and source_state["delayed"]:
        allowed = ["pending", "gap"]
        preferred = "gap"
        reason_codes.extend(["partial_coverage_forbidden", "required_source_delayed"])
        observation_refs.extend([f"observations.{partial_key}", "observations.delayed_sources"])
    elif source_state["delayed"]:
        allowed = ["provisional"]
        preferred = "provisional"
        reason_codes.append("source_delayed_progressive_delivery")
        observation_refs.append("observations.delayed_sources")
    elif observations.get("source_conflict"):
        allowed = ["planned", "provisional", "degraded"]
        preferred = "degraded"
        reason_codes.append("observed_source_conflict")
        observation_refs.append("observations.source_conflict")
    elif source_state["risk"]:
        allowed = ["provisional"]
        preferred = "provisional"
        reason_codes.append("observed_semantic_source_risk")
        observation_refs.append("observations.semantic_risk_sources")
    else:
        allowed = ["planned"]
        preferred = "planned"
        reason_codes.append("observed_sources_available")
        observation_refs.append("observations.available_sources")

    contract_refs = [item["contract_id"] for item in contracts]
    return {
        "allowed_delivery_states": allowed,
        "preferred_delivery_state": preferred,
        "allowed_source_ids": list(source_state["available"]),
        "delayed_source_ids": list(source_state["delayed"]),
        "risk_source_ids": list(source_state["risk"]),
        "reason_codes": reason_codes,
        "observation_refs": _ordered_unique(observation_refs),
        "contract_refs": contract_refs,
    }


def _ordered_tasks(
    requested_tasks: list[str],
    observations: dict[str, Any],
    task_rows: list[dict[str, Any]],
) -> list[str]:
    mission_priority = observations.get("mission_priority")
    if isinstance(mission_priority, list):
        ordered = [task for task in mission_priority if task in requested_tasks]
        return ordered + [task for task in requested_tasks if task not in ordered]
    state_rank = {"planned": 0, "provisional": 1, "degraded": 2, "pending": 3, "gap": 4}
    row_by_task = {row["task_kind"]: row for row in task_rows}
    return sorted(
        requested_tasks,
        key=lambda task: (
            state_rank[row_by_task[task]["decision_constraints"]["preferred_delivery_state"]],
            requested_tasks.index(task),
        ),
    )


def _overall_decision_constraints(
    *,
    scenario_supported: bool,
    requested_tasks: list[str],
    task_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if not scenario_supported or not requested_tasks:
        return {
            "allowed_decisions": ["reject"],
            "preferred_decision": "reject",
            "reason_codes": ["unsupported_scenario_or_empty_task_scope"],
        }
    states = {
        row["decision_constraints"]["preferred_delivery_state"] for row in task_rows
    }
    if states.intersection({"gap", "pending"}):
        allowed = ["partial", "gap"]
    elif "degraded" in states:
        allowed = ["degraded", "partial", "manual_intervention"]
    elif "provisional" in states:
        allowed = ["partial", "degraded"]
    else:
        allowed = ["plan", "partial", "degraded"]
    return {
        "allowed_decisions": allowed,
        "preferred_decision": allowed[0],
        "reason_codes": ["aggregate_task_delivery_constraints"],
    }


def _observed_source_supports_task(
    source_id: str,
    task_kind: str,
    task_source_index: dict[str, dict[str, Any]],
) -> bool:
    source = task_source_index.get(source_id)
    if source is not None:
        return _source_supports_task(source, task_kind)
    lowered = source_id.casefold()
    if task_kind == "water_polygon":
        return "water_polygon" in lowered or "hydrolakes" in lowered or lowered.endswith(".water")
    if task_kind == "waterways":
        return "waterways" in lowered or "hydrorivers" in lowered
    return task_kind in lowered


def _source_supports_task(source: dict[str, Any], task_kind: str) -> bool:
    supported_types = set(source.get("supported_types", []))
    supported_jobs = set(source.get("supported_job_types", []))
    metadata = source.get("metadata", {})
    theme = metadata.get("theme") or metadata.get("track_b_theme")
    if task_kind == "water_polygon":
        return "dt.water.bundle" in supported_types or theme == "water_polygon"
    if task_kind == "waterways":
        return "dt.waterways.bundle" in supported_types or theme == "waterways"
    return task_kind in supported_jobs or theme == task_kind


def _source_supports_disaster(source: dict[str, Any], disaster_type: str) -> bool:
    supported = {str(value).casefold() for value in source.get("disaster_types", [])}
    return disaster_type.casefold() in supported or "generic" in supported


def _pattern_supports_task(pattern: dict[str, Any], task_kind: str) -> bool:
    return any(_step_supports_task(step, task_kind) for step in pattern.get("steps", []))


def _step_supports_task(step: dict[str, Any], task_kind: str) -> bool:
    output_type = str(step.get("output_data_type") or "")
    algorithm_id = str(step.get("algorithm_id") or "")
    if task_kind == "water_polygon":
        return output_type.startswith("dt.water.") or "water_polygon" in algorithm_id
    if task_kind == "waterways":
        return output_type.startswith("dt.waterways.") or "waterways" in algorithm_id
    return f".{task_kind}." in output_type or f".{task_kind}." in algorithm_id


def _requirement_supports_task(requirement: Any, task_kind: str) -> bool:
    if not isinstance(requirement, dict):
        return False
    output_type = str(requirement.get("output_type") or "")
    if task_kind == "water_polygon":
        return output_type.startswith("dt.water.")
    if task_kind == "waterways":
        return output_type.startswith("dt.waterways.")
    return f".{task_kind}." in output_type


def _job_type(task_kind: str) -> JobType:
    return JobType.water if task_kind in {"water_polygon", "waterways"} else JobType(task_kind)


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return _plain(dataclasses.asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _ordered_unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def _output_schema() -> dict[str, Any]:
    from schemas.research_llm_pilot import ResearchPlanningDecision

    return ResearchPlanningDecision.model_json_schema()
