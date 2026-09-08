# 三种 LLM-KG 协作方式实施方案

> 状态：A1 实施方案草案（未授权执行）
> 版本：`method-selection-implementation-plan.v1`
> 更新日期：2026-09-01
> 研究口径：[`research-charter.md`](research-charter.md)
> 方法选择规则：[`method-selection-protocol-v1.md`](method-selection-protocol-v1.md)
> 平台依赖：[`benchmark-platform-implementation-protocol.md`](benchmark-platform-implementation-protocol.md)

## 1. 目标与边界

### 1.1 目标

在不预设某种协作方式优越的前提下，建立一套可复现、可审计的六组规划实验，并在三种 LLM 条件完成同口径比较后选择后续研究采用方式：

```text
固定工作流 / 规则 / KG-only
            +
LLM-only / LLM + capability KG / LLM + full-contract KG
            -> 产品契约评价
            -> 分层机制评价
            -> 预注册方法选择
            -> 选择性 E2E 与论文主方法
```

### 1.2 非目标

- 本方案不改变 A0 研究主体、RQ1-RQ4 或 I1-I4。
- 不把 `llm_full_contract_kg` 预设为冠军。
- 不把三种 LLM 条件合并成一个“LLM+KG”黑盒组。
- 不把选择集上的最高分直接写成普遍优越性。
- 不在本方案阶段生成 confirmation 实例、调用 Provider/judge 或运行 E2E。
- 不重写冻结的 Benchmark V1、平台 core V1、历史 evidence root 或 KG v1。

## 2. 最终交付物

| 编号 | 交付物 | 内容 | 完成判据 |
| --- | --- | --- | --- |
| D1 | 方法选择协议 | 三条件定义、选择顺序、等价 margin、胜者/平局语义 | 机器字段和文字规则一致，独立复核无分歧 |
| D2 | 模板与 oracle 包 | 高难度场景模板、变量域、约束、候选行动、veto、合法计划集合 | schema、crosswalk、oracle 可解，历史语义同构排除 |
| D3 | canonical context 与 projection | 同一 KG/context 的六组可见视图及 hash | 六组 allowlist、禁止字段、投影 hash 可复算 |
| D4 | 实验运行合同 | 六组、seed、重复、预算、失败和 evidence root | 运行前冻结，三 LLM 条件仅知识视图不同 |
| D5 | 自动评价与人工盲评包 | pre-fallback、契约向量、关系单元、人工 rubric 和裁决规则 | 不读取 evaluator-only 字段，失败不被 fallback 覆盖 |
| D6 | 选择结果与采用记录 | 选择集排名、Pareto/平局、method identity 和选择理由 | 可回链到 protocol、manifest、原始响应和审计报告 |
| D7 | 选择性 E2E 证据 | source-closed AOI、执行、质量、交付和 evidence | 只使用预注册选例，不以结果替换案例 |

## 3. 总体架构

```text
Case / template
  -> KGRepository + policy registry
  -> CanonicalContextFactory
  -> ProjectionRegistry
       | fixed_workflow
       | rules_only
       | kg_only
       | llm_only
       | llm_capability_kg
       | llm_full_contract_kg
  -> planner / deterministic baseline
  -> pre-fallback validator
  -> ContractSatisfactionEvaluator
  -> relation evaluator
  -> blinded human packet
  -> evidence freezer
  -> SelectionEngine
```

设计原则：所有条件从同一 canonical context 派生；条件差异只能出现在已登记的可见知识投影和决策机制。`gold`、`oracle`、`veto`、自动分数和 condition label 始终属于 evaluator-only 或 human-blind 之外的隐藏域。

## 4. 实施阶段

### P0：基线与授权审计

**动作**

1. 建立独立短期实现分支和 worktree，不在 `main`、formal、method 或 confirmation checkpoint 上直接修改。
2. 记录 branch、commit、Python/依赖、KG release、平台 core tag、工作树状态和零调用计数。
3. 核对冻结输入：研究章程、Benchmark V1、平台合同、KG v1、选择协议。
4. 确认输出根不存在或为空，禁止覆盖历史证据。

**验收**

- 研究口径和依赖哈希可复算；
- 工作树干净；
- Provider、judge、实例和正式结果计数为 0；
- P0 失败时不创建任何实验产物。

### P1：canonical context 与 KG crosswalk

**动作**

1. 新增 `CanonicalContextFactory`，从 `KGRepository`、`KnowledgePolicyRegistry` 和 case observation 生成唯一上下文。
2. 上下文必须包含 `kg_release_id`、semantic hash、contract ID、scenario ID、task/source/algorithm/policy ID 和 observation hash。
3. 建立 `case-to-KG crosswalk`，对未知或不支持对象返回 `unsupported`，禁止 Python alias、默认值或静默替换。
4. 记录 selected、resolved、executed、evaluated 四个决策状态及其来源。

**建议文件**

```text
benchmark_platform/context.py
benchmark_platform/crosswalk.py
schemas/benchmark_method_selection.py
tests/test_method_selection_context.py
```

**验收**

- 同一输入跨进程生成相同 context/hash；
- 修改 KG 测试副本可改变 projection 输入；
- 缺失 KG ID、错误 release、未闭合 contract 均 fail closed；
- 无第二份静态算法、源或质量策略目录。

### P2：六组 projection registry

**动作**

为同一 canonical context 建立显式 allowlist：

| 条件 | 允许可见信息 | 禁止可见信息 |
| --- | --- | --- |
| `fixed_workflow` | 冻结 workflow 接口 | gold、LLM、动态 KG 结果 |
| `rules_only` | request、observable facts、`rules.general.v1` | KG query result、LLM |
| `kg_only` | request、observable facts、KG query result | LLM、gold |
| `llm_only` | request、observable facts、output schema | KG projection、gold |
| `llm_capability_kg` | LLM-only + capability projection | full contract、gold |
| `llm_full_contract_kg` | LLM-only + 冻结 full-contract projection | gold、自动分数 |

三种 LLM 条件共享模型、system prompt、output schema、temperature、max tokens、timeout、重试和 repair policy。

**验收**

- 每组生成 `visible_fields.json`、`forbidden_fields.json`、`projection_trace.json` 和 projection hash；
- 递归泄漏审计为 0；
- rules-only 不调用 KG repository；KG-only 不调用 LLM；
- full-contract projection 只能使用 development 阶段冻结的接口版本。

### P3：高难度模板与 oracle

**动作**

创建 10-15 个代表性模板族，覆盖：

- 建筑、道路、水体面、水系线、POI 五类产品；
- required/optional/skip、priority、deadline、quality、evidence、delivery level；
- source available/late/absent/partial/stale/semantic mismatch/access failure；
- 网络正常/受限/不可用，时间宽松/紧张；
- acquisition、schema、type、semantic、algorithm、quality gate、evidence、delivery 故障；
- 无历史、provisional 已交付、quality failed、source veto、等待 supersession；
- 同义改写、输入顺序、无关噪声、多任务组合和跨任务污染。

每个模板必须定义：变量域、合法组合约束、状态转移、候选行动、产品契约、oracle、veto、覆盖标签和难度等级。oracle 使用有限状态约束求解，输出合法计划集合、最优/Pareto 集合、必须/禁止行动、正确交付状态、gap/degraded/supersession 和 proof，而非单一字节答案。

**生成规则**

1. 普通变量至少达到 1-way 全覆盖，关键交互达到 pairwise 或 3-wise；
2. 关键规则进行 MC/DC 覆盖；
3. causal pair 只改变一个 causal variable；invariant set 只改变 nuisance variable；
4. canonical signature 去除语义同构；
5. 每个实例记录 coverage credit，replicate 与新语义案例分开统计；
6. 先生成 development 候选，再用 set-cover 选择正式案例，不根据方法分数排除。

**验收**

- oracle 对全部合法模板可解；
- 典型错误计划至少触发一个明确 veto；
- 每个 capability cell、gap、veto、delivery state 和 transition 至少有正反实例；
- C01-C06、H01-H09 及语义同构副本全部排除新 confirmation。

### P4：本地离线生成与评价闭合

**动作**

1. 复用平台 core V1 的 closed models、canonicalization、relations、views、store 和 checkpoint；必要时创建 V2 协议，不修改 V1 冻结包。
2. 生成 development corpus 和 `generation_attempts.jsonl`，保留无效候选、原因和 hash。
3. 为每个 unit 运行 oracle solver、自动 evaluator 和 leakage audit。
4. 生成人工盲评 packet；planner 不可看到 oracle、veto 解释和 expected consequence。

**验收**

- 重复离线运行的实例 ID、canonical payload 和 hash 一致；
- 无效生成保留但不计入有效样本；
- evaluator 只读 gold/oracle，planner 只读允许视图；
- 自动评价、人工评价和 E2E 指标分开记录。

### P5：development 接口筛选与方法冻结

**动作**

在 development 数据上比较 full-contract 的 raw full KG、task-conditioned typed projection 和 capped query-on-demand 候选。该步骤只筛选**接口工程版本**，不决定三种 LLM 条件的效果冠军。

按以下顺序审查接口：

1. KG identity、crosswalk、grounding 和 fail-closed；
2. token、latency、内存和实现复杂度；
3. contract/capability 信息完整性与可解释性；
4. development 中的稳定性与 evidence trace。

冻结内容：`method_commit`、projection allowlist、KG release、prompt/schema hash、预算、repair policy、接口 hash 和 protocol hash。

**停止条件**

- 任一接口不能闭合 KG crosswalk；
- 接口依赖未登记的 Python 规则；
- 只能通过 fallback 掩盖原始规划失败；
- 不同接口的 token/信息边界无法公平比较。

### P6：选择集与独立 confirmation

**动作**

1. 将新模板划分为 `selection` 和 `confirmation`，使用不同 seed namespace、instance ID namespace 和 evidence root。
2. 六组全部运行；三种 LLM 条件不得缺席或提前停止。
3. 记录原始响应、失败、pre-fallback validity、契约向量、机制单元、人工盲评、成本和证据 hash。
4. 全部运行与评价结束后，执行 SelectionEngine，按方法选择协议的字典序规则输出冠军、Pareto 集或无胜者。

**验收**

- 不存在基于结果的案例替换、补跑、改 oracle 或改 metric；
- 安全硬门、契约满足度、机制覆盖、效率和复现指标均有逐条件表；
- 选择结果可以回链到 selection evidence root；
- 若没有独立 confirmation，报告标为探索性选择。

### P7：选择后的 E2E 与论文证据

**动作**

1. 仅将选定方式作为后续 RQ4 selective E2E 的默认配置；其他条件继续保留为比较基线。
2. 只选择 source-closed、质量/真值可评价、有明确 failure opportunity 的 AOI 和模板。
3. 验证 materialization、algorithm execution、quality gate、delivery state、gap、supersession 和 evidence completeness。
4. 生成 claim-evidence index，分别绑定 planning、execution、quality、external validity 和 I4 证据。

**验收**

- 选择集与 E2E 结果不混池；
- E2E 不改变既定选择规则；
- 每个论文数字可回链到原始 run、manifest、commit、KG release 和 artifact hash；
- 结论只使用与证据等级相称的限定表述。

## 5. 一周实施节奏

本节是交付排序，不代表自动授权真实实验。

| 日期 | 目标 | 交付 | 当日停止条件 |
| --- | --- | --- | --- |
| 9/1 | 基线与权威核对 | P0 清单、版本表、方法选择协议审查稿 | 权威文档或 KG identity 不一致 |
| 9/2 | context/crosswalk | canonical context schema、crosswalk 表、字段 allowlist | 出现第二知识真源或未知 ID 静默替换 |
| 9/3 | 模板/oracle | 10-15 个模板族设计、约束和 oracle proof 草案 | oracle 不可解或与历史案例同构 |
| 9/4 | projection/评价 | 六组 projection、leakage audit、metric/rubric/evidence manifest | 组间信息边界无法证明公平 |
| 9/5 | development preflight | 零调用生成/关系/覆盖/去重审计报告 | 生成器产生不可复现 ID 或覆盖不足 |
| 9/6 | 选择协议冻结候选 | selection/confirmation 划分、seed、margin、停止规则 | 选择规则依赖结果或未保留失败语义 |
| 9/7 | 独立复核与决策包 | review report、变更清单、授权请求包 | 存在未解决协议分歧；不进入 Provider |

本周“显著成果”的定义是：形成可复核的模板、oracle、六组信息边界和方法选择冻结候选，而不是提前制造方法效果结论。

## 6. 文件与分支变更边界

### 允许新增或修改

```text
docs/current/method-selection-implementation-plan-v1.md
docs/current/method-selection-protocol-v1.md
docs/current/research-governance-index.md
docs/current/research-experiment-ledger.md
benchmark_platform/context.py              # 进入实施阶段后
benchmark_platform/projections.py          # 进入实施阶段后
benchmark_platform/oracle.py               # 进入实施阶段后
benchmark_platform/selection.py            # 进入实施阶段后
schemas/benchmark_method_selection.py      # 进入实施阶段后
tests/test_method_selection_*.py           # 进入实施阶段后
```

### 本方案阶段禁止触碰

- `kg/ontology/v1.0.0/` 冻结内容；如需语义变化，另建 KG v1.1 方案。
- 历史 formal/method/confirmation evidence root 和原始响应。
- `schemas/benchmark.py` 旧 Freeze B 合同。
- Planner、Provider、Prompt、质量服务和执行服务的生产路径。
- `requirements.txt`、部署配置和前端。

## 7. 验收矩阵与回滚

| Gate | 证明内容 | 必需证据 | 回滚方式 |
| --- | --- | --- | --- |
| `MS0` | 基线和权威身份一致 | manifest、hash、branch audit | 删除未发布分支/worktree，不触碰历史 |
| `MS1` | context/crosswalk 单一真源 | schema、crosswalk、tamper tests | 保留失败记录，回到文档设计 |
| `MS2` | 六组投影隔离 | allowlist、projection hash、leakage report | 废弃当前 draft，升 protocol 版本 |
| `MS3` | 模板和 oracle 可解 | template audit、solver proof、coverage report | 仅替换未执行候选，保留旧 hash |
| `MS4` | 离线生成可复现 | repeated run、store/checkpoint、relation audit | 删除未发布 development root，不删除失败记录 |
| `MS5` | 选择规则可执行 | selection dry-run、tie/Pareto report | 不选冠军，记录 blocker |
| `MS6` | 独立复核通过 | review record、diff、decision log | 保持 `not_authorized`，创建修订版本 |

任何阶段失败均不得通过放宽 schema、oracle、veto、分母、停止规则或 fallback 掩盖；已产生的失败和无效尝试必须保留。

## 8. 启动与停止闸门

### 进入真实实施前必须满足

- 本方案和方法选择协议通过独立审查；
- 下一版本 template/development 协议单独冻结；
- 实现分支、KG release、模板、oracle、evaluator 和 selection hash 已绑定；
- development/selection/confirmation evidence root 互斥；
- 用户明确授权进入实现或 Provider 阶段。

### 以下情况立即停止

- 发现文档权威冲突、KG crosswalk 未闭合或第二知识真源；
- 发现 planner 可见 gold、oracle、expected decision 或自动分数；
- 发现三种 LLM 条件的模型、prompt、预算或失败规则不一致；
- 发现案例在看过结果后被替换、补跑或改变 oracle；
- 输出根已存在、输入 hash 漂移或需要覆盖历史产物；
- Provider、judge、网络数据源或真实 E2E 被未授权调用。

## 9. 预期论文表述路径

| 完成状态 | 允许写法 |
| --- | --- |
| 仅 MS0-MS4 | “建立了可复现、可审计的六组规划实验与参数化案例基础设施。” |
| 完成 development 接口冻结 | “在 development 条件下固定了 full-contract KG 的接口实现版本。” |
| 完成选择集 | “三种 LLM 协作方式在预注册选择集上的相对表现为……，据此选择 X 作为后续默认配置；该选择是探索性的。” |
| 独立 confirmation 复现 | “在限定案例、模型、KG release 和协议下，X 相对比较条件表现出受限、可重复的优势。” |
| selective E2E | 在上述表述后增加 AOI、数据源、质量、交付和故障边界，不将 planning 结果替代 execution 证据。 |

## 10. 当前状态

当前阶段为 `development_member_materializer_pending_semantic_revision`：

- v2 candidate 语义、契约、数组化多任务扩展和五产品模板包已完成机器审计；
- 15 个 base template snapshot、6 个 v2 extension envelope、15 个 oracle proof 和计划绑定已生成；
- `35 passed` 聚焦回归通过，冻结 v1、KG v1、Provider/judge、实例和正式结果根均保持不变；
- authoring fixture hash 明确不是 live GIS artifact，L4 eligibility 也不代表真实 E2E 能力；
- member materializer 已实现并接入 generator，但 package audit 仅有 9/15 族可物化；6 族因 v1 proxy causal 字段或 causal/invariant/source-role 变量重叠而 fail-closed，模板包仍不是完整可运行 benchmark corpus；
- materializer audit 为 `passed_with_semantic_blockers`，仅在内存中生成候选成员，不创建 run root 或 instances.jsonl；Provider/judge、confirmation/selective E2E 仍保持封锁。

下一验收点：用户决定是否为 15/12 分母、三个 proxy 族补充显式 v2 payload 字段、修复变量角色重叠并补齐 evidence causal 域；完成后再复核 materializer audit，才可授权 development instance generation。
