# Thesis-Aligned FusionAgent Design

## Context

FusionAgent 当前已经拥有可运行的 agent runtime，但论文方向与执行态结构之间仍存在叙事缺口。现有实现已经完成规划、验证、执行、修复、写回、artifact 复用、durable learning 和 decision trace 等关键能力，但知识图谱本体仍偏执行子集，尚未完整体现论文要表达的“场景约束 + 任务实例化 + 智能体记忆”的整体结构。

本设计的目标不是推翻现有实现，也不是回到更粗糙的开题报告方案，而是在当前代码之上收束出一条论文与工程都能成立的主线。

## Agreed Direction

本轮共识如下：

- 核心知识基座采用 `算法 - 任务 - 数据` 三元结构。
- `灾害` 不再作为核心三元之一，而是上移为场景约束层。
- 系统入口采用双模式：
  - `scenario-driven`
  - `task-driven`
- 智能体模式定义为：
  - `Constrained Plan-and-Execute with Reactive Healing`
- 当前显式状态机、validator、policy、repair、artifact reuse、durable learning 均保留，不做推倒重写。

## Why The Core Triad Changes

继续把 `灾害` 放在核心三元中会带来一个问题：灾害并不总是直接决定底层融合算法或输入输出类型。更真实的作用方式是：

- 灾害影响任务集合
- 灾害影响数据需求
- 灾害影响参数偏好
- 灾害影响输出要求
- 灾害影响评价标准

而 `任务` 则是执行层真正的桥梁，因为它能稳定地连接：

- 算法
- 数据
- 参数
- 输入输出约束
- 工作流步骤

因此，本设计将核心执行层重构为：

- `Algorithm`
- `Task`
- `Data`

并将 `DisasterEvent`、`ScenarioProfile`、`DataNeed`、`OutputRequirement`、`QoSPolicy` 放入场景约束层。

## Dual-Entry Architecture

系统统一入口定义为：

`Input -> Intent/Profile Resolution -> TaskBundle -> KG Retrieval -> Planning -> Validation -> Execution -> Healing -> Writeback`

### Scenario-Driven Entry

面向灾害事件、预警和场景化请求。

流程：

`DisasterEvent -> ScenarioProfile -> TaskBundle -> Planning`

### Task-Driven Entry

面向用户直接指定的任务请求。

例如：

- 需要某区域的建筑物与道路数据
- 需要某区域建筑融合结果
- 需要某区域已有结果裁剪输出

流程：

`UserIntent -> TaskBundle -> DefaultPolicyProfile -> Planning`

在此模式下，灾害层不是必经入口，系统应允许直接使用默认策略与任务模板完成规划。

## Agent Mode

本系统不宜定义为纯 `ReAct`，原因如下：

- 当前运行时是显式阶段式的，而不是连续对话式推理调用工具。
- planner、validator、policy、executor 已经天然构成多阶段 pipeline。
- repair 行为具备局部 `ReAct` 风格，但主链路仍是先规划后执行。

因此正式定义为：

`Constrained Plan-and-Execute with Reactive Healing`

其含义是：

- 主体采用先规划后执行
- 规划阶段由 KG 检索约束
- LLM 仅做受限补全
- 执行失败时启用响应式修复机制
- 整体由显式状态机驱动

## Agent Components

### 1. Perception

输入源包括：

- 灾害事件
- 用户直接任务
- 定时任务
- artifact reuse 命中

### 2. Memory

分为三层：

- `Working memory`
- `Structured long-term memory`
- `Operational memory`

分别对应：

- 当前 run 上下文
- KG、本体、场景约束、参数规范
- artifact、durable learning、成功路径和失败统计

### 3. Reasoning and Planning

包含：

- 意图解析
- 场景/任务归一化
- KG skeleton retrieval
- LLM constrained instantiation

### 4. Validation and Policy

包含：

- `V(t_i)` 可达性验证
- 参数绑定
- schema policy
- 候选评分与显式决策

### 5. Action and Healing

包含：

- 融合执行
- 数据下载
- CRS / 字段中间步骤插入
- 替代算法与替代数据源
- transform insertion
- replan

### 6. Audit and Evolution

包含：

- decision trace
- repair records
- artifact writeback
- durable learning

## Role Of Disaster

灾害层的职责是驱动场景约束，不是直接选择算法。其作用被正式定义为五类影响：

1. `Task activation`
2. `Data requirement and acquisition policy`
3. `Parameter strategy`
4. `Output requirement`
5. `Evaluation and reliability policy`

这样可以解释：

- 为什么当前代码中 `disaster_type` 更接近 pattern/source 过滤条件
- 为什么真正决定执行链的是 task/data/parameter
- 为什么同一套融合算法可以在不同灾害场景中复用，只是配置和目标不同

## Minimal Ontology Additions

为对齐论文叙事且不推倒当前实现，近期建议只补以下对象：

- `TaskNode`
- `ScenarioProfileNode`
- `TaskBundle`
- `OutputRequirement`
- `QoSPolicy`

其中：

- `TaskNode` 用于把当前字符串型 `task_type` 升级为显式语义对象
- `ScenarioProfileNode` 用于将灾害转译成运行时可消费约束
- `TaskBundle` 用于统一双入口模式

## Mapping To Current Runtime

当前运行时可映射为：

- `Perception`: `RunTrigger`
- `Reasoning and Planning`: `PlanningContextBuilder` + `WorkflowPlanner`
- `Validation and Policy`: `WorkflowValidator` + `PolicyEngine`
- `Action and Healing`: `WorkflowExecutor`
- `Audit and Evolution`: `AgentRunService` writeback, audit, durable learning

因此当前代码不需要重写，只需要逐步补充：

- 更明确的任务抽象
- 更明确的双入口归一化
- 更明确的场景约束对象

## Reliability Model

系统可靠性拆分为四层：

- `Constraint reliability`
- `Execution reliability`
- `Memory reliability`
- `Decision reliability`

其核心思想是：

系统鲁棒性不依赖“更强的大模型”，而依赖“更强的约束、验证、状态、修复与写回”。

## Evaluation Model

论文评测建议统一使用四类指标：

- `Correctness`
- `Efficiency`
- `Robustness`
- `Practical utility`

baseline 至少包括：

- 纯 KG top-pattern
- 弱约束 LLM planning
- 无 repair 执行链
- 完整系统

## Near-Term Priority

当前优先级不是继续增加大量算法，而是先补齐论文叙事与执行态映射：

1. 固定术语与系统模式
2. 定义执行本体与论文本体映射
3. 补最小必要本体对象
4. 引入双入口任务归一化
5. 再补自动下载、缺字段补数和实验矩阵

## Immediate Conclusion

本设计确立了一个不会推倒重来的方向：

- 用 `算法 - 任务 - 数据` 作为可执行核心
- 用 `灾害/场景约束层` 影响规划与评估
- 用 `双入口 + 受约束 Plan-and-Execute + 反应式修复` 定义智能体模式
- 用显式状态、记忆与决策记录支撑论文中的可靠性与智能体叙事

这条路线与当前代码、开题报告方向和后续论文写作目标是一致的。
