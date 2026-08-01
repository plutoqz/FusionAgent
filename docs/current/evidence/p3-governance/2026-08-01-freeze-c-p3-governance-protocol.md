# Freeze C P3 治理对照与消融协议

## 目的

在冻结的 C02/C04/C06 案例上，对产品契约、质量门、降级恢复和任务优先级做最小治理方向比较。该实验只比较治理行为，不比较融合算法本身。

## 对照组

| 变体 | 实验开关 | 预期移除的机制 |
| --- | --- | --- |
| 完整方法 | `full_method` | 无 |
| 无产品契约 | `no_product_contract` | 运行期产品契约绑定、契约质量字段和 provisional/supersession 授权 |
| 无质量门 | `no_quality_gate` | 融合输出后的质量门与质量失败阻断；保留输出 schema 校验 |
| 无降级恢复 | `no_degraded_recovery` | 不执行 manifest 中的 resume 阶段 |
| 固定优先级 | `fixed_priority` | 用 KG 静态 `execution_order` 替代请求中的上下文任务顺序 |

## 固定条件

- 同一 manifest：`docs/thesis/manifests/2026-07-20-c02-c04-c06-real-data.json`
- C02/C04/C06 使用相同外部数据、AOI 和阶段源配置。
- memory KG、mock LLM、eager Celery、单 child worker、local-only、禁用 artifact reuse。
- 显式固定 `GEOFUSION_PLAN_GROUNDING_MODE=report`，与 P2 Freeze C 运行协议一致；不把 grounding 模式差异归因于治理变体。
- 每个变体独立目录运行一次；不运行全量测试。

## 指标

- 计划有效率：初始阶段所有 child 的 `validation.json.valid` 均为真时计为该案例通过；保留原始 validator issue，不用最终交付掩盖它。
- 首次质量门通过率：初始阶段的质量报告全部 `accepted=true` 且无 child 失败时通过；质量门被禁用时为不可用值，并另报绕过率。
- 最终交付成功率：最终阶段处于案例允许阶段且至少存在一个交付 artifact；无降级恢复跳过最终 resume 阶段时计为失败。
- 恢复成功率：C04/C06 的恢复机会为分母；产生新 child run 且最终有 artifact 时计为成功。
- 恢复代价：恢复阶段相对于初始阶段新增 child run 的数量。
- 关键图层按时交付率：初始阶段首个任务为案例关键图层且该图层已有 artifact。
- gap 声明正确率：机器报告中的观测 gap 类型覆盖 manifest 声明的期望类型。
- 证据完整率：案例证据文件、child 的 plan/validation/audit 均存在。

## 运行命令

```powershell
.venv\Scripts\python.exe scripts\run_governance_ablation.py
```

正式机器报告和中文摘要落在 `docs/current/evidence/p3-governance/`。本轮原始运行证据统一保存在 `D:\code\freeze-c-evidence\` 下：完整方法、无产品契约和无质量门位于 `p3-governance-20260801-c02-c04-c06-grounding-report-v2\`，无降级恢复和固定优先级位于 `p3-governance-20260801-c02-c04-c06-grounding-report-missing\`；每个变体的真实路径和 `experiment_evidence_manifest.json` 路径均记录在机器报告中。`...-grounding-report\` 与 `...-grounding-report-v2\` 中未闭合的早期运行仅作诊断保留，不并入正式汇总。

## 解释边界

每个变体只有一次运行，结果是最小比较性证据和后续重复实验的协议样本，不报告统计显著性、效果量置信区间或跨 AOI 外部有效性。`no_quality_gate` 的质量门通过率不可直接解释为通过；`fixed_priority` 只检验任务顺序差异。
