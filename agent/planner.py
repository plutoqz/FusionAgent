from __future__ import annotations

import json
import logging
import time
import uuid
from threading import Lock
from typing import Any, Dict, List, Optional

from agent.parameter_binding import bind_plan_parameters
from agent.retriever import PlanningContextBuilder
from kg.models import WorkflowPatternNode
from kg.repository import KGRepository
from llm.providers.base import LLMProvider
from schemas.agent import RunTrigger, WorkflowPlan, WorkflowTask
from schemas.agent import (
    DataNeedRef,
    OutputRequirementRef,
    QoSPolicyRef,
    RepairStrategyRef,
    TaskBundleRef,
)
from schemas.fusion import JobType
from services.artifact_registry import ArtifactRegistry
from services.run_telemetry_service import estimate_json_size_bytes, normalize_llm_usage


SYSTEM_PROMPT = """
You are GeoFusion workflow planner.
Generate a strict JSON object for the workflow plan.
Rules:
1) Use only algorithms listed in candidate patterns.
2) Keep tasks executable and ordered.
3) Prefer high success-rate patterns.
4) When resolved_aoi and source_coverage_hints are present, use them to choose executable source-aware tasks.
5) Return valid JSON only.
"""


class _ProviderPlanningCallError(RuntimeError):
    def __init__(self, cause: Exception, telemetry: Dict[str, Any]) -> None:
        super().__init__(str(cause))
        self.telemetry = telemetry
        self.__cause__ = cause


class WorkflowPlanner:
    def __init__(self, kg_repo: KGRepository, llm_provider: LLMProvider, artifact_registry: ArtifactRegistry | None = None) -> None:
        self.kg_repo = kg_repo
        self.llm_provider = llm_provider
        self.context_builder = PlanningContextBuilder(kg_repo, artifact_registry=artifact_registry)
        self.logger = logging.getLogger("geofusion.planner")
        self._provider_call_lock = Lock()

    def create_plan(self, run_id: str, job_type: JobType, trigger: RunTrigger) -> WorkflowPlan:
        planning_context, selection_reason = self.context_builder.build(job_type=job_type, trigger=trigger)
        candidate_patterns = planning_context["retrieval"]["candidate_patterns"]
        if not candidate_patterns:
            raise ValueError(f"No workflow pattern found for job_type={job_type.value}")
        preferred_pattern_id = str(planning_context.get("execution_hints", {}).get("preferred_pattern_id") or "").strip()

        planning_telemetry: Dict[str, Any] | None = None
        try:
            plan_payload, planning_telemetry = self._generate_plan_payload(planning_context)
            plan = WorkflowPlan.model_validate(plan_payload)
            if not plan.tasks:
                raise ValueError("LLM returned plan with no tasks.")
            plan.trigger = trigger
            planning_source = "llm"
        except _ProviderPlanningCallError as exc:
            planning_telemetry = exc.telemetry
            self.logger.warning("LLM planning failed (%s), fallback to top KG pattern.", exc)
            top_pattern = self._select_fallback_pattern(
                job_type=job_type,
                disaster_type=trigger.disaster_type,
                preferred_pattern_id=preferred_pattern_id,
            )
            plan = self._build_skeleton_plan(top_pattern, trigger=trigger)
            planning_source = "kg_fallback"
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("LLM planning failed (%s), fallback to top KG pattern.", exc)
            top_pattern = self._select_fallback_pattern(
                job_type=job_type,
                disaster_type=trigger.disaster_type,
                preferred_pattern_id=preferred_pattern_id,
            )
            plan = self._build_skeleton_plan(top_pattern, trigger=trigger)
            planning_source = "kg_fallback"
        if planning_telemetry is None:
            planning_telemetry = self._build_planning_telemetry(
                planning_context=planning_context,
                started_at=time.perf_counter(),
            )

        plan = self._finalize_plan(plan)
        plan = bind_plan_parameters(plan, self.kg_repo)
        plan.context = self._normalize_plan_context(
            planning_context=planning_context,
            selection_reason=selection_reason,
            revision=1,
            planning_telemetry=planning_telemetry,
            planning_source=planning_source,
            existing_context=plan.context,
        )
        selected_pattern_id = self._infer_selected_pattern_id(plan, candidate_patterns)
        if selected_pattern_id:
            plan.context["selected_pattern_id"] = selected_pattern_id
        self._hydrate_plan_semantics(plan)
        return plan

    def _select_fallback_pattern(
        self,
        *,
        job_type: JobType,
        disaster_type: str | None,
        preferred_pattern_id: str | None,
    ) -> WorkflowPatternNode:
        patterns = self.kg_repo.get_candidate_patterns(job_type=job_type, disaster_type=disaster_type, limit=20)
        preferred = str(preferred_pattern_id or "").strip()
        if preferred:
            for pattern in patterns:
                if pattern.pattern_id == preferred:
                    return pattern
        if not patterns:
            raise ValueError(f"No workflow pattern found for job_type={job_type.value}")
        return patterns[0]

    @staticmethod
    def _infer_selected_pattern_id(plan: WorkflowPlan, candidate_patterns: List[Dict[str, Any]]) -> str | None:
        executable_tasks = [task for task in sorted(plan.tasks, key=lambda item: item.step) if not task.is_transform]
        if not executable_tasks:
            return None
        for candidate in candidate_patterns:
            if not isinstance(candidate, dict):
                continue
            steps = candidate.get("steps")
            if not isinstance(steps, list) or len(steps) < len(executable_tasks):
                continue
            matched = True
            for task, step in zip(executable_tasks, steps):
                if str(step.get("algorithm_id") or "").strip() != task.algorithm_id:
                    matched = False
                    break
                if str(step.get("input_data_type") or "").strip() != task.input.data_type_id:
                    matched = False
                    break
                if str(step.get("data_source_id") or "").strip() != task.input.data_source_id:
                    matched = False
                    break
                if str(step.get("output_data_type") or "").strip() != task.output.data_type_id:
                    matched = False
                    break
            if matched:
                pattern_id = str(candidate.get("pattern_id") or "").strip()
                if pattern_id:
                    return pattern_id
        if candidate_patterns:
            fallback = str(candidate_patterns[0].get("pattern_id") or "").strip()
            if fallback:
                return fallback
        return None

    def replan_from_error(
        self,
        run_id: str,
        job_type: JobType,
        trigger: RunTrigger,
        previous_plan: WorkflowPlan,
        failed_step: int,
        error_message: str,
    ) -> WorkflowPlan:
        planning_context, _ = self.context_builder.build(job_type=job_type, trigger=trigger)
        planning_context["execution_hints"]["previous_plan"] = previous_plan.model_dump(mode="json")
        planning_context["execution_hints"]["failed_step"] = failed_step
        planning_context["execution_hints"]["error"] = error_message
        planning_telemetry: Dict[str, Any] | None = None
        try:
            payload, planning_telemetry = self._generate_plan_payload(planning_context)
            plan = WorkflowPlan.model_validate(payload)
            if not plan.tasks:
                raise ValueError("LLM returned plan with no tasks.")
            plan.trigger = trigger
            plan = self._finalize_plan(plan, fallback_workflow_id=previous_plan.workflow_id)
            plan = bind_plan_parameters(plan, self.kg_repo)
            revision = int(previous_plan.context.get("plan_revision", 1)) + 1
            plan.context = self._normalize_plan_context(
                planning_context=planning_context,
                selection_reason="replanned_after_failure",
                revision=revision,
                planning_telemetry=planning_telemetry,
                planning_source="llm",
                existing_context=plan.context,
                failed_step=failed_step,
                error_message=error_message,
            )
            selected_pattern_id = self._infer_selected_pattern_id(
                plan,
                planning_context["retrieval"]["candidate_patterns"],
            )
            if selected_pattern_id:
                plan.context["selected_pattern_id"] = selected_pattern_id
            self._hydrate_plan_semantics(plan)
            return plan
        except _ProviderPlanningCallError as exc:
            planning_telemetry = exc.telemetry
            self.logger.warning("Replan failed (%s), returning previous plan.", exc)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Replan failed (%s), returning previous plan.", exc)
        if planning_telemetry is None:
            planning_telemetry = self._build_planning_telemetry(
                planning_context=planning_context,
                started_at=time.perf_counter(),
            )
        return previous_plan.model_copy(
            update={
                "context": {
                    **previous_plan.context,
                    "failed_replan_telemetry": planning_telemetry,
                }
            },
            deep=True,
        )

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

    def _build_skeleton_plan(self, pattern: WorkflowPatternNode, trigger: RunTrigger) -> WorkflowPlan:
        payload = {
            "workflow_id": f"wf_{pattern.pattern_id}_{uuid.uuid4().hex[:8]}",
            "trigger": trigger.model_dump(),
            "context": {
                "pattern_id": pattern.pattern_id,
                "pattern_name": pattern.pattern_name,
                "source": "kg_fallback",
            },
            "tasks": [
                {
                    "step": idx,
                    "name": step.name,
                    "description": f"Execute {step.algorithm_id}",
                    "task_id": self._infer_task_id_from_pattern_step(pattern, step.algorithm_id),
                    "algorithm_id": step.algorithm_id,
                    "input": {
                        "data_type_id": step.input_data_type,
                        "data_source_id": step.data_source_id,
                        "parameters": {},
                    },
                    "output": {
                        "data_type_id": step.output_data_type,
                        "description": "Output generated by workflow step",
                    },
                    "depends_on": step.depends_on,
                    "is_transform": False,
                    "kg_validated": False,
                    "alternatives": [],
                }
                for idx, step in enumerate(pattern.steps, start=1)
            ],
            "expected_output": f"{pattern.job_type.value} fusion result",
            "estimated_time": "unknown",
            "task_bundle": self._task_bundle_from_context({}),
            "output_requirement": self._output_requirement_from_context({}),
            "qos_policy": self._qos_policy_from_context({}),
            "data_needs": [],
            "repair_strategies": [],
        }
        # Roundtrip for stronger schema normalization.
        return WorkflowPlan.model_validate(json.loads(json.dumps(payload)))

    def _finalize_plan(self, plan: WorkflowPlan, fallback_workflow_id: Optional[str] = None) -> WorkflowPlan:
        patched_tasks: List[WorkflowTask] = []
        for task in plan.tasks:
            alternatives = [a.algo_id for a in self.kg_repo.get_alternative_algorithms(task.algorithm_id, limit=3)]
            task.alternatives = list(dict.fromkeys([*task.alternatives, *alternatives]))
            patched_tasks.append(task)
        plan.tasks = patched_tasks

        if not plan.workflow_id:
            plan.workflow_id = fallback_workflow_id or f"wf_{uuid.uuid4().hex}"
        for task in plan.tasks:
            if not task.task_id:
                task.task_id = self._task_id_from_context(plan.context, task)
        if plan.task_bundle is None:
            raw = self._task_bundle_from_context(plan.context)
            if isinstance(raw, dict):
                plan.task_bundle = TaskBundleRef.model_validate(raw)
        if plan.output_requirement is None:
            raw = self._output_requirement_from_context(plan.context)
            if isinstance(raw, dict):
                plan.output_requirement = OutputRequirementRef.model_validate(raw)
        if plan.qos_policy is None:
            raw = self._qos_policy_from_context(plan.context)
            if isinstance(raw, dict):
                plan.qos_policy = QoSPolicyRef.model_validate(raw)
        if not plan.data_needs:
            plan.data_needs = [
                DataNeedRef.model_validate(item)
                for item in self._data_needs_from_context(plan.context, plan.tasks)
                if isinstance(item, dict)
            ]
        if not plan.repair_strategies:
            plan.repair_strategies = [
                RepairStrategyRef.model_validate(item)
                for item in self._repair_strategies_from_context(plan.context, plan.tasks)
                if isinstance(item, dict)
            ]
        return plan

    def _normalize_plan_context(
        self,
        planning_context: Dict[str, Any],
        selection_reason: str,
        revision: int,
        planning_telemetry: Dict[str, Any],
        planning_source: str,
        existing_context: Optional[Dict[str, Any]] = None,
        failed_step: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized = {
            "intent": planning_context["intent"],
            "retrieval": planning_context["retrieval"],
            "execution_hints": planning_context["execution_hints"],
            "selection_reason": selection_reason,
            "llm_provider": self.llm_provider.provider_name,
            "plan_revision": revision,
            "planning_mode": planning_context["intent"]["planning_mode"],
            "planning_source": planning_source,
            "planning_telemetry": planning_telemetry,
        }
        if isinstance(existing_context, dict):
            for key in ("pattern_id", "pattern_name", "source"):
                value = existing_context.get(key)
                if value is not None:
                    normalized[key] = value
        if failed_step is not None:
            normalized["failed_step"] = failed_step
        if error_message is not None:
            normalized["error_message"] = error_message
        return normalized

    def _reset_provider_telemetry(self) -> None:
        self.llm_provider.last_usage = None
        self.llm_provider.last_model = None

    def _generate_plan_payload(self, planning_context: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
        with self._provider_call_lock:
            self._reset_provider_telemetry()
            started_at = time.perf_counter()
            try:
                payload = self.llm_provider.generate_workflow_plan(SYSTEM_PROMPT, planning_context)
            except Exception as exc:  # noqa: BLE001
                telemetry = self._build_planning_telemetry(
                    planning_context=planning_context,
                    started_at=started_at,
                )
                raise _ProviderPlanningCallError(exc, telemetry) from exc
            telemetry = self._build_planning_telemetry(
                planning_context=planning_context,
                started_at=started_at,
            )
            return payload, telemetry

    def _build_planning_telemetry(self, planning_context: Dict[str, Any], started_at: float) -> Dict[str, Any]:
        elapsed_ms = max(0, int((time.perf_counter() - started_at) * 1000))
        model = self.llm_provider.last_model
        if model is None:
            model = getattr(self.llm_provider, "model", None)
        return {
            "elapsed_ms": elapsed_ms,
            "context_size_bytes": estimate_json_size_bytes(planning_context),
            "provider": self.llm_provider.provider_name,
            "model": model,
            "llm_usage": normalize_llm_usage(self.llm_provider.last_usage),
        }

    def _hydrate_plan_semantics(self, plan: WorkflowPlan) -> None:
        for task in plan.tasks:
            if not task.task_id:
                task.task_id = self._task_id_from_context(plan.context, task)
        if plan.task_bundle is None:
            raw = self._task_bundle_from_context(plan.context)
            if isinstance(raw, dict):
                plan.task_bundle = TaskBundleRef.model_validate(raw)
        if plan.output_requirement is None:
            raw = self._output_requirement_from_context(plan.context)
            if isinstance(raw, dict):
                plan.output_requirement = OutputRequirementRef.model_validate(raw)
        if plan.qos_policy is None:
            raw = self._qos_policy_from_context(plan.context)
            if isinstance(raw, dict):
                plan.qos_policy = QoSPolicyRef.model_validate(raw)
        if not plan.data_needs:
            plan.data_needs = [
                DataNeedRef.model_validate(item)
                for item in self._data_needs_from_context(plan.context, plan.tasks)
                if isinstance(item, dict)
            ]
        if not plan.repair_strategies:
            plan.repair_strategies = [
                RepairStrategyRef.model_validate(item)
                for item in self._repair_strategies_from_context(plan.context, plan.tasks)
                if isinstance(item, dict)
            ]

    @staticmethod
    def _task_bundle_from_context(context: Dict[str, Any] | None):
        if not isinstance(context, dict):
            return None
        intent = context.get("intent")
        if not isinstance(intent, dict):
            return None
        return intent.get("task_bundle")

    @staticmethod
    def _output_requirement_from_context(context: Dict[str, Any] | None):
        if not isinstance(context, dict):
            return None
        intent = context.get("intent")
        if not isinstance(intent, dict):
            return None
        return intent.get("output_requirement")

    @staticmethod
    def _qos_policy_from_context(context: Dict[str, Any] | None):
        if not isinstance(context, dict):
            return None
        intent = context.get("intent")
        if not isinstance(intent, dict):
            return None
        return intent.get("qos_policy")

    @staticmethod
    def _data_needs_from_context(context: Dict[str, Any] | None, tasks: List[WorkflowTask]) -> List[Dict[str, Any]]:
        if not isinstance(context, dict):
            return []
        retrieval = context.get("retrieval")
        if not isinstance(retrieval, dict):
            return []
        raw_needs = retrieval.get("data_needs")
        if not isinstance(raw_needs, list):
            return []
        task_ids = {task.task_id for task in tasks if task.task_id}
        return [item for item in raw_needs if isinstance(item, dict) and item.get("task_id") in task_ids]

    @staticmethod
    def _repair_strategies_from_context(context: Dict[str, Any] | None, tasks: List[WorkflowTask]) -> List[Dict[str, Any]]:
        if not isinstance(context, dict):
            return []
        retrieval = context.get("retrieval")
        if not isinstance(retrieval, dict):
            return []
        raw_strategies = retrieval.get("repair_strategies")
        if not isinstance(raw_strategies, list):
            return []
        task_ids = {task.task_id for task in tasks if task.task_id}
        selected: List[Dict[str, Any]] = []
        for item in raw_strategies:
            if not isinstance(item, dict):
                continue
            applies = item.get("applies_to_task_ids")
            if not isinstance(applies, list):
                continue
            if any(task_id in task_ids for task_id in applies):
                selected.append(item)
        return selected

    @staticmethod
    def _task_id_from_context(context: Dict[str, Any] | None, task: WorkflowTask) -> str | None:
        if not isinstance(context, dict):
            return None
        retrieval = context.get("retrieval")
        if not isinstance(retrieval, dict):
            return None
        task_nodes = retrieval.get("task_nodes")
        if not isinstance(task_nodes, list):
            return None
        for item in task_nodes:
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata")
            output_type = None
            input_types: List[str] = []
            if isinstance(metadata, dict):
                output_type = str(metadata.get("output_data_type") or "").strip() or None
                raw_input_types = metadata.get("input_data_types")
                if isinstance(raw_input_types, list):
                    input_types = [str(value).strip() for value in raw_input_types if str(value).strip()]
            if output_type == task.output.data_type_id and (
                not input_types or task.input.data_type_id in input_types
            ):
                value = str(item.get("task_id") or "").strip()
                if value:
                    return value
        return None

    @staticmethod
    def _infer_task_id_from_pattern_step(pattern: WorkflowPatternNode, algorithm_id: str) -> str | None:
        default_task_id = f"task.{pattern.job_type.value}.fusion"
        if any(step.algorithm_id == algorithm_id for step in pattern.steps):
            return default_task_id
        return None
