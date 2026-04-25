from __future__ import annotations

from typing import Any, Dict, Iterable

from kg.models import AlgorithmNode, DataSourceNode, WorkflowPatternNode
from kg.repository import KGRepository
from schemas.agent import WorkflowPlan
from schemas.kg_graph import KgGraphEdge, KgGraphNode, KgGraphResponse
from services.kg_path_trace_service import build_kg_path_trace


def build_overview_graph(repo: KGRepository) -> KgGraphResponse:
    algorithms = {algorithm.algo_id: algorithm for algorithm in repo.list_algorithms()}
    patterns = {pattern.pattern_id: pattern for pattern in repo.list_workflow_patterns()}
    data_sources = {source.source_id: source for source in repo.list_data_sources()}

    nodes = []
    nodes.extend(_algorithm_nodes(algorithms.values()))
    nodes.extend(_pattern_nodes(patterns.values()))
    nodes.extend(_data_source_nodes(data_sources.values()))

    edge_map: Dict[tuple[str, str, str], KgGraphEdge] = {}
    for pattern in patterns.values():
        for step in pattern.steps:
            if step.algorithm_id in algorithms:
                algo_key = (pattern.pattern_id, step.algorithm_id, "uses_algorithm")
                edge = edge_map.get(algo_key)
                if edge is None:
                    edge = KgGraphEdge(
                        source=pattern.pattern_id,
                        target=step.algorithm_id,
                        relationship="uses_algorithm",
                        meta={"step_orders": []},
                    )
                    edge_map[algo_key] = edge
                _append_unique(edge.meta["step_orders"], step.order)
            if step.data_source_id in data_sources:
                source_key = (pattern.pattern_id, step.data_source_id, "uses_data_source")
                edge = edge_map.get(source_key)
                if edge is None:
                    edge = KgGraphEdge(
                        source=pattern.pattern_id,
                        target=step.data_source_id,
                        relationship="uses_data_source",
                        meta={"step_orders": []},
                    )
                    edge_map[source_key] = edge
                _append_unique(edge.meta["step_orders"], step.order)

    edges = sorted(edge_map.values(), key=lambda item: (item.source, item.relationship, item.target))
    return KgGraphResponse(
        nodes=sorted(nodes, key=lambda item: (item.kind, item.id)),
        edges=edges,
        meta={
            "graph_type": "overview",
            "pattern_count": len(patterns),
            "algorithm_count": len(algorithms),
            "data_source_count": len(data_sources),
            "edge_count": len(edges),
        },
    )


def build_run_path_graph(plan: WorkflowPlan) -> KgGraphResponse:
    trace = build_kg_path_trace(plan)
    node_map: Dict[str, KgGraphNode] = {}
    edge_map: Dict[tuple[str, str, str], KgGraphEdge] = {}

    for chain in trace.get("chains", []):
        task_step = chain.get("task_step")
        task_name = chain.get("task_name")
        for raw_node in chain.get("nodes", []):
            node_id = str(raw_node.get("id"))
            if node_id not in node_map:
                node_map[node_id] = KgGraphNode(
                    id=node_id,
                    kind=str(raw_node.get("kind", "unknown")),
                    label=str(raw_node.get("label") or node_id),
                    meta=_normalize_meta(raw_node.get("evidence")),
                )
                continue
            if raw_node.get("evidence"):
                node_map[node_id].meta.update(_normalize_meta(raw_node.get("evidence")))

        for raw_edge in chain.get("edges", []):
            source = str(raw_edge.get("from"))
            target = str(raw_edge.get("to"))
            relationship = str(raw_edge.get("relationship", "related_to"))
            key = (source, target, relationship)
            edge = edge_map.get(key)
            if edge is None:
                edge = KgGraphEdge(
                    source=source,
                    target=target,
                    relationship=relationship,
                    meta={"task_steps": [], "task_names": []},
                )
                edge_map[key] = edge
            _append_unique(edge.meta["task_steps"], task_step)
            _append_unique(edge.meta["task_names"], task_name)

    edges = sorted(edge_map.values(), key=lambda item: (item.source, item.relationship, item.target))
    return KgGraphResponse(
        nodes=sorted(node_map.values(), key=lambda item: (item.kind, item.id)),
        edges=edges,
        meta={
            "graph_type": "run_path",
            "workflow_id": trace.get("workflow_id"),
            "selected_pattern_id": trace.get("selected_pattern_id"),
            "grounding_report": trace.get("grounding_report", {}),
            "chain_count": len(trace.get("chains", [])),
            "task_count": len(plan.tasks),
        },
    )


def _algorithm_nodes(algorithms: Iterable[AlgorithmNode]) -> list[KgGraphNode]:
    return [
        KgGraphNode(
            id=algorithm.algo_id,
            kind="algorithm",
            label=algorithm.algo_name,
            meta={
                "input_types": list(algorithm.input_types),
                "output_type": algorithm.output_type,
                "task_type": algorithm.task_type,
                "success_rate": algorithm.success_rate,
                "usage_mode": algorithm.usage_mode,
            },
        )
        for algorithm in algorithms
    ]


def _pattern_nodes(patterns: Iterable[WorkflowPatternNode]) -> list[KgGraphNode]:
    return [
        KgGraphNode(
            id=pattern.pattern_id,
            kind="workflow_pattern",
            label=pattern.pattern_name,
            meta={
                "job_type": pattern.job_type.value,
                "disaster_types": list(pattern.disaster_types),
                "step_count": len(pattern.steps),
                "success_rate": pattern.success_rate,
            },
        )
        for pattern in patterns
    ]


def _data_source_nodes(data_sources: Iterable[DataSourceNode]) -> list[KgGraphNode]:
    return [
        KgGraphNode(
            id=source.source_id,
            kind="data_source",
            label=source.source_name,
            meta={
                "supported_types": list(source.supported_types),
                "disaster_types": list(source.disaster_types),
                "quality_score": source.quality_score,
                "source_kind": source.source_kind,
            },
        )
        for source in data_sources
    ]


def _normalize_meta(raw: Any) -> dict[str, Any]:
    return dict(raw) if isinstance(raw, dict) else {}


def _append_unique(values: list[Any], candidate: Any) -> None:
    if candidate is None:
        return
    if candidate not in values:
        values.append(candidate)
