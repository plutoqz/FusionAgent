from __future__ import annotations

from typing import Iterable

from kg.policy_registry import KnowledgePolicyRegistry, default_policy_registry
from kg.repository import KGRepository
from schemas.research_case_manifest import ResearchCaseManifest


def validate_manifest_crosswalk(
    manifest: ResearchCaseManifest,
    repository: KGRepository,
    policy_registry: KnowledgePolicyRegistry | None = None,
) -> list[str]:
    """Return closed-reference failures without mutating the frozen KG."""
    registry = policy_registry or default_policy_registry()
    source_ids = {item.source_id for item in repository.list_data_sources()}
    algorithm_ids = {item.algo_id for item in repository.list_algorithms()}
    pattern_ids = {item.pattern_id for item in repository.list_workflow_patterns()}
    bundle_ids = {item.bundle_id for item in repository.list_task_bundles()}
    contract_ids = {item.contract_id for item in repository.get_product_contracts(None)}
    profile_ids = {
        profile.profile_id
        for case in manifest.cases
        for profile in repository.get_scenario_profiles(case.scenario.disaster_type)
    }
    policy_ids = _policy_ids(registry)
    failures: list[str] = []
    for case in manifest.cases:
        crosswalk = case.kg_crosswalk.model_dump(mode="json")
        _check_ids(failures, case.case_id, "source_catalog_ids", crosswalk.get("source_catalog_ids", []), source_ids)
        _check_ids(failures, case.case_id, "algorithm_ids", crosswalk.get("algorithm_ids", []), algorithm_ids)
        _check_ids(failures, case.case_id, "workflow_pattern_ids", crosswalk.get("workflow_pattern_ids", []), pattern_ids)
        _check_ids(failures, case.case_id, "quality_policy_ids", crosswalk.get("quality_policy_ids", []), policy_ids)
        _check_ids(failures, case.case_id, "recovery_policy_ids", crosswalk.get("recovery_policy_ids", []), policy_ids)
        _check_ids(failures, case.case_id, "contract_ids", case.request_scope.contract_ids, contract_ids)
        _check_ids(failures, case.case_id, "profile_id", [case.scenario.profile_id] if case.scenario.profile_id else [], profile_ids)
        _check_ids(failures, case.case_id, "task_bundle_id", [case.scenario.task_bundle_id] if case.scenario.task_bundle_id else [], bundle_ids)
        _check_ids(failures, case.case_id, "policy_id", [crosswalk["policy_id"]] if crosswalk.get("policy_id") else [], policy_ids)
    return failures


def _policy_ids(registry: KnowledgePolicyRegistry) -> set[str]:
    payload = registry.payload
    result: set[str] = set()
    for section in ("quality_policies", "decision_policies", "quality_adaptation_policy", "recovery_policy", "intent_boundary_policy"):
        value = payload.get(section)
        if isinstance(value, list):
            result.update(str(item["policy_id"]) for item in value if isinstance(item, dict) and item.get("policy_id"))
        elif isinstance(value, dict) and value.get("policy_id"):
            result.add(str(value["policy_id"]))
    return result


def _check_ids(failures: list[str], case_id: str, field: str, values: Iterable[object], known: set[str]) -> None:
    unknown = sorted({str(value) for value in values if str(value).strip()} - known)
    failures.extend(f"{case_id}.{field} references unknown KG id: {value}" for value in unknown)
