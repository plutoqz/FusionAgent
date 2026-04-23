from __future__ import annotations

from typing import Any

from schemas.agent import WorkflowPlan
from services.plan_grounding_service import build_plan_grounding_report, grounding_report_matches_plan


def build_kg_path_trace(plan: WorkflowPlan) -> dict[str, Any]:
    retrieval = plan.context.get("retrieval", {}) if isinstance(plan.context, dict) else {}
    candidate_patterns = retrieval.get("candidate_patterns", []) if isinstance(retrieval, dict) else []
    data_sources = retrieval.get("data_sources", []) if isinstance(retrieval, dict) else []
    selected_pattern_id = _selected_pattern_id(plan, candidate_patterns)

    chains = []
    for task in sorted(plan.tasks, key=lambda item: item.step):
        nodes = [
            _node("trigger", "trigger", plan.trigger.content, plan.trigger.model_dump(mode="json")),
            _node("workflow_pattern", selected_pattern_id or "unknown_pattern", _pattern_name(candidate_patterns, selected_pattern_id), _find_by_id(candidate_patterns, "pattern_id", selected_pattern_id)),
            _node("task", f"task:{task.step}", task.name, {"step": task.step, "description": task.description}),
            _node("data_source", task.input.data_source_id, _source_name(data_sources, task.input.data_source_id), _find_by_id(data_sources, "source_id", task.input.data_source_id)),
            _node("algorithm", task.algorithm_id, task.algorithm_id, {"algorithm_id": task.algorithm_id}),
            _node("output_data_type", task.output.data_type_id, task.output.data_type_id, task.output.model_dump(mode="json")),
        ]
        chains.append(
            {
                "task_step": task.step,
                "task_name": task.name,
                "nodes": nodes,
                "edges": _edges_for_chain(nodes),
            }
        )

    return {
        "workflow_id": plan.workflow_id,
        "selected_pattern_id": selected_pattern_id,
        "grounding_report": _grounding_report(plan),
        "chains": chains,
    }


def _node(kind: str, node_id: str, label: str | None, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "kind": kind,
        "id": node_id,
        "label": label or node_id,
        "evidence": evidence or {},
    }


def _find_by_id(items: list[Any], key: str, value: str | None) -> dict[str, Any]:
    if value is None:
        return {}
    for item in items:
        if isinstance(item, dict) and item.get(key) == value:
            return dict(item)
    return {}


def _selected_pattern_id(plan: WorkflowPlan, candidate_patterns: list[Any]) -> str | None:
    explicit = plan.context.get("selected_pattern_id") if isinstance(plan.context, dict) else None
    if explicit:
        return str(explicit)
    if candidate_patterns and isinstance(candidate_patterns[0], dict):
        value = candidate_patterns[0].get("pattern_id")
        return str(value) if value else None
    return None


def _pattern_name(candidate_patterns: list[Any], pattern_id: str | None) -> str | None:
    raw = _find_by_id(candidate_patterns, "pattern_id", pattern_id)
    return raw.get("pattern_name") or pattern_id


def _source_name(data_sources: list[Any], source_id: str) -> str:
    raw = _find_by_id(data_sources, "source_id", source_id)
    return str(raw.get("source_name") or source_id)


def _edges_for_chain(nodes: list[dict[str, Any]]) -> list[dict[str, str]]:
    relationships = [
        "selects_pattern",
        "activates_task",
        "uses_data_source",
        "executes_algorithm",
        "produces_output",
    ]
    return [
        {
            "from": nodes[index]["id"],
            "to": nodes[index + 1]["id"],
            "relationship": relationships[index],
        }
        for index in range(min(len(nodes) - 1, len(relationships)))
    ]


def _grounding_report(plan: WorkflowPlan) -> dict[str, Any]:
    if isinstance(plan.context, dict):
        cached_report = plan.context.get("grounding_report")
        if grounding_report_matches_plan(plan, cached_report):
            return dict(cached_report)
    return build_plan_grounding_report(plan)
