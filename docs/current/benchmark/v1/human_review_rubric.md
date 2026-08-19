# FusionAgent Benchmark Human Review Rubric V1

> 状态：frozen_design_asset
> Rubric ID：`fusionagent.benchmark-human-review-rubric.v1`
> Evaluation Contract：`fusionagent.benchmark-evaluation-contract.v1`
> 冻结日期：2026-08-19

## 1. 目的

人工评价只处理自动 gate 无法可靠判断的语义问题，包括允许多解的合同满足、source trade-off、失败历史保持、交付状态解释和证据充分性。人工评价不重复 strict schema、ID grounding 或确定性 veto 检查。

## 2. 评价角色

| 角色 | 职责 | 禁止事项 |
| --- | --- | --- |
| Reviewer A | 独立评价全部 required items | 查看 Reviewer B 决策或 condition key |
| Reviewer B | 独立评价全部 required items | 查看 Reviewer A 决策或自动得分 |
| Adjudicator | 只处理分歧和 `unscorable` | 修改 template、oracle 或历史输出 |
| Protocol owner | 生成盲包、检查完整性、保存 key | 代替 reviewer 填写判断 |

Reviewer A/B 应在方法和结果生成之外完成评价。无法取得独立 reviewer 时，正式 claim 保持 `pending_human_review`。

## 3. Blind Packet

每个 review item 只包含：

- 随机 `blind_item_id`；
- planner-visible request 与 observable facts；
- 对该 review item 必需的合同摘录；
- 候选 plan；
- item-specific question；
- 允许选择 `pass`、`fail`、`unscorable`；
- 自由文本 evidence note。

必须移除：

- method condition；
- run ID、replicate、seed 和 evidence root；
- 自动 gate 结果和自动分数；
- 历史组间均值；
- expected decision、gold explanation 和其他 reviewer 决策。

## 4. 通用判定

### `pass`

候选 plan 在可见事实内满足该 item 的全部要求；如果存在多种合法计划，当前计划是其中之一，且没有依赖未观察事实。

### `fail`

候选 plan 明确违反 item 要求、合同或可见事实；reviewer 必须引用 plan 字段与输入证据。

### `unscorable`

输入缺少判定必需事实、packet 损坏、问题含糊或合同自身冲突。`unscorable` 不等于 pass，并触发 adjudication 或协议阻塞。

## 5. Review Item 类型

### `HR-CONTRACT-SEMANTICS`

问题：候选 decision、gap 和 delivery state 是否与产品合同及已知资源状态一致？

- Pass：不把缺源或失败任务静默声明为 final；合法 partial/degraded/gap 被正确表达。
- Fail：绕过 required contract、把 pending 写成 final、或遗漏必须声明的 gap。

### `HR-SOURCE-TRADEOFF`

问题：候选 source 选择和 trade-off 是否只使用可见、合法且语义兼容的 source？

- Pass：说明可见限制；不创造 source 属性或 availability。
- Fail：使用 missing/illegal source、把 semantic mismatch 当兼容、或伪造外部失败原因。

### `HR-TASK-LOCALITY`

问题：多任务计划是否保持各自合同、source state 和 delivery state？

- Pass：一个任务的 source/contract 变化不污染其他任务；跨任务 precedence 有依据。
- Fail：第一任务上下文被复用于其他任务，或组合后丢失/新增任务。

### `HR-CAUSAL-RESPONSE`

问题：counterfactual pair 的语义变化是否与唯一因果变量一致？

- Pass：应变部分发生正确变化，其余 canonical semantics 保持。
- Fail：方向错误、完全不响应、或出现额外未声明变化。

### `HR-INVARIANT-STABILITY`

问题：不变性 set 是否保持相同 canonical plan semantics？

- Pass：允许 rationale 措辞变化，但 task/source/precedence/gap/delivery state 等价。
- Fail：nuisance variable 导致实质决策变化。

### `HR-RECOVERY-HISTORY`

问题：recovery plan 是否忠实保留已观察失败和交付历史？

- Pass：不重用已 veto 路径，不预写未发生失败，状态转移合法。
- Fail：遗忘质量失败、伪造根因、非法恢复源或错误 final 状态。

### `HR-EVIDENCE-SUFFICIENCY`

问题：E2E 结果的 evidence 是否足以支持声明的执行、质量和交付状态？

- Pass：输入、计划、执行、质量、交付、lineage 和 hash 均可追溯。
- Fail：仅有 HTTP/terminal success、缺质量报告、缺 artifact hash 或状态与产物冲突。

## 6. 允许多解

人工评价不要求与单一 gold plan 字节相同。若 oracle 标记 `allows_multiple_valid_plans=true`，reviewer 应判断：

1. 所有 required tasks 和 veto 是否满足；
2. source、precedence 和 state 是否在允许集合内；
3. 差异是否影响产品合同；
4. 是否依赖不可见事实。

仅 rationale 风格、合法 task 内部次序或等价 source 组合差异不能单独判 fail。

## 7. 双评与裁决

1. A/B reviewer 独立完成所有 item 后锁定 decision 文件。
2. 协议脚本只比较 decision，不向 reviewer 展示 condition。
3. A/B 一致则成为 provisional final decision。
4. A/B 分歧、任一 `unscorable` 或 evidence note 缺失时进入 adjudication。
5. Adjudicator 查看两份 evidence note 和原盲包，输出 final decision 与理由。
6. 未裁决 item 保持 `pending`，不能被按多数、自动分或默认值补齐。
7. blind key 只在所有 final decisions 锁定后解封。

## 8. Development 校准

正式 confirmation 前，reviewer 只能在 development packet 上校准：

- 至少覆盖每种 review item 类型；
- 记录分歧类型，不根据某方法输赢修改 rubric；
- rubric 语义变化必须提升版本并重新校准；
- calibration 决策不得进入 confirmation 指标。

本设计冻结不执行校准，也不生成 review packet。

## 9. LLM Judge 边界

LLM judge 仅可用于 development triage、发现疑似不一致或帮助抽样人工复核。其输出：

- 不进入 formal gold；
- 不替代 Reviewer A/B；
- 不决定 case exclusion；
- 不升级任何 claim；
- 必须与模型、prompt、输入和费用一并记录。

本阶段 judge 调用数固定为 0。

## 10. 人工评价完成条件

- required item 覆盖率 100%；
- Reviewer A/B 独立决策完整；
- 所有分歧与 `unscorable` 已裁决；
- condition key 在 final decision 前未解封；
- final decision、evidence note 和 adjudication 可追溯；
- 缺失决策数为 0。

未满足任一条件时，相关主张状态保持 `pending_human_review`。
