# FusionAgent 实验账本

> 状态：A1 当前权威实验索引
> 更新日期：2026-09-07
> 当前执行入口：`research-governance-index.md`
> 当前主张状态：`research-claim-evidence-ledger.md`

## 1. 登记规则

2026-09-06 本轮核对新简化实验的 manifest/summary/诊断表和源码身份；旧六组、B 与 C 系列保持原账本边界，未在本轮重跑或重新完成盲评。下文旧“当前事实”指对应已登记批次，不是全项目零调用声明。

每个实验集必须记录方法版本、案例角色、调用与人工评价状态、允许复用范围。preflight、正式运行、人工评价和 E2E 不因目录相邻而自动属于同一证据层。

状态含义：

- `frozen_complete`：运行与完整性审计完成。
- `pending_human_review`：运行完成，人工评价未完成。
- `development_only`：用于设计或修复，不能进入正式确认。
- `bounded_observation`：只支持指定案例事实。
- `negative_result`：预注册机制未出现或主张未获支持。
- `historical_only`：仅用于追溯，不进入当前比较性结论。
- `active_zero_call_design`：只授权零调用协议设计，不授权平台实现或实验运行。
- `frozen_protocol`：协议及人工复核已冻结，但所约束的实现仍需另行明确授权。
- `implementation_validated_offline`：平台实现的离线合同、测试、审计和人工复核闭环已冻结；不代表方法效果、生产能力或正式实验能力。
- `not_authorized`：尚未通过启动闸门，不得实施或调用 Provider。

## 2. RQ3 原六组主实验

| Evidence ID | 方法/案例 | 证据位置 | 状态 | 允许用途 | 禁止用途 |
| --- | --- | --- | --- | --- | --- |
| `E-RQ3-DET-54` | C01-C06 x fixed/rules/KG-only x 3 exact repetitions | `D:\code\fusionagent-evidence\p3-planning-repeated\2026-08-14-deterministic-repeated-v1-audit.json` | `frozen_complete` | deterministic 稳定性和 cell baseline | 把重复行当独立样本 |
| `E-RQ3-LLM-90` | C01-C06 x 3 LLM conditions x 5 repetitions | `D:\code\fusionagent-evidence\p3-planning-repeated\2026-08-15-deepseek-v4-flash-repeated-combined-v1` | `pending_human_review` | 自动描述、结构稳定性、token/latency | 比较性 superiority 或 E2E 能力 |
| `E-RQ3-MANUAL-180` | 90 runs 对应 180 个盲评 item | `D:\code\fusionagent-evidence\p3-planning-repeated\2026-08-15-manual-review-combined-v1` | `pending_human_review` | 完成人工双评和裁决后用于 RQ3 | 当前 null decision 不得解释为 pass/fail |
| `E-RQ3-SIX-DESC` | 六组旧描述表 | `D:\code\fusionagent-evidence\p3-planning-formal\2026-08-13-six-group-descriptive-comparison-v1.json` | `historical_only` | 追溯早期分组和 metric | 最终六组统一比较 |

当前事实：90/90 LLM runs 完成、18 cells 各 5 次、总 token `1,171,179`、72 个自动检查失败；180 个 manual decisions 仍为空。原六组实验尚未闭环。

## 3. 方案 B 接口消融

| Evidence ID | 案例/阶段 | 证据位置 | 状态 | 允许用途 | 禁止用途 |
| --- | --- | --- | --- | --- | --- |
| `E-B-SCREEN` | C01-C06，6 次开发 screen | `D:\code\fusionagent-evidence\p3-planning-method-b\2026-08-15-method-b-screen-v1-real` | `development_only` | 发现接口缺陷 | 正式效果比较 |
| `E-B-H01-H06` | H01-H06，原 54 calls + 18 repair calls | `D:\code\fusionagent-evidence\p3-planning-method-b\2026-08-16-method-b-heldout-formal-v1` 与 `D:\code\fusionagent-evidence\p3-planning-method-b\2026-08-16-method-b-heldout-formal-repair-v1` | `development_only` | post-repair 机制分析 | pristine confirmation、通用 superiority |
| `E-B-H01-H06-HUMAN` | H01-H06，54 个人工 rubric item，双评+裁决 | `D:\code\fusionagent-evidence\p3-planning-method-b\2026-08-17-method-b-manual-adjudication-v1` | `frozen_complete` | 解释 specific interface repair | E2E、跨 AOI、统计推广 |
| `E-B-H07-H09` | H07-H09 x 3 conditions x 3 repetitions，27 calls | `D:\code\fusionagent-evidence\p3-planning-method-b\2026-08-17-method-b-independent-confirmation-v1` | `frozen_complete` | 独立 planning confirmation | 与 H01-H06 混池 |
| `E-B-H07-H09-HUMAN` | H07-H09，63 个 rubric item，双评+裁决 | `D:\code\fusionagent-evidence\p3-planning-method-b\2026-08-18-method-b-independent-confirmation-manual-adjudication-v1` | `frozen_complete` | 报告 B 与 Full KG 均为 `21/21` 的描述性人工结果 | 统计非劣、B 普遍优越或产品质量结论 |

## 4. RQ4 选择性执行与外部有效性

| Evidence ID | 案例 | 证据位置 | 状态 | 最强允许表述 |
| --- | --- | --- | --- | --- |
| `E-RQ4-C02` | Caracas C02 | `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c02-water-road-e2e-r2` | `bounded_observation` | water polygon 成功；waterways 在算法前因未计划 source expansion 和 semantic contract invalid 而 fail closed；road 未运行 |
| `E-RQ4-C04` | Caracas C04 | `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c04-road-e2e-r4` | `bounded_observation` | 两阶段 road artifact 与 supersession 成功；delivery 仍为 degraded；单 AOI |
| `E-RQ4-C06` | Caracas C06 screening | `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c06-failure-screening-r1` | `negative_result` | 候选通过质量门，旧“必然失败”机制退役；未运行正式 recovery |
| `E-RQ4-S6` | C02/C04/C06 统一只读审计 | `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-s6-selective-e2e-audit-v1` | `frozen_complete` | 固定上述三项边界，不支持方法 superiority |
| `E-E5-AOI` | Caracas/Abidjan/越南候选清单 | `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-15-multi-aoi-candidate-inventory-v1` | `negative_result` | Caracas 是相关案例唯一 source-closed AOI；E5 未选例 |

## 5. 历史 evidence 的复用规则

1. 历史 preflight 只证明当时的输入、预算和运行准备，不证明能力。
2. 不完整 v2 LLM repeated batch 继续排除，不与 v3/extension 混池。
3. C01-C06、H01-H06、H07-H09 均已被观察，不能作为新 benchmark 的独立正式确认实例。
4. 旧 C02/C04/C06 E2E 可作为机制和工程风险依据，但不能计入未来新协议的重复样本。
5. 新 template、KG、method、evaluator 或信息边界产生新版本后，必须创建新 evidence root 和新 Evidence ID。

## 6. 已替代的 Benchmark 设计与方法选择路线

本节为历史资产登记，不再定义当前下一动作。原方法选择/模板路线由[工作计划](research-evidence-next-design.md)替代；旧批准和离线测试不等于新实验授权。

### 方法选择（历史设计）

| Planned ID | 目标 | 当前状态 | 选择范围 | 启动闸门 |
| --- | --- | --- | --- | --- |
| `P-METHOD-SELECTION` | 原三条件方法选择路线 | `superseded` | 原候选批准与 P1-P7 离线产物保留 | 不再推进 candidate generation、judge 或冠军筛选 |

该计划不在实验前指定冠军。full-contract 的接口实现必须在 development 阶段冻结；确认阶段不允许根据结果更换接口。选择集结果只能形成探索性选择，独立 confirmation 结果才可支持受限的确认性优势表述。

旧实施顺序见[`method-selection-implementation-plan-v1.md`](method-selection-implementation-plan-v1.md)，仅供历史追溯。旧 2026-09-01 至 2026-09-07 的平台冲刺窗口退役。

### 已冻结设计里程碑

| Evidence ID | 设计包 | 状态 | 审计与调用边界 | 允许用途 | 禁止用途 |
| --- | --- | --- | --- | --- | --- |
| `E-BENCH-DESIGN-V1` | `docs/current/benchmark/v1/`，tag `benchmark-design-freeze-v1` | `frozen_complete` | 机器审计 `16/16`；两轮人工复核最终批准；Provider/judge/实例/正式结果根均为 `0` | 后续平台协议、development 实例和正式协议的版本化设计输入 | 方法效果、正式 gold、平台能力、execution/quality/external-validity 证据 |
| `E-BENCH-PLATFORM-PROTOCOL-V1` | `docs/current/benchmark/platform/v1/` 与 `benchmark-platform-implementation-protocol.md` | `frozen_protocol` | 机器审计 `17/17`；`pluto` 独立复核七项批准；Provider/judge/实例/正式结果根均为 `0` | `M-BENCH-PLATFORM-CORE-V1` 的版本化实现合同与 P0-P7 验收输入 | 平台已实现、实例已生成、方法效果、生产能力、正式实验或 E2E 证据 |
| `E-BENCH-PLATFORM-CORE-V1` | `docs/current/benchmark/platform/v1/implementation/`，tag `benchmark-platform-core-v1` | `implementation_validated_offline` | BP7 机器审计 `11/11`；用户七项人工复核批准；核心合同测试 `64 passed`；Provider/judge/实例/正式结果根均为 `0` | 后续 template authoring/development 协议的版本化实现输入 | 方法效果、生产能力、confirmation、E2E、Provider/judge 或正式实验证据 |

### 原计划状态与替代

| Planned ID | 目标 | 当前状态 | 启动闸门 |
| --- | --- | --- | --- |
| `P-BENCH-DESIGN` | 参数化、分层、可诊断案例与评价体系 | `frozen_complete` | `M-BENCH-DESIGN-FREEZE-V1` 已通过；冻结后语义修改必须升版本 |
| `P-BENCH-PLATFORM` | 参数化实例生成与校验平台最小实现 | `frozen_complete` | core V1 保留为离线基础设施，不继续扩建 |
| `P-BENCH-JUDGE` | 多模型开发 judge 平台 | `retired_not_started` | 不进入当前计划 |
| `P-BENCH-FORMAL` | 原平台驱动的六组实验计划 | `superseded` | 新直接比较另登记；不能把五方法批次改名为原六组完成 |
| `P-BENCH-E2E` | 原平台选例 E2E | `superseded` | 由新计划 E4 的预选 source-closed 案例替代；尚未运行 |

`P-BENCH-DESIGN` 的[执行方案](../archive/plans/benchmark-design-freeze-execution-plan-2026-08-19.md)已终止于对应冻结。当前不再以 template/development P0、N0/N1 或 planning-only Q1 作为下一验收点。

## 7. 新简化实验（与旧六组分开）

| Evidence ID | 批次与设计 | 已记录结果 | 状态与边界 |
| --- | --- | --- | --- |
| `E-SIMPLE-ADV-20260904` | `adversarial-baseline-v1-qwen37-20260904-live-w4`；60 对，120 成员，960 rows，720 真实调用；五方法和三个消融 | Full fault `13/60`、rules `5/60`；去 capability aggregate 下降 `35.8 pp`；去 contract 上升 `1.7 pp` | 探索性；无 exact-input 随机重复；不是所有模块必要性证据 |
| `E-SIMPLE-HELDOUT-20260905` | `heldout-confirmatory-v1-qwen37-20260905-live-w4`；120 对，240 成员，2640 rows；三 LLM 各 3 次，共 2160 次调用 | Full/capability fault primary 各 `4/120`，LLM-only `1/120`，rules/fixed 各 `0/120`；26 schema-invalid | Primary 未确认整体优势；未运行三个 without 条件；actual E2E denominator 为 0 |
| `E-SIMPLE-POSTHOC-20260905` | 同一 held-out 的 `diagnostic_decomposition.json`，不是新增调用 | semantic：Full `38/120`，LLM-only/capability 各 `13/120`，rules/fixed 各 `3/120` | Post-hoc；不检查 source/algorithm grounding，不是 semantic_delivery_v2 或产品契约满足 |

实际根目录均为 `D:\code\FusionAgent\runs\experiments\`。已核对的原始依据为各批次 `manifest.json`、`summary.json` 和 held-out 的 `diagnostic_decomposition.md`、`confirmatory_statistics.json`，adversarial 的 `kg_ablation.md`。本轮没有重跑 Provider 或重写这些文件，也未完成全部 raw rows 的独立复算。

Held-out case file 为 `D:\code\FusionAgent\experiments\heldout_confirmatory_v1\cases.json`，manifest 声明 SHA-256 为 `ae5be68c3d0027c6ff5f0e4ebb0fdd2e0831eaac18cb1f2f75afc0706d06b801`。旧数据已被查看，不再用于新独立确认。

### 实现与解释风险

- Held-out manifest 的 `source_state.git_dirty=true`；runner hash 为 `6519f767402faf9c190169a2be3b5c3d24261d68f16ba278ac4d92836a7d7248`，本轮当前文件实算为 `c0c7ad366d9aafa7ae12ab41b9174fec9dbe5835b1143c729d2a574077795a9e`，二者不同。
- Provider 文件当前 hash 与 manifest 一致，为 `831a8ba61b2a8be141e5961bf20d0aa4ea47988fdaa9ef9b6038c61b05611a9f`。单文件相同不证明整个运行实现已复原。
- 当前 runner 的固定优先级投影、规则基线能力范围和 oracle 关系需在 N0 核对历史输入；不能将当前代码直接归因为旧性能原因。
- manifest `claim_eligible=true`、summary 顶层 `end_to_end_completion_rate` 不能升级结论；真实执行以 `outcome_metrics.actual_e2e_*` 的 `0/0`、`not_executed` 为准。
- 旧 semantic 与新拟定 semantic_delivery_v2 分开版本、分开结果。确认集名叫 held-out 不自动消除开发共享规则、信息不等量或代码身份风险。

## 8. 当前工作登记

2026-09-07 用户确认继续 KG+LLM 主线，优先验证灾害应急矢量融合的真实闭环，不把冻结/复核作为前置。当前推进 `P-RESEARCH-R1-R4`；旧 Q1、N0/N1 和 E1-E5 保留为历史或长期候选，不定义当前执行顺序。

| Planned ID | 对应计划 | 状态 | 进入条件 |
| --- | --- | --- | --- |
| `P-RESEARCH-Q1` | 24 输入、4 LLM 条件的一轮 planning-only 比较 | `superseded` | 保留历史设计，不追加同类调用 |
| `P-RESEARCH-R1-R4` | Caracas 真实资产上的闭环比较、协作机制和知识消融 | `in_progress` | R1 核对完成，R2 trace 实现中；R3 五方法运行尚未开始 |
| `P-RESEARCH-N0` | 原全量证据/语义核查 | `superseded` | 不作为前置；必要问题在真实闭环运行中直接检查 |
| `P-RESEARCH-N1` | 原独立修正与联合冻结阶段 | `superseded` | 不作为前置；不预先优化被比较的方法 |
| `P-RESEARCH-E1` | 新指标独立确认 | `deferred` | 在真实闭环指标和结果语义明确后再设计 |
| `P-RESEARCH-E2` | 三模块与同信息机制对照 | `deferred` | 由 R4 的实际增益问题决定具体消融 |
| `P-RESEARCH-E3` | 安全拒绝/恢复/正确终态 | `deferred` | 由真实下载和质量失败机会决定 |
| `P-RESEARCH-E4` | 选择性真实 GIS E2E | `deferred` | 已并入 R1-R3，不再作为独立前置阶段 |
| `P-RESEARCH-E5` | 产品质量与独立复核 | `deferred` | 在首轮方法差异成立后再扩展 |

E1-E5 保留为长期候选而非近期任务。当前数据路径、闭环阶段、比较组、协作机制、指标和退出条件见[下一步工作计划](research-evidence-next-design.md)。`P-RESEARCH-R1-R4` 不是已运行 Evidence ID，尚无新闭环结果。

### R1/R2 实施证据（2026-09-07）

| Evidence ID | 证据 | 状态与边界 |
| --- | --- | --- |
| `E-R1-CARACAS-INPUT-20260907` | `D:\code\FusionAgent\runs\research\r2-caracas-input-audit-20260907\input_audit.json`；[入口与数据核对](evidence/r1-real-closed-loop-data-audit-20260907.md) | 输入核对；不是新融合运行。HydroLAKES bbox=1、严格 AOI=0 |
| `E-R2-CONTROL-FLOW-20260907` | `services/agent_run_service.py:execute_run`、`services/run_writeback_service.py`；trace 修改与聚焦测试 | 源码事实：首次规划早于材料化、质量 writeback 在执行 replan 循环外。尚未完成下载/质量反馈闭环或五方法接入，不是 superiority 证据 |

此次继续执行未调用 Provider，未重新下载外部来源，未执行新的 GIS 融合。测试与源码检查不计入 R3 样本。

验证记录（源码工作树 `D:\code\FusionAgent`）：

- `.venv/Scripts/python.exe -m pytest tests/test_workflow_trace_service.py tests/test_report_quality_service.py -q`：17 passed。
- 加入 `tests/test_run_report_service.py` 直接收集失败：`runtime_contract_service -> agent.__init__ -> executor -> runtime_contract_service` 循环导入；不是运行报告测试通过。
- `.venv/Scripts/python.exe -c "import agent; import pytest; raise SystemExit(pytest.main(['tests/test_workflow_trace_service.py', 'tests/test_report_quality_service.py', 'tests/test_run_report_service.py', '-q']))"`：23 passed。此命令以导入顺序绕过收集问题，未修复循环依赖。
- `git diff --check`：通过，仅有 CRLF 转换提示。

### R2b 质量反馈实现（2026-09-07 后续）

`E-R2-QUALITY-FEEDBACK-20260907`：修改 `agent/planner.py`、`services/agent_run_service.py`、`services/run_writeback_service.py`；质量拒绝可进入有界重规划，保存每个失败 revision 的报告和矢量 sidecars。一般 writeback 错误不触发融合重规划；重规划不产生新版本则失败，不用旧计划冒充恢复成功。

新增测试使用 mock planner/executor/quality evaluator 和本地最小矢量 fixture，覆盖通过、持续拒绝、版本不变、存储错误，以及 output/intermediate 两种产物位置；另用 capturing provider 检查质量报告进入规划上下文。不是 live LLM、真实下载或 Caracas GIS 融合，不计入 R3 分母。

最终修改后验证：`.venv/Scripts/python.exe -m pytest tests/test_agent_run_service_enhancements.py tests/test_agent_run_service_runtime_refresh.py tests/test_workflow_trace_service.py tests/test_planner_context.py -q --disable-warnings`，121 passed、114 warnings、26.36 秒；警告包括 Shapefile 字段名截断。`git diff --check` 通过，仅 CRLF 提示。未执行全仓库测试。

### R2a 下载后规划实现（2026-09-07 后续）

`E-R2-POST-ACQUISITION-20260907`：新增显式请求开关 `plan_after_acquisition`、planner 下载后规划方法和服务阶段；保存观测与候选，拒绝无新版本及材料化 source/type 不匹配。默认行为未切换；启用时禁用 artifact reuse，保留质量所需的覆盖与来源语义。新方法只在材料化返回实际观测后调用，全部失败时尚无方法特有的下载恢复循环。

同上述四个测试文件命令：127 passed、117 warnings、27.15 秒。新增正常事件顺序、真实 planner 上下文构造、未生成新版本、换源、换类型和 validator 换源测试。材料化、Provider、执行和质量相关输入为 mock/fixture；没有新增真实 Provider 调用、互联网下载或 Caracas 融合，不进入 R3 分母。五方法公平性与 deadline/network 尚未验证。

### Caracas 真实道路运行（2026-09-07）

`E-R2-CARACAS-ROAD-SMOKE-20260907`：使用 `scripts/run_caracas_closed_loop_smoke.py`，证据根为 `D:\code\FusionAgent\runs\research\caracas-road-kg-runtime-smoke-20260907-r{1,2,3}`。三次运行分别保留，不合并或覆盖：

| 批次 | 实际结果 | 边界 |
| --- | --- | --- |
| r1 | 脚本 provider 接口缺少 provider_name，规划前失败 | 脚本错误，无融合 |
| r2 | 真实材料化完成；下载后候选为 upload.bundle，与 catalog.flood.road 不一致，被拒绝 | 未融合；随后修正确定性 smoke 选择器，使下载后从 KG 候选中选同 source/type 的模式 |
| r3 | 实际融合、质量审查、自动修复、再次审查和恢复规划均执行；最终 failed，无发布 artifact | run_id=`7b26936ae46349969abb9e92394e9dc6`，服务调用耗时 104.0787 秒（不含提前源文件复制准备） |

r3 使用真实 OSM/Microsoft 道路缓存，memory KG pinned snapshot、eager、单 worker；使用确定性 KG 候选选择器，不调用真实 LLM，也不是 formal KG-only 求解器基线。默认 mock 设置仅用于服务初始化，执行通过 RuntimeDependencies 显式注入确定性选择器；不可把 settings 的 mock 标签或 planner 中的通用 LLM 方法名当成真实模型调用。未执行互联网下载、自然语言灾种/AOI 抽取评测、deadline 或网络扰动。

真实 GPKG 经 pyogrio 独立读取：23,760 条 LineString，EPSG:32619。`output/quality_report.json` 记录 accepted=false；invalid_geometry_rate=0、duplicate_geometry_rate=0、zero_length_geometry_count=0，dangle_endpoint_rate_per_100km=637.028929，高于 hard 阈值 500。另有 feature_retention_rate/coverage_retention_rate 的 null 软检查，不能解释为实际保留率为零。修复后仍未达标，触发 revision 3；恢复选择器返回无法供 task-driven 材料化的来源，终态为 `task-driven input strategy could not resolve a source_id from the plan`。

失败矢量和质量报告保存在该 run 的 `quality-failures/revision-2/`，当前 output 中有 `road_large_area_fused.repair-1.gpkg`。这证明真实质量反馈路径已被触发，不证明恢复成功、可用成果交付或 KG+LLM 优势。三个命令均非零退出；r3 的非零退出是已保留的研究工程失败观察，不是执行工具未启动。

真实 LLM 启动条件：本轮检查当前项目环境变量和 RuntimeSettingsService，仅输出存在性，key/model/base URL 均未配置。未检索其他项目密钥，也未打印任何凭据。真实模型组仍需本地恢复配置。

配置核对更正（用户提醒后，2026-09-07）：上述“未配置”仅反映未加载 dotenv 的进程，不代表本地配置缺失。项目根 `.env` 已包含非空 Provider、GEOFUSION_LLM_API_KEY、GEOFUSION_LLM_MODEL、GEOFUSION_LLM_BASE_URL。原因是 `apply_runtime_entrypoint_defaults()` 只调用 `apply_local_dependency_defaults()`，不会加载 `.env`。使用现有 `read_dotenv_defaults()` 向独立进程注入缺失环境变量后，RuntimeSettingsService 能读取配置，OpenAICompatibleProvider 初始化成功；没有进行 API 调用，连通性/凭据有效性仍待实际调用验证。全程仅输出存在性，不记录密钥和完整地址。后续真实运行显式加载 dotenv，不再要求用户重新配置。

### 首次真实 LLM 道路闭环（2026-09-07）

`E-R3-LIVE-ROAD-SMOKE-20260907`：命令为 `.venv/Scripts/python.exe scripts/run_caracas_closed_loop_smoke.py --planner live --output runs/research/caracas-road-live-smoke-20260907-rN`。各运行独立目录、各自最多 3 次调用；开发修复后重启不是同输入重复试验，禁止混池。原始 prompt/context/响应/usage 位于 `provider-calls/`。显式加载 dotenv，注入真实 Provider，禁止把 KG fallback/override 当作模型成功；设置快照不写入密钥。

| 运行 | 实际结果 |
| --- | --- |
| r1 | 1 次 HTTP 200、strict JSON；返回嵌套 workflow_plan，不符合 WorkflowPlan schema，禁止 fallback 后终止。29,942 tokens。确认公共调用未提供输出 schema，随后加入实际模型 schema，不修改 gold 或放宽 validator |
| r2 | 1 次真实计划通过，材料化完成；run.json 原子替换遇到 WinError 5，中断。随后仅对 Windows 5/32/33 的替换增加最多 4 次、有界等待的重试；其他权限错误不重试，持续失败仍报告 |
| r3 | run_id=`ac4514624c82472f8d95f5cad0d05cca`；3 次真实调用，响应模型 qwen3.7-flash、HTTP 200、strict_json、finish_reason=stop；初步计划、下载后计划、质量反馈重规划均执行。两次真实融合后仍未达标，达到总 revision=3 上限，终态 failed、artifact=null |

r3 服务调用耗时 245.5115 秒，不含输入缓存复制准备。三个调用分别消耗 35,893 / 74,925 / 123,566 tokens，总计 234,384。道路融合 revision 2/3 均为 23,760 条，质量拒绝原因为 dangle_endpoint_rate_per_100km=637.028929，大于阈值 500。两版计划的算法均为 algo.fusion.road.conflation.v7，来源均为 catalog.flood.road，参数相同，因此未观察到有效恢复增益。产物和报告按 quality-failures/revision-2、revision-3 保留。

本次真实 LLM、真实缓存材料化、实际 GIS 执行和质量反馈均已运行；不是互联网下载/网络扰动，灾种和 bbox 由请求显式提供，非自由文本解析能力测试；也不是五方法比较或已完成 R3 全部任务。可支持“真实闭环执行并安全拒绝不合格产物”的受限观察，不支持恢复成功、截止时间交付或方法 superiority。

验证：输出 schema 修改后的四文件回归 128 passed；Windows 原子写入重试专项 3 passed；git diff --check 通过。此前 1 个 context-key 测试因新增 output_schema 需同步预期，修正后 planner 测试 25 passed。没有执行全仓库测试。

### 真实失败诊断及恢复成本修正（2026-09-07）

`E-R3-ROAD-DIAGNOSTIC-20260907`：`D:\code\FusionAgent\runs\research\caracas-road-diagnostic-20260907-r1.json`，由 `scripts/diagnose_caracas_road_smoke.py` 读取真实源数据、r3 产物和历史请求生成，无新 Provider 调用，不修改旧报告或 gate。

| 数据（统一 EPSG:32619） | 悬挂端点计数 | 每 100 km 计数 |
| --- | ---: | ---: |
| 原始 OSM | 14,968 | 595.1582 |
| 原始 Microsoft | 3,276 | 208.1368 |
| 融合产物 | 16,775 | 637.0289 |

stored 与 request_bbox_clipped 的指标几乎一致，故本次请求 bbox 裁剪不是该差异的解释；不排除数据上游行政裁剪的影响。当前算法只统计唯一端点坐标，不判断端点是否连在线段内部。同一 T 形几何连接在未分段/分段表示下得到 4/3 个“悬挂端点”，证明当前 proxy 对分段敏感；不能直接解释为真实网络断连率。融合指标高于 OSM 是按当前 proxy 的观察，不是已经证明融合损害真实通行能力。阈值 500 保持不变。

历史调用 2/3 的请求经动作快照投影，JSON 序列化字节分别由 243,503 降至 111,717（54.12%）、401,489 降至 117,880（70.64%）。这是离线字节测量，不是新调用 token、费用或时延实测。

实现：`planning_action_snapshot` 仅向后续规划保留历史任务、输入参数、触发信息、版本及必要运行事实；上一轮 retrieval、telemetry、raw response 不再递归进入模型，完整证据保留在磁盘。质量恢复若可执行算法/输入参数/来源/依赖/备选算法均未改变，候选写入 `rejected-quality-replan-N.json` 后停止，不再仅因版本增加而重复融合；有实际动作变化的恢复仍可执行。

最终回归：`.venv/Scripts/python.exe -m pytest tests/test_planner_context.py tests/test_agent_run_service_enhancements.py tests/test_agent_run_service_runtime_refresh.py tests/test_workflow_trace_service.py tests/test_run_state_store_atomic_retry.py -q --disable-warnings`，134 passed、123 warnings、29.12 秒。未重新运行 LLM 或融合；不得将新停止条件回填到旧 r3 作为节省时间或恢复成功。

### 五方法真实首案探索（2026-09-07）

`E-R3-FIVE-METHOD-SCREEN-20260907`：命令 `.venv/Scripts/python.exe scripts/run_caracas_five_method_screen.py --output runs/research/caracas-five-method-screen-20260907-r1`。证据根 `D:\code\FusionAgent\runs\research\caracas-five-method-screen-20260907-r1`；汇总为 `comparison.json`，各方法保留独立日志、summary、trace、计划和失败产物，真实模型另保留 `provider-calls/` 原始请求/响应/usage。源码 HEAD=`f47fbef94969cc178c66684fbabc2acf437a5986`，含未提交修改，不代表干净版本；各组 `smoke_metadata.json` 记录部分执行源码哈希及 manifest 哈希，不是完整环境快照。

五组串行运行，同一 Caracas OSM/Microsoft 真实道路缓存、bbox 和共享执行器/质量门，总计划版本最多 3；两个模型组使用本地配置 qwen3.7-flash、temperature=0.1、最多 3 次调用，禁止隐藏 fallback。计时不含源文件预复制。各组仅一次，无独立重复，无 deadline/网络扰动、互联网下载或开放式灾种/区域解析。

| 方法 | 秒 | 真实调用 | tokens | 道路数 | 质量/发布 |
| --- | ---: | ---: | ---: | ---: | --- |
| fixed | 101.1048 | 0 | 0 | 23,760 | 拒绝/未发布 |
| rules | 106.0529 | 0 | 0 | 23,760 | 拒绝/未发布 |
| KG 首候选 | 100.9144 | 0 | 0 | 23,760 | 拒绝/未发布 |
| LLM-only | 36.7482 | 1 | 11,855 | 未执行 | 计划被拒绝/未发布 |
| KG+LLM（live） | 178.9356 | 3 | 114,771 | 23,760 | 拒绝/未发布 |

四个已融合方法的 dangle_endpoint_rate_per_100km 均为 637.0289291208259。质量修复后仍拒绝，候选恢复动作不变，被新机制拦截，未重复融合；该停止是避免无效执行，不是恢复成功。KG+LLM run_id=`79b42a079b98461d900976ac25cd0c0c`，未观察到更高质量或达标交付。与旧 live r3 相比 tokens/时间数值较低，但代码、提示和执行次数均已变化，单次开发运行不能隔离上下文压缩的因果效果。

**基线审查发现与结论边界：**

- LLM-only run_id=`991df75f7bd24f008493c48450f378d9`，`validation.json` 两条 MISSING_RUNTIME_STATUS 均指向 `algo.transform.raw_to_road_bundle`。公共投影只排除显式 selectable_now=false，缺失值默认保留，并剥离 runtime_status；运行契约则拒绝缺少该字段的算法。模型面对不充分的可执行性说明，不能把这一执行前失败算作 KG 的可靠性优势。尚未修正或补跑。
- fixed/rules 是公共类型匹配及简单来源排序，KG 是首候选选择器，均不是正式强基线。LLM-only 未见 KG 模式/策略/排名，但参数绑定、validator 和执行器仍使用公共 KG 能力；这是规划信息对照，不是全系统无 KG 消融。
- 当前单道路大区域路径由输入类型路由到同一 v7 执行器；还需验证未来候选算法/参数确实改变执行动作。此次四组相同数量和 proxy 不等价于已证明所有矢量几何逐条相同。
- 旧端点 proxy 的分段敏感性继续成立。不得将本次质量拒绝直接表述为真实灾害路网不可用，或以修改阈值让任何组获胜。无可用成果发布，也没有证据支持 KG+LLM superiority。

当前状态：完成一个探索性首案比较和公共接口缺口定位，不是完成 R3 正式矩阵。下一步按计划顶部摘要修正公共工具可用性、补共同评价，再引入真正可执行的应急动作与受扰条件。失败全部保留。

批次后聚焦回归：`.venv/Scripts/python.exe -m pytest tests/test_closed_loop_baseline_context.py tests/test_planner_context.py tests/test_agent_run_service_enhancements.py tests/test_agent_run_service_runtime_refresh.py tests/test_workflow_trace_service.py tests/test_run_state_store_atomic_retry.py -q --disable-warnings`，135 passed、123 warnings、29.49 秒；源码树和本次三个权威文档的 `git diff --check` 通过（存在 CRLF 提示）。测试仅覆盖现有投影/运行机制，不证明公共工具缺口已修复或方法优越。

公共工具投影修正后的独立批次 `E-R3-FIVE-METHOD-SCREEN-R2-20260907`：fixed/rules/KG 均融合 23,760 条道路、proxy=637.028929、质量拒绝且未发布；KG+LLM（run_id=`9dc93e0136324cac8a6b5c232b1985b4`）真实调用 3 次、118,900 tokens、189.39 秒，同样质量拒绝且未发布。单 LLM（run_id=`b92fcae65d334b04a5f99d5421e81a70`）已越过 `MISSING_RUNTIME_STATUS`，但被 smoke 适配器以 `Live smoke rejects non-LLM fallback or override` 停止，未进入融合。该失败不能作为 KG 胜出证据；r1/r2 均不与正式重复实验混池。

## 2026-09-08 设计更新（非运行证据）

用户要求按优越性主线更新设计并提交、推送已有变更。本次未新增 Provider 调用、融合产物或统计结果，不分配运行 Evidence ID。

`P-RESEARCH-R1-R4` 继续；下一点为公共接口、共同质量评价和恢复动作验证，然后 4 条件 x 5 方法 = 20 次开发筛查。正常、多图层紧迫时限、主源延迟/中断、首次质量失败各条件各方法一次。五组使用 fixed、合理 rules、完整接口 LLM-only、同知识确定性 KG-only、KG+LLM；窄规则和首候选 smoke 不充当正式强基线。

具体可行案例、共享动作、预算、deadline 和分母在执行前记录。开发筛查不支持显著性；未调试 AOI/组合/轨迹用于独立确认，历史开发运行不混池。机制与知识消融见当前计划，原 r1/r2、held-out 和失败记录保持原样。

## 9. 更新规则

- 只在实验终态或闸门状态变化时更新本账本。
- 原始结果数字来自冻结 JSON，不手工重算后覆盖历史值。
- 新实验必须先分配 Evidence ID；运行后绑定 branch、commit、protocol hash、case/template version 和 evidence root。
- 任何失败、未执行尾部、人工分歧和负结果都保留。
