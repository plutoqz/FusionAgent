# 不支持研究核心或提示预期机制可能无效的证据

> 状态：A1 当前证据归纳
> 更新日期：2026-09-05
> 研究口径依据：`D:\code\FusionAgent\docs\thesis\research_direction_guide_2026-07-09.md`、`D:\code\FusionAgent\docs\current\research-charter.md`
> 证据状态依据：本分支 `research-claim-evidence-ledger.md` 与 `research-experiment-ledger.md`

本文集中登记三类材料：实验结果未显示预期增益、实验设计无法识别目标效应、结果直接提示原机制可能无效。所有条目按研究核心链条定位，不以平台测试、功能数量或后续正向结果覆盖负结果。

## 1. 数据产品契约的增量价值尚未得到支持

### 1.1 P3-G 中完整方法与无产品契约结果相同

**实验：** C02/C04/C06，同一 manifest 和固定环境下比较完整方法、无产品契约、无质量门、无降级恢复和固定优先级，各运行一次。

**数据：**

| 变体 | 计划有效率 | 首次质量门通过率 | 最终交付成功率 | 恢复成功率 | 关键图层按时交付率 | gap 正确率 | 证据完整率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 完整方法 | 1.0 | 0.0 | 0.3333 | 0.5 | 0.0 | 0.3333 | 0.3333 |
| 无产品契约 | 1.0 | 0.0 | 0.3333 | 0.5 | 0.0 | 0.3333 | 0.3333 |

**结论影响：**

- 该结果不支持“产品契约提高了计划有效性、最终交付、恢复、gap 正确性或证据完整性”。
- 两组完全相同提示：在 C02/C04/C06 及当前实现中，产品契约消融没有形成足以改变可观测行为的信息差异。
- 当前不能把产品契约层从“已建模、已记录”升级为“已证明具有增量效果”。

**证据：**

- `docs/current/evidence/p3-governance/2026-08-01-freeze-c-p3-governance.md`
- `docs/current/evidence/p3-governance/2026-08-01-freeze-c-p3-governance-grounding-report-v2.json`

### 1.2 P4-G 没有再次设置无产品契约对照

**实验：** Caracas、Abidjan、越南北部沿海走廊的 C02/C04，只比较完整方法与固定优先级。

**数据：**

- 完整方法与固定优先级的计划有效率、最终交付成功率、gap 正确率和证据完整率均为 `7/7`。
- 两组唯一明显差异集中在关键图层按时交付率：`6/7` 对 `3/7`。

**结论影响：**

- 该实验只能提示任务优先级对及时性的影响，不能识别产品契约层本身的贡献。
- 当前多 AOI 结果不能补足 P3-G 中“完整方法与无产品契约相同”的证据缺口。
- 研究方向指引提出的核心中介变量“产品契约满足度”尚未被完整方法相对无契约方法的多 AOI 对照直接验证。

**证据：**

- `docs/current/evidence/p4-external-validity/2026-08-01-freeze-c-p4-external-validity.json`

## 2. KG 表示规模不能证明知识完整性或创新性

**实验/数据：** KG v1 已冻结 7 层、71 个模式类、42 类关系、241 个静态对象、8 项约束和 8 个 competency questions。

**结论影响：**

- 类、关系、节点和约束数量只能证明知识结构已经实现，不能证明其完整覆盖灾害应急数据产品知识。
- 当前没有已完成的专家覆盖评价、CQ 检索正确率、跨层一致性评价或与分散 schema/策略表的同口径对照结果。
- 当前数据不能支持“七层结构优于能力目录型 KG”“完整表达所有相关灾害产品语义”或“本体规模本身构成创新”。

**证据：**

- `kg/ontology/v1.0.0/`
- `docs/current/research-claim-evidence-ledger.md` 中 `CL-I1-REP`

## 3. 原六组真实 LLM 结果未显示 raw KG 稳定增益

**实验：** C01-C06，LLM-only、LLM + capability KG、LLM + full contract KG 三类真实 LLM 条件，18 个 cell，各 5 次，共 90 runs。

**数据：**

- `LLM-only = 0.908333`
- `LLM + full contract KG = 0.908333`
- `LLM + capability KG = 0.883333`
- 总 token `1,171,179`
- 自动检查失败 `72`
- 对应 180 个盲评 item 尚无人工裁决结果

**结论影响：**

- raw Full KG 与 LLM-only 自动均值完全相同，不支持“完整 KG 注入已经提高规划质量”。
- Capability KG 均值低于 LLM-only，提示知识上下文的选择、组织或注入可能产生负效应。
- 当前结果不支持 KG/full method 优于 rules-only、KG-only 或 LLM-only。
- 这组数据提示“向 LLM 提供更多 KG 内容”本身不是有效方法，知识接口和任务相关投影可能才是关键变量。

**证据：**

- `D:\code\fusionagent-evidence\p3-planning-repeated\2026-08-15-deepseek-v4-flash-repeated-combined-v1`
- `docs/current/research-claim-evidence-ledger.md` 中 `CL-RQ3-MAIN`、`CL-I2-RAW-KG-GAIN`

## 4. H07-H09 未确认方案 B 优于 raw Full KG

**实验：** H07-H09 独立 planning confirmation；B、LLM-only、Full KG 三条件，27 次调用、63 个 rubric item，双人盲评和裁决。

**数据：**

- B：`21/21`
- Full KG：`21/21`
- LLM-only：`17/21`

**结论影响：**

- B 与 Full KG 的人工通过数相同，不支持 B superiority，也不足以证明统计非劣。
- task-conditioned projection 在 H01-H06 修复了特定接口故障，但 H01-H06 已参与方法开发，不能作为独立效果确认。
- B 不能升级为第七组主方法，也不能从 planning rubric 外推为 E2E 数据产品质量、及时性或恢复能力改善。
- 该结果提示 B 可能是接口消融或等效表示方案，而不是已证实优于 raw Full KG 的新主方法。

**证据：**

- `D:\code\fusionagent-evidence\p3-planning-method-b\2026-08-17-method-b-independent-confirmation-v1`
- `D:\code\fusionagent-evidence\p3-planning-method-b\2026-08-18-method-b-independent-confirmation-manual-adjudication-v1`
- `docs/current/research-protocol-method-confirmation-v1.json`

## 5. 新 held-out primary 未确认 KG+LLM 整体优于规则基线

### 5.1 严格综合指标没有确认 superiority

**实验：** `heldout_confirmatory_v1`；12 个新高难场景、5 类产品、每场景 2 个实例，共 120 对 base/fault。三种 LLM 方法对完全相同输入各运行 3 次，`rules_only` 和 `fixed_workflow` 各运行 1 次。统计单元为案例级多数结果。

**数据：**

| 方法 | Base majority | Fault majority（primary） |
| --- | ---: | ---: |
| `llm_only` | 45/120（37.5%） | 1/120（0.8%） |
| `llm_capability_kg` | 120/120（100.0%） | 4/120（3.3%） |
| `llm_full_contract_kg` | 119/120（99.2%） | 4/120（3.3%） |
| `rules_only` | 120/120（100.0%） | 0/120（0.0%） |
| `fixed_workflow` | 120/120（100.0%） | 0/120（0.0%） |

- Full KG 相对 `rules_only` 的 fault primary 差值为 3.3 个百分点，scenario-cluster bootstrap 95% CI `[0.0%, 10.0%]`，McNemar exact `p=0.125`。
- Full KG 与 capability KG 的 fault primary 完全相同；配对差值为 0，95% CI `[-2.5%, 2.5%]`。
- Full KG 的 4 个 primary passes 全部来自 quality degradation；其余 11 类高难场景均为 0。

**结论影响：**

- 置信区间包含 0，不能确认 full KG 在预声明严格综合指标上优于规则或固定流程。
- Full KG 与 capability KG 的 primary 结果相同，不支持完整 ontology + contract 上下文在该指标上产生额外增益。
- 规则与 fixed 的 base 100% 只说明 clean workflow 正好处于固定映射的覆盖区，不能解释为复杂故障能力；但也不能因为它们简单而从公平基线中排除。
- Post-hoc semantic delivery 的正向结果必须留在诊断层，不能事后替换 primary endpoint。

### 5.2 Hard-veto、schema 可靠性和真实 E2E 仍失败或未验证

**数据：**

- 所有方法在 held-out implicit hard-veto 场景均为 `0/10`；adversarial non-explicit veto 也均为 `0/5`。
- Held-out 的 2160 次真实 Provider 调用中有 26 次 schema-invalid 输出：`llm_only` 3/720、capability KG 10/720、full KG 13/720。它们均作为方法失败保留。
- Full KG 的 schema-valid execution 为 98.2%，低于 capability KG 的 98.6% 和 LLM-only 的 99.6%。
- 两轮实验都没有执行实际 acquisition、融合算法、quality writeback 和 delivery writeback；Actual E2E denominator 为 0。

**结论影响：**

- 当前不能声称 KG+LLM 已解决隐式 veto、复杂故障安全拒绝或 schema 可靠性问题。
- Full KG 更长的上下文没有自动带来更可靠的结构化输出。
- 受控 planning/replay 指标不能证明真实 GIS 数据产品交付、质量提升或运行韧性。

### 5.3 当前模块消融不支持“所有 KG 部分均必要”

**数据：**

- Adversarial 中移除 contract / quality / delivery policy 后，aggregate oracle 从 60.8% 上升到 62.5%，fault-only 从 21.7% 上升到 25.0%；未观察到该模块的独立正向贡献。
- 移除 ontology / identity / crosswalk 只使 aggregate 下降 3.3 个百分点，且配对成员中有 6 个退化、2 个改善，效应较小且不稳定。
- Capability grounding 的 35.8 个百分点 aggregate drop 是最强正向消融信号，但来自单轮 adversarial 集；held-out 未运行三类 `without_*` 条件。

**结论影响：**

- 不能声称 contract / quality / delivery policy 的独立必要性已经得到支持，也不能据单轮结果反向断言该模块有害。
- Ontology 的局部收益尚不足以支持普遍必要性。
- Capability grounding 可表述为“当前证据最强的必要模块”，不能写成已经通过独立 held-out 因果确认。

**证据：**

- `D:\code\FusionAgent\runs\experiments\adversarial-baseline-v1-qwen37-20260904-live-w4`
- `D:\code\FusionAgent\runs\experiments\heldout-confirmatory-v1-qwen37-20260905-live-w4`
- `D:\code\FusionAgent\experiments\heldout_confirmatory_v1\cases.json`

## 6. 旧研究 runner 不能证明当前 KG v1 驱动正式规划

**审计数据：**

- `research/product-contract` 的 `build_planning_context()` 由案例字段和 Python 常量拼装 KG-like context，没有直接调用当前 KG v1 的 `KGRepository` 或 release API。
- 分支维护 `PLANNING_ALGORITHM_BY_LAYER`、`RUNTIME_ALGORITHM_BY_LAYER` 和 `TASK_KIND_BY_LAYER`，存在 planner selected、runtime resolved 和实际 executed 混淆。
- 研究版质量服务重新定义 Python 质量政策，可能形成第二知识真源。
- 旧 runner 只实现五组，没有当前 A0 要求的独立 `rules-only`。

**结论影响：**

- 旧 runner 的测试和运行结果不能证明 `fusionagent-kg-v1.0.0` 已直接驱动正式六组规划实验。
- 不能把 KG-like JSON context 视为当前冻结 KG 的实际消费证据。
- 旧五组、旧 150-run 协议和结构化决策输出不能直接升级为 I2/RQ3 的正式效果结果。

**证据：**

- `docs/current/research-branch-kg-v1-merge-audit.md`
- `origin/research/product-contract`

## 7. 当前恢复证据不支持总体韧性增益

### 7.1 P3-G 仅为一次性小切片

**数据：**

- 完整方法恢复成功率为 `0.5`，无降级恢复为 `0.0`。
- 完整方法与固定优先级的恢复成功率均为 `0.5`。
- 每个变体在同一三个案例上只运行一次。

**结论影响：**

- 数据说明移除恢复机制会改变本轮行为，但不能支持总体恢复率、跨故障类型韧性或生产可靠性改善。
- 当前没有把 failure opportunity、恢复资格、恢复动作和恢复代价扩展为足够的独立统计单元。

### 7.2 C06 正式 recovery 没有发生

**实验数据：**

- C06 预冻结双源候选通过 raw 和 adapted quality gate。
- 旧协议预期的自然质量失败没有出现。
- S5 正式 recovery 实验未运行，状态为 `not_run_precondition_unsatisfied`。

**结论影响：**

- C06 不支持“质量门失败后恢复成功”这一预期叙事。
- 当前不能声称 C06 已验证 recovery，也不能把未发生的失败补写成方法成功。
- C04 的 progressive delivery/supersession 是另一种交付机制，不能替代 C06 的故障恢复对照。

**证据：**

- `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c06-failure-screening-r1`
- `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-s6-selective-e2e-audit-v1`

## 8. C02/C04/C06 真实 E2E 没有形成完整方法效果闭环

**数据：**

- C02：water polygon 完成；waterways 因未计划 source expansion 和 semantic contract invalid 在算法前 fail closed；road 未运行。
- C04：两阶段道路 artifact 和 supersession 成功；最终 delivery 仍为 degraded，且仅一个 AOI。
- C06：只完成 failure screening，正式 recovery 未运行。
- S6 审计明确写入 `claim_eligible_for_method_superiority=false`。

**结论影响：**

- 当前选择性 E2E 不支持完整方法 superiority。
- C02 不能写成多图层 E2E 成功，C04 不能写成完全满足最终契约，C06 不能写成恢复能力成功。
- 当前三例不能支持跨 AOI、跨灾种或跨源条件的完整执行有效性。

**证据：**

- `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-s6-selective-e2e-audit-v1\audit.json`
- `docs/current/research-experiment-ledger.md` 中 `E-RQ4-C02`、`E-RQ4-C04`、`E-RQ4-C06`

## 9. 当前融合质量数据不能证明产品整体优于单源

**实验与数据：**

- Freeze C 保存要素数、源贡献、无效几何率、重复率、字段非空率、AOI 一致性和部分 feature alignment。
- C04 道路从 16,279 个 OSM provisional 要素增加到 23,760 个双源阶段要素。
- P4-G 外部参考仅对 HydroLAKES/HydroRIVERS 前 30 个要素进行代表点或线中点 100 m 匹配。

**结论影响：**

- 要素数增加只直接支持“数量更丰富”，不能自动证明新增要素正确、无重复、拓扑连通性更好或属性质量更高。
- 当前没有以最佳单源、简单 union、现有融合算法基线和人工/独立真值共同构成的产品质量对照。
- 外部匹配率是源一致性代理，不是人工真值精度、召回、完整几何偏差、属性正确率或拓扑质量。
- 当前数据不能支撑“融合产品相对原始单源整体更丰富、更优质”这一研究方向指引中的完整表述，只能支撑部分要素增量和任务特定指标已被记录。

**证据：**

- `docs/current/evidence/p2-stability/2026-08-01-freeze-c-p2-stability.json`
- `docs/current/evidence/p4-external-validity/2026-08-01-freeze-c-p4-external-validity.json`
- `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c04-road-e2e-r4`

## 10. 多 AOI 结果不能证明广泛外部有效性

**实验数据：**

- P4-G 覆盖 Caracas、Abidjan 和越南北部沿海走廊，但每个 AOI/变体只运行一次。
- C06 只有 Caracas 具备独立第二道路源；其余两个 AOI 不可运行。
- 环境使用 mock LLM、memory KG、eager Celery、单 child worker 和 local-only 配置。
- 后续 E5 source-closed inventory 发现相关选择性 E2E 中只有 Caracas 满足候选条件，没有选出新增正式 AOI。

**结论影响：**

- `6/7` 对 `3/7` 和 Cohen h `0.9389505` 只能作为探索性及时性差异，不能作为统计显著性结论。
- 当前不能从三 AOI 治理切片外推到不同国家、灾种、数据提供商和数据缺失条件。
- 当前不能把 mock LLM 或本地 eager 运行解释为真实 LLM、分布式调度或生产能力。

**证据：**

- `docs/current/evidence/p4-external-validity/2026-08-01-freeze-c-p4-external-validity.md`
- `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-15-multi-aoi-candidate-inventory-v1`

## 11. I4 和平台实现不能替代 I1-I3 效果证据

**数据：**

- Freeze C 通过独立审计和三次语义稳定重跑。
- Benchmark Platform Core V1 为 `64 passed`、P7 `10/10`、BP7 `11/11`，七项人工复核批准。
- 平台冻结时 Provider、judge、benchmark instances 和 formal result roots 均为 `0`。

**结论影响：**

- 审计、哈希和稳定性证明证据可复核，不证明七层 KG 更完整、LLM+KG 规划更优或恢复机制更有效。
- 平台 core 只证明离线组件合同和治理闭环，不能作为正式 benchmark 结果、方法效果或生产能力证据。
- I4 是可信性支撑，不得反向替代 I1-I3 的比较实验。

**证据：**

- `docs/current/evidence/2026-08-01-freeze-c-p1-audit.json`
- `docs/current/evidence/p2-stability/2026-08-01-freeze-c-p2-stability.json`
- `docs/current/benchmark/platform/v1/implementation/`

## 12. 当前不能使用的总体表述

以下表述均不受当前实验数据支持：

- 产品契约已经显著提高产品契约满足度、交付成功率或 gap 正确率。
- 七层 KG 已完整覆盖灾害应急数据产品知识，或其规模本身证明创新性。
- raw Full KG、Capability KG 或完整方法普遍优于 fixed workflow、rules-only、KG-only 或 LLM-only。
- Held-out primary 已经证明 full KG 整体显著优于规则或 fixed；或者 post-hoc semantic delivery 可以替代预声明 primary 结论。
- Ontology、capability 和 contract 三类 KG 模块都已通过独立 held-out 消融证明必要。
- 方案 B 已经统计非劣、普遍优于 Full KG，或已改善真实 E2E 产品质量。
- 当前完整方法已经提高总体恢复率、故障韧性或生产可靠性。
- 当前融合产品已经在几何、属性和拓扑三个方面整体优于最佳单源或简单多源基线。
- 当前结果已经证明跨 AOI、跨灾种、跨数据源的广泛外部有效性。
- 当前 benchmark 平台的离线合同测试等同于正式方法效果、真实实验能力或生产能力。
