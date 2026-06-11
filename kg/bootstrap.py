from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable, List

from kg.seed import (
    ALGORITHMS,
    CAN_TRANSFORM_TO,
    DATA_NEEDS,
    DATA_SOURCES,
    DATA_TYPES,
    OUTPUT_SCHEMA_POLICIES,
    OUTPUT_REQUIREMENTS,
    PARAMETER_SPECS,
    QOS_POLICIES,
    REPAIR_STRATEGIES,
    SCENARIO_PROFILES,
    TASK_BUNDLES,
    TASKS,
    WORKFLOW_PATTERNS,
)
from utils.local_runtime import DEFAULT_GRAPH_NAMESPACE, apply_local_dependency_defaults, get_graph_namespace


MANAGED_LABEL = "FusionAgentManaged"
GRAPH_NAMESPACE = DEFAULT_GRAPH_NAMESPACE
COMMUNITY_HOME_DATABASE = "neo4j"


def expected_seed_inventory() -> dict[str, int]:
    return {
        "DataType": len(DATA_TYPES),
        "Task": len(TASKS),
        "TaskBundle": len(TASK_BUNDLES),
        "Algorithm": len(ALGORITHMS),
        "AlgorithmParameterSpec": sum(len(items) for items in PARAMETER_SPECS.values()),
        "DataSource": len(DATA_SOURCES),
        "ScenarioProfile": len(SCENARIO_PROFILES),
        "QoSPolicy": len(QOS_POLICIES),
        "OutputSchemaPolicy": len(OUTPUT_SCHEMA_POLICIES),
        "OutputRequirement": len(OUTPUT_REQUIREMENTS),
        "DataNeed": len(DATA_NEEDS),
        "RepairStrategy": len(REPAIR_STRATEGIES),
        "WorkflowPattern": len(WORKFLOW_PATTERNS),
    }


def managed_inventory_missing_seed_labels(inventory: dict[str, Any]) -> dict[str, dict[str, int]]:
    live_counts = {str(item["label"]): int(item["count"]) for item in inventory.get("label_counts", [])}
    expected = expected_seed_inventory()
    missing: dict[str, dict[str, int]] = {}
    for label, expected_count in expected.items():
        live_count = int(live_counts.get(label, 0))
        if live_count < expected_count:
            missing[label] = {
                "expected": expected_count,
                "actual": live_count,
            }
    return missing


def _cypher_literal(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _merge_properties(properties: dict[str, Any]) -> str:
    return ", ".join(f"{key}: {_cypher_literal(value)}" for key, value in properties.items())


def _statement_lines(lines: Iterable[str]) -> str:
    return "\n".join(line.rstrip() for line in lines if line is not None)


def resolve_graph_namespace(graph_namespace: str | None = None) -> str:
    candidate = (graph_namespace or os.getenv("GEOFUSION_GRAPH_NAMESPACE", "")).strip()
    return candidate or GRAPH_NAMESPACE


def build_bootstrap_cypher(graph_namespace: str | None = None) -> str:
    namespace = resolve_graph_namespace(graph_namespace or GRAPH_NAMESPACE)
    sections: List[str] = [
        "// Auto-generated FusionAgent bootstrap for Neo4j.",
        f"// All managed nodes are labeled :{MANAGED_LABEL} to avoid querying unrelated graph content.",
        "// Safe to replay because every statement uses IF NOT EXISTS or MERGE.",
        "",
        _build_schema_section(),
        _build_datatype_section(namespace),
        _build_task_section(namespace),
        _build_task_bundle_section(namespace),
        _build_algorithm_section(namespace),
        _build_parameter_spec_section(namespace),
        _build_datasource_section(namespace),
        _build_scenario_profile_section(namespace),
        _build_qos_policy_section(namespace),
        _build_output_schema_policy_section(namespace),
        _build_output_requirement_section(namespace),
        _build_data_need_section(namespace),
        _build_repair_strategy_section(namespace),
        _build_pattern_section(namespace),
        _build_transform_section(),
    ]
    return "\n\n".join(section for section in sections if section)


def write_bootstrap_cypher(path: Path, graph_namespace: str | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_bootstrap_cypher(graph_namespace), encoding="utf-8")
    return path


def _build_schema_section() -> str:
    return _statement_lines(
        [
            "CREATE CONSTRAINT workflow_pattern_pattern_id IF NOT EXISTS",
            "FOR (wp:WorkflowPattern) REQUIRE wp.patternId IS UNIQUE;",
            "CREATE CONSTRAINT algorithm_algo_id IF NOT EXISTS",
            "FOR (algo:Algorithm) REQUIRE algo.algoId IS UNIQUE;",
            "CREATE CONSTRAINT algorithm_parameter_spec_spec_id IF NOT EXISTS",
            "FOR (ps:AlgorithmParameterSpec) REQUIRE ps.specId IS UNIQUE;",
            "CREATE CONSTRAINT datasource_source_id IF NOT EXISTS",
            "FOR (ds:DataSource) REQUIRE ds.sourceId IS UNIQUE;",
            "CREATE CONSTRAINT output_schema_policy_policy_id IF NOT EXISTS",
            "FOR (osp:OutputSchemaPolicy) REQUIRE osp.policyId IS UNIQUE;",
            "CREATE CONSTRAINT datatype_type_id IF NOT EXISTS",
            "FOR (dt:DataType) REQUIRE dt.typeId IS UNIQUE;",
            "CREATE CONSTRAINT task_task_id IF NOT EXISTS",
            "FOR (task:Task) REQUIRE task.taskId IS UNIQUE;",
            "CREATE CONSTRAINT task_bundle_bundle_id IF NOT EXISTS",
            "FOR (tb:TaskBundle) REQUIRE tb.bundleId IS UNIQUE;",
            "CREATE CONSTRAINT scenario_profile_profile_id IF NOT EXISTS",
            "FOR (profile:ScenarioProfile) REQUIRE profile.profileId IS UNIQUE;",
            "CREATE CONSTRAINT qos_policy_policy_id IF NOT EXISTS",
            "FOR (qos:QoSPolicy) REQUIRE qos.policyId IS UNIQUE;",
            "CREATE CONSTRAINT output_requirement_requirement_id IF NOT EXISTS",
            "FOR (orq:OutputRequirement) REQUIRE orq.requirementId IS UNIQUE;",
            "CREATE CONSTRAINT data_need_need_id IF NOT EXISTS",
            "FOR (dn:DataNeed) REQUIRE dn.needId IS UNIQUE;",
            "CREATE CONSTRAINT repair_strategy_strategy_id IF NOT EXISTS",
            "FOR (rs:RepairStrategy) REQUIRE rs.strategyId IS UNIQUE;",
            "CREATE CONSTRAINT step_template_step_key IF NOT EXISTS",
            "FOR (st:StepTemplate) REQUIRE st.stepKey IS UNIQUE;",
            "CREATE CONSTRAINT workflow_instance_instance_id IF NOT EXISTS",
            "FOR (run:WorkflowInstance) REQUIRE run.instanceId IS UNIQUE;",
            "CREATE FULLTEXT INDEX wp_search IF NOT EXISTS",
            "FOR (wp:WorkflowPattern) ON EACH [wp.patternId, wp.patternName];",
            "CREATE FULLTEXT INDEX algo_search IF NOT EXISTS",
            "FOR (algo:Algorithm) ON EACH [algo.algoId, algo.algoName];",
            "CREATE FULLTEXT INDEX ds_search IF NOT EXISTS",
            "FOR (ds:DataSource) ON EACH [ds.sourceId, ds.sourceName];",
        ]
    )


def _build_datatype_section(graph_namespace: str) -> str:
    lines = ["// Seed DataType nodes"]
    for data_type in DATA_TYPES.values():
        lines.append(
            f"MERGE (dt:DataType {{{_merge_properties({'typeId': data_type.type_id})}}}) "
            f"SET dt:{MANAGED_LABEL} "
            f"SET dt += {{{_merge_properties({'theme': data_type.theme, 'geometryType': data_type.geometry_type, 'description': data_type.description, 'graphNamespace': graph_namespace})}}};"
        )
    return _statement_lines(lines)


def _build_task_section(graph_namespace: str) -> str:
    lines = ["// Seed Task nodes"]
    for task in TASKS.values():
        properties = {
            "taskId": task.task_id,
            "taskName": task.task_name,
            "category": task.category,
            "description": task.description,
            "graphNamespace": graph_namespace,
        }
        lines.append(
            f"MERGE (task:Task {{{_merge_properties({'taskId': task.task_id})}}}) "
            f"SET task:{MANAGED_LABEL} "
            f"SET task += {{{_merge_properties(properties)}}};"
        )
    return _statement_lines(lines)


def _build_task_bundle_section(graph_namespace: str) -> str:
    lines = ["// Seed TaskBundle nodes"]
    for bundle in TASK_BUNDLES.values():
        properties = {
            "bundleId": bundle.bundle_id,
            "bundleName": bundle.bundle_name,
            "requestedTasks": bundle.requested_tasks,
            "outputRequirementId": bundle.output_requirement_id,
            "qosPolicyId": bundle.qos_policy_id,
            "dataNeedIds": bundle.data_need_ids,
            "repairStrategyIds": bundle.repair_strategy_ids,
            "requiresDisasterProfile": bundle.requires_disaster_profile,
            "metadataJson": json.dumps(bundle.metadata, ensure_ascii=False),
            "graphNamespace": graph_namespace,
        }
        lines.append(
            f"MERGE (tb:TaskBundle {{{_merge_properties({'bundleId': bundle.bundle_id})}}}) "
            f"SET tb:{MANAGED_LABEL} "
            f"SET tb += {{{_merge_properties(properties)}}};"
        )
        for task_id in bundle.requested_tasks:
            lines.append(
                f"MATCH (tb:TaskBundle:{MANAGED_LABEL} {{bundleId: {_cypher_literal(bundle.bundle_id)}}}), "
                f"(task:Task:{MANAGED_LABEL} {{taskId: {_cypher_literal(task_id)}}}) "
                "MERGE (tb)-[:REQUESTS_TASK]->(task);"
            )
    return _statement_lines(lines)


def _build_algorithm_section(graph_namespace: str) -> str:
    lines = ["// Seed Algorithm nodes and alternatives"]
    for algorithm in ALGORITHMS.values():
        properties = {
            "algoId": algorithm.algo_id,
            "algoName": algorithm.algo_name,
            "inputTypes": algorithm.input_types,
            "outputType": algorithm.output_type,
            "taskType": algorithm.task_type,
            "toolRef": algorithm.tool_ref,
            "successRate": algorithm.success_rate,
            "accuracyScore": algorithm.accuracy_score,
            "stabilityScore": algorithm.stability_score,
            "usageMode": algorithm.usage_mode,
            "metadataJson": json.dumps(algorithm.metadata, ensure_ascii=False),
            "graphNamespace": graph_namespace,
        }
        lines.append(
            f"MERGE (algo:Algorithm {{{_merge_properties({'algoId': algorithm.algo_id})}}}) "
            f"SET algo:{MANAGED_LABEL} "
            f"SET algo += {{{_merge_properties(properties)}}};"
        )
    for algorithm in ALGORITHMS.values():
        for alternative in algorithm.alternatives:
            lines.append(
                f"MATCH (src:Algorithm:{MANAGED_LABEL} {{algoId: {_cypher_literal(algorithm.algo_id)}}}), "
                f"(dst:Algorithm:{MANAGED_LABEL} {{algoId: {_cypher_literal(alternative)}}}) "
                "MERGE (src)-[:ALTERNATIVE_TO]->(dst);"
            )
    return _statement_lines(lines)


def _build_parameter_spec_section(graph_namespace: str) -> str:
    lines = ["// Seed AlgorithmParameterSpec nodes"]
    for algo_id, specs in PARAMETER_SPECS.items():
        for spec in specs:
            properties = {
                "specId": spec.spec_id,
                "algoId": spec.algo_id,
                "key": spec.key,
                "label": spec.label,
                "paramType": spec.param_type,
                "default": spec.default,
                "minValue": spec.min_value,
                "maxValue": spec.max_value,
                "unit": spec.unit,
                "description": spec.description,
                "required": spec.required,
                "choices": spec.choices,
                "tunable": spec.tunable,
                "optimizationTags": spec.optimization_tags,
                "conditionalDefaults": json.dumps(spec.conditional_defaults, ensure_ascii=False),
                "defaultProvenance": json.dumps(spec.default_provenance, ensure_ascii=False),
                "order": spec.order,
                "graphNamespace": graph_namespace,
            }
            lines.append(
                f"MERGE (ps:AlgorithmParameterSpec {{{_merge_properties({'specId': spec.spec_id})}}}) "
                f"SET ps:{MANAGED_LABEL} "
                f"SET ps += {{{_merge_properties(properties)}}};"
            )
            lines.append(
                f"MATCH (algo:Algorithm:{MANAGED_LABEL} {{algoId: {_cypher_literal(algo_id)}}}), "
                f"(ps:AlgorithmParameterSpec:{MANAGED_LABEL} {{specId: {_cypher_literal(spec.spec_id)}}}) "
                f"MERGE (algo)-[:HAS_PARAMETER_SPEC {{order: {spec.order}}}]->(ps);"
            )
    return _statement_lines(lines)


def _build_datasource_section(graph_namespace: str) -> str:
    lines = ["// Seed DataSource nodes"]
    for source in DATA_SOURCES:
        properties = {
            "sourceId": source.source_id,
            "sourceName": source.source_name,
            "supportedTypes": source.supported_types,
            "disasterTypes": source.disaster_types,
            "qualityScore": source.quality_score,
            "sourceKind": source.source_kind,
            "qualityTier": source.quality_tier,
            "freshnessCategory": source.freshness_category,
            "freshnessHours": source.freshness_hours,
            "freshnessScore": source.freshness_score,
            "supportedJobTypes": source.supported_job_types,
            "supportedGeometryTypes": source.supported_geometry_types,
            "metadataJson": json.dumps(source.metadata, ensure_ascii=False),
            "graphNamespace": graph_namespace,
        }
        lines.append(
            f"MERGE (ds:DataSource {{{_merge_properties({'sourceId': source.source_id})}}}) "
            f"SET ds:{MANAGED_LABEL} "
            f"SET ds += {{{_merge_properties(properties)}}};"
        )
    return _statement_lines(lines)


def _build_scenario_profile_section(graph_namespace: str) -> str:
    lines = ["// Seed ScenarioProfile nodes"]
    for profile in SCENARIO_PROFILES:
        properties = {
            "profileId": profile.profile_id,
            "profileName": profile.profile_name,
            "disasterTypes": profile.disaster_types,
            "activatedTasks": profile.activated_tasks,
            "preferredOutputFields": profile.preferred_output_fields,
            "qosPriorityJson": json.dumps(profile.qos_priority, ensure_ascii=False),
            "qosPolicyId": profile.qos_policy_id,
            "metadataJson": json.dumps(profile.metadata, ensure_ascii=False),
            "graphNamespace": graph_namespace,
        }
        lines.append(
            f"MERGE (profile:ScenarioProfile {{{_merge_properties({'profileId': profile.profile_id})}}}) "
            f"SET profile:{MANAGED_LABEL} "
            f"SET profile += {{{_merge_properties(properties)}}};"
        )
        for task_id in profile.activated_tasks:
            lines.append(
                f"MATCH (profile:ScenarioProfile:{MANAGED_LABEL} {{profileId: {_cypher_literal(profile.profile_id)}}}), "
                f"(task:Task:{MANAGED_LABEL} {{taskId: {_cypher_literal(task_id)}}}) "
                "MERGE (profile)-[:ACTIVATES_TASK]->(task);"
            )
    return _statement_lines(lines)


def _build_qos_policy_section(graph_namespace: str) -> str:
    lines = ["// Seed QoSPolicy nodes"]
    for policy in QOS_POLICIES.values():
        properties = {
            "policyId": policy.policy_id,
            "policyName": policy.policy_name,
            "priorityJson": json.dumps(policy.priority, ensure_ascii=False),
            "maxLatencySeconds": policy.max_latency_seconds,
            "minSuccessRate": policy.min_success_rate,
            "metadataJson": json.dumps(policy.metadata, ensure_ascii=False),
            "graphNamespace": graph_namespace,
        }
        lines.append(
            f"MERGE (qos:QoSPolicy {{{_merge_properties({'policyId': policy.policy_id})}}}) "
            f"SET qos:{MANAGED_LABEL} "
            f"SET qos += {{{_merge_properties(properties)}}};"
        )
    for profile in SCENARIO_PROFILES:
        if profile.qos_policy_id:
            lines.append(
                f"MATCH (profile:ScenarioProfile:{MANAGED_LABEL} {{profileId: {_cypher_literal(profile.profile_id)}}}), "
                f"(qos:QoSPolicy:{MANAGED_LABEL} {{policyId: {_cypher_literal(profile.qos_policy_id)}}}) "
                "MERGE (profile)-[:DEFAULTS_TO_QOS]->(qos);"
            )
    return _statement_lines(lines)


def _build_output_schema_policy_section(graph_namespace: str) -> str:
    lines = ["// Seed OutputSchemaPolicy nodes"]
    for policy in OUTPUT_SCHEMA_POLICIES.values():
        properties = {
            "policyId": policy.policy_id,
            "outputType": policy.output_type,
            "jobType": policy.job_type.value,
            "retentionMode": policy.retention_mode,
            "requiredFields": policy.required_fields,
            "optionalFields": policy.optional_fields,
            "renameHintsJson": json.dumps(policy.rename_hints, ensure_ascii=False),
            "compatibilityBasis": policy.compatibility_basis,
            "metadataJson": json.dumps(policy.metadata, ensure_ascii=False),
            "graphNamespace": graph_namespace,
        }
        lines.append(
            f"MERGE (osp:OutputSchemaPolicy {{{_merge_properties({'policyId': policy.policy_id})}}}) "
            f"SET osp:{MANAGED_LABEL} "
            f"SET osp += {{{_merge_properties(properties)}}};"
        )
        lines.append(
            f"MATCH (osp:OutputSchemaPolicy:{MANAGED_LABEL} {{policyId: {_cypher_literal(policy.policy_id)}}}), "
            f"(dt:DataType:{MANAGED_LABEL} {{typeId: {_cypher_literal(policy.output_type)}}}) "
            "MERGE (osp)-[:APPLIES_TO_OUTPUT_TYPE]->(dt);"
        )
    return _statement_lines(lines)


def _build_output_requirement_section(graph_namespace: str) -> str:
    lines = ["// Seed OutputRequirement nodes"]
    for requirement in OUTPUT_REQUIREMENTS.values():
        properties = {
            "requirementId": requirement.requirement_id,
            "jobType": requirement.job_type.value,
            "outputType": requirement.output_type,
            "schemaPolicyId": requirement.schema_policy_id,
            "requiredFields": requirement.required_fields,
            "preferredFields": requirement.preferred_fields,
            "optionalFields": requirement.optional_fields,
            "metadataJson": json.dumps(requirement.metadata, ensure_ascii=False),
            "graphNamespace": graph_namespace,
        }
        lines.append(
            f"MERGE (orq:OutputRequirement {{{_merge_properties({'requirementId': requirement.requirement_id})}}}) "
            f"SET orq:{MANAGED_LABEL} "
            f"SET orq += {{{_merge_properties(properties)}}};"
        )
        lines.append(
            f"MATCH (orq:OutputRequirement:{MANAGED_LABEL} {{requirementId: {_cypher_literal(requirement.requirement_id)}}}), "
            f"(dt:DataType:{MANAGED_LABEL} {{typeId: {_cypher_literal(requirement.output_type)}}}) "
            "MERGE (orq)-[:REQUIRES_OUTPUT_TYPE]->(dt);"
        )
        lines.append(
            f"MATCH (orq:OutputRequirement:{MANAGED_LABEL} {{requirementId: {_cypher_literal(requirement.requirement_id)}}}), "
            f"(osp:OutputSchemaPolicy:{MANAGED_LABEL} {{policyId: {_cypher_literal(requirement.schema_policy_id)}}}) "
            "MERGE (orq)-[:USES_SCHEMA_POLICY]->(osp);"
        )
    for bundle in TASK_BUNDLES.values():
        if bundle.output_requirement_id:
            lines.append(
                f"MATCH (tb:TaskBundle:{MANAGED_LABEL} {{bundleId: {_cypher_literal(bundle.bundle_id)}}}), "
                f"(orq:OutputRequirement:{MANAGED_LABEL} {{requirementId: {_cypher_literal(bundle.output_requirement_id)}}}) "
                "MERGE (tb)-[:TARGETS_OUTPUT_REQUIREMENT]->(orq);"
            )
    return _statement_lines(lines)


def _build_data_need_section(graph_namespace: str) -> str:
    lines = ["// Seed DataNeed nodes"]
    for need in DATA_NEEDS:
        properties = {
            "needId": need.need_id,
            "taskId": need.task_id,
            "dataTypeId": need.data_type_id,
            "direction": need.direction,
            "required": need.required,
            "description": need.description,
            "metadataJson": json.dumps(need.metadata, ensure_ascii=False),
            "graphNamespace": graph_namespace,
        }
        lines.append(
            f"MERGE (dn:DataNeed {{{_merge_properties({'needId': need.need_id})}}}) "
            f"SET dn:{MANAGED_LABEL} "
            f"SET dn += {{{_merge_properties(properties)}}};"
        )
        lines.append(
            f"MATCH (dn:DataNeed:{MANAGED_LABEL} {{needId: {_cypher_literal(need.need_id)}}}), "
            f"(task:Task:{MANAGED_LABEL} {{taskId: {_cypher_literal(need.task_id)}}}) "
            "MERGE (task)-[:HAS_DATA_NEED]->(dn);"
        )
        lines.append(
            f"MATCH (dn:DataNeed:{MANAGED_LABEL} {{needId: {_cypher_literal(need.need_id)}}}), "
            f"(dt:DataType:{MANAGED_LABEL} {{typeId: {_cypher_literal(need.data_type_id)}}}) "
            "MERGE (dn)-[:REFERS_TO_DATA_TYPE]->(dt);"
        )
    return _statement_lines(lines)


def _build_repair_strategy_section(graph_namespace: str) -> str:
    lines = ["// Seed RepairStrategy nodes"]
    for strategy in REPAIR_STRATEGIES.values():
        properties = {
            "strategyId": strategy.strategy_id,
            "strategyName": strategy.strategy_name,
            "reasonCodes": strategy.reason_codes,
            "fromAlgorithmId": strategy.from_algorithm_id,
            "toAlgorithmId": strategy.to_algorithm_id,
            "appliesToTaskIds": strategy.applies_to_task_ids,
            "metadataJson": json.dumps(strategy.metadata, ensure_ascii=False),
            "graphNamespace": graph_namespace,
        }
        lines.append(
            f"MERGE (rs:RepairStrategy {{{_merge_properties({'strategyId': strategy.strategy_id})}}}) "
            f"SET rs:{MANAGED_LABEL} "
            f"SET rs += {{{_merge_properties(properties)}}};"
        )
        for task_id in strategy.applies_to_task_ids:
            lines.append(
                f"MATCH (rs:RepairStrategy:{MANAGED_LABEL} {{strategyId: {_cypher_literal(strategy.strategy_id)}}}), "
                f"(task:Task:{MANAGED_LABEL} {{taskId: {_cypher_literal(task_id)}}}) "
                "MERGE (rs)-[:APPLIES_TO_TASK]->(task);"
            )
    for bundle in TASK_BUNDLES.values():
        for strategy_id in bundle.repair_strategy_ids:
            lines.append(
                f"MATCH (tb:TaskBundle:{MANAGED_LABEL} {{bundleId: {_cypher_literal(bundle.bundle_id)}}}), "
                f"(rs:RepairStrategy:{MANAGED_LABEL} {{strategyId: {_cypher_literal(strategy_id)}}}) "
                "MERGE (tb)-[:USES_REPAIR_STRATEGY]->(rs);"
            )
    return _statement_lines(lines)


def _build_pattern_section(graph_namespace: str) -> str:
    lines = ["// Seed WorkflowPattern and StepTemplate nodes"]
    for pattern in WORKFLOW_PATTERNS:
        pattern_properties = {
            "patternId": pattern.pattern_id,
            "patternName": pattern.pattern_name,
            "jobType": pattern.job_type.value,
            "disasterTypes": pattern.disaster_types,
            "successRate": pattern.success_rate,
            "metadataJson": json.dumps(pattern.metadata, ensure_ascii=False),
            "graphNamespace": graph_namespace,
        }
        lines.append(
            f"MERGE (wp:WorkflowPattern {{{_merge_properties({'patternId': pattern.pattern_id})}}}) "
            f"SET wp:{MANAGED_LABEL} "
            f"SET wp += {{{_merge_properties(pattern_properties)}}};"
        )
        for step in pattern.steps:
            step_key = f"{pattern.pattern_id}#{step.order}"
            step_properties = {
                "stepKey": step_key,
                "order": step.order,
                "name": step.name,
                "algorithmId": step.algorithm_id,
                "inputDataType": step.input_data_type,
                "outputDataType": step.output_data_type,
                "dataSourceId": step.data_source_id,
                "dependsOn": step.depends_on,
                "isOptional": step.is_optional,
                "graphNamespace": graph_namespace,
            }
            lines.append(
                f"MERGE (st:StepTemplate {{{_merge_properties({'stepKey': step_key})}}}) "
                f"SET st:{MANAGED_LABEL} "
                f"SET st += {{{_merge_properties(step_properties)}}};"
            )
            lines.append(
                f"MATCH (wp:WorkflowPattern:{MANAGED_LABEL} {{patternId: {_cypher_literal(pattern.pattern_id)}}}), "
                f"(st:StepTemplate:{MANAGED_LABEL} {{stepKey: {_cypher_literal(step_key)}}}) "
                f"MERGE (wp)-[:HAS_STEP {{order: {step.order}}}]->(st);"
            )
    return _statement_lines(lines)


def _build_transform_section() -> str:
    lines = ["// Seed transform graph"]
    for source_type, destination_types in CAN_TRANSFORM_TO.items():
        for destination_type in destination_types:
            lines.append(
                f"MATCH (src:DataType:{MANAGED_LABEL} {{typeId: {_cypher_literal(source_type)}}}), "
                f"(dst:DataType:{MANAGED_LABEL} {{typeId: {_cypher_literal(destination_type)}}}) "
                "MERGE (src)-[:CAN_TRANSFORM_TO]->(dst);"
            )
    return _statement_lines(lines)


def _split_cypher_statements(cypher: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_string = False
    quote_char = ""
    escape = False

    for char in cypher:
        current.append(char)
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if in_string:
            if char == quote_char:
                in_string = False
            continue
        if char in {"'", '"'}:
            in_string = True
            quote_char = char
            continue
        if char == ";":
            statement = "".join(current[:-1]).strip()
            if statement:
                statements.append(statement)
            current = []

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def _create_driver(uri: str, user: str, password: str):
    from neo4j import GraphDatabase  # type: ignore

    return GraphDatabase.driver(uri, auth=(user, password))


def _safe_database_name(database: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", database):
        raise ValueError(f"Unsupported Neo4j database name: {database!r}")
    return f"`{database}`"


def apply_bootstrap_cypher(
    *,
    uri: str,
    user: str,
    password: str,
    cypher: str | None = None,
    database: str | None = None,
) -> int:
    statements = _split_cypher_statements(cypher or build_bootstrap_cypher())
    driver = _create_driver(uri=uri, user=user, password=password)
    try:
        with driver.session(database=database) as session:
            for statement in statements:
                result = session.run(statement)
                consume = getattr(result, "consume", None)
                if callable(consume):
                    consume()
    finally:
        driver.close()
    return len(statements)


def get_neo4j_server_info(*, uri: str, user: str, password: str) -> dict[str, Any]:
    driver = _create_driver(uri=uri, user=user, password=password)
    last_error: Exception | None = None
    try:
        def _discover_default_database(session: Any) -> str | None:
            try:
                rows = session.run("SHOW DATABASES YIELD name, home, default RETURN name, home, default")
            except Exception:  # noqa: BLE001
                return None

            fallback_names: list[str] = []
            for row in rows:
                name = str(row.get("name", "")).strip()
                if not name:
                    continue
                if bool(row.get("default")) or bool(row.get("home")):
                    return name
                if name != "system":
                    fallback_names.append(name)
            if len(fallback_names) == 1:
                return fallback_names[0]
            return None

        for database in ("system", None):
            try:
                with driver.session(database=database) as session:
                    row = session.run(
                        "CALL dbms.components() YIELD name, versions, edition RETURN name, versions, edition LIMIT 1"
                    ).single()
                    if row:
                        versions = list(row.get("versions", []))
                        return {
                            "name": str(row.get("name", "Neo4j")),
                            "version": versions[0] if versions else None,
                            "edition": str(row.get("edition", "unknown")).lower(),
                            "default_database": _discover_default_database(session),
                        }
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        if last_error is not None:
            raise last_error
        raise RuntimeError("Unable to determine Neo4j server info.")
    finally:
        driver.close()


def resolve_graph_target(
    *,
    uri: str,
    user: str,
    password: str,
    database: str | None = None,
) -> dict[str, Any]:
    server = get_neo4j_server_info(uri=uri, user=user, password=password)
    requested = (database or "").strip() or None
    edition = str(server["edition"]).lower()
    default_database = str(server.get("default_database") or COMMUNITY_HOME_DATABASE)
    notes: list[str] = []

    if edition == "community":
        if requested and requested.lower() not in {default_database.lower()}:
            notes.append(
                "Neo4j Community Edition does not support multiple user databases; "
                f"using the home database '{default_database}' with the :{MANAGED_LABEL} label namespace."
            )
        return {
            **server,
            "database_requested": requested,
            "database_used": default_database,
            "isolation_mode": "managed-label",
            "notes": notes,
        }

    return {
        **server,
        "database_requested": requested,
        "database_used": requested or server.get("default_database"),
        "isolation_mode": "database" if requested else "managed-label",
        "notes": notes,
    }


def ensure_database_exists(
    *,
    uri: str,
    user: str,
    password: str,
    database: str,
) -> bool:
    driver = _create_driver(uri=uri, user=user, password=password)
    try:
        with driver.session(database="system") as session:
            names = {str(row["name"]) for row in session.run("SHOW DATABASES YIELD name RETURN name")}
            if database in names:
                return False
            session.run(f"CREATE DATABASE {_safe_database_name(database)} IF NOT EXISTS")
            return True
    finally:
        driver.close()


def reset_managed_graph(
    *,
    uri: str,
    user: str,
    password: str,
    database: str | None = None,
    graph_namespace: str | None = None,
) -> int:
    namespace = resolve_graph_namespace(graph_namespace)
    driver = _create_driver(uri=uri, user=user, password=password)
    try:
        with driver.session(database=database) as session:
            row = session.run(
                f"""
                MATCH (n:{MANAGED_LABEL})
                WHERE n.graphNamespace = $graph_namespace
                RETURN count(n) AS count
                """,
                graph_namespace=namespace,
            ).single()
            deleted = int(row.get("count", 0)) if row else 0
            session.run(
                f"""
                MATCH (n:{MANAGED_LABEL})
                WHERE n.graphNamespace = $graph_namespace
                DETACH DELETE n
                """,
                graph_namespace=namespace,
            )
            return deleted
    finally:
        driver.close()


def inspect_graph_state(
    *,
    uri: str,
    user: str,
    password: str,
    database: str | None = None,
    managed_only: bool = False,
    graph_namespace: str | None = None,
) -> dict[str, Any]:
    namespace = resolve_graph_namespace(graph_namespace)
    driver = _create_driver(uri=uri, user=user, password=password)
    try:
        with driver.session(database=database) as session:
            if managed_only:
                node_row = session.run(
                    f"""
                    MATCH (n:{MANAGED_LABEL})
                    WHERE n.graphNamespace = $graph_namespace
                    RETURN count(n) AS count
                    """,
                    graph_namespace=namespace,
                ).single()
                label_rows = session.run(
                    f"""
                    MATCH (n:{MANAGED_LABEL})
                    WHERE n.graphNamespace = $graph_namespace
                    UNWIND [label IN labels(n) WHERE label <> $managed_label] AS label
                    RETURN label, count(*) AS count
                    ORDER BY count DESC, label
                    """,
                    managed_label=MANAGED_LABEL,
                    graph_namespace=namespace,
                )
                rel_rows = session.run(
                    f"""
                    MATCH (:{MANAGED_LABEL})-[r]->(:{MANAGED_LABEL})
                    WHERE startNode(r).graphNamespace = $graph_namespace
                      AND endNode(r).graphNamespace = $graph_namespace
                    RETURN type(r) AS relationshipType, count(*) AS count
                    ORDER BY count DESC, relationshipType
                    """,
                    graph_namespace=namespace,
                )
            else:
                node_row = session.run("MATCH (n) RETURN count(n) AS count").single()
                label_rows = session.run(
                    """
                    MATCH (n)
                    UNWIND labels(n) AS label
                    RETURN label, count(*) AS count
                    ORDER BY count DESC, label
                    """
                )
                rel_rows = session.run(
                    """
                    MATCH ()-[r]->()
                    RETURN type(r) AS relationshipType, count(*) AS count
                    ORDER BY count DESC, relationshipType
                    """
                )

            return {
                "database": database,
                "managed_only": managed_only,
                "graph_namespace": namespace if managed_only else None,
                "node_count": int(node_row.get("count", 0)) if node_row else 0,
                "label_counts": [dict(row) for row in label_rows],
                "relationship_counts": [dict(row) for row in rel_rows],
            }
    finally:
        driver.close()


def ensure_bootstrap_data(
    *,
    uri: str,
    user: str,
    password: str,
    database: str | None = None,
    cypher: str | None = None,
    graph_namespace: str | None = None,
) -> bool:
    namespace = resolve_graph_namespace(graph_namespace)
    live_inventory = inspect_graph_state(
        uri=uri,
        user=user,
        password=password,
        database=database,
        managed_only=True,
        graph_namespace=namespace,
    )
    if not managed_inventory_missing_seed_labels(live_inventory):
        return False

    apply_bootstrap_cypher(
        uri=uri,
        user=user,
        password=password,
        cypher=cypher or build_bootstrap_cypher(namespace),
        database=database,
    )
    return True


def prepare_local_neo4j(
    *,
    uri: str,
    user: str,
    password: str,
    database: str | None = None,
    reset_managed: bool = False,
    cypher: str | None = None,
) -> dict[str, Any]:
    namespace = get_graph_namespace()
    resolved = resolve_graph_target(uri=uri, user=user, password=password, database=database)
    database_used = resolved["database_used"]
    database_created = False

    if resolved["isolation_mode"] == "database" and database_used:
        database_created = ensure_database_exists(uri=uri, user=user, password=password, database=database_used)

    deleted_nodes = 0
    if reset_managed:
        deleted_nodes = reset_managed_graph(
            uri=uri,
            user=user,
            password=password,
            database=database_used,
            graph_namespace=namespace,
        )

    bootstrap_applied = ensure_bootstrap_data(
        uri=uri,
        user=user,
        password=password,
        database=database_used,
        cypher=cypher,
        graph_namespace=namespace,
    )

    managed_inventory = inspect_graph_state(
        uri=uri,
        user=user,
        password=password,
        database=database_used,
        managed_only=True,
        graph_namespace=namespace,
    )
    all_inventory = inspect_graph_state(
        uri=uri,
        user=user,
        password=password,
        database=database_used,
        managed_only=False,
    )

    managed_labels = {label["label"] for label in managed_inventory["label_counts"]}
    foreign_labels = [
        label
        for label in all_inventory["label_counts"]
        if label["label"] not in managed_labels and label["label"] != MANAGED_LABEL
    ]
    missing_seed_labels = managed_inventory_missing_seed_labels(managed_inventory)

    return {
        **resolved,
        "managed_label": MANAGED_LABEL,
        "graph_namespace": namespace,
        "database_created": database_created,
        "managed_nodes_deleted": deleted_nodes,
        "bootstrap_applied": bootstrap_applied,
        "expected_seed_inventory": expected_seed_inventory(),
        "missing_seed_labels": missing_seed_labels,
        "kg_contract_ok": not missing_seed_labels,
        "managed_inventory": managed_inventory,
        "foreign_labels": foreign_labels,
    }


def _connection_settings_from_env(args: argparse.Namespace) -> tuple[str, str, str, str | None]:
    apply_local_dependency_defaults()
    uri = (args.uri or os.getenv("GEOFUSION_NEO4J_URI", "")).strip()
    user = (args.user or os.getenv("GEOFUSION_NEO4J_USER", "")).strip()
    password = (args.password or os.getenv("GEOFUSION_NEO4J_PASSWORD", "")).strip()
    database = (args.database or os.getenv("GEOFUSION_NEO4J_DATABASE", "")).strip() or None
    if not uri or not user or not password:
        raise RuntimeError("Neo4j connection settings are required for --apply/--ensure/--inspect/--prepare-local.")
    return uri, user, password, database


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate, inspect, or apply the FusionAgent Neo4j bootstrap script.")
    parser.add_argument("--output", default="kg/bootstrap/neo4j_bootstrap.cypher", help="Path to the output cypher file.")
    parser.add_argument("--apply", action="store_true", help="Apply the bootstrap cypher to Neo4j.")
    parser.add_argument(
        "--ensure",
        action="store_true",
        help="Apply the bootstrap cypher only when FusionAgent-managed WorkflowPattern seed data is missing.",
    )
    parser.add_argument("--inspect", action="store_true", help="Read-only inspection of the current Neo4j graph.")
    parser.add_argument("--managed-only", action="store_true", help="Inspect only FusionAgent-managed labels and relationships.")
    parser.add_argument("--reset-managed", action="store_true", help="Delete FusionAgent-managed nodes before reseeding.")
    parser.add_argument(
        "--prepare-local",
        action="store_true",
        help="Prepare the local FusionAgent graph: resolve isolation mode, optionally reset managed nodes, ensure bootstrap data, and report inventory.",
    )
    parser.add_argument("--json", action="store_true", help="Print structured JSON output for inspect / prepare-local.")
    parser.add_argument("--uri", help="Neo4j bolt URI. Falls back to GEOFUSION_NEO4J_URI.")
    parser.add_argument("--user", help="Neo4j user. Falls back to GEOFUSION_NEO4J_USER.")
    parser.add_argument("--password", help="Neo4j password. Falls back to GEOFUSION_NEO4J_PASSWORD.")
    parser.add_argument("--database", help="Neo4j database. Community edition will fall back to the home database.")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_argument_parser()
    args = parser.parse_args(argv)

    if args.inspect:
        uri, user, password, database = _connection_settings_from_env(args)
        graph_namespace = get_graph_namespace()
        resolved = resolve_graph_target(uri=uri, user=user, password=password, database=database)
        report = {
            **resolved,
            "managed_label": MANAGED_LABEL,
            "graph_namespace": graph_namespace,
            "expected_seed_inventory": expected_seed_inventory(),
            "inventory": inspect_graph_state(
                uri=uri,
                user=user,
                password=password,
                database=resolved["database_used"],
                managed_only=args.managed_only,
                graph_namespace=graph_namespace if args.managed_only else None,
            ),
        }
        report["missing_seed_labels"] = (
            managed_inventory_missing_seed_labels(report["inventory"]) if args.managed_only else {}
        )
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(report)
        return

    if args.prepare_local:
        uri, user, password, database = _connection_settings_from_env(args)
        graph_namespace = get_graph_namespace()
        path = write_bootstrap_cypher(Path(args.output), graph_namespace=graph_namespace)
        summary = prepare_local_neo4j(
            uri=uri,
            user=user,
            password=password,
            database=database,
            reset_managed=args.reset_managed,
            cypher=path.read_text(encoding="utf-8"),
        )
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(summary)
        return

    graph_namespace = get_graph_namespace()
    path = write_bootstrap_cypher(Path(args.output), graph_namespace=graph_namespace)
    if args.reset_managed:
        uri, user, password, database = _connection_settings_from_env(args)
        resolved = resolve_graph_target(uri=uri, user=user, password=password, database=database)
        deleted = reset_managed_graph(
            uri=uri,
            user=user,
            password=password,
            database=resolved["database_used"],
            graph_namespace=graph_namespace,
        )
        print(f"deleted {deleted} managed nodes")
        return

    if args.ensure or args.apply:
        uri, user, password, database = _connection_settings_from_env(args)
        resolved = resolve_graph_target(uri=uri, user=user, password=password, database=database)
        database_used = resolved["database_used"]
        if resolved["isolation_mode"] == "database" and database_used:
            ensure_database_exists(uri=uri, user=user, password=password, database=database_used)
        if args.ensure:
            changed = ensure_bootstrap_data(
                uri=uri,
                user=user,
                password=password,
                database=database_used,
                cypher=path.read_text(encoding="utf-8"),
            )
            print("applied" if changed else "already-seeded")
            return
        count = apply_bootstrap_cypher(
            uri=uri,
            user=user,
            password=password,
            database=database_used,
            cypher=path.read_text(encoding="utf-8"),
        )
        print(f"applied {count} statements")
        return

    print(path)


if __name__ == "__main__":
    main()
