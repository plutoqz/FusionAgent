# FusionAgent V2 Revised Design

## Context

FusionAgent 当前已经是一个可运行的领域受限 agentic workflow MVP，而不是单纯的算法包装层。现有实现已经具备：

- KG 驱动的候选 pattern / algorithm / data source 检索
- LLM 或 mock 参与的计划生成
- 基于 `validator` 的类型校验与 transform 插入
- 基于 `executor` 的 repair 策略与有限 replan
- 运行状态、audit、artifact、feedback 写回

但当前系统也有三个结构性短板：

1. 搜索空间太小，LLM 和 policy 的“选择”意义不够强。
2. policy 是隐式的，决策依据分散在 prompt、validator 和 executor 中。
3. 历史 artifact 还没有真正成为可复用的长期记忆，经验写回也仍偏弱。

本次设计修订的目标，是在不引入重型通用 agent 框架的前提下，把 FusionAgent 演化为一个“可解释、可扩展、可评测”的无人值守灾害矢量融合智能体。

## Agreed Direction

基于本轮讨论，确认以下方向：

- 保持自研单智能体机制，不做 `AutoGen` / `CrewAI` 式多智能体对话框架迁移。
- 参考成熟框架的工程思想，尤其是显式状态图、可复现 harness、可审计决策、故障注入与评测矩阵。
- 增大搜索空间，但不是盲目增大，而是按“可被 policy 管理”的方式扩展自由度。
- 保留 KG 作为约束层和长期结构化记忆，不把它降级成普通 RAG 文档库。
- 允许原始本体文档继续作为目标态方案保留，但需要新增一份执行导向的 V2 设计作为近期实现依据。

## Approaches Considered

### Option A: Continue the Custom Orchestrator and Add Explicit Policy

做法：

- 保留 `planner -> validator -> executor -> writeback` 主循环。
- 新增显式 `PolicyEngine`，统一处理 pattern/source/parameter/cache/replan 选择。
- 新增 artifact registry 与 freshness 检查。
- 扩展 KG 以表达 parameter spec 和可复用结果元数据。

优点：

- 与当前代码结构最一致。
- 风险最小，最适合逐步验证。
- 论文贡献点可直接落在约束、验证、修复、复用和评测上。

缺点：

- 需要自己补齐状态机、policy trace 和 evaluation harness。

### Option B: Introduce LangGraph as an Orchestration Shell Now

做法：

- 用 LangGraph 承载节点编排、状态转移和 checkpoint。
- 保留现有 planner / validator / executor 作为 graph nodes。

优点：

- 状态流与 checkpoint 更标准。
- 后续可视化和多分支调试更方便。

缺点：

- 当前阶段会引入额外抽象成本。
- 容易把研究焦点带偏到框架迁移，而不是方法本身。

### Option C: Migrate to a Full General-Purpose Agent Framework

做法：

- 用通用 agent framework 重写 planning、tool use、memory 和 execution。

优点：

- 表面上“组件齐全”。

缺点：

- 与当前任务不匹配。
- 会弱化 KG 约束、validator、repair 这几个真正有价值的差异点。
- 工程风险和论文风险都最高。

### Recommendation

推荐采用 Option A，并吸收 Option B 的工程思想，但暂不迁移到 LangGraph。

换句话说：实现一个“LangGraph 风格但仍然自研”的显式状态机系统，而不是直接上框架。

## Revised System Architecture

### 1. Completeness Target

V2 之后的系统需要完整覆盖以下组件：

- `Model`: LLM provider，负责计划候选生成、必要时辅助 replan。
- `Instructions`: planner prompt、validator rules、policy rules、output schema rules。
- `Tools`: 已注册融合算法、转换算法、数据获取器、artifact 查询器。
- `State`: run state、plan revision、decision trace、artifact registry、repair records。
- `Loop`: planning -> validation -> policy selection -> execution -> healing/replan -> writeback。
- `Policy`: 独立可解释的打分与选择模块。
- `Harness`: goldens、fault injection、baseline 对比、回归套件。

当前系统缺的是显式 `Policy` 和系统化 `Harness`。V2 的实现重点就是补齐这两块。

### 2. Runtime Topology

推荐保持单智能体、多阶段循环：

1. 输入请求进入 `RunCreateRequest`。
2. `retriever` 组装 planning context：
   - KG candidates
   - parameter specs
   - data source quality
   - artifact reuse candidates
3. `planner` 生成候选 plan。
4. `validator` 做类型一致性与 transform 插入。
5. `PolicyEngine` 在候选 pattern / source / parameter / reuse path 中做显式选择。
6. `executor` 执行并记录 repair / fallback / replan 证据。
7. `writeback` 写 artifact、feedback、decision trace。
8. `Harness` 使用同一批 case 做离线评测和回归。

### 3. Policy Responsibilities

显式 policy 至少要管理五类决策：

- `pattern_selection`
- `data_source_selection`
- `parameter_binding`
- `artifact_reuse_selection`
- `replan_or_fail`

每个决策都应输出：

- 候选列表
- 每个候选的分数拆解
- 被选项
- rationale
- 关联证据

这部分不应继续散落在 prompt 文本和 repair 分支里。

## Search Space Expansion Model

“搜索空间变大”不是简单添加更多算法，而是把可决策自由度结构化。V2 推荐扩展五个轴：

### Axis 1: Algorithm Family Expansion

从当前“building / road 各 2 个算法”扩展到：

- 主算法
- 安全回退算法
- 成本更低但精度较弱的快速算法
- 更多 transform 算法

要求：

- 每个算法必须声明输入输出类型、成功率、耗时、替代关系。
- 不能只加脚本，不加元数据。

### Axis 2: Data Source and Data Type Expansion

从“上传 bundle + 少量 catalog source”扩展到：

- 多数据类型
- 多来源
- 时效性
- 空间覆盖
- schema 兼容性

要求：

- 所有 source 必须具备 freshness 与 quality 信号。
- `DataType` 与 `DataSource` 不能只是枚举，需要可被 policy 量化比较。

### Axis 3: Parameterized Execution

这部分是当前本体最明显的空洞。

V2 应将算法参数提为一等对象，而不是继续藏在 JSON 中。至少需要：

- 参数名
- 参数类型
- 默认值
- 可选范围 / 枚举值
- 是否 tunable
- 影响维度，例如 `precision`, `speed`, `stability`

这样 planner 才能真正“选择参数”，policy 也才能给出有理有据的绑定。

### Axis 4: Output Field and Naming Policy

这不是边缘需求，而是结果交付的一部分。

V2 应允许：

- 输出字段保留策略
- 输出字段重命名策略
- schema 兼容策略

推荐将其视为 `output policy`，而不是散落在 adapter 中的特殊逻辑。

### Axis 5: Artifact Reuse and Freshness-Aware Retrieval

历史融合结果必须成为长期记忆的一部分。

V2 应支持：

- 注册每次输出 artifact 的空间范围、时间戳、job_type、schema 摘要
- 对新请求进行“是否可复用”的判断
- 如可复用，则直接返回 / 裁剪
- 如不可复用，则根据 freshness policy 触发重新下载或重新规划

这一步会显著提升无人值守场景的实用性，也会让 agent 的“记忆”不再只靠 KG pattern 成功率。

## Ontology Assessment

### Overall Judgment

原始本体方向是合理的，但对当前实现来说有两个问题：

- 目标态类太多，执行态核心类太少
- 对“参数化执行、artifact 复用、显式 policy trace”的支持不足

因此，不建议推翻原始四层结构，但建议把它重构为：

- `Core Executable Ontology`
- `Extended Research Ontology`

### Core Executable Ontology

近期实现必须优先保证以下类是完整、可查询、可写回的：

- `DataSource`
- `DataType`
- `Algorithm`
- `TransformOp`
- `WorkflowPattern`
- `StepTemplate`
- `WorkflowInstance`
- `ResultArtifact`，由原先偏目标态的 `DataArtifact` 升级为核心类
- `RepairRecord`
- `ExecutionFeedback`
- `AlgorithmParameterSpec`，新增
- `DecisionRecord`，新增

### Extended Research Ontology

以下内容可以保留为扩展层，但不应阻塞 V2：

- 完整 `Scenario Layer`
- 大规模 OWL / SHACL 约束体系
- 面向所有场景的通用 query template
- 全量知识演进机制

### Redundancy and Simplification

以下内容建议降级，不作为 V2 的实现主线：

- 过细的场景类层次
- 纯论文导向但当前无消费方的类
- 对 every-step 全量 OWL 化表达

具体建议：

1. `DisasterType`、`SpatialExtent`、`TemporalExtent` 保留。
2. `SeverityLevel`、`ResponsePhase`、`DataNeed` 暂时保留为可选扩展，不作为 planner 的必经查询入口。
3. `ExecutionLog` 继续以文件 audit 为主，不要求立即入 KG。
4. `ToolImplementation.parameterTemplate` 不再承担参数建模职责，只保留实现侧默认值。

### Required Ontology Additions

#### 1. `AlgorithmParameterSpec`

目的：

- 支撑动态参数选择
- 让 parameter binding 成为搜索空间的一部分

核心字段建议：

- `parameter_name`
- `parameter_type`
- `default_value`
- `allowed_values`
- `min_value`
- `max_value`
- `tunable`
- `optimization_tags`

#### 2. `ResultArtifact`

目的：

- 支撑 artifact 复用
- 让“已有结果是否可直接复用”成为一等决策

核心字段建议：

- `artifact_id`
- `run_id`
- `job_type`
- `disaster_type`
- `spatial_extent`
- `temporal_extent`
- `schema_summary`
- `created_at`
- `fresh_until`
- `source_snapshot`

#### 3. `DecisionRecord`

目的：

- 让 policy 真正可解释
- 为 audit、评测和 failure analysis 提供证据

核心字段建议：

- `decision_type`
- `selected_id`
- `candidate_scores`
- `rationale`
- `evidence_refs`
- `policy_version`

## Framework Position

当前阶段不建议迁移到通用 agent framework，但建议显式借鉴成熟框架的工程原则：

- 图式状态流
- checkpoint / replay
- deterministic node contracts
- structured memory
- audit-first execution
- harness-driven validation

如果未来确实需要引入框架，优先顺序应是：

1. 先把 V2 的自研 policy、artifact registry、harness 补齐
2. 再评估是否用 LangGraph 承载现有节点

而不是现在直接迁移。

## Evaluation Strategy

V2 需要把“系统能跑”升级为“系统被可靠评估”。建议建立四层评测：

### Layer 1: Engineering Reliability

- run success rate
- artifact availability
- audit completeness
- API / worker regression

### Layer 2: Planning Quality

- validation pass rate
- executable plan rate
- transform insertion correctness
- candidate discrimination quality

### Layer 3: Healing Robustness

- repair success rate
- replan success rate
- average recovery attempts
- failure mode coverage

### Layer 4: Research Evaluation

与以下 baseline 做对比：

- pure KG top-pattern
- pure LLM planning
- doc RAG without KG constraints
- no validation
- no healing
- full system

## Information Needed from the User

以下信息不是阻塞生成实施计划，但会决定后续实现质量：

### Strongly Recommended

- 每类任务至少 2 到 3 组真实数据样例
  - `building`
  - `road`
  - 不同灾害类型或不同质量水平
- 现有可接入算法清单
  - 脚本入口
  - 主要参数
  - 失败模式
- 你期望的结果字段规则
  - 保留哪些字段
  - 如何命名
  - 哪些字段必须稳定

### Needed for Artifact Reuse

- 你可以接受的 freshness 策略
  - 例如 1 天 / 3 天 / 7 天
- 可复用判定阈值
  - 空间覆盖比例
  - schema 兼容度

### Needed for Policy Calibration

- 你更看重的目标排序
  - `accuracy`
  - `stability`
  - `speed`
  - `freshness`
  - `cost`

## Recommended Sequencing

实现顺序建议固定为：

1. 显式 state / policy schema
2. policy engine
3. parameter spec
4. artifact registry and reuse
5. execution binding
6. healing and audit strengthening
7. evaluation harness
8. ontology doc refresh

这比先加大量算法更稳，因为先把“如何选择”和“如何评估”补齐，再扩搜索空间，系统不会失控。

## Immediate Conclusion

本次修订不建议大换框架，也不建议大改论文目标，而是把 FusionAgent 的贡献更准确地落在：

- 受 KG 约束的可执行工作流生成
- 参数化与 artifact 复用驱动的搜索空间扩展
- 显式 policy 与 decision trace
- 无人值守场景下的 repair / replan / harness 评测闭环

这条线既贴合你当前代码，也比“通用 GIS agent”更容易站住。
