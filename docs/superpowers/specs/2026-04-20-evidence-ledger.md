# Evidence Ledger

## Purpose

This ledger indexes the current evidence base that supports FusionAgent's engineering, research, and product-readiness claims.

Durability labels:

- `strong`: tracked artifact or repeatable test/command with clear expected result.
- `medium`: tracked documentation or design evidence that needs periodic synchronization.
- `weak`: useful narrative evidence but not enough for final claims.
- `missing`: needed evidence that does not yet exist.

## Verification Baseline

| Evidence | Path or Command | Supports | Durability | Notes |
| --- | --- | --- | --- | --- |
| Full repository test suite | `python -m pytest -q` | Current codebase health after PR #1 and PR #2 | strong | Passed on 2026-04-20 with `158 passed, 1 skipped, 6 warnings` |
| Warning profile | `tests/test_building_adapter_safe.py` | Known non-blocking baseline noise | medium | Warnings are pyproj/numpy deprecations during building adapter tests |
| Plan closure scan | `docs/superpowers/plans/*.md` | Prior roadmap phases are closed | strong | All existing plan checkbox counts had `Unchecked = 0` before Phase A |

## Roadmap And Positioning Evidence

| Evidence | Path | Supports | Durability | Notes |
| --- | --- | --- | --- | --- |
| Main project positioning | `README.md` | Engineering MVP and research prototype are reached; final product shape is not reached | strong | Primary entry point for current status |
| English project positioning | `README.en.md` | Same status for English readers | medium | Keep synchronized if README status changes |
| v2 operations guide | `docs/v2-operations.md` | Runtime modes, evaluation tiers, benchmark conventions, operator endpoints | strong | Primary operator evidence |
| Local direct-run guide | `docs/local-direct-run.md` | Local full-loop capability and current true boundaries | medium | Useful for local verification and smoke runs |
| Master v2 plan | `docs/superpowers/plans/2026-04-07-fusion-agent-v2-implementation.md` | Prior six-phase v2 roadmap status | strong | Explicitly says baseline roadmap is complete for intended scope |
| Evaluation contract and claim lock | `docs/superpowers/specs/2026-04-20-evaluation-contract-claim-lock.md` | Scoped thesis/product claims, metrics, baselines, datasets, and Phase C-D authorization | strong | Current control document for post-Phase-A implementation |

## Design And Thesis Alignment Evidence

| Evidence | Path | Supports | Durability | Notes |
| --- | --- | --- | --- | --- |
| Thesis-aligned design | `docs/superpowers/specs/2026-04-10-thesis-aligned-agent-design.md` | Agent mode, dual-entry architecture, algorithm-task-data core, scenario constraint layer | strong | Main bridge between paper narrative and runtime architecture |
| FusionAgent v2 design | `docs/superpowers/specs/2026-04-07-fusion-agent-v2-design.md` | Planner/validator/executor/healing/writeback architecture | medium | Historical design; use with current README status |
| Agentic any-region design | `docs/superpowers/specs/2026-04-17-agentic-any-region-fusion-design.md` | Natural-language AOI, source materialization, AOI-scoped runtime path | strong | Recent design tied to implemented PR #1 |
| Full project context | `文档/完整项目上下文文档.md` | Research background, final target, MVP constraints, current boundaries | medium | Long-form narrative source |
| KG ontology target design | `文档/GeoFusion 知识图谱本体模式层设计方案.md` | Target-state ontology and explicit implemented-subset boundary | medium | Do not treat target-state classes as already implemented |

## Runtime Capability Evidence

| Evidence | Path or Command | Supports | Durability | Notes |
| --- | --- | --- | --- | --- |
| v2 API integration tests | `tests/test_api_v2_integration.py` | Run creation, inspection, task-driven input paths, AOI target CRS behavior | strong | Good regression gate for API/runtime contract |
| Agent run service tests | `tests/test_agent_run_service_enhancements.py` | Planning, audit, input acquisition, reuse, AOI, runtime orchestration, partial replan behavior | strong | Main runtime behavior test file |
| Planner context tests | `tests/test_planner_context.py` | KG/context evidence exposed to planner | strong | Useful for Phase D and E |
| Policy engine tests | `tests/test_policy_engine.py` | Explicit policy decision behavior | strong | Useful for Phase D policy hints |
| Artifact registry tests | `tests/test_artifact_registry.py` | Reusable artifact metadata and lookup | strong | Supports artifact reuse claims |
| Artifact reuse planner tests | `tests/test_planner_artifact_reuse.py` | Planning-stage reuse reasoning | strong | Use with runtime reuse tests |
| Workflow validator tests | `tests/test_workflow_validator.py` | Validation constraints and transform insertion | strong | Useful for Phase C replan gate design |
| Repair strategy and audit tests | `tests/test_repair_strategy.py`, `tests/test_repair_audit.py` | Current healing/repair coverage | strong | Evidence for current reactive healing below full replan target |

## Data Acquisition And AOI Evidence

| Evidence | Path or Command | Supports | Durability | Notes |
| --- | --- | --- | --- | --- |
| AOI resolution tests | `tests/test_aoi_resolution_service.py` | Natural-language region resolution behavior | strong | Main AOI unit evidence |
| Source asset service tests | `tests/test_source_asset_service.py` | Official/cache-backed source materialization | strong | Key for source acquisition claims |
| Raw vector source service tests | `tests/test_raw_vector_source_service.py` | Runtime local/remote raw-vector resolution | strong | Important for Phase F |
| Local bundle catalog tests | `tests/test_local_bundle_catalog.py` | Bundle assembly from raw/vector sources | strong | Important for task-driven input preparation |
| Input acquisition tests | `tests/test_input_acquisition_service.py` | Cached input bundle lookup and clipping | strong | Supports task-driven auto input claims |
| AOI smoke script | `scripts/smoke_agentic_region.py` | Natural-language AOI live smoke path | medium | Requires running runtime and network/geocoder availability |
| Source materialization script | `scripts/materialize_source_assets.py` | Bounded source-asset prefetch path | strong | Useful for reproducible benchmark prep |

## Benchmark And Evaluation Evidence

| Evidence | Path or Command | Supports | Durability | Notes |
| --- | --- | --- | --- | --- |
| Evaluation harness | `scripts/eval_harness.py` | Golden-case and manifest-backed evaluation | strong | Core repeatable benchmark driver |
| Golden cases | `tests/golden_cases/*/case.json` | API-to-runtime regression cases | strong | Tracked inputs and expected paths |
| Real-data manifest | `docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json` | Manifest-backed benchmark contract | strong | Contains bounded source-id-backed case |
| Fresh-checkout benchmark result | `docs/superpowers/specs/2026-04-16-building-micro-msft-fresh-checkout-result.json` | Official source-id materialization and isolated benchmark evidence | strong | Strongest current reproducibility artifact; rerun before final paper freeze |
| Clean micro alignment result | `docs/superpowers/specs/2026-04-16-building-micro-alignment-result.json` | Isolated runtime benchmark alignment | medium | Good historical evidence but should be normalized before final paper use |
| Historical Google-backed building benchmark result | `docs/superpowers/specs/2026-04-08-building-real-benchmark-result.json` | Historical real-data pass with Google-backed reference | medium | Useful but depends on restored local `Data/` assets |
| Benchmark follow-up summary | `docs/superpowers/specs/2026-04-08-benchmark-followup-summary.md` | Timeout correction and evidence discipline history | medium | Historical narrative evidence |

## Operator And Product Evidence

| Evidence | Path or Command | Supports | Durability | Notes |
| --- | --- | --- | --- | --- |
| Runtime metadata endpoint | `GET /api/v2/runtime` documented in `docs/v2-operations.md` | Evidence alignment and runtime inspection | strong | Used by harness metadata capture |
| Run inspection endpoint | `GET /api/v2/runs/{run_id}/inspection` documented in `docs/v2-operations.md` | Operator-facing inspection | strong | Thin but practical operator layer |
| Run comparison endpoint | `GET /api/v2/runs/{left_run_id}/compare/{right_run_id}` documented in `docs/v2-operations.md` | Operator comparison workflow | strong | Useful productization foundation |
| Independent frontend product | none | Full product surface | missing | Explicitly outside current achieved state |

## Missing Evidence To Create Next

| Missing Evidence | Phase | Why It Is Needed |
| --- | --- | --- |
| Evaluation contract mapping thesis claims to metrics and baselines | B | Prevents future implementation from drifting away from provable claims |
| Replan-loop failure injection evidence with preserved plan revisions and downstream reacquisition | C | Proves reactive healing can replace or amend a plan under explicit gates |
| Durable-learning policy-hint decision trace | D | Proves memory can influence future planning/policy without hidden auto-tuning |
| Executable ontology closure tests for data types, step IO, sources, scenarios, and schema policy references | E | Bridges research ontology and runtime evidence |
| One third vertical slice benchmark | F | Shows architecture can extend beyond current building/road center |
| Final experiment matrix with frozen run artifacts | G | Produces paper-grade evidence |
| Thin operator workflow smoke | H | Shows product-facing usability only after runtime evidence is stable |
