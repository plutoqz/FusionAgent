# Data Asset Contract And Registry Roles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Prefer `gpt-5.5` workers. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Standardize artifact roles and materialization evidence so raw sources, input bundles, fusion results, compatibility exports, quality reports, and evidence packages can be classified without path guessing.

**Architecture:** Keep `ArtifactRegistry` as the JSON index, but add a first-class `artifact_role` field while preserving existing `meta["artifact_role"]` compatibility. Stabilize `source_materialization_manifest.json` with a versioned contract and role-aware provider attempts. This plan does not change download behavior, algorithm selection, GPKG output, or quality acceptance.

**Tech Stack:** Python, Pydantic v2, pytest, existing `ArtifactRegistry`, `InputAcquisitionService`, `RawVectorSourceService`, and `AgentRunService`.

---

## Phase 0: Documentation Discovery

### Sources Consulted

- `docs/superpowers/specs/2026-06-03-engineering-agent-upgrade-design.md`
  - Confirms target asset roles: `raw_source`, `input_bundle`, `intermediate`, `fusion_result`, `compat_export`, `quality_report`, `evidence_package`.
- `services/artifact_registry.py`
  - `ArtifactRecord` currently stores `meta` but has no top-level `artifact_role`.
  - `ArtifactLookupRequest` can filter `required_meta`, but not top-level role.
- `services/raw_vector_source_service.py`
  - Raw vectors are registered with `meta["artifact_role"] == "raw_vector"`.
- `services/input_acquisition_service.py`
  - Input bundles are registered with `meta["artifact_role"] == "input_bundle"` and materialization manifests are written.
- `services/agent_run_service.py`
  - Final artifacts are registered in `_register_artifact()`, but no explicit `fusion_result` role exists.
- `services/source_materialization_manifest_service.py`
  - Manifest currently records source id, selected source, mode, bbox, coverage, provider attempts, and fault.
- `tests/test_artifact_registry.py`
  - Existing lookup tests cover fields, output type, target CRS, bbox, and required meta.
- `tests/test_input_acquisition_service.py`
  - Existing manifest assertions cover provider attempts and failed provider fault manifests.

### Allowed APIs

- Add optional fields to Pydantic models as backward-compatible changes.
- Keep existing `meta["artifact_role"]` records readable during migration.
- Add helper functions in a new focused schema module.
- Use existing `ArtifactRegistry.register()`, `find_reusable()`, and `list_reusable()`.

### Anti-Pattern Guards

- Do not rename existing artifact records in-place.
- Do not remove `meta["artifact_role"]` compatibility in this slice.
- Do not change cache directory layout.
- Do not change final artifact format yet.
- Do not introduce a database backend for the registry.

## File Structure

- Create: `schemas/artifact_role.py`
  - Owns the asset role vocabulary and normalization helper.
- Modify: `services/artifact_registry.py`
  - Adds top-level role fields and role filtering with meta fallback.
- Modify: `services/raw_vector_source_service.py`
  - Registers raw vectors as `raw_source` while preserving legacy `raw_vector` in meta.
- Modify: `services/input_acquisition_service.py`
  - Registers input bundles with top-level `artifact_role`.
- Modify: `services/agent_run_service.py`
  - Registers final outputs as `fusion_result`.
- Modify: `services/source_materialization_manifest_service.py`
  - Adds `manifest_version`, `artifact_role`, and richer attempt fields without breaking existing callers.
- Test: `tests/test_artifact_roles.py`
- Test: `tests/test_artifact_registry.py`
- Test: `tests/test_input_acquisition_service.py`
- Test: `tests/test_raw_vector_source_service.py`
- Test: `tests/test_agent_run_service_enhancements.py`

---

### Task 1: Add Artifact Role Vocabulary

**Files:**
- Create: `schemas/artifact_role.py`
- Test: `tests/test_artifact_roles.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_artifact_roles.py`:

```python
from __future__ import annotations

from schemas.artifact_role import ArtifactRole, normalize_artifact_role


def test_artifact_role_vocab_has_engineering_contract_values() -> None:
    assert [role.value for role in ArtifactRole] == [
        "raw_source",
        "input_bundle",
        "intermediate",
        "fusion_result",
        "compat_export",
        "quality_report",
        "evidence_package",
    ]


def test_normalize_artifact_role_keeps_legacy_raw_vector_compatible() -> None:
    assert normalize_artifact_role("raw_vector") == ArtifactRole.raw_source.value
    assert normalize_artifact_role("raw_source") == ArtifactRole.raw_source.value
    assert normalize_artifact_role(ArtifactRole.fusion_result) == ArtifactRole.fusion_result.value
    assert normalize_artifact_role("unknown") is None
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
py -3.13 -m pytest tests/test_artifact_roles.py -q
```

Expected: FAIL because `schemas.artifact_role` does not exist.

- [ ] **Step 3: Implement the role module**

Create `schemas/artifact_role.py`:

```python
from __future__ import annotations

from enum import Enum


class ArtifactRole(str, Enum):
    raw_source = "raw_source"
    input_bundle = "input_bundle"
    intermediate = "intermediate"
    fusion_result = "fusion_result"
    compat_export = "compat_export"
    quality_report = "quality_report"
    evidence_package = "evidence_package"


_ALIASES = {
    "raw_vector": ArtifactRole.raw_source.value,
    "raw-source": ArtifactRole.raw_source.value,
    "input-bundle": ArtifactRole.input_bundle.value,
    "fusion-result": ArtifactRole.fusion_result.value,
}


def normalize_artifact_role(value: object | None) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        value = getattr(value, "value")
    token = str(value).strip()
    if not token:
        return None
    token = token.replace(" ", "_").casefold()
    token = _ALIASES.get(token, token)
    allowed = {role.value for role in ArtifactRole}
    return token if token in allowed else None
```

- [ ] **Step 4: Verify**

Run:

```powershell
py -3.13 -m pytest tests/test_artifact_roles.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add schemas/artifact_role.py tests/test_artifact_roles.py
git commit -m "feat: add artifact role vocabulary"
```

### Task 2: Add Role-Aware Registry Filtering

**Files:**
- Modify: `services/artifact_registry.py`
- Test: `tests/test_artifact_registry.py`

- [ ] **Step 1: Add failing registry tests**

Append to `tests/test_artifact_registry.py`:

```python
def test_artifact_registry_filters_by_top_level_artifact_role(tmp_path: Path) -> None:
    registry = ArtifactRegistry(index_path=tmp_path / "artifact_index.json")
    now = datetime(2026, 6, 4, 0, 0, 0, tzinfo=timezone.utc)
    registry.register(
        ArtifactRecord(
            artifact_id="raw-osm",
            artifact_path=str(tmp_path / "raw.zip"),
            job_type="building",
            created_at=now.isoformat(),
            artifact_role="raw_source",
        )
    )
    registry.register(
        ArtifactRecord(
            artifact_id="fused-building",
            artifact_path=str(tmp_path / "fused.zip"),
            job_type="building",
            created_at=now.isoformat(),
            artifact_role="fusion_result",
        )
    )

    selected = registry.find_reusable(
        ArtifactLookupRequest(job_type="building", required_artifact_role="fusion_result"),
        now=now,
    )

    assert selected is not None
    assert selected.artifact_id == "fused-building"


def test_artifact_registry_role_filter_accepts_legacy_meta_role(tmp_path: Path) -> None:
    registry = ArtifactRegistry(index_path=tmp_path / "artifact_index.json")
    now = datetime(2026, 6, 4, 0, 0, 0, tzinfo=timezone.utc)
    registry.register(
        ArtifactRecord(
            artifact_id="legacy-raw",
            artifact_path=str(tmp_path / "legacy.zip"),
            job_type="road",
            created_at=now.isoformat(),
            meta={"artifact_role": "raw_vector"},
        )
    )

    selected = registry.find_reusable(
        ArtifactLookupRequest(job_type="road", required_artifact_role="raw_source"),
        now=now,
    )

    assert selected is not None
    assert selected.artifact_id == "legacy-raw"
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_artifact_registry.py::test_artifact_registry_filters_by_top_level_artifact_role tests/test_artifact_registry.py::test_artifact_registry_role_filter_accepts_legacy_meta_role -q
```

Expected: FAIL because `artifact_role` and `required_artifact_role` fields do not exist.

- [ ] **Step 3: Update registry models and filters**

Modify `services/artifact_registry.py`:

```python
from schemas.artifact_role import normalize_artifact_role
```

Add to `ArtifactRecord`:

```python
    artifact_role: Optional[str] = None
```

Add to `ArtifactLookupRequest`:

```python
    required_artifact_role: Optional[str] = None
```

Add helper:

```python
def _record_artifact_role(record: ArtifactRecord) -> Optional[str]:
    return normalize_artifact_role(record.artifact_role) or normalize_artifact_role(record.meta.get("artifact_role"))
```

Inside both `find_reusable()` and `list_reusable()`, after `want_meta`:

```python
        want_role = normalize_artifact_role(request.required_artifact_role)
```

Inside the record loop in both methods, after meta filtering:

```python
            if want_role is not None and _record_artifact_role(record) != want_role:
                continue
```

- [ ] **Step 4: Verify registry tests**

```powershell
py -3.13 -m pytest tests/test_artifact_roles.py tests/test_artifact_registry.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add services/artifact_registry.py tests/test_artifact_registry.py
git commit -m "feat: filter artifact registry by role"
```

### Task 3: Register Raw, Input, And Fusion Roles

**Files:**
- Modify: `services/raw_vector_source_service.py`
- Modify: `services/input_acquisition_service.py`
- Modify: `services/agent_run_service.py`
- Test: `tests/test_raw_vector_source_service.py`
- Test: `tests/test_input_acquisition_service.py`
- Test: `tests/test_agent_run_service_enhancements.py`

- [ ] **Step 1: Add or update assertions**

In existing raw vector registry tests, assert registered raw records have:

```python
assert record.artifact_role == "raw_source"
assert record.meta["artifact_role"] == "raw_source"
assert record.meta["legacy_artifact_role"] == "raw_vector"
```

In `tests/test_input_acquisition_service.py`, after a successful materialization, add:

```python
records = registry.list_reusable(
    ArtifactLookupRequest(required_artifact_role="input_bundle"),
    limit=10,
)
assert records
assert records[0].artifact_role == "input_bundle"
```

In the final artifact registration test in `tests/test_agent_run_service_enhancements.py`, assert:

```python
record = service.artifact_registry.find_reusable(
    ArtifactLookupRequest(job_type="building", required_artifact_role="fusion_result")
)
assert record is not None
assert record.meta["artifact_role"] == "fusion_result"
```

- [ ] **Step 2: Run focused tests and confirm failure**

```powershell
py -3.13 -m pytest tests/test_raw_vector_source_service.py tests/test_input_acquisition_service.py tests/test_agent_run_service_enhancements.py -q
```

Expected: FAIL on missing top-level roles.

- [ ] **Step 3: Update registration sites**

In `services/raw_vector_source_service.py`, when creating `ArtifactRecord`, set:

```python
ArtifactRecord(
    artifact_id=f"raw_vector.{uuid.uuid4().hex}",
    artifact_path=str(cache_zip),
    artifact_role="raw_source",
    job_type="raw_vector",
    created_at=_utc_now(),
    output_data_type="dt.raw.vector",
    target_crs=normalized_target_crs,
    bbox=materialized.bbox,
    meta={
        "artifact_role": "raw_source",
        "legacy_artifact_role": "raw_vector",
        "source_id": source_id,
        "source_version": version_token,
        "source_mode": source_resolution.source_mode,
        **_tile_meta(request_bbox),
    },
)
```

In `services/input_acquisition_service.py`, input bundle `ArtifactRecord` gets:

```python
artifact_role="input_bundle",
```

and keep `meta["artifact_role"] == "input_bundle"`.

In `services/agent_run_service.py::_register_artifact()`, final output `ArtifactRecord` gets:

```python
artifact_role="fusion_result",
```

and `meta` gets:

```python
"artifact_role": "fusion_result",
```

- [ ] **Step 4: Verify**

```powershell
py -3.13 -m pytest tests/test_artifact_roles.py tests/test_artifact_registry.py tests/test_raw_vector_source_service.py tests/test_input_acquisition_service.py tests/test_agent_run_service_enhancements.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add services/raw_vector_source_service.py services/input_acquisition_service.py services/agent_run_service.py tests/test_raw_vector_source_service.py tests/test_input_acquisition_service.py tests/test_agent_run_service_enhancements.py
git commit -m "feat: register artifact roles across runtime"
```

### Task 4: Version Source Materialization Manifest

**Files:**
- Modify: `services/source_materialization_manifest_service.py`
- Modify: `services/input_acquisition_service.py`
- Test: `tests/test_input_acquisition_service.py`

- [ ] **Step 1: Add failing manifest contract assertions**

In `test_input_acquisition_manifest_records_provider_attempts_and_component_coverage`, add:

```python
assert manifest["manifest_version"] == 2
assert manifest["artifact_role"] == "input_bundle"
assert manifest["provider_attempts"][0]["attempt_type"] == "provider"
```

In `test_input_acquisition_writes_manifest_for_failed_provider`, add:

```python
assert manifest["manifest_version"] == 2
assert manifest["artifact_role"] == "input_bundle"
assert manifest["provider_attempts"][0]["recoverable"] is True
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_input_acquisition_service.py::test_input_acquisition_manifest_records_provider_attempts_and_component_coverage tests/test_input_acquisition_service.py::test_input_acquisition_writes_manifest_for_failed_provider -q
```

Expected: FAIL because new manifest fields do not exist.

- [ ] **Step 3: Update manifest builder**

Modify `build_source_materialization_manifest()` signature:

```python
    artifact_role: str = "input_bundle",
```

Return payload starts with:

```python
        "manifest_version": 2,
        "artifact_role": artifact_role,
```

Normalize provider attempts:

```python
        "provider_attempts": [_attempt_payload(attempt) for attempt in (provider_attempts or [])],
```

Add:

```python
def _attempt_payload(value: dict[str, object]) -> dict[str, object]:
    status = str(value.get("status") or "")
    payload = dict(value)
    payload.setdefault("attempt_type", "provider")
    payload.setdefault("recoverable", status == "failed")
    return payload
```

- [ ] **Step 4: Verify**

```powershell
py -3.13 -m pytest tests/test_input_acquisition_service.py tests/test_input_acquisition_faults.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add services/source_materialization_manifest_service.py services/input_acquisition_service.py tests/test_input_acquisition_service.py
git commit -m "feat: version source materialization manifest"
```

### Task 5: Final Verification

- [ ] **Step 1: Run focused verification**

```powershell
py -3.13 -m pytest tests/test_artifact_roles.py tests/test_artifact_registry.py tests/test_input_acquisition_service.py tests/test_input_acquisition_faults.py tests/test_raw_vector_source_service.py tests/test_agent_run_service_enhancements.py -q
```

Expected: PASS.

- [ ] **Step 2: Anti-pattern scan**

```powershell
rg -n "\"raw_vector\"" services schemas tests
```

Expected: only compatibility assertions or `legacy_artifact_role` references remain.

```powershell
rg -n "artifact_role.*fusion_result|artifact_role.*input_bundle|artifact_role.*raw_source" services tests
```

Expected: registration sites and tests are visible.

- [ ] **Step 3: Commit any verification-only fixes**

If verification changed code, commit only relevant files:

```powershell
git add schemas/artifact_role.py services/artifact_registry.py services/raw_vector_source_service.py services/input_acquisition_service.py services/agent_run_service.py services/source_materialization_manifest_service.py tests/test_artifact_roles.py tests/test_artifact_registry.py tests/test_raw_vector_source_service.py tests/test_input_acquisition_service.py tests/test_agent_run_service_enhancements.py
git commit -m "test: lock artifact role contract"
```

## Self-Review

- Data asset roles are explicit and queryable.
- Existing metadata compatibility is preserved.
- Source manifest is versioned but still accepts existing callers.
- No acquisition behavior, quality gate behavior, or GPKG behavior is changed.
