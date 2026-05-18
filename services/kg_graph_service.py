from __future__ import annotations

from typing import Any, Dict, Iterable

from kg.models import (
    AlgorithmNode,
    AlgorithmParameterSpec,
    DataSourceNode,
    DataTypeNode,
    DataNeedNode,
    DurableLearningSummary,
    OutputRequirementNode,
    OutputSchemaPolicy,
    QoSPolicyNode,
    RepairStrategyNode,
    ScenarioProfileNode,
    TaskBundleNode,
    TaskNode,
    WorkflowPatternNode,
)
from kg.repository import KGRepository
from schemas.agent import WorkflowPlan
from schemas.kg_graph import KgGraphEdge, KgGraphNode, KgGraphResponse
from services.kg_path_trace_service import build_kg_path_trace

AGENT_STRUCTURE = (
    {
        "layer_id": "perception",
        "layer_name": "Perception",
        "module_refs": [
            "schemas/agent.py::RunTrigger",
            "services/scenario_trigger_service.py::normalize_trigger_event",
            "services/unsupported_intent_guard.py::classify_unsupported_intent",
        ],
        "ontology_kinds": ["scenario_profile", "task_bundle"],
        "evidence_refs": [
            "tests/test_scenario_trigger_service.py",
            "tests/test_task_bundle_context.py",
        ],
    },
    {
        "layer_id": "reasoning_planning",
        "layer_name": "Reasoning and Planning",
        "module_refs": [
            "agent/retriever.py::PlanningContextBuilder",
            "agent/planner.py::WorkflowPlanner",
        ],
        "ontology_kinds": ["task", "workflow_pattern", "algorithm", "task_bundle"],
        "evidence_refs": [
            "tests/test_planner_context.py",
            "tests/test_kg_path_trace_service.py",
        ],
    },
    {
        "layer_id": "validation_policy",
        "layer_name": "Validation and Policy",
        "module_refs": [
            "agent/validator.py::WorkflowValidator",
            "agent/policy.py::PolicyEngine",
        ],
        "ontology_kinds": ["data_need", "qos_policy", "output_requirement", "output_schema_policy", "parameter_spec"],
        "evidence_refs": [
            "tests/test_workflow_validator.py",
            "tests/test_policy_engine.py",
        ],
    },
    {
        "layer_id": "action_healing",
        "layer_name": "Action and Healing",
        "module_refs": [
            "agent/executor.py::WorkflowExecutor",
            "services/input_acquisition_service.py::InputAcquisitionService",
        ],
        "ontology_kinds": ["repair_strategy", "data_source", "data_type"],
        "evidence_refs": [
            "tests/test_repair_strategy.py",
            "tests/test_repair_audit.py",
        ],
    },
    {
        "layer_id": "audit_evolution",
        "layer_name": "Audit and Evolution",
        "module_refs": [
            "services/agent_run_service.py::AgentRunService",
            "services/kg_path_trace_service.py::build_kg_path_trace",
        ],
        "ontology_kinds": ["workflow_pattern", "algorithm", "data_source", "durable_learning_summary"],
        "evidence_refs": [
            "tests/test_agent_run_service_enhancements.py",
            "tests/test_kg_path_trace_service.py",
        ],
    },
)


def build_overview_graph(repo: KGRepository) -> KgGraphResponse:
    algorithms = {algorithm.algo_id: algorithm for algorithm in repo.list_algorithms()}
    patterns = {pattern.pattern_id: pattern for pattern in repo.list_workflow_patterns()}
    data_types = {data_type.type_id: data_type for data_type in repo.list_data_types()}
    data_sources = {source.source_id: source for source in repo.list_data_sources()}
    task_nodes = {task.task_id: task for task in repo.list_task_nodes()}
    scenario_profiles = {profile.profile_id: profile for profile in repo.get_scenario_profiles(None)}
    task_bundles = {bundle.bundle_id: bundle for bundle in repo.list_task_bundles()}
    output_requirements = {
        requirement.requirement_id: requirement for requirement in repo.list_output_requirements()
    }
    qos_policies = {policy.policy_id: policy for policy in repo.list_qos_policies()}
    data_needs = {need.need_id: need for need in repo.list_data_needs()}
    repair_strategies = {strategy.strategy_id: strategy for strategy in repo.list_repair_strategies()}
    parameter_specs = {
        algo_id: repo.get_parameter_specs(algo_id)
        for algo_id in sorted(algorithms)
    }
    output_schema_policies = {
        policy.policy_id: policy
        for requirement in output_requirements.values()
        if (policy := repo.get_output_schema_policy(requirement.output_type)) is not None
    }
    transform_edges = repo.list_transform_edges()
    durable_learning_summaries = repo.summarize_durable_learning_records(limit=10)

    nodes = []
    nodes.extend(_algorithm_nodes(algorithms.values()))
    nodes.extend(_pattern_nodes(patterns.values()))
    nodes.extend(_data_type_nodes(data_types.values()))
    nodes.extend(_data_source_nodes(data_sources.values()))
    nodes.extend(_task_nodes(task_nodes.values()))
    nodes.extend(_scenario_profile_nodes(scenario_profiles.values()))
    nodes.extend(_task_bundle_nodes(task_bundles.values()))
    nodes.extend(_output_schema_policy_nodes(output_schema_policies.values()))
    nodes.extend(_output_requirement_nodes(output_requirements.values()))
    nodes.extend(_qos_policy_nodes(qos_policies.values()))
    nodes.extend(_data_need_nodes(data_needs.values()))
    nodes.extend(_repair_strategy_nodes(repair_strategies.values()))
    nodes.extend(
        _parameter_spec_nodes(
            spec
            for specs in parameter_specs.values()
            for spec in specs
        )
    )
    nodes.extend(_durable_learning_summary_nodes(durable_learning_summaries))

    edge_map: Dict[tuple[str, str, str], KgGraphEdge] = {}
    requirement_by_output_type = output_requirements_by_output_type(output_requirements)

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
            if step.output_data_type in requirement_by_output_type:
                requirement = requirement_by_output_type[step.output_data_type]
                edge_map[(pattern.pattern_id, requirement.requirement_id, "targets_output_requirement")] = KgGraphEdge(
                    source=pattern.pattern_id,
                    target=requirement.requirement_id,
                    relationship="targets_output_requirement",
                    meta={},
                )
            if step.input_data_type in data_types:
                edge_map[(pattern.pattern_id, step.input_data_type, "requires_input_type")] = KgGraphEdge(
                    source=pattern.pattern_id,
                    target=step.input_data_type,
                    relationship="requires_input_type",
                    meta={"step_order": step.order},
                )
            if step.output_data_type in data_types:
                edge_map[(pattern.pattern_id, step.output_data_type, "emits_output_type")] = KgGraphEdge(
                    source=pattern.pattern_id,
                    target=step.output_data_type,
                    relationship="emits_output_type",
                    meta={"step_order": step.order},
                )
        default_task_id = f"task.{pattern.job_type.value}.fusion"
        if default_task_id in task_nodes:
            edge_map[(pattern.pattern_id, default_task_id, "solves_task")] = KgGraphEdge(
                source=pattern.pattern_id,
                target=default_task_id,
                relationship="solves_task",
                meta={},
            )

    for profile in scenario_profiles.values():
        for task_id in profile.activated_tasks:
            if task_id in task_nodes:
                edge_map[(profile.profile_id, task_id, "activates_task")] = KgGraphEdge(
                    source=profile.profile_id,
                    target=task_id,
                    relationship="activates_task",
                    meta={},
                )
        if profile.qos_policy_id and profile.qos_policy_id in qos_policies:
            edge_map[(profile.profile_id, profile.qos_policy_id, "defaults_to_qos")] = KgGraphEdge(
                source=profile.profile_id,
                target=profile.qos_policy_id,
                relationship="defaults_to_qos",
                meta={},
            )

    for bundle in task_bundles.values():
        for task_id in bundle.requested_tasks:
            if task_id in task_nodes:
                edge_map[(bundle.bundle_id, task_id, "requests_task")] = KgGraphEdge(
                    source=bundle.bundle_id,
                    target=task_id,
                    relationship="requests_task",
                    meta={},
                )
        if bundle.output_requirement_id and bundle.output_requirement_id in output_requirements:
            edge_map[(bundle.bundle_id, bundle.output_requirement_id, "targets_output_requirement")] = KgGraphEdge(
                source=bundle.bundle_id,
                target=bundle.output_requirement_id,
                relationship="targets_output_requirement",
                meta={},
            )
        if bundle.qos_policy_id and bundle.qos_policy_id in qos_policies:
            edge_map[(bundle.bundle_id, bundle.qos_policy_id, "uses_qos_policy")] = KgGraphEdge(
                source=bundle.bundle_id,
                target=bundle.qos_policy_id,
                relationship="uses_qos_policy",
                meta={},
            )
        for strategy_id in bundle.repair_strategy_ids:
            if strategy_id in repair_strategies:
                edge_map[(bundle.bundle_id, strategy_id, "uses_repair_strategy")] = KgGraphEdge(
                    source=bundle.bundle_id,
                    target=strategy_id,
                    relationship="uses_repair_strategy",
                    meta={},
                )
        for need_id in bundle.data_need_ids:
            if need_id in data_needs:
                edge_map[(bundle.bundle_id, need_id, "declares_data_need")] = KgGraphEdge(
                    source=bundle.bundle_id,
                    target=need_id,
                    relationship="declares_data_need",
                    meta={},
                )

    for need in data_needs.values():
        if need.task_id in task_nodes:
            edge_map[(need.task_id, need.need_id, "has_data_need")] = KgGraphEdge(
                source=need.task_id,
                target=need.need_id,
                relationship="has_data_need",
                meta={"direction": need.direction},
            )
        edge_map[(need.need_id, need.data_type_id, "refers_to_data_type")] = KgGraphEdge(
            source=need.need_id,
            target=need.data_type_id,
            relationship="refers_to_data_type",
            meta={"direction": need.direction},
        )

    for strategy in repair_strategies.values():
        for task_id in strategy.applies_to_task_ids:
            if task_id in task_nodes:
                edge_map[(strategy.strategy_id, task_id, "applies_to_task")] = KgGraphEdge(
                    source=strategy.strategy_id,
                    target=task_id,
                    relationship="applies_to_task",
                    meta={"reason_codes": list(strategy.reason_codes)},
                )

    for source in data_sources.values():
        for type_id in source.supported_types:
            if type_id in data_types:
                edge_map[(source.source_id, type_id, "supports_data_type")] = KgGraphEdge(
                    source=source.source_id,
                    target=type_id,
                    relationship="supports_data_type",
                    meta={},
                )

    for algorithm in algorithms.values():
        for type_id in algorithm.input_types:
            if type_id in data_types:
                edge_map[(algorithm.algo_id, type_id, "consumes_data_type")] = KgGraphEdge(
                    source=algorithm.algo_id,
                    target=type_id,
                    relationship="consumes_data_type",
                    meta={},
                )
        if algorithm.output_type in data_types:
            edge_map[(algorithm.algo_id, algorithm.output_type, "produces_data_type")] = KgGraphEdge(
                source=algorithm.algo_id,
                target=algorithm.output_type,
                relationship="produces_data_type",
                meta={},
            )
        for spec in parameter_specs.get(algorithm.algo_id, []):
            edge_map[(algorithm.algo_id, spec.spec_id, "has_parameter_spec")] = KgGraphEdge(
                source=algorithm.algo_id,
                target=spec.spec_id,
                relationship="has_parameter_spec",
                meta={"parameter_key": spec.key},
            )

    for requirement in output_requirements.values():
        if requirement.schema_policy_id in output_schema_policies:
            edge_map[(requirement.requirement_id, requirement.schema_policy_id, "enforces_schema_policy")] = KgGraphEdge(
                source=requirement.requirement_id,
                target=requirement.schema_policy_id,
                relationship="enforces_schema_policy",
                meta={},
            )

    for policy in output_schema_policies.values():
        if policy.output_type in data_types:
            edge_map[(policy.policy_id, policy.output_type, "applies_to_output_type")] = KgGraphEdge(
                source=policy.policy_id,
                target=policy.output_type,
                relationship="applies_to_output_type",
                meta={},
            )

    for source_type, destination_types in transform_edges.items():
        if source_type not in data_types:
            continue
        for destination_type in destination_types:
            if destination_type not in data_types:
                continue
            edge_map[(source_type, destination_type, "can_transform_to")] = KgGraphEdge(
                source=source_type,
                target=destination_type,
                relationship="can_transform_to",
                meta={},
            )

    for summaries in durable_learning_summaries.values():
        for summary in summaries:
            relationship = _durable_learning_relationship(summary.entity_kind)
            if relationship is None:
                continue
            edge_map[(_durable_learning_summary_id(summary), summary.entity_id, relationship)] = KgGraphEdge(
                source=_durable_learning_summary_id(summary),
                target=summary.entity_id,
                relationship=relationship,
                meta={"total_runs": summary.total_runs, "success_count": summary.success_count},
            )

    edges = sorted(edge_map.values(), key=lambda item: (item.source, item.relationship, item.target))
    return KgGraphResponse(
        nodes=sorted(nodes, key=lambda item: (item.kind, item.id)),
        edges=edges,
        meta={
            "graph_type": "overview_closure_graph",
            "pattern_count": len(patterns),
            "algorithm_count": len(algorithms),
            "data_type_count": len(data_types),
            "data_source_count": len(data_sources),
            "task_count": len(task_nodes),
            "scenario_profile_count": len(scenario_profiles),
            "task_bundle_count": len(task_bundles),
            "output_schema_policy_count": len(output_schema_policies),
            "output_requirement_count": len(output_requirements),
            "qos_policy_count": len(qos_policies),
            "data_need_count": len(data_needs),
            "repair_strategy_count": len(repair_strategies),
            "parameter_spec_count": sum(len(specs) for specs in parameter_specs.values()),
            "transform_edge_count": sum(len(destinations) for destinations in transform_edges.values()),
            "durable_learning_summary_count": sum(len(items) for items in durable_learning_summaries.values()),
            "agent_structure": [dict(item) for item in AGENT_STRUCTURE],
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
            "graph_type": "runtime_path_graph",
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


def _data_type_nodes(data_types: Iterable[DataTypeNode]) -> list[KgGraphNode]:
    return [
        KgGraphNode(
            id=data_type.type_id,
            kind="data_type",
            label=data_type.type_id,
            meta={
                "theme": data_type.theme,
                "geometry_type": data_type.geometry_type,
                "description": data_type.description,
            },
        )
        for data_type in data_types
    ]


def _task_nodes(tasks: Iterable[TaskNode]) -> list[KgGraphNode]:
    return [
        KgGraphNode(
            id=task.task_id,
            kind="task",
            label=task.task_name,
            meta={
                "category": task.category,
                "description": task.description,
                "metadata": dict(task.metadata or {}),
            },
        )
        for task in tasks
    ]


def _scenario_profile_nodes(profiles: Iterable[ScenarioProfileNode]) -> list[KgGraphNode]:
    return [
        KgGraphNode(
            id=profile.profile_id,
            kind="scenario_profile",
            label=profile.profile_name,
            meta={
                "disaster_types": list(profile.disaster_types),
                "activated_tasks": list(profile.activated_tasks),
                "preferred_output_fields": list(profile.preferred_output_fields),
                "qos_priority": dict(profile.qos_priority),
                "qos_policy_id": profile.qos_policy_id,
                "metadata": dict(profile.metadata or {}),
            },
        )
        for profile in profiles
    ]


def _task_bundle_nodes(bundles: Iterable[TaskBundleNode]) -> list[KgGraphNode]:
    return [
        KgGraphNode(
            id=bundle.bundle_id,
            kind="task_bundle",
            label=bundle.bundle_name,
            meta={
                "requested_tasks": list(bundle.requested_tasks),
                "output_requirement_id": bundle.output_requirement_id,
                "qos_policy_id": bundle.qos_policy_id,
                "data_need_ids": list(bundle.data_need_ids),
                "repair_strategy_ids": list(bundle.repair_strategy_ids),
                "requires_disaster_profile": bundle.requires_disaster_profile,
                "metadata": dict(bundle.metadata or {}),
            },
        )
        for bundle in bundles
    ]


def _output_schema_policy_nodes(policies: Iterable[OutputSchemaPolicy]) -> list[KgGraphNode]:
    return [
        KgGraphNode(
            id=policy.policy_id,
            kind="output_schema_policy",
            label=policy.policy_id,
            meta={
                "job_type": policy.job_type.value,
                "output_type": policy.output_type,
                "retention_mode": policy.retention_mode,
                "required_fields": list(policy.required_fields),
                "optional_fields": list(policy.optional_fields),
                "rename_hints": dict(policy.rename_hints),
                "compatibility_basis": policy.compatibility_basis,
                "metadata": dict(policy.metadata or {}),
            },
        )
        for policy in policies
    ]


def _output_requirement_nodes(requirements: Iterable[OutputRequirementNode]) -> list[KgGraphNode]:
    return [
        KgGraphNode(
            id=requirement.requirement_id,
            kind="output_requirement",
            label=requirement.requirement_id,
            meta={
                "job_type": requirement.job_type.value,
                "output_type": requirement.output_type,
                "schema_policy_id": requirement.schema_policy_id,
                "required_fields": list(requirement.required_fields),
                "preferred_fields": list(requirement.preferred_fields),
                "optional_fields": list(requirement.optional_fields),
                "metadata": dict(requirement.metadata or {}),
            },
        )
        for requirement in requirements
    ]


def _qos_policy_nodes(policies: Iterable[QoSPolicyNode]) -> list[KgGraphNode]:
    return [
        KgGraphNode(
            id=policy.policy_id,
            kind="qos_policy",
            label=policy.policy_name,
            meta={
                "priority": dict(policy.priority),
                "max_latency_seconds": policy.max_latency_seconds,
                "min_success_rate": policy.min_success_rate,
                "metadata": dict(policy.metadata or {}),
            },
        )
        for policy in policies
    ]


def _data_need_nodes(data_needs: Iterable[DataNeedNode]) -> list[KgGraphNode]:
    return [
        KgGraphNode(
            id=data_need.need_id,
            kind="data_need",
            label=data_need.need_id,
            meta={
                "task_id": data_need.task_id,
                "data_type_id": data_need.data_type_id,
                "direction": data_need.direction,
                "required": data_need.required,
                "description": data_need.description,
                "metadata": dict(data_need.metadata or {}),
            },
        )
        for data_need in data_needs
    ]


def _repair_strategy_nodes(strategies: Iterable[RepairStrategyNode]) -> list[KgGraphNode]:
    return [
        KgGraphNode(
            id=strategy.strategy_id,
            kind="repair_strategy",
            label=strategy.strategy_name,
            meta={
                "reason_codes": list(strategy.reason_codes),
                "from_algorithm_id": strategy.from_algorithm_id,
                "to_algorithm_id": strategy.to_algorithm_id,
                "applies_to_task_ids": list(strategy.applies_to_task_ids),
                "metadata": dict(strategy.metadata or {}),
            },
        )
        for strategy in strategies
    ]


def _parameter_spec_nodes(specs: Iterable[AlgorithmParameterSpec]) -> list[KgGraphNode]:
    return [
        KgGraphNode(
            id=spec.spec_id,
            kind="parameter_spec",
            label=spec.label,
            meta={
                "algo_id": spec.algo_id,
                "key": spec.key,
                "param_type": spec.param_type,
                "default": spec.default,
                "min_value": spec.min_value,
                "max_value": spec.max_value,
                "unit": spec.unit,
                "description": spec.description,
                "required": spec.required,
                "choices": list(spec.choices or []),
                "tunable": spec.tunable,
                "optimization_tags": list(spec.optimization_tags),
                "order": spec.order,
            },
        )
        for spec in specs
    ]


def _durable_learning_summary_nodes(
    durable_learning_summaries: Dict[str, list[DurableLearningSummary]],
) -> list[KgGraphNode]:
    nodes: list[KgGraphNode] = []
    for summaries in durable_learning_summaries.values():
        for summary in summaries:
            nodes.append(
                KgGraphNode(
                    id=_durable_learning_summary_id(summary),
                    kind="durable_learning_summary",
                    label=f"{summary.entity_kind}:{summary.entity_id}",
                    meta={
                        "entity_kind": summary.entity_kind,
                        "entity_id": summary.entity_id,
                        "job_type": summary.job_type.value,
                        "disaster_type": summary.disaster_type,
                        "total_runs": summary.total_runs,
                        "success_count": summary.success_count,
                        "failure_count": summary.failure_count,
                        "repaired_count": summary.repaired_count,
                        "last_run_at": summary.last_run_at,
                        "last_failure_reason": summary.last_failure_reason,
                    },
                )
            )
    return nodes


def output_requirements_by_output_type(
    requirements: Dict[str, OutputRequirementNode],
) -> Dict[str, OutputRequirementNode]:
    return {requirement.output_type: requirement for requirement in requirements.values()}


def _durable_learning_summary_id(summary: DurableLearningSummary) -> str:
    return f"durable_summary:{summary.entity_kind}:{summary.entity_id}"


def _durable_learning_relationship(entity_kind: str) -> str | None:
    mapping = {
        "pattern": "summarizes_pattern",
        "algorithm": "summarizes_algorithm",
        "data_source": "summarizes_data_source",
    }
    return mapping.get(entity_kind)


def _normalize_meta(raw: Any) -> dict[str, Any]:
    return dict(raw) if isinstance(raw, dict) else {}


def _append_unique(values: list[Any], candidate: Any) -> None:
    if candidate is None:
        return
    if candidate not in values:
        values.append(candidate)
