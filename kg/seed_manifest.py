from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from kg import seed
from kg.models import (
    AlgorithmNode,
    AlgorithmParameterSpec,
    DataNeedNode,
    DataSourceNode,
    DataTypeNode,
    OutputRequirementNode,
    OutputSchemaPolicy,
    PatternStep,
    QoSPolicyNode,
    RepairStrategyNode,
    ScenarioProfileNode,
    TaskBundleNode,
    TaskNode,
    WorkflowPatternNode,
)
from schemas.fusion import JobType


SCHEMA_VERSION = "1.0.0"
SOURCE_MODULES = ["kg.seed", "fusion_algorithms.registry_metadata"]


def build_seed_manifest_payload() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "metadata": {
            "schema_version": SCHEMA_VERSION,
            "generated_from": "kg.seed",
            "source_modules": SOURCE_MODULES,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "content_hash": "",
        },
        "data_types": _sorted_dict_values(seed.DATA_TYPES, "type_id"),
        "tasks": _sorted_dict_values(seed.TASKS, "task_id"),
        "scenario_profiles": _sorted_list(seed.SCENARIO_PROFILES, "profile_id"),
        "task_bundles": _sorted_dict_values(getattr(seed, "TASK_BUNDLES", {}), "bundle_id"),
        "output_requirements": _sorted_dict_values(getattr(seed, "OUTPUT_REQUIREMENTS", {}), "requirement_id"),
        "qos_policies": _sorted_dict_values(getattr(seed, "QOS_POLICIES", {}), "policy_id"),
        "data_needs": _sorted_list(getattr(seed, "DATA_NEEDS", []), "need_id"),
        "repair_strategies": _sorted_dict_values(getattr(seed, "REPAIR_STRATEGIES", {}), "strategy_id"),
        "algorithms": _sorted_dict_values(seed.ALGORITHMS, "algo_id"),
        "parameter_specs": _flatten_parameter_specs(seed.PARAMETER_SPECS),
        "workflow_patterns": _sorted_list(seed.WORKFLOW_PATTERNS, "pattern_id"),
        "data_sources": _sorted_list(seed.DATA_SOURCES, "source_id"),
        "output_schema_policies": _sorted_dict_values(seed.OUTPUT_SCHEMA_POLICIES, "policy_id"),
    }
    payload["metadata"]["content_hash"] = "sha256:" + _content_hash(payload)
    return payload


def load_seed_manifest_payload(payload: dict[str, Any]) -> dict[str, Any]:
    _validate_hash(payload)
    return {
        "data_types": {item["type_id"]: DataTypeNode(**item) for item in payload.get("data_types", [])},
        "tasks": {item["task_id"]: TaskNode(**item) for item in payload.get("tasks", [])},
        "scenario_profiles": [
            ScenarioProfileNode(**item) for item in payload.get("scenario_profiles", [])
        ],
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
