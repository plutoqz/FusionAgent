# 后续设计优化与补充实验

> 状态：A1 当前后续实验设计；第一组 held-out confirmation 已执行
> 更新日期：2026-09-05
> 研究口径依据：`D:\code\FusionAgent\docs\thesis\research_direction_guide_2026-07-09.md`、`D:\code\FusionAgent\docs\current\research-charter.md`
> 当前实验口径：五方法直接比较、三类 KG 模块消融、冻结 held-out、受控 planning/replay 与真实 E2E 分开报告

本文面向以下研究核心建立后续证据闭环：

```text
应急决策需求
-> 数据产品契约
-> 数据/算法/质量/证据知识
-> KG 约束的 LLM 与确定性规划
-> 获取、融合和交付
-> 质量验收
-> 渐进交付、恢复、证据与缺口声明
```

系统级和真实 E2E 的统一主要结局是**产品契约满足度**。它不是单一平均分，而是由图层交付、时效、几何/属性/拓扑质量、证据完整性、gap 正确性、降级合法性和 supersession 正确性组成的可审计判定。Planning-only 的 E1 单独使用预注册 `semantic_delivery_v2` 评价语义规划，不把它冒充系统级契约满足度。I1-I4 分别回答知识是否表达充分、知识是否实际驱动行为、治理是否改善交付，以及结论是否可以独立复核。

本文是后续实验的设计输入，不自动授权 Provider 或真实 E2E。2026-09-05 起不再把 template authoring、P0-P7 闸门、独立 judge、confirmation selection 或 Pareto 筛选作为实验目标；既有代码保留为基础设施，但不以其完成度替代实验结果。

## 0. 2026-09-05 状态更新与剩余证据缺口

### 0.1 已完成的第一组实验

| 实验 | 规模 | 已得到的结果 | 结论等级 |
| --- | ---: | --- | --- |
| Adversarial baseline | 60 对 base/fault，120 个成员，960 rows，720 次真实调用 | Full KG fault-only 21.7%，rules 8.3%，fixed 0%；capability 消融 aggregate 下降 35.8 pp | 探索性局部优势和模块信号 |
| Held-out confirmatory | 120 对 base/fault，240 个成员，2640 rows，2160 次真实调用 | Full KG 与 capability KG primary 均为 3.3%；full vs rules 差值 3.3 pp，cluster 95% CI [0, 10.0%]，p=0.125 | Primary 未确认整体 superiority |
| Held-out post-hoc decomposition | 同上 | Full KG semantic delivery 31.7%，rules/fixed 2.5%；差值 29.2 pp，cluster 95% CI [6.7%, 53.3%] | 诊断性语义规划优势，需预注册复验 |

第一组实验已经完成“在更难案例和更大样本上挑战规则与固定流程”的目标，但也暴露出原 primary composite 同时捆绑 semantic decision、canonical order、grounding、逐字 evidence anchor、veto 和 delivery state，导致局部语义优势无法被单独确认。这个结果不能通过事后降低标准修正，只能用于设计新的预注册实验。

### 0.2 当前剩余的四个实验问题

1. Full KG 的 semantic delivery 优势能否在新冻结案例和预声明指标上重复？
2. Capability、ontology 和 contract 三类 KG 模块各自是否具有独立、可重复的贡献？
3. 所有方法共同失败的 implicit hard-veto、source/retry 和 evidence-chain 场景，能否通过 KG 授权的确定性验证与恢复得到正确终态？
4. Planning 差异能否在真实 source-closed GIS 输入上转化为 acquisition、融合质量、交付状态和 artifact 证据差异？

后续只围绕这四个问题推进，不再增加方法选择治理支线。

## 1. 目标主张与实验闭环

| 目标主张 | 对应创新/RQ | 必需比较 | 主要评价对象 | 升级条件 |
| --- | --- | --- | --- | --- |
| 契约化七层 KG 能完整、一致、可追溯地表达限定领域知识 | I1 / RQ1 | 分散知识基线、能力目录型 KG、完整契约 KG | CQ、专家标注、约束、来源追溯 | 覆盖、一致性和追溯结果完成独立评价 |
| KG 变化会因果性改变规划、验证、源解析、质量门和恢复 | I2 / RQ2 | 隐藏规则/固定实现与 KG 驱动实现 | 单变量反事实、fail-closed、决策溯源 | 多任务、多后端上出现预注册的成对行为变化 |
| KG 约束 LLM 在复杂处境中提高可执行计划和契约满足 | I2 / RQ3 | fixed、rules-only、LLM-only、LLM+capability KG、LLM+full contract KG | semantic decision/order/delivery、严格 composite、成本 | 五方法公平、真实 LLM、重复、预注册 oracle 和区间闭环 |
| 产品契约、质量门和恢复提高正确交付而非放宽接受 | I3 / RQ4 | 无契约、无质量门、无恢复、固定优先级、完整方法 | 最终契约状态、错误接受、及时性、恢复、gap | 预注册故障、多 AOI、对照和选择性 E2E 闭环 |
| 融合产品相对单源更丰富且保持可接受质量 | 研究核心 / RQ4 | 最佳单源、简单 union、既有确定性融合 | 几何、属性、拓扑、覆盖、lineage | 独立真值或专家评价下获得任务特定质量证据 |
| 正式结论可重复、可篡改检测、可独立审计 | I4 / RQ4 | 原始包、重跑包、篡改包 | manifest、语义哈希、verifier、独立复跑 | 每项核心主张均绑定原始证据和独立复核结果 |

## 2. 设计优化

### 2.1 将产品契约固定为唯一评价中介层

建立版本化 `ProductContract`，至少包含：

- `contract_id`、`scenario_id`、`aoi`、`time_window`；
- `required_layers`、`optional_layers`、`skip_layers` 和每层 priority；
- 每层允许的数据源类型、融合模式和禁止行为；
- 几何、属性、拓扑、覆盖、现势性和 lineage 的质量阈值；
- `delivery_deadline`、`allowed_delivery_levels`、`provisional_ttl`；
- `evidence_requirements`、`gap_taxonomy`、`supersession_policy`。

建立独立 `ContractSatisfactionEvaluator`，输出维度向量而不是不透明总分：

```text
layer_delivery
timeliness
quality_acceptance
forbidden_action
gap_correctness
degradation_legality
supersession_correctness
evidence_completeness
overall_contract_state
```

`overall_contract_state` 只能由冻结规则根据上述维度生成，LLM 不负责判定自身是否满足契约。

**预计加强表述：** 从“系统保存了产品契约字段”推进到“产品契约是规划、验收、降级和评价共同使用的可计算对象”。

### 2.2 建立 case-to-KG 唯一 crosswalk

为每个案例建立显式映射：

- `case_id`、`scenario_id`、`task_kind`、`contract_id`；
- `source_id`、`algorithm_id`、`quality_policy_id`、`repair_policy_id`；
- `kg_release_id`、`semantic_hash`、`mapping_status`、`fixture_only_reason`；
- 每个 gold 条目所依赖的 KG 实体、关系和约束。

不存在于 KG 的对象必须标为 `unsupported` 或进入新 KG 版本候选，禁止由 Python alias、默认值或 runner 常量静默补齐。

**预计加强表述：** 从“案例包含 KG-like context”推进到“案例、gold、计划和执行均可回链到同一冻结 KG release”。

### 2.3 消除第二知识真源

将灾害词汇、任务映射、源适用性、算法能力、质量阈值、降级许可、修复动作和证据要求统一归入 KG/政策 release。运行代码只保留：

- schema 解析；
- 图查询和候选投影；
- 数值计算；
- 状态机与执行机制；
- fail-closed 校验。

新增静态审计和运行追踪，要求每个决定记录：

- 使用的 KG 实体/政策 ID；
- 决策输入和版本；
- selected、resolved、executed、evaluated 四个状态；
- fallback 的触发阶段、原因和新 artifact hash。

**预计加强表述：** 从“KG 参与部分规划”推进到“限定决策链由单一版本化知识源驱动并可逐项归因”。

### 2.4 从 canonical context 生成公平的五方法视图

先由 `KGRepository`、政策 registry 和案例 observation 生成唯一 canonical context，再按预注册 allowlist 投影：

1. fixed workflow；
2. rules-only；
3. LLM-only；
4. LLM + capability KG；
5. LLM + full contract KG。

每组保存 visible-field manifest、projection hash、来源和禁止字段。要求：

- fixed workflow 不读取 case gold；
- rules-only 有独立规则实现，不是 fixed workflow 改名；
- 三个 LLM 组使用同一模型、prompt、schema、temperature、max tokens 和重试规则；
- 组间只改变已声明的知识视图；
- 实验模式单独报告 pre-fallback 计划，fallback 不覆盖原始失败。

**预计加强表述：** 从“多个配置可运行”推进到“五方法比较的信息边界公平且可审计”。

### 2.5 重新定义 LLM 的有效决策空间

案例应要求 LLM 处理以下处境化组合，而不是对已排序候选做 argmax：

- 模糊自然语言需求到产品契约字段的解释；
- 多 critical 图层与截止时间冲突；
- 数据覆盖、现势性、网络和时间条件组合；
- 完整融合与 provisional 交付之间的取舍；
- source mismatch、data absent、source unavailable 和 quality failed 的区分；
- 失败后的结构性重规划，而不是只换一个算法 ID；
- 相似历史案例作为条件证据，而不是直接模板回放。

规划输出必须包含候选计划、引用的 KG ID、权衡理由、预期交付等级、gap proposal 和禁止行为自检；最终合法性仍由确定性 validator 判断。

**预计加强表述：** 从“LLM 调用工具”推进到“LLM 在知识和产品契约限定的组合空间中提出可验证计划”。

### 2.6 固化交付生命周期和双轨缺口输出

统一产品生命周期：

```text
requested
-> planned
-> materializing
-> provisional/degraded/final/rejected
-> superseded（可选）
```

缺口输出同时生成：

- 机器可读 JSON：供重规划、统计和审计；
- 用户可读报告：说明已交付内容、未满足条件、原因、可用等级和后续补交关系。

每个状态转换必须绑定产品契约条款、质量报告、artifact、时间和决策来源。

**预计加强表述：** 从“系统有 gap 日志”推进到“缺口声明和 supersession 是正式数据产品的一部分”。

### 2.7 将融合质量拆为几何、属性、拓扑和来源四类

为建筑、道路、水面、水系线和 POI 分别冻结质量 schema：

- 几何：validity、重复/重叠、位置偏差、覆盖、遗漏和新增正确率；
- 属性：非空率、字段保留、来源间冲突、规范化正确率和新增属性正确率；
- 拓扑：道路/水系连通性、dangle、断裂、自相交和面重叠；
- 来源与证据：source contribution、feature lineage、license/version、时间和 artifact hash。

质量报告必须同时列出每个单源、简单 union、确定性融合和最终交付产品，避免以最终要素数替代质量改善。

**预计加强表述：** 从“结果包含更多要素”推进到“融合产品在指定质量维度上相对公平基线更丰富且保持或改善正确性”。

## 3. 补充实验

### 3.1 RQ1：知识表达、覆盖和一致性实验

**比较对象：**

- 分散 Python/schema/配置基线；
- 只包含算法和数据能力目录的 KG；
- 完整契约化七层 KG。

**实验单元：**

- 8 个现有 competency questions 的可执行版本；
- 按情景、产品、数据、算法、质量、恢复和证据分层的新 CQ；
- 专家标注的知识片段和 case-to-KG crosswalk。

**指标：**

- CQ answer correctness / completeness；
- 必需实体、关系和约束覆盖率；
- 冲突、孤立对象和来源缺失率；
- 版本追溯成功率；
- 独立专家一致性和分歧裁决结果。

**验收标准：**

- 每个 CQ 具有预注册期望答案和来源锚点；
- 所有正式案例均完成 crosswalk，无静默 alias；
- 专家评价和机器约束均生成冻结结果；
- 与两个基线完成同口径比较。

**预计加强表述：** “在限定产品域和预注册问题集上，七层 KG 对产品契约、能力、质量、恢复和证据知识提供了更完整且可追溯的表达。”

### 3.2 RQ2：KG 因果绑定和 fail-closed 实验

**设计：** 使用成对反事实模板，每对只改变一个知识变量：

- required/optional/skip layer；
- 图层 priority 或 deadline；
- source availability / freshness / coverage；
- algorithm capability 或输入输出类型；
- quality threshold；
- allowed degradation；
- repair authorization；
- evidence requirement。

**观察链：**

```text
KG intervention
-> candidate set
-> selected plan
-> validator result
-> resolved source/algorithm
-> executed action
-> quality/recovery decision
-> contract state and evidence
```

**指标：**

- 预期行为变化命中率；
- 不应变化字段的语义稳定率；
- 缺失知识 fail-closed 率；
- 决策 KG ID/政策 ID 溯源完整率；
- memory/Neo4j parity；
- selected-resolved-executed 一致性。

**验收标准：** 多任务、多知识变量和两个后端均出现预注册、可解释、单变量驱动的行为变化；不存在第二知识真源造成的反事实失效。

**预计加强表述：** “KG 不仅存储知识，而且对规划、验证、源解析、质量门和恢复产生可重复的因果约束。”

### 3.3 RQ3：预注册 semantic-planning confirmation

第一组 held-out 已完成，但 semantic delivery 是运行后分解指标。下一轮必须在生成新案例和调用模型前，将其冻结为 primary outcome，不能复用当前 120 个 fault members 作为独立确认集。

**比较方法：**

- `llm_only`；
- `llm_capability_kg`；
- `llm_full_contract_kg`；
- `rules_only`；
- `fixed_workflow`。

**建议规模：** 24 个独立场景簇 × 5 类产品 × 2 个实例，形成 240 对 base/fault、480 个案例成员。三种 LLM 方法每个成员运行 3 次，共 4320 次真实 Provider 调用；规则和固定流程各运行一次。最终样本量仍需根据最小关注差异和 scenario-cluster 设计效应在 protocol 中复核，但不得小于当前 120 对 held-out。

**场景覆盖：**

- alias/crosswalk 与身份歧义；
- 多任务 precedence 和候选计划冲突；
- 多源状态、许可、coverage、freshness 和 fallback 冲突；
- algorithm capability 与 contract policy 冲突；
- quality degradation、部分交付和 primary/secondary channel；
- implicit veto、retry exhaustion 和 evidence-chain gap；
- 单、双、三重约束组合，并在各层保持产品平衡。

**预声明主要指标：**

1. `semantic_delivery_v2`：决策、canonical task order、合法 delivery state 和必要 grounding 同时正确，但不要求逐字复述 observation ID。
2. `hard_constraint_safety`：hard-veto、forbidden action、非法算法/数据源接受和错误 unrestricted delivery 分开计数。
3. 原严格 composite 保留为 secondary，用于衡量 evidence anchor 和完整交付约束，不再掩盖语义决策分解。

**统计：** 案例级多数结果为主分析单位；报告 Wilson interval、scenario-cluster bootstrap 配对差值和逐场景结果。Full KG 相对每个基线分别报告，不通过综合排名或 Pareto selection 选冠军。

**验收标准：** 只有 full KG 相对所有基线的预声明 semantic primary 差值区间下界均大于 0，才能把当前 post-hoc 局部优势升级为独立确认结论。若 primary 不成立，保留结果并停止宣称 semantic superiority；无论结果如何，都不能外推到真实 E2E。

### 3.4 KG 三模块 held-out 消融

Adversarial 消融显示 capability grounding 的 aggregate drop 为 35.8 pp，ontology drop 为 3.3 pp，而移除 contract 后反而上升 1.7 pp。由于该轮没有 exact-input 随机重复，且当前 held-out 未运行 `without_*` 条件，下一轮必须单独确认模块贡献。

**比较：** 以 `llm_full_contract_kg` 为唯一基线，在相同新案例、模型、Prompt、预算和 3 次 exact-input 重复下分别运行：

- `without_ontology_identity_crosswalk`；
- `without_capability_algorithm_grounding`；
- `without_contract_quality_delivery_policy`。

**模块特定主要指标：**

- Ontology：alias/crosswalk resolution、identity consistency、canonical precedence；
- Capability：合法 algorithm/source grounding、错误能力接受率、base planning validity；
- Contract：quality state、delivery level、gap/evidence decision、错误 unrestricted delivery；
- 严格 composite 只作为共同 secondary，不用其单一总分替代机制指标。

**Contract 场景必须包含：**

- 同一数据结果在不同契约下分别合格和不合格；
- required/optional/skip 图层差异；
- 不同 deadline 和 provisional 许可；
- 相同质量指标对应不同产品等级；
- evidence 缺失导致不可交付；
- 明确禁止的不合格结果接受。

**验收标准：** 每个模块都必须在其预声明机制指标上报告配对差值和 scenario-cluster interval。只有区间方向稳定且未以其他模块信息泄漏补回，才可表述为独立必要；没有增益的模块必须保留为负结果，不继续拆节点寻找事后显著性。

**预计加强表述：** 分别回答 capability、ontology 和 contract 哪一类知识对哪一类决策必要，而不是笼统声称“知识越多越好”或“七层都已证明必要”。

### 3.5 RQ4：质量门、恢复和渐进交付对照

当前 adversarial non-explicit veto 和 held-out implicit hard-veto 均为所有方法全败，因此这一组优先级高于继续扩大 clean-case planning。建议至少覆盖 6 类故障 × 5 类产品 × 4 个独立实例，形成 120 个 failure opportunities；每个机会预先声明应 veto、可恢复、应降级、应部分交付或应最终拒绝。

**比较：** 完整方法、无质量门、无降级恢复、固定优先级，以及按 3.4 定义的契约消融。

**故障与时序：**

- source unavailable / timeout；
- coverage insufficient；
- semantic mismatch；
- schema/type invalid；
- quality gate failed；
- late source arrival；
- provisional artifact 已发布后完整融合到达；
- 修复失败或无合法修复动作。

自然失败不是必要条件。允许使用预注册故障注入，但注入层、机会、强度、gold 和停止条件必须在运行前冻结，不能在看到结果后调整。

**实验单元：** failure opportunity，而不是所有 task 行；每个机会记录是否应恢复、允许动作、恢复代价和正确终态。

**主要指标：**

- 错误接受率；
- 最终契约状态正确率；
- eligible recovery success rate；
- 非法恢复率；
- 恢复代价和时延；
- 关键图层按时交付率；
- provisional/final/supersession 正确率；
- gap 和 evidence 完整率；
- 质量损失。

**E2E 选择：** 只从 planning 实验中预注册具有组间差异且 source-closed 的代表案例，覆盖多个 AOI；每例绑定真实输入、独立参考源、failure opportunity 和 artifact hash。

**预计加强表述：** “产品契约、质量门和知识化恢复在预注册故障条件下改善正确交付、恢复和审计结果，同时避免通过放宽质量标准制造成功。”

### 3.6 融合产品质量对照实验

该实验评价已有融合算法生成的数据产品，不将算法本身包装为论文创新。

**每类产品的公平基线：**

1. 主要单源；
2. 最佳可用单源；
3. 简单拼接/union；
4. 当前确定性融合算法；
5. 系统实际交付产品。

**数据与真值：**

- source-closed AOI；
- 与测试源独立的公开参考数据；
- 分层人工标注样本；
- 属性和拓扑专家复核；
- 每个源的版本、时间、许可和空间覆盖记录。

**指标：**

- geometry precision/recall 或匹配代理及误差分布；
- 新增要素正确率、遗漏率和重复率；
- 属性完整率、正确率和冲突解决正确率；
- 道路/水系连通性、dangle、断裂、重叠和自相交；
- source contribution 与 feature lineage 完整率；
- 相对于各基线的质量增益和代价。

**验收标准：** 每个“更丰富”结论同时报告新增量和新增正确率；每个“更优质”结论绑定具体质量维度、基线、真值和效果量。

**预计加强表述：** “在指定 AOI、数据源和产品类型上，多源融合产品相对公平单源/union 基线在明确的几何、属性或拓扑指标上获得可测改善。”

### 3.7 I4：独立复现和证据篡改实验

**实施：**

- 每个正式 cell 保存 branch、commit、clean status、KG release、contract version、case/template/evaluator version、Provider/model、prompt、schema、seed、预算、原始响应、日志、失败和 artifact hash。
- 对时间戳、绝对路径、run ID 和容器字节进行规范化，分别报告 byte stability、semantic stability 和允许波动。
- 分别篡改输入、KG、产品契约、prompt、输出、质量报告和 manifest，一个字节变化必须使 verifier 非零退出。
- 由未参与开发的复核者在全新 worktree 复跑代表 cell，核对主要指标和 claim-evidence index。

**验收标准：** 所有核心论文表格均可回链到原始 cell；所有失败、排除和协议偏差可查询；独立复跑和篡改检测通过预注册标准。

**预计加强表述：** “研究结论可以由独立执行者依据冻结 manifest、语义哈希和 verifier 重复、定位与核验。”

## 4. 评价与统计规则

1. 预先冻结 primary outcome、secondary outcomes、分母、`not_assessable` 语义和停止条件。
2. 分开统计 case、template instance、condition、repetition、rubric item、failure opportunity、AOI 和 artifact，禁止混为独立样本。
3. 参数化 benchmark 的样本量通过开发 pilot 的方差和目标最小效应确定，并在 confirmation 前冻结。
4. 成对案例优先使用配对效应量和区间；多 AOI/多模板分析使用能够表示分层结构的模型。
5. 主要结论使用冻结 deterministic oracle；人工抽查只用于发现 evaluator 漏洞，不作为独立 judge 或方法筛选分数。
6. 自动 evaluator、人工评价、GIS 质量真值和最终契约状态分别报告，不用单一总分掩盖机制差异。
7. Adversarial、held-out confirmation、模块消融和真实 E2E 分开登记，不混池平均。
8. 保留负结果、失败运行、协议偏差和未执行尾部；不修改 gold、metric、case 或停止条件追求正向结论。

## 5. 推荐实验顺序与停止条件

### E1：预注册 semantic-planning confirmation

- 使用 3.3 的新冻结 240 对 base/fault，不复用当前 held-out 成员。
- 运行五方法公平比较，将 `semantic_delivery_v2` 和 `hard_constraint_safety` 预先冻结为主要指标。
- 报告逐场景结果、配对差值和 scenario-cluster interval，不做方法筛选或新增 judge。

**停止条件：** 若 full KG 相对任一主要基线的 semantic primary 区间下界不大于 0，则停止整体或语义 superiority 主张，转为报告无增益或场景限定增益。

### E2：三模块 held-out 消融

- 在同一批新案例上运行三个 `without_*` 条件，每个完全相同输入 3 次。
- 使用 ontology、capability、contract 各自的机制指标，不以 aggregate oracle 代替。
- 同步纳入 implicit veto 和 evidence/delivery 场景，检验 contract 模块为何在旧消融中没有收益。

**停止条件：** 某模块的配对区间跨 0 或方向不稳定时，结论保持“必要性未确认”；不继续细分节点追求正结果。

### E3：Hard-veto、恢复和正确终态实验

- 构造至少 120 个预注册 failure opportunities，覆盖 veto、permission、timeout/retry、semantic mismatch、quality failure 和 evidence gap。
- 分别统计应拒绝、可恢复、应降级、应部分交付和无合法动作时的正确率。
- 验证 KG 授权的确定性 validator/recovery 是否能把语义计划转化为安全终态，同时记录非法恢复和错误接受。

**停止条件：** hard-veto 正确率和错误接受率未达到预注册阈值时，不进入真实 E2E，不用重试或 Prompt 调整掩盖机制缺口。

### E4：选择性真实 GIS E2E

- 只选择 E1/E3 中方法间存在预注册差异、且具备 source-closed 输入的案例。
- 覆盖 acquisition、算法执行、质量写回、delivery writeback 和 artifact hash；至少包含多个 AOI 和两类故障终态。
- 分开报告规划正确、工具执行、产品质量和最终契约状态，不把任一阶段成功替代全链路结论。

**停止条件：** 若 planning 差异未转化为正确终态或产品指标差异，则结论限定在 planning 层，不再外推到 E2E。

### E5：融合产品质量与独立复现

- 完成最佳单源、简单 union、确定性融合和实际交付产品的公平质量对照。
- 完成独立 worktree 复跑、篡改检测和核心表格到原始证据的回链。

**停止条件：** 没有独立真值或任务特定质量增益时，只报告多源贡献和已记录质量字段，不使用“整体更优质”。

近期分析顺序固定为 `E1 -> E2 -> E3 -> E4 -> E5`。E1 和 E2 的案例、指标及停止条件必须在任何新 Provider 调用前联合冻结，并可在同一批次执行；箭头表示结论分析顺序，不表示看到 E1 结果后再设计 E2。E1-E3 是回答 KG+LLM 是否有效以及哪些 KG 模块必要的核心实验；E4-E5 只在前置机制通过后执行。旧 P0-P7、template governance、method selection 和独立 judge 不再作为近期实验交付物。

## 6. 表述升级路径

| 当前可写表述 | 完成对应实验后预计可加强为 |
| --- | --- |
| KG v1 在限定任务域中提供七层、版本化表示 | 七层 KG 在预注册 CQ、专家评价和分散知识对照下提供更完整、一致且可追溯的契约知识表达 |
| KG 单点扰动会改变限定规划并 fail closed | 多类单变量知识变化在多任务和双后端上产生可预测的规划、验证、源解析、质量和恢复变化 |
| Held-out primary 未确认 full KG 整体优于规则；post-hoc semantic delivery 显示局部优势 | 新预注册 semantic confirmation 若复现且配对区间下界大于 0，可表述为限定复杂处境中的语义规划增量 |
| Capability grounding 的 adversarial 消融下降 35.8 pp，ontology 信号较小，contract 未见独立收益 | 三模块 held-out 消融完成后，分别报告每类 KG 知识在哪些机制指标上必要或不必要 |
| 系统保存产品契约、gap 和交付状态 | 产品契约独立决定图层选择、质量验收、交付等级、gap 和 supersession，并提高契约状态判定正确性 |
| C04 单 AOI 观察到 progressive delivery/supersession | 多 AOI、预注册时序和故障条件下，渐进交付与恢复产生正确、可比较的产品终态 |
| 融合结果包含多源要素和任务特定质量报告 | 在指定产品类型和 AOI 上，融合产品相对最佳单源/union 在明确几何、属性或拓扑指标上获得可测改善 |
| 实验包可冻结、重跑和审计 | 每项核心论文结论均可由独立执行者依据 manifest、哈希、原始响应和 verifier 重复与核验 |

表述升级必须绑定实际完成的 protocol、manifest、evidence root、分支、commit、KG release、产品契约版本、人工评价状态和真实运行结果。设计文档、测试通过数或平台冻结均不能单独触发表述升级。
