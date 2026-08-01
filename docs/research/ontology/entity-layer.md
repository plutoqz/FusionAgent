# FusionAgent 契约化灾害知识图谱：实体层

> 状态：A1 当前实体与政策说明  
> 对应候选发布：`fusionagent-kg-v1.0.0`  
> 对应语义哈希：`sha256:50067b9368914c47580707650789c04c78b2e856ccb3ef4d120a31f36c0ad71e`  
> 更新日期：2026-07-28

## 1. 计数口径

本文件描述两类冻结知识：

1. [`entities.json`](../../../kg/ontology/v1.0.0/entities.json) 中具有稳定 ID 的静态知识对象。
2. [`policies.json`](../../../kg/ontology/v1.0.0/policies.json) 中由类型化 registry 消费的政策记录。

`entities.json` 当前包含 241 个静态知识对象和 1 条显式类型转换边。241 不是本体类数量，也不是 Neo4j 运行节点数。运行期间生成的计划、运行、质量结果、证据项、gap 和 supersession 均不进入此计数。

## 2. 静态对象清单

| 分区 | 数量 | 主要稳定 ID |
| --- | ---: | --- |
| `parameter_specs` | 72 | `spec_id` |
| `data_sources` | 34 | `source_id` |
| `algorithms` | 33 | `algo_id` |
| `data_types` | 27 | `type_id` |
| `workflow_patterns` | 15 | `pattern_id` |
| `data_needs` | 12 | `need_id` |
| `tasks` | 11 | `task_id` |
| `task_bundles` | 7 | `bundle_id` |
| `product_contracts` | 6 | `contract_id` |
| `repair_strategies` | 6 | `strategy_id` |
| `output_requirements` | 5 | `requirement_id` |
| `output_schema_policies` | 5 | `policy_id` |
| `scenario_profiles` | 4 | `profile_id` |
| `qos_policies` | 4 | `policy_id` |
| **合计** | **241** | 不含运行派生实例 |

## 3. 灾害情景与任务包

当前场景 profile 为 `scenario.flood.default`、`scenario.earthquake.default`、`scenario.typhoon.default` 和 `scenario.default.task`。前三者面向场景驱动任务，通用 profile 面向显式直接任务。对应灾害词汇及别名由 `policies.json#disaster_vocabulary` 管理。

| 任务包 | 模式 | 请求任务 |
| --- | --- | --- |
| `task_bundle.direct_request` | 直接任务 | building、road、water polygon、waterways、POI 中的显式请求 |
| `task_bundle.flood.building_road` | 洪水 provisional | building、road |
| `task_bundle.flood.emergency_vector` | 洪水完整包 | building、road、water polygon、waterways、POI |
| `task_bundle.earthquake.building_road` | 地震 provisional | building、road |
| `task_bundle.earthquake.emergency_vector` | 地震完整包 | building、road、water polygon、waterways、POI |
| `task_bundle.typhoon.building_road` | 台风 provisional | building、road |
| `task_bundle.typhoon.emergency_vector` | 台风完整包 | building、road、water polygon、waterways、POI |

`*.emergency_vector` 通过 `supersedes_bundle_id` 关联同灾种的 building-road 临时包。是否允许 provisional 和 supersession 由产品契约的 `degradation_policy` 决定，不能由运行代码自行扩大。

未知灾种不会进入默认灾害任务包。`hurricane`、`wildfire` 和 `conflict` 当前不属于 v1 可执行灾种；它们只有在新增 scenario profile、任务包、产品契约和数据源闭包后才能进入支持范围。

## 4. 任务、算法与工作流

11 个任务中，五个核心融合任务为：

- `task.building.fusion`
- `task.road.fusion`
- `task.water.fusion`
- `task.waterways.fusion`
- `task.poi.fusion`

`task.vector.download`、`task.partition.aoi` 和 `task.enrich.building.height.reserved` 是支持性或研究工具任务。`task.clip.raster.by_tile`、`task.merge.building.tiles.reserved` 和 `task.trajectory_to_road` 为 `reservation_only`，不得因已有实体就宣称运行能力已经完成。

33 个算法对象分别声明任务归属、输入类型、输出类型、参数和运行状态；15 个工作流模式声明步骤、依赖、算法和输入数据源。72 个参数规范保存算法参数边界。独立 verifier 检查工作流 DAG 与算法 I/O 闭包。

## 5. 产品契约

| 产品契约 | 覆盖任务 | 主要治理含义 |
| --- | --- | --- |
| `contract.product.building.v1` | building | 建筑几何、字段、质量、证据和修复授权 |
| `contract.product.road.v1` | road | 道路字段、拓扑、名称保留和恢复授权 |
| `contract.product.water_polygon.v1` | water polygon | 面水体几何、lineage、质量与降级 |
| `contract.product.waterways.v1` | waterways | 线水系几何、拓扑、source closure 与恢复 |
| `contract.product.poi.v1` | POI | 限定 AOI 的 POI 输出、双源证据与质量 |
| `contract.product.emergency_vector_bundle.v1` | 五类核心任务 | 场景级交付、provisional、gap 与 supersession |

六个契约均显式列出适用任务、输出要求、证据要求、允许修复策略和降级政策。当前均允许带标记的 `partially_satisfied` 或 `degraded_but_usable` 状态，并允许 provisional 被最终产品替代；这只是机制授权，是否提升交付效果仍需 P3 消融证明。

## 6. 数据源实体

34 个数据源按 `metadata.kind` 分为：

| 类型 | 数量 | 含义 |
| --- | ---: | --- |
| `catalog` | 9 | 面向任务的组合源或采集入口 |
| `raw_vector` | 22 | 可材料化的矢量源 |
| `raw_raster` | 2 | 栅格高度/存在性信号 |
| `local` | 1 | 限定 AOI 的本地补充源 |

其中 26 个为 `runtime_candidate`，8 个为 `reservation_only`。按主题标注的实体包括 building 8、road 4、water polygon 4、waterways 3、POI 5；另有 10 个跨主题或未设置单一 theme 的 catalog/辅助对象。

关键源闭包如下：

- building：OSM 为 primary footprint，Microsoft 为 required reference，Google building 为 optional supplemental；高度信号使用 `raw.google.building_height.raster`。
- road：OSM 与 Microsoft 构成当前核心源角色，Overture 相关对象受运行状态和契约限制。
- water polygon：OSM water 与 HydroLAKES 形成当前源闭包。
- waterways：OSM waterways 与 HydroRIVERS 形成可移植闭包，Pakistan local waterways 仅为 AOI 特定补充。
- POI：OSM 为 base，GNS/GeoNames 为首选 reference；Google/RH 受授权或可用性约束。

具体候选顺序、required closure、fallback 和可接受部分覆盖由 `source_role_policies`、`source_bundle_policies` 与 `source_runtime_bindings` 决定，不能从本段文字反向生成运行配置。

## 7. 输出、质量与恢复

五类核心融合任务分别具有 output requirement、output schema policy、output contract、quality policy 和 quality component policy。政策列表的冻结记录数为：

| 政策分区 | 数量 |
| --- | ---: |
| `task_semantics` | 5 |
| `output_contracts` | 5 |
| `quality_policies` | 5 |
| `source_role_policies` | 13 |
| `source_bundle_policies` | 9 |
| `quality_component_policies` | 5 |
| `decision_policies` | 2 |

六个修复策略分为两类：

- 运行替代：`repair.source_fallback.v1`、`repair.alternative_algorithm.v1`。
- artifact 修复：schema backfill、road name preservation、line topology cleanup、geometry validity repair。

策略能否执行由计划请求、产品契约授权、任务包授权和 `recovery.default.v1` 全局授权的交集决定。alternative source 只提供候选关系；执行器不得把旧 artifact 重新标注成新 source，而必须由上游重新材料化。

`fault_policy` 统一拥有故障分类词表、状态归一化、可恢复故障、候选 fallback 故障、重试参数、推断缺失分类和 inspection guidance。代码只负责匹配、集合计算和证据输出。

## 8. 静态知识与运行实例

以下对象属于运行派生实例，不写入 `entities.json`：

- `PlanningContext`、`PlanningDecision`、`PlanningRationale`
- `RunInstance`、`WorkflowInstance`、`ExecutionStep`
- `QualityGateResult`、`CoverageEvidence`、`DataAbsence`
- `EvidenceTrace`、`EvidenceItem`、`GapDeclaration`、`DeliveryManifest`
- provisional/final `DataProduct` 及其 `SUPERSEDES` 关系
- `DurableLearningRecord`

运行实例必须引用 `release_id`、`semantic_hash` 和相关实体/政策 ID。动态经验使用单独的 `experience_snapshot_hash`，不得改变基础 KG 语义哈希。

## 9. K3 迁移结论与边界

P0-K3 已将高风险决策知识迁入 `entities.json`/`policies.json`，并把运行常量改为 KG 派生兼容视图。静态复核中：

- provider 实现内的 `raw.*` ID 是适配器身份绑定，保留在代码中。
- POI bounded 双源条件、推断缺失故障、operator guidance 和源空覆盖规则不再由 source-specific 行为分支拥有；Microsoft building 的 `coverage_empty` 语义由 `fault_policy.empty_coverage_status_by_source` 声明。
- URL、凭据、超时和 artifact reuse 开关属于运行/实验配置，不进入基础 KG 语义哈希。
- 字段 probe order 的完全本体化仍是中风险后续项 `SRC-08`，不构成 K3 高风险第二权威副本。

P0-K4/K5 已于 2026-07-29 完成：KG-only 计划扰动、fail-closed、真实 source rematerialization、Neo4j 5.26/pinned memory parity 和最终 clean/tamper 发布校验均通过。该结论是定向运行验收，不扩大为真实 LLM、长期稳定性或生产部署证明。
