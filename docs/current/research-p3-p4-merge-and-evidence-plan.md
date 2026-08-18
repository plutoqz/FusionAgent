# P3-P/P4-P 研究归并与证据冻结计划

状态：历史实施计划与 append-only checkpoint 日志；不再是当前实施入口。

继承说明（2026-08-18）：本文保留 P3-P/P4-P 的协议演进、失败和执行记录，不删除或回写历史“下一步”。当前研究阶段与唯一下一验收点见 `research-governance-index.md`；实验角色和主张状态分别见 `research-experiment-ledger.md` 与 `research-claim-evidence-ledger.md`。不得从本文最后一个 checkpoint 自动恢复实验或启动调用。

## 1. 研究边界

本轮工作的目标是在当前冻结的 KG v1 上，建立可审计的六组规划对照，并用有限的真实端到端案例验证规划差异是否改变执行结果。

六组固定为：

```text
fixed workflow
rules-only
KG-only
LLM-only
LLM + capability KG
LLM + full contract KG
```

planning-only 覆盖 C01-C06。C03 是 unsupported wildfire 的独立负向安全层，不纳入正向计划质量平均值。选择性端到端覆盖 C02、C04、C06，六组使用同一执行器；C01、C05 暂只进入 planning-only。

当前 KG v1 不原地修改。source、algorithm、contract、quality policy 和 disaster vocabulary 必须通过显式 crosswalk 对齐；不能在 runner 中用 alias、默认值或第二份 Python 知识表掩盖缺失。

## 2. 不可改变的实验语义

### 2.1 共同执行边界

六组共享请求接收、计划 schema validator、source materialization、预处理、融合、质量门、artifact writeback 和证据登记。规划组只决定 source、algorithm、task order、delivery mode、gap 和 supersession/recovery proposal。

validator 只报告失败，不修复计划。LLM 调用、schema、grounding 或契约失败不得由 deterministic/KG fallback 改写为成功。

### 2.2 知识投影

从同一 canonical context 生成六个白名单投影，并记录字段清单和 hash：

| 组别 | 允许知识 |
|---|---|
| fixed | 非决策运行参数；固定跨案例 DAG 和策略 |
| rules-only | 可观察请求/资源/source 状态；冻结通用规则；不查询 KG |
| KG-only | 可观察事实加完整 KG v1；通用确定性求解器 |
| LLM-only | 请求、资源状态、最小运行接口目录和输出 schema；不注入 KG |
| LLM + capability KG | LLM-only 加 source/algorithm/task capability 子图 |
| LLM + full contract KG | capability 子图加情景、契约、质量、降级、gap、证据知识 |

公共 LLM prompt 只描述输出语法和类型规则，不包含优先级、降级或 gap 决策建议。

## 3. 归并顺序

### P3-P0：案例和 KG crosswalk

1. 将 C01-C06 重写为版本化 case manifest。
2. C04 规范为 typhoon road 渐进交付。
3. C05 使用 `raw.osm.building` 和 `raw.microsoft.building`。
4. C06 使用 `raw.osm.road` 和 `raw.microsoft.road`，区分首次双源质量失败与后续单源 provisional。
5. C03 标记为 negative-control，不参与普通平均值。
6. 为每个案例登记 scenario、task、source、algorithm、contract、quality policy、运行范围和 gold rubric。

验收：所有正向案例的 KG ID 可由当前 release loader 解析；不闭合对象必须标为 fixture-only 或阻止进入 formal。

### P3-P1：canonical context 和六组投影器

新增实验上下文工厂，输入当前 `KGRepository`、`KnowledgePolicyRegistry` 和 canonical case observation，输出：

- canonical context；
- KG release identity；
- source/algorithm/contract crosswalk；
- 六组可见字段白名单；
- 每组 context hash；
- 缺失知识和 fail-closed 状态。

禁止从 case 动态创造 `contract.<case_id>`、能力目录或质量策略。

验收：改变 KG 测试副本的实体或关系能够改变 KG-only/full-contract 投影或计划；删除必要关系必须 fail closed；rules-only 不触发 KG repository。

### P3-P2：确定性基线

- fixed workflow：固定任务 DAG，不读取灾种、资源、KG 或质量结果；只允许公共运行重试。
- rules-only：独立通用规则表，不能出现 case ID/AOI 特判或复制 KG 实体属性。
- KG-only：运行时图查询加通用确定性求解器；记录 query、命中实体、排序依据和 release hash。

验收：三组可以在同一输入上产生可解释差异；KG-only 行为扰动不需要修改 runner；rules-only 运行不读取 KG。

### P3-P3：真实 LLM telemetry 和 pilot

先扩展 provider 为 attempt-level call trace，至少记录：

- 脱敏请求、原始响应、HTTP status、request ID、finish reason；
- provider/model/base-url host、开始/结束时间、latency；
- prompt/context/schema hash；
- prompt/completion/cached/reasoning token；
- transport retry、semantic repair 和失败分类。

严格 JSON 解析失败必须保留原文；正则 salvage 只能作为诊断，不能成为首轮成功。

pilot 使用 C02、C03、C06，三种 LLM 知识条件各两次真实调用，共 18 个主调用。pilot 只验证隔离、证据完整性、模型稳定性、失败不 fallback 和预算估计，不据此宣称性能优越。

验收：每次尝试都有原始证据和 hash；三种 LLM 组使用相同模型、provider、prompt 骨架、schema、参数和重试规则；`planning_source=llm` 可追踪；任何失败均保留为失败观察。

### P3-P4：planning-only 正式运行

在 pilot 通过后才冻结：

- provider 和不可变 model ID；
- temperature、output token 上限和 response format；
- transport retry 与 semantic repair 次数；
- canonical input、input variant、replicate 的独立定义；
- repetition、预算上限和 block 中止规则；
- 正式协议 hash 和 schedule seed。

建议将 input variant 与 replicate 分离。不能用一次 variant 代表一次 repetition，否则无法区分输入顺序敏感性和模型随机性。

主要指标：首轮计划有效率、grounding、契约满足率、禁止行为率、gap F1、稳定性、latency、token、费用。C03 单独报告拒绝正确率、错误接受率和错误执行率。

### P4-P1：选择性端到端

只运行 C02、C04、C06，六组共享同一执行器和冻结输入。

- C02：初始规划，观察 priority、semantic mismatch、gap 是否改变实际交付。
- C04：初始规划和 source 到达后的统一 replan，观察 provisional/supersession。
- C06：初始规划和质量门失败后的统一 replan，观察 quality_failed、单源 provisional 和恢复。

端到端使用预先指定的 e2e repetition，不从多次 LLM 结果中事后挑选最佳计划。正确结果可以是拒绝、部分交付、degraded、gap、provisional、supersession 或人工介入。

必须分别记录 `selected -> resolved -> executed -> evaluated`，并保留首次质量门 raw/adapted 结果。

## 4. 单源质量 pilot 闸门

KG v1 的 `quality.external_degradation.v1` 只作为外部 source 缺失下的质量适配，不等于完整单源产品契约。

正式 C06 前至少验证：

1. 外部 source 不可用时允许 provisional/degraded，且保留 raw failure；
2. 系统故障、人工移除 source 或 intrinsic geometry failure 不得伪装为 external degradation；
3. 适配通过不得标记为 fully satisfied；
4. 被软化的检查、原始阈值、gap 和 supersession 要求均有证据。

如果研究目标需要“主动排除低质量 source”或“单源最终满足完整契约”，必须发布新 KG 版本，不能修改 v1 或恢复 Python policy 表。

## 5. 证据目录和冻结规则

旧 P1/P2/P3-G/P4-G 证据不覆盖、不改名。新增证据使用独立命名空间：

```text
docs/current/evidence/p3-planning-pilot/
docs/current/evidence/p3-planning-formal/
docs/current/evidence/p4-planning-e2e/
```

每个 batch 至少保存：

```text
batch_metadata.json
protocol_snapshot.json
case_manifest_snapshot.json
kg_identity.json
implementation_manifest.json
schedule.json
audit_ledger.jsonl
stability_summary.json
audit_manifest.json
runs/<run_id>/...
```

formal batch 要求 clean worktree、commit、KG release hash、协议 hash、实现 manifest hash 和可验证的前向 hash chain。中断运行不得插补；resume 只能在协议、代码和实现 manifest 未变化时继续。

## 6. 停工条件

遇到以下任一情况，停止 formal，不用结果补救实现：

- KG crosswalk 未闭合；
- 六组可见信息或 rules/KG 边界无法自动测试；
- LLM 原始响应、token、latency 或模型身份缺失；
- provider alias 在 batch 中漂移；
- LLM 失败被 fallback、repair 或静默 salvage 掩盖；
- C06 的降级触发原因无法区分 external source failure 与人工 source removal；
- selected/resolved/executed/evaluated 链断裂；
- 端到端首轮质量报告缺失。

## 7. 最终冻结顺序

```text
case manifest/crosswalk
-> canonical context/projection tests
-> deterministic baseline tests
-> provider telemetry tests
-> 18-call real LLM pilot
-> model/repetition/budget freeze
-> planning-only formal
-> selected end-to-end
-> evidence freeze and paper tables
```

在最后一个 evidence freeze 完成前，只能使用“在所测案例和冻结环境下观察到”的限定表述，不能写成普遍性能或生产能力结论。

## 8. 当前实施进度（2026-08-13）

- P3-P0：已形成 `research-case-manifest-v1.json`，并增加 Pydantic schema、案例分区和 negative-control 自动校验。
- P3-P1：已实现 canonical context、六组字段白名单投影、稳定输入 hash，以及 fixed/rules-only/KG-only 的最小确定性决策器。
- P3-P2：已完成投影级隔离测试，并为 C01-C06 实现声明式 planning rubric 与通用 evaluator v1。自动评分覆盖前置有效性、decision、grounding、任务集合、gap、顺序、precedence 和 delivery state；文本语义与端到端事实保留为 pending 人工审查，不使用关键词判定。
- P3-P3：provider 已记录 attempt-level 原始响应、模型、request ID、HTTP 状态、token、延迟、hash、parse mode 和失败类别；pilot 路径强制 strict JSON，禁止 regex salvage 和 fallback。
- 18-call pilot：离线 preflight 位于 `docs/current/evidence/p3-planning-pilot/2026-08-07-preflight-v2/`；DeepSeek 官方 API 的真实批次位于 `D:\code\fusionagent-evidence\p3-planning-pilot\2026-08-13-deepseek-official-v4-flash-r1`。18 次均为 HTTP 200 且响应模型为 `deepseek-v4-flash`，16 次 strict JSON/schema 成功，2 次 C06 知识增强调用以 `finish_reason=length` 失败，总消耗 222,980 tokens；失败未被补跑或 fallback 替换。
- pilot 审计：全部 source/algorithm 引用均可在各自输入中 grounding，但 18/18 输入暴露 `expected_consequence`，部分案例还暴露 `unsupported_terms`、`quality_policy_id` 或 `semantic_guard`。这些评测/策略字段必须从 formal planner observation 中移除，并只保留在独立 gold rubric 中。
- v3 隔离修复：case manifest 已升为 `1.1.0-draft`，运行时 `observations` 与 `gold_rubric` 使用互斥的 `extra=forbid` schema，六组 projection 不接收 gold；`prepare_pilot` 对六个禁止字段 fail closed。离线证据位于 `docs/current/evidence/p3-planning-pilot/2026-08-13-preflight-v3-no-gold-leak/`，审计结果为 18 个输入、9 个唯一 hash、泄漏 0，且 18/18 input hash 相对 v2 改变。
- evaluator 回放：旧 18-call 真实 pilot 已写入外部证据目录的 `pilot_scoring_replay.json`，保留 16 个有效计划和 2 个原始失败。报告强制标记 `diagnostic_only=true`、`input_leakage=true`、`claim_eligible=false`；18/18 泄漏输入的任何分数只用于检查 evaluator 行为，不能作为性能证据。
- formal readiness：当前仍为 `false`。v3 C06 真实压力小 pilot 已完成，但 C06 输入与 gold 的决策时点不闭合，rubric/evaluator 协议与 hash 也尚未冻结；`max_tokens=16384` 和至少 600,000-token 的同规模批次预算仍是候选参数。不得直接进入 planning-only formal。
- v3 C06 真实小 pilot：提交 `d15ed71` 上按 `C06 × 三种 LLM knowledge condition × replicate 1` 执行 3 次 DeepSeek 官方 `deepseek-v4-flash` 调用。3/3 HTTP 200、模型一致、`finish_reason=stop`、strict JSON/schema 成功，消耗 32,072 tokens，泄漏 0，零 retry/repair/salvage/fallback。`16384` output 上限只通过本次压力小样本，尚未冻结。
- 新 formal blocker：C06 planner observations 未暴露首次质量失败，但 gold 要求恢复后的 provisional/degraded/gap；两种 KG 增强条件据可见双源能力输出 `plan/planned`，仅 llm-only 输出 `degraded`。这是输入与评分时点不闭合，不得通过 prompt 提示、放宽 rubric 或补跑掩盖。下一步先冻结 C06 是“失败前规划”还是“失败后恢复规划”，再决定 observation schema、gold 和是否重跑真实小 pilot。
- C06 阶段语义冻结：P3 planning-only 使用质量门拒绝后的 `recovery_replan` 快照；P4 end-to-end 保留 `initial_planning -> quality_gate_failure -> recovery_replan -> provisional_delivery`。`observed_failure` 只包含已发生的 failure category、quality gate 状态、recoverable 和当时 source 分类；首次失败时 OSM/Microsoft 均 available，不预写后续 Microsoft external-uncontrollable 缺失。external degradation、raw failure 保留和 recovery trace 继续由端到端证据人工审查。
- v4 preflight：manifest `1.2.0-draft`、input variant `canonical_v2`，证据位于 `docs/current/evidence/p3-planning-pilot/2026-08-13-preflight-v4-c06-recovery-replan/`。18 个输入泄漏 0、9 个唯一 hash；相对 v3 恰好 6 个 C06 输入 hash 改变，其他案例不变。`max_tokens=16384` 下保守 18-call 上界为 549,050，候选 600,000 预算可覆盖。下一闸门是提交后执行 v4 C06 三条件真实小 pilot，仍不直接进入 formal。
- v4 真实诊断：提交 `7c29fa3` 上的 C06 三条件调用 3/3 HTTP 200、strict JSON/schema、泄漏 0，共 35,578 tokens；三次自动分均为 0.75。共同问题是 `delivery_state=planned` 被理解为 workflow lifecycle，full-contract 另输出内部 `transform` task。该结果暴露公共输出契约歧义，不支持放宽 C06 gold。
- v5 公共 schema：`task_kind` 仅允许 building/road/water_polygon/waterways/poi，禁止内部 transform/validation/workflow step；decision 与 delivery state 明确为计划执行后的预期产品交付姿态，`plan/planned` 只表示预期不受限交付。input variant 为 `canonical_v3`。离线证据位于 `docs/current/evidence/p3-planning-pilot/2026-08-13-preflight-v5-product-delivery-schema/`：泄漏 0、18/18 hash 相对 v4 改变，16384 output 下保守上界 554,576。下一次 C06 真实小 pilot 是本轮协议诊断的最后一次；若仍不通过，不再连续修改协议追分。
- v5 真实闸门：提交 `8bbf901` 上的 C06 三条件调用 3/3 HTTP 200、模型一致、`finish_reason=stop`、strict JSON/schema，消耗 38,658 tokens；泄漏 0、ungrounded reference 0，自动检查均为 1.0。三组均选择 OSM recovery source 和 degraded delivery，并保留失败根因未知的不确定性。manual review 的 quality failure evidence、semantic guard 和 recovery trace 尚未验证，因此该小 pilot 不具备 formal claim eligibility。
- 下一步：停止协议诊断迭代，冻结 DeepSeek 官方 Provider、`deepseek-v4-flash`、temperature 0.1、strict JSON、16384 output、零 retry/repair/fallback、manifest/output schema/evaluator hash、schedule seed、重复次数和 600,000-token 18-call 预算。冻结审计通过后才可进入 planning-only formal；P4 manual items 不得由 planning-only 自动分代替。
- formal freeze v2：证据位于 `docs/current/evidence/p3-planning-formal/2026-08-13-protocol-freeze-v2/`。18-call schedule 使用 seed `20260813`，每个 C01-C06 × 三种 LLM knowledge condition 运行 1 次；该设计不支持 stability claim。600,000-token 预算覆盖 555,437-token 保守上界。manifest、output schema、system prompt、evaluator、六个实现文件、schedule 与 prepared inputs 均有 SHA-256 并通过复算。
- remaining blocker：DeepSeek 官方 `/models` 对 `deepseek-v4-flash` 只返回 provider-reported ID 和 owner，`created=null`，无 immutable revision/version 字段。因此协议保持 `blocked_before_formal_execution`，唯一 freeze audit 失败项为 `immutable_model_revision`。不得把多批响应 model ID 一致提升为不可变版本证明；取得官方固定 revision 或经用户明确改变该研究要求前，不执行 18-call formal。

## 9. 阶段检查点（2026-08-14，C04 v4/r3）

### 目标和阶段

- 当前目标：执行 `C04 / llm_full_contract_kg` 两阶段真实 road fusion，并保留 frozen plan 精确注入、0 LLM、0 Provider network、禁止 fallback/自动重试/artifact reuse 的实验边界。
- 当前阶段：v3/r2 首阶段真实失败后的 schema/quality 根因修复已完成；v4/r3 已冻结并通过 preflight，尚未执行。

### 已完成证据

- v3/r2 真实 run `3c9624f31826468e8308e5bd82580bc4` 完成 1 次 large-area V7 单源执行，输出 16,279 个 `MultiLineString`，随后仅因 `required_fields` 缺失 `road_class/source_layer/osm_name/road_name` 被质量门拒绝；第二阶段未启动，未重试。
- r2 原始 `experiment_failure.json`、`audit.jsonl` 和 `stage_record.json` 未覆盖。新增外部证据 `experiment_failure.correction.json`，依据 audit 将算法执行统计校正为 started=1、completed=1，并冻结三份原始证据 hash。
- 根因修复提交 `76ab5a0`：单源 road 分支复用 V7 canonical output；research adapter 从冻结 KG 水合 product contract 授权的 repair strategy 节点；runner 同时统计普通与 large-area 执行事件。
- 对 r2 的真实 16,279 要素产物进行回放式质量验证：同一 `contract.road.fused.v1`、同一 external-degradation 语义下 `accepted=true`、`missing_fields=[]`；没有放宽质量合同或改变原有 soft adaptation。
- 验证：聚焦回归 48 passed；扩大 Agent/quality/road/research/P4 回归 158 passed；`compileall` 通过；KG release verification 11/11 通过。仅保留既有 GeoPandas/PyProj warning。
- v4 freeze 提交 `3e78976`，目录 `docs/current/evidence/p4-planning-e2e/2026-08-14-c04-road-protocol-freeze-v4/`。身份为 `fusionagent.p4.c04-road-e2e.v4 / p4-c04-road-caracas-r3`，implementation commit `76ab5a0`，workflow hash `sha256:a1792cbbaa35c0e69f9b4ae59e15cecd4555215d69acac0271bae16d7de8bc59`。
- v4 freeze audit 12/12、runner preflight 11/11 通过；preflight 实际计数为 fusion runs 0、LLM calls 0、Provider calls 0。外部 r3 evidence root 尚不存在。

### 未完成 / 阻塞

- r3 两阶段正式执行尚未开始，因此不能声称 C04 端到端成功、supersession 成功或研究主张成立。
- Microsoft 到达阶段的真实双源执行、质量复评和 supersession 仍待 r3 首阶段通过后验证。

### 下一验收点

- 用户再次明确“继续”后，唯一下一动作是执行一次：`python scripts/run_p4_c04_road_e2e.py --freeze docs/current/evidence/p4-planning-e2e/2026-08-14-c04-road-protocol-freeze-v4 --execute`。
- 执行后在任何阶段失败即停止，不自动重试；保留新 r3 evidence root，并核对 run ID、frozen plan hash、事件计数、真实产物字段/数量/CRS、质量报告及第二阶段是否启动。

### 不应自动扩展的事项

- 不修改 rubric、Prompt、KG v1、质量阈值或 degradation 语义。
- 不复用或覆盖 r1/r2 失败证据，不从旧产物冒充 r3 结果。
- 不在本检查点自动执行 r3，不因 preflight 通过宣称真实能力完成。

## 10. 阶段检查点（2026-08-14，C04 r3 失败后诊断）

本节取代第 9 节作为当前恢复点；第 9 节保留为 r3 执行前历史记录。

### 目标和阶段

- 当前目标不变：执行 `C04 / llm_full_contract_kg` 两阶段真实 road fusion，并保持 frozen plan 精确注入、0 LLM、0 Provider network、禁止 fallback/自动重试/artifact reuse。
- 当前阶段：v4/r3 已执行一次并停止于第二阶段质量门；失败证据已保留，已完成只读根因诊断，尚未实施修复。

### 已完成证据

- r3 外部证据根为 `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c04-road-e2e-r3`；`experiment_failure.json` 为权威失败摘要，未生成 `experiment_result.json`，也未写入成功 supersession。
- 正式命令只启动一次。工具层超时后未重新启动进程；最终统计为 runtime runs 2、stages completed 1、fusion executions started/completed 2/2、second stage started=true、automatic retry=false。
- 第一阶段 run `f600c6fec1e34cd7bab40d12c8c9cf5e` 成功：OSM 16,279，Microsoft 为 `NO_OFFICIAL_COVERAGE`，单源 V7 输出 16,279；schema 与 external-degradation quality gate 均通过。交付 ZIP SHA-256 为 `a62ebe91c9144ebb7fa23fc6335054a14230fc5ce39e52afcba789b509769f2d`。
- 第二阶段 run `60df11ce004e4739bf998155406c909d` 真实执行 OSM 16,279 + Microsoft 11,809；V7 最终输出 23,760，其中 matched Microsoft segments 11,629、unmatched 2,916、residual 465。schema validation 通过，但 `quality.default.road.v1` 以唯一 hard failure `dangle_endpoint_rate_per_100km=637.0289291208259 > 500` 拒绝。
- repair 前后均为 23,760 features、2,633.318399 km、16,775 exact-coordinate dangle endpoints，指标完全不变。repair 实际依次尝试四个获授权策略；仅 `repair.artifact.road_name.v1` 因填充 59 个名称而标记 changed，`repair.artifact.line_topology.v1` 只检查 MultiLineString/零长度线且 changed=false。
- 对第二阶段真实产物的只读拓扑分解：16,775 个 exact-coordinate dangle 中，10,383 个端点实际精确落在另一条非自身线要素上；现 metric 未把 endpoint-to-line-interior 的 T junction 视为连接。按该线网连接语义排除后剩 6,392 个，约为 `242.7/100km`，无需修改 `500/100km` 阈值即可通过该项。输入基线按现 metric 分别为 OSM `583.57/100km`、Microsoft `204.07/100km`，说明失败不能只归因于 Microsoft 数据质量。
- 第二阶段 `source_semantic_contract.json` 明确为 `valid=false`：`raw.microsoft.road` 缺少 required `source_feature_id` 和 `road_class` 映射。KG 当前把 Microsoft road 错配为 `fields.road.osm`；实际字段仅为 `WidthMeters/CountryCode/source_country`，但 V7 会在执行时生成位置 ID 并把缺失 class 默认为 `road`。runtime 目前只记录 invalid contract 后继续执行。

### 已验证根因

1. **评价语义错误（直接导致拒绝）**：`dangle_endpoint_rate_per_100km` 只统计完全相同端点坐标的出现次数，没有识别端点落在线内部的有效 junction，导致至少 10,383 个假阳性 dangle。
2. **repair reason-to-strategy 决策缺失（导致无关产物变更）**：`ArtifactRepairService` 未按 `quality_report.failure_reasons` 过滤策略，而是尝试所有 authorized + available 策略；因此 dangle 失败触发了无关 road-name 修改。现有 line-topology action 也不具备连接真实 dangle 的能力。
3. **source semantic contract 未 fail closed（独立合同缺陷）**：Microsoft road 的 KG field profile 与实际 provider schema 不符，contract 已判 invalid，但 agent runtime 仍绑定参数并执行。V7 内部默认/生成字段不等于 provider-backed raw field mapping，不能把本次 schema output pass 当作 source semantic contract pass。

### 未完成 / 阻塞

- r3 仍是正式失败，禁止重试、覆盖或改写为成功；C04 的最终 supersession 和端到端研究主张尚未成立。
- 尚未冻结 Microsoft road 的合法语义路径：必须明确是 provider fid + geometry-only reference contract、预融合规范化，还是拒绝当前 source；不得把 `WidthMeters` 冒充 `road_class`，也不得把未声明的 positional ID 冒充稳定 upstream ID。
- 尚未修改 topology metric、repair 筛选和 semantic contract enforcement；没有新的回归或真实回放成功证据。

### 下一验收点

- 实施前先冻结三个最小契约：line-network dangle 的 junction 定义；quality reason 到 artifact strategy 的 KG-authoritative 映射；Microsoft reference source 的 identifier/class 解析与 fail-closed 语义。
- 随后实施最小代码/KG 修复，增加聚焦测试，并用 r3 双源 GPKG 做只读回放；只有回放在原阈值下通过且 source semantic contract 为 valid，才运行扩大回归和 KG release verification。
- 修复提交后生成全新 `v5/r4` protocol/run/evidence identity，仅执行 freeze audit 与 preflight；正式 r4 仍需用户再次明确授权。

### 不应自动扩展的事项

- 不修改或软化 `dangle_endpoint_rate_per_100km <= 500/100km`，不改变 degradation 语义。
- 不把无关 road-name backfill 当作 topology repair，不通过自动 retry 或 artifact reuse 掩盖失败。
- 不重跑 r3，不复用 r3 run ID/evidence root，不在修复前生成 r4 正式结果。

## 11. 阶段检查点（2026-08-14，质量修复完成 / KG 语义阻塞）

本节取代第 10 节作为当前恢复点；第 10 节保留失败后诊断记录，其中“10,383 个精确落在线上”应以本节的严格 `intersects` 回放结果为准。

### 已实现

- `artifact_evaluation_service` 的 dangle 计算现在把 endpoint 落在另一条 line interior 的 T junction 视为已连接，不再要求目标线必须预先 node 化；未修改 `500/100km` 阈值。
- `ArtifactRepairService` 先把 quality check ID 归一到 frozen KG 已有 reason code，再使用 KG `RepairStrategyNode.reason_codes` 筛选 authorized + available 策略。dangle failure 不再触发无关 road-name backfill。
- frozen-plan 严格执行在 source semantic contract `valid=false` 时 fail closed，固定错误前缀为 `SOURCE_SEMANTIC_CONTRACT_INVALID`；普通既有 runtime 仍记录 `source_semantics_invalid`，避免在本阶段扩大产品行为变更。
- frozen KG v1 内容和 semantic hash 未改变；曾用于验证候选 Microsoft profile 的本地改动已撤回并通过 builder 恢复为 `sha256:50067b9368914c47580707650789c04c78b2e856ccb3ef4d120a31f36c0ad71e`。

### 真实回放与验证

- 对 r3 原始 23,760-feature 双源 GPKG 做只读质量回放：`dangle_endpoint_count=7,142`、`dangle_endpoint_rate_per_100km=271.2167279750187`、threshold `500.0`、`accepted=true`、hard failures `[]`。该回放没有生成或覆盖 r3 成功结果。
- 同一输入按 frozen KG v1 重建 semantic contract 仍为 `valid=false`：Microsoft 缺 `source_feature_id` 与 `road_class`，因此严格 frozen-plan 路径会在算法前正确阻断。
- 聚焦回归 33 passed；修正普通 runtime 兼容性后回归 34 passed；最终扩大 Agent/large-area/quality/road/research/P4/frozen-plan 回归 192 passed。仅有既有 GeoPandas/PyProj warning。
- `python -m compileall -q services tests` 通过；KG release verification 11/11 通过。

### 当前阻塞

- 不能在 `kg/ontology/v1.0.0` 中原地把 Microsoft road 改为新 profile；这会改变 frozen KG semantic hash，却继续冒用 v1 identity。
- 当前 Microsoft artifact 的 provider FID 和 geometry-only reference 语义可以形成候选新 profile，且 `road_class` 可明确由 V7 默认 `road`，但该语义必须进入新 KG release 并获得独立 protocol identity，不能暗藏在 Python override 中。
- 另一条合法路径是替换为满足 frozen v1 `fields.road.osm` 的 Microsoft normalized artifact；这会改变正式输入 hash，同样必须使用新 protocol/run/evidence identity。

### 下一验收点

- 先决定并冻结二选一：发布新 KG release 承载 `fields.road.microsoft`，或生成并冻结符合 KG v1 的 Microsoft normalized input。
- 决策后实现对应最小路径、验证 semantic contract `valid=true`，再生成全新 v5/r4 freeze 与 preflight；本检查点不生成 r4，不执行正式实验。

### 不应自动扩展的事项

- 不原地改写 frozen KG v1，不用代码 special-case 覆盖 KG 字段语义。
- 不把只读 quality replay 升级为 r3 成功，不重跑或覆盖 r3。
- 未冻结 source semantic 路径前，不创建声称 formal-ready 的 v5/r4。

## 12. 阶段检查点（2026-08-14，Microsoft normalization 修复 / v5-r4 preflight）

本节取代第 11 节作为当前恢复点；第 11 节保留为修复前的语义阻塞记录。

### 已实现

- source semantic contract 已明确分为 `provider raw schema -> deterministic normalization -> algorithm canonical schema` 三层；strict frozen-plan gate 验证 `normalized_algorithm_input`，不再要求 Microsoft raw Shapefile 预先包含 OSM canonical 字段。
- 新增声明式 `normalization.road.microsoft_shapefile.v1`：`source_feature_id` 由 immutable provider artifact 的 GDAL FID 派生，`road_class` 使用 V7 已声明的 generic supplement default `road`；contract 和 normalized artifact 均记录 resolution 与 provenance。
- provider FID 只对声明了 derived-FID normalization 的 source 扫描；缺少稳定 FID、CRS、允许的 line geometry 或 normalization 后 required canonical field 未解析时均 fail closed。
- frozen-plan 路径在 semantic contract invalid 或 unavailable 时阻断；普通 runtime 保持既有兼容边界。
- frozen KG v1 未修改，semantic hash 保持 `sha256:50067b9368914c47580707650789c04c78b2e856ccb3ef4d120a31f36c0ad71e`。

### 提交与验证

- semantic normalization 修复提交：`3273901 fix: normalize Microsoft road source semantics`。
- v5 freeze 实现提交：`43042af research: prepare C04 road protocol v5`。
- 聚焦 semantic/normalization/strict 测试 25 passed；large-area/national-scale 回归 25 passed；扩大 Agent/quality/road/research/P4 回归 228 passed；最终 freeze 相关回归 12 passed，附加聚焦回归 61 passed。
- `python -m compileall -q services scripts tests` 通过；KG release verification 通过且 failed checks 为空。

### r3 只读回放

- 独立证据根：`D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c04-road-semantic-normalization-replay-v1`；未写入或覆盖 r3，fusion/LLM/Provider 调用计数均为 0。
- Microsoft raw artifact：11,809 features，ESRI Shapefile，`EPSG:32619`，provider FID 可用；normalized contract `valid=true`。
- Microsoft normalized input：11,809 个唯一 `source_feature_id`，required fields 无缺失，normalization profile 与两个 provenance 字段齐全。
- r3 原始双源 GPKG 质量回放：23,760 features，2,633.318399 km，dangle 7,142，`271.2167279750187/100km <= 500`，hard failures `[]`，`accepted=true`。
- 该结果只证明当前修复对保留输入的 semantic normalization 与质量评价回放成立，不把 r3 改写为成功，也不证明新的端到端执行成功。

### v5/r4 冻结状态

- freeze：`docs/current/evidence/p4-planning-e2e/2026-08-14-c04-road-protocol-freeze-v5/`。
- 身份：`fusionagent.p4.c04-road-e2e.v5 / p4-c04-road-caracas-r4`；implementation commit `43042af72a053cc92ee904e700e1b3362696b40e`。
- source normalization contract hash：`sha256:37726c21a6b0a3d82eaa9be2d4270765f9da1fbbbd9bdd52358d4c104845c4be`。
- freeze audit 13/13 通过；runner preflight 11/11 通过；fusion runs 0、LLM calls 0、Provider calls 0。
- r4 evidence root `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c04-road-e2e-r4` 仍不存在，正式 r4 未执行。

### 下一验收点

- 当前阶段任务 1-5 已完成。下一步只有在用户再次明确授权正式 r4 后，才执行一次：`python scripts/run_p4_c04_road_e2e.py --freeze docs/current/evidence/p4-planning-e2e/2026-08-14-c04-road-protocol-freeze-v5 --execute`。
- 正式执行必须在任一阶段失败时停止，不自动重试；执行后核对两个新 run ID、frozen plan hash、normalized semantic contract、真实产物字段/数量/CRS、质量报告和 supersession 证据。

### 不应自动扩展的事项

- 不执行正式 r4，除非取得新的明确授权。
- 不覆盖或重解释 r3 失败证据，不复用 r3 run ID/evidence root。
- 不修改 frozen KG v1、质量阈值、Prompt、rubric、fallback 或自动重试边界。

## 13. 阶段检查点（2026-08-14，C04 r4 正式执行完成）

本节取代第 12 节作为当前恢复点；第 12 节保留为 r4 执行前历史记录。

### 已完成证据

- 已按 v5 冻结协议执行一次正式 C04 两阶段端到端运行：`fusionagent.p4.c04-road-e2e.v5`，运行身份 `p4-c04-road-caracas-r4`。执行 worktree 为提交 `389c9f8391c04bf46fa48449ffb66210ab75c64f`，冻结实现身份仍为 `43042af72a053cc92ee904e700e1b3362696b40e`。
- R4 证据根为 `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c04-road-e2e-r4`。preflight 11/11 通过；正式执行无 LLM、无 Provider network、无 fallback、无自动重试或 replanning；终态无残留 runner 进程。
- `osm_provisional` run `465c2c810bd845c2a0acb14107e02bd1` 成功：OSM 16,279 features，Microsoft 0 features，产物 SHA-256 `28a48cbe3b392578de28b9e1f1dd231f49e104c824707a4e2b3db62e27c3e26f`，质量门 `accepted=true`。
- `microsoft_arrival` run `296f3476098148c9b37ad1b3bfc85db0` 成功：OSM 16,279 + Microsoft 11,809 features，最终产物 23,760 features，产物 SHA-256 `e2cdf841cfcdcce97bba30fbbf30abada1f02abb59d24ed899aec8a9e1967ced`，质量门 `accepted=true`，目标 CRS `EPSG:32619`。
- `experiment_result.json` 的 15 项评价检查全部通过：精确 frozen plan 注入、normalized semantic contract、两次独立 runtime、两阶段质量评估、真实产物哈希、Microsoft 到达转换和 supersession 证据均已记录。顶层 `passed=true`。
- `supersession.json` 已证明 provisional 产物被 Microsoft 到达阶段产物替代；旧 r1/r2/r3 证据未覆盖或重解释。

### 研究边界与残余风险

- R4 证明的是单个 Caracas C04 在冻结输入、KG v1、实现和本地真实矢量数据条件下的执行链路与产物证据；不能支持比较优势、统计显著性或跨 AOI 有效性主张。
- 两阶段最终交付状态仍为 `degraded`；planning gold 的 `provisional` 期望与端到端结果差异保留为评价结果，不通过改 rubric 或补跑消除。
- ZIP 内 Shapefile 按 ESRI 10 字段名限制存在字段名规范化警告；质量报告引用的 GPKG 是当前结构化质量产物，后续交付审计需继续核对字段映射。

### 下一验收点

- 对 R4 证据执行独立只读审计，确认两个 GPKG/ZIP 的几何、属性、CRS、质量报告和 hash 链一致；审计通过后再决定是否冻结 C02/C06 的选择性 P4 执行协议。
- 在新的案例协议、输入和证据根冻结前，不启动 C02/C06，不把 C04 单案例结果扩展为方法级结论。

### 不应自动扩展的事项

- 不修改 R4 结果、质量阈值、frozen KG v1、Prompt、rubric、fallback 或重试边界。
- 不删除失败证据，不将 R4 的执行通过升级为 comparative capability 或 external validity 结论。

## 14. 阶段检查点（2026-08-14，C02/C06 选择性 P4 冻结闸门）

本节取代第 13 节作为当前恢复点；第 13 节保留 R4 的成功执行证据。

### 冻结前审计事实

- 当前正式 planning 18-run readiness audit 仅有 `C04 / llm_full_contract_kg` 一项 wiring-ready；不能从“C04 已完成”推断 C02 或 C06 可执行。
- `formal-c02-llm_full_contract_kg-r1` 的五个任务均未给出 `algorithm_id`。它描述 water polygon、waterways、road 的优先顺序以及 building/POI gap，但不能直接形成被冻结的 executable workflow；运行时补填 algorithm 会改变 `selected` 层含义，不能被记为该 LLM plan 的端到端成功。
- `formal-c06-llm_full_contract_kg-r1` 只表达质量门拒绝之后的 `recovery_replan`，选择 `raw.osm.road` 交给输入类型为 `dt.road.bundle` 的 V7。它既不包含首个双源质量门阶段，也不能在 adapter 中解析为 executable workflow。
- KG v1 对 `catalog.flood.road` 和 `catalog.typhoon.road` 都声明相同的 `raw.osm.road + raw.microsoft.road` component candidates。R4 在 Caracas 的相同双源道路条件和 V7 下完成 Microsoft arrival，并以 `quality.default.road.v1` 通过质量门；因此 C06 旧机制“首个双源融合必然质量门失败”已不再由当前冻结实现和数据支持。

### 决策

- **不冻结、不执行 C02/C06 P4 正式运行。** 这是研究语义与可执行性阻断，不是可由重试、Prompt 调整、运行时补全或阈值放宽解决的失败。
- C06 的历史失败和原始 recovery evidence 保留为历史观察；不得用 R4 的成功结果反写为 C06 成功，也不得人为注入失败来维持旧机制。

### 下一验收点

- 先形成一个新的研究设计决策：C02 是将“algorithm resolution”显式纳入 `resolved` 层并把它与 LLM selected plan 分开评价，还是将缺少 algorithm 的正式 LLM 计划作为不可执行结果保留；两种选择不能混用。
- C06 需要先以新的、可证伪且由真实输入支撑的 failure mechanism 或非失败 recovery research question 重写案例、gold 和 protocol。新的案例必须使用新版本、输入 hash、执行身份和证据根，不能覆盖 C06 v1.2.0-draft 或既有 formal run。
- 在上述设计冻结和独立预检通过前，不创建 C02/C06 runner，不调用 LLM/provider，不启动新的空间处理运行。

### 不应自动扩展的事项

- 不将 C02/C06 的 runtime resolver 推断、旧 Freeze C 成果或 mock P4-G 结果标为本次正式 LLM P4 证据。
- 不因 C06 旧机制失效而降低 quality threshold、伪造质量失败、删除 R4 成功证据或重跑任何已冻结 formal call。

## 15. 后续长时实验执行计划（C02/C06）

本节是第 14 节之后的唯一执行计划。它把 C02/C06 的研究设计、实现、真实运行和证据审计拆成可恢复阶段；在本节每个阶段的验收通过前，不得进入下一阶段。

### 15.1 项目契约

**目标**：在不重写 P3 formal 原始响应、不覆盖 C04 R1-R4 或 C06 历史失败证据的条件下，判断 C02 是否可作为“LLM selected plan + KG resolved execution”的受限端到端案例，及 C06 是否存在可由真实输入自然复现的质量失败-恢复机制。只有各自协议、输入和证据冻结后，才执行一次新的正式运行。

**当前事实基线**：C04 R4 是唯一已完成的正式 P4 execution；C02/C06 没有可直接执行的 frozen workflow。P3 formal 的 18 个原始 LLM 响应、model revision、schedule 和 run ID 只读保留。

**非目标**：本计划不重新调用 LLM 来修复旧计划，不修改 KG v1、质量阈值、Prompt、rubric、R4 产物或既有 evidence root；不把 mock、历史 P4-G 或代码单测表述为真实端到端能力。

**共同运行边界**：真实阶段使用本地已声明的实际矢量资产和真实 runtime；禁止 fallback、自动 retry、JSON salvage、人工补齐算法/来源或人为制造质量失败。每次正式运行使用新的 protocol ID、case version、input hash、run ID 和外部 evidence root。任何 paid Provider 调用须在单独 protocol 中重新冻结 provider、不可变 revision、预算和失败保留规则。

### 15.2 主张矩阵

| 工作项 | 可检验主张 | 比较对象/反例 | 实验单元 | 必需证据 | 不可声称 |
|---|---|---|---|---|---|
| C02 | 已冻结的 LLM selected priority/gap 可经确定性 KG resolver 显式转换为实际多图层执行与 gap 记录 | selected plan 缺算法、source closure 不足或 resolver 拒绝 | 单个固定 AOI、一个 frozen formal run、三个可执行图层与两个 gap 层 | selected/resolved/executed/evaluated 链、真实产物、质量报告、gap declaration、hash manifest | LLM 独立选择了算法、比较优越性、跨 AOI 有效性 |
| C06 | 只有真实观察到的双源质量拒绝才能触发保留 raw failure 的受控恢复；若未观察到失败，该机制不成立 | 质量门通过、source 不可用、系统故障、人工移除 source | 预冻结候选 AOI/source snapshot 的单次真实运行 | 首次 raw/adapted quality、failure class、source lineage、recovery plan、最终质量与 supersession/gap | 人为注入失败、C04 成功可证明 C06 恢复能力、跨场景稳健性 |

### 15.3 阶段总览

| 阶段 | 状态 | 下一验收点 |
|---|---|---|
| S0：基线锁定 | 已完成 | C04 R4 与第 14 节冻结闸门保持可复核 |
| S1：C02 selected/resolved 语义冻结 | 已完成（2026-08-14） | resolver 不隐藏算法选择，且 C02 selected plan 与缺口语义可机械审计 |
| S2：C02 真实输入预检与协议冻结 | 已完成（2026-08-14） | 三个执行层和两个 gap 层的真实输入、语义和预算全部闭合 |
| S3：C02 单次正式端到端运行与审计 | 已执行，受控失败（2026-08-14） | r2 失败证据与独立审计保持不可覆盖，进入 S4 |
| S4：C06 真实失败机制发现与案例重设计 | 已完成，未观察到自然 failure（2026-08-14） | 退役旧“必然失败”机制 |
| S5：C06 协议冻结、单次运行与审计 | 未运行，前置条件不成立 | `not_run_precondition_unsatisfied` |
| S6：独立证据审计与受限结论汇总 | 已完成（2026-08-14） | 13/13 统一审计通过，保留受限主张 |

### 15.4 S1：C02 selected/resolved 语义冻结

**依赖**：第 14 节的 formal result 与 KG v1 identity。

**允许修改范围**：仅限 C02 research schema、`ResearchPlanRuntimeAdapter` 的显式 resolution trace、C02 专用冻结器/测试和本计划检查点。不得修改旧 formal result、通用 planning rubric 或 KG v1。

**实施动作**：

1. 固定 C02 正式输入为 `formal-c02-llm_full_contract_kg-r1`，以 schedule `run_id` 连接 result，不按目录名或人工复制选择。
2. 冻结以下解释：`selected` 只记录 LLM 输出的 task kind、source ID、delivery state、priority/gap；`resolved` 才记录由 KG v1 确定性解析出的 algorithm、effective source、handler 和输入/输出类型。
3. 在 resolver 不能闭合时把该 layer 记录为 `rejected` 或 `gap`，绝不补填为已执行；building/POI 继续作为显式 gap，不生成空产物。
4. 为 water polygon、waterways、road 分别验证 task-kind、algorithm、catalog bundle、component roles 和 product-contract layer requirement，特别禁止把 water polygon algorithm 解析为 waterways。

**最小验证集**：C02 selected/resolved contract unit tests、C02 workflow validator test、对 frozen result 的只读 resolution replay。

**验收标准**：每个可执行 layer 有唯一的 KG-backed algorithm/source/handler；每个不可执行 layer 有显式 gap/rejection reason；`selected -> resolved` 差异可机器读取；不存在未记录的默认 algorithm 或 source substitution。

**退出条件**：若 LLM selected fields 本身不足以形成可审计 resolution，停止 C02，不修改原响应或补调模型。

### 15.5 S2：C02 真实输入预检与协议冻结

**依赖**：S1 通过。

**允许修改范围**：C02 专用 asset inventory、freeze/runner 脚本、测试与外部 evidence root；不修改 C04/C06 runner 和既有 KG release。

**实施动作**：

1. 为 Caracas AOI 生成真实 asset inventory：AOI 边界、OSM water/waterways/road、HydroLAKES、HydroRIVERS 和 Microsoft road 的路径、版本、SHA-256、要素数、CRS、source role 与可用性。
2. 明确 water polygon 的 HydroLAKES 延迟/缺失语义：若正式 selected/resolved contract 要求 HydroLAKES 而它不可用，只允许 provisional 或 gap，不允许将单源结果称为 final。
3. 冻结 C02 运行顺序为 water polygon -> waterways -> road；冻结 building/POI gap declaration；冻结 source semantic risk 的评价字段与产品合同状态。
4. 生成新的 `protocol.json`、`execution_config.json`、selected/resolved plan、asset inventory、implementation manifest、freeze audit 和零运行 preflight。计划中的未来入口为 `scripts/freeze_p4_c02_protocol.py` 与 `scripts/run_p4_c02_e2e.py`；在此阶段创建前不得假定其存在。

**最小验证集**：冻结器 hash 复算、WorkflowValidator(enforce)、真实资产只读 profile、source semantic contract、预检 0 runtime/0 LLM/0 Provider 调用。

**验收标准**：所有实际输入与冻结 source role 一致；预检通过；预期 evidence root 不存在；所有质量/contract/gap 输出路径已确定；没有把临时缓存、mock 或旧运行产物登记为输入。

**退出条件**：任一 required source 无法合法物化、CRS/几何/语义不闭合，或 water delayed semantics 与 formal selected plan 冲突时停止并记录 gap，不启动正式 C02。

### 15.6 S3：C02 单次正式端到端运行与审计

**依赖**：S2 freeze audit 和 preflight 全部通过，且用户对实际空间处理再次授权。

**实施动作**：只执行一次冻结 runner；按固定顺序创建独立 runtime run，保留每层 selected/resolved/executed/evaluated、source materialization、raw/adapted quality、product contract、gap declaration 和 artifact hash。失败即停止，不补跑、不跳过失败层、不重用旧 artifact。

**最小验证集**：正式 runner 退出状态、独立重读 stage records、ZIP/GPKG SHA-256 复算、要素数/CRS/字段抽查、质量报告与产品合同一致性审计。

**验收标准**：真实输入可追溯；water/road/waterways 的实际结果或失败各自有证据；building/POI gap 可追溯；优先级、semantic risk、质量和交付状态未被结果回填改写；正式结果不超出 C02 单 AOI 的受限主张。

**退出条件**：任何链条断裂、质量报告缺失、计划哈希漂移、source semantic invalid 或运行时 hidden fallback 均将该 run 记为失败并停止。

### 15.7 S4：C06 真实失败机制发现与案例重设计

**依赖**：S0；可与 C02 文档设计并行，但不得与 C02/C06 正式运行并行。

**允许修改范围**：C06 候选集清单、只读 profile/quality screening、研究 case/protocol draft 和测试。不得篡改输入、调整阈值、注入坏几何或将系统故障改写成质量失败。

**实施动作**：

1. 先冻结有限候选集：每个候选必须有独立真实 source snapshot、AOI、双源 materialization 路径、算法版本和质量 policy；候选集之外的结果不得事后补入。
2. 对候选执行只读数据 profile 与受控真实 fusion screening，逐项记录 raw quality、adapted quality、failure class、source availability 和 geometry hash。此阶段是机制发现，不是正式能力实验。
3. 仅当出现 `quality_gate_rejected_fusion_output` 且 source lineage、算法输入和 runtime 环境完整时，才把该输入冻结为新的 C06 case。若所有候选通过质量门，则正式退役“必然失败”机制，改写研究问题而不制造 failure。
4. 新 C06 case 必须区分 initial dual-source plan、observed failure、recovery replan 和 final delivery；external source failure、system failure 与 quality failure 不得混用。

**最小验证集**：候选清单 hash、真实资产 profile、failure taxonomy test、raw/adapted quality replay、source semantic contract check。

**验收标准**：得到一个真实且可复核的 failure case，或得到“预冻结候选未观察到该机制”的负结果；两种都是有效阶段终态。

**退出条件**：发现需要人工移除 source、篡改几何、放宽阈值或重试才能触发 failure 时，立即排除候选并不得进入 S5。

### 15.8 S5：C06 协议冻结、单次运行与审计

**依赖**：S4 观察到合法 failure case，并完成新的 case version、gold、input schema、implementation manifest 与 evidence root 冻结。

**实施动作**：创建未来专用入口 `scripts/freeze_p4_c06_protocol.py` 与 `scripts/run_p4_c06_e2e.py`，在冻结 runner 中依次执行 initial dual-source、记录真实 quality failure、构造 recovery replan、执行允许的单源恢复。恢复不是 transport retry；其触发条件、source change 和产品状态必须来自冻结 case contract。

**最小验证集**：冻结器与 runner 的 fail-closed 单元/合同测试、真实预检、一次正式运行后的 raw failure/recovery trace/最终 artifact 独立审计。

**验收标准**：首次失败真实存在且未被覆盖；recovery 只在 frozen policy 允许时发生；raw 与 adapted quality 均保存；最终状态为 accepted degraded/provisional、gap 或失败中的一种，不冒充 fully satisfied。

**退出条件**：初始阶段通过质量门、failure 分类不明、source semantics 不合法、recovery 依赖自动 retry 或任何 artifact reuse 时，停止并保存 observed result，不产生成功结论。

### 15.9 S6：独立证据审计与结论汇总

**依赖**：S3 已有 C02 formal result，及 S5 的合法成功或负结果。

**实施动作**：对每个新的 evidence root 重新计算 protocol/input/implementation/artifact hash，验证 run-set、selected/resolved/executed/evaluated 链、质量报告、gap/supersession 和实际矢量产物。更新论文表格时分别列出 C02、C04、C06，负结果和未运行项目不得删除。

**验收标准**：每条研究表述能回指具体 protocol、AOI、run ID 和 evidence file；不将 C04 单案例、C02 resolver 行为或 C06 screening 升格为比较优势、统计显著性或广泛外部有效性。

### 15.10 恢复规则与暂停条件

- 当前恢复点为 **S6 已完成后的证据冻结终态**；S1-S4 与 S6 已完成，S5 因 S4 未观察到合法 failure 而按协议未运行。
- 每次恢复先检查 `git status`、当前 commit、相关 evidence root 是否已存在、运行进程、KG semantic hash、protocol/asset hashes；发现已有同名 evidence root 时拒绝覆盖。
- 任一 paid API、实际 fusion 或长时下载都必须在对应 preflight 通过后、并获得该阶段的明确执行授权才可启动。
- 连续两次同方向修复不能闭合契约时停止编码，回到数据/schema、KG、workflow、planning、工具环境、评价的诊断顺序；不得以增加 retry、Prompt 或阈值放宽继续推进。

### 15.11 执行检查点（2026-08-14，S1 完成 / S2 进行中）

- S1 实现已提交：`services/research_plan_runtime_adapter.py` 增加显式 `complete_from_kg=False`；默认路径仍 fail-closed，只有 C02 专用调用可启用 frozen KG workflow pattern completion。
- `selected` 保留 formal LLM 原始字段；`resolved` 记录 `resolution_basis=kg_workflow_pattern`、pattern/step、effective source/algorithm 和 completion metadata。无法闭合的任务保持 rejected/gap，不生成执行任务。
- 新增只读审计入口 `scripts/audit_c02_selected_resolved.py`，按 immutable `run_id` 连接 formal result 与 schedule，不调用 LLM、Provider 或 fusion runtime，输出 `claim_eligible=false`。
- S1 证据根：`D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c02-selected-resolved-s1-r2`。3 个执行层为 `water_polygon`、`waterways`、`road`；`building`、`poi` 为显式 gap；`kg_completion_count=3`；调用计数为 `0/0/0`。
- 验证：`python -m pytest tests/test_research_plan_runtime_adapter.py tests/test_audit_p4_planning_e2e_readiness.py -q`，`9 passed`；`git diff --check` 通过。
- S2 首个动作：只读清点 Caracas AOI 的真实 water/waterways/road、HydroLAKES/HydroRIVERS、Microsoft road 资产，生成 source/CRS/feature-count/hash inventory；在 inventory 和 semantic contract 闭合前，不启动 fusion、LLM 或 Provider。

### 15.12 执行检查点（2026-08-14，S2 资产清点与 semantic contract 通过）

- 只读资产 profile 脚本：`scripts/profile_p4_c02_assets.py`。它只读取 manifest 与本地真实矢量，不调用 LLM、Provider 或 fusion runtime；重复运行拒绝覆盖既有 evidence root。
- 初始资产清点证据：`D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c02-asset-inventory-s2-r1`，所有 7 个 C02 required assets 存在，AOI 相交计数非零，null/invalid geometry 均为 0，HydroLAKES 全库 `1,427,688` 个要素、AOI 相交 `1` 个要素。
- 增强清点与 semantic contract 阻塞诊断保留在 `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c02-asset-inventory-s2-r2`，不得覆盖；它记录了 water/waterways 的原始 `feature_kind` 缺口。
- S2a 修复提交新增四个按 frozen `field_mapping_profile` 选择的 normalization profile：`normalization.water.osm_polygon_geometry.v1`、`normalization.water.hydrolakes_polygon_geometry.v1`、`normalization.waterways.osm_line_geometry.v1`、`normalization.waterways.hydrorivers_line_geometry.v1`。contract trace 明确记录 `derivation=geometry_type`、规范化值、allowed geometry types 与 provenance；KG v1 semantic hash 未改变。
- 修复验证：水面/水系 semantic contract 聚焦测试与既有 Track-B normalization 测试 `12 passed`；真实清点新 revision `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c02-asset-inventory-s2-r3` 通过，三个 C02 bundle contract 均 `valid=true`，仍为 `fusion_runs=0 / llm_calls=0 / provider_calls=0`。
- 下一动作：创建 C02 专用 freeze/preflight 入口，冻结 selected/resolved plan、asset inventory、semantic contracts、workflow、gap declaration、implementation manifest、预算和 evidence root；freeze/preflight 通过前不启动 S3。

### 15.13 执行检查点（2026-08-14，S2 freeze/preflight 通过）

- C02 freeze 入口：`scripts/freeze_p4_c02_protocol.py`；冻结根：`D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c02-water-road-protocol-freeze-v1`。
- 协议：`fusionagent.p4.c02-water-road-e2e.v1`；implementation commit `af2dc35`；冻结的三个 stage plan 分别对应 `water_polygon`、`waterways`、`road`，每个 stage 单独通过 `WorkflowValidator(enforce)`。
- freeze audit：15/15 checks passed；preflight：9/9 checks passed。冻结输入包含 formal result/schedule、S1 selected-resolved audit、S2 r3 inventory、case manifest、KG identity 和 implementation file hashes；未来证据根 `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c02-water-road-e2e-r1` 保持不存在/空目录。
- 当前禁止动作：不调用 `scripts/run_p4_c02_e2e.py`，不启动 fusion，不复用 C04/C02 旧运行产物，不用 preflight 结果宣称 C02 端到端成功。S3 需先实现并纳入 runner hash 的正式入口，然后由用户明确授权一次真实空间处理；任何 stage 失败即停止，不自动重试。

### 15.14 执行检查点（2026-08-14，S3 C02 r2 受控失败）

本节取代 15.10 的 S3 恢复状态；S1、S2 保持完成，S3 已按冻结协议执行一次并以真实失败终止，不得重跑或覆盖。

#### 提交、冻结与执行身份

- frozen water task/job 语义修复提交 `89d3989`：`water_polygon`、`waterways` 通过 KG-authoritative `task_kind_to_job_type()` 映射到 `JobType.water`，真正 mismatch 仍 fail closed。
- C02 runner 与 v2 freeze 实现提交 `e765adc429f64239d0ea668eed95689bf80873b7`；v2 将 `scripts/run_p4_c02_e2e.py`、`schemas/task_kind.py` 和相关 runtime 文件纳入 implementation hash。
- v2 freeze：`D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c02-water-road-protocol-freeze-v2`；协议 `fusionagent.p4.c02-water-road-e2e.v2`，运行身份 `p4-c02-water-road-caracas-r2`。
- freeze audit 15/15、runner preflight 13/13 通过；正式启动前计数为 fusion 0、LLM 0、Provider 0，KG semantic hash 保持 `sha256:50067b9368914c47580707650789c04c78b2e856ccb3ef4d120a31f36c0ad71e`。

#### 正式执行事实

- r2 证据根：`D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c02-water-road-e2e-r2`；只启动一次 runner，创建 2 个独立 runtime run，完成 1 次 fusion，未执行 retry、replan、fallback 或 artifact reuse，终态无残留 runner 进程。
- `water_polygon` run `f2df80b624534375bfe972cee542dcfe` 成功：OSM 38 + HydroLAKES AOI 1，输出 39 个有效 `MultiPolygon`，CRS `EPSG:32619`；GPKG SHA-256 `982d371347598300ed5028dba0298fc99d38ecb8e04321cdac8f5e036bdfc3b9`，ZIP SHA-256 `400628f14b3de63401ee80d31dd04c3c809a0d97be52d3b8209839b151e45488`，`quality.default.water_polygon.v1` 接受。
- `waterways` run `1854e11850c24dc790f2e94af5b5eeb5` 在算法前被 strict source semantic gate 拒绝；未生成 artifact 或 quality report。正式错误为 `SOURCE_SEMANTIC_CONTRACT_INVALID`。
- 冻结 stage 只声明 `raw.osm.waterways + raw.hydrorivers.water`，runtime component coverage 却额外物化 `raw.local.pakistan.waterways`，并将 22-feature HydroRIVERS materialization 暴露为该未计划 source；这是冻结 abort condition `unplanned_source_or_algorithm_substitution` 的真实命中。
- semantic contract 同时记录 OSM/HydroRIVERS `feature_kind` unresolved，以及未计划 local source 的 `source_feature_id/feature_kind/water_class` unresolved。由于失败即停，road 未启动；不存在 `experiment_result.json`，权威终态是 `experiment_failure.json`。

#### 独立审计与研究边界

- `independent_audit.json` 对 freeze copy、run set、plan hash、event attempt、water GPKG/ZIP、质量报告、semantic contract 和 road 未启动状态重新复算，20/20 checks 通过；`evidence_integrity_passed=true`，但 `formal_execution_passed=false`、`claim_eligible=false`。
- r2 只能支持“C02 在冻结 Caracas 输入上完成 water polygon，随后因未计划 source expansion 与 semantic contract invalid 而 fail closed”的受限事实；不能声称 C02 多层端到端成功、LLM 优越、跨 AOI 有效或 road 已验证。
- 不修复后补跑 r2，不生成 r2 success correction，不把 S2 原始资产 semantic preflight 当作 runtime materialization contract 成功。若未来研究未计划 source expansion，必须使用新的协议、输入/实现 hash、run identity 和 evidence root。

#### 下一验收点

- 当前阶段转入 S4：先冻结有限 C06 候选集及每个候选的 AOI、双源 snapshot、算法、quality policy、source semantic contract 与 geometry hash；候选集冻结前不启动 screening fusion。
- S4 只观察自然产生的质量结果。若预冻结候选全部通过质量门，正式退役旧“首个双源必然失败”机制，不得通过删除 source、篡改几何、放宽阈值或重试制造 failure。

### 15.15 执行检查点（2026-08-14，S4-S6 完成）

本节取代 15.14 的下一阶段状态，作为 S1-S6 长时实验目标的最终恢复点。

#### S4 候选冻结与真实 screening

- 仓库只存在一个同时声明 OSM 与 Microsoft road、且具有可复算真实 snapshot 的 AOI，因此候选集在运行前冻结为唯一候选 `c06-screen-caracas-dual-road-v1`；没有为增加失败概率临时下载或事后添加候选。
- 实现提交 `5fd4aa3ccea7390c84f3c7c461db435824ae0ebe`；协议 `fusionagent.p4.c06-failure-screening.v1`；freeze 根 `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c06-failure-screening-freeze-v1`。freeze audit 10/10、preflight 9/9 通过，启动前 fusion/LLM/Provider 均为 0。
- screening 证据根 `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c06-failure-screening-r1`；唯一 run `8846dcd1bd5b4f92950bf26f34c751af` 使用 `catalog.flood.road`、V7、`quality.default.road.v1` 和 frozen OSM 16,279 + Microsoft 11,809 输入。
- source semantic contract `valid=true`；输出 23,760 个有效 `LineString`，CRS `EPSG:32619`，GPKG SHA-256 `d35dba0c25078af027d2b722e2be2d066029f2b425cb7aa12041685b8cc10a1f`，geometry SHA-256 `sha256:8e71aa487d1c68a98e42c4f2c8774c25d5641be6fc4c9cf4314b698d13611e93`。
- 质量门 `accepted=true`、`raw_quality_passed=true`、`adapted_quality_passed=true`；dangle `271.2167279750187/100km <= 500`，duplicate/invalid geometry rate 均为 0。独立审计 14/14 通过，screening outcome 为 `no_quality_failure_observed`。

#### S5 终态

- S4 未观察到 `quality_gate_rejected_fusion_output`，因此 `eligible_for_s5=false`。S5 状态固定为 `not_run_precondition_unsatisfied`；没有创建 recovery protocol、没有执行 recovery run，也没有删除 Microsoft source 或制造 failure。
- 旧 C06 “首个双源融合必然质量失败”机制正式退役。历史失败仍保留为历史观察，但不再作为当前实现和输入下的案例前提。

#### S6 统一证据审计

- 统一审计根：`D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-s6-selective-e2e-audit-v1`；`audit.json` 的 13/13 checks 通过，`claim_matrix.json` 和 `manifest.json` 固定三条案例结果及关键 evidence SHA-256。
- C04：v5/r4 两阶段 road 执行与 supersession 是单 Caracas AOI 成功证据；两个实际 GPKG/ZIP 和质量报告在 S6 重新读取、复算 hash，不能外推为比较优势或跨 AOI 有效性。
- C02：v2/r2 是正式受控失败；仅 water polygon 完成，waterways 因未计划 source expansion 与 semantic contract invalid 在算法前阻断，road 未运行。
- C06：只完成机制 screening，得到负结果；没有执行正式 recovery E2E，不能声称 recovery capability。
- 总体不支持方法比较优越、统计显著性或广泛外部有效性。可用表述必须逐条回指冻结 protocol、AOI、run ID 和 evidence file。

#### 最终状态与后续边界

- S1-S4、S6 已完成；S5 依据冻结前置条件合法跳过。当前 worktree、提交链、KG identity、实验根和主张矩阵已由 S6 audit 对齐。
- C02 未计划 waterways source expansion 是后续工程/研究问题，不在本目标内修复或重跑。任何新 C02/C06 实验都必须使用新的 protocol、candidate/input hash、implementation commit、run identity 和 evidence root。

## 16. 论文实验闭环执行计划（E1-E6）

本节是 S6 之后的唯一执行计划。第 15 节保持为已完成历史，不将 P3 v1、C02 r2、C04 r4 或 C06 screening 结果并入新的重复实验样本。

### 16.1 项目契约

**目标**：在不覆盖既有正式证据的前提下，为 RQ3 建立同一 implementation commit、同一输出合同和三次完整重复的六组 planning comparison，并为 RQ4 增加与主张宽度匹配的选择性多 AOI 真实执行证据；最终生成论文可直接引用的评价表、图和证据索引。

**当前主张边界**：实验不预设 LLM+KG 优于 rules-only 或 KG-only。三次重复只用于描述同一案例内的规划稳定性、失败率和有界效应，不支持统计显著性或总体泛化。C03 继续作为 negative control，不计入正例均值。

**冻结输入**：`docs/current/research-case-manifest-v1.json`、KG v1 identity、`ResearchPlanningDecision` schema、当前 system prompt、evaluator、DeepSeek provider/model revision evidence。任何语义修改必须产生新 protocol，不得在批次中途变更。

**非目标**：不修复或重跑 C02 r2；不人为制造 C06 质量失败；不修改 KG v1、旧 Prompt、旧 rubric、旧 formal result 或旧 evidence root；不把 mock、preflight、确定性测试或历史 P4-G 当作真实 LLM 能力证据。

**共同失败语义**：Provider、HTTP、模型身份、usage、strict JSON、schema、grounding 和 rubric 失败均按观察结果保留；禁止 retry、repair、salvage、fallback、结果替换和只对低分格子补跑。

### 16.2 主张矩阵

| 主张 | 比较对象 | 指标 | 实验单元 | 证据文件 |
| --- | --- | --- | --- | --- |
| RQ3-a：知识上下文是否改变计划有效性与合同满足 | LLM-only / capability KG / full-contract KG | pre-fallback validity、automatic score、人工 rubric、禁止行为率 | case x condition x replicate | raw response、result、automatic audit、review records |
| RQ3-b：LLM 条件相对确定性策略的增量与代价 | fixed / rules / KG-only / 3 LLM groups | 同一 rubric、latency、tokens、失败率 | case x group；LLM replicate 描述随机性 | deterministic report、LLM audit、comparison table |
| RQ3-c：规划是否稳定 | 三个 LLM condition 的三次重复 | plan structure signature、score range、decision/state agreement | case-condition cell | stability audit |
| RQ4-a：选定计划是否保持 selected-resolved-executed-evaluated 一致 | 选择性 E2E case/AOI | contract state、质量门、gap、artifact/hash/evidence completeness | frozen case-AOI run | protocol、run evidence、independent audit |
| RQ4-b：主张是否可独立复核 | 完整方法证据链 | manifest/checksum/audit pass rate | evidence root | unified paper evidence index |

### 16.3 E1：主张与缺口冻结

**阶段目标**：以 A0 研究章程和 S6 audit 为准，冻结本轮只补 RQ3 planning repetition 与 RQ4 external validity，不扩展系统功能。

**实施动作**：

1. 对齐 A0、P3 v1、S6 claim matrix 和人工评价文件。
2. 将 36 项 v1 manual items 区分为已裁决与必须由 execution evidence 支撑的项目。
3. 冻结本节项目契约、主张矩阵和 E2-E6 闸门。

**验收标准**：旧证据保持只读；所有新增工作可映射到 RQ3 或 RQ4；明确三次重复不产生显著性主张；状态文档、Git 和证据终态一致。

**退出条件**：若目标变为证明统计显著性、扩大灾种或修改 KG 语义，停止本阶段并新建研究协议，不在本计划内隐式吸收。

### 16.4 E2：统一六组重复协议与无网络预检

**依赖**：E1 通过。

**允许修改**：formal schedule/freeze/runner、对应 tests、本状态文件；不得修改 manifest、KG v1、system prompt、output schema 或 evaluator 语义。

**实施动作**：

1. 新建 `fusionagent.planning-repeated-formal.v2`，包含 C01-C06 x 3 LLM conditions x 3 repetitions，共 54 次真实调用。
2. 在同一 protocol/commit 下生成 C01-C06 x 3 deterministic groups x 3 repetitions，共 54 行；确定性重复只验证 exact stability，不作为独立随机样本。
3. 冻结 schedule seed `20260814`、temperature `0.1`、max output `16384`、zero retry/repair/salvage/fallback、model revision 和全部实现 hash。
4. token 保守预算固定为 `1,700,000`；正式启动前环境值必须逐项匹配。
5. 预注册扩展闸门：任一 cell 出现 Provider/schema failure、多个 plan structure signature 或 automatic score range >= 0.25 时，才允许通过新协议将所有 case-condition 一致扩至 5 repetitions；禁止选择性补跑。
6. 执行无网络 preflight，证明 paid provider calls 为 0、54 个 run ID 唯一且完整、所有输入无 gold leakage。

**最小验证**：协议/runner 聚焦 pytest、`compileall`、freeze audit、preflight manifest/hash/count 检查。

**验收标准**：freeze audit 全通过；worktree clean；实现 commit 在当前 HEAD 祖先链；未来 evidence root 不存在；API key 仅来自环境；尚未发生 Provider 调用。

**退出条件**：预算小于 conservative bound、model revision 无法复核、输入/hash 漂移或工作树不干净时，不进入 E3。

### 16.5 E3：确定性重复与真实 LLM 批次

**依赖**：E2 freeze/preflight 通过，运行环境包含匹配的 base URL、model、token budget 和 API key。

**实施动作**：

1. 先执行确定性 54 行并验证同一 case-group 的三个 semantic output hash 完全一致。
2. 对冻结的 54-call schedule 只启动一次真实批次；按 schedule 顺序执行，不并发修改证据根。
3. 每次保存 request/input hash、raw response、response model/request ID、usage、latency、finish reason、parse mode、plan 和 failure class。
4. 批次结束后运行自动 evaluator 和独立 integrity audit；不因 rubric fail 重跑。
5. 计算每个 cell 的 plan structure signature、decision/state agreement、score range 和失败率，按预注册闸门决定是否提出独立的 5-repetition extension protocol。

**验收标准**：所有已尝试调用均有不可变结果；失败未被替换；总 tokens 不超预算；运行集合与 schedule 精确相等，或在 fatal failure 后保留明确的未执行尾部；claim boundary 写入报告。

**退出条件**：模型身份不匹配、usage 缺失、预算超限或 fatal transport failure 时立即停止；不自动重启。

### 16.6 E4：盲化人工评价与一致性审计

**依赖**：E3 原始结果冻结。

**实施动作**：

1. 生成去除 condition 名称、run ID 暗示和自动分数的盲化 review packet；每条包含可见 planner input、plan、rubric item 和允许的 pass/fail/not-assessable。
2. 由两名独立人工评审者完成；Codex 或脚本生成的规则裁决只能标为 machine-assisted diagnostic，不冒充 human rating。
3. 在揭盲前冻结两份原始评价；报告 Cohen's kappa（名义项）及逐项一致率；分歧由第三人或预定义 adjudication 规则解决并保留原始分歧。
4. C05 `provenance_complete` 若仍需要 execution evidence，记为 not-assessable-at-planning，不强行转为 pass；规划质量与执行完整性分开统计。

**验收标准**：每个适用 manual item 有两份独立裁决或明确 not-assessable；评审身份使用稳定匿名 ID；原始评价、揭盲映射、分歧和裁决均有 hash。

### 16.7 E5：选择性多 AOI 真实端到端

**依赖**：E3/E4 已指出哪些 planning case 真正具有区分度；不得先选表现最好的案例再补协议。

**实施动作**：

1. 先只读清点 Caracas、Abidjan、越南北部沿海走廊及其他仓库已声明 AOI 的真实资产、CRS、feature count、geometry hash、source coverage 和运行能力。
2. 按预定义规则选择最多 2 个机制、每个至少 2 个可比 AOI；优先选择能验证 progressive delivery、source conflict 或 fail-closed contract 的案例，不复活已失效的 C06 机制。
3. 每个 case-AOI 使用新 case version、protocol、input hash、implementation commit、run ID 和 evidence root；一次性运行，失败即停。
4. 复算实际 GPKG/ZIP、CRS、geometry validity、quality report、lineage、contract state 和 evidence hash，执行独立审计。

**验收标准**：每个纳入论文的 case-AOI 都有真实输入、真实 runtime、实际产物或受控失败、独立审计和明确外推边界。资产不足时缩窄主张，不用 mock 补齐。

### 16.8 E6：论文结果流水线与统一审计

**依赖**：E3-E5 达到各自终态，包含合法失败或未运行状态。

**实施动作**：生成六组 comparison table、stability table、manual review agreement、E2E outcome table、案例时间线、claim-evidence matrix、有效性威胁表、环境/命令清单和数据代码可用性材料；所有数字由冻结 JSON 生成，不手工抄写。

**验收标准**：表图中的每个数字可回指 run/evidence file；负结果和失败保留；论文摘要允许表述与统一 claim audit 一致；未支持的 superiority/significance/cross-AOI 主张被机器检查拒绝。

### 16.9 当前恢复点

- 当前阶段：E1 主张与缺口冻结。
- 下一验收点：E2 v2 runner、测试、implementation commit、freeze audit 和 zero-call preflight 全部通过。
- 当前外部条件：本 shell 未配置 API key，因此 E2 可完成，E3 真实调用不得启动。

### 16.10 执行检查点（2026-08-14，E1-E2 完成，E3 确定性半段完成）

#### E1 主张与缺口冻结

- 本轮实验只服务 RQ3 planning comparison 与 RQ4 selective E2E；不把旧 P3 v1、P4-G mock、C02 r2、C04 r4 或 C06 screening 混入新的重复样本。
- P3 v1 的 36 项 manual review 实际状态为 27 pass、6 fail、3 pending；3 项 pending 均为 C05 `provenance_complete`，属于 planning output 无法单独证明的 execution-time property。自动审计中的 36 pending 是待评项生成状态，不再作为当前人工完成度口径。
- 三次重复只用于 case-condition 内稳定性与有界效应估计；不支持统计显著性或广泛外部有效性。旧 v1 结果不可与 v2 pooling。

#### E2 实现、冻结与 zero-call preflight

- v2 实现提交：`f6837fdc7f01b6ad13b5c8c422278572b069b8bd`；协议冻结提交：`559f22d828270b008497738e2f268da7cd43c73e`；确定性审计入口提交：`d033103`。
- protocol `fusionagent.planning-repeated-formal.v2`：C01-C06 x 3 LLM conditions x 3 repetitions = 54 paid calls；对应 deterministic grid 也是 54 行。
- freeze root：`docs/current/evidence/p3-planning-repeated/2026-08-14-protocol-freeze-v1`。freeze audit 13/13 通过；54 个 run ID 唯一，replicate 集合为 1/2/3；implementation、manifest、schema、evaluator、schedule、prepared input、KG identity 和 model revision 均有 hash。
- conservative token bound 为 `1,666,311`，batch budget 为 `1,700,000`；temperature `0.1`、max output `16384`、retry/repair/salvage/fallback 均为 0/forbidden。
- zero-call preflight root：`D:\code\fusionagent-evidence\p3-planning-repeated\2026-08-14-deepseek-v4-flash-repeated-v1-preflight`。记录 `paid_provider_calls_made=0`、`api_key_configured=false`、`execution_ready=false`；preflight execution commit 为 `559f22d828270b008497738e2f268da7cd43c73e`，worktree clean。

#### E3 确定性结果与独立审计

- 结果：`D:\code\fusionagent-evidence\p3-planning-repeated\2026-08-14-deterministic-repeated-v1.json`；54/54 行、18 个 case-group cells、每个 cell 三次 input hash 和 output hash 完全一致，所有 `pre_fallback_valid=true`。
- 结果 SHA-256：`sha256:17880b3a6e21878e1f0a5292fb5a125feb926367504548689637ae8c80de3e17`；execution commit `559f22d828270b008497738e2f268da7cd43c73e`。
- 独立审计：`D:\code\fusionagent-evidence\p3-planning-repeated\2026-08-14-deterministic-repeated-v1-audit.json`，11/11 checks passed。三组 all-case automatic mean 分别为 fixed `0.729167`、KG-only `0.916667`、rules-only `0.9375`；确定性重复只证明 exact stability，不构成 54 个独立样本。
- 聚焦回归 50 passed；新增确定性 audit 聚焦测试 7 passed；`python -m compileall -q schemas scripts tests` 通过；`git diff --check` 通过。

#### 当前阻断与下一验收点

- 本进程未配置 `OPENAI_API_KEY` 或 `GEOFUSION_LLM_API_KEY`，因此真实 54-call batch 尚未启动；这不是模型、协议或代码失败。
- 计划中的正式输出根 `D:\code\fusionagent-evidence\p3-planning-repeated\2026-08-14-deepseek-v4-flash-repeated-v1` 当前不存在，避免与 preflight 混用。
- 下一验收点：在 clean worktree 与匹配环境中设置 model `deepseek-v4-flash`、base URL `https://api.deepseek.com`、max output `16384`、token budget `1700000` 和 API key，然后对上述正式输出根只执行一次 `scripts/run_research_llm_repeated_formal.py --execute`。任何 fatal failure 按协议停止，不自动重启。
- E3 完成前不启动 E4 人工评价、E5 多 AOI 或 E6 论文图表，不修改 frozen prompt/schema/evaluator/manifest/KG。

### 16.11 执行检查点（2026-08-15，E3/E4 后处理工具就绪）

#### 当前事实

- 2026-08-15 重新核对：正式 worktree clean，HEAD `dd4562bccf0f266e70485534edc217c00632959b`；v2 freeze audit 仍为 13/13 passed，说明新增只读分析代码没有改变 frozen generation path。
- Process/User/Machine 三层仍未配置 `GEOFUSION_LLM_API_KEY` 或 `OPENAI_API_KEY`；正式 54-call 结果根与 manual-review 根均不存在，没有 Provider 调用或人评被提前执行。
- 真实调用闸门保持不变；本检查点不把缺少凭据重解释为实验失败，也不创建空的正式结果根。

#### 新增的 E3 只读分析能力

- 提交 `dd4562b` 新增 `scripts/analyze_research_llm_repeated_formal.py`。它只读取完成或受控中止的正式证据，不修改 result。
- integrity 层重新核对 freeze checks、protocol/schedule/prepared/model-revision semantic hash、execution provider/generation config、implementation ancestry、输入 hash、response model、strict JSON、raw response、zero retry、summary/token 和 schedule-prefix 关系。
- completion 层单独判断 54 个 run 与 18 个 case-condition x 3 repetitions 是否完整；自动 rubric fail 是研究结果，不被当作 evidence-integrity failure。
- stability 层按 cell 输出 plan structure signature hash、decision/task-order agreement、automatic score min/max/range 和 failure class；仅在完整批次上评估预注册扩展闸门。任一失败、多个 structure signature 或 score range >= 0.25 时，只允许通过新协议将所有 cell 扩至 5 次，禁止选择性补跑。
- audit 内置 fixed files 与全部 `result.json` 的 path/size/SHA-256 manifest。相关旧/新分析、协议、runner 和人工评价流水线回归合计 58 passed；`compileall` 与 `git diff --check` 通过。

#### 新增的 E4 工具边界

- `scripts/prepare_research_manual_review.py` 只有在 audit 同时满足 `evidence_integrity_valid=true` 和 `formal_execution_complete=true` 时才生成 packet；因此当前不能运行。
- 生成物固定为两份不可变 reviewer context、两份独立 decisions template、单独 blind key 和 packet manifest。reviewer context 不包含 condition label、run ID、replicate、automatic score、gold rationale 或既有 machine-assisted decision。
- 该设计明确是 label/metadata blinding；可见 KG 内容可能使 reviewer 推断 condition，不虚称完全内容盲法。shuffle seed 只写 manifest，不暴露给 reviewer context。
- `scripts/audit_research_manual_review.py` 验证两位 reviewer ID、context hash、review-record index hash、decision completeness、精确一致率、Cohen's kappa 和逐 rubric item 一致性。分歧原样保留；存在未裁决分歧时 audit 不通过。
- Codex 和脚本不填写 human decision；当前只证明工具合同，不构成人工评价完成证据。

#### 凭据到位后的连续执行链

1. 按 16.10 的冻结环境只启动一次 `scripts/run_research_llm_repeated_formal.py --execute`，输出到 `D:\code\fusionagent-evidence\p3-planning-repeated\2026-08-14-deepseek-v4-flash-repeated-v1`。
2. 若 runner 达到合法终态，运行 `scripts/analyze_research_llm_repeated_formal.py`，将 audit 写为该根下新的 `formal_automatic_audit.json`；若批次不完整，保留 audit 并停止，不生成 review packet。
3. 只有完整 audit 通过后，运行 `scripts/prepare_research_manual_review.py`，输出到新的 `D:\code\fusionagent-evidence\p3-planning-repeated\2026-08-15-manual-review-v1`。
4. 两名独立人工 reviewer 只编辑各自 `reviewer-*.decisions.json`；冻结两份文件后再运行 `scripts/audit_research_manual_review.py`。blind key 在两份人评冻结前不得揭示。
5. E3 extension gate 与 E4 agreement audit 均有终态后，才进入 E5 AOI 资产清点和 case selection；不根据单次高分事后选择 E2E 案例。

### 16.12 执行检查点（2026-08-15，多 AOI 候选宇宙清点完成）

#### E5 候选清点事实与边界

- 候选证据：`D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-15-multi-aoi-candidate-inventory-v1\candidate_inventory.json`，文件大小 `88,350` bytes，SHA-256 `sha256:5cb4f1fe9821cbc575cf3784dab042cc6d29f5759e7531e789d1844b258b032c`。
- 协议为 `fusionagent.p4.multi-aoi-candidate-inventory.v1`，实现提交 `bce1ad7f6c798b3abf91da3bdeb0c1e9995e84d7`；清单完整性、资产存在性、AOI 相交性、几何有效性、可用历史 hash 一致性和 zero-call checks 全部通过。
- 三个已声明 AOI 中，Caracas 对 C01/C02/C04/C05 各自 source-closed；Abidjan 与越南北部沿海走廊均缺少相应 Microsoft building/road 源。四个正式案例的 `source_closed_aoi_count` 均为 `1`，因此 `e5_multi_aoi_source_coverage_ready=false`。
- 当前结论是候选宇宙已审计但没有可选择的双 AOI 正式案例；`claim_eligible=false`、`selection_status=candidate_universe_only_no_case_selected`。不得用历史 P4-G mock 运行补齐跨 AOI，也不得把单 AOI 资产清点写成 external-validity 结果。
- 清单只证明候选可行性，不证明 planning E2E 能力；其 `runtime_calls` 为 `fusion_runs=0, llm_calls=0, provider_calls=0`。该负结果保留进入 E5/E6 的证据索引。

#### 可执行恢复顺序（唯一允许的推进路径）

1. 凭据到位后先在 clean worktree 复查 `OPENAI_API_KEY`/`GEOFUSION_LLM_API_KEY`、model `deepseek-v4-flash`、base URL、temperature `0.1`、max output `16384`、budget `1700000` 和 freeze audit `13/13`；任一不匹配则停止。
2. 仅执行一次 `scripts/run_research_llm_repeated_formal.py --execute` 到既定正式根；不预创建根、不重跑、不 retry。记录 runner 退出码、进程状态和已写入 run 数。
3. 对同一根运行 `scripts/analyze_research_llm_repeated_formal.py`。只有 `evidence_integrity_valid=true` 且 `formal_execution_complete=true` 才允许生成 E4 packet；不完整批次保留原始失败和 audit，终止后续步骤。
4. 生成 packet 后由两名独立 reviewer 完成各自 decisions 文件；冻结文件 hash 后运行 `scripts/audit_research_manual_review.py`。任何缺项或未裁决分歧均保持非终态，不揭盲、不进入 E5。
5. 只有 E3 extension gate 与 E4 agreement audit 都有终态，才重新读取本清单并按预注册规则选择 case-AOI。当前清单无双 AOI 候选时，E5 以“未运行/不可行”终止，不下载新源、不改机制、不复活 C06。
6. E6 只消费冻结 JSON 和审计 manifest，生成 comparison/stability/manual-agreement/E2E outcome/claim-evidence 表；统一 claim audit 必须把跨 AOI 主张标记为 unsupported，除非未来新增来源后形成新的、独立冻结的协议与证据根。

#### 当前阻断

- 本 shell 的 Process/User/Machine scope 仍未配置 `OPENAI_API_KEY` 或 `GEOFUSION_LLM_API_KEY`；因此 E3 真实半段、E4 人评和 E5 runtime 均未执行。这是外部凭据阻断，不是 runner 或候选清点失败。
- 在凭据到位前，允许的工作仅限于只读审计、计划/证据索引维护和测试；不得创建正式结果根或调用 Provider。

### 16.13 执行检查点（2026-08-15，官方 DeepSeek 批次受控不完整）

#### 执行事实

- 本地凭据文件为 `.env.formal.local`，已由 `.gitignore` 明确忽略；忽略规则提交为 `6f5d82c`。key 未写入协议、结果或 Git 追踪文件。
- 正式根：`D:\code\fusionagent-evidence\p3-planning-repeated\2026-08-14-deepseek-v4-flash-repeated-v1`。使用冻结的官方 endpoint/model/revision，runner 付款前 clean-worktree 检查通过，正式调用已实际发生。
- `formal_summary.json`：scheduled `54`，executed `45`，successful `43`，failed `2`，consumed tokens `564012`，`failed_calls_replaced=false`，状态为 `completed_with_observed_failures`。
- 自动审计：`formal_automatic_audit.json`，SHA-256 `sha256:25176b02f9fce8838a0da768760ba809d941df4f76ad6474d053895d01c98388`；`evidence_integrity_valid=true`，但 `formal_execution_complete=false`。
- 两个失败均原样保留：C01 `llm_full_contract_kg-r1` 为 `output_schema_validation_failure`；C05 `llm_capability_kg-r3` 为 `transport_error`（read timeout）。两者均无 retry、repair、salvage 或替换。
- 以下 9 个计划 run 未产生 `result.json`：`formal-v2-c01-llm_only-r3`、`formal-v2-c03-llm_capability_kg-r1`、`formal-v2-c03-llm_capability_kg-r3`、`formal-v2-c04-llm_capability_kg-r3`、`formal-v2-c04-llm_full_contract_kg-r1`、`formal-v2-c05-llm_only-r3`、`formal-v2-c06-llm_capability_kg-r2`、`formal-v2-c06-llm_only-r2`、`formal-v2-c06-llm_only-r3`。

#### 终态与后续闸门

- 本批次是合法的受控不完整证据，不是完整 E3 结果；不得计算 stability/extension gate，不得启动 E4 manual review，不得进入 E5 case selection，也不得把 43/54 当作正式比较样本。
- 下一步只能先定位 runner 为何在 45 个 scheduled items 后正常退出，再制定新 protocol。禁止对这 9 个 run 或 2 个失败 run 做选择性补跑；若要重新获得完整批次，必须新建、重新冻结并一次性执行完整协议。

### 16.14 执行检查点（2026-08-15，v3 完整 54-call 批次）

#### v3 协议与执行

- v3 实现提交 `a1682d7`；freeze 提交 `e95afb1`。协议 `fusionagent.planning-repeated-formal.v3` 使用新的 `formal-v3-*` run IDs、schedule seed `20260815`，明确不与不完整 v2 混池。
- freeze root：`docs/current/evidence/p3-planning-repeated/2026-08-15-protocol-freeze-v3`；15 项 freeze checks 全部通过。Provider/model/revision、prompt/schema/evaluator/manifest/implementation/input hash 与 `1,700,000` token budget 保持原冻结语义，唯一执行参数变化是显式冻结单请求 timeout `600` 秒；transport retries 仍为 `0`。
- zero-call preflight：`D:\code\fusionagent-evidence\p3-planning-repeated\2026-08-15-deepseek-v4-flash-repeated-v3-preflight`；`execution_ready=true`、`paid_provider_calls_made=0`、timeout `600`、54 calls，preflight SHA-256 `sha256:25d8c3ea3284b425be29dc37e01d6e5740e112316b6a78923419c7e586450cdb`。
- 正式根：`D:\code\fusionagent-evidence\p3-planning-repeated\2026-08-15-deepseek-v4-flash-repeated-v3`。`formal_summary.json` 记录 scheduled/executed/successful `54/54/54`、failed `0`、consumed tokens `708460`、zero retry/repair/salvage/fallback、`prior_incomplete_v2_pooled=false`。

#### 自动审计与 extension gate

- `formal_automatic_audit.json` SHA-256 `sha256:3656537a16c1caccf908af2cfa748dd8d3bc77bfe71ee68ea7f1237614ce56ec`；全部 integrity 与 completion checks 通过，`evidence_integrity_valid=true`、`formal_execution_complete=true`。
- 三组 automatic mean：`llm_only=0.923611`、`llm_full_contract_kg=0.909722`、`llm_capability_kg=0.895833`。这些只是自动 rubric 描述性结果；39 个 automatic checks 失败、108 个 manual items 待评，不支持 superiority 结论。
- extension gate 已评估且 `extension_required=true`。C01 三组、C02 三组、C04 capability/LLM-only、C05 三组、C06 capability 出现多个 plan structure signatures；C01/C02 多个 cell 的 automatic score range 为 `0.25-0.50`。
- 按预注册规则，下一步只能通过新协议将全部 `6 cases x 3 LLM conditions` 从 3 repetitions 一致扩展至 5 repetitions；不得只补不稳定 cell。E4 manual packet 延后到 extension 终态，避免对 3-repetition packet 重复人评。

#### 当前下一验收点

- 先新建并冻结 5-repetition extension protocol，新增 repetitions 4/5 共 36 次真实调用，并明确与 v3 的 54 个已冻结 run 组合为每 cell 5 次的分析集合；旧 v2 仍不混池。
- extension freeze/zero-call preflight 完成后需要新的付费执行授权；未授权前不发起额外 36 次调用。

### 16.15 执行检查点（2026-08-15，五次重复扩展与 90-run 自动审计完成）

#### extension 协议与付费执行

- extension 实现提交为 `85a03b681644c77fb1e9ef939cfdfc09348aac89`，freeze 提交为 `1a05417`；协议 `fusionagent.planning-repeated-extension-formal.v1` 只新增全部 18 个 LLM case-condition cells 的 repetitions 4/5，共 36 calls，禁止选择性补跑。
- freeze root：`docs/current/evidence/p3-planning-repeated/2026-08-15-protocol-freeze-extension-v1`。19 项协议检查与 13 项 v3 base binding 检查全部通过；绑定的 v3 audit SHA-256 为 `sha256:3656537a16c1caccf908af2cfa748dd8d3bc77bfe71ee68ea7f1237614ce56ec`，并逐一复核 54 个 base result hash。
- generation 保持官方 `deepseek-v4-flash`、revision `7872f01b1d1fe23eabc4c98b48bffcef5a386062`、temperature `0.1`、max output `16384`、timeout `600` 秒、retry/repair `0`、salvage/fallback forbidden。36-call conservative bound 为 `1,110,874`，batch budget 为 `1,200,000`。
- zero-call preflight root：`D:\code\fusionagent-evidence\p3-planning-repeated\2026-08-15-deepseek-v4-flash-repeated-extension-v1-preflight`；`execution_ready=true`、`base_evidence_binding_valid=true`、`paid_provider_calls_made=0`，preflight SHA-256 为 `sha256:8bc915fdfeb16271994f70e5588b1bd5eb9ff9fa71a8eaa4d769eae95e8f424f`。
- 正式 extension root：`D:\code\fusionagent-evidence\p3-planning-repeated\2026-08-15-deepseek-v4-flash-repeated-extension-v1`。runner 单实例正常退出；scheduled/executed/successful 为 `36/36/36`、failed `0`、consumed tokens `462719`，所有成功响应均为 exact model、strict JSON、transport retry `0`，且未与 v2 混池。

#### extension 与 90-run combined 自动审计

- extension automatic audit 位于正式 extension root 的 `formal_automatic_audit.json`，SHA-256 为 `sha256:7c7b69aed93076ff8d459227633ccf7c069be752fd72b20415f69db0646c9756`；`evidence_integrity_valid=true`、`formal_execution_complete=true`。33 个 automatic rubric failures 与 72 个 manual items 原样保留，不视为 transport/integrity failure。
- combined analysis root：`D:\code\fusionagent-evidence\p3-planning-repeated\2026-08-15-deepseek-v4-flash-repeated-combined-v1`；只读组合 v3 repetitions 1/2/3 与 extension repetitions 4/5，旧 v2 继续排除。
- combined audit `formal_combined_automatic_audit.json` SHA-256 为 `sha256:4bfdc65db36c23d571f28b17f8d9a02db94638e85a4704c1d060092ca585457f`。15 项 integrity checks 与 3 项 completion checks 全部通过；90/90 runs 成功、18 cells 均精确包含 repetitions `{1,2,3,4,5}`、total tokens `1,171,179`、extension gate 状态为 `fulfilled`。
- 五次重复的 all-case automatic mean 为 `llm_capability_kg=0.883333`、`llm_full_contract_kg=0.908333`、`llm_only=0.908333`；排除 C03 后的 positive-case mean 分别为 `0.865`、`0.895`、`0.895`。72 个 automatic checks 失败，17/18 cells 存在多个 plan structure signatures，7/18 cells 的 automatic score range >= `0.25`。这些是描述性稳定性结果，不支持 KG superiority、显著性或广泛外推主张。

#### combined 人工评价准备与当前闸门

- combined manual-review root：`D:\code\fusionagent-evidence\p3-planning-repeated\2026-08-15-manual-review-combined-v1`；packet ID 为 `packet-dc1cf0ac217aff3d7c3d`，source audit hash 与 combined audit 一致，共 180 items。
- 两份 reviewer context 各 180 records；顶层 condition、run ID、replicate 与 automatic score 已移除。两份 decisions template 的 180 个 decision 均为 `null`，Codex 未填写或冒充 human rating。packet manifest SHA-256 为 `sha256:16e8e2541c91571e71c69cf79861f1dcf077f8584b396297e98c062d8b3584ab`。
- 当前阶段进入 E4 外部人工评价：必须由两名独立 reviewer 分别完成 `reviewer-a.decisions.json` 与 `reviewer-b.decisions.json`，冻结两份文件 hash 后才能运行 agreement audit 和揭盲。任何缺项或分歧都保留；不得根据 automatic score 引导 reviewer。
- E5 多 AOI 仍受 16.12 的 source coverage 事实约束：当前没有双 AOI source-closed case，因此以不可行负结果保留，不用 mock 或临时新增来源补齐。E6 可继续生成标记为 pending-human-review 的自动描述表和 evidence index，但论文 comparative claim 在 E4 终态前保持 `not ready`。
