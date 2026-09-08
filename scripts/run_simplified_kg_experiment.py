"""Run the compact KG + LLM comparison requested for the research reset.

The default local mode is a deterministic harness smoke test.  It exercises the
same case generation, context projection, oracle and reporting paths without
claiming that it is evidence about a live LLM.  ``--mode live`` makes the LLM
conditions call the configured OpenAI-compatible provider and records the raw
provider attempt for every call.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import random
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kg.inmemory_repository import InMemoryKGRepository
from kg.knowledge_release import semantic_hash, sha256_file
from kg.policy_registry import KnowledgePolicyRegistry
from llm.providers.openai_compatible import OpenAICompatibleProvider
from schemas.research_llm_pilot import ResearchPlanningDecision
from utils.local_runtime import read_dotenv_defaults


PRODUCTS = ("building", "road", "water_polygon", "waterways", "poi")
PRIMARY_METHODS = ("llm_only", "llm_capability_kg", "llm_full_contract_kg", "rules_only", "fixed_workflow")
ABLATIONS = ("without_ontology_identity_crosswalk", "without_capability_algorithm_grounding", "without_contract_quality_delivery_policy")
ALL_METHODS = (*PRIMARY_METHODS, *ABLATIONS)
LABELED_EXACT_PROFILE = "labeled_exact_v1"
OBSERVABLE_INVARIANT_PROFILE = "observable_invariant_v2"
OBSERVABLE_INVARIANT_V3_PROFILE = "observable_invariant_v3"
COMPLEX_PROFILE = "observable_complex_v1"
ADVERSARIAL_PROFILE = "adversarial_baseline_v1"
HELDOUT_CONFIRMATORY_PROFILE = "heldout_confirmatory_v1"
V3_LIKE_PROFILES = {
    OBSERVABLE_INVARIANT_V3_PROFILE,
    COMPLEX_PROFILE,
    ADVERSARIAL_PROFILE,
    HELDOUT_CONFIRMATORY_PROFILE,
}
EXPERIMENT_PROFILES = (
    LABELED_EXACT_PROFILE,
    OBSERVABLE_INVARIANT_PROFILE,
    OBSERVABLE_INVARIANT_V3_PROFILE,
    COMPLEX_PROFILE,
    ADVERSARIAL_PROFILE,
    HELDOUT_CONFIRMATORY_PROFILE,
)
FAMILIES = (
    "aoi_determination",
    "source_availability",
    "contract_requiredness",
    "cross_task_precedence",
    "kg_crosswalk",
    "plan_validity",
    "algorithm_capability",
    "vector_acquisition_failure",
    "validator_veto",
    "quality_gate",
    "evidence_completeness",
    "delivery_state",
)
LIVE_SYSTEM_PROMPT = """You are a geospatial planning system.
Return exactly one JSON object matching the supplied output_schema. Use only
the request, observations, and KG context supplied. Never invent source IDs or
algorithm IDs. When an observed constraint prevents unrestricted delivery,
choose reject, partial, gap, degraded, or manual_intervention and state the
appropriate per-product delivery state.
"""
V3_SYSTEM_PROMPT = """You are a geospatial planning system.
Return exactly one JSON object matching the supplied output_schema. Use only
the request, raw observations, and KG modules supplied. Emit canonical task
kinds. Use only source IDs whose catalog and acquisition states are usable.
Algorithm IDs in the shared tool_catalog are available to every method; when
capability grounding is present, its task-to-algorithm compatibility is
authoritative. A plan decision is allowed only when AOI, source, algorithm,
contract, quality, evidence, and delivery constraints permit unrestricted
delivery. Otherwise choose a safe constrained
decision and cite exact input IDs, field names, check IDs, or error codes in
evidence or uncertainties. Prefer the supplied observation_ids for traceable
evidence. When the ontology module supplies canonical_precedence, use it to
resolve task order instead of trusting a conflicting request order or noisy
mission-priority observation. Never copy an invalid candidate plan reference.
"""


def generate_cases(*, profile: str = LABELED_EXACT_PROFILE) -> list[dict[str, Any]]:
    """Generate 24 base cases and their 24 matched failure members."""
    if profile not in EXPERIMENT_PROFILES:
        raise ValueError(f"Unknown experiment profile: {profile}")
    if profile == HELDOUT_CONFIRMATORY_PROFILE:
        raise ValueError("heldout_confirmatory_v1 requires a frozen --case-file")
    if profile == OBSERVABLE_INVARIANT_V3_PROFILE:
        return _generate_v3_cases()
    if profile == COMPLEX_PROFILE:
        return _generate_complex_cases()
    if profile == ADVERSARIAL_PROFILE:
        return _generate_adversarial_cases()
    cases: list[dict[str, Any]] = []
    for index, family in enumerate(FAMILIES):
        # Two product slices per family yield 24 base cases without new families.
        for slice_index in range(2):
            product = PRODUCTS[(index + slice_index) % len(PRODUCTS)]
            companions = _companions(product, family)
            for variant, is_fault in (("base", False), ("fault", True)):
                case_id = f"{family}.{product}.s{slice_index + 1}.{variant}"
                task_kinds = [product, *companions]
                fault = family if is_fault else None
                cases.append(
                    {
                        "case_id": case_id,
                        "pair_id": f"{family}.{product}.s{slice_index + 1}",
                        "family": family,
                        "variant": variant,
                        "is_fault": is_fault,
                        "product": product,
                        "task_kinds": task_kinds,
                        "request": {
                            "request_id": case_id,
                            "disaster_type": "flood" if product in {"water_polygon", "waterways"} else "earthquake",
                            "aoi": {"kind": "named_admin_area", "value": "controlled-aoi"},
                            "products": task_kinds,
                            "delivery_intent": "emergency_vector_delivery",
                        },
                        "observations": _observations(
                            product,
                            companions,
                            fault,
                            expose_fault_label=profile == LABELED_EXACT_PROFILE,
                        ),
                        "oracle": _oracle(product, companions, fault, profile=profile),
                        "evaluation_profile": profile,
                    }
                )
    return cases


def load_frozen_cases(case_file: Path, *, expected_profile: str) -> list[dict[str, Any]]:
    payload = json.loads(Path(case_file).read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("Frozen case file must contain a non-empty JSON array")
    cases = [dict(case) for case in payload]
    case_ids = [str(case.get("case_id")) for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("Frozen case file contains duplicate case_id values")
    if {case.get("evaluation_profile") for case in cases} != {expected_profile}:
        raise ValueError("Frozen cases do not match the selected evaluation profile")
    pairs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        pairs[str(case.get("pair_id"))].append(case)
        if {"request", "observations", "oracle"} - set(case):
            raise ValueError(f"Frozen case {case.get('case_id')} is incomplete")
    for pair_id, members in pairs.items():
        if len(members) != 2 or {member.get("variant") for member in members} != {"base", "fault"}:
            raise ValueError(f"Frozen pair {pair_id} must contain one base and one fault member")
    return cases


V3_CROSSWALK_ALIASES = {
    "building": "buildings",
    "road": "roads",
    "water_polygon": "lakes",
    "waterways": "rivers",
    "poi": "hospitals",
}
V3_MISSION_PRIORITY = {"water_polygon": 0, "waterways": 1, "road": 2, "building": 3, "poi": 4}


def _generate_v3_cases() -> list[dict[str, Any]]:
    repo = InMemoryKGRepository(experience_policy="pinned_snapshot")
    registry = KnowledgePolicyRegistry()
    cases: list[dict[str, Any]] = []
    for family_index, family in enumerate(FAMILIES):
        for slice_index in range(2):
            product = PRODUCTS[(family_index * 2 + slice_index) % len(PRODUCTS)]
            companions = _companions(product, family)
            task_kinds = [product, *companions]
            disaster_type = "flood" if product in {"water_polygon", "waterways"} else "earthquake"
            grounding = {
                task: _v3_product_grounding(repo, registry, task, disaster_type)
                for task in task_kinds
            }
            for variant, is_fault in (("base", False), ("fault", True)):
                presented = {task: task for task in task_kinds}
                if is_fault and family == "kg_crosswalk":
                    presented[product] = V3_CROSSWALK_ALIASES[product]
                canonical_order = sorted(task_kinds, key=lambda task: V3_MISSION_PRIORITY[task])
                request_order = list(task_kinds)
                if is_fault and family == "cross_task_precedence":
                    request_order = list(reversed(canonical_order))
                request_tokens = [presented[task] for task in request_order]
                priority_tokens = [presented[task] for task in canonical_order]
                case_id = f"{family}.{product}.s{slice_index + 1}.{variant}"
                observations = _v3_observations(
                    product=product,
                    task_kinds=task_kinds,
                    presented=presented,
                    priority_tokens=priority_tokens,
                    grounding=grounding,
                    family=family,
                    is_fault=is_fault,
                )
                request_text = (
                    f"Prepare {', '.join(request_tokens)} for the emergency AOI."
                    if slice_index == 0
                    else f"Need an emergency delivery covering {', '.join(request_tokens)} in the named area."
                )
                request_id = "REQ-" + semantic_hash("observable-invariant-v3-request", case_id).split(":", 1)[1][:16]
                request = {
                    "request_id": request_id,
                    "text": request_text,
                    "disaster_type": disaster_type,
                    "aoi": {"kind": "named_admin_area", "value": "controlled-aoi"},
                    "products": request_tokens,
                    "delivery_intent": "emergency_vector_delivery",
                }
                if slice_index == 1:
                    request["operator_note"] = "Archive the coordination ticket after review."
                cases.append(
                    {
                        "case_id": case_id,
                        "pair_id": f"{family}.{product}.s{slice_index + 1}",
                        "family": family,
                        "variant": variant,
                        "is_fault": is_fault,
                        "product": product,
                        "task_kinds": task_kinds,
                        "request": request,
                        "observations": observations,
                        "oracle": _v3_oracle(
                            product=product,
                            task_kinds=task_kinds,
                            canonical_order=canonical_order,
                            grounding=grounding,
                            observations=observations,
                            family=family,
                            is_fault=is_fault,
                        ),
                        "evaluation_profile": OBSERVABLE_INVARIANT_V3_PROFILE,
                        "perturbation_tags": [
                            f"wording_{slice_index + 1}",
                            "request_order_reversed" if is_fault and family == "cross_task_precedence" else "request_order_canonical",
                            "operator_note_present" if slice_index == 1 else "no_irrelevant_noise",
                        ],
                    }
                )
    return cases


def _generate_complex_cases() -> list[dict[str, Any]]:
    repo = InMemoryKGRepository(experience_policy="pinned_snapshot")
    registry = KnowledgePolicyRegistry()
    specs = [
        ("multi_source_quality", "water_polygon", ["waterways", "building"], "vector_acquisition_failure", {"timeout_product", "quality_invalid"}),
        ("alias_precedence", "road", ["building", "poi"], "kg_crosswalk", {"alias_product", "reverse_order"}),
        ("contract_evidence", "building", ["road"], "contract_requiredness", {"missing_field", "missing_evidence"}),
        ("algorithm_acquisition", "poi", ["building", "road"], "algorithm_capability", {"algorithm_override", "timeout_product"}),
        ("veto_delivery", "waterways", ["water_polygon", "road"], "validator_veto", {"validator_veto", "delivery_blocked"}),
        ("aoi_source", "water_polygon", ["waterways", "poi"], "aoi_determination", {"aoi_ambiguous", "source_unavailable"}),
    ]
    cases: list[dict[str, Any]] = []
    for index, (name, product, companions, oracle_family, faults) in enumerate(specs, start=1):
        task_kinds = [product, *companions]
        disaster_type = "flood" if product in {"water_polygon", "waterways"} else "earthquake"
        grounding = {
            task: _v3_product_grounding(repo, registry, task, disaster_type)
            for task in task_kinds
        }
        canonical_order = sorted(task_kinds, key=lambda task: V3_MISSION_PRIORITY[task])
        for variant, is_fault in (("base", False), ("fault", True)):
            presented = {task: task for task in task_kinds}
            request_order = list(canonical_order)
            if is_fault and "alias_product" in faults:
                presented[product] = V3_CROSSWALK_ALIASES[product]
            if is_fault and "reverse_order" in faults:
                request_order = list(reversed(canonical_order))
            request_tokens = [presented[task] for task in request_order]
            priority_tokens = [presented[task] for task in canonical_order]
            observations = _v3_observations(
                product=product,
                task_kinds=task_kinds,
                presented=presented,
                priority_tokens=priority_tokens,
                grounding=grounding,
                family=oracle_family,
                is_fault=False,
            )
            if is_fault:
                _apply_complex_faults(observations, product=product, presented=presented, grounding=grounding, faults=faults)
            case_id = f"complex.{name}.s{index}.{variant}"
            request_id = "REQ-" + semantic_hash("observable-complex-v1-request", case_id).split(":", 1)[1][:16]
            request = {
                "request_id": request_id,
                "text": f"Coordinate a difficult emergency delivery covering {', '.join(request_tokens)}.",
                "disaster_type": disaster_type,
                "aoi": {"kind": "named_admin_area", "value": "controlled-aoi"},
                "products": request_tokens,
                "delivery_intent": "emergency_vector_delivery",
                "operator_note": "Prioritize the incident ticket over routine reporting.",
            }
            cases.append(
                {
                    "case_id": case_id,
                    "pair_id": f"complex.{name}.s{index}",
                    "family": oracle_family,
                    "variant": variant,
                    "is_fault": is_fault,
                    "product": product,
                    "task_kinds": task_kinds,
                    "request": request,
                    "observations": observations,
                    "oracle": _v3_oracle(
                        product=product,
                        task_kinds=task_kinds,
                        canonical_order=canonical_order,
                        grounding=grounding,
                        observations=observations,
                        family=oracle_family,
                        is_fault=is_fault,
                    ),
                    "evaluation_profile": COMPLEX_PROFILE,
                    "perturbation_tags": [
                        "multi_constraint_fault" if is_fault else "complex_base",
                        *(sorted(faults) if is_fault else []),
                    ],
                }
            )
    return cases


ADVERSARIAL_SCENARIOS = (
    ("priority_conflict", "plan"),
    ("mixed_alias_crosswalk", "plan"),
    ("partial_source_outage", "gap"),
    ("timeout_exhausted", "gap"),
    ("quality_provisional", "degraded"),
    ("required_field_missing", "gap"),
    ("evidence_partial", "manual"),
    ("algorithm_incompatible", "gap"),
    ("delivery_blocked", "gap"),
    ("nonexplicit_veto", "hard_veto"),
    ("candidate_plan_contradiction", "plan"),
    ("partial_delivery_fallback", "gap"),
)


def _generate_adversarial_cases() -> list[dict[str, Any]]:
    """Generate a broad, repeated profile aimed at fixed-baseline blind spots."""
    repo = InMemoryKGRepository(experience_policy="pinned_snapshot")
    registry = KnowledgePolicyRegistry()
    cases: list[dict[str, Any]] = []
    for scenario_index, (scenario, oracle_kind) in enumerate(ADVERSARIAL_SCENARIOS):
        for repetition in range(5):
            product = PRODUCTS[(scenario_index + repetition) % len(PRODUCTS)]
            companions = _adversarial_companions(product, scenario_index, repetition)
            task_kinds = [product, *companions]
            disaster_type = "flood" if product in {"water_polygon", "waterways"} else "earthquake"
            grounding = {
                task: _v3_product_grounding(repo, registry, task, disaster_type)
                for task in task_kinds
            }
            canonical_order = sorted(task_kinds, key=lambda task: V3_MISSION_PRIORITY[task])
            for variant, is_fault in (("base", False), ("fault", True)):
                presented = {task: task for task in task_kinds}
                request_order = list(canonical_order)
                priority_tokens = list(canonical_order)
                if is_fault:
                    if scenario == "mixed_alias_crosswalk":
                        presented = {
                            task: V3_CROSSWALK_ALIASES[task]
                            for task in task_kinds
                        }
                        request_order = list(reversed(canonical_order))
                        priority_tokens = [presented[task] for task in canonical_order]
                    elif scenario in {
                        "priority_conflict",
                        "candidate_plan_contradiction",
                    }:
                        request_order = list(reversed(canonical_order))
                        if scenario == "priority_conflict":
                            priority_tokens = _rotate(canonical_order, repetition + 1)
                    elif repetition % 2:
                        request_order = _rotate(canonical_order, 1)
                observations = _v3_observations(
                    product=product,
                    task_kinds=task_kinds,
                    presented=presented,
                    priority_tokens=[presented[task] for task in priority_tokens]
                    if priority_tokens and set(priority_tokens) <= set(task_kinds)
                    else priority_tokens,
                    grounding=grounding,
                    family="source_availability",
                    is_fault=False,
                )
                if is_fault:
                    _apply_adversarial_fault(
                        observations,
                        product=product,
                        presented=presented,
                        grounding=grounding,
                        scenario=scenario,
                        repetition=repetition,
                    )
                request_tokens = [presented[task] for task in request_order]
                priority_observation = observations.get("mission_priority", [])
                case_id = f"adversarial.{scenario}.r{repetition + 1}.{variant}"
                request_id = "REQ-" + semantic_hash(
                    "adversarial-baseline-v1-request", case_id
                ).split(":", 1)[1][:16]
                wording = (
                    f"Coordinate an emergency delivery for {', '.join(request_tokens)}."
                    if repetition % 2 == 0
                    else f"Prepare a time-critical package covering {', '.join(request_tokens)}."
                )
                request = {
                    "request_id": request_id,
                    "text": wording,
                    "disaster_type": disaster_type,
                    "aoi": {"kind": "named_admin_area", "value": "controlled-aoi"},
                    "products": request_tokens,
                    "delivery_intent": "emergency_vector_delivery",
                    "operator_note": (
                        "The incident commander needs a traceable result before routine reporting."
                        if repetition % 2
                        else "Do not silently substitute an unregistered source or algorithm."
                    ),
                }
                effective_oracle_kind = oracle_kind if is_fault else "plan"
                family = _adversarial_oracle_family(effective_oracle_kind)
                oracle = _adversarial_oracle(
                    product=product,
                    task_kinds=task_kinds,
                    canonical_order=canonical_order,
                    grounding=grounding,
                    observations=observations,
                    oracle_kind=effective_oracle_kind,
                    family=family,
                )
                cases.append(
                    {
                        "case_id": case_id,
                        "pair_id": f"adversarial.{scenario}.r{repetition + 1}",
                        "family": scenario,
                        "variant": variant,
                        "is_fault": is_fault,
                        "product": product,
                        "task_kinds": task_kinds,
                        "request": request,
                        "observations": observations,
                        "oracle": oracle,
                        "evaluation_profile": ADVERSARIAL_PROFILE,
                        "perturbation_tags": [
                            "baseline_adversarial",
                            scenario,
                            f"repetition_{repetition + 1}",
                            "fault" if is_fault else "clean_base",
                            "request_order_reversed"
                            if is_fault and request_order != canonical_order
                            else "request_order_canonical",
                            "operator_noise_even"
                            if repetition % 2 == 0
                            else "operator_noise_odd",
                        ],
                    }
                )
    return cases


def _rotate(values: list[str], offset: int) -> list[str]:
    if not values:
        return []
    offset %= len(values)
    return values[offset:] + values[:offset]


def _adversarial_companions(product: str, scenario_index: int, repetition: int) -> list[str]:
    remaining = [item for item in PRODUCTS if item != product]
    offset = (scenario_index + repetition) % len(remaining)
    rotated = remaining[offset:] + remaining[:offset]
    return [rotated[0], rotated[1]]


def _apply_adversarial_fault(
    observations: dict[str, Any],
    *,
    product: str,
    presented: dict[str, str],
    grounding: dict[str, dict[str, Any]],
    scenario: str,
    repetition: int,
) -> None:
    token = presented[product]
    if scenario == "priority_conflict":
        observations["mission_priority"] = (
            [] if repetition == 4 else list(reversed(observations["mission_priority"]))
        )
        observations["candidate_plan"]["task_tokens"] = list(
            reversed(observations["candidate_plan"]["task_tokens"])
        )
    elif scenario == "mixed_alias_crosswalk":
        observations["candidate_plan"]["task_tokens"] = list(
            observations["mission_priority"]
        )
    elif scenario in {"partial_source_outage", "timeout_exhausted"}:
        checks = observations["source_checks"].get(token, [])
        if checks:
            checks[0]["acquisition_status"] = (
                "permission_denied" if scenario == "partial_source_outage" else "timeout"
            )
            checks[0]["error_code"] = (
                "source_permission_denied"
                if scenario == "partial_source_outage"
                else "acquisition_timeout"
            )
            checks[0]["retry_count"] = 3 if scenario == "timeout_exhausted" else 0
            checks[0]["retry_exhausted"] = scenario == "timeout_exhausted"
    elif scenario == "quality_provisional":
        observations["quality_measurements"][token].update(
            {"geometry_valid": False, "non_empty": True, "attribute_completeness": 0.62}
        )
        observations["quality_gate_status"] = "degraded_allowed"
    elif scenario == "required_field_missing":
        required = grounding[product]["required_fields"][0]
        observations["proposed_output_fields"][token] = [
            field
            for field in observations["proposed_output_fields"][token]
            if field != required
        ]
    elif scenario == "evidence_partial":
        required = grounding[product]["evidence_requirements"][0]
        observations["available_evidence"][token] = [
            item
            for item in observations["available_evidence"][token]
            if item != required
        ]
        observations["evidence_status"] = "incomplete"
    elif scenario == "algorithm_incompatible":
        observations["required_algorithm_override"] = "algo.external.unregistered.v1"
        observations["algorithm_constraint"] = "registered_capability_required"
    elif scenario == "delivery_blocked":
        observations["delivery_channel"].update(
            {"status": "blocked", "error_code": "primary_channel_unavailable"}
        )
    elif scenario == "nonexplicit_veto":
        observations["validator_results"] = [
            {
                "check_id": "contract_compatibility",
                "status": "blocked",
                "code": "contract_conflict",
            }
        ]
        observations["delivery_channel"]["status"] = "blocked"
    elif scenario == "candidate_plan_contradiction":
        observations["candidate_plan"].update(
            {
                "source_ids": ["catalog.invalid.unregistered"],
                "status": "candidate_rejected",
            }
        )
    elif scenario == "partial_delivery_fallback":
        observations["delivery_channel"].update(
            {
                "status": "blocked",
                "fallback_channel": "delivery.secondary",
                "fallback_status": "ready",
            }
        )


def _adversarial_oracle_family(oracle_kind: str) -> str:
    return {
        "plan": "cross_task_precedence",
        "gap": "source_availability",
        "degraded": "quality_gate",
        "manual": "evidence_completeness",
        "hard_veto": "validator_veto",
    }[oracle_kind]


def _adversarial_oracle(
    *,
    product: str,
    task_kinds: list[str],
    canonical_order: list[str],
    grounding: dict[str, dict[str, Any]],
    observations: dict[str, Any],
    oracle_kind: str,
    family: str,
) -> dict[str, Any]:
    oracle = _v3_oracle(
        product=product,
        task_kinds=task_kinds,
        canonical_order=canonical_order,
        grounding=grounding,
        observations=observations,
        family=family,
        is_fault=oracle_kind != "plan",
    )
    if oracle_kind == "hard_veto":
        oracle["hard_veto"] = "nonexplicit_contract_veto"
    return oracle


def _apply_complex_faults(
    observations: dict[str, Any],
    *,
    product: str,
    presented: dict[str, str],
    grounding: dict[str, dict[str, Any]],
    faults: set[str],
) -> None:
    token = presented[product]
    if "timeout_product" in faults:
        observations["source_checks"][token][0]["acquisition_status"] = "timeout"
        observations["source_checks"][token][0]["error_code"] = "acquisition_timeout"
    if "quality_invalid" in faults:
        observations["quality_measurements"][token]["geometry_valid"] = False
    if "alias_product" in faults:
        pass
    if "missing_field" in faults:
        missing_field = grounding[product]["required_fields"][0]
        observations["proposed_output_fields"][token] = [
            field for field in observations["proposed_output_fields"][token] if field != missing_field
        ]
    if "missing_evidence" in faults:
        missing_evidence = grounding[product]["evidence_requirements"][0]
        observations["available_evidence"][token] = [
            item for item in observations["available_evidence"][token] if item != missing_evidence
        ]
    if "algorithm_override" in faults:
        observations["required_algorithm_override"] = "algo.external.unregistered.v1"
    if "validator_veto" in faults:
        observations["validator_results"] = [
            {"check_id": "contract_compatibility", "status": "fail", "code": "contract_conflict"}
        ]
    if "delivery_blocked" in faults:
        observations["delivery_channel"]["status"] = "blocked"
    if "aoi_ambiguous" in faults:
        observations["aoi_candidates"].append({"candidate_id": "AOI-002", "label": "controlled-aoi district"})
        observations["selected_aoi_id"] = None
    if "source_unavailable" in faults:
        observations["source_checks"][token] = []


def _v3_product_grounding(
    repo: InMemoryKGRepository,
    registry: KnowledgePolicyRegistry,
    product: str,
    disaster_type: str,
) -> dict[str, Any]:
    task_record = registry.task_record(product)
    output_type = str(task_record["output_data_type"])
    patterns = repo.get_candidate_patterns(_job_type(product), disaster_type, limit=20)
    preferred_pattern_id = task_record.get("preferred_pattern_id")
    matching_patterns = [
        pattern
        for pattern in patterns
        if any(step.output_data_type == output_type for step in pattern.steps)
    ]
    matching_patterns.sort(key=lambda item: (item.pattern_id != preferred_pattern_id, item.pattern_id))
    steps = [
        step
        for pattern in matching_patterns
        for step in pattern.steps
        if step.output_data_type == output_type
    ]
    if not steps:
        raise RuntimeError(f"No frozen KG pattern step for product={product!r}, disaster={disaster_type!r}")
    algorithm_ids = sorted({step.algorithm_id for step in steps})
    source_ids = sorted({step.data_source_id for step in steps})
    known_algorithms = {algorithm.algo_id for algorithm in repo.list_algorithms()}
    known_sources = {source.source_id for source in repo.list_data_sources()}
    if not set(algorithm_ids) <= known_algorithms or not set(source_ids) <= known_sources:
        raise RuntimeError(f"Pattern grounding for {product!r} references missing KG entities")
    contract_id = f"contract.product.{product}.v1"
    contract = repo.product_contracts.get(contract_id)
    if contract is None:
        raise RuntimeError(f"Missing frozen product contract: {contract_id}")
    requirement_by_id = {
        requirement.requirement_id: requirement
        for requirement in repo.list_output_requirements()
    }
    requirements = [requirement_by_id[item] for item in contract.output_requirement_ids]
    if len(requirements) != 1:
        raise RuntimeError(f"Expected one output requirement for {contract_id}, found {len(requirements)}")
    return {
        "task_kind": product,
        "task_id": str(task_record["task_id"]),
        "output_type": output_type,
        "pattern_ids": [pattern.pattern_id for pattern in matching_patterns],
        "algorithm_ids": algorithm_ids,
        "source_ids": source_ids,
        "contract_id": contract.contract_id,
        "required_fields": list(requirements[0].required_fields),
        "output_requirement_id": requirements[0].requirement_id,
        "quality_gates": list(contract.quality_gates),
        "evidence_requirements": list(contract.evidence_requirements),
        "qos_policy_ids": list(contract.qos_policy_ids),
    }


def _v3_observations(
    *,
    product: str,
    task_kinds: list[str],
    presented: dict[str, str],
    priority_tokens: list[str],
    grounding: dict[str, dict[str, Any]],
    family: str,
    is_fault: bool,
) -> dict[str, Any]:
    observations: dict[str, Any] = {
        "observation_ids": {
            "aoi": "obs.aoi_resolution",
            "sources": "obs.source_checks",
            "output_fields": "obs.output_fields",
            "quality": "obs.quality_measurements",
            "evidence": "obs.available_evidence",
            "delivery": "obs.delivery_channel",
            "algorithm_override": "obs.algorithm_override",
            "validator": "obs.validator_results",
            "candidate_plan": "obs.candidate_plan",
        },
        "aoi_candidates": [{"candidate_id": "AOI-001", "label": "controlled-aoi"}],
        "selected_aoi_id": "AOI-001",
        "mission_priority": priority_tokens,
        "source_checks": {
            presented[task]: [
                {
                    "source_id": grounding[task]["source_ids"][0],
                    "catalog_status": "available",
                    "acquisition_status": "ready",
                }
            ]
            for task in task_kinds
        },
        "proposed_output_fields": {
            presented[task]: list(grounding[task]["required_fields"])
            for task in task_kinds
        },
        "quality_measurements": {
            presented[task]: {
                "geometry_valid": True,
                "non_empty": True,
                "attribute_completeness": 1.0,
            }
            for task in task_kinds
        },
        "available_evidence": {
            presented[task]: list(grounding[task]["evidence_requirements"])
            for task in task_kinds
        },
        "delivery_channel": {"channel_id": "delivery.primary", "status": "ready"},
        "required_algorithm_override": None,
        "validator_results": [],
        "candidate_plan": {
            "task_tokens": list(priority_tokens),
            "source_ids": [grounding[task]["source_ids"][0] for task in task_kinds],
        },
    }
    if not is_fault:
        return observations
    token = presented[product]
    if family == "aoi_determination":
        observations["aoi_candidates"].append({"candidate_id": "AOI-002", "label": "controlled-aoi district"})
        observations["selected_aoi_id"] = None
    elif family == "source_availability":
        observations["source_checks"][token] = []
    elif family == "contract_requiredness":
        missing_field = grounding[product]["required_fields"][0]
        observations["proposed_output_fields"][token] = [
            field for field in observations["proposed_output_fields"][token] if field != missing_field
        ]
    elif family == "plan_validity":
        observations["candidate_plan"]["source_ids"] = ["catalog.invalid.unregistered"]
    elif family == "algorithm_capability":
        observations["required_algorithm_override"] = "algo.external.unregistered.v1"
    elif family == "vector_acquisition_failure":
        observations["source_checks"][token][0]["acquisition_status"] = "timeout"
        observations["source_checks"][token][0]["error_code"] = "acquisition_timeout"
    elif family == "validator_veto":
        observations["validator_results"] = [
            {"check_id": "contract_compatibility", "status": "fail", "code": "contract_conflict"}
        ]
    elif family == "quality_gate":
        observations["quality_measurements"][token]["geometry_valid"] = False
    elif family == "evidence_completeness":
        missing_evidence = grounding[product]["evidence_requirements"][0]
        observations["available_evidence"][token] = [
            item for item in observations["available_evidence"][token] if item != missing_evidence
        ]
    elif family == "delivery_state":
        observations["delivery_channel"]["status"] = "blocked"
    return observations


def _v3_oracle(
    *,
    product: str,
    task_kinds: list[str],
    canonical_order: list[str],
    grounding: dict[str, dict[str, Any]],
    observations: dict[str, Any],
    family: str,
    is_fault: bool,
) -> dict[str, Any]:
    decision = "plan"
    state = "planned"
    allowed_decisions = ["plan"]
    allowed_states = ["planned"]
    hard_veto = None
    allow_empty_tasks_on: list[str] = []
    evidence_anchor = None
    if is_fault and family in {"aoi_determination", "validator_veto"}:
        decision = "reject"
        state = "rejected"
        allowed_decisions = ["reject"]
        allowed_states = []
        hard_veto = family
        allow_empty_tasks_on = ["reject"]
        evidence_anchor = (
            observations["observation_ids"]["aoi"]
            if family == "aoi_determination"
            else observations["observation_ids"]["validator"]
        )
    elif is_fault and family in {
        "source_availability",
        "contract_requiredness",
        "algorithm_capability",
        "vector_acquisition_failure",
        "delivery_state",
    }:
        decision = "gap"
        state = "gap"
        allowed_decisions = ["gap", "reject", "manual_intervention"]
        allowed_states = ["gap", "rejected", "pending"]
        allow_empty_tasks_on = ["reject"]
        if family == "source_availability":
            evidence_anchor = observations["observation_ids"]["sources"]
        elif family == "contract_requiredness":
            evidence_anchor = observations["observation_ids"]["output_fields"]
        elif family == "algorithm_capability":
            evidence_anchor = observations["observation_ids"]["algorithm_override"]
        elif family == "vector_acquisition_failure":
            evidence_anchor = observations["observation_ids"]["sources"]
        else:
            evidence_anchor = observations["observation_ids"]["delivery"]
    elif is_fault and family == "quality_gate":
        decision = "degraded"
        state = "provisional"
        allowed_decisions = ["degraded", "gap", "manual_intervention"]
        allowed_states = ["provisional", "degraded", "gap", "pending"]
        evidence_anchor = observations["observation_ids"]["quality"]
    elif is_fault and family == "evidence_completeness":
        decision = "manual_intervention"
        state = "pending"
        allowed_decisions = ["manual_intervention", "partial", "gap"]
        allowed_states = ["pending", "provisional", "gap"]
        evidence_anchor = observations["observation_ids"]["evidence"]
    states = {task: (state if task == product else "planned") for task in canonical_order}
    expected_tasks = [] if decision == "reject" else canonical_order
    return {
        "decision": decision,
        "tasks": expected_tasks,
        "states": {} if decision == "reject" else states,
        "hard_veto": hard_veto,
        "acceptance": {
            "allowed_decisions": allowed_decisions,
            "allowed_product_states": allowed_states,
            "allow_empty_tasks_on": allow_empty_tasks_on,
        },
        "ground_truth": {
            "task_kinds": task_kinds,
            "canonical_order": canonical_order,
            "products": grounding,
            "evidence_anchor": evidence_anchor,
        },
    }


def run_experiment(
    output_dir: Path,
    *,
    mode: str = "local",
    case_limit: int | None = None,
    include_ablations: bool = True,
    profile: str = LABELED_EXACT_PROFILE,
    selected_methods: Iterable[str] | None = None,
    selected_pair_ids: Iterable[str] | None = None,
    invocation: list[str] | None = None,
    max_workers: int = 1,
    case_file: Path | None = None,
    llm_replicates: int = 1,
) -> dict[str, Any]:
    if mode not in {"local", "live"}:
        raise ValueError("mode must be 'local' or 'live'")
    if case_limit is not None and selected_pair_ids is not None:
        raise ValueError("case_limit and selected_pair_ids are mutually exclusive")
    if max_workers < 1:
        raise ValueError("max_workers must be positive")
    if llm_replicates < 1 or llm_replicates % 2 == 0:
        raise ValueError("llm_replicates must be a positive odd number")
    if profile == HELDOUT_CONFIRMATORY_PROFILE and case_file is None:
        raise ValueError("heldout_confirmatory_v1 requires case_file")
    if case_file is not None and profile != HELDOUT_CONFIRMATORY_PROFILE:
        raise ValueError("case_file is reserved for the heldout confirmatory profile")
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite experiment directory: {output_dir}")
    output_dir.mkdir(parents=True)
    cases = (
        load_frozen_cases(case_file, expected_profile=profile)
        if case_file is not None
        else generate_cases(profile=profile)
    )
    if selected_pair_ids is not None:
        requested_pairs = list(dict.fromkeys(selected_pair_ids))
        known_pairs = {case["pair_id"] for case in cases}
        unknown_pairs = sorted(set(requested_pairs) - known_pairs)
        if unknown_pairs:
            raise ValueError(f"Unknown pair IDs: {', '.join(unknown_pairs)}")
        cases = [case for case in cases if case["pair_id"] in requested_pairs]
        selected_counts = {
            pair_id: sum(case["pair_id"] == pair_id for case in cases)
            for pair_id in requested_pairs
        }
        if any(count != 2 for count in selected_counts.values()):
            raise ValueError("Every selected pair must contain exactly one base and one fault member")
    if case_limit is not None:
        if case_limit <= 0:
            raise ValueError("case_limit must be positive")
        cases = cases[:case_limit]
    if len(cases) % 2:
        raise ValueError("case selection must retain base/fault pairs")

    repo = InMemoryKGRepository(experience_policy="pinned_snapshot")
    if selected_methods is None:
        methods = list(PRIMARY_METHODS)
        if include_ablations:
            methods.extend(ABLATIONS)
    else:
        methods = list(dict.fromkeys(selected_methods))
        unknown = sorted(set(methods) - set(ALL_METHODS))
        if unknown:
            raise ValueError(f"Unknown methods: {', '.join(unknown)}")
        if not methods:
            raise ValueError("selected_methods must not be empty")
    has_llm_methods = any(method.startswith("llm_") or method.startswith("without_") for method in methods)
    provider = _live_provider() if mode == "live" and has_llm_methods else None
    manifest = {
        "experiment_id": {
            LABELED_EXACT_PROFILE: "fusionagent.simplified-kg-llm.v1",
            OBSERVABLE_INVARIANT_PROFILE: "fusionagent.simplified-kg-llm.observable-invariant.v2",
            OBSERVABLE_INVARIANT_V3_PROFILE: "fusionagent.simplified-kg-llm.observable-invariant.v3",
            COMPLEX_PROFILE: "fusionagent.simplified-kg-llm.observable-complex.v1",
            ADVERSARIAL_PROFILE: "fusionagent.simplified-kg-llm.adversarial-baseline.v1",
            HELDOUT_CONFIRMATORY_PROFILE: "fusionagent.simplified-kg-llm.heldout-confirmatory.v1",
        }[profile],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "claim_eligible": mode == "live",
        "claim_boundary": (
            "live OpenAI-compatible planning calls; execution stages are controlled replay outcomes"
            if mode == "live"
            else "deterministic local harness only; not evidence for a live LLM or external acquisition capability"
        ),
        "kg_identity": repo.get_knowledge_identity(),
        "case_count": len(cases),
        "selected_pair_ids": list(dict.fromkeys(selected_pair_ids)) if selected_pair_ids is not None else None,
        "base_case_count": sum(not case["is_fault"] for case in cases),
        "families": sorted({str(case["family"]) for case in cases}),
        "scenarios": (
            sorted({str(case["family"]) for case in cases})
            if profile in {ADVERSARIAL_PROFILE, HELDOUT_CONFIRMATORY_PROFILE}
            else []
        ),
        "repetitions_per_scenario": (
            5 if profile == ADVERSARIAL_PROFILE
            else 2 if profile == HELDOUT_CONFIRMATORY_PROFILE
            else None
        ),
        "products": list(PRODUCTS),
        "primary_methods": [method for method in methods if method in PRIMARY_METHODS],
        "ablations": [method for method in methods if method in ABLATIONS],
        "method_count": len(methods),
        "selected_methods": methods,
        "evaluation_profile": profile,
        "fault_labels_exposed_to_methods": profile == LABELED_EXACT_PROFILE,
        "case_set_hash": semantic_hash(cases),
        "case_set_source": {
            "kind": "frozen_external_json" if case_file is not None else "runner_generator",
            "path": str(Path(case_file).resolve()) if case_file is not None else None,
            "sha256": sha256_file(Path(case_file).resolve()) if case_file is not None else None,
        },
        "prompt": {
            "version": "simplified-planner-v3" if profile in V3_LIKE_PROFILES else "simplified-planner-v1",
            "semantic_hash": semantic_hash(V3_SYSTEM_PROMPT if profile in V3_LIKE_PROFILES else LIVE_SYSTEM_PROMPT),
        },
        "source_state": _source_state(),
        "runtime": {
            "python": platform.python_version(),
            "invocation": invocation,
            "random_seed": None,
            "method_order_policy": "deterministic_case_rotating",
            "max_workers": max_workers,
            "llm_replicates": llm_replicates,
            "deterministic_baseline_replicates": 1,
        },
        "provider_config": _provider_config(provider),
    }
    _write_json(output_dir / "manifest.json", manifest)
    _write_json(output_dir / "cases.json", cases)

    jobs: list[tuple[int, int, int, dict[str, Any], str]] = []
    execution_index = 0
    for case_index, case in enumerate(cases):
        offset = case_index % len(methods)
        ordered_methods = methods[offset:] + methods[:offset]
        for method_position, method in enumerate(ordered_methods):
            repeats = llm_replicates if _is_llm_method(method) else 1
            for replicate_id in range(1, repeats + 1):
                jobs.append((execution_index, method_position, replicate_id, case, method))
                execution_index += 1

    def run_job(job: tuple[int, int, int, dict[str, Any], str]) -> dict[str, Any]:
        job_index, method_position, replicate_id, case, method = job
        job_provider = provider
        if max_workers > 1 and mode == "live" and (
            method.startswith("llm_") or method.startswith("without_")
        ):
            # Provider state carries the last attempt, so each worker owns its client.
            job_provider = _live_provider()
        row = _run_one(case, method, repo=repo, mode=mode, provider=job_provider)
        row["execution_index"] = job_index
        row["method_position_in_case"] = method_position
        row["replicate_id"] = replicate_id
        return row

    rows: list[dict[str, Any]] = []
    checkpoint_path = output_dir / "rows.inprogress.jsonl"
    checkpoint_path.write_text("", encoding="utf-8")

    def record_row(row: dict[str, Any]) -> None:
        rows.append(row)
        trace_path = _trace_path(output_dir, row)
        _write_json(trace_path, row)
        with checkpoint_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        if len(rows) % 50 == 0 or len(rows) == len(jobs):
            print(f"progress {len(rows)}/{len(jobs)}", flush=True)

    if max_workers == 1:
        completed = (run_job(job) for job in jobs)
        for row in completed:
            record_row(row)
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(run_job, job) for job in jobs]
            for future in as_completed(futures):
                row = future.result()
                record_row(row)
        rows.sort(key=lambda item: int(item["execution_index"]))
    _write_json(output_dir / "rows.json", rows)
    _write_jsonl(output_dir / "rows.jsonl", rows)
    checkpoint_path.replace(output_dir / "rows.completion_order.jsonl")

    return _finalize_outputs(output_dir, manifest=manifest, rows=rows, provider=provider)


def _is_llm_method(method: str) -> bool:
    return method.startswith("llm_") or method.startswith("without_")


def _trace_path(output_dir: Path, row: dict[str, Any]) -> Path:
    return (
        output_dir
        / "traces"
        / str(row["case_id"])
        / str(row["method"])
        / f"replicate-{int(row.get('replicate_id') or 1)}"
        / "trace.json"
    )


def resume_failed_calls(output_dir: Path, *, transport_only: bool = False) -> dict[str, Any]:
    """Retry only failed live LLM rows and preserve each original failure trace."""
    output_dir = Path(output_dir)
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("mode") != "live":
        raise ValueError("Only live experiments can resume failed provider calls")
    cases = json.loads((output_dir / "cases.json").read_text(encoding="utf-8"))
    rows = json.loads((output_dir / "rows.json").read_text(encoding="utf-8"))
    case_by_id = {case["case_id"]: case for case in cases}
    repo = InMemoryKGRepository(experience_policy="pinned_snapshot")
    provider = _live_provider()
    retry_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    retried = 0
    updated: list[dict[str, Any]] = []
    for row in rows:
        is_llm = _is_llm_method(row["method"])
        failure_class = str((row.get("provider_attempt") or {}).get("failure_class") or "")
        retryable_transport = failure_class in {"http_error", "transport_error"}
        if not is_llm or _llm_row_complete(row) or (transport_only and not retryable_transport):
            updated.append(row)
            continue
        failed_path = (
            output_dir
            / "failed_attempts"
            / row["case_id"]
            / row["method"]
            / f"replicate-{int(row.get('replicate_id') or 1)}"
            / f"trace-{retry_stamp}.json"
        )
        _write_json(failed_path, row)
        replacement = _run_one(
            case_by_id[row["case_id"]],
            row["method"],
            repo=repo,
            mode="live",
            provider=provider,
        )
        replacement["retry_count"] = int(row.get("retry_count") or 0) + 1
        replacement["replicate_id"] = int(row.get("replicate_id") or 1)
        replacement["execution_index"] = row.get("execution_index")
        replacement["method_position_in_case"] = row.get("method_position_in_case")
        replacement["retry_history"] = [
            {
                "failure_class": (row.get("provider_attempt") or {}).get("failure_class"),
                "error": row.get("error"),
                "preserved_trace": str(failed_path.resolve()),
            }
        ]
        _write_json(_trace_path(output_dir, replacement), replacement)
        updated.append(replacement)
        retried += 1
    _write_json(output_dir / "rows.json", updated)
    _write_jsonl(output_dir / "rows.jsonl", updated)
    summary = _finalize_outputs(output_dir, manifest=manifest, rows=updated, provider=provider)
    summary["resume"] = {
        "retried_call_count": retried,
        "retry_stamp": retry_stamp,
        "transport_only": transport_only,
        "runner_sha256": sha256_file(Path(__file__).resolve()),
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


def _finalize_outputs(
    output_dir: Path,
    *,
    manifest: dict[str, Any],
    rows: list[dict[str, Any]],
    provider: OpenAICompatibleProvider | None,
) -> dict[str, Any]:
    summary = summarize_rows(
        rows,
        mode=str(manifest["mode"]),
        profile=str(manifest.get("evaluation_profile") or LABELED_EXACT_PROFILE),
    )
    llm_rows = [
        row
        for row in rows
        if row["method"].startswith("llm_") or row["method"].startswith("without_")
    ]
    provider_response_count = sum(
        1 for row in llm_rows if (row.get("provider_attempt") or {}).get("success") is True
    )
    strict_json_count = sum(
        1 for row in llm_rows if (row.get("provider_attempt") or {}).get("parse_mode") == "strict_json"
    )
    schema_valid_plan_count = sum(
        1 for row in llm_rows if row.get("plan") is not None and not row.get("error")
    )
    model_match_count = sum(
        1
        for row in llm_rows
        if (row.get("provider_attempt") or {}).get("response_model") == (row.get("provider_attempt") or {}).get("requested_model")
    )
    usage_complete_count = sum(
        1
        for row in llm_rows
        if ((row.get("provider_attempt") or {}).get("usage") or {}).get("total_tokens") is not None
    )
    complete_llm_call_count = sum(
        1
        for row in llm_rows
        if (row.get("provider_attempt") or {}).get("success") is True
        and (row.get("provider_attempt") or {}).get("parse_mode") == "strict_json"
        and row.get("plan") is not None
        and not row.get("error")
        and (row.get("provider_attempt") or {}).get("response_model") == (row.get("provider_attempt") or {}).get("requested_model")
        and ((row.get("provider_attempt") or {}).get("usage") or {}).get("total_tokens") is not None
    )
    auditable_provider_response_count = sum(
        1
        for row in llm_rows
        if 200 <= int((row.get("provider_attempt") or {}).get("http_status") or 0) < 300
        and (row.get("provider_attempt") or {}).get("raw_response") is not None
        and (row.get("provider_attempt") or {}).get("response_model")
        == (row.get("provider_attempt") or {}).get("requested_model")
        and ((row.get("provider_attempt") or {}).get("usage") or {}).get("total_tokens") is not None
    )
    output_schema_failure_count = sum(
        1
        for row in llm_rows
        if 200 <= int((row.get("provider_attempt") or {}).get("http_status") or 0) < 300
        and row.get("plan") is None
        and bool(row.get("error"))
    )
    manifest["provider"] = {
        "configured_model": provider.model if provider is not None else None,
        "configured_base_url_host": provider.base_url.split("//", 1)[-1].split("/", 1)[0] if provider is not None else None,
        "llm_call_count": len(llm_rows),
        "provider_response_count": provider_response_count,
        "strict_json_count": strict_json_count,
        "schema_valid_plan_count": schema_valid_plan_count,
        "model_match_count": model_match_count,
        "usage_complete_count": usage_complete_count,
        "complete_llm_call_count": complete_llm_call_count,
        "successful_llm_call_count": complete_llm_call_count,
        "auditable_provider_response_count": auditable_provider_response_count,
        "output_schema_failure_count": output_schema_failure_count,
        "response_models": sorted(
            {
                str((row.get("provider_attempt") or {}).get("response_model"))
                for row in llm_rows
                if (row.get("provider_attempt") or {}).get("response_model")
            }
        ),
        "failure_classes": sorted(
            {
                str((row.get("provider_attempt") or {}).get("failure_class") or "schema_validation_error")
                for row in llm_rows
                if (row.get("provider_attempt") or {}).get("failure_class") or row.get("error")
            }
        ),
        "provider_failure_classes": sorted(
            {
                str((row.get("provider_attempt") or {}).get("failure_class"))
                for row in llm_rows
                if (row.get("provider_attempt") or {}).get("failure_class")
                in {"http_error", "transport_error"}
            }
        ),
        "method_output_failure_classes": (
            ["schema_validation_error"] if output_schema_failure_count else []
        ),
    }
    summary["provider"] = manifest["provider"]
    if manifest.get("evaluation_profile") == HELDOUT_CONFIRMATORY_PROFILE:
        summary["claim_eligible"] = bool(
            manifest["mode"] == "live"
            and manifest["provider"]["llm_call_count"] > 0
            and manifest["provider"]["auditable_provider_response_count"]
            == manifest["provider"]["llm_call_count"]
        )
    else:
        summary["claim_eligible"] = bool(
            manifest["mode"] == "live"
            and manifest["provider"]["llm_call_count"] > 0
            and manifest["provider"]["complete_llm_call_count"] == manifest["provider"]["llm_call_count"]
        )
    manifest["claim_eligible"] = summary["claim_eligible"]
    _write_json(output_dir / "manifest.json", manifest)
    _write_json(output_dir / "summary.json", summary)
    (output_dir / "main_comparison.md").write_text(render_main_table(summary), encoding="utf-8")
    (output_dir / "kg_ablation.md").write_text(render_ablation_table(summary), encoding="utf-8")
    (output_dir / "outcome_metrics.md").write_text(render_outcome_metrics(summary), encoding="utf-8")
    (output_dir / "experiment_plan.md").write_text(render_experiment_plan(summary), encoding="utf-8")
    (output_dir / "case_catalog.md").write_text(render_case_catalog(rows), encoding="utf-8")
    (output_dir / "conclusion.md").write_text(render_conclusion(summary), encoding="utf-8")
    if manifest.get("evaluation_profile") == HELDOUT_CONFIRMATORY_PROFILE:
        stats = confirmatory_statistics(rows)
        summary["confirmatory_statistics"] = stats
        _write_json(output_dir / "confirmatory_statistics.json", stats)
        (output_dir / "confirmatory_statistics.md").write_text(
            render_confirmatory_statistics(stats), encoding="utf-8"
        )
        _write_json(output_dir / "summary.json", summary)
    _write_json(output_dir / "success_trace.json", _representative(rows, passed=True))
    _write_json(output_dir / "failure_trace.json", _representative(rows, passed=False))
    return summary


def _llm_row_complete(row: dict[str, Any]) -> bool:
    attempt = row.get("provider_attempt") or {}
    return bool(
        attempt.get("success") is True
        and attempt.get("parse_mode") == "strict_json"
        and row.get("plan") is not None
        and not row.get("error")
        and attempt.get("response_model") == attempt.get("requested_model")
        and (attempt.get("usage") or {}).get("total_tokens") is not None
    )


def _companions(product: str, family: str) -> list[str]:
    if family == "cross_task_precedence":
        if product in {"water_polygon", "waterways"}:
            return ["building"]
        return ["road"] if product != "road" else ["building"]
    return []


def _observations(
    product: str,
    companions: list[str],
    fault: str | None,
    *,
    expose_fault_label: bool,
) -> dict[str, Any]:
    all_tasks = [product, *companions]
    disaster_type = "flood" if product in {"water_polygon", "waterways"} else "earthquake"
    available = {task: [_source_id(disaster_type, task)] for task in all_tasks}
    observations: dict[str, Any] = {
        "available_sources": available,
        "mission_priority": _priority(all_tasks),
        "crosswalk_status": "closed",
    }
    if expose_fault_label:
        observations["fault_signal"] = fault
    if fault in {"source_availability", "vector_acquisition_failure"}:
        observations["available_sources"][product] = []
    if fault == "aoi_determination":
        observations["aoi_resolved"] = False
    if fault == "kg_crosswalk":
        observations["crosswalk_status"] = "missing"
    if fault == "algorithm_capability":
        observations["required_algorithm"] = "algo.unsupported.v1"
    if fault == "quality_gate":
        observations["quality_gate_previous"] = "rejected"
    if fault == "evidence_completeness":
        observations["evidence_complete"] = False
    if fault == "validator_veto":
        observations["validator_veto"] = "contract_conflict"
    if fault == "contract_requiredness":
        observations["required_field_missing"] = "provenance"
    if fault == "delivery_state":
        observations["delivery_blocked"] = True
    if fault == "plan_validity":
        observations["plan_constraint"] = "must_not_invent_references"
    return observations


def _priority(tasks: list[str]) -> list[str]:
    rank = {"water_polygon": 0, "waterways": 1, "road": 2, "building": 3, "poi": 4}
    return sorted(tasks, key=lambda task: rank[task])


def _oracle(
    product: str,
    companions: list[str],
    fault: str | None,
    *,
    profile: str,
) -> dict[str, Any]:
    tasks = _priority([product, *companions])
    if fault in {"aoi_determination", "kg_crosswalk", "validator_veto"}:
        oracle = {"decision": "reject", "tasks": [], "states": {}, "hard_veto": fault}
        if profile == OBSERVABLE_INVARIANT_PROFILE:
            oracle["acceptance"] = {
                "allowed_decisions": ["reject"],
                "allowed_product_states": [],
                "allow_empty_tasks_on": ["reject"],
            }
        return oracle
    state = "planned"
    decision = "plan"
    if fault in {"source_availability", "vector_acquisition_failure", "contract_requiredness", "delivery_state"}:
        state, decision = "gap", "gap"
    elif fault == "quality_gate":
        state, decision = "provisional", "degraded"
    elif fault == "evidence_completeness":
        state, decision = "pending", "manual_intervention"
    elif fault == "algorithm_capability":
        state, decision = "gap", "gap"
    elif fault == "plan_validity":
        state, decision = "planned", "plan"
    states = {task: (state if task == product else "planned") for task in tasks}
    oracle = {"decision": decision, "tasks": tasks, "states": states, "hard_veto": None}
    if profile == OBSERVABLE_INVARIANT_PROFILE:
        allowed_decisions = [decision]
        allowed_states = [state]
        allow_empty_tasks_on: list[str] = []
        if fault in {
            "source_availability",
            "vector_acquisition_failure",
            "contract_requiredness",
            "delivery_state",
            "algorithm_capability",
        }:
            allowed_decisions = ["gap", "reject", "manual_intervention"]
            allowed_states = ["gap", "rejected", "pending"]
            allow_empty_tasks_on = ["reject"]
        elif fault == "quality_gate":
            allowed_decisions = ["degraded", "gap", "manual_intervention"]
            allowed_states = ["provisional", "degraded", "gap", "pending"]
        elif fault == "evidence_completeness":
            allowed_decisions = ["manual_intervention", "partial", "gap"]
            allowed_states = ["pending", "provisional", "gap"]
        oracle["acceptance"] = {
            "allowed_decisions": allowed_decisions,
            "allowed_product_states": allowed_states,
            "allow_empty_tasks_on": allow_empty_tasks_on,
        }
    return oracle


def _run_one(
    case: dict[str, Any],
    method: str,
    *,
    repo: InMemoryKGRepository,
    mode: str,
    provider: OpenAICompatibleProvider | None,
) -> dict[str, Any]:
    started = time.perf_counter()
    context, kg_trace = _build_context(case, method, repo)
    raw_plan: dict[str, Any] | None
    attempt: dict[str, Any] | None = None
    error: str | None = None
    try:
        if method.startswith("llm_") or method.startswith("without_"):
            if mode == "live":
                assert provider is not None
                system_prompt = V3_SYSTEM_PROMPT if case.get("evaluation_profile") in V3_LIKE_PROFILES else LIVE_SYSTEM_PROMPT
                raw_plan = provider.generate_workflow_plan(system_prompt, context)
                attempt = provider.last_attempt
            else:
                raw_plan = _local_llm_plan(case, method, context)
        else:
            raw_plan = _baseline_plan(case, method, context=context)
        plan = ResearchPlanningDecision.model_validate(raw_plan)
    except Exception as exc:  # noqa: BLE001
        plan = None
        error = str(exc)
        if provider is not None:
            attempt = provider.last_attempt
    evaluation = _evaluate(case, plan, method=method, error=error)
    latency_ms = round((time.perf_counter() - started) * 1000, 3)
    usage = dict((attempt or {}).get("usage") or {})
    estimated_tokens = _estimate_tokens(context, raw_plan if plan is not None else None)
    return {
        "case_id": case["case_id"],
        "pair_id": case["pair_id"],
        "family": case["family"],
        "variant": case["variant"],
        "product": case["product"],
        "perturbation_tags": case.get("perturbation_tags", []),
        "method": method,
        "execution_mode": mode,
        "raw_request": case["request"],
        "observations": case["observations"],
        "kg_provided": kg_trace,
        "planning_input": context,
        "plan": plan.model_dump(mode="json") if plan is not None else None,
        "provider_attempt": attempt,
        "tool_call_sequence": _tool_sequence(
            plan,
            proposed_only=case.get("evaluation_profile") in V3_LIKE_PROFILES,
        ),
        "tool_execution_mode": (
            "not_executed_controlled_evaluation"
            if case.get("evaluation_profile") in V3_LIKE_PROFILES
            else "legacy_controlled_replay"
        ),
        "stage_status": evaluation["stage_status"],
        "final_delivery_state": evaluation["final_delivery_state"],
        "oracle": evaluation["oracle"],
        "vetoes": evaluation["vetoes"],
        "oracle_pass": evaluation["oracle_pass"],
        "hard_veto_violated": evaluation["hard_veto_violated"],
        "token_count": int(usage.get("total_tokens") or estimated_tokens),
        "token_count_source": "provider_usage" if usage.get("total_tokens") is not None else "local_estimate",
        "latency_ms": float((attempt or {}).get("latency_ms") or latency_ms),
        "retry_count": int((attempt or {}).get("transport_retry_count") or 0),
        "error": error,
    }


def _build_context(case: dict[str, Any], method: str, repo: InMemoryKGRepository) -> tuple[dict[str, Any], dict[str, Any]]:
    if case.get("evaluation_profile") in V3_LIKE_PROFILES:
        return _build_v3_context(case, method, repo)
    product = case["product"]
    kg = repo.build_context(_job_type(product), case["request"]["disaster_type"])
    capability = {
        "algorithms": [{"id": key, "tool_ref": value.tool_ref} for key, value in sorted(kg.algorithms.items())],
        "sources": [{"id": value.source_id, "supported_job_types": value.supported_job_types} for value in kg.data_sources],
        "task_nodes": [{"id": value.task_id} for value in kg.task_nodes],
    }
    contract = {
        "contracts": [{"id": value.contract_id, "quality_gates": value.quality_gates, "delivery_policy": value.delivery_policy} for value in kg.product_contracts],
        "output_requirements": [{"id": key, "required_fields": value.required_fields} for key, value in kg.output_requirements.items()],
        "qos_policies": [{"id": key} for key in kg.qos_policies],
    }
    ontology = {
        "identity": repo.get_knowledge_identity(),
        "crosswalk": {"status": case["observations"]["crosswalk_status"], "product": product, "source_ids": [item["id"] for item in capability["sources"]]},
    }
    removed: list[str] = []
    include_capability, include_contract, include_ontology = method in {"llm_capability_kg", "llm_full_contract_kg"}, method == "llm_full_contract_kg", method == "llm_full_contract_kg"
    if method == "without_ontology_identity_crosswalk":
        include_capability, include_contract, include_ontology = True, True, False
        removed.append("ontology_identity_crosswalk")
    elif method == "without_capability_algorithm_grounding":
        include_capability, include_contract, include_ontology = False, True, True
        removed.append("capability_algorithm_grounding")
    elif method == "without_contract_quality_delivery_policy":
        include_capability, include_contract, include_ontology = True, False, True
        removed.append("contract_quality_delivery_policy")
    payload: dict[str, Any] = {
        "request": case["request"],
        "observations": case["observations"],
        "output_schema": ResearchPlanningDecision.model_json_schema(),
    }
    entities: list[dict[str, str]] = []
    relationships: list[dict[str, str]] = []
    if include_ontology:
        payload["ontology_identity_crosswalk"] = ontology
        entities.append({"kind": "kg_release", "id": ontology["identity"]["release_id"]})
        relationships.append({"source": product, "relation": "crosswalked_to", "target": ontology["crosswalk"]["status"]})
    if include_capability:
        payload["capability_algorithm_grounding"] = capability
        entities.extend({"kind": "algorithm", "id": item["id"]} for item in capability["algorithms"])
        relationships.extend({"source": product, "relation": "can_use", "target": item["id"]} for item in capability["algorithms"])
    if include_contract:
        payload["contract_quality_delivery_policy"] = contract
        entities.extend({"kind": "contract", "id": item["id"]} for item in contract["contracts"])
        relationships.extend({"source": product, "relation": "governed_by", "target": item["id"]} for item in contract["contracts"])
    return payload, {"entities": entities, "relationships": relationships, "removed_modules": removed}


def _method_modules(method: str) -> tuple[bool, bool, bool, list[str]]:
    include_capability = method in {"llm_capability_kg", "llm_full_contract_kg"}
    include_contract = method == "llm_full_contract_kg"
    include_ontology = method == "llm_full_contract_kg"
    removed: list[str] = []
    if method == "without_ontology_identity_crosswalk":
        include_capability, include_contract, include_ontology = True, True, False
        removed.append("ontology_identity_crosswalk")
    elif method == "without_capability_algorithm_grounding":
        include_capability, include_contract, include_ontology = False, True, True
        removed.append("capability_algorithm_grounding")
    elif method == "without_contract_quality_delivery_policy":
        include_capability, include_contract, include_ontology = True, False, True
        removed.append("contract_quality_delivery_policy")
    return include_capability, include_contract, include_ontology, removed


def _build_v3_context(
    case: dict[str, Any],
    method: str,
    repo: InMemoryKGRepository,
) -> tuple[dict[str, Any], dict[str, Any]]:
    include_capability, include_contract, include_ontology, removed = _method_modules(method)
    registry = KnowledgePolicyRegistry()
    request_tokens = [str(item) for item in case["request"]["products"]]
    mappings: list[dict[str, Any]] = []
    resolved_tasks: list[str] = []
    for token in request_tokens:
        if include_ontology:
            matches = registry.task_kinds_for_alias(token)
        else:
            matches = [token] if token in PRODUCTS else []
        mapping: dict[str, Any] = {
            "input": token,
            "status": "resolved" if len(matches) == 1 else "unresolved",
            "canonical_task_kind": matches[0] if len(matches) == 1 else None,
        }
        if len(matches) == 1:
            task_record = registry.task_record(matches[0])
            mapping.update(
                task_id=str(task_record["task_id"]),
                output_type=str(task_record["output_data_type"]),
            )
            if matches[0] not in resolved_tasks:
                resolved_tasks.append(matches[0])
        mappings.append(mapping)

    grounding = {
        task: _v3_product_grounding(repo, registry, task, case["request"]["disaster_type"])
        for task in resolved_tasks
    }
    payload: dict[str, Any] = {
        "request": case["request"],
        "observations": case["observations"],
        "tool_catalog": {
            "algorithms": [
                {"id": algorithm.algo_id, "tool_ref": algorithm.tool_ref}
                for algorithm in repo.list_algorithms()
                if algorithm.task_type != "transform"
            ]
        },
        "output_schema": ResearchPlanningDecision.model_json_schema(),
    }
    entities: dict[tuple[str, str], dict[str, str]] = {}
    relationships: dict[tuple[str, str, str], dict[str, str]] = {}
    if include_ontology:
        payload["ontology_identity_crosswalk"] = {
            "identity": repo.get_knowledge_identity(),
            "mappings": mappings,
        }
        if case.get("evaluation_profile") in {ADVERSARIAL_PROFILE, HELDOUT_CONFIRMATORY_PROFILE}:
            payload["ontology_identity_crosswalk"]["canonical_precedence"] = [
                {"task_kind": task, "rank": rank}
                for rank, task in enumerate(
                    sorted(case["task_kinds"], key=lambda item: V3_MISSION_PRIORITY[item]),
                    start=1,
                )
            ]
        identity = repo.get_knowledge_identity()
        entities[("kg_release", identity["release_id"])] = {"kind": "kg_release", "id": identity["release_id"]}
        for mapping in mappings:
            if mapping["status"] != "resolved":
                continue
            task_id = str(mapping["task_id"])
            entities[("task", task_id)] = {"kind": "task", "id": task_id}
            relationships[(mapping["input"], "maps_to", task_id)] = {
                "source": mapping["input"],
                "relation": "maps_to",
                "target": task_id,
            }
    if include_capability:
        task_capabilities = []
        algorithm_by_id = {algorithm.algo_id: algorithm for algorithm in repo.list_algorithms()}
        source_by_id = {source.source_id: source for source in repo.list_data_sources()}
        for task in resolved_tasks:
            item = grounding[task]
            algorithms = [
                {
                    "id": algorithm_id,
                    "output_type": algorithm_by_id[algorithm_id].output_type,
                    "tool_ref": algorithm_by_id[algorithm_id].tool_ref,
                }
                for algorithm_id in item["algorithm_ids"]
            ]
            sources = [
                {
                    "id": source_id,
                    "supported_job_types": source_by_id[source_id].supported_job_types,
                }
                for source_id in item["source_ids"]
            ]
            task_capabilities.append(
                {
                    "task_kind": task,
                    "task_id": item["task_id"],
                    "output_type": item["output_type"],
                    "pattern_ids": item["pattern_ids"],
                    "algorithms": algorithms,
                    "sources": sources,
                }
            )
            for algorithm in algorithms:
                entities[("algorithm", algorithm["id"])] = {"kind": "algorithm", "id": algorithm["id"]}
                relationships[(item["task_id"], "can_use", algorithm["id"])] = {
                    "source": item["task_id"],
                    "relation": "can_use",
                    "target": algorithm["id"],
                }
            for source in sources:
                entities[("source", source["id"])] = {"kind": "source", "id": source["id"]}
                relationships[(source["id"], "supports", item["task_id"])] = {
                    "source": source["id"],
                    "relation": "supports",
                    "target": item["task_id"],
                }
        payload["capability_algorithm_grounding"] = {"tasks": task_capabilities}
    if include_contract:
        contract_by_id = repo.product_contracts
        requirement_by_id = {item.requirement_id: item for item in repo.list_output_requirements()}
        qos_by_id = {item.policy_id: item for item in repo.list_qos_policies()}
        products = []
        for task in resolved_tasks:
            item = grounding[task]
            contract = contract_by_id[item["contract_id"]]
            requirement = requirement_by_id[item["output_requirement_id"]]
            qos_ids = [policy_id for policy_id in item["qos_policy_ids"] if policy_id in qos_by_id]
            products.append(
                {
                    "task_kind": task,
                    "contract": {
                        "id": contract.contract_id,
                        "quality_gates": contract.quality_gates,
                        "evidence_requirements": contract.evidence_requirements,
                        "delivery_policy": contract.delivery_policy,
                    },
                    "output_requirement": {
                        "id": requirement.requirement_id,
                        "output_type": requirement.output_type,
                        "required_fields": requirement.required_fields,
                    },
                    "qos_policy_ids": qos_ids,
                }
            )
            entities[("contract", contract.contract_id)] = {"kind": "contract", "id": contract.contract_id}
            entities[("output_requirement", requirement.requirement_id)] = {
                "kind": "output_requirement",
                "id": requirement.requirement_id,
            }
            relationships[(item["task_id"], "governed_by", contract.contract_id)] = {
                "source": item["task_id"],
                "relation": "governed_by",
                "target": contract.contract_id,
            }
            relationships[(contract.contract_id, "requires_output", requirement.requirement_id)] = {
                "source": contract.contract_id,
                "relation": "requires_output",
                "target": requirement.requirement_id,
            }
            for policy_id in qos_ids:
                entities[("qos_policy", policy_id)] = {"kind": "qos_policy", "id": policy_id}
                relationships[(contract.contract_id, "uses_qos", policy_id)] = {
                    "source": contract.contract_id,
                    "relation": "uses_qos",
                    "target": policy_id,
                }
        payload["contract_quality_delivery_policy"] = {"products": products}
    return payload, {
        "entities": [entities[key] for key in sorted(entities)],
        "relationships": [relationships[key] for key in sorted(relationships)],
        "removed_modules": removed,
    }


def _local_llm_plan(case: dict[str, Any], method: str, context: dict[str, Any]) -> dict[str, Any]:
    """A labeled offline control, not a substitute for a provider call."""
    if case.get("evaluation_profile") in V3_LIKE_PROFILES:
        return _local_v3_llm_plan(case, method, context)
    fault = case["observations"].get("fault_signal")
    full = method == "llm_full_contract_kg"
    has_capability = "capability_algorithm_grounding" in context
    has_contract = "contract_quality_delivery_policy" in context
    has_ontology = "ontology_identity_crosswalk" in context
    recognized = full or method == "llm_capability_kg"
    if method.startswith("without_"):
        recognized = True
    if fault in {"aoi_determination", "validator_veto"} and has_contract:
        return {"decision": "reject", "tasks": [], "uncertainties": [fault], "evidence": ["observations"]}
    if fault == "kg_crosswalk" and has_ontology:
        return {"decision": "reject", "tasks": [], "uncertainties": [fault], "evidence": ["crosswalk"]}
    tasks = _priority(case["task_kinds"]) if recognized else list(case["task_kinds"])
    decision, state = "plan", "planned"
    if fault in {"source_availability", "vector_acquisition_failure", "contract_requiredness", "delivery_state"} and has_contract:
        decision, state = "gap", "gap"
    elif fault == "quality_gate" and has_contract:
        decision, state = "degraded", "provisional"
    elif fault == "evidence_completeness" and has_contract:
        decision, state = "manual_intervention", "pending"
    elif fault == "algorithm_capability" and has_capability:
        decision, state = "gap", "gap"
    algorithm = _known_algorithm(case["product"], context) if has_capability else None
    if fault == "algorithm_capability" and not has_capability:
        algorithm = "algo.unsupported.v1"
    return _plan_payload(case, tasks, decision=decision, affected_state=state, algorithm_id=algorithm)


def _local_v3_llm_plan(case: dict[str, Any], method: str, context: dict[str, Any]) -> dict[str, Any]:
    """Deterministic V3 control used only to validate the harness and oracle."""
    observations = context["observations"]
    mappings = (context.get("ontology_identity_crosswalk") or {}).get("mappings", [])
    token_to_task = {
        str(item.get("input")): str(item.get("canonical_task_kind"))
        for item in mappings
        if item.get("status") == "resolved" and item.get("canonical_task_kind")
    }
    for task in case["task_kinds"]:
        token_to_task.setdefault(task, task)

    resolved_tokens = [
        (str(token), token_to_task[token])
        for token in context["request"]["products"]
        if token in token_to_task
    ]
    resolved_tasks = list(dict.fromkeys(task for _token, task in resolved_tokens))
    precedence = (context.get("ontology_identity_crosswalk") or {}).get("canonical_precedence") or []
    if precedence:
        rank_by_task = {str(item["task_kind"]): int(item["rank"]) for item in precedence}
        resolved_tasks.sort(key=lambda task: rank_by_task.get(task, len(rank_by_task) + 1))
    else:
        mission = [token_to_task.get(str(token)) for token in observations.get("mission_priority", [])]
        mission = [task for task in mission if task in resolved_tasks]
        if len(set(mission)) == len(resolved_tasks):
            resolved_tasks = list(dict.fromkeys(mission))

    if any(item.get("status") in {"fail", "blocked"} for item in observations.get("validator_results", [])):
        return {
            "decision": "reject",
            "tasks": [],
            "uncertainties": list(observations.get("observation_ids", {}).values()),
            "evidence": list(observations.get("observation_ids", {}).values()),
        }
    if observations.get("selected_aoi_id") is None:
        return {
            "decision": "reject",
            "tasks": [],
            "uncertainties": list(observations.get("observation_ids", {}).values()),
            "evidence": list(observations.get("observation_ids", {}).values()),
        }

    capability_tasks = {
        str(item.get("task_kind")): item
        for item in (context.get("capability_algorithm_grounding") or {}).get("tasks", [])
    }
    task_sources: dict[str, list[str]] = {}
    for task in resolved_tasks:
        token = next((raw for raw, canonical in resolved_tokens if canonical == task), task)
        task_sources[task] = [
            str(item["source_id"])
            for item in observations.get("source_checks", {}).get(token, [])
            if item.get("catalog_status") == "available" and item.get("acquisition_status") == "ready"
        ]

    decision = "plan"
    affected_state = "planned"
    evidence = list(observations.get("observation_ids", {}).values())
    product_token = next(
        (raw for raw, canonical in resolved_tokens if canonical == case["product"]),
        case["product"],
    )
    product_checks = observations.get("source_checks", {}).get(product_token, [])
    product_measurements = observations.get("quality_measurements", {}).get(product_token, {})
    required_fields = set(
        next(
            (
                item.get("output_requirement", {}).get("required_fields", [])
                for item in (context.get("contract_quality_delivery_policy") or {}).get("products", [])
                if item.get("task_kind") == case["product"]
            ),
            [],
        )
    )
    observed_fields = set(observations.get("proposed_output_fields", {}).get(product_token, []))
    missing_evidence = not all(
        item in observations.get("available_evidence", {}).get(product_token, [])
        for item in next(
            (
                item.get("contract", {}).get("evidence_requirements", [])
                for item in (context.get("contract_quality_delivery_policy") or {}).get("products", [])
                if item.get("task_kind") == case["product"]
            ),
            [],
        )
    )
    if not product_checks or any(item.get("acquisition_status") != "ready" for item in product_checks):
        decision, affected_state = "gap", "gap"
    elif observations.get("required_algorithm_override"):
        decision, affected_state = "gap", "gap"
    elif required_fields and not required_fields <= observed_fields:
        decision, affected_state = "gap", "gap"
    elif missing_evidence or observations.get("evidence_status") == "incomplete":
        decision, affected_state = "manual_intervention", "pending"
    elif any(value is False for value in product_measurements.values()):
        decision, affected_state = "degraded", "provisional"
    elif observations.get("delivery_channel", {}).get("status") == "blocked":
        decision, affected_state = "gap", "gap"

    tasks = []
    for index, task in enumerate(resolved_tasks, start=1):
        algorithm_id = None
        grounded = capability_tasks.get(task) or {}
        algorithms = grounded.get("algorithms") or []
        if algorithms:
            algorithm_id = str(algorithms[0]["id"])
        else:
            algorithm_id = V3_FIXED_ALGORITHMS.get(task)
        tasks.append(
            {
                "order": index,
                "task_kind": task,
                "source_ids": task_sources.get(task, []),
                "algorithm_id": algorithm_id,
                "delivery_state": affected_state if task == case["product"] else "planned",
                "rationale": "deterministic V3 control planner",
            }
        )
    return {
        "decision": decision,
        "tasks": tasks,
        "uncertainties": [],
        "evidence": evidence,
    }


V3_FIXED_ALGORITHMS = {
    "building": "algo.fusion.building.v1",
    "road": "algo.fusion.road.conflation.v7",
    "water_polygon": "algo.fusion.water_polygon.priority_merge.v2",
    "waterways": "algo.fusion.waterways.conflation.v7",
    "poi": "algo.fusion.poi.v1",
}


def _baseline_plan(case: dict[str, Any], method: str, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
    if case.get("evaluation_profile") in V3_LIKE_PROFILES:
        return _v3_baseline_plan(case, method, context=context or {})
    observations = case["observations"]
    if method == "rules_only" and (
        observations.get("aoi_resolved") is False or observations.get("validator_veto") is not None
    ):
        return {
            "decision": "reject",
            "tasks": [],
            "uncertainties": ["request blocked by an observed precondition"],
            "evidence": ["rules.general.v1"],
        }
    tasks = _priority(case["task_kinds"]) if method == "rules_only" else list(case["task_kinds"])
    return _plan_payload(case, tasks, decision="plan", affected_state="planned", algorithm_id=None)


def _v3_baseline_plan(case: dict[str, Any], method: str, *, context: dict[str, Any]) -> dict[str, Any]:
    observations = context["observations"]
    validator_failed = any(item.get("status") == "fail" for item in observations["validator_results"])
    aoi_ambiguous = observations.get("selected_aoi_id") is None
    if method == "rules_only" and (aoi_ambiguous or validator_failed):
        anchor = observations["observation_ids"]["aoi" if aoi_ambiguous else "validator"]
        return {
            "decision": "reject",
            "tasks": [],
            "uncertainties": [f"blocked by {anchor}"],
            "evidence": [anchor],
        }
    request_tokens = [str(item) for item in context["request"]["products"]]
    recognized = [token for token in request_tokens if token in PRODUCTS]
    if method == "rules_only":
        priority_tokens = [str(item) for item in observations.get("mission_priority", [])]
        recognized = [token for token in priority_tokens if token in recognized]
    tasks = []
    for index, task in enumerate(recognized, start=1):
        checks = observations["source_checks"].get(task, [])
        source_ids = [
            str(item["source_id"])
            for item in checks
            if item.get("catalog_status") == "available" and item.get("acquisition_status") == "ready"
        ]
        tasks.append(
            {
                "order": index,
                "task_kind": task,
                "source_ids": source_ids,
                "algorithm_id": V3_FIXED_ALGORITHMS[task],
                "delivery_state": "planned",
                "rationale": "fixed reference workflow",
            }
        )
    return {
        "decision": "plan",
        "tasks": tasks,
        "uncertainties": [],
        "evidence": ["request", "raw observations"],
    }


def _plan_payload(case: dict[str, Any], tasks: list[str], *, decision: str, affected_state: str, algorithm_id: str | None) -> dict[str, Any]:
    product = case["product"]
    return {
        "decision": decision,
        "tasks": [
            {
                "order": index,
                "task_kind": task,
                "source_ids": [_source_id(case["request"]["disaster_type"], task)],
                "algorithm_id": algorithm_id if task == product else None,
                "delivery_state": affected_state if task == product else "planned",
                "rationale": "controlled experiment planner output",
            }
            for index, task in enumerate(tasks, start=1)
        ],
        "uncertainties": [],
        "evidence": ["request", "observations"],
    }


def _known_algorithm(product: str, context: dict[str, Any]) -> str | None:
    algorithms = context.get("capability_algorithm_grounding", {}).get("algorithms", [])
    for item in algorithms:
        algorithm_id = str(item.get("id") or "")
        if product in algorithm_id:
            return algorithm_id
    return str(algorithms[0]["id"]) if algorithms else None


def _evaluate(case: dict[str, Any], plan: ResearchPlanningDecision | None, *, method: str, error: str | None) -> dict[str, Any]:
    expected = case["oracle"]
    profile = case.get("evaluation_profile", LABELED_EXACT_PROFILE)
    if profile in V3_LIKE_PROFILES:
        return _evaluate_v3(case, plan, error=error)
    actual_tasks = [task.task_kind for task in plan.tasks] if plan else []
    actual_states = {task.task_kind: task.delivery_state for task in plan.tasks} if plan else {}
    plan_valid = plan is not None and error is None and len(actual_tasks) == len(set(actual_tasks))
    if profile == OBSERVABLE_INVARIANT_PROFILE:
        source_known = all(
            source in set(case["observations"]["available_sources"].get(task.task_kind, []))
            for task in (plan.tasks if plan else [])
            for source in task.source_ids
        )
    else:
        source_known = all(
            source in set(case["observations"]["available_sources"].get(task.task_kind, []))
            or source == _source_id(case["request"]["disaster_type"], task.task_kind)
            for task in (plan.tasks if plan else [])
            for source in task.source_ids
        )
    algorithm_known = all(
        task.algorithm_id is None or not task.algorithm_id.startswith("algo.unsupported")
        for task in (plan.tasks if plan else [])
    )
    aoi_ok = case["observations"].get("aoi_resolved") is not False or (plan is not None and plan.decision == "reject")
    acquisition_ok = all(case["observations"]["available_sources"].get(task, []) or actual_states.get(task) in {"gap", "pending", "rejected"} for task in actual_tasks)
    quality_ok = case["observations"].get("quality_gate_previous") != "rejected" or actual_states.get(case["product"]) in {"provisional", "degraded", "gap"}
    if profile == OBSERVABLE_INVARIANT_PROFILE:
        delivery_ok = _matches_invariant_acceptance(
            case,
            plan,
            actual_tasks=actual_tasks,
            actual_states=actual_states,
        )
    else:
        delivery_ok = plan is not None and plan.decision == expected["decision"] and actual_states == expected["states"] and actual_tasks == expected["tasks"]
    expected_veto = expected["hard_veto"]
    hard_veto_violated = bool(expected_veto) and not (plan is not None and plan.decision == "reject")
    vetoes = []
    if expected_veto:
        vetoes.append({"veto_id": expected_veto, "triggered": plan is not None and plan.decision == "reject"})
    stages = {
        "planning": plan_valid,
        "aoi": aoi_ok,
        "acquisition": acquisition_ok,
        "algorithm": algorithm_known and source_known,
        "quality": quality_ok,
        "delivery": delivery_ok,
    }
    return {
        "oracle": expected,
        "stage_status": stages,
        "final_delivery_state": actual_states.get(case["product"], "not_delivered"),
        "vetoes": vetoes,
        "hard_veto_violated": hard_veto_violated,
        "oracle_pass": all(stages.values()) and not hard_veto_violated,
    }


def _evaluate_v3(
    case: dict[str, Any],
    plan: ResearchPlanningDecision | None,
    *,
    error: str | None,
) -> dict[str, Any]:
    expected = case["oracle"]
    ground_truth = expected["ground_truth"]
    actual_tasks = [task.task_kind for task in plan.tasks] if plan else []
    actual_states = {task.task_kind: task.delivery_state for task in plan.tasks} if plan else {}
    actual_orders = [task.order for task in plan.tasks] if plan else []
    plan_text = " ".join(
        [
            *(plan.evidence if plan else []),
            *(plan.uncertainties if plan else []),
            *((task.rationale for task in plan.tasks) if plan else []),
        ]
    ).casefold()
    anchors = list(ground_truth.get("evidence_anchors") or [])
    if not anchors and ground_truth.get("evidence_anchor"):
        anchors = [ground_truth["evidence_anchor"]]
    evidence_ok = bool(plan and plan.evidence) and all(
        str(anchor).casefold() in plan_text for anchor in anchors
    )
    plan_valid = bool(
        plan is not None
        and error is None
        and len(actual_tasks) == len(set(actual_tasks))
        and actual_orders == list(range(1, len(actual_orders) + 1))
        and set(actual_tasks) <= set(ground_truth["task_kinds"])
        and evidence_ok
    )

    selected_aoi = case["observations"].get("selected_aoi_id")
    aoi_ok = selected_aoi is not None or bool(plan and plan.decision == "reject")

    usable_sources: dict[str, set[str]] = {}
    known_sources: dict[str, set[str]] = {}
    for task, product_truth in ground_truth["products"].items():
        known_sources[task] = set(product_truth["source_ids"])
        token = _presented_token_for_task(case, task)
        usable_sources[task] = {
            str(item["source_id"])
            for item in case["observations"]["source_checks"].get(token, [])
            if item.get("catalog_status") == "available" and item.get("acquisition_status") == "ready"
        }
    acquisition_ok = True
    algorithm_ok = True
    for task in plan.tasks if plan else []:
        task_sources = set(task.source_ids)
        if not task_sources <= known_sources.get(task.task_kind, set()):
            acquisition_ok = False
        if task.delivery_state == "planned":
            if not task_sources or not task_sources <= usable_sources.get(task.task_kind, set()):
                acquisition_ok = False
        elif not task_sources <= usable_sources.get(task.task_kind, set()):
            acquisition_ok = False
        allowed_algorithms = set(ground_truth["products"].get(task.task_kind, {}).get("algorithm_ids", []))
        if task.delivery_state == "planned":
            if task.algorithm_id not in allowed_algorithms:
                algorithm_ok = False
        elif task.algorithm_id is not None and task.algorithm_id not in allowed_algorithms:
            algorithm_ok = False

    product_token = _presented_token_for_task(case, case["product"])
    measurements = case["observations"]["quality_measurements"].get(product_token, {})
    quality_failed = any(value is False for value in measurements.values())
    quality_ok = not quality_failed or bool(
        plan
        and plan.decision in expected["acceptance"]["allowed_decisions"]
        and actual_states.get(case["product"]) in expected["acceptance"]["allowed_product_states"]
        and evidence_ok
    )
    delivery_ok = _matches_v3_delivery(case, plan, actual_tasks=actual_tasks, actual_states=actual_states) and evidence_ok
    expected_veto = expected["hard_veto"]
    hard_veto_violated = bool(expected_veto) and not bool(plan and plan.decision == "reject" and not plan.tasks)
    vetoes = []
    if expected_veto:
        vetoes.append(
            {
                "veto_id": expected_veto,
                "triggered": bool(plan and plan.decision == "reject" and not plan.tasks),
            }
        )
    stages = {
        "planning": plan_valid,
        "aoi": aoi_ok,
        "acquisition": acquisition_ok,
        "algorithm": algorithm_ok,
        "quality": quality_ok,
        "delivery": delivery_ok,
    }
    return {
        "oracle": expected,
        "stage_status": stages,
        "final_delivery_state": actual_states.get(case["product"], "not_delivered"),
        "vetoes": vetoes,
        "hard_veto_violated": hard_veto_violated,
        "oracle_pass": all(stages.values()) and not hard_veto_violated,
    }


def _presented_token_for_task(case: dict[str, Any], task: str) -> str:
    presented = case.get("presented_tokens") or {}
    if task in presented:
        return str(presented[task])
    if case["family"] == "kg_crosswalk" and case["is_fault"] and task == case["product"]:
        return V3_CROSSWALK_ALIASES[task]
    return task


def _matches_v3_delivery(
    case: dict[str, Any],
    plan: ResearchPlanningDecision | None,
    *,
    actual_tasks: list[str],
    actual_states: dict[str, str],
) -> bool:
    if plan is None:
        return False
    expected = case["oracle"]
    acceptance = expected["acceptance"]
    if plan.decision not in acceptance["allowed_decisions"]:
        return False
    if plan.decision in acceptance["allow_empty_tasks_on"]:
        return not actual_tasks
    if actual_tasks != expected["ground_truth"]["canonical_order"]:
        return False
    if actual_states.get(case["product"]) not in acceptance["allowed_product_states"]:
        return False
    return all(
        actual_states.get(task) == "planned"
        for task in expected["ground_truth"]["canonical_order"]
        if task != case["product"]
    )


def _matches_invariant_acceptance(
    case: dict[str, Any],
    plan: ResearchPlanningDecision | None,
    *,
    actual_tasks: list[str],
    actual_states: dict[str, str],
) -> bool:
    if plan is None:
        return False
    expected = case["oracle"]
    acceptance = expected["acceptance"]
    if plan.decision not in acceptance["allowed_decisions"]:
        return False
    if plan.decision in acceptance["allow_empty_tasks_on"]:
        return not actual_tasks
    if actual_tasks != expected["tasks"]:
        return False
    product = case["product"]
    if actual_states.get(product) not in acceptance["allowed_product_states"]:
        return False
    return all(actual_states.get(task) == "planned" for task in expected["tasks"] if task != product)


def _tool_sequence(
    plan: ResearchPlanningDecision | None,
    *,
    proposed_only: bool = False,
) -> list[dict[str, Any]]:
    if plan is None:
        return []
    status = "proposed_not_executed" if proposed_only else "planned"
    if plan.decision == "reject":
        return [{"tool": "validate_request", "status": "proposed_veto" if proposed_only else "vetoed"}]
    return [
        {"tool": "resolve_aoi", "status": status},
        {"tool": "acquire_vector_sources", "status": status},
        {"tool": "run_fusion_algorithm", "status": status},
        {"tool": "quality_gate", "status": status},
        {"tool": "write_delivery", "status": status},
    ]


def _majority(values: Iterable[bool]) -> bool:
    votes = [bool(value) for value in values]
    return sum(votes) * 2 > len(votes)


def _collapse_replicates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["method"]), str(row["case_id"]))].append(row)
    collapsed: list[dict[str, Any]] = []
    for group in grouped.values():
        group.sort(key=lambda item: int(item.get("replicate_id") or 1))
        passed = _majority(row.get("oracle_pass", False) for row in group)
        representative = next(
            (row for row in group if bool(row.get("oracle_pass")) is passed),
            group[0],
        )
        item = dict(representative)
        item["oracle_pass"] = passed
        item["hard_veto_violated"] = _majority(
            row.get("hard_veto_violated", False) for row in group
        )
        item["stage_status"] = {
            stage: _majority(row["stage_status"][stage] for row in group)
            for stage in ("planning", "aoi", "acquisition", "algorithm", "quality", "delivery")
        }
        empty_reject = _majority(
            bool(
                (row.get("plan") or {}).get("decision") == "reject"
                and not (row.get("plan") or {}).get("tasks")
            )
            for row in group
        )
        if empty_reject:
            item["plan"] = {"decision": "reject", "tasks": [], "uncertainties": [], "evidence": []}
        item["replicate_count"] = len(group)
        item["replicate_pass_count"] = sum(bool(row.get("oracle_pass")) for row in group)
        collapsed.append(item)
    return collapsed


def summarize_rows(
    rows: list[dict[str, Any]],
    *,
    mode: str,
    profile: str = LABELED_EXACT_PROFILE,
) -> dict[str, Any]:
    raw_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        raw_groups[row["method"]].append(row)
    analysis_rows = (
        _collapse_replicates(rows)
        if profile == HELDOUT_CONFIRMATORY_PROFILE
        else rows
    )
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in analysis_rows:
        groups[row["method"]].append(row)
    methods = []
    for method in [*PRIMARY_METHODS, *ABLATIONS]:
        group = groups.get(method, [])
        if not group:
            continue
        stage_rates = {stage: _rate([bool(row["stage_status"][stage]) for row in group]) for stage in ("planning", "aoi", "acquisition", "algorithm", "quality", "delivery")}
        pairs: dict[str, dict[str, bool]] = defaultdict(dict)
        for row in group:
            pairs[row["pair_id"]][row["variant"]] = bool(row["oracle_pass"])
        paired_outcomes = {
            "both_pass": sum(item.get("base") is True and item.get("fault") is True for item in pairs.values()),
            "base_only": sum(item.get("base") is True and item.get("fault") is False for item in pairs.values()),
            "fault_only": sum(item.get("base") is False and item.get("fault") is True for item in pairs.values()),
            "neither": sum(item.get("base") is False and item.get("fault") is False for item in pairs.values()),
        }
        controlled_completion_rate = _rate([all(row["stage_status"].values()) for row in group])
        outcome_metrics = _outcome_metrics(group)
        raw_group = raw_groups[method]
        methods.append({
            "method": method,
            "case_count": len(group),
            "execution_count": len(raw_group),
            "oracle_pass_rate": _rate([row["oracle_pass"] for row in group]),
            "hard_veto_violation_rate": _rate([row["hard_veto_violated"] for row in group]),
            "controlled_completion_rate": controlled_completion_rate,
            "end_to_end_completion_rate": controlled_completion_rate,
            "stage_pass_rates": stage_rates,
            "paired_outcomes": paired_outcomes,
            "average_token_count": sum(row["token_count"] for row in raw_group) / len(raw_group),
            "average_latency_ms": sum(row["latency_ms"] for row in raw_group) / len(raw_group),
            "average_retry_count": sum(row["retry_count"] for row in raw_group) / len(raw_group),
            "outcome_metrics": outcome_metrics,
        })
    by_method = {item["method"]: item for item in methods}
    full_rate = by_method.get("llm_full_contract_kg", {}).get("oracle_pass_rate")
    ablation_drops = {
        method: (full_rate - item["oracle_pass_rate"] if full_rate is not None else None)
        for method, item in by_method.items() if method in ABLATIONS
    }
    full_by_case = {
        row["case_id"]: bool(row["oracle_pass"])
        for row in analysis_rows
        if row["method"] == "llm_full_contract_kg"
    }
    ablation_paired_changes: dict[str, dict[str, int]] = {}
    for method in ABLATIONS:
        method_rows = [row for row in analysis_rows if row["method"] == method and row["case_id"] in full_by_case]
        if not method_rows:
            continue
        ablation_paired_changes[method] = {
            "improved": sum(not full_by_case[row["case_id"]] and bool(row["oracle_pass"]) for row in method_rows),
            "regressed": sum(full_by_case[row["case_id"]] and not bool(row["oracle_pass"]) for row in method_rows),
            "unchanged": sum(full_by_case[row["case_id"]] == bool(row["oracle_pass"]) for row in method_rows),
        }
    return {
        "mode": mode,
        "evaluation_profile": profile,
        "claim_eligible": mode == "live",
        "row_count": len(rows),
        "total_retry_count": sum(int(row.get("retry_count") or 0) for row in rows),
        "methods": methods,
        "ablation_drops_vs_full_contract_kg": ablation_drops,
        "ablation_paired_changes_vs_full_contract_kg": ablation_paired_changes,
    }


def _outcome_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    base_rows = [row for row in rows if row.get("variant") == "base"]
    fault_rows = [row for row in rows if row.get("variant") == "fault"]

    def plan_decision(row: dict[str, Any]) -> str | None:
        plan = row.get("plan") or {}
        return plan.get("decision")

    def empty_reject(row: dict[str, Any]) -> bool:
        plan = row.get("plan") or {}
        return plan.get("decision") == "reject" and not plan.get("tasks")

    base_normal = [
        bool(row.get("oracle_pass")) and plan_decision(row) == "plan"
        for row in base_rows
    ]
    fault_handled = [bool(row.get("oracle_pass")) for row in fault_rows]
    veto_rows = [row for row in fault_rows if (row.get("oracle") or {}).get("hard_veto")]
    veto_triggered = [empty_reject(row) for row in veto_rows]
    safe_rejections = []
    constrained_rows = []
    constrained_correct = []
    e2e_rows = []
    e2e_completed = []
    for row in fault_rows:
        oracle = row.get("oracle") or {}
        acceptance = oracle.get("acceptance") or {}
        if empty_reject(row) and "reject" in acceptance.get("allowed_decisions", []) and "reject" in acceptance.get("allow_empty_tasks_on", []):
            safe_rejections.append(True)
        else:
            safe_rejections.append(False)
        constrained_decisions = set(acceptance.get("allowed_decisions", [])) - {"plan", "reject"}
        constrained_states = set(acceptance.get("allowed_product_states", [])) - {"planned", "rejected"}
        if not oracle.get("hard_veto") and constrained_decisions and constrained_states:
            constrained_rows.append(row)
            state = ((row.get("plan") or {}).get("tasks") or [])
            product = row.get("product")
            product_state = next((item.get("delivery_state") for item in state if item.get("task_kind") == product), None)
            constrained_correct.append(
                bool(row.get("oracle_pass"))
                and plan_decision(row) in constrained_decisions
                and product_state in constrained_states
            )
        execution_mode = row.get("tool_execution_mode")
        if execution_mode == "executed":
            e2e_rows.append(row)
            e2e_completed.append(
                bool(row.get("final_delivery_state") in {"delivered", "completed"})
                and bool(row.get("oracle_pass"))
            )

    return {
        "base_normal_planning_rate": _rate(base_normal),
        "base_normal_planning_count": sum(base_normal),
        "base_normal_planning_denominator": len(base_normal),
        "fault_handling_rate": _rate(fault_handled),
        "fault_handling_count": sum(fault_handled),
        "fault_handling_denominator": len(fault_handled),
        "hard_veto_correct_trigger_rate": _rate(veto_triggered),
        "hard_veto_correct_trigger_count": sum(veto_triggered),
        "hard_veto_correct_trigger_denominator": len(veto_triggered),
        "safe_rejection_rate": _rate(safe_rejections),
        "safe_rejection_count": sum(safe_rejections),
        "safe_rejection_denominator": len(safe_rejections),
        "constrained_delivery_correct_rate": _rate(constrained_correct),
        "constrained_delivery_correct_count": sum(constrained_correct),
        "constrained_delivery_correct_denominator": len(constrained_correct),
        "actual_e2e_completion_rate": _rate(e2e_completed) if e2e_rows else None,
        "actual_e2e_completion_count": sum(e2e_completed),
        "actual_e2e_completion_denominator": len(e2e_completed),
        "actual_e2e_status": "executed" if e2e_rows else "not_executed",
    }


def _wilson_interval(successes: int, total: int, *, z: float = 1.959963984540054) -> list[float] | None:
    if total == 0:
        return None
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def _mcnemar_exact_p(full_wins: int, comparator_wins: int) -> float:
    discordant = full_wins + comparator_wins
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, index) for index in range(0, min(full_wins, comparator_wins) + 1))
    return min(1.0, 2.0 * tail / (2**discordant))


def _cluster_bootstrap_difference(
    full: dict[str, dict[str, Any]],
    comparator: dict[str, dict[str, Any]],
    *,
    iterations: int = 10000,
    seed: int = 20260905,
) -> list[float] | None:
    shared_ids = sorted(set(full) & set(comparator))
    families = sorted({str(full[case_id]["family"]) for case_id in shared_ids})
    if not families:
        return None
    by_family = {
        family: [case_id for case_id in shared_ids if str(full[case_id]["family"]) == family]
        for family in families
    }
    rng = random.Random(seed)
    samples: list[float] = []
    for _ in range(iterations):
        selected = [rng.choice(families) for _ in families]
        differences = [
            float(bool(full[case_id]["oracle_pass"])) - float(bool(comparator[case_id]["oracle_pass"]))
            for family in selected
            for case_id in by_family[family]
        ]
        samples.append(sum(differences) / len(differences))
    samples.sort()
    return [samples[int(0.025 * iterations)], samples[min(iterations - 1, int(0.975 * iterations))]]


def confirmatory_statistics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    collapsed = _collapse_replicates(rows)
    by_method: dict[str, list[dict[str, Any]]] = defaultdict(list)
    raw_by_method_case: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in collapsed:
        by_method[row["method"]].append(row)
    for row in rows:
        raw_by_method_case[(str(row["method"]), str(row["case_id"]))].append(row)

    methods: list[dict[str, Any]] = []
    for method in PRIMARY_METHODS:
        group = by_method.get(method, [])
        if not group:
            continue
        base = [row for row in group if row["variant"] == "base"]
        fault = [row for row in group if row["variant"] == "fault"]
        consistent = [
            len({bool(item["oracle_pass"]) for item in raw_by_method_case[(method, row["case_id"])]}) == 1
            for row in group
        ]
        fault_passes = sum(bool(row["oracle_pass"]) for row in fault)
        methods.append(
            {
                "method": method,
                "case_count": len(group),
                "execution_count": sum(len(raw_by_method_case[(method, row["case_id"])]) for row in group),
                "base_majority_pass_rate": _rate([row["oracle_pass"] for row in base]),
                "base_majority_pass_count": sum(bool(row["oracle_pass"]) for row in base),
                "base_denominator": len(base),
                "fault_majority_pass_rate": _rate([row["oracle_pass"] for row in fault]),
                "fault_majority_pass_count": fault_passes,
                "fault_denominator": len(fault),
                "fault_wilson_95": _wilson_interval(fault_passes, len(fault)),
                "replicate_outcome_consistency_rate": _rate(consistent),
            }
        )

    fault_maps = {
        method: {
            str(row["case_id"]): row
            for row in group
            if row["variant"] == "fault"
        }
        for method, group in by_method.items()
    }
    full = fault_maps.get("llm_full_contract_kg", {})
    comparisons: list[dict[str, Any]] = []
    for comparator_name in ("llm_only", "llm_capability_kg", "rules_only", "fixed_workflow"):
        comparator = fault_maps.get(comparator_name, {})
        shared = sorted(set(full) & set(comparator))
        full_wins = sum(full[item]["oracle_pass"] and not comparator[item]["oracle_pass"] for item in shared)
        comparator_wins = sum(comparator[item]["oracle_pass"] and not full[item]["oracle_pass"] for item in shared)
        difference = (
            sum(bool(full[item]["oracle_pass"]) for item in shared)
            - sum(bool(comparator[item]["oracle_pass"]) for item in shared)
        ) / len(shared) if shared else 0.0
        comparisons.append(
            {
                "comparator": comparator_name,
                "fault_case_count": len(shared),
                "difference_vs_full_kg": difference,
                "full_kg_only_pass": full_wins,
                "comparator_only_pass": comparator_wins,
                "mcnemar_exact_p": _mcnemar_exact_p(full_wins, comparator_wins),
                "scenario_cluster_bootstrap_95": _cluster_bootstrap_difference(full, comparator),
            }
        )

    scenarios: list[dict[str, Any]] = []
    families = sorted({str(row["family"]) for row in collapsed})
    for family in families:
        entry: dict[str, Any] = {"scenario": family}
        for method in PRIMARY_METHODS:
            group = [
                row for row in by_method.get(method, [])
                if row["family"] == family and row["variant"] == "fault"
            ]
            if group:
                entry[method] = {
                    "passes": sum(bool(row["oracle_pass"]) for row in group),
                    "total": len(group),
                }
        scenarios.append(entry)
    return {
        "analysis_unit": "case-level majority across exact-input LLM replicates",
        "llm_replicates": max(
            (len(group) for (method, _case_id), group in raw_by_method_case.items() if _is_llm_method(method)),
            default=0,
        ),
        "bootstrap": {"cluster": "scenario", "iterations": 10000, "seed": 20260905},
        "methods": methods,
        "paired_fault_comparisons": comparisons,
        "scenario_fault_results": scenarios,
    }


def render_confirmatory_statistics(stats: dict[str, Any]) -> str:
    lines = [
        "# Held-out Confirmatory Statistics",
        "",
        "Primary rates are case-level majority outcomes across exact-input LLM replicates. Wilson intervals describe case-level fault pass rates; paired differences use scenario-cluster bootstrap intervals. McNemar p-values are descriptive because cases within a scenario are structurally related.",
        "",
        "| Method | Cases | Executions | Base majority | Fault majority | Fault Wilson 95% | Replicate consistency |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in stats["methods"]:
        interval = item["fault_wilson_95"] or [0.0, 0.0]
        lines.append(
            f"| {item['method']} | {item['case_count']} | {item['execution_count']} | {item['base_majority_pass_rate']:.3f} ({item['base_majority_pass_count']}/{item['base_denominator']}) | {item['fault_majority_pass_rate']:.3f} ({item['fault_majority_pass_count']}/{item['fault_denominator']}) | [{interval[0]:.3f}, {interval[1]:.3f}] | {item['replicate_outcome_consistency_rate']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Paired Fault Differences",
            "",
            "Positive differences favor `llm_full_contract_kg`.",
            "",
            "| Comparator | Difference | Scenario-cluster bootstrap 95% | Full-only | Comparator-only | McNemar exact p |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in stats["paired_fault_comparisons"]:
        interval = item["scenario_cluster_bootstrap_95"] or [0.0, 0.0]
        lines.append(
            f"| {item['comparator']} | {item['difference_vs_full_kg']:.3f} | [{interval[0]:.3f}, {interval[1]:.3f}] | {item['full_kg_only_pass']} | {item['comparator_only_pass']} | {item['mcnemar_exact_p']:.6f} |"
        )
    lines.extend(
        [
            "",
            "## Scenario Fault Results",
            "",
            "| Scenario | llm_only | llm_capability_kg | llm_full_contract_kg | rules_only | fixed_workflow |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in stats["scenario_fault_results"]:
        cells = []
        for method in PRIMARY_METHODS:
            value = item.get(method) or {"passes": 0, "total": 0}
            cells.append(f"{value['passes']}/{value['total']}")
        lines.append(f"| {item['scenario']} | {' | '.join(cells)} |")
    return "\n".join(lines) + "\n"


def render_main_table(summary: dict[str, Any]) -> str:
    completion_label = "Controlled completion" if summary.get("evaluation_profile") in V3_LIKE_PROFILES else "End-to-end"
    lines = [
        "# Main Comparison",
        "",
        "Base and fault members are reported separately so clean-case planning does not mask failure handling. `Oracle pass` is retained as a secondary aggregate only.",
        "",
        f"| Method | Cases | Base normal | Fault-only | Oracle pass (secondary) | Hard-veto violation | {completion_label} | Planning | AOI | Acquisition | Algorithm | Quality | Delivery |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in summary["methods"]:
        if item["method"] not in PRIMARY_METHODS:
            continue
        rates = item["stage_pass_rates"]
        outcome = item["outcome_metrics"]

        def fmt(metric: str) -> str:
            value = outcome[f"{metric}_rate"]
            count = outcome[f"{metric}_count"]
            denominator = outcome[f"{metric}_denominator"]
            return f"{value:.3f} ({count}/{denominator})" if value is not None else f"n/a ({count}/{denominator})"

        lines.append(
            "| {method} | {case_count} | {base_normal} | {fault_only} | {oracle_pass_rate:.3f} | {hard_veto_violation_rate:.3f} | {end_to_end_completion_rate:.3f} | {planning:.3f} | {aoi:.3f} | {acquisition:.3f} | {algorithm:.3f} | {quality:.3f} | {delivery:.3f} |".format(
                **item,
                **rates,
                base_normal=fmt("base_normal_planning"),
                fault_only=fmt("fault_handling"),
            )
        )
    return "\n".join(lines) + "\n"


def render_outcome_metrics(summary: dict[str, Any]) -> str:
    lines = [
        "# Outcome Metrics",
        "",
        "Rates use separate denominators: base members for normal planning, fault members for fault handling and safe rejection, hard-veto fault members for veto triggering, non-veto constrained fault members for constrained delivery. Actual E2E is null when tools were not executed.",
        "",
        "| Method | Base normal planning | Fault handling | Hard-veto trigger | Safe rejection | Constrained delivery | Actual E2E | E2E status |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in summary["methods"]:
        metrics = item["outcome_metrics"]

        def fmt(value: Any) -> str:
            return "n/a" if value is None else f"{value:.3f}"

        lines.append(
            f"| {item['method']} | {fmt(metrics['base_normal_planning_rate'])} ({metrics['base_normal_planning_count']}/{metrics['base_normal_planning_denominator']}) | {fmt(metrics['fault_handling_rate'])} ({metrics['fault_handling_count']}/{metrics['fault_handling_denominator']}) | {fmt(metrics['hard_veto_correct_trigger_rate'])} ({metrics['hard_veto_correct_trigger_count']}/{metrics['hard_veto_correct_trigger_denominator']}) | {fmt(metrics['safe_rejection_rate'])} ({metrics['safe_rejection_count']}/{metrics['safe_rejection_denominator']}) | {fmt(metrics['constrained_delivery_correct_rate'])} ({metrics['constrained_delivery_correct_count']}/{metrics['constrained_delivery_correct_denominator']}) | {fmt(metrics['actual_e2e_completion_rate'])} ({metrics['actual_e2e_completion_count']}/{metrics['actual_e2e_completion_denominator']}) | {metrics['actual_e2e_status']} |"
        )
    return "\n".join(lines) + "\n"


def render_experiment_plan(summary: dict[str, Any]) -> str:
    lines = [
            "# Experiment Plan",
            "",
            f"Profile: `{summary['evaluation_profile']}`; rows: `{summary['row_count']}`.",
            "",
            "## Metrics",
            "",
            "1. Base normal planning rate: base members with a correct unrestricted `plan` / all base members.",
            "2. Fault handling rate: fault members accepted by the case oracle / all fault members.",
            "3. Hard-veto correct trigger rate: expected hard-veto faults with `reject` and empty tasks / hard-veto fault members.",
            "4. Safe rejection rate: fault members where an empty `reject` is explicitly allowed by the oracle / all fault members.",
            "5. Constrained delivery correctness: non-veto fault members requiring a constrained decision, correctly matched to the allowed decision and product state / those members.",
            "6. Actual E2E completion rate: executed tool runs reaching delivered/completed state / executed tool runs; `n/a` when tools are not executed.",
            "",
            "## Metric rationale",
            "",
            "The earlier aggregate pass rate mixed clean base members with fault members, so a method could score highly by planning ordinary cases while failing to handle faults. It is retained only for historical comparability; the six metrics above use explicit denominators and are the primary interpretation.",
            "",
    ]
    if summary.get("evaluation_profile") == ADVERSARIAL_PROFILE:
        lines.extend(
            [
                "## Adversarial coverage",
                "",
                "This profile contains 12 scenarios, 5 repetitions per scenario, 5 products, 60 base/fault pairs, and 120 members. Fault members target baseline blind spots without exposing a fault label: priority conflict, mixed alias crosswalk, partial source outage, exhausted timeout, quality provisional state, required-field loss, incomplete evidence, incompatible algorithm, delivery blockage, non-explicit veto, contradictory candidate plan, and fallback-channel blockage.",
                "",
                "The clean base member of every pair remains canonical and fully usable. This preserves a separate normal-planning denominator while the fault denominator measures robustness under the corresponding adversarial perturbation.",
                "",
            ]
        )
    elif summary.get("evaluation_profile") == HELDOUT_CONFIRMATORY_PROFILE:
        lines.extend(
            [
                "## Held-out confirmatory coverage",
                "",
                "The runner loaded a frozen external case file containing 12 scenarios, 5 products, 2 independently authored instances per scenario-product cell, 120 base/fault pairs, and 240 members. LLM conditions use three exact-input replicates; deterministic baselines run once. Primary inference uses case-level majority outcomes and scenario-cluster bootstrap intervals.",
                "",
            ]
        )
    lines.extend(
        [
            "## Boundary",
            "",
            "The current profile records planning and oracle outcomes. Tool sequences are proposed only; no external source acquisition, algorithm execution, quality computation, or delivery writeback is performed. Future user-supplied real cases should be appended as a versioned profile without changing these denominators retroactively.",
            "",
        ]
    )
    return "\n".join(lines)


def render_case_catalog(rows: list[dict[str, Any]]) -> str:
    seen: set[str] = set()
    lines = ["# Case Catalog", "", "Generated cases are production-like controlled stress cases; each pair has one base and one multi-constraint fault member.", "", "| Pair | Variant | Product | Requested products | Perturbation tags |", "| --- | --- | --- | --- | --- |"]
    for row in rows:
        case_id = str(row.get("case_id"))
        if case_id in seen:
            continue
        seen.add(case_id)
        request = row.get("raw_request") or {}
        lines.append(
            f"| {row.get('pair_id')} | {row.get('variant')} | {row.get('product')} | {', '.join(str(item) for item in request.get('products', []))} | {', '.join(str(item) for item in row.get('perturbation_tags', [])) or 'none'} |"
        )
    return "\n".join(lines) + "\n"


def render_ablation_table(summary: dict[str, Any]) -> str:
    by_method = {item["method"]: item for item in summary["methods"]}
    lines = ["# KG Ablation", "", "| Condition | Oracle pass | Drop vs full KG | Improved | Regressed | Unchanged | Hard-veto violation | Controlled completion |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for method in ("llm_full_contract_kg", *ABLATIONS):
        item = by_method.get(method)
        if item is None:
            continue
        drop = summary["ablation_drops_vs_full_contract_kg"].get(method, 0.0)
        changes = summary["ablation_paired_changes_vs_full_contract_kg"].get(method, {})
        lines.append(f"| {method} | {item['oracle_pass_rate']:.3f} | {drop:.3f} | {changes.get('improved', 0)} | {changes.get('regressed', 0)} | {changes.get('unchanged', item['case_count'])} | {item['hard_veto_violation_rate']:.3f} | {item['controlled_completion_rate']:.3f} |")
    return "\n".join(lines) + "\n"


def render_conclusion(summary: dict[str, Any]) -> str:
    if not summary["claim_eligible"]:
        provider = summary.get("provider") or {}
        if summary["mode"] == "live" and provider.get("failure_classes"):
            failures = ", ".join(provider["failure_classes"])
            return f"# Conclusion\n\nThe live-provider run is not claim-eligible: {provider.get('complete_llm_call_count', 0)}/{provider.get('llm_call_count', 0)} LLM rows passed transport, strict-JSON, schema, model-identity, and usage checks. Failure classes: `{failures}`. No effectiveness conclusion is admitted from this run.\n"
        return "# Conclusion\n\nThis is a deterministic local harness result. It validates case generation, trace capture, oracle aggregation, and report production only. Read the fault-only metric separately from clean base planning; the harness cannot answer whether KG + LLM is effective until the same run is executed with `--mode live` and a recorded provider/model.\n"
    by_method = {item["method"]: item for item in summary["methods"]}
    full = by_method["llm_full_contract_kg"]

    def fmt(method: str, metric: str) -> str:
        item = by_method.get(method)
        if item is None:
            return "n/a"
        outcome = item["outcome_metrics"]
        value = outcome[f"{metric}_rate"]
        return "n/a" if value is None else f"{value:.3f} ({outcome[f'{metric}_count']}/{outcome[f'{metric}_denominator']})"

    return "\n".join(
        [
            "# Conclusion",
            "",
            "The recorded live-provider result should be read through the fault-only metric; aggregate `oracle pass` is secondary because it mixes clean base and fault members.",
            "",
            f"- `llm_full_contract_kg`: base normal {fmt('llm_full_contract_kg', 'base_normal_planning')}; fault-only {fmt('llm_full_contract_kg', 'fault_handling')}; aggregate oracle pass {full['oracle_pass_rate']:.3f}.",
            f"- `rules_only`: base normal {fmt('rules_only', 'base_normal_planning')}; fault-only {fmt('rules_only', 'fault_handling')}; its aggregate score is dominated by clean base members.",
            f"- `fixed_workflow`: base normal {fmt('fixed_workflow', 'base_normal_planning')}; fault-only {fmt('fixed_workflow', 'fault_handling')}; it is a clean-case reference, not a fault-handling method.",
            "",
            "Ablation drops and fault-handling rates are controlled planning-replay evidence, not external geospatial delivery evidence. Actual E2E remains `n/a` when tools are not executed.",
            "",
        ]
    )


def _representative(rows: Iterable[dict[str, Any]], *, passed: bool) -> dict[str, Any]:
    for row in rows:
        if bool(row["oracle_pass"]) is passed:
            return row
    return {"status": "no_matching_trace"}


def _job_type(product: str):
    from schemas.fusion import JobType
    return JobType.water if product in {"water_polygon", "waterways"} else JobType(product)


def _source_id(disaster_type: str, product: str) -> str:
    return f"catalog.{disaster_type}.{product}"


def _estimate_tokens(*values: Any) -> int:
    return max(1, len(json.dumps(values, ensure_ascii=False, sort_keys=True).encode("utf-8")) // 4)


def _rate(values: list[bool]) -> float:
    return sum(bool(value) for value in values) / len(values) if values else 0.0


def _apply_dotenv_defaults() -> None:
    """Load repository .env values without overriding explicit process values."""
    for key, value in read_dotenv_defaults().items():
        if value and not os.getenv(key):
            os.environ[key] = value


def _live_provider() -> OpenAICompatibleProvider:
    _apply_dotenv_defaults()
    return OpenAICompatibleProvider(
        api_key=_required_env("OPENAI_API_KEY", "GEOFUSION_LLM_API_KEY"),
        model=_required_env("GEOFUSION_LLM_MODEL"),
        base_url=os.getenv("GEOFUSION_LLM_BASE_URL", "https://api.openai.com/v1"),
        timeout_sec=int(os.getenv("GEOFUSION_LLM_TIMEOUT_SEC", "60")),
        allow_json_salvage=False,
        max_output_tokens=int(os.getenv("GEOFUSION_LLM_MAX_OUTPUT_TOKENS", "8192")),
        temperature=float(os.getenv("GEOFUSION_LLM_TEMPERATURE", "0.1")),
    )


def _provider_config(provider: OpenAICompatibleProvider | None) -> dict[str, Any] | None:
    if provider is None:
        return None
    return {
        "model": provider.model,
        "base_url_host": provider.base_url.split("//", 1)[-1].split("/", 1)[0],
        "timeout_sec": provider.timeout_sec,
        "max_output_tokens": provider.max_output_tokens,
        "temperature": provider.temperature,
        "allow_json_salvage": provider.allow_json_salvage,
    }


def _source_state() -> dict[str, Any]:
    def git(*args: str) -> str | None:
        completed = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip() if completed.returncode == 0 else None

    status = git("status", "--porcelain")
    files = [
        Path(__file__).resolve(),
        (REPO_ROOT / "llm" / "providers" / "openai_compatible.py").resolve(),
    ]
    return {
        "git_commit": git("rev-parse", "HEAD"),
        "git_dirty": bool(status),
        "tracked_and_untracked_status_hash": semantic_hash(status or ""),
        "source_file_hashes": {
            str(path.relative_to(REPO_ROOT)).replace("\\", "/"): sha256_file(path)
            for path in files
        },
    }


def _required_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    raise RuntimeError(f"Missing required environment variable: {' or '.join(names)}")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the compact KG + LLM comparison and ablation experiment.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("local", "live"), default="local")
    parser.add_argument("--case-limit", type=int, default=None, help="Even number retaining complete base/fault pairs.")
    parser.add_argument("--no-ablations", action="store_true")
    parser.add_argument("--profile", choices=EXPERIMENT_PROFILES, default=LABELED_EXACT_PROFILE)
    parser.add_argument("--methods", nargs="+", choices=ALL_METHODS, default=None)
    parser.add_argument("--pair-ids", nargs="+", default=None)
    parser.add_argument("--workers", type=int, default=1, help="Concurrent case/method workers; use 1 for serial execution.")
    parser.add_argument("--case-file", type=Path, default=None, help="Frozen JSON case file for heldout_confirmatory_v1.")
    parser.add_argument("--llm-replicates", type=int, default=1, help="Positive odd exact-input replicate count for LLM methods.")
    parser.add_argument("--resume-failed", action="store_true", help="Retry only failed live LLM calls in an existing output directory.")
    parser.add_argument("--resume-transport-only", action="store_true", help="With --resume-failed, retry only HTTP or transport failures; preserve model output/schema failures.")
    args = parser.parse_args(argv)
    if args.case_limit is not None and args.case_limit % 2:
        parser.error("--case-limit must be even to keep paired members")
    if args.resume_failed:
        summary = resume_failed_calls(args.output, transport_only=args.resume_transport_only)
    else:
        summary = run_experiment(
            args.output,
            mode=args.mode,
            case_limit=args.case_limit,
            include_ablations=not args.no_ablations,
            profile=args.profile,
            selected_methods=args.methods,
            selected_pair_ids=args.pair_ids,
            invocation=[sys.executable, *sys.argv],
            max_workers=args.workers,
            case_file=args.case_file,
            llm_replicates=args.llm_replicates,
        )
    print(json.dumps({"output": str(args.output.resolve()), "rows": summary["row_count"], "claim_eligible": summary["claim_eligible"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
