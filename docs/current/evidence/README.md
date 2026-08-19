# FusionAgent 仓库内证据索引

> 状态：A1 证据目录分类索引
> 更新日期：2026-08-19

本目录保存冻结协议、prepared inputs、preflight、审计报告和少量证据绑定清单。目录内文件相邻不代表它们属于同一证据层，也不代表运行已完成或主张已成立。当前实验状态、Evidence ID 和允许表述以 [`research-experiment-ledger.md`](../research-experiment-ledger.md) 为准。

| 目录 | 当前角色 | 使用边界 |
| --- | --- | --- |
| [`p2-stability/`](p2-stability/) | Freeze C 三次稳定性重跑的协议与报告 | 只支持冻结环境中的语义稳定性 |
| [`p3-governance/`](p3-governance/) | Freeze C 治理消融协议、报告和 grounding 审计 | 不支持真实 LLM planning 增量 |
| [`p3-planning-pilot/`](p3-planning-pilot/) | v2-v5 输入与 schema 演进的 diagnostic/preflight 快照 | preflight 和 pilot 不等于正式效果证据 |
| [`p3-planning-formal/`](p3-planning-formal/) | 原六组 planning formal 协议冻结快照；v2 freeze audit 未通过，后续版本按各自 audit 解释 | 运行和人工评价状态必须查实验账本与外部 evidence root |
| [`p3-planning-repeated/`](p3-planning-repeated/) | repeated formal 与 extension 的协议、schedule 和模型 revision 绑定 | 不完整批次不得与已审计批次混池 |
| [`p3-planning-method-b/`](p3-planning-method-b/) | H01-H06 post-held-out repair 证据冻结清单 | `development_only`，不是独立 confirmation |
| [`p4-planning-e2e/`](p4-planning-e2e/) | C04 road v1-v5 协议演进和 preflight 快照 | 各版本不得混写；真实执行结论查 `E-RQ4-*` 账本项 |
| [`p4-external-validity/`](p4-external-validity/) | Freeze C 多 AOI 治理外部有效性切片 | mock LLM、探索性、受限外部有效性 |

## 版本解释规则

1. `protocol`、`prepared_inputs`、`schedule` 或 `preflight` 存在，只证明对应设计资产存在。
2. `freeze_audit.passed=true` 只证明冻结合同完整，不自动证明 Provider 调用、人工评价或 E2E 成功。
3. 旧版本和失败版本保持不可变；通过本索引和实验账本标记角色，不回写历史 JSON。
4. 原始响应、正式结果和人工决策主要位于 `D:\code\fusionagent-evidence\`，路径、状态和复用限制以实验账本为唯一入口。
5. 新证据必须先分配 Evidence ID，并绑定 branch、commit、protocol hash、case/template version 和 evidence root。
