"""Compatibility view over the frozen KG entity release.

This module keeps the historical constant names used by a few callers.  It is
not a knowledge source: every value below is reconstructed from the canonical
``kg/ontology/v1.0.0/entities.json`` release by ``load_seed_data``.
"""

from __future__ import annotations

from kg.seed_provider import load_seed_data


_SEED = load_seed_data()

DATA_TYPES = _SEED["data_types"]
TASKS = _SEED["tasks"]
SCENARIO_PROFILES = _SEED["scenario_profiles"]
PRODUCT_CONTRACTS = _SEED["product_contracts"]
TASK_BUNDLES = _SEED["task_bundles"]
OUTPUT_REQUIREMENTS = _SEED["output_requirements"]
QOS_POLICIES = _SEED["qos_policies"]
DATA_NEEDS = _SEED["data_needs"]
REPAIR_STRATEGIES = _SEED["repair_strategies"]
CAN_TRANSFORM_TO = _SEED["can_transform_to"]
ALGORITHMS = _SEED["algorithms"]
PARAMETER_SPECS = _SEED["parameter_specs"]
WORKFLOW_PATTERNS = _SEED["patterns"]
DATA_SOURCES = _SEED["data_sources"]
OUTPUT_SCHEMA_POLICIES = _SEED["output_schema_policies"]


__all__ = [
    "ALGORITHMS",
    "CAN_TRANSFORM_TO",
    "DATA_NEEDS",
    "DATA_SOURCES",
    "DATA_TYPES",
    "OUTPUT_REQUIREMENTS",
    "OUTPUT_SCHEMA_POLICIES",
    "PARAMETER_SPECS",
    "PRODUCT_CONTRACTS",
    "QOS_POLICIES",
    "REPAIR_STRATEGIES",
    "SCENARIO_PROFILES",
    "TASK_BUNDLES",
    "TASKS",
    "WORKFLOW_PATTERNS",
]
