# FusionAgent 契约化灾害知识图谱：本体层

> 状态：A1 当前本体说明  
> 对应候选发布：`fusionagent-kg-v1.0.0`  
> 对应语义哈希：`sha256:50067b9368914c47580707650789c04c78b2e856ccb3ef4d120a31f36c0ad71e`  
> 更新日期：2026-07-28

## 1. 权威边界

本文件解释本体设计，不是机器真源。类、关系、属性、约束和 competency questions 的唯一机器可读权威是 [`schema.json`](../../../kg/ontology/v1.0.0/schema.json)。静态知识对象见[实体层说明](entity-layer.md)，任务编译、质量、源选择和恢复政策见 [`policies.json`](../../../kg/ontology/v1.0.0/policies.json)。

当前模式包含 7 层、71 个类、42 类关系、19 个正式属性、8 条完整性约束和 8 个 competency questions。这里的“类”是概念模式，不是静态实体数量，也不是运行图中的节点数量。

类的状态有三种：

- `implemented`：已有静态知识、运行消费者或两者兼有。
- `runtime-derived`：类已建模，但实例只能由任务运行产生。
- `reserved`：仅保留扩展位置，不能据此宣称当前能力已经实现。

## 2. 七层结构

| 层 | 名称 | 类数 | 主要职责 | 代表类 |
| --- | --- | ---: | --- | --- |
| L1 | 灾害情景层 | 12 | 把事件、请求、地点、响应阶段和资源处境规范化为规划上下文 | `DisasterEvent`、`DisasterContext`、`ScenarioProfile`、`SituationSignature` |
| L2 | 数据产品契约层 | 10 | 表达必须交付什么、允许怎样降级、需要哪些质量和证据 | `DataProductContract`、`RequiredLayer`、`OutputRequirement`、`AcceptableDegradation` |
| L3 | 数据需求与数据源语义层 | 10 | 连接数据需求、类型、源角色、覆盖、时效和缺失语义 | `DataNeed`、`DataType`、`DataSource`、`SourceContract`、`DataAbsence` |
| L4 | 数据-算法-任务能力层 | 8 | 表达任务、任务包、算法 I/O、参数、工作流和修复能力 | `Task`、`TaskBundle`、`Algorithm`、`WorkflowPattern`、`RepairStrategy` |
| L5 | 受约束规划层 | 7 | 记录候选空间、采集与渐进交付策略、决策政策和理由 | `PlanningContext`、`PlanningDecision`、`DecisionPolicy`、`ReplanningProposal` |
| L6 | 执行质量校验层 | 14 | 表达运行契约、质量门、故障分类、重试、恢复和运行闸门 | `RuntimeContract`、`QualityGate`、`FailureClass`、`RecoveryPolicy` |
| L7 | 证据与经验层 | 10 | 固化 KG 身份、运行证据、gap、manifest、替代关系和经验边界 | `KnowledgeRelease`、`EvidenceTrace`、`GapDeclaration`、`DurableLearningRecord` |

七层形成的主决策链为：

```text
灾害情景/用户请求
  -> 数据产品契约
  -> 数据需求与数据源角色
  -> 任务、算法与工作流能力
  -> 受约束规划决策
  -> 执行、质量门与恢复
  -> 证据、缺口和发布身份
```

## 3. 关系设计

42 类关系按职责分组如下：

| 关系组 | 关系类型 |
| --- | --- |
| 情景规范化与触发 | `NORMALIZED_TO`、`HAS_PHASE`、`HAS_RESOURCE_REGIME`、`USES_PROFILE`、`RAISES`、`TRIGGERS`、`COMPILED_TO` |
| 产品契约与要求 | `REQUIRES`、`INCLUDES`、`SPECIFIES_OUTPUT`、`HAS_FIELD_REQUIREMENT`、`HAS_GEOMETRY_CONSTRAINT`、`SPECIFIES_QUALITY`、`SPECIFIES_EVIDENCE`、`ALLOWS` |
| 数据需求与数据源 | `DERIVES`、`REQUIRES_TYPE`、`SUPPORTS`、`GOVERNED_BY`、`HAS_SOURCE_ROLE` |
| 任务、算法与工作流 | `CONTAINS`、`CONSUMES`、`PRODUCES`、`IMPLEMENTS`、`HAS_PARAMETER`、`CAN_TRANSFORM_TO`、`APPLIES_TO`、`HAS_STEP`、`USES`、`SUBSTITUTES` |
| 规划与治理 | `BUILDS_CONTEXT`、`SELECTS`、`USES_DECISION_POLICY`、`VALIDATED_BY`、`PRODUCES_RESULT`、`CLASSIFIES_FAILURE`、`RECOVERED_BY`、`AUTHORIZES_REPAIR` |
| 证据与交付 | `GENERATES`、`DECLARES`、`SUPERSEDES`、`REFERENCES_RELEASE` |

关系的端点类型由 `schema.json#relations` 固定。例如 `AUTHORIZES_REPAIR` 只能从 `DataProductContract` 指向 `RepairStrategy`，`REFERENCES_RELEASE` 只能从 `RunInstance` 指向 `KnowledgeRelease`。静态 JSON 中的引用必须通过 `C-REF-CLOSED` 校验；运行时关系必须在证据中保留稳定 ID 和 KG 身份。

## 4. 正式属性

19 个正式属性不是所有 JSON 字段的穷举，而是跨层必须稳定解释的核心属性：

| 主题 | 属性 |
| --- | --- |
| 发布身份 | `release_id`、`semantic_hash`、`experience_snapshot_hash` |
| 情景与任务包 | `disaster_type`、`requested_tasks` |
| 产品与输出 | `contract_id`、`required_fields`、`allowed_geometry_types`、`quality_threshold` |
| 数据源 | `source_id`、`candidate_source_ids`、`fallback_source_ids` |
| 算法与类型 | `algo_id`、`input_types`、`output_type` |
| 恢复与政策 | `strategy_id`、`authorized_strategy_ids`、`policy_id` |
| 证据 | `evidence_refs` |

稳定 ID 在同一类内必须唯一；发布身份字段在冻结发布中不可变。版本化机器源可以增加对象或关系，但不得在同一版本目录中静默改变既有语义。

## 5. 完整性约束

| ID | 约束 | 防止的问题 |
| --- | --- | --- |
| `C-ID-UNIQUE` | 同一本体类中的稳定标识唯一 | 同名对象覆盖或歧义引用 |
| `C-REF-CLOSED` | 静态关系端点和实体引用均存在 | 悬空 task/source/contract 引用 |
| `C-WORKFLOW-DAG` | 工作流步骤依赖构成 DAG | 环路计划无法执行 |
| `C-ALGO-IO` | 工作流步骤与算法 I/O、数据类型闭合 | 计划形式有效但不可执行 |
| `C-CONTRACT-CLOSED` | 产品契约引用输出、质量、证据和恢复知识 | 只有任务名、没有交付治理 |
| `C-STRICT-REQUIRED` | 缺少必要知识时研究运行 fail closed | 隐藏默认规则接管决策 |
| `C-RELEASE-IMMUTABLE` | 冻结文件字节哈希与 `release.json` 一致 | 发布内容静默漂移 |
| `C-EXPERIENCE-SEPARATE` | 动态经验不改变基础 KG 语义哈希 | 运行反馈污染可复现基线 |

## 6. Competency Questions

| ID | 本体必须能够回答的问题 |
| --- | --- |
| `CQ01` | 给定灾害类型和响应阶段，需要交付哪些产品与图层？ |
| `CQ02` | 给定产品契约，哪些数据源、算法和工作流能够形成可执行闭环？ |
| `CQ03` | 某项输出必须满足哪些字段、几何和质量阈值？ |
| `CQ04` | 某数据源不可用时允许使用哪些替代源，何时必须声明缺口？ |
| `CQ05` | 某算法或质量门失败后，哪些修复策略被当前产品契约授权？ |
| `CQ06` | 规划决策引用了哪个 KG 版本、哪些实体和约束？ |
| `CQ07` | 临时产品被何种最终产品替代，证据和缺口是否完整？ |
| `CQ08` | 相同基础 KG 与固定经验快照能否生成语义一致的计划？ |

独立 verifier 检查这 8 个问题及其 `required_concepts` 是否完整，但“模式能表达”不等于所有研究问题均已获得外部评价。P0-K4 已完成运行消费、KG-only 行为扰动和双后端定向验收。

## 7. 本体与运行的边界

本体负责定义可表达、可约束和可追溯的对象；代码负责解析、下载、几何计算、指标计算和执行。以下内容不得混为一谈：

- provider 适配器中的固定 `source_id` 是实现与 KG 实体的身份绑定，不是候选顺序的第二份权威。
- 正则、集合运算、哈希计算和几何修复算法可以留在代码中，但分类词表、阈值、授权和顺序必须来自 KG 或冻结运行配置。
- `RunInstance`、`QualityGateResult`、`EvidenceItem`、`GapDeclaration`、`DeliveryManifest` 等实例由运行产生，不计入 241 个静态知识对象。
- `ConflictAxis` 和 `PatternCandidate` 当前为 `reserved`；真实 LLM 规划仍未验证。真实 Neo4j 与 pinned memory 的四类任务定向一致性已通过 K4，但不代表长期稳定性或生产规模性能。

## 8. 变更规则

修改本体时应先改 `schema.json`，再同步实体/政策闭包、独立 verifier 和本说明。P0-K5 已完成，`v1.0.0` 不得原地覆盖；后续语义修改必须创建新版本目录。
