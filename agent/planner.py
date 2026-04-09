from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from agent.parameter_binding import bind_plan_parameters
from agent.retriever import PlanningContextBuilder
from kg.models import WorkflowPatternNode
from kg.repository import KGRepository
from llm.providers.base import LLMProvider
from schemas.agent import RunTrigger, WorkflowPlan, WorkflowTask
from schemas.fusion import JobType
from services.artifact_registry import ArtifactRegistry


SYSTEM_PROMPT = """
You are GeoFusion workflow planner.
Generate a strict JSON object for the workflow plan.
Rules:
1) Use only algorithms listed in candidate patterns.
2) Keep tasks executable and ordered.
3) Prefer high success-rate patterns.
4) Return valid JSON only.
"""


class WorkflowPlanner:
    def __init__(self, kg_repo: KGRepository, llm_provider: LLMProvider, artifact_registry: ArtifactRegistry | None = None) -> None:
        self.kg_repo = kg_repo
        self.llm_provider = llm_provider
        self.context_builder = PlanningContextBuilder(kg_repo, artifact_registry=artifact_registry)
        self.logger = logging.getLogger("geofusion.planner")

    def create_plan(self, run_id: str, job_type: JobType, trigger: RunTrigger) -> WorkflowPlan:
        planning_context, selection_reason = self.context_builder.build(job_type=job_type, trigger=trigger)
        candidate_patterns = planning_context["retrieval"]["candidate_patterns"]
        if not candidate_patterns:
            raise ValueError(f"No workflow pattern found for job_type={job_type.value}")

        try:
            plan_payload = self.llm_provider.generate_workflow_plan(SYSTEM_PROMPT, planning_context)
            plan = WorkflowPlan.model_validate(plan_payload)
            if not plan.tasks:
                raise ValueError("LLM returned plan with no tasks.")
            plan.trigger = trigger
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("LLM planning failed (%s), fallback to top KG pattern.", exc)
            top_pattern = self.kg_repo.get_candidate_patterns(job_type=job_type, disaster_type=trigger.disaster_type, limit=1)[0]
            plan = self._build_skeleton_plan(top_pattern, trigger=trigger)

        plan = self._finalize_plan(plan)
        plan = bind_plan_parameters(plan, self.kg_repo)
        plan.context = self._normalize_plan_context(
            planning_context=planning_context,
            selection_reason=selection_reason,
            revision=1,
        )
        return plan

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
        try:
            payload = self.llm_provider.generate_workflow_plan(SYSTEM_PROMPT, planning_context)
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
                failed_step=failed_step,
                error_message=error_message,
            )
            return plan
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Replan failed (%s), returning previous plan.", exc)
            return previous_plan

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
        return plan

    def _normalize_plan_context(
        self,
        planning_context: Dict[str, Any],
        selection_reason: str,
        revision: int,
        failed_step: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized = {
            "intent": planning_context["intent"],
            "retrieval": planning_context["retrieval"],
            "selection_reason": selection_reason,
            "llm_provider": self.llm_provider.provider_name,
            "plan_revision": revision,
        }
        if failed_step is not None:
            normalized["failed_step"] = failed_step
        if error_message is not None:
            normalized["error_message"] = error_message
        return normalized
