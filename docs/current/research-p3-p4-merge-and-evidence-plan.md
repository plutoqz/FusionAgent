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
