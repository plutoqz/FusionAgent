# FusionAgent Research Charter

状态: 当前有效
版本: 2026-07-20
适用分支: `research/product-contract`

## 1. 文档权威性

本文件是 FusionAgent 当前研究工作的最高优先级纲领文档, 用于约束研究方向、系统边界、实验设计、代码实现和论文表述。

发生冲突时按以下顺序处理:

1. 可复现的代码与实验事实。
2. 本文件。
3. `docs/CURRENT.md` 指向的当前规格文档。
4. 其他当前设计文档。
5. 历史 plan、freeze、maturity、scenario 和 evidence ledger 文档。

历史文档只用于追溯和复用工程经验, 不能自动恢复为当前研究主张。

任何改变研究对象、创新点、实验基线、产品范围或 LLM 职责边界的修改, 必须先更新本文件, 再修改代码。

## 2. 一句话定位

> FusionAgent 研究一种面向灾害应急基础矢量数据产品交付的契约化知识图谱框架, 由受约束的 LLM 在灾害情景、资源处境和产品契约下提出获取、融合与交付计划, 再由确定性执行、质量门、证据链和缺口声明机制完成可审计交付。

## 3. 研究问题

本研究回答的核心问题是:

```text
在灾害应急场景中, 当数据覆盖、现势性、网络、时间和质量条件不完整时,
如何形式化需要交付的数据产品, 如何让 LLM 在 KG 约束下做出可执行取舍,
以及如何证明最终产品满足、部分满足或无法满足契约?
```

正式研究问题为:

- `RQ1`: 如何把灾害情景、产品要求、数据源、算法、质量和证据统一建模为可执行的数据产品契约 KG?
- `RQ2`: 在资源受限和数据不完整条件下, 完整契约 KG 约束的 LLM 是否优于固定规则、KG-only 和弱约束 LLM?
- `RQ3`: 产品契约、质量门、证据链和缺口声明能否正确识别并解释不同交付状态?
- `RQ4`: 在固定且有限的数据源集合上, 该方法能否通过复杂组合场景体现可迁移的研究价值?

## 4. 产品范围

当前研究只覆盖固定数据源集合下的多源矢量融合产品:

- `building`
- `road`
- `water_type_1`
- `water_type_2`
- `poi`

数据产品主要体现:

- 几何补充、去重和融合。
- 属性补充、规范化和来源保留。
- 有界的拓扑冲突检测或处理。
- 质量验收、来源证据和缺口声明。

两类水系的正式名称、语义边界和质量指标必须在正式实验前冻结。未冻结前不得在论文中把它们描述为已经稳定定义的产品类型。

## 5. 明确非目标

本研究不主张:

- 提出新的通用矢量融合算法。
- 构建开放域或通用 GIS Agent。
- 自动完成灾情研判、损失评估或应急决策。
- 支持任意数据源自动接入。
- 支持任意任务类型无限扩展。
- LLM 可以绕过 KG、runtime contract 或质量门。
- 成功执行等于产品质量合格。
- 历史 workflow 可以作为固定模板直接回放。
- 当前系统已经达到生产级无人值守或 `7x24` 运行能力。

## 6. 拟定创新点

### 6.1 契约化灾害应急数据产品 KG

将灾害情景、资源处境、产品要求、必需图层、数据源、算法、质量门、证据要求、降级策略和缺口规则统一建模, 使“什么算交付成功”可以被机器表达和验证。

### 6.2 KG 约束的 LLM 编排

LLM 作为 bounded proposer, 在给定约束空间中提出图层优先级、数据源选择、获取策略、融合策略、渐进交付、后台补交和重规划建议。

LLM 输出必须经过 grounding。实验模式不得在 LLM 失败时静默回退到能获得标准答案的确定性策略。

### 6.3 证据化产品验收和缺口声明

系统不仅输出数据, 还输出产品契约满足度、质量门结果、来源和处理证据、未满足条件、影响与补救建议。

### 6.4 渐进式和可替换交付

资源受限时允许先交付 provisional 或 degraded 产品, 后台继续材料化和融合, 最终产品通过明确的 supersede 关系替换临时产品。

## 7. KG、LLM 与确定性层职责

### KG 负责

- 表达产品契约、灾害情景和资源约束。
- 表达数据源、数据类型、算法、任务和 workflow pattern。
- 提供质量门、证据要求和缺口规则。
- 为 planner 提供候选能力和历史案例证据。
- 为 grounding 提供合法性依据。

KG 应编码约束、事实、适用条件和权衡关系, 不应直接编码每个案例的标准答案。

### LLM 负责

- 将请求转译为候选产品和交付计划。
- 在时效、覆盖、完整度、现势性和质量之间做处境化取舍。
- 提出图层优先级、数据源使用、渐进交付和缺口建议。
- 给出可审计 rationale。
- 参考历史案例, 但生成 fresh plan。

LLM 不负责:

- 发明 KG 中不存在的算法和数据源。
- 判断几何计算结果是否真实正确。
- 修改质量门实测结果。
- 绕过产品契约和 runtime contract。
- 直接读取实验 gold answer。

### 确定性层负责

- 校验算法、数据源、数据类型和参数是否接地。
- 执行数据材料化、转换和融合算法。
- 计算质量指标并执行质量门。
- 校验 LLM 提出的缺口是否有事实依据。
- 生成最终产品状态、正式缺口声明和证据链。
- 记录运行、模型、prompt、上下文和失败证据。

## 8. 不可违反的实验约束

### 8.1 Gold 隔离

- `docs/thesis/experiment_cases.json` 只能包含 planner 可观察的场景事实。
- `docs/thesis/experiment_gold.json` 只能由规划完成后的 evaluator 读取。
- `expected_*`、标准答案、评分 rubric 和 `must_not_do` 不得进入 prompt、planning context、KG retrieval 或 LLM 可访问的文件内容。
- 测试必须检查序列化 planning context 中不存在 gold 字段。

### 8.2 消除位置和格式提示

- 输入数组顺序不得暗示标准优先级。
- 正式实验应对 required layers、sources 和等价候选做规范排序或受控随机置换。
- Gold 应优先表达优先级层级、偏序和可接受替代策略, 不应强迫唯一全序答案。

### 8.3 Planner 输出必须影响评分

- 不得由 evaluator 或 deterministic postprocessor 自动替 planner 生成正确的 `proposed_gaps`、优先级或交付策略后再给 planner 计分。
- Planner 提议与系统最终正式声明必须区分:

```text
planner_gap_proposal
-> grounding / verification
-> final_gap_declaration
```

- 规划实验评分 planner 自己的提议。
- 产品交付使用经过确定性验证后的最终声明。

### 8.4 基线可比性

正式基线为:

1. `fixed`
2. `kg_only`
3. `llm_only`
4. `llm_capability_kg`
5. `llm_full_contract_kg`

涉及 LLM 的模式必须尽量使用相同模型、温度、输出 schema、调用接口和重试策略。主要变量只能是提供给模型的知识和约束层。

### 8.5 不静默掩盖失败

- 真实 LLM 调用失败必须记录为失败或显式重试。
- Grounding 失败不得伪装成成功计划。
- 实验 runner 不得静默回落到 gold-aware 或 oracle 策略。
- 系统应用运行可以有安全 fallback, 但必须记录 `planning_source` 和 fallback 原因, 且不能用于冒充 LLM 规划结果。

## 9. 决策输出协议

下一版 planner 应使用结构化字段, 自然语言 rationale 不能作为唯一可评分输出:

```text
priority_tiers
initial_delivery_layers
background_completion_layers
not_delivered_layers
selected_algorithm_per_layer
selected_sources_per_layer
delivery_mode_per_layer
planner_gap_proposal
supersession_plan
rationale
```

结构化字段之间必须进行一致性校验。例如 `initial_delivery_layers` 不得与 `not_delivered_layers` 重叠, rationale 不能替代结构化交付顺序。

## 10. 评价指标

规划与契约评价至少包括:

- 产品契约满足度。
- 关键图层优先级或偏序满足度。
- 交付策略正确率。
- Planner 缺口 proposal precision、recall 和 F1。
- 禁止行为发生率。
- Grounding 通过率。
- 计划内部一致性。
- 可接受替代策略覆盖率。
- 首个可用产品时延。
- 最终产品时延。
- 证据完整率。
- LLM token、延迟、失败率和重复运行稳定性。

算法自身的几何、属性和拓扑质量指标是产品验收证据, 但不能替代 agent planning 和契约满足度指标。

## 11. 实验可复现要求

每次 LLM 规划至少记录:

```text
case_id
planner_mode
model
base_url_host
temperature
prompt_version
prompt_hash
context_hash
raw_llm_response
grounding_report
token_usage
latency
retry_count
failure_reason
code_commit
```

不得记录 API key。密钥只能存在于本地忽略文件或进程环境中。

每个正式 LLM 条件应至少重复 5 次。正式重复次数、随机化方式和统计方法必须在查看最终结果前冻结。

## 12. 数据和凭据约束

- 当前实验以固定数据源集合为边界, 不用增加数据源数量代替研究深度。
- 数据源不可用、无覆盖、语义失配、质量失败和任务无关必须分别表达。
- `skip`、`data_absent`、`source_unavailable`、`source_mismatch`、`quality_failed` 不得混用。
- 本地密钥文件使用 `.env.local`, 必须被 Git 忽略。
- 日志、JSON、traceback、测试 fixture 和文档不得包含真实密钥。
- 对外报告只记录 endpoint host、模型和非敏感运行配置。

## 13. 当前事实状态

截至 2026-07-20:

- 七层产品契约 KG 本体已有设计草案。
- 已有 6 个机器可读组合实验案例。
- 实验 case 与 gold label 已物理分离。
- `llm_only`、`llm_capability_kg` 和 `llm_full_contract_kg` 均已恢复真实 OpenAI-compatible API 调用。
- LLM 输出已使用结构化 priority tiers、交付集合、逐层决策、planner gap proposal 和 supersession plan, 并完成案例相关 grounding。
- 当前 runner 已实现 `fixed`、`kg_only`、`llm_only`、`llm_capability_kg`、`llm_full_contract_kg` 五种正式基线。
- Phase 1 机器评分协议已在最小 runner 中实现, 自然语言 rationale 不再作为主要评分依据。
- Planner gap proposal、gap verification 与最终确定性 gap declaration 已物理分离, 评分只使用 planner proposal。
- 输入顺序变体、gold 隔离、结构一致性、grounding 失败和缺口遗漏已有自动化测试。
- LLM schema 或 grounding 最终失败会生成 `planning_failure.json` 并继续抛错, 不进行静默 deterministic fallback。
- `C02` 已完成三种 LLM 基线在统一 `gpt-5.4-mini`、prompt、temperature、JSON schema 和 retry policy 下的真实开发验证运行, 结果仅用于验证协议, 不作为论文结论。
- Phase 3 正式稳定性协议已冻结为 6 案例 × 5 基线 × 5 重复, 输入变体 0--4 均衡分配并使用固定 seed 打乱执行顺序。
- 重复实验 runner 已生成带 SHA-256 产物清单和前向哈希链的 `audit_ledger.jsonl`, 成功与失败运行均可追溯。
- 已完成 30-run 六案例开发矩阵和 10-run C02 双重复开发批次, 均为 `claim_eligible=false` 的调试证据。
- 正式 150-run 实验尚未执行; formal 模式要求 clean Git worktree, 不允许在当前未提交状态下生成论文证据。
- Phase 4 最小真实运行时闭环已实现: runner 现在显式区分 `planning_only`
  与 `end_to_end`, 并将 planner 选择连接到真实 source materialization、现有
  domain fusion runner、`QualityGateService` 和 `ArtifactRegistry` writeback。
- `C02`、`C04`、`C06` 已完成合成真实矢量输入的开发验证; 这些运行用于验证
  执行协议和失败边界, 不属于真实外部数据论文证据。
- 三个代表案例的真实外部数据 end-to-end 运行和冻结证据仍待完成。
- 两类水系的正式产品语义尚未冻结。
- 当前结果均为开发验证结果, 不得作为论文最终结论。

## 14. 后续实施顺序

必须按以下顺序推进, 除非本文件先被正式修改:

### Phase 1: 决策 schema 与评分有效性

状态: 已完成最小研究 runner 的实现与真实调用验证。

- 重构结构化 planning decision。
- 分离 planner gap proposal 和 final gap declaration。
- 消除输入顺序提示。
- 将 gold 改为优先级层级、偏序和可接受策略集合。
- 增加内部一致性和泄漏测试。

### Phase 2: 五类基线

状态: 已完成五种基线实现、上下文消融测试和三种 LLM 条件的真实调用验证。

- 实现 `llm_only`。
- 实现 `llm_capability_kg`。
- 明确 `llm_full_contract_kg` 与其他模式的唯一上下文差异。
- 冻结统一 prompt schema 和调用参数。

### Phase 3: 重复实验和稳定性

状态: 稳定性协议、审计 runner 和开发矩阵已完成; clean commit 后的正式 150-run 重复实验待执行。

- 对 6 个案例进行开发运行。
- 修正 grounding 和 schema 问题。
- 冻结正式重复次数和统计协议。
- 执行多次真实 LLM 运行并保存原始证据。

### Phase 4: 真实运行时闭环

状态: 最小执行协议和 C02/C04/C06 开发验证已完成; 真实外部数据运行、长耗时
稳定性和正式证据冻结待完成。

- 优先接入 `C02`、`C04`、`C06`。
- 将规划结果连接到真实材料化、融合、质量门和 writeback。
- 保留 planning-only 与 end-to-end 两类实验, 不混淆结论。
- 单源可用时只允许显式 `runtime.single_source_passthrough.v1`, 必须记录所选
  fusion algorithm 未执行的原因, 不得伪装为多源融合结果。
- `water_type_1` 固定映射为 polygon water, `water_type_2` 固定映射为 line
  waterways; 语义未冻结前不得互相替代。

### Phase 5: 证据冻结与论文写作

- 生成机器可读实验总表。
- 完成统计分析、消融和失败案例分析。
- 冻结图表、prompt、模型和 commit。
- 证据冻结后再撰写正式结果和讨论。

经验案例检索和 pattern promotion 属于后续阶段, 不得抢占当前五基线和契约评价工作。

## 15. 阶段完成标准

在宣称“研究实验系统完成”之前, 必须同时满足:

- 产品契约和两类水系语义冻结。
- 五类基线全部可运行。
- Gold 不可被 planner 访问, 且有自动测试证明。
- 输入顺序置换不会系统性改变合理结论。
- Planner proposal 的指标不是由确定性代码代答。
- LLM 原始输出、grounding、模型、token 和延迟可追溯。
- 至少 6 个组合案例完成规定次数的重复实验。
- 至少 3 个代表案例完成真实运行时闭环。
- 质量门和缺口声明均有可检查证据。
- 所有论文主张均可追溯到冻结产物。

## 16. 开发前检查清单

开始任何新任务前必须回答:

1. 这项工作直接服务哪个 RQ 或 Phase?
2. 它改变的是研究方法、实验工具还是应用工程?
3. 是否扩大了产品、数据源或任务边界?
4. 是否可能把 gold、case-specific rule 或输入顺序提示暴露给 planner?
5. Planner 的输出是否真正影响评分?
6. 失败是否会被静默 fallback 掩盖?
7. 新指标是否能区分不同 baseline?
8. 新输出是否包含可复现证据且不泄露密钥?
9. 是否需要先更新本文件?

如果无法明确回答前两项, 不应开始编码。

## 17. 当前文档入口

当前有效文档:

- `PROJECT.md`: 最高优先级研究章程。
- `docs/CURRENT.md`: 当前文档导航和历史边界。
- `docs/thesis/research_direction_guide_2026-07-09.md`: 研究方向形成过程和详细论证。
- `docs/thesis/ontology_schema_v2.md`: 本体设计。
- `docs/thesis/product_contract_spec.md`: 产品契约与输出规格。
- `docs/thesis/experiment_case_matrix.md`: 实验案例和基线设计。
- `docs/thesis/experiment_cases.json`: Planner 可观察输入。
- `docs/thesis/experiment_gold.json`: 仅供规划后评价的 gold labels。
- `docs/research-runtime-minimum.md`: 最小研究运行时。

以下目录默认为历史材料:

- `docs/superpowers/plans/**`
- `docs/superpowers/specs/**`
- `docs/pasted/**`
- 旧 paper freeze、maturity freeze 和 scenario harness 文档

从历史材料恢复任何主张或流程前, 必须先说明它如何服务当前研究问题并更新当前文档。
