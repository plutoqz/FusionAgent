from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Literal

from pydantic import BaseModel, ConfigDict, Field

from benchmark_platform.canonical import canonical_sha256
from benchmark_platform.generator import GeneratedUnit
from benchmark_platform.models import BenchmarkPlatformValidationError, FailureClass, FailureRecord


_PATH_TOKEN = re.compile(r"(?:^\$)|(?:\.([A-Za-z_][A-Za-z0-9_]*))|(?:\[([0-9]+)\])")
_MISSING = object()
_NO_DEFAULT = object()


class RelationValidationError(BenchmarkPlatformValidationError):
    """Raised when a generated unit violates its frozen relation contract."""


class AssertionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    assertion_id: str
    passed: bool
    failure_code: str | None = None


class RelationValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instance_id: str
    unit_type: str
    passed: bool
    assertion_results: tuple[AssertionResult, ...]
    primary_failure_class: str | None = None
    failures: tuple[FailureRecord, ...] = Field(default=())


def _record(code: str, message: str, path: tuple[str | int, ...] = ()) -> FailureRecord:
    return FailureRecord(
        failure_class=FailureClass.RUNTIME_INVALID_STATE,
        message=message,
        path=path,
        validator="relations",
        details={"code": code},
    )


def parse_json_path(path: str) -> tuple[str | int, ...]:
    if not isinstance(path, str) or not path.startswith("$"):
        raise RelationValidationError([_record("invalid_path", f"invalid JSONPath: {path!r}")])
    tokens: list[str | int] = []
    position = 0
    for match in _PATH_TOKEN.finditer(path):
        if match.start() != position:
            raise RelationValidationError([_record("invalid_path", f"unsupported JSONPath: {path}")])
        position = match.end()
        if match.group(1) is not None:
            tokens.append(match.group(1))
        elif match.group(2) is not None:
            tokens.append(int(match.group(2)))
    if position != len(path):
        raise RelationValidationError([_record("invalid_path", f"unsupported JSONPath: {path}")])
    return tuple(tokens)


def resolve_json_path(document: Any, path: str, *, missing: Any = _NO_DEFAULT) -> Any:
    current = document
    for token in parse_json_path(path):
        if isinstance(token, str) and isinstance(current, Mapping) and token in current:
            current = current[token]
        elif isinstance(token, int) and isinstance(current, list) and token < len(current):
            current = current[token]
        else:
            if missing is _NO_DEFAULT:
                raise RelationValidationError([_record("missing_path", f"JSONPath does not resolve: {path}")])
            return missing
    return current


def _pair_values(payloads: list[dict[str, Any]], left_path: str, right_path: str | None) -> Iterable[tuple[Any, Any]]:
    if right_path:
        for payload in payloads:
            yield resolve_json_path(payload, left_path), resolve_json_path(payload, right_path)
    else:
        for left, right in zip(payloads, payloads[1:]):
            yield resolve_json_path(left, left_path), resolve_json_path(right, left_path)


def _compare(operator: str, left: Any, right: Any, expected: Any) -> bool:
    target = right if expected is None else expected
    if operator == "equals":
        return left == target
    if operator == "not_equals":
        return left != target
    if operator == "contains":
        return target in left
    if operator == "excludes":
        return target not in left
    if operator == "subset":
        return set(left).issubset(set(target))
    if operator == "superset":
        return set(left).issuperset(set(target))
    if operator == "precedes":
        return left < target
    if operator == "transitions_to":
        return left != target and right == target
    raise RelationValidationError([_record("unknown_operator", f"unknown relation operator: {operator}")])


def _variable_paths(template: Mapping[str, Any], role: str) -> list[str]:
    variables = template.get("variables", {})
    values = variables.get(role, []) if isinstance(variables, Mapping) else []
    return [item["json_path"] for item in values if isinstance(item, Mapping) and isinstance(item.get("json_path"), str)]


def _changed_paths(payloads: list[dict[str, Any]], paths: Iterable[str]) -> list[str]:
    changed: list[str] = []
    for path in paths:
        values = [resolve_json_path(payload, path, missing=_MISSING) for payload in payloads]
        if any(value != values[0] for value in values[1:]):
            changed.append(path)
    return changed


def _leaf_map(value: Any, path: str = "$") -> dict[str, Any]:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            result.update(_leaf_map(item, f"{path}.{key}"))
        return result
    if isinstance(value, list):
        result = {}
        for index, item in enumerate(value):
            result.update(_leaf_map(item, f"{path}[{index}]"))
        return result
    return {path: value}


def _changed_leaf_paths(payloads: list[dict[str, Any]]) -> set[str]:
    maps = [_leaf_map(payload) for payload in payloads]
    keys = set().union(*(item.keys() for item in maps))
    return {path for path in keys if any(item.get(path, _MISSING) != maps[0].get(path, _MISSING) for item in maps[1:])}


def _under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + ".") or path.startswith(prefix + "[")


def _unit_semantics(unit: GeneratedUnit, payloads: list[dict[str, Any]], template: Mapping[str, Any]) -> list[FailureRecord]:
    failures: list[FailureRecord] = []
    causal = _variable_paths(template, "causal_variables")
    invariants = _variable_paths(template, "invariants")
    nuisance = _variable_paths(template, "nuisance_variables")
    if unit.unit_type == "single" and len(payloads) != 1:
        failures.append(_record("invalid_member_count", "single unit must have exactly one member"))
    elif unit.unit_type == "counterfactual_pair":
        if len(payloads) != 2:
            failures.append(_record("invalid_member_count", "counterfactual pair must have exactly two members"))
        elif len(_changed_paths(payloads, causal)) != 1 or _changed_paths(payloads, invariants):
            failures.append(_record("multi_causal_drift", "counterfactual pair must change exactly one causal variable and no invariant"))
        else:
            changed_causal = _changed_paths(payloads, causal)[0]
            if any(not _under(path, changed_causal) for path in _changed_leaf_paths(payloads)):
                failures.append(_record("multi_causal_drift", "counterfactual pair changed an undeclared field"))
    elif unit.unit_type == "invariant_set":
        if len(payloads) < 2:
            failures.append(_record("invalid_member_count", "invariant set requires at least two members"))
        elif _changed_paths(payloads, [*causal, *invariants]):
            failures.append(_record("invariant_drift", "invariant set changed a causal or invariant variable"))
        elif nuisance and not _changed_paths(payloads, nuisance):
            failures.append(_record("invalid_member", "invariant set must vary at least one declared nuisance variable"))
        elif any(not any(_under(path, allowed) for allowed in nuisance) for path in _changed_leaf_paths(payloads)):
            failures.append(_record("invariant_drift", "invariant set changed an undeclared field"))
    elif unit.unit_type == "composition_family":
        task_maps: list[dict[str, Any]] = []
        for payload in payloads:
            tasks = payload.get("task_state", {}).get("tasks", [])
            task_maps.append({item.get("task_id"): item for item in tasks if isinstance(item, dict)})
        if len(payloads) < 2 or any(set(item) != set(task_maps[0]) for item in task_maps[1:]):
            failures.append(_record("cross_task_pollution", "composition family task bindings are inconsistent"))
        else:
            changed_tasks = {task_id for task_id in task_maps[0] if any(task_maps[0][task_id] != item[task_id] for item in task_maps[1:])}
            if len(changed_tasks) > 1:
                failures.append(_record("cross_task_pollution", "composition mutation leaked into multiple tasks"))
            elif changed_tasks:
                changed_id = next(iter(changed_tasks))
                task_index = next(index for index, item in enumerate(payloads[0]["task_state"]["tasks"]) if item.get("task_id") == changed_id)
                allowed_prefix = f"$.task_state.tasks[{task_index}]"
                if any(not _under(path, allowed_prefix) for path in _changed_leaf_paths(payloads)):
                    failures.append(_record("cross_task_pollution", "composition changed data outside the task-local binding"))
    elif unit.unit_type == "temporal_trace":
        if len(payloads) < 2:
            failures.append(_record("invalid_member_count", "temporal trace requires at least two members"))
        for payload in payloads:
            for task in payload.get("task_state", {}).get("tasks", []):
                steps = [event.get("step") for event in task.get("delivery_history", []) if isinstance(event, dict)]
                if steps != sorted(set(steps)):
                    failures.append(_record("illegal_transition", "delivery history steps must increase without duplicates"))
                    return failures
    return failures


def validate_relations(
    unit: GeneratedUnit,
    template: Mapping[str, Any],
    primary_failure_class: str,
    allowed_failure_classes: Iterable[str],
) -> RelationValidationReport:
    if primary_failure_class not in set(allowed_failure_classes):
        raise RelationValidationError([_record("unknown_failure_class", f"failure class is not frozen: {primary_failure_class}")])
    payloads = [member.member_payload for member in unit.members]
    integrity_failures = [
        _record("member_hash_mismatch", f"member hash mismatch at index {member.member_index}")
        for member in unit.members
        if canonical_sha256(member.member_payload) != member.member_sha256
    ]
    failures = integrity_failures or _unit_semantics(unit, payloads, template)
    results: list[AssertionResult] = []
    for assertion in template.get("experiment_unit", {}).get("relation_assertions", []):
        assertion_id = str(assertion.get("assertion_id", ""))
        try:
            if assertion.get("operator") == "present":
                passed = all(resolve_json_path(payload, assertion["left_path"], missing=_MISSING) is not _MISSING for payload in payloads)
            else:
                pairs = list(_pair_values(payloads, assertion["left_path"], assertion.get("right_path")))
                passed = bool(pairs) and all(_compare(assertion["operator"], left, right, assertion.get("expected_value")) for left, right in pairs)
        except (KeyError, TypeError, RelationValidationError):
            passed = False
        results.append(AssertionResult(assertion_id=assertion_id, passed=passed, failure_code=None if passed else "relation_assertion_failed"))
        if not passed:
            failures.append(_record("relation_assertion_failed", f"relation assertion failed: {assertion_id}"))
    passed = not failures
    return RelationValidationReport(
        instance_id=unit.instance_id,
        unit_type=unit.unit_type,
        passed=passed,
        assertion_results=tuple(results),
        primary_failure_class=None if passed else primary_failure_class,
        failures=tuple(failures[:1]),
    )
