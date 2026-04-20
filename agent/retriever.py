from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from agent.intent_resolver import resolve_planning_mode
from kg.models import (
    AlgorithmNode,
    AlgorithmParameterSpec,
    DataSourceNode,
    DurableLearningSummary,
    KGContext,
    OutputSchemaPolicy,
    WorkflowPatternNode,
)
from kg.repository import KGRepository
from schemas.agent import RunTrigger, RunTriggerType
from schemas.fusion import JobType
from services.aoi_resolution_service import AOIResolutionService, ResolvedAOI
from services.artifact_reuse_policy import get_artifact_reuse_max_age_seconds
from services.artifact_registry import ArtifactLookupRequest, ArtifactRegistry, ArtifactRecord


class PlanningContextBuilder:
    def __init__(self, kg_repo: KGRepository, artifact_registry: ArtifactRegistry | None = None) -> None:
        self.kg_repo = kg_repo
        self.artifact_registry = artifact_registry
        self.aoi_resolution_service: AOIResolutionService | None = None
        self.resolved_aoi_override: ResolvedAOI | None = None

    def build(self, job_type: JobType, trigger: RunTrigger) -> Tuple[Dict[str, Any], str]:
        kg_context = self.kg_repo.build_context(job_type=job_type, disaster_type=trigger.disaster_type)
        location_query = self._extract_location_query(trigger)
        resolved_aoi = self._resolve_aoi(trigger)
        selection_reason = self._select_reason(kg_context.patterns)
        return (
            {
                "intent": self._extract_intent(job_type, trigger, location_query, resolved_aoi),
                "retrieval": self._build_retrieval_payload(job_type, trigger, kg_context, resolved_aoi),
                "constraints": self._build_constraints(job_type),
                "execution_hints": self._build_execution_hints(kg_context, resolved_aoi),
            },
            selection_reason,
        )

    def _resolve_aoi(self, trigger: RunTrigger) -> ResolvedAOI | None:
        if self.resolved_aoi_override is not None:
            return self.resolved_aoi_override
        if self.aoi_resolution_service is None:
            return None
        if trigger.type != RunTriggerType.user_query:
            return None
        if not trigger.content.strip():
            return None
        return self.aoi_resolution_service.resolve(trigger.content)

    @staticmethod
    def _extract_location_query(trigger: RunTrigger) -> str | None:
        content = (trigger.content or "").strip()
        if not content:
            return None
        return AOIResolutionService.extract_location_query(content)

    @staticmethod
    def _extract_intent(
        job_type: JobType,
        trigger: RunTrigger,
        location_query: str | None,
        resolved_aoi: ResolvedAOI | None,
    ) -> Dict[str, Any]:
        resolved = resolve_planning_mode(trigger)
        if resolved["planning_mode"] == "task_driven":
            task_bundle = {
                "bundle_id": "task_bundle.direct_request",
                "requested_tasks": [f"task.{job_type.value}.fusion"],
                "requires_disaster_profile": False,
            }
        else:
            task_bundle = {
                "bundle_id": f"task_bundle.{trigger.disaster_type or 'default'}",
                "requested_tasks": [f"task.{job_type.value}.fusion"],
                "requires_disaster_profile": True,
            }
        return {
            "job_type": job_type.value,
            "trigger": trigger.model_dump(),
            "location_query": location_query,
            "resolved_aoi": resolved_aoi.to_dict() if resolved_aoi is not None else None,
            "expected_output_type": f"dt.{job_type.value}.fused",
            "spatial_extent": trigger.spatial_extent,
            "temporal_start": trigger.temporal_start,
            "temporal_end": trigger.temporal_end,
            "planning_mode": resolved["planning_mode"],
            "profile_source": resolved["profile_source"],
            "task_bundle": task_bundle,
        }

    def _build_retrieval_payload(
        self,
        job_type: JobType,
        trigger: RunTrigger,
        kg_context: KGContext,
        resolved_aoi: ResolvedAOI | None,
    ) -> Dict[str, Any]:
        required_types = sorted({step.input_data_type for pattern in kg_context.patterns for step in pattern.steps})
        transform_paths = {
            required_type: self.kg_repo.find_transform_path("dt.raw.vector", required_type, max_depth=3)
            for required_type in required_types
        }
        search_query = " ".join(
            token
            for token in [job_type.value, trigger.disaster_type or "", trigger.content]
            if token
        )
        payload: Dict[str, Any] = {
            "candidate_patterns": [self._pattern_to_dict(pattern) for pattern in kg_context.patterns],
            "algorithms": {algo_id: self._algo_to_dict(algo) for algo_id, algo in kg_context.algorithms.items()},
            "task_nodes": [self._task_node_to_dict(task) for task in kg_context.task_nodes],
            "scenario_profiles": [self._scenario_profile_to_dict(item) for item in kg_context.scenario_profiles],
            "parameter_specs": {
                algo_id: [self._parameter_spec_to_dict(spec) for spec in specs]
                for algo_id, specs in kg_context.parameter_specs.items()
            },
            "data_sources": [self._data_source_to_dict(source) for source in kg_context.data_sources],
            "output_schema_policies": {
                output_type: self._output_schema_policy_to_dict(policy)
                for output_type, policy in kg_context.output_schema_policies.items()
            },
            "durable_learning_summaries": {
                key: [self._durable_learning_summary_to_dict(item) for item in items]
                for key, items in kg_context.durable_learning_summaries.items()
            },
            "source_coverage_hints": self._build_source_coverage_hints(
                kg_context,
                job_type=job_type,
                resolved_aoi=resolved_aoi,
            ),
            "transform_paths": transform_paths,
            "knowledge_hits": self.kg_repo.search_knowledge(search_query, limit=5),
        }
        reusable = self._find_reusable_artifacts(job_type=job_type, trigger=trigger, limit=3)
        if reusable:
            payload["reusable_artifacts"] = [self._artifact_to_dict(item) for item in reusable]
        return payload

    def _find_reusable_artifacts(self, *, job_type: JobType, trigger: RunTrigger, limit: int) -> List[ArtifactRecord]:
        if not self.artifact_registry:
            return []
        bbox = self._parse_bbox(trigger.spatial_extent)
        required_output_type = f"dt.{job_type.value}.fused"
        request = ArtifactLookupRequest(
            job_type=job_type.value,
            disaster_type=trigger.disaster_type,
            max_age_seconds=get_artifact_reuse_max_age_seconds(job_type),
            required_fields=[],
            required_output_type=required_output_type,
            bbox=bbox,
        )
        try:
            return self.artifact_registry.list_reusable(request, limit=limit)
        except Exception:  # noqa: BLE001
            # Planner context enrichment should never block planning.
            return []

    @staticmethod
    def _parse_bbox(value: str | None):
        if not value:
            return None
        # Expected form used throughout this repo/tests: bbox(minx,miny,maxx,maxy)
        match = re.match(r"^bbox\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)\s*$", value)
        if not match:
            return None
        try:
            return (float(match.group(1)), float(match.group(2)), float(match.group(3)), float(match.group(4)))
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _artifact_to_dict(record: ArtifactRecord) -> Dict[str, Any]:
        return {
            "artifact_id": record.artifact_id,
            "artifact_path": record.artifact_path,
            "job_type": record.job_type,
            "disaster_type": record.disaster_type,
            "created_at": record.created_at,
            "output_fields": record.output_fields,
            "output_data_type": record.output_data_type,
            "target_crs": record.target_crs,
            "schema_policy_id": record.schema_policy_id,
            "compatibility_basis": record.compatibility_basis,
            "bbox": record.bbox,
            "meta": record.meta,
        }

    @staticmethod
    def _build_constraints(job_type: JobType) -> Dict[str, Any]:
        return {
            # Derived from the enum to avoid drift as JobType evolves.
            "allowed_job_types": [jt.value for jt in JobType],
            "required_output_type": f"dt.{job_type.value}.fused",
            "must_use_registered_algorithms": True,
            "must_keep_json_schema": True,
        }

    @staticmethod
    def _build_execution_hints(kg_context: KGContext, resolved_aoi: ResolvedAOI | None) -> Dict[str, Any]:
        hints = {
            "preferred_pattern_id": kg_context.patterns[0].pattern_id if kg_context.patterns else None,
            "fallback_pattern_ids": [pattern.pattern_id for pattern in kg_context.patterns[1:]],
            "available_data_source_ids": [source.source_id for source in kg_context.data_sources],
        }
        if resolved_aoi is not None:
            hints["available_aoi"] = resolved_aoi.to_dict()
        return hints

    @staticmethod
    def _select_reason(patterns: List[WorkflowPatternNode]) -> str:
        if not patterns:
            return "no_pattern_available"
        # Patterns are already ordered by upstream context building/ranking.
        return f"preferred_{patterns[0].pattern_id}_by_context_order"

    @staticmethod
    def _algo_to_dict(algo: AlgorithmNode) -> Dict[str, Any]:
        return {
            "algo_id": algo.algo_id,
            "algo_name": algo.algo_name,
            "input_types": algo.input_types,
            "output_type": algo.output_type,
            "task_type": algo.task_type,
            "tool_ref": algo.tool_ref,
            "success_rate": algo.success_rate,
            "accuracy_score": algo.accuracy_score,
            "stability_score": algo.stability_score,
            "usage_mode": algo.usage_mode,
            "metadata": algo.metadata,
            "alternatives": algo.alternatives,
        }

    @staticmethod
    def _data_source_to_dict(source: DataSourceNode) -> Dict[str, Any]:
        return {
            "source_id": source.source_id,
            "source_name": source.source_name,
            "supported_types": source.supported_types,
            "disaster_types": source.disaster_types,
            "quality_score": source.quality_score,
            "source_kind": source.source_kind,
            "quality_tier": source.quality_tier,
            "freshness_category": source.freshness_category,
            "freshness_hours": source.freshness_hours,
            "freshness_score": source.freshness_score,
            "supported_job_types": source.supported_job_types,
            "supported_geometry_types": source.supported_geometry_types,
            "metadata": source.metadata,
        }

    @staticmethod
    def _parameter_spec_to_dict(spec: AlgorithmParameterSpec) -> Dict[str, Any]:
        return {
            "spec_id": spec.spec_id,
            "algo_id": spec.algo_id,
            "key": spec.key,
            "label": spec.label,
            "param_type": spec.param_type,
            "default": spec.default,
            "min_value": spec.min_value,
            "max_value": spec.max_value,
            "unit": spec.unit,
            "description": spec.description,
            "required": spec.required,
            "choices": spec.choices,
            "tunable": spec.tunable,
            "optimization_tags": spec.optimization_tags,
            "order": spec.order,
        }

    @staticmethod
    def _output_schema_policy_to_dict(policy: OutputSchemaPolicy) -> Dict[str, Any]:
        return {
            "policy_id": policy.policy_id,
            "output_type": policy.output_type,
            "job_type": policy.job_type.value,
            "retention_mode": policy.retention_mode,
            "required_fields": policy.required_fields,
            "optional_fields": policy.optional_fields,
            "rename_hints": policy.rename_hints,
            "compatibility_basis": policy.compatibility_basis,
            "metadata": policy.metadata,
        }

    @staticmethod
    def _durable_learning_summary_to_dict(summary: DurableLearningSummary) -> Dict[str, Any]:
        return {
            "entity_kind": summary.entity_kind,
            "entity_id": summary.entity_id,
            "job_type": summary.job_type.value,
            "disaster_type": summary.disaster_type,
            "total_runs": summary.total_runs,
            "success_count": summary.success_count,
            "failure_count": summary.failure_count,
            "repaired_count": summary.repaired_count,
            "last_run_at": summary.last_run_at,
            "last_failure_reason": summary.last_failure_reason,
        }

    @staticmethod
    def _task_node_to_dict(task) -> Dict[str, Any]:
        return {
            "task_id": task.task_id,
            "task_name": task.task_name,
            "category": task.category,
            "description": task.description,
        }

    @staticmethod
    def _scenario_profile_to_dict(profile) -> Dict[str, Any]:
        return {
            "profile_id": profile.profile_id,
            "profile_name": profile.profile_name,
            "disaster_types": profile.disaster_types,
            "activated_tasks": profile.activated_tasks,
            "preferred_output_fields": profile.preferred_output_fields,
            "qos_priority": profile.qos_priority,
            "metadata": profile.metadata,
        }

    @staticmethod
    def _build_source_coverage_hints(
        kg_context: KGContext,
        *,
        job_type: JobType,
        resolved_aoi: ResolvedAOI | None,
    ) -> List[Dict[str, Any]]:
        hints: List[Dict[str, Any]] = []
        for source in kg_context.data_sources:
            if job_type.value not in source.supported_job_types and source.source_id != "upload.bundle":
                continue
            metadata = dict(source.metadata or {})
            hint = {
                "source_id": source.source_id,
                "source_name": source.source_name,
                "source_kind": source.source_kind,
                "provider_family": metadata.get("provider_family"),
                "path_hint": metadata.get("path_hint") or metadata.get("path_hints"),
                "supports_aoi": metadata.get("supports_aoi"),
                "materialization_scope": metadata.get("materialization_scope"),
                "materialization_provider": metadata.get("materialization_provider"),
                "supported_job_types": source.supported_job_types,
                "supported_geometry_types": source.supported_geometry_types,
                "quality_score": source.quality_score,
                "freshness_score": source.freshness_score,
            }
            if resolved_aoi is not None:
                hint["resolved_aoi"] = {
                    "display_name": resolved_aoi.display_name,
                    "country_code": resolved_aoi.country_code,
                    "country_name": resolved_aoi.country_name,
                    "bbox": list(resolved_aoi.bbox),
                }
            hints.append(hint)
        return hints

    @staticmethod
    def _pattern_to_dict(pattern: WorkflowPatternNode) -> Dict[str, Any]:
        return {
            "pattern_id": pattern.pattern_id,
            "pattern_name": pattern.pattern_name,
            "job_type": pattern.job_type.value,
            "disaster_types": pattern.disaster_types,
            "success_rate": pattern.success_rate,
            "metadata": pattern.metadata,
            "steps": [
                {
                    "order": step.order,
                    "name": step.name,
                    "algorithm_id": step.algorithm_id,
                    "input_data_type": step.input_data_type,
                    "output_data_type": step.output_data_type,
                    "data_source_id": step.data_source_id,
                    "depends_on": step.depends_on,
                    "is_optional": step.is_optional,
                }
                for step in pattern.steps
            ],
        }
