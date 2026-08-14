from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agent.tooling import ToolRegistry, build_default_tool_registry
from kg.policy_registry import default_policy_registry
from kg.repository import KGRepository
from schemas.agent import (
    ProductContractRef,
    RepairStrategyRef,
    RunTrigger,
    RunTriggerType,
    WorkflowPlan,
    WorkflowTask,
    WorkflowTaskInput,
    WorkflowTaskOutput,
)
from schemas.research_case_manifest import ResearchCase
from schemas.research_llm_pilot import ResearchPlanTask, ResearchPlanningDecision
from schemas.task_kind import TaskKind, task_kind_output_type, task_kind_to_job_type
from services.runtime_contract_service import RuntimeContractService


EXECUTABLE_DELIVERY_STATES = {"planned", "provisional", "degraded"}
NON_EXECUTABLE_DELIVERY_STATES = {"pending", "gap", "rejected"}


class ResearchTaskResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: int
    task_kind: str
    resolution_status: Literal["resolved", "rejected", "not_executable"]
    selected: dict[str, Any]
    resolved: dict[str, Any] = Field(default_factory=dict)
    reason_codes: list[str] = Field(default_factory=list)
    workflow_task: WorkflowTask | None = None


class ResearchPlanRuntimeResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_id: str = "fusionagent.research-plan-runtime-resolution.v1"
    case_id: str
    condition: str
    status: Literal["resolved", "partial", "rejected", "not_executable"]
    selected: dict[str, Any]
    resolved: dict[str, Any] = Field(default_factory=dict)
    executed: dict[str, Any] = Field(default_factory=lambda: {"status": "not_executed"})
    evaluated: dict[str, Any] = Field(default_factory=lambda: {"status": "not_evaluated"})
    task_resolutions: list[ResearchTaskResolution] = Field(default_factory=list)
    workflow_plan: WorkflowPlan | None = None


class ResearchPlanRuntimeAdapter:
    def __init__(self, kg_repo: KGRepository, *, tool_registry: ToolRegistry | None = None) -> None:
        self.kg_repo = kg_repo
        self.tool_registry = tool_registry or build_default_tool_registry()
        self.runtime_contract = RuntimeContractService(kg_repo, tool_registry=self.tool_registry)
        self.sources = {source.source_id: source for source in kg_repo.list_data_sources()}
        self.contracts = {contract.contract_id: contract for contract in kg_repo.get_product_contracts(None)}
        self.repair_strategies = {
            strategy.strategy_id: strategy for strategy in kg_repo.list_repair_strategies()
        }

    def resolve(
        self,
        *,
        case: ResearchCase,
        condition: str,
        decision: ResearchPlanningDecision,
    ) -> ResearchPlanRuntimeResolution:
        contract, contract_reasons = self._resolve_contract(case)
        task_resolutions = [self._resolve_task(task) for task in sorted(decision.tasks, key=lambda item: item.order)]
        executable = [item for item in task_resolutions if item.resolution_status == "resolved"]
        rejected = [item for item in task_resolutions if item.resolution_status == "rejected"]
        unresolved_reasons = sorted({reason for item in rejected for reason in item.reason_codes} | set(contract_reasons))

        for step, item in enumerate(executable, start=1):
            if item.workflow_task is not None:
                item.workflow_task.step = step

        workflow_plan = None
        if executable and not contract_reasons:
            executable_task_ids = {
                item.workflow_task.task_id
                for item in executable
                if item.workflow_task is not None and item.workflow_task.task_id
            }
            repair_strategies = [
                RepairStrategyRef.model_validate(asdict(strategy))
                for strategy_id in contract.repair_strategy_ids
                if (strategy := self.repair_strategies.get(strategy_id)) is not None
                and (
                    not strategy.applies_to_task_ids
                    or bool(executable_task_ids.intersection(strategy.applies_to_task_ids))
                )
            ]
            workflow_plan = WorkflowPlan(
                workflow_id=f"research-{case.case_id.lower()}-{condition}",
                trigger=RunTrigger(
                    type=RunTriggerType.user_query,
                    content=f"Research case {case.case_id}",
                    disaster_type=case.scenario.disaster_type,
                ),
                context={
                    "research_protocol": "fusionagent.research-plan-runtime-resolution.v1",
                    "case_id": case.case_id,
                    "condition": condition,
                    "decision": decision.decision,
                    "knowledge_identity": self.kg_repo.get_knowledge_identity(),
                },
                tasks=[item.workflow_task for item in executable if item.workflow_task is not None],
                expected_output=contract.product_type,
                product_contract=ProductContractRef.model_validate(asdict(contract)),
                repair_strategies=repair_strategies,
            )

        if rejected or contract_reasons:
            status = "partial" if workflow_plan is not None else "rejected"
        elif workflow_plan is not None:
            status = "resolved"
        else:
            status = "not_executable"

        return ResearchPlanRuntimeResolution(
            case_id=case.case_id,
            condition=condition,
            status=status,
            selected={
                "decision": decision.decision,
                "contract_ids": list(case.request_scope.contract_ids),
                "task_count": len(decision.tasks),
            },
            resolved={
                "contract_id": contract.contract_id if contract is not None else None,
                "workflow_task_count": len(executable),
                "reason_codes": unresolved_reasons,
                "knowledge_identity": self.kg_repo.get_knowledge_identity(),
            },
            task_resolutions=task_resolutions,
            workflow_plan=workflow_plan,
        )

    def _resolve_contract(self, case: ResearchCase) -> tuple[Any | None, list[str]]:
        contract_ids = list(case.request_scope.contract_ids)
        if len(contract_ids) != 1:
            return None, ["REQUIRES_SINGLE_PRODUCT_CONTRACT"]
        contract = self.contracts.get(contract_ids[0])
        if contract is None:
            return None, ["UNKNOWN_PRODUCT_CONTRACT"]
        if case.scenario.disaster_type not in contract.disaster_types:
            return None, ["PRODUCT_CONTRACT_DISASTER_MISMATCH"]
        return contract, []

    def _resolve_task(self, task: ResearchPlanTask) -> ResearchTaskResolution:
        selected = {
            "task_kind": task.task_kind,
            "source_ids": list(task.source_ids),
            "algorithm_id": task.algorithm_id,
            "delivery_state": task.delivery_state,
        }
        if task.delivery_state in NON_EXECUTABLE_DELIVERY_STATES:
            return ResearchTaskResolution(
                order=task.order,
                task_kind=task.task_kind,
                resolution_status="not_executable",
                selected=selected,
                reason_codes=[f"DELIVERY_STATE_{task.delivery_state.upper()}"],
            )

        reasons: list[str] = []
        if task.delivery_state not in EXECUTABLE_DELIVERY_STATES:
            reasons.append("UNKNOWN_DELIVERY_STATE")
        if not task.algorithm_id:
            reasons.append("MISSING_ALGORITHM")
        if len(task.source_ids) != 1:
            reasons.append("REQUIRES_SINGLE_EFFECTIVE_SOURCE")

        algorithm = self.kg_repo.get_algorithm(task.algorithm_id) if task.algorithm_id else None
        tool = self.tool_registry.get(task.algorithm_id) if task.algorithm_id else None
        if task.algorithm_id and algorithm is None:
            reasons.append("UNKNOWN_ALGORITHM")
        if task.algorithm_id and algorithm is not None:
            contract = self.runtime_contract.evaluate_algorithm(task.algorithm_id, surface="research_plan_adapter")
            if not contract.allowed:
                reasons.append(contract.reason_code or "ALGORITHM_NOT_RUNTIME_SELECTABLE")
            task_kind = TaskKind(task.task_kind)
            if algorithm.output_type != task_kind_output_type(task_kind):
                reasons.append("ALGORITHM_TASK_KIND_MISMATCH")
        if task.algorithm_id and tool is None:
            reasons.append("UNKNOWN_TOOL")

        source_id = task.source_ids[0] if len(task.source_ids) == 1 else None
        source = self.sources.get(source_id) if source_id else None
        if source_id and source is None:
            reasons.append("UNKNOWN_DATA_SOURCE")
        if source_id and source is not None:
            source_contract = self.runtime_contract.evaluate_data_source(source_id, surface="research_plan_adapter")
            if not source_contract.allowed:
                reasons.append(source_contract.reason_code or "DATA_SOURCE_NOT_RUNTIME_SELECTABLE")
            if task_kind_to_job_type(TaskKind(task.task_kind)).value not in source.supported_job_types:
                reasons.append("DATA_SOURCE_TASK_KIND_MISMATCH")

        input_type = None
        output_type = None
        handler_name = None
        if algorithm is not None and tool is not None:
            shared_inputs = [value for value in tool.input_types if value in algorithm.input_types]
            compatible_inputs = [value for value in shared_inputs if source is not None and value in source.supported_types]
            if not compatible_inputs:
                reasons.append("SOURCE_ALGORITHM_INPUT_TYPE_MISMATCH")
            elif len(compatible_inputs) > 1:
                reasons.append("AMBIGUOUS_ALGORITHM_INPUT_TYPE")
            else:
                input_type = compatible_inputs[0]
            if tool.output_type != algorithm.output_type:
                reasons.append("TOOL_ALGORITHM_OUTPUT_TYPE_MISMATCH")
            else:
                output_type = algorithm.output_type
            handler_name = tool.handler_name

        unique_reasons = sorted(set(reasons))
        resolved = {
            "effective_source_id": source_id if source is not None else None,
            "component_source_ids": list((source.metadata or {}).get("component_source_ids", [])) if source else [],
            "effective_algorithm_id": task.algorithm_id if algorithm is not None else None,
            "input_data_type": input_type,
            "output_data_type": output_type,
            "handler_name": handler_name,
        }
        if unique_reasons:
            return ResearchTaskResolution(
                order=task.order,
                task_kind=task.task_kind,
                resolution_status="rejected",
                selected=selected,
                resolved=resolved,
                reason_codes=unique_reasons,
            )

        workflow_task = WorkflowTask(
            step=task.order,
            name=f"research_{task.task_kind}",
            description=task.rationale,
            task_id=str(default_policy_registry().task_record(task.task_kind)["task_id"]),
            algorithm_id=task.algorithm_id,
            input=WorkflowTaskInput(data_type_id=input_type, data_source_id=source_id),
            output=WorkflowTaskOutput(data_type_id=output_type, description=f"Research {task.task_kind} output"),
            kg_validated=True,
        )
        return ResearchTaskResolution(
            order=task.order,
            task_kind=task.task_kind,
            resolution_status="resolved",
            selected=selected,
            resolved=resolved,
            workflow_task=workflow_task,
        )
