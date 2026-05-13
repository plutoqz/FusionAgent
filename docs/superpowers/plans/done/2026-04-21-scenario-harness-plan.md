# Scenario Harness Operations And Paper Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the scenario evidence layer into a stable long-running evaluation and operations foundation that supports paper evidence, demos, and resume presentation.

**Architecture:** Add a scenario evaluation harness and lightweight scenario registry above the existing `/api/v2/scenario-runs` endpoint. Keep the long-running trigger path minimal and file/API driven for now: normalize incoming event records into `ScenarioRunRequest`, enqueue them through the existing scenario API/service, and freeze outputs into paper- and demo-facing evidence packages. Self-evolution remains visible in evidence but is not a core control-loop dependency in this phase.

**Tech Stack:** Python 3.9+, FastAPI, Pydantic, pytest, existing scenario run service, existing v2 agent runtime, JSON/Markdown evidence files.

**Completion Status:** Completed on 2026-04-21 with focused verification output `14 passed in 1.97s`, scenario/runtime regression output `49 passed, 6 warnings in 7.94s`, full-suite output `234 passed, 1 skipped, 12 warnings in 104.07s (0:01:44)`, real scenario harness output `5 passed cases and 0 failed cases` from `tmp/eval/scenario-harness-summary.json`, and frozen evidence written to `docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.json` plus `docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.md`.

---

## Scope Priorities

This phase optimizes for stable long-running operation, paper-grade reproducibility, and resume-ready project narrative. It deliberately does not implement external news/social-media crawling, broad policy auto-tuning, a full dashboard, or new geospatial task families.

Self-evolution remains in scope only as explicit scenario evidence: `hint_available`, `hint_used`, `policy_adjustment`, and `learning_opportunity_recorded`. Runtime decisions must not depend on self-evolution being present.

## Phase 0: Documentation Discovery

Read these before implementation:

- `services/scenario_run_service.py`
- `api/routers/scenario_runs.py`
- `schemas/scenario.py`
- `services/scenario_output.py`
- `services/scenario_report_service.py`
- `docs/v2-operations.md`
- `docs/superpowers/specs/2026-04-20-evaluation-contract-claim-lock.md`
- `docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json`
- `docs/superpowers/plans/2026-04-21-scenario-evidence-and-reporting-upgrade.md`

Allowed APIs and patterns:

- Use `ScenarioRunRequest`, `ScenarioRunResponse`, and `ScenarioPhase` from `schemas/scenario.py`.
- Use `scenario_run_service.create_scenario_run(request)` for in-process orchestration.
- Use `POST /api/v2/scenario-runs` for API-level orchestration.
- Use `resolve_scenario_output_root(output_root)` to resolve scenario output roots.
- Treat `scenario_summary.json`, `kg_path_trace.json`, `workflow_trace.json`, `source_coverage.json`, `evaluation.json`, and bilingual reports as canonical scenario evidence.

Anti-pattern guards:

- Do not duplicate `AgentRunService` orchestration inside harness code.
- Do not invent external feed connectors in this phase.
- Do not make self-evolution hints mandatory for scenario success.
- Do not replace existing single-run evidence files or `/api/v2/runs` behavior.

---

## File Map

- Create: `schemas/scenario_manifest.py`
  Responsibility: scenario evaluation manifest models, case definitions, trigger event models, and harness output summary schema.
- Create: `services/scenario_manifest_service.py`
  Responsibility: load/validate scenario manifests and convert cases into `ScenarioRunRequest`.
- Create: `services/scenario_registry_service.py`
  Responsibility: maintain a lightweight scenario index under the scenario output root and load scenario summaries by id.
- Create: `services/scenario_trigger_service.py`
  Responsibility: normalize long-running trigger inbox records into scenario requests with deterministic idempotency keys.
- Create: `scripts/scenario_eval_harness.py`
  Responsibility: run scenario manifest cases through the API or in-process service and write a harness summary JSON.
- Create: `scripts/freeze_scenario_evidence.py`
  Responsibility: freeze selected scenario harness outputs into paper/demo JSON and Markdown summaries.
- Create: `scripts/watch_scenario_inbox.py`
  Responsibility: optional file-inbox runner for long-running local operation demos.
- Modify: `services/scenario_run_service.py`
  Responsibility: write scenario registry records after scenario completion.
- Modify: `api/routers/scenario_runs.py`
  Responsibility: add read-only scenario listing and inspection endpoints.
- Modify: `docs/v2-operations.md`
  Responsibility: document scenario harness, scenario registry, trigger inbox, and evidence freeze workflow.
- Modify: `README.md`
  Responsibility: add Chinese resume/demo positioning for the project.
- Modify: `README.en.md`
  Responsibility: add English resume/demo positioning.
- Create: `docs/superpowers/specs/2026-04-21-scenario-eval-manifest.json`
  Responsibility: checked-in small scenario manifest for paper/demo regression.
- Create: `docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.md`
  Responsibility: generated paper/demo-facing scenario evidence summary.
- Create: `docs/demo/fusionagent-resume-project-brief.md`
  Responsibility: resume-oriented project brief with architecture, impact, and verification evidence.
- Test: `tests/test_scenario_manifest_service.py`
  Responsibility: manifest validation and request conversion.
- Test: `tests/test_scenario_registry_service.py`
  Responsibility: index write/read and summary lookup.
- Test: `tests/test_scenario_trigger_service.py`
  Responsibility: trigger normalization, idempotency, and scope control.
- Test: `tests/test_api_scenario_registry.py`
  Responsibility: API listing and inspection endpoints.
- Test: `tests/test_scenario_eval_harness.py`
  Responsibility: harness summary generation with fake API/service runner.
- Test: `tests/test_freeze_scenario_evidence.py`
  Responsibility: evidence freeze JSON/Markdown output.

---

## Task 1: Add Scenario Manifest Models And Loader

**Files:**
- Create: `schemas/scenario_manifest.py`
- Create: `services/scenario_manifest_service.py`
- Create: `tests/test_scenario_manifest_service.py`
- Create: `docs/superpowers/specs/2026-04-21-scenario-eval-manifest.json`

- [ ] **Step 1: Write failing manifest loader tests**

Add tests proving that a manifest with `manifest_id`, `cases`, `case_id`, `trigger_content`, `disaster_type`, `job_types`, and `expected_phase` loads correctly and converts to `ScenarioRunRequest`.

Required assertions:

```python
assert manifest.manifest_id == "scenario.paper.demo.v1"
assert manifest.cases[0].case_id == "parakou_earthquake_building_road"
assert manifest.cases[0].job_types == [JobType.building, JobType.road]
assert request.metadata["case_id"] == "parakou_earthquake_building_road"
```

- [ ] **Step 2: Run and confirm failure**

Run:

```powershell
python -m pytest -q tests/test_scenario_manifest_service.py
```

Expected:

```text
ModuleNotFoundError: No module named 'schemas.scenario_manifest'
```

- [ ] **Step 3: Implement manifest schemas**

Create `schemas/scenario_manifest.py` with `ScenarioEvalCase`, `ScenarioEvalManifest`, `ScenarioHarnessCaseResult`, and `ScenarioHarnessSummary`. Use Python 3.9-compatible typing: `Optional[str]`, `List[...]`, and `Dict[...]`; do not use `str | None`.

Required fields:

```python
class ScenarioEvalCase(BaseModel):
    case_id: str
    scenario_name: str
    trigger_content: str
    disaster_type: Optional[str] = None
    job_types: List[JobType] = Field(default_factory=list)
    target_crs: Optional[str] = None
    expected_phase: List[str] = Field(default_factory=lambda: ["succeeded", "partial"])
    tags: List[str] = Field(default_factory=list)
    notes: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 4: Implement loader and request conversion**

Create `services/scenario_manifest_service.py` with:

```python
def load_scenario_manifest(path: Path) -> ScenarioEvalManifest:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    manifest = ScenarioEvalManifest.model_validate(payload)
    if not manifest.cases:
        raise ValueError("Scenario manifest must contain at least one case.")
    return manifest
```

and:

```python
def scenario_case_to_request(case: ScenarioEvalCase, *, output_root: Optional[str] = None) -> ScenarioRunRequest:
    metadata = dict(case.metadata)
    metadata["case_id"] = case.case_id
    metadata["expected_phase"] = list(case.expected_phase)
    metadata["tags"] = list(case.tags)
    return ScenarioRunRequest(
        scenario_name=case.scenario_name,
        trigger_content=case.trigger_content,
        disaster_type=case.disaster_type,
        job_types=list(case.job_types),
        output_root=output_root,
        target_crs=case.target_crs,
        metadata=metadata,
    )
```

- [ ] **Step 5: Add checked-in manifest**

Create `docs/superpowers/specs/2026-04-21-scenario-eval-manifest.json` with one initial case:

```json
{
  "manifest_id": "scenario.paper.demo.v1",
  "metadata": {
    "purpose": "Small paper/demo scenario regression set for FusionAgent scenario evidence.",
    "scope": "Stable building/road scenarios only; no self-evolution auto-tuning required."
  },
  "cases": [
    {
      "case_id": "parakou_earthquake_building_road",
      "scenario_name": "Parakou earthquake",
      "trigger_content": "fuse building and road data for Parakou, Benin after an earthquake",
      "disaster_type": "earthquake",
      "job_types": ["building", "road"],
      "expected_phase": ["succeeded", "partial"],
      "tags": ["paper", "demo", "fallback", "bilingual-report"],
      "notes": "Regression case for disaster-aware AOI parsing, building+road orchestration, evidence package generation, and graceful partial success."
    }
  ]
}
```

- [ ] **Step 6: Run tests**

Run:

```powershell
python -m pytest -q tests/test_scenario_manifest_service.py
```

Expected:

```text
2 passed
```

---

## Task 2: Add Scenario Registry And Read APIs

**Files:**
- Create: `services/scenario_registry_service.py`
- Create: `tests/test_scenario_registry_service.py`
- Create: `tests/test_api_scenario_registry.py`
- Modify: `services/scenario_run_service.py`
- Modify: `api/routers/scenario_runs.py`
- Modify: `schemas/scenario.py`

- [ ] **Step 1: Write failing registry tests**

Add tests proving that `ScenarioRegistryService.record()` appends JSONL records and `get_summary(scenario_id)` loads `scenario_summary.json` from the scenario directory under the configured output root.

Required assertions:

```python
assert records[0]["scenario_id"] == "scenario-a"
assert records[0]["phase"] == "succeeded"
assert summary["scenario_name"] == "Parakou earthquake"
```

- [ ] **Step 2: Run and confirm failure**

Run:

```powershell
python -m pytest -q tests/test_scenario_registry_service.py
```

Expected:

```text
ModuleNotFoundError: No module named 'services.scenario_registry_service'
```

- [ ] **Step 3: Implement registry service**

Create `services/scenario_registry_service.py` with `record()`, `list_records(limit=50, phase=None)`, and `get_summary(scenario_id)`. Store records in `scenario_runs_index.jsonl` under the configured output root.

Anti-pattern guard: do not keep registry state in memory only; scenario listing must survive process restart.

- [ ] **Step 4: Wire registry writes into scenario service**

Modify `services/scenario_run_service.py` so `create_scenario_run()` writes a registry record after summary/report files are written. Include `scenario_id`, `scenario_name`, `phase`, `output_dir`, `child_run_ids`, `created_at`, and `case_id`.

- [ ] **Step 5: Add API response models**

Modify `schemas/scenario.py`:

```python
class ScenarioRunListResponse(BaseModel):
    records: List[Dict[str, Any]] = Field(default_factory=list)


class ScenarioRunInspectionResponse(BaseModel):
    summary: Dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 6: Add read-only API endpoints**

Modify `api/routers/scenario_runs.py`:

```text
GET /api/v2/scenario-runs?limit=50&phase=succeeded
GET /api/v2/scenario-runs/{scenario_id}
```

Both endpoints must use `ScenarioRegistryService(output_root=resolve_scenario_output_root(None))`.

- [ ] **Step 7: Run focused tests**

Run:

```powershell
python -m pytest -q tests/test_scenario_registry_service.py tests/test_api_scenario_registry.py tests/test_api_scenario_runs.py
```

Expected:

```text
all tests pass
```

---

## Task 3: Add Scenario Evaluation Harness

**Files:**
- Create: `scripts/scenario_eval_harness.py`
- Create: `tests/test_scenario_eval_harness.py`
- Modify: `docs/v2-operations.md`

- [ ] **Step 1: Write failing harness test**

Add a fake `ScenarioClient` test that runs a one-case manifest and asserts:

```python
assert summary.total_cases == 1
assert summary.passed_cases == 1
assert summary.results[0].scenario_id == "scenario-a"
```

- [ ] **Step 2: Run and confirm failure**

Run:

```powershell
python -m pytest -q tests/test_scenario_eval_harness.py
```

Expected:

```text
ModuleNotFoundError or ImportError for scripts.scenario_eval_harness
```

- [ ] **Step 3: Implement harness**

Create `scripts/scenario_eval_harness.py` with:

- `HttpScenarioClient(base_url, timeout)`
- `run_manifest_cases(manifest_path, output_root, client) -> ScenarioHarnessSummary`
- CLI args: `--manifest`, `--base-url`, `--output-root`, `--output-json`, `--timeout`
- exit code `0` when `failed_cases == 0`, otherwise `1`

Anti-pattern guard: the harness must call `/api/v2/scenario-runs` or a `ScenarioClient` abstraction; it must not manually run child v2 runs.

- [ ] **Step 4: Document harness command**

Add to `docs/v2-operations.md`:

```powershell
python scripts/scenario_eval_harness.py `
  --manifest docs/superpowers/specs/2026-04-21-scenario-eval-manifest.json `
  --base-url http://127.0.0.1:8000 `
  --output-root E:\fyx\data\fusionagentTEST `
  --output-json tmp/eval/scenario-harness-summary.json `
  --timeout 1200
```

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m pytest -q tests/test_scenario_eval_harness.py tests/test_scenario_manifest_service.py
```

Expected:

```text
all tests pass
```

---

## Task 4: Add Minimal Long-Running Trigger Inbox

**Files:**
- Create: `services/scenario_trigger_service.py`
- Create: `scripts/watch_scenario_inbox.py`
- Create: `tests/test_scenario_trigger_service.py`
- Modify: `docs/v2-operations.md`

**Design choice:** Use a file inbox first. This supports long-running local operation and demonstrations without committing to an external feed provider.

- [ ] **Step 1: Write failing trigger normalization test**

Add a test where this event:

```json
{
  "event_id": "usgs-2026-001",
  "event_type": "earthquake",
  "location": "Parakou, Benin",
  "requested_layers": ["building", "road"],
  "description": "M5 earthquake near Parakou"
}
```

normalizes to a `ScenarioRunRequest` with:

```python
assert request.disaster_type == "earthquake"
assert request.job_types == [JobType.building, JobType.road]
assert "Parakou, Benin" in request.trigger_content
assert request.metadata["idempotency_key"] == "usgs-2026-001"
```

- [ ] **Step 2: Run and confirm failure**

Run:

```powershell
python -m pytest -q tests/test_scenario_trigger_service.py
```

Expected:

```text
ModuleNotFoundError: No module named 'services.scenario_trigger_service'
```

- [ ] **Step 3: Implement trigger normalization**

Create `services/scenario_trigger_service.py` with `normalize_trigger_event(event: dict[str, Any]) -> ScenarioRunRequest`.

Rules:

- `event_type` maps to `disaster_type`
- `location` is embedded in `trigger_content`
- `requested_layers` maps to `JobType`
- unknown or empty layers fall back to `[JobType.building, JobType.road]`
- `event_id` becomes `metadata["idempotency_key"]`
- if no `event_id` exists, create a stable SHA1 hash from sorted event items

- [ ] **Step 4: Implement file inbox runner**

Create `scripts/watch_scenario_inbox.py` with `process_inbox_once(inbox_dir, processed_dir, output_root=None) -> list[str]`.

Behavior:

- read `*.json` files from inbox
- normalize each event
- call `scenario_run_service.create_scenario_run(request)`
- move processed files to `processed_dir`
- print `{"processed": ["scenario_id"]}` as JSON

- [ ] **Step 5: Document operational boundary**

Add to `docs/v2-operations.md`:

```markdown
The file inbox runner is an operations demo path, not a production event-feed integration. It proves that scenario requests can be triggered automatically from normalized event records while keeping external feed reliability out of this phase.
```

- [ ] **Step 6: Run focused tests**

Run:

```powershell
python -m pytest -q tests/test_scenario_trigger_service.py
```

Expected:

```text
all tests pass
```

---

## Task 5: Add Scenario Evidence Freeze For Paper

**Files:**
- Create: `scripts/freeze_scenario_evidence.py`
- Create: `tests/test_freeze_scenario_evidence.py`
- Create: `docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.md`

- [ ] **Step 1: Write failing freeze tests**

Add a test that creates a fake `scenario_summary.json`, runs `freeze_scenario_evidence([...])`, and asserts:

```python
assert payload["scenario_count"] == 1
assert "Parakou earthquake" in markdown
assert "manual_intervention_count" in markdown
```

- [ ] **Step 2: Implement freeze script**

Create `scripts/freeze_scenario_evidence.py` with:

- `freeze_scenario_evidence(scenario_dirs, output_json, output_markdown) -> dict`
- CLI args: `--scenario-dir` repeatable, `--output-json`, `--output-markdown`
- JSON fields: `scenario_count`, `scenarios`
- per-scenario fields: `scenario_id`, `scenario_name`, `agentic_metrics`, `self_evolution`, `kg_path_trace_count`, `workflow_trace_count`, `document_paths`, `source_dir`

- [ ] **Step 3: Run focused tests**

Run:

```powershell
python -m pytest -q tests/test_freeze_scenario_evidence.py
```

Expected:

```text
all tests pass
```

---

## Task 6: Add Resume And Demo Project Brief

**Files:**
- Create: `docs/demo/fusionagent-resume-project-brief.md`
- Modify: `README.md`
- Modify: `README.en.md`

- [ ] **Step 1: Create resume project brief**

Create `docs/demo/fusionagent-resume-project-brief.md` with these sections:

- `One-Line Summary`
- `What It Demonstrates`
- `Technical Highlights`
- `Resume Bullets`
- `Demo Script`

Required resume bullets:

```markdown
- Built a KG-constrained geospatial fusion agent that plans, validates, executes, repairs, and audits disaster-response GIS workflows.
- Added scenario-level orchestration for multi-task building/road disaster cases with bilingual evidence reports and evaluation metrics.
- Implemented task-driven data acquisition with AOI-aware source materialization, cache reuse, and coverage-aware fallback handling.
- Established paper-grade reproducibility through scenario manifests, harness summaries, frozen evidence artifacts, and full-suite pytest verification.
```

- [ ] **Step 2: Add README pointers**

Add to `README.md`:

```markdown
简历/演示项目说明见 [FusionAgent Resume Project Brief](./docs/demo/fusionagent-resume-project-brief.md)。
```

Add to `README.en.md`:

```markdown
Resume/demo project brief: [FusionAgent Resume Project Brief](./docs/demo/fusionagent-resume-project-brief.md).
```

- [ ] **Step 3: Run documentation grep checks**

Run:

```powershell
Select-String -Path README.md,README.en.md -Pattern "fusionagent-resume-project-brief"
Select-String -Path docs/demo/fusionagent-resume-project-brief.md -Pattern "Resume Bullets"
```

Expected:

```text
both commands find at least one matching line
```

---

## Task 7: Verification And Operating Evidence

**Files:**
- Modify: `docs/v2-operations.md`
- Modify: `docs/superpowers/plans/2026-04-21-scenario-harness-plan.md`

- [ ] **Step 1: Run focused new test set**

Run:

```powershell
python -m pytest -q `
  tests/test_scenario_manifest_service.py `
  tests/test_scenario_registry_service.py `
  tests/test_scenario_trigger_service.py `
  tests/test_api_scenario_registry.py `
  tests/test_scenario_eval_harness.py `
  tests/test_freeze_scenario_evidence.py `
  tests/test_api_scenario_runs.py `
  tests/test_scenario_run_service.py `
  tests/test_parakou_scenario_regression.py
```

Expected:

```text
all tests pass
```

- [ ] **Step 2: Run existing scenario and runtime regression tests**

Run:

```powershell
python -m pytest -q `
  tests/test_scenario_output.py `
  tests/test_aoi_resolution_service.py `
  tests/test_source_coverage_fallback.py `
  tests/test_kg_path_trace_service.py `
  tests/test_workflow_trace_service.py `
  tests/test_artifact_evaluation_service.py `
  tests/test_scenario_report_service.py `
  tests/test_agent_run_service_enhancements.py `
  tests/test_api_v2_integration.py
```

Expected:

```text
all tests pass
```

- [ ] **Step 3: Run full test suite**

Run:

```powershell
python -m pytest -q
```

Expected:

```text
all tests pass with only known non-blocking warnings
```

- [ ] **Step 4: Run a real scenario harness check if local API is available**

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
exit code 0 if all manifest cases meet expected phases; otherwise summary JSON records the failing case and phase
```

- [ ] **Step 5: Freeze paper/demo scenario evidence**

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
freeze JSON and Markdown exist and reference scenario id, agentic metrics, self-evolution evidence state, KG trace count, workflow trace count, and source directory
```

- [ ] **Step 6: Update completion status**

After implementation and verification are complete, replace the completion status line with one sentence that includes the completion date, the focused verification output copied from the terminal, the full-suite output copied from the terminal, and either the scenario harness output copied from the terminal or the documented reason the harness was deferred.

---

## Self-Review

- Spec coverage: This plan covers scenario manifests, scenario registry, read APIs, scenario harness, long-running file-inbox trigger path, paper/demo evidence freeze, resume project brief, and verification.
- Scope control: Self-evolution remains visible through existing metrics and scenario summaries but is not required to influence runtime decisions in this phase.
- Long-running fit: The file inbox runner proves automatic trigger intake without locking the project into an external feed provider too early.
- Paper fit: Manifest-driven scenario runs and freeze scripts produce reproducible artifacts that can be cited and inspected.
- Resume fit: The project brief converts technical work into understandable project impact and demo steps.
- Risk: The file inbox is intentionally not production-grade event ingestion; document it as a stable local operations/demo path.
