# Karachi Flood Runtime Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Chinese disaster-scenario runs such as Karachi flood resolve AOI correctly, expand the bounded scenario task bundle, choose disaster-appropriate sources, recover from empty AOI coverage where possible, and publish scenario evidence only after child runs reach their real terminal state.

**Architecture:** Keep the existing FastAPI/Celery/runtime shape. Harden the boundary between `ScenarioRunService` and `AgentRunService`: scenario requests decide bounded child tasks, run planning resolves a usable AOI/bbox before source materialization, source selection honors disaster compatibility before numeric scoring, and scenario summaries are rebuilt from final child run evidence.

**Tech Stack:** Python 3.12, FastAPI service layer, Pydantic schemas, pytest, GeoPandas runtime helpers, existing `AOIResolutionService`, `InputAcquisitionService`, `LocalBundleCatalogProvider`, and `ScenarioRunService`.

---

## Context And Failure Evidence

The June 1, 2026 Karachi flood observation test produced these failed runs:

- `95cc69148c7440ab83335c84bcf8cbcc`: original Chinese Karachi flood scenario, failed with `ValueError: Multi-source tiled building runtime requires an AOI bbox.`
- `193bce0241e94fde87513e384e5ae4d9`: same scenario with `force_aoi_resolution=true`, failed with the same missing bbox error.
- `c9ea75ef2cbd415aa5d9863c494c2d97`: manual intervention changed `spatial_extent` to `bbox(66.2862312,24.4273517,67.5827753,25.676796)`, then failed with `SOURCE_MISSING` after selecting `catalog.earthquake.building`.

The important evidence paths are:

- `runs/95cc69148c7440ab83335c84bcf8cbcc/run.json`
- `runs/193bce0241e94fde87513e384e5ae4d9/run.json`
- `runs/c9ea75ef2cbd415aa5d9863c494c2d97/run.json`
- `tmp/karachi-flood-real-test/scenario_99bc90e4610d4a42a8f56ce52198082d/scenario_summary.json`

## File Structure

- Modify `services/agent_run_service.py`
  - Add AOI resolution query selection that prefers non-bbox `spatial_extent`.
  - Keep direct `bbox(...)` as the execution bbox.
  - Apply disaster/source compatibility before task-driven source selection mutates the executable plan.
  - Add a bounded source fallback hook around task-driven input materialization failures.
- Modify `agent/retriever.py`
  - Align planning context AOI extraction with the run service by preferring non-bbox `spatial_extent`.
  - Surface `resolved_aoi` and direct bbox consistently in retrieval context.
- Modify `services/scenario_run_service.py`
  - Expand implicit flood scenarios to bounded child jobs.
  - Refresh child results after `create_run` when the configured agent service executes asynchronously.
  - Recompute scenario phase and reports from final or freshly inspected child states.
- Modify `tests/test_agent_run_service_enhancements.py`
  - Add AOI regression tests for non-bbox `spatial_extent`.
  - Add disaster-compatible source selection tests.
  - Add source materialization fallback tests at the run-service boundary.
- Modify `tests/test_scenario_run_service.py`
  - Add implicit flood task expansion tests.
  - Add final-child-summary refresh tests.
- Modify `tests/test_input_acquisition_service.py`
  - Add manifest assertions for attempted source fallback with explicit request bbox.
- Optional docs update in `docs/no-ui-agent-operations.md`
  - Document that free-text scenario locations should be placed in `spatial_extent`, and direct bbox remains supported.

---

### Task 1: Resolve AOI From `spatial_extent` Before Planning And Input Materialization

**Files:**
- Modify: `services/agent_run_service.py`
- Modify: `agent/retriever.py`
- Test: `tests/test_agent_run_service_enhancements.py`

- [ ] **Step 1: Write the failing test for non-bbox `spatial_extent` AOI resolution**

Append this test near `test_agent_run_service_resolves_nairobi_before_input_materialization` in `tests/test_agent_run_service_enhancements.py`:

```python
def test_agent_run_service_resolves_named_spatial_extent_before_input_materialization(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "karachi_osm.shp"
    ref_shp = tmp_path / "karachi_ref.shp"
    fused_shp = tmp_path / "karachi_fused.shp"
    artifact_zip = tmp_path / "karachi_artifact.zip"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")
    _write_minimal_polygon_shapefile(fused_shp)
    artifact_zip.write_bytes(b"zip")

    plan = _build_plan(workflow_id="wf_karachi_named_spatial_extent", revision=1)
    plan.trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="巴基斯坦卡拉奇市发生洪涝灾害，请执行地理空间矢量数据融合。",
        disaster_type="flood",
        spatial_extent="Karachi, Pakistan",
    )
    plan.tasks[0].input.data_source_id = "catalog.flood.building"

    prepared_dir = tmp_path / "prepared_karachi"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    resolved_inputs = ResolvedRunInputs(
        osm_zip_path=prepared_dir / "osm.zip",
        ref_zip_path=prepared_dir / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.flood.building",
        cache_hit=False,
        version_token="pk-karachi-v1",
    )
    resolved_inputs.osm_zip_path.write_bytes(b"osm")
    resolved_inputs.ref_zip_path.write_bytes(b"ref")

    karachi_aoi = ResolvedAOI(
        query="Karachi, Pakistan",
        display_name="Karachi Division, Sindh, Pakistan",
        country_name="Pakistan",
        country_code="pk",
        bbox=(66.2862312, 24.4273517, 67.5827753, 25.676796),
        confidence=0.657,
        selection_reason="single_candidate",
        candidates=tuple(),
    )
    resolve_queries: list[str] = []
    captured: dict[str, object] = {}

    def fake_resolve(query: str) -> ResolvedAOI:
        resolve_queries.append(query)
        return karachi_aoi

    def fake_resolve_task_driven_inputs(**kwargs):
        captured.update(kwargs)
        return resolved_inputs

    monkeypatch.setattr(service.aoi_resolution_service, "resolve", fake_resolve)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service.input_acquisition_service, "resolve_task_driven_inputs", fake_resolve_task_driven_inputs)
    monkeypatch.setattr(
        "services.agent_run_service.validate_zip_has_shapefile",
        lambda zip_path, *_args, **_kwargs: osm_shp if Path(zip_path).name.startswith("osm") else ref_shp,
    )
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: fused_shp)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(
                type=RunTriggerType.user_query,
                content="巴基斯坦卡拉奇市发生洪涝灾害，请执行地理空间矢量数据融合。",
                disaster_type="flood",
                spatial_extent="Karachi, Pakistan",
            ),
            target_crs="EPSG:32643",
            field_mapping={},
            debug=False,
            input_strategy=RunInputStrategy.task_driven_auto,
        ),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert resolve_queries == ["Karachi, Pakistan"]
    assert captured["resolved_aoi"] == karachi_aoi
    assert captured["request_bbox"] == karachi_aoi.bbox

    audit_events = service.get_audit_events(status.run_id)
    aoi_event = next(event for event in audit_events if event.kind == "aoi_resolved")
    assert aoi_event.details["query"] == "Karachi, Pakistan"
    resolved_event = next(event for event in audit_events if event.kind == "task_inputs_resolved")
    assert resolved_event.details["resolved_aoi"]["country_code"] == "pk"
```

- [ ] **Step 2: Run the failing AOI test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_agent_run_service_enhancements.py::test_agent_run_service_resolves_named_spatial_extent_before_input_materialization
```

Expected: FAIL because `AgentRunService._should_resolve_aoi()` does not resolve when `spatial_extent` is present and is not a direct bbox.

- [ ] **Step 3: Implement AOI query selection in `services/agent_run_service.py`**

Replace the current `_should_resolve_aoi` static method with these two methods, and update `run_planning_stage()` to use `_aoi_resolution_query(request)`:

```python
    @staticmethod
    def _aoi_resolution_query(request: RunCreateRequest) -> str | None:
        if request.input_strategy != RunInputStrategy.task_driven_auto:
            return None
        if request.trigger.type != RunTriggerType.user_query:
            return None

        spatial_extent = (request.trigger.spatial_extent or "").strip()
        if spatial_extent:
            if AgentRunService._parse_bbox(spatial_extent) is not None:
                if request.trigger.force_aoi_resolution:
                    content = (request.trigger.content or "").strip()
                    return content or None
                return None
            return spatial_extent

        content = (request.trigger.content or "").strip()
        if not content:
            return None
        if request.trigger.force_aoi_resolution:
            return content
        if re.search(r"\b(for|in|around|within)\b", content, flags=re.IGNORECASE):
            return content
        return None

    @staticmethod
    def _should_resolve_aoi(request: RunCreateRequest) -> bool:
        return AgentRunService._aoi_resolution_query(request) is not None
```

Then change this block in `run_planning_stage()`:

```python
        resolved_aoi: ResolvedAOI | None = None
        if self._should_resolve_aoi(request):
            try:
                resolved_aoi = self.aoi_resolution_service.resolve(request.trigger.content)
```

to:

```python
        resolved_aoi: ResolvedAOI | None = None
        aoi_query = self._aoi_resolution_query(request)
        if aoi_query is not None:
            try:
                resolved_aoi = self.aoi_resolution_service.resolve(aoi_query)
```

And change the AOI failure event details from:

```python
                        "query": request.trigger.content,
```

to:

```python
                        "query": aoi_query,
```

- [ ] **Step 4: Align planner context AOI query in `agent/retriever.py`**

Replace `_resolve_aoi()` and `_extract_location_query()` in `agent/retriever.py` with:

```python
    def _resolve_aoi(self, trigger: RunTrigger) -> ResolvedAOI | None:
        if self.resolved_aoi_override is not None:
            return self.resolved_aoi_override
        if self.aoi_resolution_service is None:
            return None
        if trigger.type != RunTriggerType.user_query:
            return None
        query = self._extract_location_query(trigger)
        if not query:
            return None
        return self.aoi_resolution_service.resolve(query)

    @staticmethod
    def _extract_location_query(trigger: RunTrigger) -> str | None:
        spatial_extent = (trigger.spatial_extent or "").strip()
        if spatial_extent:
            if PlanningContextBuilder._parse_bbox(spatial_extent) is None:
                return spatial_extent
            content = (trigger.content or "").strip()
            return AOIResolutionService.extract_location_query(content) if content else None

        content = (trigger.content or "").strip()
        if not content:
            return None
        return AOIResolutionService.extract_location_query(content)
```

- [ ] **Step 5: Run AOI regression tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_agent_run_service_enhancements.py::test_agent_run_service_resolves_named_spatial_extent_before_input_materialization `
  tests/test_agent_run_service_enhancements.py::test_agent_run_service_resolves_nairobi_before_input_materialization `
  tests/test_agent_run_service_enhancements.py::test_agent_run_service_prefers_explicit_spatial_extent_but_still_records_aoi_resolution `
  tests/test_agent_run_service_enhancements.py::test_agent_run_service_direct_bbox_run_does_not_force_aoi_resolution
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```powershell
git add services/agent_run_service.py agent/retriever.py tests/test_agent_run_service_enhancements.py
git commit -m "fix: resolve AOI from named scenario spatial extent"
```

---

### Task 2: Expand Implicit Flood Scenarios Into Bounded Child Tasks

**Files:**
- Modify: `services/scenario_run_service.py`
- Test: `tests/test_scenario_run_service.py`

- [ ] **Step 1: Write the failing implicit flood expansion test**

Append this test after `test_build_child_run_specs_propagates_spatial_extent` in `tests/test_scenario_run_service.py`:

```python
def test_build_child_run_specs_expands_implicit_flood_bundle_for_chinese_scenario(tmp_path):
    request = ScenarioRunRequest(
        scenario_name="Karachi flood",
        trigger_content="巴基斯坦卡拉奇市发生洪涝灾害，请作为灾害响应场景执行地理空间矢量数据融合。",
        disaster_type="flood",
        spatial_extent="Karachi, Pakistan",
        output_root=str(tmp_path),
    )

    specs = build_child_run_specs(request)

    assert [spec.job_type for spec in specs] == [JobType.building, JobType.road, JobType.water]
    assert all(spec.disaster_type == "flood" for spec in specs)
    assert all(spec.spatial_extent == "Karachi, Pakistan" for spec in specs)
```

- [ ] **Step 2: Run the failing scenario expansion test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_scenario_run_service.py::test_build_child_run_specs_expands_implicit_flood_bundle_for_chinese_scenario
```

Expected: FAIL because `_scenario_job_types()` defaults to `[JobType.building]`.

- [ ] **Step 3: Implement bounded scenario default job inference**

In `services/scenario_run_service.py`, replace `_scenario_job_types()` with:

```python
def _scenario_job_types(request: ScenarioRunRequest) -> list[JobType]:
    if request.job_types:
        return list(request.job_types)

    content = " ".join(
        part.casefold()
        for part in [request.scenario_name, request.trigger_content, request.disaster_type]
        if str(part or "").strip()
    )
    detected = [job_type for job_type in JobType if job_type.value in content]
    if detected:
        return detected

    if _contains_any(content, ("flood", "洪涝", "洪水", "内涝", "淹没")):
        return [JobType.building, JobType.road, JobType.water]
    if _contains_any(content, ("earthquake", "地震")):
        return [JobType.building, JobType.road]
    if _contains_any(content, ("typhoon", "台风", "风暴")):
        return [JobType.building, JobType.road, JobType.water]
    return [JobType.building]


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)
```

- [ ] **Step 4: Run scenario expansion tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_scenario_run_service.py::test_build_child_run_specs_expands_implicit_flood_bundle_for_chinese_scenario `
  tests/test_scenario_run_service.py::test_build_child_run_specs_expands_building_and_road_tasks `
  tests/test_scenario_run_service.py::test_build_child_run_specs_propagates_spatial_extent
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```powershell
git add services/scenario_run_service.py tests/test_scenario_run_service.py
git commit -m "fix: expand implicit bounded flood scenario tasks"
```

---

### Task 3: Make Disaster-Compatible Source Selection A Hard Constraint

**Files:**
- Modify: `services/agent_run_service.py`
- Test: `tests/test_agent_run_service_enhancements.py`

- [ ] **Step 1: Replace the outdated source-selection expectation**

In `tests/test_agent_run_service_enhancements.py`, find the test that currently asserts:

```python
assert selected.selected_id == "catalog.earthquake.building"
assert service._resolve_task_driven_source_id(plan) == "catalog.earthquake.building"
assert service._extract_alternative_sources(plan) == ["catalog.flood.building"]
```

Replace those assertions with:

```python
assert selected.selected_id == "catalog.flood.building"
assert service._resolve_task_driven_source_id(plan) == "catalog.flood.building"
assert service._extract_alternative_sources(plan) == ["catalog.earthquake.building"]
assert selected.evidence_refs == [
    "context.retrieval.data_sources",
    "policy:deterministic_weighted_sum",
    "policy:disaster_source_compatibility",
]
```

- [ ] **Step 2: Add an explicit generic fallback selection test**

Append this test near the source-selection test:

```python
def test_agent_run_service_allows_generic_source_when_disaster_specific_source_missing(tmp_path: Path) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    plan = _build_plan(workflow_id="wf_generic_source_for_flood", revision=1)
    plan.trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="Karachi flood building fusion",
        disaster_type="flood",
    )
    plan.context["intent"] = {
        "request_input_strategy": RunInputStrategy.task_driven_auto.value,
        "expected_output_type": "dt.building.fused",
    }
    plan.context["retrieval"] = {
        "data_sources": [
            {
                "source_id": "catalog.generic.building",
                "supported_types": ["dt.building.bundle"],
                "disaster_types": ["generic"],
                "quality_score": 0.80,
                "freshness_score": 0.60,
                "source_name": "Generic Building Bundle",
                "source_kind": "catalog",
                "quality_tier": "curated",
                "freshness_category": "snapshot",
                "metadata": {"selectable_now": True, "runtime_status": "runtime_candidate"},
            },
            {
                "source_id": "catalog.earthquake.building",
                "supported_types": ["dt.building.bundle"],
                "disaster_types": ["earthquake", "generic"],
                "quality_score": 0.95,
                "freshness_score": 0.90,
                "source_name": "Earthquake Building Bundle",
                "source_kind": "catalog",
                "quality_tier": "curated",
                "freshness_category": "event_snapshot",
                "metadata": {"selectable_now": True, "runtime_status": "runtime_candidate"},
            },
        ]
    }

    decisions = service._build_planning_decisions(plan)
    selected = next(item for item in decisions if item.decision_type == "data_source_selection")

    assert selected.selected_id == "catalog.generic.building"
    assert service._resolve_task_driven_source_id(plan) == "catalog.generic.building"
```

- [ ] **Step 3: Run the failing source-selection tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_agent_run_service_enhancements.py::test_agent_run_service_prefers_compatible_task_driven_source_over_plan_source `
  tests/test_agent_run_service_enhancements.py::test_agent_run_service_allows_generic_source_when_disaster_specific_source_missing
```

Expected: FAIL because source selection currently ranks earthquake higher than flood when scores are close.

- [ ] **Step 4: Implement disaster compatibility helpers**

In `services/agent_run_service.py`, add these methods near `_extract_task_driven_compatible_sources()`:

```python
    @staticmethod
    def _source_disaster_types(raw: Dict[str, Any]) -> set[str]:
        direct = raw.get("disaster_types")
        values: list[object] = []
        if isinstance(direct, list):
            values.extend(direct)
        metadata = raw.get("metadata")
        if isinstance(metadata, dict):
            meta_values = metadata.get("disaster_types")
            if isinstance(meta_values, list):
                values.extend(meta_values)
            scenario_focus = metadata.get("scenario_focus")
            if scenario_focus:
                values.append(scenario_focus)
        source_id = str(raw.get("source_id") or "").casefold()
        for known in ("flood", "earthquake", "typhoon", "generic"):
            if known in source_id:
                values.append(known)
        return {str(value).strip().casefold() for value in values if str(value).strip()}

    @staticmethod
    def _filter_disaster_compatible_sources(plan: WorkflowPlan, sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        disaster_type = str(getattr(plan.trigger, "disaster_type", "") or "").strip().casefold()
        if not disaster_type:
            return sources
        exact = [raw for raw in sources if disaster_type in AgentRunService._source_disaster_types(raw)]
        if exact:
            return exact
        generic = [raw for raw in sources if "generic" in AgentRunService._source_disaster_types(raw)]
        return generic or sources
```

- [ ] **Step 5: Apply compatibility filtering in source resolution and alternatives**

In `_resolve_task_driven_source_id()`, change:

```python
        compatible_sources = AgentRunService._extract_task_driven_compatible_sources(plan)
```

to:

```python
        compatible_sources = AgentRunService._filter_disaster_compatible_sources(
            plan,
            AgentRunService._extract_task_driven_compatible_sources(plan),
        )
```

In `_extract_alternative_sources()`, change:

```python
        compatible_sources = AgentRunService._extract_task_driven_compatible_sources(plan)
```

to:

```python
        compatible_sources = AgentRunService._filter_disaster_compatible_sources(
            plan,
            AgentRunService._extract_task_driven_compatible_sources(plan),
        )
```

In `_build_data_source_selection_decision()`, change:

```python
        compatible_task_driven_sources = self._extract_task_driven_compatible_sources(plan)
```

to:

```python
        compatible_task_driven_sources = self._filter_disaster_compatible_sources(
            plan,
            self._extract_task_driven_compatible_sources(plan),
        )
```

And change the evidence refs block from:

```python
        decision = self.policy_engine.select("data_source_selection", candidates).model_copy(
            update={"evidence_refs": ["context.retrieval.data_sources", "policy:deterministic_weighted_sum"]}
        )
```

to:

```python
        evidence_refs = ["context.retrieval.data_sources", "policy:deterministic_weighted_sum"]
        if str(getattr(plan.trigger, "disaster_type", "") or "").strip():
            evidence_refs.append("policy:disaster_source_compatibility")
        decision = self.policy_engine.select("data_source_selection", candidates).model_copy(
            update={"evidence_refs": evidence_refs}
        )
```

- [ ] **Step 6: Run source-selection regression tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_agent_run_service_enhancements.py::test_agent_run_service_prefers_compatible_task_driven_source_over_plan_source `
  tests/test_agent_run_service_enhancements.py::test_agent_run_service_allows_generic_source_when_disaster_specific_source_missing
```

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```powershell
git add services/agent_run_service.py tests/test_agent_run_service_enhancements.py
git commit -m "fix: prefer disaster-compatible task driven sources"
```

---

### Task 4: Recover From AOI Source Coverage Failures With Bounded Fallback Evidence

**Files:**
- Modify: `services/agent_run_service.py`
- Test: `tests/test_agent_run_service_enhancements.py`
- Test: `tests/test_input_acquisition_service.py`

- [ ] **Step 1: Write the run-service fallback test**

Append this test near existing fallback/replan tests in `tests/test_agent_run_service_enhancements.py`:

```python
def test_agent_run_service_retries_task_driven_source_alternative_after_source_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "fallback_osm.shp"
    ref_shp = tmp_path / "fallback_ref.shp"
    fused_shp = tmp_path / "fallback_fused.shp"
    artifact_zip = tmp_path / "fallback_artifact.zip"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")
    _write_minimal_polygon_shapefile(fused_shp)
    artifact_zip.write_bytes(b"zip")

    plan = _build_plan(workflow_id="wf_source_missing_fallback", revision=1)
    plan.trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="Karachi flood building fusion",
        disaster_type="flood",
        spatial_extent="bbox(66.2862312,24.4273517,67.5827753,25.676796)",
    )
    plan.context["intent"] = {
        "request_input_strategy": RunInputStrategy.task_driven_auto.value,
        "expected_output_type": "dt.building.fused",
    }
    plan.context["retrieval"] = {
        "data_sources": [
            {
                "source_id": "catalog.flood.building",
                "supported_types": ["dt.building.bundle"],
                "disaster_types": ["flood", "generic"],
                "quality_score": 0.86,
                "freshness_score": 0.74,
                "metadata": {"selectable_now": True, "runtime_status": "runtime_candidate"},
            },
            {
                "source_id": "catalog.generic.building",
                "supported_types": ["dt.building.bundle"],
                "disaster_types": ["generic"],
                "quality_score": 0.75,
                "freshness_score": 0.50,
                "metadata": {"selectable_now": True, "runtime_status": "runtime_candidate"},
            },
        ]
    }
    plan.tasks[0].input.data_source_id = "catalog.flood.building"

    prepared_dir = tmp_path / "prepared_fallback"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    resolved_inputs = ResolvedRunInputs(
        osm_zip_path=prepared_dir / "osm.zip",
        ref_zip_path=prepared_dir / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.generic.building",
        selected_source_id="catalog.generic.building",
        fallback_from_source_id="catalog.flood.building",
        cache_hit=False,
        version_token="generic-v1",
        component_coverage={"raw.osm.building": {"feature_count": 12, "coverage_status": "available"}},
    )
    resolved_inputs.osm_zip_path.write_bytes(b"osm")
    resolved_inputs.ref_zip_path.write_bytes(b"ref")

    resolve_calls: list[str] = []

    def fake_resolve_task_driven_inputs(**kwargs):
        resolve_calls.append(kwargs["source_id"])
        if kwargs["source_id"] == "catalog.flood.building":
            raise ValueError(
                "task-driven input materialization failed for catalog.flood.building: "
                "fault=SOURCE_MISSING; error=AOI-scoped bundle has empty source coverage"
            )
        return resolved_inputs

    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service.input_acquisition_service, "resolve_task_driven_inputs", fake_resolve_task_driven_inputs)
    monkeypatch.setattr(
        "services.agent_run_service.validate_zip_has_shapefile",
        lambda zip_path, *_args, **_kwargs: osm_shp if Path(zip_path).name.startswith("osm") else ref_shp,
    )
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: fused_shp)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(
                type=RunTriggerType.user_query,
                content="Karachi flood building fusion",
                disaster_type="flood",
                spatial_extent="bbox(66.2862312,24.4273517,67.5827753,25.676796)",
            ),
            target_crs="EPSG:32643",
            field_mapping={},
            debug=False,
            input_strategy=RunInputStrategy.task_driven_auto,
        ),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert resolve_calls == ["catalog.flood.building", "catalog.generic.building"]
    fallback_event = next(event for event in service.get_audit_events(status.run_id) if event.kind == "source_fallback_selected")
    assert fallback_event.details["fallback_from_source_id"] == "catalog.flood.building"
    assert fallback_event.details["selected_source_id"] == "catalog.generic.building"
```

- [ ] **Step 2: Run the failing fallback test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_agent_run_service_enhancements.py::test_agent_run_service_retries_task_driven_source_alternative_after_source_missing
```

Expected: FAIL because `_resolve_execution_inputs()` does not retry alternatives after `SOURCE_MISSING`.

- [ ] **Step 3: Implement bounded source retry in `_resolve_execution_inputs()`**

In `services/agent_run_service.py`, replace the single call to `resolve_task_driven_inputs()` inside `_resolve_execution_inputs()` with:

```python
        request_bbox = self._resolve_request_bbox(request, resolved_aoi=resolved_aoi)
        source_candidates = [source_id]
        for alternative in self._extract_alternative_sources(plan):
            if alternative not in source_candidates:
                source_candidates.append(alternative)

        last_error: Exception | None = None
        for candidate_source_id in source_candidates:
            try:
                resolved = self.input_acquisition_service.resolve_task_driven_inputs(
                    request=request,
                    source_id=candidate_source_id,
                    required_output_type=required_output_type,
                    input_dir=input_dir,
                    request_bbox=request_bbox,
                    resolved_aoi=resolved_aoi,
                )
                if candidate_source_id != source_id and resolved.fallback_from_source_id is None:
                    resolved = ResolvedRunInputs(
                        osm_zip_path=resolved.osm_zip_path,
                        ref_zip_path=resolved.ref_zip_path,
                        source_mode=resolved.source_mode,
                        source_id=resolved.source_id,
                        cache_hit=resolved.cache_hit,
                        version_token=resolved.version_token,
                        selected_source_id=resolved.selected_source_id or candidate_source_id,
                        fallback_from_source_id=source_id,
                        component_coverage=resolved.component_coverage,
                        manifest_path=resolved.manifest_path,
                    )
                return resolved.osm_zip_path, resolved.ref_zip_path, resolved
            except ValueError as exc:
                last_error = exc
                message = str(exc)
                if "SOURCE_MISSING" not in message and "empty source coverage" not in message:
                    raise
                if candidate_source_id == source_candidates[-1]:
                    raise

        if last_error is not None:
            raise last_error
        raise ValueError("task-driven input strategy could not materialize any candidate source")
```

- [ ] **Step 4: Run fallback and input-acquisition manifest tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_agent_run_service_enhancements.py::test_agent_run_service_retries_task_driven_source_alternative_after_source_missing `
  tests/test_input_acquisition_service.py::test_input_acquisition_manifest_records_provider_attempts_and_component_coverage `
  tests/test_input_acquisition_service.py::test_input_acquisition_writes_manifest_for_failed_provider
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```powershell
git add services/agent_run_service.py tests/test_agent_run_service_enhancements.py tests/test_input_acquisition_service.py
git commit -m "fix: retry task driven source alternatives on empty coverage"
```

---

### Task 5: Refresh Scenario Summaries From Final Child Run State

**Files:**
- Modify: `services/scenario_run_service.py`
- Test: `tests/test_scenario_run_service.py`

- [ ] **Step 1: Add a fake async agent service for scenario refresh tests**

Append this helper after `_FakeAgentRunService` in `tests/test_scenario_run_service.py`:

```python
class _QueuedThenSucceededAgentRunService(_FakeAgentRunService):
    def create_run(self, *, request, osm_zip_name, osm_zip_bytes, ref_zip_name, ref_zip_bytes):
        run_id = f"run-{request.job_type.value}"
        queued = RunStatus(
            run_id=run_id,
            job_type=request.job_type,
            trigger=request.trigger,
            phase=RunPhase.queued,
            progress=0,
            target_crs=request.target_crs or "EPSG:32631",
            debug=False,
            created_at="2026-04-21T00:00:00+00:00",
        )
        succeeded = queued.model_copy(
            update={
                "phase": RunPhase.succeeded,
                "progress": 100,
                "finished_at": "2026-04-21T00:00:03+00:00",
            }
        )
        self.statuses[run_id] = succeeded
        self.plans[run_id] = _make_plan(request.job_type)
        self.events[run_id] = _make_events(request.job_type)
        artifact = self.tmp_path / f"{run_id}.zip"
        artifact.write_bytes(b"zip")
        self.artifacts[run_id] = artifact
        return queued

    def get_run(self, run_id: str):
        return self.statuses.get(run_id)
```

- [ ] **Step 2: Write the failing scenario refresh test**

Append this test after `test_scenario_run_service_writes_summary_and_reports`:

```python
def test_scenario_run_service_refreshes_child_status_before_summary(tmp_path):
    service = ScenarioRunService(agent_run_service=_QueuedThenSucceededAgentRunService(tmp_path))

    response = service.create_scenario_run(
        ScenarioRunRequest(
            scenario_name="Karachi flood",
            trigger_content="巴基斯坦卡拉奇市发生洪涝灾害，请作为灾害响应场景执行地理空间矢量数据融合。",
            disaster_type="flood",
            job_types=[JobType.building],
            spatial_extent="Karachi, Pakistan",
            output_root=str(tmp_path / "scenarios"),
        )
    )

    scenario_dir = Path(response.output_dir)
    summary = json.loads((scenario_dir / "scenario_summary.json").read_text(encoding="utf-8"))
    assert response.phase == ScenarioPhase.succeeded
    assert summary["child_runs"][0]["phase"] == RunPhase.succeeded.value
    assert summary["workflow_traces"][0]["steps"]
    assert summary["final_outputs"]
```

- [ ] **Step 3: Run the failing scenario refresh test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_scenario_run_service.py::test_scenario_run_service_refreshes_child_status_before_summary
```

Expected: FAIL because `_run_child()` returns the immediate queued status and does not refresh final evidence.

- [ ] **Step 4: Implement child result refresh in `ScenarioRunService`**

In `services/scenario_run_service.py`, replace the success branch in `_run_child()`:

```python
            run_id = status.run_id
            return {
                "run_id": run_id,
                "job_type": spec.job_type.value,
                "phase": status.phase.value,
                "status": status,
                "plan": self.agent_run_service.get_plan(run_id),
                "audit_events": self.agent_run_service.get_audit_events(run_id),
                "artifact_path": self.agent_run_service.get_artifact_path(run_id),
            }
```

with:

```python
            return self._inspect_child_result(run_id=status.run_id, job_type=spec.job_type)
```

Then add this method to `ScenarioRunService`:

```python
    def _inspect_child_result(self, *, run_id: str, job_type: JobType) -> dict[str, Any]:
        current_status = None
        get_run = getattr(self.agent_run_service, "get_run", None)
        if callable(get_run):
            current_status = get_run(run_id)
        if current_status is None:
            current_status = self.agent_run_service.get_run(run_id) if hasattr(self.agent_run_service, "get_run") else None
        status = current_status
        phase = status.phase.value if status is not None else ScenarioPhase.failed.value
        return {
            "run_id": run_id,
            "job_type": job_type.value,
            "phase": phase,
            "status": status,
            "plan": self.agent_run_service.get_plan(run_id),
            "audit_events": self.agent_run_service.get_audit_events(run_id),
            "artifact_path": self.agent_run_service.get_artifact_path(run_id),
            "error": getattr(status, "error", None) if status is not None else None,
        }
```

If the duplicate `get_run` branch looks awkward after implementation, simplify it to:

```python
        get_run = getattr(self.agent_run_service, "get_run", None)
        status = get_run(run_id) if callable(get_run) else None
```

- [ ] **Step 5: Update phase computation to distinguish all failed from partial**

Replace `_phase_from_child_results()` with:

```python
def _phase_from_child_results(child_results: list[dict[str, Any]]) -> ScenarioPhase:
    if not child_results:
        return ScenarioPhase.failed
    phases = [str(result.get("phase")) for result in child_results]
    if all(phase == RunPhase.succeeded.value for phase in phases):
        return ScenarioPhase.succeeded
    if all(phase == RunPhase.failed.value or phase == ScenarioPhase.failed.value for phase in phases):
        return ScenarioPhase.failed
    return ScenarioPhase.partial
```

- [ ] **Step 6: Run scenario service tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_scenario_run_service.py
```

Expected: PASS.

- [ ] **Step 7: Commit Task 5**

```powershell
git add services/scenario_run_service.py tests/test_scenario_run_service.py
git commit -m "fix: refresh scenario evidence from child run state"
```

---

### Task 6: End-To-End Karachi Regression Harness

**Files:**
- Create: `tests/test_karachi_flood_regression.py`

- [ ] **Step 1: Create a focused regression test with fakes**

Create `tests/test_karachi_flood_regression.py` with:

```python
from __future__ import annotations

from pathlib import Path

from schemas.agent import RunEvent, RunPhase, RunStatus, RunTrigger, RunTriggerType, ValidationReport, WorkflowPlan, WorkflowTask, WorkflowTaskInput, WorkflowTaskOutput
from schemas.fusion import JobType
from schemas.scenario import ScenarioRunRequest
from services.scenario_run_service import ScenarioRunService


def test_karachi_chinese_flood_scenario_expands_and_records_finished_children(tmp_path: Path) -> None:
    service = ScenarioRunService(agent_run_service=_KarachiFakeAgentRunService(tmp_path))

    response = service.create_scenario_run(
        ScenarioRunRequest(
            scenario_name="Karachi flood",
            trigger_content="巴基斯坦卡拉奇市发生洪涝灾害，请作为灾害响应场景执行地理空间矢量数据融合。",
            disaster_type="flood",
            spatial_extent="Karachi, Pakistan",
            output_root=str(tmp_path / "scenarios"),
        )
    )

    assert response.phase.value == "succeeded"
    assert response.child_run_ids == ["run-building", "run-road", "run-water"]
    summary_path = Path(response.output_dir) / "scenario_summary.json"
    assert summary_path.exists()
    summary_text = summary_path.read_text(encoding="utf-8")
    assert "run-building" in summary_text
    assert "run-road" in summary_text
    assert "run-water" in summary_text


class _KarachiFakeAgentRunService:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.statuses: dict[str, RunStatus] = {}
        self.plans: dict[str, WorkflowPlan] = {}
        self.events: dict[str, list[RunEvent]] = {}
        self.artifacts: dict[str, Path] = {}

    def create_run(self, *, request, osm_zip_name, osm_zip_bytes, ref_zip_name, ref_zip_bytes):
        run_id = f"run-{request.job_type.value}"
        status = RunStatus(
            run_id=run_id,
            job_type=request.job_type,
            trigger=request.trigger,
            phase=RunPhase.succeeded,
            progress=100,
            target_crs=request.target_crs or "EPSG:32643",
            debug=False,
            created_at="2026-06-01T00:00:00+00:00",
            finished_at="2026-06-01T00:00:03+00:00",
        )
        self.statuses[run_id] = status
        self.plans[run_id] = _make_plan(request.job_type)
        self.events[run_id] = _make_events(request.job_type)
        artifact = self.tmp_path / f"{run_id}.zip"
        artifact.write_bytes(b"zip")
        self.artifacts[run_id] = artifact
        return status

    def get_run(self, run_id: str):
        return self.statuses.get(run_id)

    def get_plan(self, run_id: str):
        return self.plans.get(run_id)

    def get_audit_events(self, run_id: str):
        return list(self.events.get(run_id, []))

    def get_artifact_path(self, run_id: str):
        return self.artifacts.get(run_id)


def _make_plan(job_type: JobType) -> WorkflowPlan:
    return WorkflowPlan(
        workflow_id=f"wf-karachi-{job_type.value}",
        trigger=RunTrigger(
            type=RunTriggerType.user_query,
            content="巴基斯坦卡拉奇市发生洪涝灾害，请作为灾害响应场景执行地理空间矢量数据融合。",
            disaster_type="flood",
            spatial_extent="Karachi, Pakistan",
        ),
        context={
            "intent": {
                "resolved_aoi": {
                    "display_name": "Karachi Division, Sindh, Pakistan",
                    "country_code": "pk",
                    "bbox": [66.2862312, 24.4273517, 67.5827753, 25.676796],
                }
            },
            "retrieval": {
                "candidate_patterns": [{"pattern_id": f"wp.flood.{job_type.value}", "success_rate": 0.9}],
                "data_sources": [{"source_id": f"catalog.flood.{job_type.value}"}],
            },
            "plan_revision": 1,
        },
        tasks=[
            WorkflowTask(
                step=1,
                name=f"{job_type.value}_fusion",
                description="fusion",
                algorithm_id=f"algo.fusion.{job_type.value}.v1",
                input=WorkflowTaskInput(
                    data_type_id=f"dt.{job_type.value}.bundle",
                    data_source_id=f"catalog.flood.{job_type.value}",
                ),
                output=WorkflowTaskOutput(data_type_id=f"dt.{job_type.value}.fused"),
                kg_validated=True,
            )
        ],
        expected_output=f"{job_type.value} fused",
        validation=ValidationReport(valid=True),
    )


def _make_events(job_type: JobType) -> list[RunEvent]:
    return [
        RunEvent(
            timestamp="2026-06-01T00:00:00+00:00",
            kind="aoi_resolved",
            phase=RunPhase.planning,
            message="aoi",
            details={
                "query": "Karachi, Pakistan",
                "country_code": "pk",
                "bbox": [66.2862312, 24.4273517, 67.5827753, 25.676796],
            },
        ),
        RunEvent(
            timestamp="2026-06-01T00:00:01+00:00",
            kind="task_inputs_resolved",
            phase=RunPhase.running,
            message="inputs",
            details={
                "source_id": f"catalog.flood.{job_type.value}",
                "selected_source_id": f"catalog.flood.{job_type.value}",
                "component_coverage": {},
            },
        ),
        RunEvent(
            timestamp="2026-06-01T00:00:02+00:00",
            kind="run_succeeded",
            phase=RunPhase.succeeded,
            message="succeeded",
        ),
    ]
```

- [ ] **Step 2: Run the focused regression test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_karachi_flood_regression.py
```

Expected: PASS after Tasks 2 and 5 are complete.

- [ ] **Step 3: Run the integrated hardening suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_scenario_run_service.py `
  tests/test_karachi_flood_regression.py `
  tests/test_agent_run_service_enhancements.py::test_agent_run_service_resolves_named_spatial_extent_before_input_materialization `
  tests/test_agent_run_service_enhancements.py::test_agent_run_service_prefers_compatible_task_driven_source_over_plan_source `
  tests/test_agent_run_service_enhancements.py::test_agent_run_service_retries_task_driven_source_alternative_after_source_missing `
  tests/test_input_acquisition_service.py::test_input_acquisition_manifest_records_provider_attempts_and_component_coverage
```

Expected: PASS.

- [ ] **Step 4: Commit Task 6**

```powershell
git add tests/test_karachi_flood_regression.py
git commit -m "test: cover chinese karachi flood scenario regression"
```

---

### Task 7: Real Runtime Verification Against Karachi Flood

**Files:**
- No source edits.
- Runtime outputs under `tmp/karachi-flood-real-test-after-hardening/` and `runs/<run_id>/`.

- [ ] **Step 1: Start isolated runtime**

Run:

```powershell
.\.venv\Scripts\python.exe scripts\start_local.py --port 8012
```

Expected:

```text
KG contract: PASS
API: http://127.0.0.1:8012
```

- [ ] **Step 2: Submit the original Chinese Karachi flood scenario**

Run:

```powershell
$payload = @{
  scenario_name = 'Karachi flood hardening verification'
  trigger_content = '巴基斯坦卡拉奇市发生洪涝灾害，请作为灾害响应场景执行地理空间矢量数据融合，评估受洪涝影响区域相关的可用矢量数据。'
  disaster_type = 'flood'
  spatial_extent = 'Karachi, Pakistan'
  output_root = 'E:\vscode\fusionAgent\tmp\karachi-flood-real-test-after-hardening'
  metadata = @{ verification = 'karachi-flood-runtime-hardening' }
} | ConvertTo-Json -Depth 8
Invoke-RestMethod -Method Post `
  -Uri 'http://127.0.0.1:8012/api/v2/scenario-runs' `
  -ContentType 'application/json; charset=utf-8' `
  -Body $payload `
  -TimeoutSec 1800 | ConvertTo-Json -Depth 8
```

Expected:

- The response contains 3 child run ids for `building`, `road`, and `water`.
- Scenario phase is `succeeded` or `partial` only if a child source is unavailable and the report records the final failed child evidence.
- No child run fails with `Multi-source tiled building runtime requires an AOI bbox.`
- No building child selects `catalog.earthquake.building` for a flood request when `catalog.flood.building` is available.

- [ ] **Step 3: Inspect evidence**

Run:

```powershell
$scenarioDir = Get-ChildItem -Directory 'E:\vscode\fusionAgent\tmp\karachi-flood-real-test-after-hardening' |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1
Get-Content -LiteralPath (Join-Path $scenarioDir.FullName 'scenario_summary.json') -Raw
Get-Content -LiteralPath (Join-Path $scenarioDir.FullName 'documents\scenario_report.zh.md') -Raw
```

Expected:

- `scenario_summary.json` includes non-empty `workflow_traces`.
- `source_coverage` includes final child source evidence where inputs were resolved.
- The Chinese report lists final child outcomes and does not show `最终执行工作流 - none` when child runs completed.

- [ ] **Step 4: Stop isolated runtime**

Run:

```powershell
Get-Process | Where-Object { $_.Path -like '*fusionAgent*' -or $_.ProcessName -in @('python','python3') } |
  Where-Object { $_.StartTime -gt (Get-Date).AddHours(-4) } |
  Select-Object Id,ProcessName,Path,StartTime
```

Stop only the API, worker, and scheduler PIDs printed by `scripts/start_local.py` for this verification run:

```powershell
Stop-Process -Id <api-pid>,<worker-pid>,<scheduler-pid> -Force
```

Expected: `http://127.0.0.1:8012/api/v2/runtime` is unreachable afterward.

- [ ] **Step 5: Commit verification evidence pointer if needed**

Do not commit raw `runs/` directories. If a small evidence pointer is needed, create a Markdown summary under `docs/superpowers/specs/` with run ids and paths, then:

```powershell
git add docs/superpowers/specs/<created-evidence-summary>.md
git commit -m "docs: record karachi flood hardening verification"
```

---

## Final Verification

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_scenario_run_service.py `
  tests/test_karachi_flood_regression.py `
  tests/test_agent_run_service_enhancements.py `
  tests/test_input_acquisition_service.py
```

Expected: PASS.

Then run the isolated real runtime verification in Task 7. The completion claim is valid only if both the focused pytest suite and the real Karachi scenario verification have fresh passing evidence.

## Self-Review

Spec coverage:

- AOI/bbox failure is covered by Task 1.
- Missing flood task expansion is covered by Task 2.
- Earthquake source selection in flood scenario is covered by Task 3.
- Empty AOI source coverage fallback is covered by Task 4.
- Scenario report/summary final-state mismatch is covered by Task 5.
- Chinese Karachi scenario regression is covered by Task 6 and Task 7.

Placeholder scan:

- No `TBD`, `TODO`, `implement later`, or open-ended test instructions are present.
- Every code-changing step names concrete files and code snippets.

Type consistency:

- `RunCreateRequest`, `RunTrigger`, `RunInputStrategy`, `RunPhase`, `ResolvedAOI`, and `ResolvedRunInputs` match existing imports used in `tests/test_agent_run_service_enhancements.py`.
- `ScenarioRunRequest`, `ScenarioPhase`, and `JobType` match existing imports used in `tests/test_scenario_run_service.py`.
- New helper names are local to their modified files: `_aoi_resolution_query`, `_source_disaster_types`, `_filter_disaster_compatible_sources`, `_inspect_child_result`, and `_contains_any`.
