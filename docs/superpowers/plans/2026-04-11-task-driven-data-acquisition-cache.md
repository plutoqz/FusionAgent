# Task-Driven Data Acquisition And Cache Reuse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `task-driven` requests run without uploaded ZIP inputs by automatically preparing source bundles, checking cached bundle freshness/version, and reusing or clipping cached bundles before execution.

**Architecture:** Keep the current `planner -> validator -> executor -> healing -> writeback` loop intact. Add a new input-preparation layer ahead of execution that resolves run inputs from either uploaded ZIPs or task-driven auto-acquisition. Reuse the existing artifact registry for cached input bundles by tagging records with input-bundle metadata, and keep the current executor/adapters unchanged by always materializing concrete `osm.zip` and `ref.zip` files before execution.

**Tech Stack:** Python, FastAPI, Pydantic, GeoPandas, existing artifact registry JSON index, pytest

---

## File Structure

### Existing files to modify

- Modify: `E:\vscode\fusionAgent\schemas\agent.py`
- Modify: `E:\vscode\fusionAgent\api\routers\runs_v2.py`
- Modify: `E:\vscode\fusionAgent\services\artifact_registry.py`
- Modify: `E:\vscode\fusionAgent\services\agent_run_service.py`
- Modify: `E:\vscode\fusionAgent\README.md`

### New files to create

- Create: `E:\vscode\fusionAgent\services\input_acquisition_service.py`
- Create: `E:\vscode\fusionAgent\services\local_bundle_catalog.py`
- Create: `E:\vscode\fusionAgent\tests\test_input_acquisition_service.py`

### Existing tests to update

- Modify: `E:\vscode\fusionAgent\tests\test_artifact_registry.py`
- Modify: `E:\vscode\fusionAgent\tests\test_agent_run_service_enhancements.py`
- Modify: `E:\vscode\fusionAgent\tests\test_api_v2_integration.py`

---

### Task 1: Add Run Input Strategy For Uploaded And Auto-Acquired Inputs

**Files:**
- Modify: `E:\vscode\fusionAgent\schemas\agent.py`
- Modify: `E:\vscode\fusionAgent\api\routers\runs_v2.py`
- Modify: `E:\vscode\fusionAgent\tests\test_api_v2_integration.py`

- [x] **Step 1: Write the failing API test for task-driven run creation without uploads**

```python
def test_v2_task_driven_run_allows_missing_uploads_when_auto_acquire_is_requested(
    tmp_path: Path,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_create_run(**kwargs):
        captured.update(kwargs)
        return type("CreatedRun", (), {"run_id": "run-auto", "phase": "queued"})()

    monkeypatch.setattr(runs_v2_router, "agent_run_service", type("StubService", (), {"create_run": staticmethod(fake_create_run)})())

    resp = client.post(
        "/api/v2/runs",
        data={
            "job_type": "building",
            "trigger_type": "user_query",
            "trigger_content": "need building data for bbox(29,40,30,41)",
            "spatial_extent": "bbox(29,40,30,41)",
            "target_crs": "EPSG:32643",
            "input_strategy": "task_driven_auto",
            "field_mapping": "{}",
            "debug": "false",
        },
    )

    assert resp.status_code == 200, resp.text
    assert captured["request"].input_strategy == "task_driven_auto"
    assert captured["osm_zip_name"] is None
    assert captured["ref_zip_name"] is None
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_api_v2_integration.py -k task_driven_run_allows_missing_uploads`

Expected: FAIL because the route still requires both upload files and the request model has no `input_strategy`

- [x] **Step 3: Add the request-side input strategy model**

```python
class RunInputStrategy(str, Enum):
    uploaded = "uploaded"
    task_driven_auto = "task_driven_auto"


class RunCreateRequest(BaseModel):
    job_type: JobType
    trigger: RunTrigger
    target_crs: str = "EPSG:32643"
    field_mapping: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    debug: bool = False
    input_strategy: RunInputStrategy = RunInputStrategy.uploaded
```

- [x] **Step 4: Make `/api/v2/runs` accept missing files when `input_strategy=task_driven_auto`**

```python
async def create_run(
    osm_zip: Optional[UploadFile] = File(None),
    ref_zip: Optional[UploadFile] = File(None),
    ...
    input_strategy: RunInputStrategy = Form(RunInputStrategy.uploaded),
) -> RunCreateResponse:
    if input_strategy == RunInputStrategy.uploaded:
        if osm_zip is None or ref_zip is None:
            raise HTTPException(status_code=400, detail="uploaded mode requires osm_zip and ref_zip")
    else:
        if osm_zip is not None or ref_zip is not None:
            raise HTTPException(status_code=400, detail="task_driven_auto mode does not accept uploaded files")
```

- [x] **Step 5: Pass optional upload payloads through to the run service**

```python
    status = agent_run_service.create_run(
        request=request,
        osm_zip_name=osm_zip.filename if osm_zip else None,
        osm_zip_bytes=await osm_zip.read() if osm_zip else None,
        ref_zip_name=ref_zip.filename if ref_zip else None,
        ref_zip_bytes=await ref_zip.read() if ref_zip else None,
    )
```

- [x] **Step 6: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_api_v2_integration.py -k task_driven_run_allows_missing_uploads`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add schemas/agent.py api/routers/runs_v2.py tests/test_api_v2_integration.py
git commit -m "feat: add task-driven auto input strategy"
```

### Task 2: Add Cached Input Bundle Lookup And Version-Aware Reuse

**Files:**
- Modify: `E:\vscode\fusionAgent\services\artifact_registry.py`
- Create: `E:\vscode\fusionAgent\services\input_acquisition_service.py`
- Create: `E:\vscode\fusionAgent\services\local_bundle_catalog.py`
- Create: `E:\vscode\fusionAgent\tests\test_input_acquisition_service.py`
- Modify: `E:\vscode\fusionAgent\tests\test_artifact_registry.py`

- [ ] **Step 1: Write the failing registry test for metadata-filtered reusable bundle lookup**

```python
def test_artifact_registry_filters_candidates_by_required_meta(tmp_path: Path) -> None:
    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    registry.register(
        ArtifactRecord(
            artifact_id="bundle-a",
            artifact_path=str(tmp_path / "bundle-a"),
            job_type="building",
            created_at="2026-04-11T00:00:00+00:00",
            output_data_type="dt.building.bundle",
            target_crs="EPSG:32643",
            bbox=(0.0, 0.0, 10.0, 10.0),
            meta={"artifact_role": "input_bundle", "source_id": "catalog.task.building.default"},
        )
    )
    registry.register(
        ArtifactRecord(
            artifact_id="bundle-b",
            artifact_path=str(tmp_path / "bundle-b"),
            job_type="building",
            created_at="2026-04-11T01:00:00+00:00",
            output_data_type="dt.building.bundle",
            target_crs="EPSG:32643",
            bbox=(0.0, 0.0, 10.0, 10.0),
            meta={"artifact_role": "input_bundle", "source_id": "catalog.other"},
        )
    )

    found = registry.find_reusable(
        ArtifactLookupRequest(
            job_type="building",
            required_output_type="dt.building.bundle",
            required_target_crs="EPSG:32643",
            bbox=(1.0, 1.0, 2.0, 2.0),
            required_meta={"artifact_role": "input_bundle", "source_id": "catalog.task.building.default"},
        )
    )

    assert found is not None
    assert found.artifact_id == "bundle-a"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_artifact_registry.py -k required_meta`

Expected: FAIL because `ArtifactLookupRequest` has no `required_meta` and the registry ignores meta filters

- [ ] **Step 3: Extend `ArtifactLookupRequest` with exact-match metadata filters**

```python
class ArtifactLookupRequest(BaseModel):
    ...
    required_meta: Dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 4: Apply `required_meta` subset matching in `find_reusable()` and `list_reusable()`**

```python
def _meta_contains(actual: Dict[str, Any], required: Dict[str, Any]) -> bool:
    for key, value in (required or {}).items():
        if actual.get(key) != value:
            return False
    return True
```

- [ ] **Step 5: Write the failing input-acquisition test for version-aware cache reuse and clipping**

```python
def test_input_acquisition_reuses_cached_bundle_when_version_matches_and_clips_to_request_bbox(tmp_path: Path) -> None:
    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    provider = StubBundleProvider(version_token="v1")
    service = InputAcquisitionService(registry=registry, providers=[provider], cache_dir=tmp_path / "cache")

    initial = service.resolve_task_driven_inputs(
        request=_build_request(),
        source_id="catalog.task.building.default",
        required_output_type="dt.building.bundle",
        input_dir=tmp_path / "run1",
    )
    reused = service.resolve_task_driven_inputs(
        request=_build_request(spatial_extent="bbox(1,1,2,2)"),
        source_id="catalog.task.building.default",
        required_output_type="dt.building.bundle",
        input_dir=tmp_path / "run2",
    )

    assert initial.source_mode == "downloaded"
    assert reused.source_mode == "clip_reused"
    assert provider.download_calls == 1
```

- [ ] **Step 6: Run test to verify it fails**

Run: `python -m pytest -q tests/test_input_acquisition_service.py`

Expected: FAIL because `InputAcquisitionService` does not exist

- [ ] **Step 7: Implement a local catalog provider interface and the input-acquisition service**

```python
class InputBundleProvider(Protocol):
    def can_handle(self, source_id: str) -> bool: ...
    def current_version(self, source_id: str) -> str: ...
    def materialize(self, *, source_id: str, request_bbox: BBox | None, target_dir: Path, target_crs: str) -> MaterializedBundle: ...


class InputAcquisitionService:
    def resolve_task_driven_inputs(... ) -> ResolvedRunInputs:
        candidate = self._find_cached_bundle(...)
        if candidate and self._version_matches(candidate, source_id):
            return self._reuse_or_clip_cached_bundle(...)
        return self._download_and_register_bundle(...)
```

- [ ] **Step 8: Store cached input bundles in the existing registry with explicit metadata**

```python
meta={
    "artifact_role": "input_bundle",
    "source_id": source_id,
    "source_version": provider.current_version(source_id),
    "planning_mode": "task_driven",
}
```

- [ ] **Step 9: Run tests to verify they pass**

Run:

```powershell
python -m pytest -q `
  tests/test_artifact_registry.py -k required_meta `
  tests/test_input_acquisition_service.py
```

Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add services/artifact_registry.py services/input_acquisition_service.py services/local_bundle_catalog.py tests/test_artifact_registry.py tests/test_input_acquisition_service.py
git commit -m "feat: add task-driven input acquisition cache service"
```

### Task 3: Wire Auto-Acquired Inputs Into Run Creation And Execution

**Files:**
- Modify: `E:\vscode\fusionAgent\services\agent_run_service.py`
- Modify: `E:\vscode\fusionAgent\tests\test_agent_run_service_enhancements.py`
- Modify: `E:\vscode\fusionAgent\tests\test_api_v2_integration.py`

- [ ] **Step 1: Write the failing run-service test for task-driven auto input preparation**

```python
def test_agent_run_service_task_driven_auto_prepares_inputs_before_execution(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    resolved = ResolvedRunInputs(
        osm_zip_path=tmp_path / "prepared" / "osm.zip",
        ref_zip_path=tmp_path / "prepared" / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.task.building.default",
        cache_hit=False,
        version_token="v1",
    )

    monkeypatch.setattr(service.input_acquisition_service, "resolve_task_driven_inputs", lambda **_kwargs: resolved)
    monkeypatch.setattr(service, "execute_run", lambda **kwargs: None)

    status = service.create_run(
        request=_build_auto_request(),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    audit = service.get_audit_events(status.run_id)
    created = next(event for event in audit if event.kind == "run_created")
    assert created.details["input_strategy"] == "task_driven_auto"
    assert created.details["input_resolution"]["source_mode"] == "downloaded"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_agent_run_service_enhancements.py -k task_driven_auto_prepares_inputs`

Expected: FAIL because `create_run()` still requires uploaded bytes

- [ ] **Step 3: Make `AgentRunService.create_run()` accept optional uploaded files and resolve task-driven inputs**

```python
def create_run(
    self,
    request: RunCreateRequest,
    osm_zip_name: str | None,
    osm_zip_bytes: bytes | None,
    ref_zip_name: str | None,
    ref_zip_bytes: bytes | None,
) -> RunStatus:
    ...
    resolved_inputs = self._prepare_run_inputs(
        request=request,
        run_dir=run_dir,
        input_dir=input_dir,
        osm_zip_name=osm_zip_name,
        osm_zip_bytes=osm_zip_bytes,
        ref_zip_name=ref_zip_name,
        ref_zip_bytes=ref_zip_bytes,
    )
```

- [ ] **Step 4: Persist input-resolution evidence in the run audit**

```python
details={
    "request_path": str(run_dir / "request.json"),
    "input_strategy": request.input_strategy.value,
    "input_resolution": {
        "source_mode": resolved_inputs.source_mode,
        "source_id": resolved_inputs.source_id,
        "cache_hit": resolved_inputs.cache_hit,
        "version_token": resolved_inputs.version_token,
        "osm_zip_name": resolved_inputs.osm_zip_path.name,
        "ref_zip_name": resolved_inputs.ref_zip_path.name,
    },
}
```

- [ ] **Step 5: Add API integration coverage for upload-free task-driven execution**

```python
def test_v2_run_task_driven_auto_input_integration(tmp_path: Path, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        runs_v2_router.agent_run_service.input_acquisition_service,
        "resolve_task_driven_inputs",
        lambda **_kwargs: _build_resolved_inputs(tmp_path),
    )
    ...
    resp = client.post(
        "/api/v2/runs",
        data={
            "job_type": "building",
            "trigger_type": "user_query",
            "trigger_content": "need building data",
            "spatial_extent": "bbox(0,0,1,1)",
            "target_crs": "EPSG:32643",
            "input_strategy": "task_driven_auto",
            "field_mapping": "{}",
            "debug": "false",
        },
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run:

```powershell
python -m pytest -q `
  tests/test_agent_run_service_enhancements.py -k task_driven_auto_prepares_inputs `
  tests/test_api_v2_integration.py -k task_driven_auto
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add services/agent_run_service.py tests/test_agent_run_service_enhancements.py tests/test_api_v2_integration.py
git commit -m "feat: wire task-driven auto inputs into run execution"
```

### Task 4: Align README And Plan Status With The New Input Pipeline

**Files:**
- Modify: `E:\vscode\fusionAgent\README.md`
- Modify: `E:\vscode\fusionAgent\docs\superpowers\plans\2026-04-11-task-driven-data-acquisition-cache.md`

- [ ] **Step 1: Update README capability and gap notes**

```md
### Phase 4.5: Task-Driven Input Acquisition

- `task-driven` runs can prepare inputs without uploaded ZIP bundles
- input preparation can reuse cached bundles, verify source version tokens, and clip cached bundles to the requested bbox
- the current concrete provider is local-catalog based; remote source download remains a follow-up
```

- [ ] **Step 2: Mark completed plan steps**

Update the checkbox state in this plan file as work is completed so execution history remains trustworthy.

- [ ] **Step 3: Run focused regression verification**

Run:

```powershell
python -m pytest -q `
  tests/test_artifact_registry.py `
  tests/test_input_acquisition_service.py `
  tests/test_agent_run_service_enhancements.py `
  tests/test_api_v2_integration.py
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add README.md docs/superpowers/plans/2026-04-11-task-driven-data-acquisition-cache.md
git commit -m "docs: describe task-driven acquisition cache pipeline"
```

## Self-Review

### Spec coverage

- Task-driven automatic input expansion is covered by Task 1 and Task 3.
- Data acquisition, version check, and clip reuse are covered by Task 2.
- README and plan synchronization are covered by Task 4.

### Placeholder scan

- No `TODO`, `TBD`, or “same as above” placeholders remain.
- Each task names exact files, expected tests, and commit points.

### Type consistency

- New runtime terms stay consistent across tasks:
  - `RunInputStrategy`
  - `InputAcquisitionService`
  - `ResolvedRunInputs`
  - `artifact_role = input_bundle`
  - `source_version`

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-11-task-driven-data-acquisition-cache.md`.

Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
