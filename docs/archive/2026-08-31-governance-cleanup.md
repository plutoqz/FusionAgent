# 2026-08-31 文档与分支归档清单

## 冻结基线

- 当前分支：`codex/benchmark-platform-dev-r1`
- 当前 HEAD：`5bf70ed51f0121901f9908ac7498e537b2abeb40`
- 平台 core tag：`benchmark-platform-core-v1`
- 设计 tag：`benchmark-design-freeze-v1`（`08b55f7e03eabb74721979153df57aeee3200538`）
- 协议 tag：`benchmark-platform-protocol-v1`（`4db9f51f261d61ecb5c17b726d9897a09773eec2`）

## 文档动作

- 归档 `project-status.md`、`claims-and-priorities.md`、`repository-worktrees.md` 三个历史快照。
- 归档 `research-p3-p4-merge-and-evidence-plan.md` 和 `benchmark-design-freeze-execution-plan-2026-08-19.md` 两个已完成计划。
- 在原 `docs/current/` 路径保留 `superseded` 兼容入口，避免历史脚本、测试和外部链接失效。
- 新增三份当前证据整理：支持性、非支持性/负结果、后续设计与补充实验。
- 更新 `docs/README.md`、根 README、研究章程、治理入口、实验账本和 Benchmark V1 链接，使当前下一验收点与 P7 冻结状态一致。

## 分支动作

| 分支 | 动作 | 依据 |
| --- | --- | --- |
| `codex/benchmark-design-r1` | 删除本地和远程分支 | tip 已被当前平台分支包含；冻结提交由 `benchmark-design-freeze-v1` 保留 |
| `codex/benchmark-platform-protocol-r1` | 删除本地和远程分支 | tip 已被当前平台分支包含；冻结提交由 `benchmark-platform-protocol-v1` 保留 |
| `origin/codex/p3-planning-formal-r1` | 保留 | 原六组正式 planning 证据 |
| `origin/codex/kg-llm-method-r1` | 保留 | B 方法开发、repair 和人工评价证据 |
| `origin/codex/kg-llm-confirmation-r1` | 保留 | H07-H09 独立 confirmation 证据 |
| `origin/codex/research-governance-r1` | 保留 | 治理与口径历史 checkpoint |
| `origin/codex/evidence-and-road-followups` | 保留 | 历史 evidence follow-up |
| `origin/research/product-contract` | 保留 | 归并审计所依据的研究资产来源 |

未删除 `D:\code\FusionAgent-formal-f47fbef` 和 `D:\code\FusionAgent-head-baseline` 两个 detached evidence worktree；它们继续承担历史复核用途。
