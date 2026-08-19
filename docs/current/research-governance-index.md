# FusionAgent 研究治理入口

> 状态：A1 当前唯一执行入口
> 更新日期：2026-08-19
> 所在分支：`codex/research-governance-r1`
> A0 研究基线：[研究章程](research-charter.md)

## 1. 一分钟当前口径

1. 研究主体、O1-O4、RQ1-RQ4 和 I1-I4 继续以 `research-charter.md` 为唯一 A0 权威，不修改研究主线。
2. 原六组仍是 RQ3 主实验：fixed workflow、rules-only、KG-only、LLM-only、LLM + capability KG、LLM + full contract KG。
3. 方案 B 只属于 I2/RQ3 的 KG-LLM 接口消融。H01-H06 是开发及 post-held-out repair 证据；H07-H09 是独立 planning confirmation。两者不得混池，也不得替代原六组。
4. 原六组的三类 LLM 条件已完成 90 次冻结调用，但 180-item 双人盲评仍未开始，比较性主张保持 `pending_human_review`。
5. 当前 C02/C04/C06 端到端证据只支持单 AOI、指定案例事实；不支持六组执行优势、恢复率改善或跨 AOI 结论。
6. 当前工作重点转为参数化、分层、可诊断的案例与评价体系。该工作处于协议设计阶段，不授权新 Provider 调用、KG 语义修改或正式实验。

## 2. 当前唯一下一验收点

在任何平台实现或新模型调用前，冻结以下零调用设计资产：

1. `benchmark charter`：服务的 O/RQ/I/claim、非目标、开发集与正式集边界。
2. 案例能力矩阵：机制族、复杂度层级、陷阱类型和所诊断能力。
3. 参数化 template schema：语义不变量、因果变量、干扰变量、oracle、veto 和 KG crosswalk。
4. 评价合同：分层 gate、主指标、辅助指标、人工 rubric 和 LLM judge 的非正式角色。
5. 选择治理：禁止按当前方法胜负选例；冻结模板、seed、停止条件和 held-out 生成规则。

上述五项被明确验收前，不进入案例平台实现，不运行自动 judge，不生成新的正式结果根。

逐阶段执行顺序、产物合同、验收、回滚和恢复检查点见 [`benchmark-design-freeze-execution-plan.md`](benchmark-design-freeze-execution-plan.md)。该计划终止于 `M-BENCH-DESIGN-FREEZE-V1`，不授权后续平台实现或 Provider 调用。

## 3. 文档权威顺序

| 顺序 | 文档 | 权威范围 |
| --- | --- | --- |
| A0-1 | `research-charter.md` | 研究主体、目标、RQ、创新点、核心主张和非主张 |
| A0-2 | `document-governance.md` | 文档等级、归档、继承和状态规则 |
| A1-1 | 本文件 | 当前阶段、唯一下一验收点、分支和文档入口 |
| A1-2 | `research-claim-evidence-ledger.md` | 当前主张状态、允许表述、缺口和证据边界 |
| A1-3 | `research-experiment-ledger.md` | 每个实验集、方法版本、案例角色和复用范围 |
| A1-4 | `benchmark-design-freeze-execution-plan.md` | 当前里程碑的阶段、产物、验收、回滚和恢复合同 |
| A1-5 | 当前明确冻结的 protocol/manifest | 单次实验的输入、模型、指标、预算和停止条件 |
| A3 | 旧状态、旧计划、历史 checkpoint 和 evidence root | 仅用于追溯，不决定当前下一动作 |

当旧文档与本入口冲突时：A0 语义由 `research-charter.md` 决定；执行状态由本入口决定；证据可用范围由两个账本决定。

## 4. 当前分支与 Worktree 角色

| 路径/分支 | 冻结身份 | 当前角色 | 修改规则 |
| --- | --- | --- | --- |
| `D:\code\FusionAgent` / `main` | `f47fbef` | 共享稳定基线；存在用户本地改动和未跟踪文件 | 本治理批次不修改、不清理 |
| `origin/codex/p3-planning-formal-r1` | `ce37073` | 原六组正式 planning 证据 checkpoint | 只读，不改写历史证据 |
| `origin/codex/kg-llm-method-r1` | `446a7dd` | B 开发、H01-H06 repair 与人工评价 checkpoint | 只读，不作为 confirmation 分支 |
| `codex/kg-llm-confirmation-r1` | `bfd5308` | H07-H09 独立 confirmation checkpoint | 只读，不继续追加方法修改 |
| `codex/research-governance-r1` | 从 `bfd5308` 分出 | 当前文档、口径、账本和执行方案 checkpoint | 本批次推送后只读；实际设计从其远程 HEAD 新建 `codex/benchmark-design-r1` |
| `D:\code\FusionAgent-head-baseline` | detached `db256d5` | 独立基线复核 | 只读 |

任何 KG v1.1、案例平台或方法实现都必须从治理分支再建立独立实现分支，不能直接追加到 formal、method 或 confirmation checkpoint。

## 5. 当前材料角色

| 材料 | 当前角色 |
| --- | --- |
| `research-case-manifest-v1.json` | C01-C06 原主实验开发/正式历史案例；不得作为未来独立确认集 |
| `research-case-manifest-heldout-method-b-v1.json` | H01-H06 B 开发与修复案例；禁止重新用于 confirmation |
| `research-case-manifest-confirmation-v1.json` | H07-H09 B 接口确认案例；只回答 planning 接口机制 |
| `research-p3-p4-merge-and-evidence-plan.md` | 历史实施与 checkpoint 日志；不再是当前下一步入口 |
| `claims-and-priorities.md` | 2026-08-04 A0 口径与旧状态快照；当前 claim status 由新账本继承 |
| `project-status.md` | 2026-08-13 项目状态快照；当前执行状态由本入口继承 |

## 6. 变更与实验闸门

每项后续工作必须同时记录：

- 服务的 `O/RQ/I/claim ID`。
- 所属类型：baseline、ablation、method revision、development、confirmation 或 selective E2E。
- 允许使用的案例集和禁止复用的案例集。
- 源码分支、commit、KG release、template/evaluator/protocol 版本。
- 是否发生 Provider 调用、是否需要人工评价、结果允许支持的最强表述。

发生下列任一情况必须停止并新建协议：

- 看过正式结果后修改模板、gold、rubric、停止条件或 case selection。
- 修改 KG 语义、方法实现或信息边界后仍试图混用旧结果。
- 将 development/post-repair 结果升级为独立 confirmation。
- 将 planning、execution、quality 或 external validity 指标互相替代。
- 使用 LLM judge 结果作为正式人工真值。

## 7. 更新纪律

1. 本入口只保留当前状态，不追加长篇执行日志。
2. 实验终态写入 `research-experiment-ledger.md`，主张变化写入 `research-claim-evidence-ledger.md`。
3. 旧 protocol、manifest、原始响应、人工决策和 evidence root 保持不可变。
4. 新阶段被验收后，更新本文件的“当前唯一下一验收点”，并在 Git 提交中注明被替代阶段。
