# 三种 LLM-KG 协作方式的方法选择协议

> 状态：A1 当前方法选择设计（未冻结）
> 更新日期：2026-09-01
> 研究口径：[`research-charter.md`](research-charter.md)
> 适用范围：RQ3 / I2 的规划比较，以及后续 RQ4 选择性 E2E

## 1. 决策结论

不在实验前宣称某一种 LLM-KG 协作方式最优。正式规划实验同时运行以下三种 LLM 条件，并在全部预注册运行完成后按本协议选择研究采用方式：

| 条件 ID | 协作方式 | 可见知识 |
| --- | --- | --- |
| `llm_only` | LLM-only | 请求、可观测运行事实、公共输出 schema |
| `llm_capability_kg` | LLM + capability KG | `llm_only` 加数据源、算法和任务能力投影 |
| `llm_full_contract_kg` | LLM + selected full-contract KG interface | `llm_only` 加任务条件化的产品契约、能力、质量、恢复和证据投影 |

这里的 `selected full-contract KG interface` 表示在方法冻结前已经完成接口工程筛选并固定的 full-contract 投影实现，不表示在确认结果出来后临时挑选对自己有利的接口。接口候选的筛选只能使用 development 数据；确认集上的三种条件必须使用同一冻结接口、同一模型、prompt、schema、温度、预算和失败规则。

六组 RQ3 主实验仍保留：`fixed_workflow`、`rules_only`、`kg_only` 和以上三种 LLM 条件。方法选择只在三种 LLM 条件之间进行，固定工作流、规则和 KG-only 用于解释增量价值，不能被事后排除。

## 2. 为什么采用并行比较

并行比较可以同时回答两个不同问题：

1. 三种协作方式在同一案例、同一预算和同一评价合同下的相对表现是什么；
2. 知识条件对计划有效性、契约满足度、稳定性和代价的增量来自哪里。

它不会把“预先假定 full-contract KG 必然最好”写进研究设计，也不会因某个 pilot 结果而删去表现较弱的条件。负结果、调用失败、schema 失败、grounding 失败和人工不可判定项均保留。

需要区分两种结论：

- **选择结论**：在本协议、模型、案例集和评价指标下，哪一种方式被选为后续研究采用方式；
- **确认性优越结论**：某方式相对其他方式在独立、未用于选择的 confirmation 集上具有可重复优势。

同一批数据既用于选出冠军又用于声称独立优越，会产生选择偏差。因此，第一批结果最多支持“预注册条件下的探索性选择”；要写成确认性优越，应保留独立 confirmation 集，或在选择集和确认集之间进行嵌套划分。

## 3. 两阶段实验结构

### 3.1 阶段 A：development 与接口冻结

目的：验证三种条件能运行、接口边界可解释、案例和 evaluator 闭合，并从 full-contract 接口候选中选定一个工程版本。

允许使用：development partition、历史案例的机制回归和零调用 preflight。

不允许：使用 confirmation 结果调参、修改 gold/rubric/evaluator、删除失败运行或把 development 分数写成正式效果结论。

接口候选可包括 raw full KG、task-conditioned typed projection 和 capped query-on-demand。选择依据在运行前登记，至少包含：

1. schema、grounding、KG release identity 和 fail-closed 闭合；
2. 输入字段边界和 token/latency 上限；
3. 在 development 中的可解释性、合同满足度和稳定性；
4. 实现复杂度与证据可追溯性。

接口冻结后记录 `method_commit`、KG release、projection allowlist、prompt、output schema、预算、repair policy 和 hash。接口选择不是三种主条件的效果冠军选择，不能根据 confirmation 结果更换。

### 3.2 阶段 B：held-out confirmation 与方法选择

在阶段 A 的身份和参数全部冻结后，使用新的 template family 和独立 seed 运行六组主实验。三种 LLM 条件必须逐案例共享输入、随机化顺序和调用预算。

每个运行同时保存：

- 原始请求、可见 context 和原始响应；
- pre-fallback 结构有效性、grounding 和 validator 结果；
- 产品契约维度向量；
- 人工盲评 packet、分歧和裁决；
- latency、token、cost、失败类别和 evidence hash。

结果发布前不得查看 condition label 来修改案例、oracle、评分或停止规则。方法选择在全部预注册运行、自动评价和人工评价完成后进行。

## 4. 预注册选择规则

选择单位是 `condition`，不是单个案例或单次运行。按以下字典序比较；前一层无法区分时才进入下一层：

1. **安全硬门**：最小化 forbidden action、错误 `final`、未接地引用和未保留失败历史；任一条件未达到预注册硬门时，不得被选为默认研究方法。
2. **主要效果**：最大化产品契约满足度向量，优先比较 critical layer 按时交付、overall contract state correctness、gap/degradation/supersession 正确率，再比较人工盲评通过率。
3. **机制覆盖**：比较 causal response、invariance、composition 和 recovery 四类 benchmark 单元的分层通过率，不用总平均掩盖某一类失败。
4. **效率与复现**：在效果等价时，依次选择较低 token/cost、较低 latency、较少 repair、较高 evidence completeness 的方式。

“等价”必须在运行前冻结 margin 和置信区间规则。若没有唯一胜者，则报告 Pareto 集合和分层结果，不强行制造单一冠军；后续工程采用方式需另行记录为治理决定，不冒充效果优越。

选择规则禁止：

- 看过结果后改变主指标、分母、margin、停止条件或案例排除；
- 只保留表现最好的案例或重复；
- 用 fallback 后的最终计划覆盖 LLM 原始失败；
- 把 LLM judge 单独作为人工真值；
- 将选择集结果与独立 confirmation 结果混池。

## 5. 研究采用方式与论文表述

### 5.1 选择后的采用

选定方式只作为后续 RQ4 选择性 E2E、真实故障恢复和论文主方法实现的默认配置。其身份必须绑定：

```text
method_id
method_commit
KG release / semantic hash
projection hash
prompt / schema hash
selection protocol hash
selection evidence root
```

任何后续代码、KG 语义或信息边界变化都必须创建新的 method version，不能继续沿用旧选择结果。

### 5.2 允许的表述强度

| 证据层 | 允许表述 |
| --- | --- |
| 仅完成 development 选择 | “在 development 条件下选择了 X 作为后续实验采用接口/方式。” |
| 选择集完成，未有独立 confirmation | “X 在本协议选择集上取得最高预注册效用；属于探索性选择。” |
| 独立 confirmation 复现 | “在限定案例、模型和协议下，X 相对比较条件表现出受限、可重复的优势。” |
| 选择性 E2E 完成 | 在上述边界外，再增加 source-closed AOI、执行、质量和交付状态的限定表述 |

无论最终哪一条件胜出，均不得写成“KG 在所有灾害场景下必然有效”或“full-contract KG 普遍优于 LLM-only”。

## 6. 与冻结材料的关系

- Benchmark V1 的六组身份、能力单元、评价合同和 selection governance 保持冻结；本文件只定义下一版本的**方法选择**，不回写 V1 tag。
- 原 C01-C06、H01-H09 及其语义同构副本继续排除在新 confirmation 之外。
- 既有 `E-RQ3-LLM-90`、`E-B-H07-H09` 等结果保留为历史/当前描述性证据，不用于事后修改本协议的选择规则。
- 本文件本身不授权 template authoring、Provider、judge、confirmation 或 E2E；启动仍需独立协议和显式授权。

## 7. 一周内的可交付验收点（2026-09-01 至 2026-09-07）

1. 完成三种 LLM 条件的 canonical context、投影 allowlist 和 method identity 草案。
2. 完成 10-15 个代表性模板的 oracle、覆盖标签和难度分层设计，不生成正式 confirmation 实例。
3. 完成 selection metric、等价 margin、人工盲评 packet 和 evidence manifest 的零调用 preflight。
4. 完成 development/selection/confirmation 的目录、seed 和排除规则审计。
5. 形成一份可审查的 method-selection protocol freeze candidate；通过独立复核后再授权实现与真实调用。

本周目标是把“可以公平比较并可选择”变成可冻结的研究资产，不把未执行的实验写成已取得效果。
