# V7 Road And Waterways Algorithm Replacement Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current simplified road and water-line fusion algorithms with the V7 road / waterways conflation algorithms from `E:\vscode\fusionAgent\Algorithm`, and remove the old algorithms from active algorithm metadata, KG seed, workflow patterns, repair alternatives, and runtime routes so KG reasoning, planner selection, and LLM tool calls cannot choose the obsolete implementations.

**Architecture:** Productize `Algorithm\road_fusion_optimized_v7.py` and `Algorithm\waterways_fusion_v7.py` into importable `fusion_algorithms` modules with typed configs, explicit return objects, canonical output schemas, and evidence stats. Split line waterway fusion from generic `water` fusion. Road and waterways national-scale execution should call the V7 pipeline directly, while water polygon fusion remains a separate track. Old road/water-line algorithms must not remain selectable fallback algorithms.

**Tech Stack:** Python, GeoPandas, Shapely, pandas, numpy, pyogrio, existing FusionAgent KG repository/seed/bootstrap, Track B national-scale runtime, pytest.

---

## Scope

### In Scope

- Productize V7 road conflation and V7 waterways conflation as runtime-callable library modules.
- Replace active road and waterways algorithm IDs in KG seed, registry metadata, workflow patterns, and national runtime.
- Add explicit `waterways` task/source/data-type semantics instead of treating line waterways as generic `water`.
- Add local Pakistan waterways source contract so `Pakistan_Waterways_Data.shp` is not misrepresented as HydroRIVERS.
- Emit V7 fusion stats into evidence artifacts and operator reports.
- Add grep/test gates that prevent old algorithms from re-entering active KG/runtime paths.

### Out Of Scope

- Building, POI, and raster algorithm rewrites.
- Frontend changes.
- Authentication, multi-tenant operation, or production deployment hardening.
- Rewriting water polygon fusion beyond separating it from line waterways and preserving a clear polygon-only track.
- Creating a generic all-country local waterways downloader. This plan only creates the source-contract path needed for local/preloaded waterways.

## Non-Negotiables

- Old road and water-line algorithms cannot remain active fallback candidates.
- Safe mode must be a V7 config profile, not a route to the old algorithm.
- `water` cannot continue to implicitly mean both water polygons and waterway lines.
- `raw.hydrorivers.water` cannot be used for local Pakistan waterways data.
- Active KG workflow patterns must not reference deprecated algorithm IDs.
- National runtime must not import or call `run_road_segment_match_topology()` or `fuse_water_lines()`.
- Output schemas for V7 line fusion must be semantic fusion schemas, not raw field unions.

---

## Current Findings

### New Algorithm Sources

- `E:\vscode\fusionAgent\Algorithm\road_fusion_optimized_v7.py`
  - Main reusable logic: `RoadFusionConfig`, `fuse_roads_pipeline()`, matching, residual extraction, duplicate pruning, endpoint snapping, dangle cleanup, stats writing.
  - Important phases: split by angle/max length, coverage-based matching, unmatched supplement retention, matched residual extraction, single/group duplicate removal, near-base-return pruning, crossing duplicate pruning, endpoint snap.

- `E:\vscode\fusionAgent\Algorithm\waterways_fusion_v7.py`
  - Reuses V7 road pipeline.
  - Defines waterways-specific config.
  - Adds `polish_waterway_attributes()` to produce canonical waterways fields such as `fusion_source`, `match_role`, `matched_supplement_high`, `supplement_segment_id`, `waterway_class`.

### Current Active Runtime Calls To Replace

- `services\track_b_national_scale_service.py`
  - Imports `run_road_segment_match_topology` from `fusion_algorithms.road_fusion`.
  - Imports `fuse_water_lines`, `fuse_water_polygons` from `fusion_algorithms.water_fusion`.
  - Calls `run_road_segment_match_topology(base_tile, ref_tile)` for road.
  - Calls `fuse_water_lines(line_sources)` inside `_run_water_tile_fusion()`.

### Current Active KG/Registry IDs To Remove Or Deprecate

- `algo.fusion.road.v1`
- `algo.fusion.road.safe`
- `algo.fusion.water.v1`
- `algo.fusion.road.segment_match_topology.v1`
- `algo.fusion.water.line_three_source_priority.v1`

These may remain only in migration notes or explicit negative tests. They must not appear in active workflow patterns, runtime-candidate algorithm metadata, repair alternatives, or planner expected outputs.

---

## Target IDs And Semantics

### New Algorithm IDs

- `algo.fusion.road.conflation.v7`
- `algo.fusion.waterways.conflation.v7`
- `algo.fusion.water_polygon.priority_merge.v2`

### New Or Revised Data Types

- `dt.road.bundle`
- `dt.road.fused`
- `dt.road.quality_report`
- `dt.waterways.bundle`
- `dt.waterways.fused`
- `dt.waterways.quality_report`
- `dt.water_polygon.bundle`
- `dt.water_polygon.fused`
- `dt.water.bundle` only as a composite/compatibility type, not as the default line fusion type.

### New Or Revised Catalog Sources

- `catalog.flood.road`
  - base: `raw.osm.road`
  - supplement: configured road reference source, e.g. Overture/Microsoft-compatible line source depending on existing source matrix.

- `catalog.flood.waterways`
  - base: `raw.osm.waterways`
  - supplement: `raw.local.pakistan.waterways` or generic local waterways supplement.

- `catalog.flood.water_polygon`
  - base: `raw.osm.water`
  - supplement: `raw.hydrolakes.water`

### New Local Waterways Source Contract

- `raw.local.pakistan.waterways`
  - theme: `waterways`
  - role: `supplement_line`
  - acquisition: local/manual preload
  - geometry: `LineString`, `MultiLineString`
  - ID field candidates: `osm_id`
  - class field candidates: `waterway`
  - name fields: `name`, `name_en`, `name_ur`
  - source fields: `source`, `osm_type`
  - normalization profile: `fields.waterways.local_osm_like`

---

## File Structure

### Create

- `fusion_algorithms/line_conflation_v7.py`
  - Shared V7 line conflation primitives copied/adapted from `Algorithm\road_fusion_optimized_v7.py`.

- `fusion_algorithms/road_conflation_v7.py`
  - Road-specific config/profile and public road runtime entry point.

- `fusion_algorithms/waterways_conflation_v7.py`
  - Waterways-specific config/profile, public waterways runtime entry point, and canonical schema polishing.

- `tests/test_road_conflation_v7.py`
- `tests/test_waterways_conflation_v7.py`
- `tests/test_v7_algorithm_registry_replacement.py`
- `tests/test_v7_kg_seed_replacement.py`
- `tests/test_track_b_national_v7_routes.py`
- `tests/test_waterways_source_contract.py`

### Modify

- `fusion_algorithms/contracts.py`
  - Add V7 config/result dataclasses if not placed in the new V7 modules.

- `fusion_algorithms/registry_metadata.py`
  - Add V7 algorithm nodes and parameter specs.
  - Remove active old road/water-line algorithms.

- `fusion_algorithms/road_fusion.py`
  - Deprecate or remove active runtime exports after call sites are replaced.

- `fusion_algorithms/water_fusion.py`
  - Keep polygon path only, or mark line helpers as deprecated and non-runtime.

- `services/track_b_national_scale_service.py`
  - Replace old road and water-line calls with V7 road/waterways pipeline.
  - Split water polygon and waterways paths.

- `services/track_b_source_normalization.py`
  - Add `fields.waterways.osm`, `fields.waterways.local_osm_like`, and optional `fields.waterways.hydrorivers`.

- `kg/track_b_source_contract.py`
  - Add waterways theme/source contracts.
  - Keep HydroRIVERS semantically separate from local Pakistan waterways.

- `kg/source_catalog.py`
  - Add `catalog.flood.waterways` and local waterways raw source spec.
  - Ensure `catalog.flood.water` no longer hides line waterways semantics.

- `kg/seed.py`
  - Replace old algorithm nodes and workflow pattern references with V7 IDs.
  - Remove old algorithm alternatives from active repair paths.

- `kg/bootstrap/neo4j_bootstrap.cypher`
  - Regenerate or manually update active Algorithm, StepTemplate, and DataSource nodes.

- `docs/fusioncode-algorithm-library.md`
  - Replace old algorithm library claims with V7 road/waterways algorithm IDs and status.

- `scripts/eval_harness.py`
  - Replace expected active algorithm IDs for road/waterways.

- Existing tests that assert old IDs.
  - Update to V7 IDs or convert to negative/deprecated tests.

---

## Phase 1: Productize V7 Line Conflation Library

**Files:**
- Create: `fusion_algorithms/line_conflation_v7.py`
- Modify: `fusion_algorithms/contracts.py` if shared result contracts are preferred there.
- Tests: `tests/test_road_conflation_v7.py`, `tests/test_waterways_conflation_v7.py`

- [ ] Copy the stable algorithm phases from `Algorithm\road_fusion_optimized_v7.py` into reusable functions.
- [ ] Preserve key V7 behavior:
  - split by sharp turns
  - split by max segment length
  - unique generated segment IDs after splitting
  - coverage-based matching
  - residual extraction from partially matched supplement lines
  - unmatched supplement retention
  - single-line duplicate removal
  - group duplicate removal
  - near-base-return pruning
  - crossing duplicate pruning
  - endpoint snapping
  - optional dangle cleanup
- [ ] Replace script paths and `main()` usage with public API functions.
- [ ] Define a result object:

```python
@dataclass
class LineConflationResult:
    frame: gpd.GeoDataFrame
    stats: dict[str, Any]
    config: dict[str, Any]
    lineage: dict[str, Any]
    warnings: list[str]
```

- [ ] Ensure API accepts both paths and already-loaded GeoDataFrames.
- [ ] Ensure all output can be written as GPKG without Shapefile field truncation assumptions.

**Verification:**
- [ ] Small synthetic line test proves matched supplement is removed from supplement output.
- [ ] Partial overlap test proves uncovered residual is retained.
- [ ] Duplicate supplement test proves duplicate pruning removes near-identical supplement lines.
- [ ] MultiLineString input test proves no crash.
- [ ] Stats include matched/unmatched/residual/duplicate counts.

**Anti-pattern guards:**
- [ ] Do not call script `main()` from runtime.
- [ ] Do not store hard-coded absolute paths from `Algorithm\*.py`.
- [ ] Do not use original feature IDs as spatial-index keys after splitting.

---

## Phase 2: Productize Road V7 Runtime

**Files:**
- Create: `fusion_algorithms/road_conflation_v7.py`
- Modify: `fusion_algorithms/registry_metadata.py`
- Tests: `tests/test_road_conflation_v7.py`

- [ ] Add `RoadConflationV7Config` or reuse `RoadFusionConfig` with road defaults.
- [ ] Add public function:

```python
def run_road_conflation_v7(
    base: gpd.GeoDataFrame | Path | str,
    supplement: gpd.GeoDataFrame | Path | str,
    *,
    config: RoadConflationV7Config | None = None,
) -> LineConflationResult:
    ...
```

- [ ] Preserve stats compatible with `Algorithm\road_fusion_optimized_v7.py`.
- [ ] Add canonical road fields where practical:
  - `fusion_source`
  - `match_role`
  - `matched_supplement_segment_id`
  - `supplement_segment_id`
  - `road_class`
  - `source_layer`
  - `residual_from_matched`
  - `residual_part`
- [ ] Add config profiles:
  - `balanced`
  - `quality`
  - `fast`
  - `conservative`

**Verification:**
- [ ] Road V7 API test returns a GeoDataFrame and stats.
- [ ] Conservative profile uses the same V7 algorithm, not old `road.safe`.
- [ ] GPKG write/read preserves canonical fields.

**Anti-pattern guards:**
- [ ] Do not reintroduce `algo.fusion.road.safe` as fallback.
- [ ] Do not call `run_road_segment_match_topology()`.

---

## Phase 3: Productize Waterways V7 Runtime

**Files:**
- Create: `fusion_algorithms/waterways_conflation_v7.py`
- Modify: `fusion_algorithms/registry_metadata.py`
- Tests: `tests/test_waterways_conflation_v7.py`

- [ ] Add waterways-specific config using defaults from `Algorithm\waterways_fusion_v7.py`.
- [ ] Add public function:

```python
def run_waterways_conflation_v7(
    base: gpd.GeoDataFrame | Path | str,
    supplement: gpd.GeoDataFrame | Path | str,
    *,
    config: WaterwaysConflationV7Config | None = None,
) -> LineConflationResult:
    ...
```

- [ ] Port `polish_waterway_attributes()` into library form.
- [ ] Output canonical waterways schema:
  - `fusion_source`
  - `match_role`
  - `matched_supplement_high`
  - `matched_supplement_loose`
  - `supplement_segment_id`
  - `matched_base_segment_id`
  - `waterway_class`
  - `name`
  - `name_en`
  - `name_ur`
  - `width`
  - `depth`
  - `covered`
  - `layer`
  - `blockage`
  - `tunnel`
  - `natural`
  - `water`
  - `supplement_source`
  - `source_layer`
  - `residual_from_matched`
  - `residual_part`
  - `residual_parent_FID_1`
  - `geometry`
- [ ] Ensure final output contains only line geometries.

**Verification:**
- [ ] Fixture with OSM waterways and Pakistan local waterways maps IDs/classes correctly.
- [ ] `source_feature_id` or generated segment IDs are not mostly empty.
- [ ] Output geometry types are only `LineString` or `MultiLineString`.
- [ ] Stats match expected high-level V7 categories.

**Anti-pattern guards:**
- [ ] Do not route local Pakistan waterways through `raw.hydrorivers.water`.
- [ ] Do not append water polygons to waterways output.
- [ ] Do not call `fuse_water_lines()`.

---

## Phase 4: Source Contracts And Normalization

**Files:**
- Modify: `kg/track_b_source_contract.py`
- Modify: `kg/source_catalog.py`
- Modify: `services/track_b_source_normalization.py`
- Tests: `tests/test_waterways_source_contract.py`, `tests/test_track_b_source_matrix.py`, `tests/test_national_source_matrix.py`

- [ ] Add source contract for `raw.local.pakistan.waterways`.
- [ ] Add raw source spec for local/manual waterways path discovery.
- [ ] Add `catalog.flood.waterways`.
- [ ] Add or revise `catalog.flood.water_polygon`.
- [ ] Add normalization profile `fields.waterways.local_osm_like`.
- [ ] Add normalization profile `fields.waterways.osm`.
- [ ] Keep `raw.hydrorivers.water` restricted to HydroRIVERS-like schema.
- [ ] Ensure `raw.osm.water` remains polygon-only and `raw.osm.waterways` remains line-only.

**Verification:**
- [ ] `normalization_summary.json` for Pakistan local waterways reports `raw.local.pakistan.waterways`, not `raw.hydrorivers.water`.
- [ ] `field_mapping_profile` is waterways-specific.
- [ ] Feature ID field is populated from `osm_id`.
- [ ] Geometry filter rejects polygon features in waterways normalization.

**Anti-pattern guards:**
- [ ] Do not widen `raw.hydrorivers.water` to accept arbitrary local waterways.
- [ ] Do not use one `fields.water.*` profile for both lines and polygons.

---

## Phase 5: KG And Registry Replacement

**Files:**
- Modify: `kg/seed.py`
- Modify: `fusion_algorithms/registry_metadata.py`
- Modify: `kg/bootstrap/neo4j_bootstrap.cypher`
- Modify: `docs/fusioncode-algorithm-library.md`
- Tests: `tests/test_v7_algorithm_registry_replacement.py`, `tests/test_v7_kg_seed_replacement.py`, affected KG tests.

- [ ] Add algorithm node `algo.fusion.road.conflation.v7`.
- [ ] Add algorithm node `algo.fusion.waterways.conflation.v7`.
- [ ] Add algorithm node `algo.fusion.water_polygon.priority_merge.v2` if polygon path remains runtime-supported.
- [ ] Add parameter specs for V7 config fields:
  - `target_crs`
  - `angle_threshold`
  - `max_segment_length`
  - `match_buffer_dist`
  - `max_hausdorff`
  - `loose_angle_threshold`
  - `min_len_similarity`
  - `min_supplement_coverage_for_matched`
  - `preserve_matched_supplement_residuals`
  - `min_residual_length`
  - duplicate and pruning thresholds
  - cleanup mode
  - output CRS
- [ ] Remove old algorithm IDs from active `ALGORITHMS`.
- [ ] Remove old algorithm IDs from active `FUSIONCODE_ALGORITHMS`.
- [ ] Remove old algorithm IDs from active workflow pattern steps.
- [ ] Remove old algorithm IDs from active repair alternatives.
- [ ] If a deprecated ledger is required, mark old algorithms as:

```json
{
  "runtime_status": "deprecated",
  "selectable_now": false,
  "deprecated_by": "algo.fusion.road.conflation.v7"
}
```

- [ ] Do not include deprecated algorithms in active KG retrieval unless the query explicitly asks for deprecated history.

**Verification:**
- [ ] `get_algorithm("algo.fusion.road.v1")` does not return a runtime candidate.
- [ ] `get_algorithm("algo.fusion.water.v1")` does not return a runtime candidate.
- [ ] `list_workflow_patterns()` contains V7 IDs for road and waterways.
- [ ] `get_alternative_algorithms("algo.fusion.road.conflation.v7")` does not include old road algorithms.
- [ ] Bootstrap Cypher contains V7 active nodes and no active old road/water-line StepTemplate references.

**Anti-pattern guards:**
- [ ] Do not keep `algo.fusion.road.safe` as alternative fallback.
- [ ] Do not leave old IDs in `docs/fusioncode-algorithm-library.md` as runtime-supported.

---

## Phase 6: Workflow Pattern Replacement

**Files:**
- Modify: `kg/seed.py`
- Modify: `fusion_algorithms/registry_metadata.py`
- Tests: `tests/test_planner_context.py`, `tests/test_ontology_closure.py`, `tests/test_kg_repository_enhancements.py`

- [ ] Replace `wp.flood.road.default` algorithm with `algo.fusion.road.conflation.v7`.
- [ ] Replace `wp.typhoon.road.default` algorithm with `algo.fusion.road.conflation.v7`.
- [ ] Remove or repoint `wp.flood.road.safe` and `wp.typhoon.road.safe` to V7 conservative config.
- [ ] Add `wp.flood.waterways.default` using `algo.fusion.waterways.conflation.v7`.
- [ ] Add `wp.flood.water_polygon.default` using polygon algorithm.
- [ ] Update pattern names and step names so they do not say generic `water_fusion` when executing waterways.
- [ ] Ensure generic `wp.flood.water.default` either becomes a composite route or does not execute line fusion directly.

**Verification:**
- [ ] Road planning chooses `algo.fusion.road.conflation.v7`.
- [ ] Waterways planning chooses `algo.fusion.waterways.conflation.v7`.
- [ ] Generic water planning does not silently choose waterways unless the request mentions line waterways/rivers/streams/canals.

**Anti-pattern guards:**
- [ ] Do not keep old algorithm IDs in any `PatternStep`.
- [ ] Do not use old safe route as a workflow fallback.

---

## Phase 7: Track B National Runtime Replacement

**Files:**
- Modify: `services/track_b_national_scale_service.py`
- Tests: `tests/test_track_b_national_scale_service.py`, `tests/test_track_b_national_v7_routes.py`

- [ ] Remove imports:
  - `run_road_segment_match_topology`
  - `fuse_water_lines`
- [ ] Add imports:
  - `run_road_conflation_v7`
  - `run_waterways_conflation_v7`
- [ ] Replace road national fusion route with V7 road route.
- [ ] Add waterways national fusion route.
- [ ] Keep water polygon route separate.
- [ ] Decide whether V7 line fusion runs national-level or tile-level:
  - Preferred first implementation: national-level V7 pipeline to avoid tile seam artifacts.
  - If tile-level is required, implement V7-aware stitch and stats merge.
- [ ] Write `fusion_stats.json` from V7 stats.
- [ ] Include `fusion_stats.json` in `inspection_summary.json`.
- [ ] Include config snapshot and algorithm ID in `stitched_artifact.json`.

**Verification:**
- [ ] Road national smoke output includes V7 stats.
- [ ] Waterways national smoke output includes V7 stats.
- [ ] Waterways output is line-only.
- [ ] Water polygon output is polygon-only.
- [ ] `rg "run_road_segment_match_topology|fuse_water_lines" services/track_b_national_scale_service.py` returns no matches.

**Anti-pattern guards:**
- [ ] Do not run V7 line fusion inside the old generic water tile loop.
- [ ] Do not combine polygon and line outputs into one GPKG unless a composite report explicitly requires it.

---

## Phase 8: Evidence, Reports, And Quality Gates

**Files:**
- Modify: `services/artifact_evaluation_service.py` if extra metrics belong there.
- Modify: `services/scenario_report_service.py` if scenario reports need stats.
- Modify: `services/track_b_national_scale_service.py`
- Tests: evidence/report tests touched by Track B.

- [ ] Add `fusion_stats.json`.
- [ ] Add `quality_summary.json` or embed quality summary in existing evidence.
- [ ] Track road/waterways line metrics:
  - `base_segments`
  - `supplement_segments`
  - `matched_supplement_segments`
  - `unmatched_supplement_segments`
  - `residual_supplement_segments`
  - `supplemented_segments`
  - `duplicate_removed_before_snap`
  - `group_duplicate_removed_before_snap`
  - `near_base_return_removed_before_snap`
  - `crossing_duplicate_removed_before_snap`
  - `duplicate_removed_after_snap`
  - `final_count`
  - `total_length_km`
  - `outside_boundary_count`
  - `invalid_geometry_count`
  - `elapsed_seconds`
  - `config`
- [ ] Update operator-readable report language:
  - no generic "fusion succeeded" without quality metrics
  - include matched/unmatched/residual/duplicate counts
- [ ] Preserve input hashes / source version tokens where available.

**Verification:**
- [ ] Evidence files prove which algorithm ID and config profile ran.
- [ ] Evidence files include source IDs and source contract profiles.
- [ ] Reports distinguish road, waterways, and water polygon outputs.

**Anti-pattern guards:**
- [ ] Do not treat feature count alone as success.
- [ ] Do not hide duplicate/removal/residual stats from operator evidence.

---

## Phase 9: API, Planner, And LLM Guardrails

**Files:**
- Modify planner/retriever/validator files as needed after locating exact references:
  - `agent/planner.py`
  - `agent/retriever.py`
  - `agent/validator.py`
  - `services/plan_grounding_service.py`
  - `services/tool_contract_report_service.py`
- Tests:
  - `tests/test_planner_context.py`
  - `tests/test_tool_contract_report_service.py`
  - any API v2 integration tests expecting old algorithm IDs.

- [ ] Ensure planner context only exposes active V7 algorithms for road/waterways.
- [ ] Add negative guard: deprecated algorithms are not surfaced as alternatives.
- [ ] Update plan validation so old IDs fail active runtime validation.
- [ ] Ensure tool contract report accepts V7 tool refs and rejects old tool refs where active execution is expected.
- [ ] Add LLM prompt/context note in retrieval metadata:
  - old algorithms deprecated
  - road uses V7
  - waterways uses V7
  - water polygons are separate

**Verification:**
- [ ] Generated road plan uses `algo.fusion.road.conflation.v7`.
- [ ] Generated waterways plan uses `algo.fusion.waterways.conflation.v7`.
- [ ] Generated generic water plan does not use deprecated `algo.fusion.water.v1`.
- [ ] Validator rejects old runtime candidate IDs.

**Anti-pattern guards:**
- [ ] Do not leave old algorithm IDs in examples that the LLM may retrieve as active examples.
- [ ] Do not map "safe" to old algorithm IDs.

---

## Phase 10: Migration Cleanup

**Files:**
- Modify all files found by grep gate below.
- Tests: full targeted suite plus grep gate.

- [ ] Run grep gate:

```powershell
rg "algo\.fusion\.road\.v1|algo\.fusion\.road\.safe|algo\.fusion\.water\.v1|segment_match_topology|line_three_source_priority|fuse_water_lines|run_road_segment_match_topology" kg fusion_algorithms services tests docs scripts
```

- [ ] Classify every match:
  - active path: must be removed/replaced
  - deprecated ledger: allowed only if explicitly non-selectable
  - negative test: allowed
  - historical done plan: allowed but should not be used by retrieval as active plan
- [ ] Update docs and tests that still call old IDs runtime-supported.
- [ ] Move this plan to `docs/superpowers/plans/done/` only after implementation and verification are complete.

**Verification:**
- [ ] Grep gate has no active old references.
- [ ] Unit tests pass.
- [ ] KG seed tests pass.
- [ ] Track B national route tests pass.

---

## Phase 11: Pakistan Regression

**Data:**
- `E:\fyx\data\巴基斯坦\rare\water`
- Correct reference:
  - `E:\fyx\data\巴基斯坦\fusion\waterways_fusion_v7\pakistan_waterways_fused_v7_final.gpkg`

- [ ] Run a small AOI waterways smoke using:
  - base: `raw.osm.waterways`
  - supplement: `raw.local.pakistan.waterways`
  - algorithm: `algo.fusion.waterways.conflation.v7`
- [ ] Compare output stats against V7 reference behavior:
  - output line-only
  - has canonical waterways schema
  - includes matched/unmatched/residual stats
  - does not output water polygons
- [ ] Run national Pakistan waterways if small AOI passes.
- [ ] Record evidence under `E:\fyx\data\巴基斯坦\fusionwatertest` or a clearly named subdirectory.
- [ ] Verify no boundary leakage beyond expected tolerance.

**Verification:**
- [ ] `inspection_summary.json` reports V7 algorithm ID.
- [ ] `fusion_stats.json` exists.
- [ ] Output geometry types are line-only.
- [ ] Output schema includes `fusion_source`, `match_role`, `waterway_class`.
- [ ] Stats are directionally consistent with `waterways_fusion_v7` reference.

---

## Recommended Execution Order

1. Productize V7 common line conflation library.
2. Add road V7 wrapper and tests.
3. Add waterways V7 wrapper and tests.
4. Add local Pakistan waterways source contract and normalization.
5. Add new data types, algorithm IDs, and registry metadata.
6. Replace KG seed workflow patterns.
7. Replace Neo4j bootstrap.
8. Replace Track B national runtime routes.
9. Add evidence/report stats.
10. Add planner/validator guardrails.
11. Run grep gate and targeted tests.
12. Run Pakistan small AOI regression.
13. Run Pakistan national waterways regression.

---

## Minimum Acceptance Criteria

- Road plans and national runs use `algo.fusion.road.conflation.v7`.
- Waterways plans and national runs use `algo.fusion.waterways.conflation.v7`.
- Old algorithm IDs are not active runtime candidates, alternatives, or workflow pattern steps.
- `raw.local.pakistan.waterways` exists and maps `osm_id`, `waterway`, `name`, `name_en`, `name_ur`.
- Pakistan local waterways are not normalized as HydroRIVERS.
- V7 stats are written to evidence.
- Waterways output is line-only and uses canonical waterways schema.
- Generic water polygon output remains polygon-only.
- Grep gate confirms no active old imports or algorithm IDs.

## Final Verification Commands

```powershell
python -m pytest -q `
  tests/test_road_conflation_v7.py `
  tests/test_waterways_conflation_v7.py `
  tests/test_v7_algorithm_registry_replacement.py `
  tests/test_v7_kg_seed_replacement.py `
  tests/test_track_b_national_v7_routes.py `
  tests/test_waterways_source_contract.py
```

```powershell
rg "run_road_segment_match_topology|fuse_water_lines" services fusion_algorithms
```

```powershell
rg "algo\.fusion\.road\.v1|algo\.fusion\.road\.safe|algo\.fusion\.water\.v1|segment_match_topology|line_three_source_priority" kg fusion_algorithms services tests docs scripts
```

Any match in active runtime/KG/planner paths fails completion.
