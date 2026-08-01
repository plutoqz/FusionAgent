from __future__ import annotations

import dataclasses
import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Any

from kg.knowledge_release import DEFAULT_ENTITIES_PATH
from kg.models import (
    AlgorithmNode,
    AlgorithmParameterSpec,
    DataNeedNode,
    DataSourceNode,
    DataTypeNode,
    OutputRequirementNode,
    OutputSchemaPolicy,
    PatternStep,
    ProductContractNode,
    QoSPolicyNode,
    RepairStrategyNode,
    ScenarioProfileNode,
    TaskBundleNode,
    TaskNode,
    WorkflowPatternNode,
)
from schemas.fusion import JobType


SCHEMA_VERSION = "2.0.0"
SOURCE_MODULES = ["kg/ontology/v1.0.0/entities.json"]


def build_seed_manifest_payload(manifest_path: Path | None = None) -> dict[str, Any]:
    """Return the canonical static graph payload.

    The historical name is retained for callers, but this function no longer
    synthesizes knowledge from ``kg.seed``.  The versioned JSON release is the
    authority and Python modules are compatibility views over it.
    """
    path = Path(manifest_path) if manifest_path is not None else DEFAULT_ENTITIES_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"KG entity manifest must contain an object: {path}")
    _validate_hash(payload)
    return json.loads(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def load_seed_manifest_payload(payload: dict[str, Any]) -> dict[str, Any]:
    _validate_hash(payload)
    return {
        "data_types": {item["type_id"]: DataTypeNode(**item) for item in payload.get("data_types", [])},
        "tasks": {item["task_id"]: TaskNode(**item) for item in payload.get("tasks", [])},
        "scenario_profiles": [
            ScenarioProfileNode(**item) for item in payload.get("scenario_profiles", [])
        ],
        "product_contracts": {
            item["contract_id"]: ProductContractNode(**item) for item in payload.get("product_contracts", [])
        },
        "task_bundles": {
            item["bundle_id"]: TaskBundleNode(**item) for item in payload.get("task_bundles", [])
        },
        "output_requirements": {
            item["requirement_id"]: OutputRequirementNode(**_coerce_job_type(item))
            for item in payload.get("output_requirements", [])
        },
        "qos_policies": {
            item["policy_id"]: QoSPolicyNode(**item) for item in payload.get("qos_policies", [])
        },
        "data_needs": [DataNeedNode(**item) for item in payload.get("data_needs", [])],
        "repair_strategies": {
            item["strategy_id"]: RepairStrategyNode(**item) for item in payload.get("repair_strategies", [])
        },
        "transform_edges": {
            str(source): [str(target) for target in targets]
            for source, targets in payload.get("transform_edges", {}).items()
        },
        "algorithms": {item["algo_id"]: AlgorithmNode(**item) for item in payload.get("algorithms", [])},
        "parameter_specs": _load_parameter_specs(payload.get("parameter_specs", [])),
        "workflow_patterns": [
            _load_workflow_pattern(item) for item in payload.get("workflow_patterns", [])
        ],
        "data_sources": [DataSourceNode(**item) for item in payload.get("data_sources", [])],
        "output_schema_policies": {
            item["output_type"]: OutputSchemaPolicy(**_coerce_job_type(item))
            for item in payload.get("output_schema_policies", [])
        },
    }


def _sorted_dict_values(values: dict[str, Any], sort_key: str) -> list[dict[str, Any]]:
    return sorted((_to_plain(value) for value in values.values()), key=lambda item: str(item.get(sort_key, "")))


def _sorted_list(values: list[Any], sort_key: str) -> list[dict[str, Any]]:
    return sorted((_to_plain(value) for value in values), key=lambda item: str(item.get(sort_key, "")))


def _flatten_parameter_specs(values: dict[str, list[Any]]) -> list[dict[str, Any]]:
    flattened = [_to_plain(spec) for specs in values.values() for spec in specs]
    return sorted(
        flattened,
        key=lambda item: (
            str(item.get("algo_id", "")),
            int(item.get("order", 0) or 0),
            str(item.get("key", "")),
        ),
    )


def _load_parameter_specs(values: list[dict[str, Any]]) -> dict[str, list[AlgorithmParameterSpec]]:
    specs: dict[str, list[AlgorithmParameterSpec]] = {}
    for item in values:
        spec = AlgorithmParameterSpec(**item)
        specs.setdefault(spec.algo_id, []).append(spec)
    for algo_id in specs:
        specs[algo_id].sort(key=lambda spec: (int(spec.order), spec.key))
    return specs


def _load_workflow_pattern(item: dict[str, Any]) -> WorkflowPatternNode:
    payload = dict(item)
    payload["job_type"] = _coerce_job_type_value(payload.get("job_type"))
    payload["steps"] = [PatternStep(**step) for step in payload.get("steps", [])]
    return WorkflowPatternNode(**payload)


def _coerce_job_type(item: dict[str, Any]) -> dict[str, Any]:
    payload = dict(item)
    if "job_type" in payload:
        payload["job_type"] = _coerce_job_type_value(payload.get("job_type"))
    return payload


def _coerce_job_type_value(value: Any) -> JobType:
    if isinstance(value, JobType):
        return value
    return JobType(str(value))


def _to_plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {key: _to_plain(item) for key, item in dataclasses.asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _to_plain(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    if isinstance(value, tuple):
        return [_to_plain(item) for item in value]
    if isinstance(value, set):
        return sorted(_to_plain(item) for item in value)
    return value


def _content_hash(payload: dict[str, Any]) -> str:
    normalized = _payload_for_hash(payload)
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _payload_for_hash(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    metadata = dict(normalized.get("metadata") or {})
    metadata["content_hash"] = ""
    metadata["generated_at"] = ""
    normalized["metadata"] = metadata
    return normalized


def _validate_hash(payload: dict[str, Any]) -> None:
    metadata = payload.get("metadata") if isinstance(payload, dict) else None
    expected = ""
    if isinstance(metadata, dict):
        expected = str(metadata.get("content_hash") or "")
    actual = "sha256:" + _content_hash(payload)
    if expected != actual:
        raise ValueError(f"KG seed manifest content_hash mismatch: expected {expected!r}, got {actual!r}")


def seal_manifest_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sealed = json.loads(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    metadata = dict(sealed.get("metadata") or {})
    metadata["content_hash"] = ""
    sealed["metadata"] = metadata
    metadata["content_hash"] = "sha256:" + _content_hash(sealed)
    return sealed
