from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kg.inmemory_repository import InMemoryKGRepository
from llm.providers.openai_compatible import OpenAICompatibleProvider
from schemas.research_case_manifest import load_research_case_manifest
from schemas.research_llm_pilot import ResearchPlanningDecision, build_research_llm_pilot_schedule
from services.research_baselines import CanonicalContextFactory
from services.research_manifest_validation import validate_manifest_crosswalk


SYSTEM_PROMPT = """You are a geospatial emergency planning system.
Return exactly one JSON object conforming to the supplied output_schema.
Use only information present in the input. Do not invent sources, algorithms, contracts, or evidence.
Rejection, gaps, provisional delivery, degradation, and manual intervention are valid decisions.
"""

FORBIDDEN_PLANNER_KEYS = {
    "expected_consequence",
    "expected_outcome_classes",
    "gold_rubric",
    "quality_policy_id",
    "semantic_guard",
    "unsupported_terms",
}

FATAL_PILOT_FAILURES = {
    "http_error",
    "transport_error",
    "response_model_mismatch",
    "usage_missing",
    "token_budget_exceeded",
    "token_budget_preflight_exceeded",
}


def prepare_pilot(manifest_path: Path) -> tuple[Any, list[dict[str, Any]]]:
    manifest = load_research_case_manifest(manifest_path)
    schedule = build_research_llm_pilot_schedule()
    return schedule, prepare_research_schedule(manifest, schedule)


def prepare_research_schedule(manifest: Any, schedule: Any) -> list[dict[str, Any]]:
    repository = InMemoryKGRepository(experience_policy="pinned_snapshot")
    crosswalk_failures = validate_manifest_crosswalk(manifest, repository)
    if crosswalk_failures:
        raise ValueError(f"Research manifest KG crosswalk is not closed: {crosswalk_failures}")
    cases = {case.case_id: case for case in manifest.cases}
    factory = CanonicalContextFactory(repository)
    prepared: list[dict[str, Any]] = []
    for item in schedule.items:
        case = cases[item.case_id]
        projection = factory.project(factory.build(case), item.baseline_group)
        leaked_keys = sorted(FORBIDDEN_PLANNER_KEYS & set(_nested_keys(projection.payload)))
        if leaked_keys:
            raise ValueError(f"{item.run_id} planning input contains forbidden gold keys: {leaked_keys}")
        prepared.append(
            {
                "schedule": item.model_dump(mode="json"),
                "input_hash": projection.input_hash,
                "allowed_top_level_fields": projection.allowed_top_level_fields,
                "forbidden_top_level_fields": projection.forbidden_top_level_fields,
                "payload": projection.payload,
            }
        )
    return prepared


def execute_pilot(
    prepared: list[dict[str, Any]],
    output_dir: Path,
    *,
    pilot_scope: str,
    claim_eligible: bool = False,
    protocol_id: str | None = None,
    model_revision: str | None = None,
) -> list[dict[str, Any]]:
    model = _required_env("GEOFUSION_LLM_MODEL")
    base_url = os.getenv("GEOFUSION_LLM_BASE_URL", "https://api.openai.com/v1")
    max_output_tokens = _required_positive_int("GEOFUSION_LLM_MAX_OUTPUT_TOKENS")
    token_budget = _required_positive_int("GEOFUSION_LLM_PILOT_TOKEN_BUDGET")
    provider = OpenAICompatibleProvider(
        api_key=_required_env("OPENAI_API_KEY", "GEOFUSION_LLM_API_KEY"),
        model=model,
        base_url=base_url,
        timeout_sec=int(os.getenv("GEOFUSION_LLM_TIMEOUT_SEC", "60")),
        allow_json_salvage=False,
        max_output_tokens=max_output_tokens,
    )
    conservative_total_bound = _validate_batch_token_budget(
        prepared,
        max_output_tokens=max_output_tokens,
        token_budget=token_budget,
    )
    _write_json(
        output_dir / "execution_config.json",
        {
            "provider": "openai_compatible",
            "base_url_host": urlsplit(base_url).netloc,
            "requested_model": model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "max_output_tokens": max_output_tokens,
            "token_budget": token_budget,
            "conservative_total_token_bound": conservative_total_bound,
            "fallback": "forbidden",
            "json_salvage": "forbidden",
            "transport_retries": 0,
            "semantic_repairs": 0,
            "pilot_scope": pilot_scope,
            "claim_eligible": claim_eligible,
            "protocol_id": protocol_id,
            "model_revision": model_revision,
        },
    )
    results: list[dict[str, Any]] = []
    consumed_tokens = 0
    for run in prepared:
        run_id = run["schedule"]["run_id"]
        run_dir = output_dir / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        result: dict[str, Any] = {"run_id": run_id, "input_hash": run["input_hash"], "success": False}
        estimated_prompt_tokens = _conservative_token_estimate(SYSTEM_PROMPT, run["payload"])
        if consumed_tokens + estimated_prompt_tokens + max_output_tokens > token_budget:
            result.update(
                failure_class="token_budget_preflight_exceeded",
                error=f"Pilot token budget of {token_budget} cannot cover the next bounded request.",
            )
            result["attempt"] = None
            _write_json(run_dir / "result.json", result)
            results.append(result)
            break
        try:
            raw_plan = provider.generate_workflow_plan(SYSTEM_PROMPT, run["payload"])
        except Exception as exc:  # noqa: BLE001
            attempt_failure = (provider.last_attempt or {}).get("failure_class")
            result.update(failure_class=attempt_failure or "provider_failure", error=str(exc))
        else:
            attempt = provider.last_attempt or {}
            response_model = attempt.get("response_model")
            usage = attempt.get("usage")
            total_tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
            if response_model != model:
                result.update(
                    failure_class="response_model_mismatch",
                    error=f"Requested model {model!r}, provider returned {response_model!r}.",
                )
            elif not isinstance(total_tokens, int) or total_tokens < 0:
                result.update(
                    failure_class="usage_missing",
                    error="Provider response did not include a valid usage.total_tokens value.",
                )
            else:
                consumed_tokens += total_tokens
                if consumed_tokens > token_budget:
                    result.update(
                        failure_class="token_budget_exceeded",
                        error=f"Pilot token budget of {token_budget} was exceeded by the provider response.",
                    )
                else:
                    try:
                        plan = ResearchPlanningDecision.model_validate(raw_plan)
                    except ValidationError as exc:
                        result.update(failure_class="output_schema_validation_failure", error=str(exc))
                    else:
                        result.update(success=True, plan=plan.model_dump(mode="json"))
            result["consumed_tokens_after_call"] = consumed_tokens
        result["attempt"] = provider.last_attempt
        _write_json(run_dir / "result.json", result)
        results.append(result)
        if result.get("failure_class") in FATAL_PILOT_FAILURES:
            break
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare or execute the 18-call FusionAgent LLM pilot.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("docs/current/research-case-manifest-v1.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", help="Make real provider calls. Default is dry-run only.")
    parser.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="Restrict the pilot to one or more scheduled case IDs.",
    )
    parser.add_argument(
        "--replicate",
        action="append",
        type=int,
        dest="replicates",
        help="Restrict the pilot to one or more scheduled replicate numbers.",
    )
    args = parser.parse_args()

    if args.output.exists():
        raise RuntimeError(f"Refusing to overwrite pilot evidence directory: {args.output}")
    args.output.mkdir(parents=True)
    schedule, prepared = prepare_pilot(args.manifest)
    prepared = _select_pilot_subset(
        prepared,
        case_ids=args.case_ids,
        replicates=args.replicates,
    )
    pilot_scope = "full_18_call_pilot" if len(prepared) == len(schedule.items) else "diagnostic_subset_pilot"
    schedule_payload = schedule.model_dump(mode="json")
    schedule_metadata = dict(schedule_payload["metadata"])
    schedule_metadata.update(
        {
            "pilot_scope": pilot_scope,
            "claim_eligible": False,
            "selected_call_count": len(prepared),
            "selection": {
                "case_ids": sorted({item["schedule"]["case_id"] for item in prepared}),
                "replicates": sorted({item["schedule"]["replicate"] for item in prepared}),
            },
        }
    )
    schedule_payload.update(
        {
            "cases": sorted({item["schedule"]["case_id"] for item in prepared}),
            "knowledge_conditions": sorted(
                {item["schedule"]["knowledge_condition"] for item in prepared}
            ),
            "replicates": len({item["schedule"]["replicate"] for item in prepared}),
            "metadata": schedule_metadata,
        }
    )
    schedule_payload["items"] = [item["schedule"] for item in prepared]
    _write_json(args.output / "schedule.json", schedule_payload)
    _write_json(args.output / "prepared_inputs.json", prepared)
    if not args.execute:
        _write_json(
            args.output / "preflight.json",
            {
                "status": "prepared",
                "main_call_count": len(prepared),
                "pilot_scope": pilot_scope,
                "claim_eligible": False,
            },
        )
        return 0

    results = execute_pilot(prepared, args.output, pilot_scope=pilot_scope)
    _write_json(
        args.output / "pilot_summary.json",
        {
            "status": "completed_with_observed_failures" if not all(item["success"] for item in results) else "completed",
            "main_call_count": len(results),
            "successful_calls": sum(1 for item in results if item["success"]),
            "failed_calls": sum(1 for item in results if not item["success"]),
            "consumed_tokens": sum(_attempt_total_tokens(item.get("attempt")) for item in results),
        },
    )
    return 0


def _select_pilot_subset(
    prepared: list[dict[str, Any]],
    *,
    case_ids: list[str] | None,
    replicates: list[int] | None,
) -> list[dict[str, Any]]:
    known_cases = {item["schedule"]["case_id"] for item in prepared}
    known_replicates = {item["schedule"]["replicate"] for item in prepared}
    requested_cases = set(case_ids or known_cases)
    requested_replicates = set(replicates or known_replicates)
    unknown_cases = requested_cases - known_cases
    unknown_replicates = requested_replicates - known_replicates
    if unknown_cases:
        raise ValueError(f"Unknown pilot case IDs: {sorted(unknown_cases)}")
    if unknown_replicates:
        raise ValueError(f"Unknown pilot replicates: {sorted(unknown_replicates)}")
    selected = [
        item
        for item in prepared
        if item["schedule"]["case_id"] in requested_cases
        and item["schedule"]["replicate"] in requested_replicates
    ]
    if not selected:
        raise ValueError("Pilot selection is empty")
    return selected


def _required_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    raise RuntimeError(f"Missing required environment variable: {' or '.join(names)}")


def _required_positive_int(name: str) -> int:
    raw = _required_env(name)
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero.")
    return value


def _conservative_token_estimate(system_prompt: str, context: dict[str, Any]) -> int:
    encoded = (system_prompt + json.dumps(context, ensure_ascii=False, sort_keys=True)).encode("utf-8")
    return (len(encoded) + 1) // 2


def _validate_batch_token_budget(
    prepared: list[dict[str, Any]],
    *,
    max_output_tokens: int,
    token_budget: int,
) -> int:
    conservative_total_bound = sum(
        _conservative_token_estimate(SYSTEM_PROMPT, run["payload"]) + max_output_tokens
        for run in prepared
    )
    if conservative_total_bound > token_budget:
        raise RuntimeError(
            "GEOFUSION_LLM_PILOT_TOKEN_BUDGET is below the conservative batch bound: "
            f"budget={token_budget}, bound={conservative_total_bound}."
        )
    return conservative_total_bound


def _attempt_total_tokens(attempt: Any) -> int:
    if not isinstance(attempt, dict):
        return 0
    usage = attempt.get("usage")
    if not isinstance(usage, dict):
        return 0
    total_tokens = usage.get("total_tokens")
    return int(total_tokens) if isinstance(total_tokens, int) and total_tokens >= 0 else 0


def _nested_keys(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _nested_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _nested_keys(item)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
