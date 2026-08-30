# Benchmark Platform Core V1 Implementation

> 当前阶段：P6/BP6 complete
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
| [`p3_checkpoint.json`](p3_checkpoint.json) | P3 development-only 生成与验证证据清单 |
| [`p3_audit.json`](p3_audit.json) | BP3 机器审计结果 |
| [`p4_checkpoint.json`](p4_checkpoint.json) | P4 relation/view isolation 验证证据清单 |
| [`p4_audit.json`](p4_audit.json) | BP4 机器审计结果 |
| [`p5_checkpoint.json`](p5_checkpoint.json) | P5 artifact store、checkpoint 与恢复验证证据清单 |
| [`p5_audit.json`](p5_audit.json) | BP5 机器审计结果 |
| [`p6_checkpoint.json`](p6_checkpoint.json) | P6 离线 CLI、退出码与边界测试证据清单 |
| [`p6_audit.json`](p6_audit.json) | BP6 机器审计结果 |

P0 只证明开发分支精确继承冻结协议，环境与输入身份已记录，未来 output root 尚不存在，且平台代码、实例、Provider、judge、confirmation、formal 和 E2E 均未启动。

P0 首次按协议示例运行 `tests/test_benchmark_platform_*.py` 时，PowerShell 未展开传给原生命令的 glob，pytest 以 exit code `4` 返回路径不存在。第二次跨平台 collection 又纳入了协议分支专用测试；这些测试有意禁止 implementation 目录，因此在开发分支失败。第三次关键词排除虽为 exit code `0`，却误排除了两个 P0 测试，按不完整验收拒绝。三次尝试均保留在 baseline；最终核心测试命令使用精确模块排除。

一次确定性审计复跑还发现初版进程探针用通用 `pytest` 关键词误报了其他任务的测试进程。该失败审计保留在 baseline；探针已收窄为仅匹配本 worktree、`benchmark_platform`、核心审计器或平台测试，不终止也不干预无关进程。

## 恢复点

```text
current_goal: M-BENCH-PLATFORM-CORE-V1
completed_stage: P6
completed_gate: BP6
next_stage: P7 implementation audit and freeze
next_gate: BP7
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

P3 新增的 `benchmark_platform.generator` 仅在内存中生成 development unit，绑定冻结 seed namespace、master seed、cell 和 attempt 上限，输出稳定的成员 hash 与 development instance ID。它拒绝 confirmation/E2E/错误 seed/未知 cell，不调用 Provider/LLM，不写入 benchmark corpus 或 future output root。

P4 新增的 `benchmark_platform.relations` 与 `benchmark_platform.views` 使用受限 JSONPath、完整 payload mutation audit 和显式 failure taxonomy 校验五类 experiment unit；三类 view 均由 allowlist 重建，planner forbidden/evaluator-only 路径、gold subtree 和 condition/run identity 泄漏均 fail closed。P4 不写入 run root。

P5 新增的 `benchmark_platform.store` 仅提供 development run root 的 write-new 原子发布、固定阶段 checkpoint、显式 resume binding 重算与完整已提交输出 hash 校验。重复有效实例、已有 output root、阶段越迁和篡改均 fail closed；终态 `checksums.json` 覆盖 root 内除自身外的全部发布文件，并由 root 外持有的 `TerminalBinding` 绑定其自身 hash。所有 P5 replay 仅使用 pytest 临时目录，未创建实际 development corpus。

P6 新增的 `benchmark_platform.cli` 只暴露冻结合同中的七个离线命令，采用结构化单行 JSON 输出和稳定退出码：成功 `0`、用法错误 `2`、输入或合同失败 `3`、未处理内部错误 `4`。CLI 的 development 生命周期必须按 `generate-development -> validate-run -> project-views -> audit-run` 显式推进，`resume-development` 重新加载冻结设计和模板并重算 code revision binding。subprocess、tamper、resume、no-network 与 forbidden-import 测试均只使用 pytest 临时目录；未创建仓库内 corpus 或 future output root。

P1 首次全核心回归有 `30 passed, 1 failed`：P0 测试错误地把 P0 时的依赖哈希与已获准变更依赖的 P1 工作树比较。失败保留在 P1 checkpoint；修复后 P0 依赖快照改由 `e71c106` Git blob 验证，设计、协议和 KG 冻结输入仍校验当前文件。

不得从 P6 自动进入 P7。P7 需要新的明确执行指令；在此之前不得创建实现 freeze tag、修改治理账本、开展人工最终复核或进入 template authoring、confirmation、E2E、Provider/judge 阶段。
