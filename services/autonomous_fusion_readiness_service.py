from __future__ import annotations

from typing import Any, Iterable

from kg.knowledge_release import KnowledgeReleaseError
from kg.policy_registry import KnowledgePolicyRegistry, default_policy_registry

def classify_autonomous_readiness(
    job_type: str,
    component_coverage: dict[str, Any] | None,
    source_attempts: list[dict[str, Any]] | dict[str, Any] | None,
    *,
    policy_identifier: str | None = None,
    policy_registry: KnowledgePolicyRegistry | None = None,
) -> dict[str, Any]:
    registry = policy_registry or default_policy_registry()
    normalized_job_type = str(job_type or "").strip().lower()
    normalized_policy_identifier = str(
        policy_identifier or normalized_job_type
    ).strip().lower()
    try:
        required, policy_ref = _required_source_ids(
            normalized_policy_identifier,
            registry=registry,
        )
    except KnowledgeReleaseError:
        return {
            "status": "system_failure",
            "job_type": normalized_job_type,
            "required_source_ids": [],
            "missing_required_source_ids": [f"<unknown_job_type:{normalized_job_type}>"],
            "external_uncontrollable_source_ids": [],
        }
    aliases = registry.source_id_aliases()
    coverage = _canonical_coverage(component_coverage or {}, aliases=aliases)
    attempts = list(_iter_source_attempts(source_attempts, aliases=aliases))
    missing = [source_id for source_id in required if not _coverage_is_available(coverage.get(source_id))]
    external_missing = [
        source_id
        for source_id in missing
        if _has_external_attempt(source_id, attempts, aliases=aliases)
    ]

    if not missing:
        status = "full_autonomous_closure"
    elif len(external_missing) == len(missing):
        status = "degraded_external"
    else:
        status = "system_failure"

    return {
        "status": status,
        "job_type": normalized_job_type,
        "required_source_ids": required,
        "missing_required_source_ids": missing,
        "external_uncontrollable_source_ids": external_missing,
        "knowledge_identity": registry.knowledge_identity(),
        "policy_ref": policy_ref,
    }


def _required_source_ids(
    identifier: str,
    *,
    registry: KnowledgePolicyRegistry,
) -> tuple[list[str], str]:
    exact_bundle = registry.source_bundle_policy(identifier)
    if exact_bundle is not None:
        return _nonempty_source_ids(exact_bundle, "required_full_closure"), f"source_bundle:{identifier}"

    try:
        component_policy = registry.quality_component_policy(identifier)
    except KnowledgeReleaseError:
        component_policy = None
    if component_policy is not None:
        policy_id = str(component_policy.get("policy_id") or identifier)
        return _nonempty_source_ids(component_policy, "expected_source_ids"), f"quality_component:{policy_id}"

    suffix = f".{identifier}"
    matches = [
        item
        for item in registry.source_bundle_policies()
        if str(item.get("source_id") or "").endswith(suffix)
    ]
    closures = {
        tuple(_nonempty_source_ids(item, "required_full_closure"))
        for item in matches
    }
    if matches and len(closures) == 1:
        source_ids = list(next(iter(closures)))
        refs = ",".join(sorted(str(item["source_id"]) for item in matches))
        return source_ids, f"source_bundle_suffix:{refs}"
    raise KnowledgeReleaseError(f"No unambiguous autonomous readiness policy for {identifier!r}")


def _nonempty_source_ids(policy: dict[str, Any], field: str) -> list[str]:
    source_ids = [str(item).strip() for item in policy.get(field, []) if str(item).strip()]
    if not source_ids:
        raise KnowledgeReleaseError(f"Policy {policy.get('policy_id') or policy.get('source_id')} has no {field}")
    return source_ids


def _canonical_coverage(component_coverage: dict[str, Any], *, aliases: dict[str, str]) -> dict[str, Any]:
    coverage: dict[str, Any] = {}
    for raw_source_id, payload in component_coverage.items():
        source_id = _canonical_source_id(raw_source_id, aliases=aliases)
        if source_id not in coverage or _coverage_is_available(payload):
            coverage[source_id] = payload
    return coverage


def _iter_source_attempts(
    source_attempts: list[dict[str, Any]] | dict[str, Any] | None,
    *,
    aliases: dict[str, str],
) -> Iterable[dict[str, Any]]:
    if source_attempts is None:
        return []
    if isinstance(source_attempts, dict):
        raw_attempts = source_attempts.get("attempts") or source_attempts.get("source_attempts") or []
    else:
        raw_attempts = source_attempts
    attempts: list[dict[str, Any]] = []
    for item in raw_attempts:
        if not isinstance(item, dict):
            continue
        attempt = dict(item)
        attempt["source_id"] = _canonical_source_id(attempt.get("source_id"), aliases=aliases)
        attempts.append(attempt)
    return attempts


def _coverage_is_available(payload: Any) -> bool:
    if payload is None:
        return False
    feature_count = _optional_int(_coverage_value(payload, "feature_count"))
    if feature_count is not None:
        return feature_count > 0
    return str(_coverage_value(payload, "coverage_status") or "").strip().lower() == "available"


def _has_external_attempt(
    source_id: str,
    source_attempts: list[dict[str, Any]],
    *,
    aliases: dict[str, str],
) -> bool:
    canonical_source_id = _canonical_source_id(source_id, aliases=aliases)
    for attempt in source_attempts:
        if _canonical_source_id(attempt.get("source_id"), aliases=aliases) != canonical_source_id:
            continue
        if attempt.get("external_uncontrollable") is True:
            return True
    return False


def _coverage_value(payload: Any, key: str) -> Any:
    if isinstance(payload, dict):
        return payload.get(key)
    return getattr(payload, key, None)


def _canonical_source_id(source_id: Any, *, aliases: dict[str, str]) -> str:
    normalized = str(source_id or "").strip().lower()
    return aliases.get(normalized, normalized)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
