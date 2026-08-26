from __future__ import annotations

from copy import deepcopy
import json
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict

from benchmark_platform.models import BenchmarkPlatformValidationError, FailureClass, FailureRecord
from benchmark_platform.relations import parse_json_path, resolve_json_path


class ViewProjectionError(BenchmarkPlatformValidationError):
    """Raised when allowlist projection or leakage validation fails."""


class ViewPacket(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    view: str
    payload: dict[str, Any]


class LeakageAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: bool
    forbidden_path_hits: tuple[str, ...]


class ProjectedViews(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    planner: ViewPacket
    evaluator: ViewPacket
    human_blind: ViewPacket
    leakage_audit: LeakageAudit


def _record(code: str, message: str) -> FailureRecord:
    return FailureRecord(
        failure_class=FailureClass.RUNTIME_INVALID_STATE,
        message=message,
        validator="views",
        details={"code": code},
    )


def _assign(target: dict[str, Any], tokens: tuple[str | int, ...], value: Any) -> None:
    current: Any = target
    for index, token in enumerate(tokens):
        last = index == len(tokens) - 1
        if isinstance(token, str):
            if not isinstance(current, dict):
                raise ViewProjectionError([_record("invalid_path", "view path conflicts with another allowlist path")])
            if last:
                current[token] = deepcopy(value)
            else:
                next_token = tokens[index + 1]
                current = current.setdefault(token, [] if isinstance(next_token, int) else {})
        else:
            if not isinstance(current, list):
                raise ViewProjectionError([_record("invalid_path", "array index used under non-array view path")])
            while len(current) <= token:
                current.append(None)
            if last:
                current[token] = deepcopy(value)
            else:
                next_token = tokens[index + 1]
                if current[token] is None:
                    current[token] = [] if isinstance(next_token, int) else {}
                current = current[token]


def project_allowlist(document: Mapping[str, Any], paths: list[str]) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    for path in paths:
        tokens = parse_json_path(path)
        if not tokens:
            raise ViewProjectionError([_record("invalid_path", "root-only view path is forbidden")])
        try:
            value = resolve_json_path(document, path)
        except BenchmarkPlatformValidationError as error:
            raise ViewProjectionError([_record("missing_view_path", f"view allowlist path does not resolve: {path}")]) from error
        _assign(projected, tokens, value)
    return projected


def _overlaps(path: str, forbidden: str) -> bool:
    return path == forbidden or path.startswith(forbidden + ".") or path.startswith(forbidden + "[") or forbidden.startswith(path + ".") or forbidden.startswith(path + "[")


def _walk(value: Any) -> list[Any]:
    values = [value]
    if isinstance(value, dict):
        for item in value.values():
            values.extend(_walk(item))
    elif isinstance(value, list):
        for item in value:
            values.extend(_walk(item))
    return values


def _identity_keys(value: Any) -> set[str]:
    forbidden = {"condition", "condition_label", "method_condition", "run_id"}
    found: set[str] = set()
    if isinstance(value, dict):
        found.update(forbidden.intersection(value))
        for item in value.values():
            found.update(_identity_keys(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_identity_keys(item))
    return found


def project_views(document: Mapping[str, Any], contract: Mapping[str, Any]) -> ProjectedViews:
    planner_paths = list(contract.get("planner_visible_paths", []))
    evaluator_paths = list(contract.get("evaluator_only_paths", []))
    human_paths = list(contract.get("human_blind_paths", []))
    forbidden = list(contract.get("planner_forbidden_path_prefixes", []))
    protected = [*forbidden, *evaluator_paths]
    hits = tuple(sorted({path for path in planner_paths for prefix in protected if _overlaps(path, prefix)}))
    if hits:
        raise ViewProjectionError([_record("forbidden_path_visible", f"planner allowlist overlaps forbidden paths: {', '.join(hits)}")])
    planner = project_allowlist(document, planner_paths)
    evaluator = project_allowlist(document, evaluator_paths)
    human = project_allowlist(document, human_paths)
    forbidden_keys = {parse_json_path(path)[0] for path in forbidden}
    leaked_keys = {str(key) for key in forbidden_keys if key in planner}
    leaked_keys.update(_identity_keys(planner))
    planner_values = {json.dumps(value, sort_keys=True, ensure_ascii=False) for value in _walk(planner) if isinstance(value, (dict, list)) and value}
    for path in evaluator_paths:
        protected_value = resolve_json_path(document, path)
        if isinstance(protected_value, (dict, list)) and protected_value and json.dumps(protected_value, sort_keys=True, ensure_ascii=False) in planner_values:
            leaked_keys.add(path)
    leaked = tuple(sorted(leaked_keys))
    audit = LeakageAudit(passed=not leaked, forbidden_path_hits=leaked)
    if not audit.passed:
        raise ViewProjectionError([_record("gold_value_leak", "planner packet contains a forbidden subtree")])
    return ProjectedViews(
        planner=ViewPacket(view="planner", payload=planner),
        evaluator=ViewPacket(view="evaluator", payload=evaluator),
        human_blind=ViewPacket(view="human_blind", payload=human),
        leakage_audit=audit,
    )
