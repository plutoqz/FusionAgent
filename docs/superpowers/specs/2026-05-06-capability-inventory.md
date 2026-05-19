# Capability Inventory

## Vocabulary

- `status`: one of `core`, `core_next`, `optional`, `deferred`
- `claim_state`: one of `runtime_supported`, `bounded_supported`, `kg_only`, `inspect_only`, `reservation_only`, `research_utility`
- `evidence_contract`: the artifact or API surface that must stay aligned with the claim

## Theme Summary

### Building

| capability_id | status | claim_state | evidence_contract | owner_files |
| --- | --- | --- | --- | --- |
| `building.task_driven_auto` | `core` | `runtime_supported` | `run.json`, `plan.json`, `validation.json`, `audit.jsonl`, artifact bundle | `README.md`, `docs/v2-operations.md`, `services/agent_run_service.py` |
| `building.large_aoi_tiled_runtime` | `core` | `runtime_supported` | `run.json`, `audit.jsonl`, `tile_manifest.json`, `selected_sources.json`, `stitched_artifact.json`, artifact bundle, bounded `inspection_summary.json` from the checked-in benchmark utility | `services/agent_run_service.py`, `services/tiled_building_runtime_service.py`, `scripts/benchmark_tiled_building.py`, `docs/v2-operations.md`, `tests/test_agent_run_service_enhancements.py` |
| `building.scale_validation_source_profiling` | `optional` | `research_utility` | `source_profile_snapshot.json` plus bounded preparation docs for the checked-in validation dataset | `scripts/profile_benin_sources.py`, `services/source_profile_service.py`, `docs/v2-operations.md` |
| `building.scale_validation_cleanup_rules` | `optional` | `research_utility` | cleanup report and targeted tests for the checked-in validation dataset | `scripts/clean_benin_final_buildings.py`, `tests/test_clean_benin_final_buildings.py`, `docs/v2-operations.md` |
| `building.multisource_fusion_semantics` | `optional` | `research_utility` | `tile_manifest.json`, `source_profile_snapshot.json`, `selected_sources.json`, `stitched_artifact.json`, `runtime_output/fused_buildings.gpkg`, bounded `inspection_summary.json`, targeted tests | `scripts/run_benin_multisource_building_fusion.py`, `services/tiled_building_runtime_service.py`, `docs/v2-operations.md`, `docs/fusioncode-algorithm-library.md` |

Script and dataset names may still carry Benin labels because the current checked-in validation dataset is organized that way. Capability ids stay generic so they describe the validation role rather than a country-specific scope.

### Road

| capability_id | status | claim_state | evidence_contract | owner_files |
| --- | --- | --- | --- | --- |
| `road.task_driven_auto` | `core` | `runtime_supported` | `run.json`, `plan.json`, `validation.json`, `audit.jsonl`, artifact bundle | `README.md`, `docs/v2-operations.md`, `services/agent_run_service.py` |
| `trajectory_to_road.seam` | `deferred` | `reservation_only` | metadata only; no executable runtime path | `README.md`, `docs/v2-operations.md`, `docs/no-ui-agent-operations.md` |

### Water

| capability_id | status | claim_state | evidence_contract | owner_files |
| --- | --- | --- | --- | --- |
| `water.task_driven_auto` | `core` | `runtime_supported` | shared evidence contract plus water slice tests | `README.md`, `docs/v2-operations.md`, `tests/test_api_v2_integration.py` |

### POI

| capability_id | status | claim_state | evidence_contract | owner_files |
| --- | --- | --- | --- | --- |
| `poi.task_driven_auto` | `core` | `bounded_supported` | shared evidence contract with bounded slice wording | `README.md`, `docs/v2-operations.md`, `docs/no-ui-agent-operations.md` |

### Operator

| capability_id | status | claim_state | evidence_contract | owner_files |
| --- | --- | --- | --- | --- |
| `operator.inspection_compare_api` | `core` | `runtime_supported` | inspection and compare endpoints | `docs/no-ui-agent-operations.md`, `api/routers/runs_v2.py` |
| `operator.web_workbench` | `optional` | `research_utility` | operator-facing workbench wording, not final UI claim | `README.md`, `frontend/src/app` |

### Evidence

| capability_id | status | claim_state | evidence_contract | owner_files |
| --- | --- | --- | --- | --- |
| `evidence.shared_run_contract` | `core` | `runtime_supported` | `run.json`, `plan.json`, `validation.json`, `audit.jsonl`, artifact bundle | `README.md`, `docs/v2-operations.md`, `docs/no-ui-agent-operations.md` |
| `evidence.tool_contracts_grounding_recovery` | `core_next` | `reservation_only` | tests plus future inspection and audit extensions | `docs/superpowers/specs/2026-05-06-capability-consolidation-review.md`, `docs/superpowers/specs/2026-04-23-system-next-improvement-review.md` |

## Inventory Rule

- `core` items are part of the current stable runtime proof.
- `core_next` items are the only authorized near-term claim-strengthening additions.
- `optional` items may stay in the repo, but they must not silently become the main runtime story.
- `deferred` items may remain visible in KG or docs as seams, but they are not part of the current executable claim.

