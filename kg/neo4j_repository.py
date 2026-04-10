from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from schemas.fusion import JobType

from kg.bootstrap import MANAGED_LABEL, resolve_graph_target
from kg.models import (
    AlgorithmNode,
    AlgorithmParameterSpec,
    DataSourceNode,
    DurableLearningRecord,
    ExecutionFeedback,
    KGContext,
    OutputSchemaPolicy,
    PatternStep,
    ScenarioProfileNode,
    TaskNode,
    WorkflowPatternNode,
)
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
        resolved = resolve_graph_target(uri=uri, user=user, password=password, database=database)
        return cls(uri=uri, user=user, password=password, database=resolved["database_used"])

    def close(self) -> None:
        self._driver.close()

    def _execute(self, cypher: str, **params: object) -> List[Dict[str, object]]:
        with self._driver.session(database=self.database) as session:
            result = session.run(cypher, params)
            return [dict(record) for record in result]

    @staticmethod
    def _parse_metadata_json(raw: object) -> Dict[str, object]:
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return dict(raw)
        if isinstance(raw, str):
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                return {}
            return payload if isinstance(payload, dict) else {}
        return {}

    def list_task_nodes(self) -> List[TaskNode]:
        rows = self._execute(
            f"""
            MATCH (task:Task:{MANAGED_LABEL})
            RETURN task
            ORDER BY task.taskId ASC
            """
        )
        return [
            TaskNode(
                task_id=str(row["task"].get("taskId")),
                task_name=str(row["task"].get("taskName", row["task"].get("taskId"))),
                category=str(row["task"].get("category", "unknown")),
                description=str(row["task"].get("description", "")),
            )
            for row in rows
        ]

    def get_scenario_profiles(self, disaster_type: Optional[str]) -> List[ScenarioProfileNode]:
        rows = self._execute(
            f"""
            MATCH (profile:ScenarioProfile:{MANAGED_LABEL})
            WHERE $disaster_type IS NULL
               OR $disaster_type IN profile.disasterTypes
               OR "generic" IN profile.disasterTypes
            RETURN profile
            ORDER BY profile.profileId ASC
            """,
            disaster_type=(disaster_type or None),
        )
        result: List[ScenarioProfileNode] = []
        for row in rows:
            profile = row["profile"]
            result.append(
                ScenarioProfileNode(
                    profile_id=str(profile.get("profileId")),
                    profile_name=str(profile.get("profileName", profile.get("profileId"))),
                    disaster_types=list(profile.get("disasterTypes", [])),
                    activated_tasks=list(profile.get("activatedTasks", [])),
                    preferred_output_fields=list(profile.get("preferredOutputFields", [])),
                    qos_priority=self._parse_metadata_json(profile.get("qosPriorityJson")),
                    metadata=self._parse_metadata_json(profile.get("metadataJson")),
                )
            )
        return result

    def get_candidate_patterns(
        self,
        job_type: JobType,
        disaster_type: Optional[str],
        limit: int = 3,
    ) -> List[WorkflowPatternNode]:
        rows = self._execute(
            f"""
            MATCH (wp:WorkflowPattern:{MANAGED_LABEL})
            WHERE wp.jobType = $job_type
              AND ($disaster_type IS NULL OR $disaster_type IN wp.disasterTypes OR "generic" IN wp.disasterTypes)
            OPTIONAL MATCH (wp)-[hs:HAS_STEP]->(st:StepTemplate:{MANAGED_LABEL})
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
                    metadata=self._parse_metadata_json(wp.get("metadataJson")),
                )
            )
        return patterns

    def get_algorithm(self, algo_id: str) -> Optional[AlgorithmNode]:
        rows = self._execute(
            f"""
            MATCH (a:Algorithm:{MANAGED_LABEL} {{algoId: $algo_id}})
            OPTIONAL MATCH (a)-[:ALTERNATIVE_TO]->(alt:Algorithm:{MANAGED_LABEL})
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
            accuracy_score=float(algo.get("accuracyScore")) if algo.get("accuracyScore") is not None else None,
            stability_score=float(algo.get("stabilityScore")) if algo.get("stabilityScore") is not None else None,
            usage_mode=str(algo.get("usageMode", "balanced")),
            metadata=self._parse_metadata_json(algo.get("metadataJson")),
            alternatives=[a for a in row.get("alternatives", []) if a],
        )

    def get_parameter_specs(self, algo_id: str) -> List[AlgorithmParameterSpec]:
        rows = self._execute(
            f"""
            MATCH (algo:Algorithm:{MANAGED_LABEL} {{algoId: $algo_id}})
            OPTIONAL MATCH (algo)-[hs:HAS_PARAMETER_SPEC]->(ps:AlgorithmParameterSpec:{MANAGED_LABEL})
            RETURN ps, hs
            ORDER BY coalesce(hs.order, ps.order, 0) ASC, ps.key ASC
            """,
            algo_id=algo_id,
        )
        specs: List[AlgorithmParameterSpec] = []
        for row in rows:
            ps = row.get("ps")
            if not ps:
                continue
            hs = row.get("hs") or {}

            min_value = ps.get("minValue", None)
            max_value = ps.get("maxValue", None)
            min_value = float(min_value) if min_value is not None else None
            max_value = float(max_value) if max_value is not None else None

            choices_raw = ps.get("choices", None)
            if choices_raw is None:
                choices = None
            elif isinstance(choices_raw, list):
                choices = choices_raw
            else:
                choices = [choices_raw]

            key = str(ps.get("key", ""))
            spec_id = ps.get("specId") or f"ps.{algo_id}.{key}"

            order = hs.get("order", None)
            if order is None:
                order = ps.get("order", 0)

            unit_raw = ps.get("unit", None)
            unit = None if unit_raw is None else str(unit_raw)

            specs.append(
                AlgorithmParameterSpec(
                    spec_id=str(spec_id),
                    algo_id=str(ps.get("algoId", algo_id)),
                    key=key,
                    label=str(ps.get("label", key)),
                    param_type=str(ps.get("paramType", "")),
                    default=ps.get("default", None),
                    min_value=min_value,
                    max_value=max_value,
                    unit=unit,
                    description=str(ps.get("description", "")),
                    required=bool(ps.get("required", False)),
                    choices=choices,
                    tunable=bool(ps.get("tunable", False)),
                    optimization_tags=list(ps.get("optimizationTags", [])),
                    order=int(order),
                )
            )
        return specs

    def get_alternative_algorithms(self, algo_id: str, limit: int = 3) -> List[AlgorithmNode]:
        rows = self._execute(
            f"""
            MATCH (:Algorithm:{MANAGED_LABEL} {{algoId: $algo_id}})-[:ALTERNATIVE_TO]->(alt:Algorithm:{MANAGED_LABEL})
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
                    accuracy_score=float(alt.get("accuracyScore")) if alt.get("accuracyScore") is not None else None,
                    stability_score=float(alt.get("stabilityScore")) if alt.get("stabilityScore") is not None else None,
                    usage_mode=str(alt.get("usageMode", "balanced")),
                    metadata=self._parse_metadata_json(alt.get("metadataJson")),
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
              (s:DataType:{MANAGED_LABEL} {{typeId: $from_type}})-[:CAN_TRANSFORM_TO*..{depth}]->(t:DataType:{MANAGED_LABEL} {{typeId: $to_type}})
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
            f"""
            MATCH (ds:DataSource:{MANAGED_LABEL})
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
                source_kind=str(row["ds"].get("sourceKind", "catalog")),
                quality_tier=str(row["ds"].get("qualityTier", "standard")),
                freshness_category=str(row["ds"].get("freshnessCategory", "static")),
                freshness_hours=int(row["ds"].get("freshnessHours")) if row["ds"].get("freshnessHours") is not None else None,
                freshness_score=(
                    float(row["ds"].get("freshnessScore")) if row["ds"].get("freshnessScore") is not None else None
                ),
                supported_job_types=list(row["ds"].get("supportedJobTypes", [])),
                supported_geometry_types=list(row["ds"].get("supportedGeometryTypes", [])),
                metadata=self._parse_metadata_json(row["ds"].get("metadataJson")),
            )
            for row in rows
        ]

    def get_output_schema_policy(self, output_type: str) -> Optional[OutputSchemaPolicy]:
        rows = self._execute(
            f"""
            MATCH (osp:OutputSchemaPolicy:{MANAGED_LABEL})-[:APPLIES_TO_OUTPUT_TYPE]->(dt:DataType:{MANAGED_LABEL} {{typeId: $output_type}})
            RETURN osp
            LIMIT 1
            """,
            output_type=output_type,
        )
        if not rows:
            return None
        osp = rows[0]["osp"]
        return OutputSchemaPolicy(
            policy_id=str(osp.get("policyId")),
            output_type=str(osp.get("outputType", output_type)),
            job_type=JobType(str(osp.get("jobType"))),
            retention_mode=str(osp.get("retentionMode", "preserve_listed")),
            required_fields=list(osp.get("requiredFields", [])),
            optional_fields=list(osp.get("optionalFields", [])),
            rename_hints=self._parse_metadata_json(osp.get("renameHintsJson")),
            compatibility_basis=str(osp.get("compatibilityBasis", "field_names")),
            metadata=self._parse_metadata_json(osp.get("metadataJson")),
        )

    def search_knowledge(self, query: str, limit: int = 5) -> List[Dict[str, object]]:
        rows = self._execute(
            f"""
            CALL {{
              CALL db.index.fulltext.queryNodes("algo_search", $query) YIELD node, score
              WITH node, score WHERE $managed_label IN labels(node)
              RETURN "algorithm" AS kind, node.algoId AS id, node.algoName AS label, score
              UNION
              CALL db.index.fulltext.queryNodes("wp_search", $query) YIELD node, score
              WITH node, score WHERE $managed_label IN labels(node)
              RETURN "pattern" AS kind, node.patternId AS id, node.patternName AS label, score
              UNION
              CALL db.index.fulltext.queryNodes("ds_search", $query) YIELD node, score
              WITH node, score WHERE $managed_label IN labels(node)
              RETURN "data_source" AS kind, node.sourceId AS id, node.sourceName AS label, score
            }}
            RETURN kind, id, label, score
            ORDER BY score DESC
            LIMIT $limit
            """,
            query=query,
            limit=limit,
            managed_label=MANAGED_LABEL,
        )
        return rows

    def record_execution_feedback(self, feedback: ExecutionFeedback) -> None:
        self._execute(
            f"""
            MERGE (run:WorkflowInstance {{instanceId: $run_id}})
            SET run:{MANAGED_LABEL}
            SET run.jobType = $job_type,
                run.disasterType = $disaster_type,
                run.triggerType = $trigger_type,
                run.success = $success,
                run.repaired = $repaired,
                run.repairCount = $repair_count,
                run.failureReason = $failure_reason,
                run.graphNamespace = "fusionagent"
            WITH run
            OPTIONAL MATCH (wp:WorkflowPattern:{MANAGED_LABEL} {{patternId: $pattern_id}})
            OPTIONAL MATCH (algo:Algorithm:{MANAGED_LABEL} {{algoId: $algorithm_id}})
            OPTIONAL MATCH (ds:DataSource:{MANAGED_LABEL} {{sourceId: $selected_data_source}})
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

    def record_durable_learning_record(self, record: DurableLearningRecord) -> None:
        self._execute(
            f"""
            MERGE (run:WorkflowInstance {{instanceId: $run_id}})
            SET run:{MANAGED_LABEL}
            MERGE (dlr:DurableLearningRecord {{recordId: $record_id}})
            SET dlr:{MANAGED_LABEL}
            SET dlr.runId = $run_id,
                dlr.jobType = $job_type,
                dlr.triggerType = $trigger_type,
                dlr.success = $success,
                dlr.disasterType = $disaster_type,
                dlr.patternId = $pattern_id,
                dlr.algorithmId = $algorithm_id,
                dlr.selectedDataSource = $selected_data_source,
                dlr.outputDataType = $output_data_type,
                dlr.targetCrs = $target_crs,
                dlr.repaired = $repaired,
                dlr.repairCount = $repair_count,
                dlr.failureReason = $failure_reason,
                dlr.planRevision = $plan_revision,
                dlr.metadataJson = $metadata_json,
                dlr.createdAt = $created_at,
                dlr.graphNamespace = "fusionagent"
            MERGE (run)-[:HAS_DURABLE_LEARNING]->(dlr)
            WITH dlr
            OPTIONAL MATCH (wp:WorkflowPattern:{MANAGED_LABEL} {{patternId: $pattern_id}})
            OPTIONAL MATCH (algo:Algorithm:{MANAGED_LABEL} {{algoId: $algorithm_id}})
            OPTIONAL MATCH (ds:DataSource:{MANAGED_LABEL} {{sourceId: $selected_data_source}})
            FOREACH (_ IN CASE WHEN wp IS NULL THEN [] ELSE [1] END | MERGE (dlr)-[:SUMMARIZES_PATTERN]->(wp))
            FOREACH (_ IN CASE WHEN algo IS NULL THEN [] ELSE [1] END | MERGE (dlr)-[:SUMMARIZES_ALGORITHM]->(algo))
            FOREACH (_ IN CASE WHEN ds IS NULL THEN [] ELSE [1] END | MERGE (dlr)-[:SUMMARIZES_SOURCE]->(ds))
            """,
            record_id=record.record_id,
            run_id=record.run_id,
            job_type=record.job_type.value,
            trigger_type=record.trigger_type,
            success=record.success,
            disaster_type=record.disaster_type,
            pattern_id=record.pattern_id,
            algorithm_id=record.algorithm_id,
            selected_data_source=record.selected_data_source,
            output_data_type=record.output_data_type,
            target_crs=record.target_crs,
            repaired=record.repaired,
            repair_count=record.repair_count,
            failure_reason=record.failure_reason,
            plan_revision=record.plan_revision,
            metadata_json=(json.dumps(record.metadata, ensure_ascii=False, sort_keys=True) if record.metadata else None),
            created_at=record.created_at,
        )

    def list_durable_learning_records(
        self,
        *,
        job_type: Optional[JobType] = None,
        success: Optional[bool] = None,
        limit: int = 20,
    ) -> List[DurableLearningRecord]:
        rows = self._execute(
            f"""
            MATCH (dlr:DurableLearningRecord:{MANAGED_LABEL})
            WHERE ($job_type IS NULL OR dlr.jobType = $job_type)
              AND ($success IS NULL OR dlr.success = $success)
            RETURN dlr
            ORDER BY coalesce(dlr.createdAt, "") DESC, dlr.recordId DESC
            LIMIT $limit
            """,
            job_type=(job_type.value if job_type is not None else None),
            success=success,
            limit=limit,
        )
        result: List[DurableLearningRecord] = []
        for row in rows:
            dlr = row["dlr"]
            metadata: Dict[str, object] = {}
            raw_metadata = dlr.get("metadataJson")
            if raw_metadata:
                try:
                    metadata = json.loads(str(raw_metadata))
                except json.JSONDecodeError:
                    metadata = {}
            result.append(
                DurableLearningRecord(
                    record_id=str(dlr.get("recordId")),
                    run_id=str(dlr.get("runId")),
                    job_type=JobType(str(dlr.get("jobType"))),
                    trigger_type=str(dlr.get("triggerType", "")),
                    success=bool(dlr.get("success", False)),
                    disaster_type=(str(dlr.get("disasterType")) if dlr.get("disasterType") is not None else None),
                    pattern_id=(str(dlr.get("patternId")) if dlr.get("patternId") is not None else None),
                    algorithm_id=(str(dlr.get("algorithmId")) if dlr.get("algorithmId") is not None else None),
                    selected_data_source=(
                        str(dlr.get("selectedDataSource")) if dlr.get("selectedDataSource") is not None else None
                    ),
                    output_data_type=(str(dlr.get("outputDataType")) if dlr.get("outputDataType") is not None else None),
                    target_crs=(str(dlr.get("targetCrs")) if dlr.get("targetCrs") is not None else None),
                    repaired=bool(dlr.get("repaired", False)),
                    repair_count=int(dlr.get("repairCount", 0)),
                    failure_reason=(str(dlr.get("failureReason")) if dlr.get("failureReason") is not None else None),
                    plan_revision=int(dlr.get("planRevision", 0)),
                    metadata=metadata,
                    created_at=(str(dlr.get("createdAt")) if dlr.get("createdAt") is not None else None),
                )
            )
        return result

    def build_context(self, job_type: JobType, disaster_type: Optional[str]) -> KGContext:
        patterns = self.get_candidate_patterns(job_type=job_type, disaster_type=disaster_type, limit=3)
        algorithms: Dict[str, AlgorithmNode] = {}
        for pattern in patterns:
            for step in pattern.steps:
                algo = self.get_algorithm(step.algorithm_id)
                if algo:
                    algorithms[algo.algo_id] = algo
        parameter_specs = {algo_id: self.get_parameter_specs(algo_id) for algo_id in sorted(algorithms)}
        required_types = {step.input_data_type for pattern in patterns for step in pattern.steps}
        output_types = {step.output_data_type for pattern in patterns for step in pattern.steps}
        sources: Dict[str, DataSourceNode] = {}
        for required_type in required_types:
            for source in self.get_candidate_data_sources(job_type, disaster_type, required_type, limit=3):
                sources[source.source_id] = source
        output_schema_policies = {
            output_type: policy
            for output_type in sorted(output_types)
            if (policy := self.get_output_schema_policy(output_type)) is not None
        }
        return KGContext(
            patterns=patterns,
            algorithms=algorithms,
            parameter_specs=parameter_specs,
            data_sources=list(sources.values()),
            output_schema_policies=output_schema_policies,
            durable_learning_summaries=self.summarize_durable_learning_records(
                job_type=job_type,
                disaster_type=disaster_type,
                limit=5,
            ),
            task_nodes=self.list_task_nodes(),
            scenario_profiles=self.get_scenario_profiles(disaster_type),
            disaster_type=disaster_type,
        )
