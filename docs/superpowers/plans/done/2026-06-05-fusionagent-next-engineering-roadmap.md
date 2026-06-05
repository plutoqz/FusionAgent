# FusionAgent Next Engineering Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining engineering gaps after the June 4 upgrades, with Scenario runtime reliability first, KG seed consolidation second, and validation/quality/operator visibility as follow-up tracks.

**Architecture:** Split the work into independent, testable tracks instead of one broad refactor. Track A hardens Scenario execution and recovery without changing planning semantics. Track B removes KG registration drift by making seed data loading explicit. Track C expands evidence quality through validation cases and topology metrics. Track D exposes the new runtime state in the existing operator frontend.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, GeoPandas/Shapely, pytest, React/Vite/TypeScript, existing `services/*`, `kg/*`, `scripts/run_engineering_validation.py`, and `frontend/src/*`.

---

## Phase 0: Documentation And Interface Discovery

**Purpose:** Make the next implementation round evidence-led. Do this before touching code for each track.

**Sources already verified:**
- `services/scenario_run_service.py`: scenario submission, child run creation, child polling, summary writing.
- `services/agent_run_service.py`: default eager execution, run checkpoint, recovery hooks, quality gate, durable learning writeback.
- `kg/repository.py`: durable learning time decay, condition key, automatic adjustment.
- `kg/seed.py`, `kg/seed_manifest.py`, `kg/inmemory_repository.py`: current Python seed source and manifest loader.
- `docs/superpowers/validation/engineering_validation_matrix.yaml`: current four-case flood-only engineering validation matrix.
- `frontend/src/app/router.tsx`: current operator pages.

**Allowed APIs and patterns:**
- Use `ScenarioRunService.create_scenario_run()` for synchronous tests and `submit_scenario_run()` for API/background behavior.
- Use existing `ScenarioRegistryService.record()` for scenario registry updates.
- Use existing `AgentRunService.create_run()` and `AgentRunService.get_run()` for child run lifecycle checks.
- Use existing `RunRecoveryExecutor` and `AgentRunService.resume_run_from_checkpoint()` for run-level recovery; do not invent a second run recovery path.
- Use `build_scenario_evidence_manifest()` after writing scenario evidence files.
- Use `QualityGateService.evaluate()` and `evaluate_vector_artifact()` for new quality metrics rather than adding a parallel evaluator.
- Use the current React API client in `frontend/src/lib/api/client.ts` for new frontend endpoints.

**Anti-pattern guards:**
- Do not describe Scenario as "fully parallel" until default eager mode is measured or changed.
- Do not remove `kg/seed.py` in the first KG consolidation task; keep compatibility until parity tests prove the manifest path is identical.
- Do not expand validation claims by documentation only; every new matrix claim needs a runner assertion or an explicit `expected_*` field.
- Do not build a new dashboard shell; extend the existing `RunsPage`, `ScenarioPage`, `KnowledgeGraphOverviewPage`, and API client.

---

## Track A: Scenario Runtime Reliability

**Priority:** P0

**Outcome:** Scenario runs can launch child runs concurrently under local eager mode, persist enough scenario state to survive process interruption, and resume incomplete scenarios without losing completed child evidence.

### Task A1: Add Local Child Concurrency To ScenarioRunService

**Files:**
- Modify: `services/scenario_run_service.py`
- Modify: `tests/test_scenario_run_service.py`
- Optional docs: `docs/no-ui-agent-operations.md`

- [x] **Step 1: Write a failing test for eager-mode child concurrency**

Add a test in `tests/test_scenario_run_service.py` using a fake `AgentRunService` whose `create_run()` blocks until all five disaster child calls have entered. The assertion should prove all child calls start before any child is allowed to return.

```python
def test_scenario_run_service_can_run_children_concurrently_in_local_eager_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOFUSION_SCENARIO_CHILD_MAX_WORKERS", "5")
    fake = _BlockingConcurrentAgentRunService(tmp_path, expected_children=5)
    service = ScenarioRunService(agent_run_service=fake)

    response = service.create_scenario_run(
        ScenarioRunRequest(
            scenario_name="Karachi flood",
            trigger_content="Karachi flood bounded validation",
            disaster_type="flood",
            spatial_extent="bbox(66.95,24.78,67.20,25.02)",
            output_root=str(tmp_path / "scenarios"),
        )
    )

    assert response.phase == ScenarioPhase.succeeded
    assert fake.max_simultaneous_create_run_calls == 5
    assert fake.created_task_kinds == ["building", "road", "water_polygon", "waterways", "poi"]
```

- [x] **Step 2: Run the failing test**

Run:

```powershell
py -3.13 -m pytest tests/test_scenario_run_service.py::test_scenario_run_service_can_run_children_concurrently_in_local_eager_mode -q
```

Expected before implementation: fail because `_BlockingConcurrentAgentRunService` is not present and child execution is not dispatched through a child pool.

- [x] **Step 3: Implement configurable child pool**

In `services/scenario_run_service.py`, keep `self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scenario-run")` for background scenario submissions, and add a separate child executor used only inside `_execute_scenario_run`.

Design:
- Add `_scenario_child_max_workers()` reading `GEOFUSION_SCENARIO_CHILD_MAX_WORKERS`.
- Default to `1` for compatibility, but document production value `5`.
- When the value is greater than `1`, submit `_run_child(output_dir, spec)` to a local `ThreadPoolExecutor`.
- Preserve output order by collecting futures in the original child spec order.

- [x] **Step 4: Run targeted scenario tests**

Run:

```powershell
py -3.13 -m pytest tests/test_scenario_run_service.py -q
```

Expected: all scenario tests pass.

- [x] **Step 5: Document the runtime mode distinction**

Update `docs/no-ui-agent-operations.md` with one short section:

```markdown
### Scenario child concurrency

`GEOFUSION_SCENARIO_CHILD_MAX_WORKERS` controls local child-run concurrency inside one Scenario run. This is separate from `GEOFUSION_CELERY_EAGER`: eager mode controls whether each Agent run executes in-process, while the Scenario child pool controls how many child Agent runs may be created concurrently by the Scenario service.
```

- [x] **Step 6: Run docs and scenario verification**

Run:

```powershell
py -3.13 -m pytest tests/test_scenario_run_service.py tests/test_no_ui_operations_docs.py -q
```

Expected: pass.

### Task A2: Persist Scenario Checkpoint State

**Files:**
- Create: `schemas/scenario_checkpoint.py`
- Create: `services/scenario_checkpoint_service.py`
- Modify: `services/scenario_run_service.py`
- Modify: `tests/test_scenario_run_service.py`

- [x] **Step 1: Add checkpoint schema tests**

Add tests proving checkpoint JSON includes:
- `scenario_id`
- `phase`
- `request`
- ordered `child_specs`
- ordered `child_runs`
- `started_at`
- `updated_at`
- `resume_count`

Expected file path for runtime output:

```text
<scenario_output_dir>/scenario_checkpoint.json
```

- [x] **Step 2: Implement checkpoint schema**

Create `schemas/scenario_checkpoint.py` with Pydantic models:
- `ScenarioCheckpointChildSpec`
- `ScenarioCheckpointChildRun`
- `ScenarioCheckpoint`

Keep field names aligned with existing `scenario_summary.json` where possible.

- [x] **Step 3: Implement checkpoint service**

Create `services/scenario_checkpoint_service.py` with:
- `write_scenario_checkpoint(path: Path, checkpoint: ScenarioCheckpoint) -> None`
- `load_scenario_checkpoint(path: Path) -> ScenarioCheckpoint`
- `checkpoint_path(output_dir: Path) -> Path`

Use atomic write by writing to `scenario_checkpoint.json.tmp` and replacing the final file.

- [x] **Step 4: Wire checkpoints into ScenarioRunService**

Write checkpoints:
- after request is persisted
- after child specs are compiled
- after each child run is started
- after child polling completes
- after final summary is written

- [x] **Step 5: Run checkpoint tests**

Run:

```powershell
py -3.13 -m pytest tests/test_scenario_run_service.py -q
```

Expected: pass, and scenario output directories created by tests contain `scenario_checkpoint.json`.

### Task A3: Add Scenario Resume API

**Files:**
- Modify: `services/scenario_run_service.py`
- Modify: `api/routers/scenario_runs.py`
- Modify: `schemas/scenario.py`
- Modify: `frontend/src/lib/api/client.ts`
- Test: `tests/test_api_scenario_runs.py`
- Test: `tests/test_scenario_run_service.py`

- [x] **Step 1: Define resume behavior**

Resume rules:
- terminal child run with an artifact stays terminal and is not recreated
- running child run is re-inspected through `AgentRunService.get_run()`
- missing/unstarted child run is launched
- failed child run is not retried unless request includes `retry_failed=true`
- scenario `resume_count` increments

- [x] **Step 2: Add service method**

Add:

```python
def resume_scenario_run(self, scenario_id: str, *, retry_failed: bool = False) -> ScenarioRunResponse:
    ...
```

The method loads the registry record, reads `scenario_checkpoint.json`, reconstructs the request and child specs, and then continues execution according to the resume rules.

- [x] **Step 3: Add API endpoint**

Add:

```python
@router.post("/scenario-runs/{scenario_id}/resume", response_model=ScenarioRunResponse)
async def resume_scenario_run(scenario_id: str, retry_failed: bool = False) -> ScenarioRunResponse:
    return scenario_run_service.resume_scenario_run(scenario_id, retry_failed=retry_failed)
```

- [x] **Step 4: Add tests**

Add tests for:
- completed child is not duplicated
- unstarted child is launched
- failed child is kept failed by default
- `retry_failed=true` relaunches failed child

- [x] **Step 5: Run verification**

Run:

```powershell
py -3.13 -m pytest tests/test_scenario_run_service.py tests/test_api_scenario_runs.py -q
```

Expected: pass.

---

## Track B: KG Seed Consolidation

**Priority:** P1

**Outcome:** KG seed data has an explicit source-of-truth path, import-time FusionCode merging is no longer hidden, and adding an algorithm no longer requires editing disconnected registries blindly.

### Task B1: Introduce Explicit Seed Provider

**Files:**
- Create: `kg/seed_provider.py`
- Modify: `kg/inmemory_repository.py`
- Modify: `tests/test_kg_seed_manifest.py`
- Modify: `tests/test_kg_seed_inventory.py`

- [x] **Step 1: Write parity tests**

Test that loading from default Python seed and checked-in manifest produce identical counts and stable IDs for:
- data types
- algorithms
- parameter specs
- workflow patterns
- data sources
- output schema policies

- [x] **Step 2: Implement `kg.seed_provider`**

Expose:

```python
def load_seed_data(seed_manifest_path: Path | None = None) -> dict[str, object]:
    ...
```

Rules:
- if `seed_manifest_path` is provided, load through `load_seed_manifest_payload`
- otherwise load from `kg.seed`
- no behavior change for existing repository constructors

- [x] **Step 3: Use provider in InMemoryKGRepository**

Replace direct default assignments in `InMemoryKGRepository.__init__()` with the provider payload while keeping constructor overrides working exactly as they do now.

- [x] **Step 4: Run KG tests**

Run:

```powershell
py -3.13 -m pytest tests/test_kg_seed_manifest.py tests/test_kg_seed_inventory.py tests/test_kg_repository.py -q
```

Expected: pass.

### Task B2: Make FusionCode Merge Auditable

**Files:**
- Modify: `kg/seed_manifest.py`
- Modify: `scripts/export_kg_seed_manifest.py`
- Modify: `tests/test_fusioncode_kg_metadata.py`
- Modify: `tests/test_kg_seed_manifest.py`

- [x] **Step 1: Add manifest provenance assertions**

Assert every FusionCode algorithm in the generated manifest has:
- `metadata.algorithm_family`
- `metadata.handler_name`
- `tool_ref`
- input/output type parity with `agent/tooling.py`

- [x] **Step 2: Add seed provenance metadata**

Manifest metadata should include:

```json
{
  "source_modules": ["kg.seed", "fusion_algorithms.registry_metadata"],
  "schema_version": "1.0.0"
}
```

- [x] **Step 3: Add drift check**

Extend `scripts/export_kg_seed_manifest.py --check` to fail when manifest payload differs from current seed modules, ignoring only `generated_at`.

- [x] **Step 4: Run drift verification**

Run:

```powershell
py -3.13 scripts/export_kg_seed_manifest.py --check
py -3.13 -m pytest tests/test_fusioncode_kg_metadata.py tests/test_kg_seed_manifest.py -q
```

Expected: pass.

### Task B3: Decide YAML Migration After Provider Stabilizes

**Files:**
- Create a follow-up plan only after B1-B2 pass.

Decision criteria:
- If the manifest is primarily machine-generated, keep JSON as the checked parity artifact and create smaller YAML source fragments later.
- If humans need to add algorithms frequently, create YAML fragments under `kg/seeds/` grouped by `data_types`, `algorithms`, `workflow_patterns`, and `data_sources`.
- Do not delete `kg/seed.py` until both InMemory and Neo4j bootstrap tests pass from the external source.

---

## Track C: Validation And Quality Depth

**Priority:** P1

**Outcome:** Engineering validation stops being flood-only smoke coverage, and Quality Gate starts measuring topology defects relevant to roads, waterways, and polygons.

### Task C1: Expand Engineering Validation Matrix

**Files:**
- Modify: `docs/superpowers/validation/engineering_validation_matrix.yaml`
- Modify: `schemas/engineering_validation.py`
- Modify: `scripts/run_engineering_validation.py`
- Modify: `tests/test_engineering_validation_matrix.py`
- Modify: `tests/test_engineering_validation_runner.py`

- [x] **Step 1: Add case fields**

Add optional fields:
- `expected_task_kinds`
- `expected_failed_children_max`
- `expected_quality_checks`
- `degradation_mode`

- [x] **Step 2: Add cases**

Move from 4 to at least 12 cases:
- 4 flood cases kept
- 2 earthquake cases
- 1 typhoon case
- 2 task-kind focused cases
- 3 degradation cases: missing reference source, single-source fallback, bounded large AOI timeout/retry evidence

- [x] **Step 3: Strengthen runner assertions**

`evaluate_case_summary()` should assert expected task kinds and quality checks when those fields are present.

- [x] **Step 4: Run validation tests**

Run:

```powershell
py -3.13 -m pytest tests/test_engineering_validation_matrix.py tests/test_engineering_validation_runner.py -q
```

Expected: pass.

### Task C2: Add Topology Quality Metrics

**Files:**
- Modify: `services/artifact_evaluation_service.py`
- Modify: `services/quality_policy_service.py`
- Modify: `tests/test_artifact_evaluation_service.py`
- Modify: `tests/test_quality_gate_service.py`

- [x] **Step 1: Add metric tests**

Add tests for:
- `zero_length_geometry_count`
- `self_intersection_count` for polygons
- `sliver_polygon_count` with a configurable area threshold
- `dangle_endpoint_count` for line outputs

- [x] **Step 2: Implement metrics in `evaluate_vector_artifact()`**

Keep metrics deterministic and cheap:
- project geographic CRS to EPSG:3857 before area/length thresholds
- count zero-length line geometries
- count invalid polygon geometries with self-intersection reason when Shapely exposes it
- count polygons below sliver area threshold
- count line endpoints that appear only once for dangle endpoint count

- [x] **Step 3: Add policy checks**

Add hard or soft checks by task kind:
- roads/waterways: `zero_length_geometry_count == 0`, `dangle_endpoint_count <= threshold`
- buildings/water polygons: `self_intersection_count == 0`, `sliver_polygon_count <= threshold`

- [x] **Step 4: Run quality tests**

Run:

```powershell
py -3.13 -m pytest tests/test_artifact_evaluation_service.py tests/test_quality_gate_service.py tests/test_quality_policy_service.py -q
```

Expected: pass.

---

## Track D: Operator Visibility

**Priority:** P2

**Outcome:** The existing frontend shows scenario checkpoint/resume state, validation sessions, and quality trends without creating a separate dashboard shell.

### Task D1: Add Scenario Recovery Controls

**Files:**
- Modify: `frontend/src/lib/api/client.ts`
- Modify: `frontend/src/lib/api/types.ts`
- Modify: `frontend/src/features/scenarios/ScenarioPage.tsx`
- Modify: `frontend/src/features/scenarios/ScenarioPage.test.tsx`

- [x] **Step 1: Add API client method**

Add:

```ts
export function resumeScenarioRun(scenarioId: string, retryFailed = false) {
  const params = new URLSearchParams();
  if (retryFailed) params.set("retry_failed", "true");
  const query = params.toString();
  return request<ScenarioRunResponse>(
    `/api/v2/scenario-runs/${scenarioId}/resume${query ? `?${query}` : ""}`,
    { method: "POST" },
  );
}
```

- [x] **Step 2: Add UI action**

On `ScenarioPage`, show a resume action for `running`, `partial`, or stale scenarios once backend exposes checkpoint metadata.

- [x] **Step 3: Run frontend tests**

Run:

```powershell
Set-Location frontend
npm test -- --run ScenarioPage
```

Expected: pass.

### Task D2: Add Validation Session Read Model

**Files:**
- [x] Create or modify backend read model service after Track C creates stable output files.
- [x] Modify: `frontend/src/app/router.tsx`
- [x] Create: `frontend/src/features/validation/ValidationSessionsPage.tsx`
- [x] Create: `frontend/src/features/validation/ValidationSessionsPage.test.tsx`

This task should start only after Track C1 lands, because the frontend should render the final `validation_summary.json` contract instead of guessing.

---

## Recommended Execution Order

1. **A1 child concurrency**: smallest runtime win, validates the corrected understanding of eager vs non-eager behavior.
2. **A2 scenario checkpoint**: creates the state contract needed for recovery and UI.
3. **A3 scenario resume API**: closes the biggest reliability gap.
4. **B1 seed provider**: prepares KG consolidation without risky deletion.
5. **B2 FusionCode drift checks**: turns hidden merge debt into explicit CI evidence.
6. **C1 validation matrix expansion**: makes engineering claims harder to overstate.
7. **C2 topology metrics**: raises output quality confidence.
8. **D1-D2 frontend visibility**: expose backend reliability features after contracts stabilize.

## What Not To Do In The Next Round

- Do not start by replacing the agent framework.
- Do not remove `kg/seed.py` before parity and bootstrap evidence exist.
- Do not make the validation matrix claim full production coverage while `expected_min_succeeded_children` remains low.
- Do not build a new frontend dashboard app; extend the existing operator pages.
- Do not mix topology metrics and golden truth precision/recall in the same first quality task. Golden truth needs curated datasets and should follow after topology metrics are stable.

## Final Verification Gate

Before marking this roadmap complete, run:

```powershell
py -3.13 -m pytest tests/test_scenario_run_service.py tests/test_api_scenario_runs.py -q
py -3.13 -m pytest tests/test_kg_seed_manifest.py tests/test_kg_seed_inventory.py tests/test_fusioncode_kg_metadata.py -q
py -3.13 -m pytest tests/test_engineering_validation_matrix.py tests/test_engineering_validation_runner.py -q
py -3.13 -m pytest tests/test_artifact_evaluation_service.py tests/test_quality_gate_service.py tests/test_quality_policy_service.py -q
```

For frontend work after Track D:

```powershell
Set-Location frontend
npm test -- --run
```

Expected: all targeted tests pass. Full test suite can be run after the targeted tracks are green.
