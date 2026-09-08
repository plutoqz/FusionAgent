"""Public tool facts for narrow closed-loop planning comparisons."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


def public_planning_context(context: dict[str, Any]) -> dict[str, Any]:
    retrieval = context["retrieval"]
    algorithms = {}
    for key, value in retrieval["algorithms"].items():
        metadata = value.get("metadata", {})
        runtime_status = str(metadata.get("runtime_status") or "").strip().lower()
        if metadata.get("selectable_now") is False:
            continue
        # Match the runtime contract: algorithms without an explicit status
        # are not executable capabilities and must not be offered to baselines.
        if not runtime_status or runtime_status in {"deprecated", "reservation_only"}:
            continue
        algorithms[key] = {
            field: value[field]
            for field in ("algo_id", "algo_name", "input_types", "output_type", "task_type", "tool_ref")
            if field in value
        }
        algorithms[key]["runtime_status"] = runtime_status
        algorithms[key]["selectable_now"] = True
    sources = [{
        field: source[field]
        for field in (
            "source_id", "source_name", "supported_types", "disaster_types",
            "source_kind", "quality_tier", "freshness_category", "freshness_hours",
            "supported_job_types", "supported_geometry_types",
        )
        if field in source
    } for source in retrieval["data_sources"]
        if source.get("source_kind") != "local_upload"
        and source.get("metadata", {}).get("selectable_now", True)]
    hints = context.get("execution_hints", {})
    return deepcopy({
        "request": context["intent"]["trigger"],
        "input_strategy": "task_driven_auto",
        "tools": {
            "algorithms": algorithms, "sources": sources,
            "parameter_specs": retrieval.get("parameter_specs", {}),
            "data_types": retrieval.get("data_types", {}),
        },
        "observations": {
            key: hints[key] for key in (
                "previous_plan", "planning_stage", "acquisition_observation",
                "observed_failure", "failed_step", "error", "input_constraint",
            ) if key in hints
        },
        "output_schema": context["output_schema"],
    })
