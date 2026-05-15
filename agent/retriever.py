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
    ScenarioProfileNode,
    WorkflowPatternNode,
)
from kg.repository import KGRepository
from schemas.agent import RunTrigger, RunTriggerType
from schemas.fusion import JobType
from services.aoi_resolution_service import AOIResolutionService, ResolvedAOI
from services.artifact_reuse_policy import get_artifact_reuse_max_age_seconds
from services.artifact_registry import ArtifactLookupRequest, ArtifactRegistry, ArtifactRecord


def _to_unit_interval(value: Any, *, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, numeric))


def _candidate_identity(candidate: Dict[str, Any]) -> str:
    for key in ("candidate_id", "pattern_id", "source_id"):
        value = str(candidate.get(key) or "").strip()
        if value:
            return value
    return ""


def rank_retrieval_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []
    for raw in candidates:
        candidate = dict(raw)
        source_quality = _to_unit_interval(candidate.get("source_quality"), default=0.0)
        algorithm_fit = _to_unit_interval(candidate.get("algorithm_fit"), default=0.0)
        workflow_support = _to_unit_interval(candidate.get("workflow_support"), default=0.0)
        missing_requirements = candidate.get("missing_requirements") or []
        if not isinstance(missing_requirements, list):
            missing_requirements = [missing_requirements]
        penalty = min(1.0, 0.25 * len(missing_requirements))
        score = max(
            0.0,
            min(
                1.0,
                0.40 * source_quality + 0.35 * algorithm_fit + 0.25 * workflow_support - penalty,
            ),
        )
        candidate["ranking_score"] = round(score, 6)
        candidate["ranking_rationale"] = {
            "source_quality": round(source_quality, 3),
            "algorithm_fit": round(algorithm_fit, 3),
            "workflow_support": round(workflow_support, 3),
            "penalty_for_missing_requirements": round(penalty, 3),
        }
        ranked.append(candidate)
    ranked.sort(key=lambda item: (-float(item["ranking_score"]), _candidate_identity(item)))
    return ranked


class PlanningContextBuilder:
    def __init__(self, kg_repo: KGRepository, artifact_registry: ArtifactRegistry | None = None) -> None:
        self.kg_repo = kg_repo
        self.artifact_registry = artifact_registry
        self.aoi_resolution_service: AOIResolutionService | None = None
        self.resolved_aoi_override: ResolvedAOI | None = None
        self.preferred_pattern_id_override: str | None = None

    def build(self, job_type: JobType, trigger: RunTrigger) -> Tuple[Dict[str, Any], str]:
        kg_context = self.kg_repo.build_context(job_type=job_type, disaster_type=trigger.disaster_type)
        location_query = self._extract_location_query(trigger)
        resolved_aoi = self._resolve_aoi(trigger)
        resolved_mode = resolve_planning_mode(trigger)
        effective_profile = self._select_effective_scenario_profile(
            kg_context.scenario_profiles,
            trigger=trigger,
        )
        relevant_sources = self._collect_relevant_data_sources(
            job_type=job_type,
            disaster_type=trigger.disaster_type,
            kg_context=kg_context,
        )
        retrieval_payload = self._build_retrieval_payload(
            job_type,
            trigger,
            kg_context,
            resolved_aoi,
            planning_mode=str(resolved_mode["planning_mode"]),
        )
        selection_reason = self._select_reason_from_retrieval(retrieval_payload, fallback_patterns=kg_context.patterns)
        reserved_capability_hints = self._build_reserved_capability_hints(
            job_type=job_type,
            relevant_sources=relevant_sources,
        )
        return (
            {
                "intent": self._extract_intent(
                    job_type,
                    trigger,
                    location_query,
                    resolved_aoi,
                    effective_profile=effective_profile,
                    resolved_mode=resolved_mode,
                ),
                "retrieval": retrieval_payload,
                "constraints": self._build_constraints(job_type),
                "execution_hints": self._build_execution_hints(
                    kg_context,
                    resolved_aoi,
                    relevant_sources=relevant_sources,
                    reserved_capability_hints=reserved_capability_hints,
                    preferred_pattern_id=self.preferred_pattern_id_override,
                ),
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
        effective_profile: ScenarioProfileNode | None,
        resolved_mode: Dict[str, object],
    ) -> Dict[str, Any]:
        if resolved_mode["planning_mode"] == "task_driven":
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
            "planning_mode": resolved_mode["planning_mode"],
            "profile_source": resolved_mode["profile_source"],
            "task_bundle": task_bundle,
            "effective_scenario_profile_id": effective_profile.profile_id if effective_profile is not None else None,
            "effective_activated_tasks": list(effective_profile.activated_tasks) if effective_profile is not None else [],
            "effective_preferred_output_fields": (
                list(effective_profile.preferred_output_fields) if effective_profile is not None else []
            ),
            "effective_qos_priority": dict(effective_profile.qos_priority) if effective_profile is not None else {},
        }

    @staticmethod
    def _select_effective_scenario_profile(
        profiles: List[ScenarioProfileNode],
        *,
        trigger: RunTrigger,
    ) -> ScenarioProfileNode | None:
        if not profiles:
            return None
        if trigger.disaster_type:
            dtype = trigger.disaster_type.lower()
            for profile in profiles:
                profile_types = [item.lower() for item in profile.disaster_types]
                if dtype in profile_types:
                    return profile
        for profile in profiles:
            if profile.profile_id == "scenario.default.task":
                return profile
        return profiles[0]

    def _build_retrieval_payload(
        self,
        job_type: JobType,
        trigger: RunTrigger,
        kg_context: KGContext,
        resolved_aoi: ResolvedAOI | None,
        *,
        planning_mode: str,
    ) -> Dict[str, Any]:
        required_types = sorted({step.input_data_type for pattern in kg_context.patterns for step in pattern.steps})
        relevant_sources = self._collect_relevant_data_sources(
            job_type=job_type,
            disaster_type=trigger.disaster_type,
            kg_context=kg_context,
        )
        reserved_capability_hints = self._build_reserved_capability_hints(
            job_type=job_type,
            relevant_sources=relevant_sources,
        )
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
            "candidate_patterns": self._rank_pattern_candidates(
                kg_context.patterns,
                algorithms=kg_context.algorithms,
                sources=relevant_sources,
                planning_mode=planning_mode,
            ),
            "algorithms": {algo_id: self._algo_to_dict(algo) for algo_id, algo in kg_context.algorithms.items()},
            "task_nodes": [self._task_node_to_dict(task) for task in kg_context.task_nodes],
            "scenario_profiles": [self._scenario_profile_to_dict(item) for item in kg_context.scenario_profiles],
            "parameter_specs": {
                algo_id: [self._parameter_spec_to_dict(spec) for spec in specs]
                for algo_id, specs in kg_context.parameter_specs.items()
            },
            "data_sources": self._rank_data_source_candidates(
                relevant_sources,
                job_type=job_type,
                resolved_aoi=resolved_aoi,
            ),
            "output_schema_policies": {
                output_type: self._output_schema_policy_to_dict(policy)
                for output_type, policy in kg_context.output_schema_policies.items()
            },
            "durable_learning_summaries": {
                key: [self._durable_learning_summary_to_dict(item) for item in items]
                for key, items in kg_context.durable_learning_summaries.items()
            },
            "data_types": [self._data_type_to_dict(item) for item in kg_context.data_types],
            "source_coverage_hints": self._build_source_coverage_hints(
                relevant_sources,
                resolved_aoi=resolved_aoi,
            ),
            "transform_paths": transform_paths,
            "knowledge_hits": self.kg_repo.search_knowledge(search_query, limit=5),
        }
        if reserved_capability_hints:
            payload["reserved_capability_hints"] = reserved_capability_hints
        reusable = self._find_reusable_artifacts(job_type=job_type, trigger=trigger, limit=3)
        if reusable:
            payload["reusable_artifacts"] = [self._artifact_to_dict(item) for item in reusable]
        return payload

    def _rank_pattern_candidates(
        self,
        patterns: List[WorkflowPatternNode],
        *,
        algorithms: Dict[str, AlgorithmNode],
        sources: List[DataSourceNode],
        planning_mode: str,
    ) -> List[Dict[str, Any]]:
        source_by_id = {source.source_id: source for source in sources}
        prefer_task_driven_catalog_patterns = planning_mode == "task_driven" and any(
            str((pattern.metadata or {}).get("input_strategy") or "").strip().lower() == "task_driven_auto_supported"
            and any(step.data_source_id != "upload.bundle" for step in pattern.steps)
            for pattern in patterns
        )
        candidates: List[Dict[str, Any]] = []
        for pattern in patterns:
            candidate = self._pattern_to_dict(pattern)
            candidate.update(
                self._pattern_ranking_metrics(
                    pattern,
                    algorithms=algorithms,
                    source_by_id=source_by_id,
                    prefer_task_driven_catalog_patterns=prefer_task_driven_catalog_patterns,
                )
            )
            candidates.append(candidate)
        ranked = rank_retrieval_candidates(candidates)
        preferred_pattern_id = str(self.preferred_pattern_id_override or "").strip()
        if preferred_pattern_id:
            preferred = [
                item for item in ranked if str(item.get("pattern_id") or "").strip() == preferred_pattern_id
            ]
            others = [
                item for item in ranked if str(item.get("pattern_id") or "").strip() != preferred_pattern_id
            ]
            if preferred:
                ranked = preferred + others
        return ranked

    def _rank_data_source_candidates(
        self,
        sources: List[DataSourceNode],
        *,
        job_type: JobType,
        resolved_aoi: ResolvedAOI | None,
    ) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        required_prefix = f"dt.{job_type.value}."
        for source in sources:
            candidate = self._data_source_to_dict(source)
            metadata = dict(source.metadata or {})
            selectable_now = bool(metadata.get("selectable_now", False))
            runtime_status = str(metadata.get("runtime_status") or "runtime_candidate").lower()
            missing_requirements: List[str] = []
            workflow_support = 1.0
            if not selectable_now:
                workflow_support -= 0.35
                missing_requirements.append("not_selectable_now")
            if runtime_status == "reservation_only":
                workflow_support -= 0.35
                missing_requirements.append("reservation_only")
            if resolved_aoi is not None and metadata.get("supports_aoi") is False:
                workflow_support -= 0.15
                missing_requirements.append("aoi_not_supported")
            candidate.update(
                {
                    "source_quality": _to_unit_interval(source.quality_score, default=0.0),
                    "algorithm_fit": 1.0 if any(item.startswith(required_prefix) for item in source.supported_types) else 0.6,
                    "workflow_support": max(0.0, min(1.0, workflow_support)),
                    "missing_requirements": missing_requirements,
                }
            )
            candidates.append(candidate)
        return rank_retrieval_candidates(candidates)

    def _pattern_ranking_metrics(
        self,
        pattern: WorkflowPatternNode,
        *,
        algorithms: Dict[str, AlgorithmNode],
        source_by_id: Dict[str, DataSourceNode],
        prefer_task_driven_catalog_patterns: bool,
    ) -> Dict[str, Any]:
        source_scores: List[float] = []
        algorithm_scores: List[float] = []
        workflow_supported_steps = 0
        missing_requirements: List[str] = []
        for step in pattern.steps:
            algorithm = algorithms.get(step.algorithm_id)
            if algorithm is None:
                missing_requirements.append(f"missing_algorithm:{step.algorithm_id}")
                algorithm_scores.append(0.0)
            else:
                success_rate = _to_unit_interval(algorithm.success_rate, default=_to_unit_interval(pattern.success_rate))
                accuracy_score = _to_unit_interval(algorithm.accuracy_score, default=success_rate)
                stability_score = _to_unit_interval(algorithm.stability_score, default=success_rate)
                algorithm_scores.append(0.65 * success_rate + 0.25 * accuracy_score + 0.10 * stability_score)
            source = source_by_id.get(step.data_source_id)
            if source is None:
                if step.data_source_id == "upload.bundle":
                    source_scores.append(1.0)
                    workflow_supported_steps += 1
                else:
                    missing_requirements.append(f"missing_source:{step.data_source_id}")
            else:
                source_scores.append(_to_unit_interval(source.quality_score, default=0.0))
                runtime_status = str(source.metadata.get("runtime_status") or "runtime_candidate").lower()
                selectable_now = bool(source.metadata.get("selectable_now", False))
                if runtime_status == "reservation_only" or not selectable_now:
                    missing_requirements.append(f"source_unavailable:{source.source_id}")
                else:
                    workflow_supported_steps += 1
        workflow_support = workflow_supported_steps / max(1, len(pattern.steps))
        metadata = dict(pattern.metadata or {})
        if metadata.get("input_strategy") == "task_driven_auto_supported":
            workflow_support = min(1.0, workflow_support + 0.05)
        elif prefer_task_driven_catalog_patterns and all(step.data_source_id == "upload.bundle" for step in pattern.steps):
            missing_requirements.append("task_driven_bundle_not_supported")
        return {
            "source_quality": round(sum(source_scores) / max(1, len(source_scores)), 6),
            "algorithm_fit": round(sum(algorithm_scores) / max(1, len(algorithm_scores)), 6),
            "workflow_support": round(workflow_support, 6),
            "missing_requirements": missing_requirements,
        }

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
    def _build_execution_hints(
        kg_context: KGContext,
        resolved_aoi: ResolvedAOI | None,
        *,
        relevant_sources: List[DataSourceNode] | None = None,
        reserved_capability_hints: List[Dict[str, Any]] | None = None,
        preferred_pattern_id: str | None = None,
    ) -> Dict[str, Any]:
        sources = relevant_sources or kg_context.data_sources
        effective_preferred_pattern_id = preferred_pattern_id or (kg_context.patterns[0].pattern_id if kg_context.patterns else None)
        hints = {
            "preferred_pattern_id": effective_preferred_pattern_id,
            "fallback_pattern_ids": [
                pattern.pattern_id for pattern in kg_context.patterns if pattern.pattern_id != effective_preferred_pattern_id
            ],
            "available_data_source_ids": [source.source_id for source in sources],
            "selectable_source_ids": [
                source.source_id
                for source in sources
                if source.metadata.get("selectable_now", False)
                and source.metadata.get("runtime_status", "runtime_candidate") != "reservation_only"
            ],
            "reserved_source_ids": [
                source.source_id
                for source in sources
                if source.metadata.get("runtime_status") == "reservation_only"
                or source.metadata.get("selectable_now") is False
            ],
        }
        if reserved_capability_hints:
            hints["runtime_candidate_capabilities"] = [
                item["capability_id"]
                for item in reserved_capability_hints
                if item.get("runtime_status") == "runtime_candidate"
            ]
            hints["required_reserved_capabilities"] = [
                item["capability_id"]
                for item in reserved_capability_hints
                if item.get("runtime_status") == "reservation_only"
            ]
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
    def _select_reason_from_retrieval(
        retrieval_payload: Dict[str, Any],
        *,
        fallback_patterns: List[WorkflowPatternNode],
    ) -> str:
        candidates = retrieval_payload.get("candidate_patterns", [])
        if isinstance(candidates, list) and candidates:
            top = candidates[0]
            pattern_id = str(top.get("pattern_id") or "").strip()
            if pattern_id:
                return f"preferred_{pattern_id}_by_ranked_retrieval"
        return PlanningContextBuilder._select_reason(fallback_patterns)

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
    def _data_type_to_dict(data_type) -> Dict[str, Any]:
        return {
            "type_id": data_type.type_id,
            "theme": data_type.theme,
            "geometry_type": data_type.geometry_type,
            "description": data_type.description,
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
        sources: List[DataSourceNode],
        *,
        resolved_aoi: ResolvedAOI | None,
    ) -> List[Dict[str, Any]]:
        hints: List[Dict[str, Any]] = []
        for source in sources:
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
                "source_form": metadata.get("source_form"),
                "runtime_status": metadata.get("runtime_status"),
                "selectable_now": metadata.get("selectable_now"),
                "supports_tiling": metadata.get("supports_tiling"),
                "height_semantics": metadata.get("height_semantics"),
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

    def _collect_relevant_data_sources(
        self,
        *,
        job_type: JobType,
        disaster_type: str | None,
        kg_context: KGContext,
    ) -> List[DataSourceNode]:
        dtype = (disaster_type or "generic").lower()
        sources: Dict[str, DataSourceNode] = {source.source_id: source for source in kg_context.data_sources}
        for source in self.kg_repo.list_data_sources():
            if source.source_id in sources:
                continue
            supported_disasters = [item.lower() for item in source.disaster_types]
            if dtype not in supported_disasters and "generic" not in supported_disasters:
                continue
            metadata = dict(source.metadata or {})
            source_theme = str(metadata.get("theme") or "").lower()
            job_support = job_type.value in source.supported_job_types
            typed_support = any(
                supported_type.startswith(f"dt.{job_type.value}.")
                for supported_type in source.supported_types
            )
            if source.source_id != "upload.bundle" and not job_support and not typed_support and source_theme != job_type.value:
                continue
            sources[source.source_id] = source

        def _sort_key(item: DataSourceNode) -> tuple[int, float, str]:
            selectable = 1 if item.metadata.get("selectable_now", False) else 0
            return (selectable, item.quality_score, item.source_id)

        return sorted(sources.values(), key=_sort_key, reverse=True)

    def _build_reserved_capability_hints(
        self,
        *,
        job_type: JobType,
        relevant_sources: List[DataSourceNode],
    ) -> List[Dict[str, Any]]:
        if job_type != JobType.building:
            return []

        reserved_vectors = [
            source.source_id
            for source in relevant_sources
            if source.metadata.get("runtime_status") == "reservation_only"
            and source.metadata.get("source_form") == "vector"
        ]
        reserved_rasters = [
            source.source_id
            for source in relevant_sources
            if source.metadata.get("runtime_status") == "reservation_only"
            and source.metadata.get("source_form") == "raster"
        ]
        tiling_sources = [
            source.source_id
            for source in relevant_sources
            if bool(source.metadata.get("supports_tiling"))
        ]

        hints: List[Dict[str, Any]] = []
        if tiling_sources:
            hints.append(
                self._reserved_capability_hint(
                    capability_id="algo.partition.aoi.grid.v1",
                    capability_kind="algorithm",
                    reason="Large building AOIs need deterministic tiling before fan-out execution.",
                    activated_source_ids=tiling_sources,
                )
            )
            hints.append(
                self._reserved_capability_hint(
                    capability_id="algo.merge.building.tiles.reserved",
                    capability_kind="algorithm",
                    reason="Tile-scoped outputs need a controlled stitch step before final building delivery.",
                    activated_source_ids=tiling_sources,
                )
            )
        if reserved_vectors:
            hints.append(
                self._reserved_capability_hint(
                    capability_id="algo.fusion.building.multi_source.decomposed.v1",
                    capability_kind="algorithm",
                    reason="Additional building vector sources can be routed through the decomposed FusionCode multi-source workflow.",
                    activated_source_ids=reserved_vectors,
                )
            )
        if reserved_rasters:
            hints.append(
                self._reserved_capability_hint(
                    capability_id="algo.clip.raster.tile.v1",
                    capability_kind="algorithm",
                    reason="Raster-assisted building workflows require tiled raster clipping control that is not executable yet.",
                    activated_source_ids=reserved_rasters,
                )
            )
            hints.append(
                self._reserved_capability_hint(
                    capability_id="algo.validate.building.presence_raster.v1",
                    capability_kind="algorithm",
                    reason="Building presence rasters can be used by the executable FusionCode raster validation primitive once materialized.",
                    activated_source_ids=reserved_rasters,
                )
            )
            hints.append(
                self._reserved_capability_hint(
                    capability_id="algo.enrich.building.height_from_raster.v1",
                    capability_kind="algorithm",
                    reason="Building height rasters can be used by the executable FusionCode height enrichment primitive once materialized.",
                    activated_source_ids=reserved_rasters,
                )
            )
        return hints

    def _reserved_capability_hint(
        self,
        *,
        capability_id: str,
        capability_kind: str,
        reason: str,
        activated_source_ids: List[str],
    ) -> Dict[str, Any]:
        runtime_status = "reservation_only"
        if capability_kind == "algorithm":
            algo = self.kg_repo.get_algorithm(capability_id)
            if algo is not None:
                runtime_status = str(algo.metadata.get("runtime_status") or runtime_status)
        return {
            "capability_id": capability_id,
            "capability_kind": capability_kind,
            "runtime_status": runtime_status,
            "activated_source_ids": activated_source_ids,
            "reason": reason,
        }

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
