from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict

from benchmark_platform.canonical import canonical_sha256
from benchmark_platform.context import CanonicalContext
from benchmark_platform.design_loader import FrozenDesignBundle
from benchmark_platform.models import BenchmarkPlatformValidationError, FailureClass, FailureRecord
from schemas.benchmark_method_selection import ProjectionSpec


ConditionId = Literal[
    "fixed_workflow",
    "rules_only",
    "kg_only",
    "llm_only",
    "llm_capability_kg",
    "llm_full_contract_kg",
]

COMMON_FIELDS = ("request", "observable_facts")
FORBIDDEN_FIELDS = (
    "gold",
    "oracle",
    "vetoes",
    "expected_decision",
    "expected_consequence",
    "automatic_score",
    "condition_id",
    "condition_label",
    "run_id",
)
VISIBLE_FIELDS: dict[str, tuple[str, ...]] = {
    "fixed_workflow": (*COMMON_FIELDS, "workflow_interface"),
    "rules_only": (*COMMON_FIELDS, "rules"),
    "kg_only": (*COMMON_FIELDS, "kg_query_result"),
    "llm_only": (*COMMON_FIELDS, "output_schema"),
    "llm_capability_kg": (*COMMON_FIELDS, "output_schema", "capability_projection"),
    "llm_full_contract_kg": (*COMMON_FIELDS, "output_schema", "full_contract_projection"),
}


class ProjectionError(BenchmarkPlatformValidationError):
    """Raised when a method condition cannot receive an isolated projection."""


class ProjectionTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    condition_id: ConditionId
    context_semantic_hash: str
    kg_release_id: str | None
    selected_reference_ids: tuple[str, ...]
    leakage_hits: tuple[str, ...]


class ConditionProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    spec: ProjectionSpec
    payload: dict[str, Any]
    trace: ProjectionTrace


def _fail(code: str, message: str) -> None:
    raise ProjectionError([
        FailureRecord(
            failure_class=FailureClass.RUNTIME_INVALID_STATE,
            message=message,
            validator="method_projection",
            details={"code": code},
        )
    ])


def _walk_forbidden(value: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            item_path = f"{path}.{key}"
            if str(key) in FORBIDDEN_FIELDS:
                hits.append(item_path)
            hits.extend(_walk_forbidden(item, item_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            hits.extend(_walk_forbidden(item, f"{path}[{index}]"))
    return hits


def _items_by_id(items: Any, field: str, identifiers: tuple[str, ...]) -> list[dict[str, Any]]:
    wanted = set(identifiers)
    selected = [deepcopy(item) for item in items if isinstance(item, dict) and item.get(field) in wanted]
    if {item[field] for item in selected} != wanted:
        _fail("kg_reference_missing", f"frozen KG does not contain every requested {field}")
    return sorted(selected, key=lambda item: str(item[field]))


def _capability_projection(context: CanonicalContext, bundle: FrozenDesignBundle) -> dict[str, Any]:
    entities = bundle.kg_entities
    return {
        "task_ids": list(context.task_ids),
        "sources": _items_by_id(entities.get("data_sources", []), "source_id", context.source_ids),
        "algorithms": _items_by_id(entities.get("algorithms", []), "algo_id", context.algorithm_ids),
    }


def _full_contract_projection(context: CanonicalContext, bundle: FrozenDesignBundle) -> dict[str, Any]:
    entities = bundle.kg_entities
    policies = bundle.kg_policies
    capability = _capability_projection(context, bundle)
    quality_ids = tuple(item for item in context.policy_ids if item.startswith("quality."))
    return {
        **capability,
        "scenario": _items_by_id(entities.get("scenario_profiles", []), "profile_id", (context.scenario_id,)),
        "contracts": _items_by_id(entities.get("product_contracts", []), "contract_id", context.contract_ids),
        "quality_policies": _items_by_id(policies.get("quality_policies", []), "policy_id", quality_ids),
        "kg_release_id": context.kg_release_id,
        "kg_semantic_hash": context.kg_semantic_hash,
    }


def project_condition(
    condition_id: ConditionId,
    context: CanonicalContext,
    *,
    request: Mapping[str, Any],
    output_schema: Mapping[str, Any] | None = None,
    workflow_interface: Mapping[str, Any] | None = None,
    rules: Mapping[str, Any] | None = None,
    bundle: FrozenDesignBundle | None = None,
) -> ConditionProjection:
    if condition_id not in VISIBLE_FIELDS:
        _fail("unknown_condition", f"unknown method condition: {condition_id}")
    payload: dict[str, Any] = {
        "request": deepcopy(dict(request)),
        "observable_facts": deepcopy(context.payload["observation"]),
    }
    selected_ids: tuple[str, ...] = ()
    if condition_id == "fixed_workflow":
        if workflow_interface is None:
            _fail("missing_projection_input", "fixed_workflow requires workflow_interface")
        payload["workflow_interface"] = deepcopy(dict(workflow_interface))
    elif condition_id == "rules_only":
        if rules is None:
            _fail("missing_projection_input", "rules_only requires explicit rules")
        payload["rules"] = deepcopy(dict(rules))
    elif condition_id == "kg_only":
        if bundle is None:
            _fail("missing_kg_bundle", "kg_only requires the frozen KG bundle")
        payload["kg_query_result"] = _full_contract_projection(context, bundle)
        selected_ids = tuple(sorted(item.reference_id for item in context.crosswalk.bindings))
    else:
        if output_schema is None:
            _fail("missing_projection_input", f"{condition_id} requires output_schema")
        payload["output_schema"] = deepcopy(dict(output_schema))
        if condition_id in {"llm_capability_kg", "llm_full_contract_kg"}:
            if bundle is None:
                _fail("missing_kg_bundle", f"{condition_id} requires the frozen KG bundle")
            key = "capability_projection" if condition_id == "llm_capability_kg" else "full_contract_projection"
            payload[key] = (
                _capability_projection(context, bundle)
                if condition_id == "llm_capability_kg"
                else _full_contract_projection(context, bundle)
            )
            selected_ids = tuple(sorted(item.reference_id for item in context.crosswalk.bindings))
    if tuple(payload) != VISIBLE_FIELDS[condition_id]:
        _fail("visible_field_mismatch", f"projection fields do not match the registry for {condition_id}")
    leakage_hits = tuple(sorted(_walk_forbidden(payload)))
    if leakage_hits:
        _fail("recursive_leakage", f"projection contains forbidden fields: {', '.join(leakage_hits)}")
    projection_hash = canonical_sha256(payload)
    return ConditionProjection(
        spec=ProjectionSpec(
            condition_id=condition_id,
            visible_fields=VISIBLE_FIELDS[condition_id],
            forbidden_fields=FORBIDDEN_FIELDS,
            projection_hash=projection_hash,
        ),
        payload=payload,
        trace=ProjectionTrace(
            condition_id=condition_id,
            context_semantic_hash=context.semantic_hash,
            kg_release_id=context.kg_release_id if bundle is not None else None,
            selected_reference_ids=selected_ids,
            leakage_hits=(),
        ),
    )
