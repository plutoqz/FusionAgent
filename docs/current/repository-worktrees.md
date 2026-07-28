# 仓库、分支与 Worktree 角色

> 状态：A0 当前权威工作流
> 更新日期：2026-07-28

## 1. 当前布局

| 路径 | 当前分支/提交 | 当前状态 | 角色 |
| --- | --- | --- | --- |
| `D:\code\FusionAgent` | `main@db256d5` | 已与 `origin/main` 同步；保留少量本机未提交文件 | 共享稳定集成 |
| `D:\code\FusionAgent-freeze-c-93ebdc5` | detached `93ebdc5`；标签 `freeze-c-20260725` | 干净 | Freeze C 只读复现基线，不再占用长期分支 |
| `D:\code\FusionAgent-worktrees\research` | `research/product-contract` | Phase 1–4 研究增量已提交并同步 main | 产品契约、实验协议、本体 v2 和论文研究 |

主路径当前检出 `main`。分支和 worktree 状态仍应以 `git status --short --branch` 与 `git worktree list` 的实际结果为准。

## 2. 不可破坏约束

1. 不在 Freeze C worktree 中进行活动开发或文档编辑。
2. 不删除、重置或强制清理 dirty 的 research worktree。
3. 不把一次性交付分支长期保留；合并后删除本地和远程分支。
4. 不把实验临时产物、渲染缓存和诊断目录提交为当前文档。
5. 不在未核对差异时批量迁移跨 worktree 文件。

## 3. 各工作区职责

### Main 工作区

`D:\code\FusionAgent` 用于：

- 维护共享 schema、manifest、仓库接口和测试。
- 接纳已经验证的产品契约本体和文档治理能力。
- 作为短期任务分支的起点和稳定成果的合并目标。

本机 `.claude` 设置、Reasonix 状态、tmp 记录和未分类脚本不属于 `main` 共享提交。

### Freeze C 基线

`D:\code\FusionAgent-freeze-c-93ebdc5` 只用于：

- 复核 commit `93ebdc51c8732ec466067de760a65f30f3f1155c`。
- 重建或验证 C02/C04/C06 的冻结证据。
- 对比后续实现是否改变冻结行为。

允许的操作是只读检查或从该提交创建新的临时 worktree；不在该目录直接编辑。

### Research Worktree

`D:\code\FusionAgent-worktrees\research` 用于：

- 产品契约 KG 和七层本体 v2。
- 五类规划基线、稳定性协议和审计协议。
- 论文案例、评分规则、实验 runner 和研究写作。
- KG/LLM 责任边界与实验性实现。

该 worktree 已提交 `PROJECT.md`、`docs/CURRENT.md`、本体 v2、稳定性协议、实验 runner、runtime、schemas、services 和 tests，并已合入 `main@db256d5`。后续正式实验仍在本分支推进，稳定能力再提升到 `main`。

## 4. 稳定成果提升流程

当前只保留两条长期分支：

- `main`：共享稳定集成分支。
- `research/product-contract`：确有并行、未提交研究工作的长期研究分支。

`codex/repository-docs-consolidation-20260728` 已于 2026-07-28 合并到 `main`，本地和远程分支均已删除。原 `app/autonomous-fusion` 与 `main` 没有提交差异且 worktree 干净，也已删除。以后需要应用开发时，从最新 `main` 创建按任务命名的短期分支，不预留空的长期 app 分支。

推荐流程：

```text
research/product-contract
  -> 验证研究协议/契约能力
  -> 提升共享部分到 main

main
  -> 同步回 research

main
  -> 按具体任务创建短期 app/feature 分支
  -> 验证并合并
  -> 删除短期分支
```

需要改变共享 schema 时：

1. 在来源分支完成实现和定向测试。
2. 明确哪些文件是共享稳定能力，哪些仍是实验性材料。
3. 通过独立提交或挑选提交提升共享部分到 `main`。
4. 从 `main` 同步到 research；如存在短期应用分支，也同步共享变更。
5. 在所有受影响分支分别运行定向测试。

## 5. 日常检查命令

```powershell
git status --short --branch
git worktree list --porcelain
git branch -vv
```

清理失效的 worktree 元数据可使用：

```powershell
git worktree prune
```

该命令不应与删除现存 worktree 混为一谈。移除 worktree 前必须先确认目标绝对路径、分支状态和未提交修改。

## 6. 提交边界建议

为了便于审查，本轮修改拆分为：

1. 产品契约图谱实体和运行接入。
2. 对应测试与 manifest 更新。
3. 知识图谱导出脚本和机器可读文档包。
4. 仓库/文档治理与 PPT 归档。

本地还保留一个只存在于远程的历史分支 `origin/codex/evidence-and-road-followups`。它包含尚未并入 `main` 的旧 evidence/road 工作，因此本轮不删除远程副本；确认其成果已被吸收或明确放弃后再删除。

若已有修改无法无损拆分，不使用 reset 或 checkout 强拆；优先保留当前工作树，再通过精确暂存形成可审查提交。
