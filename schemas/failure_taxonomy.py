from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from kg.knowledge_release import KnowledgeReleaseError
from kg.policy_registry import KnowledgePolicyRegistry, default_policy_registry


class FailureDetails(BaseModel):
    failure_category: str
    root_cause: str
    recoverable: bool
    suggested_action: str


def classify_failure_category(
    raw: str | None,
    *,
    scope: str = "general",
    error_type: str | None = None,
    policy_registry: KnowledgePolicyRegistry | None = None,
) -> str:
    registry = policy_registry or default_policy_registry()
    policy = registry.failure_classification_policy()
    normalized_scope = str(scope or "general").strip().lower()
    text = str(raw or "").strip().casefold()
    if not text:
        return _scope_default(policy, "empty_by_scope", normalized_scope)

    rules = policy.get("rules")
    if not isinstance(rules, list) or not rules:
        raise KnowledgeReleaseError("fault_policy.classification.rules must be a non-empty list")
    ordered_rules = sorted(
        (rule for rule in rules if isinstance(rule, dict)),
        key=lambda rule: (int(rule.get("priority") or 0), str(rule.get("failure_class") or "")),
    )
    normalized_error_type = str(error_type or "").strip()
    for rule in ordered_rules:
        scopes = {str(item).strip().lower() for item in rule.get("scopes", [])}
        if normalized_scope not in scopes and "*" not in scopes:
            continue
        if _failure_rule_matches(rule, text=text, error_type=normalized_error_type):
            failure_class = str(rule.get("failure_class") or "").strip()
            if not failure_class:
                raise KnowledgeReleaseError("Failure classification rule has an empty failure_class")
            return failure_class
    return _scope_default(policy, "default_by_scope", normalized_scope)


def _failure_rule_matches(rule: dict[str, object], *, text: str, error_type: str) -> bool:
    exception_types = {str(item).strip() for item in rule.get("exception_types", [])}
    if error_type and error_type in exception_types:
        return True
    match_any = [str(item).casefold() for item in rule.get("match_any", []) if str(item)]
    if any(term in text for term in match_any):
        return True
    alternatives = rule.get("match_all_alternatives", [])
    if not isinstance(alternatives, list):
        raise KnowledgeReleaseError("Failure classification match_all_alternatives must be a list")
    for alternative in alternatives:
        if not isinstance(alternative, list) or not alternative:
            continue
        if all(str(term).casefold() in text for term in alternative):
            return True
    return False


def _scope_default(policy: dict[str, object], section: str, scope: str) -> str:
    defaults = policy.get(section)
    if not isinstance(defaults, dict):
        raise KnowledgeReleaseError(f"fault_policy.classification.{section} must be an object")
    value = defaults.get(scope, defaults.get("general"))
    if not isinstance(value, str):
        raise KnowledgeReleaseError(
            f"fault_policy.classification.{section} has no string default for scope {scope}"
        )
    return value


def classify_failure_details(
    *,
    error: str | None = None,
    reason_code: str | None = None,
    recoverable: Optional[bool] = None,
    suggested_action: Optional[str] = None,
) -> FailureDetails:
    root_cause = str(reason_code or "unknown_reason").strip().upper()
    if not root_cause:
        root_cause = "UNKNOWN_REASON"
    category = classify_failure_category(reason_code or error)
    resolved_recoverable = True if recoverable is None else bool(recoverable)
    resolved_action = str(suggested_action or ("replan" if resolved_recoverable else "inspect_and_retry")).strip()
    if not resolved_action:
        resolved_action = "replan" if resolved_recoverable else "inspect_and_retry"
    return FailureDetails(
        failure_category=category,
        root_cause=root_cause,
        recoverable=resolved_recoverable,
        suggested_action=resolved_action,
    )
