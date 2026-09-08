"""Real-vector runtime smoke; deterministic KG selection is not a fair baseline."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--planner", choices=["fixed", "rules", "kg", "llm_only", "live"], default="kg")
    args = parser.parse_args()
    root = args.output.resolve()
    if root.exists():
        raise ValueError("Use a new output root; previous evidence must not be overwritten")
    root.mkdir(parents=True)
    data_root = root / "data"
    # All preparation targets are under a newly created, explicitly checked directory.
    data_root.mkdir()
    os.environ.update({
        "GEOFUSION_KG_BACKEND": "memory",
        "GEOFUSION_LLM_PROVIDER": "mock",
        "GEOFUSION_CELERY_EAGER": "1",
        "GEOFUSION_LOCAL_ONLY": "1",
        "GEOFUSION_DISABLE_ARTIFACT_REUSE": "1",
        "GEOFUSION_P3_VARIANT": "full_method",
        "GEOFUSION_PLAN_GROUNDING_MODE": "enforce",
        "GEOFUSION_MAX_PLAN_REVISIONS": "3",
        "GEOFUSION_DATA_REPOSITORY_ROOT": str(data_root),
        "GEOFUSION_DOWNLOAD_ROOT": str(root / "downloads"),
        "GEOFUSION_RUNS_ROOT": str(root / "runs"),
    })
    from agent.planner import WorkflowPlanner
    from llm.providers.base import LLMProvider
    from kg.inmemory_repository import InMemoryKGRepository
    from schemas.agent import RunCreateRequest, RunTrigger, RunTriggerType, RunInputStrategy
    from schemas.fusion import JobType
    from schemas.settings import EffectiveLLMSettings
    from schemas.contract_experiment import ExperimentStageDeclaration
    from services.agent_run_service import AgentRunService, RuntimeDependencies
    from services.contract_experiment_service import load_experiment_manifest, prepare_stage_sources, sha256_file
    from services.runtime_settings_service import RuntimeSettingsService
    from services.workflow_trace_service import build_workflow_trace
    from utils.local_runtime import read_dotenv_defaults
    from llm.providers.openai_compatible import OpenAICompatibleProvider
    from services.closed_loop_baseline_context import public_planning_context
    live = args.planner in {"live", "llm_only"}

    class RecordedLiveProvider(OpenAICompatibleProvider):
        call_count = 0

        def generate_workflow_plan(self, system_prompt, context):
            if self.call_count >= 3:
                raise RuntimeError("Smoke planning call budget exhausted")
            self.call_count += 1
            if args.planner == "llm_only":
                context = public_planning_context(context)
                system_prompt = (
                    "Generate a top-level workflow object conforming to output_schema. "
                    "Use the supplied request, public tool definitions and observed runtime facts. "
                    "Return strict JSON only."
                )
            call_root = root / "provider-calls"
            call_root.mkdir(exist_ok=True)
            write_json(call_root / f"call-{self.call_count}-input.json", {
                "system_prompt": system_prompt, "context": context,
            })
            try:
                return super().generate_workflow_plan(system_prompt, context)
            finally:
                write_json(call_root / f"call-{self.call_count}-attempt.json", self.last_attempt)

    class StrictLivePlanner(WorkflowPlanner):
        def _normalize_plan_context(self, **kwargs):
            if kwargs["planning_source"] != "llm":
                raise RuntimeError("Live smoke rejects non-LLM fallback or override")
            return super()._normalize_plan_context(**kwargs)

    class PatternProvider(LLMProvider):
        """Select the first KG candidate; no model and no mock model response."""
        model = "deterministic-kg-first-candidate"

        def generate_workflow_plan(self, system_prompt, context):
            if args.planner in {"fixed", "rules"}:
                return self.public_decision(public_planning_context(context))
            candidates = context["retrieval"]["candidate_patterns"]
            candidates = [
                candidate for candidate in candidates
                if candidate["steps"][0]["data_source_id"] != "upload.bundle"
            ]
            previous = context.get("execution_hints", {}).get("previous_plan")
            if context.get("execution_hints", {}).get("acquisition_observation") is not None:
                source = previous["tasks"][0]["input"]["data_source_id"]
                input_type = previous["tasks"][0]["input"]["data_type_id"]
                candidates = [
                    candidate for candidate in candidates
                    if candidate["steps"][0]["data_source_id"] == source
                    and candidate["steps"][0]["input_data_type"] == input_type
                ]
                if not candidates:
                    raise ValueError("No KG candidate matches the materialized bundle")
            candidate = candidates[0]
            tasks = [{
                "step": i,
                "name": step["name"],
                "description": step["name"],
                "algorithm_id": step["algorithm_id"],
                "input": {
                    "data_type_id": step["input_data_type"],
                    "data_source_id": step["data_source_id"],
                    "parameters": step.get("parameters", {}),
                },
                "output": {"data_type_id": step["output_data_type"]},
                "depends_on": step.get("depends_on", []),
                "is_transform": False,
            } for i, step in enumerate(candidate["steps"], 1)]
            return {
                "workflow_id": "kg_smoke_" + candidate["pattern_id"],
                "trigger": context["intent"]["trigger"],
                "tasks": tasks,
                "expected_output": "road fusion",
            }

        def public_decision(self, context):
            # Narrow typed-road task: join tool input types to source capabilities.
            tools = context["tools"]
            algorithms = sorted(
                [a for a in tools["algorithms"].values() if a["task_type"] == "road_fusion"],
                key=lambda a: a["algo_id"],
            )
            algorithm = algorithms[0]
            disaster = context["request"].get("disaster_type")
            sources = [
                source for source in tools["sources"]
                if set(source["supported_types"]) & set(algorithm["input_types"])
                and disaster in source.get("disaster_types", [])
            ]
            sources.sort(key=lambda source: source["source_id"])
            if args.planner == "rules":
                observation = context["observations"].get("acquisition_observation", {})
                selected = observation.get("selected_source_id")
                sources.sort(key=lambda source: (
                    source["source_id"] != selected if selected else False,
                    source.get("freshness_hours") if source.get("freshness_hours") is not None else float("inf"),
                    source["source_id"],
                ))
            source = sources[0]
            input_type = sorted(set(source["supported_types"]) & set(algorithm["input_types"]))[0]
            return {
                "workflow_id": "public_" + args.planner,
                "trigger": context["request"], "expected_output": "road fusion",
                "tasks": [{
                    "step": 1, "name": "road fusion", "description": "Execute selected public tool",
                    "algorithm_id": algorithm["algo_id"],
                    "input": {"data_type_id": input_type, "data_source_id": source["source_id"], "parameters": {}},
                    "output": {"data_type_id": algorithm["output_type"]},
                }],
            }

    class PatternPlanner(WorkflowPlanner):
        def _normalize_plan_context(self, **kwargs):
            if kwargs["planning_source"] != "llm":
                raise RuntimeError("Deterministic adapter failed; hidden fallback is not a baseline result")
            kwargs["planning_source"] = args.planner + "_deterministic_smoke"
            result = super()._normalize_plan_context(**kwargs)
            result["llm_provider"] = "none"
            return result

    manifest_path = ROOT / "docs/thesis/manifests/2026-07-20-c02-c04-c06-real-data.json"
    manifest = load_experiment_manifest(manifest_path)
    selected_ids = ["raw.osm.road", "raw.microsoft.road"]
    selected = [s for s in manifest.sources if s.source_id in selected_ids]
    for source in selected:
        target = (data_root / source.runtime_relative_path).resolve()
        if not target.is_relative_to(data_root):
            raise ValueError("Source preparation escapes the isolated data root")
    manifest = manifest.model_copy(update={"sources": selected})
    prepare_stage_sources(
        manifest=manifest,
        stage=ExperimentStageDeclaration(stage_id="roads", action="create", active_source_ids=selected_ids),
        data_root=data_root, evidence_dir=root,
    )
    repo = InMemoryKGRepository(experience_policy="pinned_snapshot")
    service = AgentRunService(
        base_dir=root / "runs", max_workers=1, kg_repo=repo,
        data_repository_root=data_root, download_root=root / "downloads",
        runtime_settings_service=RuntimeSettingsService(
            settings_path=root / "settings.json", snapshots_dir=root / "settings-snapshots",
        ),
    )
    provider = PatternProvider()
    provider.model = args.planner + "-deterministic-reference"
    planner_class = PatternPlanner
    if live:
        for key, value in read_dotenv_defaults().items():
            if value:
                os.environ.setdefault(key, value)
        key = os.getenv("OPENAI_API_KEY") or os.getenv("GEOFUSION_LLM_API_KEY")
        model = os.getenv("GEOFUSION_LLM_MODEL")
        base_url = os.getenv("GEOFUSION_LLM_BASE_URL")
        if not all([key, model, base_url]):
            service.shutdown()
            raise RuntimeError("Live configuration is incomplete after dotenv loading")
        provider = RecordedLiveProvider(
            api_key=key, model=model, base_url=base_url, timeout_sec=120,
            max_output_tokens=8192, allow_json_salvage=False, temperature=0.1,
        )
        planner_class = StrictLivePlanner
    runtime = RuntimeDependencies(
        settings=EffectiveLLMSettings(provider="mock"),
        llm_provider=provider,
        planner=planner_class(repo, provider, artifact_registry=service.artifact_registry),
        executor=service.executor,
    )
    request = RunCreateRequest(
        job_type=JobType.road,
        trigger=RunTrigger(
            type=RunTriggerType.user_query,
            content="Fuse road vectors for flood response in the declared Caracas bounding box.",
            disaster_type="flood",
            spatial_extent="bbox(-67.17,10.38,-66.86,10.57)",
        ),
        target_crs="EPSG:32619",
        input_strategy=RunInputStrategy.task_driven_auto,
        plan_after_acquisition=True,
    )
    write_json(root / "smoke_metadata.json", {
        "real_llm": live, "method": args.planner, "planner": provider.model,
        "runtime_settings_note": "Credential-free settings snapshot; eager execution uses injected provider.",
        "max_planning_calls": 3 if live else 0,
        "formal_baseline": False, "purpose": "real-vector runtime smoke",
        "internet_download": False, "data_mode": "local_cached_real_vectors",
        "aoi_semantics": "request_bbox_not_strict_admin",
        "manifest_sha256": sha256_file(manifest_path),
        "code_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_hashes": {p: sha256_file(ROOT / p) for p in [
            "scripts/run_caracas_closed_loop_smoke.py", "agent/planner.py",
            "services/agent_run_service.py", "services/run_writeback_service.py",
        ]},
    })
    started = time.perf_counter()
    try:
        status = service.create_run(
            request=request, osm_zip_name=None, osm_zip_bytes=None,
            ref_zip_name=None, ref_zip_bytes=None, runtime_dependencies=runtime,
        )
        events = service.get_audit_events(status.run_id)
        write_json(root / "trace.json", build_workflow_trace(events))
        summary = {
            "run_id": status.run_id, "phase": status.phase.value,
            "elapsed_seconds": time.perf_counter() - started,
            "error": status.error, "plan_revision": status.plan_revision,
            "artifact": status.artifact.model_dump(mode="json") if status.artifact else None,
            "event_kinds": [e.kind for e in events],
            "real_llm": live, "method": args.planner, "formal_baseline": False,
            "planning_call_count": getattr(provider, "call_count", 0),
        }
        write_json(root / "summary.json", summary)
        print(json.dumps(summary, ensure_ascii=True))
    finally:
        service.shutdown()
    return 0 if status.phase.value == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
