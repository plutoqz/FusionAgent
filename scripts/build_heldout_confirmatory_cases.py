"""Build the frozen held-out confirmatory planning case set.

This builder is deliberately independent from run_simplified_kg_experiment.py:
it does not import its case generators, fault mutators, or oracle constructors.
The generated JSON is frozen input to the runner, not generated during a run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any


PROFILE = "heldout_confirmatory_v1"
PRODUCTS = ("building", "road", "water_polygon", "waterways", "poi")
PRIORITY = {"water_polygon": 0, "waterways": 1, "road": 2, "building": 3, "poi": 4}
ALIASES = {
    "building": "buildings",
    "road": "roads",
    "water_polygon": "reservoirs",
    "waterways": "streams",
    "poi": "clinics",
}

# This fixture is copied from the frozen KG v1 release and reviewed as case-set
# ground truth. The experiment runner never regenerates oracle truth from KG.
PRODUCT_TRUTH: dict[str, dict[str, Any]] = {
    "building": {
        "task_kind": "building",
        "task_id": "task.building.fusion",
        "output_type": "dt.building.fused",
        "pattern_ids": ["wp.earthquake.building.default", "wp.earthquake.building.safe", "wp.flood.building.default", "wp.flood.building.safe"],
        "algorithm_ids": ["algo.fusion.building.safe", "algo.fusion.building.v1"],
        "source_ids": ["upload.bundle"],
        "contract_id": "contract.product.building.v1",
        "required_fields": ["geometry"],
        "output_requirement_id": "or.building.fused.v1",
        "quality_gates": ["source_materialized", "aoi_coverage_checked", "non_empty_or_justified_empty", "geometry_validity_checked", "minimum_attribute_set_checked", "provenance_recorded", "duplicate_or_overlap_rate_checked"],
        "evidence_requirements": ["source_provenance", "aoi_coverage", "geometry_validity", "quality_result", "coverage_result", "duplicate_or_overlap_result"],
        "qos_policy_ids": ["qos.task.default.v1", "qos.scenario.flood.v1", "qos.scenario.earthquake.v1", "qos.scenario.typhoon.v1"],
    },
    "road": {
        "task_kind": "road",
        "task_id": "task.road.fusion",
        "output_type": "dt.road.fused",
        "pattern_ids": ["wp.flood.road.default", "wp.road.fusioncode.conflation.v7"],
        "algorithm_ids": ["algo.fusion.road.conflation.v7"],
        "source_ids": ["catalog.flood.road", "upload.bundle"],
        "contract_id": "contract.product.road.v1",
        "required_fields": ["geometry"],
        "output_requirement_id": "or.road.fused.v1",
        "quality_gates": ["source_materialized", "aoi_coverage_checked", "non_empty_or_justified_empty", "geometry_validity_checked", "minimum_attribute_set_checked", "provenance_recorded", "duplicate_line_rate_checked", "line_topology_checked"],
        "evidence_requirements": ["source_provenance", "aoi_coverage", "geometry_validity", "quality_result", "network_topology_result", "duplicate_line_result"],
        "qos_policy_ids": ["qos.task.default.v1", "qos.scenario.flood.v1", "qos.scenario.earthquake.v1", "qos.scenario.typhoon.v1"],
    },
    "water_polygon": {
        "task_kind": "water_polygon",
        "task_id": "task.water.fusion",
        "output_type": "dt.water.fused",
        "pattern_ids": ["wp.flood.water_polygon.default", "wp.flood.water.default", "wp.water_polygon.fusioncode.priority_merge.v2"],
        "algorithm_ids": ["algo.fusion.water_polygon.priority_merge.v2"],
        "source_ids": ["catalog.flood.water", "catalog.flood.water_polygon"],
        "contract_id": "contract.product.water_polygon.v1",
        "required_fields": ["geometry"],
        "output_requirement_id": "or.water.fused.v1",
        "quality_gates": ["source_materialized", "aoi_coverage_checked", "non_empty_or_justified_empty", "geometry_validity_checked", "minimum_attribute_set_checked", "provenance_recorded", "duplicate_or_sliver_rate_checked", "polygon_boundary_validity_checked"],
        "evidence_requirements": ["source_provenance", "aoi_coverage", "geometry_validity", "quality_result", "duplicate_or_sliver_result", "polygon_boundary_result"],
        "qos_policy_ids": ["qos.task.default.v1", "qos.scenario.flood.v1", "qos.scenario.typhoon.v1"],
    },
    "waterways": {
        "task_kind": "waterways",
        "task_id": "task.waterways.fusion",
        "output_type": "dt.waterways.fused",
        "pattern_ids": ["wp.flood.waterways.default", "wp.waterways.fusioncode.conflation.v7"],
        "algorithm_ids": ["algo.fusion.waterways.conflation.v7"],
        "source_ids": ["catalog.flood.waterways"],
        "contract_id": "contract.product.waterways.v1",
        "required_fields": ["geometry", "fusion_source", "match_role", "waterway_class", "source_layer"],
        "output_requirement_id": "or.waterways.fused.v1",
        "quality_gates": ["source_materialized", "aoi_coverage_checked", "non_empty_or_justified_empty", "geometry_validity_checked", "minimum_attribute_set_checked", "provenance_recorded", "zero_length_segments_checked", "endpoint_dangles_checked", "connectivity_checked"],
        "evidence_requirements": ["source_provenance", "aoi_coverage", "geometry_validity", "quality_result", "line_topology_metrics", "connectivity_result"],
        "qos_policy_ids": ["qos.task.default.v1", "qos.scenario.flood.v1", "qos.scenario.typhoon.v1"],
    },
    "poi": {
        "task_kind": "poi",
        "task_id": "task.poi.fusion",
        "output_type": "dt.poi.fused",
        "pattern_ids": ["wp.generic.poi.default", "wp.poi.fusioncode.geohash_priority.v1"],
        "algorithm_ids": ["algo.fusion.poi.geohash_neighbor_match.v1", "algo.fusion.poi.v1"],
        "source_ids": ["catalog.generic.poi", "upload.bundle"],
        "contract_id": "contract.product.poi.v1",
        "required_fields": ["geometry"],
        "output_requirement_id": "or.poi.fused.v1",
        "quality_gates": ["source_materialized", "aoi_coverage_checked", "non_empty_or_justified_empty", "geometry_validity_checked", "minimum_attribute_set_checked", "provenance_recorded", "duplicate_candidate_rate_checked", "category_conflicts_checked"],
        "evidence_requirements": ["source_provenance", "aoi_coverage", "geometry_validity", "quality_result", "duplicate_candidate_result", "category_conflict_result"],
        "qos_policy_ids": ["qos.task.default.v1"],
    },
}

SCENARIOS = (
    ("precedence_conflict", "plan", "priority_conflict"),
    ("alias_ambiguity", "plan", "alias_tokens"),
    ("source_permission", "gap", "source_permission_denied"),
    ("retry_exhaustion", "gap", "timeout_exhausted"),
    ("quality_degradation", "degraded", "quality_invalid"),
    ("contract_field_loss", "gap", "required_field_missing"),
    ("evidence_chain_gap", "manual", "evidence_missing"),
    ("algorithm_policy_conflict", "gap", "algorithm_incompatible"),
    ("primary_delivery_block", "gap", "delivery_blocked"),
    ("implicit_contract_veto", "hard_veto", "validator_blocked"),
    ("poisoned_candidate_plan", "plan", "candidate_poison"),
    ("secondary_channel_recovery", "partial", "fallback_ready"),
)

SIGNAL_POOLS = {
    "plan": ("priority_conflict", "alias_tokens", "candidate_poison"),
    "gap": ("source_permission_denied", "timeout_exhausted", "required_field_missing", "algorithm_incompatible", "delivery_blocked"),
    "degraded": ("quality_invalid", "priority_conflict", "candidate_poison"),
    "manual": ("evidence_missing", "alias_tokens", "candidate_poison"),
    "hard_veto": ("validator_blocked", "delivery_blocked", "timeout_exhausted"),
    "partial": ("fallback_ready", "priority_conflict", "candidate_poison"),
}


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _companions(product: str, scenario_index: int, instance: int) -> list[str]:
    remaining = [item for item in PRODUCTS if item != product]
    offset = (scenario_index + instance * 2) % len(remaining)
    rotated = remaining[offset:] + remaining[:offset]
    return rotated[:2]


def _signals(kind: str, primary: str, count: int, offset: int) -> list[str]:
    pool = list(SIGNAL_POOLS[kind])
    ordered = [primary, *pool[offset % len(pool) :], *pool[: offset % len(pool)]]
    selected: list[str] = []
    source_states = {"source_permission_denied", "timeout_exhausted"}
    for signal in dict.fromkeys(ordered):
        if signal in source_states and any(item in source_states for item in selected):
            continue
        selected.append(signal)
        if len(selected) == count:
            break
    return selected


def _observations(
    *,
    case_key: str,
    task_kinds: list[str],
    canonical_order: list[str],
    presented: dict[str, str],
    signals: list[str],
) -> dict[str, Any]:
    prefix = "OBS-" + _hash_text(case_key)[:10]
    ids = {
        "aoi": f"{prefix}-aoi",
        "sources": f"{prefix}-sources",
        "output_fields": f"{prefix}-fields",
        "quality": f"{prefix}-quality",
        "evidence": f"{prefix}-evidence",
        "delivery": f"{prefix}-delivery",
        "algorithm_override": f"{prefix}-algorithm",
        "validator": f"{prefix}-validator",
        "candidate_plan": f"{prefix}-candidate",
        "priority": f"{prefix}-priority",
        "crosswalk": f"{prefix}-crosswalk",
    }
    obs: dict[str, Any] = {
        "observation_ids": ids,
        "aoi_candidates": [{"candidate_id": f"AOI-{_hash_text(case_key)[:8]}", "label": "heldout-admin-area"}],
        "selected_aoi_id": f"AOI-{_hash_text(case_key)[:8]}",
        "mission_priority": [presented[task] for task in canonical_order],
        "source_checks": {
            presented[task]: [{"source_id": PRODUCT_TRUTH[task]["source_ids"][0], "catalog_status": "available", "acquisition_status": "ready"}]
            for task in task_kinds
        },
        "proposed_output_fields": {presented[task]: list(PRODUCT_TRUTH[task]["required_fields"]) for task in task_kinds},
        "quality_measurements": {
            presented[task]: {"geometry_valid": True, "non_empty": True, "attribute_completeness": 1.0}
            for task in task_kinds
        },
        "available_evidence": {presented[task]: list(PRODUCT_TRUTH[task]["evidence_requirements"]) for task in task_kinds},
        "delivery_channel": {"channel_id": "delivery.primary", "status": "ready"},
        "required_algorithm_override": None,
        "validator_results": [],
        "candidate_plan": {
            "status": "proposed",
            "task_tokens": [presented[task] for task in canonical_order],
            "source_ids": [PRODUCT_TRUTH[task]["source_ids"][0] for task in task_kinds],
        },
    }
    product = task_kinds[0]
    token = presented[product]
    for signal in signals:
        if signal == "priority_conflict":
            obs["mission_priority"] = list(reversed(obs["mission_priority"]))
        elif signal == "candidate_poison":
            obs["candidate_plan"].update(status="rejected_by_catalog", source_ids=["catalog.external.unknown"])
        elif signal == "source_permission_denied":
            obs["source_checks"][token][0].update(acquisition_status="permission_denied", error_code="source_permission_denied")
        elif signal == "timeout_exhausted":
            obs["source_checks"][token][0].update(acquisition_status="timeout", error_code="acquisition_timeout", retry_count=4, retry_exhausted=True)
        elif signal == "required_field_missing":
            obs["proposed_output_fields"][token] = obs["proposed_output_fields"][token][1:]
        elif signal == "evidence_missing":
            obs["available_evidence"][token] = obs["available_evidence"][token][1:]
            obs["evidence_status"] = "incomplete"
        elif signal == "algorithm_incompatible":
            obs["required_algorithm_override"] = "algo.vendor.unregistered.v2"
            obs["algorithm_constraint"] = "registered_capability_required"
        elif signal == "quality_invalid":
            obs["quality_measurements"][token].update(geometry_valid=False, attribute_completeness=0.58)
            obs["quality_gate_status"] = "degraded_delivery_permitted"
        elif signal == "delivery_blocked":
            obs["delivery_channel"].update(status="blocked", error_code="primary_channel_unavailable")
        elif signal == "validator_blocked":
            obs["validator_results"] = [{"check_id": "contract_compatibility", "status": "blocked", "code": "non_overridable_contract_conflict"}]
        elif signal == "fallback_ready":
            obs["delivery_channel"].update(status="blocked", error_code="primary_channel_unavailable", fallback_channel="delivery.secondary", fallback_status="ready")
    return obs


def _oracle(
    *,
    task_kinds: list[str],
    canonical_order: list[str],
    product: str,
    observations: dict[str, Any],
    kind: str,
    signals: list[str],
) -> dict[str, Any]:
    decision_by_kind = {
        "plan": ("plan", "planned", ["plan"], ["planned"], []),
        "gap": ("gap", "gap", ["gap", "reject", "manual_intervention"], ["gap", "rejected", "pending"], ["reject"]),
        "degraded": ("degraded", "provisional", ["degraded", "gap", "manual_intervention"], ["provisional", "degraded", "gap", "pending"], []),
        "manual": ("manual_intervention", "pending", ["manual_intervention", "partial", "gap"], ["pending", "provisional", "gap"], []),
        "hard_veto": ("reject", "rejected", ["reject"], [], ["reject"]),
        "partial": ("partial", "provisional", ["partial", "gap", "manual_intervention"], ["provisional", "gap", "pending"], []),
    }
    decision, state, allowed_decisions, allowed_states, allow_empty = decision_by_kind[kind]
    anchor_key = {
        "priority_conflict": "priority",
        "alias_tokens": "crosswalk",
        "candidate_poison": "candidate_plan",
        "source_permission_denied": "sources",
        "timeout_exhausted": "sources",
        "required_field_missing": "output_fields",
        "evidence_missing": "evidence",
        "algorithm_incompatible": "algorithm_override",
        "quality_invalid": "quality",
        "delivery_blocked": "delivery",
        "validator_blocked": "validator",
        "fallback_ready": "delivery",
    }
    anchors = list(dict.fromkeys(observations["observation_ids"][anchor_key[signal]] for signal in signals))
    return {
        "decision": decision,
        "tasks": [] if kind == "hard_veto" else canonical_order,
        "states": {task: (state if task == product else "planned") for task in canonical_order},
        "hard_veto": "heldout_non_overridable_contract_veto" if kind == "hard_veto" else None,
        "acceptance": {
            "allowed_decisions": allowed_decisions,
            "allowed_product_states": allowed_states,
            "allow_empty_tasks_on": allow_empty,
        },
        "ground_truth": {
            "task_kinds": task_kinds,
            "canonical_order": canonical_order,
            "products": {task: deepcopy(PRODUCT_TRUTH[task]) for task in task_kinds},
            "evidence_anchor": anchors[0] if anchors else None,
            "evidence_anchors": anchors,
        },
    }


def build_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for scenario_index, (scenario, kind, primary_signal) in enumerate(SCENARIOS):
        for product_index, product in enumerate(PRODUCTS):
            for instance in range(2):
                pair_key = f"heldout.{scenario}.{product}.i{instance + 1}"
                task_kinds = [product, *_companions(product, scenario_index, instance)]
                canonical_order = sorted(task_kinds, key=PRIORITY.__getitem__)
                complexity = 1 + ((scenario_index * len(PRODUCTS) * 2 + product_index * 2 + instance) % 3)
                signals = _signals(kind, primary_signal, complexity, scenario_index + product_index + instance)
                for variant, is_fault in (("base", False), ("fault", True)):
                    active_signals = signals if is_fault else []
                    presented = {task: task for task in task_kinds}
                    if "alias_tokens" in active_signals:
                        presented = {task: ALIASES[task] for task in task_kinds}
                    request_order = list(canonical_order)
                    if "priority_conflict" in active_signals:
                        request_order = list(reversed(request_order))
                    case_key = f"{pair_key}.{variant}"
                    observations = _observations(
                        case_key=case_key,
                        task_kinds=task_kinds,
                        canonical_order=canonical_order,
                        presented=presented,
                        signals=active_signals,
                    )
                    request_id = "REQ-" + _hash_text(f"heldout-confirmatory-v1:{case_key}")[:16]
                    wording = (
                        f"Prepare an emergency vector package for {', '.join(presented[task] for task in request_order)} in the named administrative area."
                        if instance == 0
                        else f"Coordinate time-critical delivery of {', '.join(presented[task] for task in request_order)} for the incident area."
                    )
                    oracle_kind = kind if is_fault else "plan"
                    cases.append(
                        {
                            "case_id": case_key,
                            "pair_id": pair_key,
                            "family": scenario,
                            "variant": variant,
                            "is_fault": is_fault,
                            "product": product,
                            "task_kinds": task_kinds,
                            "presented_tokens": presented,
                            "request": {
                                "request_id": request_id,
                                "text": wording,
                                "disaster_type": "flood" if product in {"water_polygon", "waterways"} else "earthquake",
                                "aoi": {"kind": "named_admin_area", "value": "heldout-admin-area"},
                                "products": [presented[task] for task in request_order],
                                "delivery_intent": "emergency_vector_delivery",
                                "operator_note": "Preserve provenance and do not silently replace unavailable inputs.",
                            },
                            "observations": observations,
                            "oracle": _oracle(
                                task_kinds=task_kinds,
                                canonical_order=canonical_order,
                                product=product,
                                observations=observations,
                                kind=oracle_kind,
                                signals=active_signals,
                            ),
                            "evaluation_profile": PROFILE,
                            "perturbation_tags": [
                                "independent_heldout",
                                f"constraint_count_{len(active_signals)}" if is_fault else "clean_base",
                                *active_signals,
                            ],
                            "design_metadata": {
                                "authoring_instance": instance + 1,
                                "constraint_count": len(active_signals),
                                "fault_signals": active_signals,
                                "oracle_kind": oracle_kind,
                            },
                        }
                    )
    return cases


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("experiments/heldout_confirmatory_v1"))
    args = parser.parse_args()
    cases = build_cases()
    case_bytes = (json.dumps(cases, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    cases_path = args.output_dir / "cases.json"
    cases_path.parent.mkdir(parents=True, exist_ok=True)
    cases_path.write_bytes(case_bytes)
    faults = [case for case in cases if case["is_fault"]]
    manifest = {
        "dataset_id": "fusionagent.heldout-confirmatory.v1",
        "evaluation_profile": PROFILE,
        "authoring_date": "2026-09-05",
        "authoring_method": "independent_declarative_fixture",
        "runner_oracle_generation_reused": False,
        "case_file_sha256": hashlib.sha256(case_bytes).hexdigest(),
        "case_count": len(cases),
        "pair_count": len({case["pair_id"] for case in cases}),
        "scenario_count": len({case["family"] for case in cases}),
        "products": list(PRODUCTS),
        "instances_per_scenario_product": 2,
        "constraint_count_distribution": dict(sorted(Counter(case["design_metadata"]["constraint_count"] for case in faults).items())),
        "fault_labels_excluded_from_planning_input": True,
        "oracle_frozen_before_live_run": True,
    }
    _write_json(args.output_dir / "manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
