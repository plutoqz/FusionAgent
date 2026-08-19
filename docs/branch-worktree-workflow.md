# 分支与 Worktree 工作流

> 状态：A3 历史兼容入口
> 更新日期：2026-08-19

当前分支、worktree 角色和修改规则见 [`docs/current/research-governance-index.md`](current/research-governance-index.md#4-当前分支与-worktree-角色)。[`docs/current/repository-worktrees.md`](current/repository-worktrees.md) 也是历史布局快照。本文件只保留旧链接兼容，不得据此判断当前 HEAD、路径或 dirty 状态。

核心规则：

1. `D:\code\FusionAgent-freeze-c-93ebdc5` 是 detached `93ebdc5` 的干净只读复现基线，由标签 `freeze-c-20260725` 保持语义，不需要长期冻结分支。
2. `D:\code\FusionAgent-worktrees\research` 承担产品契约、本体、实验协议和论文研究。
3. `D:\code\FusionAgent` 当前是一次性仓库/文档交付分支，合并后删除。
4. 长期分支只保留 `main` 和确有并行研究工作的 `research/product-contract`。
5. 应用开发按任务从 `main` 创建短期分支，完成后合并并删除，不预留空的长期 app 分支。
6. 不删除、重置或强制清理任何有未提交修改的 worktree。

执行操作前始终检查：

```powershell
git status --short --branch
git worktree list --porcelain
```
