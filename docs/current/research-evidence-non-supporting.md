# 未形成支持或提示可能无效的实验数据

> 状态：A1 当前证据归纳
> 更新日期：2026-08-31
> 适用范围：依据冻结实验、自动结果、人工复核和归并审计整理

本文集中列出不能支撑预期创新点或研究核心、以及已经提示某些预期方向可能无效的实验和数据。所有失败、未完成和负结果均保持原始证据链，不用后续正向结果覆盖。

## 1. 原六组 RQ3 自动结果未显示 raw KG 增益

**实验：** C01-C06，三类真实 LLM 条件，18 cells，各 5 次，共 90 runs。

**数据：**

- `LLM-only = 0.908333`
- `LLM + full contract KG = 0.908333`
- `LLM + capability KG = 0.883333`
- 总 token `1,171,179`；自动检查失败 `72`。

**结论影响：**

- 该结果不支持“原始 Full KG 注入已经稳定提高规划得分”。
- Capability KG 的均值低于 LLM-only，提示知识上下文的组织方式可能带来负效应。
- 该结果不能支持 KG/full method 已优于 rules-only、KG-only 或 LLM-only。

**证据：**

- `D:\code\fusionagent-evidence\p3-planning-repeated\2026-08-15-deepseek-v4-flash-repeated-combined-v1`
- `docs/current/research-claim-evidence-ledger.md`
- `docs/current/research-experiment-ledger.md`

## 2. H07-H09 未确认方案 B superiority

**实验：** 独立 planning confirmation，H07-H09，B、LLM-only、Full KG 三条件，27 calls，盲评和裁决。

**数据：**

- B：`21/21` 人工通过。
- Full KG：`21/21` 人工通过。
- LLM-only：`17/21` 人工通过。

**结论影响：**

- B 与 Full KG 的人工通过数相同，不能支持 B 的非劣或普遍优越。
- B 不能被升级为第七组主方法，也不能直接转化为 E2E 产品质量改善结论。
- H01-H06 的修复结果只能保留为特定接口故障的 post-held-out repair 证据。

**证据：**

- `D:\code\fusionagent-evidence\p3-planning-method-b\2026-08-17-method-b-independent-confirmation-manual-adjudication-v1`
- `docs/current/research-protocol-method-confirmation-v1.json`
- `docs/current/research-claim-evidence-ledger.md`

## 3. P3-G 不能单独证明完整方法的比较性增益

**实验：** C02/C04/C06 同一 manifest 和固定环境下的完整方法、无产品契约、无质量门、无降级恢复、固定优先级五变体，各运行一次。

**数据：**

| 变体 | 计划有效率 | 首次质量门通过率 | 最终交付成功率 | 恢复成功率 | 关键图层按时交付率 | gap 正确率 | 证据完整率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 完整方法 | 1.0 | 0.0 | 0.3333 | 0.5 | 0.0 | 0.3333 | 0.3333 |
| 无产品契约 | 1.0 | 0.0 | 0.3333 | 0.5 | 0.0 | 0.3333 | 0.3333 |
| 无质量门 | 1.0 | 不适用 | 0.6667 | 0.0 | 0.3333 | 0.0 | 0.3333 |
| 无降级恢复 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.3333 |
| 固定优先级 | 1.0 | 0.0 | 0.3333 | 0.5 | 0.0 | 0.3333 | 0.3333 |

**结论影响：**

- 完整方法与无产品契约在本轮主要指标上相同，不能单独证明产品契约带来比较性增益。
- 无质量门的最终交付率高于完整方法，但其首次质量门指标不可用且质量门被绕过，说明只看最终交付会产生错误结论。
- 无降级恢复的结果显示恢复机制对本轮案例行为有影响，但单轮小切片不能支撑普遍恢复率或生产韧性主张。

**证据：**

- `docs/current/evidence/p3-governance/2026-08-01-freeze-c-p3-governance.md`
- `docs/current/evidence/p3-governance/2026-08-01-freeze-c-p3-governance-grounding-report-v2.json`

## 4. P4-G 结果不能单独证明外部有效性或真实 LLM 增益

**实验：** Caracas、Abidjan、越南北部沿海走廊的 C02/C04；完整方法与固定优先级各 7 个可比较案例。

**数据：**

- 完整方法与固定优先级计划有效率均为 `7/7`。
- 最终交付成功率均为 `7/7`。
- 关键图层按时交付率：完整方法 `6/7`，固定优先级 `3/7`，Cohen h `0.93895`。
- C06 只有 Caracas 的独立道路参考源条件。
- 运行使用 mock LLM、memory KG、eager Celery、单 child worker 和 local-only 环境。

**结论影响：**

- 该差异不能单独转化为真实 LLM planning 增益、统计显著性或生产性能结论。
- 外部参考抽样匹配率不是人工真值精度、召回率或完整位置误差。
- 单 AOI/案例的恢复现象不能代表跨地区恢复能力。

**证据：**

- `docs/current/evidence/p4-external-validity/2026-08-01-freeze-c-p4-external-validity.json`
- `docs/current/evidence/p4-external-validity/2026-08-01-freeze-c-p4-paper-materials.md`

## 5. 研究分支 runner 不能证明当前 KG v1 驱动的正式规划效果

**审计数据：** `research/product-contract` 归并审计发现：

- `build_planning_context()` 由 case 字段和 Python 常量拼装 KG-like context，没有直接调用当前 `KGRepository` 或 KG release API。
- 研究分支维护 `PLANNING_ALGORITHM_BY_LAYER`、`RUNTIME_ALGORITHM_BY_LAYER` 和 `TASK_KIND_BY_LAYER`，存在 selected/resolved/executed 混淆。
- 研究版质量服务重新定义 Python 质量政策，可能恢复第二知识真源。
- 研究分支只实现五组，缺少当前 A0 要求的独立 `rules-only`。

**结论影响：**

- 该分支上的 runner 通过测试，只能证明开发资产可运行，不能证明当前 KG v1 已驱动正式规划。
- 旧五组、150-run 协议和旧 runner 输出不能直接升级为当前六组正式证据。
- 不能把研究分支中的结构化决策、gold 隔离或最小 E2E 代码直接当作方法效果结果。

**证据：**

- `docs/current/research-branch-kg-v1-merge-audit.md`
- `origin/research/product-contract`

## 6. C06 recovery 预期没有被正式运行验证

**实验数据：** C06 预冻结候选通过质量门，没有出现预注册的自然失败条件；正式 recovery 实验未运行。

**结论影响：**

- 不能把 C06 预期 recovery 机制写成已经完成的正式实验结论。
- 不能为了维持旧叙事而人为制造失败或修改停止条件。
- C04 的单 AOI progressive delivery/supersession 不能替代 C06 recovery 对照。

**证据：**

- `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c06-failure-screening-r1`
- `docs/current/research-claim-evidence-ledger.md`

## 7. 不能支撑的总体表述

以下表述均未被当前数据支持：

- KG/full method 普遍优于 fixed workflow、rules-only、KG-only 或 LLM-only。
- raw Full KG 注入已经稳定带来规划增益。
- 方案 B 已经统计非劣、普遍优越或改善 E2E 产品质量。
- 完整方法已经提高总体恢复率、交付成功率或生产韧性。
- 当前结果已经证明跨 AOI、跨灾种、跨数据源的广泛外部有效性。
- 当前平台 core 的离线合同测试已经等同于生产能力或正式 benchmark 效果。
