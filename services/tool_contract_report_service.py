from __future__ import annotations

from typing import Any

from agent.tooling import ToolRegistry, build_default_tool_registry
from kg.repository import KGRepository
from schemas.agent import WorkflowPlan, WorkflowTask
from services.runtime_contract_service import RuntimeContractService


UNKNOWN_TOOL = "UNKNOWN_TOOL"
TOOL_INPUT_TYPE_MISMATCH = "TOOL_INPUT_TYPE_MISMATCH"
TOOL_OUTPUT_TYPE_MISMATCH = "TOOL_OUTPUT_TYPE_MISMATCH"
RESERVATION_ONLY_TOOL = "RESERVATION_ONLY_TOOL"


def build_tool_contract_report(
    plan: WorkflowPlan,
    *,
    registry: ToolRegistry | None = None,
    kg_repo: KGRepository | None = None,
) -> dict[str, Any]:
    tool_registry = registry or build_default_tool_registry()
    runtime_contract = RuntimeContractService(kg_repo, tool_registry=tool_registry) if kg_repo is not None else None
    steps = [
        _build_step_report(task, tool_registry, runtime_contract)
        for task in sorted(plan.tasks, key=lambda item: item.step)
    ]
    known_step_count = sum(1 for step in steps if step["known"])
    blocking_issue_codes = {
        UNKNOWN_TOOL,
        TOOL_INPUT_TYPE_MISMATCH,
        TOOL_OUTPUT_TYPE_MISMATCH,
        "DEPRECATED_ALGORITHM",
        "RESERVED_ALGORITHM",
        "UNSELECTABLE_ALGORITHM",
        "MISSING_RUNTIME_STATUS",
        "RESEARCH_UTILITY_ALGORITHM",
        "RESERVED_TOOL",
    }
    valid = all(
        not any(code in blocking_issue_codes for code in step["issue_codes"])
        for step in steps
    )
    return {
        "valid": valid,
        "known_step_count": known_step_count,
        "total_step_count": len(steps),
        "steps": steps,
    }


def _build_step_report(
    task: WorkflowTask,
    registry: ToolRegistry,
    runtime_contract: RuntimeContractService | None,
) -> dict[str, Any]:
    spec = registry.get(task.algorithm_id)
    runtime_contract_payload = None
    if runtime_contract is not None:
        contract_decision = runtime_contract.evaluate_algorithm(task.algorithm_id, surface="tool_contract_report")
        runtime_contract_payload = contract_decision.to_dict()
    if spec is None:
        issue_codes = [UNKNOWN_TOOL]
        if (
            runtime_contract_payload is not None
            and not runtime_contract_payload.get("allowed")
            and runtime_contract_payload.get("reason_code")
        ):
            issue_codes.append(str(runtime_contract_payload["reason_code"]))
        return {
            "step": task.step,
            "algorithm_id": task.algorithm_id,
            "known": False,
            "reserved": False,
            "handler_name": None,
            "input_types": [],
            "output_type": None,
            "timeout_seconds": None,
            "retry_count": None,
            "error_policy": {},
            "runtime_contract": runtime_contract_payload,
            "issue_codes": list(dict.fromkeys(issue_codes)),
            "evidence_refs": [
                f"plan.task(step={task.step}).algorithm_id",
                "agent.tooling.ToolRegistry",
            ],
        }

    issue_codes: list[str] = []
    if task.input.data_type_id not in spec.input_types:
        issue_codes.append(TOOL_INPUT_TYPE_MISMATCH)
    if task.output.data_type_id != spec.output_type:
        issue_codes.append(TOOL_OUTPUT_TYPE_MISMATCH)
    reserved = spec.error_policy.get("reserved") == "true"
    if reserved:
        issue_codes.append(RESERVATION_ONLY_TOOL)
    if (
        runtime_contract_payload is not None
        and not runtime_contract_payload.get("allowed")
        and runtime_contract_payload.get("reason_code")
    ):
        issue_codes.append(str(runtime_contract_payload["reason_code"]))

    return {
        "step": task.step,
        "algorithm_id": task.algorithm_id,
        "known": True,
        "reserved": reserved,
        "handler_name": spec.handler_name,
        "input_types": list(spec.input_types),
        "output_type": spec.output_type,
        "timeout_seconds": spec.timeout_seconds,
        "retry_count": spec.retry_count,
        "error_policy": dict(spec.error_policy),
        "runtime_contract": runtime_contract_payload,
        "issue_codes": list(dict.fromkeys(issue_codes)),
        "evidence_refs": [
            f"plan.task(step={task.step}).algorithm_id",
            f"plan.task(step={task.step}).input.data_type_id",
            f"plan.task(step={task.step}).output.data_type_id",
            "agent.tooling.ToolRegistry",
        ],
    }
