# FusionAgent 参数化 Benchmark 设计冻结执行方案

> 状态：A1 active execution plan
> 版本：1.0.0
> 制定日期：2026-08-19
> 当前目标：完成 `P-BENCH-DESIGN` 零调用设计冻结
> 下一重大里程碑：`M-BENCH-DESIGN-FREEZE-V1`
> 当前执行入口：[`research-governance-index.md`](research-governance-index.md)
> 当前主张状态：[`research-claim-evidence-ledger.md`](research-claim-evidence-ledger.md)
> 当前实验状态：[`research-experiment-ledger.md`](research-experiment-ledger.md)

## 1. 计划用途与授权边界

本文把当前唯一下一验收点拆成可逐步恢复、逐阶段验收的执行流程。本文被提交、合并或引用，只表示执行方案已建立，不表示已经授权开始平台实现、调用 LLM judge、调用 Provider、生成正式实验结果或修改 KG 语义。

未来执行必须从阶段 0 开始。用户说“继续”时，只推进到当前阶段的下一验收点；用户明确说“开始实施”或等价指令后，才能创建执行分支并修改本计划列出的设计资产。

本计划终止于设计冻结，不跨入 `P-BENCH-JUDGE`、`P-BENCH-FORMAL` 或 `P-BENCH-E2E`。

## 2. 里程碑定义

### 2.1 目标

冻结一套参数化、分层、可诊断的 benchmark 设计，使后续实验能够检验知识图谱条件是否对合同、数据源、失败状态和任务组合的变化作出正确、稳定且可解释的响应，而不是继续围绕少量已观察案例追求更高平均分。

### 2.2 完成条件

只有以下条件全部满足，才可标记 `M-BENCH-DESIGN-FREEZE-V1=complete`：

1. benchmark charter、能力矩阵、template schema、评价合同和选择治理五项资产均已冻结。
2. 五项资产都映射到现有 O/RQ/I/Claim ID，不创建新的论文主线或“第七种方法”。
3. C01-C06、H01-H06、H07-H09 被明确登记为已观察材料，不进入新正式确认集。
4. development、confirmation、selective E2E 三类集合的生成、隔离、停止条件和禁止复用规则已机器可读。
5. 每个 template family 都能定位被检验能力、允许变化、禁止变化、oracle、veto、KG crosswalk 和失败归因层。
6. 评价合同明确 pre-fallback 结果、成对实验单元、主指标、人工 rubric 和 LLM judge 的非正式角色。
7. 冻结 manifest 记录所有输入文件、版本和 SHA-256；独立 audit 全部通过。
8. 本里程碑期间 Provider 调用数为 0，新正式实验结果根数量为 0，KG 语义版本未变化。
9. 人工协议复核完成；未解决分歧为 0，或被显式记录为阻塞并停止冻结。
10. Git 工作树干净，冻结 commit 已推送；冻结后任何语义修改必须产生新版本。

### 2.3 不属于本里程碑

- 不实现案例生成平台、Web UI、自动 judge 服务或调度系统。
- 不调用真实模型、mock 模型或外部 Provider。
- 不生成 development、confirmation 或正式 benchmark 实例。
- 不执行原六组、方案 B、E2E 或跨 AOI 实验。
- 不补做原六组 180-item 双人盲评；该工作仍按 `E-RQ3-MANUAL-180` 独立管理。
- 不修改 `kg/ontology/v1.0.0/`、Planner、projection、validator、Prompt 或历史 evaluator。
- 不重写既有 protocol、manifest、原始响应、人工决策或 evidence root。
- 不预设 KG、方案 B 或完整方法应当获胜。

## 3. 事实基线、假设与待验证项

### 3.1 已确认事实

1. 原六组仍是 RQ3 主实验：fixed workflow、rules-only、KG-only、LLM-only、LLM + capability KG、LLM + full contract KG。
2. 方案 B 只是 I2/RQ3 的 KG-LLM 接口消融，不是第七组主方法。
3. C01-C06、H01-H06、H07-H09 均已被观察，不能作为新 benchmark 的独立确认实例。
4. 原六组 90 次真实 LLM 调用已完成，但 180-item 双人盲评未闭环，比较性主张仍为 `pending_human_review`。
5. H07-H09 的人工结果中，方案 B 与 raw Full KG 均为 `21/21`；方案 B superiority 未被确认。
6. C04、C02、C06 的现有端到端证据分别是单 AOI bounded observation、fail-closed observation 和 negative result，不支持方法级或跨 AOI 结论。

### 3.2 待验证假设

1. 参数化反事实和不变性模板能够比固定故事案例更准确地定位 KG、projection、planning、validator 或 execution 缺陷。
2. template-level oracle 与 veto 可以在不泄露 gold reasoning 的前提下支持确定性 gate 和盲评。
3. 分层复杂度能够区分单任务因果响应、多任务组合、时序恢复和选择性 E2E 资格。

这些假设在本里程碑只被转化为可检验设计，不被宣布为成立。

## 4. 主张与设计单元矩阵

| Candidate Claim ID | 服务 O/RQ/I | 要检验的主张 | 比较对象 | 主要实验单元 | 本里程碑证据 |
| --- | --- | --- | --- | --- | --- |
| `CL-BENCH-CAUSAL` | O2/O3, RQ2/RQ3, I2 | 方法能对 contract/source/failure 单变量变化作出正确因果响应 | 同模板的成对反事实实例 | counterfactual pair | template/oracle 设计，不是效果结果 |
| `CL-BENCH-INVARIANT` | O3, RQ3, I2 | 方法对措辞、输入顺序和无关噪声保持语义稳定 | 同语义的扰动实例 | invariant pair/set | invariant 定义与指标合同 |
| `CL-BENCH-COMPOSE` | O2/O3, RQ2/RQ3, I2 | 多任务合同和 source state 不发生跨任务污染 | 单任务与组合任务模板 | composition family | task-local oracle 与污染 veto |
| `CL-BENCH-RECOVERY` | O4, RQ4, I3 | recovery replan 保留失败历史、合法 source 和 delivery state | 初始状态与时序失败状态 | temporal pair/trace | 时序状态 schema 与 E2E 资格规则 |
| `CL-BENCH-DIAG` | O2/O3/O4, RQ2/RQ3/RQ4, I2/I3/I4 | 失败能归因到明确能力层 | 不同注入位置和失败类型 | capability x mechanism cell | 失败分类与证据字段合同 |

正式效果主张仍需后续真实运行、人工评价和选择性 E2E；本表不能用于升级当前 claim status。

## 5. 冻结产物合同

执行阶段使用独立目录 `docs/current/benchmark/v1/`，至少生成：

| 产物 | 格式 | 作用 |
| --- | --- | --- |
| `README.md` | Markdown | 版本入口、资产关系和非主张 |
| `benchmark_charter.md` | Markdown | 目标、非目标、集合边界、方法角色和成功/证伪条件 |
| `capability_matrix.json` | JSON | claim、能力层、机制族、复杂度、陷阱和证据需求矩阵 |
| `template.schema.json` | JSON Schema | 参数化模板、变量、oracle、veto、crosswalk 和 provenance 合同 |
| `evaluation_contract.json` | JSON | gates、指标、实验单元、失败分类、统计和成本口径 |
| `human_review_rubric.md` | Markdown | 双盲人工评价、分歧与裁决规则 |
| `selection_governance.json` | JSON | partition、seed、实例生成、停止条件和禁止选例规则 |
| `freeze_manifest.json` | JSON | 文件版本、SHA-256、Git/KG 身份和零调用声明 |
| `freeze_audit.json` | JSON | 机器审计结果与里程碑状态 |

允许新增一个只读、零网络的审计器及其聚焦测试：

- `scripts/audit_benchmark_design_freeze.py`
- `tests/test_benchmark_design_freeze.py`

该审计器只能解析、交叉引用和计算哈希，不能生成案例、调用模型、连接 Provider 或修改冻结输入。

## 6. 全局不可变约束

1. A0 研究章程不变；任何无法映射到现有 O/RQ/I 的内容退出当前计划。
2. 原六组身份不变；方案 B 固定为内部接口消融。
3. 输入信息边界必须按方法条件定义，gold、oracle、veto 和自动得分不得暴露给 planner。
4. planning、execution、quality、external validity 指标分层记录，不得互相替代。
5. 自动 evaluator 和 LLM judge 不能单独把主张升级为 `supported_bounded`。
6. 正式实验必须保留 pre-fallback 失败；应用 fallback 不能覆盖实验失败。
7. 所有引用的 KG ID、source ID、contract ID 和 delivery state 必须可 crosswalk；缺失时 fail closed。
8. 已冻结文件不得原地改写；语义变化创建 `v1.1` 或 `v2`，并保留迁移说明。

## 7. 阶段总览

| 阶段 | 目标 | 主要产物 | 阶段验收点 |
| --- | --- | --- | --- |
| 0 | 建立干净、可恢复的执行基线 | kickoff record、输入哈希、独立分支 | `G0-BASELINE-READY` |
| 1 | 冻结 benchmark charter | `benchmark_charter.md` | `G1-CHARTER-FROZEN` |
| 2 | 冻结能力矩阵 | `capability_matrix.json` | `G2-MATRIX-FROZEN` |
| 3 | 冻结参数化 template schema | `template.schema.json` | `G3-SCHEMA-FROZEN` |
| 4 | 冻结评价合同与人工 rubric | `evaluation_contract.json`、`human_review_rubric.md` | `G4-EVAL-FROZEN` |
| 5 | 冻结选择治理 | `selection_governance.json` | `G5-SELECTION-FROZEN` |
| 6 | 交叉审计并冻结设计包 | manifest、audit、提交与标签 | `M-BENCH-DESIGN-FREEZE-V1` |

任一阶段未通过时，不进入下一阶段。

## 8. 阶段 0：执行基线与恢复点

### 阶段目标

从当前治理 checkpoint 创建独立设计分支，证明没有混入历史工作树改动、Provider 调用或实验结果。

### 依赖

- 当前治理提交已推送。
- `main`、formal、method、confirmation checkpoint 不被改写。
- 当前服务和实验进程不存在待完成写入；若存在，只读记录后暂停。

### 允许修改

- 新建 `codex/benchmark-design-r1` 及独立 worktree。
- 新增 `docs/current/benchmark/v1/` 下的设计文件。
- 后续阶段允许的审计脚本、测试和 A1 索引更新。

### 明确非目标

- 不合并 formal/method/confirmation 分支。
- 不修改 `main`、KG、运行代码或历史 evidence。
- 不执行任何模型或实验 runner。

### 执行动作

1. 拉取并清理远程引用，不改写历史：

   ```powershell
   git -C D:\code\FusionAgent fetch origin --prune
   git -C D:\code\FusionAgent worktree add `
     D:\code\FusionAgent-benchmark-design `
     -b codex/benchmark-design-r1 `
     origin/codex/research-governance-r1
   ```

2. 记录 `git status --short --branch`、`git rev-parse HEAD`、`git worktree list --porcelain`。
3. 计算 A0/A1 输入文件和 `kg/ontology/v1.0.0/release.json` 的 SHA-256。
4. 检查目标目录不存在，避免覆盖旧冻结包。
5. 建立 kickoff record，记录当前目标、阶段、下一验收点和可恢复检查点。

### 最小验证集

```powershell
git status --short --branch
git diff --check
git merge-base --is-ancestor origin/codex/research-governance-r1 HEAD
Test-Path docs/current/benchmark/v1
```

### 验收标准

- 新 worktree 干净，HEAD 精确继承已推送治理 checkpoint。
- 目标目录此前不存在。
- 输入哈希完整；未记录或输出任何 API key 值。
- Provider 调用、judge 调用和新实验结果均为 0。

### 回滚与恢复

- 创建资产前失败：删除未使用的新 worktree/本地分支，远程 checkpoint 不动。
- 创建资产后失败：保留未提交工作树，写入阶段检查点；不得把半成品标记为 frozen。
- 发现基线变化：停止并重新核对差异，不自动 rebase 或混合旧结果。

## 9. 阶段 1：Benchmark Charter

### 阶段目标

冻结 benchmark 服务的研究主张、非目标、方法角色、集合边界、成功条件和证伪条件。

### 输入

- `research-charter.md`
- `research-claim-evidence-ledger.md`
- `research-experiment-ledger.md`
- C01-C06、H01-H06、H07-H09 的历史角色

### 执行动作

1. 为五个 `CL-BENCH-*` 候选主张逐项登记 O/RQ/I 映射。
2. 固定原六组的角色和相同模型条件；方案 B 单独登记为接口消融。
3. 定义三类未来集合：development、independent confirmation、selective E2E。
4. 列出禁止进入 confirmation 的所有已观察 case ID 和模板语义。
5. 为每项主张写出：支持条件、证伪条件、允许结论、禁止结论。
6. 明确统计单元是 pair、template family 或 trace，不把重复行当独立案例。
7. 冻结本 milestone 的零调用和不实施边界。

### 验收标准

- 五项候选主张全部映射到既有 O/RQ/I。
- 六组主实验与方案 B 的身份无歧义。
- development/confirmation/E2E 集合互斥规则完整。
- 每项主张都有可观察的失败条件，不使用“效果更好”等不可证伪措辞。
- 不包含预设获胜方向、目标分数或事后选例空间。

### 退出与恢复

- 若需要改变 A0、RQ 或创新点：停止阶段，提交方向变更讨论，不继续写 matrix。
- 若某候选主张无法形成明确实验单元：降为 backlog，不为凑齐五项制造指标。
- 通过后提交阶段 checkpoint；后续不得在不升版本的情况下改变集合边界。

## 10. 阶段 2：案例能力矩阵

### 阶段目标

把主张拆成可覆盖、可诊断的 capability x mechanism x complexity 矩阵，不生成具体实例。

### 必须覆盖的维度

- 能力层：KG、projection、planning、validator、execution/evidence。
- 机制族：contract precedence、source availability、unsupported request、task composition、delivery state、quality failure、recovery history、irrelevant noise。
- 复杂度：L0 单任务基线、L1 单变量因果、L2 多任务组合、L3 时序恢复、L4 selective E2E eligibility。
- 陷阱：first-task bias、跨任务污染、无效 source、隐藏 fallback、gold leakage、顺序敏感、错误 delivery state、伪造 failure cause。
- 证据类型：deterministic gate、pair relation、human review、execution artifact、quality report。

### 执行动作

1. 为每个 matrix row 分配稳定 `capability_cell_id`。
2. 关联一个 `CL-BENCH-*`、一个主要能力层和一个失败归因层。
3. 定义适用复杂度、必要 template family 和预期 evidence type。
4. 标记正向、负向/veto、counterfactual、invariant 或 temporal 角色。
5. 登记与历史案例的语义相似性风险，禁止简单改名复用。
6. 为潜在 E2E 单元增加 source-closed、truth 可用和成本资格字段，但不选择具体案例。

### 验收标准

- 五个候选主张各由至少两个不同机制族覆盖。
- 每个能力层至少存在一个可被明确判失败的 cell。
- 因果主张有 counterfactual pair；稳定性主张有 invariant pair/set；恢复主张有 temporal trace。
- 每个 cell 只有一个主要归因层，次级风险单独列出。
- 所有历史案例均被标记为 development/historical reference，confirmation 复用数为 0。

### 回滚与恢复

- 发现 cell 同时改变多个因果变量：拆分或删除，不进入 schema 阶段。
- 发现能力无法由 planning-only 观察：标记为 E2E-only，不用 proxy 指标替代。
- matrix 扩张超过已冻结主张：进入 backlog，不扩大当前 milestone。

## 11. 阶段 3：参数化 Template Schema

### 阶段目标

冻结 template 的机器合同，使后续实例生成能够区分语义不变量、因果变量、干扰变量、oracle、veto 和信息边界。

### 必需字段组

1. 身份：schema/template family/version/claim/capability cell。
2. provenance：authoring source、KG release、contract version、生成规则版本。
3. task state：灾害、AOI role、task set、contract、source state、failure history、delivery state。
4. variables：`causal_variables`、`invariants`、`nuisance_variables`，每项带类型、域和允许变化。
5. oracle：必须满足、允许多解、顺序/状态关系和 evidence requirements。
6. veto：禁止行为、unsupported 条件、非法 source、信息泄漏和错误 fallback。
7. crosswalk：所有 KG/source/contract/algorithm ID 及其验证规则。
8. views：planner-visible input、evaluator-only gold、human-review blind packet。
9. partition：development/confirmation/E2E eligibility 和禁止复用来源。
10. hashing：canonical serialization、实例 ID 和内容哈希规则。

### 执行动作

1. 使用关闭式 JSON Schema；未知关键字段默认拒绝。
2. 定义单变量 counterfactual 约束，禁止 pair 内隐式改变无关字段。
3. 定义 invariant perturbation 只允许改变措辞、顺序或显式噪声字段。
4. 定义多任务 task-local namespace，防止第一任务上下文污染其他任务。
5. 定义 recovery trace 的事件顺序和 observable runtime facts 优先级。
6. 将 oracle/gold 与 planner-visible view 结构隔离。
7. 定义无答案、正确拒绝、partial、provisional、degraded 和 supersession 的合法表达。

### 验收标准

- schema 自身可解析，并能拒绝未知顶层关键字段。
- 每个 matrix cell 都能映射到 schema 字段，不依赖自由文本补充关键语义。
- planner-visible view 不包含 gold、自动得分、预期 decision 或 evaluator-only veto 解释。
- crosswalk 缺失、非法 state transition 和 pair 多变量漂移能够 fail closed。
- schema 不包含模型、Provider、预算或结果方向的临时硬编码。

### 回滚与恢复

- 如需修改 KG 语义才能表达模板：停止并登记 KG v1.1 候选，不在当前阶段改 KG。
- 如 schema 只能通过案例特判表达某机制：回到能力矩阵调整抽象，不添加 case ID 分支。
- 已通过的 schema 发生语义修改时提升版本，并重新执行后续全部审计。

## 12. 阶段 4：评价合同与人工 Rubric

### 阶段目标

冻结从输入完整性到人工语义评价的分层 gate，确保失败可定位且自动分数不冒充最终真值。

### Gate 顺序

| Gate | 评价内容 | 失败归因 |
| --- | --- | --- |
| G0 | 输入、版本、partition、hash 和信息边界完整性 | protocol/input |
| G1 | strict JSON、schema 和字段类型 | model/structure |
| G2 | KG/source/contract/algorithm grounding | projection/planning |
| G3 | contract precedence、task-local state、veto 和 delivery state | planning/validator |
| G4 | counterfactual、invariant、composition、temporal pair relation | method behavior |
| G5 | 语义正确性、理由充分性和允许多解 | human review |
| G6 | materialization、quality、delivery 和 evidence artifact | selective E2E only |

### 执行动作

1. 为每个 gate 定义输入、输出、状态和不可用语义。
2. 固定 pre-fallback validity；fallback 后成功不能覆盖 G1-G4 失败。
3. 按 pair/template family/trace 定义主指标，重复调用只用于稳定性估计。
4. 为禁止行为率、grounding、合同满足、gap、delivery state、稳定性、token、时延和费用定义分母。
5. 对 quality gate disabled 等情况使用 `not_applicable`，不得记为通过。
6. 定义双人盲评、blind key、分歧、第三方裁决和缺失决策处理。
7. 固定 LLM judge 为 development triage；不得进入正式 gold 或单独升级主张。
8. 定义 failure taxonomy：input、KG、projection、planning、validator、execution、quality、evidence、external blocker。

### 验收标准

- 每个 matrix cell 至少有一个主要 gate 和一个证据字段。
- 指标分母、实验单元、聚合层级和不可用语义明确。
- 自动 evaluator 不通过关键词猜测 semantic guard、provenance 或 recovery trace。
- 人工 packet 不暴露 condition、run ID、replicate 或自动得分。
- 分歧未裁决时主张状态保持 pending，不按多数猜测补齐。
- planning 指标不能替代 execution/quality/external-validity 指标。

### 回滚与恢复

- 若主要指标无法区分能力层：回到 matrix/schema，不增加模糊综合分。
- 若人工 rubric 对同一允许多解输出无法稳定判定：暂停冻结，修订 rubric 并重新校准。
- 若 judge 建议与人工规则冲突：以人工协议为准并记录，不调整 gold 迎合 judge。

## 13. 阶段 5：选择治理

### 阶段目标

冻结 template 到实例、development 到 confirmation、planning 到 selective E2E 的选择规则，阻止按当前方法胜负选例。

### 执行动作

1. 冻结 template family 列表后再生成 seed；不得先看输出再增删 family。
2. 定义 development/confirmation 的独立 seed 空间、实例 ID 空间和禁止碰撞规则。
3. 定义停止条件：计划实例数、无效生成上限、外部阻塞和预算上限。
4. 定义排除条件只能来自预先登记的输入完整性或 source-closed 规则。
5. 定义 confirmation 解封顺序：方法和 evaluator 冻结后才能生成；一旦查看结果不得回写模板。
6. 定义 E2E 选择只基于预注册机制覆盖、source closure、truth/quality 可评价性和成本，不基于某方法领先。
7. 规定任何 post-freeze 修复进入新 development 版本，旧 confirmation 保留为负结果。

### 验收标准

- seed、partition、停止、排除、替换和解封规则均机器可读。
- confirmation 不包含 C01-C06、H01-H09 或其简单同义改写。
- 结果不可见时即可唯一决定实例集合或生成算法。
- E2E 资格与 planning 胜负解耦，并明确 source-closed 要求。
- 任何异常替换都会产生新 ID、reason、hash 和审计记录。

### 回滚与恢复

- 发现已查看 confirmation 内容后修改选择规则：当前版本作废，建立新版本和新 seed 空间。
- source inventory 不足：保持 `not_authorized`，不使用 mock 或历史结果代替。
- 预算变化：调整未来运行协议，不回写本设计冻结中的方法公平性规则。

## 14. 阶段 6：交叉审计与里程碑冻结

### 阶段目标

证明五项资产内部一致、可追溯、零调用，并形成不可变设计 checkpoint。

### 执行动作

1. 实现只读审计器，验证 ID 唯一性、引用闭合、矩阵覆盖、schema 合法性、partition 隔离和禁止 case 复用。
2. 为所有设计资产计算 SHA-256，写入 `freeze_manifest.json`。
3. 记录 Git commit parent、KG release identity、A0/A1 输入哈希和工具版本。
4. 审计当前工作树和目标目录，确认没有原始响应、运行结果、API key 或 Provider telemetry。
5. 由非作者或用户逐项复核 charter、oracle/veto、人工 rubric 和选择规则；保存 decision 与分歧处理。
6. 运行聚焦测试、JSON 解析、Markdown 链接和 `git diff --check`。
7. 更新 `research-governance-index.md` 和 `research-experiment-ledger.md`：只有全部通过时才将 `P-BENCH-DESIGN` 标为 frozen complete，并把下一验收点切换到平台实现协议。
8. 提交、推送并创建 annotated tag；不自动启动下一阶段。

### 建议验证命令

```powershell
.venv\Scripts\python.exe scripts/audit_benchmark_design_freeze.py `
  --root docs/current/benchmark/v1 `
  --output docs/current/benchmark/v1/freeze_audit.json

.venv\Scripts\python.exe -m pytest `
  tests/test_benchmark_design_freeze.py -q

Get-ChildItem docs/current/benchmark/v1 -Filter *.json | ForEach-Object {
  Get-Content -Raw -LiteralPath $_.FullName | ConvertFrom-Json | Out-Null
}

git diff --check
git status --short --branch
```

### 最终验收标准

- 审计器退出码为 0，所有 required checks 为 passed。
- 五项资产、rubric、manifest 和 audit 均存在且哈希一致。
- `provider_call_count=0`、`judge_call_count=0`、`formal_result_count=0`。
- `kg_release_changed=false`、`historical_evidence_mutated=false`。
- 人工协议复核完成，无未解决高风险分歧。
- 工作树在提交后干净，commit 与 tag 已推送。
- 当前执行入口已切换，但平台实现和新调用仍保持 `not_authorized`，等待新的明确启动指令。

### 冻结命名

建议使用：

```text
branch: codex/benchmark-design-r1
tag:    benchmark-design-freeze-v1
id:     fusionagent.benchmark-design-freeze.v1
```

若审计失败，不创建 tag，不标记 milestone complete。

## 15. 阶段检查点模板

每个阶段结束时在唯一执行记录中追加以下结构；不创建并行状态文档：

```markdown
## 阶段检查点

### 目标和阶段
- 当前目标：M-BENCH-DESIGN-FREEZE-V1
- 当前阶段：
- 下一验收点：

### 已完成证据
- 修改文件：
- 验证命令和实际结果：
- commit / hash：

### 未完成 / 阻塞
- 问题分类：
- 影响：

### 决策、推断与待验证假设
- 事实：
- 推断：
- 待验证：

### 恢复位置
- worktree / branch / HEAD：
- 首个恢复命令：

### 不应自动扩展的事项
- Provider、judge、平台实现、正式实验和 E2E 均未授权。
```

## 16. 暂停、降级与变更控制

出现以下任一情况必须暂停：

1. 需要改变 A0、RQ、创新点或六组身份。
2. 需要修改 KG v1 语义才能完成 schema。
3. 已观察案例被提议重新作为独立 confirmation。
4. 自动指标被提议替代人工语义评价或 E2E 质量证据。
5. 同一 pair 无法保持单因果变量。
6. 需要调用 Provider、judge 或生成正式实例才能继续设计。
7. 看过结果后需要改变模板、gold、rubric、seed 或停止条件。

允许的降级只有：缩小 capability cell 范围、把无法观测的能力移入 backlog、或把 E2E-only 能力标记为未授权。不得通过 mock、fallback、重试、关键词规则或旧结果填补设计缺口。

## 17. 里程碑之后但不在本计划内

设计冻结完成后，下一份计划才可以讨论：

1. 参数化实例生成和校验平台的最小实现。
2. development-only judge 与人工 rubric 校准。
3. 新 held-out 六组 planning 正式协议和真实 Provider 预算。
4. 根据预注册资格选择 selective E2E。

这些工作必须从冻结设计包创建新协议和独立分支；不得在本计划末尾自动继续。
