from __future__ import annotations

from typing import Any

from kg.policy_registry import KnowledgePolicyRegistry, default_policy_registry


def _job_type_value(job_type: Any) -> str:
    return str(getattr(job_type, "value", job_type))


def classify_unsupported_intent(
    content: str,
    *,
    job_type: str,
    policy_registry: KnowledgePolicyRegistry | None = None,
) -> list[dict[str, str]]:
    normalized = str(content or "").casefold()
    normalized_job_type = _job_type_value(job_type).casefold()
    registry = policy_registry or default_policy_registry()
    for rule in registry.unsupported_intent_rules():
        job_types = {str(item).casefold() for item in rule.get("job_types", [])}
        if normalized_job_type not in job_types:
            continue
        matched_keyword = _matched_rule_keyword(rule, normalized)
        if matched_keyword is not None:
            return [_issue_payload(rule, matched_keyword, normalized_job_type)]
    return []


def _matched_rule_keyword(rule: dict[str, Any], normalized: str) -> str | None:
    for keyword in rule.get("keywords", []):
        term = str(keyword).casefold()
        if term and term in normalized:
            return str(keyword)
    groups = rule.get("required_keyword_groups", [])
    if not isinstance(groups, list) or not groups:
        return None
    matched: list[str] = []
    for group in groups:
        if not isinstance(group, list) or not group:
            return None
        match = next((str(term) for term in group if str(term).casefold() in normalized), None)
        if match is None:
            return None
        matched.append(match)
    return "+".join(matched)


def _issue_payload(rule: dict[str, Any], matched_keyword: str, job_type: str) -> dict[str, str]:
    payload = {
        "code": str(rule["code"]),
        "message": str(rule["message"]),
        "matched_keyword": matched_keyword,
        "job_type": job_type,
    }
    if rule.get("supported_boundary") is not None:
        payload["supported_boundary"] = str(rule["supported_boundary"])
    return payload
