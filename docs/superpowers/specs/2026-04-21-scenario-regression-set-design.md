# Scenario Regression Set Expansion Design

## Purpose

Expand the scenario evaluation manifest from a single demo case into a small capability-oriented regression set that covers `building`, `road`, `water`, and bounded `poi`, while still allowing a small amount of realistic `partial` behavior.

This design keeps the current scenario API contract intact. It does not introduce provider steering or new scenario runtime control fields. Instead, it upgrades the manifest and harness so regression success depends on both:

- expected scenario phase
- required scenario evidence appearing in `scenario_summary.json`

## Goals

- Extend the checked-in scenario manifest from 1 case to 5 cases.
- Cover four runtime job families: `building`, `road`, `water`, and `poi`.
- Keep one mixed multi-task case for fallback and partial-success regression.
- Allow selected cases to pass with `partial`, but only when capability evidence proves the run still exercised the intended runtime path.
- Make harness failures actionable by reporting which capability checks failed.

## Non-Goals

- No new scenario API request fields.
- No provider pinning or source-id steering inside scenario manifests.
- No dashboard or operator UI work in this slice.
- No new runtime semantics for `ScenarioPhase`.
- No attempt to force all cases to become `succeeded`.

## Design Summary

The manifest model will gain a typed `capability_checks` section per case. The harness will continue posting `ScenarioRunRequest` objects to `/api/v2/scenario-runs`, but after receiving a successful HTTP response it will load the generated `scenario_summary.json` and validate capability evidence.

Each case will pass only if:

1. `response.phase` is included in `expected_phase`
2. `capability_checks` are satisfied against `scenario_summary.json`

This turns the manifest into a real capability regression set instead of a pure phase smoke test.

## Manifest Model Changes

Add a new schema:

```python
class ScenarioCapabilityChecks(BaseModel):
    required_job_types: List[JobType] = Field(default_factory=list)
    min_succeeded_children: int = 0
    require_aoi_resolved: bool = False
    require_task_inputs_resolved: bool = False
    require_source_coverage: bool = False
```

Extend `ScenarioEvalCase` with:

```python
capability_checks: ScenarioCapabilityChecks = Field(default_factory=ScenarioCapabilityChecks)
```

Rationale:

- `required_job_types` verifies the scenario actually spawned the intended child jobs.
- `min_succeeded_children` prevents single-task `partial` cases from being counted as successful when no child run actually succeeded.
- `require_aoi_resolved` proves natural-language AOI resolution happened.
- `require_task_inputs_resolved` proves task-driven acquisition happened.
- `require_source_coverage` proves source coverage evidence was written.

## Regression Set Composition

The checked-in manifest will be expanded to five cases.

### 1. `parakou_earthquake_building_road`

Role:
- mixed baseline
- preserves current paper/demo scenario

Config:
- `job_types=["building", "road"]`
- `expected_phase=["succeeded", "partial"]`
- `capability_checks.required_job_types=["building", "road"]`
- `capability_checks.min_succeeded_children=1`
- `capability_checks.require_task_inputs_resolved=true`
- `capability_checks.require_source_coverage=true`

### 2. `nairobi_flood_road_single`

Role:
- road single-task capability coverage

Config:
- `job_types=["road"]`
- `expected_phase=["succeeded", "partial"]`
- `capability_checks.required_job_types=["road"]`
- `capability_checks.min_succeeded_children=1`
- `capability_checks.require_aoi_resolved=true`
- `capability_checks.require_task_inputs_resolved=true`
- `capability_checks.require_source_coverage=true`

### 3. `nairobi_flood_water_single`

Role:
- water single-task capability coverage

Config:
- `job_types=["water"]`
- `expected_phase=["succeeded", "partial"]`
- `capability_checks.required_job_types=["water"]`
- `capability_checks.min_succeeded_children=1`
- `capability_checks.require_aoi_resolved=true`
- `capability_checks.require_task_inputs_resolved=true`
- `capability_checks.require_source_coverage=true`

### 4. `nairobi_poi_single`

Role:
- bounded POI single-task capability coverage

Config:
- `job_types=["poi"]`
- `expected_phase=["succeeded", "partial"]`
- `capability_checks.required_job_types=["poi"]`
- `capability_checks.min_succeeded_children=1`
- `capability_checks.require_aoi_resolved=true`
- `capability_checks.require_task_inputs_resolved=true`
- `capability_checks.require_source_coverage=true`

### 5. `gitega_building_single`

Role:
- building single-task coverage
- more acquisition-oriented representative case

Config:
- `job_types=["building"]`
- `expected_phase=["succeeded", "partial"]`
- `capability_checks.required_job_types=["building"]`
- `capability_checks.min_succeeded_children=1`
- `capability_checks.require_aoi_resolved=true`
- `capability_checks.require_task_inputs_resolved=true`
- `capability_checks.require_source_coverage=true`

## Harness Validation Rules

The harness will keep using the current API orchestration path:

- build request from manifest case
- call `POST /api/v2/scenario-runs`
- load `scenario_summary.json` from `response.output_dir`

Then it will derive an observed evidence view:

- `observed_job_types` from `summary["child_runs"][*]["job_type"]`
- `succeeded_child_count` from `summary["child_runs"][*]["phase"] == "succeeded"`
- `workflow_step_names` from `summary["workflow_traces"][*]["steps"][*]["step_name"]`
- `source_coverage_count` from `len(summary["source_coverage"])`

Capability checks will map to evidence as follows:

- `required_job_types`: every requested job type must appear in `observed_job_types`
- `min_succeeded_children`: `succeeded_child_count >= min_succeeded_children`
- `require_aoi_resolved`: `aoi_resolved` must appear in workflow trace steps
- `require_task_inputs_resolved`: `task_inputs_resolved` must appear in workflow trace steps
- `require_source_coverage`: `source_coverage_count > 0`

If the phase passes but one or more capability checks fail, the case result is failed.

## Harness Result Model Changes

Extend `ScenarioHarnessCaseResult` with:

```python
summary_path: Optional[str] = None
capability_checks_passed: bool = False
capability_failures: List[str] = Field(default_factory=list)
observed: Dict[str, Any] = Field(default_factory=dict)
```

This allows harness output to explain failures precisely, for example:

- missing `aoi_resolved`
- missing `task_inputs_resolved`
- expected `poi` child job not found
- no child run succeeded

## Error Handling

Use conservative failure semantics:

- API error: fail case
- missing `scenario_summary.json`: fail case
- malformed or incomplete summary: fail case
- phase passes but capability checks fail: fail case

No fallback logic will be added in the harness. The harness is a verifier, not a repair layer.

## Testing Strategy

Use TDD in three steps.

### Manifest Schema Tests

Update `tests/test_scenario_manifest_service.py` to prove:

- `capability_checks` load correctly from JSON
- required job types and boolean flags survive parsing

### Harness Capability Tests

Update `tests/test_scenario_eval_harness.py` to cover:

- one fake summary where phase and capability checks both pass
- one fake summary where phase passes but capability evidence is missing, causing failure

### Real Harness Check

Run the expanded manifest against a local `memory + mock + eager` API runtime and write:

- `tmp/eval/scenario-harness-summary.json`
- refreshed `docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.json`
- refreshed `docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.md`

## File Changes

Modify:

- `schemas/scenario_manifest.py`
- `scripts/scenario_eval_harness.py`
- `tests/test_scenario_manifest_service.py`
- `tests/test_scenario_eval_harness.py`
- `docs/superpowers/specs/2026-04-21-scenario-eval-manifest.json`
- `docs/v2-operations.md` if command examples need updated wording

Refresh after real run:

- `tmp/eval/scenario-harness-summary.json`
- `docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.json`
- `docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.md`

## Verification Contract

Focused verification:

```powershell
python -m pytest -q tests/test_scenario_manifest_service.py tests/test_scenario_eval_harness.py
```

Real harness verification:

```powershell
python scripts/scenario_eval_harness.py `
  --manifest docs/superpowers/specs/2026-04-21-scenario-eval-manifest.json `
  --base-url http://127.0.0.1:8000 `
  --output-root E:\fyx\data\fusionagentTEST `
  --output-json tmp/eval/scenario-harness-summary.json `
  --timeout 1200
```

## Scope Check

This design remains a single implementation slice:

- one manifest contract extension
- one harness verification upgrade
- one checked-in regression-set expansion

It does not require scenario runtime redesign, provider steering, or UI work, so it is appropriately scoped for one implementation plan.
