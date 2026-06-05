# Source Materialization Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Prefer `gpt-5.5` workers. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn data acquisition into a recoverable engineering subsystem with structured local/remote/fallback attempts, retry metadata, and Africa/Pakistan materialization coverage tests.

**Architecture:** Keep `SourceAssetService`, `RawVectorSourceService`, `LocalBundleCatalogProvider`, and `InputAcquisitionService`. Add a lightweight acquisition policy and attempt recorder, then thread it through existing materialization without changing provider implementations all at once. This plan produces better evidence and deterministic fallback selection; delayed retry execution is represented as metadata here and consumed by the scenario failure plan later.

**Tech Stack:** Python, pytest, existing source services, existing `source_materialization_manifest.json`, no new external downloader.

---

## Phase 0: Documentation Discovery

### Sources Consulted

- `services/source_asset_service.py`
  - Local-first lookup and remote providers already exist.
  - `_download_file()` retries and uses HTTP channel fallback.
- `services/raw_vector_source_service.py`
  - Raw source cache/registry lookup is the first executable source resolution layer.
- `services/local_bundle_catalog.py`
  - Bundle-level fallback currently exists only for one building case.
- `services/input_acquisition_service.py`
  - Writes successful and failed source materialization manifests.
- `services/run_recovery_service.py`
  - Defines recoverable categories but not source-level retry schedules.
- `tests/test_source_asset_service.py`
  - Existing Geofabrik Kenya, corrupt cache, HTTP channel, Microsoft, HydroRIVERS, HydroLAKES, GNS samples.
- `tests/test_input_acquisition_service.py`
  - Existing provider attempts and failure manifest samples.

### Allowed APIs

- Extend manifest provider attempts with keys such as `attempt_type`, `channel`, `attempt_no`, `status`, `fault_class`, `next_retry_after_seconds`.
- Add a small policy module that returns pure data; do not sleep in unit tests.
- Keep local-first behavior.
- Keep existing provider-specific download code.

### Anti-Pattern Guards

- Do not make live network tests mandatory.
- Do not claim provider availability without test fixtures.
- Do not add manual prompts to acquisition.
- Do not hide empty AOI coverage as success unless sparse policy is explicit.
- Do not delete current local preload behavior.

## File Structure

- Create: `schemas/source_acquisition.py`
  - Attempt, retry, and fallback policy models.
- Create: `services/source_acquisition_policy.py`
  - Pure policy functions for retry/backoff/fallback attempt metadata.
- Modify: `services/input_acquisition_service.py`
  - Uses policy to write richer failure and success attempts.
- Modify: `services/local_bundle_catalog.py`
  - Uses a fallback table for source ids instead of one hardcoded dict.
- Modify: `services/source_asset_service.py`
  - Exposes channel-aware attempt information for direct downloads where practical.
- Test: `tests/test_source_acquisition_policy.py`
- Test: `tests/test_input_acquisition_service.py`
- Test: `tests/test_local_bundle_catalog.py`
- Test: `tests/test_source_asset_service.py`

---

### Task 1: Add Source Acquisition Policy Models

**Files:**
- Create: `schemas/source_acquisition.py`
- Create: `services/source_acquisition_policy.py`
- Test: `tests/test_source_acquisition_policy.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_source_acquisition_policy.py`:

```python
from __future__ import annotations

from services.source_acquisition_policy import (
    build_failed_attempt,
    requires_complete_pair_coverage,
    retry_schedule_seconds,
    source_fallback_candidates,
)


def test_retry_schedule_uses_bounded_exponential_backoff() -> None:
    assert retry_schedule_seconds(attempt_no=1) == 30
    assert retry_schedule_seconds(attempt_no=2) == 60
    assert retry_schedule_seconds(attempt_no=5) == 480
    assert retry_schedule_seconds(attempt_no=99) == 900


def test_failed_attempt_records_recoverable_retry_metadata() -> None:
    attempt = build_failed_attempt(
        source_id="catalog.flood.water",
        fault_class="SOURCE_DOWNLOAD_FAILED",
        fault_message="network timeout",
        attempt_no=2,
        channel="provider",
    )

    assert attempt["source_id"] == "catalog.flood.water"
    assert attempt["status"] == "failed"
    assert attempt["recoverable"] is True
    assert attempt["next_retry_after_seconds"] == 60
    assert attempt["channel"] == "provider"


def test_source_fallback_candidates_are_source_specific() -> None:
    assert source_fallback_candidates("catalog.earthquake.building") == ["catalog.flood.building"]
    assert source_fallback_candidates("catalog.flood.waterways") == ["catalog.flood.water"]
    assert source_fallback_candidates("catalog.generic.poi") == []


def test_complete_pair_policy_requires_waterways_before_fallback() -> None:
    assert requires_complete_pair_coverage("catalog.flood.waterways") is True
    assert requires_complete_pair_coverage("catalog.flood.road") is False
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_source_acquisition_policy.py -q
```

Expected: FAIL because policy module does not exist.

- [ ] **Step 3: Implement policy module**

Create `schemas/source_acquisition.py`:

```python
from __future__ import annotations

from pydantic import BaseModel


class SourceAcquisitionAttempt(BaseModel):
    source_id: str
    status: str
    attempt_type: str = "provider"
    attempt_no: int = 1
    channel: str | None = None
    fault_class: str | None = None
    fault_message: str | None = None
    recoverable: bool = False
    next_retry_after_seconds: int | None = None
```

Create `services/source_acquisition_policy.py`:

```python
from __future__ import annotations

from schemas.source_acquisition import SourceAcquisitionAttempt

_RECOVERABLE_FAULTS = {
    "SOURCE_DOWNLOAD_FAILED",
    "SOURCE_MISSING",
    "SOURCE_CORRUPTED",
    "CRS_MISMATCH",
}

_SOURCE_FALLBACKS = {
    "catalog.earthquake.building": ["catalog.flood.building"],
    "catalog.flood.waterways": ["catalog.flood.water"],
}


def retry_schedule_seconds(*, attempt_no: int) -> int:
    attempt_no = max(1, int(attempt_no))
    return min(900, 30 * (2 ** (attempt_no - 1)))


def is_recoverable_fault(fault_class: str) -> bool:
    return str(fault_class or "") in _RECOVERABLE_FAULTS


def build_failed_attempt(
    *,
    source_id: str,
    fault_class: str,
    fault_message: str,
    attempt_no: int,
    channel: str | None = None,
) -> dict[str, object]:
    recoverable = is_recoverable_fault(fault_class)
    return SourceAcquisitionAttempt(
        source_id=source_id,
        status="failed",
        attempt_no=attempt_no,
        channel=channel,
        fault_class=fault_class,
        fault_message=fault_message,
        recoverable=recoverable,
        next_retry_after_seconds=retry_schedule_seconds(attempt_no=attempt_no) if recoverable else None,
    ).model_dump(mode="json")


def build_success_attempt(*, source_id: str, status: str = "materialized", channel: str | None = None) -> dict[str, object]:
    return SourceAcquisitionAttempt(
        source_id=source_id,
        status=status,
        channel=channel,
        recoverable=False,
    ).model_dump(mode="json")


def source_fallback_candidates(source_id: str) -> list[str]:
    return list(_SOURCE_FALLBACKS.get(str(source_id), []))


_PARTIAL_COVERAGE_ALLOWED_SOURCES = {
    "catalog.flood.road",
    "catalog.earthquake.road",
    "catalog.typhoon.road",
    "catalog.flood.water",
    "catalog.generic.poi",
}


def requires_complete_pair_coverage(source_id: str) -> bool:
    return str(source_id) not in _PARTIAL_COVERAGE_ALLOWED_SOURCES
```

- [ ] **Step 4: Verify**

```powershell
py -3.13 -m pytest tests/test_source_acquisition_policy.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add schemas/source_acquisition.py services/source_acquisition_policy.py tests/test_source_acquisition_policy.py
git commit -m "feat: add source acquisition policy"
```

### Task 2: Use Policy For Failed Input Acquisition Manifests

**Files:**
- Modify: `services/input_acquisition_service.py`
- Test: `tests/test_input_acquisition_service.py`

- [ ] **Step 1: Add failing assertions**

In `test_input_acquisition_writes_manifest_for_failed_provider`, replace provider attempt assertion with:

```python
attempt = manifest["provider_attempts"][0]
assert attempt["source_id"] == "catalog.flood.water"
assert attempt["status"] == "failed"
assert attempt["fault_class"] == "SOURCE_MISSING"
assert attempt["recoverable"] is True
assert attempt["next_retry_after_seconds"] == 30
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_input_acquisition_service.py::test_input_acquisition_writes_manifest_for_failed_provider -q
```

Expected: FAIL because current failed attempt lacks retry metadata.

- [ ] **Step 3: Implement failed attempt metadata**

In `services/input_acquisition_service.py`, import:

```python
from services.source_acquisition_policy import build_failed_attempt
```

Replace failed manifest `provider_attempts` with:

```python
provider_attempts=[
    build_failed_attempt(
        source_id=source_id,
        fault_class=fault,
        fault_message=str(exc),
        attempt_no=1,
        channel="provider",
    )
],
```

- [ ] **Step 4: Verify**

```powershell
py -3.13 -m pytest tests/test_input_acquisition_service.py tests/test_input_acquisition_faults.py tests/test_source_acquisition_policy.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add services/input_acquisition_service.py tests/test_input_acquisition_service.py
git commit -m "feat: record recoverable source retry metadata"
```

### Task 3: Move Bundle Fallbacks To Policy

**Files:**
- Modify: `services/local_bundle_catalog.py`
- Test: `tests/test_local_bundle_catalog.py`

- [ ] **Step 1: Add failing water fallback test**

Add to `tests/test_local_bundle_catalog.py`:

```python
def test_local_bundle_catalog_uses_policy_fallback_for_waterways(tmp_path: Path) -> None:
    provider = LocalBundleCatalogProvider(
        root_dir=tmp_path,
        raw_source_service=_RawServiceWithEmptyThenAvailableWater(),
    )

    bundle = provider.materialize_with_fallback(
        source_id="catalog.flood.waterways",
        request_bbox=(66.9, 24.8, 67.1, 25.0),
        target_dir=tmp_path / "bundle",
        target_crs="EPSG:4326",
    )

    assert bundle.fallback_from == "catalog.flood.waterways"
    assert bundle.source_id == "catalog.flood.water"
    assert bundle.attempted_sources == ["catalog.flood.waterways", "catalog.flood.water"]
```

Add this fake raw source service above the test:

```python
class _RawServiceWithEmptyThenAvailableWater:
    def resolve(
        self,
        *,
        source_id: str,
        request_bbox,
        target_path: Path,
        target_crs: str,
        resolved_aoi=None,
    ):
        target_path.parent.mkdir(parents=True, exist_ok=True)
        work_dir = target_path.parent / f"raw_{source_id.replace('.', '_')}"
        work_dir.mkdir(parents=True, exist_ok=True)
        shp_path = work_dir / "source.shp"
        if source_id in {"raw.osm.waterways", "raw.local.pakistan.waterways"}:
            frame = geopandas.GeoDataFrame({"source": []}, geometry=[], crs="EPSG:4326")
            feature_count = 0
        else:
            frame = geopandas.GeoDataFrame(
                {"source": [source_id]},
                geometry=[Polygon([(66.95, 24.85), (66.95, 24.95), (67.05, 24.95), (67.05, 24.85)])],
                crs="EPSG:4326",
            )
            feature_count = 1
        frame.to_file(shp_path)
        with zipfile.ZipFile(target_path, "w") as archive:
            for file in work_dir.glob("*"):
                archive.write(file, arcname=file.name)
        from services.raw_vector_source_service import MaterializedRawVectorSource

        return MaterializedRawVectorSource(
            zip_path=target_path,
            bbox=request_bbox,
            target_crs=target_crs,
            source_id=source_id,
            source_mode="test_fixture",
            cache_hit=False,
            version_token=f"{source_id}:test",
            feature_count=feature_count,
        )
```

Add `import zipfile` at the top of `tests/test_local_bundle_catalog.py` if it is not already imported.

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_local_bundle_catalog.py::test_local_bundle_catalog_uses_policy_fallback_for_waterways -q
```

Expected: FAIL because only building fallback is hardcoded.

- [ ] **Step 3: Use policy fallback candidates**

In `services/local_bundle_catalog.py`, import:

```python
from services.source_acquisition_policy import requires_complete_pair_coverage, source_fallback_candidates
```

Replace:

```python
for fallback_source_id in BUILDING_SOURCE_FALLBACKS.get(source_id, []):
```

with:

```python
for fallback_source_id in source_fallback_candidates(source_id):
```

Replace `_requires_complete_pair_coverage()` body with:

```python
@staticmethod
def _requires_complete_pair_coverage(source_id: str) -> bool:
    return requires_complete_pair_coverage(source_id)
```

Remove `catalog.flood.waterways` from `PARTIAL_COVERAGE_ALLOWED_SOURCES` if the constant remains in the file for compatibility.

Remove `BUILDING_SOURCE_FALLBACKS` only if no tests still import it. If it is referenced, keep it as a compatibility alias:

```python
BUILDING_SOURCE_FALLBACKS = {"catalog.earthquake.building": source_fallback_candidates("catalog.earthquake.building")}
```

- [ ] **Step 4: Verify**

```powershell
py -3.13 -m pytest tests/test_local_bundle_catalog.py tests/test_source_acquisition_policy.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add services/local_bundle_catalog.py tests/test_local_bundle_catalog.py
git commit -m "feat: apply source fallback policy to bundles"
```

### Task 4: Add Africa And Pakistan Materialization Matrix Tests

**Files:**
- Modify: `tests/test_source_asset_service.py`

- [ ] **Step 1: Add fixture-backed matrix test**

Add a parametrized test that uses local fixture URLs, not live network:

```python
@pytest.mark.parametrize(
    ("country_name", "country_code", "source_id"),
    [
        ("Kenya", "KE", "raw.osm.road"),
        ("Kenya", "KE", "raw.osm.waterways"),
        ("Pakistan", "PK", "raw.osm.road"),
        ("Pakistan", "PK", "raw.osm.poi"),
    ],
)
def test_source_asset_service_materializes_africa_and_pakistan_geofabrik_matrix(
    tmp_path: Path,
    country_name: str,
    country_code: str,
    source_id: str,
) -> None:
    kenya_archive = tmp_path / "fixtures" / "kenya-latest-free.shp.zip"
    pakistan_archive = tmp_path / "fixtures" / "pakistan-latest-free.shp.zip"
    kenya_roads = geopandas.GeoDataFrame(
        {"road_id": [1, 2]},
        geometry=[
            LineString([(36.80, -1.35), (36.90, -1.25)]),
            LineString([(39.60, -4.10), (39.70, -4.00)]),
        ],
        crs="EPSG:4326",
    )
    kenya_waterways = geopandas.GeoDataFrame(
        {"waterway_id": [1]},
        geometry=[LineString([(36.78, -1.32), (36.88, -1.22)])],
        crs="EPSG:4326",
    )
    pakistan_roads = geopandas.GeoDataFrame(
        {"road_id": [3]},
        geometry=[LineString([(66.95, 24.85), (67.05, 24.95)])],
        crs="EPSG:4326",
    )
    pakistan_pois = geopandas.GeoDataFrame(
        {"poi_id": [4]},
        geometry=[Point(67.01, 24.90)],
        crs="EPSG:4326",
    )
    _write_geofabrik_zip_with_layers(kenya_archive, roads=kenya_roads, waterways=kenya_waterways)
    _write_geofabrik_zip_with_layers(pakistan_archive, roads=pakistan_roads, pois=pakistan_pois)
    index_path = tmp_path / "fixtures" / "geofabrik-index.json"
    index_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "id": "africa/kenya",
                            "parent": "africa",
                            "name": "Kenya",
                            "iso3166-1:alpha2": ["KE"],
                            "urls": {"shp": kenya_archive.resolve().as_uri()},
                        },
                    },
                    {
                        "type": "Feature",
                        "properties": {
                            "id": "asia/pakistan",
                            "parent": "asia",
                            "name": "Pakistan",
                            "iso3166-1:alpha2": ["PK"],
                            "urls": {"shp": pakistan_archive.resolve().as_uri()},
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    bbox = (36.65, -1.45, 37.10, -1.10) if country_code == "KE" else (66.90, 24.80, 67.10, 25.00)
    aoi = ResolvedAOI(
        query=country_name,
        display_name=country_name,
        country_name=country_name,
        country_code=country_code.lower(),
        bbox=bbox,
        confidence=0.95,
        selection_reason="fixture",
        candidates=(),
    )
    service = SourceAssetService(
        repo_root=tmp_path,
        cache_dir=tmp_path / "cache",
        geofabrik_index_url=index_path.resolve().as_uri(),
        prefer_local_data=False,
    )

    resolved = service.resolve_raw_source_path(source_id, aoi=aoi)

    assert resolved.source_mode == "asset_downloaded"
    assert resolved.feature_count == 1
```

- [ ] **Step 2: Run matrix test**

```powershell
py -3.13 -m pytest tests/test_source_asset_service.py::test_source_asset_service_materializes_africa_and_pakistan_geofabrik_matrix -q
```

Expected: PASS after concrete fixture implementation.

- [ ] **Step 3: Commit**

```powershell
git add tests/test_source_asset_service.py
git commit -m "test: cover africa and pakistan source materialization"
```

### Task 5: Final Verification

- [ ] **Step 1: Focused verification**

```powershell
py -3.13 -m pytest tests/test_source_acquisition_policy.py tests/test_input_acquisition_service.py tests/test_input_acquisition_faults.py tests/test_local_bundle_catalog.py tests/test_source_asset_service.py tests/test_raw_vector_source_service.py -q
```

Expected: PASS.

- [ ] **Step 2: Anti-pattern scan**

```powershell
rg -n "time\\.sleep\\(|Start-Sleep" tests/test_source_acquisition_policy.py tests/test_input_acquisition_service.py tests/test_local_bundle_catalog.py
```

Expected: no output. Unit tests must not wait for real backoff.

```powershell
rg -n "requests\\.get|urllib\\.request\\.urlopen|httpx\\.get" tests/test_source_asset_service.py
```

Expected: no new live network calls in matrix tests.

- [ ] **Step 3: Commit verification fixes if needed**

```powershell
git add schemas/source_acquisition.py services/source_acquisition_policy.py services/input_acquisition_service.py services/local_bundle_catalog.py tests/test_source_acquisition_policy.py tests/test_input_acquisition_service.py tests/test_local_bundle_catalog.py tests/test_source_asset_service.py
git commit -m "test: lock source materialization hardening"
```

## Self-Review

- Local-first behavior remains.
- Provider attempts become structured.
- Retry schedule is recorded, not slept.
- Africa and Pakistan are covered by fixture-backed tests.
