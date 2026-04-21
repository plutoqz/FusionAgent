# Scenario Regression Set Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the scenario evaluation manifest into a capability-oriented regression set and make the harness fail when expected scenario evidence is missing even if the phase still matches.

**Architecture:** Add a typed `capability_checks` contract to scenario manifest cases and extend the harness to read `scenario_summary.json` after each API run. Keep the scenario runtime contract unchanged; capability coverage is enforced entirely at the manifest and harness layers. Refresh the checked-in manifest, real harness summary, and frozen evidence after the code path is in place.

**Tech Stack:** Python 3.9+, Pydantic v2, FastAPI HTTP harness client, pytest, JSON evidence files, existing `/api/v2/scenario-runs` pipeline.

---

## File Map

- Modify: `schemas/scenario_manifest.py`
  Responsibility: typed capability-check schema and richer harness result schema.
- Modify: `scripts/scenario_eval_harness.py`
  Responsibility: load `scenario_summary.json`, compute observed evidence, apply capability checks, and emit actionable failures.
- Modify: `tests/test_scenario_manifest_service.py`
  Responsibility: prove `capability_checks` load and survive request conversion.
- Modify: `tests/test_scenario_eval_harness.py`
  Responsibility: prove harness passes when capability evidence is present and fails when evidence is missing.
- Modify: `docs/superpowers/specs/2026-04-21-scenario-eval-manifest.json`
  Responsibility: expand checked-in regression set from 1 case to 5 cases with capability coverage rules.
- Modify: `docs/v2-operations.md`
  Responsibility: document that scenario regression set now validates capability evidence in addition to phase.
- Refresh: `tmp/eval/scenario-harness-summary.json`
  Responsibility: real output from expanded scenario harness run.
- Refresh: `docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.json`
  Responsibility: frozen evidence for the latest real scenario run.
- Refresh: `docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.md`
  Responsibility: human-readable frozen evidence summary.

## Task 1: Extend Manifest Schema For Capability Checks

**Files:**
- Modify: `schemas/scenario_manifest.py`
- Modify: `tests/test_scenario_manifest_service.py`

- [ ] **Step 1: Write the failing manifest schema test**

Add a new test in `tests/test_scenario_manifest_service.py` that loads a manifest case with capability checks:

```python
def test_manifest_capability_checks_load(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_id": "scenario.paper.demo.v1",
                "cases": [
                    {
                        "case_id": "nairobi_flood_road_single",
                        "scenario_name": "Nairobi flood road",
                        "trigger_content": "fuse road data for Nairobi, Kenya after a flood",
                        "job_types": ["road"],
                        "expected_phase": ["succeeded", "partial"],
                        "capability_checks": {
                            "required_job_types": ["road"],
                            "min_succeeded_children": 1,
                            "require_aoi_resolved": True,
                            "require_task_inputs_resolved": True,
                            "require_source_coverage": True,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = load_scenario_manifest(manifest_path)

    assert manifest.cases[0].capability_checks.required_job_types == [JobType.road]
    assert manifest.cases[0].capability_checks.min_succeeded_children == 1
    assert manifest.cases[0].capability_checks.require_aoi_resolved is True
```

- [ ] **Step 2: Run the focused manifest tests and watch them fail**

Run:

```powershell
python -m pytest -q tests/test_scenario_manifest_service.py
```

Expected:

```text
AttributeError or ValidationError referencing missing capability_checks support
```

- [ ] **Step 3: Implement the minimal schema change**

Update `schemas/scenario_manifest.py` with:

```python
class ScenarioCapabilityChecks(BaseModel):
    required_job_types: List[JobType] = Field(default_factory=list)
    min_succeeded_children: int = 0
    require_aoi_resolved: bool = False
    require_task_inputs_resolved: bool = False
    require_source_coverage: bool = False
```

and extend:

```python
class ScenarioEvalCase(BaseModel):
    ...
    capability_checks: ScenarioCapabilityChecks = Field(default_factory=ScenarioCapabilityChecks)
```

- [ ] **Step 4: Run the focused manifest tests and confirm green**

Run:

```powershell
python -m pytest -q tests/test_scenario_manifest_service.py
```

Expected:

```text
all manifest service tests pass
```

## Task 2: Make Harness Validate Capability Evidence

**Files:**
- Modify: `scripts/scenario_eval_harness.py`
- Modify: `tests/test_scenario_eval_harness.py`
- Modify: `schemas/scenario_manifest.py`

- [ ] **Step 1: Write the failing harness capability tests**

Add two tests in `tests/test_scenario_eval_harness.py`.

Passing case:

```python
def test_run_manifest_cases_passes_when_summary_satisfies_capability_checks(tmp_path: Path):
    ...
    assert summary.passed_cases == 1
    assert summary.results[0].capability_checks_passed is True
    assert summary.results[0].observed["succeeded_child_count"] == 1
```

Failing case:

```python
def test_run_manifest_cases_fails_when_aoi_evidence_is_missing(tmp_path: Path):
    ...
    assert summary.failed_cases == 1
    assert summary.results[0].passed is False
    assert "require_aoi_resolved" in summary.results[0].capability_failures[0]
```

Use a fake client that returns `ScenarioRunResponse(output_dir=<tmp scenario dir>)`, and write `scenario_summary.json` fixtures under that directory instead of mocking harness internals.

- [ ] **Step 2: Run the focused harness tests and watch them fail**

Run:

```powershell
python -m pytest -q tests/test_scenario_eval_harness.py
```

Expected:

```text
FAIL because ScenarioHarnessCaseResult has no capability fields and harness does not read scenario_summary.json
```

- [ ] **Step 3: Extend harness result schema**

Add to `schemas/scenario_manifest.py`:

```python
class ScenarioHarnessCaseResult(BaseModel):
    ...
    summary_path: Optional[str] = None
    capability_checks_passed: bool = False
    capability_failures: List[str] = Field(default_factory=list)
    observed: Dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 4: Implement capability-aware harness evaluation**

In `scripts/scenario_eval_harness.py`, add helpers equivalent to:

```python
def _load_summary(output_dir: str) -> dict[str, Any]:
    return json.loads((Path(output_dir) / "scenario_summary.json").read_text(encoding="utf-8"))


def _build_observed_evidence(summary: dict[str, Any]) -> dict[str, Any]:
    child_runs = summary.get("child_runs") or []
    workflow_traces = summary.get("workflow_traces") or []
    step_names = []
    for trace in workflow_traces:
        for step in trace.get("steps", []):
            name = str(step.get("step_name") or "").strip()
            if name and name not in step_names:
                step_names.append(name)
    return {
        "observed_job_types": [item.get("job_type") for item in child_runs if item.get("job_type")],
        "succeeded_child_count": sum(1 for item in child_runs if item.get("phase") == "succeeded"),
        "workflow_step_names": step_names,
        "source_coverage_count": len(summary.get("source_coverage") or []),
    }
```

and evaluate:

```python
def _capability_failures(case, observed: dict[str, Any]) -> list[str]:
    failures = []
    ...
    return failures
```

Use final pass logic:

```python
phase_passed = phase in case.expected_phase
capability_failures = _capability_failures(case, observed)
passed = phase_passed and not capability_failures
```

- [ ] **Step 5: Run the focused harness tests and confirm green**

Run:

```powershell
python -m pytest -q tests/test_scenario_eval_harness.py tests/test_scenario_manifest_service.py
```

Expected:

```text
all focused harness and manifest tests pass
```

## Task 3: Expand The Checked-In Regression Set

**Files:**
- Modify: `docs/superpowers/specs/2026-04-21-scenario-eval-manifest.json`
- Modify: `docs/v2-operations.md`

- [ ] **Step 1: Replace the single-case manifest with the 5-case regression set**

Update `docs/superpowers/specs/2026-04-21-scenario-eval-manifest.json` to include:

- `parakou_earthquake_building_road`
- `nairobi_flood_road_single`
- `nairobi_flood_water_single`
- `nairobi_poi_single`
- `gitega_building_single`

Each case must include `capability_checks`. Use the following shape:

```json
"capability_checks": {
  "required_job_types": ["road"],
  "min_succeeded_children": 1,
  "require_aoi_resolved": true,
  "require_task_inputs_resolved": true,
  "require_source_coverage": true
}
```

- [ ] **Step 2: Document the new regression semantics**

Add one short paragraph to `docs/v2-operations.md` near the scenario harness section stating that the checked-in scenario regression set now validates capability evidence such as AOI resolution, task-input resolution, source coverage, and minimum successful child runs in addition to the top-level scenario phase.

- [ ] **Step 3: Run the focused tests again**

Run:

```powershell
python -m pytest -q tests/test_scenario_manifest_service.py tests/test_scenario_eval_harness.py
```

Expected:

```text
all focused tests pass after manifest expansion
```

## Task 4: Run Real Harness And Refresh Frozen Evidence

**Files:**
- Refresh: `tmp/eval/scenario-harness-summary.json`
- Refresh: `docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.json`
- Refresh: `docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.md`

- [ ] **Step 1: Start a temporary local fast-mode API if port 8000 is not already serving `memory/mock/eager`**

Use:

```powershell
cmd /c "set GEOFUSION_KG_BACKEND=memory&& set GEOFUSION_LLM_PROVIDER=mock&& set GEOFUSION_CELERY_EAGER=1&& set GEOFUSION_API_PORT=8000&& python -m uvicorn main:app --host 127.0.0.1 --port 8000"
```

Verify:

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8000/api/v2/runtime -UseBasicParsing
```

Expected payload contains:

```json
{"kg_backend":"memory","llm_provider":"mock","celery_eager":"1","api_port":"8000"}
```

- [ ] **Step 2: Run the expanded real harness**

Run:

```powershell
python scripts/scenario_eval_harness.py `
  --manifest docs/superpowers/specs/2026-04-21-scenario-eval-manifest.json `
  --base-url http://127.0.0.1:8000 `
  --output-root E:\fyx\data\fusionagentTEST `
  --output-json tmp/eval/scenario-harness-summary.json `
  --timeout 1200
```

Expected:

```text
exit code 0 only if every case satisfies both phase and capability checks
```

- [ ] **Step 3: Freeze the latest real scenario evidence**

Run:

```powershell
$summary = Get-Content tmp/eval/scenario-harness-summary.json -Raw | ConvertFrom-Json
$scenarioDir = $summary.results[0].output_dir
python scripts/freeze_scenario_evidence.py `
  --scenario-dir $scenarioDir `
  --output-json docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.json `
  --output-markdown docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.md
```

Expected:

```text
freeze JSON and Markdown reference the latest scenario id and evidence counts
```

- [ ] **Step 4: Stop the temporary API process if you started it for this task**

Use the captured PID or stop the specific `python -m uvicorn main:app --host 127.0.0.1 --port 8000` process.

## Self-Review

- Spec coverage: This plan covers typed capability checks, harness capability validation, manifest expansion, doc update, real harness execution, and frozen evidence refresh.
- Placeholder scan: No step relies on TBD behavior; each verification command and expected outcome is explicit.
- Type consistency: `ScenarioCapabilityChecks`, `capability_checks_passed`, `capability_failures`, and `observed` are used consistently across schema, harness, and tests.
