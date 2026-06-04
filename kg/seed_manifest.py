from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from kg import seed


SCHEMA_VERSION = "1.0.0"


def build_seed_manifest_payload() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "metadata": {
            "schema_version": SCHEMA_VERSION,
            "generated_from": "kg.seed",
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
