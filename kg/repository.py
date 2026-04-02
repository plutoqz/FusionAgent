from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from schemas.fusion import JobType

from kg.models import AlgorithmNode, DataSourceNode, ExecutionFeedback, KGContext, WorkflowPatternNode


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
    def search_knowledge(self, query: str, limit: int = 5) -> List[Dict[str, object]]:
        raise NotImplementedError

    @abstractmethod
    def record_execution_feedback(self, feedback: ExecutionFeedback) -> None:
        raise NotImplementedError

    @abstractmethod
    def build_context(self, job_type: JobType, disaster_type: Optional[str]) -> KGContext:
        raise NotImplementedError
