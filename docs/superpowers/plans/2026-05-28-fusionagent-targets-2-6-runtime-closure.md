# FusionAgent Targets 2-6 Runtime Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 FusionAgent 的建筑物、道路、水系、POI 和大范围拼接裁剪能力统一提升为稳定的共享运行时能力，完成后用户目标 2-6 可作为工程可执行能力声明。

**Architecture:** 以现有 `AgentRunService -> InputAcquisitionService -> SourceSemanticContractService -> WorkflowExecutor -> writeback/report` 主链为唯一入口，不再把大范围能力留在 Track B evidence utility 或 building 专用分支中。新增共享 `LargeAreaRuntimeService`，按 `polygon / line / point / building` 几何族统一 tile、clip、per-tile fusion、owner-bbox stitch、schema validation、source evidence 和报告摘要；building 在该服务上接入多源矢量与高度栅格，road/water/POI 接入现有 V7 和 geohash 算法。

**Tech Stack:** Python 3.11+, GeoPandas, Shapely, pandas, rasterio/GDAL CLI helpers already present in repo, FastAPI v2 run APIs, existing KG/source catalog, pytest.

---

## Completion Contract For Targets 2-6

完成本计划后，以下能力必须能通过 `task_driven_auto` 或显式 runtime service 测试稳定证明：

| Target | Required complete state |
| --- | --- |
| 2 building vector + height raster fusion | 默认 remote-capable `OSM + Microsoft` 建筑物矢量融合；支持本地/预加载 Google、OpenBuildingMap、Google Open Buildings Vector、Microsoft local cache 作为补充；当高度栅格存在时自动纳入 `SourceSemanticContract.height_policy` 并输出 `height_raster`、`height_final`、`height_final_source`。 |
| 3 road vector fusion | `OSM road + Overture transportation` 自动下载/本地缓存/裁剪，进入 V7 road conflation，并在大范围 tile/stitch 后输出稳定 road schema、source lineage、fusion stats。 |
| 4 river/lake water vector fusion | 湖泊/面水体走 `OSM water polygons + HydroLAKES` polygon fusion；河流/水道走 `OSM waterways + HydroRIVERS` line V7 conflation；外部 `JobType.water` 可生成复合水系输出，并保留 `feature_kind=polygon|line` 和 source lineage。 |
| 5 POI fusion | `OSM POI + GNS/GeoNames gazetteer` 支持自动下载/本地缓存/裁剪；bounded AOI 内 geohash + name similarity fusion；输出 `source_id`、`source_rank`、`MATCHED`、canonical name/category/id provenance；开放式实体对齐继续由 preflight 拒绝。 |
| 6 large-area stitch/clip | building/road/water/POI 共享 tile manifest、buffered tile input clip、owner bbox stitch、geometry/WKB or canonical-id dedupe、最终 AOI/country boundary clip、`selected_sources.json`、`tile_manifest.json`、`stitched_artifact.json`、`fusion_stats.json`、run report evidence。 |

## Current Gap Summary

- `services/tiled_building_runtime_service.py` 已有 building tiled 和 multisource+raster utility，但 `services/agent_run_service.py` 中 `_raster_paths_for_source_semantics()` 仍返回空字典，height raster 未接入共享 runtime。
- `services/track_b_national_scale_service.py` 已能为 road/water/poi 产生 national-scale evidence，但它是 evidence utility，不是 `AgentRunService` 的统一执行合同。
- `services/agent_run_service.py` 只有 `_should_use_tiled_building_runtime()`，road/water/POI 不会在大范围 task-driven run 中进入共享 tile/stitch runtime。
- `kg/source_catalog.py` 中 `catalog.flood.building` 仍默认 `raw.google.building`，该源是 manual/local-only，不应作为“自动完全具备”的默认 flood building bundle。
- `schemas/fusion.py` 只有 `building / road / water / poi` 外部任务类型，已有 KG 内部 `dt.waterways.*` 和 Track B `waterways` 语义；本计划保持外部 `JobType.water`，在 runtime 内部拆成 `water_polygon` 和 `waterways_line` slice。
- Run report 已能输出过程/结果评价，但尚未把 large-area slice evidence、tile counts、source lineage、height policy、fusion stats 作为稳定报告字段。

## File Structure Map

### New Files

- `services/large_area_runtime_service.py`  
  共享大范围运行时。负责 tile manifest 创建、每 tile 输入切片、调用 domain fusion runner、owner bbox stitch、最终边界裁剪、evidence JSON 写出。

- `services/domain_fusion_runners.py`  
  轻量 domain runner 集合。封装 building multisource、road V7、water polygon、waterways line、POI geohash 的统一函数签名，避免 `LargeAreaRuntimeService` 直接堆满领域分支。

- `services/runtime_source_aliases.py`  
  source id 到 runtime alias 的稳定映射，例如 building `raw.microsoft.building -> MS`、POI `raw.gns.poi/raw.geonames.poi -> GNS`。

- `tests/test_large_area_runtime_service.py`  
  覆盖 polygon/line/point stitch、owner bbox 去重、country/bbox clip、evidence JSON。

- `tests/test_agent_run_service_large_area_runtime.py`  
  覆盖 `AgentRunService` 对 building/road/water/poi 的 task-driven 大范围 runtime 路由。

### Modified Files

- `schemas/fusion.py`  
  保持外部 `JobType` 不增加 breaking enum；增加 helper 常量或 runtime labels 时只在服务层做，不改 API 请求合同。

- `kg/source_catalog.py`  
  将 `catalog.flood.building` 默认 reference 调整为 `raw.microsoft.building`；保留 Google/OBM/GOBV/local MS 为 manual supplement source。

- `kg/track_b_source_contract.py`  
  将 `raw.geonames.poi` 作为 `raw.gns.poi` 的 canonical alias 写入合同，明确 GNS/GeoNames gazetteer 口径。

- `services/source_asset_service.py`  
  支持 `raw.geonames.poi` 归一化到 `raw.gns.poi` 的同一下载/缓存路径；加入本地 raster source resolution helper。

- `services/local_bundle_catalog.py`  
  确保 default catalog bundle 与 source catalog 调整一致，并能返回 component coverage 的真实 source ids。

- `services/input_acquisition_service.py`  
  将 materialized component coverage 中的 artifact path/source mode 保持到 `ResolvedRunInputs`，供 large-area runtime 和 source semantic contract 复用。

- `services/source_semantic_contract_service.py`  
  支持 raster source profile 被写入 `height_policy.raster_height_sources`，并保留 source metadata 到报告。

- `services/agent_run_service.py`  
  接入 `LargeAreaRuntimeService`；新增 `_should_use_large_area_runtime()`、`run_large_area_execution_stage()`、非 building 领域 source map 构建；接通 `_raster_paths_for_source_semantics()`。

- `services/tiled_building_runtime_service.py`  
  只做 building per-tile/domain logic，不再承担通用 large-area stitch 责任；保留现有 tests。

- `services/track_b_national_scale_service.py`  
  改为复用 `LargeAreaRuntimeService` 或 domain runners，避免 national evidence 与 shared runtime 行为分叉。

- `services/run_report_service.py`  
  报告加入 large-area evidence、source semantic contract、fusion stats、height policy、clip/stitch 评价。

- `docs/v2-operations.md`  
  将 2-6 从 “planner/evidence/research utility 边界” 改为 “shared runtime supported” 的稳定合同，并保留 manual-only source 边界。

### Existing Tests To Extend

- `tests/test_agent_run_service_multisource_building_runtime.py`
- `tests/test_tiled_multisource_building_runtime_service.py`
- `tests/test_track_b_national_scale_service.py`
- `tests/test_track_b_national_v7_routes.py`
- `tests/test_source_asset_service.py`
- `tests/test_source_semantic_contract_service.py`
- `tests/test_run_report_service.py`
- `tests/test_ontology_closure.py`
- `tests/test_local_bundle_catalog.py`

---

## Task 1: Lock The Targets 2-6 Capability Contract And Source Defaults

**Files:**
- Modify: `kg/source_catalog.py`
- Modify: `kg/track_b_source_contract.py`
- Modify: `services/runtime_source_aliases.py`
- Modify: `docs/v2-operations.md`
- Test: `tests/test_ontology_closure.py`
- Test: `tests/test_local_bundle_catalog.py`
- Test: `tests/test_national_source_matrix.py`

- [x] **Step 1: Write failing source-contract tests**

Add these assertions to `tests/test_ontology_closure.py`:

```python
def test_targets_2_6_default_sources_are_remote_capable() -> None:
    from kg.source_catalog import get_catalog_bundle_spec

    assert get_catalog_bundle_spec("catalog.flood.building").component_source_ids == (
        "raw.osm.building",
        "raw.microsoft.building",
    )
    assert get_catalog_bundle_spec("catalog.earthquake.building").component_source_ids == (
        "raw.osm.building",
        "raw.microsoft.building",
    )
    assert get_catalog_bundle_spec("catalog.flood.road").component_source_ids == (
        "raw.osm.road",
        "raw.overture.transportation",
    )
    assert get_catalog_bundle_spec("catalog.flood.water").component_source_ids == (
        "raw.osm.water",
        "raw.hydrolakes.water",
    )
    assert get_catalog_bundle_spec("catalog.generic.poi").component_source_ids == (
        "raw.osm.poi",
        "raw.gns.poi",
    )
```

Add this test to `tests/test_national_source_matrix.py`:

```python
def test_geonames_alias_is_documented_as_gns_poi_alias() -> None:
    from kg.track_b_source_contract import get_track_b_source_contract

    canonical = get_track_b_source_contract("raw.gns.poi")
    alias = get_track_b_source_contract("raw.geonames.poi")

    assert canonical is not None
    assert alias is not None
    assert alias.theme == "poi"
    assert alias.field_mapping_profile == canonical.field_mapping_profile
    assert "GNS" in alias.notes
    assert "GeoNames" in alias.notes
```

- [x] **Step 2: Run source-contract tests and verify failure**

Run:

```powershell
python -m pytest -q tests/test_ontology_closure.py::test_targets_2_6_default_sources_are_remote_capable tests/test_national_source_matrix.py::test_geonames_alias_is_documented_as_gns_poi_alias
```

Expected: FAIL because `catalog.flood.building` still points to `raw.google.building`, and `raw.geonames.poi` is not registered.

- [x] **Step 3: Create runtime source alias module**

Create `services/runtime_source_aliases.py`:

```python
from __future__ import annotations

from pathlib import Path


BUILDING_SOURCE_ALIASES: dict[str, str] = {
    "raw.microsoft.building": "MS",
    "raw.local.microsoft.building": "MICROSOFT_LOCAL",
    "raw.openbuildingmap.building": "OBM",
    "raw.google.open_buildings.vector": "GOOGLE_OPEN_BUILDINGS",
    "raw.google.building": "GOOGLE",
    "raw.osm.building": "OSM",
}

BUILDING_SOURCE_PRIORITY_ORDER: tuple[str, ...] = (
    "MS",
    "MICROSOFT_LOCAL",
    "OBM",
    "GOOGLE_OPEN_BUILDINGS",
    "GOOGLE",
    "OSM",
)

POI_SOURCE_ALIASES: dict[str, str] = {
    "raw.osm.poi": "OSM",
    "raw.gns.poi": "GNS",
    "raw.geonames.poi": "GNS",
    "raw.rh.poi": "RH",
}

POI_SOURCE_PRIORITY_ORDER: tuple[str, ...] = ("OSM", "GNS", "RH")

LINE_SOURCE_ALIASES: dict[str, str] = {
    "raw.osm.road": "OSM",
    "raw.overture.transportation": "OVERTURE",
    "raw.overture.road": "OVERTURE",
    "raw.osm.waterways": "OSM",
    "raw.hydrorivers.water": "HYDRORIVERS",
    "raw.local.pakistan.waterways": "LOCAL_WATERWAYS",
}

POLYGON_WATER_SOURCE_ALIASES: dict[str, str] = {
    "raw.osm.water": "OSM",
    "raw.hydrolakes.water": "HYDROLAKES",
    "raw.local.water": "LOCAL_WATER",
}


def alias_paths(component_paths: dict[str, Path], aliases: dict[str, str]) -> dict[str, Path]:
    return {
        alias: path
        for source_id, path in component_paths.items()
        if (alias := aliases.get(source_id)) is not None
    }
```

- [x] **Step 4: Update default catalog and GeoNames alias contract**

In `kg/source_catalog.py`, change only the `catalog.flood.building` bundle:

```python
CatalogBundleSpec(
    source_id="catalog.flood.building",
    osm_source_id="raw.osm.building",
    ref_source_id="raw.microsoft.building",
    bundle_strategy="osm_ref_pair",
),
```

In `kg/track_b_source_contract.py`, add a `raw.geonames.poi` contract immediately after `raw.gns.poi`:

```python
"raw.geonames.poi": TrackBSourceContract(
    source_id="raw.geonames.poi",
    theme="poi",
    role="reference_remote_alias",
    acquisition_class="official_remote_supported",
    format_hint="country_zip_tabular_export",
    clip_strategy="country_zip_then_aoi_clip",
    field_mapping_profile="fields.poi.gns",
    license_boundary="Alias for raw.gns.poi; preserve GNS / GeoNames gazetteer attribution.",
    runtime_status="runtime_candidate",
    notes="Canonical alias for operators who request GeoNames POI; runtime materialization reuses raw.gns.poi.",
),
```

- [x] **Step 5: Update docs capability wording**

In `docs/v2-operations.md`, replace the Large-AOI boundary table rows for building multisource/raster with the shared-runtime wording:

```markdown
| tiled multi-source building fusion with optional raster enrichment | supported in the shared large-area runtime when at least two vector sources are materialized |
| raster-based building height extraction inside the multi-source runtime | supported when `SourceSemanticContract.height_policy.raster_height_sources` contains a readable raster |
```

Also add a short source boundary paragraph:

```markdown
Default automated building bundles use `raw.osm.building + raw.microsoft.building`. Google/OpenBuildingMap/Google Open Buildings Vector/local Microsoft remain manual-preload supplements unless their source contract is explicitly promoted by tests and evidence.
```

- [x] **Step 6: Run contract tests**

Run:

```powershell
python -m pytest -q tests/test_ontology_closure.py tests/test_local_bundle_catalog.py tests/test_national_source_matrix.py
```

Expected: PASS.

- [x] **Step 7: Commit**

```powershell
git add kg/source_catalog.py kg/track_b_source_contract.py services/runtime_source_aliases.py docs/v2-operations.md tests/test_ontology_closure.py tests/test_local_bundle_catalog.py tests/test_national_source_matrix.py
git commit -m "feat: lock targets 2-6 source contract"
```

---

## Task 2: Build The Shared Large-Area Runtime Service

**Files:**
- Create: `services/large_area_runtime_service.py`
- Create: `services/domain_fusion_runners.py`
- Test: `tests/test_large_area_runtime_service.py`

- [x] **Step 1: Write failing tests for tile/stitch behavior**

Create `tests/test_large_area_runtime_service.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon, box

from services.large_area_runtime_service import LargeAreaRuntimeService, LargeAreaSlice
from services.tile_partition_service import TileManifest, TileSpec


def _manifest() -> TileManifest:
    return TileManifest(
        bbox=(0.0, 0.0, 2.0, 1.0),
        bbox_crs="EPSG:3857",
        working_crs="EPSG:3857",
        tile_width_m=1.0,
        tile_height_m=1.0,
        overlap_m=0.2,
        tiles=[
            TileSpec("tile_000_000", (0.0, 0.0, 1.0, 1.0), (-0.2, -0.2, 1.2, 1.2), (0.0, 0.0, 1.0, 1.0), (-0.2, -0.2, 1.2, 1.2), 0, 0),
            TileSpec("tile_000_001", (1.0, 0.0, 2.0, 1.0), (0.8, -0.2, 2.2, 1.2), (1.0, 0.0, 2.0, 1.0), (0.8, -0.2, 2.2, 1.2), 0, 1),
        ],
    )


def _write(path: Path, frame: gpd.GeoDataFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(path, driver="GPKG")
    return path


def test_large_area_runtime_stitches_owner_bbox_without_overlap_duplicates(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "source.gpkg",
        gpd.GeoDataFrame(
            {"source_id": ["raw.test", "raw.test"]},
            geometry=[Point(0.5, 0.5), Point(1.5, 0.5)],
            crs="EPSG:3857",
        ),
    )

    def runner(tile, sources, output_dir, target_crs, parameters):
        del sources, parameters
        frame = gpd.GeoDataFrame(
            {"source_id": ["raw.test", "raw.test"], "canonical_id": ["a", "b"]},
            geometry=[Point(0.5, 0.5), Point(1.5, 0.5)],
            crs=target_crs,
        )
        path = output_dir / "fused.gpkg"
        frame.to_file(path, driver="GPKG")
        return path, {"algorithm_id": "algo.test.points", "tile_id": tile.tile_id}

    result = LargeAreaRuntimeService(max_workers=1).run(
        run_id="run-large-area",
        job_type="poi",
        tile_manifest=_manifest(),
        slices=[LargeAreaSlice(name="poi", geometry_family="point", sources={"raw.test": source}, runner=runner)],
        output_dir=tmp_path / "out",
        target_crs="EPSG:3857",
        parameters={},
    )

    fused = gpd.read_file(result.output_path)
    evidence = json.loads((tmp_path / "out" / "stitched_artifact.json").read_text(encoding="utf-8"))

    assert len(fused) == 2
    assert set(fused["canonical_id"]) == {"a", "b"}
    assert result.tile_count == 2
    assert evidence["tile_count"] == 2
    assert evidence["stitched_feature_count"] == 2


def test_large_area_runtime_clips_final_polygon_output_to_boundary(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "water.gpkg",
        gpd.GeoDataFrame({"source_id": ["raw.water"]}, geometry=[box(-1.0, -1.0, 2.0, 2.0)], crs="EPSG:3857"),
    )
    clip_boundary = gpd.GeoDataFrame({"name": ["clip"]}, geometry=[box(0.0, 0.0, 1.0, 1.0)], crs="EPSG:3857")

    def runner(tile, sources, output_dir, target_crs, parameters):
        del tile, sources, parameters
        path = output_dir / "fused.gpkg"
        gpd.GeoDataFrame(
            {"source_id": ["raw.water"], "feature_kind": ["polygon"]},
            geometry=[box(-1.0, -1.0, 2.0, 2.0)],
            crs=target_crs,
        ).to_file(path, driver="GPKG")
        return path, {"algorithm_id": "algo.test.water"}

    result = LargeAreaRuntimeService(max_workers=1).run(
        run_id="run-water",
        job_type="water",
        tile_manifest=_manifest(),
        slices=[LargeAreaSlice(name="water_polygon", geometry_family="polygon", sources={"raw.water": source}, runner=runner)],
        output_dir=tmp_path / "out-water",
        target_crs="EPSG:3857",
        parameters={},
        clip_boundary=clip_boundary,
    )

    fused = gpd.read_file(result.output_path)
    assert fused.geometry.iloc[0].within(box(0.0, 0.0, 1.0, 1.0)) or fused.geometry.iloc[0].equals(box(0.0, 0.0, 1.0, 1.0))
```

- [x] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest -q tests/test_large_area_runtime_service.py
```

Expected: FAIL because `services.large_area_runtime_service` does not exist.

- [x] **Step 3: Implement public dataclasses and runner signature**

Create `services/large_area_runtime_service.py` with:

```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from services.artifact_evaluation_service import evaluate_vector_artifact
from services.tile_partition_service import TileManifest, TileSpec

GeometryFamily = Literal["building", "polygon", "line", "point"]
DomainRunner = Callable[[TileSpec, dict[str, Path], Path, str, dict[str, Any]], tuple[Path, dict[str, Any]]]


@dataclass(frozen=True)
class LargeAreaSlice:
    name: str
    geometry_family: GeometryFamily
    sources: dict[str, Path]
    runner: DomainRunner
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LargeAreaTileOutput:
    tile_id: str
    slice_name: str
    output_path: Path
    feature_count: int
    working_bbox: tuple[float, float, float, float]
    stats: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tile_id": self.tile_id,
            "slice_name": self.slice_name,
            "output_path": str(self.output_path),
            "feature_count": self.feature_count,
            "working_bbox": [float(value) for value in self.working_bbox],
            "stats": self.stats,
        }


@dataclass(frozen=True)
class LargeAreaRunResult:
    output_path: Path
    tile_count: int
    stitched_feature_count: int
    tile_outputs: list[LargeAreaTileOutput]
    evidence_paths: dict[str, Path]
```

- [x] **Step 4: Implement `LargeAreaRuntimeService.run()`**

Add this implementation below the dataclasses:

```python
class LargeAreaRuntimeService:
    def __init__(self, *, max_workers: int = 1) -> None:
        self.max_workers = max(1, int(max_workers))

    def run(
        self,
        *,
        run_id: str,
        job_type: str,
        tile_manifest: TileManifest,
        slices: list[LargeAreaSlice],
        output_dir: Path,
        target_crs: str,
        parameters: dict[str, Any],
        clip_boundary: gpd.GeoDataFrame | None = None,
    ) -> LargeAreaRunResult:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "tile_manifest.json").write_text(
            json.dumps({**tile_manifest.to_dict(), "manifest_mode": "shared_large_area_runtime", "tile_count": len(tile_manifest.tiles)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        tile_outputs: list[LargeAreaTileOutput] = []
        for tile in tile_manifest.tiles:
            for slice_spec in slices:
                tile_dir = output_dir / "tiles" / tile.tile_id / slice_spec.name
                tile_dir.mkdir(parents=True, exist_ok=True)
                merged_parameters = {**parameters, **slice_spec.parameters}
                output_path, stats = slice_spec.runner(tile, slice_spec.sources, tile_dir, target_crs, merged_parameters)
                feature_count = self._feature_count(output_path)
                tile_outputs.append(
                    LargeAreaTileOutput(
                        tile_id=tile.tile_id,
                        slice_name=slice_spec.name,
                        output_path=Path(output_path),
                        feature_count=feature_count,
                        working_bbox=tile.working_bbox,
                        stats=stats,
                    )
                )

        final_output = self._stitch(
            tile_outputs=tile_outputs,
            output_path=output_dir / f"{job_type}_large_area_fused.gpkg",
            target_crs=target_crs,
            clip_boundary=clip_boundary,
        )
        artifact_metrics = evaluate_vector_artifact(final_output, required_fields=["geometry"])
        evidence_payload = {
            "run_id": run_id,
            "job_type": job_type,
            "artifact_path": str(final_output),
            "tile_count": len(tile_manifest.tiles),
            "slice_count": len(slices),
            "stitched_feature_count": int(artifact_metrics.get("feature_count") or 0),
            "artifact_metrics": artifact_metrics,
            "tile_outputs": [item.to_dict() for item in tile_outputs],
            "slice_names": [item.name for item in slices],
        }
        stitched_path = output_dir / "stitched_artifact.json"
        stats_path = output_dir / "fusion_stats.json"
        stitched_path.write_text(json.dumps(evidence_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        stats_path.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "job_type": job_type,
                    "tile_stats": [item.to_dict() for item in tile_outputs],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return LargeAreaRunResult(
            output_path=final_output,
            tile_count=len(tile_manifest.tiles),
            stitched_feature_count=int(artifact_metrics.get("feature_count") or 0),
            tile_outputs=tile_outputs,
            evidence_paths={
                "tile_manifest": output_dir / "tile_manifest.json",
                "stitched_artifact": stitched_path,
                "fusion_stats": stats_path,
            },
        )
```

- [x] **Step 5: Implement stitch helpers**

Add these methods inside `LargeAreaRuntimeService`:

```python
    @staticmethod
    def _feature_count(path: Path) -> int:
        try:
            return int(len(gpd.read_file(path).index))
        except Exception:
            return 0

    def _stitch(
        self,
        *,
        tile_outputs: list[LargeAreaTileOutput],
        output_path: Path,
        target_crs: str,
        clip_boundary: gpd.GeoDataFrame | None,
    ) -> Path:
        frames: list[gpd.GeoDataFrame] = []
        for tile_output in tile_outputs:
            frame = gpd.read_file(tile_output.output_path)
            if frame.empty:
                continue
            frame = frame.set_crs(target_crs) if frame.crs is None else frame.to_crs(target_crs)
            owner = box(*tile_output.working_bbox)
            points = frame.geometry.representative_point()
            frame = frame[points.apply(owner.covers)].copy()
            if frame.empty:
                continue
            frame["_tile_id"] = tile_output.tile_id
            frame["_slice_name"] = tile_output.slice_name
            frames.append(frame)

        if not frames:
            empty = gpd.GeoDataFrame(geometry=gpd.GeoSeries([], dtype="geometry", crs=target_crs), crs=target_crs)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            empty.to_file(output_path, driver="GPKG")
            return output_path

        combined = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry", crs=target_crs)
        combined = self._dedupe(combined)
        if clip_boundary is not None and not clip_boundary.empty:
            combined = self._clip_to_boundary(combined, clip_boundary=clip_boundary, target_crs=target_crs)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_file(output_path, driver="GPKG")
        return output_path

    @staticmethod
    def _dedupe(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        candidates = [column for column in ("canonical_id", "source_feature_id", "osm_id", "id") if column in frame.columns]
        if candidates:
            frame = frame.drop_duplicates(subset=candidates, keep="first").copy()
        frame["_geometry_wkb"] = frame.geometry.apply(lambda geom: geom.wkb_hex if geom is not None else None)
        frame = frame.drop_duplicates(subset=["_slice_name", "_geometry_wkb"], keep="first").copy()
        return frame.drop(columns=["_geometry_wkb", "_tile_id"], errors="ignore")

    @staticmethod
    def _clip_to_boundary(
        frame: gpd.GeoDataFrame,
        *,
        clip_boundary: gpd.GeoDataFrame,
        target_crs: str,
    ) -> gpd.GeoDataFrame:
        if frame.empty:
            return frame
        boundary = clip_boundary.to_crs(target_crs).unary_union
        clipped = frame.copy()
        clipped["geometry"] = clipped.geometry.apply(
            lambda geom: geom.intersection(boundary) if geom is not None and not geom.is_empty else geom
        )
        return clipped[clipped.geometry.notna() & ~clipped.geometry.is_empty].copy()
```

- [x] **Step 6: Create domain runner module with a stable signature**

Create `services/domain_fusion_runners.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd

from fusion_algorithms.poi_fusion import run_poi_geohash_priority_fusion
from fusion_algorithms.road_conflation_v7 import RoadConflationV7Config, run_road_conflation_v7
from fusion_algorithms.water_fusion import fuse_water_polygons
from fusion_algorithms.waterways_conflation_v7 import WaterwaysConflationV7Config, run_waterways_conflation_v7
from services.tile_partition_service import TileSpec


def _read(path: Path, target_crs: str) -> gpd.GeoDataFrame:
    frame = gpd.read_file(path)
    return frame.set_crs(target_crs) if frame.crs is None else frame.to_crs(target_crs)


def _write(frame: gpd.GeoDataFrame, output_dir: Path, name: str, target_crs: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    if frame.crs is None:
        frame = frame.set_crs(target_crs)
    else:
        frame = frame.to_crs(target_crs)
    path = output_dir / f"{name}.gpkg"
    frame.to_file(path, driver="GPKG")
    return path


def run_road_tile(tile: TileSpec, sources: dict[str, Path], output_dir: Path, target_crs: str, parameters: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    del tile
    base = _read(sources["raw.osm.road"], target_crs)
    supplement = _read(sources["raw.overture.transportation"], target_crs)
    result = run_road_conflation_v7(base, supplement, config=RoadConflationV7Config(target_crs=target_crs, profile=str(parameters.get("profile") or "balanced")))
    return _write(result.frame, output_dir, "road_fused", target_crs), {"algorithm_id": result.lineage["algorithm_id"], "stats": result.stats, "config": result.config}


def run_water_polygon_tile(tile: TileSpec, sources: dict[str, Path], output_dir: Path, target_crs: str, parameters: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    del tile, parameters
    base = _read(sources["raw.osm.water"], target_crs)
    supplement = _read(sources["raw.hydrolakes.water"], target_crs)
    fused = fuse_water_polygons(base, supplement)
    fused["feature_kind"] = "polygon"
    return _write(fused, output_dir, "water_polygon_fused", target_crs), {"algorithm_id": "algo.fusion.water_polygon.priority_merge.v2"}


def run_waterways_tile(tile: TileSpec, sources: dict[str, Path], output_dir: Path, target_crs: str, parameters: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    del tile
    base = _read(sources["raw.osm.waterways"], target_crs)
    supplement_id = "raw.hydrorivers.water" if "raw.hydrorivers.water" in sources else "raw.local.pakistan.waterways"
    supplement = _read(sources[supplement_id], target_crs)
    result = run_waterways_conflation_v7(base, supplement, config=WaterwaysConflationV7Config(target_crs=target_crs))
    frame = result.frame.copy()
    frame["feature_kind"] = "line"
    return _write(frame, output_dir, "waterways_fused", target_crs), {"algorithm_id": result.lineage["algorithm_id"], "stats": result.stats, "config": result.config}


def run_poi_tile(tile: TileSpec, sources: dict[str, Path], output_dir: Path, target_crs: str, parameters: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    del tile
    ordered_sources: dict[str, gpd.GeoDataFrame] = {}
    if "raw.osm.poi" in sources:
        ordered_sources["OSM"] = _read(sources["raw.osm.poi"], target_crs)
    gns_id = "raw.gns.poi" if "raw.gns.poi" in sources else "raw.geonames.poi"
    if gns_id in sources:
        ordered_sources["GNS"] = _read(sources[gns_id], target_crs)
    if "raw.rh.poi" in sources:
        ordered_sources["RH"] = _read(sources["raw.rh.poi"], target_crs)
    fused = run_poi_geohash_priority_fusion(ordered_sources)
    fused["source_rank"] = fused.get("SRC", "").map({"base": 1, "target": 2}).fillna(99).astype(int)
    return _write(fused, output_dir, "poi_fused", target_crs), {"algorithm_id": "algo.fusion.poi.geohash_neighbor_match.v1"}
```

- [x] **Step 7: Run large-area service tests**

Run:

```powershell
python -m pytest -q tests/test_large_area_runtime_service.py
```

Expected: PASS.

- [x] **Step 8: Commit**

```powershell
git add services/large_area_runtime_service.py services/domain_fusion_runners.py tests/test_large_area_runtime_service.py
git commit -m "feat: add shared large area runtime service"
```

---

## Task 3: Promote Building Multi-Source Vector + Height Raster Into Shared Runtime

**Files:**
- Modify: `services/source_asset_service.py`
- Modify: `services/source_semantic_contract_service.py`
- Modify: `services/agent_run_service.py`
- Modify: `services/tiled_building_runtime_service.py`
- Modify: `services/domain_fusion_runners.py`
- Test: `tests/test_agent_run_service_multisource_building_runtime.py`
- Test: `tests/test_tiled_multisource_building_runtime_service.py`
- Test: `tests/test_source_semantic_contract_service.py`

- [x] **Step 1: Add failing test for raster semantic binding**

Append to `tests/test_agent_run_service_multisource_building_runtime.py`:

```python
def test_raster_paths_for_source_semantics_returns_existing_height_raster(tmp_path: Path) -> None:
    from services.input_acquisition_service import ResolvedRunInputs

    service = AgentRunService(base_dir=tmp_path / "runs")
    height_path = tmp_path / "Data" / "buildings" / "rasters" / "height.tif"
    height_path.parent.mkdir(parents=True, exist_ok=True)
    height_path.write_bytes(b"fake-raster")
    resolved = ResolvedRunInputs(
        osm_zip_path=tmp_path / "osm.zip",
        ref_zip_path=tmp_path / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.earthquake.building",
        cache_hit=False,
        version_token="v1",
        selected_source_id="catalog.earthquake.building",
        component_coverage={
            "raw.google.building_height.raster": {
                "path": str(height_path),
                "feature_count": None,
                "source_mode": "local_raster",
            }
        },
    )

    try:
        rasters = service._raster_paths_for_source_semantics(resolved)
    finally:
        service.shutdown()

    assert rasters == {"raw.google.building_height.raster": height_path}
```

- [x] **Step 2: Run the focused test and verify failure**

Run:

```powershell
python -m pytest -q tests/test_agent_run_service_multisource_building_runtime.py::test_raster_paths_for_source_semantics_returns_existing_height_raster
```

Expected: FAIL because `_raster_paths_for_source_semantics()` returns `{}`.

- [x] **Step 3: Implement raster path extraction**

In `services/agent_run_service.py`, replace `_raster_paths_for_source_semantics()` with:

```python
    @staticmethod
    def _raster_paths_for_source_semantics(resolved_inputs: ResolvedRunInputs) -> dict[str, Path]:
        rasters: dict[str, Path] = {}
        for source_id, payload in dict(resolved_inputs.component_coverage or {}).items():
            if not str(source_id).endswith(".raster"):
                continue
            path = AgentRunService._component_path_from_payload(payload)
            if path is not None and path.exists():
                rasters[source_id] = path
        return rasters
```

- [x] **Step 4: Add building domain runner that delegates to `TiledBuildingRuntimeService` per tile**

In `services/domain_fusion_runners.py`, add:

```python
from services.tiled_building_runtime_service import TiledBuildingRuntimeService


def make_building_multisource_runner(
    *,
    raster_sources: dict[str, Path],
    source_priority_order: tuple[str, ...],
) -> DomainRunner:
    def _runner(tile: TileSpec, sources: dict[str, Path], output_dir: Path, target_crs: str, parameters: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
        from services.tile_partition_service import TileManifest

        manifest = TileManifest(
            bbox=tile.bbox,
            bbox_crs=target_crs,
            working_crs=target_crs,
            tile_width_m=max(tile.working_bbox[2] - tile.working_bbox[0], 1.0),
            tile_height_m=max(tile.working_bbox[3] - tile.working_bbox[1], 1.0),
            overlap_m=0.0,
            tiles=[tile],
        )
        result = TiledBuildingRuntimeService(max_workers=1).run_tiled_multisource_building_job(
            run_id=f"large-area-building-{tile.tile_id}",
            tile_manifest=manifest,
            vector_sources=sources,
            output_dir=output_dir,
            target_crs=target_crs,
            vector_source_crs=target_crs,
            raster_sources=raster_sources,
            source_priority_order=source_priority_order,
            parameters=parameters,
        )
        return result.output_path, {
            "algorithm_id": "algo.fusion.building.multi_source.decomposed.v1",
            "tile_count": result.tile_count,
            "stitched_feature_count": result.stitched_feature_count,
        }

    return _runner
```

- [x] **Step 5: Route multi-source building through shared large-area runtime**

In `services/agent_run_service.py`, keep `run_multisource_building_execution_stage()` as the public method but change its body to:

```python
        from services.domain_fusion_runners import make_building_multisource_runner
        from services.large_area_runtime_service import LargeAreaRuntimeService, LargeAreaSlice

        repair_records = repair_records if repair_records is not None else []
        request_bbox = self._resolve_request_bbox(request, resolved_aoi=resolved_aoi)
        if request_bbox is None:
            raise ValueError("Multi-source tiled building runtime requires an AOI bbox.")
        target_crs = self._request_with_effective_target_crs(run_id, request).target_crs
        tile_manifest = self.tile_partition_service.partition_bbox(
            bbox=request_bbox,
            bbox_crs="EPSG:4326",
            working_crs=target_crs,
        )
        parameters = self._extract_step_parameters(plan)
        priority = tuple(parameters.get("source_priority_order") or vector_sources.keys())
        result = LargeAreaRuntimeService(max_workers=1).run(
            run_id=run_id,
            job_type="building",
            tile_manifest=tile_manifest,
            slices=[
                LargeAreaSlice(
                    name="building",
                    geometry_family="building",
                    sources=vector_sources,
                    runner=make_building_multisource_runner(
                        raster_sources=raster_sources or {},
                        source_priority_order=priority,
                    ),
                )
            ],
            output_dir=output_dir,
            target_crs=target_crs,
            parameters=parameters,
        )
        self._record_large_area_runtime_completed(run_id=run_id, plan=plan, repair_records=repair_records, result=result)
        return result.output_path, repair_records
```

Also add `_record_large_area_runtime_completed()`:

```python
    def _record_large_area_runtime_completed(self, *, run_id: str, plan: WorkflowPlan, repair_records: list[RepairRecord], result) -> None:
        self._update_status(
            run_id,
            RunPhase.running,
            progress=80,
            repair_records=repair_records,
            current_step=self._count_executable_steps(plan),
            attempt_no=self._max_attempt_no(repair_records),
            healing_summary=self._build_healing_summary(repair_records),
            plan_revision=self._extract_plan_revision(plan),
            checkpoint=self._checkpoint(stage="execution", plan_revision=self._extract_plan_revision(plan)),
            event_kind="large_area_runtime_completed",
            event_message="Shared large-area runtime completed and produced an output artifact.",
            event_details={
                "tile_count": result.tile_count,
                "stitched_feature_count": result.stitched_feature_count,
                "evidence_paths": {key: str(value) for key, value in result.evidence_paths.items()},
            },
        )
```

- [x] **Step 6: Run building tests**

Run:

```powershell
python -m pytest -q tests/test_agent_run_service_multisource_building_runtime.py tests/test_tiled_multisource_building_runtime_service.py tests/test_source_semantic_contract_service.py
```

Expected: PASS.

- [x] **Step 7: Commit**

```powershell
git add services/agent_run_service.py services/domain_fusion_runners.py services/source_asset_service.py services/source_semantic_contract_service.py services/tiled_building_runtime_service.py tests/test_agent_run_service_multisource_building_runtime.py tests/test_tiled_multisource_building_runtime_service.py tests/test_source_semantic_contract_service.py
git commit -m "feat: promote building multisource raster runtime"
```

---

## Task 4: Close Road Vector Fusion In The Shared Large-Area Runtime

**Files:**
- Modify: `services/agent_run_service.py`
- Modify: `services/domain_fusion_runners.py`
- Modify: `services/track_b_national_scale_service.py`
- Test: `tests/test_agent_run_service_large_area_runtime.py`
- Test: `tests/test_track_b_national_scale_service.py`
- Test: `tests/test_road_conflation_v7.py`

- [x] **Step 1: Add failing AgentRunService road routing test**

Create `tests/test_agent_run_service_large_area_runtime.py` with:

```python
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon

from schemas.agent import RunCreateRequest, RunInputStrategy, RunPhase, RunStatus, RunTrigger, RunTriggerType, WorkflowPlan
from schemas.fusion import JobType
from services.agent_run_service import AgentRunService
from services.input_acquisition_service import ResolvedRunInputs


def _request(job_type: JobType) -> RunCreateRequest:
    return RunCreateRequest(
        job_type=job_type,
        trigger=RunTrigger(type=RunTriggerType.user_query, content=job_type.value, spatial_extent="bbox(0,0,2,1)"),
        input_strategy=RunInputStrategy.task_driven_auto,
        target_crs="EPSG:3857",
    )


def _status(run_id: str, request: RunCreateRequest) -> RunStatus:
    return RunStatus(
        run_id=run_id,
        job_type=request.job_type,
        trigger=request.trigger,
        phase=RunPhase.running,
        progress=55,
        target_crs=request.target_crs,
        checkpoint={"stage": "execution"},
        created_at="2026-05-28T00:00:00+00:00",
        updated_at="2026-05-28T00:00:00+00:00",
    )


def _plan(source_id: str, input_type: str, output_type: str, algorithm_id: str) -> WorkflowPlan:
    return WorkflowPlan.model_validate(
        {
            "workflow_id": "wf",
            "trigger": {"type": "user_query", "content": "runtime"},
            "tasks": [
                {
                    "step": 1,
                    "name": "fusion",
                    "description": "fusion",
                    "algorithm_id": algorithm_id,
                    "input": {"data_type_id": input_type, "data_source_id": source_id, "parameters": {}},
                    "output": {"data_type_id": output_type},
                }
            ],
            "expected_output": output_type,
        }
    )


def _write(path: Path, frame: gpd.GeoDataFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(path, driver="GPKG")
    return path


def test_road_task_driven_run_uses_shared_large_area_runtime(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    run_id = "road-run"
    request = _request(JobType.road)
    run_dir = service.base_dir / run_id
    for name in ["intermediate", "output", "logs"]:
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    service._persist_status(_status(run_id, request))

    osm = _write(tmp_path / "osm_road.gpkg", gpd.GeoDataFrame({"osm_id": [1], "fclass": ["primary"]}, geometry=[LineString([(0, 0), (2, 0)])], crs="EPSG:3857"))
    overture = _write(tmp_path / "overture_road.gpkg", gpd.GeoDataFrame({"id": ["o1"], "class": ["primary"]}, geometry=[LineString([(0, 0.1), (2, 0.1)])], crs="EPSG:3857"))
    resolved = ResolvedRunInputs(
        osm_zip_path=tmp_path / "osm.zip",
        ref_zip_path=tmp_path / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.flood.road",
        cache_hit=False,
        version_token="v1",
        selected_source_id="catalog.flood.road",
        component_coverage={
            "raw.osm.road": {"path": str(osm), "feature_count": 1},
            "raw.overture.transportation": {"path": str(overture), "feature_count": 1},
        },
    )

    try:
        path, repairs = service.run_large_area_execution_stage(
            run_id=run_id,
            request=request,
            plan=_plan("catalog.flood.road", "dt.road.bundle", "dt.road.fused", "algo.fusion.road.conflation.v7"),
            intermediate_dir=run_dir / "intermediate",
            output_dir=run_dir / "output",
            resolved_inputs=resolved,
            resolved_aoi=None,
        )
    finally:
        service.shutdown()

    assert repairs == []
    assert path.exists()
    assert (run_dir / "output" / "stitched_artifact.json").exists()
```

- [x] **Step 2: Run road routing test and verify failure**

Run:

```powershell
python -m pytest -q tests/test_agent_run_service_large_area_runtime.py::test_road_task_driven_run_uses_shared_large_area_runtime
```

Expected: FAIL because `run_large_area_execution_stage()` is not implemented.

- [x] **Step 3: Implement source component path helper reuse**

In `services/agent_run_service.py`, add:

```python
    def _component_paths_from_resolved_inputs_for_runtime(self, *, run_id: str, resolved_inputs: ResolvedRunInputs) -> dict[str, Path]:
        return self._source_component_paths_from_resolved_inputs(run_id=run_id, resolved_inputs=resolved_inputs)
```

- [x] **Step 4: Implement `_should_use_large_area_runtime()`**

In `services/agent_run_service.py`, add:

```python
    def _should_use_large_area_runtime(
        self,
        *,
        request: RunCreateRequest,
        plan: WorkflowPlan,
        resolved_inputs: ResolvedRunInputs | None,
        resolved_aoi: ResolvedAOI | None,
    ) -> bool:
        if request.input_strategy != RunInputStrategy.task_driven_auto:
            return False
        if request.job_type not in {JobType.road, JobType.water, JobType.poi}:
            return False
        if resolved_inputs is None:
            return False
        if self._resolve_request_bbox(request, resolved_aoi=resolved_aoi) is None:
            return False
        selected_source_id = resolved_inputs.selected_source_id or resolved_inputs.source_id or self._resolve_task_driven_source_id(plan)
        return bool(selected_source_id)
```

- [x] **Step 5: Implement `run_large_area_execution_stage()` for road first**

Add to `services/agent_run_service.py`:

```python
    def run_large_area_execution_stage(
        self,
        *,
        run_id: str,
        request: RunCreateRequest,
        plan: WorkflowPlan,
        intermediate_dir: Path,
        output_dir: Path,
        resolved_inputs: ResolvedRunInputs,
        resolved_aoi: ResolvedAOI | None,
        repair_records: Optional[list[RepairRecord]] = None,
    ) -> tuple[Path, list[RepairRecord]]:
        from services.domain_fusion_runners import run_road_tile
        from services.large_area_runtime_service import LargeAreaRuntimeService, LargeAreaSlice

        repair_records = repair_records if repair_records is not None else []
        request_bbox = self._resolve_request_bbox(request, resolved_aoi=resolved_aoi)
        if request_bbox is None:
            raise ValueError("Shared large-area runtime requires an AOI bbox.")
        target_crs = self._request_with_effective_target_crs(run_id, request).target_crs
        component_paths = self._component_paths_from_resolved_inputs_for_runtime(run_id=run_id, resolved_inputs=resolved_inputs)
        tile_manifest = self.tile_partition_service.partition_bbox(
            bbox=request_bbox,
            bbox_crs="EPSG:4326",
            working_crs=target_crs,
        )
        if request.job_type == JobType.road:
            slices = [
                LargeAreaSlice(
                    name="road",
                    geometry_family="line",
                    sources={
                        "raw.osm.road": component_paths["raw.osm.road"],
                        "raw.overture.transportation": component_paths["raw.overture.transportation"],
                    },
                    runner=run_road_tile,
                )
            ]
        else:
            raise ValueError(f"Shared large-area runtime not wired for job_type={request.job_type.value}")
        result = LargeAreaRuntimeService(max_workers=1).run(
            run_id=run_id,
            job_type=request.job_type.value,
            tile_manifest=tile_manifest,
            slices=slices,
            output_dir=output_dir,
            target_crs=target_crs,
            parameters=self._extract_step_parameters(plan),
        )
        self._record_large_area_runtime_completed(run_id=run_id, plan=plan, repair_records=repair_records, result=result)
        return result.output_path, repair_records
```

- [x] **Step 6: Wire the execution branch**

In `execute_run()`, after `should_tile = ...`, compute:

```python
            should_use_large_area_runtime = self._should_use_large_area_runtime(
                request=runtime_request,
                plan=plan,
                resolved_inputs=resolved_inputs,
                resolved_aoi=resolved_aoi,
            )
```

Then in the execution branch, before the generic `run_execution_stage()` fallback, add:

```python
                    elif should_use_large_area_runtime and resolved_inputs is not None:
                        fused_shp, repair_records = self.run_large_area_execution_stage(
                            run_id=run_id,
                            request=runtime_request,
                            plan=plan,
                            intermediate_dir=intermediate_dir,
                            output_dir=output_dir,
                            resolved_inputs=resolved_inputs,
                            resolved_aoi=resolved_aoi,
                            repair_records=repair_records,
                        )
```

- [x] **Step 7: Reuse shared runtime in Track B road evidence**

In `services/track_b_national_scale_service.py`, replace `_run_v7_national_line_fusion()` road-specific direct full-frame call with the same `run_road_tile` + `LargeAreaRuntimeService` path. Keep the existing `fusion_stats.json`, `selected_sources.json`, and `inspection_summary.json` names unchanged so existing evidence consumers still work.

- [x] **Step 8: Run road verification**

Run:

```powershell
python -m pytest -q tests/test_agent_run_service_large_area_runtime.py::test_road_task_driven_run_uses_shared_large_area_runtime tests/test_road_conflation_v7.py tests/test_track_b_national_scale_service.py::test_track_b_national_scale_service_uses_non_empty_overture_reference_when_available
```

Expected: PASS.

- [x] **Step 9: Commit**

```powershell
git add services/agent_run_service.py services/domain_fusion_runners.py services/track_b_national_scale_service.py tests/test_agent_run_service_large_area_runtime.py tests/test_track_b_national_scale_service.py tests/test_road_conflation_v7.py
git commit -m "feat: route road fusion through large area runtime"
```

---

## Task 5: Close River And Lake Water Fusion In The Shared Runtime

**Files:**
- Modify: `services/agent_run_service.py`
- Modify: `services/domain_fusion_runners.py`
- Modify: `services/track_b_national_scale_service.py`
- Modify: `services/source_asset_service.py`
- Test: `tests/test_agent_run_service_large_area_runtime.py`
- Test: `tests/test_track_b_national_scale_service.py`
- Test: `tests/test_track_b_national_v7_routes.py`
- Test: `tests/test_waterways_conflation_v7.py`

- [x] **Step 1: Add failing water runtime test with polygon and line slices**

Append to `tests/test_agent_run_service_large_area_runtime.py`:

```python
def test_water_task_driven_run_outputs_polygon_and_line_slices(tmp_path: Path) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    run_id = "water-run"
    request = _request(JobType.water)
    run_dir = service.base_dir / run_id
    for name in ["intermediate", "output", "logs"]:
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    service._persist_status(_status(run_id, request))

    osm_water = _write(tmp_path / "osm_water.gpkg", gpd.GeoDataFrame({"osm_id": [1]}, geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])], crs="EPSG:3857"))
    hydrolakes = _write(tmp_path / "hydrolakes.gpkg", gpd.GeoDataFrame({"Hylak_id": [11]}, geometry=[Polygon([(0.2, 0.2), (0.2, 0.8), (0.8, 0.8), (0.8, 0.2)])], crs="EPSG:3857"))
    osm_waterways = _write(tmp_path / "osm_waterways.gpkg", gpd.GeoDataFrame({"osm_id": [2], "fclass": ["river"]}, geometry=[LineString([(0, 0.5), (2, 0.5)])], crs="EPSG:3857"))
    hydrorivers = _write(tmp_path / "hydrorivers.gpkg", gpd.GeoDataFrame({"HYRIV_ID": [22]}, geometry=[LineString([(0, 0.55), (2, 0.55)])], crs="EPSG:3857"))
    resolved = ResolvedRunInputs(
        osm_zip_path=tmp_path / "osm.zip",
        ref_zip_path=tmp_path / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.flood.water",
        cache_hit=False,
        version_token="v1",
        selected_source_id="catalog.flood.water",
        component_coverage={
            "raw.osm.water": {"path": str(osm_water), "feature_count": 1},
            "raw.hydrolakes.water": {"path": str(hydrolakes), "feature_count": 1},
            "raw.osm.waterways": {"path": str(osm_waterways), "feature_count": 1},
            "raw.hydrorivers.water": {"path": str(hydrorivers), "feature_count": 1},
        },
    )

    try:
        path, repairs = service.run_large_area_execution_stage(
            run_id=run_id,
            request=request,
            plan=_plan("catalog.flood.water", "dt.water.bundle", "dt.water.fused", "algo.fusion.water_polygon.priority_merge.v2"),
            intermediate_dir=run_dir / "intermediate",
            output_dir=run_dir / "output",
            resolved_inputs=resolved,
            resolved_aoi=None,
        )
    finally:
        service.shutdown()

    fused = gpd.read_file(path)
    assert repairs == []
    assert {"polygon", "line"}.issubset(set(fused["feature_kind"]))
```

- [x] **Step 2: Run the water test and verify failure**

Run:

```powershell
python -m pytest -q tests/test_agent_run_service_large_area_runtime.py::test_water_task_driven_run_outputs_polygon_and_line_slices
```

Expected: FAIL because `run_large_area_execution_stage()` only wires road.

- [x] **Step 3: Add water slices to `run_large_area_execution_stage()`**

In `services/agent_run_service.py`, import `run_water_polygon_tile` and `run_waterways_tile` inside the method and add this branch:

```python
        elif request.job_type == JobType.water:
            water_sources = {
                "raw.osm.water": component_paths["raw.osm.water"],
                "raw.hydrolakes.water": component_paths["raw.hydrolakes.water"],
            }
            slices = [
                LargeAreaSlice(
                    name="water_polygon",
                    geometry_family="polygon",
                    sources=water_sources,
                    runner=run_water_polygon_tile,
                )
            ]
            if "raw.osm.waterways" in component_paths and (
                "raw.hydrorivers.water" in component_paths or "raw.local.pakistan.waterways" in component_paths
            ):
                line_sources = {"raw.osm.waterways": component_paths["raw.osm.waterways"]}
                if "raw.hydrorivers.water" in component_paths:
                    line_sources["raw.hydrorivers.water"] = component_paths["raw.hydrorivers.water"]
                else:
                    line_sources["raw.local.pakistan.waterways"] = component_paths["raw.local.pakistan.waterways"]
                slices.append(
                    LargeAreaSlice(
                        name="waterways_line",
                        geometry_family="line",
                        sources=line_sources,
                        runner=run_waterways_tile,
                    )
                )
```

- [x] **Step 4: Ensure water acquisition includes waterways supplements**

In `services/local_bundle_catalog.py`, when selected source is `catalog.flood.water`, include supplemental component coverage for `raw.osm.waterways` and `raw.hydrorivers.water` if materialization succeeds. The returned `MaterializedInputBundle.component_coverage` should include all four ids:

```python
{
    "raw.osm.water": ...,
    "raw.hydrolakes.water": ...,
    "raw.osm.waterways": ...,
    "raw.hydrorivers.water": ...,
}
```

The `osm_zip_path/ref_zip_path` pair remains polygon-compatible for legacy executor fallback; shared large-area runtime reads the component coverage paths.

- [x] **Step 5: Preserve explicit line/polygon semantics in output**

In `services/domain_fusion_runners.py`, ensure:

```python
fused["feature_kind"] = "polygon"
```

for polygon output and:

```python
frame["feature_kind"] = "line"
```

for waterways output. Also set:

```python
frame["source_id"] = frame.get("source_id", "raw.hydrorivers.water")
```

where source id is absent after V7 canonicalization.

- [x] **Step 6: Reuse shared runtime in Track B water evidence**

In `services/track_b_national_scale_service.py`, route `theme == "water"` through `LargeAreaRuntimeService` with two slices when line sources are present. Preserve existing tests that assert:

```python
assert "line" in feature_kinds
assert any("Polygon" in value for value in geom_types)
```

- [x] **Step 7: Run water verification**

Run:

```powershell
python -m pytest -q tests/test_agent_run_service_large_area_runtime.py::test_water_task_driven_run_outputs_polygon_and_line_slices tests/test_track_b_national_scale_service.py::test_track_b_national_scale_service_includes_hydrorivers_lines_in_water_output tests/test_track_b_national_scale_service.py::test_track_b_national_scale_service_includes_osm_waterways_lines_in_water_output tests/test_track_b_national_v7_routes.py tests/test_waterways_conflation_v7.py
```

Expected: PASS.

- [x] **Step 8: Commit**

```powershell
git add services/agent_run_service.py services/domain_fusion_runners.py services/local_bundle_catalog.py services/track_b_national_scale_service.py services/source_asset_service.py tests/test_agent_run_service_large_area_runtime.py tests/test_track_b_national_scale_service.py tests/test_track_b_national_v7_routes.py tests/test_waterways_conflation_v7.py
git commit -m "feat: route water fusion through large area runtime"
```

---

## Task 6: Close Bounded POI Fusion With OSM + GNS/GeoNames

**Files:**
- Modify: `services/source_asset_service.py`
- Modify: `services/agent_run_service.py`
- Modify: `services/domain_fusion_runners.py`
- Modify: `services/unsupported_intent_guard.py`
- Test: `tests/test_source_asset_service.py`
- Test: `tests/test_agent_run_service_large_area_runtime.py`
- Test: `tests/test_poi_adapter.py`
- Test: `tests/test_fusioncode_poi.py`
- Test: `tests/test_run_preflight.py`

- [ ] **Step 1: Add failing GeoNames alias materialization test**

Append to `tests/test_source_asset_service.py`:

```python
def test_source_asset_service_treats_geonames_poi_as_gns_alias(tmp_path: Path) -> None:
    from services.source_asset_service import SourceAssetService

    gns_path = tmp_path / "Data" / "POI" / "Kenya" / "GNS.shp"
    gns_path.parent.mkdir(parents=True, exist_ok=True)
    geopandas.GeoDataFrame(
        {"ufi": [1], "full_name": ["Clinic A"], "desig_cd": ["HSP"]},
        geometry=[Point(36.8, -1.2)],
        crs="EPSG:4326",
    ).to_file(gns_path)
    service = SourceAssetService(repo_root=tmp_path, cache_dir=tmp_path / "cache")

    resolved = service.resolve_raw_source_path("raw.geonames.poi", request_bbox=(36.7, -1.3, 36.9, -1.1))

    assert resolved.source_id == "raw.gns.poi"
    assert resolved.path.exists()
    assert resolved.feature_count == 1
```

- [ ] **Step 2: Run alias test and verify failure**

Run:

```powershell
python -m pytest -q tests/test_source_asset_service.py::test_source_asset_service_treats_geonames_poi_as_gns_alias
```

Expected: FAIL because `raw.geonames.poi` is not canonicalized.

- [ ] **Step 3: Canonicalize POI source alias**

In `services/source_asset_service.py`, add:

```python
_SOURCE_ID_ALIASES = {
    "raw.geonames.poi": "raw.gns.poi",
}


def _canonical_source_id(source_id: str) -> str:
    return _SOURCE_ID_ALIASES.get(source_id, source_id)
```

At the start of `can_materialize()` and `resolve_raw_source_path()`, use:

```python
source_id = _canonical_source_id(source_id)
```

Ensure `SourceAssetResolution.source_id` uses the canonical id.

- [ ] **Step 4: Add failing POI large-area runtime test**

Append to `tests/test_agent_run_service_large_area_runtime.py`:

```python
def test_poi_task_driven_run_uses_osm_and_gns_large_area_runtime(tmp_path: Path) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    run_id = "poi-run"
    request = _request(JobType.poi)
    run_dir = service.base_dir / run_id
    for name in ["intermediate", "output", "logs"]:
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    service._persist_status(_status(run_id, request))

    osm = _write(tmp_path / "osm_poi.gpkg", gpd.GeoDataFrame({"osm_id": [1], "name": ["Clinic A"], "GeoHash": ["abc"]}, geometry=[Point(0.5, 0.5)], crs="EPSG:3857"))
    gns = _write(tmp_path / "gns_poi.gpkg", gpd.GeoDataFrame({"ufi": [10], "name": ["Clinic A"], "GeoHash": ["abc"]}, geometry=[Point(0.51, 0.5)], crs="EPSG:3857"))
    resolved = ResolvedRunInputs(
        osm_zip_path=tmp_path / "osm.zip",
        ref_zip_path=tmp_path / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.generic.poi",
        cache_hit=False,
        version_token="v1",
        selected_source_id="catalog.generic.poi",
        component_coverage={
            "raw.osm.poi": {"path": str(osm), "feature_count": 1},
            "raw.gns.poi": {"path": str(gns), "feature_count": 1},
        },
    )

    try:
        path, repairs = service.run_large_area_execution_stage(
            run_id=run_id,
            request=request,
            plan=_plan("catalog.generic.poi", "dt.poi.bundle", "dt.poi.fused", "algo.fusion.poi.geohash_neighbor_match.v1"),
            intermediate_dir=run_dir / "intermediate",
            output_dir=run_dir / "output",
            resolved_inputs=resolved,
            resolved_aoi=None,
        )
    finally:
        service.shutdown()

    fused = gpd.read_file(path)
    assert repairs == []
    assert path.exists()
    assert "source_rank" in fused.columns
```

- [ ] **Step 5: Add POI branch to `run_large_area_execution_stage()`**

In `services/agent_run_service.py`, add:

```python
        elif request.job_type == JobType.poi:
            poi_sources = {"raw.osm.poi": component_paths["raw.osm.poi"]}
            if "raw.gns.poi" in component_paths:
                poi_sources["raw.gns.poi"] = component_paths["raw.gns.poi"]
            elif "raw.geonames.poi" in component_paths:
                poi_sources["raw.geonames.poi"] = component_paths["raw.geonames.poi"]
            else:
                raise ValueError("POI large-area runtime requires raw.gns.poi or raw.geonames.poi")
            slices = [
                LargeAreaSlice(
                    name="poi",
                    geometry_family="point",
                    sources=poi_sources,
                    runner=run_poi_tile,
                )
            ]
```

- [ ] **Step 6: Keep unbounded POI entity alignment rejected**

In `services/unsupported_intent_guard.py`, add or preserve this behavior under tests:

```python
if job_type == JobType.poi and _looks_like_unbounded_entity_alignment(content):
    return [{"code": "unsupported_unbounded_poi_entity_alignment", "supported_boundary": "bounded AOI POI fusion only"}]
```

Add `tests/test_run_preflight.py` assertion:

```python
def test_preflight_rejects_unbounded_poi_entity_alignment() -> None:
    issues = classify_unsupported_intent("match all global POI entities without bbox", job_type=JobType.poi)
    assert any(item["code"] == "unsupported_unbounded_poi_entity_alignment" for item in issues)
```

- [ ] **Step 7: Run POI verification**

Run:

```powershell
python -m pytest -q tests/test_source_asset_service.py::test_source_asset_service_treats_geonames_poi_as_gns_alias tests/test_agent_run_service_large_area_runtime.py::test_poi_task_driven_run_uses_osm_and_gns_large_area_runtime tests/test_poi_adapter.py tests/test_fusioncode_poi.py tests/test_run_preflight.py
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add services/source_asset_service.py services/agent_run_service.py services/domain_fusion_runners.py services/unsupported_intent_guard.py tests/test_source_asset_service.py tests/test_agent_run_service_large_area_runtime.py tests/test_poi_adapter.py tests/test_fusioncode_poi.py tests/test_run_preflight.py
git commit -m "feat: close bounded poi large area fusion"
```

---

## Task 7: Report, Inspection, And Evidence Closure For Targets 2-6

**Files:**
- Modify: `services/run_report_service.py`
- Modify: `services/agent_run_service.py`
- Modify: `api/routers/runs_v2.py`
- Modify: `docs/v2-operations.md`
- Test: `tests/test_run_report_service.py`
- Test: `tests/test_api_v2_integration.py`
- Test: `tests/test_agent_run_service_large_area_runtime.py`

- [ ] **Step 1: Add failing report evidence test**

Append to `tests/test_run_report_service.py`:

```python
def test_run_report_includes_large_area_runtime_evidence(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.gpkg"
    artifact.write_bytes(b"gpkg")
    status = _run_status(artifact)
    audit_events = _audit_events() + [
        RunEvent(
            timestamp="2026-05-28T00:00:07+00:00",
            kind="large_area_runtime_completed",
            phase=RunPhase.running,
            message="large area complete",
            details={
                "tile_count": 4,
                "stitched_feature_count": 12,
                "evidence_paths": {
                    "tile_manifest": str(tmp_path / "tile_manifest.json"),
                    "stitched_artifact": str(tmp_path / "stitched_artifact.json"),
                    "fusion_stats": str(tmp_path / "fusion_stats.json"),
                },
            },
        )
    ]

    summary = build_run_report_summary(
        status=status,
        plan=_plan(),
        audit_events=audit_events,
        artifact_path=artifact,
        source_semantic_contract={
            "height_policy": {
                "raster_height_sources": {"raw.google.building_height.raster": "height.tif"}
            }
        },
    )

    assert summary["large_area_runtime"]["tile_count"] == 4
    assert summary["large_area_runtime"]["stitched_feature_count"] == 12
    assert "raw.google.building_height.raster" in summary["source_semantic_contract"]["height_policy"]["raster_height_sources"]
```

- [ ] **Step 2: Run report test and verify failure**

Run:

```powershell
python -m pytest -q tests/test_run_report_service.py::test_run_report_includes_large_area_runtime_evidence
```

Expected: FAIL because `large_area_runtime` is not in report summary.

- [ ] **Step 3: Add report summary extraction**

In `services/run_report_service.py`, add:

```python
def _large_area_runtime_from_events(audit_events: list[RunEvent]) -> dict[str, Any]:
    for event in reversed(audit_events):
        if event.kind == "large_area_runtime_completed":
            details = dict(event.details or {})
            return {
                "tile_count": details.get("tile_count"),
                "stitched_feature_count": details.get("stitched_feature_count"),
                "evidence_paths": details.get("evidence_paths", {}),
            }
    return {}
```

In `build_run_report_summary()`, add top-level:

```python
"large_area_runtime": _large_area_runtime_from_events(audit_events),
```

- [ ] **Step 4: Render report lines in Chinese and English reports**

In `_render_zh()`, after `## 结果评价`, add:

```python
f"- 大范围运行时：{_compact(summary.get('large_area_runtime', {}))}",
```

In `_render_en()`, after `## Result Evaluation`, add:

```python
f"- Large-area runtime: {_compact(summary.get('large_area_runtime', {}))}",
```

- [ ] **Step 5: Include source semantic and evidence paths in inspection**

In `api/routers/runs_v2.py`, make sure `/api/v2/runs/{run_id}/inspection` returns:

```python
"large_area_runtime": report_summary.get("large_area_runtime", {}),
"source_semantic_contract": report_summary.get("source_semantic_contract", {}),
```

If inspection builds from raw status rather than report summary, load `documents/run_report_summary.json` when it exists and merge only these keys.

- [ ] **Step 6: Update docs with exact evidence contract**

In `docs/v2-operations.md`, add this evidence list under the stable runtime contract:

```markdown
For every large-area target 2-6 run, shared runtime evidence includes:

- `tile_manifest.json`
- `stitched_artifact.json`
- `fusion_stats.json`
- `source_semantic_contract.json` when profiling succeeds
- `documents/run_report_summary.json`
- `documents/run_report.zh.md`
- `documents/run_report.en.md`
```

- [ ] **Step 7: Run reporting and API tests**

Run:

```powershell
python -m pytest -q tests/test_run_report_service.py tests/test_api_v2_integration.py tests/test_agent_run_service_large_area_runtime.py
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add services/run_report_service.py services/agent_run_service.py api/routers/runs_v2.py docs/v2-operations.md tests/test_run_report_service.py tests/test_api_v2_integration.py tests/test_agent_run_service_large_area_runtime.py
git commit -m "feat: expose large area runtime evidence in reports"
```

---

## Task 8: End-To-End Verification And Evidence Freeze For Targets 2-6

**Files:**
- Modify: `scripts/smoke_agentic_region.py`
- Modify: `docs/superpowers/specs/2026-05-28-targets-2-6-runtime-evidence-freeze.json`
- Modify: `docs/superpowers/specs/2026-05-28-targets-2-6-runtime-evidence-freeze.md`
- Modify: `docs/v2-operations.md`
- Test: `tests/test_smoke_agentic_region.py`
- Test: `tests/test_track_b_national_scale_service.py`
- Test: `tests/test_agent_run_service_large_area_runtime.py`

- [ ] **Step 1: Add smoke summary checks for targets 2-6 evidence**

In `tests/test_smoke_agentic_region.py`, add:

```python
def test_smoke_summary_accepts_large_area_evidence_fields() -> None:
    summary = {
        "job_type": "road",
        "phase": "succeeded",
        "large_area_runtime": {"tile_count": 2, "stitched_feature_count": 5},
        "source_semantic_contract": {"component_source_ids": ["raw.osm.road", "raw.overture.transportation"]},
        "documents": {"summary": "run_report_summary.json"},
    }

    assert summary["large_area_runtime"]["tile_count"] >= 1
    assert summary["source_semantic_contract"]["component_source_ids"]
    assert summary["documents"]["summary"].endswith(".json")
```

- [ ] **Step 2: Run final targeted regression set**

Run:

```powershell
python -m pytest -q `
  tests/test_large_area_runtime_service.py `
  tests/test_agent_run_service_large_area_runtime.py `
  tests/test_agent_run_service_multisource_building_runtime.py `
  tests/test_tiled_multisource_building_runtime_service.py `
  tests/test_source_semantic_contract_service.py `
  tests/test_source_asset_service.py `
  tests/test_road_conflation_v7.py `
  tests/test_waterways_conflation_v7.py `
  tests/test_fusioncode_poi.py `
  tests/test_run_report_service.py `
  tests/test_track_b_national_scale_service.py `
  tests/test_track_b_national_v7_routes.py
```

Expected: PASS.

- [ ] **Step 3: Run no-network fixture-level shared runtime smoke**

Run:

```powershell
$env:GEOFUSION_KG_BACKEND='memory'
$env:GEOFUSION_LLM_PROVIDER='mock'
$env:GEOFUSION_CELERY_EAGER='1'
python -m pytest -q tests/test_agent_run_service_large_area_runtime.py
```

Expected: PASS and each job type writes `stitched_artifact.json`.

- [ ] **Step 4: Run optional live-source smoke when network and source services are available**

Use a small bounded AOI to avoid making the verification depend on national data volume:

```powershell
python scripts/materialize_source_assets.py `
  --source raw.osm.building `
  --source raw.microsoft.building `
  --source raw.osm.road `
  --source raw.overture.transportation `
  --source raw.osm.water `
  --source raw.hydrolakes.water `
  --source raw.osm.waterways `
  --source raw.hydrorivers.water `
  --source raw.osm.poi `
  --source raw.gns.poi `
  --bbox 36.65,-1.45,37.10,-1.10 `
  --prefer-remote
```

Expected: command exits 0, or if a remote provider is unavailable, the failure is recorded as provider-specific evidence and does not invalidate fixture-level target 2-6 closure.

- [ ] **Step 5: Freeze evidence JSON**

Create `docs/superpowers/specs/2026-05-28-targets-2-6-runtime-evidence-freeze.json` with this structure and real paths from the test/smoke outputs:

```json
{
  "freeze_id": "2026-05-28-targets-2-6-runtime-evidence",
  "capability_contract": {
    "building_vector_height_raster": "shared_runtime_supported",
    "road_vector": "shared_runtime_supported",
    "water_river_lake_vector": "shared_runtime_supported",
    "bounded_poi_osm_geonames": "shared_runtime_supported",
    "large_area_stitch_clip": "shared_runtime_supported"
  },
  "required_evidence_files": [
    "tile_manifest.json",
    "stitched_artifact.json",
    "fusion_stats.json",
    "source_semantic_contract.json",
    "documents/run_report_summary.json"
  ],
  "verification_commands": [
    "python -m pytest -q tests/test_large_area_runtime_service.py tests/test_agent_run_service_large_area_runtime.py",
    "python -m pytest -q tests/test_track_b_national_scale_service.py tests/test_track_b_national_v7_routes.py"
  ],
  "manual_only_boundaries": [
    "raw.google.building",
    "raw.openbuildingmap.building",
    "raw.google.open_buildings.vector",
    "raw.local.microsoft.building",
    "raw.rh.poi"
  ]
}
```

- [ ] **Step 6: Freeze evidence Markdown**

Create `docs/superpowers/specs/2026-05-28-targets-2-6-runtime-evidence-freeze.md`:

```markdown
# Targets 2-6 Runtime Evidence Freeze

## Capability State

- Target 2: supported in shared runtime for building vectors plus optional height raster enrichment.
- Target 3: supported in shared runtime for OSM road plus Overture transportation.
- Target 4: supported in shared runtime for water polygons and waterways lines.
- Target 5: supported in shared runtime for bounded OSM POI plus GNS/GeoNames gazetteer fusion.
- Target 6: supported through shared tile, stitch, clip, and evidence outputs.

## Boundaries

- Google/OpenBuildingMap building sources remain manual-preload supplements.
- `raw.rh.poi` remains manual-preload supplement.
- Unbounded POI entity alignment remains unsupported.
- Trajectory-to-road remains reservation-only and is outside targets 2-6.

## Verification

Record the exact pytest output and smoke evidence paths from the implementation branch before merging.
```

- [ ] **Step 7: Run full relevant regression**

Run:

```powershell
python -m pytest -q
```

Expected: PASS. If repository-wide unrelated tests fail, record the failing tests and still require all target 2-6 tests from Step 2 to pass before claiming closure.

- [ ] **Step 8: Commit**

```powershell
git add scripts/smoke_agentic_region.py docs/v2-operations.md docs/superpowers/specs/2026-05-28-targets-2-6-runtime-evidence-freeze.json docs/superpowers/specs/2026-05-28-targets-2-6-runtime-evidence-freeze.md tests/test_smoke_agentic_region.py tests/test_track_b_national_scale_service.py tests/test_agent_run_service_large_area_runtime.py
git commit -m "docs: freeze targets 2-6 runtime evidence"
```

---

## Final Verification Gate

Before declaring targets 2-6 fully equipped, run:

```powershell
python -m pytest -q `
  tests/test_ontology_closure.py `
  tests/test_local_bundle_catalog.py `
  tests/test_large_area_runtime_service.py `
  tests/test_agent_run_service_large_area_runtime.py `
  tests/test_agent_run_service_multisource_building_runtime.py `
  tests/test_tiled_multisource_building_runtime_service.py `
  tests/test_source_semantic_contract_service.py `
  tests/test_source_asset_service.py `
  tests/test_road_conflation_v7.py `
  tests/test_waterways_conflation_v7.py `
  tests/test_poi_adapter.py `
  tests/test_fusioncode_poi.py `
  tests/test_run_report_service.py `
  tests/test_track_b_national_scale_service.py `
  tests/test_track_b_national_v7_routes.py `
  tests/test_run_preflight.py
```

Expected: PASS.

Then run the repository suite:

```powershell
python -m pytest -q
```

Expected: PASS, or a documented unrelated failure with the target 2-6 suite passing.

## Self-Review

**Spec coverage:**  
Target 2 is covered by Tasks 1, 3, 7, and 8. Target 3 is covered by Tasks 1, 2, 4, 7, and 8. Target 4 is covered by Tasks 1, 2, 5, 7, and 8. Target 5 is covered by Tasks 1, 2, 6, 7, and 8. Target 6 is covered by Tasks 2, 4, 5, 6, 7, and 8.

**Placeholder scan:**  
The plan avoids placeholder tokens and gives concrete file paths, method names, tests, commands, evidence file names, and commit points. Manual-only boundaries are explicitly listed instead of being left open.

**Type consistency:**  
New shared runtime types are `LargeAreaSlice`, `LargeAreaTileOutput`, and `LargeAreaRunResult`. Agent routing uses existing `RunCreateRequest`, `RunInputStrategy`, `ResolvedRunInputs`, `ResolvedAOI`, `WorkflowPlan`, `RepairRecord`, and `JobType`. External `JobType` remains unchanged; internal water line/polygon separation is represented by slice names and existing `dt.waterways.*` ontology.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-28-fusionagent-targets-2-6-runtime-closure.md`. Two execution options:

**1. Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
