from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Set

from schemas.fusion import JobType

from kg.models import (
    AlgorithmNode,
    AlgorithmParameterSpec,
    DataSourceNode,
    DurableLearningRecord,
    ExecutionFeedback,
    KGContext,
    OutputSchemaPolicy,
    WorkflowPatternNode,
)
from kg.repository import KGRepository
from kg.seed import ALGORITHMS, CAN_TRANSFORM_TO, DATA_SOURCES, OUTPUT_SCHEMA_POLICIES, PARAMETER_SPECS, WORKFLOW_PATTERNS


class InMemoryKGRepository(KGRepository):
    def __init__(
        self,
        algorithms: Optional[Dict[str, AlgorithmNode]] = None,
        patterns: Optional[List[WorkflowPatternNode]] = None,
        can_transform_to: Optional[Dict[str, List[str]]] = None,
        data_sources: Optional[List[DataSourceNode]] = None,
        parameter_specs: Optional[Dict[str, List[AlgorithmParameterSpec]]] = None,
        output_schema_policies: Optional[Dict[str, OutputSchemaPolicy]] = None,
    ) -> None:
        self.algorithms = ALGORITHMS if algorithms is None else algorithms
        self.patterns = WORKFLOW_PATTERNS if patterns is None else patterns
        self.can_transform_to = CAN_TRANSFORM_TO if can_transform_to is None else can_transform_to
        self.data_sources = DATA_SOURCES if data_sources is None else data_sources
        self.parameter_specs = PARAMETER_SPECS if parameter_specs is None else parameter_specs
        self.output_schema_policies = OUTPUT_SCHEMA_POLICIES if output_schema_policies is None else output_schema_policies
        self.feedback_history: List[ExecutionFeedback] = []
        self.durable_learning_records: List[DurableLearningRecord] = []
        self._pattern_scores: Dict[str, float] = {}
        self._algorithm_scores: Dict[str, float] = {}
        self._data_source_scores: Dict[str, float] = {}

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

    def build_context(self, job_type: JobType, disaster_type: Optional[str]) -> KGContext:
        patterns = self.get_candidate_patterns(job_type=job_type, disaster_type=disaster_type, limit=3)
        algo_ids = {step.algorithm_id for p in patterns for step in p.steps}
        algorithms = {aid: self.algorithms[aid] for aid in algo_ids if aid in self.algorithms}
        parameter_specs = {algo_id: self.get_parameter_specs(algo_id) for algo_id in sorted(algorithms)}
        required_types = {step.input_data_type for pattern in patterns for step in pattern.steps}
        output_types = {step.output_data_type for pattern in patterns for step in pattern.steps}
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
            disaster_type=disaster_type,
        )
