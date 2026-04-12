# Source Catalog Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the knowledge-graph source catalog and local bundle provider so current task-driven building/road runs can choose richer OSM/Google/Microsoft bundle sources while raw water/POI/open-data sources become visible for later download and enrichment stages.

**Architecture:** Introduce one shared source-catalog definition layer that describes both KG-visible `DataSourceNode` metadata and locally materializable bundle pairings. Keep the current executor unchanged: building/road runs still consume `osm.zip` and `ref.zip`, but the planner and provider will now agree on more concrete source identities and component-source metadata.

**Tech Stack:** Python, dataclasses, GeoPandas, existing KG seed/bootstrap flow, pytest

---

## File Structure

### Existing files to modify

- Modify: `E:\vscode\fusionAgent\kg\seed.py`
- Modify: `E:\vscode\fusionAgent\services\local_bundle_catalog.py`
- Modify: `E:\vscode\fusionAgent\tests\test_kg_repository_enhancements.py`
- Modify: `E:\vscode\fusionAgent\tests\test_planner_context.py`
- Modify: `E:\vscode\fusionAgent\README.md`

### New files to create

- Create: `E:\vscode\fusionAgent\kg\source_catalog.py`
- Create: `E:\vscode\fusionAgent\tests\test_local_bundle_catalog.py`

---

### Task 1: Introduce A Shared Source Catalog Definition Layer

**Files:**
- Create: `E:\vscode\fusionAgent\kg\source_catalog.py`
- Modify: `E:\vscode\fusionAgent\kg\seed.py`
- Modify: `E:\vscode\fusionAgent\tests\test_kg_repository_enhancements.py`
- Modify: `E:\vscode\fusionAgent\tests\test_planner_context.py`

- [x] **Step 1: Write the failing repository test for expanded bundle and raw source coverage**

```python
def test_repository_exposes_bundle_and_raw_sources_for_catalog_expansion() -> None:
    repo = InMemoryKGRepository()

    bundle_sources = repo.get_candidate_data_sources(
        job_type=JobType.building,
        disaster_type="flood",
        required_type="dt.building.bundle",
        limit=8,
    )
    raw_sources = repo.get_candidate_data_sources(
        job_type=JobType.building,
        disaster_type="generic",
        required_type="dt.raw.vector",
        limit=16,
    )

    bundle_ids = {source.source_id for source in bundle_sources}
    raw_ids = {source.source_id for source in raw_sources}

    assert "catalog.flood.building" in bundle_ids
    assert "catalog.earthquake.building" in bundle_ids
    assert "raw.osm.water" in raw_ids
    assert "raw.osm.poi" in raw_ids
    assert "raw.microsoft.building" in raw_ids
    assert "raw.google.building" in raw_ids
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_kg_repository_enhancements.py -k catalog_expansion`

Expected: FAIL because the raw source ids do not exist yet and the bundle metadata is still too thin

- [x] **Step 3: Add a shared source-catalog module**

```python
@dataclass(frozen=True)
class CatalogBundleSpec:
    source_id: str
    osm_relative_dir: tuple[str, ...]
    ref_relative_dir: tuple[str, ...] | None


def build_data_sources() -> list[DataSourceNode]:
    return [
        DataSourceNode(
            source_id="catalog.flood.building",
            source_name="Flood Building Bundle (OSM + Google)",
            supported_types=["dt.building.bundle"],
            ...,
            metadata={
                "component_source_ids": ["raw.osm.building", "raw.google.building"],
                "provider_family": "local_bundle_catalog",
                "bundle_strategy": "osm_ref_pair",
            },
        ),
        ...
    ]
```

- [x] **Step 4: Switch `kg.seed.DATA_SOURCES` to use the shared catalog builder**

```python
from kg.source_catalog import build_data_sources

DATA_SOURCES: List[DataSourceNode] = build_data_sources()
```

- [x] **Step 5: Add planner-context assertions for richer source metadata**

```python
def test_planner_context_exposes_component_source_metadata_for_catalog_sources() -> None:
    ...
    source = next(item for item in provider.last_context["retrieval"]["data_sources"] if item["source_id"] == "catalog.flood.building")
    assert source["metadata"]["component_source_ids"] == ["raw.osm.building", "raw.google.building"]
    assert source["metadata"]["bundle_strategy"] == "osm_ref_pair"
```

- [x] **Step 6: Run the repository and planner tests**

Run:

```powershell
python -m pytest -q `
  tests/test_kg_repository_enhancements.py `
  tests/test_planner_context.py -k "catalog_expansion or component_source_metadata"
```

Expected: PASS

- [x] **Step 7: Commit**

```bash
git add kg/source_catalog.py kg/seed.py tests/test_kg_repository_enhancements.py tests/test_planner_context.py
git commit -m "feat: expand source catalog metadata"
```

### Task 2: Expand The Local Bundle Catalog Provider To Match The Catalog

**Files:**
- Modify: `E:\vscode\fusionAgent\services\local_bundle_catalog.py`
- Create: `E:\vscode\fusionAgent\tests\test_local_bundle_catalog.py`
- Modify: `E:\vscode\fusionAgent\tests\test_input_acquisition_service.py`

- [x] **Step 1: Write the failing provider tests for Google/Microsoft building bundles**

```python
def test_local_bundle_catalog_materializes_google_and_microsoft_building_pairs(tmp_path: Path) -> None:
    _seed_local_catalog_tree(tmp_path)
    provider = LocalBundleCatalogProvider(tmp_path)

    google_bundle = provider.materialize(
        source_id="catalog.flood.building",
        request_bbox=None,
        target_dir=tmp_path / "google_bundle",
        target_crs="EPSG:4326",
    )
    microsoft_bundle = provider.materialize(
        source_id="catalog.earthquake.building",
        request_bbox=None,
        target_dir=tmp_path / "microsoft_bundle",
        target_crs="EPSG:4326",
    )

    assert google_bundle.ref_zip_path.exists()
    assert microsoft_bundle.ref_zip_path.exists()
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_local_bundle_catalog.py -k google_and_microsoft`

Expected: FAIL because the provider is still hard-coded and not validated against the shared catalog contract

- [x] **Step 3: Refactor `LocalBundleCatalogProvider` to consume shared bundle specs**

```python
from kg.source_catalog import CATALOG_BUNDLE_SPECS


class LocalBundleCatalogProvider:
    def __init__(self, root_dir: Path) -> None:
        self.specs = {
            spec.source_id: SourceBundleSpec(
                source_id=spec.source_id,
                osm_path=_first_shp(root.joinpath(*spec.osm_relative_dir)),
                ref_path=(
                    _first_shp(root.joinpath(*spec.ref_relative_dir))
                    if spec.ref_relative_dir is not None
                    else None
                ),
            )
            for spec in CATALOG_BUNDLE_SPECS
        }
```

- [x] **Step 4: Add coverage that input acquisition can still use the expanded source ids**

```python
def test_input_acquisition_supports_catalog_earthquake_building_source(tmp_path: Path) -> None:
    provider = _StubBundleProvider(version_token="v1", supported_source_ids={"catalog.earthquake.building"})
    ...
    resolved = service.resolve_task_driven_inputs(
        request=_build_request(),
        source_id="catalog.earthquake.building",
        required_output_type="dt.building.bundle",
        input_dir=tmp_path / "run",
    )
    assert resolved.source_id == "catalog.earthquake.building"
```

- [x] **Step 5: Run the provider and acquisition tests**

Run:

```powershell
python -m pytest -q `
  tests/test_local_bundle_catalog.py `
  tests/test_input_acquisition_service.py
```

Expected: PASS

- [x] **Step 6: Commit**

```bash
git add services/local_bundle_catalog.py tests/test_local_bundle_catalog.py tests/test_input_acquisition_service.py
git commit -m "feat: align local bundle provider with source catalog"
```

### Task 3: Update Docs And Verify The Stage

**Files:**
- Modify: `E:\vscode\fusionAgent\README.md`
- Modify: `E:\vscode\fusionAgent\docs\superpowers\plans\2026-04-11-source-catalog-expansion.md`

- [x] **Step 1: Update README to describe the expanded source base**

```md
### Phase 4.6: Source Catalog Expansion

- task-driven source selection now distinguishes bundle-level and raw-vector sources
- bundle sources cover OSM + Google / OSM + Microsoft building pairs and OSM road bundles
- raw-vector catalog coverage now includes OSM building/road/water/POI plus open water and POI datasets already present in `Data/`
```

- [x] **Step 2: Mark completed plan steps**

Keep this plan file trustworthy as execution proceeds.

- [x] **Step 3: Run focused verification**

Run:

```powershell
python -m pytest -q `
  tests/test_kg_repository_enhancements.py `
  tests/test_planner_context.py `
  tests/test_local_bundle_catalog.py `
  tests/test_input_acquisition_service.py `
  tests/test_agent_run_service_enhancements.py `
  tests/test_api_v2_integration.py
```

Expected: PASS

- [x] **Step 4: Commit**

```bash
git add README.md docs/superpowers/plans/2026-04-11-source-catalog-expansion.md
git commit -m "docs: describe source catalog expansion stage"
```

## Self-Review

### Spec coverage

- Shared source definitions are covered by Task 1.
- Provider/runtime alignment is covered by Task 2.
- README and verification are covered by Task 3.

### Placeholder scan

- No `TODO`, `TBD`, or “same as above” placeholders remain.
- Each task includes exact files, tests, and commit points.

### Type consistency

- The new shared terms stay consistent across tasks:
  - `build_data_sources`
  - `CatalogBundleSpec`
  - `component_source_ids`
  - `bundle_strategy`
  - `provider_family`

## Execution Status

- Status: completed
- Runtime outcome: planner-visible source metadata now distinguishes bundle-level and raw-vector sources, and the local bundle provider aligns with the shared source catalog.
- Evidence in code: `kg/source_catalog.py`, `kg/seed.py`, `services/local_bundle_catalog.py`
