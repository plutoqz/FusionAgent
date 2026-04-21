# FusionAgent Resume Project Brief

## One-Line Summary

FusionAgent is a KG-constrained geospatial fusion agent for disaster-response GIS workflows, with scenario-level orchestration, auditable evidence, and reproducible paper/demo evaluation.

## What It Demonstrates

- Converts natural-language disaster-response requests into constrained building/road/water/POI fusion workflows.
- Uses KG retrieval, validation, policy checks, repair, and audit trails to keep agent execution inspectable.
- Produces scenario-level evidence packages with summaries, KG path traces, workflow traces, source coverage, evaluation metrics, and bilingual reports.
- Supports repeatable paper/demo runs through checked-in scenario manifests, API harness summaries, and frozen evidence artifacts.
- Mature no-UI operation through scenario triggers, operator read APIs, reproducible evidence freezes, and documented local runbooks before any final frontend is introduced.

## Technical Highlights

- FastAPI v2 runtime with durable run status, plans, validation reports, audit events, and artifact bundles.
- Scenario orchestration layer above `/api/v2/scenario-runs` for multi-task disaster cases.
- File-backed scenario registry for restart-safe listing and inspection.
- Manifest-driven scenario harness and local trigger inbox for long-running operation demos.
- Evidence freeze scripts for paper-facing JSON and Markdown summaries.

## Resume Bullets

- Built a KG-constrained geospatial fusion agent that plans, validates, executes, repairs, and audits disaster-response GIS workflows.
- Added scenario-level orchestration for multi-task building/road disaster cases with bilingual evidence reports and evaluation metrics.
- Implemented task-driven data acquisition with AOI-aware source materialization, cache reuse, and coverage-aware fallback handling.
- Established paper-grade reproducibility through scenario manifests, harness summaries, frozen evidence artifacts, and full-suite pytest verification.

## Demo Script

1. Start the local v2 runtime with mock-friendly settings for a fast scenario demo.
2. Run `scripts/scenario_eval_harness.py` against `docs/superpowers/specs/2026-04-21-scenario-eval-manifest.json`.
3. Open the generated scenario directory and inspect `scenario_summary.json`, `kg_path_trace.json`, `workflow_trace.json`, `source_coverage.json`, `evaluation.json`, and bilingual reports.
4. Freeze the scenario evidence with `scripts/freeze_scenario_evidence.py`.
5. Use the frozen Markdown and JSON as paper/demo proof that the workflow is reproducible and auditable.
