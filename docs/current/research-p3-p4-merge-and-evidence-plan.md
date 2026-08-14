# P3-P/P4-P 研究归并与证据冻结计划

状态：五项实验语义已讨论确定；本文是实施入口，不是正式运行协议。正式协议、模型、重复次数和预算须在真实 LLM pilot 通过后另行冻结。

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
