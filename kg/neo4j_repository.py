from __future__ import annotations

import os
from typing import Dict, List, Optional

from schemas.fusion import JobType

from kg.models import AlgorithmNode, DataSourceNode, ExecutionFeedback, KGContext, PatternStep, WorkflowPatternNode
from kg.repository import KGRepository


class Neo4jKGRepository(KGRepository):
    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        database: Optional[str] = None,
    ) -> None:
        try:
            from neo4j import GraphDatabase  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("neo4j package is required for Neo4jKGRepository") from exc

        self._GraphDatabase = GraphDatabase
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self.database = database

    @classmethod
    def from_env(cls) -> Optional["Neo4jKGRepository"]:
        uri = os.getenv("GEOFUSION_NEO4J_URI")
        user = os.getenv("GEOFUSION_NEO4J_USER")
        password = os.getenv("GEOFUSION_NEO4J_PASSWORD")
        database = os.getenv("GEOFUSION_NEO4J_DATABASE")
        if not uri or not user or not password:
            return None
        return cls(uri=uri, user=user, password=password, database=database)

    def close(self) -> None:
        self._driver.close()

    def _execute(self, cypher: str, **params: object) -> List[Dict[str, object]]:
        with self._driver.session(database=self.database) as session:
            # Pass Neo4j parameters as a dedicated dict so keys like "query"
            # do not collide with the driver's run(query, ...) signature.
            result = session.run(cypher, params)
            return [dict(record) for record in result]

    def get_candidate_patterns(
        self,
        job_type: JobType,
        disaster_type: Optional[str],
        limit: int = 3,
    ) -> List[WorkflowPatternNode]:
        rows = self._execute(
            """
            MATCH (wp:WorkflowPattern)
            WHERE wp.jobType = $job_type
              AND ($disaster_type IS NULL OR $disaster_type IN wp.disasterTypes OR "generic" IN wp.disasterTypes)
            OPTIONAL MATCH (wp)-[hs:HAS_STEP]->(st:StepTemplate)
            WITH wp, st, hs ORDER BY hs.order ASC
            RETURN wp, collect(st) AS steps
            ORDER BY wp.successRate DESC
            LIMIT $limit
            """,
            job_type=job_type.value,
            disaster_type=(disaster_type or None),
            limit=limit,
        )
        patterns: List[WorkflowPatternNode] = []
        for row in rows:
            wp = row["wp"]
            step_nodes = row["steps"] or []
            steps: List[PatternStep] = []
            for idx, sn in enumerate(step_nodes, start=1):
                if sn is None:
                    continue
                steps.append(
                    PatternStep(
                        order=int(sn.get("order", idx)),
                        name=str(sn.get("name", f"step_{idx}")),
                        algorithm_id=str(sn.get("algorithmId", "")),
                        input_data_type=str(sn.get("inputDataType", "dt.raw.vector")),
                        output_data_type=str(sn.get("outputDataType", "dt.raw.vector")),
                        data_source_id=str(sn.get("dataSourceId", "upload.bundle")),
                        depends_on=list(sn.get("dependsOn", [])),
                        is_optional=bool(sn.get("isOptional", False)),
                    )
                )
            patterns.append(
                WorkflowPatternNode(
                    pattern_id=str(wp.get("patternId")),
                    pattern_name=str(wp.get("patternName")),
                    job_type=job_type,
                    disaster_types=list(wp.get("disasterTypes", ["generic"])),
                    steps=steps,
                    success_rate=float(wp.get("successRate", 0.0)),
                    metadata={"source": "neo4j"},
                )
            )
        return patterns

    def get_algorithm(self, algo_id: str) -> Optional[AlgorithmNode]:
        rows = self._execute(
            """
            MATCH (a:Algorithm {algoId: $algo_id})
            OPTIONAL MATCH (a)-[:ALTERNATIVE_TO]->(alt:Algorithm)
            RETURN a AS algo, collect(alt.algoId) AS alternatives
            LIMIT 1
            """,
            algo_id=algo_id,
        )
        if not rows:
            return None
        row = rows[0]
        algo = row["algo"]
        return AlgorithmNode(
            algo_id=str(algo.get("algoId")),
            algo_name=str(algo.get("algoName", algo_id)),
            input_types=list(algo.get("inputTypes", [])),
            output_type=str(algo.get("outputType", "")),
            task_type=str(algo.get("taskType", "")),
            tool_ref=str(algo.get("toolRef", "")),
            success_rate=float(algo.get("successRate", 0.0)),
            alternatives=[a for a in row.get("alternatives", []) if a],
        )

    def get_alternative_algorithms(self, algo_id: str, limit: int = 3) -> List[AlgorithmNode]:
        rows = self._execute(
            """
            MATCH (:Algorithm {algoId: $algo_id})-[:ALTERNATIVE_TO]->(alt:Algorithm)
            RETURN alt
            ORDER BY alt.successRate DESC
            LIMIT $limit
            """,
            algo_id=algo_id,
            limit=limit,
        )
        result: List[AlgorithmNode] = []
        for row in rows:
            alt = row["alt"]
            result.append(
                AlgorithmNode(
                    algo_id=str(alt.get("algoId")),
                    algo_name=str(alt.get("algoName", "")),
                    input_types=list(alt.get("inputTypes", [])),
                    output_type=str(alt.get("outputType", "")),
                    task_type=str(alt.get("taskType", "")),
                    tool_ref=str(alt.get("toolRef", "")),
                    success_rate=float(alt.get("successRate", 0.0)),
                    alternatives=[],
                )
            )
        return result

    def find_transform_path(self, from_type: str, to_type: str, max_depth: int = 3) -> List[str]:
        if from_type == to_type:
            return [from_type]
        depth = max(1, int(max_depth))
        rows = self._execute(
            f"""
            MATCH p = shortestPath(
              (s:DataType {{typeId: $from_type}})-[:CAN_TRANSFORM_TO*..{depth}]->(t:DataType {{typeId: $to_type}})
            )
            RETURN [n IN nodes(p) | n.typeId] AS path
            LIMIT 1
            """,
            from_type=from_type,
            to_type=to_type,
        )
        if not rows:
            return []
        return list(rows[0].get("path", []))

    def get_candidate_data_sources(
        self,
        job_type: JobType,
        disaster_type: Optional[str],
        required_type: str,
        limit: int = 3,
    ) -> List[DataSourceNode]:
        rows = self._execute(
            """
            MATCH (ds:DataSource)
            WHERE $required_type IN ds.supportedTypes
              AND ($disaster_type IS NULL OR $disaster_type IN ds.disasterTypes OR "generic" IN ds.disasterTypes)
            RETURN ds
            ORDER BY coalesce(ds.qualityScore, 0.0) DESC
            LIMIT $limit
            """,
            job_type=job_type.value,
            disaster_type=(disaster_type or None),
            required_type=required_type,
            limit=limit,
        )
        return [
            DataSourceNode(
                source_id=str(row["ds"].get("sourceId")),
                source_name=str(row["ds"].get("sourceName", row["ds"].get("sourceId"))),
                supported_types=list(row["ds"].get("supportedTypes", [])),
                disaster_types=list(row["ds"].get("disasterTypes", [])),
                quality_score=float(row["ds"].get("qualityScore", 0.0)),
                metadata={"source": "neo4j"},
            )
            for row in rows
        ]

    def search_knowledge(self, query: str, limit: int = 5) -> List[Dict[str, object]]:
        rows = self._execute(
            """
            CALL {
              CALL db.index.fulltext.queryNodes("algo_search", $query) YIELD node, score
              RETURN "algorithm" AS kind, node.algoId AS id, node.algoName AS label, score
              UNION
              CALL db.index.fulltext.queryNodes("wp_search", $query) YIELD node, score
              RETURN "pattern" AS kind, node.patternId AS id, node.patternName AS label, score
              UNION
              CALL db.index.fulltext.queryNodes("ds_search", $query) YIELD node, score
              RETURN "data_source" AS kind, node.sourceId AS id, node.sourceName AS label, score
            }
            RETURN kind, id, label, score
            ORDER BY score DESC
            LIMIT $limit
            """,
            query=query,
            limit=limit,
        )
        return rows

    def record_execution_feedback(self, feedback: ExecutionFeedback) -> None:
        self._execute(
            """
            MERGE (run:WorkflowInstance {instanceId: $run_id})
            SET run.jobType = $job_type,
                run.disasterType = $disaster_type,
                run.triggerType = $trigger_type,
                run.success = $success,
                run.repaired = $repaired,
                run.repairCount = $repair_count,
                run.failureReason = $failure_reason
            WITH run
            OPTIONAL MATCH (wp:WorkflowPattern {patternId: $pattern_id})
            OPTIONAL MATCH (algo:Algorithm {algoId: $algorithm_id})
            OPTIONAL MATCH (ds:DataSource {sourceId: $selected_data_source})
            FOREACH (_ IN CASE WHEN wp IS NULL THEN [] ELSE [1] END | MERGE (run)-[:INSTANTIATES]->(wp))
            FOREACH (_ IN CASE WHEN algo IS NULL THEN [] ELSE [1] END | MERGE (run)-[:USED_ALGORITHM]->(algo))
            FOREACH (_ IN CASE WHEN ds IS NULL THEN [] ELSE [1] END | MERGE (run)-[:USED_SOURCE]->(ds))
            """,
            run_id=feedback.run_id,
            job_type=feedback.job_type.value,
            disaster_type=feedback.disaster_type,
            trigger_type=feedback.trigger_type,
            success=feedback.success,
            repaired=feedback.repaired,
            repair_count=feedback.repair_count,
            failure_reason=feedback.failure_reason,
            pattern_id=feedback.pattern_id,
            algorithm_id=feedback.algorithm_id,
            selected_data_source=feedback.selected_data_source,
        )

    def build_context(self, job_type: JobType, disaster_type: Optional[str]) -> KGContext:
        patterns = self.get_candidate_patterns(job_type=job_type, disaster_type=disaster_type, limit=3)
        algorithms: Dict[str, AlgorithmNode] = {}
        for pattern in patterns:
            for step in pattern.steps:
                algo = self.get_algorithm(step.algorithm_id)
                if algo:
                    algorithms[algo.algo_id] = algo
        required_types = {step.input_data_type for pattern in patterns for step in pattern.steps}
        sources: Dict[str, DataSourceNode] = {}
        for required_type in required_types:
            for source in self.get_candidate_data_sources(job_type, disaster_type, required_type, limit=3):
                sources[source.source_id] = source
        return KGContext(
            patterns=patterns,
            algorithms=algorithms,
            data_sources=list(sources.values()),
            disaster_type=disaster_type,
        )
