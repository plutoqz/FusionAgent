from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

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


def prepare_pilot(manifest_path: Path) -> tuple[Any, list[dict[str, Any]]]:
    manifest = load_research_case_manifest(manifest_path)
    schedule = build_research_llm_pilot_schedule()
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
        prepared.append(
            {
                "schedule": item.model_dump(mode="json"),
                "input_hash": projection.input_hash,
                "allowed_top_level_fields": projection.allowed_top_level_fields,
                "forbidden_top_level_fields": projection.forbidden_top_level_fields,
                "payload": projection.payload,
            }
        )
    return schedule, prepared


def execute_pilot(prepared: list[dict[str, Any]], output_dir: Path) -> list[dict[str, Any]]:
    provider = OpenAICompatibleProvider(
        api_key=_required_env("OPENAI_API_KEY", "GEOFUSION_LLM_API_KEY"),
        model=_required_env("GEOFUSION_LLM_MODEL"),
        base_url=os.getenv("GEOFUSION_LLM_BASE_URL", "https://api.openai.com/v1"),
        timeout_sec=int(os.getenv("GEOFUSION_LLM_TIMEOUT_SEC", "60")),
        allow_json_salvage=False,
    )
    results: list[dict[str, Any]] = []
    for run in prepared:
        run_id = run["schedule"]["run_id"]
        run_dir = output_dir / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        result: dict[str, Any] = {"run_id": run_id, "input_hash": run["input_hash"], "success": False}
        try:
            raw_plan = provider.generate_workflow_plan(SYSTEM_PROMPT, run["payload"])
        except Exception as exc:  # noqa: BLE001
            attempt_failure = (provider.last_attempt or {}).get("failure_class")
            result.update(failure_class=attempt_failure or "provider_failure", error=str(exc))
        else:
            try:
                plan = ResearchPlanningDecision.model_validate(raw_plan)
            except ValidationError as exc:
                result.update(failure_class="output_schema_validation_failure", error=str(exc))
            else:
                result.update(success=True, plan=plan.model_dump(mode="json"))
        result["attempt"] = provider.last_attempt
        _write_json(run_dir / "result.json", result)
        results.append(result)
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
    args = parser.parse_args()

    if args.output.exists():
        raise RuntimeError(f"Refusing to overwrite pilot evidence directory: {args.output}")
    args.output.mkdir(parents=True)
    schedule, prepared = prepare_pilot(args.manifest)
    _write_json(args.output / "schedule.json", schedule.model_dump(mode="json"))
    _write_json(args.output / "prepared_inputs.json", prepared)
    if not args.execute:
        _write_json(args.output / "preflight.json", {"status": "prepared", "main_call_count": len(prepared)})
        return 0

    results = execute_pilot(prepared, args.output)
    _write_json(
        args.output / "pilot_summary.json",
        {
            "status": "completed_with_observed_failures" if not all(item["success"] for item in results) else "completed",
            "main_call_count": len(results),
            "successful_calls": sum(1 for item in results if item["success"]),
            "failed_calls": sum(1 for item in results if not item["success"]),
        },
    )
    return 0


def _required_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    raise RuntimeError(f"Missing required environment variable: {' or '.join(names)}")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
