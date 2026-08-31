# 完全支撑研究创新点与核心主张的后续设计

> 状态：A1 后续研究设计草案
> 更新日期：2026-08-31
> 前置冻结：`benchmark-design-freeze-v1`、`benchmark-platform-protocol-v1`、`benchmark-platform-core-v1`

本文把后续工作组织成“设计优化、实验补充、评价闭环、表述升级”四个层次。它是后续协议输入，不自动授权 template authoring、Provider、judge、正式实验或 E2E。

## 1. 设计优化

### 1.1 建立唯一的 case-to-KG crosswalk

为每个案例的灾种、任务、产品契约、数据源、算法和质量政策建立显式映射，字段至少包含：

- `case_id`、`task_kind`、`contract_id`、`source_id`、`algorithm_id`、`quality_policy_id`；
- `kg_release_id`、`semantic_hash`、`mapping_status`、`fixture_only_reason`；
- 对不存在于 KG v1 的对象使用显式 `unsupported` 或新版本候选，不使用 Python alias、默认值或静默替换。

**预期加强表述：** 从“KG 结构已建立”推进到“案例语义可追溯地绑定到冻结 KG release”。

### 1.2 从同一 canonical context 生成六组投影

先由 `KGRepository`、`KnowledgePolicyRegistry` 和 case observation 生成唯一 canonical context，再按 allowlist 投影：

1. fixed workflow；
2. rules-only；
3. KG-only；
4. LLM-only；
5. LLM + capability KG；
6. LLM + full contract KG。

每组记录可见字段清单、投影 hash、信息来源和禁止字段。`rules-only` 必须拥有独立实现边界，不能只是 fixed workflow 改名。

**预期加强表述：** 从“不同配置产生不同输出”推进到“六组比较具有可审计的信息边界和公平输入”。

### 1.3 拆分 selected、resolved、executed 和 fallback

所有规划和运行记录分别保存：

- planner 选择的稳定 ID；
- runtime 解析后的稳定 ID；
- 实际执行的算法/源/策略；
- fallback reason、触发阶段和新 artifact hash。

执行器只能解析 KG/runtime contract 明确声明的能力，不维护第二份算法目录或质量政策表。

**预期加强表述：** 从“计划被执行”推进到“规划选择到实际执行的因果链可以逐字段核对”。

### 1.4 固定真实 LLM 实验合同

在正式运行前冻结：Provider、model revision、system prompt、output schema、temperature、max tokens、预算、seed、transport retries、semantic repairs、fallback policy、原始响应保留策略和停止条件。所有 LLM 组使用同一模型、prompt、schema、温度和重试规则，只有知识投影不同。

**预期加强表述：** 从“存在真实调用事实”推进到“真实 LLM 条件可复核且组间差异归因于知识条件”。

## 2. 补充实验设计

### 2.1 RQ1：知识表达与覆盖实验

**实验单元：** KG v1 competency-question 集、专家标注集、分散知识 baseline 和 case-to-KG crosswalk。

**实施：**

- 为 8 个 competency questions 建立可执行查询、期望实体/关系和审核记录。
- 引入领域专家或独立审阅者，对情景、需求、能力、质量、恢复和证据层进行覆盖与一致性评分。
- 与分散 schema/策略表进行同口径对照，报告实体、关系、约束、来源和版本追溯结果。

**预计增强：** 将 I1/RQ1 从“统一模型已实现”加强为“在指定问题集和专家评价下具有可核对覆盖与一致性”。

### 2.2 RQ2：因果扰动与 fail-closed 实验

**实验单元：** 成对反事实模板实例，每次只改变一个 contract/source/quality/failure 知识变量。

**实施：**

- 逐项修改 KG 约束，验证 planner、validator、source resolver 和 recovery selector 的行为变化。
- 删除必需知识、注入未知 ID、改变 source availability、改变质量阈值，验证明确失败和失败原因。
- 在 memory 与 Neo4j 后端复跑同一 manifest，比较 selected/resolved/executed 和 evidence hash。

**预计增强：** 将 I2/RQ2 从“限定案例行为扰动”加强为“单变量知识变化产生可预测、可解释和可复核的系统行为变化”。

### 2.3 RQ3：六组真实 LLM planning formal

**实验单元：** 新参数化 held-out benchmark，不复用 C01-C06、H01-H06、H07-H09 作为独立确认实例。

**设计：**

- 六组完整对照，至少覆盖常规、歧义、冲突、数据缺失、质量失败和渐进交付机制。
- 成对反事实实例、语义不变扰动、输入顺序扰动和多任务组合污染实例。
- 每个 cell 固定重复次数、schedule seed、预算和 evidence root。

**指标：** pre-fallback planning validity、contract satisfaction、forbidden-action rate、grounding、gap precision/recall/F1、plan stability、latency、token、cost，以及人工盲评通过率。

**人工闭环：** 180-item 旧六组材料先完成双人盲评、分歧裁决和统一分析；新 benchmark 使用独立 rubric、盲 key 和第三评审员规则。

**预计增强：** 将 RQ3 从“90-run 自动描述和接口观察”推进到“六组公平对照、重复、人工评价和可统计分析”。

### 2.4 RQ4：治理、恢复与选择性 E2E

**实验单元：** source-closed AOI、故障注入模板、质量门失败、源不可用、部分交付和 supersession 时序。

**实施：**

- 对完整方法、无产品契约、无质量门、无降级恢复和固定优先级进行同一故障序列对照。
- 预注册 C06 recovery 触发条件；自然失败不足时使用协议内的故障注入，不修改 gold 或停止条件。
- 选择能区分 planning 差异的代表案例连接真实外部数据，验证规划变化是否改变材料化、融合、质量门和最终契约状态。
- 至少覆盖多个 source-closed AOI，并为每个 recovery case 绑定独立参考源、输入 hash 和 failure opportunity。

**指标：** 首次质量门通过率、错误接受率、最终契约状态正确率、恢复率、恢复代价、关键图层按时交付率、gap 正确率、evidence completeness 和质量损失。

**预计增强：** 将 I3/RQ4 从“单 AOI 过程观察”推进到“故障条件、对照、恢复机会和交付状态均可比较的治理证据”。

### 2.5 I4：复现与证据方法实验

**实验单元：** 多次干净重跑、独立 verifier、篡改 fixture、跨后端 parity 和 evidence manifest。

**实施：**

- 每个正式 cell 保存源码、KG、prompt、schema、输入、输出、失败响应、日志、预算和产物哈希。
- 对时间戳、绝对路径和运行 ID 进行规范化，区分 byte stability、semantic stability 和允许波动。
- 对输入、KG、prompt、输出和 manifest 分别做单字节篡改测试，要求 verifier 非零退出。
- 由独立复核者从全新 worktree 执行审计命令并核对结果。

**预计增强：** 将 I4 从“证据链已建立”加强为“研究结果可以由独立执行者重复、定位和复核”。

## 3. 评价与统计补充

1. 预先冻结 primary metric、secondary metrics、分母定义、not-assessable 规则和停止条件。
2. 把 case、condition、repetition 和 failure opportunity 明确区分，禁止把重复行、自动检查项和人工 rubric item 混为同一统计单元。
3. 对主要比较报告 effect size、置信区间和逐案例结果；在样本不足时只报告描述性结果。
4. 对人工评价报告双评一致性、分歧项和裁决路径；LLM judge 只能作为开发诊断，不替代人工真值。
5. 保留负结果、失败运行、未完成尾部、协议偏差和无答案案例，不使用 fallback 或事后规则修补提升指标。

## 4. 研究表述升级路径

| 当前表述层级 | 完成后可加强为 |
| --- | --- |
| KG v1 在限定任务域提供统一、版本化、可校验表示 | KG v1 在预注册 CQ、专家评价和分散知识对照下提供可核对的契约化知识表达 |
| KG 扰动和缺失知识会改变限定决策并 fail closed | 单变量知识扰动在多个任务和后端上产生可预测的规划、验证和恢复变化 |
| B 修复了特定接口失败 | B 在新 held-out planning benchmark 中相对 Full KG/LLM-only 的预注册比较结果得到人工和统计证据支持 |
| C04 观察到 progressive delivery/supersession | 在预注册故障序列和多个 source-closed AOI 中，契约化恢复保持可比较的交付和证据状态 |
| 证据链可冻结、重跑和独立审计 | 正式实验结果可由独立执行者依据 manifest、哈希和 verifier 重复与回溯 |

任何表述升级都必须绑定新的 protocol、manifest、evidence root、分支、commit、KG release、评价状态和实际运行结果；不得用设计冻结或平台合同测试直接替代方法效果证据。
