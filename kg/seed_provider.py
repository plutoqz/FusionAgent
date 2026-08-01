from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from kg.knowledge_release import DEFAULT_ENTITIES_PATH, load_release_index
from kg.models import (
    AlgorithmNode,
    AlgorithmParameterSpec,
    DataNeedNode,
    DataSourceNode,
    DataTypeNode,
    OutputRequirementNode,
    OutputSchemaPolicy,
    ProductContractNode,
    QoSPolicyNode,
    RepairStrategyNode,
    ScenarioProfileNode,
    TaskBundleNode,
    TaskNode,
    WorkflowPatternNode,
)
from kg.seed_manifest import load_seed_manifest_payload


class RepositorySeedPayload(TypedDict):
    algorithms: dict[str, AlgorithmNode]
    patterns: list[WorkflowPatternNode]
    can_transform_to: dict[str, list[str]]
    data_sources: list[DataSourceNode]
    data_types: dict[str, DataTypeNode]
    parameter_specs: dict[str, list[AlgorithmParameterSpec]]
    output_schema_policies: dict[str, OutputSchemaPolicy]
    tasks: dict[str, TaskNode]
    scenario_profiles: list[ScenarioProfileNode]
    product_contracts: dict[str, ProductContractNode]
    task_bundles: dict[str, TaskBundleNode]
    output_requirements: dict[str, OutputRequirementNode]
    qos_policies: dict[str, QoSPolicyNode]
    data_needs: list[DataNeedNode]
    repair_strategies: dict[str, RepairStrategyNode]


def load_seed_data(seed_manifest_path: Path | None = None) -> RepositorySeedPayload:
    """Load all static repository knowledge from one versioned manifest."""
    if seed_manifest_path is None:
        load_release_index()
    manifest_path = Path(seed_manifest_path) if seed_manifest_path is not None else DEFAULT_ENTITIES_PATH
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return _repository_seed_payload(load_seed_manifest_payload(payload))


def _repository_seed_payload(seed_payload: dict[str, Any]) -> RepositorySeedPayload:
    return {
        "algorithms": seed_payload["algorithms"],
        "patterns": seed_payload["workflow_patterns"],
        "can_transform_to": seed_payload["transform_edges"],
        "data_sources": seed_payload["data_sources"],
        "data_types": seed_payload["data_types"],
        "parameter_specs": seed_payload["parameter_specs"],
        "output_schema_policies": seed_payload["output_schema_policies"],
        "tasks": seed_payload["tasks"],
        "scenario_profiles": seed_payload["scenario_profiles"],
        "product_contracts": seed_payload["product_contracts"],
        "task_bundles": seed_payload["task_bundles"],
        "output_requirements": seed_payload["output_requirements"],
        "qos_policies": seed_payload["qos_policies"],
        "data_needs": seed_payload["data_needs"],
        "repair_strategies": seed_payload["repair_strategies"],
    }
