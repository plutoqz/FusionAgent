# Scenario Evidence And Reporting Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade FusionAgent from single-run evidence files to scenario-level, coverage-aware, bilingual, self-evolution-aware evidence packages for real disaster response tests.

**Architecture:** Add a scenario orchestration layer above the existing v2 run runtime instead of replacing `AgentRunService`. The scenario layer resolves a shared AOI/CRS/output root, launches one or more task-driven child runs, captures KG relationship chains and actual execution workflow traces, evaluates both data-fusion results and agent behavior, then renders Chinese and English reports. Existing single-run evidence files remain stable; new scenario evidence is additive.

**Tech Stack:** Python 3.9+, FastAPI, Pydantic, GeoPandas, Shapely, pytest, existing KG repository, existing artifact/input acquisition services, existing durable-learning repository.

**Completion Status:** Completed on 2026-04-21; focused verification output: `19 passed in 2.27s`; runtime regression output: `66 passed, 6 warnings in 12.34s`; full-suite output: `222 passed, 1 skipped, 12 warnings in 100.00s (0:01:40)`.

---

## Scope Check

This plan covers the problems exposed by the Benin Parakou earthquake test:

- One request should be able to drive a building-plus-road scenario instead of requiring manual run splitting.
- The output root must be configurable and must also have a default. Preserve any existing configured scenario output root; if none exists, use `E:\fyx\data\fusionagentTEST`.
- AOI parsing must ignore disaster suffixes such as `after an earthquake` and geocode only the location phrase.
- Source materialization must be coverage-aware and able to fall back when a component source, such as Microsoft buildings, has zero AOI coverage.
- KG evidence must be a relationship chain, not only a list of candidate patterns or data sources.
- Final evidence must include the actual workflow chain: AOI resolution, source discovery, download/cache, clip, bundle creation, fusion, artifact checks, metric computation, and report generation.
- Evaluation must include both data-fusion metrics and agentic metrics.
- Self-evolution must be explicit: durable learning writeback, prior learning consumption, policy-hint influence, and learning opportunities must be exposed in evidence and reports.
- Reports must be generated in both Chinese and English.

This plan does not change the current stable single-run contract: `run.json`, `plan.json`, `validation.json`, `audit.jsonl`, and artifact bundle remain available.

---

## File Map

- Create: `schemas/scenario.py`
  Responsibility: scenario request/response models, child task specs, output-root settings, scenario status, summary schema.
- Create: `services/scenario_output.py`
  Responsibility: resolve explicit output root, configured default output root, and fallback default `E:\fyx\data\fusionagentTEST`.
- Create: `services/scenario_run_service.py`
  Responsibility: orchestrate one scenario into shared AOI/CRS plus multiple child v2 runs and scenario-level evidence.
- Create: `api/routers/scenario_runs.py`
  Responsibility: expose scenario run API endpoints without changing existing `/api/v2/runs`.
- Modify: `api/app.py`
  Responsibility: register the scenario router.
- Modify: `services/aoi_resolution_service.py`
  Responsibility: robust location extraction from disaster phrasing.
- Modify: `agent/retriever.py`
  Responsibility: expose KG source coverage hints and relationship-chain source data.
- Modify: `services/source_asset_service.py`
  Responsibility: expose structured source coverage status and remote/local coverage attempts.
- Modify: `services/raw_vector_source_service.py`
  Responsibility: propagate component-source coverage evidence into materialized raw-vector metadata.
- Modify: `services/local_bundle_catalog.py`
  Responsibility: surface bundle component coverage and allow fallback bundle specs.
- Modify: `services/input_acquisition_service.py`
  Responsibility: return selected/fallback source lineage with task-driven input bundles.
- Modify: `services/agent_run_service.py`
  Responsibility: keep plan task source, decision source, and materialized source consistent; emit workflow trace events.
- Create: `services/kg_path_trace_service.py`
  Responsibility: convert plan/context/KG retrieval payload into explicit KG relationship chains.
- Create: `services/workflow_trace_service.py`
  Responsibility: normalize audit events and runtime events into execution workflow steps.
- Create: `services/artifact_evaluation_service.py`
  Responsibility: compute data-fusion metrics and agentic metrics from artifacts, plan, audit, decisions, durable learning, and fallback events.
- Create: `services/scenario_report_service.py`
  Responsibility: render Chinese and English Markdown reports from scenario summary, KG path trace, workflow trace, and evaluation.
- Create: `templates/reports/scenario_report.zh.md.j2`
  Responsibility: Chinese scenario report template.
- Create: `templates/reports/scenario_report.en.md.j2`
  Responsibility: English scenario report template.
- Modify: `docs/v2-operations.md`
  Responsibility: document scenario output root, scenario evidence, and report generation.
- Modify: `.env.example`
  Responsibility: document optional `GEOFUSION_SCENARIO_OUTPUT_ROOT` default behavior.
- Test: `tests/test_scenario_output.py`
  Responsibility: output-root resolution.
- Test: `tests/test_aoi_resolution_service.py`
  Responsibility: disaster-aware location extraction.
- Test: `tests/test_source_coverage_fallback.py`
  Responsibility: coverage-aware Microsoft-empty fallback.
- Test: `tests/test_kg_path_trace_service.py`
  Responsibility: KG relationship-chain rendering.
- Test: `tests/test_workflow_trace_service.py`
  Responsibility: actual workflow trace generation.
- Test: `tests/test_artifact_evaluation_service.py`
  Responsibility: data-fusion metrics, agentic metrics, and self-evolution metrics.
- Test: `tests/test_scenario_report_service.py`
  Responsibility: Chinese and English report generation.
- Test: `tests/test_scenario_run_service.py`
  Responsibility: multi-task scenario orchestration.
- Test: `tests/test_api_scenario_runs.py`
  Responsibility: API-level scenario flow.
- Test: `tests/test_parakou_scenario_regression.py`
  Responsibility: regression for Parakou-style AOI parsing, source fallback, KG path trace, workflow trace, metrics, and bilingual reports using small fixtures.

---

## Design Contracts

### Output Root Contract

Resolution order:

```text
1. request.output_root if provided
2. GEOFUSION_SCENARIO_OUTPUT_ROOT if set
3. existing project-configured scenario output root if introduced before this task starts
4. E:\fyx\data\fusionagentTEST
```

The existing `runs/` directory for single v2 runs remains unchanged. The new default only applies to scenario-level outputs.

Scenario output layout:

```text
<output_root>/
  <scenario_id>/
    request.json
    scenario_summary.json
    evaluation.json
    kg_path_trace.json
    workflow_trace.json
    source_coverage.json
    final_outputs/
    documents/
      scenario_report.zh.md
      scenario_report.en.md
    child_runs/
      <job_type>-<run_id>/
```

### Agentic Evaluation Contract

In addition to fusion result metrics, every scenario evaluation must include:

```text
planning_validity_rate
kg_path_trace_completeness
decision_trace_completeness
plan_decision_materialization_consistency
source_coverage_resolution_rate
fallback_success_rate
autonomy_ratio
manual_intervention_count
recovery_success_rate
evidence_completeness_rate
self_evolution_record_written
self_evolution_hint_available
self_evolution_hint_used
self_evolution_policy_adjustment
self_evolution_learning_opportunity_recorded
```

### Self-Evolution Contract

This project already has durable learning records and bounded policy hints. The upgrade must make them visible and testable at scenario level:

```text
run outcome -> durable learning record -> aggregated durable summary
-> planner retrieval durable_learning_summaries
-> policy learning_adjustment
-> decision evidence
-> scenario self_evolution section
```

If no prior learning exists, the report must state `self_evolution_hint_available=false` instead of implying the agent learned from history.

---

## Task 1: Add Scenario Output Root Resolution

**Files:**
- Create: `services/scenario_output.py`
- Create: `tests/test_scenario_output.py`
- Modify: `.env.example`
- Modify: `docs/v2-operations.md`

- [ ] **Step 1: Write failing tests for default and explicit output roots**

Add `tests/test_scenario_output.py`:

```python
from services.scenario_output import DEFAULT_SCENARIO_OUTPUT_ROOT, resolve_scenario_output_root


def test_resolve_scenario_output_root_uses_request_value(monkeypatch, tmp_path):
    monkeypatch.delenv("GEOFUSION_SCENARIO_OUTPUT_ROOT", raising=False)

    resolved = resolve_scenario_output_root(str(tmp_path / "custom"))

    assert resolved == tmp_path / "custom"


def test_resolve_scenario_output_root_uses_environment_when_request_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("GEOFUSION_SCENARIO_OUTPUT_ROOT", str(tmp_path / "configured"))

    resolved = resolve_scenario_output_root(None)

    assert resolved == tmp_path / "configured"


def test_resolve_scenario_output_root_uses_project_default_when_unconfigured(monkeypatch):
    monkeypatch.delenv("GEOFUSION_SCENARIO_OUTPUT_ROOT", raising=False)

    resolved = resolve_scenario_output_root(None)

    assert resolved == DEFAULT_SCENARIO_OUTPUT_ROOT
    assert str(resolved) == r"E:\fyx\data\fusionagentTEST"
```

- [ ] **Step 2: Run the focused test and confirm it fails**

Run:

```powershell
python -m pytest -q tests/test_scenario_output.py
```

Expected:

```text
ModuleNotFoundError: No module named 'services.scenario_output'
```

- [ ] **Step 3: Implement output-root resolver**

Create `services/scenario_output.py`:

```python
from __future__ import annotations

import os
from pathlib import Path


DEFAULT_SCENARIO_OUTPUT_ROOT = Path(r"E:\fyx\data\fusionagentTEST")


def resolve_scenario_output_root(requested_output_root: str | None) -> Path:
    if requested_output_root and requested_output_root.strip():
        return Path(requested_output_root).expanduser().resolve()

    configured = os.getenv("GEOFUSION_SCENARIO_OUTPUT_ROOT")
    if configured and configured.strip():
        return Path(configured).expanduser().resolve()

    return DEFAULT_SCENARIO_OUTPUT_ROOT
```

- [ ] **Step 4: Document the setting**

Append to `.env.example`:

```dotenv
# Optional scenario-level output root. If unset, scenario outputs default to E:\fyx\data\fusionagentTEST.
GEOFUSION_SCENARIO_OUTPUT_ROOT=
```

Add to `docs/v2-operations.md`:

```markdown
- Scenario-level runs accept an explicit output root. If omitted, `GEOFUSION_SCENARIO_OUTPUT_ROOT` is used. If that is also unset, scenario outputs are written under `E:\fyx\data\fusionagentTEST`.
```

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m pytest -q tests/test_scenario_output.py
```

Expected:

```text
3 passed
```

---

## Task 2: Harden AOI Extraction For Disaster Phrases

**Files:**
- Modify: `services/aoi_resolution_service.py`
- Modify: `tests/test_aoi_resolution_service.py`

- [ ] **Step 1: Write failing tests for Parakou disaster suffixes**

Add to `tests/test_aoi_resolution_service.py`:

```python
def test_extract_location_query_removes_disaster_suffix() -> None:
    assert (
        AOIResolutionService.extract_location_query(
            "fuse building and road data for Parakou, Benin after an earthquake"
        )
        == "Parakou, Benin"
    )


def test_extract_location_query_supports_disaster_prefix() -> None:
    assert (
        AOIResolutionService.extract_location_query(
            "earthquake in Parakou, Benin, need building and road fusion"
        )
        == "Parakou, Benin"
    )
```

- [ ] **Step 2: Run focused AOI tests and confirm failure**

Run:

```powershell
python -m pytest -q tests/test_aoi_resolution_service.py -k "Parakou or disaster"
```

Expected:

```text
2 failed
```

- [ ] **Step 3: Implement phrase cleanup**

Update `AOIResolutionService.extract_location_query()` with deterministic cleanup:

```python
_DISASTER_SUFFIX_RE = re.compile(
    r"\s+(after|following|during|because of|due to)\s+(an?\s+)?"
    r"(earthquake|flood|typhoon|disaster|emergency)\b.*$",
    flags=re.IGNORECASE,
)

_NEED_SUFFIX_RE = re.compile(
    r"\s*,?\s*(need|needs|requiring|requires)\s+"
    r"(building|road|water|poi|data|fusion).*$",
    flags=re.IGNORECASE,
)


def _clean_location_phrase(value: str) -> str:
    cleaned = _DISASTER_SUFFIX_RE.sub("", value).strip(" .,:;")
    cleaned = _NEED_SUFFIX_RE.sub("", cleaned).strip(" .,:;")
    return cleaned
```

Call `_clean_location_phrase()` before returning a captured location.

- [ ] **Step 4: Run existing AOI tests**

Run:

```powershell
python -m pytest -q tests/test_aoi_resolution_service.py
```

Expected:

```text
all tests pass
```

---

## Task 3: Add Scenario Request Models And Orchestration Service

**Files:**
- Create: `schemas/scenario.py`
- Create: `services/scenario_run_service.py`
- Create: `tests/test_scenario_run_service.py`

- [ ] **Step 1: Write scenario model tests**

Add `tests/test_scenario_run_service.py`:

```python
from schemas.fusion import JobType
from schemas.scenario import ScenarioRunRequest
from services.scenario_run_service import build_child_run_specs


def test_build_child_run_specs_expands_building_and_road_tasks(tmp_path):
    request = ScenarioRunRequest(
        scenario_name="Parakou earthquake",
        trigger_content="fuse building and road data for Parakou, Benin after an earthquake",
        disaster_type="earthquake",
        job_types=[JobType.building, JobType.road],
        output_root=str(tmp_path),
    )

    specs = build_child_run_specs(request)

    assert [spec.job_type for spec in specs] == [JobType.building, JobType.road]
    assert all(spec.disaster_type == "earthquake" for spec in specs)
```

- [ ] **Step 2: Run and confirm schema/service are missing**

Run:

```powershell
python -m pytest -q tests/test_scenario_run_service.py::test_build_child_run_specs_expands_building_and_road_tasks
```

Expected:

```text
ModuleNotFoundError: No module named 'schemas.scenario'
```

- [ ] **Step 3: Create scenario schemas**

Create `schemas/scenario.py`:

```python
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from schemas.fusion import JobType


class ScenarioPhase(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    partial = "partial"
    failed = "failed"


class ScenarioRunRequest(BaseModel):
    scenario_name: str = "scenario run"
    trigger_content: str
    disaster_type: str | None = None
    job_types: list[JobType] = Field(default_factory=list)
    output_root: str | None = None
    target_crs: str | None = None
    debug: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScenarioChildRunSpec(BaseModel):
    job_type: JobType
    trigger_content: str
    disaster_type: str | None = None
    target_crs: str | None = None
    debug: bool = False


class ScenarioRunResponse(BaseModel):
    scenario_id: str
    phase: ScenarioPhase
    output_dir: str
    child_run_ids: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Create child spec builder**

Create `services/scenario_run_service.py`:

```python
from __future__ import annotations

import uuid
from pathlib import Path

from schemas.scenario import ScenarioChildRunSpec, ScenarioRunRequest
from services.scenario_output import resolve_scenario_output_root


def create_scenario_id() -> str:
    return f"scenario_{uuid.uuid4().hex}"


def scenario_output_dir(request: ScenarioRunRequest, scenario_id: str) -> Path:
    return resolve_scenario_output_root(request.output_root) / scenario_id


def build_child_run_specs(request: ScenarioRunRequest) -> list[ScenarioChildRunSpec]:
    return [
        ScenarioChildRunSpec(
            job_type=job_type,
            trigger_content=request.trigger_content,
            disaster_type=request.disaster_type,
            target_crs=request.target_crs,
            debug=request.debug,
        )
        for job_type in request.job_types
    ]
```

- [ ] **Step 5: Run scenario model tests**

Run:

```powershell
python -m pytest -q tests/test_scenario_run_service.py::test_build_child_run_specs_expands_building_and_road_tasks
```

Expected:

```text
1 passed
```

---

## Task 4: Add Coverage-Aware Source Fallback

**Files:**
- Modify: `services/source_asset_service.py`
- Modify: `services/raw_vector_source_service.py`
- Modify: `services/local_bundle_catalog.py`
- Modify: `services/input_acquisition_service.py`
- Modify: `services/agent_run_service.py`
- Create: `tests/test_source_coverage_fallback.py`

- [ ] **Step 1: Write failing fallback test**

Create `tests/test_source_coverage_fallback.py`:

```python
def test_building_catalog_falls_back_from_empty_microsoft_to_google(tmp_path):
    provider = make_provider_with_component_counts(
        tmp_path,
        counts={
            "raw.osm.building": 10,
            "raw.microsoft.building": 0,
            "raw.google.building": 8,
        },
    )

    bundle = provider.materialize_with_fallback(
        source_id="catalog.earthquake.building",
        request_bbox=(2.48, 9.23, 2.77, 9.44),
        resolved_aoi=make_resolved_aoi("Parakou, Benin"),
        target_dir=tmp_path / "bundle",
        target_crs="EPSG:32631",
    )

    assert bundle.source_id == "catalog.flood.building"
    assert bundle.fallback_from == "catalog.earthquake.building"
    assert bundle.component_coverage["raw.microsoft.building"].feature_count == 0
    assert bundle.component_coverage["raw.google.building"].feature_count == 8
```

Implement `make_provider_with_component_counts()` and `make_resolved_aoi()` in the same test file using tiny fixture shapefiles.

- [ ] **Step 2: Run fallback test and confirm missing API**

Run:

```powershell
python -m pytest -q tests/test_source_coverage_fallback.py
```

Expected:

```text
AttributeError: 'LocalBundleCatalogProvider' object has no attribute 'materialize_with_fallback'
```

- [ ] **Step 3: Add structured coverage models**

Add to `services/source_asset_service.py`:

```python
@dataclass(frozen=True)
class SourceCoverageStatus:
    source_id: str
    source_mode: str
    feature_count: int | None
    coverage_status: str
    path: Path | None = None
    error: str | None = None


def coverage_status_for_count(feature_count: int | None) -> str:
    if feature_count is None:
        return "unknown"
    if feature_count == 0:
        return "empty"
    return "available"
```

- [ ] **Step 4: Add fallback bundle materialization**

Add to `services/local_bundle_catalog.py`:

```python
BUILDING_SOURCE_FALLBACKS = {
    "catalog.earthquake.building": ["catalog.flood.building"],
}
```

Add `materialize_with_fallback()` that tries the requested bundle first, then configured fallback bundles, and returns a materialized bundle with `source_id`, `fallback_from`, `attempted_sources`, and `component_coverage`.

- [ ] **Step 5: Record fallback in input acquisition and audit**

Extend `ResolvedRunInputs` in `services/input_acquisition_service.py` with:

```python
selected_source_id: str | None = None
fallback_from_source_id: str | None = None
component_coverage: dict[str, dict[str, object]] = field(default_factory=dict)
```

Update `_record_task_inputs_resolved()` in `services/agent_run_service.py` to include:

```python
"requested_source_id": resolved_inputs.source_id,
"selected_source_id": resolved_inputs.selected_source_id or resolved_inputs.source_id,
"fallback_from_source_id": resolved_inputs.fallback_from_source_id,
"component_coverage": resolved_inputs.component_coverage,
```

- [ ] **Step 6: Run fallback tests**

Run:

```powershell
python -m pytest -q tests/test_source_coverage_fallback.py tests/test_input_acquisition_service.py
```

Expected:

```text
all tests pass
```

---

## Task 5: Make Plan, Decision, And Materialization Consistent

**Files:**
- Modify: `services/agent_run_service.py`
- Modify: `agent/retriever.py`
- Modify: `kg/source_catalog.py`
- Modify: `tests/test_agent_run_service_enhancements.py`
- Modify: `tests/test_planner_context.py`

- [ ] **Step 1: Write failing consistency test**

Add to `tests/test_agent_run_service_enhancements.py`:

```python
def test_task_driven_source_decision_plan_and_materialization_are_consistent(tmp_path, monkeypatch):
    service = AgentRunService(base_dir=tmp_path)
    monkeypatch.setattr(service.aoi_resolution_service, "resolve", lambda _query: _resolved_nairobi_aoi())
    monkeypatch.setattr(
        service.input_acquisition_service,
        "resolve_task_driven_inputs",
        fake_resolved_inputs(selected_source_id="catalog.earthquake.road"),
    )

    status = service.create_run(
        request=make_task_driven_request(job_type=JobType.road, disaster_type="earthquake"),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    plan = service.get_plan(status.run_id)
    source_decision = next(record for record in status.decision_records if record.decision_type == "data_source_selection")
    resolved_event = next(event for event in service.get_audit_events(status.run_id) if event.kind == "task_inputs_resolved")

    assert plan.tasks[0].input.data_source_id == source_decision.selected_id
    assert resolved_event.details["selected_source_id"] == source_decision.selected_id
```

- [ ] **Step 2: Run and confirm failure**

Run:

```powershell
python -m pytest -q tests/test_agent_run_service_enhancements.py::test_task_driven_source_decision_plan_and_materialization_are_consistent
```

Expected:

```text
assertion fails because selected/materialized source can diverge
```

- [ ] **Step 3: Write source decision back into plan**

Update `_build_data_source_selection_decision()` so the selected source is reflected in matching task inputs:

```python
for task in plan.tasks:
    if task.input.data_source_id != decision.selected_id:
        task.input.data_source_id = decision.selected_id
```

When fallback is later selected, update the plan with the selected fallback source and preserve the original source in `plan.context["source_fallbacks"]`.

- [ ] **Step 4: Improve earthquake road source ordering**

Update `kg/source_catalog.py` and `agent/retriever.py` so `catalog.earthquake.road` appears as an earthquake road candidate before typhoon/flood road sources when disaster type is `earthquake`.

- [ ] **Step 5: Run consistency and planner tests**

Run:

```powershell
python -m pytest -q tests/test_agent_run_service_enhancements.py::test_task_driven_source_decision_plan_and_materialization_are_consistent tests/test_planner_context.py
```

Expected:

```text
all tests pass
```

---

## Task 6: Generate KG Relationship Chain Evidence

**Files:**
- Create: `services/kg_path_trace_service.py`
- Create: `tests/test_kg_path_trace_service.py`
- Modify: `api/routers/runs_v2.py`
- Modify: `schemas/agent.py`

- [ ] **Step 1: Write failing KG path trace test**

Create `tests/test_kg_path_trace_service.py`:

```python
from services.kg_path_trace_service import build_kg_path_trace


def test_build_kg_path_trace_contains_relationship_chain() -> None:
    trace = build_kg_path_trace(make_building_plan_with_retrieval_context())

    assert trace["job_type"] == "building"
    assert trace["chain"][0]["node_type"] == "ScenarioProfile"
    assert trace["chain"][-1]["node_type"] == "OutputSchemaPolicy"
    assert ("DataSource", "HAS_COMPONENT_SOURCE", "RawVectorSource") in {
        (edge["from_type"], edge["relation"], edge["to_type"]) for edge in trace["edges"]
    }
```

- [ ] **Step 2: Run and confirm missing service**

Run:

```powershell
python -m pytest -q tests/test_kg_path_trace_service.py
```

Expected:

```text
ModuleNotFoundError: No module named 'services.kg_path_trace_service'
```

- [ ] **Step 3: Implement KG path trace builder**

Create `services/kg_path_trace_service.py`:

```python
from __future__ import annotations

from schemas.agent import WorkflowPlan


def build_kg_path_trace(plan: WorkflowPlan) -> dict[str, object]:
    context = plan.context or {}
    intent = context.get("intent") or {}
    retrieval = context.get("retrieval") or {}
    task = plan.tasks[0] if plan.tasks else None
    selected_source_id = task.input.data_source_id if task else None
    selected_algorithm_id = task.algorithm_id if task else None
    selected_output_type = task.output.data_type_id if task else None

    source = _find_by_id(retrieval.get("data_sources", []), "source_id", selected_source_id)
    algorithm = (retrieval.get("algorithms") or {}).get(selected_algorithm_id) or {}
    schema_policy = (retrieval.get("output_schema_policies") or {}).get(selected_output_type) or {}
    pattern_id = _selected_pattern_id(plan)
    pattern = _find_by_id(retrieval.get("candidate_patterns", []), "pattern_id", pattern_id)
    component_sources = (source.get("metadata") or {}).get("component_source_ids") or []

    chain = [
        _node("ScenarioProfile", intent.get("profile_source") or "direct"),
        _node("TaskBundle", (intent.get("task_bundle") or {}).get("bundle_id")),
        _node("WorkflowPattern", pattern.get("pattern_id")),
        _node("StepTemplate", task.name if task else None),
        _node("Algorithm", selected_algorithm_id, label=algorithm.get("algo_name")),
        _node("InputDataType", task.input.data_type_id if task else None),
        _node("DataSource", selected_source_id, label=source.get("source_name")),
        *[_node("RawVectorSource", component) for component in component_sources],
        _node("OutputDataType", selected_output_type),
        _node("OutputSchemaPolicy", schema_policy.get("policy_id")),
    ]
    chain = [node for node in chain if node["node_id"]]
    return {"job_type": intent.get("job_type"), "chain": chain, "edges": _edges_for_chain(chain)}
```

Add `_node()`, `_find_by_id()`, `_selected_pattern_id()`, and `_edges_for_chain()` in the same file.

- [ ] **Step 4: Expose trace in inspection response**

Modify `schemas/agent.py`:

```python
class RunInspectionResponse(BaseModel):
    run: RunStatus
    plan: Optional[WorkflowPlan] = None
    audit_events: List[RunEvent] = Field(default_factory=list)
    artifact: RunInspectionArtifact = Field(default_factory=RunInspectionArtifact)
    kg_path_trace: Dict[str, Any] = Field(default_factory=dict)
```

Modify `api/routers/runs_v2.py` to call `build_kg_path_trace(plan)` when a plan exists.

- [ ] **Step 5: Run KG trace tests and API integration subset**

Run:

```powershell
python -m pytest -q tests/test_kg_path_trace_service.py tests/test_api_v2_integration.py
```

Expected:

```text
all tests pass
```

---

## Task 7: Add Actual Workflow Trace

**Files:**
- Create: `services/workflow_trace_service.py`
- Create: `tests/test_workflow_trace_service.py`
- Modify: `services/agent_run_service.py`

- [ ] **Step 1: Write failing workflow trace test**

Create `tests/test_workflow_trace_service.py`:

```python
from services.workflow_trace_service import build_workflow_trace


def test_build_workflow_trace_normalizes_runtime_events() -> None:
    trace = build_workflow_trace(make_audit_events_for_successful_road_run())

    step_names = [step["step_name"] for step in trace["steps"]]
    assert step_names == [
        "aoi_resolved",
        "target_crs_resolved",
        "kg_path_selected",
        "plan_validated",
        "task_inputs_resolved",
        "fusion_executed",
        "artifact_written",
    ]
    assert trace["steps"][0]["actor"] == "agent"
```

- [ ] **Step 2: Implement trace builder**

Create `services/workflow_trace_service.py`:

```python
from __future__ import annotations

from schemas.agent import RunEvent


EVENT_TO_STEP = {
    "aoi_resolved": "aoi_resolved",
    "target_crs_resolved": "target_crs_resolved",
    "plan_created": "kg_path_selected",
    "plan_validated": "plan_validated",
    "task_inputs_resolved": "task_inputs_resolved",
    "execution_completed": "fusion_executed",
    "run_succeeded": "artifact_written",
    "run_failed": "failure_recorded",
}


def build_workflow_trace(events: list[RunEvent]) -> dict[str, object]:
    steps = []
    for event in events:
        step_name = EVENT_TO_STEP.get(event.kind)
        if step_name is None:
            continue
        steps.append(
            {
                "step_name": step_name,
                "actor": _actor_for_event(event.kind),
                "status": "failed" if event.kind == "run_failed" else "succeeded",
                "phase": event.phase.value,
                "timestamp": event.timestamp,
                "input": _event_input(event),
                "output": _event_output(event),
                "details": event.details,
            }
        )
    return {"steps": steps}
```

Add `_actor_for_event()`, `_event_input()`, and `_event_output()` with deterministic mappings.

- [ ] **Step 3: Emit source discovery and clipping trace events**

Update `AgentRunService` around input acquisition to emit additional audit events:

```text
source_coverage_checked
source_fallback_selected
source_clipped
input_bundle_created
```

These events must include path and feature-count details when available.

- [ ] **Step 4: Run workflow trace tests**

Run:

```powershell
python -m pytest -q tests/test_workflow_trace_service.py tests/test_agent_run_service_enhancements.py -k "task_inputs_resolved or coverage or trace"
```

Expected:

```text
all selected tests pass
```

---

## Task 8: Add Artifact And Agentic Evaluation Service

**Files:**
- Create: `services/artifact_evaluation_service.py`
- Create: `tests/test_artifact_evaluation_service.py`

- [ ] **Step 1: Write data-fusion metric tests**

Create `tests/test_artifact_evaluation_service.py`:

```python
from services.artifact_evaluation_service import evaluate_vector_artifact


def test_evaluate_vector_artifact_reports_polygon_metrics(tmp_path):
    shp_path = write_polygon_fixture(tmp_path / "buildings.shp", count=2, crs="EPSG:32631")

    metrics = evaluate_vector_artifact(shp_path, required_fields=["geometry"])

    assert metrics["artifact_validity"] is True
    assert metrics["feature_count"] == 2
    assert metrics["crs"] == "EPSG:32631"
    assert metrics["geometry_types"] == ["Polygon"]
    assert metrics["total_area_sq_km"] > 0


def test_evaluate_vector_artifact_reports_line_metrics(tmp_path):
    shp_path = write_line_fixture(tmp_path / "roads.shp", count=3, crs="EPSG:32631")

    metrics = evaluate_vector_artifact(shp_path, required_fields=["geometry"])

    assert metrics["artifact_validity"] is True
    assert metrics["feature_count"] == 3
    assert metrics["total_length_km"] > 0
```

- [ ] **Step 2: Write agentic metric tests**

Add:

```python
from services.artifact_evaluation_service import evaluate_agentic_run


def test_evaluate_agentic_run_reports_trace_and_self_evolution_metrics() -> None:
    result = evaluate_agentic_run(
        plan=make_plan_with_kg_path(),
        decision_records=make_decisions_with_learning_adjustment(),
        audit_events=make_successful_audit_events(),
        durable_learning_summary={"patterns": [{"entity_id": "wp.a", "total_runs": 3}]},
        manual_intervention_count=0,
    )

    assert result["kg_path_trace_completeness"] == 1.0
    assert result["decision_trace_completeness"] == 1.0
    assert result["autonomy_ratio"] == 1.0
    assert result["self_evolution_hint_available"] is True
    assert result["self_evolution_hint_used"] is True
    assert result["self_evolution_policy_adjustment"] != 0
```

- [ ] **Step 3: Implement artifact evaluation**

Create `services/artifact_evaluation_service.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd


def evaluate_vector_artifact(shp_path: Path, *, required_fields: list[str]) -> dict[str, Any]:
    frame = gpd.read_file(shp_path)
    missing_fields = [field for field in required_fields if field != "geometry" and field not in frame.columns]
    metrics = {
        "artifact_validity": shp_path.exists() and not frame.empty and not missing_fields,
        "feature_count": int(len(frame)),
        "crs": str(frame.crs),
        "geometry_types": sorted(str(value) for value in frame.geometry.geom_type.dropna().unique()),
        "missing_fields": missing_fields,
        "bbox": [float(value) for value in frame.to_crs("EPSG:4326").total_bounds] if len(frame) else None,
    }
    metrics.update(_geometry_measurements(frame))
    return metrics
```

Add `_geometry_measurements()` to compute `total_area_sq_km` for polygon outputs and `total_length_km` for line outputs.

- [ ] **Step 4: Implement agentic evaluation**

Add:

```python
def evaluate_agentic_run(
    *,
    plan,
    decision_records,
    audit_events,
    durable_learning_summary,
    manual_intervention_count: int,
) -> dict[str, Any]:
    learning_adjustments = [
        candidate.evidence.get("metrics", {}).get("learning_adjustment")
        for record in decision_records
        for candidate in record.candidates
        if candidate.evidence.get("metrics", {}).get("learning_adjustment") is not None
    ]
    return {
        "planning_validity_rate": _planning_validity_rate(plan, audit_events),
        "decision_trace_completeness": _decision_trace_completeness(decision_records),
        "kg_path_trace_completeness": _kg_path_trace_completeness(plan),
        "recovery_success_rate": _recovery_success_rate(audit_events),
        "evidence_completeness_rate": _evidence_completeness_rate(audit_events),
        "autonomy_ratio": 1.0 if manual_intervention_count == 0 else 0.0,
        "manual_intervention_count": manual_intervention_count,
        "self_evolution_record_written": any(event.kind == "durable_learning_recorded" for event in audit_events),
        "self_evolution_hint_available": bool((durable_learning_summary or {}).get("patterns")),
        "self_evolution_hint_used": any(value not in (None, 0, 0.0) for value in learning_adjustments),
        "self_evolution_policy_adjustment": max(learning_adjustments, default=0.0),
        "self_evolution_learning_opportunity_recorded": any(event.kind in {"run_succeeded", "run_failed"} for event in audit_events),
    }
```

- [ ] **Step 5: Run evaluation tests**

Run:

```powershell
python -m pytest -q tests/test_artifact_evaluation_service.py
```

Expected:

```text
all tests pass
```

---

## Task 9: Add Scenario Report Service With Chinese And English Reports

**Files:**
- Create: `services/scenario_report_service.py`
- Create: `templates/reports/scenario_report.zh.md.j2`
- Create: `templates/reports/scenario_report.en.md.j2`
- Create: `tests/test_scenario_report_service.py`

- [ ] **Step 1: Write failing report tests**

Create `tests/test_scenario_report_service.py`:

```python
from services.scenario_report_service import render_scenario_reports


def test_render_scenario_reports_writes_chinese_and_english_markdown(tmp_path):
    summary = make_scenario_summary_with_kg_trace_workflow_trace_and_metrics()

    output = render_scenario_reports(summary=summary, documents_dir=tmp_path)

    zh = (tmp_path / "scenario_report.zh.md").read_text(encoding="utf-8")
    en = (tmp_path / "scenario_report.en.md").read_text(encoding="utf-8")
    assert output["zh"].endswith("scenario_report.zh.md")
    assert output["en"].endswith("scenario_report.en.md")
    assert "知识图谱关系链" in zh
    assert "KG Relationship Chain" in en
    assert "智能体评价指标" in zh
    assert "Agentic Evaluation Metrics" in en
    assert "自进化证据" in zh
    assert "Self-Evolution Evidence" in en
```

- [ ] **Step 2: Implement report renderer**

Create `services/scenario_report_service.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape


TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates" / "reports"


def render_scenario_reports(*, summary: dict[str, Any], documents_dir: Path) -> dict[str, str]:
    documents_dir.mkdir(parents=True, exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    outputs = {}
    for lang in ("zh", "en"):
        template = env.get_template(f"scenario_report.{lang}.md.j2")
        output_path = documents_dir / f"scenario_report.{lang}.md"
        output_path.write_text(template.render(summary=summary), encoding="utf-8")
        outputs[lang] = str(output_path)
    return outputs
```

- [ ] **Step 3: Add report templates**

Create `templates/reports/scenario_report.zh.md.j2` with sections:

```markdown
# {{ summary.scenario_name }} 场景报告

## 场景概述
## 知识图谱关系链
## 最终执行工作流
## 数据源覆盖与退化
## 数据融合结果评价指标
## 智能体评价指标
## 自进化证据
## 输出文件
```

Create `templates/reports/scenario_report.en.md.j2` with sections:

```markdown
# {{ summary.scenario_name }} Scenario Report

## Scenario Overview
## KG Relationship Chain
## Final Execution Workflow
## Source Coverage And Fallbacks
## Data Fusion Evaluation Metrics
## Agentic Evaluation Metrics
## Self-Evolution Evidence
## Output Files
```

- [ ] **Step 4: Run report tests**

Run:

```powershell
python -m pytest -q tests/test_scenario_report_service.py
```

Expected:

```text
all tests pass
```

---

## Task 10: Wire Scenario Service End To End

**Files:**
- Modify: `services/scenario_run_service.py`
- Create: `api/routers/scenario_runs.py`
- Modify: `api/app.py`
- Create: `tests/test_api_scenario_runs.py`

- [ ] **Step 1: Write API test for scenario request**

Create `tests/test_api_scenario_runs.py`:

```python
def test_create_scenario_run_generates_summary_and_reports(client, tmp_path, monkeypatch):
    monkeypatch.setenv("GEOFUSION_SCENARIO_OUTPUT_ROOT", str(tmp_path))

    response = client.post(
        "/api/v2/scenario-runs",
        json={
            "scenario_name": "Parakou earthquake",
            "trigger_content": "fuse building and road data for Parakou, Benin after an earthquake",
            "disaster_type": "earthquake",
            "job_types": ["building", "road"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["phase"] in {"succeeded", "partial"}
    assert payload["output_dir"].startswith(str(tmp_path))
```

- [ ] **Step 2: Implement scenario router**

Create `api/routers/scenario_runs.py`:

```python
from __future__ import annotations

from fastapi import APIRouter

from schemas.scenario import ScenarioRunRequest, ScenarioRunResponse
from services.scenario_run_service import scenario_run_service


router = APIRouter(tags=["scenario-runs"])


@router.post("/scenario-runs", response_model=ScenarioRunResponse)
async def create_scenario_run(request: ScenarioRunRequest) -> ScenarioRunResponse:
    return scenario_run_service.create_scenario_run(request)
```

Register it in `api/app.py` under the existing `/api/v2` prefix.

- [ ] **Step 3: Implement scenario service orchestration**

Extend `services/scenario_run_service.py`:

```python
class ScenarioRunService:
    def __init__(self, *, agent_run_service: AgentRunService) -> None:
        self.agent_run_service = agent_run_service

    def create_scenario_run(self, request: ScenarioRunRequest) -> ScenarioRunResponse:
        scenario_id = create_scenario_id()
        output_dir = scenario_output_dir(request, scenario_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        child_specs = build_child_run_specs(request)
        child_results = [self._run_child(output_dir, spec) for spec in child_specs]
        summary = self._build_summary(request, scenario_id, output_dir, child_results)
        self._write_summary_and_reports(output_dir, summary)
        return ScenarioRunResponse(
            scenario_id=scenario_id,
            phase=_phase_from_child_results(child_results),
            output_dir=str(output_dir),
            child_run_ids=[result["run_id"] for result in child_results if result.get("run_id")],
        )
```

`_build_summary()` must include:

```text
kg_path_traces
workflow_traces
source_coverage
evaluation.data_fusion_metrics
evaluation.agentic_metrics
evaluation.self_evolution
manual_interventions
final_outputs
document_paths
```

- [ ] **Step 4: Run API scenario tests**

Run:

```powershell
python -m pytest -q tests/test_api_scenario_runs.py
```

Expected:

```text
all tests pass
```

---

## Task 11: Add Parakou Scenario Regression Fixture

**Files:**
- Create: `tests/test_parakou_scenario_regression.py`

- [ ] **Step 1: Write regression test**

Create `tests/test_parakou_scenario_regression.py`:

```python
def test_parakou_scenario_generates_kg_trace_workflow_trace_metrics_and_bilingual_reports(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOFUSION_SCENARIO_OUTPUT_ROOT", str(tmp_path))
    service = make_scenario_service_with_parakou_fixture(tmp_path)

    response = service.create_scenario_run(
        ScenarioRunRequest(
            scenario_name="Parakou earthquake",
            trigger_content="fuse building and road data for Parakou, Benin after an earthquake",
            disaster_type="earthquake",
            job_types=[JobType.building, JobType.road],
        )
    )

    scenario_dir = Path(response.output_dir)
    summary = json.loads((scenario_dir / "scenario_summary.json").read_text(encoding="utf-8"))
    assert response.phase in {ScenarioPhase.succeeded, ScenarioPhase.partial}
    assert (scenario_dir / "documents" / "scenario_report.zh.md").exists()
    assert (scenario_dir / "documents" / "scenario_report.en.md").exists()
    assert summary["kg_path_traces"]
    assert summary["workflow_traces"]
    assert summary["evaluation"]["agentic_metrics"]["manual_intervention_count"] == 0
    assert summary["evaluation"]["self_evolution"]["learning_opportunity_recorded"] is True
```

- [ ] **Step 2: Generate mini fixture data in test helpers**

Use helper functions in the test file to create tiny GeoPandas fixtures at runtime instead of tracking large shapefiles:

```python
def write_parakou_fixture_data(root: Path) -> None:
    write_polygon_fixture(root / "Data" / "buildings" / "OSM" / "osm.shp", count=3, crs="EPSG:4326")
    write_polygon_fixture(root / "Data" / "buildings" / "Google" / "google.shp", count=2, crs="EPSG:4326")
    write_empty_polygon_fixture(root / "Data" / "buildings" / "Microsoft" / "microsoft.shp", crs="EPSG:4326")
    write_line_fixture(root / "Data" / "roads" / "OSM" / "roads.shp", count=2, crs="EPSG:4326")
```

- [ ] **Step 3: Run regression test**

Run:

```powershell
python -m pytest -q tests/test_parakou_scenario_regression.py
```

Expected:

```text
all tests pass
```

---

## Task 12: Verification And Documentation

**Files:**
- Modify: `docs/v2-operations.md`
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/superpowers/plans/2026-04-21-scenario-evidence-and-reporting-upgrade.md`

- [ ] **Step 1: Run focused test set**

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
  tests/test_scenario_run_service.py `
  tests/test_api_scenario_runs.py `
  tests/test_parakou_scenario_regression.py
```

Expected:

```text
all tests pass
```

- [ ] **Step 2: Run runtime regression subset**

Run:

```powershell
python -m pytest -q `
  tests/test_agent_run_service_enhancements.py `
  tests/test_input_acquisition_service.py `
  tests/test_source_asset_service.py `
  tests/test_api_v2_integration.py `
  tests/test_planner_context.py
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

- [ ] **Step 4: Update operator docs**

Document:

```text
POST /api/v2/scenario-runs
GEOFUSION_SCENARIO_OUTPUT_ROOT
default root E:\fyx\data\fusionagentTEST
scenario_summary.json
kg_path_trace.json
workflow_trace.json
evaluation.json
scenario_report.zh.md
scenario_report.en.md
```

- [ ] **Step 5: Update this plan completion status after implementation**

When implementation and verification are complete, replace the completion status line with one sentence that includes the completion date, the exact focused verification command output, and the exact full-suite output copied from the terminal log.

---

## Self-Review

- Spec coverage: The plan covers default output root behavior, scenario-level orchestration, AOI parsing, coverage-aware fallback, KG relationship-chain evidence, final execution workflow traces, data-fusion metrics, agentic metrics, self-evolution evidence, and bilingual reports.
- Scope control: This plan keeps existing v2 run APIs stable and adds scenario-level capabilities above them.
- Type consistency: New schema names are `ScenarioRunRequest`, `ScenarioChildRunSpec`, `ScenarioRunResponse`, and `ScenarioPhase`; service names are `ScenarioRunService`, `scenario_output`, `kg_path_trace_service`, `workflow_trace_service`, `artifact_evaluation_service`, and `scenario_report_service`.
- Evidence discipline: Every new capability has a focused test and a scenario-level regression tied to the Parakou experiment failure modes.
- Default root handling: The plan preserves existing single-run `runs/` behavior and only defaults scenario outputs to `E:\fyx\data\fusionagentTEST` when no explicit or configured scenario output root exists.
