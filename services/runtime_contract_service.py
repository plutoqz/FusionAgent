from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from agent.tooling import ToolRegistry, build_default_tool_registry
from kg.models import DataSourceNode, WorkflowPatternNode
from kg.repository import KGRepository


BLOCKED_ALGORITHM_STATUSES = {"deprecated", "reservation_only"}
RESEARCH_ONLY_STATUSES = {"research_utility"}
BLOCKED_SOURCE_STATUSES = {"reservation_only", "deprecated"}


@dataclass(frozen=True)
class RuntimeContractDecision:
    allowed: bool
    reason_code: str | None = None
    message: str = ""
    runtime_status: str | None = None
    selectable_now: bool | None = None
    gap_severity: str = "none"
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason_code": self.reason_code,
            "message": self.message,
            "runtime_status": self.runtime_status,
            "selectable_now": self.selectable_now,
            "gap_severity": self.gap_severity,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class RuntimeContractFilterResult:
    allowed_ids: list[str]
    skipped: list[dict[str, Any]]


class RuntimeContractService:
    def __init__(self, kg_repo: KGRepository, *, tool_registry: ToolRegistry | None = None) -> None:
        self.kg_repo = kg_repo
        self.tool_registry = tool_registry or build_default_tool_registry()

    def evaluate_algorithm(
        self,
        algorithm_id: str,
        *,
        surface: str,
        require_tool: bool = True,
        allow_research_utility: bool = False,
    ) -> RuntimeContractDecision:
        algo = self.kg_repo.get_algorithm(algorithm_id)
        if algo is None:
            return RuntimeContractDecision(
                allowed=False,
                reason_code="UNKNOWN_ALGORITHM",
                message=f"Algorithm not found in KG: {algorithm_id}",
                gap_severity="unguarded",
                evidence={"algorithm_id": algorithm_id, "surface": surface},
            )

        metadata = dict(algo.metadata or {})
        runtime_status = str(metadata.get("runtime_status") or "").strip().lower() or None
        selectable_now = metadata.get("selectable_now")
        selectable_bool = None if selectable_now is None else bool(selectable_now)
        evidence: dict[str, Any] = {
            "algorithm_id": algorithm_id,
            "surface": surface,
            "usage_mode": algo.usage_mode,
            "metadata": metadata,
        }
        if metadata.get("deprecated_by"):
            evidence["deprecated_by"] = metadata.get("deprecated_by")

        if runtime_status is None:
            return RuntimeContractDecision(
                allowed=False,
                reason_code="MISSING_RUNTIME_STATUS",
                message=f"Algorithm lacks runtime_status metadata: {algorithm_id}",
                runtime_status=None,
                selectable_now=selectable_bool,
                gap_severity="unguarded",
                evidence=evidence,
            )
        if runtime_status == "deprecated" or str(algo.usage_mode).lower() == "deprecated":
            return RuntimeContractDecision(
                allowed=False,
                reason_code="DEPRECATED_ALGORITHM",
                message=f"Algorithm is deprecated: {algorithm_id}",
                runtime_status=runtime_status,
                selectable_now=selectable_bool,
                gap_severity="fail_soft",
                evidence=evidence,
            )
        if runtime_status in BLOCKED_ALGORITHM_STATUSES:
            reason_code = "RESERVED_ALGORITHM" if runtime_status == "reservation_only" else "UNSELECTABLE_ALGORITHM"
            return RuntimeContractDecision(
                allowed=False,
                reason_code=reason_code,
                message=f"Algorithm is not executable at runtime: {algorithm_id}",
                runtime_status=runtime_status,
                selectable_now=selectable_bool,
                gap_severity="fail_soft",
                evidence=evidence,
            )
        if selectable_bool is False:
            return RuntimeContractDecision(
                allowed=False,
                reason_code="UNSELECTABLE_ALGORITHM",
                message=f"Algorithm is marked selectable_now=false: {algorithm_id}",
                runtime_status=runtime_status,
                selectable_now=False,
                gap_severity="fail_soft",
                evidence=evidence,
            )
        if runtime_status in RESEARCH_ONLY_STATUSES and not allow_research_utility:
            return RuntimeContractDecision(
                allowed=False,
                reason_code="RESEARCH_UTILITY_ALGORITHM",
                message=f"Algorithm is research-only for this surface: {algorithm_id}",
                runtime_status=runtime_status,
                selectable_now=selectable_bool,
                gap_severity="fail_soft",
                evidence=evidence,
            )

        spec = self.tool_registry.get(algorithm_id) if require_tool else None
        if require_tool and spec is None:
            return RuntimeContractDecision(
                allowed=False,
                reason_code="UNKNOWN_TOOL",
                message=f"Algorithm is not registered in ToolRegistry: {algorithm_id}",
                runtime_status=runtime_status,
                selectable_now=selectable_bool,
                gap_severity="unguarded",
                evidence=evidence,
            )
        if spec is not None and spec.error_policy.get("reserved") == "true":
            return RuntimeContractDecision(
                allowed=False,
                reason_code="RESERVED_TOOL",
                message=f"ToolRegistry marks algorithm as reserved: {algorithm_id}",
                runtime_status=runtime_status,
                selectable_now=selectable_bool,
                gap_severity="fail_soft",
                evidence={**evidence, "tool_error_policy": dict(spec.error_policy)},
            )

        return RuntimeContractDecision(
            allowed=True,
            runtime_status=runtime_status,
            selectable_now=selectable_bool,
            gap_severity="none",
            evidence=evidence,
        )

    def evaluate_data_source(self, source_id: str, *, surface: str) -> RuntimeContractDecision:
        source = self._get_source(source_id)
        if source is None:
            return RuntimeContractDecision(
                allowed=False,
                reason_code="UNKNOWN_DATA_SOURCE",
                message=f"Data source not found in KG: {source_id}",
                gap_severity="unguarded",
                evidence={"source_id": source_id, "surface": surface},
            )

        metadata = dict(source.metadata or {})
        runtime_status = str(metadata.get("runtime_status") or "runtime_candidate").strip().lower()
        selectable_now = metadata.get("selectable_now")
        selectable_bool = None if selectable_now is None else bool(selectable_now)
        evidence = {"source_id": source_id, "surface": surface, "metadata": metadata}
        if runtime_status in BLOCKED_SOURCE_STATUSES or selectable_bool is False:
            return RuntimeContractDecision(
                allowed=False,
                reason_code="UNSELECTABLE_DATA_SOURCE",
                message=f"Data source is not selectable now: {source_id}",
                runtime_status=runtime_status,
                selectable_now=selectable_bool,
                gap_severity="fail_soft",
                evidence=evidence,
            )
        return RuntimeContractDecision(
            allowed=True,
            runtime_status=runtime_status,
            selectable_now=selectable_bool,
            gap_severity="none",
            evidence=evidence,
        )

    def evaluate_pattern(self, pattern: WorkflowPatternNode, *, surface: str) -> RuntimeContractDecision:
        blocked: list[dict[str, Any]] = []
        for step in pattern.steps:
            decision = self.evaluate_algorithm(step.algorithm_id, surface=surface)
            if not decision.allowed:
                blocked.append({"algorithm_id": step.algorithm_id, **decision.to_dict()})
        if blocked:
            return RuntimeContractDecision(
                allowed=False,
                reason_code="PATTERN_CONTAINS_BLOCKED_ALGORITHM",
                message=f"Pattern contains blocked algorithms: {pattern.pattern_id}",
                gap_severity="fail_soft",
                evidence={
                    "pattern_id": pattern.pattern_id,
                    "surface": surface,
                    "blocked_algorithm_ids": [item["algorithm_id"] for item in blocked],
                    "blocked": blocked,
                },
            )
        return RuntimeContractDecision(
            allowed=True,
            gap_severity="none",
            evidence={"pattern_id": pattern.pattern_id, "surface": surface},
        )

    def filter_patterns(
        self,
        patterns: Iterable[WorkflowPatternNode],
        *,
        surface: str,
    ) -> tuple[list[WorkflowPatternNode], list[dict[str, Any]]]:
        allowed: list[WorkflowPatternNode] = []
        skipped: list[dict[str, Any]] = []
        for pattern in patterns:
            decision = self.evaluate_pattern(pattern, surface=surface)
            if decision.allowed:
                allowed.append(pattern)
            else:
                skipped.append({"pattern_id": pattern.pattern_id, **decision.to_dict()})
        return allowed, skipped

    def filter_algorithm_ids(self, algorithm_ids: Iterable[str], *, surface: str) -> RuntimeContractFilterResult:
        allowed_ids: list[str] = []
        skipped: list[dict[str, Any]] = []
        for algorithm_id in algorithm_ids:
            decision = self.evaluate_algorithm(algorithm_id, surface=surface)
            if decision.allowed:
                allowed_ids.append(algorithm_id)
            else:
                skipped.append({"algorithm_id": algorithm_id, **decision.to_dict()})
        return RuntimeContractFilterResult(allowed_ids=allowed_ids, skipped=skipped)

    def _get_source(self, source_id: str) -> DataSourceNode | None:
        return next((source for source in self.kg_repo.list_data_sources() if source.source_id == source_id), None)
