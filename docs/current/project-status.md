# FusionAgent 当前项目状态

> 状态：A0 当前权威状态
> 基准日期：2026-08-13
> 当前活动工作区：`D:\code\FusionAgent`，分支 `main`

## 1. 总体判断

FusionAgent 已跨过“系统能否运行”的阶段，进入“以冻结知识基线约束运行，并把系统能力转化为可发表证据”的阶段。P0-R 与 P0-K1–K5 已按顺序验收，KG v1 已完成运行消费闸门和最终冻结发布。治理比较、稳定性和最小多 AOI 切片已有受限证据，但真实 LLM 规划对照及其选择性端到端验证仍未形成共享正式证据。

- **工程实现**：产品契约、任务规划、质量门、渐进式交付、降级恢复和证据关联已经形成闭环。
- **知识图谱实现**：七层 KG v1 的 schema、实体和政策机器源已冻结；模式含 71 个类，静态包含 241 个稳定标识知识对象和 1 条转换边。35 个高风险知识片段已完成唯一真源迁移或执行机制归类，K4 已证明 KG-only 行为扰动、fail-closed、源重新材料化和真实双后端一致性。
- **研究证据**：P1、P2、P3-G 治理消融和 P4-G 最小外部有效性切片已完成；P3-P 真实规划对照和 P4-P 规划外部有效性未完成。C02/C04/C06 及三 AOI 结果仍是受限证据，不构成广泛有效性证明。
- **真实 LLM 状态**：已使用 DeepSeek 官方 API 的 `deepseek-v4-flash` 完成 18-call planning pilot。18 次均为 HTTP 200 且响应模型一致，16 次通过 strict JSON/schema，2 次 C06 知识增强调用因 8192 reasoning tokens 用尽而以 `finish_reason=length` 失败；总消耗 222,980 tokens。该 pilot 未使用 mock、fallback、salvage 或重试，但只验证调用链、隔离记录和失败留痕，不是组间优越性证据。
- **研究分支资产**：`research/product-contract` 已实现五类规划模式、结构化决策、gold 隔离、重复实验审计和最小端到端运行时，定向套件当前为 `32 passed`。归并审计已确认其 KG 上下文未直接消费当前 KG v1；这些是待适配和选择性提升的开发资产，不是正式实验结论。
- **论文准备度**：期刊实验与证据准备度约 45%–60%；硕士论文工程核心约 65%–75%，包含写作和补充实验后的整体完成度约 45%–60%。这些比例仅用于项目规划。

## 2. 已完成的工程闭环

1. 产品契约约束下的任务规划与执行。
2. 水体面、水系线、道路、建筑物和兴趣点的语义区分及优先级表达。
3. provisional 产物、渐进式交付和最终 supersession。
4. 质量门失败、任务延期和降级数据源恢复。
5. artifact、quality report、gap declaration 与运行证据的关联。
6. `ProductContract` 从模型、seed、manifest、内存/Neo4j 仓库、检索上下文、规划结果到 KG API 的端到端接入。

当前 KG v1 机器基线包含：

| 项目 | 数量 |
| --- | ---: |
| 本体层 | 7 |
| 模式类 | 71 |
| 核心属性 | 19 |
| 关系类型 | 42 |
| 完整性约束 | 8 |
| Competency questions | 8 |
| 稳定标识静态知识对象 | 241 |
| 类型转换边 | 1 |
| 产品契约实体 | 6 |

当前权威机器源见 `kg/ontology/v1.0.0/`；`docs/research/ontology/2026-07-27/` 是此前导出快照，不再承担 KG v1 的机器真源角色。模式状态区分 `implemented`、`runtime-derived` 和 `reserved`，因此模式类数量不得被解释为静态实例数量或方法创新强度。

## 3. Freeze C 证据基线

Freeze C 的独立复现基线保存在：

```text
worktree: D:\code\FusionAgent-freeze-c-93ebdc5
commit:   93ebdc51c8732ec466067de760a65f30f3f1155c
evidence: D:\code\freeze-c-evidence\exp-c02-c04-c06-20260725-final-93ebdc5
```

已冻结案例：

| 案例 | 已观察机制 | 可支持的受限结论 |
| --- | --- | --- |
| C02 | 水体/水系/道路优先，建筑物延期，保留 provisional/degraded 证据 | 契约可以显式治理优先级、延期和降级状态 |
| C04 | 先交付 provisional，后完成最终融合并记录 supersession | 渐进式交付和替代关系可以被审计 |
| C06 | 道路全量融合质量失败，随后 OSM-only 降级恢复成功 | 质量门可以暴露失败并触发受控恢复 |

Freeze C 已记录真实外部矢量数据、真实融合算法、9 项外部输入、32 个源文件及 sidecar、638 个输出文件和干净工作区状态。此前全量回归记录为 `320 passed`。这些数字描述冻结时点，不自动代表当前活动分支状态，也不等于方法优于基线。

## 4. 两种知识基线必须区分

| 范围 | 状态 | 内容 | 允许的表述 |
| --- | --- | --- | --- |
| Freeze C 历史可执行图谱 | 已冻结历史证据 | 15 类、27 种关系、232 个静态实体；包含 6 个产品契约 | “Freeze C 时点的产品契约已成为可遍历图谱实体” |
| 契约化七层 KG v1 | P0-K1–K5 已验收并冻结 | 7 层、71 个模式类、42 类关系、241 个稳定标识静态知识对象；高风险决策知识已统一到机器源并通过定向运行验收 | “KG v1 已完成定向运行强绑定与真实双后端验收”；不能扩大为真实 LLM 或生产部署结论 |

其中 `DurableLearningRecord`、质量门结果、运行实例、证据链、缺口声明和 supersession 等被明确建模为运行派生类，不要求进入静态实体包。`ConflictAxis` 和 `PatternCandidate` 当前为 `reserved`，不得据此宣称已有对应运行能力。

## 5. 当前不能直接宣称

- 不能仅凭 C02/C04/C06 宣称系统在不同地区、灾种和数据质量条件下广泛有效。
- 不能用 320 个测试通过替代与基线的效果比较。
- 不能把 mock LLM 或 memory KG 的结果表述为真实 LLM 智能规划已验证。
- 不能把单次 C06 恢复案例表述为韧性得到统计性证明。
- 不能把 P4 的 OSM/HydroSheds 源匹配率表述为人工真值精度、召回率或完整位置误差评价。
- 不能把 P4 的三 AOI C02/C04 重复外推为所有地区；C06 的独立道路参考源目前只有 Caracas。
- 不能把可运行研究原型表述为生产级多租户平台。
- 不能把七层模式类的存在表述为全部概念已有静态实例或全部运行消费者已完成绑定。
- 不能把单次 Neo4j 5.26 harness parity 表述为生产部署、长期稳定性或大规模性能证明。

## 6. 当前工作区状态

| 工作区 | 分支/状态 | 处理原则 |
| --- | --- | --- |
| `D:\code\FusionAgent` | `main@2bcafaa`，当前活动工作区 | 保留用户与并行任务改动，不回滚、不清理 |
| `D:\code\FusionAgent-freeze-c-93ebdc5` | detached `93ebdc5`，标签 `freeze-c-20260725`，干净 | 只读保留，承担 Freeze C 复现基线 |
| `D:\code\FusionAgent-head-baseline` | detached `db256d5`，含未跟踪的 `baseline-junit.xml` | 保留基线产物，不在共享任务中清理 |
| `D:\code\FusionAgent-worktrees\research` | `research/product-contract`，当前干净 | 用于实验协议和论文研究；提升前独立审查 |

原 `app/autonomous-fusion` 分支与 `main` 没有独有提交，worktree 也保持干净，已于 2026-07-28 删除。应用开发改为需要时从 `main` 创建短期任务分支。

详细规则见[仓库与 Worktree](repository-worktrees.md)。

## 7. 已验收证据与待补缺口

### P0-K3 验收记录

P0-R/K1/K2 文档与结构验收已经完成。P0-K3 采用“语义退出条件 + 基线归因”，没有继续使用“全量必须全绿”的影子闸门：

- `git diff --check` 通过。
- 研究目标 O1–O4、RQ1–RQ4、创新点 I1–I4、责任边界和非主张已进入唯一 A0 研究章程。
- K1/K3 台账登记 47 个片段、七条决策链；35 个高风险片段全部完成唯一真源迁移或执行机制闭合，无未分类的已知高风险决策常量。
- 三份权威 JSON 可解析且声明相同 `release_id`/版本；schema 为 7 层、71 类、42 类关系、19 项属性、8 项约束和 8 个 competency questions。
- 独立 HEAD 基线全量结果为 `1197 passed, 17 failed, 2 skipped`；K3 初次全量结果为 `1249 passed, 34 failed, 2 skipped`。共有失败 10 项，K3 新增 24 项。
- 24 项新增失败中，23 项 A/B/C 类已修复并通过定向回归；剩余 Neo4j bootstrap 生成物同步归 P0-K5，不阻塞 K3。
- K3 最终专属模块套件覆盖 intent、mission、task kind、KG fail-closed、source contract、quality、fault/recovery、release identity 和 verifier，共 `205 passed`；此前残余硬编码整改相关组合套件为 `100 passed`。
- 阶段收口全量执行结果为 `1272 passed, 12 failed, 2 skipped`。其中 10 项是 HEAD 基线共有失败，1 项是 P0-K5 的 Neo4j bootstrap 派生物同步，1 项是本轮空覆盖状态泛化导致的 K3 回归；该回归已改为 KG source policy 并通过 2 项定向复测。没有剩余 K3 A/B/C 类失败。
- `release.json` 中三份受保护文件的 SHA-256 与当前字节一致；独立 verifier 对候选语义哈希 `sha256:50067b9368914c47580707650789c04c78b2e856ccb3ef4d120a31f36c0ad71e` 完成 11/11 项检查。

上述结果验收 P0-R/K1/K2/K3；K4/K5 的后续独立验收记录如下。Freeze C 的 `320 passed` 仍不能作为当前分支结果。

### P0-K4/K5 验收记录

2026-07-29 完成后续顺序验收：

- KG-only 修改 `wp.flood.building.safe.success_rate` 后，运行计划由 `wp.flood.building.default`/`algo.fusion.building.v1` 切换为 safe pattern/algorithm；计划上下文记录 `knowledge_identity`、`selected_pattern_id`、排序依据和实际选择理由。
- 删除运行期必需知识、缺失输出 schema、超出冻结灾害词汇、strict Neo4j 不可用等路径均明确失败，不静默回退隐藏默认规则。
- source fallback 测试确认上游重新材料化，fallback artifact 内容与 SHA-256 均不同于失败源残留，不允许仅替换 source ID。
- 使用 Java 21 与 Neo4j 5.26 官方 harness 启动真实 Bolt 实例，导入冻结 bootstrap；release identity 与 live manifest 一致，建筑、道路、水体、POI 四类上下文的 pattern/step、算法和数据源顺序与 pinned memory 一致。实机验收同时修复了数组属性 manifest 序列化和跨类型数据源顺序不稳定问题。
- K4/K5 最终定向组合为 `47 passed`；未运行全量测试。
- K5 重封后语义哈希仍为 `sha256:50067b9368914c47580707650789c04c78b2e856ccb3ef4d120a31f36c0ad71e`。包内独立报告为 11/11；clean 校验通过，`schema.json`、`entities.json`、`policies.json` 各自单字节篡改均返回非零；Neo4j bootstrap 已与冻结身份同步。

### 研究阶段状态

当前研究阶段从“冻结统一 KG v1”转入“把已有能力变成可独立审计、可重复、可比较的证据”：

1. P0-R 研究章程与主张口径冻结。
2. 已完成 P0-K1–K5；KG v1 已冻结。
3. P1 已完成：独立审计通过；Freeze C 的 638 个包内声明文件、9 组/32 个外部输入、5 个 prepared-input、运行 input/output、`all_cases_passed` 和冻结 worktree 均已核验。机器报告与中文摘要见 `docs/current/evidence/2026-08-01-freeze-c-p1-audit.json` 和 `docs/current/evidence/2026-08-01-freeze-c-p1-audit.md`。
4. P2 已完成：同一干净 commit 三次重跑通过；语义级稳定，artifact 字节差异均已分类，未解释差异为 0。报告见 `docs/current/evidence/p2-stability/2026-08-01-freeze-c-p2-stability.json` 和 `docs/current/evidence/p2-stability/2026-08-01-freeze-c-p2-stability.md`。
5. P3-G 治理方向最小消融已完成：完整方法、无产品契约、无质量门、无降级恢复和固定优先级均在同一 C02/C04/C06 manifest 与固定环境下各运行一次。P3-P 规划方向尚未形成当前 KG v1 上的正式证据。
6. P4-G 最小外部有效性切片已完成：Caracas、Abidjan 和越南北部沿海走廊三 AOI 已纳入；C02/C04 在两种变体各重复一次，C06 在 Caracas 重复一次。该切片使用 mock LLM，只评价治理与交付链路，不评价真实 LLM 规划增量。P4-P 尚未完成。

本轮 P3-G 只支持受限的治理行为差异，不支持统计显著性、真实 LLM 增量或广泛有效性结论。完整方法的计划有效率、最终交付成功率、恢复成功率和证据完整率均为 1.0；无降级恢复的恢复成功率为 0；无质量门的首次质量门通过率为不可用值，质量门绕过率为 1.0；固定优先级改变了 C02 任务顺序，并使关键图层按时交付率由 2/3 降为 1/3。P4-G 中完整方法与固定优先级各包含 7 个可比较案例，完整方法关键图层按时交付率为 6/7，固定优先级为 3/7；该差异为探索性结果，不能作为显著性结论。原始证据统一保存在 `D:\code\freeze-c-evidence\` 下的正式变体根目录；中断的早期运行目录仅作诊断保留。

`research/product-contract` 资产、当前 KG v1 消费路径、真实 LLM 证据路径和选择性端到端边界的联合审计已经完成，报告见[研究分支成果与当前 KG v1 归并审计](research-branch-kg-v1-merge-audit.md)。结论是禁止整分支合并；保留结构化决策、gold 隔离、失败留痕和审计链等设计资产；KG 上下文、运行映射和质量政策边界必须适配或重写。

五项研究语义决策已经完成，P3-P/P4-P 已进入实现阶段。当前已形成版本化案例 manifest、canonical context、六组输入投影和确定性基线隔离测试，并完成 18-call 真实 LLM pilot。pilot 原始证据位于 `D:\code\fusionagent-evidence\p3-planning-pilot\2026-08-13-deepseek-official-v4-flash-r1`，执行源码为 `3231f04108a0dda2d675ad32b1ce19033ffc3bc2`。

pilot 审计曾确认旧 v2 输入的 18/18 LLM 调用暴露 `expected_consequence`，部分案例还暴露 `unsupported_terms`、`quality_policy_id` 或 `semantic_guard`。当前 manifest 已升为 `1.1.0-draft`，将这些字段移入独立 `gold_rubric`，planner observation schema 和 `prepare_pilot` 均 fail closed。新的离线 preflight 位于 `docs/current/evidence/p3-planning-pilot/2026-08-13-preflight-v3-no-gold-leak/`：18 个输入的泄漏命中为 0，9 个 canonical input hash 均唯一，18/18 hash 相对 v2 变化，因此不得与旧 pilot 直接混合。

当前已为 C01-C06 增加声明式 planning rubric，并实现通用 evaluator v1。自动项只评价 strict schema 前置有效性、decision、grounding、任务集合、gap、顺序、precedence 和 delivery state；provenance、semantic guard、supersession 等语义项保持 `manual_review=pending`，不通过关键词匹配自动判定。聚焦验证为 `26 passed`。旧 18-call pilot 已生成 `pilot_scoring_replay.json`，其中强制记录 `diagnostic_only=true`、`input_leakage=true`、`claim_eligible=false`；其评分只能验证 evaluator 回放链路，不能作为模型质量或组间差异证据。

当前仍为 `formal_ready=false`：v3 无泄漏输入已完成 C06 真实压力小 pilot，但暴露 C06 输入与 gold 的决策时点不闭合；rubric/evaluator 协议与 hash 也尚未冻结。`max_tokens=16384` 与至少 600,000-token 的同规模批次预算仍是候选参数，不是正式冻结值。planning-only formal 和选择性端到端均未执行。

2026-08-13 已在提交 `d15ed71` 上执行 C06 的 v3 真实压力小 pilot：三种 LLM knowledge condition 各一次，共 3 次 DeepSeek 官方 `deepseek-v4-flash` 调用。3/3 为 HTTP 200、响应模型一致、`finish_reason=stop`、strict JSON/schema 成功，总消耗 32,072 tokens；输入泄漏为 0，未使用 retry、repair、salvage 或 fallback。该结果只说明 `max_tokens=16384` 在这 3 次 C06 调用中未复现旧有截断，不足以冻结参数或证明模型质量。

该小 pilot 同时发现 formal blocker：C06 v3 的 planner observations 只包含初始双源和 recovery source，没有“首次质量门失败”这一运行事实；gold rubric 却要求直接输出 provisional/degraded/gap 恢复状态。`llm_only` 自动检查全部通过，而 capability-KG 与 full-contract-KG 均规划双源 `planned`，decision/state 两项未通过。当前证据支持“案例输入与评分目标不闭合”，不支持通过修改 prompt、放宽评分或补跑来消除失败。正式实验保持暂停，须先重新冻结 C06 的决策时点、可见观察和 gold 语义。

C06 语义现已冻结为两阶段：P3 planning-only 评价“首次质量门拒绝后”的 `recovery_replan`；P4 end-to-end 从初始双源规划开始，实际执行到质量门失败后再构造同一 replan 输入。manifest `1.2.0-draft` 的 `observed_failure` 只记录已发生的质量门拒绝、可恢复性和当时双源均可用，不提前声称 external source failure；source external/system 分类互斥且只能引用 initial sources。v4 离线 preflight 位于 `docs/current/evidence/p3-planning-pilot/2026-08-13-preflight-v4-c06-recovery-replan/`，18 个输入泄漏为 0，相对 v3 仅 C06 的 6 个输入 hash 改变。正式实验仍需先通过 v4 C06 真实小 pilot。

具体优先级、退出条件和论文映射见[论文主张与优先级](claims-and-priorities.md)。
