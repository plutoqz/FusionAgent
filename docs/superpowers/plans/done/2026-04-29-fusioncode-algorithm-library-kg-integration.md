# FusionCode Algorithm Library KG Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status Note:** Deferred to Conditional Phase 6 by `docs/superpowers/plans/2026-05-12-fusionagent-master-execution-plan.md`. Do not treat the unchecked boxes below as current active backlog unless the master plan explicitly reopens this expansion track.

**Goal:** 将 `E:\vscode\fusioncode` 的完整矢量融合能力纳入 `E:\vscode\fusionAgent` 的算法库和知识图谱，使智能体能按 KG 节点选择、组合、调参和执行多源融合、建筑物存在性栅格验证、建筑物高度栅格提取、道路/水系/湖泊/POI 融合与质量评估。

**Architecture:** 不把 `fusioncode.algorithm_adapter.run_full_pipeline()` 作为 KG 中的单一黑盒算法。新建 `fusion_algorithms/` 作为可组合算法原语层，每个原语都有输入/输出数据类型、参数规格、执行处理器和测试；`run_full_pipeline()` 只作为迁移期的端到端行为对照。KG 中保存算法节点、参数节点和工作流模式，执行器按 KG 任务链调度原语。

**Tech Stack:** Python, GeoPandas, Shapely, Rasterio, NetworkX, SciPy, joblib, Pydantic, pytest, `fusionAgent` KG repository/validator/executor, `fusioncode` algorithm modules.

---

## Scope And Non-Negotiables

- 本计划只写方案，获得用户审查同意前不修改运行时代码。
- 完整纳入 `fusioncode` 功能范围：
  - 建筑：多源源集解析、OBM 属性增强、Presence 栅格存在性验证、V8 候选图、V8 连通分量求解、级联几何优先融合、道路拓扑优化、冲突图优化、后冲突收缩、道路尾部冲突细调、Height 栅格高度提取、质量指标。
  - 道路：尖角切分、缓冲/Hausdorff/角度匹配、融合、去重、端点吸附、拓扑清理。
  - 水系线：河流/水线三源融合、尖角切分、Hausdorff/缓冲匹配、来源保留。
  - 水域面：湖泊/水面多边形重叠匹配、优先级合并。
  - POI：GeoHash 邻域匹配、名称/来源优先级合并、剩余点输出。
  - 冲突/质量：空间冲突检测、建筑优化前后指标、可审计 lineage。
- 必须做算法拆分和参数解耦：
  - KG 不存一个“大函数”，而存可组合算法原语。
  - 每个关键阈值、权重、开关、字段别名和输出字段策略进入 `AlgorithmParameterSpec`。
  - 工作流模式使用多个 `PatternStep` 串接，允许智能体跳过可选步骤或替换安全策略。
- 现有未跟踪文件 `E:\vscode\fusionAgent\runs\benin-source-profile.json` 与本计划无关，执行时不得修改或删除。

## Source Inventory Locked By This Plan

| Capability | FusionCode Source | Important Entry Points |
| --- | --- | --- |
| Building full script | `E:\vscode\fusioncode\algorithm_core\main.py` | imports and sequences raster validation, V8 fusion, optimization, height extraction |
| Building adapter | `E:\vscode\fusioncode\algorithm_adapter.py` | `_parse_geometry_source_paths()`, `run_full_pipeline()` |
| Building V8 matching | `E:\vscode\fusioncode\algorithm_core\models\matching_engine.py` | `MatchConfig`, `generate_candidate_edges_v8()`, `process_worker_v8()`, `build_fusion_rows()`, `execute_v8_fusion()` |
| Building raster | `E:\vscode\fusioncode\algorithm_core\models\temporal_validator.py` | `validate_existence_parallel()`, `extract_height_parallel()` |
| Building optimization | `E:\vscode\fusioncode\algorithm_core\models\spatial_optimizer.py` | `OptConfig`, `optimize_road_topology()`, `build_constraint_graph()`, `run_graph_optimization_v5()`, `calculate_metrics()` |
| Building refiners | `E:\vscode\fusioncode\algorithm_core\models\post_conflict_shrink_refiner.py`, `z1r3_conflict.py`, `obm_enricher.py`, `quality_assessor.py` | post conflict shrink, special conflict handling, OBM enrichment, validation metrics |
| Road | `E:\vscode\fusioncode\MapTileTool\FusionTool\road.py` | `process_road_fusion()` plus helper phases |
| River / water line | `E:\vscode\fusioncode\MapTileTool\FusionTool\river.py` | `perform_river_fusion()` plus helper phases |
| Lake / water polygon | `E:\vscode\fusioncode\MapTileTool\FusionTool\lake.py` | `process_lake_fusion()` plus overlap helper |
| POI | `E:\vscode\fusioncode\MapTileTool\FusionPOI.py` | `PiPei()` |
| Generic conflicts | `E:\vscode\fusioncode\MapTileTool\FusionTool\conflict.py` | `detect_conflicts()` |

## File Structure

### Create

- `E:\vscode\fusionAgent\fusion_algorithms\__init__.py`  
  Package marker and public exports.
- `E:\vscode\fusionAgent\fusion_algorithms\contracts.py`  
  Typed contracts for source specs, raster specs, vector artifacts, algorithm step context, lineage, quality summaries, and parameter dataclasses.
- `E:\vscode\fusionAgent\fusion_algorithms\fusioncode_loader.py`  
  Imports `fusioncode` modules from `FUSIONCODE_ROOT` or default `E:\vscode\fusioncode`; no business logic.
- `E:\vscode\fusionAgent\fusion_algorithms\building_raster.py`  
  Presence validation and height extraction primitives.
- `E:\vscode\fusionAgent\fusion_algorithms\building_matching_v8.py`  
  Source normalization, pairwise candidate graph, component solving, fusion row construction, residual priority resolution.
- `E:\vscode\fusionAgent\fusion_algorithms\building_optimization.py`  
  Road topology, conflict graph optimization, post-conflict shrink, road-tail adjustment, metrics.
- `E:\vscode\fusionAgent\fusion_algorithms\building_workflows.py`  
  KG-step orchestration helpers for decomposed multi-source building workflows.
- `E:\vscode\fusionAgent\fusion_algorithms\road_fusion.py`  
  Road fusion primitives with injected parameters instead of module constants.
- `E:\vscode\fusionAgent\fusion_algorithms\water_fusion.py`  
  River/water-line and lake/water-polygon primitives.
- `E:\vscode\fusionAgent\fusion_algorithms\poi_fusion.py`  
  POI geohash/name/source-priority primitives.
- `E:\vscode\fusionAgent\fusion_algorithms\quality.py`  
  Cross-theme conflict and quality metric wrappers.
- `E:\vscode\fusionAgent\fusion_algorithms\registry_metadata.py`  
  Single source of truth for new algorithm ids, data type ids, parameter defaults, and workflow pattern ids used by seed tests.
- `E:\vscode\fusionAgent\adapters\fusioncode_building_adapter.py`  
  Bridges executor context to decomposed building primitives.
- `E:\vscode\fusionAgent\adapters\fusioncode_linear_adapter.py`  
  Bridges road and water-line primitives.
- `E:\vscode\fusionAgent\adapters\fusioncode_polygon_adapter.py`  
  Bridges lake/water-polygon primitives.
- `E:\vscode\fusionAgent\adapters\fusioncode_poi_adapter.py`  
  Bridges POI primitives.
- `E:\vscode\fusionAgent\tests\test_fusioncode_inventory_contract.py`
- `E:\vscode\fusionAgent\tests\test_fusioncode_contracts.py`
- `E:\vscode\fusionAgent\tests\test_fusioncode_kg_metadata.py`
- `E:\vscode\fusionAgent\tests\test_fusioncode_building_raster.py`
- `E:\vscode\fusionAgent\tests\test_fusioncode_building_v8_decomposition.py`
- `E:\vscode\fusionAgent\tests\test_fusioncode_building_workflow.py`
- `E:\vscode\fusionAgent\tests\test_fusioncode_linear_water_road.py`
- `E:\vscode\fusionAgent\tests\test_fusioncode_poi.py`
- `E:\vscode\fusionAgent\tests\test_fusioncode_executor_handlers.py`

### Modify

- `E:\vscode\fusionAgent\kg\models.py`  
  Add metadata types only if current `Dict[str, str]` workflow metadata blocks list-valued or nested algorithm phase metadata.
- `E:\vscode\fusionAgent\kg\seed.py`  
  Add data types, algorithm nodes, parameter specs, workflow patterns; replace reserved building multi-source and raster-height capabilities with executable nodes while preserving compatibility aliases.
- `E:\vscode\fusionAgent\kg\source_catalog.py`  
  Mark source-set and raster sources as executable where local/runtime acquisition supports them.
- `E:\vscode\fusionAgent\agent\tooling.py`  
  Register decomposed algorithm ids and handlers.
- `E:\vscode\fusionAgent\agent\executor.py`  
  Extend `ExecutionContext` with named artifacts/source sets/raster paths and add handlers for new adapters.
- `E:\vscode\fusionAgent\agent\retriever.py`  
  Stop presenting multi-source and height raster as reserved when the new executable algorithms are available; emit workflow hints for optional raster/road steps.
- `E:\vscode\fusionAgent\agent\validator.py`  
  Validate dependent steps with intermediate data types and multiple input artifacts.
- `E:\vscode\fusionAgent\services\input_acquisition_service.py`  
  Bind multi-source vectors and rasters into named artifacts for execution.
- `E:\vscode\fusionAgent\services\agent_run_service.py`  
  Persist decomposed step events, intermediate artifacts, and lineage summaries.
- `E:\vscode\fusionAgent\docs\v2-operations.md`  
  Update the reserved-capability statements after implementation and verification.

## KG Algorithm Decomposition

### Building Data Types

- `dt.building.source_set`: named vector sources such as `MS`, `GG`, `OSM`, `OBM`, custom user uploads.
- `dt.building.normalized_set`: source-set after CRS, geometry validity, area filtering, source labels, and canonical fields.
- `dt.building.presence_validated_set`: normalized buildings with `core_score`, probability features, shifted support fields, and existence status.
- `dt.building.match_candidate_graph`: candidate edges and node summaries from V8 matching.
- `dt.building.match_components`: accepted 1:1, 1:N, M:N, unmatched and residual groups.
- `dt.building.fused_raw`: geometry-priority fused rows before conflict optimization.
- `dt.building.road_topology_adjusted`: buildings after road-aware topology preprocessing.
- `dt.building.conflict_optimized`: buildings after graph optimization.
- `dt.building.height_enriched`: fused buildings with `H_Raster` and canonical `height`.
- `dt.building.quality_report`: metric JSON or table artifact.
- `dt.raster.building_presence`: probability/presence raster.
- `dt.raster.building_height`: height raster.
- `dt.road.network`: road network used as context for building road-cut and optimization.

### Building Algorithm Nodes

- `algo.preprocess.building.source_normalize.v1`
- `algo.enrich.building.obm_attributes.v1`
- `algo.validate.building.presence_raster.v1`
- `algo.match.building.v8_candidate_graph.v1`
- `algo.match.building.v8_component_solver.v1`
- `algo.fusion.building.cascade_geometry_priority.v1`
- `algo.resolve.building.residual_priority.v1`
- `algo.optimize.road.topology_for_buildings.v1`
- `algo.optimize.building.conflict_graph.v1`
- `algo.refine.building.post_conflict_shrink.v1`
- `algo.refine.building.road_tail.v1`
- `algo.enrich.building.height_from_raster.v1`
- `algo.assess.building.quality_metrics.v1`
- Compatibility composite: `algo.fusion.building.multi_source.decomposed.v1`
  - This node is a planner convenience and must expand into the primitive nodes above before execution.
  - It must not call `run_full_pipeline()` as its runtime implementation.

### Road / Water / POI Algorithm Nodes

- `algo.preprocess.road.source_normalize.v1`
- `algo.preprocess.road.split_sharp_turns.v1`
- `algo.match.road.buffer_hausdorff_angle.v1`
- `algo.fusion.road.segment_priority_merge.v1`
- `algo.refine.road.dedupe_endpoint_snap.v1`
- `algo.fusion.road.segment_match_topology.v1`
- `algo.preprocess.water.line_source_normalize.v1`
- `algo.match.water.line_buffer_hausdorff.v1`
- `algo.fusion.water.line_three_source_priority.v1`
- `algo.match.water.polygon_overlap.v1`
- `algo.fusion.water.polygon_priority_merge.v1`
- `algo.fusion.poi.geohash_neighbor_match.v1`
- `algo.fusion.poi.name_source_priority_merge.v1`
- `algo.detect.spatial_conflicts.v1`

## Parameter Decoupling Plan

### Building Matching Parameters

Store these on `algo.match.building.v8_candidate_graph.v1` and `algo.match.building.v8_component_solver.v1`:

- `parallel_backend`, `workers`
- `shift_anchor_iou`, `shift_grid_size`, `max_shift_residual_norm`
- `enable_anchor_recall`, `anchor_min_groups`, `anchor_recall_min_group_score`, `anchor_recall_max_shift_m`
- `anchor_recall_min_cover`, `anchor_recall_min_iou`, `anchor_recall_min_explain`, `anchor_recall_min_area_ratio`, `anchor_recall_min_fit`
- `fan_min_cover_small`, `fan_min_iou_fallback`
- `weak_min_cover`, `weak_min_iou`
- `enable_road_cut`, `road_highway_col`, `major_roads`, `exemption_cover_small`
- `lock_single_min_strict_score`, `lock_single_min_cover`, `lock_single_min_iou`, `lock_single_min_fit`, `lock_single_min_area_ratio`, `lock_single_min_mutual_explain`
- `lock_mutual_min_gap`, `lock_mutual_min_adv_ratio`
- `thresh_1_to_1`, `thresh_1_to_N`, `thresh_M_to_N`
- `large_group_penalty`, `max_dynamic_threshold`
- `min_closure_accept_1to1`, `min_closure_accept_multi`, `min_purity_accept_multi`, `min_coarse_accept_multi`, `min_detail_accept_multi`
- `min_macro_iou_accept_multi`, `min_explain_accept_multi`, `max_dominant_edge_ratio`, `max_weak_member_ratio`
- `min_support_accept_1to1`, `min_fit_accept_1to1`, `min_explain_accept_1to1`, `min_macro_iou_accept_1to1`, `min_support_accept_multi`
- `source_priority_order`, `name_aliases`, `height_aliases`, `levels_aliases`, `class_aliases`

### Building Raster Parameters

Store these on `algo.validate.building.presence_raster.v1`:

- `prob_threshold`, `search_dist_m`, `height_thresh`, `n_jobs`
- `confirmed_score_threshold`, `confirmed_p90_threshold`, `confirmed_support_threshold`
- `uncertain_score_threshold`, `uncertain_max_threshold`, `uncertain_support_threshold`
- `status_field`, `core_score_field`, `shift_score_field`, `keep_uncertain`

Store these on `algo.enrich.building.height_from_raster.v1`:

- `height_sampling_method`, `n_jobs`, `height_output_field`, `canonical_height_field`
- `positive_only`, `nodata_value`, `fallback_height`, `preserve_original_crs`

### Building Optimization Parameters

Store these on road topology, conflict graph, shrink and tail nodes:

- `global_max_shift`, `global_area_change_limit`
- `simplify_tol`, `cluster_tol`, `snap_tol`, `cpc_threshold`, `sinuosity_limit`
- `neighbor_search_radius`, `neighbor_max_k`, `neighbor_weight_mode`, `neighbor_distance_weight_power`
- `overlap_delete_threshold`, `overlap_min_area`
- `road_buffer_width`, `phantom_lpr_threshold`, `phantom_weight_discount`, `max_tolerable_depth`
- `w_overlap`, `w_neighbor_barrier`, `w_road_expulsion`, `w_road_barrier`, `buffer_zone`
- `max_translate`, `min_scale`, `max_scale`, `max_nfev`, `ftol`, `max_outer_iterations`
- `post_shrink_threshold_m2`, `post_shrink_scale_cap_pct`, `post_shrink_scale_step_pct`
- `tail_conflict_max_area`, `tail_translate_limit`, `tail_min_scale`, `tail_max_scale`, `tail_max_iterations`, `tail_area_change_limit_pct`

### Road / Water / POI Parameters

Store these on the line and POI primitives:

- Road and water line: `angle_threshold_deg`, `buffer_dist_m`, `max_hausdorff_m`, `snap_tolerance_m`, `endpoint_buffer_radius_m`, `dedupe_buffer_m`, `angle_diff_max_deg`, `min_length_similarity`, `line_priority_order`
- Water polygon: `overlap_threshold`, `min_intersection_area`, `source_priority_order`, `preserve_unmatched_osm`, `preserve_unmatched_new`
- POI: `geohash_precision`, `neighbor_rings`, `name_similarity_threshold`, `source_priority_order`, `duplicate_distance_m`, `remaining_output_mode`
- Conflict detection: `geometry_type_scope`, `buffer_distance_m`, `overlap_area_min`, `touch_policy`, `report_fields`

## Workflow Patterns

### `wp.building.drs4br.decomposed.v1`

1. `algo.preprocess.building.source_normalize.v1`
2. Optional `algo.enrich.building.obm_attributes.v1`
3. Optional `algo.validate.building.presence_raster.v1`
4. `algo.match.building.v8_candidate_graph.v1`
5. `algo.match.building.v8_component_solver.v1`
6. `algo.fusion.building.cascade_geometry_priority.v1`
7. `algo.resolve.building.residual_priority.v1`
8. Optional `algo.optimize.road.topology_for_buildings.v1`
9. `algo.optimize.building.conflict_graph.v1`
10. Optional `algo.refine.building.post_conflict_shrink.v1`
11. Optional `algo.refine.building.road_tail.v1`
12. Optional `algo.enrich.building.height_from_raster.v1`
13. `algo.assess.building.quality_metrics.v1`

### `wp.road.fusioncode.segment_topology.v1`

1. `algo.preprocess.road.source_normalize.v1`
2. `algo.preprocess.road.split_sharp_turns.v1`
3. `algo.match.road.buffer_hausdorff_angle.v1`
4. `algo.fusion.road.segment_priority_merge.v1`
5. `algo.refine.road.dedupe_endpoint_snap.v1`

### `wp.water.fusioncode.line_and_polygon.v1`

1. `algo.preprocess.water.line_source_normalize.v1`
2. `algo.match.water.line_buffer_hausdorff.v1`
3. `algo.fusion.water.line_three_source_priority.v1`
4. `algo.match.water.polygon_overlap.v1`
5. `algo.fusion.water.polygon_priority_merge.v1`

### `wp.poi.fusioncode.geohash_priority.v1`

1. `algo.fusion.poi.geohash_neighbor_match.v1`
2. `algo.fusion.poi.name_source_priority_merge.v1`

## Task 1: Add Inventory Guard Tests

**Files:**
- Create: `E:\vscode\fusionAgent\tests\test_fusioncode_inventory_contract.py`

- [ ] **Step 1: Write tests that lock the external source inventory**

```python
from __future__ import annotations

from pathlib import Path


FUSIONCODE_ROOT = Path("E:/vscode/fusioncode")


def test_fusioncode_core_files_exist() -> None:
    expected = [
        "algorithm_adapter.py",
        "algorithm_core/main.py",
        "algorithm_core/models/matching_engine.py",
        "algorithm_core/models/temporal_validator.py",
        "algorithm_core/models/spatial_optimizer.py",
        "algorithm_core/models/post_conflict_shrink_refiner.py",
        "algorithm_core/models/obm_enricher.py",
        "algorithm_core/models/quality_assessor.py",
        "MapTileTool/FusionTool/road.py",
        "MapTileTool/FusionTool/river.py",
        "MapTileTool/FusionTool/lake.py",
        "MapTileTool/FusionTool/conflict.py",
        "MapTileTool/FusionPOI.py",
    ]
    missing = [rel for rel in expected if not (FUSIONCODE_ROOT / rel).exists()]
    assert missing == []


def test_fusioncode_entry_points_are_still_present() -> None:
    files_and_symbols = {
        "algorithm_adapter.py": ["def _parse_geometry_source_paths", "def run_full_pipeline"],
        "algorithm_core/models/matching_engine.py": [
            "class MatchConfig",
            "def generate_candidate_edges_v8",
            "def process_worker_v8",
            "def build_fusion_rows",
            "def execute_v8_fusion",
        ],
        "algorithm_core/models/temporal_validator.py": [
            "def validate_existence_parallel",
            "def extract_height_parallel",
        ],
        "algorithm_core/models/spatial_optimizer.py": [
            "class OptConfig",
            "def optimize_road_topology",
            "def build_constraint_graph",
            "def run_graph_optimization_v5",
            "def calculate_metrics",
        ],
        "MapTileTool/FusionTool/road.py": ["def process_road_fusion"],
        "MapTileTool/FusionTool/river.py": ["def perform_river_fusion"],
        "MapTileTool/FusionTool/lake.py": ["def process_lake_fusion"],
        "MapTileTool/FusionTool/conflict.py": ["def detect_conflicts"],
        "MapTileTool/FusionPOI.py": ["def PiPei"],
    }
    for rel, symbols in files_and_symbols.items():
        text = (FUSIONCODE_ROOT / rel).read_text(encoding="utf-8", errors="ignore")
        for symbol in symbols:
            assert symbol in text, f"{symbol} missing from {rel}"
```

- [ ] **Step 2: Run the inventory tests**

Run: `pytest E:\vscode\fusionAgent\tests\test_fusioncode_inventory_contract.py -q`

Expected: PASS with two tests. If it fails, update this plan's source inventory before writing runtime code.

- [ ] **Step 3: Commit the inventory guard**

Run:

```powershell
git add tests/test_fusioncode_inventory_contract.py
git commit -m "test: lock fusioncode inventory contract"
```

## Task 2: Add Typed Algorithm Contracts

**Files:**
- Create: `E:\vscode\fusionAgent\fusion_algorithms\__init__.py`
- Create: `E:\vscode\fusionAgent\fusion_algorithms\contracts.py`
- Create: `E:\vscode\fusionAgent\tests\test_fusioncode_contracts.py`

- [ ] **Step 1: Write contract tests**

```python
from __future__ import annotations

from pathlib import Path

from fusion_algorithms.contracts import (
    BuildingMatchParams,
    BuildingRasterPresenceParams,
    RasterSpec,
    SourceSpec,
)


def test_source_spec_normalizes_labels() -> None:
    spec = SourceSpec(name=" ms ", path=Path("a.gpkg"), priority=10)
    assert spec.name == "MS"
    assert spec.path == Path("a.gpkg")
    assert spec.priority == 10


def test_raster_spec_requires_kind() -> None:
    spec = RasterSpec(kind="building_height", path=Path("height.vrt"))
    assert spec.kind == "building_height"


def test_building_match_defaults_mirror_fusioncode_config() -> None:
    params = BuildingMatchParams()
    assert params.weak_min_cover == 0.05
    assert params.weak_min_iou == 0.05
    assert params.thresh_1_to_1 == 0.40
    assert params.thresh_1_to_N == 0.44
    assert params.thresh_M_to_N == 0.47


def test_presence_defaults_mirror_fusioncode_config() -> None:
    params = BuildingRasterPresenceParams()
    assert params.prob_threshold == 0.20
    assert params.search_dist_m == 4.0
    assert params.confirmed_score_threshold == 0.55
    assert params.uncertain_score_threshold == 0.30
```

- [ ] **Step 2: Implement `contracts.py`**

Create frozen dataclasses for `SourceSpec`, `RasterSpec`, `VectorArtifact`, `AlgorithmStepContext`, `LineageRecord`, `QualitySummary`, `BuildingRasterPresenceParams`, `BuildingHeightParams`, `BuildingMatchParams`, `BuildingOptimizationParams`, `RoadFusionParams`, `WaterLineFusionParams`, `WaterPolygonFusionParams`, `PoiFusionParams`, and `ConflictDetectionParams`.

Minimum implementation detail:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SourceSpec:
    name: str
    path: Path
    priority: int = 100
    data_type: str = "vector"
    role: str = "primary"

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", self.name.strip().upper())


@dataclass(frozen=True)
class RasterSpec:
    kind: str
    path: Path
    band: int = 1
    nodata: float | None = None


@dataclass(frozen=True)
class BuildingRasterPresenceParams:
    prob_threshold: float = 0.20
    search_dist_m: float = 4.0
    height_thresh: float = 2.0
    n_jobs: int = -1
    confirmed_score_threshold: float = 0.55
    confirmed_p90_threshold: float = 0.45
    confirmed_support_threshold: float = 0.50
    uncertain_score_threshold: float = 0.30
    uncertain_max_threshold: float = 0.45
    uncertain_support_threshold: float = 0.15


@dataclass(frozen=True)
class BuildingMatchParams:
    parallel_backend: str = "process"
    workers: int | None = None
    shift_anchor_iou: float = 0.40
    shift_grid_size: float = 300.0
    fan_min_cover_small: float = 0.20
    weak_min_cover: float = 0.05
    weak_min_iou: float = 0.05
    thresh_1_to_1: float = 0.40
    thresh_1_to_N: float = 0.44
    thresh_M_to_N: float = 0.47
    enable_road_cut: bool = True
    source_priority_order: tuple[str, ...] = ("MS", "GG", "OSM")
    extra: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 3: Run contract tests**

Run: `pytest E:\vscode\fusionAgent\tests\test_fusioncode_contracts.py -q`

Expected: PASS.

- [ ] **Step 4: Commit contracts**

Run:

```powershell
git add fusion_algorithms tests/test_fusioncode_contracts.py
git commit -m "feat: add fusioncode algorithm contracts"
```

## Task 3: Add FusionCode Loader Without Runtime Coupling

**Files:**
- Create: `E:\vscode\fusionAgent\fusion_algorithms\fusioncode_loader.py`
- Modify: `E:\vscode\fusionAgent\fusion_algorithms\__init__.py`
- Test: `E:\vscode\fusionAgent\tests\test_fusioncode_contracts.py`

- [ ] **Step 1: Add tests for deterministic external loading**

```python
from fusion_algorithms.fusioncode_loader import FusionCodeModules, load_fusioncode_modules


def test_load_fusioncode_modules_exposes_core_modules() -> None:
    modules = load_fusioncode_modules()
    assert isinstance(modules, FusionCodeModules)
    assert hasattr(modules.matching_engine, "MatchConfig")
    assert hasattr(modules.temporal_validator, "validate_existence_parallel")
    assert hasattr(modules.spatial_optimizer, "OptConfig")
```

- [ ] **Step 2: Implement loader**

`load_fusioncode_modules()` must:

- Resolve root from `FUSIONCODE_ROOT`, defaulting to `E:\vscode\fusioncode`.
- Insert `root`, `root\algorithm_core`, and `root\algorithm_core\models` into `sys.path` if absent.
- Import modules lazily through `importlib`.
- Return module handles only; it must not execute `run_full_pipeline()`.

- [ ] **Step 3: Run tests**

Run: `pytest E:\vscode\fusionAgent\tests\test_fusioncode_contracts.py -q`

Expected: PASS.

- [ ] **Step 4: Commit loader**

Run:

```powershell
git add fusion_algorithms/fusioncode_loader.py fusion_algorithms/__init__.py tests/test_fusioncode_contracts.py
git commit -m "feat: load fusioncode modules lazily"
```

## Task 4: Add KG Metadata For Decomposed Algorithms

**Files:**
- Create: `E:\vscode\fusionAgent\fusion_algorithms\registry_metadata.py`
- Modify: `E:\vscode\fusionAgent\kg\seed.py`
- Modify: `E:\vscode\fusionAgent\kg\models.py` only if nested workflow metadata needs `Dict[str, Any]`
- Test: `E:\vscode\fusionAgent\tests\test_fusioncode_kg_metadata.py`

- [ ] **Step 1: Write KG metadata tests**

```python
from __future__ import annotations

from kg.inmemory_repository import InMemoryKGRepository
from schemas.fusion import JobType


def _repo() -> InMemoryKGRepository:
    return InMemoryKGRepository()


def test_decomposed_building_algorithms_are_registered() -> None:
    repo = _repo()
    required = [
        "algo.preprocess.building.source_normalize.v1",
        "algo.validate.building.presence_raster.v1",
        "algo.match.building.v8_candidate_graph.v1",
        "algo.match.building.v8_component_solver.v1",
        "algo.fusion.building.cascade_geometry_priority.v1",
        "algo.optimize.building.conflict_graph.v1",
        "algo.enrich.building.height_from_raster.v1",
        "algo.assess.building.quality_metrics.v1",
    ]
    missing = [algo_id for algo_id in required if repo.get_algorithm(algo_id) is None]
    assert missing == []


def test_reserved_building_capabilities_have_executable_replacements() -> None:
    repo = _repo()
    multi_source = repo.get_algorithm("algo.fusion.building.multi_source.decomposed.v1")
    height = repo.get_algorithm("algo.enrich.building.height_from_raster.v1")
    assert multi_source is not None
    assert multi_source.metadata["runtime_status"] == "runtime_candidate"
    assert height is not None
    assert height.metadata["runtime_status"] == "runtime_candidate"


def test_v8_matching_parameters_are_queryable() -> None:
    repo = _repo()
    keys = {spec.key for spec in repo.get_parameter_specs("algo.match.building.v8_component_solver.v1")}
    assert {"weak_min_cover", "weak_min_iou", "thresh_1_to_1", "thresh_1_to_N", "thresh_M_to_N"} <= keys


def test_decomposed_building_workflow_has_ordered_steps() -> None:
    repo = _repo()
    patterns = repo.get_candidate_patterns(job_type=JobType.building, disaster_type="generic", limit=20)
    pattern = next(p for p in patterns if p.pattern_id == "wp.building.drs4br.decomposed.v1")
    assert [step.order for step in pattern.steps] == list(range(1, len(pattern.steps) + 1))
    assert pattern.steps[0].algorithm_id == "algo.preprocess.building.source_normalize.v1"
    assert pattern.steps[-1].algorithm_id == "algo.assess.building.quality_metrics.v1"
```

- [ ] **Step 2: Implement `registry_metadata.py`**

Store lists of data type ids, algorithm ids, handler names, parameter specs, and pattern definitions in Python constants. This keeps `kg/seed.py` readable and makes tests compare expected ids without duplicating long lists.

- [ ] **Step 3: Modify `kg/seed.py`**

Add all new data types, algorithm nodes and parameter specs. Existing reserved ids remain for compatibility but receive metadata that points to executable replacements:

```python
metadata={
    "runtime_status": "compatibility_alias",
    "replacement_algorithm_id": "algo.fusion.building.multi_source.decomposed.v1",
}
```

- [ ] **Step 4: Run KG tests**

Run: `pytest E:\vscode\fusionAgent\tests\test_fusioncode_kg_metadata.py E:\vscode\fusionAgent\tests\test_kg_parameter_specs.py E:\vscode\fusionAgent\tests\test_planner_context.py -q`

Expected: PASS. Existing tests that asserted reserved-only hints must be updated to assert executable replacements and optional raster hints.

- [ ] **Step 5: Commit KG metadata**

Run:

```powershell
git add fusion_algorithms/registry_metadata.py kg/seed.py kg/models.py tests/test_fusioncode_kg_metadata.py tests/test_planner_context.py
git commit -m "feat: register decomposed fusioncode algorithms in kg"
```

## Task 5: Implement Building Raster Primitives

**Files:**
- Create: `E:\vscode\fusionAgent\fusion_algorithms\building_raster.py`
- Test: `E:\vscode\fusionAgent\tests\test_fusioncode_building_raster.py`

- [ ] **Step 1: Write raster wrapper tests with monkeypatched FusionCode calls**

```python
from __future__ import annotations

import geopandas as gpd
from shapely.geometry import box

from fusion_algorithms.building_raster import enrich_height_from_raster, validate_presence_from_raster
from fusion_algorithms.contracts import BuildingHeightParams, BuildingRasterPresenceParams, RasterSpec


def _gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"id": [1]}, geometry=[box(0, 0, 1, 1)], crs="EPSG:4326")


def test_presence_wrapper_passes_decoupled_params(monkeypatch) -> None:
    captured = {}

    def fake_validate(gdf, raster_path, **kwargs):
        captured.update(kwargs)
        out = gdf.copy()
        out["exist_status"] = "confirmed"
        return out

    monkeypatch.setattr("fusion_algorithms.building_raster._validate_existence_parallel", fake_validate)
    result = validate_presence_from_raster(
        _gdf(),
        RasterSpec(kind="building_presence", path="presence.vrt"),
        BuildingRasterPresenceParams(prob_threshold=0.25, search_dist_m=6.0),
    )
    assert result.iloc[0]["exist_status"] == "confirmed"
    assert captured["prob_threshold"] == 0.25
    assert captured["search_dist_m"] == 6.0


def test_height_wrapper_maps_height_field(monkeypatch) -> None:
    def fake_height(gdf, raster_path, n_jobs):
        out = gdf.copy()
        out["H_Raster"] = [12.5]
        return out

    monkeypatch.setattr("fusion_algorithms.building_raster._extract_height_parallel", fake_height)
    result = enrich_height_from_raster(
        _gdf(),
        RasterSpec(kind="building_height", path="height.vrt"),
        BuildingHeightParams(height_output_field="height_m"),
    )
    assert float(result.iloc[0]["height_m"]) == 12.5
```

- [ ] **Step 2: Implement wrappers**

Implement functions:

- `validate_presence_from_raster(gdf, raster, params)`
- `enrich_height_from_raster(gdf, raster, params)`

The wrappers convert `RasterSpec.path` to string, pass every decoupled parameter explicitly, preserve CRS, and map output field names without mutating input `gdf`.

- [ ] **Step 3: Run raster tests**

Run: `pytest E:\vscode\fusionAgent\tests\test_fusioncode_building_raster.py -q`

Expected: PASS.

- [ ] **Step 4: Commit raster primitives**

Run:

```powershell
git add fusion_algorithms/building_raster.py tests/test_fusioncode_building_raster.py
git commit -m "feat: add building raster fusion primitives"
```

## Task 6: Implement Building V8 Matching Decomposition

**Files:**
- Create: `E:\vscode\fusionAgent\fusion_algorithms\building_matching_v8.py`
- Test: `E:\vscode\fusionAgent\tests\test_fusioncode_building_v8_decomposition.py`

- [ ] **Step 1: Write tests that forbid monolithic runtime use**

```python
from __future__ import annotations

import inspect

from fusion_algorithms import building_matching_v8


def test_decomposed_v8_runtime_does_not_call_full_pipeline() -> None:
    source = inspect.getsource(building_matching_v8)
    assert "run_full_pipeline(" not in source


def test_decomposed_v8_runtime_exposes_primitive_steps() -> None:
    required = [
        "normalize_building_sources",
        "build_v8_candidate_graph",
        "solve_v8_components",
        "build_cascade_fusion_rows",
        "resolve_residual_priority_conflicts",
        "run_pairwise_v8_fusion",
        "run_cascaded_multi_source_fusion",
    ]
    missing = [name for name in required if not hasattr(building_matching_v8, name)]
    assert missing == []
```

- [ ] **Step 2: Add tests for source-order controlled cascade**

Use three tiny synthetic GeoDataFrames and monkeypatch `run_pairwise_v8_fusion()` to record call order. The expected call order is `MS+GG`, then `FUSED_MS_GG+OSM` for default `source_priority_order=("MS", "GG", "OSM")`.

- [ ] **Step 3: Implement parameter conversion**

Implement `to_match_config(params: BuildingMatchParams)` that creates `fusioncode` `MatchConfig` and copies every field that exists on both dataclasses. Unknown fields stay in `params.extra` and are recorded in lineage, not silently applied.

- [ ] **Step 4: Implement primitives**

Implement:

- `normalize_building_sources(source_specs, target_crs, filters, field_aliases)`
- `build_v8_candidate_graph(base_gdf, target_gdf, roads, params)`
- `solve_v8_components(candidate_graph, base_gdf, target_gdf, params)`
- `build_cascade_fusion_rows(groups, base_gdf, target_gdf, params, base_name, target_name)`
- `resolve_residual_priority_conflicts(fusion_rows, params, base_name, target_name)`
- `run_pairwise_v8_fusion(base_gdf, target_gdf, roads, params, base_name, target_name)`
- `run_cascaded_multi_source_fusion(source_map, roads, params, source_priority_order)`

`run_pairwise_v8_fusion()` may call `execute_v8_fusion()` only as a temporary compatibility implementation if it emits lineage that identifies the covered primitive phases. The final execution path should use `generate_candidate_edges_v8()`, component processing, and `build_fusion_rows()` directly once tests cover parity.

- [ ] **Step 5: Run matching tests**

Run: `pytest E:\vscode\fusionAgent\tests\test_fusioncode_building_v8_decomposition.py -q`

Expected: PASS.

- [ ] **Step 6: Commit matching decomposition**

Run:

```powershell
git add fusion_algorithms/building_matching_v8.py tests/test_fusioncode_building_v8_decomposition.py
git commit -m "feat: decompose fusioncode building v8 matching"
```

## Task 7: Implement Building Optimization And Quality Primitives

**Files:**
- Create: `E:\vscode\fusionAgent\fusion_algorithms\building_optimization.py`
- Create: `E:\vscode\fusionAgent\fusion_algorithms\quality.py`
- Test: `E:\vscode\fusionAgent\tests\test_fusioncode_building_workflow.py`

- [ ] **Step 1: Write tests for explicit optimization phases**

Test that `run_building_optimization_chain()` calls road topology, conflict graph, post-shrink, road-tail, and metrics functions according to boolean parameters and records skipped optional phases.

- [ ] **Step 2: Implement `to_opt_config()`**

Map `BuildingOptimizationParams` to `fusioncode` `OptConfig` by copying matching attribute names. Explicitly set `global_max_shift`, `road_buffer_width`, `max_tolerable_depth`, `w_road_expulsion`, `max_outer_iterations`, `tail_*`, and `n_jobs`.

- [ ] **Step 3: Implement optimization wrappers**

Implement:

- `optimize_building_road_topology(buildings, roads, params)`
- `optimize_building_conflict_graph(buildings, roads, params)`
- `refine_post_conflict_shrink(buildings, params)`
- `refine_road_tail_conflicts(buildings, roads, params)`
- `assess_building_quality(before, after, roads, params)`
- `run_building_optimization_chain(raw_fused, roads, params)`

- [ ] **Step 4: Run tests**

Run: `pytest E:\vscode\fusionAgent\tests\test_fusioncode_building_workflow.py -q`

Expected: PASS.

- [ ] **Step 5: Commit optimization primitives**

Run:

```powershell
git add fusion_algorithms/building_optimization.py fusion_algorithms/quality.py tests/test_fusioncode_building_workflow.py
git commit -m "feat: add building optimization primitives"
```

## Task 8: Implement Decomposed Building Workflow Adapter

**Files:**
- Create: `E:\vscode\fusionAgent\fusion_algorithms\building_workflows.py`
- Create: `E:\vscode\fusionAgent\adapters\fusioncode_building_adapter.py`
- Modify: `E:\vscode\fusionAgent\agent\executor.py`
- Modify: `E:\vscode\fusionAgent\agent\tooling.py`
- Test: `E:\vscode\fusionAgent\tests\test_fusioncode_executor_handlers.py`

- [ ] **Step 1: Extend execution context tests**

Test that an `ExecutionContext` can carry:

- `named_vectors={"MS": Path(...), "GG": Path(...), "OSM": Path(...)}`
- `named_rasters={"building_presence": Path(...), "building_height": Path(...)}`
- `context_vectors={"roads": Path(...)}`
- current step parameters.

- [ ] **Step 2: Modify `ExecutionContext`**

Add fields with empty-dict defaults:

```python
named_vectors: Dict[str, Path] = field(default_factory=dict)
named_rasters: Dict[str, Path] = field(default_factory=dict)
context_vectors: Dict[str, Path] = field(default_factory=dict)
intermediate_artifacts: Dict[str, Path] = field(default_factory=dict)
```

- [ ] **Step 3: Register handlers**

Add `ToolSpec` entries for every executable algorithm node. Use handler names such as `_handle_building_source_normalize`, `_handle_building_presence_raster`, `_handle_building_v8_candidate_graph`, `_handle_building_v8_component_solver`, `_handle_building_cascade_fusion`, `_handle_building_conflict_graph`, `_handle_building_height_from_raster`, `_handle_building_quality_metrics`, and `_handle_building_multi_source_decomposed`.

- [ ] **Step 4: Implement adapter functions**

The adapter reads named vectors/rasters, loads GeoDataFrames, invokes the primitive for the active algorithm, writes an artifact under `context.output_dir`, and returns the artifact path. Each output filename includes the step number and algorithm slug, for example `step_04_building_v8_candidate_graph.gpkg` or `step_13_building_quality_metrics.json`.

- [ ] **Step 5: Run executor tests**

Run: `pytest E:\vscode\fusionAgent\tests\test_fusioncode_executor_handlers.py E:\vscode\fusionAgent\tests\test_tool_registry.py -q`

Expected: PASS.

- [ ] **Step 6: Commit building adapter**

Run:

```powershell
git add agent/executor.py agent/tooling.py adapters/fusioncode_building_adapter.py fusion_algorithms/building_workflows.py tests/test_fusioncode_executor_handlers.py tests/test_tool_registry.py
git commit -m "feat: execute decomposed fusioncode building workflow"
```

## Task 9: Implement Road And Water Primitive Adapters

**Files:**
- Create: `E:\vscode\fusionAgent\fusion_algorithms\road_fusion.py`
- Create: `E:\vscode\fusionAgent\fusion_algorithms\water_fusion.py`
- Create: `E:\vscode\fusionAgent\adapters\fusioncode_linear_adapter.py`
- Create: `E:\vscode\fusionAgent\adapters\fusioncode_polygon_adapter.py`
- Modify: `E:\vscode\fusionAgent\agent\tooling.py`
- Modify: `E:\vscode\fusionAgent\agent\executor.py`
- Test: `E:\vscode\fusionAgent\tests\test_fusioncode_linear_water_road.py`

- [ ] **Step 1: Write road primitive tests**

Use simple `LineString` GeoDataFrames and assert:

- sharp-turn splitting respects `angle_threshold_deg`
- match candidates respect `buffer_dist_m`, `max_hausdorff_m`, and `angle_diff_max_deg`
- dedupe removes contained shorter duplicate segments when `dedupe_buffer_m` covers the candidate.

- [ ] **Step 2: Write water primitive tests**

Use simple line and polygon GeoDataFrames and assert:

- river/water-line matching uses line params rather than module constants
- lake/water-polygon matching uses `overlap_threshold`
- polygon priority merge preserves unmatched source features according to parameters.

- [ ] **Step 3: Implement road functions**

Implement road primitives by porting or wrapping helper-level logic from `MapTileTool\FusionTool\road.py` with injected `RoadFusionParams`. Do not mutate module-level constants like `ANGLE_THRESHOLD`, `BUFFER_DIST`, or `MAX_HAUSDORFF` during runtime.

- [ ] **Step 4: Implement water functions**

Implement water-line and water-polygon primitives by porting or wrapping helper-level logic from `river.py` and `lake.py` with injected params. Keep `perform_river_fusion()` and `process_lake_fusion()` as parity references.

- [ ] **Step 5: Register and run adapters**

Add handlers for road/water primitives and compatibility composite nodes `algo.fusion.road.segment_match_topology.v1` and `algo.fusion.water.line_area_polygon.v1`.

- [ ] **Step 6: Run tests**

Run: `pytest E:\vscode\fusionAgent\tests\test_fusioncode_linear_water_road.py E:\vscode\fusionAgent\tests\test_tool_registry.py -q`

Expected: PASS.

- [ ] **Step 7: Commit road/water primitives**

Run:

```powershell
git add fusion_algorithms/road_fusion.py fusion_algorithms/water_fusion.py adapters/fusioncode_linear_adapter.py adapters/fusioncode_polygon_adapter.py agent/tooling.py agent/executor.py tests/test_fusioncode_linear_water_road.py
git commit -m "feat: add fusioncode road and water primitives"
```

## Task 10: Implement POI And Conflict Primitives

**Files:**
- Create: `E:\vscode\fusionAgent\fusion_algorithms\poi_fusion.py`
- Modify: `E:\vscode\fusionAgent\fusion_algorithms\quality.py`
- Create: `E:\vscode\fusionAgent\adapters\fusioncode_poi_adapter.py`
- Modify: `E:\vscode\fusionAgent\agent\tooling.py`
- Modify: `E:\vscode\fusionAgent\agent\executor.py`
- Test: `E:\vscode\fusionAgent\tests\test_fusioncode_poi.py`

- [ ] **Step 1: Write POI tests**

Create small POI tables with `GeoHash`, name, and source columns. Assert that:

- same geohash matches directly
- neighbor geohash matches when `neighbor_rings >= 1`
- source priority controls retained attributes
- unmatched POIs appear in the remaining output artifact.

- [ ] **Step 2: Write conflict tests**

Use two overlapping polygons and assert `detect_spatial_conflicts()` returns conflict records when overlap area exceeds `overlap_area_min`.

- [ ] **Step 3: Implement POI primitives**

Implement:

- `build_geohash_candidates()`
- `match_poi_neighbors()`
- `merge_poi_by_name_source_priority()`
- `run_poi_geohash_priority_fusion()`

Use `PiPei()` as behavior reference, not as a single runtime black box.

- [ ] **Step 4: Implement conflict primitive**

Implement `detect_spatial_conflicts(gdf, params)` around `MapTileTool\FusionTool\conflict.py::detect_conflicts()` with explicit parameters and normalized output fields.

- [ ] **Step 5: Run tests**

Run: `pytest E:\vscode\fusionAgent\tests\test_fusioncode_poi.py -q`

Expected: PASS.

- [ ] **Step 6: Commit POI/conflict primitives**

Run:

```powershell
git add fusion_algorithms/poi_fusion.py fusion_algorithms/quality.py adapters/fusioncode_poi_adapter.py agent/tooling.py agent/executor.py tests/test_fusioncode_poi.py
git commit -m "feat: add fusioncode poi and conflict primitives"
```

## Task 11: Update Planning Context, Source Catalog, And Validator

**Files:**
- Modify: `E:\vscode\fusionAgent\kg\source_catalog.py`
- Modify: `E:\vscode\fusionAgent\agent\retriever.py`
- Modify: `E:\vscode\fusionAgent\agent\validator.py`
- Modify: `E:\vscode\fusionAgent\services\input_acquisition_service.py`
- Modify: `E:\vscode\fusionAgent\services\agent_run_service.py`
- Test: existing planner, validator and run-service tests plus new focused tests in `E:\vscode\fusionAgent\tests\test_fusioncode_executor_handlers.py`

- [ ] **Step 1: Write planning tests**

Add tests asserting:

- building jobs with multiple vector sources select `wp.building.drs4br.decomposed.v1`
- raster sources add optional presence and height steps instead of reserved warnings
- missing raster sources keep raster steps optional and plan remains valid
- a reserved compatibility alias is repaired or expanded to executable replacement.

- [ ] **Step 2: Update source catalog**

Mark local vector source sets and building rasters with metadata:

```python
metadata={
    "runtime_status": "runtime_candidate",
    "source_form": "raster",
    "artifact_role": "building_height",
}
```

- [ ] **Step 3: Update retriever reserved hints**

Change the old reserved hint logic so it emits:

- executable workflow hint for `algo.fusion.building.multi_source.decomposed.v1`
- optional raster hint for `algo.validate.building.presence_raster.v1`
- optional raster hint for `algo.enrich.building.height_from_raster.v1`
- fallback warning only when the required artifact is absent.

- [ ] **Step 4: Update validator**

Allow a task to consume prior step outputs through `depends_on` and allow named artifact inputs described in `task.input.parameters`. Keep fail-closed behavior for unknown algorithms, unknown sources, and compatibility aliases that were not expanded.

- [ ] **Step 5: Update run service**

Persist each decomposed step event with:

- `algorithm_id`
- input artifact ids
- output artifact path
- parameter hash
- lineage summary
- optional `effective_algorithm_id` when a compatibility alias expands.

- [ ] **Step 6: Run planning and service tests**

Run:

```powershell
pytest E:\vscode\fusionAgent\tests\test_planner_context.py E:\vscode\fusionAgent\tests\test_workflow_validator.py E:\vscode\fusionAgent\tests\test_agent_run_service_enhancements.py E:\vscode\fusionAgent\tests\test_fusioncode_executor_handlers.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit planning integration**

Run:

```powershell
git add kg/source_catalog.py agent/retriever.py agent/validator.py services/input_acquisition_service.py services/agent_run_service.py tests/test_planner_context.py tests/test_workflow_validator.py tests/test_agent_run_service_enhancements.py tests/test_fusioncode_executor_handlers.py
git commit -m "feat: plan decomposed fusioncode workflows"
```

## Task 12: Add Parity And Smoke Verification

**Files:**
- Create: `E:\vscode\fusionAgent\tests\test_fusioncode_parity_smoke.py`
- Modify: `E:\vscode\fusionAgent\scripts\eval_harness.py` if benchmark discovery needs new algorithm ids

- [ ] **Step 1: Write synthetic smoke tests**

Create minimal synthetic GeoDataFrames for:

- two overlapping buildings with one road context line
- two nearly identical road segments
- two overlapping water polygons
- POI records with same and neighboring geohashes

Assert every decomposed workflow returns a path or GeoDataFrame with non-empty output, valid geometry, and lineage.

- [ ] **Step 2: Write parity test for building composite**

Use a small local fixture. Compare decomposed building composite output with `execute_v8_fusion()` reference on:

- feature count within a fixed tolerance
- source lineage fields present
- valid geometries
- no call to `run_full_pipeline()`

- [ ] **Step 3: Run smoke tests**

Run: `pytest E:\vscode\fusionAgent\tests\test_fusioncode_parity_smoke.py -q`

Expected: PASS.

- [ ] **Step 4: Run focused regression set**

Run:

```powershell
pytest E:\vscode\fusionAgent\tests\test_fusioncode_* E:\vscode\fusionAgent\tests\test_tool_registry.py E:\vscode\fusionAgent\tests\test_kg_parameter_specs.py E:\vscode\fusionAgent\tests\test_workflow_validator.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit smoke coverage**

Run:

```powershell
git add tests/test_fusioncode_parity_smoke.py scripts/eval_harness.py
git commit -m "test: add fusioncode decomposed workflow smoke coverage"
```

## Task 13: Update Operations Documentation

**Files:**
- Modify: `E:\vscode\fusionAgent\docs\v2-operations.md`
- Create: `E:\vscode\fusionAgent\docs\fusioncode-algorithm-library.md`

- [ ] **Step 1: Document algorithm library architecture**

`docs\fusioncode-algorithm-library.md` must include:

- source inventory table
- KG data type list
- algorithm id list
- parameter groups
- workflow pattern diagrams
- distinction between compatibility composites and primitive executable nodes
- statement that `run_full_pipeline()` is retained only as a parity reference.

- [ ] **Step 2: Update operations doc**

Replace statements that height extraction and true multi-source building fusion are reserved with the executable decomposed workflow and its prerequisites.

- [ ] **Step 3: Run docs-related tests**

Run: `pytest E:\vscode\fusionAgent\tests\test_planner_context.py E:\vscode\fusionAgent\tests\test_api_kg.py -q`

Expected: PASS.

- [ ] **Step 4: Commit docs**

Run:

```powershell
git add docs/v2-operations.md docs/fusioncode-algorithm-library.md
git commit -m "docs: describe fusioncode algorithm library integration"
```

## Task 14: Final Verification

**Files:**
- No new files unless tests reveal a specific defect.

- [ ] **Step 1: Run full test suite**

Run: `pytest E:\vscode\fusionAgent\tests -q`

Expected: PASS.

- [ ] **Step 2: Run focused source inventory check**

Run: `pytest E:\vscode\fusionAgent\tests\test_fusioncode_inventory_contract.py -q`

Expected: PASS.

- [ ] **Step 3: Inspect git status**

Run: `git status --short`

Expected: changes only from this implementation plus the pre-existing unrelated `?? runs/benin-source-profile.json`.

- [ ] **Step 4: Produce execution summary**

Summarize:

- which `fusioncode` functions are now represented by KG nodes
- which parameters are queryable through KG
- which workflows are executable
- which tests passed
- any remaining limitations tied to missing local data or optional rasters.

## Self-Review

- Spec coverage: The plan covers full `fusioncode` scope: building, roads, water lines, water polygons, POI, conflicts, quality, raster presence and raster height. It explicitly avoids a monolithic `run_full_pipeline()` runtime abstraction.
- Parameter decoupling: Matching thresholds, raster thresholds, optimization weights, line matching constants, polygon overlap thresholds, POI matching options and conflict settings are all assigned to KG parameter specs.
- KG storage: The plan adds data type nodes, algorithm nodes, parameter specs and workflow patterns. Reserved capabilities become compatibility aliases with executable replacements.
- Execution path: The plan extends execution context for named source sets and rasters, registers handlers, validates dependent intermediate data types and stores step lineage.
- Test discipline: Each implementation task starts with tests, runs focused tests, and includes a commit checkpoint.
