# FusionAgent 实验账本

> 状态：A1 当前权威实验索引
> 更新日期：2026-08-19
> 当前执行入口：`research-governance-index.md`
> 当前主张状态：`research-claim-evidence-ledger.md`

## 1. 登记规则

每个实验集必须记录方法版本、案例角色、调用与人工评价状态、允许复用范围。preflight、正式运行、人工评价和 E2E 不因目录相邻而自动属于同一证据层。

状态含义：

- `frozen_complete`：运行与完整性审计完成。
- `pending_human_review`：运行完成，人工评价未完成。
- `development_only`：用于设计或修复，不能进入正式确认。
- `bounded_observation`：只支持指定案例事实。
- `negative_result`：预注册机制未出现或主张未获支持。
- `historical_only`：仅用于追溯，不进入当前比较性结论。
- `active_zero_call_design`：只授权零调用协议设计，不授权平台实现或实验运行。
- `not_authorized`：尚未通过启动闸门，不得实施或调用 Provider。

## 2. RQ3 原六组主实验

| Evidence ID | 方法/案例 | 证据位置 | 状态 | 允许用途 | 禁止用途 |
| --- | --- | --- | --- | --- | --- |
| `E-RQ3-DET-54` | C01-C06 x fixed/rules/KG-only x 3 exact repetitions | `D:\code\fusionagent-evidence\p3-planning-repeated\2026-08-14-deterministic-repeated-v1-audit.json` | `frozen_complete` | deterministic 稳定性和 cell baseline | 把重复行当独立样本 |
| `E-RQ3-LLM-90` | C01-C06 x 3 LLM conditions x 5 repetitions | `D:\code\fusionagent-evidence\p3-planning-repeated\2026-08-15-deepseek-v4-flash-repeated-combined-v1` | `pending_human_review` | 自动描述、结构稳定性、token/latency | 比较性 superiority 或 E2E 能力 |
| `E-RQ3-MANUAL-180` | 90 runs 对应 180 个盲评 item | `D:\code\fusionagent-evidence\p3-planning-repeated\2026-08-15-manual-review-combined-v1` | `pending_human_review` | 完成人工双评和裁决后用于 RQ3 | 当前 null decision 不得解释为 pass/fail |
| `E-RQ3-SIX-DESC` | 六组旧描述表 | `D:\code\fusionagent-evidence\p3-planning-formal\2026-08-13-six-group-descriptive-comparison-v1.json` | `historical_only` | 追溯早期分组和 metric | 最终六组统一比较 |

当前事实：90/90 LLM runs 完成、18 cells 各 5 次、总 token `1,171,179`、72 个自动检查失败；180 个 manual decisions 仍为空。原六组实验尚未闭环。

## 3. 方案 B 接口消融

| Evidence ID | 案例/阶段 | 证据位置 | 状态 | 允许用途 | 禁止用途 |
| --- | --- | --- | --- | --- | --- |
| `E-B-SCREEN` | C01-C06，6 次开发 screen | `D:\code\fusionagent-evidence\p3-planning-method-b\2026-08-15-method-b-screen-v1-real` | `development_only` | 发现接口缺陷 | 正式效果比较 |
| `E-B-H01-H06` | H01-H06，原 54 calls + 18 repair calls | `D:\code\fusionagent-evidence\p3-planning-method-b\2026-08-16-method-b-heldout-formal-v1` 与 `D:\code\fusionagent-evidence\p3-planning-method-b\2026-08-16-method-b-heldout-formal-repair-v1` | `development_only` | post-repair 机制分析 | pristine confirmation、通用 superiority |
| `E-B-H01-H06-HUMAN` | H01-H06，54 个人工 rubric item，双评+裁决 | `D:\code\fusionagent-evidence\p3-planning-method-b\2026-08-17-method-b-manual-adjudication-v1` | `frozen_complete` | 解释 specific interface repair | E2E、跨 AOI、统计推广 |
| `E-B-H07-H09` | H07-H09 x 3 conditions x 3 repetitions，27 calls | `D:\code\fusionagent-evidence\p3-planning-method-b\2026-08-17-method-b-independent-confirmation-v1` | `frozen_complete` | 独立 planning confirmation | 与 H01-H06 混池 |
| `E-B-H07-H09-HUMAN` | H07-H09，63 个 rubric item，双评+裁决 | `D:\code\fusionagent-evidence\p3-planning-method-b\2026-08-18-method-b-independent-confirmation-manual-adjudication-v1` | `frozen_complete` | 报告 B 与 Full KG 均为 `21/21` 的描述性人工结果 | 统计非劣、B 普遍优越或产品质量结论 |

## 4. RQ4 选择性执行与外部有效性

| Evidence ID | 案例 | 证据位置 | 状态 | 最强允许表述 |
| --- | --- | --- | --- | --- |
| `E-RQ4-C02` | Caracas C02 | `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c02-water-road-e2e-r2` | `bounded_observation` | water polygon 成功；waterways 在算法前因未计划 source expansion 和 semantic contract invalid 而 fail closed；road 未运行 |
| `E-RQ4-C04` | Caracas C04 | `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c04-road-e2e-r4` | `bounded_observation` | 两阶段 road artifact 与 supersession 成功；delivery 仍为 degraded；单 AOI |
| `E-RQ4-C06` | Caracas C06 screening | `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c06-failure-screening-r1` | `negative_result` | 候选通过质量门，旧“必然失败”机制退役；未运行正式 recovery |
| `E-RQ4-S6` | C02/C04/C06 统一只读审计 | `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-s6-selective-e2e-audit-v1` | `frozen_complete` | 固定上述三项边界，不支持方法 superiority |
| `E-E5-AOI` | Caracas/Abidjan/越南候选清单 | `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-15-multi-aoi-candidate-inventory-v1` | `negative_result` | Caracas 是相关案例唯一 source-closed AOI；E5 未选例 |

## 5. 历史 evidence 的复用规则

1. 历史 preflight 只证明当时的输入、预算和运行准备，不证明能力。
2. 不完整 v2 LLM repeated batch 继续排除，不与 v3/extension 混池。
3. C01-C06、H01-H06、H07-H09 均已被观察，不能作为新 benchmark 的独立正式确认实例。
4. 旧 C02/C04/C06 E2E 可作为机制和工程风险依据，但不能计入未来新协议的重复样本。
5. 新 template、KG、method、evaluator 或信息边界产生新版本后，必须创建新 evidence root 和新 Evidence ID。

## 6. 当前未启动实验

| Planned ID | 目标 | 当前状态 | 启动闸门 |
| --- | --- | --- | --- |
| `P-BENCH-DESIGN` | 参数化、分层、可诊断案例与评价体系 | `active_zero_call_design` | 冻结 charter、能力矩阵、schema、评价合同、选择治理 |
| `P-BENCH-JUDGE` | 多模型开发 judge 平台 | `not_authorized` | 先完成人工校准协议、模型角色、预算和非正式用途边界 |
| `P-BENCH-FORMAL` | 新 held-out 六组规划实验 | `not_authorized` | 冻结 KG/method/template/evaluator/seed，完成 development/confirmation 隔离 |
| `P-BENCH-E2E` | 新案例选择性真实执行 | `not_authorized` | 先由 planning 机制结果和 source-closed inventory 预注册选例 |

`P-BENCH-DESIGN` 的唯一详细执行方案为 [`benchmark-design-freeze-execution-plan.md`](benchmark-design-freeze-execution-plan.md)。其下一重大里程碑是 `M-BENCH-DESIGN-FREEZE-V1`；计划文档存在不等于该里程碑已完成。

## 7. 更新规则

- 只在实验终态或闸门状态变化时更新本账本。
- 原始结果数字来自冻结 JSON，不手工重算后覆盖历史值。
- 新实验必须先分配 Evidence ID；运行后绑定 branch、commit、protocol hash、case/template version 和 evidence root。
- 任何失败、未执行尾部、人工分歧和负结果都保留。
