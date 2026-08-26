from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from benchmark_platform.design_loader import FrozenDesignBundle
from benchmark_platform.models import (
    BenchmarkPlatformValidationError,
    FailureClass,
    FailureRecord,
    validate_template_document,
)


REFERENCE_TYPES = (
    "scenario",
    "task_bundle",
    "contract",
    "source",
    "algorithm",
    "workflow_pattern",
    "quality_policy",
    "normalization_contract",
    "intent_policy",
)


class CrosswalkError(BenchmarkPlatformValidationError):
    """Raised when a template reference cannot be resolved uniquely."""


class CrosswalkBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reference_id: str = Field(min_length=1)
    reference_type: str = Field(min_length=1)
    registry: str = Field(min_length=1)
    used_by_task_ids: tuple[str, ...]


class CrosswalkReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kg_release_id: str
    template_family_id: str
    bindings: tuple[CrosswalkBinding, ...]
    reference_count: int = Field(ge=1)


def _failure(code: str, message: str, path: tuple[str | int, ...] = ()) -> CrosswalkError:
    return CrosswalkError(
        [
            FailureRecord(
                failure_class=FailureClass.RUNTIME_INVALID_STATE,
                message=message,
                path=path,
                validator="crosswalk",
                details={"code": code},
            )
        ]
    )


def _items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _nested_references(value: Any) -> list[tuple[str, str]]:
    """Extract explicit ID-bearing fields without interpreting free-form text."""
    fields = {
        "scenario_profile_id": "scenario",
        "scenario_id": "scenario",
        "task_bundle_id": "task_bundle",
        "bundle_id": "task_bundle",
        "contract_id": "contract",
        "product_contract_id": "contract",
        "source_id": "source",
        "algorithm_id": "algorithm",
        "algo_id": "algorithm",
        "pattern_id": "workflow_pattern",
        "preferred_pattern_id": "workflow_pattern",
        "quality_policy_id": "quality_policy",
        "normalization_contract_id": "normalization_contract",
        "intent_policy_id": "intent_policy",
    }
    found: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            kind = fields.get(key)
            if kind and isinstance(item, str):
                found.append((kind, item))
            elif key.endswith("_ids") and isinstance(item, list):
                singular = key[:-4] + "_id"
                kind = fields.get(singular)
                if kind:
                    found.extend((kind, item) for item in item if isinstance(item, str))
            found.extend(_nested_references(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_nested_references(item))
    return found


def build_crosswalk_registry(entities: Mapping[str, Any], policies: Mapping[str, Any]) -> dict[str, dict[str, list[str]]]:
    registry: dict[str, dict[str, list[str]]] = {kind: {} for kind in REFERENCE_TYPES}

    def add(kind: str, identifier: Any, source: str) -> None:
        if isinstance(identifier, str) and identifier:
            registry[kind].setdefault(identifier, []).append(source)

    for item in _items(entities.get("scenario_profiles")):
        add("scenario", item.get("profile_id"), "entities.scenario_profiles")
    for item in _items(entities.get("task_bundles")):
        add("task_bundle", item.get("bundle_id"), "entities.task_bundles")
    for item in _items(entities.get("product_contracts")):
        add("contract", item.get("contract_id"), "entities.product_contracts")
    for item in _items(policies.get("output_contracts")):
        add("contract", item.get("contract_id"), "policies.output_contracts")
    for item in _items(entities.get("data_sources")):
        add("source", item.get("source_id"), "entities.data_sources")
    for item in _items(entities.get("algorithms")):
        add("algorithm", item.get("algo_id"), "entities.algorithms")
        if "normalize" in str(item.get("algo_id", "")):
            add("normalization_contract", item.get("algo_id"), "entities.algorithms")
    for item in _items(entities.get("workflow_patterns")):
        add("workflow_pattern", item.get("pattern_id"), "entities.workflow_patterns")
    for item in _items(policies.get("quality_policies")):
        add("quality_policy", item.get("policy_id"), "policies.quality_policies")
    intent = policies.get("intent_boundary_policy")
    if isinstance(intent, dict):
        add("intent_policy", intent.get("policy_id"), "policies.intent_boundary_policy")
    for key, value in policies.items():
        if "normalization" in key and isinstance(value, list):
            for item in _items(value):
                add("normalization_contract", item.get("contract_id") or item.get("policy_id"), f"policies.{key}")
    return registry


def validate_crosswalk(bundle: FrozenDesignBundle, template: Mapping[str, Any]) -> CrosswalkReport:
    crosswalk = template.get("crosswalk")
    if isinstance(crosswalk, dict) and crosswalk.get("kg_release_id") != bundle.kg_release_id:
        raise _failure("wrong_kg_release", "template references a different KG release", ("crosswalk", "kg_release_id"))
    try:
        validate_template_document(template, bundle.schema_document)
    except BenchmarkPlatformValidationError as error:
        raise _failure("missing_reference", "template does not satisfy the frozen schema") from error
    crosswalk = template.get("crosswalk")
    if not isinstance(crosswalk, dict):
        raise _failure("missing_reference", "template crosswalk is missing")
    if crosswalk.get("kg_release_id") != bundle.kg_release_id:
        raise _failure("wrong_kg_release", "template references a different KG release", ("crosswalk", "kg_release_id"))
    if crosswalk.get("missing_reference_policy") != "fail_closed":
        raise _failure("missing_reference", "crosswalk must use fail_closed policy")
    tasks = template.get("task_state", {}).get("tasks", [])
    task_ids = {item.get("task_id") for item in tasks if isinstance(item, dict)}
    registry = build_crosswalk_registry(bundle.kg_entities, bundle.kg_policies)
    bindings: list[CrosswalkBinding] = []
    seen: set[tuple[str, str]] = set()
    references = crosswalk.get("references")
    if not isinstance(references, list) or not references:
        raise _failure("missing_reference", "crosswalk references must be non-empty")
    resolved_keys: set[tuple[str, str]] = set()
    for index, reference in enumerate(references):
        if not isinstance(reference, dict):
            raise _failure("missing_reference", "crosswalk reference must be an object", ("crosswalk", "references", index))
        reference_id = reference.get("reference_id")
        reference_type = reference.get("reference_type")
        used_by = reference.get("used_by_task_ids")
        if reference_type not in REFERENCE_TYPES or not isinstance(reference_id, str) or not isinstance(used_by, list):
            raise _failure("unknown_id", "crosswalk reference has an unknown type or malformed ID", ("crosswalk", "references", index))
        key = (reference_type, reference_id)
        if key in seen:
            raise _failure("duplicate_binding", f"duplicate crosswalk binding: {reference_type}:{reference_id}")
        seen.add(key)
        candidates = registry[reference_type].get(reference_id, [])
        if not candidates:
            raise _failure("unknown_id", f"unknown crosswalk ID: {reference_type}:{reference_id}")
        if len(candidates) != 1:
            raise _failure("ambiguous_binding", f"ambiguous crosswalk ID: {reference_type}:{reference_id}")
        if any(task_id not in task_ids for task_id in used_by):
            raise _failure("missing_reference", f"crosswalk binding uses an unknown task ID: {reference_id}")
        resolved_keys.add(key)
        bindings.append(CrosswalkBinding(reference_id=reference_id, reference_type=reference_type, registry=candidates[0], used_by_task_ids=tuple(used_by)))
    for kind, reference_id in _nested_references(template):
        candidates = registry[kind].get(reference_id, [])
        if not candidates:
            raise _failure("unknown_id", f"unknown nested crosswalk ID: {kind}:{reference_id}")
        if len(candidates) != 1:
            raise _failure("ambiguous_binding", f"ambiguous nested crosswalk ID: {kind}:{reference_id}")
        if (kind, reference_id) not in resolved_keys:
            raise _failure("missing_reference", f"nested ID is absent from crosswalk references: {kind}:{reference_id}")
    return CrosswalkReport(
        kg_release_id=bundle.kg_release_id,
        template_family_id=str(template.get("template_family_id")),
        bindings=tuple(bindings),
        reference_count=len(bindings),
    )
