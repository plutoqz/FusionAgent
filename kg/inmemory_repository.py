from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Set

from schemas.fusion import JobType

from kg.models import (
    AlgorithmNode,
    AlgorithmParameterSpec,
    DataTypeNode,
    DataSourceNode,
    DataNeedNode,
    DurableLearningRecord,
    ExecutionFeedback,
    KGContext,
    OutputSchemaPolicy,
    OutputRequirementNode,
    QoSPolicyNode,
    ScenarioProfileNode,
    RepairStrategyNode,
    TaskBundleNode,
    TaskNode,
    WorkflowPatternNode,
)
from kg.repository import KGRepository
from kg.seed_provider import load_seed_data


class InMemoryKGRepository(KGRepository):
    def __init__(
        self,
        algorithms: Optional[Dict[str, AlgorithmNode]] = None,
        patterns: Optional[List[WorkflowPatternNode]] = None,
        can_transform_to: Optional[Dict[str, List[str]]] = None,
        data_sources: Optional[List[DataSourceNode]] = None,
        data_types: Optional[Dict[str, DataTypeNode]] = None,
        parameter_specs: Optional[Dict[str, List[AlgorithmParameterSpec]]] = None,
        output_schema_policies: Optional[Dict[str, OutputSchemaPolicy]] = None,
        task_nodes: Optional[Dict[str, TaskNode]] = None,
        scenario_profiles: Optional[List[ScenarioProfileNode]] = None,
        task_bundles: Optional[Dict[str, TaskBundleNode]] = None,
        output_requirements: Optional[Dict[str, OutputRequirementNode]] = None,
        qos_policies: Optional[Dict[str, QoSPolicyNode]] = None,
        data_needs: Optional[List[DataNeedNode]] = None,
        repair_strategies: Optional[Dict[str, RepairStrategyNode]] = None,
        seed_manifest_path: Optional[Path] = None,
    ) -> None:
        seed_payload = load_seed_data(seed_manifest_path)
        self.algorithms = seed_payload["algorithms"] if algorithms is None else algorithms
        self.patterns = seed_payload["patterns"] if patterns is None else patterns
        self.can_transform_to = seed_payload["can_transform_to"] if can_transform_to is None else can_transform_to
        self.data_sources = seed_payload["data_sources"] if data_sources is None else data_sources
        self.data_types = seed_payload["data_types"] if data_types is None else data_types
        self.parameter_specs = seed_payload["parameter_specs"] if parameter_specs is None else parameter_specs
        self.output_schema_policies = (
            seed_payload["output_schema_policies"] if output_schema_policies is None else output_schema_policies
        )
        self.task_nodes = seed_payload["tasks"] if task_nodes is None else task_nodes
        self.scenario_profiles = seed_payload["scenario_profiles"] if scenario_profiles is None else scenario_profiles
        self.task_bundles = seed_payload["task_bundles"] if task_bundles is None else task_bundles
        self.output_requirements = seed_payload["output_requirements"] if output_requirements is None else output_requirements
        self.qos_policies = seed_payload["qos_policies"] if qos_policies is None else qos_policies
        self.data_needs = seed_payload["data_needs"] if data_needs is None else data_needs
        self.repair_strategies = seed_payload["repair_strategies"] if repair_strategies is None else repair_strategies
        self.feedback_history: List[ExecutionFeedback] = []
        self.durable_learning_records: List[DurableLearningRecord] = []
        self._pattern_scores: Dict[str, float] = {}
        self._algorithm_scores: Dict[str, float] = {}
        self._data_source_scores: Dict[str, float] = {}

    def list_algorithms(self) -> List[AlgorithmNode]:
        return [self.algorithms[algo_id] for algo_id in sorted(self.algorithms)]

    def list_workflow_patterns(self) -> List[WorkflowPatternNode]:
        return sorted(list(self.patterns), key=lambda item: item.pattern_id)

    def list_data_sources(self) -> List[DataSourceNode]:
        return sorted(list(self.data_sources), key=lambda item: item.source_id)

    def list_data_types(self) -> List[DataTypeNode]:
        return [self.data_types[type_id] for type_id in sorted(self.data_types)]

    def list_task_nodes(self) -> List[TaskNode]:
        return list(self.task_nodes.values())

    def get_scenario_profiles(self, disaster_type: Optional[str]) -> List[ScenarioProfileNode]:
        dtype = (disaster_type or "generic").lower()
        profiles = [
            profile
            for profile in self.scenario_profiles
            if dtype in (item.lower() for item in profile.disaster_types)
            or "generic" in (item.lower() for item in profile.disaster_types)
        ]
        profiles.sort(key=lambda item: item.profile_id)
        return profiles

    def list_task_bundles(self) -> List[TaskBundleNode]:
        return [self.task_bundles[bundle_id] for bundle_id in sorted(self.task_bundles)]

    def list_output_requirements(self) -> List[OutputRequirementNode]:
        return [self.output_requirements[requirement_id] for requirement_id in sorted(self.output_requirements)]

    def list_qos_policies(self) -> List[QoSPolicyNode]:
        return [self.qos_policies[policy_id] for policy_id in sorted(self.qos_policies)]

    def list_data_needs(self) -> List[DataNeedNode]:
        return list(self.data_needs)

    def list_repair_strategies(self) -> List[RepairStrategyNode]:
        return [self.repair_strategies[strategy_id] for strategy_id in sorted(self.repair_strategies)]

    def get_candidate_patterns(
        self,
        job_type: JobType,
        disaster_type: Optional[str],
        limit: int = 3,
    ) -> List[WorkflowPatternNode]:
        dtype = (disaster_type or "generic").lower()
        matches: List[WorkflowPatternNode] = []
        for pattern in self.patterns:
            if pattern.job_type != job_type:
                continue
            if dtype in (d.lower() for d in pattern.disaster_types) or "generic" in (
                d.lower() for d in pattern.disaster_types
            ):
                matches.append(pattern)
        matches.sort(key=lambda p: p.success_rate + self._pattern_scores.get(p.pattern_id, 0.0), reverse=True)
        return matches[:limit]

    def get_algorithm(self, algo_id: str) -> Optional[AlgorithmNode]:
        return self.algorithms.get(algo_id)

    def get_parameter_specs(self, algo_id: str) -> List[AlgorithmParameterSpec]:
        specs = self.parameter_specs.get(algo_id, [])
        # Return a stable order for UI/display and tests.
        return sorted(list(specs), key=lambda s: int(getattr(s, "order", 0)))

    def get_alternative_algorithms(self, algo_id: str, limit: int = 3) -> List[AlgorithmNode]:
        algo = self.get_algorithm(algo_id)
        if algo is None:
            return []
        alternatives = [self.algorithms[aid] for aid in algo.alternatives if aid in self.algorithms]
        alternatives.sort(key=lambda a: a.success_rate + self._algorithm_scores.get(a.algo_id, 0.0), reverse=True)
        return alternatives[:limit]

    def find_transform_path(self, from_type: str, to_type: str, max_depth: int = 3) -> List[str]:
        if from_type == to_type:
            return [from_type]

        queue: deque[tuple[str, List[str], int]] = deque([(from_type, [from_type], 0)])
        visited: Set[str] = {from_type}
        while queue:
            current, path, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for nxt in self.can_transform_to.get(current, []):
                if nxt == to_type:
                    return path + [nxt]
                if nxt in visited:
                    continue
                visited.add(nxt)
                queue.append((nxt, path + [nxt], depth + 1))
        return []

    def list_transform_edges(self) -> Dict[str, List[str]]:
        return {
            source_type: list(destination_types)
            for source_type, destination_types in sorted(self.can_transform_to.items())
        }

    def get_candidate_data_sources(
        self,
        job_type: JobType,
        disaster_type: Optional[str],
        required_type: str,
        limit: int = 3,
    ) -> List[DataSourceNode]:
        dtype = (disaster_type or "generic").lower()
        matches: List[DataSourceNode] = []
        for source in self.data_sources:
            if required_type not in source.supported_types:
                continue
            supported_disasters = [item.lower() for item in source.disaster_types]
            if dtype not in supported_disasters and "generic" not in supported_disasters:
                continue
            matches.append(source)
        matches.sort(
            key=lambda source: source.quality_score + self._data_source_scores.get(source.source_id, 0.0),
            reverse=True,
        )
        return matches[:limit]

    def get_output_schema_policy(self, output_type: str) -> Optional[OutputSchemaPolicy]:
        return self.output_schema_policies.get(output_type)

    def search_knowledge(self, query: str, limit: int = 5) -> List[Dict[str, object]]:
        tokens = [token for token in query.lower().split() if token]
        hits: List[Dict[str, object]] = []
        for algo in self.algorithms.values():
            haystack = f"{algo.algo_id} {algo.algo_name}".lower()
            score = sum(token in haystack for token in tokens)
            if score:
                hits.append({"kind": "algorithm", "id": algo.algo_id, "label": algo.algo_name, "score": score})
        for pattern in self.patterns:
            haystack = f"{pattern.pattern_id} {pattern.pattern_name}".lower()
            score = sum(token in haystack for token in tokens)
            if score:
                hits.append({"kind": "pattern", "id": pattern.pattern_id, "label": pattern.pattern_name, "score": score})
        for source in self.data_sources:
            haystack = f"{source.source_id} {source.source_name}".lower()
            score = sum(token in haystack for token in tokens)
            if score:
                hits.append({"kind": "data_source", "id": source.source_id, "label": source.source_name, "score": score})
        hits.sort(key=lambda item: int(item["score"]), reverse=True)
        return hits[:limit]

    def record_execution_feedback(self, feedback: ExecutionFeedback) -> None:
        self.feedback_history.append(feedback)
        delta = 0.2 if feedback.success else -0.15
        if feedback.pattern_id:
            self._pattern_scores[feedback.pattern_id] = self._pattern_scores.get(feedback.pattern_id, 0.0) + delta
        if feedback.algorithm_id:
            algo_delta = 0.15 if feedback.success else -0.1
            self._algorithm_scores[feedback.algorithm_id] = self._algorithm_scores.get(feedback.algorithm_id, 0.0) + algo_delta
        if feedback.selected_data_source:
            source_delta = 0.08 if feedback.success else -0.05
            self._data_source_scores[feedback.selected_data_source] = (
                self._data_source_scores.get(feedback.selected_data_source, 0.0) + source_delta
            )

    def record_durable_learning_record(self, record: DurableLearningRecord) -> None:
        updated: List[DurableLearningRecord] = []
        replaced = False
        for existing in self.durable_learning_records:
            if existing.record_id == record.record_id:
                updated.append(record)
                replaced = True
            else:
                updated.append(existing)
        if not replaced:
            updated.append(record)
        updated.sort(key=lambda item: ((item.created_at or ""), item.record_id), reverse=True)
        self.durable_learning_records = updated

    def list_durable_learning_records(
        self,
        *,
        job_type: Optional[JobType] = None,
        success: Optional[bool] = None,
        limit: int = 20,
    ) -> List[DurableLearningRecord]:
        if limit <= 0:
            return []
        records = self.durable_learning_records
        if job_type is not None:
            records = [record for record in records if record.job_type == job_type]
        if success is not None:
            records = [record for record in records if record.success is success]
        return list(records[:limit])

    def _collect_upstream_transform_types(self, target_types: Set[str], max_depth: int = 3) -> Set[str]:
        frontier = set(target_types)
        discovered = set(target_types)
        for _ in range(max(0, max_depth)):
            next_frontier: Set[str] = set()
            for source_type, dest_types in self.can_transform_to.items():
                if source_type in discovered:
                    continue
                if any(dest in frontier for dest in dest_types):
                    next_frontier.add(source_type)
            if not next_frontier:
                break
            discovered.update(next_frontier)
            frontier = next_frontier
        return discovered

    def build_context(self, job_type: JobType, disaster_type: Optional[str]) -> KGContext:
        patterns = self.get_candidate_patterns(job_type=job_type, disaster_type=disaster_type, limit=3)
        algo_ids = {step.algorithm_id for p in patterns for step in p.steps}
        algorithms = {aid: self.algorithms[aid] for aid in algo_ids if aid in self.algorithms}
        parameter_specs = {algo_id: self.get_parameter_specs(algo_id) for algo_id in sorted(algorithms)}
        required_types = {step.input_data_type for pattern in patterns for step in pattern.steps}
        output_types = {step.output_data_type for pattern in patterns for step in pattern.steps}
        upstream_types = self._collect_upstream_transform_types(required_types)
        for algo in self.algorithms.values():
            if algo.task_type != "transform":
                continue
            if algo.output_type not in upstream_types:
                continue
            if not any(input_type in upstream_types for input_type in algo.input_types):
                continue
            algorithms.setdefault(algo.algo_id, algo)
            parameter_specs.setdefault(algo.algo_id, self.get_parameter_specs(algo.algo_id))
        sources: Dict[str, DataSourceNode] = {}
        for required_type in sorted(required_types):
            for source in self.get_candidate_data_sources(
                job_type=job_type,
                disaster_type=disaster_type,
                required_type=required_type,
                limit=3,
            ):
                sources[source.source_id] = source
        output_schema_policies = {
            output_type: policy
            for output_type in sorted(output_types)
            if (policy := self.get_output_schema_policy(output_type)) is not None
        }
        task_bundles = self.list_task_bundles()
        output_requirements = {
            requirement.output_type: requirement
            for requirement in self.list_output_requirements()
        }
        return KGContext(
            patterns=patterns,
            algorithms=algorithms,
            data_types=self.list_data_types(),
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
            task_bundles=task_bundles,
            output_requirements=output_requirements,
            qos_policies={policy.policy_id: policy for policy in self.list_qos_policies()},
            data_needs=self.list_data_needs(),
            repair_strategies=self.list_repair_strategies(),
            disaster_type=disaster_type,
        )
