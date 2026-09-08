# FusionAgent 主张-证据账本

> 状态：A1 当前权威主张状态
> 更新日期：2026-09-07
> A0 边界：`research-charter.md`
> 当前执行入口：`research-governance-index.md`

## 当前主张补充（2026-09-08）

目标是证明公平基线下 KG+LLM 的截止前达标交付增益，目标不等于已成立结论。9 月 7 日 r2 四个融合组均为 23,760 条道路、端点 proxy 637.028929，未发布；LLM-only 被适配器停止，不能据此认定方法胜负。

20 次开发筛查、状态条件子图与反馈恢复、同事实文本对照均为待执行设计，不提升下表证据等级。正式主张须报告主比较、完整/部分达标交付、质量、错误发布和成本；拒绝不算融合完成。同事实文本对照未完成前不声称图结构优势。下表历史 pending 状态不作为本轮新增前置流程的理由。

## 1. 状态定义

| 状态 | 含义 |
| --- | --- |
| `implemented` | 代码、KG 或协议机制存在，但尚无效果证据 |
| `observed_bounded` | 在冻结案例中观察到，不能外推 |
| `supported_bounded` | 有对照、重复和适当评价支持限定结论 |
| `pending_human_review` | 自动/运行证据完成，但正式人工评价未闭环 |
| `not_supported` | 当前结果未支持预期方向，必须报告负结果 |
| `historical_only` | 仅用于追溯，不能进入当前比较性结论 |

## 2. 当前主张矩阵

原六组与 B/C 系列的记录按历史账本继承，本轮没有重跑或重新完成其人工盲评。2026-09-04/05 简化实验单独登记，不覆盖旧 pending 状态。

| Claim ID | 对应 O/RQ/I | 当前状态 | 当前允许表述 | 当前禁止表述 | 主要缺口 |
| --- | --- | --- | --- | --- | --- |
| `CL-I1-REP` | O1/RQ1/I1 | `observed_bounded` | KG v1 在限定任务域中提供七层、版本化、可校验的契约知识表示 | 完整覆盖所有灾害产品知识；本体规模本身证明创新 | `SRC-08`、专家/CQ 评价、与分散知识基线对照 |
| `CL-I2-BIND` | O2/RQ2/I2 | `supported_bounded` | KG 扰动、缺失知识 fail-closed、类型化消费和双后端 parity 证明 KG 实际参与限定决策 | 所有运行语义均已完全消除隐藏规则；广泛任务有效 | 扩展能力矩阵和系统性行为扰动案例 |
| `CL-RQ3-MAIN` | O3/RQ3/I2 | `pending_human_review` | 90-run 自动结果可作为描述性 planning 结果报告 | KG/full method 优于 rules-only、KG-only 或 LLM-only | 原六组 180-item 双人盲评、裁决和统一六组分析 |
| `CL-I2-RAW-KG-GAIN` | O3/RQ3/I2 | `not_supported` | raw Full KG 与 LLM-only 自动均值持平，Capability KG 更低；结果提示接口问题 | 原始 KG 注入已产生稳定增益 | 更大、分层、机制可诊断的正式案例集和人工评价 |
| `CL-I2-PROJECTION` | O2/O3/RQ2/RQ3/I2 | `observed_bounded` | task-conditioned projection 修复了 H01-H06 的特定接口失败；H07-H09 中 B 与 raw Full KG 的人工通过数均为 `21/21` | B 非劣于或普遍优于 Full KG；B 是第七组主方法；B 已改善 E2E 产品质量 | 新参数化 held-out 案例、正式人工评价协议、选择性 E2E |
| `CL-I3-RECOVERY` | O4/RQ4/I3 | `not_supported` | C04 支持单 AOI progressive delivery/supersession；C02 支持 fail-closed；C06 保留合法负结果 | 完整方法提高恢复率或交付成功率；C06 已验证 recovery | 合法自然失败、对照执行、多个 source-closed AOI |
| `CL-I4-EVIDENCE` | O4/RQ4/I4 | `supported_bounded` | 冻结输入、模型 revision、原始响应、失败、哈希和独立审计形成可复核证据链 | 证据方法本身证明 I1-I3 效果；当前证据具有广泛外部有效性 | 统一论文 evidence index 和新 benchmark 协议复用 |
| `CL-RQ3-SIMPLE-PRIMARY` | O3/RQ3/I2 | `not_supported` | 2026-09-05 严格 fault primary：Full KG `4/120`，capability `4/120`，rules/fixed `0/120`；未确认整体优势 | 用 post-hoc 替换 primary，或将旧六组与新五方法混池 | 独立确认、评价语义、实现身份与公平性核查 |
| `CL-RQ3-SEMANTIC` | O3/RQ3/I2 | `observed_bounded` | 旧 post-hoc：Full KG `38/120`，LLM-only/capability 各 `13/120`，rules/fixed 各 `3/120` | 已确认 semantic_delivery_v2；已具备可执行或安全交付能力 | 新指标需包含必要 grounding；旧指标未检验该项 |
| `CL-I2-MODULES` | O2/O3/RQ2/RQ3/I2 | `observed_bounded` | Adversarial capability 消融下降 `35.8 pp`；ontology 较小；contract aggregate 未降反升 `1.7 pp` | 七层均必要；已证明 contract 有害；图结构或 LLM 不可替代 | 同信息对照、模块重复、contract 反事实与消费审查 |
| `CL-I3-CONTRACT-GAIN` | O4/RQ4/I3 | `not_supported` | P3-G 无契约对照未显示增量，新消融也未支持契约独立收益 | 产品契约已提高满足率 | 同产物不同契约、可计算验收及受控交付对照 |
| `CL-I3-SIMPLE-SAFETY` | O4/RQ4/I3 | `not_supported` | Held-out hard-veto 指标 `0/10`，新简化实验 actual E2E denominator 为 0 | 规划结果代表安全执行或无人值守可靠性 | proposal/validator/执行分层检查、正确拒绝和恢复机会 |
| `CL-RQ4-REAL-CLOSED-LOOP` | O3/O4/RQ3/RQ4/I2/I3 | `implemented` | 已定义真实闭环比较：任务解析、下载、规划、融合、质量审查、重试/降级/发布 | KG+LLM 已经提高截止时间前真实融合交付率 | 真实多方法同执行器比较、受控网络扰动、任务特定质量和独立参照 |
| `CL-I2-COLLABORATION` | O2/O3/RQ2/RQ3/I2 | `implemented` | 已提出全量注入、状态条件子图、执行反馈重规划三种可检验协作机制 | 状态条件子图+有限次反馈重规划已经是最优方案 | 同任务、同资源、同网络轨迹下的机制比较 |
| `CL-I1-I3-KNOWLEDGE-FAMILIES` | O1/O2/O4/RQ1/RQ2/RQ4/I1/I3 | `implemented` | 已定义语义、能力、契约质量、时限恢复、证据经验五类知识消融 | 七层 KG 每一层均已被证明必要 | 保持其余知识不变的逐项消融和触发型案例 |

## 3. 当前关键负结果

1. 原六组 LLM 条件的 90-run 自动均值：`llm_only=0.908333`、`llm_full_contract_kg=0.908333`、`llm_capability_kg=0.883333`。
2. deterministic 描述性均值：`rules_only=0.9375`、`kg_only=0.916667`、`fixed_workflow=0.729167`；确定性重复不视为独立随机样本。
3. H07-H09 最终人工裁决经 blind key 分组后，B 与 Full KG 均为 `21/21`，LLM-only 为 `17/21`；B superiority 未被确认。
4. C06 预冻结候选未出现自然质量门失败，因此正式 recovery 实验未运行。不得制造失败以维持旧案例叙事。

5. 新 held-out Full KG vs rules 严格 primary 差值 `3.3 pp`，scenario-cluster 95% CI `[0, 10.0%]`，描述性 McNemar `p=0.125`；未确认总体 superiority。
6. 旧 post-hoc Full KG 的 decision accepted 为 `40/120`，低于 LLM-only/capability 的 `43/120`；order 为 `120/120`。不能把合成指标上升解释为所有决策维度都提高。
7. 2026-09-06 当前 runner 的顺序投影包含 `V3_MISSION_PRIORITY` 常量，且源码 hash 不同于历史 manifest。由此只能提出归因/复现风险，不能直接宣称旧实验已确认泄漏。

这些负结果不修改 A0。下一步按[下一步工作计划](research-evidence-next-design.md)开展真实闭环比较，必要的指标、知识来源和公平性问题直接在运行中检查，不单独开冻结复核阶段。旧 C06 自然失败未发生的事实不改写。

## 4. 方案 B 的固定位置

方案 B 的方法身份固定为：

```text
I2 / RQ3 interface ablation
raw full-contract KG
  vs task-conditioned contract projection
  vs no KG
```

证据分层固定为：

| 案例 | 角色 | 允许用途 |
| --- | --- | --- |
| C01-C06 B screen | 方法开发 | 诊断和实现反馈，不进入效果比较 |
| H01-H06 | post-held-out repair | 解释特定接口失败及修复机制，不作为独立 confirmation |
| H07-H09 | independent planning confirmation | 描述 B 与 Full KG 人工通过数均为 `21/21`，不解释为统计非劣或外推到 E2E |

历史 evidence 中出现的 “B outperformed” 文句按当时 post-repair 边界保留，但不继承为当前 claim。

## 5. 候选机制问题（非新增平台计划）

下一阶段不是追求更高平均分，而是使以下主张可证伪：

| Candidate Claim ID | 目标主张 | 核心实验单元 |
| --- | --- | --- |
| `CL-BENCH-CAUSAL` | KG 条件能对 contract/source/failure 的单变量变化作出正确因果响应 | 成对反事实模板实例 |
| `CL-BENCH-INVARIANT` | 方法对措辞、输入顺序和无关噪声保持语义稳定 | 语义不变扰动对 |
| `CL-BENCH-COMPOSE` | 多任务合同和 source state 不发生跨任务污染 | 分层多任务模板 |
| `CL-BENCH-RECOVERY` | recovery replan 保留失败历史、合法 source 和 delivery state | 时序状态模板与选择性 E2E |
| `CL-BENCH-DIAG` | 失败能映射到 KG、projection、planning、validator 或 execution 的具体能力短板 | capability-level x mechanism 矩阵 |

这些只是待验证候选主张，当前状态均为 `draft`，由真实闭环 R1-R4 选择性覆盖，不重新启动参数化平台工程。

当前不进行方法冠军选择。五方法、模块消融、同知识 KG-only 和同事实平铺表示分别识别不同增量；缺少对应比较时排除相应主张。I4 是可信性支撑，不提升为替代 I1-I3 的效果创新。

## 6. 主张更新规则

1. 自动 evaluator 得分不单独触发主张升级：须核对预注册语义、对照、独立样本和区间；需语义真值的部分由预声明人工复核支持。LLM judge 不替代真值。
2. development、repair 和 confirmation 结果分开登记，禁止混池平均。
3. 任何主张升级必须列出比较对象、实验单元、人工评价状态和 evidence root。
4. 结果不支持预期方向时更新为 `not_supported`，不修改 metric、case 或停止条件追分。
5. A0 主张变更需要单独决策；本账本只能更新证据状态和允许表述。
