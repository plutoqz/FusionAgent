# FusionAgent Benchmark Design V1

> 状态：active_zero_call_design
> Design ID：`fusionagent.benchmark-design.v1`
> 当前阶段：阶段 0 已完成，阶段 1 待执行
> 基线日期：2026-08-19
> 执行方案：[`benchmark-design-freeze-execution-plan.md`](../../benchmark-design-freeze-execution-plan.md)

## 当前目标

完成 `M-BENCH-DESIGN-FREEZE-V1`：冻结 benchmark charter、能力矩阵、template schema、评价合同和选择治理。当前目录尚未形成冻结包，不能用于生成实例、运行 judge、调用 Provider 或支持效果主张。

## 阶段 0 基线

| 项目 | 冻结值 |
| --- | --- |
| 分支 | `codex/benchmark-design-r1` |
| parent commit | `8c5302f0b30ceccd353ca442bec40daa0a884b8b` |
| parent remote | `origin/codex/research-governance-r1` |
| worktree | `D:\code\FusionAgent-benchmark-design` |
| KG release | `fusionagent-kg-v1.0.0` |
| KG semantic hash | `sha256:50067b9368914c47580707650789c04c78b2e856ccb3ef4d120a31f36c0ad71e` |
| Provider calls | `0` |
| judge calls | `0` |
| formal result roots | `0` |

## 权威输入哈希

哈希算法为 SHA-256，值为文件原始字节的小写十六进制摘要。

| 文件 | SHA-256 |
| --- | --- |
| `docs/current/research-charter.md` | `223d3ca0719a69c373a4e6a95853c1c55b23a18ae5cef40eb1267fe10c855207` |
| `docs/current/research-claim-evidence-ledger.md` | `afa05fcb8e496c8bda528837e50d86b8f942eaa93967b59f59580a0443e282ef` |
| `docs/current/research-experiment-ledger.md` | `a1f859e306701cc2293287168c29d70254800a05ecf9bfe166419d1f4f50ec14` |
| `docs/current/research-governance-index.md` | `f1080d9961a6cab16e21f85e4b5b04bd9458d9eca1a4336522f8aea4045d06d6` |
| `kg/ontology/v1.0.0/release.json` | `8d0d801331a4c57b062442f2b7cc9b836de207ee3792d0de2db75b65bbbeb35b` |

## 已确认边界

1. 原六组保持不变；方案 B 仅作为 I2/RQ3 接口消融。
2. C01-C06、H01-H06、H07-H09 全部属于已观察材料，禁止进入新 confirmation。
3. 本阶段没有修改 KG v1、历史 protocol、evidence root、Planner、Prompt 或 evaluator。
4. 当前只允许设计资产和只读审计器，不允许案例平台实现。

## 恢复点

```text
current_goal: M-BENCH-DESIGN-FREEZE-V1
current_stage: 1 - benchmark charter
next_acceptance: G1-CHARTER-FROZEN
worktree: D:\code\FusionAgent-benchmark-design
branch: codex/benchmark-design-r1
parent: 8c5302f0b30ceccd353ca442bec40daa0a884b8b
```

恢复时先运行：

```powershell
git status --short --branch
git merge-base --is-ancestor origin/codex/research-governance-r1 HEAD
```

若 parent、权威输入或 KG release 与本记录不一致，必须停止并解释差异，不能自动混用旧设计。
