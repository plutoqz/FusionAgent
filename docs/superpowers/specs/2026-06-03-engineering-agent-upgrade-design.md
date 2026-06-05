# Engineering Agent Upgrade Design

## Goal

Upgrade FusionAgent from an experimental fusion-agent prototype into an engineering-grade system that can execute real GIS fusion missions without operator intervention during the run.

The upgraded system must support global AOIs, with first-class validation for Africa and Pakistan. It may use preloaded local data, but after a mission starts it must autonomously plan tasks, acquire or reuse data, run fusion, retry or fall back when recoverable failures occur, and publish evidence that explains what succeeded, what failed, and why.

## Confirmed Product Decisions

- Use the incremental engineering route, not a framework rewrite.
- Keep the current `LLM + KG + Validator + PolicyEngine + Executor` architecture.
- For disaster scenarios, default to the full bounded mission bundle:
  - `building`
  - `road`
  - `water_polygon`
  - `waterways`
  - `poi`
- The product surface may describe this as four task families: building, road, water, and poi. The execution layer must treat water as two child tasks: polygon water bodies and waterways.
- Local preloaded data is allowed. Runtime execution must not require manual uploads, manual parameter edits, or human intervention.
- Data acquisition should try local data first, then remote official/provider-backed materialization where available, then retry and fallback paths when failures are recoverable.
- Primary fusion output should be GPKG. Shapefile can remain a compatibility export, but GPKG becomes the canonical artifact.
- A partially successful scenario uses the existing `partial` state. It means some child tasks have accepted outputs and every failed child task has entered structured failure handling, with successful outputs still available.
- Building fusion data requirements are algorithm-driven. The resolver should decide which data sources are needed from the selected algorithm's input contract. Priority rules such as `OSM > Google > Microsoft` are fallback rules, not the first planning principle.
- Building data should include OSM, Google, and Microsoft where available. Height raster, 3D, or other height-capable data is included only when the requested algorithm or mission output requires building height.
- The real validation matrix must include small city AOIs, medium regional AOIs, and a bounded large AOI for split/parallel/merge verification. Test targets should be selected from Africa and Pakistan.

## Non-Goals

- Do not replace the current orchestration with LangGraph or another agent framework in this upgrade.
- Do not turn FusionAgent into an unrestricted web-browsing data agent.
- Do not claim global production coverage for a source unless its acquisition, schema normalization, AOI clipping, and quality gates have executable evidence.
- Do not require every sparse layer to spatially fill the AOI. For water and POI, coverage means the query/materialization process covered the AOI and the resulting emptiness or sparsity is explainable.
- Do not block successful child outputs merely because another child task failed. Scenario status should communicate partial completion and recovery state.

## Current State Summary

The current runtime already contains useful foundations:

- `AgentRunService` persists each run under `runs/<run_id>/` by default, unless `GEOFUSION_RUNS_ROOT` is set.
- Each run has `input/`, `intermediate/`, `output/`, and `logs/` subdirectories.
- Task-driven input materialization already uses `InputAcquisitionService`, `LocalBundleCatalogProvider`, `RawVectorSourceService`, and `SourceAssetService`.
- Local data is preferred from the repository `Data/` tree.
- Some remote materializers exist for Geofabrik/OSM, Microsoft Buildings, Overture transportation, HydroSHEDS, and GNS.
- Input materialization writes `source_materialization_manifest.json` with source id, selected source id, source mode, requested bbox, materialized bbox, component coverage, provider attempts, and recoverable fault information.
- `ArtifactRegistry` already stores reusable raw vectors and input bundles with `artifact_role` metadata.
- Final fusion artifacts are registered with `job_type`, `output_data_type`, schema policy, target CRS, bbox, and run id.
- Scenario output defaults to `E:\fyx\data\fusionagentTEST` when no request or environment output root is set.

The main gaps are:

- Disaster mission task expansion is not strict enough and can miss layers.
- Water is not consistently modeled as both water polygons and waterways at the mission layer.
- Data acquisition capabilities are partly executable but not governed by a unified data-source contract.
- Final fusion artifacts lack an explicit `artifact_role=fusion_result`.
- GPKG is not yet the canonical output across the runtime.
- Output success is still too close to "artifact exists, is readable, is non-empty, and has required fields".
- Quality gates do not yet verify AOI coverage, source lineage, multi-source contribution, or per-layer semantic expectations.
- Failed scenario children do not yet have a full delayed retry and recoverable failure lifecycle.

## Target Architecture

The upgraded flow is:

```text
User request or event
  -> Mission Compiler
  -> Mission Task Bundle
  -> Data Requirement Resolver
  -> Source Materialization
  -> Planner / Validator / PolicyEngine / Executor
  -> Quality Gate
  -> Scenario Failure Handler
  -> Evidence Package
```

The existing planner and executor remain central. The new components make mission scope, data requirements, and quality judgement explicit before and after the current agent loop.

## Component Design

### Mission Compiler

The Mission Compiler converts a request into a bounded mission specification before individual child runs are created.

Inputs:

- trigger type
- trigger content
- disaster type
- spatial extent or resolved AOI
- explicitly requested layers
- scenario metadata

Outputs:

- mission id
- normalized disaster type
- resolved or pending AOI requirement
- child task specs
- task family grouping
- required output roles
- mission-level success policy

Rules:

- A direct layer request such as "only fuse buildings" keeps its explicit scope.
- A disaster event or natural-language disaster scenario defaults to the full mission bundle.
- Full disaster mission bundle expands to five executable child tasks:
  - `building`
  - `road`
  - `water_polygon`
  - `waterways`
  - `poi`
- Unsupported requested layers are recorded and rejected or clarified before child runs start.
- The Mission Compiler should not select algorithms. It decides mission scope only.

### Task Model

The current `JobType.water` is not precise enough for the full mission. The upgrade needs an execution-level distinction between water polygons and waterways.

Recommended model:

- Keep public `JobType.water` if needed for compatibility.
- Introduce an internal `TaskKind` or equivalent execution key:
  - `building`
  - `road`
  - `water_polygon`
  - `waterways`
  - `poi`
- Map `water_polygon` to `dt.water.bundle -> dt.water.fused`.
- Map `waterways` to `dt.waterways.bundle -> dt.waterways.fused`.

This avoids overloading one water child run with two semantically different algorithms and output schemas.

### Data Requirement Resolver

The Data Requirement Resolver determines source requirements from the chosen or candidate algorithm contract.

It consumes:

- task kind
- candidate algorithms
- KG algorithm input types
- source semantic contracts
- output requirements
- optional mission requirements such as building height
- AOI and disaster context

It produces:

- required source roles
- acceptable source ids per role
- fallback order per role
- completeness policy
- whether a missing role blocks execution or causes degraded execution

Examples:

- Building footprint fusion without height:
  - required roles: primary footprint and reference footprint
  - candidates: OSM, Google, Microsoft
  - fallback priority only applies when multiple sources satisfy the same role or one role is unavailable
- Building height enrichment:
  - required roles: footprints plus height signal
  - height candidates: height raster, 3D building data, or other KG-declared height-capable source
- Road fusion:
  - required roles: base network and supplemental/reference network
  - candidates: OSM and Overture transportation where available
- Water polygon fusion:
  - required roles: base water polygons and supplemental/reference water polygons
  - candidates: OSM water and HydroLAKES/local water
- Waterways fusion:
  - required roles: base waterway lines and supplemental/reference river lines
  - candidates: OSM waterways and HydroRIVERS/local waterways
- POI fusion:
  - required roles: base POI and gazetteer/reference POI
  - candidates: OSM POI and GNS or local reference POI

### Data Source Knowledge Layer

Move source declarations toward a versioned data-source knowledge layer. YAML migration is allowed and should start with data sources and materialization metadata.

Each source should declare:

- `source_id`
- provider family
- task themes
- geometry types
- supported data types
- supported regions or coverage scope
- local path hints
- remote materialization provider
- auth or permission requirements
- source role candidates
- schema profile
- CRS behavior
- freshness policy
- claim state
- selectable state
- fallback alternatives
- known failure modes

The KG remains the knowledge base. The materializer remains the executable tool layer.

### Source Materialization

Source materialization should follow a consistent acquisition policy:

1. Try local preloaded data if it covers the AOI or can be clipped to it.
2. Try official/provider-backed remote acquisition.
3. Retry transient network failures with backoff.
4. Try alternate channel or alternate source role candidate if available.
5. Write a structured fault if all recoverable options fail.

Every materialization attempt must record:

- requested source id
- selected source id
- provider attempts
- local or remote source mode
- cache hit
- version token
- requested AOI
- materialized bbox
- feature count
- coverage status
- fault class if failed
- whether the fault is recoverable

The existing `source_materialization_manifest.json` should become a stable contract, not just a helper artifact.

### Data Asset Roles

Standardize asset roles across registry and evidence:

- `raw_source`: provider-level raw vector or raster data
- `input_bundle`: execution-ready task input bundle
- `intermediate`: transform, normalized, tile, or per-step output
- `fusion_result`: canonical fused output
- `compat_export`: compatibility export derived from canonical output
- `quality_report`: machine-readable quality gate result
- `evidence_package`: scenario or run evidence summary

Final fusion artifacts should explicitly set:

```json
{
  "artifact_role": "fusion_result"
}
```

This removes the need to infer role only from `job_type` and `output_data_type`.

### Canonical Output Format

GPKG becomes the canonical output format.

Rules:

- Fusion adapters should write GPKG as their primary artifact.
- Shapefile exports may be generated as compatibility outputs.
- Registry records for canonical outputs should point to the GPKG or a package containing the GPKG.
- Preview and inspection should read from the canonical GPKG when available.
- Quality gates should evaluate the canonical GPKG.

### Quality Gate

Quality Gate converts "run completed" into "fusion result accepted".

Minimum checks for every layer:

- artifact is readable
- canonical layer exists
- output is non-empty unless an explicit sparse/empty policy allows otherwise
- CRS is present and normalized
- output bbox is consistent with the requested AOI
- geometry type matches the task kind
- required fields exist
- source lineage fields exist
- output schema matches expected output type
- component source coverage is recorded

Additional checks by layer:

- Building:
  - polygon geometry
  - footprint source lineage
  - contribution from more than one source when more than one required source was available
  - height fields only required when height was requested
  - invalid geometries and duplicate footprint indicators below configured thresholds
- Road:
  - line geometry
  - road class or equivalent semantic field where available
  - base/supplemental lineage
  - total length greater than zero
  - topology sanity checks such as invalid geometries and excessive zero-length segments
- Water polygon:
  - polygon geometry
  - water class or source lineage
  - total area greater than zero when source coverage indicates water polygons exist in the AOI
- Waterways:
  - line geometry
  - waterway class or source lineage
  - total length greater than zero when source coverage indicates waterways exist in the AOI
- POI:
  - point geometry
  - name/category/id lineage where available
  - bounded AOI query evidence
  - multi-source contribution when reference POI data is available

Quality outputs:

- `quality_report.json`
- quality gate event in `audit.jsonl`
- compact quality summary in run inspection
- scenario-level aggregation in `scenario_summary.json`

### Scenario Failure Handling

Scenario status semantics:

- `succeeded`: all required child tasks pass quality gates.
- `partial`: at least one child task produced accepted output and at least one child task did not produce accepted output, but every failed child task has been captured by the failure handler with a recovery state and next action.
- `failed`: no required child task produced accepted output, or mission setup failed before any child task could run.
- `running`: at least one child task is still actively executing.

For `partial`:

- Successful child outputs remain published.
- Failed child tasks get failure records.
- Failure records include root cause, fault class, recoverability, recovery state, retry schedule if applicable, attempted sources, and next action.
- Scenario evidence must not hide failed children just because other children succeeded.
- Delayed retry, fallback, exhausted recovery, or blocked recovery is represented on the failed child task record instead of introducing a new scenario-level status.

Failure handling policy:

- Network or transient provider errors: retry with backoff.
- Missing local data with remote provider available: try remote.
- Empty coverage for a source role: try fallback source if the role is required.
- Empty coverage for sparse layers: distinguish true empty AOI from acquisition failure.
- Schema mismatch: block quality acceptance and mark as recoverable only if a known normalization path exists.
- Algorithm failure: try KG-declared alternate algorithm if available.

### Test And Validation Matrix

Validation should focus on Africa and Pakistan while preserving global design.

AOI classes:

- Small city AOI:
  - validates AOI resolution, source materialization, schema, and end-to-end output.
- Medium regional AOI:
  - validates larger downloads, clipping, caching, retry, and runtime stability.
- Bounded large AOI:
  - validates tiling, parallel child/tile processing, merge, and quality aggregation.

Candidate validation targets:

- Pakistan:
  - Karachi or Lahore small city AOI
  - Sindh/Punjab bounded medium or large bbox
- Africa:
  - Nairobi, Kenya
  - Gitega or Bujumbura, Burundi
  - Dakar, Senegal
  - Accra, Ghana
  - Lagos or Abuja, Nigeria

Final target selection should prefer AOIs where at least OSM, Microsoft Buildings, Overture, HydroSHEDS, and GNS have reasonable availability or official acquisition paths.

### Evidence Package

Each run should publish:

- `request.json`
- `run.json`
- `plan.json`
- `validation.json`
- `audit.jsonl`
- `source_materialization_manifest.json`
- `quality_report.json`
- canonical GPKG artifact
- compatibility exports when generated
- `repair_trace.json` when any recovery or fallback occurred

Each scenario should publish:

- `request.json`
- `scenario_summary.json`
- `source_coverage.json`
- `workflow_trace.json`
- `kg_path_trace.json`
- `evaluation.json`
- child run references
- successful artifact references
- failed child recovery records

### Phased Delivery

#### Phase 0: Baseline Freeze

Freeze current behavior before changing runtime code.

Deliverables:

- Current data-source matrix.
- Current default run/scenario output locations.
- Existing successful and failed scenario examples.
- Baseline smoke evidence for building, road, water, and poi where currently possible.

Exit criteria:

- A developer can compare future behavior against baseline evidence.

#### Phase 1: Mission Compiler

Implement strict mission expansion.

Deliverables:

- Mission Compiler service.
- Disaster scenario default expansion to building, road, water polygon, waterways, and poi.
- Compatibility handling for explicit single-layer requests.
- Scenario summary records expected task family and executable child tasks.

Exit criteria:

- A flood scenario without explicit layers creates five executable child task specs.
- A direct "only building" request still creates one building task.

#### Phase 2: Task Kind And Water Split

Add execution-level task kind support.

Deliverables:

- Internal task kind model.
- Water polygon and waterways mappings.
- Planner/retriever context updated to distinguish water output contracts.
- Scenario reporting groups both tasks under the water family.

Exit criteria:

- `water_polygon` and `waterways` can run and report independently.
- Scenario summary shows both under water without losing child-level detail.

#### Phase 3: Data Asset Contract

Standardize data roles and registry metadata.

Deliverables:

- Asset role vocabulary.
- `artifact_role=fusion_result` for final outputs.
- Stable manifest contract for raw sources and input bundles.
- Registry lookup tests for raw source, input bundle, and fusion result.

Exit criteria:

- Raw, input, intermediate, and final artifacts can be classified without path guessing.

#### Phase 4: Data Requirement Resolver

Make data needs algorithm-driven.

Deliverables:

- Resolver that derives required source roles from algorithm contracts.
- Building source role support for OSM, Google, Microsoft, and optional height signals.
- Per-role fallback policy.
- Source requirement evidence in plan context and audit.

Exit criteria:

- Building fusion chooses source roles from algorithm need, not a hardcoded global source priority.

#### Phase 5: Source Materialization Hardening

Turn data acquisition into a recoverable engineering subsystem.

Deliverables:

- Retry/backoff policy.
- Provider-attempt records for local, remote, and fallback paths.
- Recoverable fault classes.
- Africa/Pakistan source materialization tests.
- Optional prefetch command aligned with the same materializer.

Exit criteria:

- Network/provider failures create structured recoverable failure records instead of opaque run failures.

#### Phase 6: GPKG Canonical Output

Promote GPKG as primary output.

Deliverables:

- Adapter output contracts prefer GPKG.
- Registry and inspection use canonical GPKG.
- Shapefile compatibility export remains optional.

Exit criteria:

- New engineering validation runs produce canonical GPKG outputs for all successful child tasks.

#### Phase 7: Quality Gate

Implement layer-specific quality acceptance.

Deliverables:

- Quality gate service.
- Layer-specific minimum checks.
- `quality_report.json`.
- Run and scenario quality summaries.

Exit criteria:

- A run can fail after execution if its output does not meet the quality contract.

#### Phase 8: Scenario Failure Handling

Make partial success operationally useful.

Deliverables:

- Child failure records.
- Delayed retry scheduling hooks.
- Scenario `partial` semantics for accepted successful outputs plus handled failed child records.
- Repair trace standardization.

Exit criteria:

- A scenario with successful building and failed poi is `partial`, keeps building output, and records poi recovery state plus next action.

#### Phase 9: Engineering Validation Suite

Create the real-world validation suite.

Deliverables:

- Small, medium, and bounded-large AOI manifests for Africa and Pakistan.
- Scenario harness for full mission bundle.
- Evidence output under a single engineering validation root.

Exit criteria:

- The suite can prove that the system runs unattended from scenario request to outputs and quality reports.

## Acceptance Criteria

The first engineering-grade milestone is accepted when:

- A request such as `Karachi flood` or `Nairobi flood` creates the full mission bundle.
- The runtime creates child tasks for building, road, water polygon, waterways, and poi.
- Each child task attempts autonomous data materialization.
- Successful child tasks output canonical GPKG.
- Failed child tasks enter structured failure handling before a scenario is reported as `partial`.
- Scenario state is `succeeded`, `partial`, or `failed` according to quality-gated child outcomes.
- `partial` scenarios preserve successful outputs and expose failed child recovery details.
- Quality reports validate non-empty outputs, AOI consistency, expected schema, source lineage, and multi-source contribution where applicable.
- No manual file upload, parameter change, or code edit is needed during a mission run.

## Risks And Mitigations

- Global source coverage is uneven.
  - Mitigation: claim source capability by region and provider, not globally without evidence.
- Some providers require credentials, tools, or network conditions that may not exist on every machine.
  - Mitigation: record provider prerequisites and recoverable fault classes; allow local preload fallback.
- POI and water layers can be sparse.
  - Mitigation: distinguish AOI query coverage from non-empty result coverage.
- GPKG migration can break consumers expecting shapefile bundles.
  - Mitigation: keep compatibility exports while making GPKG canonical.
- Large AOI tests can consume excessive time.
  - Mitigation: use bounded large AOIs that exercise split/parallel/merge without requiring national-scale processing.

## Implementation Planning Notes

The implementation plan should be split into multiple plans rather than one monolithic task list:

1. Mission Compiler and task-kind split.
2. Data Asset Contract and registry metadata.
3. Data Requirement Resolver and source materialization hardening.
4. GPKG canonical output and quality gate.
5. Scenario failure handling and engineering validation suite.

Each plan should be independently testable and should preserve current successful runs wherever possible.
