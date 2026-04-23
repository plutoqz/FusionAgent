from __future__ import annotations

from typing import Any

from schemas.agent import WorkflowPlan, WorkflowTask


ALGORITHM_NOT_IN_CANDIDATE_PATTERNS = "ALGORITHM_NOT_IN_CANDIDATE_PATTERNS"
CANDIDATE_PATTERN_STEP_MISMATCH = "CANDIDATE_PATTERN_STEP_MISMATCH"
DATA_SOURCE_NOT_IN_RETRIEVAL = "DATA_SOURCE_NOT_IN_RETRIEVAL"
OUTPUT_TYPE_MISMATCH = "OUTPUT_TYPE_MISMATCH"
SCHEMA_POLICY_NOT_IN_RETRIEVAL = "SCHEMA_POLICY_NOT_IN_RETRIEVAL"


def build_plan_grounding_report(plan: WorkflowPlan) -> dict[str, Any]:
    context = _context_dict(plan)
    retrieval = context.get("retrieval", {})
    if not isinstance(retrieval, dict):
        retrieval = {}

    candidate_patterns = retrieval.get("candidate_patterns")
    candidate_steps = _candidate_pattern_steps(candidate_patterns)
    algorithm_pattern_ids = _algorithm_pattern_ids(candidate_patterns)
    candidate_algorithm_ids = set(algorithm_pattern_ids)
    known_algorithm_ids = _algorithm_ids(retrieval.get("algorithms")) | candidate_algorithm_ids
    known_data_source_ids = _data_source_ids(retrieval.get("data_sources"))
    known_schema_output_types = _schema_output_types(retrieval.get("output_schema_policies"))

    intent = context.get("intent", {})
    if not isinstance(intent, dict):
        intent = {}
    expected_output_type = _clean_str(intent.get("expected_output_type"))

    step_reports = [
        _build_step_report(
            task=task,
            candidate_steps=candidate_steps,
            algorithm_pattern_ids=algorithm_pattern_ids,
            known_algorithm_ids=known_algorithm_ids,
            known_data_source_ids=known_data_source_ids,
            known_schema_output_types=known_schema_output_types,
            expected_output_type=expected_output_type,
        )
        for task in sorted(plan.tasks, key=lambda item: item.step)
        if not task.is_transform
    ]

    grounded_step_count = sum(1 for step in step_reports if not step["issue_codes"])
    total_step_count = len(step_reports)
    grounding_score = 1.0 if total_step_count == 0 else grounded_step_count / total_step_count
    return {
        "grounded": grounded_step_count == total_step_count,
        "grounded_step_count": grounded_step_count,
        "total_step_count": total_step_count,
        "grounding_score": grounding_score,
        "steps": step_reports,
    }


def ensure_plan_grounding_report(plan: WorkflowPlan) -> dict[str, Any]:
    report = build_plan_grounding_report(plan)
    _context_dict(plan)["grounding_report"] = report
    return report


def grounding_report_matches_plan(plan: WorkflowPlan, report: object) -> bool:
    if not isinstance(report, dict):
        return False
    step_reports = report.get("steps")
    if not isinstance(step_reports, list):
        return False

    executable_tasks = sorted((task for task in plan.tasks if not task.is_transform), key=lambda item: item.step)
    if report.get("total_step_count") != len(executable_tasks):
        return False
    if len(step_reports) != len(executable_tasks):
        return False

    for task, step_report in zip(executable_tasks, step_reports):
        if not isinstance(step_report, dict):
            return False
        if step_report.get("step") != task.step:
            return False
        if step_report.get("algorithm_id") != task.algorithm_id:
            return False
        if step_report.get("input_data_type") != task.input.data_type_id:
            return False
        if step_report.get("data_source_id") != task.input.data_source_id:
            return False
        if step_report.get("output_data_type") != task.output.data_type_id:
            return False
    return True


def _build_step_report(
    *,
    task: WorkflowTask,
    candidate_steps: list[dict[str, str]],
    algorithm_pattern_ids: dict[str, list[str]],
    known_algorithm_ids: set[str],
    known_data_source_ids: set[str],
    known_schema_output_types: set[str],
    expected_output_type: str | None,
) -> dict[str, Any]:
    algorithm_id = task.algorithm_id
    input_data_type = task.input.data_type_id
    data_source_id = task.input.data_source_id
    output_type = task.output.data_type_id

    pattern_ids = algorithm_pattern_ids.get(algorithm_id, [])
    fully_matched_pattern_ids = _fully_matched_pattern_ids(task, candidate_steps)
    algorithm_grounded = bool(pattern_ids)
    algorithm_known = algorithm_id in known_algorithm_ids
    data_source_known = data_source_id in known_data_source_ids
    schema_policy_known = output_type in known_schema_output_types
    output_type_matches_intent = expected_output_type is None or output_type == expected_output_type

    issue_codes: list[str] = []
    if not algorithm_grounded:
        issue_codes.append(ALGORITHM_NOT_IN_CANDIDATE_PATTERNS)
    elif not fully_matched_pattern_ids:
        issue_codes.append(CANDIDATE_PATTERN_STEP_MISMATCH)
    if not data_source_known:
        issue_codes.append(DATA_SOURCE_NOT_IN_RETRIEVAL)
    if not output_type_matches_intent:
        issue_codes.append(OUTPUT_TYPE_MISMATCH)
    if not schema_policy_known:
        issue_codes.append(SCHEMA_POLICY_NOT_IN_RETRIEVAL)

    evidence_refs = [
        f"plan.task(step={task.step}).algorithm_id",
        f"plan.task(step={task.step}).input.data_type_id",
        f"plan.task(step={task.step}).input.data_source_id",
        f"plan.task(step={task.step}).output.data_type_id",
        "context.retrieval.candidate_patterns",
        "context.retrieval.data_sources",
        "context.retrieval.output_schema_policies",
    ]
    if expected_output_type is not None:
        evidence_refs.append("context.intent.expected_output_type")

    return {
        "step": task.step,
        "algorithm_id": algorithm_id,
        "input_data_type": input_data_type,
        "data_source_id": data_source_id,
        "output_data_type": output_type,
        "algorithm_grounded": algorithm_grounded,
        "algorithm_known": algorithm_known,
        "data_source_known": data_source_known,
        "output_type_matches_intent": output_type_matches_intent,
        "schema_policy_known": schema_policy_known,
        "pattern_ids": pattern_ids,
        "issue_codes": issue_codes,
        "evidence_refs": evidence_refs,
    }


def _fully_matched_pattern_ids(task: WorkflowTask, candidate_steps: list[dict[str, str]]) -> list[str]:
    matches: list[str] = []
    for candidate_step in candidate_steps:
        if candidate_step["algorithm_id"] != task.algorithm_id:
            continue
        if candidate_step["input_data_type"] != task.input.data_type_id:
            continue
        if candidate_step["data_source_id"] != task.input.data_source_id:
            continue
        if candidate_step["output_data_type"] != task.output.data_type_id:
            continue
        pattern_id = candidate_step["pattern_id"]
        if pattern_id not in matches:
            matches.append(pattern_id)
    return matches


def _candidate_pattern_steps(raw_candidate_patterns: Any) -> list[dict[str, str]]:
    candidate_steps: list[dict[str, str]] = []
    for pattern_index, raw_pattern in enumerate(_as_list(raw_candidate_patterns)):
        if not isinstance(raw_pattern, dict):
            continue
        pattern_id = _clean_str(raw_pattern.get("pattern_id")) or f"candidate_patterns[{pattern_index}]"
        for raw_step in _as_list(raw_pattern.get("steps")):
            if not isinstance(raw_step, dict):
                continue
            algorithm_id = _clean_str(raw_step.get("algorithm_id"))
            input_data_type = _clean_str(raw_step.get("input_data_type"))
            data_source_id = _clean_str(raw_step.get("data_source_id"))
            output_data_type = _clean_str(raw_step.get("output_data_type"))
            if (
                algorithm_id is None
                or input_data_type is None
                or data_source_id is None
                or output_data_type is None
            ):
                continue
            candidate_steps.append(
                {
                    "pattern_id": pattern_id,
                    "algorithm_id": algorithm_id,
                    "input_data_type": input_data_type,
                    "data_source_id": data_source_id,
                    "output_data_type": output_data_type,
                }
            )
    return candidate_steps


def _algorithm_pattern_ids(raw_candidate_patterns: Any) -> dict[str, list[str]]:
    pattern_ids_by_algorithm: dict[str, list[str]] = {}
    for pattern_index, raw_pattern in enumerate(_as_list(raw_candidate_patterns)):
        if not isinstance(raw_pattern, dict):
            continue
        pattern_id = _clean_str(raw_pattern.get("pattern_id")) or f"candidate_patterns[{pattern_index}]"
        for raw_step in _as_list(raw_pattern.get("steps")):
            if not isinstance(raw_step, dict):
                continue
            algorithm_id = _clean_str(raw_step.get("algorithm_id"))
            if algorithm_id is None:
                continue
            pattern_ids_by_algorithm.setdefault(algorithm_id, [])
            if pattern_id not in pattern_ids_by_algorithm[algorithm_id]:
                pattern_ids_by_algorithm[algorithm_id].append(pattern_id)
    return pattern_ids_by_algorithm


def _algorithm_ids(raw_algorithms: Any) -> set[str]:
    if isinstance(raw_algorithms, dict):
        return {_cleaned for value in raw_algorithms.keys() if (_cleaned := _clean_str(value)) is not None}
    ids: set[str] = set()
    for raw in _as_list(raw_algorithms):
        if isinstance(raw, str):
            cleaned = _clean_str(raw)
        elif isinstance(raw, dict):
            cleaned = _clean_str(raw.get("algorithm_id") or raw.get("id"))
        else:
            cleaned = None
        if cleaned is not None:
            ids.add(cleaned)
    return ids


def _data_source_ids(raw_data_sources: Any) -> set[str]:
    ids: set[str] = set()
    for raw in _as_list(raw_data_sources):
        if isinstance(raw, str):
            cleaned = _clean_str(raw)
        elif isinstance(raw, dict):
            cleaned = _clean_str(raw.get("source_id") or raw.get("id"))
        else:
            cleaned = None
        if cleaned is not None:
            ids.add(cleaned)
    return ids


def _schema_output_types(raw_schema_policies: Any) -> set[str]:
    if isinstance(raw_schema_policies, dict):
        output_types = {_cleaned for value in raw_schema_policies.keys() if (_cleaned := _clean_str(value)) is not None}
        for raw in raw_schema_policies.values():
            if isinstance(raw, dict):
                cleaned = _clean_str(raw.get("output_type"))
                if cleaned is not None:
                    output_types.add(cleaned)
        return output_types

    output_types: set[str] = set()
    for raw in _as_list(raw_schema_policies):
        if isinstance(raw, str):
            cleaned = _clean_str(raw)
        elif isinstance(raw, dict):
            cleaned = _clean_str(raw.get("output_type") or raw.get("data_type_id") or raw.get("type_id"))
        else:
            cleaned = None
        if cleaned is not None:
            output_types.add(cleaned)
    return output_types


def _context_dict(plan: WorkflowPlan) -> dict[str, Any]:
    if isinstance(plan.context, dict):
        return plan.context
    plan.context = {}
    return plan.context


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None
