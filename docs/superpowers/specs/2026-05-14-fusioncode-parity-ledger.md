# FusionCode Parity Ledger

## Purpose

This ledger is the live Phase D checkpoint for tracing each checked-in `fusioncode` capability family to its concrete FusionAgent landing points. It is not a marketing inventory. The goal is to answer, with file-backed evidence, whether each family has all six required elements:

1. wrapper or primitive implementation
2. KG algorithm or workflow node
3. parameter specs
4. executor handler or tool registry entry
5. planner or retriever visibility
6. focused tests

## Claim Rules

- `runtime_supported`: shared runtime claim already used by the bounded default runtime.
- `bounded_supported`: executable and visible, but intentionally bounded in task scope or evidence.
- `research_utility`: executable in utilities or validation flows, but not part of the shared runtime claim.
- `reservation_only`: visible as a seam or reserved capability and must not be treated as executable runtime support.

## Parity Matrix

| Family | Current claim | Wrapper / primitive | KG / workflow node | Parameter specs | Executor / registry | Planner / retriever visibility | Focused tests | Current gap / note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| building safe/default bundle fusion | `runtime_supported` | `adapters/building_adapter.py`, `adapters/building_safe_adapter.py`, `fusion_algorithms/building_fusion.py` | `kg/seed.py` -> `algo.fusion.building.v1`, `algo.fusion.building.safe`, default building patterns | `kg/seed.py` parameter specs for `algo.fusion.building.v1` and `algo.fusion.building.safe` | `agent/tooling.py` -> `_handle_building`, `_handle_building_safe`; `agent/executor.py` handlers | default pattern and source selection in `agent/planner.py`, `agent/retriever.py` | `tests/test_tool_registry.py`, `tests/test_agent_run_service_enhancements.py`, repair tests | already in shared runtime baseline |
| building decomposed multi-source workflow | `research_utility` | `adapters/fusioncode_building_adapter.py` -> `run_building_multi_source_decomposed`; `fusion_algorithms/building_matching_v8.py` | `kg/seed.py` -> `wp.building.drs4br.decomposed.v1`, `algo.fusion.building.multi_source.decomposed.v1` | `kg/seed.py` and `fusion_algorithms/contracts.py` -> V8 matching params | `agent/tooling.py` / `agent/executor.py` -> `_handle_building_multi_source_decomposed`, `_handle_building_cascade_fusion` | `agent/retriever.py` exposes as reserved-capability/runtime-candidate hint for building source-set expansion | `tests/test_fusioncode_building_v8_decomposition.py`, `tests/test_fusioncode_executor_handlers.py`, `tests/test_tiled_multisource_building_runtime_service.py`, `tests/test_run_benin_multisource_building_fusion.py` | executable in validation flows, but not routed by default bounded runtime |
| building raster presence / height primitives | `research_utility` | `adapters/fusioncode_building_adapter.py` -> `run_building_presence_raster`, `run_building_height_from_raster`; `fusion_algorithms/building_raster.py` | `kg/seed.py` -> `algo.validate.building.presence_raster.v1`, `algo.enrich.building.height_from_raster.v1` plus reserved raster seams | `kg/seed.py` and `fusion_algorithms/contracts.py` -> raster presence / height params | `agent/tooling.py` / `agent/executor.py` -> `_handle_building_presence_raster`, `_handle_building_height_from_raster` | `agent/retriever.py` surfaces both through reserved-capability hints; `agent/validator.py` still blocks reservation-only runtime inputs | `tests/test_fusioncode_building_raster.py`, `tests/test_fusioncode_executor_handlers.py`, `tests/test_planner_context.py` | executable primitive exists, but runtime input materialization and shared claim remain bounded |
| building conflict / optimization / quality chain | `research_utility` | `adapters/fusioncode_building_adapter.py` -> road topology, conflict graph, post-shrink, road-tail, quality metrics; `fusion_algorithms/building_optimization.py`, `fusion_algorithms/quality.py` | `kg/seed.py` -> `algo.optimize.*`, `algo.refine.*`, `algo.assess.building.quality_metrics.v1`, workflow steps 8-13 | `kg/seed.py` and `fusion_algorithms/contracts.py` -> optimization and conflict params | `agent/tooling.py` / `agent/executor.py` -> `_handle_building_road_topology`, `_handle_building_conflict_graph`, `_handle_building_post_conflict_shrink`, `_handle_building_road_tail`, `_handle_building_quality_metrics`, `_handle_spatial_conflicts` | visible through decomposed building workflow and reserved capability hints rather than default runtime selection | `tests/test_fusioncode_executor_handlers.py`, `tests/test_fusioncode_poi.py` for conflict detector, `tests/test_fusioncode_kg_metadata.py` | pieces are wired, but shared runtime evidence is still validation-utility level |
| road segment topology fusion | `runtime_supported` | `adapters/fusioncode_linear_adapter.py` -> `run_road_segment_topology`; `fusion_algorithms/road_fusion.py` | `kg/seed.py` -> `algo.fusion.road.segment_match_topology.v1`, `wp.road.fusioncode.segment_topology.v1` | `kg/seed.py` and `fusion_algorithms/contracts.py` -> road params | `agent/tooling.py` / `agent/executor.py` -> `_handle_road_segment_match_topology` | `agent/planner.py`, `agent/retriever.py`, `tests/test_planner_context.py` expose road pattern | `tests/test_fusioncode_linear_water_road.py`, `tests/test_fusioncode_executor_handlers.py`, `tests/test_fusioncode_kg_metadata.py` | aligned with current bounded road runtime slice |
| water line fusion | `runtime_supported` | `adapters/fusioncode_linear_adapter.py` -> `run_water_line_three_source`; `fusion_algorithms/water_fusion.py` | `kg/seed.py` -> `algo.fusion.water.line_three_source_priority.v1`, `wp.water.fusioncode.line_and_polygon.v1` | `kg/seed.py` and `fusion_algorithms/contracts.py` -> water line params | `agent/tooling.py` / `agent/executor.py` -> `_handle_water_line_three_source` | `agent/planner.py`, `agent/retriever.py`, `tests/test_planner_context.py` expose water pattern | `tests/test_fusioncode_linear_water_road.py`, `tests/test_fusioncode_executor_handlers.py`, `tests/test_fusioncode_kg_metadata.py` | aligned with current bounded water slice |
| water polygon fusion | `runtime_supported` | `adapters/fusioncode_polygon_adapter.py` -> `run_water_polygon_priority_merge`; `fusion_algorithms/water_fusion.py` | `kg/seed.py` -> `algo.fusion.water.polygon_priority_merge.v1`, `wp.water.fusioncode.line_and_polygon.v1` | `kg/seed.py` and `fusion_algorithms/contracts.py` -> water polygon params | `agent/tooling.py` / `agent/executor.py` -> `_handle_water_polygon_priority_merge` | `agent/planner.py`, `agent/retriever.py`, `tests/test_planner_context.py` expose water pattern | `tests/test_fusioncode_linear_water_road.py`, `tests/test_fusioncode_executor_handlers.py`, `tests/test_fusioncode_kg_metadata.py` | aligned with current bounded water slice |
| poi geohash neighbor fusion | `bounded_supported` | `adapters/fusioncode_poi_adapter.py` -> `run_poi_geohash_neighbor_match`; `fusion_algorithms/poi_fusion.py` | `kg/seed.py` -> `algo.fusion.poi.geohash_neighbor_match.v1`, `wp.poi.fusioncode.geohash_priority.v1` | `kg/seed.py` and `fusion_algorithms/contracts.py` -> POI params | `agent/tooling.py` / `agent/executor.py` -> `_handle_poi_geohash_neighbor_match` | `agent/planner.py`, `agent/retriever.py`, `tests/test_planner_context.py` expose bounded POI pattern | `tests/test_fusioncode_poi.py`, `tests/test_fusioncode_executor_handlers.py`, `tests/test_fusioncode_kg_metadata.py` | stays intentionally bounded; no general entity-resolution claim |

## Phase D Status

- D1 parity ledger: now live in this file.
- D2 six-element check: completed at the inventory level in the matrix above.
- D3 claim cleanup: partially completed. Road, water, and bounded POI are aligned with checked-in tests and runtime visibility. Building multi-source and raster-assisted primitives remain executable but are still held at `research_utility` because shared runtime routing and bounded evidence are not yet equivalent to the stable runtime contract.
- D4 smoke / inspection evidence: still open.
- D5 final wording cleanup across every doc: still open.

## Immediate Next Checks

Before promoting any building `fusioncode` claim above `research_utility`, require all of the following together:

- a shared-runtime entry path, not only an offline validation script
- non-reserved planner or retriever visibility for the required source-set and raster inputs
- run-level audit / inspection evidence under the standard contract
- documentation wording aligned in README, operations docs, capability inventory, and this ledger
