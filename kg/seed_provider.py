from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from kg import seed
from kg.models import (
    AlgorithmNode,
    AlgorithmParameterSpec,
    DataNeedNode,
    DataSourceNode,
    DataTypeNode,
    OutputRequirementNode,
    OutputSchemaPolicy,
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
    task_bundles: dict[str, TaskBundleNode]
    output_requirements: dict[str, OutputRequirementNode]
    qos_policies: dict[str, QoSPolicyNode]
    data_needs: list[DataNeedNode]
    repair_strategies: dict[str, RepairStrategyNode]


def load_seed_data(seed_manifest_path: Path | None = None) -> RepositorySeedPayload:
    """Load repository seed payload, preserving shared seed references for compatibility."""
    if seed_manifest_path is not None:
        payload = json.loads(Path(seed_manifest_path).read_text(encoding="utf-8"))
        return _repository_seed_payload(load_seed_manifest_payload(payload))

    return _repository_seed_payload(
        {
            "algorithms": seed.ALGORITHMS,
            "workflow_patterns": seed.WORKFLOW_PATTERNS,
            "can_transform_to": seed.CAN_TRANSFORM_TO,
            "data_sources": seed.DATA_SOURCES,
            "data_types": seed.DATA_TYPES,
            "parameter_specs": seed.PARAMETER_SPECS,
            "output_schema_policies": seed.OUTPUT_SCHEMA_POLICIES,
            "tasks": seed.TASKS,
            "scenario_profiles": seed.SCENARIO_PROFILES,
            "task_bundles": seed.TASK_BUNDLES,
            "output_requirements": seed.OUTPUT_REQUIREMENTS,
            "qos_policies": seed.QOS_POLICIES,
            "data_needs": seed.DATA_NEEDS,
            "repair_strategies": seed.REPAIR_STRATEGIES,
        }
    )


def _repository_seed_payload(seed_payload: dict[str, Any]) -> RepositorySeedPayload:
    return {
        "algorithms": seed_payload["algorithms"],
        "patterns": seed_payload["workflow_patterns"],
        # Manifest schema does not externalize transform edges yet, so keep the Python seed graph for old behavior.
        "can_transform_to": seed_payload.get("can_transform_to", seed.CAN_TRANSFORM_TO),
        "data_sources": seed_payload["data_sources"],
        "data_types": seed_payload["data_types"],
        "parameter_specs": seed_payload["parameter_specs"],
        "output_schema_policies": seed_payload["output_schema_policies"],
        "tasks": seed_payload["tasks"],
        "scenario_profiles": seed_payload["scenario_profiles"],
        "task_bundles": seed_payload["task_bundles"],
        "output_requirements": seed_payload["output_requirements"],
        "qos_policies": seed_payload["qos_policies"],
        "data_needs": seed_payload["data_needs"],
        "repair_strategies": seed_payload["repair_strategies"],
    }
