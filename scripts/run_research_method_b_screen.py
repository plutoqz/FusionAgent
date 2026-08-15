from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kg.inmemory_repository import InMemoryKGRepository
from schemas.research_case_manifest import load_research_case_manifest
from scripts.run_research_llm_pilot import (
    FORBIDDEN_PLANNER_KEYS,
    SYSTEM_PROMPT,
    _nested_keys,
    _write_json,
    execute_pilot,
)
from services.research_contract_aware_planning import (
    METHOD_B_ID,
    build_contract_aware_projection,
)


PROTOCOL_ID = "fusionagent.method-b-development-screen.v1"
SCHEDULE_SEED = 20260815
BASELINE_AUDIT = Path(
    r"D:\code\fusionagent-evidence\p3-planning-repeated\2026-08-15-deepseek-v4-flash-repeated-combined-v1\formal_combined_automatic_audit.json"
)


def prepare_method_b_screen(manifest_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = load_research_case_manifest(manifest_path)
    repository = InMemoryKGRepository(experience_policy="pinned_snapshot")
    cases = {case.case_id: case for case in manifest.cases}
    items = [
        {
            "run_id": f"method-b-{case_id.lower()}-r1",
            "case_id": case_id,
            "knowledge_condition": "task_conditioned_contract_aware_kg",
            "replicate": 1,
            "input_variant": METHOD_B_ID,
        }
        for case_id in sorted(cases)
    ]
    random.Random(SCHEDULE_SEED).shuffle(items)
    prepared = []
    for item in items:
        projection = build_contract_aware_projection(cases[item["case_id"]], repository)
        leaked = sorted(FORBIDDEN_PLANNER_KEYS & set(_nested_keys(projection.payload)))
        if leaked:
            raise ValueError(f"{item['run_id']} planning input contains forbidden gold keys: {leaked}")
        prepared.append(
            {
                "schedule": item,
                "input_hash": projection.input_hash,
                "allowed_top_level_fields": projection.allowed_top_level_fields,
                "forbidden_top_level_fields": projection.forbidden_top_level_fields,
                "payload": projection.payload,
            }
        )
    schedule = {
        "protocol_id": PROTOCOL_ID,
        "status": "development_screen",
        "schedule_seed": SCHEDULE_SEED,
        "method_id": METHOD_B_ID,
        "cases": sorted(cases),
        "replicates": 1,
        "items": items,
    }
    return schedule, prepared


def run_screen(manifest_path: Path, output: Path, *, execute: bool) -> int:
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite method B screen directory: {output}")
    if not BASELINE_AUDIT.is_file():
        raise RuntimeError(f"Missing immutable 90-run development baseline audit: {BASELINE_AUDIT}")
    schedule, prepared = prepare_method_b_screen(manifest_path)
    output.mkdir(parents=True)
    _write_json(output / "schedule.json", schedule)
    _write_json(output / "prepared_inputs.json", prepared)
    _write_json(
        output / "screen_protocol.json",
        {
            "protocol_id": PROTOCOL_ID,
            "method_id": METHOD_B_ID,
            "implementation_commit": _git_head(),
            "system_prompt_unchanged": True,
            "provider_configuration_matches_90_run_baseline": True,
            "real_provider_required_for_result": True,
            "calls": 6,
            "retry_repair_salvage_fallback": "forbidden",
            "baseline_audit": str(BASELINE_AUDIT),
            "gate_frozen_before_calls": {
                "all_six_calls_successful": True,
                "grounding_failures": 0,
                "negative_control_minimum_score": 0.875,
                "mean_score_strictly_above_full_contract_kg_90_run_mean": True,
                "cases_at_or_above_matching_full_contract_kg_cell_mean": 4,
                "c01_and_c02_not_below_matching_full_contract_kg_cell_mean": True,
                "total_tokens_below_full_contract_kg_one_repetition_equivalent": True,
            },
            "claim_boundary": (
                "Development-set mechanism screen only. Passing selects a method for held-out evaluation; "
                "it does not establish superiority or statistical significance."
            ),
        },
    )
    if not execute:
        _write_json(
            output / "preflight.json",
            {"status": "ready", "paid_provider_calls_made": 0, "prepared_calls": len(prepared)},
        )
        return 0
    results = execute_pilot(
        prepared,
        output,
        pilot_scope="method_b_development_screen",
        claim_eligible=False,
        protocol_id=PROTOCOL_ID,
        model_revision="deepseek-v4-flash",
    )
    _write_json(
        output / "screen_summary.json",
        {
            "status": "completed" if len(results) == 6 else "incomplete",
            "executed_calls": len(results),
            "successful_calls": sum(item.get("success") is True for item in results),
            "failed_calls": sum(item.get("success") is not True for item in results),
        },
    )
    return 0


def _git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        text=True,
    ).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the six-call method B development screen.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO_ROOT / "docs" / "current" / "research-case-manifest-v1.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    return run_screen(args.manifest, args.output, execute=args.execute)


if __name__ == "__main__":
    raise SystemExit(main())
