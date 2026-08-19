# FusionAgent 后续研究方向与工作指引

> 状态：A3 历史研究方向快照
> 继承说明（2026-08-19）：当前研究主体与主张边界见 [`research-charter.md`](../current/research-charter.md)，当前阶段与下一验收点见 [`research-governance-index.md`](../current/research-governance-index.md)。本文仅用于追溯 2026-07-09 时点的讨论，不定义当前计划。

版本: 2026-07-09

本文档整理三部分内容:

1. 2026-07-07 JSONL 讨论记录和交接文档中的上一轮讨论。
2. 本轮关于降级/优先级、研究意义、数据源不足、是否重开项目的讨论。
3. 对近期强相关论文总结和部分原文阅读后的方向修正。

目标不是形成最终论文文本, 而是作为后续研究、系统调整、实验设计和论文写作的基本指引。

---

## 1. 总判断

当前 FusionAgent 不需要推倒重来, 但研究表述必须明显收缩并上移。

不宜再把核心创新表述为:

- 基于 KG 和 LLM 的灾害遥感/地理智能 Agent。
- LLM 调用工具完成灾害数据处理。
- 图规划、并行执行、局部修复、证据链、门控执行。
- 自动选择融合算法或自动生成 workflow。

这些方向已有较强相关研究覆盖, 且当前代码中的 LLM 空间也不足以支撑这些宽泛主张。

更稳的定位是:

> 面向灾害应急数据产品的契约化知识图谱框架, 将灾害场景、决策任务、数据产品、数据源、算法能力、质量门、证据链、降级策略和缺口声明统一建模, 并以 LLM 作为受约束的任务提议者, 实现无人值守条件下的数据产品生成、验收与证据化交付。

换句话说, 贡献不在融合算法本身, 也不在通用 LLM Agent, 而在:

- 把灾害应急需求转译为可执行、可验收的数据产品契约。
- 用知识图谱表达算法、数据、任务、灾害场景、质量与证据之间的约束关系。
- 让 LLM 在该约束空间中进行无人值守的数据产出编排。
- 对产出结果给出质量验收、证据链和缺口声明。

---

## 2. 上一轮讨论的关键结论

### 2.1 当前 LLM 参与存在根本问题

上一轮对代码的审查指出:

- 默认配置使用 mock LLM。
- `MockLLMProvider` 读取顶层 `candidate_patterns`, 但上下文中候选位于 `retrieval.candidate_patterns`, 因此默认 mock 路径并不能真正产生有效 LLM 计划。
- planner 失败后会回落到 KG fallback, 即确定性选择排序第一的 pattern。
- 现有 prompt 本质上要求优先高成功率候选, 由于候选已被 retriever 排序, LLM 实际空间接近 argmax。

因此, 之前的关键判断是:

> LLM 之所以显得不必要, 不是因为 LLM 不适合该问题, 而是因为系统把判断预先压缩成了排序分数和确定性 fallback。

要让 LLM 有合理位置, 不能只是把真 LLM 接上, 而要重新定义它负责的决策边界。

### 2.2 知识图谱不能只编码能力, 还要编码语境和约束

上一轮指出, 当前 KG 主要回答:

- 有哪些算法。
- 算法输入输出是什么。
- 哪些任务可以由哪些 pattern 支持。
- 哪些数据源可用于哪些数据类型。

这属于能力层。

但 LLM 真正需要的是:

- 在什么灾害场景下哪些图层更关键。
- 哪些数据源在特定灾害下可信度下降。
- 当前网络、时间、覆盖条件下应如何权衡时效、完整度和精度。
- 什么时候可以临时交付, 什么时候必须声明缺口。

因此 KG 的优化方向不是简单加节点, 而是:

> 从可执行的能力网, 升级为可推理的决策空间。

核心原则是:

> KG 编码约束和权衡关系, 不直接编码结论。

例如:

- 不应只写 "洪水 -> 使用某数据源"。
- 应表达 "洪水下时效约束更强, 水体/道路现势性更重要, 某些静态源可能过时, 多源融合提升完整度但消耗网络和时间预算"。

结论由 LLM 在具体处境下求解, 再由确定性校验器验证合法性。

### 2.3 成功工作流应作为证据, 不应作为直接模板回放

用户此前明确担心:

> 成功案例的工作流应保存学习, 但每次规划仍应由 LLM 根据 KG 做出, 而不是直接从工作流中读取; 否则会丧失灵活性, 甚至削弱 KG 其余部分。

上一轮形成的原则是:

> workflow-as-evidence, not workflow-as-template.

即:

- 成功案例要存。
- 存的不是一个成功率标量, 而是带条件的结构化案例。
- 检索案例时, 它们作为 LLM planning context 中的正反例证据。
- LLM 仍必须根据当前 KG 能力层、规范层、情境约束层重新生成 fresh plan。
- 任何计划仍需通过 runtime contract、grounding、quality gate 等确定性校验。

建议的经验层包括:

- `ExecutionCase`: 一次运行的结构化案例。
- `CaseStep`: 实际步骤、算法、参数、数据源、输入输出、步级结果。
- `SituationSignature`: 案例发生时的任务、灾害、AOI、覆盖率、资源条件等。
- `StructuralSignature`: workflow DAG 的规范化结构指纹。
- `PatternCandidate`: 多次成功的新结构经过升格闸门后成为规范层 pattern。

学习回路是:

```text
run 完成
-> 写入 ExecutionCase / SituationSignature / StructuralSignature
-> 后续 planning 检索相似正反例作为证据
-> 多次成功且新颖的结构进入 PatternCandidate
-> 经人工、LLM curator 或 shadow 模式审查
-> 升格为 WorkflowPattern
```

该回路不是短期最高优先级, 但它是后续自我优化的合理方向。

---

## 3. 本轮讨论形成的新定位

### 3.1 研究背景

本研究的应用背景是:

> 在灾害情境下, 无人值守地实现受灾区域数据快速产出。

典型情形:

- 如果具备网络条件和时间条件, 可下载多源数据并执行融合算法。
- 如果不具备完整数据下载条件, 应优先获取可用单源数据, 先产出可用的临时数据产品。
- 完整融合仍可在后台继续, 完成后再替换或补充临时产品。

这说明系统不是为了展示一个算法, 而是为了在灾害约束下持续产出可用数据产品。

### 3.2 研究核心

研究核心应改为:

```text
灾害应急数据产品契约
-> 数据需求
-> 数据源/算法/任务/质量/证据 KG
-> LLM 约束编排
-> 自动执行
-> 质量验收
-> 证据链与缺口声明
```

即从原来的:

```text
任务 -> 检索数据源 -> 选择算法 -> 执行 -> 验证
```

上移为:

```text
应急决策需求
-> 数据产品契约
-> 数据/算法/质量需求
-> 获取-融合-交付计划
-> 结果验收
-> 证据与缺口声明
```

这是本轮最重要的纠偏。

### 3.3 当前产品范围的进一步限定

后续研究中的产品应先限定为**固定数据源集合下的多源矢量融合数据产品**, 主要覆盖:

- 建筑物。
- 道路。
- 两类水系。
- POI。

这里的"数据产品"不是下游灾情判断结果, 也不直接决定具体应急用途。系统提供的是融合后数据本身, 重点体现:

- 几何丰富: 多源几何互补、补全、去重、合并。
- 属性丰富: 不同源属性字段整合、补充和规范化。
- 一定程度的拓扑冲突处理: 处理重复、重叠、断裂、明显不一致等问题。
- 相对原始单源数据更丰富、更优质、更可交付。

至于该融合数据后续用于通达性分析、暴露分析、救援制图还是其他任务, 应由使用者或后续系统决定。本文不应把下游应用效果作为核心贡献, 否则会把研究拉向灾情分析算法和应急业务决策, 偏离当前主线。

---

## 4. 强相关研究带来的创新点修正

近期论文阅读表明, 许多原本可能被表述为创新的点已经有强相关研究覆盖。

### 4.1 需要避免泛化声明的方向

| 方向 | 强相关研究信号 | 对 FusionAgent 的影响 |
| --- | --- | --- |
| 灾害地理智能 Agent | GeoDisaster 已覆盖灾害地理任务、工具执行、执行契约、step-level evidence、trajectory evaluation | 不能泛称"灾害地理智能 Agent"为核心创新 |
| EO/KG/LLM 管线 | EO-Agents、Agentic Search for EO Data Discovery 已有 EO-KG + LLM + 多 Agent / 数据发现 | 不能泛称"KG+LLM 用于遥感/地球观测"为创新 |
| 任务驱动数据生成 | SAGA 已有 schema-grounded SAR augmentation/generation agent, validation 和 evaluator | 不能泛称"LLM 自动数据生成"为原创 |
| 图规划和局部修复 | Atomic Task Graph 等已有 DAG 分解、并行调度、局部修复 | 不宜把图规划作为核心创新 |
| 证据图与门控执行 | VeriGraph、SKILL.nb、Paper-replication 等已有 evidence DAG、completion gate、workflow artifacts | 证据链应做灾害数据产品领域化, 不能泛称原创 |
| 规格到执行 | Specification-to-Execution 已有 spec validation before execution | 应借鉴, 但创新应在灾害数据产品契约 |

### 4.2 可借鉴但不应主张为原创的机制

- 从 `Semantic Gap` 借鉴: workflow 成功执行不等于操作化语义正确。需要关注 comparative grounding、process reasoning、quantitative reasoning、role confusion、policy grounding 等失败。
- 从 `Specification-to-Execution` 借鉴: 先验证规格/契约, 再生成或执行代码/流程。
- 从 `VeriGraph` 借鉴: evidence DAG, 但要专门化为 geospatial artifact provenance 和 product contract satisfaction。
- 从 `SAGA` 借鉴: schema-grounded proposal + deterministic validation + quality evaluator。
- 从 `Paper-replication` 借鉴: target/evidence/completion gate, 可迁移为数据产品 target/evidence/completion gate。
- 从 fault-tolerant control 思路借鉴: LLM 是 bounded proposer, KG/规则/执行器/质量门是 validator。

### 4.3 仍可辩护的 FusionAgent 创新

FusionAgent 更可辩护的创新不是单个算法, 也不是通用 Agent, 而是以下组合:

1. **灾害应急数据产品契约层**  
   将应急决策任务转译为数据产品的空间范围、时间窗口、图层需求、质量阈值、证据要求和可接受降级等级。

2. **算法-数据-任务-场景-证据一体化 KG**  
   不只记录算法和数据源, 还记录灾害场景下的数据适用性、源可信度修正、质量门、证据关系、缺口声明规则。

3. **LLM 作为受约束的无人值守编排者**  
   LLM 不负责发明算法, 而是在产品契约、资源处境和 KG 约束下提出获取-融合-交付计划。

4. **产出后验收与缺口声明**  
   系统不仅产出数据, 还说明数据是否满足契约、哪些条件未满足、结果应如何被使用。

5. **面向灾害应急数据产品的实验评价**  
   评价不只看算法指标, 还看产品契约满足度、时效、质量门通过率、证据完整性和缺口声明正确性。

---

## 5. 关于降级、优先级与高性能设备的判断

### 5.1 降级/优先级不是因为算力不足

应避免把降级讲成 "机器性能不够时的妥协"。对于应急相关部门, 高性能设备、多机并行、云端调度确实可以缓解计算瓶颈。

但灾害应急数据产出中的关键约束并不只来自算力, 还包括:

- 数据源是否存在。
- 灾后数据是否已发布。
- AOI 是否被覆盖。
- 遥感影像是否受云、烟、雪、水体遮挡影响。
- 数据下载链路是否可用。
- 数据许可和访问限制。
- 数据现势性是否满足任务。
- 不同源之间是否存在语义冲突。
- 时间窗口是否允许等待完整融合。
- 当前任务更需要快速可用结果, 还是更需要完整高精度结果。

这些问题无法通过简单增加计算设备完全解决。

因此, 本研究中的降级/优先级应重新表述为:

> 在当前证据和资源条件下, 系统判断可以交付何种等级的数据产品, 不能交付什么, 为什么不能交付, 以及后续如何补交或替换。

它不是消极降级, 而是应急数据产品的等级化交付和证据化声明。

### 5.2 优先级的研究意义

优先级不是 "先跑哪个算法" 的工程小技巧, 而是灾害数据产品契约中的语义要求。

例如:

- 地震后, 建筑和道路可能是 critical, 水系可能是 skip。
- 洪水中, 水体范围和道路中断可能更关键, 建筑轮廓的完整度可能次之。
- 森林火灾中, 建筑在某些 AOI 可能 `data_absent`, 这不是失败, 而是应声明 "该产品在该区域无基线数据"。

因此, 优先级应进入 KG 的产品契约层和灾害情境层, 而不是停留在 Python 中的静态 source priority dict。

---

## 6. 数据源少、数据类型少是否会显得薄弱

这个风险存在, 但不是致命问题。

如果研究只说 "我接了若干数据源, 自动跑融合", 数据源少会明显显得工作量不足。

但如果研究转为 "面向灾害应急数据产品的契约化产出", 工作量不主要体现在源数量, 而体现在:

- 数据产品契约是否完整。
- 灾害情境约束是否可解释。
- 算法、数据、任务、质量、证据是否形成闭环。
- LLM 是否能在资源处境下做出合理编排。
- 系统是否能正确声明不可满足条件。
- 实验是否覆盖足够多的失败模式和取舍场景。

因此, 更合理的策略是:

> 少数据源, 深场景; 少算法, 强契约; 少泛化, 强验收。

### 6.1 应避免的补强方式

- 不要盲目堆更多数据源。
- 不要把已有算法包装成原创融合算法。
- 不要把多个 demo 场景当作研究深度。
- 不要让论文变成工程清单。

### 6.2 更可行的补强方式

围绕有限数据源构造更深的契约和实验:

- 同一灾害场景下, 不同应急任务需要不同数据产品。
- 同一数据源在不同时间窗口、空间范围、覆盖条件下可用性不同。
- 同一融合结果在不同产品契约下可能合格, 也可能不合格。
- 当完整产品不可得时, 系统能否给出合理降级产品和缺口声明。
- 对比规则策略、KG-only、LLM-only、LLM+KG 在组合区的表现。

### 6.3 论文中的范围边界

建议明确写出适用范围, 不要假装覆盖所有灾害数据产品。

较稳的范围表述:

> 本研究面向灾害应急底图和基础矢量数据产品的无人值守产出, 在固定数据源集合下重点覆盖建筑物、道路、两类水系、POI 等基础图层, 研究对象是多源矢量数据的几何丰富、属性丰富、基础拓扑冲突处理、质量验收和证据化交付。

这意味着论文中应主动排除或弱化以下内容:

- 不主张直接完成灾情研判或应急决策。
- 不主张覆盖所有遥感/地理数据产品。
- 不主张融合算法本身是原创。
- 不把新数据源接入数量作为主要贡献。
- 不把下游使用效果作为核心评价指标。

对于海啸、森林火灾等存在源-灾种失配的问题, 应作为已知边界并显式建模:

- `source_mismatch`: 数据源与灾害核心观测对象不匹配。
- `data_absent`: 该区域本身缺少对应基线数据。
- `skip`: 该灾害任务下该图层不需要处理。

这些不是缺点, 而是系统诚实处理现实边界的能力。

### 6.4 多源接入能力的表述边界

固定当前数据源不代表系统没有扩展性, 但扩展性应作为 KG 知识层的理论能力和后续工作来表述。

建议写法:

> 本研究在固定数据源集合上验证契约化编排、质量验收与缺口声明机制。由于数据源、算法和产品约束均以知识图谱形式表达, 新数据源原则上可通过补充源语义契约、数据类型映射、质量属性和适用条件接入系统。但新源大规模接入不是本文实验重点。

这样既保留方法扩展性, 又避免被质疑 "既然声称多源泛化, 为什么实验源这么少"。

---

## 7. 推荐的整体架构

### 7.1 分层结构

建议将系统抽象为七层:

```text
L1 灾害场景层
   disaster type, response phase, affected area, decision objective

L2 应急数据产品契约层
   product target, required layers, spatial/temporal constraints,
   quality gates, evidence requirements, acceptable degradation

L3 数据需求与源语义层
   data requirements, source availability, freshness, coverage,
   contextual confidence, source mismatch, data absent

L4 算法与能力层
   algorithms, datatype lattice, transform path, fusion workflow patterns,
   runtime source contracts

L5 LLM 受约束编排层
   acquisition strategy, fusion plan, progressive delivery,
   triage order, rationale, replanning

L6 执行与校验层
   deterministic executors, runtime contract validation,
   plan grounding, quality gate, source/materialization checks

L7 证据与经验层
   product evidence, provenance, gap declaration,
   ExecutionCase, SituationSignature, StructuralSignature, promotion
```

### 7.2 核心数据流

```text
用户/系统触发
-> 灾害场景识别
-> 产品契约编译
-> 数据需求解析
-> KG 检索能力、源、约束、历史案例
-> LLM 提出获取-融合-交付计划
-> deterministic grounding / runtime contract 校验
-> 执行与监控
-> 质量门验收
-> 产出数据产品、证据链、缺口声明
-> 写入经验层
```

### 7.3 LLM 的合理职责

LLM 不应负责:

- 发明融合算法。
- 直接判断几何运算是否正确。
- 绕过 KG 选择未知数据源或算法。
- 代替质量门给结果背书。
- 直接 replay 历史 workflow。

LLM 应负责:

- 将自然语言/场景需求转译为候选数据产品契约。
- 在多个约束冲突时提出获取-融合-交付策略。
- 在资源受限时判断先交付什么、后台补什么、声明什么缺口。
- 在计划失败或条件变化时提出重规划建议。
- 为关键取舍输出 rationale, 便于无人值守审计。
- 参考相似正反案例, 但仍生成 fresh plan。

### 7.4 KG 的合理职责

KG 应负责:

- 存储算法、数据源、任务、数据类型、产品契约、质量门、证据规则。
- 表达灾害情境对图层优先级、源可信度、时效要求的影响。
- 提供能力闭包和约束检索。
- 提供相似案例证据。
- 支持 LLM 输出的 grounding 检查。
- 支持产品满足度与缺口声明。

### 7.5 确定性层的合理职责

确定性层应负责:

- 数据下载、转换、融合算法执行。
- runtime contract 校验。
- source contract 校验。
- datatype transform 校验。
- plan grounding。
- quality gate。
- 证据收集与报告生成。

---

## 8. 应急数据产品契约层: 当前最大遗漏

本轮讨论后, 当前最大的遗漏被明确为:

> 缺少一个足够明确、可评价的 Emergency Data Product Contract, 即应急数据产品契约层。

如果只有算法-数据-任务 KG, 很容易被评为 catalog、workflow planner 或工具路由器。

新增产品契约层后, 研究对象变成:

> 系统如何理解、生产并验收一个灾害应急场景真正需要的数据产品。

### 8.1 数据产品契约建议字段

一个产品契约至少应包含:

```text
product_id
disaster_type
response_phase
decision_objective
aoi
time_window
required_layers
  - layer_id
  - urgency: critical | important | optional | skip | data_absent
  - minimum_quality
  - accepted_sources
  - freshness_requirement
  - evidence_requirement
quality_gates
degradation_policy
gap_declaration_policy
delivery_policy
evidence_contract
```

对于当前阶段, `required_layers` 应优先限定为:

```text
building
road
water_type_1
water_type_2
poi
```

其中两类水系需要在后续 schema 中明确命名和语义边界, 例如常态水系/灾害相关水体, 或河网/水面等。命名一旦确定, 质量门、源适用性和灾种优先级都应围绕这两类水系分别定义, 不宜继续笼统写成 "water"。

### 8.2 产品契约不是简单 output schema

它不是 "输出 GeoJSON" 这样的格式约束, 而是:

- 这个灾害任务为什么需要这些图层。
- 每个图层必须达到什么质量。
- 哪些图层可以缺失, 哪些必须声明缺口。
- 临时产品与最终产品的差异是什么。
- 融合后数据相对原始单源数据在哪些方面更丰富或更可靠。

需要注意: 产品契约不应替系统承诺具体下游用途。系统交付的是融合后的多源矢量数据产品, 下游是否用于制图、通达性分析、暴露分析或其他应急应用, 由使用者决定。产品契约只负责说明该数据产品自身的图层、覆盖、几何、属性、拓扑、质量和证据状态。

### 8.3 产品契约与现有代码的关系

现有代码中已有若干可复用地基:

- `schemas/data_requirement.py`
- `schemas/degradation.py`
- `schemas/quality_gate.py`
- `schemas/quality_policy.py`
- `schemas/runtime_source_contract.py`
- `schemas/scenario.py`
- `schemas/mission.py`
- `schemas/experiment_evidence.py`
- `schemas/evidence_lifecycle.py`
- `schemas/plan_grounding.py`
- `services/output_contract_service.py`
- `services/scenario_run_service.py`
- `services/quality_gate_service.py`
- `services/runtime_contract_service.py`
- `services/source_semantic_contract_service.py`
- `services/evidence_lifecycle_service.py`

因此, 不需要另开项目。更合理的路线是在现有执行层和证据层之上增加产品契约层。

### 8.4 输出形态: 内部 JSON 与用户报告分离

缺口输出不应归入错误日志。错误日志回答 "系统哪里异常", 缺口声明回答 "在当前数据、资源和契约条件下, 哪些产品要求未被满足以及原因是什么"。两者语义不同。

建议将输出分成两类。

**机器可读输出:**

```text
product_contract.json
planning_decision.json
resource_regime.json
quality_gate_result.json
gap_declaration.json
evidence_trace.json
delivery_manifest.json
```

这些 JSON 面向智能体自身、后续重规划、实验统计和可复现审计。

**用户可读输出:**

```text
run_report.md / run_report.html / run_report.pdf
```

完整报告应面向使用者说明:

- 本次交付了哪些融合数据产品。
- 每个图层来自哪些源, 做了哪些融合、属性补充和拓扑处理。
- 哪些质量门通过, 哪些未通过。
- 哪些结果是临时交付, 哪些是最终交付。
- 哪些缺口存在, 缺口原因是什么。
- 这些缺口对数据使用有什么影响。
- 后续是否会后台补交或需要新增数据源。

这种双轨输出能把无人值守系统的内部决策、实验评价和用户解释分开, 避免把所有信息混入日志或自然语言报告。

---

## 9. 灾害情境约束本体 v2.1 的保留价值

上一轮讨论中形成的 "灾害情境约束本体 v2.1" 仍有价值, 但应被放入更大的产品契约框架中。

其核心包括:

- `DisasterResponseProfile`: 灾种响应画像。
- `LayerUrgency`: 灾种-图层紧急度矩阵。
- `ResourceRegime`: 网络、时间、阶段、预算压力等资源处境。
- `AcquisitionStrategy`: 全源、多源优先、单源先交付、分层 triage 等策略。
- `ConflictAxis`: 如 latency vs completeness, freshness vs coverage。
- `dominance`: 某灾种下哪条冲突轴是主导矛盾。
- `applicability`: well_grounded, source_mismatch 等。
- `data_absent` 与 `skip`: 区分 "无数据但需声明" 与 "任务无关可跳过"。

这些概念应作为产品契约层和 LLM 编排层之间的桥。

### 9.1 关键设计原则

灾害情境层应表达:

- 约束。
- 冲突。
- 偏好。
- 不确定性。
- 缺口声明规则。

不应表达:

- 固定结论。
- 永久源排序。
- "某灾种必用某算法" 的查找表。

### 9.2 对 LLM 的意义

该层为 LLM 提供非平凡决策空间:

- 多个 critical 图层竞争有限预算。
- 某些源已覆盖, 某些源未下载或失败。
- 部分图层可临时交付, 部分必须等待融合。
- 某些图层 `skip`, 某些图层 `data_absent` 需要声明。
- 主导冲突轴不同, 交付策略不同。

这比 "从候选算法中选成功率最高者" 更能支撑 LLM 的必要性。

---

## 10. 实验设计方向

实验应围绕产品契约满足度和无人值守产出能力, 而不是只看融合算法指标。

### 10.1 核心研究问题

建议形成四个研究问题:

```text
RQ1: 如何形式化灾害应急数据产品契约, 并将其与算法、数据源、任务、质量和证据统一到 KG 中?

RQ2: 在资源受限和数据不完整条件下, KG 约束的 LLM 是否能比固定规则或 KG-only 排序更合理地产出数据产品计划?

RQ3: 产品契约、质量门和证据链能否有效识别满足、部分满足和不可满足的数据产品交付状态?

RQ4: 在数据源数量有限的情况下, 该框架是否能通过多任务、多契约、多失败模式体现足够的泛化与研究价值?
```

### 10.2 对照基线

建议至少包含:

1. **固定优先级策略**  
   静态 source priority + 固定 fallback。

2. **KG-only / deterministic planner**  
   使用 KG 检索与规则排序, 但无 LLM 语义求解。

3. **LLM-only**  
   给 LLM 任务描述和候选工具, 但不给完整 KG 约束和产品契约。

4. **LLM + KG capability layer**  
   只给算法/数据/任务能力层, 不给产品契约和灾害情境约束。

5. **LLM + full contract KG**  
   给产品契约、灾害情境、资源处境、能力层、质量门和证据要求。

关键不是让 LLM 在简单 case 中胜出, 而是在组合区中胜出。

### 10.3 组合区实验

所谓组合区是:

```text
多 critical 图层
+ 不规则 source coverage
+ 紧时间或弱网络
+ 不同灾害情境优先级
+ 可临时交付/需后补融合
+ 需要缺口声明
```

这里才是固定规则、argmax 和简单 KG 排序容易失败的区域。

实验案例应适当扩大, 但扩大方式不是铺大量简单 demo, 而是挑选复杂情形。建议优先构造 6-8 个高密度案例:

- 地震后建筑和道路 critical, 水系 skip, OSM 已下载, 高精建筑源未完成。
- 洪水中水系和道路 critical, 建筑 important, HydroSHEDS 与遥感源现势性冲突。
- 森林火灾 AOI 中 POI 或建筑 `data_absent`, road critical, 系统需不浪费预算且声明缺口。
- 台风/暴雨后大范围 AOI, 覆盖优先于完整融合, 需分块渐进交付。
- 固定数据源中某个关键源下载失败, 但已有单源数据可形成临时产品, 系统需先交付 provisional product 并继续后台融合。
- 两个源几何冲突明显, 一个属性更丰富、一个几何更完整, 系统需说明融合取舍和质量风险。
- 完整融合结果质量门未通过, 但单源或部分融合结果可作为 degraded product 交付。
- 某 AOI 中 POI 或水系为空, 系统需区分 `data_absent`、`source_unavailable` 和 `quality_failed`。

这些案例应尽量覆盖建筑物、道路、两类水系和 POI, 同时覆盖几何丰富、属性丰富、基础拓扑冲突处理三类融合收益。

### 10.4 指标

建议指标分为六类:

1. **产品契约满足度**
   - required layers 是否交付。
   - critical 层是否优先。
   - quality gates 是否通过。
   - freshness / coverage / completeness 是否达到契约。

2. **时效与交付能力**
   - first usable product latency。
   - final product latency。
   - progressive delivery 是否合理。

3. **缺口声明正确性**
   - 是否识别 source_mismatch。
   - 是否区分 skip 和 data_absent。
   - 是否避免对不可满足产品作过度声明。

4. **证据完整性**
   - 是否记录数据源、算法、参数、质量门、失败原因。
   - 是否能追溯到 product contract。

5. **编排合理性**
   - layer triage 是否符合灾害情境。
   - 资源分配是否符合 dominant conflict axis。
   - rationale 是否与 KG 约束一致。

6. **运行鲁棒性**
   - 源失败后的重规划能力。
   - 后补融合替换能力。
   - 错误恢复和审计能力。

### 10.5 标准答案与评分 rubric

可以为选定实验案例预先制定标准答案, 但标准答案应服务于评价, 不应演变成系统运行时的全局固定规则表。

建议每个案例给出:

```text
case_id
scenario
input_sources_status
resource_regime
expected_layer_priority
expected_delivery_strategy
expected_gap_declaration
must_not_do
acceptable_alternatives
scoring_rubric
```

其中:

- `expected_layer_priority` 评价系统是否理解灾害情境下建筑物、道路、两类水系、POI 的相对重要性。
- `expected_delivery_strategy` 评价系统是否选择完整融合、单源先交付、渐进交付或降级交付。
- `expected_gap_declaration` 评价系统是否正确声明数据缺口, 而不是把缺口当成错误日志或静默忽略。
- `must_not_do` 明确禁止行为, 如对 `skip` 图层消耗预算、声称不存在的数据已经交付、把质量门失败结果标为 fully satisfied。
- `acceptable_alternatives` 保留合理策略空间, 防止标准答案过度收窄, 把 LLM 逼成固定规则执行器。

这种做法的边界是:

> 实验案例可以有局部标准答案, 但研究方法不应依赖一套覆盖所有场景的固定规则表。标准答案用于评估 LLM+KG 是否做出合理取舍, 不是替代 LLM+KG 做取舍。

### 10.6 文献对照写法

论文中可以这样区别已有研究:

- 与 GeoDisaster 不同, 本研究不以问答/工具执行 benchmark 为核心, 而以应急数据产品契约的产出与验收为核心。
- 与 EO data discovery 工作不同, 本研究不止检索数据集, 而是编排数据源、融合算法、质量门与证据链生成可交付数据产品。
- 与 SAGA 不同, 本研究不聚焦单一 SAR 数据生成, 而聚焦灾害应急底图产品的契约化交付。
- 与一般 evidence graph 不同, 本研究的证据图绑定 geospatial artifact provenance、quality gates 和 product contract satisfaction。

---

## 11. 代码路线判断

### 11.1 不建议另开项目

当前代码与新方向没有大到需要重开的冲突。

理由:

- 已有 agent、retriever、planner、executor、validator 基础。
- 已有 data requirement、degradation、quality gate、runtime contract、scenario、mission、evidence 等 schema。
- 已有 source semantic contract、output contract、scenario run、quality policy、evidence lifecycle 等服务。
- 现有执行层可作为产品契约框架的落地后端。

真正缺的是上层抽象和 LLM 决策边界, 而不是底层执行能力。

### 11.2 应避免的改造方式

- 不要把所有服务重写成新架构。
- 不要先大规模重构执行层。
- 不要继续只在 AOI、source fallback、building heights 等局部问题上消耗全部研究精力。
- 不要用更多硬编码 if 来假装实现灾害场景智能。

### 11.3 推荐改造方向

在现有基础上加一条上层链路:

```text
ProductContract
-> DataRequirement
-> ResourceRegime / DisasterContext
-> Contract-aware PlanningContext
-> LLM orchestration proposal
-> Grounding / RuntimeContract / QualityGate
-> ProductEvidence / GapDeclaration
```

### 11.4 需要优先修正的代码事实

短期工程地基:

- 修复 mock provider 与 planning context 的字段不一致, 否则默认路径无法验证 LLM。
- 防止服务层覆盖 LLM 已选择的 `data_source_id`。
- 将 QoS/resource regime 从惰性元数据变成会影响 planning context 和验证的字段。
- 给 plan 增加 orchestration rationale 或 decision rationale。
- 扩展 plan grounding, 校验 LLM 不得对 `skip`/`data_absent` 图层消耗预算, 不得声称不存在数据的源已交付。

这些不是最终研究贡献, 但会影响实验可信度。

---

## 12. 后续工作路线

### 阶段 0: 研究表述冻结

输出:

- 核心主张句。
- 贡献点列表。
- 非贡献边界。
- 与强相关研究的区别表。

目标:

- 不再泛称 KG+LLM Agent。
- 明确贡献在产品契约 KG 与无人值守数据产品产出。

### 阶段 1: 产品契约层设计

输出:

- `EmergencyDataProductContract` schema 草案。
- 产品范围目录: 固定数据源下的建筑物、道路、两类水系、POI 多源矢量融合数据产品。
- required layers、quality gates、evidence requirements、degradation policy。
- 内部 JSON 输出与用户完整报告的分离方案。

目标:

- 让 "什么叫产出成功" 可定义、可验证。

### 阶段 2: 灾害情境约束 KG seed

输出:

- DisasterResponseProfile。
- LayerUrgency 矩阵。
- ConflictAxis 与 dominance。
- ResourceRegime。
- applicability / source_mismatch / data_absent。

目标:

- 把灾害语义从代码 if 和自然语言说明中迁入 KG。

### 阶段 3: LLM 读路径与返回协议

输出:

- planning context 新结构。
- prompt 从 "选择高成功率候选" 改为 "在契约与冲突轴下综合求解"。
- `orchestration_rationale`。
- grounding issue codes。

目标:

- 让 LLM 真正参与无人值守编排, 而不是 top-1 selector。

### 阶段 4: 质量验收与缺口声明

输出:

- ProductContractSatisfaction report。
- GapDeclaration。
- EvidenceGraph / provenance report。
- 临时产品与最终产品的 supersede 关系。

目标:

- 系统不仅出数据, 还说明该数据能否被应急任务使用。

### 阶段 5: 实验矩阵与基线

输出:

- 组合区 benchmark。
- 固定策略、KG-only、LLM-only、LLM+KG 的对照。
- 选定复杂实验案例的标准答案、可接受替代策略和人工评审 rubric。
- 指标计算脚本。

目标:

- 证明完整 contract KG + LLM 的增量价值。

### 阶段 6: 经验层与升格回路

输出:

- ExecutionCase。
- SituationSignature。
- StructuralSignature。
- case evidence retrieval。
- PatternCandidate shadow promotion。

目标:

- 从单次运行扩展到可持续自我优化。

该阶段可作为后续工作或论文展望, 不一定全部作为硕士阶段主贡献实现。

---

## 13. 建议的创新点表述

### 13.1 不建议使用

不建议写:

> 提出一种基于知识图谱和 LLM 的灾害遥感数据融合智能体。

原因:

- 太泛。
- 容易撞上 GeoDisaster、EO-Agents、Agentic Search、SAGA 等工作。
- 不能体现产品契约和无人值守验收的特色。

### 13.2 建议使用

建议写:

> 提出一种面向灾害应急数据产品的契约化知识图谱框架, 将灾害场景、决策任务、数据产品、数据源、算法能力、质量门、证据链和降级策略统一建模, 支撑无人值守条件下的数据产品生成、验收与缺口声明。

可以进一步拆成三个创新点:

1. **契约化灾害应急数据产品 KG**  
   面向无人值守应急产出, 构建包含灾害场景、数据产品、任务、数据源、算法、质量门、证据链和降级策略的知识图谱, 解决传统算法/数据目录难以表达产品验收语义的问题。

2. **KG 约束的 LLM 编排机制**  
   将 LLM 定位为受约束的编排提议者, 在产品契约、资源处境和灾害情境约束下生成获取-融合-交付计划, 并通过确定性 contract validation 和 grounding 约束其输出。

3. **面向无人值守交付的证据化验收机制**  
   建立数据产品满足度、质量门、证据链和缺口声明机制, 使系统不仅能产出数据, 还能说明其可信边界和未满足条件。

如果需要第四点, 可写:

4. **资源受限场景下的渐进式数据产品交付策略**  
   支持在网络、时间、覆盖不完整条件下先交付临时可用产品, 后续以更完整融合产品替换, 并保留 supersede 关系和质量证据。

---

## 14. 仍需继续讨论的问题

以下问题尚未完全定稿, 建议后续继续讨论。

### 14.1 产品类型目录到底收多宽

该问题已有基本结论: 硕士阶段产品范围先限定为固定数据源下的建筑物、道路、两类水系、POI 多源矢量融合数据产品。

仍需继续细化的是:

- 两类水系的正式命名和语义边界。
- 每类图层的融合收益如何表述: 几何丰富、属性丰富、拓扑冲突处理分别如何体现。
- 临时产品、降级产品、最终融合产品的命名和版本关系。
- 哪些下游用途只作为可能用途说明, 不进入本文评价指标。

原则上不纳入淹没范围提取、通达性分析、受损评估等下游任务, 避免扩到灾情分析全链条。

### 14.2 质量门如何绑定产品契约

需要明确:

- 每种产品的 minimum quality 是什么。
- 哪些质量指标可自动计算。
- 哪些需要 proxy metric。
- 哪些必须通过人工或半自动评审。

没有质量门, 产品契约会停留在文本声明。

### 14.3 证据链的最小闭环是什么

需要定义最低可接受证据:

- 数据源证据。
- 下载/覆盖证据。
- 算法执行证据。
- 参数证据。
- 质量门证据。
- 缺口声明证据。

不要一开始追求复杂 evidence graph, 先形成最小可审计闭环。

### 14.4 LLM 评价是否需要人工标准答案

LLM 的 rationale 和编排合理性可能需要人工 rubric。

建议为选定复杂案例制定局部标准答案和小规模人工评审表:

- 是否遵守 product contract。
- 是否正确优先 critical layer。
- 是否合理使用 progressive delivery。
- 是否正确声明缺口。
- 是否避免不可用源和无意义任务。
- 是否给出可接受的替代策略, 而不是机械匹配唯一答案。

需要特别避免的是: 将这些案例标准答案反向固化成一套全局规则表。标准答案用于实验评价, 不应替代 LLM+KG 的处境化求解。

### 14.5 是否需要真实应急部门工作流支持

如果能获得应急部门实际数据产品需求或应急制图规范, 产品契约层会更站得住。

如果没有, 可使用公开灾害响应指南、地图制图产品规范、已有 EO disaster response benchmark 作为支撑, 但论文中必须说明来源。

---

## 15. 当前应坚持的边界

### 15.1 研究边界

坚持:

- 融合算法不是贡献。
- 产出对象是融合后的多源矢量数据本身, 不是下游灾情判断。
- 评估方法不是原创, 但其知识化和契约化使用是贡献的一部分。
- LLM 不是全能决策者, 而是 bounded proposer。
- KG 不是静态 catalog, 而是产品契约和约束空间。
- 降级不是低性能设备的补丁, 而是数据产品等级化交付。
- 缺口声明是正式产品输出的一部分, 不是错误日志。
- 新数据源接入能力作为 KG 扩展性和后续工作说明, 不是当前实验重点。

### 15.2 工程边界

坚持:

- 不重开项目。
- 不先大规模重构。
- 先补上产品契约层和 LLM 决策边界。
- 保留现有执行/质量/证据服务作为后端。
- 每个阶段都应有可验证产物。

### 15.3 论文边界

坚持:

- 不夸大为通用灾害智能体。
- 不夸大为新融合算法。
- 不夸大为全自动灾情认知。
- 不把已有 KG+LLM/Agent/evidence graph 机制包装成原创。
- 明确与 GeoDisaster、SAGA、EO-Agents、Agentic Search 等工作的差异。

---

## 16. 一句话路线图

后续工作应围绕以下主线推进:

```text
限定建筑物、道路、两类水系、POI 多源矢量融合产品
-> 定义应急数据产品契约
-> 扩展灾害场景 KG 为契约和约束空间
-> 让 LLM 在该空间中做受约束编排
-> 用确定性校验和质量门验收结果
-> 输出机器可读 JSON、用户报告、证据链和缺口声明
-> 在组合区实验中证明其优于固定规则和简单 KG 排序
```

如果只能抓一个核心, 就抓:

> 产品契约满足度。

它是连接 KG 设计、LLM 必要性、无人值守应用、质量验收和论文评价的中介层。

---

## 17. 2026-07-09 最新补充共识

经过后续讨论, 当前进一步明确以下边界。

### 17.1 当前最大问题

当前最大问题不是方向不清, 也不是是否继续增加算法或数据源, 而是:

> 能否把产品契约满足度做成可评价、可复现、可对照的研究对象。

也就是说, 后续工作必须回答:

```text
什么融合数据产品算成功?
哪些图层必须交付?
几何、属性、拓扑质量达到什么程度算可用?
什么情况下算降级可用?
什么情况下必须声明缺口?
LLM+KG 的编排如何比固定规则或 KG-only 更合理?
```

如果这些问题不清楚, 系统容易退回到 "KG + LLM 调流程" 的泛化表述, 研究说服力会不足。

### 17.2 产品范围已收窄

当前产品范围限定为固定数据源集合下的多源矢量融合数据:

- 建筑物。
- 道路。
- 两类水系。
- POI。

产出目标是相对原始单源数据更丰富、更优质的数据本身, 主要体现几何丰富、属性丰富和一定的拓扑冲突处理。系统不直接决定这些数据后续用于何种应急业务, 下游用途由使用者决定。

### 17.3 缺口输出应双轨化

缺口声明不是错误日志。建议形成:

- 智能体内部读取的结构化 JSON。
- 用户可读的一份完整报告。

内部 JSON 用于重规划、评价和审计; 用户报告用于解释交付了什么、缺了什么、为什么缺、是否可用、后续是否可补。

### 17.4 实验案例应扩大但保持高密度

实验应挑选复杂情形, 覆盖:

- 多 critical 图层。
- 固定数据源下的不规则覆盖。
- 时间或网络限制。
- 源失败或质量门失败。
- 临时交付与最终融合替换。
- `skip`、`data_absent`、`source_unavailable`、`quality_failed` 等缺口类型。

不应把实验扩展成大量简单 demo。

### 17.5 可以制定案例标准答案, 但不能固定规则化

对选定实验案例可以制定标准答案和评分 rubric, 例如期望图层优先级、交付策略、缺口声明和禁止行为。

但这些标准答案只用于评价, 不应反向固化为全局固定规则。否则会削弱 LLM+KG 的处境化求解意义。

### 17.6 多源扩展是后续能力, 不是当前重点

当前实验固定数据源。后续多源接入能力可作为 KG 知识层的理论扩展:

- 新源可通过源语义契约进入 KG。
- 新源需声明数据类型、覆盖、质量、现势性、适用条件和限制。
- 新源可被纳入同一产品契约和质量门机制。

但本文重点不应放在证明可以无限接入新源, 而应放在固定源条件下证明契约化编排、质量验收和缺口声明机制成立。
