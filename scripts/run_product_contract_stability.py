from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from llm.providers.base import LLMProvider
from schemas.product_contract_stability import (
    ArtifactDigest,
    RunOutcome,
    SemanticDecisionRecord,
    StabilityAuditRecord,
    StabilityProtocol,
    StabilityScope,
)
from scripts.run_product_contract_experiment import (
    DEFAULT_CASES_PATH,
    DEFAULT_ENV_PATH,
    DEFAULT_GOLD_PATH,
    LLM_CALLING_POLICY,
    LLM_PLANNERS,
    VALID_PLANNERS,
    create_research_llm_provider,
    find_case,
    find_gold,
    load_cases,
    load_gold,
    run_product_contract_experiment,
)

DEFAULT_PROTOCOL_PATH = REPO_ROOT / "docs/thesis/stability_protocol.json"
IMPLEMENTATION_PATHS = [
    REPO_ROOT / "PROJECT.md",
    REPO_ROOT / "docs/thesis/experiment_cases.json",
    REPO_ROOT / "docs/thesis/experiment_gold.json",
    REPO_ROOT / "docs/thesis/stability_protocol.json",
    REPO_ROOT / "schemas/product_contract_experiment.py",
    REPO_ROOT / "schemas/product_contract_stability.py",
    REPO_ROOT / "scripts/run_product_contract_experiment.py",
    REPO_ROOT / "scripts/run_product_contract_stability.py",
    REPO_ROOT / "llm/providers/openai_compatible.py",
]


def load_stability_protocol(path: Path = DEFAULT_PROTOCOL_PATH) -> StabilityProtocol:
    return StabilityProtocol.model_validate_json(Path(path).read_text(encoding="utf-8"))


def build_schedule(
    protocol: StabilityProtocol,
    *,
    case_ids: list[str],
    planners: list[str],
    repetitions: int,
) -> list[dict[str, Any]]:
    unknown_cases = set(case_ids) - set(protocol.case_ids)
    unknown_planners = set(planners) - set(protocol.planners)
    if unknown_cases:
        raise ValueError(f"Cases are not present in the frozen protocol: {sorted(unknown_cases)}")
    if unknown_planners:
        raise ValueError(
            f"Planners are not present in the frozen protocol: {sorted(unknown_planners)}"
        )
    if repetitions < 1 or repetitions > protocol.formal_repetitions_per_case_planner:
        raise ValueError(
            "repetitions must be between 1 and the frozen formal repetition count."
        )

    schedule = [
        {
            "case_id": case_id,
            "planner": planner,
            "repetition_index": repetition_index,
            "input_variant": protocol.input_variants[
                (repetition_index - 1) % len(protocol.input_variants)
            ],
        }
        for case_id in case_ids
        for planner in planners
        for repetition_index in range(1, repetitions + 1)
    ]
    seed_material = {
        "schedule_seed": protocol.schedule_seed,
        "case_ids": case_ids,
        "planners": planners,
        "repetitions": repetitions,
    }
    seed = int(_hash_json(seed_material)[:16], 16)
    random.Random(seed).shuffle(schedule)
    for index, item in enumerate(schedule):
        item["sequence_index"] = index
    return schedule


def run_stability_batch(
    *,
    output_dir: Path,
    protocol_path: Path = DEFAULT_PROTOCOL_PATH,
    cases_path: Path = DEFAULT_CASES_PATH,
    gold_path: Path = DEFAULT_GOLD_PATH,
    env_path: Path = DEFAULT_ENV_PATH,
    scope: StabilityScope = StabilityScope.DEVELOPMENT,
    case_ids: list[str] | None = None,
    planners: list[str] | None = None,
    repetitions: int | None = None,
    provider_factory: Callable[[str], LLMProvider] | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    protocol = load_stability_protocol(protocol_path)
    selected_cases = case_ids or list(protocol.case_ids)
    selected_planners = planners or list(protocol.planners)
    selected_repetitions = repetitions or (
        protocol.formal_repetitions_per_case_planner
        if scope == StabilityScope.FORMAL
        else 1
    )
    _validate_batch_selection(
        protocol,
        scope=scope,
        case_ids=selected_cases,
        planners=selected_planners,
        repetitions=selected_repetitions,
    )
    _validate_calling_policy(protocol)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = output_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = output_dir / "audit_ledger.jsonl"
    if ledger_path.exists() and not resume:
        raise FileExistsError(
            f"Audit ledger already exists at {ledger_path}; pass resume=True to continue."
        )

    cases = load_cases(cases_path)
    gold_rows = load_gold(gold_path)
    for case_id in selected_cases:
        find_case(cases, case_id)
        find_gold(gold_rows, case_id)

    protocol_payload = protocol.model_dump(mode="json")
    protocol_hash = _hash_json(protocol_payload)
    schedule = build_schedule(
        protocol,
        case_ids=selected_cases,
        planners=selected_planners,
        repetitions=selected_repetitions,
    )
    batch_config = {
        "protocol_hash": protocol_hash,
        "scope": scope.value,
        "case_ids": selected_cases,
        "planners": selected_planners,
        "repetitions": selected_repetitions,
    }
    batch_id = f"stability-{_hash_json(batch_config)[:16]}"
    for item in schedule:
        item["run_id"] = (
            f"{batch_id}.{item['sequence_index']:04d}.{item['case_id']}."
            f"{item['planner']}.r{item['repetition_index']}.v{item['input_variant']}"
        )

    code_commit, code_dirty = _git_state()
    if scope == StabilityScope.FORMAL and code_dirty:
        raise RuntimeError("Formal stability runs require a clean Git worktree.")
    implementation_manifest = _implementation_manifest(protocol_path)
    implementation_manifest_hash = _hash_json(implementation_manifest)

    metadata_path = output_dir / "batch_metadata.json"
    if resume:
        if not metadata_path.exists():
            raise FileNotFoundError("Cannot resume without batch_metadata.json.")
        previous_metadata = _read_json(metadata_path)
        if previous_metadata["batch_id"] != batch_id:
            raise ValueError("Resume selection does not match the existing batch.")
        if previous_metadata["implementation_manifest_hash"] != implementation_manifest_hash:
            raise ValueError("Implementation files changed; refusing to resume the audit chain.")
        batch_created_at = previous_metadata["created_at"]
    else:
        batch_created_at = _utc_now()

    metadata = {
        "batch_id": batch_id,
        "created_at": batch_created_at,
        "updated_at": _utc_now(),
        "scope": scope.value,
        "claim_eligible": scope == StabilityScope.FORMAL and not code_dirty,
        "protocol_version": protocol.protocol_version,
        "protocol_hash": protocol_hash,
        "case_ids": selected_cases,
        "planners": selected_planners,
        "repetitions": selected_repetitions,
        "scheduled_run_count": len(schedule),
        "code_commit": code_commit,
        "code_dirty": code_dirty,
        "implementation_manifest_hash": implementation_manifest_hash,
    }
    _write_json(metadata_path, metadata)
    _write_json(output_dir / "protocol_snapshot.json", protocol_payload)
    _write_json(output_dir / "schedule.json", {"batch_id": batch_id, "runs": schedule})
    _write_json(output_dir / "implementation_manifest.json", implementation_manifest)

    existing_records = verify_audit_ledger(ledger_path) if ledger_path.exists() else []
    completed_run_ids = {record.run_id for record in existing_records}
    previous_record_hash = existing_records[-1].record_hash if existing_records else None
    records = list(existing_records)

    for item in schedule:
        if item["run_id"] in completed_run_ids:
            continue
        run_dir = runs_dir / item["run_id"]
        _preserve_orphaned_run_dir(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        case = find_case(cases, item["case_id"])
        gold = find_gold(gold_rows, item["case_id"])
        provider = None
        if item["planner"] in LLM_PLANNERS:
            provider = (
                provider_factory(item["planner"])
                if provider_factory is not None
                else create_research_llm_provider(env_path)
            )
            if (
                scope == StabilityScope.FORMAL
                and getattr(provider, "model", None)
                != protocol.llm_calling_policy.expected_model
            ):
                raise RuntimeError(
                    "Formal run model does not match the frozen protocol: "
                    f"expected={protocol.llm_calling_policy.expected_model}, "
                    f"actual={getattr(provider, 'model', None)}"
                )

        started_at = _utc_now()
        started = time.perf_counter()
        caught_error: Exception | None = None
        summary: dict[str, Any] | None = None
        try:
            summary = run_product_contract_experiment(
                case=case,
                planner=item["planner"],
                output_dir=run_dir,
                llm_provider=provider,
                gold=gold,
                input_variant=item["input_variant"],
            )
        except Exception as exc:  # noqa: BLE001
            caught_error = exc
        completed_at = _utc_now()
        duration_ms = (time.perf_counter() - started) * 1000

        record_payload = _build_audit_record_payload(
            item=item,
            scope=scope,
            claim_eligible=metadata["claim_eligible"],
            protocol=protocol,
            protocol_hash=protocol_hash,
            case=case,
            gold=gold,
            code_commit=code_commit,
            code_dirty=code_dirty,
            implementation_manifest_hash=implementation_manifest_hash,
            provider=provider,
            run_dir=run_dir,
            summary=summary,
            error=caught_error,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            previous_record_hash=previous_record_hash,
        )
        record_hash = _hash_json(record_payload)
        record_payload["record_hash"] = record_hash
        record = StabilityAuditRecord.model_validate(record_payload)
        _write_json(run_dir / "audit_record.json", record.model_dump(mode="json"))
        _append_jsonl(ledger_path, record.model_dump(mode="json"))
        records.append(record)
        previous_record_hash = record_hash

    verified_records = verify_audit_ledger(ledger_path)
    stability_summary = build_stability_summary(
        records=verified_records,
        batch_id=batch_id,
        scope=scope,
        claim_eligible=metadata["claim_eligible"],
        protocol=protocol,
    )
    _write_json(output_dir / "stability_summary.json", stability_summary)
    metadata["updated_at"] = _utc_now()
    metadata["completed_run_count"] = len(verified_records)
    metadata["failed_run_count"] = sum(
        record.outcome == RunOutcome.FAILED for record in verified_records
    )
    _write_json(metadata_path, metadata)

    audit_manifest = {
        "batch_id": batch_id,
        "protocol_hash": protocol_hash,
        "record_count": len(verified_records),
        "first_record_hash": verified_records[0].record_hash if verified_records else None,
        "last_record_hash": verified_records[-1].record_hash if verified_records else None,
        "chain_valid": True,
        "files": [
            _digest_for_path(path, output_dir).model_dump(mode="json")
            for path in (
                output_dir / "protocol_snapshot.json",
                output_dir / "schedule.json",
                output_dir / "implementation_manifest.json",
                output_dir / "batch_metadata.json",
                output_dir / "audit_ledger.jsonl",
                output_dir / "stability_summary.json",
            )
        ],
    }
    _write_json(output_dir / "audit_manifest.json", audit_manifest)
    return stability_summary


def verify_audit_ledger(path: Path) -> list[StabilityAuditRecord]:
    path = Path(path)
    records: list[StabilityAuditRecord] = []
    previous_hash: str | None = None
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        claimed_hash = payload.pop("record_hash", None)
        actual_hash = _hash_json(payload)
        if claimed_hash != actual_hash:
            raise ValueError(f"Audit record hash mismatch at line {line_number}.")
        if payload.get("previous_record_hash") != previous_hash:
            raise ValueError(f"Audit chain predecessor mismatch at line {line_number}.")
        payload["record_hash"] = claimed_hash
        record = StabilityAuditRecord.model_validate(payload)
        records.append(record)
        previous_hash = claimed_hash
    return records


def build_stability_summary(
    *,
    records: list[StabilityAuditRecord],
    batch_id: str,
    scope: StabilityScope,
    claim_eligible: bool,
    protocol: StabilityProtocol,
) -> dict[str, Any]:
    planner_groups: dict[str, list[StabilityAuditRecord]] = {}
    case_planner_groups: dict[str, list[StabilityAuditRecord]] = {}
    for record in records:
        planner_groups.setdefault(record.planner, []).append(record)
        case_planner_groups.setdefault(f"{record.case_id}|{record.planner}", []).append(record)
    return {
        "batch_id": batch_id,
        "scope": scope.value,
        "claim_eligible": claim_eligible,
        "protocol_version": protocol.protocol_version,
        "failed_run_policy": protocol.statistics.failed_run_policy,
        "run_count": len(records),
        "success_count": sum(record.outcome == RunOutcome.SUCCEEDED for record in records),
        "failure_count": sum(record.outcome == RunOutcome.FAILED for record in records),
        "planner_summaries": {
            planner: _summarize_group(group)
            for planner, group in sorted(planner_groups.items())
        },
        "case_planner_summaries": {
            key: _summarize_group(group)
            for key, group in sorted(case_planner_groups.items())
        },
    }


def _build_audit_record_payload(
    *,
    item: dict[str, Any],
    scope: StabilityScope,
    claim_eligible: bool,
    protocol: StabilityProtocol,
    protocol_hash: str,
    case: dict[str, Any],
    gold: dict[str, Any],
    code_commit: str,
    code_dirty: bool,
    implementation_manifest_hash: str,
    provider: LLMProvider | None,
    run_dir: Path,
    summary: dict[str, Any] | None,
    error: Exception | None,
    started_at: str,
    completed_at: str,
    duration_ms: float,
    previous_record_hash: str | None,
) -> dict[str, Any]:
    success = error is None and summary is not None
    decision = _read_json(run_dir / "planning_decision.json") if success else None
    evaluation = _read_json(run_dir / "evaluation_result.json") if success else None
    failure = (
        _read_json(run_dir / "planning_failure.json")
        if (run_dir / "planning_failure.json").exists()
        else {}
    )
    planning_attempts = (
        decision.get("planning_attempts", []) if decision else failure.get("planning_attempts", [])
    )
    planning_latency_ms = (
        decision.get("planning_latency_ms")
        if decision
        else sum(
            float(attempt["latency_ms"])
            for attempt in planning_attempts
            if attempt.get("latency_ms") is not None
        )
    )
    token_usage = (
        decision.get("planning_usage_total")
        if decision
        else _sum_attempt_usage(planning_attempts)
    )
    artifacts = [
        _digest_for_path(path, run_dir).model_dump(mode="json")
        for path in sorted(run_dir.rglob("*"))
        if path.is_file() and path.name != "audit_record.json"
    ]
    return {
        "record_type": "product_contract_stability_run",
        "record_version": "1",
        "run_id": item["run_id"],
        "sequence_index": item["sequence_index"],
        "previous_record_hash": previous_record_hash,
        "protocol_version": protocol.protocol_version,
        "protocol_hash": protocol_hash,
        "scope": scope.value,
        "claim_eligible": claim_eligible,
        "case_id": item["case_id"],
        "planner": item["planner"],
        "repetition_index": item["repetition_index"],
        "input_variant": item["input_variant"],
        "outcome": RunOutcome.SUCCEEDED.value if success else RunOutcome.FAILED.value,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_ms": duration_ms,
        "case_input_hash": _hash_json(case),
        "gold_label_hash": _hash_json(gold),
        "code_commit": code_commit,
        "code_dirty": code_dirty,
        "implementation_manifest_hash": implementation_manifest_hash,
        "planning_provider": (
            decision.get("planning_provider")
            if decision
            else failure.get("planning_provider") or getattr(provider, "provider_name", None)
        ),
        "planning_model": (
            decision.get("planning_model")
            if decision
            else failure.get("planning_model") or getattr(provider, "last_model", None)
        ),
        "base_url_host": _provider_host(provider),
        "prompt_version": (
            decision.get("prompt_version") if decision else failure.get("prompt_version")
        ),
        "prompt_hash": decision.get("prompt_hash") if decision else failure.get("prompt_hash"),
        "context_hash": (
            decision.get("context_hash") if decision else failure.get("context_hash")
        ),
        "planning_retry_count": (
            int(decision.get("planning_retry_count", 0))
            if decision
            else max(len(planning_attempts) - 1, 0)
        ),
        "planning_latency_ms": planning_latency_ms,
        "token_usage": token_usage,
        "metrics": evaluation["metrics"] if evaluation else None,
        "semantic_decision": _semantic_decision(decision) if decision else None,
        "artifact_dir": str(run_dir.relative_to(run_dir.parents[1])).replace("\\", "/"),
        "artifacts": artifacts,
        "failure_type": None if success else failure.get("failure_type") or type(error).__name__,
        "failure_reason": None if success else failure.get("failure_reason") or str(error),
    }


def _semantic_decision(decision: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "strategy_id": decision["strategy_id"],
        "priority_tiers": [sorted(tier) for tier in decision["priority_tiers"]],
        "initial_delivery_layers": sorted(decision["initial_delivery_layers"]),
        "background_completion_layers": sorted(
            decision["background_completion_layers"]
        ),
        "not_delivered_layers": sorted(decision["not_delivered_layers"]),
        "layer_decisions": sorted(
            [
                {
                    **item,
                    "selected_sources": sorted(item["selected_sources"]),
                }
                for item in decision["layer_decisions"]
            ],
            key=lambda item: item["layer"],
        ),
        "planner_gap_proposal": sorted(
            decision["planner_gap_proposal"],
            key=lambda item: (item["layer"], item["gap_type"]),
        ),
        "supersession_plan": sorted(
            [
                {
                    **item,
                    "trigger_source_ids": sorted(item["trigger_source_ids"]),
                }
                for item in decision["supersession_plan"]
            ],
            key=lambda item: item["layer"],
        ),
    }
    precedence_pairs = sorted(
        [
            [earlier, later]
            for tier_index, tier in enumerate(decision["priority_tiers"])
            for later_tier in decision["priority_tiers"][tier_index + 1 :]
            for earlier in tier
            for later in later_tier
        ]
    )
    return SemanticDecisionRecord(
        decision_signature=_hash_json(normalized),
        strategy_id=decision["strategy_id"],
        priority_precedence_pairs=precedence_pairs,
        initial_delivery_layers=sorted(decision["initial_delivery_layers"]),
        background_completion_layers=sorted(decision["background_completion_layers"]),
        not_delivered_layers=sorted(decision["not_delivered_layers"]),
        planner_gap_keys=sorted(
            [
                [item["layer"], item["gap_type"]]
                for item in decision["planner_gap_proposal"]
            ]
        ),
    ).model_dump(mode="json")


def _summarize_group(records: list[StabilityAuditRecord]) -> dict[str, Any]:
    successful = [record for record in records if record.outcome == RunOutcome.SUCCEEDED]
    failures = [record for record in records if record.outcome == RunOutcome.FAILED]
    metric_names = sorted(
        {
            key
            for record in successful
            for key, value in (record.metrics or {}).items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
    )
    semantic_records = [record.semantic_decision for record in successful]
    return {
        "run_count": len(records),
        "success_count": len(successful),
        "failure_count": len(failures),
        "success_rate": len(successful) / len(records) if records else 0.0,
        "failure_rate": len(failures) / len(records) if records else 0.0,
        "repair_rate": (
            sum(record.planning_retry_count > 0 for record in records) / len(records)
            if records
            else 0.0
        ),
        "mean_retry_count": (
            statistics.fmean(record.planning_retry_count for record in records)
            if records
            else 0.0
        ),
        "failure_types": dict(sorted(Counter(record.failure_type for record in failures).items())),
        "metric_distributions": {
            metric_name: _distribution(
                [float(record.metrics[metric_name]) for record in successful]
            )
            for metric_name in metric_names
        },
        "semantic_stability": {
            "strategy_mode_agreement": _mode_agreement(
                [item.strategy_id for item in semantic_records]
            ),
            "priority_pairwise_jaccard": _mean_pairwise_jaccard(
                [
                    {tuple(pair) for pair in item.priority_precedence_pairs}
                    for item in semantic_records
                ]
            ),
            "initial_delivery_jaccard": _mean_pairwise_jaccard(
                [set(item.initial_delivery_layers) for item in semantic_records]
            ),
            "background_completion_jaccard": _mean_pairwise_jaccard(
                [set(item.background_completion_layers) for item in semantic_records]
            ),
            "not_delivered_jaccard": _mean_pairwise_jaccard(
                [set(item.not_delivered_layers) for item in semantic_records]
            ),
            "planner_gap_jaccard": _mean_pairwise_jaccard(
                [
                    {tuple(pair) for pair in item.planner_gap_keys}
                    for item in semantic_records
                ]
            ),
            "exact_decision_signature_agreement": _mode_agreement(
                [item.decision_signature for item in semantic_records]
            ),
        },
    }


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "mean": statistics.fmean(values) if values else None,
        "median": statistics.median(values) if values else None,
        "sample_sd": statistics.stdev(values) if len(values) > 1 else None,
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
    }


def _mode_agreement(values: list[str]) -> float | None:
    if not values:
        return None
    return max(Counter(values).values()) / len(values)


def _mean_pairwise_jaccard(values: list[set[Any]]) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return 1.0
    scores = []
    for left_index, left in enumerate(values):
        for right in values[left_index + 1 :]:
            union = left | right
            scores.append(len(left & right) / len(union) if union else 1.0)
    return statistics.fmean(scores)


def _validate_batch_selection(
    protocol: StabilityProtocol,
    *,
    scope: StabilityScope,
    case_ids: list[str],
    planners: list[str],
    repetitions: int,
) -> None:
    if not case_ids or not planners:
        raise ValueError("At least one case and planner are required.")
    if set(planners) - VALID_PLANNERS:
        raise ValueError(f"Unknown planners: {sorted(set(planners) - VALID_PLANNERS)}")
    if scope == StabilityScope.FORMAL:
        if case_ids != protocol.case_ids:
            raise ValueError("Formal scope must use the frozen case order and complete case set.")
        if planners != protocol.planners:
            raise ValueError("Formal scope must use the frozen planner order and all five baselines.")
        if repetitions != protocol.formal_repetitions_per_case_planner:
            raise ValueError("Formal scope must use the frozen repetition count.")


def _validate_calling_policy(protocol: StabilityProtocol) -> None:
    expected = protocol.llm_calling_policy
    if LLM_CALLING_POLICY != {
        "temperature": expected.temperature,
        "response_format": expected.response_format,
        "grounding_repair_retries": expected.grounding_repair_retries,
    }:
        raise ValueError("Runner LLM calling policy differs from the frozen protocol.")


def _implementation_manifest(protocol_path: Path) -> dict[str, Any]:
    paths = list(IMPLEMENTATION_PATHS)
    protocol_path = Path(protocol_path).resolve()
    if protocol_path not in {path.resolve() for path in paths}:
        paths.append(protocol_path)
    return {
        "files": [
            _digest_for_path(path, REPO_ROOT).model_dump(mode="json")
            for path in paths
        ],
    }


def _git_state() -> tuple[str, bool]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return commit, bool(status.strip())


def _provider_host(provider: LLMProvider | None) -> str | None:
    if provider is None:
        return None
    base_url = str(getattr(provider, "base_url", "") or "")
    return urlparse(base_url).netloc or None


def _sum_attempt_usage(attempts: list[dict[str, Any]]) -> dict[str, int] | None:
    totals: dict[str, int] = {}
    for attempt in attempts:
        usage = attempt.get("usage")
        if not isinstance(usage, dict):
            continue
        for key, value in usage.items():
            if isinstance(value, int):
                totals[key] = totals.get(key, 0) + value
    return totals or None


def _preserve_orphaned_run_dir(path: Path) -> None:
    if not path.exists() or not any(path.iterdir()):
        return
    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path.rename(path.with_name(f"{path.name}.orphaned.{suffix}"))


def _digest_for_path(path: Path, relative_root: Path) -> ArtifactDigest:
    path = Path(path)
    try:
        relative_path = str(path.resolve().relative_to(Path(relative_root).resolve()))
    except ValueError:
        relative_path = str(path.resolve())
    return ArtifactDigest(
        relative_path=relative_path.replace("\\", "/"),
        sha256=_hash_bytes(path.read_bytes()),
        size_bytes=path.stat().st_size,
    )


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _hash_json(payload: Any) -> str:
    return _hash_bytes(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run repeated product-contract experiments with a hash-chained audit ledger."
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--protocol", default=str(DEFAULT_PROTOCOL_PATH))
    parser.add_argument("--cases-file", default=str(DEFAULT_CASES_PATH))
    parser.add_argument("--gold-file", default=str(DEFAULT_GOLD_PATH))
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH))
    parser.add_argument(
        "--scope",
        choices=[scope.value for scope in StabilityScope],
        default=StabilityScope.DEVELOPMENT.value,
    )
    parser.add_argument("--cases", help="Comma-separated case IDs; development scope only.")
    parser.add_argument("--planners", help="Comma-separated planners; development scope only.")
    parser.add_argument("--repetitions", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)

    summary = run_stability_batch(
        output_dir=Path(args.output_dir),
        protocol_path=Path(args.protocol),
        cases_path=Path(args.cases_file),
        gold_path=Path(args.gold_file),
        env_path=Path(args.env_file),
        scope=StabilityScope(args.scope),
        case_ids=_parse_csv(args.cases),
        planners=_parse_csv(args.planners),
        repetitions=args.repetitions,
        resume=args.resume,
    )
    print(
        json.dumps(
            {
                "batch_id": summary["batch_id"],
                "scope": summary["scope"],
                "claim_eligible": summary["claim_eligible"],
                "run_count": summary["run_count"],
                "success_count": summary["success_count"],
                "failure_count": summary["failure_count"],
                "output_dir": str(Path(args.output_dir)),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
