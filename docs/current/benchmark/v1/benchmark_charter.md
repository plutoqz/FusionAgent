# FusionAgent Parameterized Benchmark Charter V1

> 状态：frozen_design_asset
> Asset ID：`fusionagent.benchmark-charter.v1`
> Design ID：`fusionagent.benchmark-design.v1`
> 冻结日期：2026-08-19
> 服务范围：O2-O4、RQ2-RQ4、I2-I4
> A0 权威：[`research-charter.md`](../../research-charter.md)

## 1. Benchmark 目的

本 benchmark 用于评价契约化知识图谱及其受约束规划接口是否能够：

1. 对合同、数据源和失败状态的受控变化作出正确因果响应；
2. 对措辞、输入顺序和无关噪声保持语义稳定；
3. 在多任务请求中维持 task-local 合同、source state 和 delivery state；
4. 在 recovery replan 中保留已发生失败、合法候选源和交付历史；
5. 将失败定位到 KG、projection、planning、validator、execution/quality/evidence 中的明确层级。

目标不是提高一个不透明综合平均分，而是形成可证伪、可分层、可归因的研究单元。

## 2. 固定研究身份

### 2.1 原六组主实验

以下六组继续承担 RQ3 主实验，身份和信息边界不得由本 benchmark 改写：

| Group ID | 方法角色 | 允许信息 |
| --- | --- | --- |
| `fixed_workflow` | 固定工作流基线 | task interface、冻结 workflow |
| `rules_only` | 独立规则基线 | request、observable facts、`rules.general.v1` |
| `kg_only` | 确定性 KG 查询与选择 | request、observable facts、KG query result |
| `llm_only` | 无 KG 的真实 LLM | request、observable facts、output schema |
| `llm_capability_kg` | capability KG 增强的真实 LLM | 共享 LLM 输入加 capability projection |
| `llm_full_contract_kg` | full contract KG 增强的真实 LLM | 共享 LLM 输入加 capability 与 contract projection |

三个 LLM 组在未来正式实验中必须使用相同模型 revision、system prompt、output schema、temperature、预算、timeout 和失败规则；只有知识上下文不同。

### 2.2 方案 B 的固定位置

`task_conditioned_contract_aware_kg` 只属于 I2/RQ3 interface ablation：

```text
no KG
  vs raw full-contract KG
  vs task-conditioned contract projection
```

方案 B 不是第七种主实验范式，不替代原六组，也不把 H01-H09 与新 confirmation 混池。

## 3. 候选主张合同

### `CL-BENCH-CAUSAL`

- 映射：O2/O3、RQ2/RQ3、I2。
- 主张：方法对一个已声明的 contract/source/failure 因果变量变化产生符合 oracle 的关系响应。
- 比较对象：同一 template family 的 counterfactual pair。
- 实验单元：pair；单次 run 不是独立主张单元。
- 支持条件：pair 中除一个 `causal_variable` 外，所有 invariants 相同；输出关系满足 pair oracle；无 veto。
- 证伪条件：输出不变但 oracle 要求改变、改变方向错误、引用不存在的 source/capability，或 pair 发生未声明变量漂移。
- 允许表述：在冻结模板族和所测变量上观察到正确因果响应。
- 禁止表述：KG 对所有合同或数据状态都具有普遍因果推理能力。

### `CL-BENCH-INVARIANT`

- 映射：O3、RQ3、I2。
- 主张：方法对不改变任务语义的措辞、输入顺序和无关噪声保持等价决策。
- 比较对象：同一 template family 的 invariant set。
- 实验单元：set，不把 set 内变体当独立案例。
- 支持条件：canonical plan semantics 等价；允许 rationale 文本变化。
- 证伪条件：task set、合法 source、precedence、gap 或 delivery state 因 nuisance variable 变化而改变。
- 允许表述：在所测不变性扰动下语义稳定。
- 禁止表述：输出字节相同或模型完全确定。

### `CL-BENCH-COMPOSE`

- 映射：O2/O3、RQ2/RQ3、I2。
- 主张：多任务组合保持 task-local contract、source state 和 precedence，不发生跨任务污染。
- 比较对象：单任务组成项与其组合模板。
- 实验单元：composition family。
- 支持条件：组合输出等于各任务合法决策的合同一致组合，并满足跨任务 precedence。
- 证伪条件：第一任务上下文被错误应用到其他任务、source 跨任务误用、合法任务丢失或非法 task 被增加。
- 允许表述：在所测组合族中未观察到定义的跨任务污染。
- 禁止表述：任意规模任务组合都能正确规划。

### `CL-BENCH-RECOVERY`

- 映射：O4、RQ4、I3。
- 主张：recovery replan 只依据已经观察到的失败事实，保留失败历史、合法 source 和 delivery state。
- 比较对象：初始状态、失败后状态和可选恢复状态构成的 temporal trace。
- 实验单元：trace。
- 支持条件：replan 不预写未发生的外部失败；不重用已 veto 的路径；状态转移符合产品合同。
- 证伪条件：遗忘质量门失败、伪造失败根因、选择非法 source、把 degraded/provisional 错写为 final。
- 允许表述：在冻结时序模板上 recovery state 保持一致。
- 禁止表述：恢复率提高，除非后续真实 E2E 对照支持。

### `CL-BENCH-DIAG`

- 映射：O2/O3/O4、RQ2/RQ3/RQ4、I2/I3/I4。
- 主张：benchmark 失败可以映射到预先定义的主要能力层，而不是只返回综合失败。
- 比较对象：capability x mechanism cells。
- 实验单元：cell；失败实例可作为 cell 内证据但不扩大外推。
- 支持条件：每个失败通过 gate/evidence 唯一定位一个 primary layer，secondary risks 单列。
- 证伪条件：多个层级不可区分、依赖人工猜测、或使用 fallback 后成功覆盖原始失败。
- 允许表述：失败在本合同下可被分层诊断。
- 禁止表述：诊断标签已经证明真实根因，除非后续实现或执行证据验证。

## 4. 数据集角色与隔离

| Partition | 用途 | 是否允许影响方法 | 是否支持确认性主张 |
| --- | --- | --- | --- |
| `development` | schema、生成器、evaluator 和 rubric 校准 | 允许 | 否 |
| `independent_confirmation` | 冻结方法和 evaluator 后的 planning 验证 | 禁止 | 完成人工评价后可支持受限 planning 主张 |
| `selective_e2e` | 预注册 source-closed 机制的真实执行 | 禁止用结果改变选择规则 | 只支持 execution/quality/delivery 层主张 |

三个 partition 必须使用不同 seed namespace、实例 ID namespace 和 evidence root。development/post-repair 结果不得进入 confirmation 聚合。

## 5. 已观察材料排除清单

以下 ID 和其语义同构副本禁止进入新 independent confirmation：

```text
C01 C02 C03 C04 C05 C06
H01 H02 H03 H04 H05 H06 H07 H08 H09
```

语义同构不仅指名称相同，还包括只替换灾害名、任务名、AOI 或 source 名，但保持相同状态交互、因果变量、oracle 和 veto 的模板。

历史材料允许用于发现机制族、识别风险、development 回归和解释 gate；禁止用于新 confirmation、根据已知胜负设定 oracle、事后改变 stopping rule 或与新结果混池。

## 6. 复杂度层级

| Level | 定义 | 主要目的 | 是否允许 E2E |
| --- | --- | --- | --- |
| `L0` | 单任务、无冲突、source 闭合 | 校验基本合同与 grounding | 否 |
| `L1` | 单任务、单因果变量变化 | 因果响应和 veto | 否 |
| `L2` | 多任务组合与跨任务 precedence | composition 与污染诊断 | 否 |
| `L3` | 已观察失败后的时序 replan | recovery state | 候选 |
| `L4` | source-closed、truth/quality 可评价的真实执行 | execution、quality、delivery evidence | 是 |

复杂度不是难度分数；不同 level 不直接合并为一个平均值。

## 7. 信息边界

Planner-visible 只包含 request、observable runtime facts、对应方法允许的规则或 KG projection、公共 output schema。Evaluator-only 包含 oracle、veto、pair/set/trace relation、expected evidence requirements 和 blind key。

禁止泄漏 expected decision、expected consequence、gold task order、allowed delivery states、自动得分、condition label、replicate、历史组间结果和人工判定提示。

## 8. 成功、负结果与停止语义

1. 本 benchmark 不要求方法获胜；tie、局部增益、退化或无增益均是合法结果。
2. 正确拒绝、gap、pending、partial、provisional、degraded 和 supersession 可以是正确结果。
3. 生成失败、schema 失败、grounding 失败和人工分歧必须保留。
4. confirmation 一旦解封，不得因负结果修改 template、oracle、rubric 或 evaluator。
5. planning 结果不能支持 execution、quality 或 external-validity 主张。

## 9. 成本与 Provider 边界

本设计冻结阶段的 Provider、judge 和正式结果调用数均必须为 0。未来 Provider/model/revision、预算和重复次数由独立正式运行协议冻结，不进入 template schema，也不能成为生成器的隐藏变量。

## 10. Charter 验收记录

| Check | 状态 |
| --- | --- |
| 五个候选主张均映射现有 O/RQ/I | passed |
| 六组主实验身份保持不变 | passed |
| 方案 B 固定为接口消融 | passed |
| 三类 partition 角色互斥 | passed |
| C01-C06、H01-H09 禁止复用 | passed |
| 每项主张含支持和证伪条件 | passed |
| 未预设结果方向 | passed |
| Provider/judge/formal result 调用为 0 | passed |

阶段验收点：`G1-CHARTER-FROZEN`。
