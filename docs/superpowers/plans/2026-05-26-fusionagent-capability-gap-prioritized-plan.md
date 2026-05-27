# FusionAgent Capability Gap Prioritized Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前有界地理空间融合 runtime 的能力缺口按依赖关系收口为一条可无人值守执行、可自动获取数据、可大范围裁剪/拼接、可生成报告、可恢复、可审计的实施路线。

**Architecture:** 以现有 `planner -> validator -> executor -> healing/replan -> writeback` 主链为中心，不新造第二套 runtime。先补运行时自治、错误恢复、源获取与大范围编排，再补 building / road / water / POI 的融合稳定性，随后把报告、过程评估、结果评估和 bounded self-learning 证据收口到同一条可回归链路里。所有改动都必须继续保持 bounded disaster-response boundary，不引入 live event-feed、digital twin 或无约束 self-learning claim。

**Tech Stack:** Python 3.9-3.11, FastAPI, Celery/Redis, Neo4j, GeoPandas/Shapely/Rasterio/NetworkX, existing `services/`, `agent/`, `fusion_algorithms/`, `adapters/`, `scripts/`, `tests/`, and Markdown evidence docs.

---

## Priority Map

| Priority | User gap | Current state | Target exit gate |
| --- | --- | --- | --- |
| P0 | 1, 9 | already partially automated, recovery exists | unattended runs recover automatically and expose clear stop / retry semantics |
| P1 | 6, 7 | source catalog and tiling exist but are uneven | supported sources auto-download and large-AOI runs tile / stitch deterministically |
| P2 | 2, 3, 4, 5 | building is strongest, road / water / POI vary | all supported slices execute end-to-end under the same bounded runtime contract |
| P3 | 8 | scenario reports exist, run reports are thin | process and result evaluation are generated and downloadable for every successful run |
| P4 | 10 | bounded durable-learning hints exist | learning remains auditable and bounded, but measurably influences future selection |

## Boundary Lock

- Keep the stable executable claim at `building`, `road`, `water`, and bounded `poi`.
- Keep `trajectory-to-road` reservation-only.
- Keep Google building manual-only / local-data-only unless a separate evidence package promotes it.
- Keep external live event-feed integration out of scope for this plan.
- Keep self-learning bounded to policy hints and evidence summaries; do not claim auto-tuning or self-modifying runtime.

## File Structure Map

### Control Plane

- `services/agent_run_service.py`
- `services/run_recovery_service.py`
- `services/run_recovery_executor.py`
- `worker/tasks.py`
- `worker/celery_app.py`
- `api/routers/runs_v2.py`
- `api/routers/scenario_runs.py`
- `services/operator_read_model_service.py`

### Source Acquisition And Tiling

- `services/source_asset_service.py`
- `services/raw_vector_source_service.py`
- `services/input_acquisition_service.py`
- `services/local_bundle_catalog.py`
- `services/tile_partition_service.py`
- `services/tiled_building_runtime_service.py`
- `scripts/materialize_source_assets.py`
- `scripts/run_benin_multisource_building_fusion.py`

### Fusion Primitives

- `fusion_algorithms/building_matching_v8.py`
- `fusion_algorithms/building_raster.py`
- `fusion_algorithms/building_height.py`
- `fusion_algorithms/road_fusion.py`
- `fusion_algorithms/road_conflation_v7.py`
- `fusion_algorithms/line_conflation_v7.py`
- `fusion_algorithms/water_fusion.py`
- `fusion_algorithms/waterways_conflation_v7.py`
- `fusion_algorithms/poi_fusion.py`
- `adapters/building_adapter.py`
- `adapters/road_adapter.py`
- `adapters/water_adapter.py`
- `adapters/poi_adapter.py`
- `adapters/fusioncode_building_adapter.py`
- `adapters/fusioncode_linear_adapter.py`
- `adapters/fusioncode_poi_adapter.py`
- `Algorithm/build.py`
- `Algorithm/line.py`
- `Algorithm/water_line.py`
- `Algorithm/water_polygon.py`

### Reporting And Learning

- `services/run_report_service.py`
- `services/scenario_report_service.py`
- `services/scenario_document_service.py`
- `templates/reports/run_report.zh.md.j2`
- `templates/reports/run_report.en.md.j2`
- `templates/reports/scenario_report.zh.md.j2`
- `templates/reports/scenario_report.en.md.j2`
- `services/artifact_evaluation_service.py`
- `services/plan_grounding_service.py`
- `kg/models.py`
- `kg/repository.py`
- `kg/neo4j_repository.py`
- `kg/inmemory_repository.py`

### Tests

- `tests/test_scenario_trigger_service.py`
- `tests/test_worker_orchestration.py`
- `tests/test_worker_recovery_tick.py`
- `tests/test_run_recovery_service.py`
- `tests/test_run_recovery_executor.py`
- `tests/test_operator_recovery_api.py`
- `tests/test_input_acquisition_service.py`
- `tests/test_raw_vector_source_service.py`
- `tests/test_source_asset_service.py`
- `tests/test_tile_partition_service.py`
- `tests/test_tiled_building_runtime_service.py`
- `tests/test_tiled_multisource_building_runtime_service.py`
- `tests/test_agent_run_service_multisource_building_runtime.py`
- `tests/test_road_conflation_v7.py`
- `tests/test_waterways_conflation_v7.py`
- `tests/test_poi_adapter.py`
- `tests/test_fusioncode_poi.py`
- `tests/test_scenario_report_service.py`
- `tests/test_run_report_service.py`
- `tests/test_artifact_evaluation_service.py`
- `tests/test_no_ui_maturity_check.py`

## Execution Plan

### Task 1: P0 - Harden the unattended trigger and long-run control plane

**Files:**
- Modify: `services/scenario_trigger_service.py`
- Modify: `scripts/watch_scenario_inbox.py`
- Modify: `worker/tasks.py`
- Modify: `worker/celery_app.py`
- Modify: `services/operator_read_model_service.py`
- Modify: `api/routers/runs_v2.py`
- Modify: `docs/no-ui-agent-operations.md`
- Modify: `docs/v2-operations.md`
- Test: `tests/test_scenario_trigger_service.py`
- Test: `tests/test_worker_orchestration.py`
- Test: `tests/test_worker_recovery_tick.py`
- Test: `tests/test_no_ui_maturity_check.py`

- [ ] **Step 1: Add regression coverage for local inbox and scheduled trigger behavior.**
  - Assert that one inbox JSON record creates exactly one scenario run.
  - Assert that duplicate events with the same idempotency key do not create duplicate runs.
  - Assert that invalid JSON is moved to `failed_dir` when it is configured.

- [ ] **Step 2: Tighten long-run observability for unattended operation.**
  - Ensure `worker.celery_app` beat schedule keeps `scheduled_tick` and `recovery_tick` alive.
  - Surface queue / runtime state in the operator read model so a long-running job can be monitored without opening raw files.
  - Preserve bounded wording in the no-UI runbook: local inbox is supported, external event-feed replay is not.

- [ ] **Step 3: Verify the unattended path end-to-end.**
  - Run `python -m pytest -q tests/test_scenario_trigger_service.py tests/test_worker_orchestration.py tests/test_worker_recovery_tick.py tests/test_no_ui_maturity_check.py`
  - Run `python scripts/watch_scenario_inbox.py --help`
  - Run a local smoke flow that uses the inbox path and confirm that the processed file moves out of the inbox.

**Acceptance Criteria:**
- A single supported trigger record can start a full scenario run without manual file edits after the event is written.
- Duplicate trigger records do not create duplicate runs.
- The operator surface exposes enough state to monitor a long-running run from API/runbook evidence only.
- External live event-feed wording remains rejected or explicitly bounded.

### Task 2: P0 - Make recovery and fault handling fully automatic

**Files:**
- Modify: `services/run_recovery_service.py`
- Modify: `services/run_recovery_executor.py`
- Modify: `services/agent_run_service.py`
- Modify: `schemas/failure_taxonomy.py`
- Modify: `worker/tasks.py`
- Modify: `api/routers/runs_v2.py`
- Test: `tests/test_run_recovery_service.py`
- Test: `tests/test_run_recovery_executor.py`
- Test: `tests/test_worker_recovery_tick.py`
- Test: `tests/test_operator_recovery_api.py`
- Test: `tests/test_runtime_boundary_guards.py`

- [ ] **Step 1: Add regression tests for stale-run classification and lease handling.**
  - Cover `queued`, `planning`, `validation`, `running`, and `healing` states.
  - Assert that recoverable records yield a deterministic recovery action.
  - Assert that terminal runs remain terminal and are not redispatched.

- [ ] **Step 2: Extend the fault taxonomy so transient failures are handled automatically.**
  - Map download, timeout, CRS mismatch, source missing, and source corruption to deterministic recovery actions.
  - Keep manual-review fallback only for non-recoverable or terminal failures.
  - Preserve explicit recovery history in `recovery.lock.json` and `recovery.history.jsonl`.

- [ ] **Step 3: Re-run the recovery and operator API paths under tests.**
  - Run `python -m pytest -q tests/test_run_recovery_service.py tests/test_run_recovery_executor.py tests/test_worker_recovery_tick.py tests/test_operator_recovery_api.py`
  - Confirm `GET /api/v2/operator/recovery` and `POST /api/v2/operator/recovery` remain consistent with the stale-run scanner.

**Acceptance Criteria:**
- Recoverable stale runs are redispatched automatically without manual intervention.
- Recovery actions are idempotent under repeated recovery ticks.
- Terminal failures stay terminal and carry a clear, machine-readable recovery hint.
- Recovery evidence is persisted and readable through the inspection surface.

### Task 3: P1 - Complete automatic source acquisition and download catalog

**Files:**
- Modify: `services/source_asset_service.py`
- Modify: `services/raw_vector_source_service.py`
- Modify: `services/input_acquisition_service.py`
- Modify: `services/local_bundle_catalog.py`
- Modify: `kg/source_catalog.py`
- Modify: `scripts/materialize_source_assets.py`
- Modify: `docs/v2-operations.md`
- Modify: `docs/no-ui-agent-operations.md`
- Test: `tests/test_source_asset_service.py`
- Test: `tests/test_raw_vector_source_service.py`
- Test: `tests/test_input_acquisition_service.py`
- Test: `tests/test_source_coverage_fallback.py`
- Test: `tests/test_local_bundle_catalog.py`

- [ ] **Step 1: Add source coverage tests for every supported source family.**
  - Cover OSM building / road / water / waterways / POI.
  - Cover Microsoft building.
  - Cover Overture road / transportation.
  - Cover HydroRIVERS / HydroLAKES.
  - Cover GeoNames / GNS POI.

- [ ] **Step 2: Make the acquisition path deterministic and cache-aware.**
  - Reuse cached materializations when source version and bbox match.
  - Clip cached assets when the requested bbox is narrower than the cached bbox.
  - Materialize from the source catalog without manual file copying for supported sources.

- [ ] **Step 3: Preserve explicit manual-only boundaries.**
  - Keep Google building and any other manual-only paths out of the automatic claim.
  - Raise explicit source-fault classifications instead of silently falling back.
  - Record source coverage, fallback, and materialization mode in run evidence.

- [ ] **Step 4: Verify the source acquisition paths.**
  - Run `python -m pytest -q tests/test_source_asset_service.py tests/test_raw_vector_source_service.py tests/test_input_acquisition_service.py tests/test_source_coverage_fallback.py tests/test_local_bundle_catalog.py`
  - Run `python scripts/materialize_source_assets.py --help`

**Acceptance Criteria:**
- Supported sources can be materialized automatically from a clean checkout or from cache.
- Repeated requests reuse cache entries when the source version and bbox are unchanged.
- Manual-only or unsupported sources fail with explicit source-fault classification.
- Source coverage and fallback metadata are visible in audit and report artifacts.

### Task 4: P1 - Generalize large-area clip / stitch orchestration

**Files:**
- Modify: `services/tile_partition_service.py`
- Modify: `services/tiled_building_runtime_service.py`
- Modify: `services/agent_run_service.py`
- Modify: `utils/vector_clip.py`
- Modify: `scripts/benchmark_tiled_building.py`
- Modify: `scripts/run_benin_multisource_building_fusion.py`
- Test: `tests/test_tile_partition_service.py`
- Test: `tests/test_tiled_building_runtime_service.py`
- Test: `tests/test_agent_run_service_enhancements.py`
- Test: `tests/test_benchmark_tiled_building.py`

- [ ] **Step 1: Add regression coverage for tile manifest generation and clip boundaries.**
  - Assert that large-AOI requests produce deterministic tile boundaries and overlap.
  - Assert that clip operations preserve CRS and respect the request bbox.
  - Assert that stitched outputs de-duplicate boundary features.

- [ ] **Step 2: Normalize large-area evidence across the runtime.**
  - Ensure `tile_manifest.json`, `selected_sources.json`, `stitched_artifact.json`, and `inspection_summary.json` are generated consistently.
  - Keep the output schema stable enough for run inspection and scenario reports to consume.
  - Reuse the same tile metadata model for future non-building slices that use the same tile manifest and stitching contract.

- [ ] **Step 3: Re-run the benchmark path on a multi-tile fixture.**
  - Run `python -m pytest -q tests/test_tile_partition_service.py tests/test_tiled_building_runtime_service.py tests/test_benchmark_tiled_building.py`
  - Run `python scripts/benchmark_tiled_building.py --help`

**Acceptance Criteria:**
- Large-AOI requests generate deterministic tile manifests and stitched artifacts.
- Boundary duplicates are removed in stitched output.
- Output CRS and request bbox remain stable across tile and stitched artifacts.
- The same source request reuses cached tiles when available.

### Task 5: P2 - Stabilize building vector fusion and height raster integration

**Files:**
- Modify: `services/tiled_building_runtime_service.py`
- Modify: `services/agent_run_service.py`
- Modify: `fusion_algorithms/building_matching_v8.py`
- Modify: `fusion_algorithms/building_raster.py`
- Modify: `fusion_algorithms/building_height.py`
- Modify: `adapters/building_adapter.py`
- Modify: `adapters/fusioncode_building_adapter.py`
- Modify: `scripts/run_benin_multisource_building_fusion.py`
- Test: `tests/test_agent_run_service_multisource_building_runtime.py`
- Test: `tests/test_tiled_multisource_building_runtime_service.py`
- Test: `tests/test_fusioncode_building_raster.py`
- Test: `tests/test_fusioncode_building_height_fields.py`
- Test: `tests/test_fusioncode_building_adapter_height_fields.py`
- Test: `tests/test_run_benin_multisource_building_fusion.py`

- [ ] **Step 1: Add regression tests for multi-source building fusion plus raster height integration.**
  - Cover at least two vector sources.
  - Cover presence raster and height raster inputs.
  - Cover deterministic final height source selection.

- [ ] **Step 2: Stabilize the building fused output contract.**
  - Keep `height_final` and `height_final_source` stable across tile and stitched outputs.
  - Keep the field mapping / adapter contract aligned with the runtime path.
  - Keep large-AOI validation outputs and evidence artifacts in sync with the runtime output.

- [ ] **Step 3: Verify the building large-AOI validation scripts.**
  - Run `python -m pytest -q tests/test_agent_run_service_multisource_building_runtime.py tests/test_tiled_multisource_building_runtime_service.py tests/test_fusioncode_building_raster.py tests/test_fusioncode_building_height_fields.py tests/test_fusioncode_building_adapter_height_fields.py tests/test_run_benin_multisource_building_fusion.py`

**Acceptance Criteria:**
- Building fusion can consume multiple vector sources plus height / presence rasters when provided.
- Fused outputs contain deterministic `height_final` / `height_final_source` fields.
- The building large-AOI path remains bounded and test-covered.

### Task 6: P2 - Stabilize road vector fusion

**Files:**
- Modify: `fusion_algorithms/road_fusion.py`
- Modify: `fusion_algorithms/road_conflation_v7.py`
- Modify: `fusion_algorithms/line_conflation_v7.py`
- Modify: `adapters/road_adapter.py`
- Modify: `adapters/fusioncode_linear_adapter.py`
- Modify: `Algorithm/road_fusion_optimized_v7.py`
- Modify: `services/agent_run_service.py`
- Test: `tests/test_road_conflation_v7.py`
- Test: `tests/test_fusioncode_linear_water_road.py`
- Test: `tests/test_road_adapter.py`

- [ ] **Step 1: Add regression tests for supported road inputs and bbox clipping.**
  - Cover OSM road plus Overture road / transportation inputs.
  - Cover CRS normalization and request bbox clipping.
  - Cover output schema preservation and boundary dedupe.

- [ ] **Step 2: Route road execution through the supported fusion path.**
  - Keep `trajectory-to-road` out of the executable path.
  - Keep road task execution under the same evidence contract as other runtime slices.
  - Ensure the road path is discoverable in run inspection and report data.

- [ ] **Step 3: Verify the road path in tests and smoke checks.**
  - Run `python -m pytest -q tests/test_road_conflation_v7.py tests/test_fusioncode_linear_water_road.py tests/test_road_adapter.py`

**Acceptance Criteria:**
- Road `task_driven_auto` produces a fused artifact from supported road sources.
- Road fusion honors AOI clipping and CRS normalization.
- No part of the executable road path depends on live trajectory ingestion.

### Task 7: P2 - Stabilize water vector fusion

**Files:**
- Modify: `fusion_algorithms/water_fusion.py`
- Modify: `fusion_algorithms/waterways_conflation_v7.py`
- Modify: `adapters/water_adapter.py`
- Modify: `Algorithm/water_line.py`
- Modify: `Algorithm/water_polygon.py`
- Modify: `services/agent_run_service.py`
- Test: `tests/test_water_adapter.py`
- Test: `tests/test_waterways_conflation_v7.py`
- Test: `tests/test_fusioncode_linear_water_road.py`

- [ ] **Step 1: Add regression tests for rivers, waterways, and lake inputs.**
  - Cover line and polygon water geometries.
  - Cover clipping to AOI bbox and target CRS.
  - Cover stable output fields and feature counts.

- [ ] **Step 2: Keep water fusion explicit in runtime routing.**
  - Ensure water task execution is not a hidden side effect of another slice.
  - Ensure run inspection can surface the selected water source and fallback behavior.
  - Keep the water claim bounded to the supported slice.

- [ ] **Step 3: Verify the water path in tests and smoke checks.**
  - Run `python -m pytest -q tests/test_water_adapter.py tests/test_waterways_conflation_v7.py tests/test_fusioncode_linear_water_road.py`

**Acceptance Criteria:**
- Water `task_driven_auto` produces a fused artifact for river / lake slices.
- Water output geometry and fields stay stable under targeted tests.
- Water remains within the bounded supported claim.

### Task 8: P2 - Stabilize POI fusion

**Files:**
- Modify: `fusion_algorithms/poi_fusion.py`
- Modify: `adapters/poi_adapter.py`
- Modify: `adapters/fusioncode_poi_adapter.py`
- Modify: `services/source_asset_service.py`
- Modify: `services/agent_run_service.py`
- Test: `tests/test_poi_adapter.py`
- Test: `tests/test_fusioncode_poi.py`
- Test: `tests/test_source_coverage_fallback.py`

- [ ] **Step 1: Add regression tests for OSM and GeoNames / GNS POI inputs.**
  - Cover automatic source acquisition for the bounded POI slice.
  - Cover dedupe and provenance preservation.
  - Cover bounded fallback behavior when the AOI cannot be resolved.

- [ ] **Step 2: Keep POI matching bounded and explicit.**
  - Preserve per-source provenance and selected / fallback source IDs in audit output.
  - Reject or defer ambiguous entity alignment rather than silently merging it.
  - Keep the executable claim bounded instead of promoting POI to general entity resolution.

- [ ] **Step 3: Verify the POI path in tests.**
  - Run `python -m pytest -q tests/test_poi_adapter.py tests/test_fusioncode_poi.py tests/test_source_coverage_fallback.py`

**Acceptance Criteria:**
- POI `task_driven_auto` works for the bounded OSM + GeoNames / GNS slice.
- Source provenance is visible in run evidence and reports.
- Ambiguous or unsupported alignment is surfaced as a bounded failure or deferred case.

### Task 9: P3 - Produce run and scenario reports with process / result evaluation

**Files:**
- Modify: `services/scenario_report_service.py`
- Modify: `services/scenario_document_service.py`
- Modify: `services/operator_read_model_service.py`
- Modify: `services/agent_run_service.py`
- Add or modify: `services/run_report_service.py`
- Add or modify: `templates/reports/run_report.zh.md.j2`
- Add or modify: `templates/reports/run_report.en.md.j2`
- Modify: `api/routers/runs_v2.py`
- Modify: `api/routers/scenario_runs.py`
- Modify: `schemas/ui_assets.py`
- Test: `tests/test_scenario_report_service.py`
- Test: `tests/test_api_v2_integration.py`
- Test: `tests/test_api_scenario_runs.py`
- Test: `tests/test_api_run_documents.py`
- Test: `tests/test_api_scenario_documents.py`
- Test: `tests/test_scenario_output.py`
- Test: `tests/test_artifact_evaluation_service.py`

- [ ] **Step 1: Add regression tests for report content and access paths.**
  - Cover Chinese and English markdown generation.
  - Cover process evaluation sections and result evaluation sections.
  - Cover report list / download API behavior.

- [ ] **Step 2: Persist reports as first-class run artifacts.**
  - Generate run-level reports after a successful fusion task.
  - Keep scenario-level reports in sync with child run evaluation.
  - Expose report documents through the operator API, not only on disk.

- [ ] **Step 3: Make report content evidence-based.**
  - Include source coverage, fallback summary, telemetry, artifact validity, and recovery outcome.
  - Include run and scenario process metrics separately from final artifact metrics.
  - Include bounded self-evolution evidence where available.

- [ ] **Step 4: Verify report generation and retrieval.**
  - Run `python -m pytest -q tests/test_scenario_report_service.py tests/test_run_report_service.py tests/test_api_v2_integration.py tests/test_api_scenario_runs.py tests/test_api_run_documents.py tests/test_api_scenario_documents.py tests/test_scenario_output.py tests/test_artifact_evaluation_service.py`

**Acceptance Criteria:**
- Every successful fusion run and scenario run produces a human-readable Chinese and English report.
- Reports contain both process evaluation and result evaluation sections.
- Reports are accessible through API and are consistent with persisted JSON evidence.

### Task 10: P4 - Add bounded self-iteration and self-learning

**Files:**
- Modify: `services/agent_run_service.py`
- Modify: `services/artifact_evaluation_service.py`
- Modify: `services/plan_grounding_service.py`
- Modify: `services/scenario_run_service.py`
- Modify: `kg/models.py`
- Modify: `kg/repository.py`
- Modify: `kg/neo4j_repository.py`
- Modify: `kg/inmemory_repository.py`
- Test: `tests/test_agent_run_service_enhancements.py`
- Test: `tests/test_artifact_evaluation_service.py`
- Test: `tests/test_plan_grounding_service.py`
- Test: `tests/test_policy_engine.py`
- Test: `tests/test_no_ui_maturity_check.py`

- [ ] **Step 1: Add regression tests for durable-learning record writeback and reuse.**
  - Assert that each run writes a durable learning record on success or failure.
  - Assert that future runs can read bounded learning summaries from the KG context.
  - Assert that learning adjustments remain capped and auditable.

- [ ] **Step 2: Keep learning bounded to policy hints.**
  - Reuse learned summaries only as scored hints inside the planner.
  - Keep the adjustment range capped and deterministic.
  - Keep model / policy / source catalog mutation out of scope.

- [ ] **Step 3: Surface self-learning evidence in reports and evaluation.**
  - Preserve `self_evolution_record_written`, `self_evolution_hint_available`, `self_evolution_hint_used`, and policy adjustment metrics.
  - Keep the evidence narrative explicit that this is bounded learning, not auto-tuning.

- [ ] **Step 4: Verify the learning loop in tests.**
  - Run `python -m pytest -q tests/test_agent_run_service_enhancements.py tests/test_artifact_evaluation_service.py tests/test_plan_grounding_service.py tests/test_policy_engine.py tests/test_no_ui_maturity_check.py`

**Acceptance Criteria:**
- Each run writes a durable learning record and a readable learning summary when applicable.
- Future runs can use the hint, but only within bounded scoring adjustments and with evidence refs.
- No code path mutates policies, models, or source catalogs automatically without a recorded, testable gate.

## Overall Acceptance Gate

- The unattended path can start from the local inbox or scheduled trigger, survive recoverable failures, and complete without manual intervention for supported cases.
- Supported sources can be acquired automatically, cached, clipped, and tiled for large-area requests.
- Building, road, water, and bounded POI all produce fused artifacts under the same runtime contract.
- Every successful run and scenario produces process/result reports in Chinese and English.
- Learning remains bounded and auditable; no claim crosses into auto-tuning or unrestricted autonomous evolution.

## Review Checklist

- Does every task stay inside the bounded disaster-response runtime boundary?
- Does every new report or API consume persisted artifacts instead of transient memory?
- Does any task accidentally promote `trajectory-to-road`, Google building, or self-learning beyond the documented boundary?
- Does every acceptance criterion describe a testable exit condition?
- Can an engineer execute the tasks in order without guessing hidden files or missing dependencies?
