# 研究分支成果与当前 KG v1 归并审计

> 状态：A3 历史归并审计；不再是当前执行入口
> 继承说明（2026-08-19）：当前阶段、分支职责和下一验收点见 [`research-governance-index.md`](research-governance-index.md)；当前主张与实验状态分别见 [`research-claim-evidence-ledger.md`](research-claim-evidence-ledger.md) 和 [`research-experiment-ledger.md`](research-experiment-ledger.md)。本文保留当时的资产分类与归并约束，不覆盖当前治理结论。
> 审计日期：2026-08-04
> 主线基准：`main@2bcafaa`
> 研究基准：`research/product-contract@1aba2f3`

## 1. 审计结论

`research/product-contract` 中确有值得复用的研究资产，包括结构化规划决策、gold 隔离、五组规划 runner、显式 LLM 失败、重复实验审计链和最小端到端执行器。但这些资产目前不能作为一个分支或完整提交直接合并到 `main`，核心原因不是测试不可运行，而是它们尚未以当前冻结 KG v1 为唯一知识真源。

本次归并结论为：

1. **禁止整分支或整提交合并。** 研究分支的两个独有提交同时包含过时文档权威关系、实验代码和会恢复 Python 硬编码质量策略的改动。
2. **保留研究控制面的设计成果。** 结构化决策、失败留痕、gold 隔离、输入置换、hash-chain 审计和 planning-only/end-to-end 分离可以作为选择性提升基础。
3. **重做 KG 接入边界。** 研究 runner 当前从 case 数据和 Python 常量即时拼装“capability KG/full contract KG”，没有调用 `KGRepository`、`KnowledgePolicyRegistry` 或冻结 release loader，不能称为当前 KG v1 驱动。
4. **真实 LLM 已有开发调用事实，但没有正式证据。** 本地忽略目录保留一条旧版 C02 真实调用记录；它不是当前协议、未冻结、不可用于 P3-P 结论。
5. **端到端开发链路存在，但外部实证未完成。** 定向测试会生成真实矢量文件并调用现有融合、质量门和 artifact writeback；其 source materializer 是测试替身，不是从接收真实灾害信息到外部数据融合成果的正式运行证据。
6. **当前应暂停在讨论闸门。** 本审计完成后，先确认基线语义、案例处置、单源质量政策和真实 LLM 成本，再定义归并实施批次。

## 2. 审计范围与验证

研究分支相对共同基线增加或修改 35 个文件，约新增 7650 行，主要来自：

- `e2c94e5`：研究章程、实验案例、gold、协议和本体 v2 草案。
- `0a8c4ad`：规划 runner、稳定性 runner、运行服务、schema、provider telemetry 和测试。
- `1aba2f3`：将研究分支与当时的 `main@db256d5` 合并同步。

当前 `main` 此后又通过 `680ff3f` 完成 KG v1、P1/P2、P3-G 和 P4-G 相关实现与证据，因此研究分支并不包含主线的最新知识真源与运行约束。

本次实际验证结果：

| 验证对象 | 命令范围 | 结果 | 能证明什么 |
| --- | --- | --- | --- |
| 研究 runner | provider telemetry、experiment、runtime、stability 四个测试文件 | `32 passed, 3 warnings` | 开发资产在研究分支可运行 |
| 当前 KG v1 | release、runtime identity、runtime acceptance 三组测试 | `29 passed` | 当前 KG 冻结、身份、篡改和运行扰动链路可用 |
| 研究 worktree | `git status --short` | 干净 | 分支提交可独立审计 |
| 主工作区 | `git status --short` | 有未提交改动 | 当前不能生成 formal/claim-eligible 新证据 |

上述测试均未调用新的真实 LLM，也未执行真实外部数据下载。

## 3. 关键发现

### F1：研究 runner 的 KG 上下文不是当前 KG v1

`scripts/run_product_contract_experiment.py` 没有导入任何 KG repository 或 release API。`build_planning_context()` 直接使用以下输入拼装知识上下文：

- `case["required_layers"]`
- `case["input_sources_status"]`
- Python 常量生成的算法 ID
- `build_product_contract()` 中硬编码的质量、降级、交付、gap 和证据政策
- `SOURCE_PROBLEM_TO_GAP`、`VALID_STRATEGY_IDS` 等 Python 常量

因此，`kg_only` 和 `llm_full_contract_kg` 只能证明“消费了 runner 自己组织的结构化上下文”，不能证明消费了 `kg/ontology/v1.0.0/`。当前上下文也没有记录 `release_id`、`semantic_hash` 或 `experience_snapshot_hash`。

**归并要求：** 由当前 `KGRepository` 和 `KnowledgePolicyRegistry` 生成一份带 `knowledge_identity` 的完整实验上下文，再按实验组做字段投影；不得分别手工拼装三份看似不同的 KG 上下文。

### F2：规划算法和真实执行算法之间存在硬编码替换

研究运行服务同时维护：

- `PLANNING_ALGORITHM_BY_LAYER`
- `RUNTIME_ALGORITHM_BY_LAYER`
- `TASK_KIND_BY_LAYER`

规划器选择 `algo.fusion.road.v1` 时，运行服务实际调用 `algo.fusion.road.conflation.v7`，并把 `selected_algorithm_executed` 记为 `true`。两类水产品的规划 ID `algo.fusion.water_type_1.v1` 和 `algo.fusion.water_type_2.v1` 根本不在 KG v1 中。

这会把“规划选择被执行”与“代码将规划 ID 翻译成另一算法”混在一起，削弱端到端因果链。

**归并要求：** 规划输出必须使用 KG v1 的稳定算法 ID；执行能力、别名或降级只能由 KG/runtime contract 显式解析，并分别记录 selected、resolved、executed 和 fallback reason。

### F3：研究分支的质量策略改动会恢复第二知识真源

研究分支修改 `services/quality_policy_service.py`，重新在 Python 中定义五类默认质量策略、阈值、拓扑检查和单源策略。当前 `main` 已把这些规则迁入 `KnowledgePolicyRegistry` 和 `policies.json`。

研究运行服务依赖的五个 `quality.product_contract.single_source.*.v1` ID 又不在当前 KG v1 中。若直接提升运行服务并同时合并研究版质量服务，会倒退到散落 Python 常量；若只提升运行服务，则这些 policy ID 无法由当前 KG v1 解析。

**归并要求：** 保留 `main` 的 KG-backed quality service。单源交付应选择以下一种方案后再实现：复用当前 degradation adaptation；或发布新的 KG 版本新增单源政策。不得原地改写冻结 v1，也不得恢复 Python policy 表。

### F4：正式基线仍少一组

研究分支实现五组：

```text
fixed
kg_only
llm_only
llm_capability_kg
llm_full_contract_kg
```

当前 A0 研究计划要求六组，并新增独立 `rules-only`。旧稳定性协议固定为 `6 cases x 5 planners x 5 repetitions = 150 runs`，不能继续作为当前正式协议。若案例数和重复次数保持不变，六组将是 180 次；最终数量仍需在讨论后冻结。

`fixed`、`rules-only` 和 `KG-only` 必须有可审计的独立信息边界，不能只是三套不同名称的 case-specific Python 排序函数。

### F5：案例词汇与 KG v1 未闭合

当前六个研究案例不能原样进入 KG v1 正式实验：

| 对象 | 研究案例状态 | KG v1 对齐结果 |
| --- | --- | --- |
| 灾种 | `earthquake`、`flood`、`wildfire`、`typhoon_or_storm`、`generic_disaster_response`、`any` | 仅前两项精确命中；三项可讨论规范化为 `typhoon/generic`；`wildfire` 当前明确不属于可执行灾种 |
| 数据源 | 10 个不同 source ID | 7 个存在；`raw.attribute_rich.building`、`raw.geometry_rich.building`、`raw.reference.road` 不存在 |
| 规划算法 | 五类 `algo.fusion.<layer>.v1` | 建筑、道路、POI 存在；两类 water ID 不存在 |
| 运行算法 | 五类 domain runner ID | 五个均存在于 KG v1 |
| 产品契约 | 每个 case 动态生成 `contract.<case_id>` | 未引用 KG v1 的 6 个产品契约实体 |
| 单源质量政策 | 五个 product-contract single-source ID | 0 个存在于 KG v1 |

**归并要求：** 建立显式 case-to-KG crosswalk。不能在 runner 内用别名、默认值或新增 Python 常量掩盖未对齐对象。

### F6：真实 LLM 证据只达到开发事实等级

研究 worktree 的 `tmp/product-contract-live/C02-llm-kg/` 保留一条旧版记录：

- provider：OpenAI-compatible
- model：`gpt-5.4-mini`
- token：1920 prompt + 421 completion
- grounding：通过

但该记录使用旧 planner 名称 `llm_kg`，缺少当前协议要求的 prompt hash、context hash、调用延迟和重试信息，且位于 Git 忽略目录。研究文档还记载了 30-run 和 10-run 开发批次，但对应 audit ledger 和批次产物当前不在该 worktree 中，无法独立复核。

结论只能是“真实 provider 和历史调用事实存在”，不能是“当前真实 LLM 链路已正式验证”。

### F7：端到端测试使用真实处理函数，但不是完整真实灾害链路

`ProductContractRuntimeExecutor` 已把规划结果连接到 source materialization、domain fusion runner、`QualityGateService` 和 `ArtifactRegistry`。测试也验证了：

- 只材料化 planner 选择的 source。
- 材料化失败不会被模拟质量结果替代。
- 双道路源会调用现有 v7 融合 runner。
- 单源 passthrough、质量验收和 writeback 会留痕。
- planning-only 与 end-to-end 产物明确分离。

但测试中的 `RecordingMaterializer` 在临时目录生成合成 GeoPackage，并非真实外部数据获取；入口也直接接收结构化 case，而不是灾害消息、intent/mission 编译和 KG v1 检索链。因此它是“最小执行适配器验证”，不是“从接收灾害信息到融合成果”的完整链路实证。

## 4. 资产分类

本表以类、函数和责任边界为归并单位，不以 commit 为单位。

### 4.1 可直接提升

以下资产的核心语义可保留；提升时仍需按 `main` 的目录和命名进行最小适配：

| 资产 | 来源 | 保留范围 |
| --- | --- | --- |
| 结构化规划决策模型 | `schemas/product_contract_experiment.py` | priority tiers、逐层决策、planner gap proposal、supersession 及内部一致性 validator |
| 显式 LLM 失败 | `LLMPlanningFailure` 与 `planning_failure.json` | 调用、schema、grounding 失败不得变成成功计划 |
| Gold 隔离测试思想 | `tests/test_product_contract_experiment_runner.py` | planner context 不含 `expected_*`、rubric、`must_not_do` |
| 输入置换与层内无序评分 | experiment runner/tests | 消除输入顺序提示，允许 gold tier 内置换 |
| 审计链基础构件 | stability schema/runner | artifact digest、前向 hash chain、篡改检测、失败不插补 |
| planning-only/end-to-end 标签 | runtime schema/runner | 两类证据不可混算 |

没有任何完整研究提交可直接 cherry-pick；“可直接提升”不等于“原文件整份复制”。

### 4.2 适配 KG v1 后提升

| 资产 | 必须适配的内容 |
| --- | --- |
| `scripts/run_product_contract_experiment.py` | 注入 KG repository/policy registry；记录 knowledge identity；增加 `rules-only`；用 KG 投影构造三种知识条件 |
| `scripts/run_product_contract_stability.py` | 六组协议、KG identity/协议哈希、当前主线文件 manifest、正式证据目录和 clean-worktree 规则 |
| `schemas/product_contract_stability.py` | 五组常量改为六组；增加 KG release identity、execution mode 和必要的失败分类 |
| `schemas/product_contract_runtime.py` | 增加 contract、KG identity、selected/resolved/executed 决策链字段 |
| `services/product_contract_runtime_service.py` | 通过 KG/runtime contract 解析算法、source 和质量政策；接入主线执行服务而不是层级映射表 |
| `llm/providers/openai_compatible.py` telemetry | 与当前主工作区的 connection probe 改动手工合并；不能覆盖现有用户改动 |
| 三个研究测试文件 | 改为断言当前 KG v1 真源、六组隔离、fail-closed 和选中算法真实执行 |
| cases、gold、protocol | 完成 case-to-KG crosswalk，重新冻结后才可运行 formal 实验 |

### 4.3 必须重写

| 资产 | 原因 |
| --- | --- |
| `build_product_contract()` | 当前从 case 和 Python 常量创造契约，应改为引用并实例化 KG v1 产品契约 |
| `build_planning_context()` 的 KG 构造部分 | 当前是 case-to-dict 拼装，不是 KG retrieval |
| `choose_priority_tiers()` 和 deterministic `kg_only` | 当前由 case 字段和 Python 排序直接给答案，需定义独立 rules-only/KG-only 算法边界 |
| `PLANNING_ALGORITHM_BY_LAYER` / `RUNTIME_ALGORITHM_BY_LAYER` | 形成第二能力目录，并掩盖 selected 与 executed 的差异 |
| 研究版 `quality_policy_service.py` 改动 | 会撤销 KG v1 的唯一政策真源 |
| 正式稳定性协议 | 五组、150-run 和旧模型锁定已不符合当前 A0 计划 |

### 4.4 历史保留

| 资产 | 处理方式 |
| --- | --- |
| `PROJECT.md`、`docs/CURRENT.md`、研究分支 `AGENTS.md/CLAUDE.md` | 保留在研究分支追溯，不提升为共享权威；共享 A0 以 `docs/current/` 为准 |
| `docs/thesis/ontology_schema_v2.md` | 作为 KG v1 形成过程和未来版本候选需求，不覆盖冻结 schema |
| 旧五组实验矩阵和 150-run 协议 | 保留历史版本，不再标记为当前 frozen formal protocol |
| `tmp/product-contract-live/` | 仅作历史开发调用诊断，不进入正式证据目录 |
| 30-run/10-run 文档性记录 | 在原始 audit ledger 找回并独立核验前，仅作历史陈述 |

## 5. 建议的归并结构

这是一组依赖约束，不是已经冻结的下一里程碑：

1. **实验上下文工厂**：从当前 `KGRepository`、`KnowledgePolicyRegistry` 和 case observation 生成一份完整、带版本身份的 canonical context。
2. **实验组投影器**：从同一 canonical context 投影 fixed、rules-only、KG-only 和三种 LLM 条件，记录每组可见字段清单与 hash。
3. **严格实验规划器**：复用真实 provider，但绕开应用模式的 KG fallback；原始响应、schema 和 grounding 失败原样进入实验记录。
4. **规划后 evaluator**：唯一可读取 gold 的组件；planner proposal 与最终 deterministic declaration 继续分离。
5. **选择性运行适配器**：把已接地的 source/algorithm/contract ID 交给现有主线材料化、融合、质量和 writeback 服务，并核对 selected/resolved/executed。
6. **统一证据冻结器**：在现有 KG v1、P1–P4-G 证据之上增加 P3-P/P4-P 命名空间，不覆盖旧证据。

## 6. 讨论闸门

开始代码归并前，需要明确以下事项：

1. **案例集**：C03 是保留为“KG 正确拒绝 unsupported wildfire”的负例，还是替换为当前 v1 支持的灾种案例；C04–C06 的灾种别名如何规范化。
2. **三类确定性基线**：fixed workflow、rules-only、KG-only 各自可见信息和允许的决策逻辑是什么。
3. **单源质量政策**：复用当前 degradation adaptation，还是发布包含显式 single-source policy 的新 KG 版本。
4. **真实 LLM 协议**：模型、provider、重复次数、预算上限、失败重试与原始响应保留策略。
5. **端到端范围**：从六类 planning case 中选择哪些代表案例连接真实外部数据；不要求六组全部做昂贵端到端运行。

在上述五项确认前，不建议开始 runner 归并，也不建议把旧协议改名后直接执行。

## 7. 后续归并验收条件

未来的选择性提升至少满足：

- 所有 KG-based 组记录当前 release identity，且 context 可追溯到同一 KG v1。
- 修改 KG 中可见知识能够改变 KG-only 或 full-contract 组行为，且不修改 runner 代码。
- 缺失必要 KG 知识时 fail closed。
- 六组边界有自动化测试，`rules-only` 独立存在。
- 三种 LLM 组使用相同模型、prompt、schema、温度和重试规则。
- 实验模式没有 deterministic/KG fallback 冒充 LLM 成功。
- case 中所有 source、algorithm、contract、quality policy 均有显式 KG 对齐或被标记为 fixture-only。
- selected、resolved、executed 和 fallback 四个状态可分别审计。
- 真实 LLM pilot 记录原始响应、token、延迟、prompt/context hash 和 `planning_source=llm`。
- 选择性端到端 pilot 能证明规划差异确实改变材料化、融合、质量门或最终契约状态。

满足这些条件后，才适合冻结 P3-P 的正式实验协议和下一实施里程碑。
