# Agentic Any-Region Fusion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept a natural-language region request, resolve the AOI with the planner's LLM+KG flow, automatically download and clip source data for that AOI, and run the existing building/road fusion adapters end to end.

**Architecture:** Add a dedicated AOI resolution service before planning, enrich KG-driven planner context with AOI and coverage evidence, generalize source materialization so raw data can be downloaded and clipped for the resolved AOI, and keep `WorkflowPlanner` as the only component that turns context into a workflow plan. Runtime services stay constrained tools; the LLM still decides the plan, the KG still supplies candidate patterns and data-source metadata, and the execution layer still performs the actual download/clip/fuse steps.

**Tech Stack:** Python 3.9+, FastAPI, Pydantic, GeoPandas, Shapely, pytest, existing LLM provider abstractions, existing KG repository, existing artifact/input acquisition services

---

## File Structure

- `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\services\aoi_resolution_service.py`
  New AOI resolver that turns natural-language location requests into structured AOI candidates and a selected AOI.
- `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\agent\retriever.py`
  Planner-context builder gets AOI and source-coverage evidence.
- `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\agent\planner.py`
  Planner prompt and normalized plan context must preserve AOI evidence.
- `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\services\source_asset_service.py`
  Generalize source materialization from Burundi-only to AOI-aware country/global provider selection.
- `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\services\raw_vector_source_service.py`
  Allow runtime raw-source resolution to fall back to the generalized source-asset service when local `Data/` paths are insufficient.
- `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\services\input_acquisition_service.py`
  Accept an explicit AOI bbox from the resolver instead of relying only on `trigger.spatial_extent`.
- `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\services\local_bundle_catalog.py`
  Keep bundle assembly but ensure it clips and materializes AOI-scoped raw inputs.
- `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\services\agent_run_service.py`
  Orchestrate AOI resolution, planning, and input materialization in the runtime.
- `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\api\routers\runs_v2.py`
  No API shape change is required for the first pass, but the runtime contract must keep natural-language requests working through `trigger.content`.
- `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\kg\source_catalog.py`
  Add source metadata that helps the planner reason about materialization scope and provider family.
- `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\tests\test_aoi_resolution_service.py`
  New unit tests for AOI parsing and ambiguity handling.
- `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\tests\test_source_asset_service.py`
  Expand coverage for region-aware OSM and reference materialization.
- `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\tests\test_planner_context.py`
  Update planner-context assertions to include AOI and coverage evidence.
- `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\tests\test_agent_run_service_enhancements.py`
  Add runtime tests for AOI-aware planning and task-driven input preparation.
- `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\tests\test_api_v2_integration.py`
  Add API-level integration coverage for a natural-language Nairobi request.
- `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\scripts\smoke_agentic_region.py`
  New helper script for live natural-language region runs and Nairobi validation.
- `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\docs\local-direct-run.md`
- `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\README.md`
- `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\README.en.md`
- `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\docs\v2-operations.md`
  Docs and operator guidance for the new region-based flow.

---

## Task 1: Add AOI Resolution And Planner-Context Enrichment

**Files:**
- Create: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\services\aoi_resolution_service.py`
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\agent\retriever.py`
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\agent\planner.py`
- Test: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\tests\test_aoi_resolution_service.py`
- Test: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\tests\test_planner_context.py`

- [ ] **Step 1: Write the failing tests for AOI selection and planner context**

```python
class _StubGeocoder:
    def __init__(self, results):
        self.results = results

    def search(self, query: str):
        return list(self.results)


def test_aoi_resolution_service_selects_nairobi_when_query_mentions_kenya(monkeypatch):
    service = AOIResolutionService(
        geocoder=_StubGeocoder(
            [
                {
                    "display_name": "Nairobi, Nairobi County, Kenya",
                    "country_name": "Kenya",
                    "country_code": "ke",
                    "admin_level": "county",
                    "bbox": (36.65, -1.45, 37.10, -1.10),
                    "source": "nominatim",
                    "confidence": 0.97,
                    "raw": {"place_id": 101},
                }
            ]
        )
    )
    resolved = service.resolve("fuse building and road data for Nairobi, Kenya")
    assert resolved.display_name == "Nairobi, Nairobi County, Kenya"
    assert resolved.country_code == "ke"
    assert resolved.bbox == (36.65, -1.45, 37.10, -1.10)


def test_aoi_resolution_service_rejects_ambiguous_place_names(monkeypatch):
    service = AOIResolutionService(
        geocoder=_StubGeocoder(
            [
                {
                    "display_name": "Springfield, Illinois, United States",
                    "country_name": "United States",
                    "country_code": "us",
                    "admin_level": "city",
                    "bbox": (-89.75, 39.69, -89.55, 39.85),
                    "source": "nominatim",
                    "confidence": 0.55,
                    "raw": {"place_id": 201},
                },
                {
                    "display_name": "Springfield, Massachusetts, United States",
                    "country_name": "United States",
                    "country_code": "us",
                    "admin_level": "city",
                    "bbox": (-72.66, 42.05, -72.49, 42.16),
                    "source": "nominatim",
                    "confidence": 0.54,
                    "raw": {"place_id": 202},
                },
            ]
        )
    )
    with pytest.raises(AOIAmbiguityError):
        service.resolve("Springfield")


def test_planner_context_includes_resolved_aoi_and_source_coverage_hints():
    provider = CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)
    trigger = RunTrigger(type=RunTriggerType.user_query, content="fuse building and road data for Nairobi, Kenya")
    plan = planner.create_plan(run_id="run-nairobi", job_type=JobType.building, trigger=trigger)
    assert provider.last_context["intent"]["resolved_aoi"]["country_code"] == "ke"
    assert provider.last_context["retrieval"]["source_coverage_hints"]
```

- [ ] **Step 2: Run the tests and confirm they fail for missing AOI support**

Run:

```powershell
python -m pytest -q tests/test_aoi_resolution_service.py tests/test_planner_context.py -k "aoi or resolved_aoi"
```

Expected: FAIL because AOI resolution and context enrichment do not exist yet.

- [ ] **Step 3: Implement the AOI resolver and context enrichment**

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
```

Implement:

- `services/aoi_resolution_service.py`
- `PlanningContextBuilder.build()` additions for `resolved_aoi`
- `WorkflowPlanner._normalize_plan_context()` preservation of AOI evidence

Also define:

```python
class AOIAmbiguityError(ValueError):
    pass
```

- [ ] **Step 4: Re-run the AOI and planner-context tests**

Run:

```powershell
python -m pytest -q tests/test_aoi_resolution_service.py tests/test_planner_context.py -k "aoi or resolved_aoi"
```

Expected: PASS

## Task 2: Generalize Source Materialization For AOI-Scoped Downloads

**Files:**
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\services\source_asset_service.py`
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\kg\source_catalog.py`
- Test: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\tests\test_source_asset_service.py`

- [ ] **Step 1: Write failing tests for Nairobi-scoped source download and clipping**

```python
def test_source_asset_service_materializes_kenya_osm_and_clips_to_nairobi(monkeypatch, tmp_path):
    service = SourceAssetService(repo_root=tmp_path, cache_dir=tmp_path / "cache")
    resolved = service.resolve_raw_source_path(
        "raw.osm.road",
        aoi=ResolvedAOI(
            query="Nairobi, Kenya",
            display_name="Nairobi, Nairobi County, Kenya",
            country_name="Kenya",
            country_code="ke",
            bbox=(36.65, -1.45, 37.10, -1.10),
            confidence=0.97,
            selection_reason="single_high_confidence_candidate",
            candidates=(),
        ),
    )
    assert resolved.source_mode in {"asset_downloaded", "asset_cached"}
    assert resolved.feature_count >= 0


def test_source_asset_service_uses_aoi_bbox_for_reference_source(monkeypatch, tmp_path):
    service = SourceAssetService(repo_root=tmp_path, cache_dir=tmp_path / "cache")
    resolved = service.resolve_raw_source_path(
        "raw.microsoft.building",
        aoi=ResolvedAOI(
            query="Nairobi, Kenya",
            display_name="Nairobi, Nairobi County, Kenya",
            country_name="Kenya",
            country_code="ke",
            bbox=(36.65, -1.45, 37.10, -1.10),
            confidence=0.97,
            selection_reason="single_high_confidence_candidate",
            candidates=(),
        ),
    )
    assert resolved.feature_count > 0
```

- [ ] **Step 2: Run the tests and confirm the current Burundi-only logic fails**

Run:

```powershell
python -m pytest -q tests/test_source_asset_service.py
```

Expected: FAIL because the service is still Burundi-specific.

- [ ] **Step 3: Implement country-aware OSM and AOI-aware reference downloads**

```python
def resolve_raw_source_path(self, source_id: str, *, aoi: ResolvedAOI | None = None) -> SourceAssetResolution:
    if self.prefer_local_data and aoi is not None:
        local_path = self._try_local_path(source_id, aoi=aoi)
        if local_path is not None:
            return self._build_local_resolution(source_id, local_path, aoi)
    if source_id in _GEOFABRIK_LAYER_NAMES:
        return self._resolve_osm_country_bundle(source_id, aoi=aoi)
    if source_id == "raw.microsoft.building":
        return self._resolve_msft_buildings(aoi=aoi)
    raise FileNotFoundError(f"No AOI-aware source asset path available for {source_id}")
```

Implement:

- Geofabrik country bundle selection from AOI country metadata
- AOI-bounded Microsoft building tile filtering
- cache keys that include source id + AOI hash + provider version
- explicit `coverage_empty` status instead of pretending success

- [ ] **Step 4: Re-run the source-asset tests**

Run:

```powershell
python -m pytest -q tests/test_source_asset_service.py
```

Expected: PASS

## Task 3: Wire The Runtime To Resolve AOI, Select Sources, And Acquire AOI-Scoped Inputs

**Files:**
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\services\agent_run_service.py`
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\services\input_acquisition_service.py`
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\services\local_bundle_catalog.py`
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\services\raw_vector_source_service.py`
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\api\routers\runs_v2.py`
- Test: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\tests\test_agent_run_service_enhancements.py`
- Test: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\tests\test_api_v2_integration.py`

- [ ] **Step 1: Write the failing runtime integration test for Nairobi**

```python
def test_agent_run_service_resolves_nairobi_before_input_materialization(tmp_path, monkeypatch):
    service = AgentRunService(base_dir=tmp_path / "runs")
    fused_shp = tmp_path / "fused.shp"
    fused_shp.write_text("dummy", encoding="utf-8")
    artifact_zip = tmp_path / "artifact.zip"
    artifact_zip.write_bytes(b"zip")
    resolved_aoi = ResolvedAOI(
        query="Nairobi, Kenya",
        display_name="Nairobi, Nairobi County, Kenya",
        country_name="Kenya",
        country_code="ke",
        bbox=(36.65, -1.45, 37.10, -1.10),
        confidence=0.97,
        selection_reason="single_high_confidence_candidate",
        candidates=(),
    )
    plan = WorkflowPlan.model_validate({
        "workflow_id": "wf_nairobi",
        "trigger": {"type": "user_query", "content": "fuse building and road data for Nairobi, Kenya"},
        "context": {
            "intent": {"resolved_aoi": {"country_code": "ke", "bbox": [36.65, -1.45, 37.10, -1.10]}},
            "retrieval": {"candidate_patterns": [{"pattern_id": "wp.flood.building.default", "success_rate": 0.91}]},
            "selection_reason": "initial",
            "llm_provider": "mock",
            "plan_revision": 1,
            "planning_mode": "task_driven",
        },
        "tasks": [{
            "step": 1,
            "name": "building_fusion",
            "description": "building fusion",
            "algorithm_id": "algo.fusion.building.v1",
            "input": {"data_type_id": "dt.building.bundle", "data_source_id": "catalog.earthquake.building", "parameters": {}},
            "output": {"data_type_id": "dt.building.fused", "description": ""},
            "depends_on": [],
            "is_transform": False,
            "kg_validated": True,
            "alternatives": ["algo.fusion.building.safe"],
        }],
        "expected_output": "building result",
        "validation": {"valid": True, "inserted_transform_steps": 0, "issues": []},
    })
    resolved_inputs = ResolvedRunInputs(
        osm_zip_path=tmp_path / "prepared" / "osm.zip",
        ref_zip_path=tmp_path / "prepared" / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.earthquake.building",
        cache_hit=False,
        version_token="ke-v1",
    )
    resolved_inputs.osm_zip_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_inputs.osm_zip_path.write_bytes(b"osm")
    resolved_inputs.ref_zip_path.write_bytes(b"ref")
    monkeypatch.setattr(service.aoi_resolution_service, "resolve", lambda query: resolved_aoi)
    monkeypatch.setattr(service.planner, "create_plan", lambda **kwargs: plan)
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service.input_acquisition_service, "resolve_task_driven_inputs", lambda **kwargs: resolved_inputs)
    monkeypatch.setattr(service.executor, "execute_plan", lambda **kwargs: fused_shp)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)
    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(type=RunTriggerType.user_query, content="fuse building and road data for Nairobi, Kenya"),
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
    assert any(event.kind == "aoi_resolved" for event in service.get_audit_events(status.run_id))
    assert any(event.kind == "task_inputs_resolved" for event in service.get_audit_events(status.run_id))
```

- [ ] **Step 2: Run the runtime tests and confirm missing AOI orchestration fails**

Run:

```powershell
python -m pytest -q tests/test_agent_run_service_enhancements.py tests/test_api_v2_integration.py -k "nairobi or aoi or task_driven_auto"
```

Expected: FAIL because runtime orchestration still lacks AOI-aware materialization.

- [ ] **Step 3: Implement AOI-first runtime orchestration and AOI-scoped input acquisition**

```python
resolved_aoi = self.aoi_resolution_service.resolve(request.trigger.content)
plan = self.planner.create_plan(run_id=run_id, job_type=request.job_type, trigger=request.trigger)
osm_zip_path, ref_zip_path, resolved_inputs = self._resolve_execution_inputs(
    request=request,
    plan=plan,
    input_dir=input_dir,
    osm_zip_path=osm_zip_path,
    ref_zip_path=ref_zip_path,
    resolved_aoi=resolved_aoi,
)
```

Implement:

- AOI resolution before planning
- `PlanningContextBuilder` enrichment with AOI and coverage evidence
- optional `request_bbox`/`aoi` parameter passing through input acquisition
- runtime fallback to the generalized source-asset service when local `Data/` is incomplete
- audit events for AOI resolution and source coverage checks

- [ ] **Step 4: Re-run the runtime integration tests**

Run:

```powershell
python -m pytest -q tests/test_agent_run_service_enhancements.py tests/test_api_v2_integration.py -k "nairobi or aoi or task_driven_auto"
```

Expected: PASS

## Task 4: Add Nairobi Live-Run Helper And Update Docs

**Files:**
- Create: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\scripts\smoke_agentic_region.py`
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\docs\local-direct-run.md`
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\docs\v2-operations.md`
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\README.md`
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\README.en.md`
- Test: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\agentic-any-region-fusion\tests\test_smoke_agentic_region.py`

- [ ] **Step 1: Write the failing test for the smoke helper CLI**

```python
def test_smoke_agentic_region_builds_nairobi_request(monkeypatch):
    parsed = parse_args([
        "--base-url", "http://127.0.0.1:8010",
        "--query", "fuse building and road data for Nairobi, Kenya",
        "--job-type", "building",
    ])
    assert parsed.query == "fuse building and road data for Nairobi, Kenya"
```

- [ ] **Step 2: Run the smoke-helper test and confirm it fails before the script exists**

Run:

```powershell
python -m pytest -q tests/test_smoke_agentic_region.py
```

Expected: FAIL because the helper script does not exist yet.

- [ ] **Step 3: Implement the helper and docs**

```powershell
python scripts/smoke_agentic_region.py --base-url http://127.0.0.1:8010 --query "fuse building and road data for Nairobi, Kenya" --timeout 1200
```

Implement:

- a CLI that submits a natural-language run through the existing API
- a wait loop that prints AOI, source ids, run id, and final artifact path
- docs showing the Nairobi example as the canonical validation case

- [ ] **Step 4: Re-run the helper test and the full suite**

Run:

```powershell
python -m pytest -q tests/test_smoke_agentic_region.py
python -m pytest -q
```

Expected: PASS
