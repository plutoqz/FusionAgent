# Benin Building Runtime Preparation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status Note:** Deferred to Phase 5 by `docs/superpowers/plans/2026-05-12-fusionagent-master-execution-plan.md`. The unchecked boxes below are bounded scale-validation backlog, not current active implementation work.

**Goal:** Prepare FusionAgent for Benin-scale building workloads by adding source profiling, KG search-space expansion, tiled parallel runtime scaffolding for the currently supported building flow, and reserved seams for future multi-source fusion plus raster-based height enrichment.

**Architecture:** Preserve the existing `planner -> validator -> executor -> healing/replan -> writeback` spine and the current executable building contract of `dt.building.bundle -> dt.building.fused`. Add a control plane around it: canonical source profiles, richer KG metadata with `runtime_candidate` versus `reservation_only`, a tile partition and clip cache layer, and a tiled fan-out/fan-in runtime that can run today's `OSM + single reference` building fusion per tile while leaving future multi-source and raster-height logic as explicit reserved hooks.

**Tech Stack:** Python 3.9+, Pydantic, GeoPandas, pyogrio, shapely, pytest, existing `AgentRunService`, existing artifact registry, existing raw-source materialization services, locally available GDAL CLI tools for raster inspection and later clipping seams.

---

## Review Position

Implement this increment in two lanes that stay honest about current capability:

1. **Executable now:** Benin source profiling, KG metadata expansion, planner/runtime gating, tile partitioning, vector clip cache reuse, and tiled parallel execution for the already supported two-input building flow.
2. **Reserved for future algorithms:** multi-reference building fusion semantics, raster height sampling semantics, final building-height output schema, and cross-source conflict resolution rules.

This increment must improve completion odds for large AOIs without claiming that the runtime already supports `4-vector fusion + raster height extraction`.

---

## File Map

Create:

- `services/source_profile_service.py`: inspect vector and raster sources, persist canonical source profile records, and classify semantic hints such as `presence_only` versus `height_unknown`.
- `services/tile_partition_service.py`: tile AOI bbox into buffered work tiles and emit deterministic tile manifests.
- `services/tiled_building_runtime_service.py`: fan out tile-scoped building runs, collect tile outputs, and stitch buffered tile artifacts back into one shapefile bundle.
- `utils/raster_cli.py`: small GDAL CLI wrapper for `gdalinfo` JSON inspection and future `gdalwarp` clipping.
- `scripts/profile_benin_sources.py`: build canonical Benin source profile JSON from a local source root.
- `scripts/benchmark_tiled_building.py`: benchmark read, clip, fuse, and stitch phases for AOI sizes of interest.
- `tests/test_source_profile_service.py`
- `tests/test_tile_partition_service.py`
- `tests/test_tiled_building_runtime_service.py`
- `tests/test_raster_cli.py`

Modify:

- `kg/source_catalog.py`: add Benin-relevant source definitions, reserved raster source definitions, and metadata needed for planner/runtime control.
- `kg/seed.py`: add reserved data types, reserved task/algo metadata, and source/output policy metadata.
- `agent/retriever.py`: expose source runtime status, source form, height semantics, tile support, and reserved-task hints in planner context.
- `agent/validator.py`: fail closed when a plan selects a `reservation_only` source or reserved task for execution.
- `services/source_asset_service.py`: surface canonical source metadata and vector clip profile information; keep raster handling inspect-only in this increment.
- `services/raw_vector_source_service.py`: reuse tile clip cache keys and preserve tile-aware source metadata.
- `services/input_acquisition_service.py`: carry tile and source-profile metadata into bundle reuse records.
- `services/agent_run_service.py`: route eligible large building runs through tiled orchestration, emit tile-level audit events, and preserve existing non-tiled flows for smaller cases.
- `agent/executor.py`: allow a tiled building handler to own fan-out/fan-in while keeping the existing single-output artifact contract.
- `tests/test_kg_repository_enhancements.py`
- `tests/test_planner_context.py`
- `tests/test_agent_run_service_enhancements.py`
- `README.md`
- `README.en.md`
- `docs/v2-operations.md`

---

## Task 1: Lock Canonical Benin Source Profiles

**Files:**
- Create: `services/source_profile_service.py`
- Create: `utils/raster_cli.py`
- Create: `scripts/profile_benin_sources.py`
- Test: `tests/test_source_profile_service.py`
- Test: `tests/test_raster_cli.py`

- [ ] **Step 1: Write the failing source-profile tests**

Create `tests/test_source_profile_service.py` with explicit coverage for the four Benin vector sources and the Google building-presence raster semantics:

```python
from pathlib import Path

from services.source_profile_service import (
    SourceProfileService,
    classify_height_semantics,
)


def test_classify_height_semantics_prefers_presence_only_for_google_presence_raster():
    assert classify_height_semantics(
        source_name="google building presence",
        field_names=[],
        raster_band_description="building presence",
    ) == "presence_only"


def test_profile_vector_source_reads_feature_count_crs_and_fields(tmp_path: Path):
    profile = SourceProfileService().profile_vector_source(
        source_id="raw.openbuildingmap.building",
        path=tmp_path / "openbuildingmap_benin.shp",
        feature_count=5673640,
        crs="EPSG:4326",
        field_names=["id", "floorspace", "occupancy", "height"],
    )
    assert profile.source_form == "vector"
    assert profile.feature_count == 5673640
    assert profile.height_fields == ["height"]
    assert profile.height_semantics == "estimated_height"
```

- [ ] **Step 2: Run the tests to verify the feature does not exist yet**

Run:

```powershell
python -m pytest -q tests/test_source_profile_service.py tests/test_raster_cli.py
```

Expected: fail with import errors for `services.source_profile_service` and `utils.raster_cli`.

- [ ] **Step 3: Implement the profile service and raster CLI wrapper**

Create `services/source_profile_service.py` with explicit, serializable profile models and pure classification logic:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SourceProfile:
    source_id: str
    canonical_path: str
    source_form: str
    runtime_status: str
    selectable_now: bool
    crs: str | None
    feature_count: int | None
    field_names: list[str] = field(default_factory=list)
    height_fields: list[str] = field(default_factory=list)
    height_semantics: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_height_semantics(*, source_name: str, field_names: list[str], raster_band_description: str | None) -> str:
    lowered_fields = {item.casefold() for item in field_names}
    description = (raster_band_description or "").casefold()
    if "height" in lowered_fields:
        return "estimated_height"
    if "presence" in description:
        return "presence_only"
    if "height" in description:
        return "height_unknown"
    return "unknown"
```

Create `utils/raster_cli.py` as a narrow GDAL CLI wrapper that only inspects rasters in this increment:

```python
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def gdalinfo_json(path: Path) -> dict[str, object]:
    exe = shutil.which("gdalinfo")
    if not exe:
        raise FileNotFoundError("gdalinfo executable not found on PATH")
    completed = subprocess.run(
        [exe, "-json", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)
```

- [ ] **Step 4: Add the Benin profiling script**

Create `scripts/profile_benin_sources.py` to emit a deterministic JSON profile bundle for the approved Benin root:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.source_profile_service import SourceProfileService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    service = SourceProfileService()
    payload = service.profile_benin_root(Path(args.source_root))
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Re-run tests and profile the real Benin root**

Run:

```powershell
python -m pytest -q tests/test_source_profile_service.py tests/test_raster_cli.py
python scripts/profile_benin_sources.py --source-root E:\fyx\data\Benin --output runs\benin-source-profile.json
```

Expected: tests pass; `runs\benin-source-profile.json` exists and clearly distinguishes:
- canonical Microsoft shapefile versus empty duplicate shapefile
- `OpenBuildingMap.height`
- `Microsoft.height`
- Google raster semantics as `presence_only`

- [ ] **Step 6: Commit**

```powershell
git add services/source_profile_service.py utils/raster_cli.py scripts/profile_benin_sources.py tests/test_source_profile_service.py tests/test_raster_cli.py
git commit -m "feat: add canonical source profiling for benin assets"
```

---

## Task 2: Expand KG Search Space Without Overclaiming Execution Support

**Files:**
- Modify: `kg/source_catalog.py`
- Modify: `kg/seed.py`
- Test: `tests/test_kg_repository_enhancements.py`
- Test: `tests/test_planner_context.py`

- [ ] **Step 1: Write failing KG metadata tests**

Extend `tests/test_kg_repository_enhancements.py` with assertions for new sources and metadata:

```python
def test_building_source_catalog_includes_reserved_multi_source_and_raster_inputs(repo):
    ids = {item.source_id for item in repo.get_data_sources(job_type="building")}
    assert "raw.openbuildingmap.building" in ids
    assert "raw.local.microsoft.building" in ids
    assert "raw.google.building_presence.raster" in ids


def test_reserved_sources_are_not_marked_selectable_now(repo):
    raster = next(item for item in repo.get_data_sources(job_type="building") if item.source_id == "raw.google.building_presence.raster")
    assert raster.metadata["runtime_status"] == "reservation_only"
    assert raster.metadata["selectable_now"] is False
```

- [ ] **Step 2: Run the KG tests to verify they fail**

Run:

```powershell
python -m pytest -q tests/test_kg_repository_enhancements.py tests/test_planner_context.py
```

Expected: fail because the new source ids and metadata do not exist yet.

- [ ] **Step 3: Add Benin-relevant source definitions and reserved data types**

In `kg/source_catalog.py`, add new raw sources and metadata fields:

```python
DataSourceNode(
    source_id="raw.openbuildingmap.building",
    source_name="OpenBuildingMap Building Footprints",
    supported_types=["dt.raw.vector"],
    disaster_types=list(DEFAULT_DISASTER_TYPES),
    supported_job_types=["building"],
    supported_geometry_types=["polygon"],
    metadata={
        "source_form": "vector",
        "provider_family": "openbuildingmap",
        "source_role": "reference_candidate",
        "runtime_status": "reservation_only",
        "selectable_now": False,
        "supports_tiling": True,
        "height_fields": ["height"],
        "height_semantics": "estimated_height",
        "coverage_scope": "national_clip",
    },
)
```

In `kg/seed.py`, reserve future data types and tasks without making them executable:

```python
DataTypeNode(type_id="dt.building.source_set", theme="building", geometry_type="mixed", description="Multi-source building input set"),
DataTypeNode(type_id="dt.raster.building_presence", theme="building", geometry_type="raster", description="Building presence raster"),
DataTypeNode(type_id="dt.partition.tile_manifest", theme="runtime", geometry_type="none", description="Tile partition manifest"),
```

- [ ] **Step 4: Expose the new metadata in planner context**

Extend `tests/test_planner_context.py` to prove the planner can see execution eligibility and height semantics:

```python
def test_planner_context_exposes_runtime_status_and_height_semantics_for_sources():
    provider = CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)
    planner.create_plan(
        run_id="run-building-runtime-status",
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="need building data for Benin"),
    )
    sources = provider.last_context["retrieval"]["data_sources"]
    obm = next(item for item in sources if item["source_id"] == "raw.openbuildingmap.building")
    assert obm["metadata"]["runtime_status"] == "reservation_only"
    assert obm["metadata"]["height_semantics"] == "estimated_height"
```

- [ ] **Step 5: Re-run the KG tests**

Run:

```powershell
python -m pytest -q tests/test_kg_repository_enhancements.py tests/test_planner_context.py
```

Expected: pass, and no existing `building` / `road` runtime tests regress.

- [ ] **Step 6: Commit**

```powershell
git add kg/source_catalog.py kg/seed.py tests/test_kg_repository_enhancements.py tests/test_planner_context.py
git commit -m "feat: expand building kg search space with reserved benin sources"
```

---

## Task 3: Add Planner And Runtime Guards For Reserved Capabilities

**Files:**
- Modify: `agent/retriever.py`
- Modify: `agent/validator.py`
- Modify: `services/agent_run_service.py`
- Test: `tests/test_planner_context.py`
- Test: `tests/test_agent_run_service_enhancements.py`

- [ ] **Step 1: Write failing guard tests**

Add tests that require planner context and runtime events to distinguish executable sources from reserved ones:

```python
def test_planner_context_emits_selectable_source_ids_for_current_runtime():
    provider = CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)
    planner.create_plan(
        run_id="run-selectable-sources",
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="need building data for Parakou, Benin"),
    )
    hints = provider.last_context["execution_hints"]
    assert "catalog.flood.building" in hints["selectable_source_ids"]
    assert "raw.openbuildingmap.building" not in hints["selectable_source_ids"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
python -m pytest -q tests/test_planner_context.py tests/test_agent_run_service_enhancements.py
```

Expected: fail because `execution_hints.selectable_source_ids` and reserved-capability audit events are not present.

- [ ] **Step 3: Implement retrieval and validation guards**

In `agent/retriever.py`, add execution-facing hints:

```python
def _build_execution_hints(kg_context: KGContext, resolved_aoi: ResolvedAOI | None) -> Dict[str, Any]:
    selectable_source_ids = [
        source.source_id
        for source in kg_context.data_sources
        if bool((source.metadata or {}).get("selectable_now", True))
    ]
    hints = {
        "preferred_pattern_id": kg_context.patterns[0].pattern_id if kg_context.patterns else None,
        "fallback_pattern_ids": [pattern.pattern_id for pattern in kg_context.patterns[1:]],
        "available_data_source_ids": [source.source_id for source in kg_context.data_sources],
        "selectable_source_ids": selectable_source_ids,
    }
    return hints
```

In `agent/validator.py`, fail closed when a plan step selects a reserved source or reserved task:

```python
if task.input.data_source_id in reserved_source_ids:
    issues.append(ValidationIssue(code="reserved_source_selected", message=f"Source {task.input.data_source_id} is reservation_only", step=task.step))
```

- [ ] **Step 4: Add audit evidence for reserved-capability dependencies**

In `services/agent_run_service.py`, emit explicit evidence before execution:

```python
event_details = {
    "selectable_source_ids": plan.context.get("execution_hints", {}).get("selectable_source_ids", []),
    "required_reserved_capabilities": plan.context.get("intent", {}).get("required_reserved_capabilities", []),
}
```

- [ ] **Step 5: Re-run the tests**

Run:

```powershell
python -m pytest -q tests/test_planner_context.py tests/test_agent_run_service_enhancements.py
```

Expected: pass, with no regression in `tests/test_api_v2_integration.py`.

- [ ] **Step 6: Commit**

```powershell
git add agent/retriever.py agent/validator.py services/agent_run_service.py tests/test_planner_context.py tests/test_agent_run_service_enhancements.py
git commit -m "feat: guard reserved building sources and capabilities"
```

---

## Task 4: Add AOI Tile Partitioning And Deterministic Tile Manifests

**Files:**
- Create: `services/tile_partition_service.py`
- Test: `tests/test_tile_partition_service.py`

- [ ] **Step 1: Write failing tile partition tests**

Create `tests/test_tile_partition_service.py`:

```python
from services.tile_partition_service import TilePartitionService


def test_partition_service_splits_large_bbox_into_buffered_tiles():
    service = TilePartitionService(tile_width_m=5000, tile_height_m=5000, overlap_m=64)
    manifest = service.partition_bbox(
        bbox=(2.48, 9.23, 2.77, 9.44),
        bbox_crs="EPSG:4326",
        working_crs="EPSG:32631",
    )
    assert len(manifest.tiles) >= 2
    assert all(tile.tile_id.startswith("tile_") for tile in manifest.tiles)
    assert all(tile.buffered_bbox is not None for tile in manifest.tiles)
```

- [ ] **Step 2: Run the partition tests to verify they fail**

Run:

```powershell
python -m pytest -q tests/test_tile_partition_service.py
```

Expected: fail because the partition service does not exist.

- [ ] **Step 3: Implement tile manifest models and partition logic**

Create `services/tile_partition_service.py` with explicit models:

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TileSpec:
    tile_id: str
    bbox: tuple[float, float, float, float]
    buffered_bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class TileManifest:
    working_crs: str
    tiles: list[TileSpec] = field(default_factory=list)
```

Implement deterministic tiling in projected CRS, then transform tile bboxes back to request CRS for downstream clip operations.

- [ ] **Step 4: Re-run the partition tests**

Run:

```powershell
python -m pytest -q tests/test_tile_partition_service.py
```

Expected: pass with stable tile ids and buffered bboxes.

- [ ] **Step 5: Commit**

```powershell
git add services/tile_partition_service.py tests/test_tile_partition_service.py
git commit -m "feat: add deterministic aoi tile partition service"
```

---

## Task 5: Add Tile-Aware Clip Cache Reuse For Vector Inputs And Raster Inspection Seams

**Files:**
- Modify: `services/source_asset_service.py`
- Modify: `services/raw_vector_source_service.py`
- Modify: `services/input_acquisition_service.py`
- Test: `tests/test_raw_vector_source_service.py`
- Test: `tests/test_source_asset_service.py`

- [ ] **Step 1: Write failing cache metadata tests**

Add tile-awareness assertions to `tests/test_raw_vector_source_service.py`:

```python
def test_raw_vector_source_service_preserves_tile_cache_metadata(tmp_path):
    service = RawVectorSourceService(...)
    resolved = service.resolve(
        source_id="raw.osm.building",
        request_bbox=(2.50, 9.24, 2.55, 9.29),
        target_path=tmp_path / "tile_001" / "osm.zip",
        target_crs="EPSG:32631",
    )
    assert resolved.coverage_status in {"available", "empty"}
    assert resolved.source_mode in {"downloaded", "clip_reused", "cache_reused"}
```

- [ ] **Step 2: Run the vector-source tests**

Run:

```powershell
python -m pytest -q tests/test_raw_vector_source_service.py tests/test_source_asset_service.py
```

Expected: fail once the new tile-aware assertions are added.

- [ ] **Step 3: Add tile metadata and raster inspect-only hooks**

Preserve tile keys in artifact metadata and keep raster support explicitly inspect-only in this increment:

```python
meta={
    "artifact_role": "raw_vector",
    "source_id": source_id,
    "source_version": version_token,
    "source_mode": source_resolution.source_mode,
    "tile_bbox": request_bbox,
}
```

In `services/source_asset_service.py`, add a helper that only profiles rasters for now:

```python
def inspect_local_raster_profile(self, source_id: str, path: Path) -> dict[str, object]:
    info = gdalinfo_json(path)
    return {
        "source_id": source_id,
        "source_form": "raster",
        "runtime_status": "reservation_only",
        "band_count": len(info.get("bands", [])),
    }
```

- [ ] **Step 4: Re-run the source-materialization tests**

Run:

```powershell
python -m pytest -q tests/test_raw_vector_source_service.py tests/test_source_asset_service.py
```

Expected: pass, with no regression in `tests/test_input_acquisition_service.py`.

- [ ] **Step 5: Commit**

```powershell
git add services/source_asset_service.py services/raw_vector_source_service.py services/input_acquisition_service.py tests/test_raw_vector_source_service.py tests/test_source_asset_service.py
git commit -m "feat: preserve tile-aware source cache metadata"
```

---

## Task 6: Add Tiled Parallel Building Runtime For The Current Executable Flow

**Files:**
- Create: `services/tiled_building_runtime_service.py`
- Modify: `services/agent_run_service.py`
- Modify: `agent/executor.py`
- Test: `tests/test_tiled_building_runtime_service.py`
- Test: `tests/test_agent_run_service_enhancements.py`

- [ ] **Step 1: Write failing tiled-runtime tests**

Create `tests/test_tiled_building_runtime_service.py`:

```python
from services.tiled_building_runtime_service import TiledBuildingRuntimeService


def test_tiled_runtime_runs_tiles_and_stitches_outputs(tmp_path):
    service = TiledBuildingRuntimeService(max_workers=2)
    result = service.run_tiled_building_job(
        run_id="run-benin-tiled",
        tile_manifest=...,
        osm_bundle_factory=...,
        ref_bundle_factory=...,
        output_dir=tmp_path / "output",
        target_crs="EPSG:32631",
    )
    assert result.output_shp.exists()
    assert result.tile_count >= 2
```

- [ ] **Step 2: Run the tiled-runtime tests to verify they fail**

Run:

```powershell
python -m pytest -q tests/test_tiled_building_runtime_service.py tests/test_agent_run_service_enhancements.py
```

Expected: fail because the tiled runtime service does not exist.

- [ ] **Step 3: Implement fan-out and stitch logic for current building flow**

Create `services/tiled_building_runtime_service.py` around the existing safe adapter instead of inventing new fusion semantics:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from adapters.building_adapter import run_building_fusion_safe


@dataclass(frozen=True)
class TiledBuildingRunResult:
    output_shp: Path
    tile_count: int
    stitched_feature_count: int
```

Each tile should:
- materialize `osm.zip` and `ref.zip` for the tile bbox
- run `run_building_fusion_safe()`
- persist tile audit metadata

Stitching should:
- concatenate tile outputs
- remove exact duplicates caused by tile overlap using geometry WKB hashes first
- keep seam-dedup conservative; do not attempt future cross-source semantic dedup in this increment

- [ ] **Step 4: Route only eligible large building runs into tiled execution**

In `services/agent_run_service.py`, add a narrow gate:

```python
should_tile = (
    request.job_type.value == "building"
    and request.input_strategy == RunInputStrategy.task_driven_auto
    and selected_source_id in {"catalog.flood.building", "catalog.earthquake.building"}
)
```

Keep smaller or uploaded runs on the existing direct path. Emit audit events:
- `tile_manifest_created`
- `tile_execution_started`
- `tile_execution_completed`
- `tile_stitch_completed`

- [ ] **Step 5: Re-run tiled runtime tests and runtime-focused regression tests**

Run:

```powershell
python -m pytest -q tests/test_tiled_building_runtime_service.py tests/test_agent_run_service_enhancements.py tests/test_local_bundle_catalog.py tests/test_raw_vector_source_service.py
```

Expected: pass, and existing building adapter tests continue to pass without source-semantic changes.

- [ ] **Step 6: Commit**

```powershell
git add services/tiled_building_runtime_service.py services/agent_run_service.py agent/executor.py tests/test_tiled_building_runtime_service.py tests/test_agent_run_service_enhancements.py
git commit -m "feat: add tiled parallel runtime for large building jobs"
```

---

## Task 7: Add Benin Benchmarks, Operator Evidence, And Documentation

**Files:**
- Create: `scripts/benchmark_tiled_building.py`
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/v2-operations.md`
- Test: `tests/test_eval_harness.py`

- [ ] **Step 1: Write benchmark script expectations**

Add a benchmark contract to `scripts/benchmark_tiled_building.py`:

```python
"""
Expected outputs:
- timing.json
- source_profile_snapshot.json
- tile_manifest.json
- benchmark_summary.md
"""
```

- [ ] **Step 2: Implement a narrow benchmark runner**

Create a script that accepts:

```powershell
python scripts/benchmark_tiled_building.py `
  --source-root E:\fyx\data\Benin `
  --bbox 2.48,9.23,2.77,9.44 `
  --target-crs EPSG:32631 `
  --output-root runs\benin-benchmark
```

The script should capture:
- source profile snapshot
- tile-count and tile-size decisions
- per-phase timings: `profile`, `clip`, `fuse`, `stitch`
- final artifact feature count

- [ ] **Step 3: Document executable versus reserved capability boundaries**

Update documentation with an explicit matrix:

```markdown
| Capability | Status |
| --- | --- |
| Tiled parallel execution for current `OSM + single-ref` building runtime | supported |
| OpenBuildingMap retrieval and KG exposure | supported in KG, not executable |
| Google building-presence raster retrieval and profiling | inspect-only |
| Raster-based building height enrichment | reserved |
| True 4-source building fusion semantics | reserved |
```

- [ ] **Step 4: Run the benchmark and smoke the docs-linked commands**

Run:

```powershell
python scripts/profile_benin_sources.py --source-root E:\fyx\data\Benin --output runs\benin-source-profile.json
python scripts/benchmark_tiled_building.py --source-root E:\fyx\data\Benin --bbox 2.48,9.23,2.77,9.44 --target-crs EPSG:32631 --output-root runs\benin-benchmark
```

Expected: both commands complete and produce JSON/Markdown artifacts under `runs\benin-benchmark`.

- [ ] **Step 5: Commit**

```powershell
git add scripts/benchmark_tiled_building.py README.md README.en.md docs/v2-operations.md
git commit -m "docs: describe benin tiled runtime preparation and reserved seams"
```

---

## Final Verification

- [ ] Run the focused regression suite:

```powershell
python -m pytest -q `
  tests/test_source_profile_service.py `
  tests/test_raster_cli.py `
  tests/test_kg_repository_enhancements.py `
  tests/test_planner_context.py `
  tests/test_tile_partition_service.py `
  tests/test_raw_vector_source_service.py `
  tests/test_source_asset_service.py `
  tests/test_tiled_building_runtime_service.py `
  tests/test_agent_run_service_enhancements.py
```

Expected: all pass.

- [ ] Run a broader runtime suite before declaring readiness:

```powershell
python -m pytest -q `
  tests/test_local_bundle_catalog.py `
  tests/test_input_acquisition_service.py `
  tests/test_api_v2_integration.py `
  tests/test_building_adapter_safe.py
```

Expected: no regressions in the current two-input building runtime.

- [ ] Check anti-patterns with grep:

```powershell
Get-ChildItem kg,agent,services -Recurse -File -Include *.py | Select-String -Pattern '4-source supported','height extraction supported','reservation_only.*selectable_now.=.True'
```

Expected: no hits that overclaim unsupported capabilities.

- [ ] Verify docs and benchmark artifacts exist:

```powershell
Get-ChildItem runs\benin-benchmark
Get-ChildItem runs\benin-source-profile.json
```

Expected: timing, profile, tile-manifest, and summary artifacts are present.

---

## Anti-Pattern Guards

- Do **not** change the current `building` adapter to accept more than `osm_shp` and `ref_shp` in this increment.
- Do **not** expose `raw.openbuildingmap.building` or `raw.google.building_presence.raster` as executable building sources yet.
- Do **not** rename current `dt.building.fused` output policy fields to include `height` before the future algorithm contract is provided.
- Do **not** implement speculative raster sampling math or speculative multi-source conflict resolution.
- Do **not** let tile stitching perform semantic dedup beyond overlap-induced duplicate suppression.
