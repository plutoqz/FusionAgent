from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, Iterable, List

from kg.seed import ALGORITHMS, CAN_TRANSFORM_TO, DATA_SOURCES, DATA_TYPES, WORKFLOW_PATTERNS
from utils.local_runtime import apply_local_dependency_defaults


def _cypher_literal(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def _merge_properties(properties: dict[str, Any]) -> str:
    return ", ".join(f"{key}: {_cypher_literal(value)}" for key, value in properties.items())


def _statement_lines(lines: Iterable[str]) -> str:
    return "\n".join(line.rstrip() for line in lines if line is not None)


def build_bootstrap_cypher() -> str:
    sections: List[str] = [
        "// Auto-generated GeoFusion bootstrap for Neo4j.",
        "// Safe to replay because every statement uses IF NOT EXISTS or MERGE.",
        "",
        _build_schema_section(),
        _build_datatype_section(),
        _build_algorithm_section(),
        _build_datasource_section(),
        _build_pattern_section(),
        _build_transform_section(),
    ]
    return "\n\n".join(section for section in sections if section)


def write_bootstrap_cypher(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_bootstrap_cypher(), encoding="utf-8")
    return path


def _build_schema_section() -> str:
    return _statement_lines(
        [
            "CREATE CONSTRAINT workflow_pattern_pattern_id IF NOT EXISTS",
            "FOR (wp:WorkflowPattern) REQUIRE wp.patternId IS UNIQUE;",
            "CREATE CONSTRAINT algorithm_algo_id IF NOT EXISTS",
            "FOR (algo:Algorithm) REQUIRE algo.algoId IS UNIQUE;",
            "CREATE CONSTRAINT datasource_source_id IF NOT EXISTS",
            "FOR (ds:DataSource) REQUIRE ds.sourceId IS UNIQUE;",
            "CREATE CONSTRAINT datatype_type_id IF NOT EXISTS",
            "FOR (dt:DataType) REQUIRE dt.typeId IS UNIQUE;",
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


def _build_datatype_section() -> str:
    lines = ["// Seed DataType nodes"]
    for data_type in DATA_TYPES.values():
        lines.append(
            f"MERGE (dt:DataType {{{_merge_properties({'typeId': data_type.type_id})}}}) "
            f"SET dt += {{{_merge_properties({'theme': data_type.theme, 'geometryType': data_type.geometry_type, 'description': data_type.description})}}};"
        )
    return _statement_lines(lines)


def _build_algorithm_section() -> str:
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
        }
        lines.append(
            f"MERGE (algo:Algorithm {{{_merge_properties({'algoId': algorithm.algo_id})}}}) "
            f"SET algo += {{{_merge_properties(properties)}}};"
        )
    for algorithm in ALGORITHMS.values():
        for alternative in algorithm.alternatives:
            lines.append(
                f"MATCH (src:Algorithm {{algoId: {_cypher_literal(algorithm.algo_id)}}}), "
                f"(dst:Algorithm {{algoId: {_cypher_literal(alternative)}}}) "
                "MERGE (src)-[:ALTERNATIVE_TO]->(dst);"
            )
    return _statement_lines(lines)


def _build_datasource_section() -> str:
    import json

    lines = ["// Seed DataSource nodes"]
    for source in DATA_SOURCES:
        properties = {
            "sourceId": source.source_id,
            "sourceName": source.source_name,
            "supportedTypes": source.supported_types,
            "disasterTypes": source.disaster_types,
            "qualityScore": source.quality_score,
            "metadataJson": json.dumps(source.metadata, ensure_ascii=False),
        }
        lines.append(
            f"MERGE (ds:DataSource {{{_merge_properties({'sourceId': source.source_id})}}}) "
            f"SET ds += {{{_merge_properties(properties)}}};"
        )
    return _statement_lines(lines)


def _build_pattern_section() -> str:
    import json

    lines = ["// Seed WorkflowPattern and StepTemplate nodes"]
    for pattern in WORKFLOW_PATTERNS:
        pattern_properties = {
            "patternId": pattern.pattern_id,
            "patternName": pattern.pattern_name,
            "jobType": pattern.job_type.value,
            "disasterTypes": pattern.disaster_types,
            "successRate": pattern.success_rate,
            "metadataJson": json.dumps(pattern.metadata, ensure_ascii=False),
        }
        lines.append(
            f"MERGE (wp:WorkflowPattern {{{_merge_properties({'patternId': pattern.pattern_id})}}}) "
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
            }
            lines.append(
                f"MERGE (st:StepTemplate {{{_merge_properties({'stepKey': step_key})}}}) "
                f"SET st += {{{_merge_properties(step_properties)}}};"
            )
            lines.append(
                f"MATCH (wp:WorkflowPattern {{patternId: {_cypher_literal(pattern.pattern_id)}}}), "
                f"(st:StepTemplate {{stepKey: {_cypher_literal(step_key)}}}) "
                f"MERGE (wp)-[:HAS_STEP {{order: {step.order}}}]->(st);"
            )
    return _statement_lines(lines)


def _build_transform_section() -> str:
    lines = ["// Seed transform graph"]
    for source_type, destination_types in CAN_TRANSFORM_TO.items():
        for destination_type in destination_types:
            lines.append(
                f"MATCH (src:DataType {{typeId: {_cypher_literal(source_type)}}}), "
                f"(dst:DataType {{typeId: {_cypher_literal(destination_type)}}}) "
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


def ensure_bootstrap_data(
    *,
    uri: str,
    user: str,
    password: str,
    database: str | None = None,
    cypher: str | None = None,
) -> bool:
    driver = _create_driver(uri=uri, user=user, password=password)
    try:
        with driver.session(database=database) as session:
            result = session.run("MATCH (wp:WorkflowPattern) RETURN count(wp) AS count")
            row = result.single() if hasattr(result, "single") else None
            if row and int(row.get("count", 0)) > 0:
                return False
    finally:
        driver.close()

    apply_bootstrap_cypher(
        uri=uri,
        user=user,
        password=password,
        cypher=cypher,
        database=database,
    )
    return True


def _connection_settings_from_env(args: argparse.Namespace) -> tuple[str, str, str, str | None]:
    apply_local_dependency_defaults()
    uri = (args.uri or os.getenv("GEOFUSION_NEO4J_URI", "")).strip()
    user = (args.user or os.getenv("GEOFUSION_NEO4J_USER", "")).strip()
    password = (args.password or os.getenv("GEOFUSION_NEO4J_PASSWORD", "")).strip()
    database = (args.database or os.getenv("GEOFUSION_NEO4J_DATABASE", "")).strip() or None
    if not uri or not user or not password:
        raise RuntimeError("Neo4j connection settings are required for --apply/--ensure.")
    return uri, user, password, database


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate or apply the GeoFusion Neo4j bootstrap script.")
    parser.add_argument("--output", default="kg/bootstrap/neo4j_bootstrap.cypher", help="Path to the output cypher file.")
    parser.add_argument("--apply", action="store_true", help="Apply the bootstrap cypher to Neo4j.")
    parser.add_argument(
        "--ensure",
        action="store_true",
        help="Apply the bootstrap cypher only when WorkflowPattern seed data is missing.",
    )
    parser.add_argument("--uri", help="Neo4j bolt URI. Falls back to GEOFUSION_NEO4J_URI.")
    parser.add_argument("--user", help="Neo4j user. Falls back to GEOFUSION_NEO4J_USER.")
    parser.add_argument("--password", help="Neo4j password. Falls back to GEOFUSION_NEO4J_PASSWORD.")
    parser.add_argument("--database", help="Neo4j database. Defaults to the user's home database.")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_argument_parser()
    args = parser.parse_args(argv)

    path = write_bootstrap_cypher(Path(args.output))
    if args.ensure or args.apply:
        uri, user, password, database = _connection_settings_from_env(args)
        if args.ensure:
            changed = ensure_bootstrap_data(uri=uri, user=user, password=password, database=database, cypher=path.read_text(encoding="utf-8"))
            print("applied" if changed else "already-seeded")
            return
        count = apply_bootstrap_cypher(uri=uri, user=user, password=password, database=database, cypher=path.read_text(encoding="utf-8"))
        print(f"applied {count} statements")
        return

    print(path)


if __name__ == "__main__":
    main()
