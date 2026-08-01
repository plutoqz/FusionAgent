from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from kg.knowledge_release import DEFAULT_POLICIES_PATH, KnowledgeReleaseError, get_knowledge_identity, load_policies
from kg.seed_provider import load_seed_data


class KnowledgePolicyRegistry:
    """Typed lookup facade over a declarative KG release."""

    def __init__(self, policies_path: Path | None = None) -> None:
        self.policies_path = Path(policies_path).resolve() if policies_path is not None else DEFAULT_POLICIES_PATH.resolve()
        self.payload = load_policies(
            self.policies_path,
            verify_release_files=self.policies_path == DEFAULT_POLICIES_PATH.resolve(),
        )
        self._task_bundles: dict[str, dict[str, Any]] | None = None

    def knowledge_identity(self) -> dict[str, str]:
        if self.policies_path == DEFAULT_POLICIES_PATH.resolve():
            return get_knowledge_identity()
        metadata = self.payload.get("metadata") or {}
        return {
            "release_id": str(metadata.get("release_id") or "custom-unfrozen-policy"),
            "knowledge_version": str(metadata.get("knowledge_version") or "custom"),
            "ontology_version": "custom",
            "semantic_hash": "unverified-custom-policy",
            "experience_snapshot_hash": "unverified-custom-policy",
        }

    def disaster_records(self) -> list[dict[str, Any]]:
        return self._records("disaster_vocabulary")

    def resolve_disaster_type(self, value: object) -> str | None:
        token = str(value or "").strip().casefold()
        if not token:
            return None
        for record in self.disaster_records():
            aliases = {str(item).strip().casefold() for item in record.get("aliases", [])}
            aliases.add(str(record.get("disaster_type") or "").casefold())
            if token in aliases:
                return str(record["disaster_type"])
        return None

    def disaster_type_in_text(self, text: object) -> str | None:
        normalized = str(text or "").casefold()
        if not normalized:
            return None
        matches: list[tuple[int, str]] = []
        for record in self.disaster_records():
            disaster_type = str(record["disaster_type"])
            for alias in record.get("aliases", []):
                term = str(alias).strip().casefold()
                if term and _contains_term(normalized, term):
                    matches.append((len(term), disaster_type))
        return sorted(matches, key=lambda item: (-item[0], item[1]))[0][1] if matches else None

    def disaster_record(self, disaster_type: str) -> dict[str, Any]:
        return self._require("disaster_vocabulary", "disaster_type", disaster_type)

    def place_records(self) -> list[dict[str, Any]]:
        return self._records("place_vocabulary")

    def aoi_resolution_policy(self) -> dict[str, Any]:
        return self._required_object("aoi_resolution_policy")

    def aoi_disaster_terms(self) -> list[str]:
        policy = self.aoi_resolution_policy()
        additional = policy.get("additional_disaster_terms")
        if not isinstance(additional, list):
            raise KnowledgeReleaseError(
                "aoi_resolution_policy.additional_disaster_terms must be a list"
            )
        terms = [
            *(str(alias) for record in self.disaster_records() for alias in record.get("aliases", [])),
            *(str(item) for item in self.intent_boundary_policy().get("unsupported_disaster_terms", [])),
            *(str(item) for item in additional),
        ]
        return sorted({term.strip().casefold() for term in terms if term.strip()}, key=lambda item: (-len(item), item))

    def rescue_organization_terms(self) -> list[str]:
        terms = self.payload.get("rescue_organization_terms")
        if not isinstance(terms, list):
            raise KnowledgeReleaseError("rescue_organization_terms is missing from KG policy release")
        return [str(item) for item in terms]

    def mission_policy(self) -> dict[str, Any]:
        return self._required_object("mission_policy")

    def intent_boundary_policy(self) -> dict[str, Any]:
        return self._required_object("intent_boundary_policy")

    def unsupported_intent_rules(self) -> list[dict[str, Any]]:
        rules = self.intent_boundary_policy().get("rules")
        if not isinstance(rules, list) or not rules:
            raise KnowledgeReleaseError("intent_boundary_policy.rules must be a non-empty list")
        return [dict(rule) for rule in rules if isinstance(rule, dict)]

    def unsupported_disaster_term_in_text(self, text: object) -> str | None:
        terms = self.intent_boundary_policy().get("unsupported_disaster_terms")
        if not isinstance(terms, list):
            raise KnowledgeReleaseError(
                "intent_boundary_policy.unsupported_disaster_terms must be a list"
            )
        normalized = str(text or "").casefold()
        matches = [
            str(term).strip()
            for term in terms
            if str(term).strip() and _contains_term(normalized, str(term).strip().casefold())
        ]
        return sorted(matches, key=lambda item: (-len(item), item))[0] if matches else None

    def task_records(self) -> list[dict[str, Any]]:
        return sorted(self._records("task_semantics"), key=lambda item: (int(item["execution_order"]), item["task_kind"]))

    def task_record(self, task_kind: str) -> dict[str, Any]:
        return self._require("task_semantics", "task_kind", task_kind)

    def task_record_by_id(self, task_id: str) -> dict[str, Any]:
        return self._require("task_semantics", "task_id", task_id)

    def task_bundle_record(self, bundle_id: str) -> dict[str, Any]:
        if self._task_bundles is None:
            self._task_bundles = {
                key: asdict(bundle)
                for key, bundle in load_seed_data()["task_bundles"].items()
            }
        record = self._task_bundles.get(bundle_id)
        if record is None:
            raise KnowledgeReleaseError(f"No frozen TaskBundle entity with bundle_id={bundle_id!r}")
        return dict(record)

    def task_kinds_for_alias(self, value: object) -> list[str]:
        token = str(value or "").strip().casefold().replace(" ", "_").replace("-", "_")
        if not token:
            return []
        matches: list[str] = []
        for record in self.task_records():
            aliases = {str(alias).casefold().replace(" ", "_").replace("-", "_") for alias in record.get("aliases", [])}
            if token in aliases and str(record["task_kind"]) not in matches:
                matches.append(str(record["task_kind"]))
        return matches

    def task_kinds_for_job_type(self, job_type: str) -> list[str]:
        return [str(record["task_kind"]) for record in self.task_records() if record.get("job_type") == job_type]

    def task_kinds_in_text(self, text: object) -> list[str]:
        normalized = str(text or "").casefold().replace("-", "_")
        matches: list[str] = []
        for record in self.task_records():
            for alias in sorted(record.get("aliases", []), key=lambda item: -len(str(item))):
                term = str(alias).casefold().replace("-", "_")
                comparable = normalized.replace(" ", "_") if "_" in term else normalized
                if term and _contains_term(comparable, term):
                    task_kind = str(record["task_kind"])
                    if task_kind not in matches:
                        matches.append(task_kind)
                    break
        return matches

    def output_contract(self, task_kind: str) -> dict[str, Any]:
        return self._require("output_contracts", "task_kind", task_kind)

    def quality_policy(self, task_kind: str, policy_id: str | None = None) -> dict[str, Any]:
        if policy_id:
            record = self._require("quality_policies", "policy_id", policy_id)
            if record.get("task_kind") != task_kind:
                raise KnowledgeReleaseError(f"Quality policy {policy_id} is not for task kind {task_kind}")
            return record
        return self._require("quality_policies", "task_kind", task_kind)

    def quality_check_templates(self, topology: str) -> list[dict[str, Any]]:
        templates = self.payload.get("quality_check_templates")
        if not isinstance(templates, dict):
            raise KnowledgeReleaseError("quality_check_templates is missing from KG policy release")
        common = templates.get("common")
        specific = templates.get(topology)
        if not isinstance(common, list) or not isinstance(specific, list):
            raise KnowledgeReleaseError(f"Quality check template is missing for topology {topology}")
        return [dict(item) for item in [*common, *specific]]

    def quality_adaptation_policy(self) -> dict[str, Any]:
        return self._required_object("quality_adaptation_policy")

    def source_role_policies(self, task_kind: str) -> list[dict[str, Any]]:
        records = [item for item in self._records("source_role_policies") if item.get("task_kind") == task_kind]
        if not records:
            raise KnowledgeReleaseError(f"No source role policy for task kind {task_kind}")
        return records

    def source_role_policy(self, task_kind: str, role_id: str) -> dict[str, Any]:
        for record in self.source_role_policies(task_kind):
            if record.get("role_id") == role_id:
                return record
        raise KnowledgeReleaseError(f"No source role policy for task kind {task_kind} and role {role_id}")

    def source_bundle_policy(self, source_id: str, *, required: bool = False) -> dict[str, Any] | None:
        for record in self._records("source_bundle_policies"):
            if record.get("source_id") == source_id:
                return record
        if required:
            raise KnowledgeReleaseError(f"No source bundle policy for {source_id}")
        return None

    def source_bundle_policies(self) -> list[dict[str, Any]]:
        return self._records("source_bundle_policies")

    def tiled_building_catalog_source_ids(self) -> list[str]:
        source_ids = [
            str(record["source_id"])
            for record in self.source_bundle_policies()
            if record.get("tiled_building_runtime") is True
        ]
        if not source_ids:
            raise KnowledgeReleaseError(
                "No source bundle policy authorizes the tiled building runtime"
            )
        return source_ids

    def source_runtime_bindings(self) -> dict[str, Any]:
        return self._required_object("source_runtime_bindings")

    def source_runtime_aliases(self) -> dict[str, str]:
        aliases = self.source_runtime_bindings().get("aliases")
        if not isinstance(aliases, dict) or not aliases:
            raise KnowledgeReleaseError("source_runtime_bindings.aliases is missing from KG policy release")
        return {str(source_id): str(alias) for source_id, alias in aliases.items()}

    def source_id_aliases(self) -> dict[str, str]:
        aliases = self.source_runtime_bindings().get("source_id_aliases")
        if not isinstance(aliases, dict):
            raise KnowledgeReleaseError("source_runtime_bindings.source_id_aliases is missing from KG policy release")
        return {str(source_id): str(canonical_id) for source_id, canonical_id in aliases.items()}

    def vector_source_bindings(self) -> list[dict[str, Any]]:
        records = self.source_runtime_bindings().get("vector_sources")
        if not isinstance(records, list) or not records:
            raise KnowledgeReleaseError("source_runtime_bindings.vector_sources is missing from KG policy release")
        return [dict(record) for record in records if isinstance(record, dict)]

    def source_priority_order(self, binding_id: str) -> list[str]:
        orders = self.source_runtime_bindings().get("priority_orders")
        if not isinstance(orders, dict):
            raise KnowledgeReleaseError("source_runtime_bindings.priority_orders is missing from KG policy release")
        source_ids = orders.get(binding_id)
        if not isinstance(source_ids, list) or not source_ids:
            raise KnowledgeReleaseError(f"No source runtime priority order for {binding_id}")
        return [str(source_id) for source_id in source_ids]

    def raster_source_binding(self, source_id: str) -> dict[str, Any]:
        records = self.source_runtime_bindings().get("raster_sources")
        if not isinstance(records, list):
            raise KnowledgeReleaseError("source_runtime_bindings.raster_sources is missing from KG policy release")
        for record in records:
            if isinstance(record, dict) and record.get("source_id") == source_id:
                return dict(record)
        raise KnowledgeReleaseError(f"No raster source runtime binding for {source_id}")

    def source_profiling_set(self, profile_set_id: str) -> dict[str, Any]:
        records = self.source_runtime_bindings().get("profiling_sets")
        if not isinstance(records, list):
            raise KnowledgeReleaseError(
                "source_runtime_bindings.profiling_sets is missing from KG policy release"
            )
        for record in records:
            if isinstance(record, dict) and record.get("profile_set_id") == profile_set_id:
                sources = record.get("sources")
                if not isinstance(sources, list) or not sources:
                    raise KnowledgeReleaseError(
                        f"Source profiling set {profile_set_id} has no source bindings"
                    )
                return dict(record)
        raise KnowledgeReleaseError(f"No source profiling set {profile_set_id}")

    def quality_component_policy(self, task_kind: str) -> dict[str, Any]:
        return self._require("quality_component_policies", "task_kind", task_kind)

    def artifact_evaluation_policy(self) -> dict[str, Any]:
        return self._required_object("artifact_evaluation_policy")

    def fault_policy(self) -> dict[str, Any]:
        return self._required_object("fault_policy")

    def failure_classification_policy(self) -> dict[str, Any]:
        policy = self.fault_policy().get("classification")
        if not isinstance(policy, dict):
            raise KnowledgeReleaseError("fault_policy.classification is missing from KG policy release")
        return dict(policy)

    def source_candidate_fallback_faults(self) -> set[str]:
        values = self.fault_policy().get("source_candidate_fallback_faults")
        if not isinstance(values, list) or not values:
            raise KnowledgeReleaseError("fault_policy.source_candidate_fallback_faults must be a non-empty list")
        faults = {str(value).strip() for value in values if str(value).strip()}
        if not faults:
            raise KnowledgeReleaseError("fault_policy.source_candidate_fallback_faults has no valid fault class")
        return faults

    def source_mode_for_fault(self, fault_class: str) -> str:
        mapping = self.fault_policy().get("source_mode_by_fault")
        if not isinstance(mapping, dict):
            raise KnowledgeReleaseError("fault_policy.source_mode_by_fault must be an object")
        value = str(mapping.get(fault_class) or "").strip()
        if not value:
            raise KnowledgeReleaseError(
                f"fault_policy.source_mode_by_fault has no entry for {fault_class}"
            )
        return value

    def inferred_missing_fault(self, *, external: bool) -> str:
        mapping = self.fault_policy().get("inferred_missing_fault_by_control")
        if not isinstance(mapping, dict):
            raise KnowledgeReleaseError(
                "fault_policy.inferred_missing_fault_by_control must be an object"
            )
        key = "external" if external else "internal"
        value = str(mapping.get(key) or "").strip()
        if not value:
            raise KnowledgeReleaseError(
                f"fault_policy.inferred_missing_fault_by_control has no entry for {key}"
            )
        return value

    def empty_coverage_status(self, source_id: str) -> str:
        policy = self.fault_policy()
        default_status = str(policy.get("default_empty_coverage_status") or "").strip()
        overrides = policy.get("empty_coverage_status_by_source")
        if not default_status or not isinstance(overrides, dict):
            raise KnowledgeReleaseError(
                "fault_policy empty coverage status policy is incomplete"
            )
        value = str(overrides.get(source_id) or default_status).strip()
        if not value:
            raise KnowledgeReleaseError(
                f"fault_policy has no empty coverage status for {source_id}"
            )
        return value

    def inspection_operator_action(
        self,
        *,
        current_phase: str,
        fault_class: str | None,
        recoverability: str | None,
    ) -> str | None:
        guidance = self.fault_policy().get("inspection_guidance")
        if not isinstance(guidance, dict):
            raise KnowledgeReleaseError("fault_policy.inspection_guidance must be an object")
        failure_actions = guidance.get("failure_actions")
        recoverability_actions = guidance.get("recoverability_actions")
        phase_actions = guidance.get("phase_actions")
        if not all(
            isinstance(section, dict)
            for section in (failure_actions, recoverability_actions, phase_actions)
        ):
            raise KnowledgeReleaseError(
                "fault_policy.inspection_guidance action sections must be objects"
            )
        fault_key = str(fault_class or "").strip().upper()
        recoverability_key = str(recoverability or "").strip().lower()
        phase_key = str(current_phase or "").strip().lower()
        value = (
            failure_actions.get(fault_key)
            or recoverability_actions.get(recoverability_key)
            or phase_actions.get(phase_key)
        )
        return str(value).strip() if value else None

    def recovery_policy(self) -> dict[str, Any]:
        return self._required_object("recovery_policy")

    def decision_policy(self, policy_id: str) -> dict[str, Any]:
        return self._require("decision_policies", "policy_id", policy_id)

    def runtime_gates(self) -> dict[str, Any]:
        return self._required_object("runtime_gates")

    def backend_fallback_policy(self) -> str:
        value = str(self.runtime_gates().get("backend_fallback") or "").strip().lower()
        allowed = {"forbidden", "forbidden_in_strict_mode", "memory_in_development"}
        if value not in allowed:
            raise KnowledgeReleaseError(
                f"runtime_gates.backend_fallback must be one of {sorted(allowed)}; got {value!r}"
            )
        return value

    def runtime_gate_mode(self, gate_name: str) -> str:
        gates = self.runtime_gates()
        value = str(gates.get(gate_name) or "").strip().lower()
        if value not in {"enforce", "report", "warn"}:
            raise KnowledgeReleaseError(
                f"runtime_gates.{gate_name} must be enforce, report, or warn; got {value!r}"
            )
        return value

    def _records(self, section: str) -> list[dict[str, Any]]:
        records = self.payload.get(section)
        if not isinstance(records, list):
            raise KnowledgeReleaseError(f"{section} is missing from KG policy release")
        return [dict(item) for item in records if isinstance(item, dict)]

    def _require(self, section: str, key: str, value: object) -> dict[str, Any]:
        for record in self._records(section):
            if record.get(key) == value:
                return record
        raise KnowledgeReleaseError(f"No {section} record where {key}={value!r}")

    def _required_object(self, section: str) -> dict[str, Any]:
        payload = self.payload.get(section)
        if not isinstance(payload, dict):
            raise KnowledgeReleaseError(f"{section} is missing from KG policy release")
        return dict(payload)


_DEFAULT_REGISTRY: KnowledgePolicyRegistry | None = None


def default_policy_registry() -> KnowledgePolicyRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = KnowledgePolicyRegistry()
    return _DEFAULT_REGISTRY


def reset_default_policy_registry() -> None:
    global _DEFAULT_REGISTRY
    _DEFAULT_REGISTRY = None


def _contains_term(text: str, term: str) -> bool:
    if any(ord(character) > 127 for character in term):
        return term in text
    return re.search(rf"(?<![0-9a-z_]){re.escape(term)}(?![0-9a-z_])", text) is not None
