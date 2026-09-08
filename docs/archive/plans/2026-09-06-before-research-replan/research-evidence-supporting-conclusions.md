# 支持研究核心与创新点的实验和数据

> 状态：A1 当前证据归纳
> 更新日期：2026-09-05
> 研究口径依据：`D:\code\FusionAgent\docs\thesis\research_direction_guide_2026-07-09.md`、`D:\code\FusionAgent\docs\current\research-charter.md`
> 证据状态依据：本分支 `research-claim-evidence-ledger.md` 与 `research-experiment-ledger.md`

本文只整理能够对研究核心和创新点形成正向支撑的实验与数据。内容围绕以下研究链组织：

```text
灾害应急数据产品契约
-> 数据需求与数据源/算法/任务/质量/证据知识
-> KG 约束规划与确定性接地
-> 自动执行与质量验收
-> 渐进交付、恢复、证据链和缺口声明
-> 可复核的数据产品交付
```

对应关系如下：

| 研究方向指引中的创新组合 | 当前章程对应项 |
| --- | --- |
| 灾害应急数据产品契约层；算法-数据-任务-场景-证据一体化 KG | I1 / O1 / RQ1 |
| LLM 作为受约束的无人值守编排者 | I2 / O2-O3 / RQ2-RQ3 |
| 产出后验收、渐进交付与缺口声明 | I3 / O4 / RQ4 |
| 面向灾害应急数据产品的实验评价 | I4 / O4 / RQ4，作为 I1-I3 的可信性支撑 |

## 1. 数据产品契约与一体化七层知识图谱

### 1.1 KG v1 模式、实体和政策冻结

**实验与数据：**

- P0-K2 冻结 7 个知识层、71 个模式类、42 类关系、19 项核心属性、8 项完整性约束和 8 个 competency questions。
- KG v1 冻结包包含 241 个稳定标识的静态知识对象和 6 个产品契约实体。
- P0-K1/K3 台账登记 47 个知识片段，覆盖 intent、capability、产品契约、数据源、质量、恢复和证据七条决策链；35 个高风险片段完成唯一知识源迁移或执行机制归类。
- `release.json` 将发布身份固定为 `fusionagent-kg-v1.0.0`，语义哈希为 `sha256:50067b9368914c47580707650789c04c78b2e856ccb3ef4d120a31f36c0ad71e`，并分别记录 `schema.json`、`entities.json` 和 `policies.json` 的 SHA-256。

**支撑内容：**

- 从知识表示层面支撑灾害情景、产品契约、数据需求、数据源语义、算法任务能力、质量门、恢复策略和证据要求能够进入同一版本化模型。
- 从机器可计算层面支撑产品空间范围、图层要求、质量政策、可接受降级和证据要求能够以稳定 ID、关系和约束表达，而不是只存在于自然语言说明或 Python 常量中。
- 从版本治理层面支撑知识模型可以被查询、校验、冻结和追溯。

**证据位置：**

- `kg/ontology/v1.0.0/`
- `kg/ontology/v1.0.0/release.json`
- `docs/research/ontology/knowledge-fragment-ledger.md`
- `docs/archive/status/project-status-2026-08-13.md`

### 1.2 多源融合产品语义进入运行产物

**实验与数据：**

- Freeze C 的 C02 水系线结果包含 392 个要素，其中 `raw.osm.waterways=284`、`raw.hydrorivers.water=108`；输出中 `invalid_geometry_rate=0`、`duplicate_geometry_rate=0`。
- C04 水面从 provisional 阶段的 38 个 OSM 要素推进到最终阶段的 39 个要素，其中加入 `raw.hydrolakes.water=1`，并保留 provisional、final 和 superseded 三类交付记录。
- C02/C04/C06 的质量报告同时保存要素数、数据源贡献、几何合法性、重复率、字段非空统计、AOI 一致性和交付阶段。

**支撑内容：**

- 从运行实例层面支撑“一体化 KG”所描述的数据源、算法、任务、质量和证据对象能够对应到实际多源输入、融合输出和质量报告。
- 从数据产品层面支撑系统能够记录多源贡献、几何质量、属性状态和交付阶段，而不是只记录工作流是否执行完成。
- 从产品契约层面支撑同一图层可以具有 provisional、final 和 superseded 等不同交付语义。

**证据位置：**

- `docs/current/evidence/p2-stability/2026-08-01-freeze-c-p2-stability.json`
- `D:\code\freeze-c-evidence\p2-stability-20260801-c02-c04-c06`

## 2. KG 约束规划与确定性接地

### 2.1 KG-only 单点扰动改变规划行为

**实验与数据：**

- P0-K4 改变 `wp.flood.building.safe.success_rate` 后，规划选择从 `wp.flood.building.default` / `algo.fusion.building.v1` 切换到 safe pattern 和对应算法。
- 计划上下文保存 `knowledge_identity`、`selected_pattern_id`、候选排序依据和选择理由。
- 删除运行期必需知识、缺失输出 schema、输入未知稳定 ID 或使用不可用 strict backend 时，系统产生明确失败结果。

**支撑内容：**

- 直接支撑 KG 内容能够在不修改执行代码的情况下改变候选选择和规划结果。
- 直接支撑 KG 是限定决策链中的实际输入，而不是规划完成后的附属展示。
- 支撑确定性 validator 能够对类型、能力、依赖、schema 和知识后端执行 fail-closed 接地。

**证据位置：**

- `docs/current/evidence/p3-governance/`
- `docs/current/research-claim-evidence-ledger.md` 中 `CL-I2-BIND`
- `kg/ontology/v1.0.0/release.json`

### 2.2 Neo4j-memory parity 与 source fallback

**实验与数据：**

- Java 21 + Neo4j 5.26 官方 harness 与 pinned memory 在建筑、道路、水体和 POI 四类任务上核对 pattern、step、algorithm 和 data-source 顺序。
- P0-K4/K5 定向组合测试为 `47 passed`，KG 独立 verifier 为 `11/11`。
- source fallback 测试中，替代源触发重新材料化；fallback artifact 的内容和 SHA-256 与失败源残留不同。

**支撑内容：**

- 支撑冻结 KG release 可以被不同知识后端加载并保持语义一致的规划输入。
- 支撑数据源替代不仅改变 source ID，还会生成新的实际输入和独立 artifact 证据。
- 支撑从知识选择、运行解析到实际材料化之间存在可核对的执行链。

**证据位置：**

- `docs/current/evidence/p3-governance/`
- `docs/current/research-branch-kg-v1-merge-audit.md`
- `kg/ontology/v1.0.0/`

### 2.3 真实 LLM 条件下的独立规划确认

**实验与数据：**

- H07-H09 独立 planning confirmation 包含 B、LLM-only 和 Full KG 三个条件，共 27 次真实调用和 63 个 rubric item。
- 双人盲评和裁决结果为：B `21/21`、Full KG `21/21`、LLM-only `17/21`。
- 每次调用保留原始响应、模型信息、输入投影、盲评 key、双评结果和裁决记录。

**支撑内容：**

- 支撑真实 LLM 可以在结构化契约知识条件下生成满足已定义 rubric 的受约束计划。
- 支撑产品契约、资源处境、gap 和禁止行为能够作为 LLM planning 的显式评价对象。
- 支撑“LLM 是候选计划提议者，确定性规则和人工 rubric 负责接地与评价”的职责划分可以落入可审计实验。

**证据位置：**

- `D:\code\fusionagent-evidence\p3-planning-method-b\2026-08-17-method-b-independent-confirmation-v1`
- `D:\code\fusionagent-evidence\p3-planning-method-b\2026-08-18-method-b-independent-confirmation-manual-adjudication-v1`
- `docs/current/research-protocol-method-confirmation-v1.json`

### 2.4 简化对抗集与 held-out 中的局部语义规划优势

**实验与数据：**

- Adversarial baseline 使用 12 个对抗场景、5 类产品和 60 对 base/fault，共 120 个案例成员；五个主方法使用完全相同的案例，另对 full KG 执行三类模块消融。该轮共形成 960 rows，其中 720 次为真实 `qwen3.7-flash` Provider 调用。
- 该轮 fault-only 通过率为：`llm_full_contract_kg` `13/60`（21.7%）、`llm_capability_kg` `8/60`（13.3%）、`rules_only` `5/60`（8.3%）、`fixed_workflow` `0/60`。Full KG 的通过集中在 priority conflict、candidate-plan contradiction 和部分 quality degradation。
- Held-out confirmatory 冻结 12 个新高难场景、5 类产品和每场景 2 个实例，共 120 对 base/fault；三种 LLM 方法对完全相同输入各运行 3 次，规则和固定流程各运行 1 次，总计 2640 rows 和 2160 次真实 Provider 调用。
- Held-out 的预声明 primary composite 未确认整体优势，但 post-hoc semantic delivery 中 full KG 为 `38/120`（31.7%），`rules_only` 与 `fixed_workflow` 均为 `3/120`（2.5%）。Full KG 相对规则的差值为 29.2 个百分点，scenario-cluster bootstrap 95% CI 为 `[6.7%, 53.3%]`；其 fault canonical order 为 `120/120`。
- Adversarial 模块消融中，移除 capability / algorithm grounding 后 aggregate oracle 从 60.8% 降至 25.0%，下降 35.8 个百分点；120 个配对成员中 43 个退化、0 个改善。移除 ontology / identity / crosswalk 后 aggregate 下降 3.3 个百分点。

**支撑内容：**

- 支撑一个受限结论：完整 KG 上下文在 alias/crosswalk、跨任务 precedence、错误候选计划纠正和部分质量降级等复杂语义处境中，比规则和固定流程表现出更强的 canonical planning 与 semantic delivery 能力。
- 支撑 capability / algorithm grounding 是当前三类 KG 模块中贡献证据最强的一类；它直接影响合法算法选择和 clean-case 可执行规划。
- 支撑“KG 的价值集中在特定复杂决策，而不是所有案例普遍增益”的研究解释。该证据不能升级为严格综合指标、hard-veto、真实 GIS E2E 或所有 KG 模块均必要的结论。

**证据边界：**

- Held-out 的 semantic delivery 是 post-hoc diagnostic，不是预声明 primary endpoint；正向区间只能作为下一轮预注册语义指标实验的依据。
- Held-out 没有执行三个 `without_*` 消融条件，因此 capability 和 ontology 的模块必要性仍需独立 held-out 复验。
- 两轮运行均记录 `git_dirty=true`；精确复核必须使用各自 manifest 中的源码、Prompt 和 KG semantic hash，不能只依赖 Git commit。

**证据位置：**

- `D:\code\FusionAgent\runs\experiments\adversarial-baseline-v1-qwen37-20260904-live-w4`
- `D:\code\FusionAgent\runs\experiments\heldout-confirmatory-v1-qwen37-20260905-live-w4`
- `D:\code\FusionAgent\experiments\heldout_confirmatory_v1\cases.json`，SHA-256 `ae5be68c3d0027c6ff5f0e4ebb0fdd2e0831eaac18cb1f2f75afc0706d06b801`

## 3. 质量验收、渐进交付、恢复与缺口声明

### 3.1 P3-G 治理消融中的机制变化

**实验与数据：**

- 在相同 C02/C04/C06 manifest 和固定环境下分别运行完整方法、无产品契约、无质量门、无降级恢复和固定优先级变体。
- 完整方法恢复成功率为 `0.5`、最终交付成功率为 `0.333333`；无降级恢复变体对应为 `0.0` 和 `0.0`。
- 无质量门变体将首次质量门通过率保存为不可用值，并记录质量门绕过率 `1.0`。
- 每个变体均保存计划、质量状态、恢复机会、交付状态、gap 和证据完整性指标。

**支撑内容：**

- 支撑质量门、恢复、gap 和最终交付可以作为同一产品契约治理链中的独立状态被测量。
- 支撑移除降级恢复会改变恢复机会和最终交付行为。
- 支撑质量门绕过能够被显式标记，不会被自动改写成质量通过。

**证据位置：**

- `docs/current/evidence/p3-governance/2026-08-01-freeze-c-p3-governance.md`
- `docs/current/evidence/p3-governance/2026-08-01-freeze-c-p3-governance-grounding-report-v2.json`

### 3.2 P4-G 多 AOI 的契约化交付记录

**实验与数据：**

- Caracas、Abidjan 和越南北部沿海走廊的 C02/C04 采用同一固定 KG、运行时和输入声明运行；完整方法和固定优先级各形成 7 个可比较案例。
- 完整方法 7 个案例的计划有效率、最终交付成功率、gap 声明正确率和证据完整率均为 `7/7`。
- 完整方法关键图层按时交付率为 `6/7`，固定优先级为 `3/7`，探索性 Cohen h 为 `0.9389505`。
- 完整方法的 4 个恢复机会全部记录成功，平均重试 child 数为 `1.0`。

**支撑内容：**

- 支撑灾害情景和产品契约中的图层优先级能够改变任务顺序，并反映在关键图层按时交付指标中。
- 支撑计划、质量门、交付状态、gap 和证据记录可以在多个 AOI 上使用同一结构表达。
- 支撑“产品是否满足契约”可以由计划有效、首次质量门、最终交付、及时性、gap 正确性和证据完整性共同描述。

**证据位置：**

- `docs/current/evidence/p4-external-validity/2026-08-01-freeze-c-p4-external-validity.json`
- `docs/current/evidence/p4-external-validity/2026-08-01-freeze-c-p4-external-validity.md`

### 3.3 真实选择性 E2E 的渐进式交付和 supersession

**实验与数据：**

- C04 Caracas 道路案例先生成 OSM provisional artifact：16,279 个要素、`invalid_geometry_count=0`、`null_geometry_count=0`。
- Microsoft 道路到达后生成第二阶段 artifact：23,760 个要素、`invalid_geometry_count=0`、`null_geometry_count=0`。
- 两阶段 artifact 均通过各自质量验收，并保存独立 SHA-256；`supersession.json` 记录后一产品替换前一 provisional 产品。
- C02 在出现未计划的 waterways source expansion 时于算法执行前 fail closed，同时保留已完成的 water polygon artifact 和失败证据。

**支撑内容：**

- 支撑“先交付可用产品、完整数据到达后再替换”的渐进交付机制可以生成真实 GIS artifact 和正式 supersession 关系。
- 支撑最终交付不是单一成功/失败布尔值，而是可以表达 provisional、degraded、failed、superseded 和已保留产物。
- 支撑缺口和失败原因可以进入正式交付证据，而不是只保存在运行日志中。

**证据位置：**

- `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c04-road-e2e-r4`
- `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c02-water-road-e2e-r2`
- `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-s6-selective-e2e-audit-v1`

## 4. 任务特定融合质量与数据产品评价

### 4.1 Freeze C 的产品级质量指标

**实验与数据：**

- C02 水面、水系线，C04 水面和 C06 道路分别保存实际 GIS 输出、CRS、AOI 一致性、要素数、几何类型、无效几何率、重复率、字段非空统计和源贡献。
- C02 水系线融合结果为 392 个要素，两个数据源均有实际贡献，且无效几何率和重复几何率均为 `0`。
- C04 最终水面结果相对于 provisional OSM 产品增加 HydroLAKES 来源要素，并保持无效几何率和重复几何率为 `0`。
- C04 道路两阶段结果分别保存 16,279 和 23,760 个要素的质量报告与 artifact hash。

**支撑内容：**

- 支撑系统对建筑、道路、水面、水系线和 POI 类产品采用任务特定质量字段，而不是只以任务完成状态替代数据质量。
- 支撑多源贡献、几何合法性、属性状态、覆盖和交付阶段能够共同进入产品评价。
- 支撑产品契约满足度可以与实际 GIS artifact 的质量证据绑定。

**证据位置：**

- `docs/current/evidence/p2-stability/2026-08-01-freeze-c-p2-stability.json`
- `D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c04-road-e2e-r4`

## 5. 可复现实验证据方法

### 5.1 Freeze C 独立审计和三次重跑

**实验与数据：**

- P1 独立审计验证 638 个声明文件、639 个实际文件、9 个外部数据源和 32 个外部输入文件；manifest、逐文件哈希、冻结 commit 和 clean worktree 检查全部通过。
- 同一 commit、冻结输入和固定环境完成 3 次独立重跑。
- 三次运行的计划、阶段、要素数、覆盖、质量指标、gap、prepared-input 语义哈希、任务顺序和 supersession 拓扑无语义差异。
- ZIP/container 字节差异全部归类；未分类字节差异为 `0`。

**支撑内容：**

- 支撑源码、KG、原始输入、prepared input、计划、输出、质量报告和证据清单可以统一冻结和复核。
- 支撑语义稳定哈希能够把运行身份、时间戳和 ZIP 容器变化与知识或结果漂移区分开。
- 支撑独立审计者可以从 manifest 和外部锚定哈希验证实验包。

**证据位置：**

- `docs/current/evidence/2026-08-01-freeze-c-p1-audit.json`
- `docs/current/evidence/p2-stability/2026-08-01-freeze-c-p2-stability.json`
- `D:\code\freeze-c-evidence\exp-c02-c04-c06-20260725-final-93ebdc5`

### 5.2 真实 LLM 实验的原始响应与人工评价链

**实验与数据：**

- 原六组中的三类 LLM 条件完成 90 次调用，18 个 cell 各 5 次，总 token 为 `1,171,179`。
- 每次调用保留模型、Provider、输入、原始响应、结构检查、grounding、token、latency 和失败记录。
- H07-H09 confirmation 保存盲 key、双评、分歧和裁决结果，并将 planning 结果与 E2E 结果分开登记。

**支撑内容：**

- 支撑真实 LLM 规划研究可以保存调用事实、原始输出、自动评价和人工评价的完整链路。
- 支撑 development、repair、confirmation 和 E2E 可以按不同证据身份隔离。
- 支撑负结果、失败调用和未通过项能够保留在同一冻结 evidence root 中。

**证据位置：**

- `D:\code\fusionagent-evidence\p3-planning-repeated\2026-08-15-deepseek-v4-flash-repeated-combined-v1`
- `D:\code\fusionagent-evidence\p3-planning-method-b\2026-08-18-method-b-independent-confirmation-manual-adjudication-v1`
- `docs/current/research-experiment-ledger.md`

### 5.3 Benchmark Platform Core V1 的证据基础设施

**实验与数据：**

- P0-P6 核心行为合同测试为 `64 passed`。
- P7 机器检查 `10/10`，七项人工复核全部批准；BP7 总检查 `11/11`。
- implementation manifest、checkpoint、audit、失败尝试和文件 SHA-256 已绑定到 tag `benchmark-platform-core-v1`。
- Provider、judge、benchmark instances 和 formal result roots 均为 `0`，冻结对象为离线平台 core。

**支撑内容：**

- 支撑后续参数化 benchmark 可以复用版本化组件合同、fail-closed、视图隔离、恢复、CLI、manifest 和审计机制。
- 支撑研究过程可以按 checkpoint、机器审计、人工复核和 tag 形成可交接的证据基础设施。
- 支撑 I4 作为 I1-I3 的可信性保障进入后续正式实验。

**证据位置：**

- `docs/current/benchmark/platform/v1/implementation/README.md`
- `docs/current/benchmark/platform/v1/implementation/implementation_manifest.json`
- `docs/current/benchmark/platform/v1/implementation/p7_audit.json`
- `docs/current/benchmark/platform/v1/implementation/p7_checkpoint.json`

## 6. 支撑关系总表

| 研究核心/创新点 | 实验和关键数据 | 支撑角度 |
| --- | --- | --- |
| 数据产品契约与一体化七层 KG / I1 | 7 层、71 类、42 关系、241 对象、6 个产品契约、47 个知识片段、冻结 release 与语义哈希 | 将情景、需求、源、算法、质量、恢复和证据统一为可计算、可版本化知识 |
| KG 是实际决策依据 / I2-RQ2 | KG-only 行为扰动、缺失知识 fail-closed、source rematerialization、Neo4j-memory parity | KG 改变规划行为，validator 负责确定性接地，执行链可追溯 |
| 受约束 LLM 编排 / I2-RQ3 | H07-H09 27 次真实调用、63 个 rubric item；B 与 Full KG 均 21/21，LLM-only 17/21 | 结构化契约知识可以进入真实 LLM 规划与人工评价链 |
| 复杂语义规划的局部增量 / I2-RQ3 | Adversarial fault-only：Full KG 13/60、rules 5/60；held-out post-hoc semantic delivery：38/120 对 3/120，差值 29.2 pp，cluster 95% CI [6.7%, 53.3%] | 支撑 full KG 在 alias、precedence、候选计划纠正和质量降级上的局部语义优势，不支持整体 superiority |
| 质量验收、渐进交付、恢复和缺口声明 / I3-RQ4 | P3-G 五变体；P4-G 7 个可比较案例；C04 16,279 -> 23,760 要素及 supersession；C02 fail-closed | 产品状态、质量门、恢复、及时性、gap 和证据能够形成闭环 |
| 任务特定融合质量 | 多源贡献、几何合法性、重复率、字段状态、AOI 一致性、artifact hash | 产品契约满足度与真实 GIS 输出质量证据绑定 |
| 可复现实验证据方法 / I4 | P1 独立审计、3 次语义稳定重跑、真实 LLM 原始响应、P7 离线平台审计 | 研究结果、失败和治理过程可冻结、复核、追溯和交接 |
