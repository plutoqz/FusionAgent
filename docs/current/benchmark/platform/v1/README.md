# FusionAgent Benchmark Platform Protocol V1

> 状态：draft_pending_human_review
> Protocol ID：`fusionagent.benchmark-platform-implementation-protocol.v1`
> 当前里程碑：`M-BENCH-PLATFORM-PROTOCOL-V1`
> 分支：`codex/benchmark-platform-protocol-r1`
> Worktree：`D:\code\FusionAgent-benchmark-platform-protocol`

## 当前目标

冻结参数化 benchmark 平台的独立实施协议。当前目录不包含平台实现，也不授权实例生成、Provider、judge、confirmation、正式实验或 E2E。

## 资产

| 文件 | 作用 |
| --- | --- |
| [`../../../benchmark-platform-implementation-protocol.md`](../../../benchmark-platform-implementation-protocol.md) | 分阶段实施、验收、回滚与恢复协议 |
| [`component_contract.json`](component_contract.json) | 组件、输入输出、路径和禁止依赖机器合同 |
| [`protocol_manifest.json`](protocol_manifest.json) | 冻结输入和协议文件 SHA-256 |
| [`protocol_review.json`](protocol_review.json) | 用户或独立审阅者决定 |
| [`protocol_audit.json`](protocol_audit.json) | 机器交叉审计 |

## 基线

```text
base_tag: benchmark-design-freeze-v1
base_commit: 08b55f7e03eabb74721979153df57aeee3200538
design_id: fusionagent.benchmark-design.v1
kg_release: fusionagent-kg-v1.0.0
provider_calls: 0
judge_calls: 0
benchmark_instances_generated: 0
formal_result_roots: 0
```

## 恢复点

```text
current_goal: M-BENCH-PLATFORM-PROTOCOL-V1
current_stage: protocol authoring and audit
next_acceptance: independent human protocol approval
implementation_authorized: false
```

恢复时先核对：

```powershell
git status --short --branch
git merge-base --is-ancestor benchmark-design-freeze-v1 HEAD
python scripts/audit_benchmark_platform_protocol.py --root docs/current/benchmark/platform/v1 --output docs/current/benchmark/platform/v1/protocol_audit.json
```
