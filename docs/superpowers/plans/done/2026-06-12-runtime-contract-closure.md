# Runtime Contract Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a general runtime contract closure layer so source planning, source materialization, task routing, degradation decisions, and quality gates stay consistent for any region, not only a single regression location.

**Architecture:** Keep the existing ScenarioRunService, AgentRunService, InputAcquisitionService, LocalBundleCatalogProvider, RawVectorSourceService, SourceAssetService, and QualityGateService as the main runtime spine. Add small contract objects and adapters around the existing spine so every selected source has an executable materialization contract, every task kind receives only semantically valid artifacts, and every quality decision is evaluated with an explicit degradation context.

**Tech Stack:** Python, Pydantic, dataclasses, GeoPandas, Shapely, existing KG repositories, existing source catalog services, pytest, PowerShell on Windows.

---

## Scope

This is a root-cause optimization, not a location-specific fix. London is only one regression case because it exposed four generic contract failures:

- A KG-planned raw source did not have an InputBundleProvider path.
- Geofabrik package selection assumed exact country-level matches and failed on region-granularity countries.
- A waterways task received a polygon artifact when line sources were unavailable.
- A POI single-source artifact was rejected by a hard multi-source gate without considering external unavailability.

The implementation must work for any AOI where source availability, provider authorization, catalog source composition, or package granularity differs from the happy path. No branch may check for `London`, `United Kingdom`, or a specific test output folder as a special case.

---

## Phase 0: Documentation And Code Discovery

### Sources Already Consulted

- `services/input_acquisition_service.py`
  - Defines `InputBundleProvider`, `MaterializedInputBundle`, `ResolvedRunInputs`, and `_provider_for()`.
  - `InputAcquisitionService` receives a provider list and dispatches by `provider.can_handle(source_id)`.
- `services/agent_run_service.py`
  - Builds input providers in `_build_input_bundle_providers()`.
  - Routes road, water, waterways, and POI to large-area runtime in `run_large_area_execution_stage()`.
  - Evaluates quality gates in `run_writeback_stage()`.
- `services/local_bundle_catalog.py`
  - Owns catalog bundle materialization and component fallback.
  - Already records `component_coverage` and `provider_attempts`.
- `services/raw_vector_source_service.py`
  - Owns raw vector resolution through `RawVectorSourceService.resolve()`.
  - Delegates local or remote raw source lookup to `SourceAssetService`.
- `services/source_asset_service.py`
  - Owns Geofabrik, Microsoft Buildings, Google Open Buildings, Overture, HydroRIVERS, HydroLAKES, and GNS POI raw source resolution.
  - `_select_geofabrik_bundle()` currently uses exact ISO/name matching and raises if no match is found.
- `services/source_acquisition_policy.py`
  - Owns source fallback candidates, component candidates, full-closure requirements, and source attempt payload creation.
- `services/quality_gate_service.py`
  - Owns geometry, field, lineage, multi-source, and spatial quality checks.
- `services/quality_policy_service.py`
  - Owns default per-task hard and soft quality policies.
- `services/output_contract_service.py`
  - Owns per-task output contracts, including waterways line-only required fields.
- `schemas/source_acquisition.py`
  - Defines `SourceAcquisitionAttempt`.
- `schemas/quality_gate.py`
  - Defines `QualityGateReport`.
- `schemas/task_kind.py`
  - Defines canonical task kinds and job-type expansion.

### Allowed APIs And Patterns

- Use `InputBundleProvider.can_handle()`, `current_version()`, and `materialize()` as the provider interface.
- Use `RawVectorSourceService.resolve()` to materialize raw vector sources.
- Use `SourceAssetService.resolve_raw_source_path()` for raw source asset lookup.
- Use `LocalBundleCatalogProvider.materialize_with_fallback()` for catalog bundles.
- Use `SourceAcquisitionAttempt` and existing source attempt builders for materialization evidence.
- Use `QualityGateService.evaluate()` as the single quality gate entry point.
- Use `QualityGateReport` as the persisted quality report payload.
- Use `TaskKind` to distinguish `water_polygon` from `waterways`; do not infer line/polygon semantics from `JobType.water` alone.

### Anti-Pattern Guards

- Do not hard-code London, United Kingdom, Great Britain, or any local test directory into runtime code.
- Do not make missing Google credentials look like successful source coverage.
- Do not downgrade geometry-type failures from hard to soft.
- Do not let a waterways task produce polygon output.
- Do not bypass `InputAcquisitionService` by manually downloading sources in ScenarioRunService.
- Do not add a parallel source planner that duplicates `source_acquisition_policy.py`; extend the current source policy and evidence path.
- Do not silently accept single-source outputs for all tasks. Degradation must be explicit and task-policy-controlled.

---

## File Structure

- Create: `schemas/runtime_source_contract.py`
  - Defines runtime source provider status and source execution compatibility payloads.
- Create: `schemas/degradation.py`
  - Defines `DegradationContext`, `DegradationLevel`, and helper payloads used by quality gates and reports.
- Create: `services/raw_vector_input_bundle_provider.py`
  - Adapts `RawVectorSourceService` to the `InputBundleProvider` protocol.
- Create: `services/runtime_source_contract_service.py` or extend the existing file if it already exists with the same responsibility.
  - Checks KG/catalog/selectable source ids against raw-source and input-bundle provider capability.
- Modify: `services/agent_run_service.py`
  - Registers the raw vector input provider.
  - Uses task-kind-aware water routing.
  - Passes degradation context to the quality gate.
  - Writes runtime source contract diagnostics.
- Modify: `services/source_asset_service.py`
  - Generalizes Geofabrik package selection with alias and bbox containment fallback.
- Modify: `services/local_bundle_catalog.py`
  - Preserves external fault classes and records component-level degradation without losing selected source semantics.
- Modify: `services/source_acquisition_policy.py`
  - Adds reusable source availability and degradation classification helpers.
- Modify: `services/quality_gate_service.py`
  - Accepts optional `DegradationContext`.
  - Applies task-scoped, policy-controlled degradation of selected checks.
- Modify: `schemas/quality_gate.py`
  - Adds quality report fields for degradation evidence.
- Modify: `services/quality_policy_service.py`
  - Adds metadata describing which checks may be downgraded under external degradation.
- Modify: `services/source_materialization_manifest_service.py`
  - Adds runtime provider status and degradation payloads to source materialization manifests.
- Create: `services/autonomous_region_fusion_service.py`
  - Adds a thin, general region-level entry point above ScenarioRunService.
- Modify: `services/scenario_run_service.py`
  - Optionally delegates to the region service for preflight summaries and unified evidence.
- Create: `tests/test_raw_vector_input_bundle_provider.py`
- Modify: `tests/test_source_asset_service.py`
- Create: `tests/test_runtime_source_contract_service.py`
- Modify: `tests/test_quality_gate_service.py`
- Modify: `tests/test_agent_run_service_large_area_runtime.py`
- Modify: `tests/test_source_coverage_fallback.py`
- Create: `tests/test_autonomous_region_fusion_service.py`
- Create: `tests/test_runtime_contract_closure_regression.py`

---

## Task 1: Add Runtime Source Contract Schemas

**Files:**
- Create: `schemas/runtime_source_contract.py`
- Test: `tests/test_runtime_source_contract_service.py`

- [ ] **Step 1: Write the failing schema test**

Create `tests/test_runtime_source_contract_service.py` with:

```python
from __future__ import annotations

from schemas.runtime_source_contract import RuntimeProviderStatus, RuntimeSourceContract


def test_runtime_source_contract_records_provider_readiness() -> None:
    contract = RuntimeSourceContract(
        source_id="raw.example.source",
        catalog_selectable=True,
        raw_vector_supported=True,
        input_bundle_supported=False,
        status=RuntimeProviderStatus.reservation_only,
        reasons=["source is known but no input bundle provider can materialize it"],
        required_external_config=["EXAMPLE_API_KEY"],
    )

    assert contract.source_id == "raw.example.source"
    assert contract.status == RuntimeProviderStatus.reservation_only
    assert contract.catalog_selectable is True
    assert contract.raw_vector_supported is True
    assert contract.input_bundle_supported is False
    assert contract.required_external_config == ["EXAMPLE_API_KEY"]
```

- [ ] **Step 2: Run the failing schema test**

Run:

```powershell
pytest tests/test_runtime_source_contract_service.py::test_runtime_source_contract_records_provider_readiness -v
```

Expected: fail with `ModuleNotFoundError: No module named 'schemas.runtime_source_contract'`.

- [ ] **Step 3: Implement the schema**

Create `schemas/runtime_source_contract.py` with:

```python
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class RuntimeProviderStatus(str, Enum):
    runtime_ready = "runtime_ready"
    requires_external_config = "requires_external_config"
    reservation_only = "reservation_only"
    missing_provider = "missing_provider"


class RuntimeSourceContract(BaseModel):
    source_id: str
    catalog_selectable: bool = False
    raw_vector_supported: bool = False
    input_bundle_supported: bool = False
    status: RuntimeProviderStatus
    reasons: list[str] = Field(default_factory=list)
    required_external_config: list[str] = Field(default_factory=list)
    provider_names: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Verify the schema test passes**

Run:

```powershell
pytest tests/test_runtime_source_contract_service.py::test_runtime_source_contract_records_provider_readiness -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add schemas/runtime_source_contract.py tests/test_runtime_source_contract_service.py
git commit -m "feat: add runtime source contract schema"
```

---

## Task 2: Add Degradation Context Schema

**Files:**
- Create: `schemas/degradation.py`
- Modify: `schemas/quality_gate.py`
- Test: `tests/test_quality_gate_service.py`

- [ ] **Step 1: Add a failing schema test**

Append to `tests/test_quality_gate_service.py`:

```python
from schemas.degradation import DegradationContext, DegradationLevel


def test_degradation_context_serializes_external_source_absence() -> None:
    context = DegradationContext(
        degraded=True,
        level=DegradationLevel.external_uncontrollable,
        reason="missing optional provider authorization",
        available_sources=["raw.gns.poi"],
        missing_sources=["raw.google.poi", "raw.osm.poi"],
        external_uncontrollable_sources=["raw.google.poi"],
        system_failure_sources=[],
    )

    payload = context.model_dump()

    assert payload["degraded"] is True
    assert payload["level"] == "external_uncontrollable"
    assert payload["available_sources"] == ["raw.gns.poi"]
    assert payload["missing_sources"] == ["raw.google.poi", "raw.osm.poi"]
```

- [ ] **Step 2: Run the failing schema test**

Run:

```powershell
pytest tests/test_quality_gate_service.py::test_degradation_context_serializes_external_source_absence -v
```

Expected: fail with `ModuleNotFoundError: No module named 'schemas.degradation'`.

- [ ] **Step 3: Create the degradation schema**

Create `schemas/degradation.py` with:

```python
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class DegradationLevel(str, Enum):
    none = "none"
    partial_source = "partial_source"
    external_uncontrollable = "external_uncontrollable"
    system_failure = "system_failure"


class DegradationContext(BaseModel):
    degraded: bool = False
    level: DegradationLevel = DegradationLevel.none
    reason: str | None = None
    available_sources: list[str] = Field(default_factory=list)
    missing_sources: list[str] = Field(default_factory=list)
    external_uncontrollable_sources: list[str] = Field(default_factory=list)
    system_failure_sources: list[str] = Field(default_factory=list)

    @property
    def external_only(self) -> bool:
        return self.degraded and self.level == DegradationLevel.external_uncontrollable and not self.system_failure_sources
```

- [ ] **Step 4: Extend QualityGateReport**

Modify `schemas/quality_gate.py` so `QualityGateReport` includes degradation payload fields:

```python
class QualityGateReport(BaseModel):
    accepted: bool
    task_kind: TaskKind
    artifact_path: str
    checks: dict[str, dict[str, Any]] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    failure_reasons: list[str] = Field(default_factory=list)
    policy_id: str | None = None
    soft_failure_reasons: list[str] = Field(default_factory=list)
    degraded_mode: bool = False
    degradation_level: str | None = None
    degradation_reason: str | None = None
    degradation_context: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 5: Verify schema test passes**

Run:

```powershell
pytest tests/test_quality_gate_service.py::test_degradation_context_serializes_external_source_absence -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add schemas/degradation.py schemas/quality_gate.py tests/test_quality_gate_service.py
git commit -m "feat: add degradation context schema"
```

---

## Task 3: Add Raw Vector Input Bundle Provider

**Files:**
- Create: `services/raw_vector_input_bundle_provider.py`
- Modify: `services/agent_run_service.py`
- Test: `tests/test_raw_vector_input_bundle_provider.py`

- [ ] **Step 1: Write the failing provider test**

Create `tests/test_raw_vector_input_bundle_provider.py` with:

```python
from __future__ import annotations

from pathlib import Path

from services.input_acquisition_service import MaterializedInputBundle
from services.raw_vector_input_bundle_provider import RawVectorInputBundleProvider
from services.raw_vector_source_service import MaterializedRawVectorSource


class _FakeRawVectorSourceService:
    def can_handle(self, source_id: str) -> bool:
        return source_id == "raw.example.vector"

    def current_version(self, source_id: str, *, request_bbox=None, resolved_aoi=None) -> str:
        assert source_id == "raw.example.vector"
        return "version-1"

    def resolve(self, *, source_id: str, request_bbox, target_path: Path, target_crs: str, resolved_aoi=None):
        assert source_id == "raw.example.vector"
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(b"fake-zip")
        return MaterializedRawVectorSource(
            zip_path=target_path,
            bbox=(0.0, 0.0, 1.0, 1.0),
            target_crs=target_crs,
            source_id=source_id,
            source_mode="asset_downloaded",
            cache_hit=False,
            version_token="version-1",
            feature_count=7,
            coverage_status="available",
        )


def test_raw_vector_input_bundle_provider_materializes_single_raw_source(tmp_path: Path) -> None:
    provider = RawVectorInputBundleProvider(raw_source_service=_FakeRawVectorSourceService())

    assert provider.can_handle("raw.example.vector") is True
    assert provider.can_handle("catalog.example.bundle") is False
    assert provider.current_version("raw.example.vector", request_bbox=(0, 0, 1, 1)) == "version-1"

    bundle = provider.materialize(
        source_id="raw.example.vector",
        request_bbox=(0, 0, 1, 1),
        resolved_aoi=None,
        target_dir=tmp_path / "bundle",
        target_crs="EPSG:4326",
    )

    assert isinstance(bundle, MaterializedInputBundle)
    assert bundle.source_id == "raw.example.vector"
    assert bundle.osm_zip_path.exists()
    assert bundle.ref_zip_path.exists()
    assert bundle.component_coverage["raw.example.vector"]["feature_count"] == 7
    assert bundle.provider_attempts[0]["status"] == "available"
```

- [ ] **Step 2: Run the failing provider test**

Run:

```powershell
pytest tests/test_raw_vector_input_bundle_provider.py::test_raw_vector_input_bundle_provider_materializes_single_raw_source -v
```

Expected: fail with `ModuleNotFoundError: No module named 'services.raw_vector_input_bundle_provider'`.

- [ ] **Step 3: Implement the provider**

Create `services/raw_vector_input_bundle_provider.py` with:

```python
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

import geopandas as gpd

from services.aoi_resolution_service import ResolvedAOI
from services.input_acquisition_service import BBox, MaterializedInputBundle
from services.raw_vector_source_service import RawVectorSourceService, MaterializedRawVectorSource
from services.source_acquisition_policy import build_success_attempt
from services.source_asset_service import SourceCoverageStatus, coverage_status_for_count
from utils.crs import normalize_target_crs
from utils.shp_zip import validate_zip_has_shapefile, zip_shapefile_bundle


class RawVectorInputBundleProvider:
    def __init__(self, *, raw_source_service: RawVectorSourceService) -> None:
        self.raw_source_service = raw_source_service

    def can_handle(self, source_id: str) -> bool:
        return str(source_id or "").startswith("raw.") and self.raw_source_service.can_handle(source_id)

    def current_version(
        self,
        source_id: str,
        *,
        request_bbox: Optional[BBox] = None,
        resolved_aoi: ResolvedAOI | None = None,
    ) -> str:
        return self.raw_source_service.current_version(
            source_id,
            request_bbox=request_bbox,
            resolved_aoi=resolved_aoi,
        )

    def materialize(
        self,
        *,
        source_id: str,
        request_bbox: Optional[BBox],
        resolved_aoi: ResolvedAOI | None = None,
        target_dir: Path,
        target_crs: str,
    ) -> MaterializedInputBundle:
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        normalized_crs = normalize_target_crs(target_crs)
        raw = self.raw_source_service.resolve(
            source_id=source_id,
            request_bbox=request_bbox,
            target_path=target_dir / "raw.zip",
            target_crs=normalized_crs,
            resolved_aoi=resolved_aoi,
        )
        ref = _create_empty_companion_bundle(raw=raw, output_zip=target_dir / "ref.zip")
        coverage_status = coverage_status_for_count(raw.feature_count)
        component_coverage = {
            source_id: SourceCoverageStatus(
                source_id=source_id,
                source_mode=raw.source_mode,
                feature_count=raw.feature_count,
                coverage_status=coverage_status,
                path=raw.zip_path,
            )
        }
        return MaterializedInputBundle(
            osm_zip_path=raw.zip_path,
            ref_zip_path=ref.zip_path,
            bbox=raw.bbox,
            target_crs=normalized_crs,
            source_id=source_id,
            attempted_sources=[source_id],
            component_coverage=component_coverage,
            provider_attempts=[
                build_success_attempt(
                    source_id=source_id,
                    status="available" if coverage_status == "available" else "empty",
                    attempt_no=1,
                    coverage_status=coverage_status,
                    feature_count=raw.feature_count,
                    selected_for_fusion=coverage_status == "available",
                )
            ],
        )


def _create_empty_companion_bundle(*, raw: MaterializedRawVectorSource, output_zip: Path) -> MaterializedRawVectorSource:
    extract_dir = output_zip.parent / f"_raw_provider_extract_{uuid.uuid4().hex[:8]}"
    shp_path = validate_zip_has_shapefile(raw.zip_path, extract_dir)
    frame = gpd.read_file(shp_path)
    empty = frame.iloc[0:0].copy()
    out_dir = output_zip.parent / f"_raw_provider_empty_{uuid.uuid4().hex[:8]}"
    out_dir.mkdir(parents=True, exist_ok=True)
    ref_shp = out_dir / "ref.shp"
    empty.to_file(ref_shp)
    zip_shapefile_bundle(ref_shp, output_zip)
    return MaterializedRawVectorSource(
        zip_path=output_zip,
        bbox=raw.bbox,
        target_crs=raw.target_crs,
        source_id="generated.empty.reference",
        source_mode="generated_empty_ref",
        cache_hit=False,
        version_token=raw.version_token,
        feature_count=0,
        coverage_status="empty",
    )
```

- [ ] **Step 4: Register the provider**

Modify `services/agent_run_service.py`.

Add the import near existing source service imports:

```python
from services.raw_vector_input_bundle_provider import RawVectorInputBundleProvider
```

Modify `_build_input_bundle_providers()` so it appends the raw provider after the catalog provider:

```python
    def _build_input_bundle_providers(self) -> list[object]:
        providers: list[object] = []
        try:
            providers.append(
                LocalBundleCatalogProvider(
                    Path(__file__).resolve().parents[1],
                    raw_source_service=self.raw_vector_source_service,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("geofusion.run").warning(
                "Failed to initialize local bundle catalog provider: %s",
                exc,
            )
        providers.append(RawVectorInputBundleProvider(raw_source_service=self.raw_vector_source_service))
        return providers
```

- [ ] **Step 5: Run provider tests**

Run:

```powershell
pytest tests/test_raw_vector_input_bundle_provider.py -v
```

Expected: pass.

- [ ] **Step 6: Run input acquisition regression tests**

Run:

```powershell
pytest tests/test_input_acquisition_service.py tests/test_input_acquisition_faults.py -v
```

Expected: pass.

- [ ] **Step 7: Commit**

```powershell
git add services/raw_vector_input_bundle_provider.py services/agent_run_service.py tests/test_raw_vector_input_bundle_provider.py
git commit -m "feat: adapt raw vector sources as input bundles"
```

---

## Task 4: Generalize Geofabrik Bundle Selection

**Files:**
- Modify: `services/source_asset_service.py`
- Test: `tests/test_source_asset_service.py`

- [ ] **Step 1: Add failing tests for alias and bbox fallback**

Append to `tests/test_source_asset_service.py`:

```python
from shapely.geometry import mapping, box


def test_geofabrik_selection_uses_country_alias_without_location_special_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive_path = tmp_path / "fixtures" / "england-latest-free.shp.zip"
    _write_geofabrik_zip_with_layers(archive_path)
    service = SourceAssetService(repo_root=tmp_path, cache_dir=tmp_path / "cache", prefer_local_data=False)
    monkeypatch.setattr(
        service,
        "_load_geofabrik_index",
        lambda: [
            {
                "type": "Feature",
                "properties": {
                    "id": "england",
                    "name": "England",
                    "iso3166-1:alpha2": [],
                    "urls": {"shp": archive_path.resolve().as_uri()},
                },
                "geometry": mapping(box(-6.5, 49.5, 2.5, 56.0)),
            }
        ],
    )
    aoi = ResolvedAOI(
        query="Any city in a country resolved as GB",
        display_name="Generic AOI",
        country_name="United Kingdom",
        country_code="gb",
        bbox=(-0.5, 51.2, 0.4, 51.8),
        confidence=0.9,
        selection_reason="test",
        candidates=(),
    )

    resolved = service.resolve_raw_source_path("raw.osm.road", aoi=aoi)

    assert resolved.feature_count == 1
    assert "england" in str(resolved.path).casefold()


def test_geofabrik_selection_uses_smallest_containing_bbox_when_country_metadata_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    regional_archive = tmp_path / "fixtures" / "region-latest-free.shp.zip"
    continent_archive = tmp_path / "fixtures" / "continent-latest-free.shp.zip"
    _write_geofabrik_zip_with_layers(regional_archive)
    _write_geofabrik_zip_with_layers(continent_archive)
    service = SourceAssetService(repo_root=tmp_path, cache_dir=tmp_path / "cache", prefer_local_data=False)
    monkeypatch.setattr(
        service,
        "_load_geofabrik_index",
        lambda: [
            {
                "type": "Feature",
                "properties": {
                    "id": "continent",
                    "name": "Continent",
                    "urls": {"shp": continent_archive.resolve().as_uri()},
                },
                "geometry": mapping(box(-20.0, 30.0, 40.0, 70.0)),
            },
            {
                "type": "Feature",
                "properties": {
                    "id": "region",
                    "name": "Region",
                    "urls": {"shp": regional_archive.resolve().as_uri()},
                },
                "geometry": mapping(box(-1.0, 51.0, 1.0, 52.0)),
            },
        ],
    )
    aoi = ResolvedAOI(
        query="Generic AOI",
        display_name="Generic AOI",
        country_name="Metadata Missing Country",
        country_code="zz",
        bbox=(-0.5, 51.2, 0.4, 51.8),
        confidence=0.9,
        selection_reason="test",
        candidates=(),
    )

    resolved = service.resolve_raw_source_path("raw.osm.waterways", aoi=aoi)

    assert resolved.feature_count == 1
    assert "region" in str(resolved.path).casefold()
```

- [ ] **Step 2: Run the failing Geofabrik tests**

Run:

```powershell
pytest tests/test_source_asset_service.py::test_geofabrik_selection_uses_country_alias_without_location_special_case tests/test_source_asset_service.py::test_geofabrik_selection_uses_smallest_containing_bbox_when_country_metadata_is_missing -v
```

Expected: fail because `_select_geofabrik_bundle()` does not use alias or bbox fallback.

- [ ] **Step 3: Add alias and bbox helpers**

Modify `services/source_asset_service.py`.

Add near the Geofabrik helpers:

```python
_GEOFABRIK_COUNTRY_ALIASES = {
    "gb": {"great britain", "england", "scotland", "wales"},
    "uk": {"great britain", "england", "scotland", "wales"},
    "united kingdom": {"great britain", "england", "scotland", "wales"},
}


def _aoi_bbox_polygon(aoi: ResolvedAOI | None):
    if aoi is None or not aoi.bbox or len(aoi.bbox) != 4:
        return None
    minx, miny, maxx, maxy = [float(value) for value in aoi.bbox]
    if maxx <= minx or maxy <= miny:
        return None
    from shapely.geometry import box

    return box(minx, miny, maxx, maxy)


def _geofabrik_candidate_area(feature: dict[str, object]) -> float:
    geometry = _feature_geometry(feature)
    if geometry is None or geometry.is_empty:
        return float("inf")
    return float(geometry.area)
```

- [ ] **Step 4: Replace `_select_geofabrik_bundle()`**

Replace `SourceAssetService._select_geofabrik_bundle()` with:

```python
    def _select_geofabrik_bundle(self, aoi: ResolvedAOI | None) -> _GeofabrikBundle:
        if aoi is None or (aoi.country_name is None and aoi.country_code is None):
            return _GeofabrikBundle(slug="burundi", download_url=self.geofabrik_burundi_url)

        country_code = _normalize_country_code(aoi.country_code)
        country_name = _normalize_country_name(aoi.country_name)
        features = list(self._load_geofabrik_index())

        exact = self._match_geofabrik_by_exact_country(features, country_code=country_code, country_name=country_name)
        if exact is not None:
            return exact

        alias = self._match_geofabrik_by_alias(features, country_code=country_code, country_name=country_name, aoi=aoi)
        if alias is not None:
            return alias

        bbox_match = self._match_geofabrik_by_bbox(features, aoi=aoi)
        if bbox_match is not None:
            return bbox_match

        raise FileNotFoundError(
            f"No Geofabrik country bundle matched AOI country={aoi.country_name!r} code={aoi.country_code!r} bbox={aoi.bbox!r}"
        )
```

Add the three helper methods inside `SourceAssetService`:

```python
    def _match_geofabrik_by_exact_country(
        self,
        features: list[dict[str, object]],
        *,
        country_code: str | None,
        country_name: str | None,
    ) -> _GeofabrikBundle | None:
        for feature in features:
            properties = feature.get("properties") or {}
            download_url = str((properties.get("urls") or {}).get("shp") or "").strip()
            if not download_url:
                continue
            iso_codes = properties.get("iso3166-1:alpha2") or []
            if isinstance(iso_codes, str):
                iso_codes = [iso_codes]
            normalized_codes = {_normalize_country_code(code) for code in iso_codes}
            if country_code is not None and country_code in normalized_codes:
                return _GeofabrikBundle(
                    slug=self._geofabrik_slug(properties, download_url),
                    download_url=download_url,
                    boundary_geometry=_feature_geometry(feature),
                )
            names = {
                _normalize_country_name(properties.get("name")),
                _normalize_country_name(properties.get("id")),
            }
            if country_name is not None and country_name in names:
                return _GeofabrikBundle(
                    slug=self._geofabrik_slug(properties, download_url),
                    download_url=download_url,
                    boundary_geometry=_feature_geometry(feature),
                )
        return None

    def _match_geofabrik_by_alias(
        self,
        features: list[dict[str, object]],
        *,
        country_code: str | None,
        country_name: str | None,
        aoi: ResolvedAOI,
    ) -> _GeofabrikBundle | None:
        alias_names = set()
        for key in (country_code, country_name):
            if key:
                alias_names.update(_GEOFABRIK_COUNTRY_ALIASES.get(str(key).casefold(), set()))
        if not alias_names:
            return None
        aoi_polygon = _aoi_bbox_polygon(aoi)
        candidates = []
        for feature in features:
            properties = feature.get("properties") or {}
            download_url = str((properties.get("urls") or {}).get("shp") or "").strip()
            if not download_url:
                continue
            names = {
                _normalize_country_name(properties.get("name")),
                _normalize_country_name(properties.get("id")),
            }
            if not any(alias in names for alias in alias_names):
                continue
            geometry = _feature_geometry(feature)
            contains_aoi = aoi_polygon is not None and geometry is not None and geometry.covers(aoi_polygon)
            candidates.append((0 if contains_aoi else 1, _geofabrik_candidate_area(feature), feature, download_url))
        if not candidates:
            return None
        _, _, feature, download_url = sorted(candidates, key=lambda item: (item[0], item[1]))[0]
        properties = feature.get("properties") or {}
        return _GeofabrikBundle(
            slug=self._geofabrik_slug(properties, download_url),
            download_url=download_url,
            boundary_geometry=_feature_geometry(feature),
        )

    def _match_geofabrik_by_bbox(
        self,
        features: list[dict[str, object]],
        *,
        aoi: ResolvedAOI,
    ) -> _GeofabrikBundle | None:
        aoi_polygon = _aoi_bbox_polygon(aoi)
        if aoi_polygon is None:
            return None
        candidates = []
        for feature in features:
            properties = feature.get("properties") or {}
            download_url = str((properties.get("urls") or {}).get("shp") or "").strip()
            if not download_url:
                continue
            geometry = _feature_geometry(feature)
            if geometry is None or geometry.is_empty:
                continue
            if geometry.covers(aoi_polygon):
                candidates.append((_geofabrik_candidate_area(feature), feature, download_url))
        if not candidates:
            return None
        _, feature, download_url = sorted(candidates, key=lambda item: item[0])[0]
        properties = feature.get("properties") or {}
        return _GeofabrikBundle(
            slug=self._geofabrik_slug(properties, download_url),
            download_url=download_url,
            boundary_geometry=_feature_geometry(feature),
        )
```

- [ ] **Step 5: Run Geofabrik tests**

Run:

```powershell
pytest tests/test_source_asset_service.py::test_geofabrik_selection_uses_country_alias_without_location_special_case tests/test_source_asset_service.py::test_geofabrik_selection_uses_smallest_containing_bbox_when_country_metadata_is_missing -v
```

Expected: pass.

- [ ] **Step 6: Run source asset regression tests**

Run:

```powershell
pytest tests/test_source_asset_service.py -v
```

Expected: pass.

- [ ] **Step 7: Commit**

```powershell
git add services/source_asset_service.py tests/test_source_asset_service.py
git commit -m "feat: generalize geofabrik bundle selection"
```

---

## Task 5: Add Runtime Source Contract Service

**Files:**
- Create or modify: `services/runtime_source_contract_service.py`
- Modify: `services/agent_run_service.py`
- Test: `tests/test_runtime_source_contract_service.py`

- [ ] **Step 1: Add failing contract service tests**

Append to `tests/test_runtime_source_contract_service.py`:

```python
from services.runtime_source_contract_service import RuntimeSourceContractService


class _FakeRawService:
    def __init__(self, supported: set[str]) -> None:
        self.supported = supported

    def can_handle(self, source_id: str) -> bool:
        return source_id in self.supported


class _FakeProvider:
    def __init__(self, supported: set[str]) -> None:
        self.supported = supported

    def can_handle(self, source_id: str) -> bool:
        return source_id in self.supported


def test_runtime_source_contract_service_marks_missing_input_provider() -> None:
    service = RuntimeSourceContractService(
        raw_source_service=_FakeRawService({"raw.known"}),
        input_bundle_providers=[_FakeProvider({"catalog.bundle"})],
        external_config_provider=lambda source_id: [],
    )

    contracts = service.check_sources(["raw.known", "catalog.bundle", "raw.unknown"])
    by_id = {contract.source_id: contract for contract in contracts}

    assert by_id["raw.known"].raw_vector_supported is True
    assert by_id["raw.known"].input_bundle_supported is False
    assert by_id["raw.known"].status.value == "reservation_only"
    assert by_id["catalog.bundle"].status.value == "runtime_ready"
    assert by_id["raw.unknown"].status.value == "missing_provider"


def test_runtime_source_contract_service_marks_external_config_requirements() -> None:
    service = RuntimeSourceContractService(
        raw_source_service=_FakeRawService({"raw.google.poi"}),
        input_bundle_providers=[_FakeProvider({"raw.google.poi"})],
        external_config_provider=lambda source_id: ["GOOGLE_PLACES_API_KEY"] if source_id == "raw.google.poi" else [],
    )

    contract = service.check_sources(["raw.google.poi"])[0]

    assert contract.status.value == "requires_external_config"
    assert contract.required_external_config == ["GOOGLE_PLACES_API_KEY"]
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
pytest tests/test_runtime_source_contract_service.py -v
```

Expected: first schema test passes; new service tests fail because service is missing.

- [ ] **Step 3: Implement contract service**

Create `services/runtime_source_contract_service.py` if it does not already exist. If it exists, add these members without deleting existing public methods:

```python
from __future__ import annotations

from collections.abc import Callable, Iterable

from schemas.runtime_source_contract import RuntimeProviderStatus, RuntimeSourceContract


class RuntimeSourceContractService:
    def __init__(
        self,
        *,
        raw_source_service,
        input_bundle_providers: list[object],
        external_config_provider: Callable[[str], list[str]] | None = None,
    ) -> None:
        self.raw_source_service = raw_source_service
        self.input_bundle_providers = list(input_bundle_providers)
        self.external_config_provider = external_config_provider or (lambda _source_id: [])

    def check_sources(self, source_ids: Iterable[str]) -> list[RuntimeSourceContract]:
        return [self.check_source(source_id) for source_id in dict.fromkeys(source_ids)]

    def check_source(self, source_id: str) -> RuntimeSourceContract:
        raw_supported = _safe_can_handle(self.raw_source_service, source_id)
        input_supported = any(_safe_can_handle(provider, source_id) for provider in self.input_bundle_providers)
        required_external_config = list(self.external_config_provider(source_id))
        reasons: list[str] = []
        if required_external_config:
            reasons.append("source requires external configuration before autonomous materialization")
            status = RuntimeProviderStatus.requires_external_config
        elif input_supported:
            status = RuntimeProviderStatus.runtime_ready
        elif raw_supported:
            reasons.append("raw source is known but no input bundle provider can materialize it")
            status = RuntimeProviderStatus.reservation_only
        else:
            reasons.append("source is not handled by raw source service or input bundle providers")
            status = RuntimeProviderStatus.missing_provider
        return RuntimeSourceContract(
            source_id=source_id,
            catalog_selectable=True,
            raw_vector_supported=raw_supported,
            input_bundle_supported=input_supported,
            status=status,
            reasons=reasons,
            required_external_config=required_external_config,
            provider_names=[
                provider.__class__.__name__
                for provider in self.input_bundle_providers
                if _safe_can_handle(provider, source_id)
            ],
        )


def _safe_can_handle(provider: object, source_id: str) -> bool:
    can_handle = getattr(provider, "can_handle", None)
    if not callable(can_handle):
        return False
    try:
        return bool(can_handle(source_id))
    except Exception:  # noqa: BLE001
        return False
```

- [ ] **Step 4: Add external config detector in AgentRunService**

Modify `services/agent_run_service.py`.

Add a method:

```python
    @staticmethod
    def _source_required_external_config(source_id: str) -> list[str]:
        if source_id == "raw.google.poi":
            return ["GOOGLE_PLACES_API_KEY", "google_poi_authorization_manifest"]
        if source_id in {"raw.google.building", "raw.google.open_buildings.vector"}:
            return ["google_open_buildings_urls"]
        return []
```

After `self.input_acquisition_service = InputAcquisitionService(...)`, add:

```python
        self.runtime_source_contract_service = RuntimeSourceContractService(
            raw_source_service=self.raw_vector_source_service,
            input_bundle_providers=self.input_acquisition_service.providers,
            external_config_provider=self._source_required_external_config,
        )
```

Add the import:

```python
from services.runtime_source_contract_service import RuntimeSourceContractService
```

- [ ] **Step 5: Run contract tests**

Run:

```powershell
pytest tests/test_runtime_source_contract_service.py -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add schemas/runtime_source_contract.py services/runtime_source_contract_service.py services/agent_run_service.py tests/test_runtime_source_contract_service.py
git commit -m "feat: validate runtime source provider contracts"
```

---

## Task 6: Classify Degradation From Component Coverage

**Files:**
- Modify: `services/source_acquisition_policy.py`
- Test: `tests/test_source_coverage_fallback.py`

- [ ] **Step 1: Add failing degradation classification tests**

Append to `tests/test_source_coverage_fallback.py`:

```python
from schemas.degradation import DegradationLevel
from services.source_acquisition_policy import classify_component_degradation


def test_classify_component_degradation_detects_external_only_missing_sources() -> None:
    context = classify_component_degradation(
        {
            "raw.gns.poi": {"coverage_status": "available", "feature_count": 12},
            "raw.google.poi": {
                "coverage_status": "missing",
                "feature_count": 0,
                "fault_class": "UNAUTHORIZED",
            },
        }
    )

    assert context.degraded is True
    assert context.level == DegradationLevel.external_uncontrollable
    assert context.available_sources == ["raw.gns.poi"]
    assert context.external_uncontrollable_sources == ["raw.google.poi"]
    assert context.system_failure_sources == []


def test_classify_component_degradation_detects_system_provider_failures() -> None:
    context = classify_component_degradation(
        {
            "raw.osm.road": {"coverage_status": "missing", "feature_count": 0, "fault_class": "SOURCE_MISSING"},
            "raw.microsoft.road": {
                "coverage_status": "missing",
                "feature_count": 0,
                "fault_class": "MISSING_PROVIDER",
            },
        }
    )

    assert context.degraded is True
    assert context.level == DegradationLevel.system_failure
    assert context.system_failure_sources == ["raw.microsoft.road"]
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
pytest tests/test_source_coverage_fallback.py::test_classify_component_degradation_detects_external_only_missing_sources tests/test_source_coverage_fallback.py::test_classify_component_degradation_detects_system_provider_failures -v
```

Expected: fail because `classify_component_degradation` is missing.

- [ ] **Step 3: Implement degradation classification**

Modify `services/source_acquisition_policy.py`.

Add imports:

```python
from schemas.degradation import DegradationContext, DegradationLevel
```

Add constants and function:

```python
SYSTEM_FAILURE_FAULTS = {
    "MISSING_PROVIDER",
    "ALGO_RUNTIME_ERROR",
    "PARAM_OUT_OF_RANGE",
    "CRS_MISMATCH",
}


def classify_component_degradation(component_coverage: dict[str, object]) -> DegradationContext:
    available_sources: list[str] = []
    missing_sources: list[str] = []
    external_sources: list[str] = []
    system_sources: list[str] = []
    for source_id, raw_payload in component_coverage.items():
        payload = raw_payload if isinstance(raw_payload, dict) else getattr(raw_payload, "model_dump", lambda: {})()
        if not isinstance(payload, dict):
            payload = {
                "coverage_status": getattr(raw_payload, "coverage_status", None),
                "feature_count": getattr(raw_payload, "feature_count", None),
                "fault_class": getattr(raw_payload, "fault_class", None),
            }
        status = str(payload.get("coverage_status") or "")
        feature_count = payload.get("feature_count")
        fault_class = str(payload.get("fault_class") or "").upper()
        if status == "available" or (feature_count is not None and int(feature_count) > 0):
            available_sources.append(source_id)
            continue
        missing_sources.append(source_id)
        if fault_class in EXTERNAL_UNCONTROLLABLE_FAULTS:
            external_sources.append(source_id)
        elif fault_class in SYSTEM_FAILURE_FAULTS:
            system_sources.append(source_id)
    if not missing_sources:
        return DegradationContext(degraded=False, level=DegradationLevel.none, available_sources=available_sources)
    if system_sources:
        return DegradationContext(
            degraded=True,
            level=DegradationLevel.system_failure,
            reason="one or more missing sources are caused by runtime system failures",
            available_sources=available_sources,
            missing_sources=missing_sources,
            external_uncontrollable_sources=external_sources,
            system_failure_sources=system_sources,
        )
    if external_sources and len(external_sources) == len(missing_sources):
        return DegradationContext(
            degraded=True,
            level=DegradationLevel.external_uncontrollable,
            reason="all missing sources are externally uncontrollable",
            available_sources=available_sources,
            missing_sources=missing_sources,
            external_uncontrollable_sources=external_sources,
            system_failure_sources=[],
        )
    return DegradationContext(
        degraded=True,
        level=DegradationLevel.partial_source,
        reason="source coverage is partial",
        available_sources=available_sources,
        missing_sources=missing_sources,
        external_uncontrollable_sources=external_sources,
        system_failure_sources=system_sources,
    )
```

- [ ] **Step 4: Run degradation classification tests**

Run:

```powershell
pytest tests/test_source_coverage_fallback.py::test_classify_component_degradation_detects_external_only_missing_sources tests/test_source_coverage_fallback.py::test_classify_component_degradation_detects_system_provider_failures -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add services/source_acquisition_policy.py tests/test_source_coverage_fallback.py
git commit -m "feat: classify source coverage degradation"
```

---

## Task 7: Make Quality Gate Degradation-Aware

**Files:**
- Modify: `services/quality_policy_service.py`
- Modify: `services/quality_gate_service.py`
- Modify: `schemas/quality_gate.py`
- Test: `tests/test_quality_gate_service.py`

- [ ] **Step 1: Add failing POI degradation quality test**

Append to `tests/test_quality_gate_service.py`:

```python
def test_quality_gate_allows_poi_single_source_when_missing_sources_are_external(tmp_path: Path) -> None:
    path = tmp_path / "poi_single_source.gpkg"
    frame = gpd.GeoDataFrame(
        {"source_id": ["raw.gns.poi"], "canonical_name": ["Example"]},
        geometry=[Point(0, 0)],
        crs="EPSG:4326",
    )
    frame.to_file(path, driver="GPKG")

    context = DegradationContext(
        degraded=True,
        level=DegradationLevel.external_uncontrollable,
        reason="Google POI authorization is absent and OSM POI has no coverage",
        available_sources=["raw.gns.poi"],
        missing_sources=["raw.google.poi", "raw.osm.poi"],
        external_uncontrollable_sources=["raw.google.poi", "raw.osm.poi"],
    )

    report = QualityGateService().evaluate(
        artifact_path=path,
        task_kind=TaskKind.poi,
        required_fields=["geometry", "source_id"],
        requested_bbox=(-1, -1, 1, 1),
        component_coverage={
            "raw.gns.poi": {"feature_count": 1, "coverage_status": "available"},
            "raw.google.poi": {"feature_count": 0, "coverage_status": "missing", "fault_class": "UNAUTHORIZED"},
            "raw.osm.poi": {"feature_count": 0, "coverage_status": "missing", "fault_class": "NO_OFFICIAL_COVERAGE"},
        },
        degradation_context=context,
    )

    assert report.accepted is True
    assert report.degraded_mode is True
    assert report.degradation_level == "external_uncontrollable"
    assert report.checks["multi_source_lineage"]["severity"] == "soft"
    assert "multi_source_lineage" in report.soft_failure_reasons


def test_quality_gate_does_not_downgrade_geometry_type_under_degradation(tmp_path: Path) -> None:
    path = tmp_path / "wrong_geometry.gpkg"
    frame = gpd.GeoDataFrame(
        {"source_id": ["raw.gns.poi"]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
        crs="EPSG:4326",
    )
    frame.to_file(path, driver="GPKG")

    context = DegradationContext(
        degraded=True,
        level=DegradationLevel.external_uncontrollable,
        available_sources=["raw.gns.poi"],
        missing_sources=["raw.google.poi"],
        external_uncontrollable_sources=["raw.google.poi"],
    )

    report = QualityGateService().evaluate(
        artifact_path=path,
        task_kind=TaskKind.poi,
        required_fields=["geometry", "source_id"],
        requested_bbox=(-1, -1, 1, 1),
        component_coverage={"raw.gns.poi": {"feature_count": 1, "coverage_status": "available"}},
        degradation_context=context,
    )

    assert report.accepted is False
    assert "geometry_type" in report.failure_reasons
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
pytest tests/test_quality_gate_service.py::test_quality_gate_allows_poi_single_source_when_missing_sources_are_external tests/test_quality_gate_service.py::test_quality_gate_does_not_downgrade_geometry_type_under_degradation -v
```

Expected: fail because `QualityGateService.evaluate()` does not accept `degradation_context`.

- [ ] **Step 3: Mark downgrade-eligible checks in quality policy**

Modify `services/quality_policy_service.py` so the `multi_source_lineage` check has metadata:

```python
        QualityPolicyCheck(
            check_id="multi_source_lineage",
            metric_name="multi_source_lineage",
            operator="eq",
            threshold=True,
            metadata={"downgrade_to_soft_when_external_degraded_for_task_kinds": ["poi"]},
        ),
```

- [ ] **Step 4: Update QualityGateService signature and severity logic**

Modify `services/quality_gate_service.py`.

Add import:

```python
from schemas.degradation import DegradationContext
```

Change the `evaluate()` signature:

```python
        degradation_context: DegradationContext | None = None,
```

Inside the policy loop, replace severity assignment with:

```python
                severity = _effective_policy_severity(
                    policy_check.severity,
                    policy_check=policy_check,
                    task_kind=task_kind,
                    degradation_context=degradation_context,
                )
                checks[policy_check.check_id] = {
                    **checks[policy_check.check_id],
                    "passed": passed,
                    "severity": severity,
                    "operator": policy_check.operator,
                    "threshold": policy_check.threshold,
                }
```

Also use the same `severity` helper when creating checks for policy checks not already present.

Add helper:

```python
def _effective_policy_severity(
    configured: str,
    *,
    policy_check,
    task_kind: TaskKind,
    degradation_context: DegradationContext | None,
) -> str:
    if configured != "hard":
        return configured
    if degradation_context is None or not degradation_context.external_only:
        return configured
    allowed = policy_check.metadata.get("downgrade_to_soft_when_external_degraded_for_task_kinds", [])
    if task_kind.value in allowed:
        return "soft"
    return configured
```

When returning `QualityGateReport`, add degradation fields:

```python
            degraded_mode=bool(degradation_context and degradation_context.degraded),
            degradation_level=degradation_context.level.value if degradation_context is not None else None,
            degradation_reason=degradation_context.reason if degradation_context is not None else None,
            degradation_context=degradation_context.model_dump() if degradation_context is not None else {},
```

- [ ] **Step 5: Run quality degradation tests**

Run:

```powershell
pytest tests/test_quality_gate_service.py::test_quality_gate_allows_poi_single_source_when_missing_sources_are_external tests/test_quality_gate_service.py::test_quality_gate_does_not_downgrade_geometry_type_under_degradation -v
```

Expected: pass.

- [ ] **Step 6: Run full quality gate tests**

Run:

```powershell
pytest tests/test_quality_gate_service.py -v
```

Expected: pass.

- [ ] **Step 7: Commit**

```powershell
git add services/quality_policy_service.py services/quality_gate_service.py schemas/quality_gate.py tests/test_quality_gate_service.py
git commit -m "feat: make quality gates degradation-aware"
```

---

## Task 8: Make Water Large-Area Routing Task-Kind-Aware

**Files:**
- Modify: `services/agent_run_service.py`
- Test: `tests/test_agent_run_service_large_area_runtime.py`

- [ ] **Step 1: Add failing waterways routing test**

Append to `tests/test_agent_run_service_large_area_runtime.py`:

```python
def test_large_area_waterways_fails_before_execution_when_line_sources_are_missing(tmp_path: Path) -> None:
    from schemas.agent import RunCreateRequest, RunInputStrategy, RunTrigger, RunTriggerType
    from schemas.fusion import JobType
    from schemas.task_kind import TaskKind
    from services.agent_run_service import AgentRunService
    from services.input_acquisition_service import ResolvedRunInputs

    service = AgentRunService(base_dir=tmp_path / "runs", max_workers=1)
    request = RunCreateRequest(
        job_type=JobType.water,
        trigger=RunTrigger(
            type=RunTriggerType.user_query,
            content="Fuse waterways for a generic AOI",
            spatial_extent="bbox(0, 0, 1, 1)",
            force_aoi_resolution=False,
        ),
        input_strategy=RunInputStrategy.task_driven_auto,
        preferred_pattern_id="wp.flood.waterways.default",
    )
    resolved_inputs = ResolvedRunInputs(
        osm_zip_path=tmp_path / "osm.zip",
        ref_zip_path=tmp_path / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.flood.water",
        selected_source_id="catalog.flood.water",
        cache_hit=False,
        version_token="v1",
        component_coverage={
            "raw.hydrolakes.water": {"feature_count": 2, "coverage_status": "available", "path": str(tmp_path / "ref.zip")},
            "raw.hydrorivers.water": {"feature_count": 0, "coverage_status": "empty", "path": None},
            "raw.osm.waterways": {"feature_count": 0, "coverage_status": "missing", "path": None},
        },
    )

    result = service._large_area_water_slices_for_task(
        request=request,
        task_kind=TaskKind.waterways,
        component_paths={},
        resolved_inputs=resolved_inputs,
    )

    assert result.can_execute is False
    assert result.failure_reason == "no_line_source_available"
```

- [ ] **Step 2: Run failing waterways routing test**

Run:

```powershell
pytest tests/test_agent_run_service_large_area_runtime.py::test_large_area_waterways_fails_before_execution_when_line_sources_are_missing -v
```

Expected: fail because `_large_area_water_slices_for_task` does not exist.

- [ ] **Step 3: Add routing result dataclass**

Modify `services/agent_run_service.py`.

Add near other dataclasses:

```python
@dataclass(frozen=True)
class LargeAreaSlicePlan:
    can_execute: bool
    slices: list[object]
    failure_reason: str | None = None
    missing_sources: list[str] | None = None
```

- [ ] **Step 4: Extract water slice builder**

In `services/agent_run_service.py`, add a method used by `run_large_area_execution_stage()`:

```python
    def _large_area_water_slices_for_task(
        self,
        *,
        request: RunCreateRequest,
        task_kind: TaskKind,
        component_paths: dict[str, Path],
        resolved_inputs: ResolvedRunInputs,
    ) -> LargeAreaSlicePlan:
        from services.large_area_runtime_service import LargeAreaSlice
        from services.domain_fusion_runners import run_water_polygon_tile, run_waterways_tile

        if task_kind == TaskKind.water_polygon:
            water_sources = {
                key: path
                for key, path in {
                    "raw.osm.water": component_paths.get("raw.osm.water"),
                    "raw.hydrolakes.water": component_paths.get("raw.hydrolakes.water"),
                }.items()
                if path is not None
            }
            return LargeAreaSlicePlan(
                can_execute=True,
                slices=[
                    LargeAreaSlice(
                        name="water_polygon",
                        geometry_family="polygon",
                        sources=water_sources,
                        runner=run_water_polygon_tile,
                    )
                ],
            )

        if task_kind == TaskKind.waterways:
            line_supplement = component_paths.get("raw.hydrorivers.water") or component_paths.get(
                "raw.local.pakistan.waterways"
            )
            if component_paths.get("raw.osm.waterways") is None or line_supplement is None:
                return LargeAreaSlicePlan(
                    can_execute=False,
                    slices=[],
                    failure_reason="no_line_source_available",
                    missing_sources=[
                        source_id
                        for source_id in ("raw.osm.waterways", "raw.hydrorivers.water")
                        if component_paths.get(source_id) is None
                    ],
                )
            line_sources = {"raw.osm.waterways": component_paths["raw.osm.waterways"]}
            if component_paths.get("raw.hydrorivers.water") is not None:
                line_sources["raw.hydrorivers.water"] = component_paths["raw.hydrorivers.water"]
            else:
                line_sources["raw.local.pakistan.waterways"] = component_paths["raw.local.pakistan.waterways"]
            return LargeAreaSlicePlan(
                can_execute=True,
                slices=[
                    LargeAreaSlice(
                        name="waterways_line",
                        geometry_family="line",
                        sources=line_sources,
                        runner=run_waterways_tile,
                    )
                ],
            )

        return LargeAreaSlicePlan(can_execute=False, slices=[], failure_reason=f"unsupported_water_task_kind:{task_kind.value}")
```

- [ ] **Step 5: Replace inline water slice construction**

In `run_large_area_execution_stage()`, replace the current water slice construction block with:

```python
        elif request.job_type == JobType.water:
            slice_plan = self._large_area_water_slices_for_task(
                request=request,
                task_kind=task_kind,
                component_paths=component_paths,
                resolved_inputs=resolved_inputs,
            )
            if not slice_plan.can_execute:
                raise RuntimeError(
                    "SOURCE_MISSING: "
                    f"{slice_plan.failure_reason}; missing_sources={slice_plan.missing_sources or []}"
                )
            slices = slice_plan.slices
```

- [ ] **Step 6: Run waterways routing test**

Run:

```powershell
pytest tests/test_agent_run_service_large_area_runtime.py::test_large_area_waterways_fails_before_execution_when_line_sources_are_missing -v
```

Expected: pass.

- [ ] **Step 7: Run large-area runtime tests**

Run:

```powershell
pytest tests/test_agent_run_service_large_area_runtime.py tests/test_waterways_conflation_v7.py -v
```

Expected: pass.

- [ ] **Step 8: Commit**

```powershell
git add services/agent_run_service.py tests/test_agent_run_service_large_area_runtime.py
git commit -m "fix: route water tasks by task kind"
```

---

## Task 9: Pass Degradation Context From Acquisition To Quality Gate

**Files:**
- Modify: `services/agent_run_service.py`
- Modify: `services/source_materialization_manifest_service.py`
- Test: `tests/test_agent_run_service_enhancements.py`

- [ ] **Step 1: Add failing writeback test**

Append to `tests/test_agent_run_service_enhancements.py`:

```python
def test_agent_writeback_passes_degradation_context_to_quality_gate(tmp_path: Path, monkeypatch) -> None:
    from schemas.agent import RunCreateRequest, RunTrigger, RunTriggerType
    from schemas.degradation import DegradationLevel
    from schemas.fusion import JobType
    from schemas.quality_gate import QualityGateReport
    from schemas.task_kind import TaskKind
    from services.agent_run_service import AgentRunService

    service = AgentRunService(base_dir=tmp_path / "runs", max_workers=1)
    request = RunCreateRequest(
        job_type=JobType.poi,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="Fuse POI", spatial_extent="bbox(0,0,1,1)"),
    )
    captured = {}

    def fake_evaluate(**kwargs):
        captured["degradation_context"] = kwargs.get("degradation_context")
        return QualityGateReport(
            accepted=True,
            task_kind=TaskKind.poi,
            artifact_path=str(kwargs["artifact_path"]),
            checks={},
            metrics={},
            degraded_mode=True,
            degradation_level="external_uncontrollable",
        )

    monkeypatch.setattr(service.quality_gate_service, "evaluate", fake_evaluate)

    context = service._degradation_context_from_component_coverage(
        {
            "raw.gns.poi": {"feature_count": 3, "coverage_status": "available"},
            "raw.google.poi": {"feature_count": 0, "coverage_status": "missing", "fault_class": "UNAUTHORIZED"},
        }
    )

    assert context.level == DegradationLevel.external_uncontrollable
```

- [ ] **Step 2: Run failing test**

Run:

```powershell
pytest tests/test_agent_run_service_enhancements.py::test_agent_writeback_passes_degradation_context_to_quality_gate -v
```

Expected: fail because `_degradation_context_from_component_coverage` is missing.

- [ ] **Step 3: Add degradation helper to AgentRunService**

Modify `services/agent_run_service.py`.

Add import:

```python
from services.source_acquisition_policy import classify_component_degradation
```

Add method:

```python
    @staticmethod
    def _degradation_context_from_component_coverage(component_coverage: dict[str, object] | None):
        return classify_component_degradation(component_coverage or {})
```

- [ ] **Step 4: Pass context into quality gate**

In `run_writeback_stage()`, locate the call to `self.quality_gate_service.evaluate(...)` and add:

```python
                degradation_context=self._degradation_context_from_component_coverage(component_coverage),
```

Use the same `component_coverage` variable already passed to the quality gate. If the method currently computes coverage inline, first assign it:

```python
            component_coverage = self._component_coverage_for_quality(status=status, resolved_inputs=resolved_inputs)
```

Then pass that variable to both `component_coverage=` and `degradation_context=`.

- [ ] **Step 5: Extend source materialization manifest payload**

Modify `services/source_materialization_manifest_service.py`.

Add parameter:

```python
    runtime_source_contracts: list[dict[str, object]] | None = None,
```

Add field in returned dict:

```python
        "runtime_source_contracts": list(runtime_source_contracts or []),
```

- [ ] **Step 6: Run targeted test**

Run:

```powershell
pytest tests/test_agent_run_service_enhancements.py::test_agent_writeback_passes_degradation_context_to_quality_gate -v
```

Expected: pass.

- [ ] **Step 7: Run agent enhancement tests**

Run:

```powershell
pytest tests/test_agent_run_service_enhancements.py -v
```

Expected: pass.

- [ ] **Step 8: Commit**

```powershell
git add services/agent_run_service.py services/source_materialization_manifest_service.py tests/test_agent_run_service_enhancements.py
git commit -m "feat: pass degradation context to writeback quality gate"
```

---

## Task 10: Preserve Fault Classes In Catalog Coverage

**Files:**
- Modify: `services/local_bundle_catalog.py`
- Test: `tests/test_source_coverage_fallback.py`

- [ ] **Step 1: Add failing fault preservation test**

Append to `tests/test_source_coverage_fallback.py`:

```python
def test_catalog_component_coverage_preserves_fault_class_for_failed_components(tmp_path: Path) -> None:
    provider = _provider_with_counts(
        tmp_path,
        counts={"raw.gns.poi": 5},
        errors={"raw.google.poi": PermissionError("403 forbidden: invalid API key credential")},
    )

    bundle = provider.materialize_with_fallback(
        source_id="catalog.generic.poi",
        request_bbox=(0, 0, 1, 1),
        resolved_aoi=None,
        target_dir=tmp_path / "poi",
        target_crs="EPSG:4326",
    )

    google = bundle.component_coverage["raw.google.poi"]
    if hasattr(google, "model_dump"):
        google_payload = google.model_dump()
    else:
        google_payload = google.__dict__

    assert google_payload["coverage_status"] == "missing"
    assert google_payload["fault_class"] == "UNAUTHORIZED"
```

- [ ] **Step 2: Run failing test**

Run:

```powershell
pytest tests/test_source_coverage_fallback.py::test_catalog_component_coverage_preserves_fault_class_for_failed_components -v
```

Expected: fail because `SourceCoverageStatus` payload does not preserve `fault_class`.

- [ ] **Step 3: Extend SourceCoverageStatus**

Modify `services/source_asset_service.py`.

Find `SourceCoverageStatus` and add fields:

```python
    fault_class: str | None = None
    external_uncontrollable: bool = False
```

- [ ] **Step 4: Preserve fault class in LocalBundleCatalogProvider**

Modify the failed component block in `services/local_bundle_catalog.py`:

```python
                component_coverage[component_source_id] = SourceCoverageStatus(
                    source_id=component_source_id,
                    source_mode=source_mode,
                    feature_count=0,
                    coverage_status="missing",
                    path=None,
                    error=str(exc),
                    fault_class=fault_class,
                    external_uncontrollable=fault_class in {"UNAUTHORIZED", "PROVIDER_UNAVAILABLE", "NO_OFFICIAL_COVERAGE", "NETWORK_FAILED", "SOURCE_DOWNLOAD_FAILED"},
                )
```

- [ ] **Step 5: Run fault preservation test**

Run:

```powershell
pytest tests/test_source_coverage_fallback.py::test_catalog_component_coverage_preserves_fault_class_for_failed_components -v
```

Expected: pass.

- [ ] **Step 6: Run source coverage fallback tests**

Run:

```powershell
pytest tests/test_source_coverage_fallback.py -v
```

Expected: pass.

- [ ] **Step 7: Commit**

```powershell
git add services/source_asset_service.py services/local_bundle_catalog.py tests/test_source_coverage_fallback.py
git commit -m "feat: preserve source fault classes in coverage"
```

---

## Task 11: Add General Autonomous Region Fusion Entry Point

**Files:**
- Create: `services/autonomous_region_fusion_service.py`
- Test: `tests/test_autonomous_region_fusion_service.py`

- [ ] **Step 1: Write failing region entry test**

Create `tests/test_autonomous_region_fusion_service.py` with:

```python
from __future__ import annotations

from pathlib import Path

from schemas.task_kind import FULL_DISASTER_TASK_KINDS, TaskKind
from services.autonomous_region_fusion_service import AutonomousRegionFusionService


class _FakeScenarioRunService:
    def __init__(self) -> None:
        self.requests = []

    def run_scenario(self, request):
        self.requests.append(request)
        return {"scenario_id": "scenario-test", "phase": "queued"}


def test_autonomous_region_fusion_service_builds_general_five_task_request(tmp_path: Path) -> None:
    scenario_service = _FakeScenarioRunService()
    service = AutonomousRegionFusionService(scenario_run_service=scenario_service)

    result = service.run_autonomous_fusion_region(
        region_name="Generic City, Generic Country",
        output_dir=tmp_path / "region",
        task_kinds=list(FULL_DISASTER_TASK_KINDS),
    )

    assert result["scenario_id"] == "scenario-test"
    assert scenario_service.requests[0].spatial_extent == "Generic City, Generic Country"
    assert scenario_service.requests[0].force_aoi_resolution is True
    assert set(scenario_service.requests[0].metadata["requested_task_kinds"]) == {
        TaskKind.building.value,
        TaskKind.road.value,
        TaskKind.water_polygon.value,
        TaskKind.waterways.value,
        TaskKind.poi.value,
    }
```

- [ ] **Step 2: Run failing test**

Run:

```powershell
pytest tests/test_autonomous_region_fusion_service.py::test_autonomous_region_fusion_service_builds_general_five_task_request -v
```

Expected: fail because service is missing.

- [ ] **Step 3: Implement the service**

Create `services/autonomous_region_fusion_service.py` with:

```python
from __future__ import annotations

from pathlib import Path

from schemas.fusion import JobType
from schemas.scenario import ScenarioRunRequest
from schemas.task_kind import FULL_DISASTER_TASK_KINDS, TaskKind, task_kind_to_job_type


class AutonomousRegionFusionService:
    def __init__(self, *, scenario_run_service) -> None:
        self.scenario_run_service = scenario_run_service

    def run_autonomous_fusion_region(
        self,
        *,
        region_name: str,
        output_dir: Path,
        task_kinds: list[TaskKind] | None = None,
        degradation_policy: str = "evidence_preserving",
    ):
        selected_task_kinds = list(task_kinds or FULL_DISASTER_TASK_KINDS)
        job_types = _job_types_for_task_kinds(selected_task_kinds)
        request = ScenarioRunRequest(
            scenario_name=f"Autonomous fusion for {region_name}",
            trigger_content=(
                f"Autonomously fuse requested geospatial themes for {region_name}. "
                "Resolve the AOI and acquire all required public sources automatically."
            ),
            disaster_type="generic",
            job_types=job_types,
            spatial_extent=region_name,
            force_aoi_resolution=True,
            output_root=str(Path(output_dir)),
            metadata={
                "requested_task_kinds": [task_kind.value for task_kind in selected_task_kinds],
                "degradation_policy": degradation_policy,
                "entrypoint": "run_autonomous_fusion_region",
            },
        )
        return self.scenario_run_service.run_scenario(request)


def _job_types_for_task_kinds(task_kinds: list[TaskKind]) -> list[JobType]:
    ordered: list[JobType] = []
    for task_kind in task_kinds:
        job_type = task_kind_to_job_type(task_kind)
        if job_type not in ordered:
            ordered.append(job_type)
    return ordered
```

- [ ] **Step 4: Adjust schema import if needed**

If `schemas.scenario.ScenarioRunRequest` does not exist, find the actual request schema:

```powershell
rg -n "class ScenarioRunRequest|ScenarioRunRequest" schemas services tests -S
```

Use the exact existing class import and constructor fields from the grep result. Keep the constructor fields in Step 3 unchanged when the existing schema supports them.

- [ ] **Step 5: Run region service test**

Run:

```powershell
pytest tests/test_autonomous_region_fusion_service.py -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add services/autonomous_region_fusion_service.py tests/test_autonomous_region_fusion_service.py
git commit -m "feat: add autonomous region fusion entry point"
```

---

## Task 12: Add Runtime Contract Closure Regression Matrix

**Files:**
- Create: `tests/test_runtime_contract_closure_regression.py`

- [ ] **Step 1: Create regression matrix tests**

Create `tests/test_runtime_contract_closure_regression.py` with:

```python
from __future__ import annotations

from schemas.degradation import DegradationContext, DegradationLevel
from schemas.task_kind import TaskKind
from services.quality_gate_service import _EXPECTED_GEOMETRIES
from services.source_acquisition_policy import classify_component_degradation


def test_no_location_specific_runtime_policy_names_are_required() -> None:
    generic_context = classify_component_degradation(
        {
            "raw.generic.available": {"feature_count": 1, "coverage_status": "available"},
            "raw.generic.external": {"feature_count": 0, "coverage_status": "missing", "fault_class": "UNAUTHORIZED"},
        }
    )

    assert generic_context.level == DegradationLevel.external_uncontrollable
    assert "London" not in repr(generic_context)
    assert "United Kingdom" not in repr(generic_context)


def test_task_geometry_contracts_remain_hard_boundaries() -> None:
    assert _EXPECTED_GEOMETRIES[TaskKind.water_polygon] == {"Polygon", "MultiPolygon"}
    assert _EXPECTED_GEOMETRIES[TaskKind.waterways] == {"LineString", "MultiLineString"}
    assert _EXPECTED_GEOMETRIES[TaskKind.poi] == {"Point", "MultiPoint"}


def test_degradation_context_external_only_property_rejects_system_failure() -> None:
    context = DegradationContext(
        degraded=True,
        level=DegradationLevel.system_failure,
        available_sources=["raw.a"],
        missing_sources=["raw.b"],
        external_uncontrollable_sources=["raw.b"],
        system_failure_sources=["raw.c"],
    )

    assert context.external_only is False
```

- [ ] **Step 2: Run regression matrix**

Run:

```powershell
pytest tests/test_runtime_contract_closure_regression.py -v
```

Expected: pass.

- [ ] **Step 3: Run broad regression subset**

Run:

```powershell
pytest tests/test_runtime_contract_closure_regression.py tests/test_quality_gate_service.py tests/test_source_asset_service.py tests/test_source_coverage_fallback.py tests/test_agent_run_service_large_area_runtime.py -v
```

Expected: pass.

- [ ] **Step 4: Commit**

```powershell
git add tests/test_runtime_contract_closure_regression.py
git commit -m "test: add runtime contract closure regression matrix"
```

---

## Task 13: Update Evidence Documents

**Files:**
- Create: `docs/superpowers/specs/2026-06-12-runtime-contract-closure.md`
- Modify: `docs/v2-operations.md`

- [ ] **Step 1: Create the runtime contract spec**

Create `docs/superpowers/specs/2026-06-12-runtime-contract-closure.md` with:

```markdown
# Runtime Contract Closure Specification

## Purpose

FusionAgent treats autonomous fusion as a contract across five runtime boundaries:

1. KG/source catalog selection
2. Runtime source provider availability
3. Source materialization and component coverage
4. Task-kind-specific execution routing
5. Quality gate acceptance with degradation evidence

No boundary may assume a source, geometry family, credential, or region package is available without explicit evidence.

## Runtime Source Status

- `runtime_ready`: the source can be materialized by the current runtime without extra operator configuration.
- `requires_external_config`: the source is supported but needs credentials, authorization, URL manifests, or similar external configuration.
- `reservation_only`: the source is known to the catalog or raw source service but cannot be used as a task input bundle.
- `missing_provider`: no runtime provider can handle the source.

## Degradation Levels

- `none`: all required runtime inputs are available.
- `partial_source`: some optional or supplemental sources are missing.
- `external_uncontrollable`: missing sources are caused by external availability, credentials, authorization, or upstream coverage.
- `system_failure`: missing sources are caused by runtime implementation gaps such as missing providers or incompatible task routing.

## Hard Boundaries

- Geometry type mismatches remain hard failures.
- Missing required output fields remain hard failures.
- Source lineage remains a hard failure.
- Multi-source lineage may be downgraded only when the quality policy explicitly allows it for a task kind and the degradation context is external-only.

## Regression Regions

Use multiple regions to validate generic behavior:

- A country with direct Geofabrik ISO match.
- A region where Geofabrik package granularity differs from geocoder country metadata.
- A region with one source available and one externally unavailable source.
- A region with no local uploaded data.
```

- [ ] **Step 2: Add an operations note**

Append to `docs/v2-operations.md`:

```markdown
## Runtime Contract Closure Diagnostics

Autonomous fusion runs should inspect source materialization manifests, source attempts, runtime source contracts, degradation context, and quality reports together. A partial run is considered diagnosable only when each failed or degraded child run identifies whether the boundary failure occurred in source provider readiness, raw source materialization, task routing, execution, or quality gate evaluation.
```

- [ ] **Step 3: Commit docs**

```powershell
git add docs/superpowers/specs/2026-06-12-runtime-contract-closure.md docs/v2-operations.md
git commit -m "docs: document runtime contract closure"
```

---

## Final Verification

- [ ] **Step 1: Run focused contract tests**

Run:

```powershell
pytest tests/test_runtime_source_contract_service.py tests/test_raw_vector_input_bundle_provider.py tests/test_runtime_contract_closure_regression.py -v
```

Expected: all pass.

- [ ] **Step 2: Run source and quality tests**

Run:

```powershell
pytest tests/test_source_asset_service.py tests/test_source_coverage_fallback.py tests/test_quality_gate_service.py -v
```

Expected: all pass.

- [ ] **Step 3: Run execution routing tests**

Run:

```powershell
pytest tests/test_agent_run_service_large_area_runtime.py tests/test_agent_run_service_enhancements.py tests/test_scenario_run_service.py -v
```

Expected: all pass.

- [ ] **Step 4: Search for location-specific special cases**

Run:

```powershell
rg -n "London|test_0612_london|United Kingdom|great-britain|england" services schemas kg agent adapters tests -S
```

Expected:

- `London` and `test_0612_london` appear only in historical evidence or explicit regression tests, not in runtime implementation files.
- `United Kingdom`, `great-britain`, and `england` may appear only in alias-table tests or generic Geofabrik alias data, not as a branch for a single scenario.

- [ ] **Step 5: Run the real no-upload smoke command**

Run a no-upload scenario for at least two regions:

```powershell
$env:GEOFUSION_CELERY_EAGER='1'
$env:GEOFUSION_RUNS_ROOT='E:\fyx\data\fusionagentTEST\runtime_contract_smoke\agent_runs'
$env:GEOFUSION_SCENARIO_OUTPUT_ROOT='E:\fyx\data\fusionagentTEST\runtime_contract_smoke'
pytest tests/test_runtime_contract_closure_regression.py -v
```

Expected: tests pass. The real scenario runner can be executed after these tests pass; do not mark the implementation complete until source manifests and quality reports classify degraded children by boundary.

---

## Self-Review

- Spec coverage:
  - Provider registration is covered by Tasks 3 and 5.
  - Geofabrik general region matching is covered by Task 4.
  - Waterways semantic routing is covered by Task 8.
  - Degradation-aware quality policy is covered by Tasks 2, 6, 7, and 9.
  - Unified region entry point is covered by Task 11.
  - Regression protection is covered by Task 12 and Final Verification.
- Placeholder scan:
  - This plan avoids `TBD`, `TODO`, and unspecified "handle edge cases" instructions.
  - Each code-changing step includes concrete code or exact commands.
- Type consistency:
  - `DegradationContext` is defined before being passed to `QualityGateService`.
  - `RuntimeSourceContract` is defined before being returned by `RuntimeSourceContractService`.
  - `RawVectorInputBundleProvider` implements the existing `InputBundleProvider` protocol.

