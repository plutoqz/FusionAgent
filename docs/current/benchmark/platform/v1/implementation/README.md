# Benchmark Platform Core V1 Implementation

> 当前阶段：P2/BP2 complete
> 实现分支：`codex/benchmark-platform-dev-r1`
> Worktree：`D:\code\FusionAgent-benchmark-platform-dev`
> 协议基线：`benchmark-platform-protocol-v1@4db9f51f261d61ecb5c17b726d9897a09773eec2`

## 当前证据

| 文件 | 作用 |
| --- | --- |
| [`p0_baseline.json`](p0_baseline.json) | P0 环境、冻结输入、授权范围、命令和零调用基线 |
| [`p0_audit.json`](p0_audit.json) | BP0 机器审计结果 |
| [`p1_checkpoint.json`](p1_checkpoint.json) | P1 closed models、schema、canonical 与验证证据清单 |
| [`p1_audit.json`](p1_audit.json) | BP1 机器审计结果 |
| [`p2_checkpoint.json`](p2_checkpoint.json) | P2 design loader、crosswalk 与离线验证证据清单 |
| [`p2_audit.json`](p2_audit.json) | BP2 机器审计结果 |

P0 只证明开发分支精确继承冻结协议，环境与输入身份已记录，未来 output root 尚不存在，且平台代码、实例、Provider、judge、confirmation、formal 和 E2E 均未启动。

P0 首次按协议示例运行 `tests/test_benchmark_platform_*.py` 时，PowerShell 未展开传给原生命令的 glob，pytest 以 exit code `4` 返回路径不存在。第二次跨平台 collection 又纳入了协议分支专用测试；这些测试有意禁止 implementation 目录，因此在开发分支失败。第三次关键词排除虽为 exit code `0`，却误排除了两个 P0 测试，按不完整验收拒绝。三次尝试均保留在 baseline；最终核心测试命令使用精确模块排除。

一次确定性审计复跑还发现初版进程探针用通用 `pytest` 关键词误报了其他任务的测试进程。该失败审计保留在 baseline；探针已收窄为仅匹配本 worktree、`benchmark_platform`、核心审计器或平台测试，不终止也不干预无关进程。

## 恢复点

```text
current_goal: M-BENCH-PLATFORM-CORE-V1
completed_stage: P2
completed_gate: BP2
next_stage: P3 development generator
next_gate: BP3
automatic_progression: false
```

恢复时运行：

```powershell
git status --short --branch
python scripts/audit_benchmark_platform_core.py --stage P0 --baseline docs/current/benchmark/platform/v1/implementation/p0_baseline.json --output docs/current/benchmark/platform/v1/implementation/p0_audit.json
python scripts/audit_benchmark_platform_core.py --stage P1 --baseline docs/current/benchmark/platform/v1/implementation/p1_checkpoint.json --output docs/current/benchmark/platform/v1/implementation/p1_audit.json
python -m pytest tests -q -k benchmark_platform --ignore=tests/test_benchmark_platform_protocol.py --basetemp tmp/pytest-benchmark-platform-core
```

P1 新增的 `benchmark_platform.models` 与 `benchmark_platform.canonical` 只提供关闭式 runtime envelope、typed failures、Draft 2020-12 校验和确定性 canonical primitives。它们尚未加载/绑定完整冻结设计或 KG registries，也不生成 benchmark 实例。

P2 新增的 `benchmark_platform.design_loader` 与 `benchmark_platform.crosswalk` 仅加载并校验冻结设计身份、manifest 哈希、KG release identity 和只读 registry crosswalk。tamper、tag/commit 漂移、错误 KG release、未知/重复/歧义引用均 fail closed；P2 没有生成实例、写入 KG 或创建 future output root。

P1 首次全核心回归有 `30 passed, 1 failed`：P0 测试错误地把 P0 时的依赖哈希与已获准变更依赖的 P1 工作树比较。失败保留在 P1 checkpoint；修复后 P0 依赖快照改由 `e71c106` Git blob 验证，设计、协议和 KG 冻结输入仍校验当前文件。

不得从 P2 自动进入 P3。P3 需要新的明确执行指令；在此之前不得生成 benchmark 实例。
