# FusionAgent 唯一活跃主计划

**状态**: Active  
**生效日期**: 2026-05-13  
**执行规则**: 从本文件生效起，`docs/superpowers/plans/` 根目录只允许保留这一份活跃计划。后续新增 backlog 必须先并入本文件，再执行；`docs/superpowers/plans/done/` 中的文档只保留历史审计价值，不再作为执行入口。

## 0. 2026-05-15 优先级重排

从 2026-05-15 起，活跃执行队列只保留以下两条主线；其他未完成目标暂时不列入计划，也不再占用当前执行顺序：

1. 将知识图谱与智能体结构完善到“论文理想本体的完全闭合版”。
2. 实现国家级的多源建筑物、道路、水系和 POI 自动化融合，并把“数据获取 -> AOI/全国范围裁剪 -> 规范化 -> 融合 -> 结果产出 -> inspection/evidence”打通为一条可重复执行的全线链路。

### 0.1 当前唯一激活范围

- 只执行 `Track A` 与 `Track B`。
- 本文件后文已有 Phase A-F 与 thesis/history 内容，后续仅作为证据索引和背景约束，不再构成当前待办队列。
- 只有当 `Track A` 与 `Track B` 都完成后，才允许重新讨论其他 backlog 是否回到活跃计划。

### 0.2 Track A: 论文理想本体完全闭合版

#### 目标定义

把当前“能运行的 KG/Agent 子集”补成“论文与运行时一一对应的闭合本体”，至少覆盖以下对象、关系、约束与可视化读面：

- 核心三元：
  - `Algorithm`
  - `Task`
  - `Data`
- 场景约束层：
  - `ScenarioProfile`
  - `OutputRequirement`
  - `QoSPolicy`
  - `DataNeed`
- 智能体运行层：
  - `TaskBundle`
  - `WorkflowPattern`
  - `PatternStep`
  - `Transform`
  - `RepairStrategy`
  - `DurableLearning / ExecutionFeedback`
- 闭合关系：
  - `task -> consumes/produces data`
  - `algorithm -> solves task`
  - `scenario -> activates tasks / output requirement / qos`
  - `pattern -> composed_of steps`
  - `step -> uses algorithm / input_type / output_type / source`
  - `transform graph -> reachable / optional / reserved`
  - `run evidence -> writes back to memory`

#### 当前已确认缺口

- `kg.models` 已有 `TaskNode`、`ScenarioProfileNode`，但仍缺少显式 `TaskBundle`、`OutputRequirement`、`QoSPolicy` 等论文本体对象。
- `services/kg_graph_service.py` 当前 overview graph 只暴露 `workflow_pattern / algorithm / data_source`，还没有把 `data_type / task / scenario_profile / output_schema_policy / transform edge / parameter spec / durable learning` 一起纳入统一图视图。
- `tests/test_ontology_closure.py` 当前主要保证“seed 引用不悬空”，还没有保证“论文本体对象齐全、关系齐全、图视图闭合、planner/validator/executor 实际消费同一套语义对象”。
- `kg/seed.py` 仍保留大量 `reservation_only` / legacy / metadata-only 节点，需要重新梳理哪些属于闭合本体中的正式节点，哪些只应保留为 bounded future seam。

#### 执行阶段

##### 2026-05-18 进度核实

- [x] A1. 本体建模收口
- [x] A2. Seed 闭合与关系闭合
- [x] A3. 图服务与 operator 读面闭合
- [x] A4. Agent 结构与论文本体对齐
- [x] A5. 闭合门禁
- 2026-05-18 fresh verification:
  - `python -m pytest -q tests/test_ontology_closure.py tests/test_kg_graph_service.py tests/test_api_kg.py tests/test_check_kg_contract.py`
  - 结果：`17 passed in 3.88s`

##### A1. 本体建模收口

- 在 `kg.models`、`schemas/agent.py`、`schemas/kg_graph.py` 中补齐最小必要对象：
  - `TaskBundle`
  - `OutputRequirement`
  - `QoSPolicy`
  - 必要时增加 `DataNeed` / `ScenarioConstraint`
- 明确这些对象与现有 `RunCreateRequest`、`WorkflowPlan`、`WorkflowTask` 的映射，避免论文对象成为只写文档不进运行时的“悬空层”。

##### A2. Seed 闭合与关系闭合

- 扩展 `kg/seed.py`，让 seed 不只包含“节点存在”，还显式包含：
  - task-data 输入输出关系
  - scenario-task 激活关系
  - output requirement / qos policy 默认绑定
  - transform reachability
  - repair / fallback / durable learning 的运行期挂点
- 区分三类节点：
  - `runtime_supported`
  - `research_utility`
  - `reservation_only`

##### A3. 图服务与 operator 读面闭合

- 扩展 `services/kg_graph_service.py` 与 `/api/routers/kg.py`，至少提供两类闭合视图：
  - `overview_closure_graph`
  - `runtime_path_graph`
- 前者用于看“论文理想本体是否闭合”，后者用于看“某次 run 在闭合本体中的真实走法”。

##### A4. Agent 结构与论文本体对齐

- 梳理并固定：
  - `perception`
  - `reasoning/planning`
  - `validation/policy`
  - `action/healing`
  - `audit/evolution`
- 确保这些层都能在代码中回链到具体模块，而不是只存在于论文叙事。

##### A5. 闭合门禁

- 把当前 `tests/test_ontology_closure.py` 升级为多层 gate：
  - seed 闭合
  - object coverage 闭合
  - relation coverage 闭合
  - graph API 闭合
  - planner/runtime consumption 闭合

#### Track A 完成判定

- 论文理想本体中的核心对象与关系都在 live 模型、seed、graph service、API 和测试中出现。
- 任一论文主张都能从 `实体 -> 关系 -> runtime module -> evidence/test` 回链。
- 不再出现“论文说有该层，运行时没有实体；或代码有实体，图谱/论文里没有位置”的双向悬空。

### 0.3 Track B: 国家级多源融合全线贯通

#### 目标定义

在同一套共享 runtime 下，把国家级 AOI 的四个主题做成可重复执行的自动化链路：

- building
- road
- water
- poi

链路必须覆盖：

`source discovery -> official/manual source acquisition -> cache/preload -> AOI or national clip -> normalization -> fusion -> output schema -> artifact/inspection -> evidence freeze`

#### 当前已确认基线

- 已稳定自动化或半自动化：
  - OSM/Geofabrik 原始矢量：`raw.osm.building`、`raw.osm.road`、`raw.osm.water`、`raw.osm.poi`
  - Microsoft Global ML Building Footprints：`raw.microsoft.building`
- 仍以本地手工/恢复数据为主：
  - `raw.google.building`
  - `raw.openbuildingmap.building`
  - `raw.google.open_buildings.vector`
  - `raw.local.water`
  - `raw.gns.poi`
  - `raw.rh.poi`
- 当前 road / water / poi 的“多源”在 source catalog 层仍不充分，尤其 road 仍偏 OSM baseline；要达成“国家级多源自动化融合”，必须先补第二来源与标准化链路，而不是只强化现有单源入口。

#### 执行阶段

##### 2026-05-18 进度核实

- [x] B1. 国家级数据源矩阵定版
- [x] B2. 数据获取链路打通
- [x] B3. 国家级 clip / tiling / stitching 通路统一
- [ ] B4. 多源规范化与融合节点收口
- [ ] B5. 结果与证据闭环
- 2026-05-18 fresh verification:
  - `python -m pytest -q tests/test_national_source_matrix.py tests/test_run_benin_multisource_building_fusion.py tests/test_benchmark_tiled_building.py`
  - 结果：`9 passed in 3.23s`
- 当前判定：
  - `Track A` 已具备 live 模型、graph API 与闭合门禁证据；
  - `Track B` 的 `B1-B3` 已完成，当前主缺口集中在 `B4-B5`。

##### B1. 国家级数据源矩阵定版

按主题先锁定“第一批必须打通”的国家级多源组合：

- Building:
  - `OSM/Geofabrik`
  - `Microsoft Global ML Building Footprints`
  - 本地预载参考源：`Google` / `OpenBuildingMap` / `Google Open Buildings Vector`
- Road:
  - `OSM/Geofabrik`
  - 第二路国家级参考源接入为本阶段硬目标，优先评估 `Overture Transportation`
- Water:
  - `OSM/Geofabrik`
  - 第二路国家级参考源接入为本阶段硬目标，优先评估 `HydroRIVERS / HydroLAKES` 或 `Overture Water`
- POI:
  - `OSM/Geofabrik`
  - `GNS`
  - 视字段对齐复杂度决定是否追加 `Overture Places` 作为第三源

要求先把 source id、格式、裁剪方式、字段映射、license/claim boundary 一次性锁清，再进入实现。

- 2026-05-18：已新增 live `docs/superpowers/specs/2026-05-18-track-b-national-source-matrix.md`，
  并把第一批 building / road / water / poi source contract 回写到
  `kg/track_b_source_contract.py` 与 `kg/source_catalog.py` 元数据；后续 B2-B5
  以这份矩阵为准，不再临时改口径。
- 2026-05-18：B2 live 入口已补到
  `docs/superpowers/specs/2026-05-18-national-source-matrix.md` 与
  `docs/superpowers/specs/2026-05-18-national-source-matrix.json`。
  其中：
  - road 第二来源硬目标固定为 `raw.overture.transportation`
  - water 第二来源硬目标固定为 `raw.hydrorivers.water` +
    `raw.hydrolakes.water`
  - `raw.overture.water` 与 `raw.overture.places` 继续保留为 deferred
    alternative
  - building 的 Google / OpenBuildingMap / Google Open Buildings Vector /
    local Microsoft clip 继续维持 `manual_preload_required` 边界

##### B2. 数据获取链路打通

- 统一区分三类 source：
  - `official_remote_supported`
  - `manual_preload_required`
  - `reservation_only / deferred`
- 扩展 `services/source_asset_service.py`、`services/raw_vector_source_service.py`、`services/input_acquisition_service.py`：
  - building 继续保留 `Geofabrik + Microsoft` 自动下载链
  - road / water / poi 新增第二来源的 bbox/national materialization 逻辑
  - 明确 `source_mode`、`cache_hit`、`coverage_status`、`fallback_from_source_id`
- 2026-05-18 进度补记：
  - 已将 `raw.hydrorivers.water` 与 `raw.hydrolakes.water` 接入
    `services/source_asset_service.py` 的官方远程 materialization，
    并同步纳入 `kg/source_catalog.py` 与 `services/raw_vector_source_service.py`
    可消费范围。
  - 已将默认 `catalog.flood.water` reference 从本地样例 `raw.local.water`
    收口到国家级 polygon 第二来源 `raw.hydrolakes.water`；`raw.local.water`
    继续保留为手工参考源，不再承担默认 task-driven water bundle 的唯一第二来源语义。
  - 已将 `raw.overture.transportation` 接入 `services/source_asset_service.py`
    的 AOI 级 live materializer，并同步纳入 `kg/source_catalog.py` 与
    `services/raw_vector_source_service.py` 可消费范围；默认下载路径走
    Overture 官方 CLI（`overturemaps` 或 `uvx overturemaps`），测试侧用
    本地 GeoJSON fixture 做 deterministic 验证。
  - 已将 `catalog.flood.road` 从 `OSM baseline` 收口到 `OSM + Overture`
    双源 bundle：`kg/source_catalog.py` 已改为 `osm_ref_pair`，
    `services/local_bundle_catalog.py` / `services/input_acquisition_service.py`
    的 task-driven acquisition 真实链可同时产出 OSM 与 Overture road
    参考包，不再生成 empty ref 占位。
  - fresh verification:
    - `python -m pytest -q tests/test_source_asset_service.py::test_source_asset_service_materializes_hydrorivers_clip_from_remote_zip tests/test_source_asset_service.py::test_source_asset_service_materializes_hydrolakes_clip_from_remote_zip tests/test_raw_vector_source_service.py::test_raw_vector_source_service_supports_hydrosheds_water_sources_via_source_asset_service tests/test_kg_repository_enhancements.py::test_repository_exposes_bundle_and_raw_sources_for_catalog_expansion tests/test_national_source_matrix.py`
    - 结果：`6 passed in 2.31s`
    - `python -m pytest -q tests/test_ontology_closure.py::test_water_seed_records_exist tests/test_planner_context.py::test_planner_context_exposes_water_metadata_and_builds_water_plan tests/test_kg_repository_enhancements.py::test_repository_exposes_bundle_and_raw_sources_for_catalog_expansion tests/test_local_bundle_catalog.py::test_local_bundle_catalog_materializes_flood_water_bundle_from_shared_provider_path tests/test_source_coverage_fallback.py::test_water_catalog_accepts_empty_reference_when_osm_has_coverage`
    - 结果：`5 passed in 1.72s`
    - `python -m pytest -q tests/test_source_asset_service.py::test_source_asset_service_materializes_overture_transportation_clip_from_remote_geojson tests/test_raw_vector_source_service.py::test_raw_vector_source_service_supports_overture_transportation_via_source_asset_service tests/test_kg_repository_enhancements.py::test_repository_exposes_bundle_and_raw_sources_for_catalog_expansion`
    - 结果：`3 passed in 2.12s`
    - `python -m pytest -q tests/test_kg_repository_enhancements.py::test_repository_exposes_bundle_and_raw_sources_for_catalog_expansion tests/test_local_bundle_catalog.py::test_local_bundle_catalog_materializes_flood_road_bundle_from_osm_and_overture tests/test_agent_run_service_enhancements.py::test_agent_run_service_road_task_driven_auto_uses_real_shared_acquisition_chain`
    - 结果：`3 passed in 2.10s`
    - `python -m pytest -q tests/test_source_asset_service.py tests/test_raw_vector_source_service.py tests/test_local_bundle_catalog.py tests/test_input_acquisition_service.py tests/test_source_coverage_fallback.py tests/test_kg_repository_enhancements.py tests/test_agent_run_service_enhancements.py tests/test_ontology_closure.py tests/test_planner_context.py tests/test_national_source_matrix.py tests/test_neo4j_bootstrap.py`
    - 结果：`129 passed, 8 warnings in 19.13s`
  - 当前仍未完成：
    - `catalog.earthquake.road` / `catalog.typhoon.road` 仍保留 OSM baseline，
      尚未决定是否在本轮 B2 一并提升到 `OSM + Overture`
    - national 级 road / water / poi clip/stitching 统一仍待 B3
  - 2026-05-19 结论更新：
    - `catalog.earthquake.road` / `catalog.typhoon.road` 也已同步收口到
      `OSM + Overture` 双源 bundle；
    - 以 `source asset -> raw vector -> local bundle catalog -> input acquisition
      -> agent run` 为主线的 B2 fresh verification 已覆盖通过，可将 `B2`
      正式判定为完成。
  - 2026-05-19 fresh verification:
    - `python -m pytest -q tests/test_source_asset_service.py tests/test_raw_vector_source_service.py tests/test_local_bundle_catalog.py tests/test_input_acquisition_service.py tests/test_kg_repository_enhancements.py tests/test_agent_run_service_enhancements.py tests/test_national_source_matrix.py tests/test_neo4j_bootstrap.py`
    - 结果：`99 passed, 8 warnings in 17.22s`

- 2026-05-18：已完成 B2 第一层 source registration，把 `raw.overture.road`、`raw.hydrorivers.water`、`raw.hydrolakes.water` 加入 raw source contract、catalog metadata 与 local resolver 入口；后续仍需继续做 bundle/provider 接线与 national clip 运行证据。
- 2026-05-18：已把 `services/source_asset_service.py` 接到同一套 Track B raw source locator contract，统一支持 `raw.overture.road`、`raw.local.water`、`raw.hydrorivers.water`、`raw.hydrolakes.water` 以及递归定位的 `raw.gns.poi` / `raw.rh.poi` 本地预载解析；`can_materialize()` 与 `materialize_source_assets.py` 入口不再只认识早期 building/OSM 资产。

##### B3. 国家级 clip / tiling / stitching 通路统一

- building 继续用现有 tiled runtime 作为模板。
- road / water / poi 补齐国家级 clip、分块、重组与 inspection 摘要，不允许只有 building 具备大 AOI 能力。
- `tile manifest -> source profile -> selected sources -> stitched artifact -> inspection_summary` 必须对四个主题尽量统一。
- 2026-05-19：已把 `scripts/benchmark_tiled_building.py` 与 `scripts/run_benin_multisource_building_fusion.py` 的 building 模板证据面补齐到同一条 B3 contract：两者现在都会显式落 `selected_sources.json` 与 `stitched_artifact.json`，且 `tile_manifest.json` 统一带 `manifest_mode` 与 `tile_count`，避免 building 与 road / water / poi 在 operator-readable 证据链上继续漂移。
- 2026-05-19：`services/track_b_national_scale_service.py` 现已为 road / water / poi 显式落 `stitched_artifact.json`，并把该证据节点写入 `inspection_summary.json` 与 live freeze，引导 national-scale utility 与 building 模板沿同一条 stitched-artifact contract 收口。
- 2026-05-18：`scripts/smoke_agentic_region.py` 已新增 `--evidence-dir`，可直接把 shared runtime 的 road / water / poi / building smoke inspection 归档为统一的 `inspection.json`、`source_profile_snapshot.json`、`selected_sources.json`、`tile_manifest.json`、`inspection_summary.json`。其中 smoke 的 `tile_manifest.json` 明确标记为 `single_request_aoi`，用于 operator-readable bounded evidence，而不是伪装成 building 的真实 tiled runtime。
- 2026-05-18：已新增 `services/track_b_national_scale_service.py` 与 `scripts/build_track_b_national_evidence.py`，把 road / water / poi 的 national clip、tile manifest、normalized artifacts、stitch output 与 inspection summary 收口到同一套 utility；对应 live freeze 见 `docs/superpowers/specs/2026-05-18-track-b-national-scale-evidence-freeze.json`。
- 2026-05-19 fresh verification:
  - `python -m pytest -q tests/test_benchmark_tiled_building.py tests/test_run_benin_multisource_building_fusion.py tests/test_scale_validation_doc_alignment.py tests/test_capability_inventory_matrix.py tests/test_track_b_national_scale_service.py tests/test_track_b_source_matrix.py tests/test_national_source_matrix.py`
  - 结果：`20 passed in 375.51s`

##### B4. 多源规范化与融合节点收口

- building: 从当前 `OSM + Microsoft` 扩到真正多源，并把人工预载源纳入统一 source-set。
- road: 从单源 baseline 升级到双源以上的 segment/topology fusion。
- water: 明确 line / polygon 两类国家级来源与融合落点。
- poi: 把 `OSM + GNS (+ optional RH/Overture)` 规范化到统一 POI schema，再进入去重与优先级融合。
- 2026-05-18：已新增 `services/track_b_source_normalization.py`，按 `fields.road.osm`、`fields.road.overture_transportation`、`fields.water.*`、`fields.poi.*` 真实 profile 生成统一 canonical 字段；当前 freeze 已落出 `source_feature_id`、`road_class`、`water_ty`、`category`、`GeoHash` 等规范化证据，并对 `raw.hydrorivers.water`、`raw.hydrolakes.water`、`raw.rh.poi` 保留 supplemental normalized artifacts。

##### B5. 结果与证据闭环

- 每个主题至少给出 1 条国家级或准国家级 smoke/bounded run：
  - 有 source acquisition 证据
  - 有 artifact
  - 有 inspection
  - 有 operator 可读摘要
  - 有 freeze 或 regression hook
- 2026-05-18：`tests/test_smoke_agentic_region.py` 已把上述 smoke evidence bundle 落盘契约纳入回归，当前至少保证 water 与 bounded poi 的 operator-readable 摘要、claim_state 和 source-selection 证据不会回退；road / building 复用同一路径。
- 2026-05-18：已在隔离 `8010` runtime 上生成 fresh Track B smoke freeze，见 `docs/superpowers/specs/2026-05-18-track-b-smoke-evidence-freeze-8010.json`。其中 water / poi 直接通过标准 query 成功，road 通过 `road for Gilgit city, Pakistan` 成功生成 AOI-bounded evidence；对应 smoke evidence 目录位于 `runs/2026-05-18-smoke-evidence/`。本轮 road 还顺带补齐了两个 live blocker：Windows HTTPS 下载链从 `httpx -> curl -> urllib` 的回退，以及缺失手工 Overture 预载时 `catalog.*.road` version token 不再提前失败。
- 2026-05-18：已生成真实 repo-local national-scale freeze，见 `docs/superpowers/specs/2026-05-18-track-b-national-scale-evidence-freeze.json`。当前 road 基于 `raw.osm.road + raw.overture.road` 记录为 `national_scale_partial_reference`，因为 Overture 预载缺失；water 基于 `raw.osm.water + raw.local.water` 记录为 `national_scale_supported`，同时附带 `raw.hydrorivers.water` / `raw.hydrolakes.water` 的 supplemental normalization 证据；poi 基于 `raw.osm.poi + raw.gns.poi` 记录为 `national_scale_supported`，同时附带 `raw.rh.poi` supplemental normalization 证据。

#### 预下载清单与指定目录

以下数据建议由你先手工下载并放到仓库当前约定目录，因为它们要么当前仓库未实现官方稳定远程化，要么全国范围临时下载/转换更容易失败：

1. `raw.google.building`
   - 目录：`E:\vscode\fusionAgent\Data\buildings\Google\`
   - 规则：目录下放可直接读取的 shapefile bundle，服务会取该目录下第一个 `.shp`
2. `raw.openbuildingmap.building`
   - 目录：`E:\vscode\fusionAgent\Data\buildings\OpenBuildingMap\`
   - 规则：同上
3. `raw.google.open_buildings.vector`
   - 目录：`E:\vscode\fusionAgent\Data\buildings\GoogleOpenBuildingsVector\`
   - 规则：同上
4. `raw.local.microsoft.building`
   - 目录：`E:\vscode\fusionAgent\Data\buildings\MicrosoftLocal\`
   - 用途：保留一个你手工筛好的本地 Microsoft national clip / cache 版本，避免在线多分块拉取反复失败
5. `raw.local.water`
   - 目录：`E:\vscode\fusionAgent\Data\water\`
   - 当前 repo 实际样本：`布隆迪湖泊.shp`
6. `raw.overture.road`
   - 目录：`E:\vscode\fusionAgent\Data\roads\Overture\`
   - 规则：目录下放可被 loader 识别的 Overture Transportation national extract；如果缺失，这一轮 national evidence 只能记录为 `national_scale_partial_reference`
7. `raw.hydrorivers.water`
   - 文件：`E:\vscode\fusionAgent\Data\water\BDI.shp`
   - 用途：作为 Track B 第一批国家级水系线参考源
8. `raw.hydrolakes.water`
   - 文件：`E:\vscode\fusionAgent\Data\water\布隆迪湖泊.shp`
   - 用途：作为 Track B 第一批国家级湖泊面参考源
9. `raw.gns.poi`
   - 目录：`E:\vscode\fusionAgent\Data\POI\<国家或地区>\`
   - 文件名要求：路径下需要有 `GNS.shp`
10. `raw.rh.poi`
   - 目录：`E:\vscode\fusionAgent\Data\POI\<国家或地区>\`
   - 文件名要求：路径下需要有 `RH.shp`

以下数据可继续走自动远程下载，但如果你准备直接做国家级大范围实验，也建议提前预热到缓存目录，减少运行中断：

- `raw.osm.building`
- `raw.osm.road`
- `raw.osm.water`
- `raw.osm.poi`
- `raw.microsoft.building`

预热脚本仍使用：

```powershell
python scripts/materialize_source_assets.py --source raw.osm.building --source raw.microsoft.building
```

默认缓存目录：

- `E:\vscode\fusionAgent\runs\source-assets\`

#### 需要你优先手工预载的高风险数据

优先级从高到低：

1. `Google / OpenBuildingMap / Google Open Buildings Vector`
   - 当前仓库没有稳定官方远程 materializer，属于手工预载优先级最高的数据。
2. `GNS / RH`
   - GNS 虽然有官方可下载文件，但当前仓库并未打通“官方下载 -> 转换为本地 shapefile -> 直接进入 POI bundle”的自动链；RH 更是本地样例源。
3. `raw.overture.road`
   - 当前 national freeze 已把它锁为第二道路源，但本地 repo 快照仍没有对应预载；要把 road 从 `partial_reference` 提升到真正双源 national support，优先补这一份。
4. `raw.local.water / raw.hydrorivers.water / raw.hydrolakes.water`
   - 当前水系 national freeze 已证明本地 clip 可以走通，但三者都仍属于本地预载边界，没有官方自动下载链。
5. `raw.microsoft.building`
   - 已支持自动下载，但国家级时往往要拉多个 country-quadkey 分块，体量大、耗时长，建议做正式 national run 前先预热或手工缓存一份。

#### Track B 完成判定

- building / road / water / poi 四个主题都能从 source acquisition 自动走到 fusion result。
- 至少每个主题都具备“国家级或准国家级 AOI”的一条真实链路，而不是只有本地样例。
- 高风险数据源都已被明确分流到手工预载目录或官方自动下载目录，不再在运行时临时碰运气。

### 0.4 当前执行顺序

严格按以下顺序推进，不并行发散其他 backlog：

1. 先完成 `Track A / A1-A2`，把论文本体对象和 seed 关系补闭合。
2. 紧接着做 `Track B / B1`，锁定四个主题的国家级多源矩阵和预载策略。
3. 然后交替推进：
   - `Track A / A3-A5`
   - `Track B / B2-B5`
4. 最后统一刷新：
   - KG closure gates
   - national-scale evidence freeze
   - thesis claims ledger 中与这两条主线相关的 live evidence

## 1. 执行宪章

本文件的目标不是重新发散出新的子计划，而是把当前仓库里仍然需要继续完成的工作收敛成一条可持续执行到结束的主线。

执行时必须遵守以下规则：

- 不再新增第二份活跃计划文档。
- `done/` 中的旧计划不能再被当作当前待办清单直接使用；如需吸收内容，只能回写到本文件。
- `docs/superpowers/specs/done/` 可以保留历史快照，但任何被测试、脚本、README、runbook、论文证据链直接消费的规范/证据文件，必须回到 live 路径，而不是继续停留在 `done/`。
- 前端证据面增长、图后端迁移试验、`trajectory-to-road` 可执行化不进入当前执行阶段。

## 2. 已完成基线

以下内容视为当前稳定基线，除非出现新的失败证据，否则不回退为“未完成”：

- 稳定主题边界仍然是 `building`、`road`、`water`、bounded `poi`。
- 共享运行骨架仍然是 `planner -> validator -> executor -> healing/replan -> writeback`。
- 共享证据契约仍然是 `run.json`、`plan.json`、`validation.json`、`audit.jsonl` 与 artifact bundle。
- Phase 1 与 Phase 2 已经关闭；此前复核记录为：
  - focused Phase 2 slice: `57 passed in 2.46s`
  - broader integration/runtime slice: `121 passed, 10 warnings in 13.20s`
- 代码侧已经存在并通过聚焦测试的能力，不应再按“从零实现”规划：
  - `services/run_registry_service.py`
  - `services/operator_read_model_service.py`
  - `services/artifact_preview_service.py`
  - `schemas/scenario_manifest.py` 中的 `capability_checks`
  - `scripts/scenario_eval_harness.py`
  - `services/source_profile_service.py`
  - `services/tile_partition_service.py`
  - `services/tiled_building_runtime_service.py`
  - `fusion_algorithms/` 与 `adapters/fusioncode_*`

### 2026-05-13 现状诊断

本主计划写入时，仓库的主要真实缺口不是“代码骨架不存在”，而是“活跃规范/证据文件被整体归档后，校验入口失效，且能力主张与文档状态不一致”。已确认的直接证据如下：

- `python scripts/run_no_ui_maturity_check.py` 失败，原因是 `docs/superpowers/specs/` 下多份必需 live 文件缺失。
- `python -m pytest -q tests/test_scenario_manifest_service.py tests/test_scenario_eval_harness.py tests/test_run_registry_service.py tests/test_operator_read_model_service.py tests/test_artifact_preview_service.py tests/test_no_ui_maturity_check.py` 的结果是 `34 passed, 1 failed`，唯一失败项是缺失 `docs/superpowers/specs/2026-04-21-scenario-eval-manifest.json`。
- `python -m pytest -q tests/test_source_profile_service.py tests/test_tile_partition_service.py tests/test_tiled_building_runtime_service.py tests/test_raster_cli.py` 的结果是 `10 passed`。
- `python -m pytest -q tests/test_fusioncode_inventory_contract.py tests/test_fusioncode_contracts.py tests/test_fusioncode_building_raster.py tests/test_fusioncode_building_v8_decomposition.py tests/test_fusioncode_linear_water_road.py tests/test_fusioncode_poi.py tests/test_fusioncode_executor_handlers.py tests/test_fusioncode_kg_metadata.py` 的结果是 `24 passed`。

结论：后续工作应优先做 live 规范恢复、证据刷新、能力主张收口与论文资产闭环，而不是盲目重写已经存在的实现。

## 3. 历史计划吸收映射

| 历史计划 | 在本主计划中的归属 |
| --- | --- |
| `2026-05-12-fusionagent-master-execution-plan.md` | 本文件整体吸收，旧文件仅保留历史记录 |
| `2026-04-21-no-ui-mature-agent-plan.md` | Phase A / Phase B |
| `2026-04-21-scenario-regression-set-plan.md` | Phase B |
| `2026-04-23-system-next-improvements.md` | 已完成基线 |
| `2026-05-06-fusionagent-agent-capability-update-roadmap.md` | 已完成基线 |
| `2026-05-09-kg-closure-and-graph-backend-roadmap.md` | 已完成基线 |
| `2026-04-27-benin-building-runtime-preparation.md` | Phase C |
| `2026-04-29-fusioncode-algorithm-library-kg-integration.md` | Phase D |
| `2026-05-06-fusionagent-thesis-research-design-roadmap.md` | Phase E |

## 4. Phase A: live 规范/证据路径恢复

### 目标

把当前误归档到 `docs/superpowers/specs/done/` 的活跃规范、评测清单、freeze 文件与 capability 文档恢复为 live 可消费状态，使测试、脚本、README、runbook、论文证据链重新使用统一根路径。

### 涉及范围

- `docs/superpowers/specs/`
- `docs/superpowers/specs/done/`
- `scripts/run_no_ui_maturity_check.py`
- `scripts/freeze_paper_evidence.py`
- 所有直接读取上述 live spec 路径的测试

### 执行清单

- [x] A1. 明确 `specs` 的 live/archive 规则，并写成一个短说明文件：
  - `docs/superpowers/specs/README.md` 或 `docs/superpowers/specs/active-index.md`
  - 说明哪些文件是当前执行链必需 live 文件，哪些文件只是历史快照
- [x] A2. 从 `docs/superpowers/specs/done/` 非破坏性恢复以下 live 文件集合：
  - no-ui maturity:
    - `2026-04-21-no-ui-maturity-target.md`
    - `2026-04-21-no-ui-maturity-gap-ledger.md`
    - `2026-04-21-no-ui-maturity-evidence-freeze.json`
    - `2026-04-21-no-ui-maturity-evidence-freeze.md`
    - `2026-04-21-operator-read-model-contract.md`
  - scenario:
    - `2026-04-21-scenario-eval-manifest.json`
    - `2026-04-21-scenario-regression-set-design.md`
    - `2026-04-21-scenario-trigger-proof.md`
    - `2026-04-21-scenario-evidence-freeze.json`
    - `2026-04-21-scenario-evidence-freeze.md`
  - paper evidence:
    - `2026-04-21-paper-experiment-matrix.json`
    - `2026-04-21-paper-evidence-freeze.json`
    - `2026-04-21-paper-evidence-freeze.md`
  - capability/thesis baseline:
    - `2026-05-06-capability-consolidation-review.md`
    - `2026-05-06-capability-inventory.md`
    - `2026-05-06-capability-matrix.json`
    - `2026-05-06-consolidation-backlog.md`
    - `2026-05-06-next-execution-sequence.md`
    - `2026-05-06-redundancy-and-drift-ledger.md`
    - `2026-05-06-related-work-gap-matrix.json`
    - `2026-05-06-related-work-gap-matrix.md`
  - KG/paper baseline evidence:
    - `2026-04-20-evaluation-contract-claim-lock.md`
    - `2026-04-20-evidence-ledger.md`
    - `2026-05-09-kg-closure-gates.md`
    - `2026-05-10-kg-gates-evidence-summary.md`
- [x] A3. 检查并修正所有仍然硬编码为旧 live 路径、但内容已经不再对应的脚本/测试；优先选择“恢复 live 文件”而不是“把脚本改去读 `done/`”。
- [x] A4. 对恢复出的 live 文件做内容核对，确认不是落后的历史版本；如 `done/` 中的快照已经明显过时，则直接在 live 路径重写，不复制旧内容。
- [x] A5. 形成一个最小“当前活跃 spec 索引”，让后续执行知道哪些文档继续参与 Phase B-E。

### 验证

- `python scripts/run_no_ui_maturity_check.py`
- `python -m pytest -q tests/test_scenario_manifest_service.py tests/test_related_work_gap_matrix.py tests/test_capability_inventory_matrix.py tests/test_consolidation_backlog.py tests/test_no_ui_maturity_check.py`

### 完成判定

- 上述命令全部通过。
- `docs/superpowers/specs/` 根目录重新具备当前执行链必需的 live 文件。
- `done/` 仅保留历史快照，不再承担当前脚本入口职责。

### 反模式防护

- 不要把当前仍在使用的 manifest/freeze 继续留在 `done/`。
- 不要在 root 与 `done/` 并行维护两份“都宣称是当前版本”的文档。
- 不要为了省事把测试统一改成读 `done/`，从而让 archive 重新变成活跃入口。

## 5. Phase B: no-ui operator / scenario / maturity 收口

### 目标

在 Phase A 恢复 live 路径之后，把 no-ui operator 面、scenario capability regression、trigger proof 与 maturity evidence 刷新到当前代码基线，形成可持续复核的无界面运行时闭环。

### 涉及范围

- `docs/no-ui-agent-operations.md`
- `docs/superpowers/specs/2026-04-21-*`
- `services/run_registry_service.py`
- `services/operator_read_model_service.py`
- `services/artifact_preview_service.py`
- `services/scenario_trigger_service.py`
- `services/scenario_registry_service.py`
- `scripts/scenario_eval_harness.py`
- `scripts/freeze_scenario_evidence.py`
- `scripts/freeze_no_ui_maturity_evidence.py`
- `scripts/run_no_ui_maturity_check.py`

### 执行清单

- [x] B1. 把 live `scenario-eval-manifest` 与当前 capability 语义对齐：
  - 保留 building / road / water / bounded poi 的 5-case 回归集合
  - water / poi 继续保持 planner-level / bounded claim，不得借机升级为未证实执行能力
  - capability checks 继续以 `required_job_types`、`required_workflow_steps`、`require_aoi_resolved`、`require_task_inputs_resolved`、`require_source_coverage` 为准
- [x] B2. 重新运行 scenario harness，刷新：
  - `tmp/eval/scenario-harness-summary.json`
  - `docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.json`
  - `docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.md`
- [x] B3. 复核并刷新 `2026-04-21-scenario-trigger-proof.md`，确认本地 inbox 触发链与当前 `scenario_registry`、idempotency、failed-event 处理仍一致。
- [x] B4. 用当前实际 API/服务收口 operator contract：
  - run listing
  - runtime summary
  - run inspection
  - run compare
  - scenario listing / detail
  - artifact preview
  并同步更新 `docs/no-ui-agent-operations.md` 与 `2026-04-21-operator-read-model-contract.md`
- [x] B5. 重新生成 no-ui maturity freeze：
  - `2026-04-21-no-ui-maturity-evidence-freeze.json`
  - `2026-04-21-no-ui-maturity-evidence-freeze.md`
- [x] B5.a 2026-05-14 CI 回归修复：
  - GitHub `ci` 失败定位到 `mock-inmemory-tests`
  - 根因确认为 scenario building case 为保留 `aoi_resolved` 证据而放宽 AOI 解析触发范围，误伤 direct bbox run
  - 已引入 `force_aoi_resolution` 显式开关，仅对需要 `require_aoi_resolved` 的 scenario+bbox 组合启用，收回全局副作用
  - 本地验证结果：
    - focused AOI slice: `3 passed`
    - CI 对应 mock/in-memory slice: `89 passed, 8 warnings`
    - scenario/integration 扩展 slice: `22 passed, 2 warnings`
    - `python scripts/run_no_ui_maturity_check.py`: `passed=true`, `static_check_passed=true`
- [x] B6. 在 no-ui maturity gate 真实通过之前，不改 README 定位；若 gate 全通过，再决定是否补充 maturity marker 并清理 prototype-only 残余表述。
  - 2026-05-14：README 中英文入口已补充 no-ui maturity marker，后续以 `python scripts/run_no_ui_maturity_check.py --require-readme-repositioning` 作为定位切换验收门槛。

### 验证

- `python -m pytest -q tests/test_scenario_manifest_service.py tests/test_scenario_eval_harness.py tests/test_run_registry_service.py tests/test_operator_read_model_service.py tests/test_artifact_preview_service.py tests/test_no_ui_maturity_check.py`
- `python -m pytest -q tests/test_api_operator_read_models.py tests/test_api_scenario_registry.py tests/test_api_v2_integration.py`
- `python scripts/run_no_ui_maturity_check.py`
- 如准备切换 README 定位，再运行：`python scripts/run_no_ui_maturity_check.py --require-readme-repositioning`

### 完成判定

- scenario capability regression、trigger proof、operator read surface、maturity freeze 都与当前实现同步。
- no-ui maturity check 至少达到静态通过；只有在 README 真正更新后才追求 repositioning gate 通过。

### 反模式防护

- 不要把“文档存在”误当成“freeze 已刷新”。
- 不要让 `partial` 掩盖缺失 capability evidence 的 case。
- 不要用前端 workbench 替代 no-ui operator contract 的闭环证明。

## 6. Phase C: 面向大规模、多源建筑物数据融合能力的收口

### 目标

把旧“Benin scale preparation”重写为通用的大规模、多源建筑物数据融合能力主线。Benin 只作为验证数据来源之一，不再作为国家特化叙事中心。

### 涉及范围

- `services/source_profile_service.py`
- `services/tile_partition_service.py`
- `services/tiled_building_runtime_service.py`
- `services/agent_run_service.py`
- `services/source_asset_service.py`
- `services/input_acquisition_service.py`
- `scripts/profile_benin_sources.py`
- `scripts/run_benin_multisource_building_fusion.py`
- `docs/fusioncode-algorithm-library.md`
- `docs/v2-operations.md`
- `README.md`
- `README.en.md`
- `docs/superpowers/specs/2026-05-06-capability-inventory.md`
- `docs/superpowers/specs/2026-05-06-capability-matrix.json`

### 执行清单

- [x] C1. 先锁定“当前能稳定声称什么”：
  - 哪些 source-set 形式已稳定支持
  - tiled execution 的输入/输出契约是什么
  - clip cache 与 stitch 结果的证据边界是什么
  - raster presence / raster height 分别处于什么 claim 等级
  - 2026-05-14：已在 `README`、`docs/v2-operations.md`、`docs/fusioncode-algorithm-library.md` 与 capability inventory 中锁定共享 runtime 的 large-AOI `OSM + single-reference` tiled building 路径、tile manifest / stitch 证据面，以及 multi-source+raster 仍属于 research utility 的边界。
- [x] C2. 清理所有 Benin 特化措辞，把阶段目标改写为：
  - 大 AOI building runtime scale-up
  - 多源 building source-set 输入建模
  - tiled execution / cache / stitch
  - 大规模 building benchmarking 与 evidence freeze
  - 2026-05-14：高层 README / operations / algorithm-library 口径已切到通用规模化叙事；残余 Benin 特化脚本名与历史文档引用继续保留到后续收口。
  - 2026-05-15：`docs/v2-operations.md`、`docs/fusioncode-algorithm-library.md`、capability inventory / matrix 已统一声明“Benin 只作为校验数据集示例”，脚本名保留但不再承担国家特化能力叙事。
- [x] C3. 对齐“代码已实现”和“文档仍然保守”的冲突：
  - 如果多源 building vector 路径已可稳定运行，提升其 claim_state
  - 如果 raster height 仍缺少稳定证据，则保持可选/有界，不强行升级
  - 保证 `docs/fusioncode-algorithm-library.md`、capability inventory、README、operations 的说法一致
  - 2026-05-15：live capability inventory / matrix 新增 `building.scale_validation_cleanup_rules`，并继续把 multi-source / raster building 维持在 `research_utility`；shared runtime 与 validation utility 的边界已在 operations、algorithm library、parity ledger 中对齐。
- [x] C4. 补齐通用规模化证据，而不是只保留脚本存在：
  - source profile 产物
  - tile manifest
  - tiled runtime summary
  - stitch 后 artifact 合法性
  - inspection / operator 可读证据
  - 2026-05-14：已新增 `tests/test_benchmark_tiled_building.py` 与扩展 `tests/test_run_benin_multisource_building_fusion.py`，把 `source_profile_snapshot.json`、`tile_manifest.json`、`selected_sources.json`、`timing.json`、`benchmark_summary.md` 等规模化验证产物纳入回归护栏；真实 inspection/operator freeze 级证据仍待后续补齐。
  - 2026-05-15：已恢复 `2026-04-08-benchmark-followup-summary.md` 与 `2026-05-12-building-gitega-micro-msft-neo4j-baseline-8012.json` 等被 live 文档引用的基准 spec 资产到 `docs/superpowers/specs/`，修复 live 账本悬空引用。
  - 2026-05-15：`scripts/benchmark_tiled_building.py` 与 `scripts/run_benin_multisource_building_fusion.py` 现已稳定产出 `inspection_summary.json`，把 `source_profile_snapshot.json`、`tile_manifest.json`、`selected_sources.json`、`timing.json`、`benchmark_summary.md` 与 stitch 后 `artifact_validity` 收敛成 operator-readable 规模化摘要；对应测试、operations wording 与 capability inventory 已同步收口。
- [x] C5. 明确“Benin national script”在文档中的角色：
  - 可以作为规模化验证样例
  - 不能再作为“仅 Benin 专用实验脚本”的孤岛能力叙事
  - 2026-05-14：`scripts/run_benin_multisource_building_fusion.py` 与相关文档已改写为“大规模多源 building 验证样例”，并明确 Benin 只是当前仓库示例数据集。

### 验证

- `python -m pytest -q tests/test_source_profile_service.py tests/test_tile_partition_service.py tests/test_tiled_building_runtime_service.py tests/test_raster_cli.py`
- `python -m pytest -q tests/test_tiled_multisource_building_runtime_service.py tests/test_run_benin_multisource_building_fusion.py`
- 如需要补充运行时闭环，再追加与 `agent_run_service` 相关的 building tiled slice 聚焦测试

### 完成判定

- 文档已不再把该阶段描述为 Benin 特化能力。
- 至少一个大规模、多源 building 路径具备测试、运行契约、证据、操作文档四位一体闭环。
- 可选 raster/height 语义的边界被明确标注，而不是被含混地包装成“全支持”。

### 反模式防护

- 不要把国家数据集名字写成能力本体。
- 不要在没有共享证据契约的情况下把研究脚本直接升级为稳定 runtime 主张。
- 不要为了追求“大规模”而绕过已有 validator / audit / inspection 边界。

## 7. Phase D: `fusioncode` 全量算法库集成收口

### 目标

把 `fusioncode` 全量算法库集成从“代码已经有不少 wrapper 和 KG 节点”推进到“范围清晰、证据清晰、claim_state 清晰”的正式收口状态，并纳入主计划而不是继续挂起。

### 涉及范围

- `fusion_algorithms/`
- `adapters/`
- `agent/executor.py`
- `agent/retriever.py`
- `agent/validator.py`
- `kg/seed.py`
- `kg/source_catalog.py`
- `kg/bootstrap/neo4j_bootstrap.cypher`
- `docs/fusioncode-algorithm-library.md`
- `docs/v2-operations.md`
- `tests/test_fusioncode_*`
- `tests/test_planner_context.py`
- `tests/test_kg_repository_enhancements.py`

### 执行清单

- [x] D1. 建立一份 parity ledger，逐项对齐外部 `fusioncode` 能力与本仓库内部落点：
  - building primitives
  - road fusion
  - water line fusion
  - water polygon fusion
  - poi fusion
  - conflict / quality metrics
  - 2026-05-14：已新增 live `docs/superpowers/specs/2026-05-14-fusioncode-parity-ledger.md`，把 building / road / water / poi / conflict-quality 族分别映射到 adapter、KG、parameter spec、executor、retriever 与测试证据。
- [x] D2. 对每个能力族检查 6 个要素是否齐全：
  - wrapper/primitive
  - KG algorithm node
  - parameter specs
  - executor handler
  - planner/retriever 可见性
  - 对应测试
  - 2026-05-14：parity ledger 已显式记录六要素齐备情况；当前主要缺口已收敛到 shared-runtime smoke/inspection evidence 与最终 wording 全量统一，而不是代码挂点缺失。
- [x] D3. 解决当前文档与实现状态冲突：
  - road / water / bounded poi 已有实现与测试的，继续保持或升级为明确支持
  - building decomposed multi-source 若经 Phase C 证据确认可用，则从 `reservation_only` 升级到合适级别
  - 仍无足够运行证据的子能力继续显式标为 bounded / optional / reservation_only
  - 2026-05-14：road / water / bounded poi 已稳定保持 `runtime_supported` / `bounded_supported`；building multi-source、presence raster、height raster 已从早期“仅 reserved seam”口径收敛为 `research_utility`，并在 `docs/fusioncode-algorithm-library.md`、capability inventory 与 parity ledger 中保持一致。
- [x] D4. 增加跨主题 smoke/inspection 证据，证明这些 KG 算法节点不仅“存在于 seed”，还能够被 planner/executor 选中并产生可审计输出。
  - 2026-05-15：已为 task-driven smoke 增加 `preferred_pattern_id` 受控入口，并把实际执行得到的 `selected_pattern_id` 写回 plan / inspection / `kg_path_trace`。
  - 2026-05-15：fresh live smoke 已生成并 checked in：
    - `runs/smoke-road-gilgit-city-fusioncode-inspection-8012.json` -> `wp.road.fusioncode.segment_topology.v1` / `algo.fusion.road.segment_match_topology.v1`
    - `runs/smoke-water-nairobi-fusioncode-inspection-8012.json` -> `wp.water.fusioncode.line_and_polygon.v1` / `algo.fusion.water.polygon_priority_merge.v1`
    - `runs/smoke-poi-nairobi-fusioncode-inspection-8012.json` -> `wp.poi.fusioncode.geohash_priority.v1` / `algo.fusion.poi.geohash_neighbor_match.v1`
  - 结论：road / water / bounded poi 现在不只是“FusionCode candidate 可见”，而是已具备 planner/executor 真实选中后的 run-level 审计证据。
- [x] D5. 更新算法库文档与 operations 文档，禁止继续把“代码已接入、文档却说 deferred”长期并存。
  - 2026-05-15：`docs/fusioncode-algorithm-library.md`、`docs/v2-operations.md`、`docs/superpowers/specs/2026-05-06-capability-inventory.md`、`docs/superpowers/specs/2026-05-14-fusioncode-parity-ledger.md` 已统一 wording，明确 shared runtime claim 与 `research_utility` building flows 的边界。

### 验证

- `python -m pytest -q tests/test_fusioncode_inventory_contract.py tests/test_fusioncode_contracts.py tests/test_fusioncode_building_raster.py tests/test_fusioncode_building_v8_decomposition.py tests/test_fusioncode_linear_water_road.py tests/test_fusioncode_poi.py tests/test_fusioncode_executor_handlers.py tests/test_fusioncode_kg_metadata.py`
- `python -m pytest -q tests/test_planner_context.py tests/test_kg_repository_enhancements.py`
- 如补充 smoke evidence，再运行对应的 bounded live/integration slice

### 完成判定

- `fusioncode` 各主题能力的 claim_state 不再含混。
- 外部算法库存量、KG 节点、执行处理器与测试矩阵形成一一对应或有据可查的 defer 理由。
- 文档不再把已落地实现长期描述为“未来能力”。

### 反模式防护

- 不要把 `fusioncode.algorithm_adapter.run_full_pipeline()` 重新包装成单一黑盒主算法。
- 不要因为 unit tests 已过，就自动宣称所有外部能力都已成为稳定 runtime 主张。
- 不要让 building 大规模能力与 `fusioncode` 全库 claim 混成一个模糊大口号。

## 8. Phase E: 论文研究资产闭环

### 目标

在 Phase A-D 收口后的真实能力边界之上，整理出可答辩、可复核、不会超出 runtime 证据的论文资产集合。

### 涉及范围

- `docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json`
- `docs/superpowers/specs/2026-04-21-paper-evidence-freeze.json`
- `docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md`
- `docs/superpowers/specs/2026-05-06-capability-inventory.md`
- `docs/superpowers/specs/2026-05-06-related-work-gap-matrix.json`
- `docs/superpowers/specs/2026-05-06-related-work-gap-matrix.md`
- 新建 thesis docs，建议统一使用 `2026-05-13-` 前缀

### 建议新增文档

- `docs/superpowers/specs/2026-05-13-thesis-research-spec.md`
- `docs/superpowers/specs/2026-05-13-thesis-claims-ledger.md`
- `docs/superpowers/specs/2026-05-13-thesis-related-work-matrix.md`
- `docs/superpowers/specs/2026-05-13-thesis-related-work-matrix.json`
- `docs/superpowers/specs/2026-05-13-thesis-outline-and-timeline.md`
- `docs/superpowers/specs/2026-05-13-thesis-capability-handshake.md`

### 执行清单

- [x] E1. 写 thesis research spec，锁定：
  - 研究对象
  - RQ1 / RQ2 / RQ3
  - 主 claim 与非主 claim
  - 明确不把前端、运维增强、trajectory seam 写成主创新点
- [x] E2. 写 claims ledger，把每个 claim 映射到当前 live evidence、测试、freeze、run artifact，而不是映射到未来计划。
- [x] E3. 以 `2026-04-21-paper-experiment-matrix.json` 为 canonical matrix，按 Phase B-D 的最终能力边界更新 baseline、ablation、metrics、case pool。
- [x] E4. 基于 `2026-05-06-related-work-gap-matrix.*` 产出论文可直接写作的 related-work matrix 与 narrative，明确：
  - closest overlap
  - our difference
  - borrowed idea
  - 不能类比的边界
- [x] E5. 产出 thesis outline / timeline，确保实验顺序、论文章节、能力边界和 freeze 节奏一致。
- [x] E6. 产出 capability-handshake 文档，明确：
  - thesis plan 负责回答“为什么值得证明、如何证明”
  - runtime/capability plan 负责回答“什么已经能声称、什么必须继续收口”
  - 论文叙事不得超出 Phase A-D 的最终能力主张
  - 2026-05-15：已新增 `2026-05-13-thesis-research-spec.md`、`2026-05-13-thesis-claims-ledger.md`、`2026-05-13-thesis-related-work-matrix.*`、`2026-05-13-thesis-outline-and-timeline.md`、`2026-05-13-thesis-capability-handshake.md`，并把 canonical paper matrix 补充为带 `research_questions`、`baseline_catalog`、`ablation_catalog`、`metric_catalog`、`case_pool_policy` 的 live 研究入口。

### 验证

- 继续保持以下现有文档测试通过：
  - `python -m pytest -q tests/test_related_work_gap_matrix.py tests/test_capability_inventory_matrix.py`
- 为新 thesis docs 增加轻量守护测试，建议新增：
  - `tests/test_thesis_research_spec.py`
  - `tests/test_thesis_related_work_matrix.py`
  - `tests/test_thesis_outline_timeline.py`
  - `tests/test_plan_handshake.py`
- 更新后重新运行 `python scripts/freeze_paper_evidence.py` 的对应验证链，确保 paper freeze 可以从 live matrix 正常生成。

### 完成判定

- thesis 资产已经从 runtime 证据中长出来，而不是独立悬空。
- 所有论文主张都能回链到当前 live docs、tests、freeze 与 run artifacts。
- 论文资产不再依赖 `done/` 目录中的历史计划才能读懂。

### 反模式防护

- 不要拿“计划中未来会做”替代“当前已有证据”。
- 不要为了论文叙事好看而扩大 runtime 声称。
- 不要把 Benin 规模验证写成国家专题本体，而应写成规模化验证样例。

## 9. Final Phase: 总验收与归档卫生

### 目标

在所有活跃阶段完成后，做一次统一验收，确保仓库只保留一条活跃计划线，且 live docs / archive / tests / README 的边界一致。

### 执行清单

- [x] F1. 运行 Phase A-E 的全部聚焦验证命令。
- [x] F2. 刷新所有 live freeze 文档，确认路径不再引用 `done/` 作为活跃入口。
- [x] F3. 核对 `README.md`、`README.en.md`、`docs/v2-operations.md`、`docs/fusioncode-algorithm-library.md`、capability inventory 的术语一致性。
- [x] F4. 检查 `docs/superpowers/plans/` 根目录只剩本文件一份活跃计划。
- [x] F5. 检查 `docs/superpowers/plans/done/` 和 `docs/superpowers/specs/done/` 中的历史文档不再承担当前执行语义。

### 推荐最终验证命令

- `python scripts/run_no_ui_maturity_check.py`
- `python -m pytest -q tests/test_scenario_manifest_service.py tests/test_scenario_eval_harness.py tests/test_run_registry_service.py tests/test_operator_read_model_service.py tests/test_artifact_preview_service.py tests/test_no_ui_maturity_check.py`
- `python -m pytest -q tests/test_source_profile_service.py tests/test_tile_partition_service.py tests/test_tiled_building_runtime_service.py tests/test_raster_cli.py tests/test_tiled_multisource_building_runtime_service.py tests/test_run_benin_multisource_building_fusion.py`
- `python -m pytest -q tests/test_fusioncode_inventory_contract.py tests/test_fusioncode_contracts.py tests/test_fusioncode_building_raster.py tests/test_fusioncode_building_v8_decomposition.py tests/test_fusioncode_linear_water_road.py tests/test_fusioncode_poi.py tests/test_fusioncode_executor_handlers.py tests/test_fusioncode_kg_metadata.py`
- `python -m pytest -q tests/test_related_work_gap_matrix.py tests/test_capability_inventory_matrix.py`

### 2026-05-15 Final Phase closure note

- 已 fresh 运行 `python scripts/run_no_ui_maturity_check.py`，结果 `passed: true`。
- 已 fresh 运行 Final Phase 推荐的 Phase A-E 聚焦测试命令，结果分别为 `36 passed`、`17 passed, 8 warnings`、`24 passed`、`22 passed`。
- 已 fresh 刷新 `paper / scenario / no-ui maturity` 三条 live freeze。
- 已把 live specs 真正恢复到根目录并补充索引：`2026-04-07-real-data-eval-manifest.json`、`2026-04-07-fusion-agent-v2-design.md`、`2026-04-10-thesis-aligned-agent-design.md`、`2026-04-16-building-micro-alignment-result.json`、`2026-04-17-agentic-any-region-fusion-design.md`、`2026-04-23-system-next-improvement-review.md`。
- 已新增守护测试，确保 live paper evidence chain 不再依赖 `docs/superpowers/plans/done/`，且 live spec 引用真实落在 live 根目录。

### 完成判定

- 本计划成为唯一活跃执行入口。
- active spec / evidence / thesis docs 均回到明确的 live 路径。
- 大规模多源 building 能力与 `fusioncode` 全量算法库集成都被纳入正式闭环，而不是继续悬挂为“以后再说”。

## 10. 明确搁置范围

以下内容本轮不进入执行阶段，只保留边界说明：

- 前端证据面增长 / workbench 扩展
- 图后端迁移试验（如 NebulaGraph、AGE、GDB、PolarDB Graph 等）
- `trajectory-to-road` 可执行化路径

### 重新进入计划的条件

- 前端：只有在 no-ui maturity、operator surface、论文证据链都稳定后，才允许单独重开。
- 图后端迁移：只有默认后端出现明确性能、隔离或维护阻塞，才允许立项。
- `trajectory-to-road`：只有出现正式 runtime 设计、数据契约、验证链和证据需求，才允许从 seam 升级为计划项。

## 11. 结束条件

当以下条件同时满足时，本主计划可以视为完成：

- live spec / evidence 路径恢复完成，相关脚本与测试通过；
- no-ui operator / scenario / maturity 证据刷新完成；
- 面向大规模、多源建筑物数据融合能力的边界、证据、文档收口完成；
- `fusioncode` 全量算法库集成的 claim_state、证据与文档收口完成；
- thesis 研究资产形成闭环，且不超出现有 runtime 证据；
- 仓库中仍然只有这一份活跃计划。
