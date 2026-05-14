# Agentic Any-Region Fusion Design

## Goal

Allow a user to submit a natural-language regional request such as `fuse building and road data for Nairobi, Kenya`, and have FusionAgent automatically:

1. resolve the requested area of interest from natural language into a structured AOI
2. select data and execution strategy through the existing `LLM + KG` planning flow
3. download and cache the required source data for the resolved AOI
4. clip and materialize execution-ready input bundles
5. run the existing `building` and `road` fusion adapters
6. emit auditable decisions, artifacts, and failure reasons

This feature must not replace the current planning architecture with a hardcoded pipeline. The planner must remain the component that decides which pattern, source strategy, and execution path to use.

## Non-Goals

- Do not convert FusionAgent into a free-form browser agent that directly performs arbitrary internet actions without runtime constraints.
- Do not bypass the current `WorkflowPlanner`, `PlanningContextBuilder`, policy engine, or audit system.
- Do not hardcode city-specific flows such as `if Nairobi then use Kenya`.
- Do not silently fabricate a building fusion result when no configured reference source has AOI coverage.

## Core Design

### 1. Agentic AOI Resolution Before Planning

Add a new AOI resolution stage that runs before `WorkflowPlanner.create_plan()`.

This stage will:

- extract a location query from `RunTrigger.content`
- query a geocoding service for multiple candidate places
- normalize each candidate into a common AOI shape
- optionally include candidate administrative hierarchy and display labels
- return a ranked `resolved_aoi` record plus all candidate evidence

The output is not the final plan. It is planner input.

The planner remains responsible for deciding whether the selected AOI is sufficient to proceed and which source strategy to use for the resolved area.

### 2. Keep LLM + KG As The Planning Center

The main planning loop stays:

`RunTrigger -> PlanningContextBuilder -> LLM workflow plan -> validation -> policy decisions -> execution`

The new feature extends, rather than replaces, this loop:

- `PlanningContextBuilder` gains `aoi_resolution` and `source_coverage_hints`
- KG-backed `data_sources` still describe what kinds of inputs and providers are available
- the LLM still chooses workflow tasks from KG-retrieved candidates
- policy records still capture `pattern_selection`, `data_source_selection`, `artifact_reuse_selection`, `parameter_strategy`, and `output_schema_policy`

The implementation bar is that a reviewer should still be able to point to the workflow plan and audit trail as the source of truth for why a run used a specific AOI and source strategy.

### 3. Region-Aware Source Materialization

The current `SourceAssetService` is a bounded Burundi benchmark helper. It must be generalized into a region-aware materialization layer that can serve arbitrary geocoded AOIs.

The generalized service will:

- prefer local repo `Data/` assets when they already satisfy the requested AOI
- otherwise build a country-aware OSM download path from the resolved AOI country metadata
- otherwise fetch reference-building sources using AOI-aware provider lookups
- clip materialized source data to the resolved AOI bbox or polygon before bundle assembly
- emit versioned cache paths and coverage metadata

The service remains a constrained tool layer. It executes source acquisition selected by the plan; it does not decide the plan by itself.

## Component Boundaries

### `services/aoi_resolution_service.py`

New service responsible for natural-language AOI resolution.

Responsibilities:

- accept `RunTrigger`
- derive the location phrase from the user request
- call a geocoding backend
- normalize geocoder payloads into `ResolvedAOICandidate`
- rank/select a final `ResolvedAOI`
- expose confidence and evidence for audit

Expected data shape:

```python
@dataclass(frozen=True)
class ResolvedAOICandidate:
    query: str
    display_name: str
    country_name: str | None
    country_code: str | None
    admin_level: str | None
    bbox: tuple[float, float, float, float]
    source: str
    confidence: float
    raw: dict[str, object]


@dataclass(frozen=True)
class ResolvedAOI:
    query: str
    display_name: str
    country_name: str | None
    country_code: str | None
    bbox: tuple[float, float, float, float]
    confidence: float
    selection_reason: str
    candidates: tuple[ResolvedAOICandidate, ...]
```

Selection rules:

- if exactly one high-confidence candidate exists, select it
- if multiple candidates are close in confidence but share the same country/admin chain, prefer the most specific admin match
- if multiple materially different candidates remain and confidence is low, fail with a structured ambiguity error instead of guessing

### `agent/retriever.py`

Modify `PlanningContextBuilder` so planner context includes:

- `intent.location_query`
- `intent.resolved_aoi`
- `retrieval.source_coverage_hints`
- `execution_hints.available_aoi`

This keeps AOI and source evidence inside the planner context seen by the LLM.

### `agent/planner.py`

Keep `WorkflowPlanner` as the only component that turns planner context into a workflow plan.

Changes:

- update the system prompt so the planner must reason over `resolved_aoi` and `source_coverage_hints`
- ensure normalized `plan.context` preserves AOI and source evidence
- ensure replans preserve the original resolved AOI unless a recovery action explicitly widens or changes it

The planner must not output free-form downloader steps. It should keep using the repo's existing workflow-task structure and KG source identifiers.

### `services/source_asset_service.py`

Refactor the service from Burundi-specific logic into a region-aware raw-source materializer.

Responsibilities:

- OSM country bundle acquisition from Geofabrik-like country-level distribution
- AOI-aware building-reference acquisition
- cache reuse keyed by source id, country, AOI hash, and provider version
- structured materialization status such as `local_data`, `asset_downloaded`, `asset_cached`, `coverage_empty`

The service should return both path and coverage metadata:

```python
@dataclass(frozen=True)
class SourceAssetResolution:
    source_id: str
    path: Path
    source_mode: str
    cache_hit: bool
    version_token: str
    bbox: tuple[float, float, float, float] | None
    feature_count: int | None
```

### `services/raw_vector_source_service.py`

Extend runtime raw-source resolution so it can use the generalized source-asset service when local `Data/` paths do not satisfy the requested AOI.

Required behavior:

- local `Data/` remains the first choice
- if local paths are missing, broken, or clip to empty for the requested AOI, fall back to remote/cache-backed materialization
- propagate source-mode metadata into artifact registry and audit

This change is what moves the new capability from benchmark-only into the real runtime.

### `services/local_bundle_catalog.py`

Keep bundle assembly logic, but let it consume raw sources that were materialized specifically for the resolved AOI.

Expected behavior:

- `catalog.flood.building` and `catalog.earthquake.building` remain abstract bundle ids
- the actual raw sources they assemble are clipped to the planner-selected AOI
- road bundles continue to allow `single_source_with_empty_ref`
- building bundles require non-empty OSM and non-empty reference coverage

### `services/agent_run_service.py`

Add orchestration for the new AOI stage.

Execution order becomes:

1. create run
2. resolve AOI
3. build planning context with `resolved_aoi`
4. create/validate plan
5. select data source strategy
6. materialize inputs for the resolved AOI
7. execute fusion
8. write artifacts and audit

Audit additions:

- `aoi_resolved`
- `aoi_resolution_failed`
- `source_coverage_checked`
- `task_inputs_resolved` enriched with AOI metadata

## Source Strategy

### Building

Building fusion must remain a real two-source fusion path.

For building runs:

- OSM building footprints are the primary baseline source
- at least one non-empty reference-building source must be found for the resolved AOI
- the planner may choose among configured reference candidates based on KG metadata plus coverage hints
- if no configured reference candidate yields non-empty clipped coverage, the run fails explicitly

This is stricter than the current adapter fallback behavior and is required to avoid fake success.

### Road

Road runs can continue using the current OSM-primary path with an empty generated reference bundle.

For road runs:

- OSM roads are clipped from the AOI-aligned country bundle
- an empty reference bundle is still acceptable
- the planner still records source choice and reasoning

## Data Flow

### Planning-Time Flow

1. User submits natural-language request.
2. `AOIResolutionService` extracts and resolves the location.
3. `PlanningContextBuilder` builds KG retrieval payload plus AOI evidence.
4. `WorkflowPlanner` calls the LLM with:
   - KG candidate patterns
   - source metadata
   - resolved AOI
   - source coverage hints
5. The resulting plan uses existing `WorkflowTask` objects and KG source ids.

### Execution-Time Flow

1. `AgentRunService` resolves input source ids from the validated plan.
2. `InputAcquisitionService` requests AOI-scoped bundle materialization.
3. `LocalBundleCatalogProvider` uses `RawVectorSourceService`.
4. `RawVectorSourceService` uses local paths or the generalized remote source materializer.
5. Clipped `osm.zip` and `ref.zip` are written into the run input directory.
6. Existing fusion adapters run unchanged on the prepared bundles.

## Failure Handling

### Ambiguous AOI

If the location resolver finds multiple materially different places and cannot confidently rank one, the run fails with:

- the original location query
- the conflicting candidate list
- the reasons the system refused to guess

This is preferable to running the wrong country.

### Empty Coverage

If source download succeeds but AOI clipping yields no features:

- record `coverage_empty`
- try the next configured reference source candidate for building runs
- for roads, if OSM clip is empty, fail immediately because there is no usable road baseline

### Broken Local Assets

If a local shapefile bundle is incomplete or unreadable:

- do not treat the path as valid local coverage
- fall back to remote/cache-backed materialization
- record the fallback reason in audit metadata

### Download Or Provider Errors

If a provider fails:

- retry bounded transient download failures once
- preserve partial cache artifacts only when they are reusable and complete
- otherwise fail with a provider-specific error recorded in audit

## “No Fake Agent” Guardrails

The implementation must satisfy all of these:

- no city-name switch statements in API or runtime orchestration
- no fixed Nairobi or Kenya pipeline branches
- no planner bypass that chooses source ids directly in `runs_v2.py`
- no hidden deterministic source override that ignores LLM/KG decisions
- no silent downgrade from building fusion to OSM-only “success”

Utility services may be deterministic. The system still counts as agentic because the planner is the decision-maker, while services are constrained tools executing those decisions.

## Testing Strategy

### Unit Tests

- `tests/test_aoi_resolution_service.py`
  - resolves a clear location query such as `Nairobi, Kenya`
  - surfaces ambiguity when two countries or cities compete
  - preserves confidence and candidate evidence
- `tests/test_source_asset_service.py`
  - builds country-aware OSM download URLs from AOI country metadata
  - filters Microsoft building tiles by AOI bbox
  - clips AOI data and returns feature counts
- `tests/test_raw_vector_source_service.py`
  - falls back from broken or missing local assets to AOI-aware remote materialization

### Planner Context Tests

- `tests/test_planner_context.py`
  - planner context now includes `resolved_aoi`
  - source coverage hints are visible to the LLM provider
  - `plan.context` preserves the resolved AOI and planning evidence

### Runtime Integration Tests

- `tests/test_agent_run_service_enhancements.py`
  - natural-language trigger content such as `fuse building and road data for Nairobi, Kenya` resolves an AOI before planning
  - audit contains `aoi_resolved`
  - task-driven input acquisition uses the resolved AOI bbox
- `tests/test_api_v2_integration.py`
  - API accepts natural-language region requests without uploaded bundles in `task_driven_auto`
  - resulting run inspection exposes AOI and source-resolution events

### Nairobi Validation Target

Nairobi is the required representative scenario for validation because it exercises:

- natural-language AOI resolution
- country-aware OSM acquisition for Kenya
- building-reference acquisition for an urban AOI
- road baseline clipping
- end-to-end runtime execution

The automated test path may stub network I/O, but there must also be a documented real-provider validation command for Nairobi in ops docs.

## Success Criteria

The feature is complete when all of the following are true:

- a natural-language request with no uploaded bundles can resolve an AOI and produce a run plan
- the plan and audit clearly show that AOI and source choices were selected through the existing `LLM + KG` planning flow
- input materialization is no longer limited to Burundi benchmark cases
- a Nairobi example can run through download, clip, and fusion without manual bundle preparation
- building runs fail explicitly when no non-empty reference source exists for the AOI
- all new and existing tests pass
