from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from schemas.fusion import JobType

from kg.models import (
    AlgorithmNode,
    AlgorithmParameterSpec,
    DataTypeNode,
    DataSourceNode,
    DataNeedNode,
    DurableLearningRecord,
    DurableLearningSummary,
    ExecutionFeedback,
    KGContext,
    OutputSchemaPolicy,
    OutputRequirementNode,
    QoSPolicyNode,
    RepairStrategyNode,
    ScenarioProfileNode,
    TaskBundleNode,
    TaskNode,
    WorkflowPatternNode,
)


class KGRepository(ABC):
    @abstractmethod
    def list_algorithms(self) -> List[AlgorithmNode]:
        raise NotImplementedError

    @abstractmethod
    def list_workflow_patterns(self) -> List[WorkflowPatternNode]:
        raise NotImplementedError

    @abstractmethod
    def list_data_sources(self) -> List[DataSourceNode]:
        raise NotImplementedError

    @abstractmethod
    def list_data_types(self) -> List[DataTypeNode]:
        raise NotImplementedError

    @abstractmethod
    def list_task_nodes(self) -> List[TaskNode]:
        raise NotImplementedError

    @abstractmethod
    def get_scenario_profiles(self, disaster_type: Optional[str]) -> List[ScenarioProfileNode]:
        raise NotImplementedError

    @abstractmethod
    def list_task_bundles(self) -> List[TaskBundleNode]:
        raise NotImplementedError

    @abstractmethod
    def list_output_requirements(self) -> List[OutputRequirementNode]:
        raise NotImplementedError

    @abstractmethod
    def list_qos_policies(self) -> List[QoSPolicyNode]:
        raise NotImplementedError

    @abstractmethod
    def list_data_needs(self) -> List[DataNeedNode]:
        raise NotImplementedError

    @abstractmethod
    def list_repair_strategies(self) -> List[RepairStrategyNode]:
        raise NotImplementedError

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
    def list_transform_edges(self) -> Dict[str, List[str]]:
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
        grouped_records: Dict[str, List[DurableLearningRecord]] = defaultdict(list)
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
            grouped_records[str(entity_id)].append(record)

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
        for summary in summaries:
            records_for_summary = grouped_records.get(summary.entity_id, [])
            summary.condition_key = _learning_condition_key(records_for_summary[0], summary.entity_id) if records_for_summary else ""
            summary.time_decayed_score = _time_decayed_success_score(records_for_summary)
            summary.recent_success_rate = _success_rate(records_for_summary)
            summary.quality_gate_pass_rate = _quality_gate_pass_rate(records_for_summary)
            summary.avg_latency_seconds = _avg_latency_seconds(records_for_summary)
            summary.trend = _learning_trend(records_for_summary, summary.recent_success_rate)
            if summary.total_runs >= 2:
                summary.adjustment = _clamp((summary.time_decayed_score - 0.5) * 0.2, -0.10, 0.10)

        summaries.sort(
            key=lambda item: (item.total_runs, item.last_run_at or "", item.entity_id),
            reverse=True,
        )
        return summaries[:limit]

    @abstractmethod
    def build_context(self, job_type: JobType, disaster_type: Optional[str]) -> KGContext:
        raise NotImplementedError


def _learning_condition_key(record: DurableLearningRecord, entity_id: str) -> str:
    metadata = record.metadata if isinstance(record.metadata, dict) else {}
    task = str(metadata.get("task_kind") or record.job_type.value)
    aoi_size = str(metadata.get("aoi_size_bucket") or metadata.get("aoi_class") or "unknown")
    source_coverage = str(metadata.get("source_coverage_bucket") or "unknown")
    failure_category = str(metadata.get("failure_category") or record.failure_reason or "none")
    quality_outcome = str(metadata.get("quality_outcome") or "unknown")
    return (
        f"task={task}|entity={entity_id}|aoi={aoi_size}|"
        f"source_coverage={source_coverage}|failure={failure_category}|quality={quality_outcome}"
    )


def _parse_learning_timestamp(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _time_decay_weight(created_at: str | None, newest_at: str | None, *, half_life_days: float = 30.0) -> float:
    created = _parse_learning_timestamp(created_at)
    newest = _parse_learning_timestamp(newest_at)
    if created is None or newest is None or half_life_days <= 0:
        return 1.0
    age_days = max(0.0, (newest - created).total_seconds() / 86_400.0)
    return 0.5 ** (age_days / half_life_days)


def _time_decayed_success_score(records: List[DurableLearningRecord]) -> float:
    if not records:
        return 0.0
    newest_at = max((record.created_at or "" for record in records), default=None)
    weighted_total = 0.0
    weighted_success = 0.0
    for record in records:
        weight = _time_decay_weight(record.created_at, newest_at)
        weighted_total += weight
        if record.success:
            weighted_success += weight
    if weighted_total <= 0:
        return 0.0
    return weighted_success / weighted_total


def _success_rate(records: List[DurableLearningRecord]) -> float:
    if not records:
        return 0.0
    return sum(1 for record in records if record.success) / len(records)


def _learning_trend(records: List[DurableLearningRecord], recent_success_rate: float) -> str:
    if len(records) < 2:
        return "stable"
    total_success_rate = _success_rate(records)
    delta = recent_success_rate - total_success_rate
    if delta >= 0.15:
        return "improving"
    if delta <= -0.15:
        return "degrading"
    return "stable"


def _quality_gate_pass_rate(records: List[DurableLearningRecord]) -> float:
    values = [
        record.metadata.get("quality_gate_accepted")
        for record in records
        if isinstance(record.metadata, dict) and "quality_gate_accepted" in record.metadata
    ]
    if not values:
        return 0.0
    return sum(1 for value in values if bool(value)) / len(values)


def _avg_latency_seconds(records: List[DurableLearningRecord]) -> float:
    values = []
    for record in records:
        if not isinstance(record.metadata, dict) or "latency_seconds" not in record.metadata:
            continue
        try:
            values.append(float(record.metadata["latency_seconds"]))
        except (TypeError, ValueError):
            continue
    if not values:
        return 0.0
    return sum(values) / len(values)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
