# Fresh Checkout Benchmark Reproducibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current real-data benchmark path runnable on a fresh checkout by letting manifest-backed evaluation materialize benchmark inputs from repo-declared source ids and cached official downloads instead of requiring pre-restored local `Data/` paths.

**Architecture:** Keep the existing runtime planner and task-driven acquisition flow unchanged for now. Add one source-asset service that can resolve a small set of raw source ids from either the local `Data/` tree or a repo-managed download cache, then teach `scripts/eval_harness.py` to use those source ids in manifest mode so benchmark case bundles can be built deterministically without hand-restored shapefiles.

**Tech Stack:** Python 3.9+, GeoPandas, gzip/json streaming, existing `raw_vector_source_service`, existing eval harness, pytest, Markdown/JSON docs

## Scoped Status On 2026-04-17

- This batch was intentionally narrowed to fresh-checkout benchmark reproducibility at the manifest / eval layer.
- `SourceAssetService`, source-id-backed manifest inputs, the tracked `building_gitega_micro_msft_agent` case, and the `scripts/materialize_source_assets.py` helper are implemented.
- Runtime `RawVectorSourceService` fallback was reviewed and deferred so this slice would not silently widen into a broader task-driven runtime rewrite.

---

## File Structure

- `E:\vscode\fusionAgent\services\source_asset_service.py`
  New source-download/cache resolver for a bounded set of official raw source ids.
- `E:\vscode\fusionAgent\services\raw_vector_source_service.py`
  Existing runtime raw-source resolver; reviewed in this batch, but fallback integration was intentionally deferred.
- `E:\vscode\fusionAgent\scripts\eval_harness.py`
  Existing benchmark harness; this batch adds manifest support for `osm_source_id` and `reference_source_id`.
- `E:\vscode\fusionAgent\scripts\materialize_source_assets.py`
  New helper script to prefetch known source assets into the cache for fresh checkouts.
- `E:\vscode\fusionAgent\kg\source_catalog.py`
  Existing raw source ids; this batch keeps ids stable but documents which ones are remotely materializable.
- `E:\vscode\fusionAgent\docs\superpowers\specs\2026-04-07-real-data-eval-manifest.json`
  Existing benchmark manifest; this batch adds at least one fresh-checkout-capable building case based on source ids instead of absolute local shapefile paths.
- `E:\vscode\fusionAgent\README.md`
- `E:\vscode\fusionAgent\README.en.md`
- `E:\vscode\fusionAgent\docs\v2-operations.md`
- `E:\vscode\fusionAgent\docs\superpowers\plans\2026-04-07-fusion-agent-v2-implementation.md`
  Docs and roadmap status must be updated to reflect the new reproducibility path and remaining manual-only datasets.
- `E:\vscode\fusionAgent\tests\test_source_asset_service.py`
  New unit coverage for source-asset download/cache resolution.
- `E:\vscode\fusionAgent\tests\test_raw_vector_source_service.py`
  Existing raw source tests; no changes in this batch because runtime fallback work was deferred.
- `E:\vscode\fusionAgent\tests\test_eval_harness.py`
  Existing harness tests; this batch adds manifest source-id materialization coverage.

## Task 1: Add A Repo-Managed Source Asset Resolver

**Files:**
- Create: `E:\vscode\fusionAgent\services\source_asset_service.py`
- Create: `E:\vscode\fusionAgent\tests\test_source_asset_service.py`

- [x] **Step 1: Write the failing tests for local-cache fallback and download-backed source resolution**

Add tests that cover:

```python
def test_source_asset_service_prefers_existing_local_data_tree(tmp_path: Path) -> None:
    ...
    resolved = service.resolve_raw_source_path("raw.osm.building")
    assert resolved == tmp_path / "Data" / "burundi-260127-free.shp" / "gis_osm_buildings_a_free_1.shp"


def test_source_asset_service_downloads_and_extracts_geofabrik_bundle_once(tmp_path: Path, monkeypatch) -> None:
    ...
    first = service.resolve_raw_source_path("raw.osm.road")
    second = service.resolve_raw_source_path("raw.osm.road")
    assert first == second
    assert download_calls == ["geofabrik"]


def test_source_asset_service_builds_msft_burundi_gpkg_from_geojsonl_parts(tmp_path: Path, monkeypatch) -> None:
    ...
    resolved = service.resolve_raw_source_path("raw.microsoft.building")
    gdf = gpd.read_file(resolved)
    assert len(gdf) == 2
    assert "confidence" in gdf.columns
```

- [x] **Step 2: Run the tests to verify they fail**

Run:

```powershell
python -m pytest -q tests/test_source_asset_service.py
```

Observed early in the batch: FAIL because `source_asset_service.py` did not exist yet.

- [x] **Step 3: Implement a bounded source-asset catalog and cache resolver**

Implement a new service that:

- accepts `repo_root` and `cache_dir`
- first checks existing repo-local `Data/` paths
- otherwise downloads/extracts only these bounded official assets:
  - Geofabrik Burundi shapefile ZIP for `raw.osm.building`, `raw.osm.road`, `raw.osm.water`, `raw.osm.poi`
  - Microsoft Burundi building tiles from the official `dataset-links.csv` index for `raw.microsoft.building`
- returns a concrete local vector file path

Expected core shapes:

```python
@dataclass(frozen=True)
class SourceAssetResolution:
    source_id: str
    path: Path
    source_mode: str
    cache_hit: bool
    version_token: str


class SourceAssetService:
    def __init__(self, *, repo_root: Path, cache_dir: Path) -> None: ...

    def can_materialize(self, source_id: str) -> bool: ...

    def resolve_raw_source_path(self, source_id: str) -> SourceAssetResolution: ...
```

- [x] **Step 4: Re-run the tests to verify the asset resolver passes**

Run:

```powershell
python -m pytest -q tests/test_source_asset_service.py
```

Observed: PASS
## Task 2: Deferred Runtime Follow-On For Raw Source Resolution

**Files:**
- Modify: `E:\vscode\fusionAgent\services\raw_vector_source_service.py`
- Modify: `E:\vscode\fusionAgent\tests\test_raw_vector_source_service.py`

- [x] **Step 1: Review whether runtime raw-source fallback is required for this slice**

Conclusion: it is not required to satisfy the bounded fresh-checkout benchmark goal because the manifest/eval path can materialize inputs before upload.

- [x] **Step 2: Keep the runtime planner and `task_driven_auto` path unchanged in this batch**

Reason: changing `RawVectorSourceService` would widen the surface from benchmark reproducibility into runtime provider design, cache semantics, and additional policy questions.

- [ ] **Future Step 3: Add optional `source_asset_service` fallback to `RawVectorSourceService`**

Future scope if reopened:

- try the current repo-local path logic first
- fall back to `source_asset_service.resolve_raw_source_path(source_id)` if local files are absent
- preserve existing cache/version semantics for the zipped runtime artifact layer

- [ ] **Future Step 4: Add runtime fallback coverage in `tests/test_raw_vector_source_service.py`**

This deferred task remains the main follow-on item if the repo later needs the same official-source fallback inside the runtime `task_driven_auto` acquisition chain.

## Task 3: Extend Manifest Evaluation To Use Source Ids Instead Of Absolute Input Paths

**Files:**
- Modify: `E:\vscode\fusionAgent\scripts\eval_harness.py`
- Modify: `E:\vscode\fusionAgent\tests\test_eval_harness.py`
- Modify: `E:\vscode\fusionAgent\docs\superpowers\specs\2026-04-07-real-data-eval-manifest.json`

- [x] **Step 1: Write the failing harness test for source-id-backed manifest inputs**

Add coverage like:

```python
def test_materialize_manifest_case_supports_source_id_inputs(tmp_path: Path, monkeypatch) -> None:
    asset_dir = tmp_path / "assets"
    osm = _write_demo_shape(asset_dir / "osm.shp")
    ref = _write_demo_shape(asset_dir / "ref.shp")

    class _StubSourceAssetService:
        def resolve_raw_source_path(self, source_id: str):
            mapping = {
                "raw.osm.building": type("R", (), {"path": osm})(),
                "raw.microsoft.building": type("R", (), {"path": ref})(),
            }
            return mapping[source_id]

    monkeypatch.setattr(eval_harness, "_build_source_asset_service", lambda: _StubSourceAssetService())

    case_dir = eval_harness._materialize_manifest_case(
        {
            "case_id": "building_msft",
            "theme": "building",
            "clip_bbox": [0.0, 0.0, 1.0, 1.0],
            "inputs": {
                "osm_source_id": "raw.osm.building",
                "reference_source_id": "raw.microsoft.building",
            },
        },
        tmp_path / "root",
    )

    assert (case_dir / "input" / "osm.zip").exists()
    assert (case_dir / "input" / "ref.zip").exists()
```

- [x] **Step 2: Run the focused harness test to verify it fails**

Run:

```powershell
python -m pytest -q tests/test_eval_harness.py -k source_id_inputs
```

Observed early in the batch: FAIL because manifest cases still required `inputs.osm` and `inputs.reference`.

- [x] **Step 3: Extend manifest preflight and materialization to accept `osm_source_id` / `reference_source_id`**

Implement support so manifest cases may use either:

- direct local paths:
  - `inputs.osm`
  - `inputs.reference`
- or source ids:
  - `inputs.osm_source_id`
  - `inputs.reference_source_id`

and materialize the latter through `SourceAssetService`.

- [x] **Step 4: Add one fresh-checkout-capable building benchmark case to the tracked manifest**

Add a new `agent-ready` building case that uses:

- `inputs.osm_source_id = "raw.osm.building"`
- `inputs.reference_source_id = "raw.microsoft.building"`
- the existing Gitega clip bbox

Keep it separate from the historical Google-backed case so older evidence stays valid.

- [x] **Step 5: Re-run the harness tests**

Run:

```powershell
python -m pytest -q tests/test_eval_harness.py
```

Observed: PASS

## Task 4: Add Prefetch Script And Update Docs

**Files:**
- Create: `E:\vscode\fusionAgent\scripts\materialize_source_assets.py`
- Modify: `E:\vscode\fusionAgent\README.md`
- Modify: `E:\vscode\fusionAgent\README.en.md`
- Modify: `E:\vscode\fusionAgent\docs\v2-operations.md`
- Modify: `E:\vscode\fusionAgent\docs\superpowers\plans\2026-04-07-fusion-agent-v2-implementation.md`

- [x] **Step 1: Run a smoke-like manual prefetch verification for known source ids**

Command used during implementation:

```powershell
python scripts/materialize_source_assets.py --source raw.osm.building --source raw.microsoft.building
```

Observed outcome: first run returned `asset_downloaded`, second run returned `asset_cached`, and both sources resolved to stable local paths.

- [x] **Step 2: Implement the prefetch script**

The script should:

- construct `SourceAssetService`
- resolve each requested source id
- print `source_id`, `source_mode`, `cache_hit`, and final local path as JSON

- [x] **Step 3: Update docs and roadmap status**

Document:

- the new fresh-checkout benchmark asset path
- the cache directory convention
- which raw source ids are automatically materializable today
- which sources remain manual-only (`raw.google.building`, local Excel/POI assets, etc.)

- [x] **Step 4: Run focused verification**

Run:

```powershell
python -m pytest -q `
  tests/test_source_asset_service.py `
  tests/test_raw_vector_source_service.py `
  tests/test_eval_harness.py
```

Expected: PASS

Observed on `2026-04-17`: `python -m pytest -q tests/test_source_asset_service.py tests/test_eval_harness.py` passed (`20 passed`).

- [ ] **Step 5: Commit**

## Implemented Evidence

- Official-source prefetch command succeeded twice for `raw.osm.building` and `raw.microsoft.building`, proving both initial materialization and cache reuse.
- The tracked manifest now includes `building_gitega_micro_msft_agent`.
- `python scripts/eval_harness.py --manifest docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json --case building_gitega_micro_msft_agent --base-url http://127.0.0.1:8010 --timeout 180 --output-json tmp/eval/fresh-checkout-micro-msft.json` passed with run id `60e7afca80e146cd819fe87966d47e8c`.
- Durable tracked evidence now lives in `E:\vscode\fusionAgent\docs\superpowers\specs\2026-04-16-building-micro-msft-fresh-checkout-result.json`.

```bash
git add services/source_asset_service.py services/raw_vector_source_service.py scripts/eval_harness.py scripts/materialize_source_assets.py tests/test_source_asset_service.py tests/test_raw_vector_source_service.py tests/test_eval_harness.py docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json README.md README.en.md docs/v2-operations.md docs/superpowers/plans/2026-04-07-fusion-agent-v2-implementation.md
git commit -m "feat: add fresh-checkout benchmark asset resolution"
```

## Self-Review

### Spec coverage

- Covers repo-managed official download/cache resolution for a bounded raw-source set.
- Covers manifest-level fresh-checkout materialization without changing planner behavior.
- Makes the deferred runtime fallback explicit instead of silently over-claiming the scope.

### Placeholder scan

- No `TODO`, `TBD`, or vague “handle later” steps remain.
- Each task names exact files, tests, commands, or source ids.

### Type consistency

- Manifest source-id fields use `osm_source_id` / `reference_source_id` consistently.
- Raw-source ids remain aligned with `kg/source_catalog.py`.
- Manifest source-id fields use the same raw source ids as the repo source catalog.
