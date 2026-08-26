# FusionAgent 参数化 Benchmark 平台实施协议 V1

> 状态：frozen_complete
> Protocol ID：`fusionagent.benchmark-platform-implementation-protocol.v1`
> 当前里程碑：`M-BENCH-PLATFORM-PROTOCOL-V1`
> 未来实施里程碑：`M-BENCH-PLATFORM-CORE-V1`
> 制定日期：2026-08-25
> 冻结设计输入：`benchmark-design-freeze-v1@08b55f7e03eabb74721979153df57aeee3200538`

## 1. 协议用途

本协议定义参数化 benchmark 实例生成与校验平台的最小实现边界、组件合同、逐阶段动作、验收证据、失败退出和恢复方式。当前工作只建立并审批协议；协议文件存在、提交或推送均不表示已经授权平台实现。

平台实现必须在本协议通过机器审计和独立人工复核后，由用户再次明确发出“按照平台协议开始实施”或等价指令。未经该指令，不得创建 `benchmark_platform/` 代码、生成 development benchmark 实例或修改依赖。

## 2. 研究位置与目的

### 2.1 服务范围

- 服务 O2/O3、RQ2/RQ3、I2/I4。
- 服务 `CL-BENCH-CAUSAL`、`CL-BENCH-INVARIANT`、`CL-BENCH-COMPOSE`、`CL-BENCH-RECOVERY`、`CL-BENCH-DIAG` 的后续可执行化。
- 平台是研究基础设施，不创建新论文主张，不构成“第七种方法”，不改变原六组或方案 B 的身份。

### 2.2 实验目的

未来平台实现要验证的是工程机制，而不是方法效果：

1. 冻结 template schema 能否被关闭式、确定性地加载和校验。
2. 单一 seed、template、变量赋值能否产生可复现 ID、canonical payload 和 SHA-256。
3. counterfactual、invariant、composition、temporal 单元能否在生成后验证关系约束并 fail closed。
4. planner-visible、evaluator-only、human-blind 三类 view 能否隔离，且 gold/oracle/veto 解释不泄漏给 planner。
5. 中断后能否按阶段 checkpoint 恢复，并拒绝输入哈希漂移或覆盖已有 run root。

这些机制通过只能支持 `implementation_validated_offline`，不能支持 planning 效果、执行质量、外部有效性或生产能力结论。

## 3. 授权边界

### 3.1 本协议阶段允许

- 修改 `docs/current/benchmark/platform/v1/` 下的协议资产。
- 新增本协议文档、只读审计器及聚焦测试。
- 创建并推送 `codex/benchmark-platform-protocol-r1`。
- 协议批准后更新治理入口和实验账本，并创建 `benchmark-platform-protocol-v1` tag。

### 3.2 本协议阶段禁止

- 不新增或修改 `benchmark_platform/` 实现代码。
- 不修改 `requirements.txt`、现有 `schemas/benchmark.py`、Planner、Prompt、validator、KG 或服务代码。
- 不生成 development、confirmation 或 E2E benchmark 实例。
- 不调用 Provider、LLM judge、mock model、外部 API 或网络数据源。
- 不解封 confirmation，不创建正式结果根，不运行现有研究实验。

### 3.3 未来实施仍然禁止

即使本协议获批，`P-BENCH-JUDGE`、`P-BENCH-FORMAL`、`P-BENCH-E2E` 仍为 `not_authorized`。平台核心实现只允许 development namespace；不得提供 confirmation、E2E、judge、Provider 或实验 runner 命令。

## 4. 冻结输入与已确认事实

1. Design freeze tag：`benchmark-design-freeze-v1`。
2. Design commit：`08b55f7e03eabb74721979153df57aeee3200538`。
3. Design ID：`fusionagent.benchmark-design.v1`。
4. KG release：`fusionagent-kg-v1.0.0`，semantic hash `sha256:50067b9368914c47580707650789c04c78b2e856ccb3ef4d120a31f36c0ad71e`。
5. 17 个 capability cells、17 个 template family IDs、5 类 experiment unit 已冻结，但具体 template family 文档尚未创作。
6. development seed namespace 和 master seed 已冻结；confirmation 与 selective E2E 未授权。
7. `schemas/benchmark.py` 属于旧 Freeze B 质量 benchmark，`extra="allow"` 且语义不同；它保留兼容，但不得作为新平台 V1 模型。

## 5. 目标与完成条件

### 5.1 当前协议里程碑

`M-BENCH-PLATFORM-PROTOCOL-V1` 只有在以下条件全部满足时完成：

1. 本协议和 `component_contract.json` 完整且互相一致。
2. 冻结设计 tag、commit、文件哈希、KG identity 均绑定并通过审计。
3. 未来实现的组件、输入、输出、错误、状态机、允许路径和禁止依赖均机器可读。
4. P0-P7 每阶段都有验收、证据、回滚和恢复点。
5. Provider/judge/实例/正式结果根计数均为 0。
6. 人工协议复核全部批准且未解决分歧为 0。
7. 工作树干净，协议 commit 与 annotated tag 已推送。

### 5.2 未来核心实现里程碑

`M-BENCH-PLATFORM-CORE-V1` 只证明离线平台核心机制：

- 关闭式 schema validation。
- canonical serialization、stable ID 和 hash。
- development-only deterministic generation。
- relation、crosswalk、partition 和 leakage validation。
- write-new artifact store、checkpoint 和 resume。
- CLI 的离线合同与错误码。

它不包含真实模型、正式案例结果、Web UI、服务部署、调度、并发 worker、数据库或 E2E。

## 6. 目标架构

未来新增独立包 `benchmark_platform/`，不得把新语义塞入旧 `schemas/benchmark.py`：

```text
benchmark_platform/
  models.py          closed runtime models and typed failures
  canonical.py       canonical JSON, IDs and SHA-256
  design_loader.py   frozen design binding and template loading
  crosswalk.py       read-only KG/source/contract ID validation
  generator.py       deterministic development-only generation
  relations.py       pair/set/composition/trace validation
  views.py           planner/evaluator/human packet projection
  store.py           write-new artifacts, checkpoints and resume
  cli.py             offline commands; no confirmation/E2E/provider/judge
```

组件详细合同以 [`component_contract.json`](benchmark/platform/v1/component_contract.json) 为机器权威。

## 7. 核心数据与状态合同

### 7.1 输入

- `FrozenDesignBundle`：冻结 charter、matrix、schema、evaluation、selection、manifest 的已校验只读绑定。
- `DevelopmentTemplate`：未来另行审阅的 template family 文档，必须符合冻结 schema。
- `GenerationRequest`：只允许 `partition=development`，绑定 frozen seed namespace、cell、unit index 和 output root。
- `ResumeRequest`：绑定 run ID、checkpoint stage 和所有输入哈希。

### 7.2 输出

每个 write-new development run root 至少包含：

```text
run_manifest.json
design_binding.json
template_snapshots/
generation_attempts.jsonl
instances.jsonl
validation_report.json
planner_packets.jsonl
evaluator_packets.jsonl
human_blind_packets.jsonl
leakage_audit.json
checkpoint.json
checksums.json
```

无效生成必须保留在 `generation_attempts.jsonl`，但不得进入有效实例计数。测试临时目录中的 contract fixtures 不登记为 benchmark instances，也不能进入 evidence ledger。

### 7.3 状态机

```text
created
  -> design_bound
  -> templates_validated
  -> generated
  -> relations_validated
  -> views_projected
  -> audited
  -> development_complete
```

每个阶段可进入 `failed_retained`。恢复只能从最近通过的 checkpoint 继续；任一输入哈希、版本、seed 或代码 revision 变化必须拒绝 resume 并创建新 run ID。

## 8. Fail-Closed 规则

1. design tag、manifest 或任一 frozen asset hash 不符：停止。
2. 未知字段、未知 template/cell/claim/gate/failure class：停止。
3. crosswalk ID 缺失、重复或指向非冻结 KG release：停止。
4. 非 development partition：停止，且不得创建输出根。
5. counterfactual pair 改变超过一个 causal variable：停止并保留 invalid attempt。
6. invariant set 改变非 nuisance field：停止并保留 invalid attempt。
7. planner packet 包含 evaluator-only/gold/oracle/veto explanation：停止并删除未发布 packet，保留 leakage report。
8. output root 已存在：拒绝覆盖；resume 必须显式提供匹配 checkpoint。
9. 网络、Provider、judge、LLM、执行器或质量服务依赖：构建/测试失败。
10. 不得用 fallback、修复解析、关键词猜测或默认值掩盖无效输入。

## 9. 分阶段实施流程

### P0：实施基线

- 从 `benchmark-platform-protocol-v1` 创建 `codex/benchmark-platform-dev-r1` 和独立 worktree。
- 记录 branch、HEAD、Python、依赖、Git、冻结设计/KG 哈希与零调用计数。
- 确认 `benchmark_platform/` 不存在，未来 output root 不存在。

验收：HEAD 精确继承协议 tag；工作树干净；无服务或实验进程写入；零调用。

### P1：关闭式模型与 canonicalization

- 新增 Pydantic V2 `extra="forbid"` runtime models。
- 增加 `jsonschema>=4.23,<5`，使用 Draft 2020-12 validator 校验冻结 template schema。
- canonical JSON 固定 UTF-8、sorted keys、紧凑分隔符、禁止 NaN/Infinity、换行策略和 SHA-256 前缀。
- ID 由 design/template/cell/partition/unit index/seed/canonical payload 决定。

验收：相同输入跨进程 hash/ID 相同；字段顺序不影响；语义变化改变 hash；未知字段 fail closed。

### P2：冻结设计加载与 crosswalk

- 校验 tag/commit/manifest/asset hashes 后建立 `FrozenDesignBundle`。
- matrix、schema、evaluation、selection 引用闭合。
- KG 只读加载 `kg/ontology/v1.0.0/release.json` 及冻结 catalog；不修改 KG。
- 所有 source/contract/algorithm/quality-policy ID 通过显式 registry crosswalk。

验收：tamper、unknown ID、错误 KG release、缺失引用均失败且不产生实例。

### P3：Development-only 生成器

- 只接受 `partition=development`。
- 使用冻结 master seed `2026081901` 和稳定派生 seed；禁止全局随机状态。
- 按 unit type 生成成员与 generation record，保留每次尝试。
- 达到最大尝试仍无效时登记 blocker，不替换语义或放宽 oracle。

验收：重复运行字节级一致；confirmation/E2E 请求在写盘前拒绝；无效生成完整保留。

### P4：关系验证与 view 隔离

- 验证 causal mutation count、invariant/nuisance 路径、task-local composition 和 temporal transition。
- 根据 frozen `views` 白名单投影三类 packet，不用黑名单删字段。
- leakage audit 递归检查 forbidden path prefixes 和 evaluator-only values。

验收：五类 unit 的正负 contract fixtures 均覆盖；gold leakage、跨任务污染和非法 transition 被定位到明确 failure class。

### P5：Artifact store、checkpoint 与恢复

- run root 只能 write-new，文件采用临时文件加原子 rename。
- 每阶段提交 checkpoint，记录输入/输出 hash、stage、代码 revision 和 terminal status。
- resume 重算所有绑定；漂移则拒绝，不能覆盖旧产物。
- `checksums.json` 在终态覆盖所有发布文件，自身通过外部 manifest 绑定。

验收：人工中断回放可从最近 checkpoint 恢复；重复提交不产生第二份有效成员；tamper 后恢复失败。

### P6：离线 CLI 与测试

允许命令仅为：

```text
validate-design
validate-template
generate-development
validate-run
project-views
audit-run
resume-development
```

CLI 不得包含 confirmation、E2E、judge、provider、model 或 execute 命令。测试使用 `tests/fixtures/benchmark_platform/` 中的非主张 contract fixtures 和 pytest 临时目录，不生成仓库内 benchmark corpus。

验收：单元、合同、tamper、resume、no-network、forbidden-import 测试通过；帮助文本和 exit code 稳定。

### P7：实现验收与冻结

- 运行聚焦测试和全量相关合同测试。
- 生成实现 manifest/audit，记录源码、依赖、fixture 和产物 hash。
- 由用户或独立审阅者复核组件边界、失败语义、view 隔离和恢复证据。
- 只有全部通过才更新治理账本并创建实现 tag；不自动进入 template authoring 或实例批量生成。

验收：机器审计和人工复核全部通过；工作树干净；commit/tag 推送；所有调用计数仍为 0。

## 10. 验收矩阵

| Gate | 证明对象 | 必需证据 | 不能支持 |
| --- | --- | --- | --- |
| `BP0` | 冻结输入身份 | tag/commit/hash audit | 平台能力 |
| `BP1` | closed models/canonical hash | unit tests + golden bytes | domain semantics |
| `BP2` | design/crosswalk fail closed | tamper/unknown-ID tests | KG 完整性普遍结论 |
| `BP3` | deterministic development generation | repeated offline run hashes | confirmation 独立性 |
| `BP4` | relation/view isolation | negative fixtures + leakage audit | planner 效果 |
| `BP5` | persistence/recovery | interrupt/tamper replay | exactly-once 分布式语义 |
| `BP6` | CLI/no-network boundary | subprocess/import/network tests | 生产部署 |
| `BP7` | bounded implementation closure | manifest/audit/human review | 正式实验或 E2E |

## 11. 最小验证命令

未来实施至少运行：

```powershell
python -m pytest tests/test_benchmark_platform_*.py -q
python scripts/audit_benchmark_platform_core.py --root <development-run-root> --output <audit.json>
python -m benchmark_platform.cli validate-design --design-root docs/current/benchmark/v1
git diff --check
git status --short --branch
```

实际命令、测试文件和 output root 必须在 P0 checkpoint 中冻结，不能在看到结果后改变验收口径。

## 12. 回滚、暂停与恢复

- P0-P2 失败：保留分支和失败证据，修复合同后重新过 gate；不生成实例。
- P3-P4 失败：保留 invalid attempts，回到 template 或 generator 的明确归因层；不得放宽 frozen oracle/veto。
- P5 恢复失败：旧 run root 只读保留，创建新 run ID；不得手工修补 checkpoint。
- 需要修改 benchmark V1 语义：停止平台实施，建立 benchmark V1.1/V2 变更协议。
- 需要 Provider、judge、confirmation、E2E 或真实执行：停止并建立对应独立协议。

每阶段 checkpoint 必须记录目标、HEAD、输入 hash、实际测试、产物、失败、下一 gate 和恢复命令。

## 13. 协议后的下一步

本协议获批后仍等待明确实施指令。`M-BENCH-PLATFORM-CORE-V1` 完成后，下一协议才可以讨论 17 个 development template family 的语义创作、2 units/cell 的完整 development corpus、人工 rubric 校准或 confirmation 解封。任何后续工作不得在本协议尾部自动启动。
