from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from benchmark_platform.canonical import canonical_sha256
from benchmark_platform.oracle import solve_template_oracle


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "docs/current/benchmark/v2/development_templates"
PRODUCT_ORDER = ("building", "road", "water_polygon", "waterways", "poi")
TASK_IDS = {
    "building": "TASK-BUILDING",
    "road": "TASK-ROAD",
    "water_polygon": "TASK-WATER-POLYGON",
    "waterways": "TASK-WATERWAYS",
    "poi": "TASK-POI",
}
CONTRACTS = {product: f"contract.product.{product}.v1" for product in PRODUCT_ORDER}
PRIMARY_ALGORITHMS = {
    "building": "algo.fusion.building.v1",
    "road": "algo.fusion.road.conflation.v7",
    "water_polygon": "algo.fusion.water_polygon.priority_merge.v2",
    "waterways": "algo.fusion.waterways.conflation.v7",
    "poi": "algo.fusion.poi.v1",
}
SOURCE_PRODUCTS = {
    "catalog.earthquake.building": "building",
    "catalog.flood.building": "building",
    "catalog.flood.road": "road",
    "catalog.flood.water_polygon": "water_polygon",
    "catalog.flood.waterways": "waterways",
    "catalog.generic.poi": "poi",
    "raw.osm.building": "building",
    "raw.microsoft.building": "building",
    "raw.osm.road": "road",
    "raw.microsoft.road": "road",
    "raw.osm.water": "water_polygon",
    "raw.hydrolakes.water": "water_polygon",
    "raw.osm.waterways": "waterways",
    "raw.hydrorivers.water": "waterways",
    "raw.osm.poi": "poi",
    "raw.gns.poi": "poi",
    "raw.google.poi": "poi",
}
ALGORITHM_PRODUCTS = {
    "algo.fusion.building.v1": "building",
    "algo.fusion.building.safe": "building",
    "algo.transform.raw_to_building_bundle": "building",
    "algo.fusion.road.conflation.v7": "road",
    "algo.transform.raw_to_road_bundle": "road",
    "algo.fusion.water_polygon.priority_merge.v2": "water_polygon",
    "algo.fusion.waterways.conflation.v7": "waterways",
    "algo.fusion.poi.v1": "poi",
    "algo.fusion.poi.geohash_neighbor_match.v1": "poi",
}
V2_UNIT_TYPES = {
    "TF-ALGORITHM-CAPABILITY-GROUNDING": "counterfactual_pair",
    "TF-AOI-RESOLUTION-BOUNDARY": "counterfactual_pair",
    "TF-VECTOR-ACQUISITION-FAILURE": "temporal_trace",
    "TF-QUALITY-GATE-EVIDENCE": "counterfactual_pair",
    "TF-EVIDENCE-COMPLETENESS": "temporal_trace",
    "TF-DELIVERY-STATE-TRACE": "temporal_trace",
}
HISTORICAL_IDS = [f"C{index:02d}" for index in range(1, 7)] + [f"H{index:02d}" for index in range(1, 10)]


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _fixture_hash(label: str) -> str:
    return "sha256:" + hashlib.sha256(f"authoring-fixture:{label}".encode("utf-8")).hexdigest()


def _family_cell(family_id: str, v1: dict[str, Any], v2: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    base = [item for item in v1["cells"] if item["template_family_id"] == family_id]
    candidate = [item for item in v2["cells"] if item["template_family_id"] == family_id]
    cells = base + candidate
    if not cells:
        raise ValueError(f"family has no capability-cell binding: {family_id}")
    unit_type = base[0]["experiment_unit_type"] if base else V2_UNIT_TYPES[family_id]
    return cells, unit_type


def _task_sources(contract: dict[str, Any], product: str) -> list[str]:
    return [source_id for source_id in contract["source_ids"] if SOURCE_PRODUCTS.get(source_id) == product]


def _delivery_state(family_id: str, product: str) -> str:
    if family_id == "TF-AOI-RESOLUTION-BOUNDARY":
        return "rejected"
    if family_id == "TF-VECTOR-ACQUISITION-FAILURE":
        return "gap" if product == "water_polygon" else "provisional"
    if family_id == "TF-QUALITY-GATE-EVIDENCE":
        return "degraded" if product == "water_polygon" else "provisional"
    if family_id == "TF-EVIDENCE-COMPLETENESS":
        return "final"
    if family_id == "TF-DELIVERY-STATE-TRACE":
        return "provisional"
    return "planned"


def _tasks(family_id: str, contract: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    products = [product for product in PRODUCT_ORDER if product in contract["product_types"]]
    for product in products:
        sources = _task_sources(contract, product)
        states = [
            {
                "source_id": source_id,
                "availability": "available",
                "semantic_status": "compatible",
                "legal_for_task": True,
            }
            for source_id in sources
        ]
        if family_id == "TF-SOURCE-AVAILABILITY" and len(states) > 1:
            states[1]["availability"] = "delayed"
        if family_id == "TF-VECTOR-ACQUISITION-FAILURE" and product == "water_polygon" and states:
            states[0]["availability"] = "failed"
        observed: list[dict[str, Any]] = []
        if family_id == "TF-VECTOR-ACQUISITION-FAILURE" and product == "water_polygon":
            observed.append({
                "failure_id": "FAIL-ACQUISITION-WATER-POLYGON",
                "stage": "materialization",
                "failure_class": "acquisition.remote_failure",
                "observed_at_step": 1,
                "evidence_ref": "authoring://source-attempt/water-polygon",
                "recoverable": True,
            })
        if family_id == "TF-QUALITY-GATE-EVIDENCE" and product == "water_polygon":
            observed.append({
                "failure_id": "FAIL-QUALITY-WATER-POLYGON",
                "stage": "quality_gate",
                "failure_class": "quality.geometry_type",
                "observed_at_step": 2,
                "evidence_ref": "authoring://quality/water-polygon",
                "recoverable": True,
            })
        state = _delivery_state(family_id, product)
        tasks.append({
            "task_id": TASK_IDS[product],
            "task_kind": product,
            "contract_ids": [CONTRACTS[product]],
            "source_states": states,
            "observed_failures": observed,
            "delivery_history": [{"step": 1, "state": state, "evidence_ref": f"authoring://delivery/{product}"}],
            "precedence_after": [],
        })
    if family_id == "TF-CROSS-TASK-PRECEDENCE":
        by_product = {task["task_kind"]: task for task in tasks}
        priority = [product for product in ("water_polygon", "waterways", "road", "building", "poi") if product in by_product]
        for index, product in enumerate(priority):
            by_product[product]["precedence_after"] = [TASK_IDS[item] for item in priority[:index]]
    return tasks


def _path_value(document: Any, path: str) -> Any:
    current = document
    for token in path.removeprefix("$.").split("."):
        if "[" in token:
            name, index = token.rstrip("]").split("[")
            current = current[name][int(index)]
        else:
            current = current[token]
    return deepcopy(current)


def _variable_specs(family_id: str, document: dict[str, Any], contract: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    first_task = "$.task_state.tasks[0]"
    paths = {
        "VAR-CONTRACT-REQUIREDNESS": f"{first_task}.source_states[1].availability",
        "VAR-TASK-KIND": f"{first_task}.task_kind",
        "VAR-OBSERVABLE-SOURCES": f"{first_task}.source_states",
        "VAR-CANONICAL-REQUEST": f"{first_task}.task_kind",
        "VAR-OBSERVABLE-FACTS": f"{first_task}.source_states",
        "VAR-REQUEST-SURFACE-FORM": "$.task_state.disaster_type",
        "VAR-TASK-SET": "$.task_state.tasks",
        "VAR-TASK-LOCAL-FACTS": "$.task_state.tasks",
        "VAR-REQUEST-TASK-ORDER": "$.task_state.global_observations.mission_priority",
        "VAR-CONTEXT-RECORD-ORDER": "$.task_state.tasks",
        "VAR-REQUEST": "$.task_state.disaster_type",
        "VAR-IRRELEVANT-METADATA": "$.task_state.global_observations.time_budget_class",
        "VAR-UNRELATED-CATALOG-ENTRY": "$.task_state.global_observations.network_state",
        "VAR-MISSION-PRIORITY": "$.task_state.global_observations.mission_priority",
        "VAR-TASK-LOCAL-CONTRACTS": "$.task_state.tasks",
        "VAR-CROSSWALK-REFERENCE-EXISTS": "$.task_state.resource_regime",
        "VAR-CONTRACT": f"{first_task}.contract_ids",
        "VAR-PLAN-SCHEMA-VALID": "$.task_state.resource_regime",
        "VAR-PLANNER-INPUT": "$.task_state.tasks",
        "VAR-OUTPUT-SCHEMA": "$.hashing.canonicalization",
        "VAR-CANDIDATE-PLAN-VETO-VIOLATION": "$.task_state.resource_regime",
        "VAR-ALGORITHM-TASK-COMPATIBILITY": "$.v2_extensions.algorithm_grounding[0].capability_status",
        "VAR-SOURCE-SEMANTICS": f"{first_task}.source_states",
        "VAR-SOURCE-AVAILABILITY": f"{first_task}.source_states[1].availability",
        "VAR-AOI-RESOLUTION-STATUS": "$.v2_extensions.aoi.resolution_status",
        "VAR-KG-RELEASE": "$.provenance.kg_release_id",
        "VAR-AOI-SURFACE-FORM": "$.v2_extensions.aoi.aoi_candidate_set",
        "VAR-SOURCE-ATTEMPT-STATUS": "$.v2_extensions.acquisition[0].attempt_status",
        "VAR-AOI-GEOMETRY": "$.task_state.resource_regime",
        "VAR-ALGORITHM": "$.crosswalk.references",
        "VAR-RETRY-BUDGET": "$.v2_extensions.acquisition[0].retry_eligible",
        "VAR-QUALITY-GATE-ACCEPTED": "$.v2_extensions.quality_evidence[0].quality_gate_result",
        "VAR-HARD-CHECKS": "$.v2_extensions.quality_evidence[0].hard_checks",
        "VAR-ARTIFACT-LINEAGE": "$.v2_extensions.quality_evidence[0].artifact_lineage",
        "VAR-SOFT-ADAPTATION": "$.v2_extensions.quality_evidence[0].soft_adaptations",
        "VAR-REQUIRED-ARTIFACT-PRESENT": "$.v2_extensions.delivery[0].evidence_refs",
        "VAR-FROZEN-PLAN": "$.provenance.design_id",
        "VAR-INPUT-HASHES": "$.provenance.kg_release_id",
        "VAR-EVIDENCE-ORDER": "$.v2_extensions.delivery[0].evidence_refs",
        "VAR-LATEST-DELIVERY-STATE": "$.v2_extensions.delivery[0].to_state",
        "VAR-SOURCE-STATE": f"{first_task}.source_states",
        "VAR-FAILURE-HISTORY": f"{first_task}.observed_failures",
    }
    alternatives = {
        "VAR-CONTRACT-REQUIREDNESS": ["available", "missing"],
        "VAR-REQUEST-SURFACE-FORM": ["generic", "emergency", "disaster"],
        "VAR-IRRELEVANT-METADATA": ["standard", "standard_with_rescue_note"],
        "VAR-UNRELATED-CATALOG-ENTRY": ["online", "online_with_unrelated_catalog_metadata"],
        "VAR-CROSSWALK-REFERENCE-EXISTS": ["crosswalk_closed", "crosswalk_missing", "crosswalk_ambiguous"],
        "VAR-PLAN-SCHEMA-VALID": ["candidate_plan_valid", "candidate_plan_invalid"],
        "VAR-CANDIDATE-PLAN-VETO-VIOLATION": ["candidate_plan_compatible", "candidate_plan_geometry_mismatch"],
        "VAR-ALGORITHM-TASK-COMPATIBILITY": ["compatible", "geometry_mismatch", "unsupported", "reserved"],
        "VAR-SOURCE-AVAILABILITY": ["available", "delayed", "missing", "failed"],
        "VAR-AOI-RESOLUTION-STATUS": ["resolved", "ambiguous", "out_of_domain", "unresolved"],
        "VAR-SOURCE-ATTEMPT-STATUS": ["planned", "started", "succeeded", "failed", "skipped", "manual_intervention"],
        "VAR-RETRY-BUDGET": [False, True],
        "VAR-QUALITY-GATE-ACCEPTED": ["pass", "provisional", "degraded", "fail", "missing"],
        "VAR-LATEST-DELIVERY-STATE": ["pending", "gap", "provisional", "degraded", "final", "superseded"],
    }
    result = {"causal_variables": [], "invariants": [], "nuisance_variables": []}
    roles = (
        ("causal_variables", "causal_variable_ids", "causal"),
        ("invariants", "invariant_variable_ids", "invariant"),
        ("nuisance_variables", "nuisance_variable_ids", "nuisance"),
    )
    for output_key, contract_key, role in roles:
        for variable_id in contract[contract_key]:
            path = paths[variable_id]
            current = _path_value(document, path)
            allowed = deepcopy(alternatives.get(variable_id, [current]))
            if current not in allowed:
                allowed.insert(0, current)
            result[output_key].append({
                "variable_id": variable_id,
                "json_path": path,
                "value_type": {
                    str: "string", bool: "boolean", int: "integer", float: "number", list: "array", dict: "object", type(None): "null"
                }[type(current)],
                "allowed_values": allowed,
                "mutation_role": role,
            })
    return result


def _relation(unit_type: str, family_id: str, variables: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    if unit_type == "single":
        kind, path, operator, minimum = "evidence_presence", "$.task_state", "present", 1
    elif unit_type == "counterfactual_pair":
        kind, path, operator, minimum = "causal_change", variables["causal_variables"][0]["json_path"], "not_equals", 2
    elif unit_type == "invariant_set":
        kind, path, operator, minimum = "semantic_equivalence", variables["invariants"][0]["json_path"], "equals", 3
    elif unit_type == "composition_family":
        kind, path, operator, minimum = "task_local_composition", "$.task_state.tasks", "equals", 2
    else:
        kind, path, operator, minimum = "temporal_transition", "$.task_state.tasks[0].delivery_history[0].state", "transitions_to", 2
    assertion = {"assertion_id": f"ASSERT-{family_id.removeprefix('TF-')}", "kind": kind, "left_path": path, "operator": operator}
    return {"unit_type": unit_type, "relation_id": f"REL-{family_id.removeprefix('TF-')}", "minimum_members": minimum, "relation_assertions": [assertion]}


def _crosswalk(contract: dict[str, Any], tasks: list[dict[str, Any]]) -> dict[str, Any]:
    task_ids_by_product = {task["task_kind"]: task["task_id"] for task in tasks}
    refs: list[dict[str, Any]] = []
    for product in contract["product_types"]:
        refs.append({"reference_id": CONTRACTS[product], "reference_type": "contract", "used_by_task_ids": [task_ids_by_product[product]]})
    for source_id in contract["source_ids"]:
        product = SOURCE_PRODUCTS[source_id]
        refs.append({"reference_id": source_id, "reference_type": "source", "used_by_task_ids": [task_ids_by_product[product]]})
    for algorithm_id in contract["algorithm_ids"]:
        product = ALGORITHM_PRODUCTS[algorithm_id]
        refs.append({"reference_id": algorithm_id, "reference_type": "algorithm", "used_by_task_ids": [task_ids_by_product[product]]})
    for policy_id in contract["quality_policy_ids"]:
        if not policy_id.startswith("quality.default."):
            continue
        products = [product for product in contract["product_types"] if f".{product}." in policy_id]
        used_by = [task_ids_by_product[product] for product in products] or list(task_ids_by_product.values())
        refs.append({"reference_id": policy_id, "reference_type": "quality_policy", "used_by_task_ids": used_by})
    return {"kg_release_id": "fusionagent-kg-v1.0.0", "references": refs, "missing_reference_policy": "fail_closed"}


def _oracle(family_id: str, tasks: list[dict[str, Any]], unit_type: str) -> dict[str, Any]:
    constraints = []
    for task in tasks:
        state = task["delivery_history"][-1]["state"]
        allowed_states = [state]
        if family_id == "TF-AOI-RESOLUTION-BOUNDARY":
            allowed_states = ["planned", "rejected"]
        constraints.append({
            "task_id": task["task_id"],
            "required": True,
            "allowed_delivery_states": allowed_states,
            "allowed_source_ids": [source["source_id"] for source in task["source_states"]],
            "forbidden_source_ids": [],
        })
    decision = "reject" if family_id == "TF-AOI-RESOLUTION-BOUNDARY" else "gap" if any(item["delivery_history"][-1]["state"] == "gap" for item in tasks) else "degraded" if any(item["delivery_history"][-1]["state"] == "degraded" for item in tasks) else "plan"
    return {
        "allowed_decisions": [decision],
        "task_constraints": constraints,
        "relation_assertion_ids": [f"ASSERT-{family_id.removeprefix('TF-')}"],
        "manual_review_item_ids": [f"REVIEW-{family_id.removeprefix('TF-')}-SEMANTICS"],
        "allows_multiple_valid_plans": unit_type in {"counterfactual_pair", "invariant_set", "composition_family"},
    }


def _base_template(family: dict[str, Any], contract: dict[str, Any], v1: dict[str, Any], v2: dict[str, Any]) -> dict[str, Any]:
    family_id = family["family_id"]
    cells, unit_type = _family_cell(family_id, v1, v2)
    tasks = _tasks(family_id, contract)
    priority = [task["task_id"] for task in tasks]
    resource_regime = {
        "TF-KG-CROSSWALK-MISSING": "crosswalk_closed",
        "TF-PLAN-STRUCTURE-INVALID": "candidate_plan_valid",
        "TF-VALIDATOR-VETO": "candidate_plan_compatible",
        "TF-AOI-RESOLUTION-BOUNDARY": "aoi_ambiguous",
    }.get(family_id, "bounded_development_authoring")
    template: dict[str, Any] = {
        "template_family_id": family_id,
        "version": "2.0.0" if family["status"] == "v2_candidate" else "1.0.0",
        "status": "frozen_template_family",
        "claim_ids": list(dict.fromkeys(item["claim_id"] for item in cells)),
        "capability_cell_ids": [item["capability_cell_id"] for item in cells],
        "mechanism_family": cells[-1]["mechanism_family"],
        "complexity_level": contract["complexity_level"],
        "experiment_unit": {},
        "provenance": {
            "design_id": "fusionagent.benchmark-design.v1",
            "charter_id": "fusionagent.benchmark-charter.v1",
            "matrix_id": "fusionagent.benchmark-capability-matrix.v1",
            "kg_release_id": "fusionagent-kg-v1.0.0",
            "kg_semantic_hash": "sha256:50067b9368914c47580707650789c04c78b2e856ccb3ef4d120a31f36c0ad71e",
            "authoring_basis": ["approved-v2-candidate-semantics", family_id.lower()],
            "historical_case_similarity_review": "reviewed against the frozen exclusion registry; no semantic copy admitted",
        },
        "task_state": {
            "disaster_type": "generic" if family_id in {"TF-WORDING-PARAPHRASE", "TF-PLAN-STRUCTURE-INVALID", "TF-SOURCE-AVAILABILITY"} else "flood",
            "resource_regime": resource_regime,
            "tasks": tasks,
            "global_observations": {"mission_priority": priority, "time_budget_class": "standard", "network_state": "online"},
        },
        "variables": {},
        "oracle": {},
        "vetoes": [
            {
                "veto_id": f"VETO-{family_id.removeprefix('TF-')}",
                "failure_class": f"authoring.{family_id.removeprefix('TF-').lower().replace('-', '_')}",
                "condition": contract["veto_summary"],
                "evidence_path": "$.task_state.tasks",
            }
        ],
        "views": {
            "planner_visible_paths": ["$.task_state"],
            "evaluator_only_paths": ["$.oracle"],
            "human_blind_paths": ["$.task_state"],
            "planner_forbidden_path_prefixes": ["$.oracle", "$.vetoes", "$.experiment_unit.relation_assertions", "$.partition_policy", "$.hashing"],
        },
        "crosswalk": _crosswalk(contract, tasks),
        "partition_policy": {
            "allowed_partitions": ["development"],
            "historical_case_ids_forbidden_in_confirmation": HISTORICAL_IDS,
            "semantic_copy_forbidden": True,
        },
        "generation": {
            "generator_id": "generator.method-selection-authoring.v2-candidate",
            "template_first": True,
            "seed_namespace": "fusionagent-benchmark-v1-development",
            "instance_id_pattern": "^BDV1-DEV-BC-[A-Z0-9-]+-[0-9]{3}$",
            "stopping_rule_id": "stop.pre-registered-development-budget.v1",
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "utf8-json-sorted-keys-compact-no-bom",
            "template_hash_field": "template_sha256",
            "instance_hash_field": "instance_sha256",
        },
    }
    if contract.get("e2e_eligibility"):
        template["e2e_eligibility"] = contract["e2e_eligibility"]
    combined = deepcopy(template)
    if family["status"] == "v2_candidate":
        combined.update(_extension_skeleton(family_id, tasks, contract))
        combined["frozen_plan_sha256"] = _fixture_hash(f"{family_id}:plan")
        combined["lineage_binding"] = {
            "contract_ids": list(contract["contract_ids"]),
            "source_ids": list(contract["source_ids"]),
            "algorithm_ids": list(contract["algorithm_ids"]),
            "artifact_hashes": [_fixture_hash(f"{family_id}:lineage")],
        }
    variables = _variable_specs(family_id, combined, contract)
    template["variables"] = {**variables, "maximum_causal_mutations_per_pair": 1}
    template["experiment_unit"] = _relation(unit_type, family_id, variables)
    template["oracle"] = _oracle(family_id, tasks, unit_type)
    return template


def _hard_checks(status: str = "pass") -> list[dict[str, Any]]:
    return [{"check_id": check_id, "status": status, "relaxed": False} for check_id in ("geometry_type", "invalid_geometry_rate", "source_lineage", "required_fields")]


def _extension_values(family_id: str, tasks: list[dict[str, Any]], contract: dict[str, Any]) -> dict[str, Any]:
    extensions: dict[str, Any] = {}
    artifact_hashes: dict[str, str] = {}
    if "aoi" in contract["required_v2_extensions"]:
        extensions["aoi"] = {
            "aoi_candidate_set": ["Abidjan", "Abidjan, Cote d'Ivoire"],
            "resolution_status": "ambiguous" if family_id == "TF-AOI-RESOLUTION-BOUNDARY" else "resolved",
            "ambiguity_class": "duplicate_place_name" if family_id == "TF-AOI-RESOLUTION-BOUNDARY" else "none",
            "resolved_geometry_hash": None if family_id == "TF-AOI-RESOLUTION-BOUNDARY" else _fixture_hash(f"{family_id}:aoi"),
            "boundary_provenance": "aoi.resolution.v1 authoring scenario",
            "cross_aoi_isolation": True,
        }
    if "acquisition" in contract["required_v2_extensions"]:
        attempts = []
        for task in tasks:
            sources = [item["source_id"] for item in task["source_states"]]
            selected = next((item for item in sources if item.startswith("raw.")), sources[0])
            failed = family_id == "TF-VECTOR-ACQUISITION-FAILURE" and task["task_kind"] == "water_polygon"
            manual = selected == "raw.microsoft.road"
            artifact_hash = None if failed else _fixture_hash(f"{family_id}:{selected}")
            if artifact_hash:
                artifact_hashes[selected] = artifact_hash
            attempts.append({
                "task_id": task["task_id"],
                "attempt_id": f"ATTEMPT-{task['task_kind'].upper().replace('_', '-')}-01",
                "source_id": selected,
                "attempt_status": "failed" if failed else "succeeded",
                "materialization_mode": "remote" if failed else "manual_preload" if manual else "local_bundle",
                "remote_success": False,
                "manual_preload": manual,
                "failure_code": "SOURCE_DOWNLOAD_FAILED" if failed else None,
                "retry_eligible": failed,
                "artifact_hash": artifact_hash,
            })
        extensions["acquisition"] = attempts
    if "algorithm_grounding" in contract["required_v2_extensions"]:
        groundings = []
        for task in tasks:
            raw_sources = [item["source_id"] for item in task["source_states"] if item["source_id"].startswith("raw.")]
            materialized = [source_id for source_id in raw_sources if source_id in artifact_hashes]
            if family_id in {"TF-ALGORITHM-CAPABILITY-GROUNDING", "TF-EVIDENCE-COMPLETENESS"}:
                materialized = raw_sources[:1]
            if family_id == "TF-EVIDENCE-COMPLETENESS":
                materialized = raw_sources
            missing = [source_id for source_id in raw_sources if source_id not in materialized]
            groundings.append({
                "task_id": task["task_id"],
                "selected_algorithm_id": PRIMARY_ALGORITHMS[task["task_kind"]],
                "capability_status": "compatible" if not missing else "input_missing",
                "required_input_source_ids": raw_sources,
                "materialized_input_source_ids": materialized,
                "missing_required_input_source_ids": missing,
            })
        extensions["algorithm_grounding"] = groundings
    if "quality_evidence" in contract["required_v2_extensions"]:
        quality = []
        for task in tasks:
            raw_sources = [item["source_id"] for item in task["source_states"] if item["source_id"].startswith("raw.")]
            failed = family_id == "TF-QUALITY-GATE-EVIDENCE" and task["task_kind"] == "water_polygon"
            selected_sources = raw_sources if len(raw_sources) > 1 else raw_sources[:1]
            quality.append({
                "task_id": task["task_id"],
                "source_mode": "multi_source" if len(selected_sources) > 1 else "single_source",
                "source_ids": selected_sources,
                "quality_gate_result": "fail" if failed else "pass" if family_id == "TF-EVIDENCE-COMPLETENESS" else "provisional",
                "hard_checks": _hard_checks("fail" if failed else "pass"),
                "soft_adaptations": [] if len(selected_sources) > 1 else [{"policy_id": "quality.external_degradation.v1", "check_id": "source_contribution_balance", "applied": True}],
                "evidence_manifest": f"authoring://quality/{task['task_kind']}",
                "artifact_lineage": [f"authoring://artifact/{task['task_kind']}"],
            })
        extensions["quality_evidence"] = quality
    if "delivery" in contract["required_v2_extensions"]:
        deliveries = []
        full_chain = family_id == "TF-EVIDENCE-COMPLETENESS"
        for task in tasks:
            to_state = _delivery_state(family_id, task["task_kind"])
            evidence_types = ["planning_decision", "source_attempt", "gap_declaration"]
            if full_chain:
                evidence_types = ["source_attempt", "execution_trace", "quality_report", "artifact_lineage", "delivery_manifest"]
            elif family_id in {"TF-QUALITY-GATE-EVIDENCE", "TF-DELIVERY-STATE-TRACE"}:
                evidence_types = ["planning_decision", "quality_report", "artifact_lineage"]
            deliveries.append({
                "task_id": task["task_id"],
                "from_state": "provisional" if to_state == "final" else "planned",
                "to_state": to_state,
                "transition_reason": "pre-registered authoring scenario",
                "evidence_refs": [{"evidence_type": kind, "ref": f"authoring://{kind}/{task['task_kind']}"} for kind in evidence_types],
                "terminal": to_state in {"gap", "provisional", "degraded", "final", "rejected"},
            })
        extensions["delivery"] = deliveries
    return extensions


def _extension_skeleton(family_id: str, tasks: list[dict[str, Any]], contract: dict[str, Any]) -> dict[str, Any]:
    return {"v2_extensions": _extension_values(family_id, tasks, contract)}


def _extension_document(template: dict[str, Any], contract: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    values = _extension_values(template["template_family_id"], template["task_state"]["tasks"], contract)
    artifact_hashes = sorted({attempt["artifact_hash"] for attempt in values.get("acquisition", []) if attempt["artifact_hash"]})
    source_ids = sorted({source["source_id"] for task in template["task_state"]["tasks"] for source in task["source_states"]})
    if template["template_family_id"] == "TF-EVIDENCE-COMPLETENESS":
        artifact_hashes = sorted({_fixture_hash(f"{template['template_family_id']}:{source_id}") for source_id in source_ids if source_id.startswith("raw.")})
    return {
        "base_template_schema_id": "https://fusionagent.local/schemas/benchmark-template.v1.json",
        "base_template_id": template["template_family_id"],
        "base_template_sha256": canonical_sha256(template),
        "frozen_plan_sha256": canonical_sha256(plan),
        "lineage_binding": {
            "contract_ids": sorted({identifier for task in template["task_state"]["tasks"] for identifier in task["contract_ids"]}),
            "source_ids": source_ids,
            "algorithm_ids": list(contract["algorithm_ids"]),
            "artifact_hashes": artifact_hashes,
        },
        "status": "v2_candidate",
        "v2_extensions": values,
    }


def build(output_root: Path = OUTPUT_ROOT) -> dict[str, Any]:
    semantics = _read(ROOT / "docs/current/method-selection-template-families-v2-candidate.json")
    contracts_doc = _read(ROOT / "docs/current/method-selection-template-authoring-contracts-v2-candidate.json")
    v1_matrix = _read(ROOT / "docs/current/benchmark/v1/capability_matrix.json")
    v2_matrix = _read(ROOT / "docs/current/benchmark/v2/capability_matrix_candidate.json")
    contracts = {item["template_family_id"]: item for item in contracts_doc["families"]}
    entries = []
    for family in semantics["families"]:
        family_id = family["family_id"]
        contract = contracts[family_id]
        template = _base_template(family, contract, v1_matrix, v2_matrix)
        plan = {
            "plan_id": f"PLAN-AUTHORING-{family_id.removeprefix('TF-')}",
            "status": "authoring_fixture_not_executed",
            "template_family_id": family_id,
            "task_ids": [task["task_id"] for task in template["task_state"]["tasks"]],
            "contract_ids": list(contract["contract_ids"]),
            "source_ids": list(contract["source_ids"]),
            "algorithm_ids": list(contract["algorithm_ids"]),
            "delivery_states": {task["task_id"]: task["delivery_history"][-1]["state"] for task in template["task_state"]["tasks"]},
        }
        base_path = output_root / "base" / f"{family_id}.json"
        plan_path = output_root / "plan_bindings" / f"{family_id}.json"
        proof_path = output_root / "oracle_proofs" / f"{family_id}.json"
        _write(base_path, template)
        _write(plan_path, plan)
        proof = solve_template_oracle(template).model_dump(mode="json")
        _write(proof_path, proof)
        extension_path = None
        if family["status"] == "v2_candidate":
            extension_path = output_root / "extensions" / f"{family_id}.json"
            _write(extension_path, _extension_document(template, contract, plan))
        entries.append({
            "template_family_id": family_id,
            "semantic_status": family["status"],
            "base_template": base_path.relative_to(ROOT).as_posix(),
            "base_template_sha256": canonical_sha256(template),
            "plan_binding": plan_path.relative_to(ROOT).as_posix(),
            "plan_binding_sha256": canonical_sha256(plan),
            "oracle_proof": proof_path.relative_to(ROOT).as_posix(),
            "oracle_proof_sha256": canonical_sha256(proof),
            "v2_extension": extension_path.relative_to(ROOT).as_posix() if extension_path else None,
            "generation_readiness": "requires_member_materializer",
        })
    manifest = {
        "manifest_id": "fusionagent.method-selection-development-template-authoring.v2-candidate",
        "status": "authoring_spec_only_pending_review",
        "partition": "development",
        "approved_semantics_manifest": "docs/current/method-selection-template-families-v2-candidate.json",
        "authoring_contract_manifest": "docs/current/method-selection-template-authoring-contracts-v2-candidate.json",
        "template_schema": "docs/current/benchmark/v1/template.schema.json",
        "v2_extension_schema": "schemas/benchmark_template_v2_candidate_extension.schema.json",
        "family_count": len(entries),
        "family_ids": [entry["template_family_id"] for entry in entries],
        "entries": entries,
        "evidence_boundary": {
            "authoring_fixture_hashes_are_live_gis_artifacts": False,
            "instances_generated": 0,
            "provider_calls": 0,
            "judge_calls": 0,
            "external_data_calls": 0,
            "selective_e2e_executed": False,
        },
        "known_blocker": {
            "code": "member_materializer_not_implemented",
            "detail": "The current development generator clones templates and does not apply variable domains to create distinct relation members.",
            "affected_claim": "Template documents are authored and auditable, but no benchmark instance is generation-ready yet.",
        },
    }
    _write(output_root / "authoring_manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()
    manifest = build(args.output_root)
    print(json.dumps({"status": manifest["status"], "family_count": manifest["family_count"], "output_root": str(args.output_root)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
