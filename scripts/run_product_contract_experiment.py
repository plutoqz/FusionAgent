from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from llm.providers.base import LLMProvider
from llm.providers.openai_compatible import OpenAICompatibleProvider
from schemas.product_contract_experiment import (
    ProductContractGold,
    StructuredPlanningDecision,
)
from schemas.product_contract_runtime import ExperimentExecutionMode
from services.product_contract_runtime_service import ProductContractRuntimeExecutor
from utils.local_runtime import read_dotenv_defaults

DEFAULT_CASES_PATH = REPO_ROOT / "docs/thesis/experiment_cases.json"
DEFAULT_GOLD_PATH = REPO_ROOT / "docs/thesis/experiment_gold.json"
DEFAULT_ENV_PATH = REPO_ROOT / ".env.local"
LLM_PLANNERS = {
    "llm_only",
    "llm_capability_kg",
    "llm_full_contract_kg",
}
VALID_PLANNERS = {"fixed", "kg_only", *LLM_PLANNERS}
PLANNER_PROMPT_VERSION = "product-contract-planner.v2"
PLANNING_PROTOCOL_VERSION = "product-contract-decision.v2"
LLM_CALLING_POLICY = {
    "temperature": 0.1,
    "response_format": "json_object",
    "grounding_repair_retries": 1,
}
PLANNER_KNOWLEDGE_PROFILES = {
    "fixed": {
        "profile_id": "fixed_no_knowledge",
        "kg_layers": [],
    },
    "kg_only": {
        "profile_id": "deterministic_full_contract_kg",
        "kg_layers": ["L1", "L2", "L3", "L4", "L6"],
    },
    "llm_only": {
        "profile_id": "llm_no_kg",
        "kg_layers": [],
    },
    "llm_capability_kg": {
        "profile_id": "llm_capability_kg",
        "kg_layers": ["L3", "L4"],
    },
    "llm_full_contract_kg": {
        "profile_id": "llm_full_contract_kg",
        "kg_layers": ["L1", "L2", "L3", "L4", "L6"],
    },
}

FIXED_LAYER_ORDER = ["building", "road", "water_type_1", "water_type_2", "poi"]
CRITICALITY_RANK = {"critical": 0, "important": 1, "optional": 2}
VALID_STRATEGY_IDS = {
    "fixed_global_order",
    "criticality_coverage_heuristic",
    "progressive_delivery",
    "critical_first_degraded_delivery",
    "absence_aware_triage",
    "coverage_first_progressive",
    "conflict_aware_fusion",
    "quality_fallback_delivery",
}


class LLMPlanningFailure(ValueError):
    def __init__(
        self,
        message: str,
        *,
        raw_responses: list[dict[str, Any]],
        grounding_failures: list[str],
        planning_attempts: list[dict[str, Any]],
    ) -> None:
        super().__init__(message)
        self.raw_responses = raw_responses
        self.grounding_failures = grounding_failures
        self.planning_attempts = planning_attempts


SOURCE_PROBLEM_TO_GAP = {
    "delayed": "source_unavailable",
    "data_absent": "data_absent",
    "source_mismatch": "source_mismatch",
    "stale": "source_mismatch",
    "conflicting": "quality_failed",
    "quality_failed": "quality_failed",
}

LLM_PLANNER_SYSTEM_PROMPT = """
You are the constrained planning component for a disaster-response vector-data
product experiment. Return one JSON object only.

Use only layers, algorithms, data sources, delivery modes, gap types, and
strategy identifiers present in the supplied planning context. Do not invent
capabilities. Layers inside one priority tier are unordered. Every required
layer must occur exactly once across all priority tiers and exactly once in
layer_decisions. Treat the supplied strategy and gap definitions as output
protocol semantics shared by every baseline, not as case-specific advice.

Allowed delivery modes: final, provisional, degraded, background_pending,
not_delivered.

Required JSON shape:
{
  "strategy_id": "allowed_strategy_id",
  "priority_tiers": [["layer_id"]],
  "initial_delivery_layers": ["layer_id"],
  "background_completion_layers": ["layer_id"],
  "not_delivered_layers": ["layer_id"],
  "layer_decisions": [
    {
      "layer": "layer_id",
      "selected_algorithm": "algorithm_id",
      "selected_sources": ["source_id"],
      "delivery_mode": "allowed_mode"
    }
  ],
  "planner_gap_proposal": [
    {
      "layer": "layer_id",
      "gap_type": "allowed_gap_type",
      "source_id": "grounded_source_id_or_null",
      "reason": "evidence-grounded reason"
    }
  ],
  "supersession_plan": [
    {
      "layer": "background_completion_layer_id",
      "target_delivery_mode": "final",
      "trigger_source_ids": ["grounded_source_id"],
      "condition": "observable completion condition"
    }
  ],
  "rationale": "constraint-grounded explanation"
}

When time is tight, prefer a usable provisional or degraded delivery over
waiting indefinitely. A layer with no usable source may be not_delivered. A
known source problem must never be hidden by claiming an unqualified final
delivery. Propose a gap only when the supplied source status supports its gap
type. If support remains uncertain, omit the proposal instead of guessing a gap
type; a grounded omission is allowed and will reduce recall. Deterministic
verification will not add the omitted proposal to the planner score. Background
completion may overlap initial delivery for a provisional or degraded product.
Every supersession entry must refer to a background-completion layer. Apply
these set rules exactly:
- final, provisional, and degraded layers must be in initial_delivery_layers;
- background_pending layers must be in background_completion_layers and not in
  initial_delivery_layers;
- not_delivered layers must be in not_delivered_layers and must not be in
  initial_delivery_layers or background_completion_layers;
- background completion may overlap initial delivery only for provisional or
  degraded layers;
- every required layer must be accounted for by the union of initial,
  background, and not-delivered sets.
""".strip()

LLM_PLANNER_REPAIR_SYSTEM_PROMPT = f"""
{LLM_PLANNER_SYSTEM_PROMPT}

The previous response failed schema or grounding validation. Return a complete
replacement JSON object, not a patch. Use the supplied validation error to fix
the response. Do not copy an invalid delivery-set placement into the repaired
object. If an unsupported gap proposal cannot be grounded from the context,
remove it rather than replacing it with another guessed gap type.
""".strip()


def load_cases(path: Path = DEFAULT_CASES_PATH) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError(f"Case file {path} must contain a 'cases' list.")
    return cases


def load_gold(path: Path = DEFAULT_GOLD_PATH) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    gold = payload.get("gold")
    if not isinstance(gold, list):
        raise ValueError(f"Gold file {path} must contain a 'gold' list.")
    return gold


def find_case(cases: list[dict[str, Any]], case_id: str) -> dict[str, Any]:
    for case in cases:
        if case.get("case_id") == case_id:
            return case
    known = ", ".join(str(case.get("case_id")) for case in cases)
    raise KeyError(f"Unknown case_id {case_id!r}. Known cases: {known}")


def find_gold(gold_rows: list[dict[str, Any]], case_id: str) -> dict[str, Any]:
    for row in gold_rows:
        if row.get("case_id") == case_id:
            return row
    known = ", ".join(str(row.get("case_id")) for row in gold_rows)
    raise KeyError(f"Unknown gold case_id {case_id!r}. Known cases: {known}")


def run_product_contract_experiment(
    *,
    case: dict[str, Any],
    planner: str,
    output_dir: Path,
    llm_provider: LLMProvider | None = None,
    gold: dict[str, Any] | None = None,
    input_variant: int = 0,
    execution_mode: str = ExperimentExecutionMode.PLANNING_ONLY.value,
    runtime_executor: ProductContractRuntimeExecutor | None = None,
) -> dict[str, Any]:
    if planner not in VALID_PLANNERS:
        raise ValueError(f"planner must be one of {sorted(VALID_PLANNERS)}")
    execution_mode = ExperimentExecutionMode(execution_mode).value

    run_started_at = _utc_now()
    run_started = time.perf_counter()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    product_contract = build_product_contract(case)
    resource_regime = build_resource_regime(case)
    planning_context = build_planning_context(
        case,
        product_contract,
        resource_regime,
        planner=planner,
        input_variant=input_variant,
    )
    try:
        planning_decision = build_planning_decision(
            case,
            planner,
            planning_context,
            llm_provider=llm_provider,
        )
    except Exception as exc:
        if planner in LLM_PLANNERS:
            _write_json(
                output_dir / "planning_failure.json",
                {
                    "case_id": case["case_id"],
                    "planner": planner,
                    "input_variant": input_variant,
                    "prompt_version": PLANNER_PROMPT_VERSION,
                    "prompt_hash": _hash_text(LLM_PLANNER_SYSTEM_PROMPT),
                    "planning_protocol_version": PLANNING_PROTOCOL_VERSION,
                    "knowledge_profile": PLANNER_KNOWLEDGE_PROFILES[planner],
                    "calling_policy": LLM_CALLING_POLICY,
                    "context_hash": _hash_json(planning_context),
                    "planning_provider": (
                        llm_provider.provider_name if llm_provider is not None else None
                    ),
                    "planning_model": (
                        llm_provider.last_model if llm_provider is not None else None
                    ),
                    "failure_type": type(exc).__name__,
                    "failure_reason": str(exc),
                    "started_at": run_started_at,
                    "failed_at": _utc_now(),
                    "duration_ms": (time.perf_counter() - run_started) * 1000,
                    "raw_llm_responses": getattr(exc, "raw_responses", []),
                    "grounding_failures": getattr(exc, "grounding_failures", []),
                    "planning_attempts": getattr(exc, "planning_attempts", []),
                },
            )
        raise
    planner_gap_proposal = build_planner_gap_proposal(case, planning_decision)
    runtime_execution = None
    if execution_mode == ExperimentExecutionMode.END_TO_END.value:
        runtime_executor = runtime_executor or ProductContractRuntimeExecutor(
            repo_root=REPO_ROOT,
            artifact_registry_path=output_dir / "runtime_artifact_index.json",
            cache_dir=output_dir / "runtime_cache",
        )
        try:
            runtime_execution = runtime_executor.execute(
                case=case,
                planning_decision=planning_decision,
                output_dir=output_dir,
            )
        except Exception as exc:
            _write_json(
                output_dir / "runtime_failure.json",
                {
                    "case_id": case["case_id"],
                    "planner": planner,
                    "execution_mode": execution_mode,
                    "failure_type": type(exc).__name__,
                    "failure_reason": str(exc),
                    "failed_at": _utc_now(),
                },
            )
            raise
        quality_gate_result = build_runtime_quality_gate_result(
            case,
            planning_decision,
            runtime_execution,
        )
    else:
        quality_gate_result = build_quality_gate_result(case, planning_decision)
    gap_verification = build_gap_verification(
        case,
        planning_decision,
        planner_gap_proposal,
    )
    gap_declaration = build_gap_declaration(
        case,
        planning_decision,
        quality_gate_result,
        runtime_execution=runtime_execution,
    )
    evidence_trace = build_evidence_trace(
        case,
        product_contract,
        planning_decision,
        quality_gate_result,
        gap_verification,
        gap_declaration,
        execution_mode=execution_mode,
        runtime_execution=runtime_execution,
    )
    delivery_manifest = build_delivery_manifest(
        case,
        product_contract,
        planning_decision,
        quality_gate_result,
        gap_declaration,
        evidence_trace,
        execution_mode=execution_mode,
        runtime_execution=runtime_execution,
    )
    evaluation_result = evaluate_against_gold(
        case=case,
        planning_decision=planning_decision,
        gold=gold,
    )
    summary = {
        "case_id": case["case_id"],
        "planner": planner,
        "execution_mode": execution_mode,
        "runtime_status": (
            runtime_execution.get("status") if runtime_execution is not None else None
        ),
        "input_variant": input_variant,
        "satisfaction_state": delivery_manifest["satisfaction_state"],
        "gap_count": len(gap_declaration["gaps"]),
        "delivered_layers": delivery_manifest["delivered_layers"],
        "planning_provider": planning_decision["planning_provider"],
        "planning_model": planning_decision.get("planning_model"),
        "knowledge_profile": planning_decision["knowledge_profile"]["profile_id"],
        "prompt_version": planning_decision.get("prompt_version"),
        "context_hash": planning_decision.get("context_hash"),
        "planning_retry_count": planning_decision.get("planning_retry_count", 0),
        "started_at": run_started_at,
        "completed_at": _utc_now(),
        "duration_ms": (time.perf_counter() - run_started) * 1000,
        "evaluation": evaluation_result["metrics"] if evaluation_result is not None else None,
        "output_dir": str(output_dir),
    }

    artifacts = {
        "product_contract.json": product_contract,
        "resource_regime.json": resource_regime,
        "planning_context.json": planning_context,
        "planning_decision.json": planning_decision,
        "planner_gap_proposal.json": planner_gap_proposal,
        "quality_gate_result.json": quality_gate_result,
        "gap_verification.json": gap_verification,
        "gap_declaration.json": gap_declaration,
        "evidence_trace.json": evidence_trace,
        "delivery_manifest.json": delivery_manifest,
        "experiment_summary.json": summary,
    }
    if evaluation_result is not None:
        artifacts["evaluation_result.json"] = evaluation_result
    if runtime_execution is not None:
        artifacts["runtime_execution.json"] = runtime_execution
    for filename, payload in artifacts.items():
        _write_json(output_dir / filename, payload)
    (output_dir / "run_report.md").write_text(
        render_run_report(summary, product_contract, planning_decision, gap_declaration),
        encoding="utf-8",
    )
    return summary


def build_product_contract(case: dict[str, Any]) -> dict[str, Any]:
    required_layers = case["required_layers"]
    return {
        "product_id": f"contract.{case['case_id']}",
        "product_type": "disaster_response_vector_product",
        "case_id": case["case_id"],
        "disaster_type": case["scenario"],
        "response_phase": infer_response_phase(case),
        "aoi": case["aoi"],
        "time_window": {"urgency": case["resource_regime"]["time_budget"]},
        "resource_regime_id": f"resource.{case['case_id']}",
        "required_layers": required_layers,
        "quality_gates": [
            {
                "gate_id": f"gate.{case['case_id']}.{layer['layer']}.{gate}",
                "layer": layer["layer"],
                "gate": gate,
                "severity": "required" if layer["criticality"] == "critical" else "advisory",
            }
            for layer in required_layers
            for gate in _gate_names_for_layer(layer["layer"])
        ],
        "degradation_policy": {
            "allow_provisional": case["resource_regime"]["time_budget"] == "tight",
            "allow_degraded_usable": True,
            "final_can_supersede_provisional": True,
        },
        "gap_declaration_policy": {
            "required_gap_types": [
                "data_absent",
                "source_unavailable",
                "quality_failed",
                "source_mismatch",
                "contract_not_satisfied",
            ],
            "gap_declarations_are_product_outputs": True,
        },
        "delivery_policy": {
            "allowed_modes": ["final", "provisional", "degraded", "background_pending"],
            "provisional_outputs_must_be_marked": True,
            "prefer_first_usable_delivery": case["resource_regime"]["time_budget"] == "tight",
        },
        "evidence_contract": {
            "required_evidence": ["source_provenance", "coverage", "quality_result"],
            "machine_outputs": [
                "product_contract.json",
                "planning_context.json",
                "planning_decision.json",
                "planner_gap_proposal.json",
                "quality_gate_result.json",
                "evidence_trace.json",
                "gap_verification.json",
                "gap_declaration.json",
                "delivery_manifest.json",
            ],
        },
    }


def build_resource_regime(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "resource_regime_id": f"resource.{case['case_id']}",
        "case_id": case["case_id"],
        **case["resource_regime"],
    }


def build_planning_context(
    case: dict[str, Any],
    product_contract: dict[str, Any],
    resource_regime: dict[str, Any],
    *,
    planner: str = "llm_full_contract_kg",
    input_variant: int = 0,
) -> dict[str, Any]:
    if planner not in PLANNER_KNOWLEDGE_PROFILES:
        raise ValueError(f"Unknown planner knowledge profile: {planner}")

    requested_layers = _permute_items(
        [{"layer": item["layer"]} for item in case["required_layers"]],
        key=lambda item: item["layer"],
        input_variant=input_variant,
        salt=1,
    )
    data_needs = _permute_items(
        [
            {
                "need_id": f"need.{case['case_id']}.{layer['layer']}",
                "layer": layer["layer"],
                "required": True,
            }
            for layer in case["required_layers"]
        ],
        key=lambda item: item["need_id"],
        input_variant=input_variant,
        salt=2,
    )
    sources = _permute_items(
        case["input_sources_status"],
        key=lambda item: item["source_id"],
        input_variant=input_variant,
        salt=3,
    )
    algorithms = _permute_items(
        [
            {
                "algorithm_id": f"algo.fusion.{layer['layer']}.v1",
                "layer": layer["layer"],
                "mode": "simulated_research_algorithm",
            }
            for layer in case["required_layers"]
        ],
        key=lambda item: item["algorithm_id"],
        input_variant=input_variant,
        salt=4,
    )
    quality_gates = _permute_items(
        product_contract["quality_gates"],
        key=lambda item: item["gate_id"],
        input_variant=input_variant,
        salt=5,
    )
    candidate_source_ids = [
        {"source_id": item["source_id"]} for item in sources
    ]
    candidate_algorithm_ids = [
        {"algorithm_id": item["algorithm_id"]} for item in algorithms
    ]
    capability_kg = {
        "data_needs": data_needs,
        "sources": sources,
        "algorithms": algorithms,
    }
    contract_kg = {
        "disaster_context": {
            "disaster_type": product_contract["disaster_type"],
            "response_phase": product_contract["response_phase"],
            "resource_regime": resource_regime,
        },
        "product_contract": {
            "required_layers": _permute_items(
                case["required_layers"],
                key=lambda item: item["layer"],
                input_variant=input_variant,
                salt=1,
            ),
            "degradation_policy": product_contract["degradation_policy"],
            "delivery_policy": product_contract["delivery_policy"],
            "gap_declaration_policy": product_contract["gap_declaration_policy"],
            "evidence_contract": product_contract["evidence_contract"],
        },
        "quality_gates": quality_gates,
        "gap_rules": {
            "source_problem_to_gap_type": SOURCE_PROBLEM_TO_GAP,
            "known_source_problems_must_be_declared": True,
        },
    }
    kg_retrieval: dict[str, Any] = {}
    if planner in {"kg_only", "llm_capability_kg", "llm_full_contract_kg"}:
        kg_retrieval["capability_kg"] = capability_kg
    if planner in {"kg_only", "llm_full_contract_kg"}:
        kg_retrieval["full_contract_kg"] = contract_kg

    return {
        "context_id": f"context.{case['case_id']}.{planner}",
        "case_id": case["case_id"],
        "input_variant": input_variant,
        "planning_protocol_version": PLANNING_PROTOCOL_VERSION,
        "knowledge_profile": {
            "planner": planner,
            **PLANNER_KNOWLEDGE_PROFILES[planner],
        },
        "product_contract_ref": product_contract["product_id"],
        "task_observation": {
            "title": case.get("title"),
            "scenario": case["scenario"],
            "aoi": case["aoi"],
            "resource_regime": resource_regime,
            "requested_layers": requested_layers,
            "source_observations": sources,
        },
        "resource_regime": resource_regime,
        "candidate_inventory": {
            "sources": candidate_source_ids,
            "algorithms": candidate_algorithm_ids,
        },
        "kg_retrieval": kg_retrieval,
        "case_evidence": {
            "positives": [],
            "negatives": [],
            "note": "Historical cases are excluded from all five Phase 2 baselines.",
        },
        "constraints": {
            "allowed_delivery_modes": [
                "final",
                "provisional",
                "degraded",
                "background_pending",
                "not_delivered",
            ],
            "allowed_strategy_ids": sorted(VALID_STRATEGY_IDS),
            "allowed_gap_types": sorted(
                {*SOURCE_PROBLEM_TO_GAP.values(), "contract_not_satisfied"}
            ),
            "gap_type_definitions": {
                "data_absent": "The source reports that no relevant features exist in the AOI.",
                "source_unavailable": "The source is delayed, unreachable, or not materialized.",
                "source_mismatch": "The source is stale or semantically unsuitable for the requested product.",
                "quality_failed": "The source or fusion evidence is conflicting or has failed a quality check.",
                "contract_not_satisfied": "Post-execution product gates are unmet; do not propose this without execution evidence.",
            },
            "strategy_definitions": {
                "progressive_delivery": "Deliver a usable product first and complete or supersede it later.",
                "critical_first_degraded_delivery": "Prioritize critical layers and use explicit degraded delivery when necessary.",
                "absence_aware_triage": "Concentrate effort on available critical layers and explicitly mark absent layers.",
                "coverage_first_progressive": "Prioritize broad usable coverage before later refinement.",
                "conflict_aware_fusion": "Preserve provenance and expose unresolved source conflicts during fusion.",
                "quality_fallback_delivery": "Deliver a grounded fallback when fuller fusion fails quality checks.",
                "fixed_global_order": "Use one global layer ordering without case-specific adaptation.",
                "criticality_coverage_heuristic": "Order by explicit criticality tiers and source coverage heuristics.",
            },
            "provisional_outputs_must_be_marked": True,
            "unknown_algorithms_and_sources_forbidden": True,
            "delivery_set_rules": {
                "initial_modes": ["final", "provisional", "degraded"],
                "background_only_mode": "background_pending",
                "not_delivered_mode": "not_delivered",
                "background_overlap_initial_modes": ["provisional", "degraded"],
                "final_and_not_delivered_forbidden_in_background": True,
                "all_required_layers_must_be_accounted_for": True,
            },
        },
    }


def build_planning_decision(
    case: dict[str, Any],
    planner: str,
    planning_context: dict[str, Any],
    *,
    llm_provider: LLMProvider | None = None,
) -> dict[str, Any]:
    if planner in LLM_PLANNERS:
        if llm_provider is None:
            raise RuntimeError(f"{planner} requires a configured LLM provider.")
        raw_responses: list[dict[str, Any]] = []
        grounding_failures: list[str] = []
        prompt_hashes: list[str] = []
        planning_attempts: list[dict[str, Any]] = []
        decision: dict[str, Any] | None = None
        for attempt in range(2):
            if attempt == 0:
                system_prompt = LLM_PLANNER_SYSTEM_PROMPT
                provider_context = planning_context
            else:
                system_prompt = LLM_PLANNER_REPAIR_SYSTEM_PROMPT
                provider_context = {
                    "planning_context": planning_context,
                    "previous_invalid_response": raw_responses[-1],
                    "validation_error": grounding_failures[-1],
                    "repair_requirement": (
                        "Return one complete replacement decision that satisfies all "
                        "schema, grounding, and delivery-set rules."
                    ),
                }
            prompt_hashes.append(_hash_text(system_prompt))
            attempt_started_at = _utc_now()
            try:
                raw_decision = llm_provider.generate_workflow_plan(
                    system_prompt,
                    provider_context,
                )
            except Exception as exc:
                planning_attempts.append(
                    {
                        "attempt_index": attempt,
                        "started_at": attempt_started_at,
                        "completed_at": _utc_now(),
                        "prompt_hash": prompt_hashes[-1],
                        "status": "provider_failed",
                        "model": getattr(llm_provider, "last_model", None),
                        "usage": getattr(llm_provider, "last_usage", None),
                        "latency_ms": getattr(llm_provider, "last_latency_ms", None),
                        "error": str(exc),
                    }
                )
                raise LLMPlanningFailure(
                    f"LLM provider request failed: {exc}",
                    raw_responses=raw_responses,
                    grounding_failures=grounding_failures,
                    planning_attempts=planning_attempts,
                ) from exc
            raw_responses.append(raw_decision)
            attempt_record = {
                "attempt_index": attempt,
                "started_at": attempt_started_at,
                "completed_at": _utc_now(),
                "prompt_hash": prompt_hashes[-1],
                "model": getattr(llm_provider, "last_model", None),
                "usage": getattr(llm_provider, "last_usage", None),
                "latency_ms": getattr(llm_provider, "last_latency_ms", None),
                "raw_response": raw_decision,
            }
            try:
                decision = _ground_llm_decision(case, planning_context, raw_decision)
                attempt_record["status"] = "grounded"
                planning_attempts.append(attempt_record)
                break
            except ValueError as exc:
                grounding_failures.append(str(exc))
                attempt_record["status"] = "grounding_failed"
                attempt_record["error"] = str(exc)
                planning_attempts.append(attempt_record)
        if decision is None:
            raise LLMPlanningFailure(
                "LLM planning decision failed after one explicit repair retry: "
                f"{grounding_failures[-1]}",
                raw_responses=raw_responses,
                grounding_failures=grounding_failures,
                planning_attempts=planning_attempts,
            )
        decision.update(
            {
                "decision_id": f"decision.{case['case_id']}.{planner}",
                "case_id": case["case_id"],
                "planner": planner,
                "planning_provider": llm_provider.provider_name,
                "planning_model": llm_provider.last_model,
                "planning_usage": llm_provider.last_usage,
                "planning_usage_total": _sum_usage(planning_attempts),
                "planning_latency_ms": sum(
                    float(item["latency_ms"])
                    for item in planning_attempts
                    if item.get("latency_ms") is not None
                ),
                "planning_attempts": planning_attempts,
                "planning_context_ref": planning_context["context_id"],
                "input_variant": planning_context["input_variant"],
                "prompt_version": PLANNER_PROMPT_VERSION,
                "planning_protocol_version": PLANNING_PROTOCOL_VERSION,
                "prompt_hash": _hash_text(LLM_PLANNER_SYSTEM_PROMPT),
                "prompt_hashes": prompt_hashes,
                "context_hash": _hash_json(planning_context),
                "calling_policy": LLM_CALLING_POLICY,
                "knowledge_profile": planning_context["knowledge_profile"],
                "raw_llm_response": raw_responses[-1],
                "raw_llm_responses": raw_responses,
                "planning_retry_count": len(raw_responses) - 1,
                "grounding_failures_before_success": grounding_failures,
            }
        )
        return decision

    priority_tiers = choose_priority_tiers(case, planner)
    ordered_layers = [layer for tier in priority_tiers for layer in tier]
    layer_decisions = []
    for layer in ordered_layers:
        sources = _sources_for_layer(case, layer)
        has_problem = any(source["status"] in SOURCE_PROBLEM_TO_GAP for source in sources)
        layer_decisions.append(
            {
                "layer": layer,
                "selected_algorithm": f"algo.fusion.{layer}.v1",
                "selected_sources": [source["source_id"] for source in sources],
                "delivery_mode": _delivery_mode(case, layer, has_problem),
            }
        )

    initial_delivery_layers = [
        item["layer"]
        for item in layer_decisions
        if item["delivery_mode"]
        in {"final", "provisional", "degraded"}
    ]
    not_delivered_layers = [
        item["layer"]
        for item in layer_decisions
        if item["delivery_mode"] == "not_delivered"
    ]
    background_completion_layers = [
        item["layer"]
        for item in layer_decisions
        if item["delivery_mode"] == "background_pending"
        or (
            planner == "kg_only"
            and item["delivery_mode"] in {"provisional", "degraded"}
            and _known_source_issues(case, item["layer"])
        )
    ]
    planner_gap_proposal = (
        _derive_grounded_gap_proposals(case) if planner == "kg_only" else []
    )
    supersession_plan = [
        {
            "layer": layer,
            "target_delivery_mode": "final",
            "trigger_source_ids": [
                issue["source_id"] for issue in _known_source_issues(case, layer)
            ],
            "condition": "Grounded source problems are resolved and final quality gates pass.",
        }
        for layer in background_completion_layers
    ]

    structured = StructuredPlanningDecision.model_validate(
        {
            "strategy_id": (
                "fixed_global_order"
                if planner == "fixed"
                else "criticality_coverage_heuristic"
            ),
            "priority_tiers": priority_tiers,
            "initial_delivery_layers": initial_delivery_layers,
            "background_completion_layers": background_completion_layers,
            "not_delivered_layers": not_delivered_layers,
            "layer_decisions": layer_decisions,
            "planner_gap_proposal": planner_gap_proposal,
            "supersession_plan": supersession_plan,
            "rationale": _planner_rationale(case, planner, ordered_layers),
        }
    ).model_dump(mode="json")

    return {
        "decision_id": f"decision.{case['case_id']}.{planner}",
        "case_id": case["case_id"],
        "planner": planner,
        "planning_provider": "deterministic",
        "planning_model": None,
        "planning_usage": None,
        "planning_context_ref": planning_context["context_id"],
        "input_variant": planning_context["input_variant"],
        "planning_protocol_version": PLANNING_PROTOCOL_VERSION,
        "prompt_version": None,
        "context_hash": _hash_json(planning_context),
        "knowledge_profile": planning_context["knowledge_profile"],
        **structured,
        "grounding": {"valid": True, "issues": []},
    }


def _ground_llm_decision(
    case: dict[str, Any],
    planning_context: dict[str, Any],
    raw_decision: dict[str, Any],
) -> dict[str, Any]:
    required_layers = [item["layer"] for item in case["required_layers"]]
    structured = StructuredPlanningDecision.model_validate(raw_decision)
    grounded = structured.model_dump(mode="json")

    priority_layers = [
        layer for tier in grounded["priority_tiers"] for layer in tier
    ]
    if len(priority_layers) != len(required_layers) or set(priority_layers) != set(required_layers):
        raise ValueError(
            "LLM priority_tiers must contain every required layer exactly once: "
            f"expected={required_layers}, actual={priority_layers}"
        )
    if grounded["strategy_id"] not in VALID_STRATEGY_IDS:
        raise ValueError(f"LLM selected unknown strategy_id: {grounded['strategy_id']}")

    candidate_algorithm_ids = {
        item["algorithm_id"]
        for item in planning_context["candidate_inventory"]["algorithms"]
    }
    algorithms_by_layer = {
        layer: f"algo.fusion.{layer}.v1" for layer in required_layers
    }
    missing_algorithms = set(algorithms_by_layer.values()) - candidate_algorithm_ids
    if missing_algorithms:
        raise ValueError(
            f"Planning context is missing grounded algorithm candidates: {sorted(missing_algorithms)}"
        )
    candidate_source_ids = {
        item["source_id"]
        for item in planning_context["candidate_inventory"]["sources"]
    }
    sources_by_layer = {
        layer: {
            source["source_id"]
            for source in _sources_for_layer(case, layer)
            if source["source_id"] in candidate_source_ids
        }
        for layer in required_layers
    }
    raw_by_layer = {item["layer"]: item for item in grounded["layer_decisions"]}
    if set(raw_by_layer) != set(required_layers):
        raise ValueError(
            "LLM layer_decisions must contain every required layer exactly once: "
            f"expected={required_layers}, actual={sorted(raw_by_layer)}"
        )
    allowed_modes = set(planning_context["constraints"]["allowed_delivery_modes"])
    grounding_issues: list[dict[str, str]] = []

    initial = set(grounded["initial_delivery_layers"])
    background = set(grounded["background_completion_layers"])
    not_delivered = set(grounded["not_delivered_layers"])
    declared_layers = initial | background | not_delivered
    unknown_declared_layers = declared_layers - set(required_layers)
    if unknown_declared_layers:
        raise ValueError(
            f"LLM delivery sets contain unknown layers: {sorted(unknown_declared_layers)}"
        )
    if declared_layers != set(required_layers):
        raise ValueError(
            "LLM delivery sets must account for every required layer through initial, "
            "background, or not-delivered placement."
        )

    for layer in required_layers:
        raw = raw_by_layer[layer]
        algorithm_id = str(raw.get("selected_algorithm") or "").strip()
        if algorithm_id != algorithms_by_layer[layer]:
            raise ValueError(
                f"LLM selected ungrounded algorithm for {layer}: {algorithm_id or '<empty>'}"
            )
        selected_sources = raw.get("selected_sources")
        if not isinstance(selected_sources, list) or not all(isinstance(item, str) for item in selected_sources):
            raise ValueError(f"LLM selected_sources for {layer} must be a string list.")
        selected_sources = [item.strip() for item in selected_sources]
        unknown_sources = set(selected_sources) - sources_by_layer[layer]
        if unknown_sources:
            raise ValueError(f"LLM selected ungrounded sources for {layer}: {sorted(unknown_sources)}")
        delivery_mode = str(raw.get("delivery_mode") or "").strip()
        if delivery_mode not in allowed_modes:
            raise ValueError(f"LLM selected invalid delivery_mode for {layer}: {delivery_mode}")

        if delivery_mode in {"final", "provisional", "degraded"} and layer not in initial:
            grounding_issues.append(
                {
                    "code": "DELIVERED_LAYER_MISSING_FROM_INITIAL_SET",
                    "layer": layer,
                    "message": "Delivered layer modes must appear in initial_delivery_layers.",
                }
            )
        if delivery_mode == "background_pending" and (
            layer not in background or layer in initial
        ):
            grounding_issues.append(
                {
                    "code": "BACKGROUND_MODE_SET_MISMATCH",
                    "layer": layer,
                    "message": "background_pending layers belong only to background completion.",
                }
            )
        if delivery_mode == "not_delivered" and layer not in not_delivered:
            grounding_issues.append(
                {
                    "code": "NOT_DELIVERED_MODE_SET_MISMATCH",
                    "layer": layer,
                    "message": "not_delivered mode must be reflected in not_delivered_layers.",
                }
            )
        if delivery_mode != "not_delivered" and layer in not_delivered:
            grounding_issues.append(
                {
                    "code": "DELIVERED_LAYER_IN_NOT_DELIVERED_SET",
                    "layer": layer,
                    "message": "Delivered layers cannot appear in not_delivered_layers.",
                }
            )
        if layer in background and delivery_mode in {"final", "not_delivered"}:
            grounding_issues.append(
                {
                    "code": "INVALID_BACKGROUND_COMPLETION_MODE",
                    "layer": layer,
                    "message": "Background completion requires provisional, degraded, or pending mode.",
                }
            )

        known_source_issues = _known_source_issues(case, layer)
        if known_source_issues and delivery_mode == "final":
            grounding_issues.append(
                {
                    "code": "FINAL_DELIVERY_WITH_KNOWN_SOURCE_PROBLEM",
                    "layer": layer,
                    "message": "Known source problems require provisional, degraded, pending, or not-delivered state.",
                }
            )
        if not selected_sources and delivery_mode not in {"not_delivered", "background_pending"}:
            grounding_issues.append(
                {
                    "code": "DELIVERY_WITHOUT_SELECTED_SOURCE",
                    "layer": layer,
                    "message": "A delivered layer must select at least one grounded source.",
                }
            )

    for proposal in grounded["planner_gap_proposal"]:
        layer = proposal["layer"]
        if layer not in required_layers:
            raise ValueError(f"LLM gap proposal refers to unknown layer: {layer}")
        supported_issues = _known_source_issues(case, layer)
        source_id = proposal.get("source_id")
        if source_id is not None:
            supported_issues = [
                issue for issue in supported_issues if issue["source_id"] == source_id
            ]
        if not any(
            issue["gap_type"] == proposal["gap_type"] for issue in supported_issues
        ):
            raise ValueError(
                "LLM planner_gap_proposal is unsupported by grounded source status: "
                f"layer={layer}, gap_type={proposal['gap_type']}, source_id={source_id}"
            )

    all_case_sources = {
        source["source_id"]: source["layer"] for source in case["input_sources_status"]
    }
    for item in grounded["supersession_plan"]:
        layer = item["layer"]
        if layer not in background:
            raise ValueError(
                f"LLM supersession layer {layer} is not a background-completion layer."
            )
        invalid_triggers = [
            source_id
            for source_id in item["trigger_source_ids"]
            if all_case_sources.get(source_id) != layer
        ]
        if invalid_triggers:
            raise ValueError(
                f"LLM supersession plan uses ungrounded trigger sources: {invalid_triggers}"
            )

    if grounding_issues:
        raise ValueError(f"LLM planning decision failed grounding: {grounding_issues}")
    grounded["grounding"] = {"valid": True, "issues": []}
    return grounded


def build_quality_gate_result(
    case: dict[str, Any],
    planning_decision: dict[str, Any],
) -> dict[str, Any]:
    layer_results = []
    for decision in planning_decision["layer_decisions"]:
        layer = decision["layer"]
        sources = _sources_for_layer(case, layer)
        status_values = {source["status"] for source in sources}
        gates = [
            _gate_result(layer, "source_materialized", bool(sources) and "data_absent" not in status_values),
            _gate_result(layer, "aoi_coverage_checked", True),
            _gate_result(layer, "non_empty_or_justified_empty", "data_absent" not in status_values),
            _gate_result(layer, "geometry_validity_checked", "quality_failed" not in status_values),
            _gate_result(layer, "provenance_recorded", True),
        ]
        if any(status in {"conflicting", "source_mismatch", "stale"} for status in status_values):
            gates.append(_gate_result(layer, "conflict_or_mismatch_declared", True))
        layer_results.append(
            {
                "layer": layer,
                "delivery_mode": decision["delivery_mode"],
                "gates": gates,
                "passed": all(gate["passed"] for gate in gates),
            }
        )
    return {
        "quality_result_id": f"quality.{case['case_id']}.{planning_decision['planner']}",
        "case_id": case["case_id"],
        "planner": planning_decision["planner"],
        "execution_mode": ExperimentExecutionMode.PLANNING_ONLY.value,
        "evidence_origin": "controlled_status_simulation",
        "layer_results": layer_results,
    }


def build_runtime_quality_gate_result(
    case: dict[str, Any],
    planning_decision: dict[str, Any],
    runtime_execution: dict[str, Any],
) -> dict[str, Any]:
    layer_results = []
    for result in runtime_execution["layer_results"]:
        quality_report = result.get("quality_report")
        if quality_report is not None:
            gates = [
                {
                    "gate_id": f"gate.{case['case_id']}.{result['layer']}.{name}",
                    "layer": result["layer"],
                    "gate": name,
                    "passed": bool(check.get("passed")),
                    "evidence_origin": "real_runtime",
                    "details": check,
                }
                for name, check in quality_report.get("checks", {}).items()
            ]
            passed = bool(quality_report.get("accepted"))
        elif result["status"] == "skipped":
            gates = [
                {
                    "gate_id": f"gate.{case['case_id']}.{result['layer']}.execution_deferred",
                    "layer": result["layer"],
                    "gate": "execution_deferred",
                    "passed": True,
                    "evidence_origin": "real_runtime",
                    "details": {
                        "delivery_mode": result["delivery_mode"],
                        "reason": result["algorithm_result"].get("fallback_reason"),
                    },
                }
            ]
            passed = True
        else:
            gates = [
                {
                    "gate_id": f"gate.{case['case_id']}.{result['layer']}.runtime_execution",
                    "layer": result["layer"],
                    "gate": "runtime_execution",
                    "passed": False,
                    "evidence_origin": "real_runtime",
                    "details": {
                        "error": result["algorithm_result"].get("error"),
                        "source_results": result.get("source_results", []),
                    },
                }
            ]
            passed = False
        layer_results.append(
            {
                "layer": result["layer"],
                "delivery_mode": result["delivery_mode"],
                "runtime_status": result["status"],
                "artifact_path": result["algorithm_result"].get("output_path"),
                "quality_report_path": result.get("quality_report_path"),
                "gates": gates,
                "passed": passed,
            }
        )
    return {
        "quality_result_id": f"quality.{case['case_id']}.{planning_decision['planner']}.runtime",
        "case_id": case["case_id"],
        "planner": planning_decision["planner"],
        "execution_mode": ExperimentExecutionMode.END_TO_END.value,
        "evidence_origin": "real_runtime",
        "runtime_execution_ref": runtime_execution["execution_id"],
        "layer_results": layer_results,
    }


def build_planner_gap_proposal(
    case: dict[str, Any],
    planning_decision: dict[str, Any],
) -> dict[str, Any]:
    proposals = list(planning_decision["planner_gap_proposal"])
    return {
        "planner_gap_proposal_id": (
            f"planner-gaps.{case['case_id']}.{planning_decision['planner']}"
        ),
        "case_id": case["case_id"],
        "planner": planning_decision["planner"],
        "proposals": proposals,
    }


def build_gap_verification(
    case: dict[str, Any],
    planning_decision: dict[str, Any],
    planner_gap_proposal: dict[str, Any],
) -> dict[str, Any]:
    observable = _derive_grounded_gap_proposals(case)
    observable_keys = {
        (item["layer"], item["gap_type"]) for item in observable
    }
    proposals = planner_gap_proposal["proposals"]
    verified = [
        item
        for item in proposals
        if (item["layer"], item["gap_type"]) in observable_keys
    ]
    proposed_keys = {
        (item["layer"], item["gap_type"]) for item in proposals
    }
    unproposed = [
        item
        for item in observable
        if (item["layer"], item["gap_type"]) not in proposed_keys
    ]
    return {
        "gap_verification_id": (
            f"gap-verification.{case['case_id']}.{planning_decision['planner']}"
        ),
        "case_id": case["case_id"],
        "planner": planning_decision["planner"],
        "planner_gap_proposal_ref": planner_gap_proposal["planner_gap_proposal_id"],
        "all_proposals_grounded": len(verified) == len(proposals),
        "verified_proposals": verified,
        "unproposed_observable_gaps": unproposed,
    }


def build_gap_declaration(
    case: dict[str, Any],
    planning_decision: dict[str, Any],
    quality_gate_result: dict[str, Any],
    *,
    runtime_execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issues_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for source in case["input_sources_status"]:
        gap_type = SOURCE_PROBLEM_TO_GAP.get(source["status"])
        if gap_type:
            issues_by_key.setdefault((source["layer"], gap_type), []).append(source)

    gaps: list[dict[str, Any]] = []
    for (layer, gap_type), sources in sorted(issues_by_key.items()):
        source_ids = [source["source_id"] for source in sources]
        statuses = sorted({source["status"] for source in sources})
        gaps.append(
            {
                "gap_id": f"gap.{case['case_id']}.{layer}.{gap_type}",
                "layer": layer,
                "gap_type": gap_type,
                "source_ids": source_ids,
                "severity": _gap_severity(case, layer),
                "reason": (
                    f"Grounded source status requires declaration: "
                    f"sources={source_ids}, statuses={statuses}."
                ),
                "impact": _gap_impact(layer, gap_type),
                "mitigation": _gap_mitigation(gap_type),
            }
        )
    if runtime_execution is not None:
        existing_keys = {(item["layer"], item["gap_type"]) for item in gaps}
        for layer_result in runtime_execution["layer_results"]:
            layer = layer_result["layer"]
            failed_source_ids = [
                item["source_id"]
                for item in layer_result.get("source_results", [])
                if item["status"] == "failed"
            ]
            if failed_source_ids and (layer, "source_unavailable") not in existing_keys:
                gaps.append(
                    {
                        "gap_id": f"gap.{case['case_id']}.{layer}.source_unavailable.runtime",
                        "layer": layer,
                        "gap_type": "source_unavailable",
                        "source_ids": failed_source_ids,
                        "severity": _gap_severity(case, layer),
                        "reason": (
                            "Real runtime materialization failed for planner-selected "
                            f"sources={failed_source_ids}."
                        ),
                        "impact": _gap_impact(layer, "source_unavailable"),
                        "mitigation": _gap_mitigation("source_unavailable"),
                        "evidence_origin": "real_runtime",
                    }
                )
                existing_keys.add((layer, "source_unavailable"))
            quality_report = layer_result.get("quality_report")
            algorithm_result = layer_result.get("algorithm_result", {})
            if (
                layer_result.get("status") == "failed"
                and algorithm_result.get("status") == "failed"
                and (layer, "contract_not_satisfied") not in existing_keys
            ):
                gaps.append(
                    {
                        "gap_id": f"gap.{case['case_id']}.{layer}.contract_not_satisfied.runtime",
                        "layer": layer,
                        "gap_type": "contract_not_satisfied",
                        "source_ids": [],
                        "severity": _gap_severity(case, layer),
                        "reason": (
                            "Real runtime did not produce an executable layer artifact: "
                            f"{algorithm_result.get('error') or 'runtime layer failed'}."
                        ),
                        "impact": "Layer has no accepted runtime artifact.",
                        "mitigation": "Resolve the materialization or algorithm failure and rerun the layer.",
                        "evidence_origin": "real_runtime",
                    }
                )
                existing_keys.add((layer, "contract_not_satisfied"))
            if (
                quality_report is not None
                and not quality_report.get("accepted")
                and (layer, "quality_failed") not in existing_keys
            ):
                gaps.append(
                    {
                        "gap_id": f"gap.{case['case_id']}.{layer}.quality_failed.runtime",
                        "layer": layer,
                        "gap_type": "quality_failed",
                        "source_ids": [],
                        "severity": _gap_severity(case, layer),
                        "reason": (
                            "Real runtime quality gate rejected the materialized output: "
                            f"{quality_report.get('failure_reasons', [])}."
                        ),
                        "impact": _gap_impact(layer, "quality_failed"),
                        "mitigation": _gap_mitigation("quality_failed"),
                        "evidence_origin": "real_runtime",
                    }
                )
                existing_keys.add((layer, "quality_failed"))
    for layer_result in quality_gate_result["layer_results"]:
        if not layer_result["passed"] and not _has_gap_for_layer(gaps, layer_result["layer"]):
            gaps.append(
                {
                    "gap_id": f"gap.{case['case_id']}.{layer_result['layer']}.contract_not_satisfied",
                    "layer": layer_result["layer"],
                    "gap_type": "contract_not_satisfied",
                    "severity": _gap_severity(case, layer_result["layer"]),
                    "reason": "One or more quality gates did not pass.",
                    "impact": "Layer cannot be claimed as fully satisfied.",
                    "mitigation": "Deliver degraded output only if the product contract allows it.",
                }
            )
    return {
        "gap_declaration_id": f"gaps.{case['case_id']}.{planning_decision['planner']}",
        "case_id": case["case_id"],
        "planner": planning_decision["planner"],
        "execution_mode": (
            ExperimentExecutionMode.END_TO_END.value
            if runtime_execution is not None
            else ExperimentExecutionMode.PLANNING_ONLY.value
        ),
        "gaps": gaps,
    }


def build_evidence_trace(
    case: dict[str, Any],
    product_contract: dict[str, Any],
    planning_decision: dict[str, Any],
    quality_gate_result: dict[str, Any],
    gap_verification: dict[str, Any],
    gap_declaration: dict[str, Any],
    *,
    execution_mode: str = ExperimentExecutionMode.PLANNING_ONLY.value,
    runtime_execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    items = [
        {
            "evidence_id": f"evidence.{case['case_id']}.contract",
            "evidence_type": "product_contract",
            "proves": product_contract["product_id"],
        },
        {
            "evidence_id": f"evidence.{case['case_id']}.planning",
            "evidence_type": "planning_decision",
            "proves": planning_decision["decision_id"],
        },
        {
            "evidence_id": f"evidence.{case['case_id']}.quality",
            "evidence_type": "quality_gate_result",
            "proves": quality_gate_result["quality_result_id"],
        },
        {
            "evidence_id": f"evidence.{case['case_id']}.gap-verification",
            "evidence_type": "gap_verification",
            "proves": gap_verification["gap_verification_id"],
        },
        {
            "evidence_id": f"evidence.{case['case_id']}.gaps",
            "evidence_type": "gap_declaration",
            "proves": gap_declaration["gap_declaration_id"],
        },
    ]
    for source in case["input_sources_status"]:
        items.append(
            {
                "evidence_id": f"evidence.{case['case_id']}.{source['source_id']}",
                "evidence_type": "source_status",
                "source_id": source["source_id"],
                "layer": source["layer"],
                "status": source["status"],
                "coverage": source["coverage"],
            }
        )
    if runtime_execution is not None:
        items.append(
            {
                "evidence_id": f"evidence.{case['case_id']}.runtime",
                "evidence_type": "runtime_execution",
                "proves": runtime_execution["execution_id"],
                "status": runtime_execution["status"],
                "artifact_registry_path": runtime_execution["artifact_registry_path"],
            }
        )
        for layer_result in runtime_execution["layer_results"]:
            algorithm_result = layer_result["algorithm_result"]
            items.append(
                {
                    "evidence_id": (
                        f"evidence.{case['case_id']}.runtime.{layer_result['layer']}"
                    ),
                    "evidence_type": "runtime_layer_execution",
                    "layer": layer_result["layer"],
                    "status": layer_result["status"],
                    "selected_sources": layer_result["selected_sources"],
                    "selected_algorithm_id": algorithm_result["selected_algorithm_id"],
                    "resolved_algorithm_id": algorithm_result.get("resolved_algorithm_id"),
                    "output_path": algorithm_result.get("output_path"),
                    "output_sha256": algorithm_result.get("output_sha256"),
                    "quality_report_path": layer_result.get("quality_report_path"),
                    "writeback": layer_result["writeback"],
                }
            )
    return {
        "trace_id": f"trace.{case['case_id']}.{planning_decision['planner']}",
        "case_id": case["case_id"],
        "planner": planning_decision["planner"],
        "execution_mode": execution_mode,
        "evidence_items": items,
    }


def build_delivery_manifest(
    case: dict[str, Any],
    product_contract: dict[str, Any],
    planning_decision: dict[str, Any],
    quality_gate_result: dict[str, Any],
    gap_declaration: dict[str, Any],
    evidence_trace: dict[str, Any],
    *,
    execution_mode: str = ExperimentExecutionMode.PLANNING_ONLY.value,
    runtime_execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if runtime_execution is None:
        delivered_layers = [
            decision["layer"]
            for decision in planning_decision["layer_decisions"]
            if decision["delivery_mode"] in {"final", "provisional", "degraded"}
        ]
    else:
        delivered_layers = [
            item["layer"]
            for item in runtime_execution["layer_results"]
            if item["status"] == "succeeded"
        ]
    satisfaction_state = _satisfaction_state(
        case,
        planning_decision,
        quality_gate_result,
        gap_declaration,
        delivered_layers_override=(
            set(delivered_layers) if runtime_execution is not None else None
        ),
    )
    return {
        "manifest_id": f"delivery.{case['case_id']}.{planning_decision['planner']}",
        "case_id": case["case_id"],
        "planner": planning_decision["planner"],
        "execution_mode": execution_mode,
        "runtime_execution_ref": (
            runtime_execution.get("execution_id") if runtime_execution is not None else None
        ),
        "product_contract_ref": product_contract["product_id"],
        "satisfaction_state": satisfaction_state,
        "delivered_layers": delivered_layers,
        "gap_declaration_ref": gap_declaration["gap_declaration_id"],
        "evidence_trace_ref": evidence_trace["trace_id"],
        "machine_outputs": [
            "product_contract.json",
            "resource_regime.json",
            "planning_context.json",
            "planning_decision.json",
            "planner_gap_proposal.json",
            "quality_gate_result.json",
            "gap_verification.json",
            "evidence_trace.json",
            "gap_declaration.json",
            "delivery_manifest.json",
            "experiment_summary.json",
            "run_report.md",
            *(
                ["runtime_execution.json", "runtime_artifact_index.json"]
                if runtime_execution is not None
                else []
            ),
        ],
    }


def evaluate_against_gold(
    *,
    case: dict[str, Any],
    planning_decision: dict[str, Any],
    gold: dict[str, Any] | None,
    gap_declaration: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if gold is None:
        return None
    if gold.get("case_id") != case.get("case_id"):
        raise ValueError("Gold row does not match the experiment case.")
    gold_model = ProductContractGold.model_validate(gold)
    gold_data = gold_model.model_dump(mode="json")

    expected_tiers = gold_data["priority_tiers"]
    actual_tiers = planning_decision["priority_tiers"]
    actual_tier_index = {
        layer: tier_index
        for tier_index, tier in enumerate(actual_tiers)
        for layer in tier
    }
    precedence_pairs = [
        (earlier, later)
        for earlier_index, earlier_tier in enumerate(expected_tiers)
        for later_tier in expected_tiers[earlier_index + 1 :]
        for earlier in earlier_tier
        for later in later_tier
    ]
    correct_precedence = sum(
        1
        for earlier, later in precedence_pairs
        if actual_tier_index.get(earlier, 10**6)
        < actual_tier_index.get(later, -1)
    )
    priority_score = (
        correct_precedence / len(precedence_pairs) if precedence_pairs else 1.0
    )

    expectations = gold_data["delivery_expectations"]
    actual_initial = set(planning_decision["initial_delivery_layers"])
    actual_background = set(planning_decision["background_completion_layers"])
    actual_not_delivered = set(planning_decision["not_delivered_layers"])
    actual_supersession = {
        item["layer"] for item in planning_decision["supersession_plan"]
    }
    actual_modes = {
        item["layer"]: item["delivery_mode"]
        for item in planning_decision["layer_decisions"]
    }
    allowed_modes = expectations["allowed_delivery_modes"]
    delivery_mode_accuracy = (
        sum(
            1
            for layer, modes in allowed_modes.items()
            if actual_modes.get(layer) in modes
        )
        / len(allowed_modes)
        if allowed_modes
        else 1.0
    )

    expected_gaps = {
        (str(item["layer"]), str(item["gap_type"]))
        for item in gold_data["expected_gap_proposals"]
    }
    actual_gaps = {
        (str(item["layer"]), str(item["gap_type"]))
        for item in planning_decision["planner_gap_proposal"]
    }
    true_positive_gaps = expected_gaps & actual_gaps
    gap_precision = len(true_positive_gaps) / len(actual_gaps) if actual_gaps else float(not expected_gaps)
    gap_recall = len(true_positive_gaps) / len(expected_gaps) if expected_gaps else float(not actual_gaps)
    gap_f1 = (
        2 * gap_precision * gap_recall / (gap_precision + gap_recall)
        if gap_precision + gap_recall
        else 0.0
    )
    consistency_issues = _planning_consistency_issues(case, planning_decision)
    grounding_validity = float(planning_decision.get("grounding", {}).get("valid") is True)
    internal_consistency = float(not consistency_issues)

    metrics = {
        "priority_pairwise_precedence_accuracy": priority_score,
        "strategy_id_match": float(
            planning_decision["strategy_id"] in gold_data["acceptable_strategy_ids"]
        ),
        "required_initial_recall": _set_recall(
            actual_initial, set(expectations["required_initial"])
        ),
        "invalid_initial_rate": _invalid_rate(
            actual_initial, set(expectations["allowed_initial"])
        ),
        "required_background_recall": _set_recall(
            actual_background, set(expectations["required_background"])
        ),
        "invalid_background_rate": _invalid_rate(
            actual_background, set(expectations["allowed_background"])
        ),
        "required_not_delivered_recall": _set_recall(
            actual_not_delivered, set(expectations["required_not_delivered"])
        ),
        "invalid_not_delivered_rate": _invalid_rate(
            actual_not_delivered, set(expectations["allowed_not_delivered"])
        ),
        "allowed_delivery_mode_accuracy": delivery_mode_accuracy,
        "required_supersession_recall": _set_recall(
            actual_supersession, set(expectations["required_supersession"])
        ),
        "planner_gap_precision": gap_precision,
        "planner_gap_recall": gap_recall,
        "planner_gap_f1": gap_f1,
        "grounding_validity": grounding_validity,
        "internal_consistency": internal_consistency,
    }
    positive_components = [
        metrics["priority_pairwise_precedence_accuracy"],
        metrics["strategy_id_match"],
        metrics["required_initial_recall"],
        1.0 - metrics["invalid_initial_rate"],
        metrics["required_background_recall"],
        1.0 - metrics["invalid_background_rate"],
        metrics["required_not_delivered_recall"],
        1.0 - metrics["invalid_not_delivered_rate"],
        metrics["allowed_delivery_mode_accuracy"],
        metrics["required_supersession_recall"],
        metrics["planner_gap_f1"],
        metrics["grounding_validity"],
        metrics["internal_consistency"],
    ]
    metrics["overall_score"] = sum(positive_components) / len(positive_components)

    return {
        "case_id": case["case_id"],
        "planner": planning_decision["planner"],
        "gold_source": str(DEFAULT_GOLD_PATH),
        "metrics": metrics,
        "expected": {
            "priority_tiers": expected_tiers,
            "acceptable_strategy_ids": gold_data["acceptable_strategy_ids"],
            "delivery_expectations": expectations,
            "gap_keys": [list(item) for item in sorted(expected_gaps)],
        },
        "actual": {
            "priority_tiers": actual_tiers,
            "strategy_id": planning_decision["strategy_id"],
            "initial_delivery_layers": sorted(actual_initial),
            "background_completion_layers": sorted(actual_background),
            "not_delivered_layers": sorted(actual_not_delivered),
            "supersession_layers": sorted(actual_supersession),
            "delivery_modes": actual_modes,
            "gap_keys": [list(item) for item in sorted(actual_gaps)],
            "internal_consistency_issues": consistency_issues,
        },
    }


def choose_priority_tiers(case: dict[str, Any], planner: str) -> list[list[str]]:
    layers = [layer["layer"] for layer in case["required_layers"]]
    if planner == "fixed":
        return [[layer] for layer in FIXED_LAYER_ORDER if layer in layers]
    if planner == "kg_only":
        layer_meta = {layer["layer"]: layer for layer in case["required_layers"]}
        tiers: list[list[str]] = []
        for criticality in sorted(
            {layer_meta[layer]["criticality"] for layer in layers},
            key=lambda value: CRITICALITY_RANK.get(value, 99),
        ):
            tiers.append(
                sorted(
                    [
                        layer
                        for layer in layers
                        if layer_meta[layer]["criticality"] == criticality
                    ]
                )
            )
        return tiers
    raise ValueError(f"Layer ordering for planner {planner!r} requires the LLM planning path.")


def render_run_report(
    summary: dict[str, Any],
    product_contract: dict[str, Any],
    planning_decision: dict[str, Any],
    gap_declaration: dict[str, Any],
) -> str:
    lines = [
        f"# Product Contract Experiment {summary['case_id']}",
        "",
        f"- Planner: `{summary['planner']}`",
        f"- Execution mode: `{summary.get('execution_mode', 'planning_only')}`",
        f"- Runtime status: `{summary.get('runtime_status') or 'not_run'}`",
        f"- Satisfaction: `{summary['satisfaction_state']}`",
        f"- Disaster type: `{product_contract['disaster_type']}`",
        f"- Strategy id: `{planning_decision['strategy_id']}`",
        "",
        "## Priority Tiers",
        "",
    ]
    for index, tier in enumerate(planning_decision["priority_tiers"], start=1):
        lines.append(f"- Tier {index}: {', '.join(f'`{layer}`' for layer in tier)}")
    lines.extend(["", "## Gaps", ""])
    if gap_declaration["gaps"]:
        for gap in gap_declaration["gaps"]:
            lines.append(f"- `{gap['layer']}` / `{gap['gap_type']}`: {gap['reason']}")
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def infer_response_phase(case: dict[str, Any]) -> str:
    if case["resource_regime"].get("time_budget") == "tight":
        return "rapid_response"
    return "assessment"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sum_usage(attempts: list[dict[str, Any]]) -> dict[str, int] | None:
    totals: dict[str, int] = {}
    for attempt in attempts:
        usage = attempt.get("usage")
        if not isinstance(usage, dict):
            continue
        for key, value in usage.items():
            if isinstance(value, int):
                totals[key] = totals.get(key, 0) + value
    return totals or None


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_json(payload: dict[str, Any]) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return _hash_text(serialized)


def _gate_names_for_layer(_layer: str) -> list[str]:
    return [
        "source_materialized",
        "aoi_coverage_checked",
        "non_empty_or_justified_empty",
        "geometry_validity_checked",
        "provenance_recorded",
    ]


def _sources_for_layer(case: dict[str, Any], layer: str) -> list[dict[str, Any]]:
    return [source for source in case["input_sources_status"] if source["layer"] == layer]


def _known_source_issues(case: dict[str, Any], layer: str) -> list[dict[str, Any]]:
    return [
        {
            "source_id": source["source_id"],
            "status": source["status"],
            "gap_type": SOURCE_PROBLEM_TO_GAP[source["status"]],
        }
        for source in _sources_for_layer(case, layer)
        if source["status"] in SOURCE_PROBLEM_TO_GAP
    ]


def _derive_grounded_gap_proposals(case: dict[str, Any]) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for source in sorted(case["input_sources_status"], key=lambda item: item["source_id"]):
        gap_type = SOURCE_PROBLEM_TO_GAP.get(source["status"])
        gap_key = (source["layer"], gap_type or "")
        if not gap_type or gap_key in seen:
            continue
        seen.add(gap_key)
        proposals.append(
            {
                "layer": source["layer"],
                "gap_type": gap_type,
                "source_id": source["source_id"],
                "reason": (
                    f"Source {source['source_id']} has grounded status {source['status']}."
                ),
            }
        )
    return proposals


def _permute_items(
    items: list[dict[str, Any]],
    *,
    key: Any,
    input_variant: int,
    salt: int,
) -> list[dict[str, Any]]:
    ordered = sorted(items, key=key)
    if input_variant == 0 or len(ordered) < 2:
        return ordered
    rotation = (abs(input_variant) * (2 * salt + 1)) % len(ordered)
    if rotation:
        ordered = ordered[rotation:] + ordered[:rotation]
    if input_variant < 0 or abs(input_variant) % 2 == 0:
        ordered = list(reversed(ordered))
    return ordered


def _set_recall(actual: set[str], required: set[str]) -> float:
    return len(actual & required) / len(required) if required else 1.0


def _invalid_rate(actual: set[str], allowed: set[str]) -> float:
    return len(actual - allowed) / len(actual) if actual else 0.0


def _planning_consistency_issues(
    case: dict[str, Any],
    planning_decision: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    required = {item["layer"] for item in case["required_layers"]}
    tier_layers = [
        layer
        for tier in planning_decision.get("priority_tiers", [])
        for layer in tier
    ]
    if len(tier_layers) != len(set(tier_layers)) or set(tier_layers) != required:
        issues.append("priority_tiers_do_not_cover_required_layers_exactly_once")

    layer_decisions = planning_decision.get("layer_decisions", [])
    decision_layers = [item.get("layer") for item in layer_decisions]
    if len(decision_layers) != len(set(decision_layers)) or set(decision_layers) != required:
        issues.append("layer_decisions_do_not_cover_required_layers_exactly_once")

    initial = set(planning_decision.get("initial_delivery_layers", []))
    background = set(planning_decision.get("background_completion_layers", []))
    not_delivered = set(planning_decision.get("not_delivered_layers", []))
    if initial & not_delivered:
        issues.append("initial_and_not_delivered_overlap")
    if (initial | background | not_delivered) != required:
        issues.append("delivery_sets_do_not_account_for_all_required_layers")

    for item in layer_decisions:
        layer = item.get("layer")
        mode = item.get("delivery_mode")
        if mode in {"final", "provisional", "degraded"} and layer not in initial:
            issues.append(f"delivered_mode_missing_from_initial:{layer}")
        if mode == "background_pending" and (layer not in background or layer in initial):
            issues.append(f"background_mode_set_mismatch:{layer}")
        if mode == "not_delivered" and layer not in not_delivered:
            issues.append(f"not_delivered_mode_set_mismatch:{layer}")
        if mode != "not_delivered" and layer in not_delivered:
            issues.append(f"delivered_layer_in_not_delivered_set:{layer}")
        if layer in background and mode in {"final", "not_delivered"}:
            issues.append(f"invalid_background_mode:{layer}")

    supersession_layers = {
        item.get("layer") for item in planning_decision.get("supersession_plan", [])
    }
    if not supersession_layers <= background:
        issues.append("supersession_layer_missing_from_background_completion")
    return issues


def _best_coverage(case: dict[str, Any], layer: str) -> float:
    sources = _sources_for_layer(case, layer)
    if not sources:
        return 0.0
    return max(float(source.get("coverage", 0.0)) for source in sources)


def _delivery_mode(case: dict[str, Any], layer: str, has_problem: bool) -> str:
    layer_meta = next(item for item in case["required_layers"] if item["layer"] == layer)
    if layer_meta["criticality"] == "optional" and _best_coverage(case, layer) == 0:
        return "not_delivered"
    if has_problem:
        return "degraded"
    if case["resource_regime"].get("time_budget") == "tight":
        return "provisional"
    return "final"


def _planner_rationale(case: dict[str, Any], planner: str, ordered_layers: list[str]) -> str:
    if planner == "fixed":
        return "Uses a fixed global ordering; included as a baseline likely to fail some contract-specific priorities."
    if planner == "kg_only":
        return "Uses KG-visible criticality and source coverage, but does not interpret full product-contract tradeoffs."
    raise ValueError(f"Rationale for planner {planner!r} requires the LLM planning path.")


def _gate_result(layer: str, gate: str, passed: bool) -> dict[str, Any]:
    return {
        "gate_id": f"gate.{layer}.{gate}",
        "gate": gate,
        "passed": passed,
        "score": 1.0 if passed else 0.0,
    }


def _gap_severity(case: dict[str, Any], layer: str) -> str:
    layer_meta = next(item for item in case["required_layers"] if item["layer"] == layer)
    if layer_meta["criticality"] == "critical":
        return "high"
    if layer_meta["criticality"] == "important":
        return "medium"
    return "low"


def _gap_impact(layer: str, gap_type: str) -> str:
    return f"{layer} cannot be claimed as fully satisfied because of {gap_type}."


def _gap_mitigation(gap_type: str) -> str:
    if gap_type == "data_absent":
        return "Declare absence and avoid repeated retries until new evidence appears."
    if gap_type == "source_unavailable":
        return "Deliver provisional output if allowed and continue background materialization."
    if gap_type == "quality_failed":
        return "Deliver degraded output only with failed quality evidence and supersession plan."
    if gap_type == "source_mismatch":
        return "Expose semantic or freshness mismatch in the delivery report."
    return "Review product contract and update delivery state."


def _has_gap_for_layer(gaps: list[dict[str, Any]], layer: str) -> bool:
    return any(gap["layer"] == layer for gap in gaps)


def _satisfaction_state(
    case: dict[str, Any],
    planning_decision: dict[str, Any],
    quality_gate_result: dict[str, Any],
    gap_declaration: dict[str, Any],
    *,
    delivered_layers_override: set[str] | None = None,
) -> str:
    critical_layers = {
        layer["layer"] for layer in case["required_layers"] if layer["criticality"] == "critical"
    }
    delivered_layers = (
        delivered_layers_override
        if delivered_layers_override is not None
        else {
            decision["layer"]
            for decision in planning_decision["layer_decisions"]
            if decision["delivery_mode"] in {"final", "provisional", "degraded"}
        }
    )
    failed_critical_quality = any(
        result["layer"] in critical_layers and not result["passed"]
        for result in quality_gate_result["layer_results"]
    )
    critical_gap = any(gap["layer"] in critical_layers for gap in gap_declaration["gaps"])
    if critical_layers - delivered_layers:
        return "not_satisfied"
    if failed_critical_quality or critical_gap:
        return "degraded_but_usable"
    if gap_declaration["gaps"]:
        return "partially_satisfied"
    if any(decision["delivery_mode"] == "provisional" for decision in planning_decision["layer_decisions"]):
        return "partially_satisfied"
    return "fully_satisfied"


def create_research_llm_provider(env_path: Path = DEFAULT_ENV_PATH) -> OpenAICompatibleProvider:
    defaults = read_dotenv_defaults(env_path)
    for key, value in defaults.items():
        if value:
            os.environ.setdefault(key, value)
    provider_name = os.getenv("GEOFUSION_LLM_PROVIDER", "openai").strip().lower()
    if provider_name != "openai":
        raise RuntimeError(
            "LLM experiment planners require GEOFUSION_LLM_PROVIDER=openai, "
            f"got {provider_name!r}."
        )
    return OpenAICompatibleProvider.from_env()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a minimum product-contract KG research experiment."
    )
    parser.add_argument("--case", required=True, help="Case id from experiment_cases.json, e.g. C02.")
    parser.add_argument("--planner", required=True, choices=sorted(VALID_PLANNERS))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--cases", default=str(DEFAULT_CASES_PATH))
    parser.add_argument("--gold", default=str(DEFAULT_GOLD_PATH))
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH))
    parser.add_argument(
        "--execution-mode",
        choices=[item.value for item in ExperimentExecutionMode],
        default=ExperimentExecutionMode.PLANNING_ONLY.value,
        help="Keep controlled planning runs separate from real end-to-end execution.",
    )
    parser.add_argument(
        "--runtime-repo-root",
        default=str(REPO_ROOT),
        help="Repository/data root used by RawVectorSourceService in end-to-end mode.",
    )
    parser.add_argument(
        "--runtime-cache-dir",
        default=None,
        help="Optional source-materialization cache directory for end-to-end mode.",
    )
    parser.add_argument(
        "--runtime-artifact-index",
        default=None,
        help="Optional ArtifactRegistry JSON index path for end-to-end writeback.",
    )
    parser.add_argument(
        "--target-crs",
        default=None,
        help="Optional output CRS; defaults to the AOI-derived local UTM CRS.",
    )
    parser.add_argument(
        "--input-variant",
        type=int,
        default=0,
        help="Deterministic context-order variant used to test input-order robustness.",
    )
    args = parser.parse_args(argv)

    case = find_case(load_cases(Path(args.cases)), args.case)
    gold = find_gold(load_gold(Path(args.gold)), args.case)
    llm_provider = (
        create_research_llm_provider(Path(args.env_file))
        if args.planner in LLM_PLANNERS
        else None
    )
    output_dir = Path(args.output_dir)
    runtime_executor = None
    if args.execution_mode == ExperimentExecutionMode.END_TO_END.value:
        runtime_executor = ProductContractRuntimeExecutor(
            repo_root=Path(args.runtime_repo_root),
            artifact_registry_path=(
                Path(args.runtime_artifact_index)
                if args.runtime_artifact_index
                else output_dir / "runtime_artifact_index.json"
            ),
            cache_dir=(
                Path(args.runtime_cache_dir)
                if args.runtime_cache_dir
                else output_dir / "runtime_cache"
            ),
            target_crs=args.target_crs,
        )
    summary = run_product_contract_experiment(
        case=case,
        planner=args.planner,
        output_dir=output_dir,
        llm_provider=llm_provider,
        gold=gold,
        input_variant=args.input_variant,
        execution_mode=args.execution_mode,
        runtime_executor=runtime_executor,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if (
        args.execution_mode == ExperimentExecutionMode.END_TO_END.value
        and summary.get("runtime_status") == "failed"
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
