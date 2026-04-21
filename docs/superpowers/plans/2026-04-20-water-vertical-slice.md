# Water Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add a third, uploaded-input-only `water` polygon fusion vertical slice that runs through KG planning, v2 uploaded API execution, adapter output, artifact writeback, and ontology/bootstrap closure.

**Architecture:** Keep the slice deliberately narrow: users still upload two polygon shapefile ZIP bundles through `/api/v2/runs`, the planner selects a single KG-backed water workflow pattern, the executor dispatches `algo.fusion.water.v1`, and the new adapter produces a stable `fused_water.shp` bundle. Do not add task-driven auto water materialization, provider download behavior, or v1 `/fusion/water/jobs` routes in this phase.

**Tech Stack:** Python, FastAPI v2 run API, Pydantic models, GeoPandas/Shapely/Rtree geospatial processing, in-memory/Neo4j KG seed/bootstrap, pytest.

**Completion Status:** Implemented on 2026-04-21 and merged to `main` at `cfbc35b`. Focused Phase F verification passed with `37 passed`. Full repository verification on merged `main` passed with `175 passed, 1 skipped, 6 warnings`.

---

## File Structure

- Modify `schemas/fusion.py` to add `JobType.water`.
- Create `adapters/water_adapter.py` with the uploaded polygon fusion adapter and stable short-field shapefile output.
- Modify `agent/executor.py` to register and dispatch `algo.fusion.water.v1`.
- Modify `kg/seed.py` to add water data types, task, algorithm, workflow pattern, output schema policy, and transform closure metadata.
- Modify `kg/source_catalog.py` so `upload.bundle` advertises `dt.water.bundle` and `water`.
- Regenerate `kg/bootstrap/neo4j_bootstrap.cypher` from `kg.bootstrap.build_bootstrap_cypher()`.
- Modify `agent/intent_resolver.py` so direct water requests resolve to `task.water.fusion`.
- Create `tests/test_water_adapter.py` for adapter behavior.
- Modify `tests/test_api_v2_integration.py` for the v2 uploaded runtime path.
- Modify `tests/test_planner_context.py` for water retrieval context.
- Modify `tests/test_ontology_closure.py`, `tests/test_kg_repository_enhancements.py`, and `tests/test_neo4j_bootstrap.py` for KG/bootstrap closure.
- Modify `docs/superpowers/specs/2026-04-20-evidence-ledger.md` after implementation verification to record Phase F evidence.

## Non-Goals

- Do not implement `task_driven_auto` water input acquisition.
- Do not claim output schema policy enforcement; it remains metadata-only.
- Do not add v1 `/fusion/water/jobs` unless a test proves v1 is part of this phase.
- Do not change existing building/road behavior.

### Task 1: Water Adapter Contract

**Files:**
- Create: `tests/test_water_adapter.py`
- Create: `adapters/water_adapter.py`

- [x] **Step 1: Write the failing adapter test**

Create `tests/test_water_adapter.py`:

```python
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon


def _write_shapefile(path: Path, frame: gpd.GeoDataFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(path)
    return path


def _build_sample_inputs(tmp_path: Path) -> tuple[Path, Path]:
    osm = gpd.GeoDataFrame(
        {
            "name": ["OSM Lake", "OSM Pond"],
            "fclass": ["water", "water"],
            "water": ["lake", "pond"],
        },
        geometry=[
            Polygon([(0, 0), (0, 10), (10, 10), (10, 0)]),
            Polygon([(30, 30), (30, 40), (40, 40), (40, 30)]),
        ],
        crs="EPSG:3857",
    )
    ref = gpd.GeoDataFrame(
        {
            "name": ["Ref Lake", "Ref Reservoir"],
            "water": ["lake", "reservoir"],
        },
        geometry=[
            Polygon([(1, 1), (1, 9), (9, 9), (9, 1)]),
            Polygon([(60, 60), (60, 70), (70, 70), (70, 60)]),
        ],
        crs="EPSG:3857",
    )
    osm_path = _write_shapefile(tmp_path / "osm" / "osm_water.shp", osm)
    ref_path = _write_shapefile(tmp_path / "ref" / "ref_water.shp", ref)
    return osm_path, ref_path


def test_run_water_fusion_merges_matched_and_unmatched_polygons(tmp_path: Path) -> None:
    from adapters.water_adapter import run_water_fusion

    osm_path, ref_path = _build_sample_inputs(tmp_path)

    output_shp = run_water_fusion(
        osm_shp=osm_path,
        ref_shp=ref_path,
        output_dir=tmp_path / "output",
        target_crs="EPSG:3857",
        field_mapping={},
        debug=False,
        parameters={"overlap_threshold": 0.1},
    )

    result = gpd.read_file(output_shp)

    assert output_shp.exists()
    assert output_shp.name == "fused_water.shp"
    assert result.crs.to_string() == "EPSG:3857"
    assert len(result) == 3
    assert result.columns.tolist() == [
        "OSM_ID",
        "REF_ID",
        "MATCH_REF",
        "OV_RATIO",
        "MATCH_CNT",
        "SRC",
        "NAME",
        "FCLASS",
        "WATER_TY",
        "geometry",
    ]
    assert int(result.geometry.is_empty.sum()) == 0
    assert int(result.geometry.isna().sum()) == 0

    matched = result.loc[result["OSM_ID"] == 1].iloc[0]
    assert matched["MATCH_REF"] == "1"
    assert matched["MATCH_CNT"] == 1
    assert float(matched["OV_RATIO"]) == pytest.approx(0.64)
    assert matched["SRC"] == "osm"

    unmatched_osm = result.loc[result["OSM_ID"] == 2].iloc[0]
    assert unmatched_osm["MATCH_REF"] == ""
    assert unmatched_osm["MATCH_CNT"] == 0
    assert unmatched_osm["SRC"] == "osm"

    unmatched_ref = result.loc[result["REF_ID"] == 2].iloc[0]
    assert unmatched_ref["OSM_ID"] != unmatched_ref["OSM_ID"]
    assert unmatched_ref["MATCH_REF"] == "2"
    assert unmatched_ref["SRC"] == "ref"
```

- [x] **Step 2: Run the adapter test and verify it fails**

Run:

```powershell
python -m pytest tests/test_water_adapter.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'adapters.water_adapter'`.

- [x] **Step 3: Implement the adapter**

Create `adapters/water_adapter.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry.base import BaseGeometry

from utils.field_mapping import apply_field_mapping


@dataclass(frozen=True)
class WaterFusionParameters:
    overlap_threshold: float = 0.1


def _as_float(value: object, default: float) -> float:
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return default


def _resolve_water_parameters(parameters: Dict[str, object] | None) -> WaterFusionParameters:
    parameters = parameters or {}
    threshold = _as_float(parameters.get("overlap_threshold"), 0.1)
    return WaterFusionParameters(overlap_threshold=max(0.0, min(1.0, threshold)))


def _to_target_crs(gdf: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        gdf = gdf.set_crs(target_crs)
    return gdf.to_crs(target_crs)


def _valid_polygonal(geometry: BaseGeometry | None) -> bool:
    return geometry is not None and not geometry.is_empty and geometry.area > 0


def _first_text(row: pd.Series, names: Iterable[str], default: str = "") -> str:
    for name in names:
        if name in row and pd.notna(row[name]):
            return str(row[name])
    return default


def _prepare_water(
    gdf: gpd.GeoDataFrame,
    target_crs: str,
    mapping: Dict[str, str] | None,
    id_column: str,
) -> gpd.GeoDataFrame:
    prepared = apply_field_mapping(gdf, mapping or {})
    prepared = _to_target_crs(prepared, target_crs)
    prepared = prepared[prepared.geometry.map(_valid_polygonal)].copy()
    prepared = prepared.reset_index(drop=True)
    prepared[id_column] = np.arange(1, len(prepared) + 1)
    return prepared


def _build_osm_row(osm_row: pd.Series, matches: list[tuple[int, float]]) -> dict[str, object]:
    match_ids = [str(ref_id) for ref_id, _ratio in matches]
    return {
        "OSM_ID": int(osm_row["OSM_ID"]),
        "REF_ID": np.nan,
        "MATCH_REF": ";".join(match_ids),
        "OV_RATIO": max((ratio for _ref_id, ratio in matches), default=0.0),
        "MATCH_CNT": len(matches),
        "SRC": "osm",
        "NAME": _first_text(osm_row, ("name", "NAME")),
        "FCLASS": _first_text(osm_row, ("fclass", "FCLASS"), "water"),
        "WATER_TY": _first_text(osm_row, ("water", "WATER", "type", "TYPE")),
        "geometry": osm_row.geometry,
    }


def _build_ref_row(ref_row: pd.Series) -> dict[str, object]:
    return {
        "OSM_ID": np.nan,
        "REF_ID": int(ref_row["REF_ID"]),
        "MATCH_REF": str(int(ref_row["REF_ID"])),
        "OV_RATIO": 0.0,
        "MATCH_CNT": 0,
        "SRC": "ref",
        "NAME": _first_text(ref_row, ("name", "NAME")),
        "FCLASS": "ref_water",
        "WATER_TY": _first_text(ref_row, ("water", "WATER", "type", "TYPE")),
        "geometry": ref_row.geometry,
    }


def _match_water_polygons(
    osm_data: gpd.GeoDataFrame,
    ref_data: gpd.GeoDataFrame,
    overlap_threshold: float,
) -> gpd.GeoDataFrame:
    if osm_data.empty and ref_data.empty:
        raise ValueError("Both OSM and reference water datasets are empty.")

    records: list[dict[str, object]] = []
    matched_ref_ids: set[int] = set()

    if not osm_data.empty and not ref_data.empty:
        ref_sindex = ref_data.sindex
        for _idx, osm_row in osm_data.iterrows():
            osm_geom = osm_row.geometry
            matches: list[tuple[int, float]] = []
            for ref_idx in ref_sindex.intersection(osm_geom.bounds):
                ref_row = ref_data.iloc[ref_idx]
                ref_geom = ref_row.geometry
                intersection_area = osm_geom.intersection(ref_geom).area
                overlap_ratio = intersection_area / osm_geom.area if osm_geom.area else 0.0
                if overlap_ratio >= overlap_threshold:
                    ref_id = int(ref_row["REF_ID"])
                    matches.append((ref_id, overlap_ratio))
                    matched_ref_ids.add(ref_id)
            records.append(_build_osm_row(osm_row, matches))
    else:
        for _idx, osm_row in osm_data.iterrows():
            records.append(_build_osm_row(osm_row, []))

    for _idx, ref_row in ref_data.iterrows():
        if int(ref_row["REF_ID"]) not in matched_ref_ids:
            records.append(_build_ref_row(ref_row))

    return gpd.GeoDataFrame(records, geometry="geometry", crs=osm_data.crs or ref_data.crs)


def _finalize_water_output(frame: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
    output = frame.copy()
    if output.crs is None:
        output = output.set_crs(target_crs)
    else:
        output = output.to_crs(target_crs)
    columns = ["OSM_ID", "REF_ID", "MATCH_REF", "OV_RATIO", "MATCH_CNT", "SRC", "NAME", "FCLASS", "WATER_TY", "geometry"]
    for column in columns:
        if column not in output.columns:
            output[column] = np.nan if column.endswith("_ID") or column in {"OV_RATIO", "MATCH_CNT"} else ""
    output["MATCH_REF"] = output["MATCH_REF"].fillna("").astype(str)
    output["SRC"] = output["SRC"].fillna("").astype(str)
    output["NAME"] = output["NAME"].fillna("").astype(str)
    output["FCLASS"] = output["FCLASS"].fillna("").astype(str)
    output["WATER_TY"] = output["WATER_TY"].fillna("").astype(str)
    output["OV_RATIO"] = output["OV_RATIO"].fillna(0.0).astype(float)
    output["MATCH_CNT"] = output["MATCH_CNT"].fillna(0).astype(int)
    return gpd.GeoDataFrame(output[columns], geometry="geometry", crs=target_crs)


def run_water_fusion(
    osm_shp: Path,
    ref_shp: Path,
    output_dir: Path,
    target_crs: str = "EPSG:32643",
    field_mapping: Dict[str, Dict[str, str]] | None = None,
    debug: bool = False,
    parameters: Dict[str, object] | None = None,
) -> Path:
    del debug
    resolved_parameters = _resolve_water_parameters(parameters)

    osm_raw = gpd.read_file(osm_shp)
    ref_raw = gpd.read_file(ref_shp)
    osm_data = _prepare_water(osm_raw, target_crs, (field_mapping or {}).get("osm"), "OSM_ID")
    ref_data = _prepare_water(ref_raw, target_crs, (field_mapping or {}).get("ref"), "REF_ID")

    fused = _match_water_polygons(osm_data, ref_data, resolved_parameters.overlap_threshold)
    fused = _finalize_water_output(fused, target_crs)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_shp = output_dir / "fused_water.shp"
    fused.to_file(output_shp)
    return output_shp
```

- [x] **Step 4: Run the adapter test and verify it passes**

Run:

```powershell
python -m pytest tests/test_water_adapter.py -q
```

Expected: PASS.

- [x] **Step 5: Commit adapter slice**

Run:

```powershell
git add adapters/water_adapter.py tests/test_water_adapter.py
git commit -m "feat: add water polygon adapter"
```

### Task 2: KG Water Ontology And Planner Context

**Files:**
- Modify: `schemas/fusion.py`
- Modify: `kg/seed.py`
- Modify: `kg/source_catalog.py`
- Modify: `agent/intent_resolver.py`
- Modify: `tests/test_ontology_closure.py`
- Modify: `tests/test_kg_repository_enhancements.py`
- Modify: `tests/test_planner_context.py`

- [x] **Step 1: Write failing KG and planner tests**

Append to `tests/test_ontology_closure.py`:

```python
def test_water_vertical_slice_seed_records_are_present() -> None:
    assert "dt.water.bundle" in DATA_TYPES
    assert "dt.water.fused" in DATA_TYPES
    assert "task.water.fusion" in {task.task_id for task in TASKS.values()}
    assert "algo.fusion.water.v1" in ALGORITHMS
    assert "dt.water.fused" in OUTPUT_SCHEMA_POLICIES
    assert any(pattern.job_type == JobType.water for pattern in WORKFLOW_PATTERNS)
```

Append to `tests/test_kg_repository_enhancements.py`:

```python
def test_repository_returns_water_patterns_and_uploaded_bundle_source() -> None:
    repo = InMemoryKGRepository()

    patterns = repo.get_candidate_patterns(job_type=JobType.water, disaster_type="flood")
    sources = repo.get_candidate_data_sources(job_type=JobType.water, disaster_type="flood", required_type="dt.water.bundle")

    assert [pattern.pattern_id for pattern in patterns] == ["wp.flood.water.default"]
    assert any(source.source_id == "upload.bundle" for source in sources)
```

Append to `tests/test_planner_context.py`:

```python
def test_planner_context_exposes_water_vertical_slice_metadata() -> None:
    provider = CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)
    trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="water fusion for uploaded lake polygons",
        disaster_type="flood",
    )

    plan = planner.create_plan(run_id="run-water-context", job_type=JobType.water, trigger=trigger)

    assert provider.last_context is not None
    patterns = provider.last_context["retrieval"]["candidate_patterns"]
    data_types = provider.last_context["retrieval"]["data_types"]
    algorithms = provider.last_context["retrieval"]["algorithms"]
    policies = provider.last_context["retrieval"]["output_schema_policies"]

    assert patterns[0]["pattern_id"] == "wp.flood.water.default"
    assert any(item["type_id"] == "dt.water.bundle" for item in data_types)
    assert any(item["type_id"] == "dt.water.fused" for item in data_types)
    assert "algo.fusion.water.v1" in algorithms
    assert "dt.water.fused" in policies
    assert plan.tasks[0].algorithm_id == "algo.fusion.water.v1"
    assert plan.tasks[0].input.data_type_id == "dt.water.bundle"
    assert plan.tasks[0].output.data_type_id == "dt.water.fused"
```

- [x] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_ontology_closure.py tests/test_kg_repository_enhancements.py tests/test_planner_context.py -q
```

Expected: FAIL because `JobType.water` and water KG records do not exist yet.

- [x] **Step 3: Add water job type and KG seed records**

Modify `schemas/fusion.py`:

```python
class JobType(str, Enum):
    building = "building"
    road = "road"
    water = "water"
```

In `kg/seed.py`, add:

```python
"dt.water.bundle": DataTypeNode(
    type_id="dt.water.bundle",
    theme="water",
    geometry_type="polygon",
    description="Prepared water polygon fusion input bundle.",
),
"dt.water.fused": DataTypeNode(
    type_id="dt.water.fused",
    theme="water",
    geometry_type="polygon",
    description="Fused water polygon output.",
),
```

Add:

```python
"task.water.fusion": TaskNode(
    task_id="task.water.fusion",
    task_name="Water Fusion",
    category="fusion",
    description="Fuse multiple water polygon vector sources into one output.",
),
```

Add:

```python
"algo.fusion.water.v1": AlgorithmNode(
    algo_id="algo.fusion.water.v1",
    algo_name="Water Polygon Fusion",
    input_types=["dt.water.bundle"],
    output_type="dt.water.fused",
    task_type="water_fusion",
    tool_ref="adapters.water_adapter:run_water_fusion",
    success_rate=0.83,
    accuracy_score=0.8,
    stability_score=0.86,
    usage_mode="conservative",
    metadata={
        "selection_profile": "primary",
        "evidence_basis": "uploaded_polygon_runtime",
    },
    alternatives=[],
),
```

Add a workflow pattern:

```python
WorkflowPatternNode(
    pattern_id="wp.flood.water.default",
    pattern_name="Flood Water Polygon Fusion",
    job_type=JobType.water,
    disaster_types=["flood", "generic"],
    success_rate=0.83,
    metadata={
        "version": "1.0.0",
        "runtime_status": "runtime_candidate",
        "input_strategy": "uploaded_only",
    },
    steps=[
        PatternStep(
            order=1,
            name="water_fusion",
            algorithm_id="algo.fusion.water.v1",
            input_data_type="dt.water.bundle",
            output_data_type="dt.water.fused",
            data_source_id="upload.bundle",
        )
    ],
),
```

Add an output schema policy:

```python
"dt.water.fused": OutputSchemaPolicy(
    policy_id="osp.water.fused.v1",
    output_type="dt.water.fused",
    job_type=JobType.water,
    retention_mode="preserve_listed",
    required_fields=["geometry"],
    optional_fields=["OSM_ID", "REF_ID", "MATCH_REF", "OV_RATIO", "MATCH_CNT", "SRC", "NAME", "FCLASS", "WATER_TY"],
    rename_hints={},
    compatibility_basis="field_names",
    metadata={
        "policy_scope": "current_runtime",
        "notes": "Water output schema is metadata-only and mirrors the uploaded polygon adapter output.",
    },
),
```

Update `CAN_TRANSFORM_TO`:

```python
CAN_TRANSFORM_TO: Dict[str, List[str]] = {
    "dt.raw.vector": ["dt.building.bundle", "dt.road.bundle", "dt.water.bundle"],
}
```

Modify `kg/source_catalog.py` upload bundle:

```python
supported_types=["dt.building.bundle", "dt.road.bundle", "dt.water.bundle", "dt.raw.vector"],
supported_job_types=["building", "road", "water"],
```

Modify water raw source metadata where present:

```python
supported_job_types=["water"],
```

Modify `agent/intent_resolver.py` task hints:

```python
"water": {"water", "lake", "river", "reservoir", "pond"},
```

- [x] **Step 4: Run KG/planner tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_ontology_closure.py tests/test_kg_repository_enhancements.py tests/test_planner_context.py -q
```

Expected: PASS.

- [x] **Step 5: Commit KG slice**

Run:

```powershell
git add schemas/fusion.py kg/seed.py kg/source_catalog.py agent/intent_resolver.py tests/test_ontology_closure.py tests/test_kg_repository_enhancements.py tests/test_planner_context.py
git commit -m "feat: seed water fusion ontology"
```

### Task 3: Executor And V2 Uploaded Runtime

**Files:**
- Modify: `agent/executor.py`
- Modify: `tests/test_api_v2_integration.py`

- [x] **Step 1: Write failing v2 uploaded integration test**

In `tests/test_api_v2_integration.py`, add:

```python
def _build_water_sample(tmp_path: Path) -> tuple[Path, Path]:
    from shapely.geometry import Polygon

    osm = geopandas.GeoDataFrame(
        {
            "name": ["osm lake", "osm pond"],
            "fclass": ["water", "water"],
            "water": ["lake", "pond"],
            "geometry": [
                Polygon([(0, 0), (0, 0.01), (0.01, 0.01), (0.01, 0)]),
                Polygon([(0.02, 0.02), (0.02, 0.03), (0.03, 0.03), (0.03, 0.02)]),
            ],
        },
        crs="EPSG:4326",
    )
    ref = geopandas.GeoDataFrame(
        {
            "name": ["ref lake", "ref reservoir"],
            "water": ["lake", "reservoir"],
            "geometry": [
                Polygon([(0, 0), (0, 0.011), (0.011, 0.011), (0.011, 0)]),
                Polygon([(0.04, 0.04), (0.04, 0.05), (0.05, 0.05), (0.05, 0.04)]),
            ],
        },
        crs="EPSG:4326",
    )
    osm_shp = tmp_path / "osm_water.shp"
    ref_shp = tmp_path / "ref_water.shp"
    osm.to_file(osm_shp)
    ref.to_file(ref_shp)
    return osm_shp, ref_shp


def test_v2_run_water_uploaded_integration(tmp_path: Path, client: TestClient) -> None:
    osm_shp, ref_shp = _build_water_sample(tmp_path)
    osm_zip = _zip_bundle(osm_shp, tmp_path / "osm_water.zip")
    ref_zip = _zip_bundle(ref_shp, tmp_path / "ref_water.zip")

    with osm_zip.open("rb") as f1, ref_zip.open("rb") as f2:
        resp = client.post(
            "/api/v2/runs",
            files={
                "osm_zip": ("osm_water.zip", f1.read(), "application/zip"),
                "ref_zip": ("ref_water.zip", f2.read(), "application/zip"),
            },
            data={
                "job_type": "water",
                "trigger_type": "user_query",
                "trigger_content": "融合水体多边形",
                "disaster_type": "flood",
                "target_crs": "EPSG:32643",
                "field_mapping": "{}",
                "debug": "false",
            },
        )
    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]

    status = _wait_run(client, run_id)
    assert status["phase"] == "succeeded", status.get("error")

    plan_resp = client.get(f"/api/v2/runs/{run_id}/plan")
    assert plan_resp.status_code == 200
    plan = plan_resp.json()["plan"]
    assert plan["tasks"][0]["algorithm_id"] == "algo.fusion.water.v1"
    assert plan["tasks"][0]["input"]["data_type_id"] == "dt.water.bundle"
    assert plan["tasks"][0]["output"]["data_type_id"] == "dt.water.fused"

    inspection_resp = client.get(f"/api/v2/runs/{run_id}/inspection")
    assert inspection_resp.status_code == 200
    inspection = inspection_resp.json()
    assert inspection["run"]["job_type"] == "water"
    assert inspection["artifact"]["available"] is True
    assert inspection["artifact"]["download_path"] == f"/api/v2/runs/{run_id}/artifact"

    artifact_resp = client.get(f"/api/v2/runs/{run_id}/artifact")
    assert artifact_resp.status_code == 200
    assert artifact_resp.content
```

- [x] **Step 2: Run v2 test and verify it fails**

Run:

```powershell
python -m pytest tests/test_api_v2_integration.py::test_v2_run_water_uploaded_integration -q
```

Expected: FAIL with `No handler registered for algorithm: algo.fusion.water.v1`.

- [x] **Step 3: Register executor handler**

Modify `agent/executor.py`:

```python
self.algorithm_handlers.setdefault("algo.fusion.water.v1", self._handle_water)
```

Add:

```python
@staticmethod
def _handle_water(context: ExecutionContext) -> Path:
    from adapters.water_adapter import run_water_fusion

    return run_water_fusion(
        osm_shp=context.osm_shp,
        ref_shp=context.ref_shp,
        output_dir=context.output_dir,
        target_crs=context.target_crs,
        field_mapping=context.field_mapping,
        debug=context.debug,
        parameters=dict(context.step_parameters or {}),
    )
```

- [x] **Step 4: Run v2 test and verify it passes**

Run:

```powershell
python -m pytest tests/test_api_v2_integration.py::test_v2_run_water_uploaded_integration -q
```

Expected: PASS.

- [x] **Step 5: Commit runtime slice**

Run:

```powershell
git add agent/executor.py tests/test_api_v2_integration.py
git commit -m "feat: execute uploaded water runs"
```

### Task 4: Neo4j Bootstrap And Evidence Docs

**Files:**
- Modify: `kg/bootstrap/neo4j_bootstrap.cypher`
- Modify: `tests/test_neo4j_bootstrap.py`
- Modify: `docs/superpowers/specs/2026-04-20-evidence-ledger.md`

- [x] **Step 1: Write failing bootstrap test**

Append to `tests/test_neo4j_bootstrap.py`:

```python
def test_bootstrap_cypher_contains_water_vertical_slice() -> None:
    cypher = build_bootstrap_cypher()

    assert "dt.water.bundle" in cypher
    assert "dt.water.fused" in cypher
    assert "task.water.fusion" in cypher
    assert "algo.fusion.water.v1" in cypher
    assert "wp.flood.water.default" in cypher
    assert "osp.water.fused.v1" in cypher
```

- [x] **Step 2: Run bootstrap test and verify it passes from seed but file diff is stale**

Run:

```powershell
python -m pytest tests/test_neo4j_bootstrap.py::test_bootstrap_cypher_contains_water_vertical_slice -q
```

Expected: PASS after Task 2 because generated Cypher comes from seed.

Then check tracked bootstrap file:

```powershell
Select-String -Path kg/bootstrap/neo4j_bootstrap.cypher -Pattern "dt.water.fused"
```

Expected before regeneration: no match.

- [x] **Step 3: Regenerate tracked bootstrap Cypher**

Run:

```powershell
@'
from pathlib import Path
from kg.bootstrap import build_bootstrap_cypher

Path("kg/bootstrap/neo4j_bootstrap.cypher").write_text(build_bootstrap_cypher(), encoding="utf-8")
'@ | python -
```

Expected: `kg/bootstrap/neo4j_bootstrap.cypher` now contains water records.

- [x] **Step 4: Update evidence ledger with Phase F evidence**

Append or update the Runtime Capability Evidence section in `docs/superpowers/specs/2026-04-20-evidence-ledger.md`:

```markdown
| Phase F water uploaded vertical slice | `docs/superpowers/plans/2026-04-20-water-vertical-slice.md`, `tests/test_water_adapter.py`, `tests/test_api_v2_integration.py::test_v2_run_water_uploaded_integration` | Third task/data vertical slice beyond building/road, limited to uploaded polygon inputs | strong | Proves KG planning, executor dispatch, adapter output, v2 API artifact writeback, and bootstrap closure for `JobType.water`; does not claim task-driven auto water materialization |
```

- [x] **Step 5: Commit bootstrap/docs slice**

Run:

```powershell
git add kg/bootstrap/neo4j_bootstrap.cypher tests/test_neo4j_bootstrap.py docs/superpowers/specs/2026-04-20-evidence-ledger.md docs/superpowers/plans/2026-04-20-water-vertical-slice.md
git commit -m "docs: record water vertical slice evidence"
```

### Task 5: Final Verification, Merge, Push, Cleanup

**Files:**
- No planned source edits.

- [x] **Step 1: Run focused verification**

Run:

```powershell
python -m pytest tests/test_water_adapter.py tests/test_api_v2_integration.py::test_v2_run_water_uploaded_integration tests/test_ontology_closure.py tests/test_kg_repository_enhancements.py tests/test_planner_context.py tests/test_neo4j_bootstrap.py -q
```

Expected: PASS.

- [x] **Step 2: Run full verification**

Run:

```powershell
python -m pytest -q
```

Expected: PASS with the known pyproj/numpy warnings only.

- [x] **Step 3: Inspect branch diff**

Run:

```powershell
git status --short
git log --oneline main..HEAD
git diff --stat main..HEAD
```

Expected: clean status and only Phase F water vertical slice files changed.

- [x] **Step 4: Merge and push**

From main worktree `E:\vscode\fusionAgent`:

```powershell
git fetch origin
git checkout main
git merge --ff-only codex/water-vertical-slice
git push origin main
```

Expected: fast-forward merge and push succeed.

- [x] **Step 5: Clean temporary branch/worktree**

Run:

```powershell
git worktree remove C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\water-vertical-slice
git branch -d codex/water-vertical-slice
git worktree list
git status --short
```

Expected: only main worktree remains and status is clean.

## Gate After Phase F

Continue to Phase G only if the water slice proves architecture extensibility without adding task-driven auto water assumptions. Phase G should freeze the experiment matrix and paper evidence paths; Phase H should remain deferred unless product demonstration requires a thin operator surface.

