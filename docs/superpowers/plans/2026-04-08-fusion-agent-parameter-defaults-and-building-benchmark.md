# FusionAgent Parameter Defaults and Building Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make KG parameter specs automatically bind into executable plan tasks, surface effective parameters in runtime artifacts, and prepare the first real-data building benchmark to run cleanly in a fresh execution thread.

**Architecture:** Add a small deterministic parameter-binding module between planner output and validator/executor. It should merge KG defaults with any explicit task parameters without changing the executor contract. Then expose the effective parameters through saved plans and run audit, and harden the building benchmark path so a fresh thread can execute the first real-data case without rediscovering the current repo state.

**Tech Stack:** Python 3.9+, Pydantic, pytest, FastAPI, in-memory/Neo4j KG repository, existing `scripts/eval_harness.py`, existing `tests/golden_cases` and real-data manifest

---

## File Structure

### New Files

- `E:/vscode/fusionAgent/agent/parameter_binding.py`
- `E:/vscode/fusionAgent/tests/test_parameter_default_binding.py`

### Existing Files to Modify

- `E:/vscode/fusionAgent/agent/planner.py`
- `E:/vscode/fusionAgent/services/agent_run_service.py`
- `E:/vscode/fusionAgent/scripts/eval_harness.py`
- `E:/vscode/fusionAgent/tests/test_planner_context.py`
- `E:/vscode/fusionAgent/tests/test_agent_run_service_enhancements.py`
- `E:/vscode/fusionAgent/tests/test_eval_harness.py`
- `E:/vscode/fusionAgent/tests/test_api_v2_integration.py`

### Responsibilities

- `agent/parameter_binding.py`
  - Single place to compute effective task parameters from KG specs plus explicit task overrides.
  - No I/O, no planner prompt logic, no executor logic.
- `agent/planner.py`
  - Call the binder for both initial planning and replanning.
  - Keep parameter injection deterministic and independent of LLM output quirks.
- `services/agent_run_service.py`
  - Persist parameterized plans as the run truth and include enough audit context to inspect what was actually bound.
- `scripts/eval_harness.py`
  - Add a fast failure mode for unavailable local API during manifest-backed agent runs so building benchmark threads fail clearly rather than timing out blindly.
- tests
  - Prove default injection, explicit override, planner integration, audit persistence, and benchmark preflight behavior.

### Global Test Environment

```powershell
$env:GEOFUSION_KG_BACKEND = "memory"
$env:GEOFUSION_LLM_PROVIDER = "mock"
$env:GEOFUSION_CELERY_EAGER = "1"
```

## Task 1: Add Deterministic Parameter Binding Utility

**Files:**
- Create: `E:/vscode/fusionAgent/agent/parameter_binding.py`
- Test: `E:/vscode/fusionAgent/tests/test_parameter_default_binding.py`

- [x] **Step 1: Write the failing test**

```python
from agent.parameter_binding import bind_plan_parameters
from kg.inmemory_repository import InMemoryKGRepository
from schemas.agent import WorkflowPlan


def test_bind_plan_parameters_injects_kg_defaults_and_preserves_explicit_override() -> None:
    repo = InMemoryKGRepository()
    plan = WorkflowPlan.model_validate(
        {
            "workflow_id": "wf_bind_defaults",
            "trigger": {"type": "user_query", "content": "building"},
            "context": {},
            "tasks": [
                {
                    "step": 1,
                    "name": "building_fusion",
                    "description": "execute building fusion",
                    "algorithm_id": "algo.fusion.building.v1",
                    "input": {
                        "data_type_id": "dt.building.bundle",
                        "data_source_id": "upload.bundle",
                        "parameters": {
                            "match_similarity_threshold": 0.55
                        },
                    },
                    "output": {"data_type_id": "dt.building.fused", "description": "out"},
                    "depends_on": [],
                    "is_transform": False,
                    "kg_validated": True,
                    "alternatives": [],
                },
                {
                    "step": 2,
                    "name": "road_fusion_safe",
                    "description": "execute road fusion",
                    "algorithm_id": "algo.fusion.road.safe",
                    "input": {
                        "data_type_id": "dt.road.bundle",
                        "data_source_id": "upload.bundle",
                        "parameters": {},
                    },
                    "output": {"data_type_id": "dt.road.fused", "description": "out"},
                    "depends_on": [],
                    "is_transform": False,
                    "kg_validated": True,
                    "alternatives": [],
                },
            ],
            "expected_output": "out",
        }
    )

    bound = bind_plan_parameters(plan, repo)

    building_params = bound.tasks[0].input.parameters
    road_params = bound.tasks[1].input.parameters

    assert building_params["match_similarity_threshold"] == 0.55
    assert building_params["one_to_one_min_overlap_similarity"] == 0.3
    assert road_params["max_hausdorff_m"] == 10.0
    assert road_params["dedupe_buffer_m"] == 12.0
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_parameter_default_binding.py::test_bind_plan_parameters_injects_kg_defaults_and_preserves_explicit_override -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'agent.parameter_binding'`

- [x] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

from typing import Dict

from kg.repository import KGRepository
from schemas.agent import WorkflowPlan


def bind_plan_parameters(plan: WorkflowPlan, kg_repo: KGRepository) -> WorkflowPlan:
    for task in plan.tasks:
        if task.is_transform:
            continue
        specs = kg_repo.get_parameter_specs(task.algorithm_id)
        defaults: Dict[str, object] = {}
        for spec in specs:
            defaults[spec.key] = spec.default
        defaults.update(task.input.parameters or {})
        task.input.parameters = defaults
    return plan
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_parameter_default_binding.py::test_bind_plan_parameters_injects_kg_defaults_and_preserves_explicit_override -q`

Expected: PASS

- [x] **Step 5: Commit**

```bash
git add agent/parameter_binding.py tests/test_parameter_default_binding.py
git commit -m "feat: add deterministic plan parameter binding"
```

## Task 2: Wire Parameter Binding Into Planner Create/Replan Paths

**Files:**
- Modify: `E:/vscode/fusionAgent/agent/planner.py`
- Modify: `E:/vscode/fusionAgent/tests/test_planner_context.py`
- Test: `E:/vscode/fusionAgent/tests/test_parameter_default_binding.py`

- [x] **Step 1: Write the failing integration test**

Append to `E:/vscode/fusionAgent/tests/test_planner_context.py`:

```python
def test_planner_injects_kg_parameter_defaults_into_task_inputs() -> None:
    provider = CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)
    trigger = RunTrigger(type=RunTriggerType.user_query, content="fuse roads")

    plan = planner.create_plan(run_id="run-param-defaults", job_type=JobType.road, trigger=trigger)

    assert plan.tasks
    params = plan.tasks[0].input.parameters
    assert params["angle_threshold_deg"] == 135
    assert "dedupe_buffer_m" in params
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_planner_context.py::test_planner_injects_kg_parameter_defaults_into_task_inputs -q`

Expected: FAIL because planner still leaves `parameters` empty

- [x] **Step 3: Write minimal implementation**

In `E:/vscode/fusionAgent/agent/planner.py` add:

```python
from agent.parameter_binding import bind_plan_parameters
```

Then update both `create_plan(...)` and `replan_from_error(...)`:

```python
plan = self._finalize_plan(plan)
plan = bind_plan_parameters(plan, self.kg_repo)
```

and:

```python
plan = self._finalize_plan(plan, fallback_workflow_id=previous_plan.workflow_id)
plan = bind_plan_parameters(plan, self.kg_repo)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_parameter_default_binding.py tests/test_planner_context.py -q`

Expected: PASS

- [x] **Step 5: Commit**

```bash
git add agent/planner.py tests/test_planner_context.py tests/test_parameter_default_binding.py
git commit -m "feat: inject kg defaults during plan creation"
```

## Task 3: Persist Effective Parameters In Saved Run Truth

**Files:**
- Modify: `E:/vscode/fusionAgent/services/agent_run_service.py`
- Modify: `E:/vscode/fusionAgent/tests/test_agent_run_service_enhancements.py`

- [x] **Step 1: Write the failing test**

Append to `E:/vscode/fusionAgent/tests/test_agent_run_service_enhancements.py`:

```python
def test_saved_plan_contains_bound_effective_parameters(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    initial_plan = _build_plan(workflow_id="wf_initial", revision=1)
    initial_plan.tasks[0].input.parameters = {
        "match_similarity_threshold": 0.52,
        "one_to_one_min_overlap_similarity": 0.31,
    }

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: tmp_path / "osm.shp")
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: initial_plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: tmp_path / "fused.shp")
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: tmp_path / "artifact.zip")

    (tmp_path / "osm.shp").write_text("x", encoding="utf-8")
    (tmp_path / "ref.shp").write_text("x", encoding="utf-8")
    (tmp_path / "fused.shp").write_text("x", encoding="utf-8")
    (tmp_path / "artifact.zip").write_bytes(b"zip")

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
            target_crs="EPSG:32643",
            field_mapping={},
            debug=False,
        ),
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(tmp_path / "osm.zip"),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(tmp_path / "ref.zip"),
    )

    saved = service.get_plan(status.run_id)
    assert saved is not None
    assert saved.tasks[0].input.parameters["match_similarity_threshold"] == 0.52
    assert saved.tasks[0].input.parameters["one_to_one_min_overlap_similarity"] == 0.31
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_agent_run_service_enhancements.py::test_saved_plan_contains_bound_effective_parameters -q`

Expected: FAIL if saved plan loses or mutates effective parameters incorrectly

- [x] **Step 3: Write minimal implementation**

If the test fails because observability is insufficient, add a compact audit payload in `run_planning_stage(...)`:

```python
event_details["effective_parameters"] = {
    task.step: dict(task.input.parameters or {})
    for task in plan.tasks
    if not task.is_transform
}
```

Do not add a second source of truth. The saved `plan.json` remains canonical; audit only mirrors a summary.

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_agent_run_service_enhancements.py -q`

Expected: PASS

- [x] **Step 5: Commit**

```bash
git add services/agent_run_service.py tests/test_agent_run_service_enhancements.py
git commit -m "feat: persist effective parameters in run artifacts"
```

## Task 4: Fail Fast For Unavailable Local API During Manifest Benchmarks

**Files:**
- Modify: `E:/vscode/fusionAgent/scripts/eval_harness.py`
- Modify: `E:/vscode/fusionAgent/tests/test_eval_harness.py`
- Modify: `E:/vscode/fusionAgent/tests/test_api_v2_integration.py`

- [x] **Step 1: Write the failing test**

Append to `E:/vscode/fusionAgent/tests/test_eval_harness.py`:

```python
def test_manifest_agent_case_reports_fast_infra_failure_when_api_is_unreachable(monkeypatch, tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "test",
                "cases": [
                    {
                        "case_id": "building_real",
                        "theme": "building",
                        "execution_mode": "agent",
                        "readiness": "agent-ready",
                        "inputs": {
                            "osm": str(tmp_path / "osm.shp"),
                            "reference": str(tmp_path / "ref.shp"),
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    for suffix in [".shp", ".shx", ".dbf"]:
        (tmp_path / f"osm{suffix}").write_bytes(b"x")
        (tmp_path / f"ref{suffix}").write_bytes(b"x")

    monkeypatch.setattr(
        eval_harness,
        "run_local_v2_smoke",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("HTTP 111 for /health: connection refused")),
    )

    summary = eval_harness.main(["--manifest", str(manifest), "--case", "building_real"])
    assert summary == 1
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eval_harness.py::test_manifest_agent_case_reports_fast_infra_failure_when_api_is_unreachable -q`

Expected: FAIL if harness still only times out or emits ambiguous errors

- [x] **Step 3: Write minimal implementation**

In `E:/vscode/fusionAgent/scripts/eval_harness.py`, before launching a manifest-backed `agent-ready` case, wrap the runner call so connection-refused and obvious HTTP unavailability errors are surfaced directly:

```python
except Exception as exc:  # noqa: BLE001
    message = f"{type(exc).__name__}: {exc}"
    if "connection refused" in message.lower() or "/health" in message.lower():
        error = f"infra_unavailable: {message}"
    else:
        error = message
```

Do not silently convert this into `skipped`; unreachable local API during an explicitly requested live benchmark is a real failure.

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_eval_harness.py tests/test_api_v2_integration.py -q`

Expected: PASS

- [x] **Step 5: Commit**

```bash
git add scripts/eval_harness.py tests/test_eval_harness.py tests/test_api_v2_integration.py
git commit -m "feat: harden manifest-backed benchmark preflight"
```

## Task 5: Execute The First Real Building Benchmark In A Fresh Thread

**Files:**
- Use existing: `E:/vscode/fusionAgent/docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json`
- Use existing: `E:/vscode/fusionAgent/scripts/start_local.py`
- Use existing: `E:/vscode/fusionAgent/scripts/eval_harness.py`

- [x] **Step 1: Start a fresh execution thread**

Use a new Codex thread rooted at:

```text
E:\vscode\fusionAgent
```

Context to carry into the new thread:

```text
Execute docs/superpowers/plans/2026-04-08-fusion-agent-parameter-defaults-and-building-benchmark.md from Task 1 onward. After Tasks 1-4 pass, run the first real building benchmark case from docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json.
```

- [x] **Step 2: Start local API**

Run:

```powershell
python scripts/start_local.py
```

Expected:

```text
Uvicorn/FastAPI app starts locally without import errors
```

- [x] **Step 3: Run the first building benchmark**

Run:

```powershell
python scripts/eval_harness.py --manifest docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json --case building_gitega_osm_vs_google_agent
```

Expected:

```text
JSON summary with total=1 and either passed=1 or a concrete failure reason tied to data/runtime behavior
```

- [x] **Step 4: Save the benchmark result**

Write the result summary into:

```text
docs/superpowers/specs/2026-04-08-building-real-benchmark-result.json
```

- [x] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-04-08-building-real-benchmark-result.json
git commit -m "test: record first real building benchmark result"
```

## Follow-On Roadmap

After this plan is complete, the next plans should be split by subsystem:

1. `building_msft_clip_and_second_benchmark`
   - Clip the national Microsoft building layer to the Gitega AOI.
   - Add the second building benchmark case.

2. `road_reference_source_intake`
   - Add a non-OSM road reference dataset under `Data/roads/`.
   - Enable the first real road benchmark.

3. `water_polygon_agent_wrapper`
   - Wrap `Algorithm/water_polygon.py` behind a proper adapter and KG registration.
   - Prefer this before `water_line` because its threshold surface is smaller and its contract is simpler.

4. `water_line_agent_wrapper`
   - Add adapter + KG + tests once polygon masking/input contract is stable.

5. `poi_pipeline_refactor`
   - Refactor Excel-first scripts into a deterministic adapter boundary.
   - Decide one canonical runtime output: Excel-first or shapefile-first, but not both as equal primaries.

## Self-Review

### Spec coverage

- Immediate remaining gap from current progress: automatic KG-default parameter injection is covered by Tasks 1-3.
- Real-data building benchmark execution is covered by Tasks 4-5.
- Broader future work is covered in the follow-on roadmap rather than overloaded into this implementation plan.

### Placeholder scan

- No `TODO`, `TBD`, or “similar to above” references are left in the executable tasks.
- Each task has exact files, commands, and expected outcomes.

### Type consistency

- Parameter keys match current KG spec keys in `kg/seed.py`.
- Runtime terminology matches existing models: `WorkflowPlan`, `WorkflowTask.input.parameters`, `RunStatus`, `eval_harness`.

## Execution Status

- Status: completed
- Verification run on `2026-04-12`: `python -m pytest -q tests/test_parameter_default_binding.py tests/test_planner_context.py tests/test_agent_run_service_enhancements.py tests/test_eval_harness.py tests/test_api_v2_integration.py` -> `42 passed`.
- Official benchmark rerun on isolated local runtime: `building_gitega_osm_vs_google_agent` passed with `run_id=0b4315edf3a8449d940355717ad70fa7`, `duration_ms=612458`, and summary saved in `docs/superpowers/specs/2026-04-08-building-real-benchmark-result.json`.
- Branch integration note: refreshed evidence and doc updates were later merged into `main`.
