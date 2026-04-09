from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Dict, List, Optional

from schemas.fusion import JobType

from kg.models import (
    AlgorithmNode,
    AlgorithmParameterSpec,
    DataSourceNode,
    DurableLearningRecord,
    DurableLearningSummary,
    ExecutionFeedback,
    KGContext,
    OutputSchemaPolicy,
    WorkflowPatternNode,
)


class KGRepository(ABC):
    @abstractmethod
    def get_candidate_patterns(
        self,
        job_type: JobType,
        disaster_type: Optional[str],
        limit: int = 3,
    ) -> List[WorkflowPatternNode]:
        raise NotImplementedError

    @abstractmethod
    def get_algorithm(self, algo_id: str) -> Optional[AlgorithmNode]:
        raise NotImplementedError

    @abstractmethod
    def get_parameter_specs(self, algo_id: str) -> List[AlgorithmParameterSpec]:
        raise NotImplementedError

    @abstractmethod
    def get_alternative_algorithms(self, algo_id: str, limit: int = 3) -> List[AlgorithmNode]:
        raise NotImplementedError

    @abstractmethod
    def find_transform_path(self, from_type: str, to_type: str, max_depth: int = 3) -> List[str]:
        raise NotImplementedError

    @abstractmethod
    def get_candidate_data_sources(
        self,
        job_type: JobType,
        disaster_type: Optional[str],
        required_type: str,
        limit: int = 3,
    ) -> List[DataSourceNode]:
        raise NotImplementedError

    @abstractmethod
    def get_output_schema_policy(self, output_type: str) -> Optional[OutputSchemaPolicy]:
        raise NotImplementedError

    @abstractmethod
    def search_knowledge(self, query: str, limit: int = 5) -> List[Dict[str, object]]:
        raise NotImplementedError

    @abstractmethod
    def record_execution_feedback(self, feedback: ExecutionFeedback) -> None:
        raise NotImplementedError

    @abstractmethod
    def record_durable_learning_record(self, record: DurableLearningRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_durable_learning_records(
        self,
        *,
        job_type: Optional[JobType] = None,
        success: Optional[bool] = None,
        limit: int = 20,
    ) -> List[DurableLearningRecord]:
        raise NotImplementedError

    def summarize_durable_learning_records(
        self,
        *,
        job_type: Optional[JobType] = None,
        disaster_type: Optional[str] = None,
        limit: int = 5,
    ) -> Dict[str, List[DurableLearningSummary]]:
        if limit <= 0:
            return {"patterns": [], "algorithms": [], "data_sources": []}

        records = self.list_durable_learning_records(job_type=job_type, success=None, limit=max(limit * 20, 100))
        if disaster_type is not None:
            records = [
                record
                for record in records
                if (record.disaster_type or "").lower() == disaster_type.lower()
            ]

        return {
            "patterns": self._aggregate_learning_dimension(records, entity_kind="pattern", attr_name="pattern_id", limit=limit),
            "algorithms": self._aggregate_learning_dimension(records, entity_kind="algorithm", attr_name="algorithm_id", limit=limit),
            "data_sources": self._aggregate_learning_dimension(
                records,
                entity_kind="data_source",
                attr_name="selected_data_source",
                limit=limit,
            ),
        }

    @staticmethod
    def _aggregate_learning_dimension(
        records: List[DurableLearningRecord],
        *,
        entity_kind: str,
        attr_name: str,
        limit: int,
    ) -> List[DurableLearningSummary]:
        grouped: Dict[str, DurableLearningSummary] = {}
        last_failure_at: Dict[str, str] = defaultdict(str)

        for record in records:
            entity_id = getattr(record, attr_name, None)
            if not entity_id:
                continue
            summary = grouped.get(entity_id)
            if summary is None:
                summary = DurableLearningSummary(
                    entity_kind=entity_kind,
                    entity_id=str(entity_id),
                    job_type=record.job_type,
                    disaster_type=record.disaster_type,
                )
                grouped[entity_id] = summary

            summary.total_runs += 1
            if record.success:
                summary.success_count += 1
            else:
                summary.failure_count += 1
            if record.repaired:
                summary.repaired_count += 1
            if (record.created_at or "") >= (summary.last_run_at or ""):
                summary.last_run_at = record.created_at
            if not record.success and record.failure_reason and (record.created_at or "") >= last_failure_at[entity_id]:
                last_failure_at[entity_id] = record.created_at or ""
                summary.last_failure_reason = record.failure_reason

        summaries = list(grouped.values())
        summaries.sort(
            key=lambda item: (item.total_runs, item.last_run_at or "", item.entity_id),
            reverse=True,
        )
        return summaries[:limit]

    @abstractmethod
    def build_context(self, job_type: JobType, disaster_type: Optional[str]) -> KGContext:
        raise NotImplementedError
