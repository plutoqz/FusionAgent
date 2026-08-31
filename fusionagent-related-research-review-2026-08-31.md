# 面向灾害应急多源地理空间融合的契约化知识图谱与受约束规划：研究综述与创新性评估

> 文档类型：研究综述与研究定位评估
> 截止日期：2026-08-31
> 对应项目：FusionAgent
> 当前研究基线：`fusionagent-kg-v1.0.0`、`benchmark-design-freeze-v1`、`benchmark-platform-protocol-v1`、`benchmark-platform-core-v1`

## 摘要

灾害应急地理信息处理正在从单一遥感识别和静态制图，转向多源数据融合、连续状态更新、面向任务的地理分析和可审计决策。知识图谱能够为异构数据提供语义互操作、空间—时间关联和约束表达；大语言模型（LLM）及工具增强 Agent 则提供自然语言任务理解、工作流编排和代码生成能力。然而，灾害场景中的正确性不只取决于文本语义相似度，还取决于坐标和拓扑关系、数据源可用性、产品契约、质量门、时序状态、失败恢复和证据链。2025—2026 年的新工作进一步表明，地理有效性、层级推理、真实 GIS 多步工作流、执行轨迹和严格输出比对正在成为评价重点。

本文围绕 FusionAgent 的研究核心任务和四项拟定创新点，综述灾害 GeoAI、多源地理数据融合、地理知识图谱、LLM 地理推理与 Agent、约束规划与确定性接地、数据质量/溯源/可复现性以及 benchmark 研究进展。综述结论是：研究问题仍具有明确意义，I1（契约化七层 KG）和 I4（可复现证据方法）具有较稳固的研究定位；I2（KG 约束规划与确定性接地）具有方法创新潜力，但必须通过公平的六组对照、反事实案例和人工评价建立效果证据；I3（质量与证据驱动的闭环恢复）具有应用价值和系统贡献潜力，但需要预注册故障机会、跨 AOI 对照和真实端到端验证。当前实验已经支撑“限定场景中的 KG 建模、行为绑定和证据闭环”，尚未支撑“普遍的规划优越性、恢复率提升或生产级能力”。

**关键词：** 灾害应急；GeoAI；知识图谱；地理信息系统；大语言模型；工具增强 Agent；受约束规划；数据溯源；可复现性；benchmark

## 1. 综述范围与检索方法

### 1.1 问题范围

本文只讨论与以下研究链直接相关的工作：

```text
灾害情景 -> 数据产品契约 -> 数据源/算法能力 -> 受约束规划
         -> 执行与质量门 -> 降级/恢复 -> 证据与经验回写
```

不把底层建筑物、道路、水体或 POI 融合算法本身的精度提升作为本课题的主要创新，也不把通用聊天机器人、开放域应急指挥或生产级多租户平台纳入核心比较。

### 1.2 检索与证据分层

- 截止日期：2026-08-31。
- 检索主题：`geospatial knowledge graph`、`disaster response geospatial AI`、`GIS agent`、`large language model spatial reasoning`、`GeoAI benchmark`、`RAG knowledge graph grounding`、`geospatial provenance reproducibility` 等。
- 主要检索源：arXiv API（用于 2023—2026 年技术路线和最新预印本），并结合 CrossRef、OpenAlex、Semantic Scholar 的公开入口尝试核对元数据；后两类接口在本次批量访问中受到速率限制，因此新近条目的同行评议状态和 DOI 应在投稿前再次人工核验。
- 本地一手证据：FusionAgent 的研究章程、主张—证据账本、实验账本、KG v1 发布包、Freeze C、P3-G/P4-G 和 Benchmark Platform Core V1 证据。
- 证据等级：
  - **E1：** 同行评议论文、正式标准或规范；
  - **E2：** 已公开技术报告、可复现实验或预印本；
  - **E3：** 本项目冻结的代码、测试和案例证据；
  - **E4：** 研究设计或尚未运行的候选实验。

本文将 E1/E2 文献结论与 E3 项目事实分开，不把预印本结果直接当作已确立共识，也不把本项目测试通过数当作方法效果。

## 2. 研究核心任务与拟定创新点

### 2.1 核心研究任务

FusionAgent 的核心任务是：

> 在限定灾害案例和 AOI 范围内，构建一个面向多源地理空间数据产品的契约化知识图谱，并验证该图谱是否能够作为任务规划、数据源选择、质量验收、降级恢复和证据写回的实际决策依据；在此基础上，评价受约束规划相对固定工作流、规则策略、KG-only 和 LLM-only 的增量价值，并以冻结、哈希、独立验证和重复运行形成可复核的研究证据闭环。

研究对象不是“让 LLM 自主完成所有 GIS 工作”，而是把领域知识、产品要求和运行约束显式化，并限制 LLM 只承担候选计划提议和开放式请求解释。KG 是事实和约束来源，确定性 validator 是接地与验收边界，执行器负责材料化输入、算法调用、质量计算和证据写回。

### 2.2 研究目标与研究问题

| 目标 | 研究问题 | 需要证明的对象 |
| --- | --- | --- |
| O1 | RQ1：七层 KG 能否完整、一致地表达灾害数据产品知识？ | 情景、产品契约、需求、数据源、能力、质量、恢复和证据的统一表示 |
| O2 | RQ2：KG 是否真正决定规划、检索、质量和恢复行为？ | KG 扰动、缺失知识 fail-closed、决策溯源和后端语义一致性 |
| O3 | RQ3：KG 约束规划是否产生更多可执行且满足契约的计划？ | 六组公平对照、pre-fallback 计划质量、契约满足率和人工评价 |
| O4 | RQ4：治理、恢复和证据链是否改善限定案例交付？ | 质量门、恢复机会、渐进交付、gap、supersession、复现和审计 |

### 2.3 四项拟定创新点

**I1：面向灾害应急数据产品的契约化七层知识图谱。** 连接灾害情景、产品契约、数据需求、数据源语义、算法任务能力、规划决策、执行质量及证据经验，使原本分散在代码、配置和服务函数中的知识成为可查询、可验证、可版本化对象。

**I2：知识约束的规划与确定性接地机制。** 规划器只能从 KG 提供的候选能力、产品约束、资源状态和历史证据空间提出计划；确定性 validator 检查类型、依赖、参数、契约和运行能力。LLM 不是知识真源，也不能决定质量是否通过。

**I3：质量与证据驱动的闭环恢复机制。** 将质量门结果、故障类型、合法降级、修复策略、gap 声明和 supersession 纳入同一知识与证据链，使失败、恢复选择和最终交付状态可追溯，并可沉淀为后续规划经验。

**I4：面向知识驱动系统的可复现实验证据方法。** 统一冻结 KG、输入、prepared input、规划、输出、质量报告和证据清单，以语义稳定哈希、独立 verifier、篡改检测和运行清单区分元数据变化与知识/结果漂移。

## 3. 灾害 GeoAI 与多源地理空间融合

### 3.1 从遥感识别到应急工作流

传统灾害 GeoAI 主要集中在灾害检测、变化检测、建筑物损毁识别、洪水范围提取、道路可通行性和风险制图。深度学习和地理空间基础模型提升了影像表征与跨区域迁移能力，但灾害响应还需要把影像、矢量、道路网络、人口暴露、行政边界、气象和历史事件放入同一任务链。综述类工作普遍指出，多模态、时空分辨率差异、域偏移、标注稀缺和不确定性传播是主要问题。

2025 年的多模态地理空间基础模型综述将灾害响应列为重要应用场景，强调跨模态对齐、多分辨率和多时相融合、可解释性与域泛化仍是关键挑战。[R1] 2026 年的 `Agentic AI for Remote Sensing` 进一步指出，重投影、重采样、合成和聚合会改变后续状态；错误可能在多步工作流中静默传播，因此 EO Agent 必须围绕结构化地理状态、工具感知推理、验证器引导执行和有效性评价设计，而不能直接套用通用 Agent 架构。[R2]

### 3.2 数据融合的语义瓶颈

多源融合的困难并不只是格式转换，而是：

1. 同一对象在不同数据源中的标识、几何、时间和属性语义不一致；
2. 数据源的覆盖范围、更新频率、许可和可用性不同；
3. 产品要求通常包含隐含的质量阈值、必需图层、降级状态和交付时序；
4. 规划失败可能来自知识缺失、源不可用、算法能力不匹配、质量门失败或执行环境，而这些原因需要分层诊断。

这解释了为什么单纯提高影像模型或代码生成模型的分数，不等价于提高灾害数据产品交付能力。FusionAgent 将研究对象放在“契约—能力—源—质量—恢复”的中间层，具有明确的工程和研究意义。

### 3.3 与本课题的关系

现有灾害 GeoAI 工作主要验证感知精度、风险预测或单项分析；本课题关注的是将异构知识组织成可计算约束，并让约束贯穿规划、执行、质量和证据。其潜在贡献不是替代遥感或 GIS 算法，而是为这些算法提供一个可审计的任务编排和交付语义层。

## 4. 地理知识图谱与语义互操作

### 4.1 知识图谱的一般进展

知识图谱研究已经形成较成熟的实体—关系表示、schema/ontology、规则推理、知识图谱问答和图嵌入体系。Hogan 等人的综述将 KG 概括为整合异构事实、支持查询和推理的结构化知识基础，并系统讨论了构建、质量、推理和应用问题。[R3] FAIR 原则进一步要求数据具有可发现、可访问、可互操作和可复用的元数据与标识。[R4]

地理知识图谱的特殊性在于空间、地点和时间不是普通属性，而是连接数据孤岛的主索引。KnowWhereGraph 将跨领域环境、人口、供应链、公共健康和自然灾害数据置于大规模 Geo-KG 中，强调空间—地点—时间的桥接、预集成和 FAIR/AI-ready 数据仓库。[R17] 这与 FusionAgent 的 I1 方向高度一致，但 KnowWhereGraph 的主要目标是跨域数据整合和知识发现，FusionAgent 更关注面向数据产品生成的契约、能力、质量和恢复约束。

### 4.2 本体、空间标准与来源记录

GeoSPARQL 为地理对象、空间关系和查询提供了标准化表达；PROV-O 则为实体、活动、代理和派生关系提供通用来源模型。[R6-R7] 这些标准说明，FusionAgent 将产品契约、数据源、算法能力和证据纳入 KG 并非孤立做法，而是可以与既有语义 Web 和 provenance 体系对接。

当前不足在于，许多地理 KG 论文的评价停留在覆盖率、链接预测、问答准确率或数据访问示例，较少把 KG 约束直接连接到“计划选择—实际执行—质量验收—降级恢复—证据写回”的闭环。I1 的创新空间因此不在“首次使用 KG”，而在于面向灾害数据产品建立任务可执行、约束可验证、版本可冻结的垂直 KG 切片。

### 4.3 与 FusionAgent I1 的差异化定位

| 维度 | 大规模地理 KG/数据仓库 | FusionAgent 的 I1 |
| --- | --- | --- |
| 主要目标 | 数据整合、发现、查询和地理富化 | 数据产品生成与交付的契约化约束 |
| 核心对象 | 地点、观测、环境和社会经济实体 | 情景、契约、需求、源、能力、质量、恢复、证据 |
| 评价重点 | 覆盖、互操作、查询和富化 | CQ/约束闭合、案例 crosswalk、规划消费和证据追溯 |
| 运行关系 | 多数作为查询或知识服务层 | 必须实际改变 planner、validator、source resolver 和 recovery selector 行为 |
| 版本边界 | 数据仓库/ontology 版本 | KG release、semantic hash、输入输出和运行证据联合冻结 |

## 5. LLM 地理推理、RAG 与 GIS Agent

### 5.1 LLM 的地理知识与空间推理边界

`Are Large Language Models Geospatially Knowledgeable?` 通过坐标探测、空间介词和城市位置多维尺度实验指出，LLM 虽然包含一定地理知识，但需要更大或更适合的模型才能从文本信息中稳定综合地理关系；模型规模不能替代空间计算能力。[R16] `GeoLLM` 将 LLM 的文本知识与 OpenStreetMap 辅助信息结合，用于人口密度和生计预测，报告相对简单基线的明显提升，但它解决的是地理预测，不是数据产品工作流规划。[R15]

2025 年关于地理知识幻觉的工作使用结构化 Geo-KG 评估 20 个 LLM，并提出动态事实对齐方法；其核心启示是，地理幻觉需要在结构化空间知识上进行受控评估，不能只依赖一般语言事实性指标。[R35]

2026 年的 `MultiGlobeQA` 在 201 个国家和地区、16 种语言上评估距离、包含、方向、网格索引和形状计算，发现即使提供 gold facts，模型在网格索引和几何计算上仍明显失败，说明“检索到了知识”与“正确执行空间计算”是两个不同瓶颈。[R29] 这一结果直接支持 FusionAgent 将 LLM 与确定性 validator、空间运算器和执行器分离。

### 5.2 RAG 和知识图谱增强

RAG 通过从外部知识库检索证据来减少参数记忆的过时和幻觉问题；GraphRAG 进一步利用图结构形成局部实体上下文和全局社区摘要。[R10,R13-R14] 但在地理领域，语义相似并不等于空间有效：检索到“同名城市”或相邻行政层级的事实，可能在地理决策中产生错误结论。

`GeoGPT-RAG` 将地学语料库、领域 embedding 和 reranker 集成到 GeoGPT，用于提高地学问答的领域对齐。[R34] `GeoRisk-RAG` 则显式引入地理层级 DAG 和 selective answering，在野火问答中降低 location-dependent 问题的错误自信率，强调在高风险地理场景中“拒答或降级”是可靠性组成部分，而不是失败。[R33]

DisasterLex 是与本课题最接近的 2026 年工作之一：它构建专家概念图，使用概念—表结构映射，将查询实体识别、领域路由、因果边规划和 SQL grounding 分阶段执行，在 36 张地理灾害表和 75 个查询上优于多个 RAG/Text-to-SQL baseline。[R32] 它支持“专家 KG + 受限上下文 + 分阶段 grounding”的路线，但主要输出是数据库查询，尚未覆盖多源材料化、融合算法、质量门和交付恢复。

### 5.3 GIS Agent 的演进

早期 GeoGPT 将自然语言理解、GIS 工具调用和数据获取组合成自主 GIS 原型，展示了面向数据爬取、空间查询、选址和制图的 Agent 范式。[R18] 后续工作分别强化了数据检索、代码生成、静态分析、RAG 和多步搜索：

| 工作 | 主要贡献 | 对本课题的启示 |
| --- | --- | --- |
| GeoGPT [R18] | 自然语言到 GIS 工具链 | 证明用户入口可自然语言化，但案例规模有限 |
| Autonomous GIS data retrieval [R19] | 数据源 handbook、生成/执行/调试程序、QGIS 插件 | 数据源元数据和可插拔 source catalog 很重要 |
| GeoCode-GPT [R20] | GeoCode-PT、GeoCode-SFT、GeoCode-Eval 和领域代码模型 | 领域语料能提升代码生成，但代码正确不等于契约交付正确 |
| GeoAgent [R21] | 代码解释器、静态分析、RAG、MCTS 和 GIS benchmark | 多步函数调用需要搜索和验证，LLM 知识单独不够 |
| OpenEarthAgent [R22] | 统一工具注册、轨迹学习、确定性 replay，覆盖灾害和基础设施 | 工具 schema、轨迹和可执行重放与 I2/I4 直接相容 |
| GeoForge [R23] | workflow graph memory、action experience、SOP 记忆和安全蒸馏 | 经验回写需要安全门，不能把任意成功轨迹直接变成知识 |

2025 年 `GIScience in the Era of AI` 将 Autonomous GIS 概括为具有数据检索、空间分析、制图和自主决策能力的系统，并提出多层自主等级和研究议程。[R24] 2026 年 `Agentic AI for Remote Sensing` 则明确指出，地理工作流的物理、空间和时间约束使其不能简单复制通用 Agent。[R2] 因此，FusionAgent 的“受约束而非无边界自主”定位仍然符合前沿趋势。

## 6. 约束规划、工具调用与确定性接地

### 6.1 通用 Agent 方法的贡献

ReAct 将推理步骤与行动、观察交替组织，Toolformer 研究让模型学习何时调用外部工具，均奠定了 LLM Agent 的工具增强基础。[R11-R12] 这些方法解决了“模型如何提出和调用工具”的问题，但没有自动解决地理数据的 schema、坐标系、空间拓扑、数据源许可、质量阈值或产品契约。

GeoAgent 的 MCTS、代码解释器和静态分析表明，对复杂 GIS 程序进行候选搜索和执行反馈可以减少逻辑错误。[R21] TerraLogic/HieraPlan 将工具组织成层级并加入故障容忍，在 545 个层级地理推理任务上评价长程规划和跨模态泛化。[R28] GeoDisaster 更进一步，把灾害影像、SAR、矢量几何、道路网络和暴露层放入可执行工作流，使用 18 个灾害工具和显式执行契约评价工具使用、证据 grounding、状态一致性和决策生成。[R27]

### 6.2 从 prompt 约束到可验证约束

现有方法大致分为三类：

1. **提示/上下文约束：** 把规则、文档或 KG 片段放入 prompt；成本低，但可能被上下文长度、顺序和模型注意力影响。
2. **结构化输出约束：** 使用 JSON schema、函数调用或有限状态机限制输出格式；能减少结构错误，但不保证实体、源和算法语义正确。
3. **执行/验证约束：** 先生成候选计划，再由 validator、静态分析、模拟器或真实工具执行检查；更接近真实正确性，但需要完整的能力目录和错误分类。

FusionAgent I2 的合理定位应是第三类：KG 给出候选空间，LLM 提议计划，确定性 validator 负责 grounding、依赖、参数和契约检查，执行器仅消费明确声明的能力。这里真正可发表的技术问题不是“给 LLM 加 KG”，而是如何保证 **selected → resolved → executed → fallback** 因果链逐字段可核对，并把失败归因到知识、投影、规划、验证或执行层。

### 6.3 当前研究的竞争性要求

DisasterLex、OpenEarthAgent、GeoForge 和 GeoDisaster 已经分别覆盖概念图路由、统一工具 registry、轨迹记忆、执行合同和灾害工作流。因此，FusionAgent 如果只展示一个 KG、一个 planner 和若干案例，创新性会不足。必须突出：

- 产品契约和质量门是 KG 的一等对象，而不是 prompt 附件；
- source availability、算法能力和合法降级被统一建模；
- validator 和 evidence manifest 同时约束规划与交付；
- 研究评价区分 pre-fallback 计划、最终 fallback 计划和实际执行结果；
- 失败、拒答、provisional/degraded 和 supersession 是可评价的正确状态。

## 7. 数据质量、溯源与可复现研究

### 7.1 数据质量不是单一准确率

灾害数据产品的质量至少包括位置和几何有效性、属性完整性、时间有效性、源覆盖、拓扑一致性、契约满足和证据完整性。一个最终文件“存在”或一项自动检查“通过”，不能替代对这些维度的分解。质量门的价值在于将不可接受结果阻止在交付之前，并让缺口和降级状态显式化。

### 7.2 Provenance 与 FAIR

PROV-O 提供实体、活动、代理和派生关系的通用来源模型，适合表达输入、处理步骤、输出和责任主体。[R7] FAIR 指导原则要求数据和元数据可发现、可访问、可互操作和可复用，强调持久标识、丰富元数据和机器可操作性。[R4] 这些原则与 FusionAgent I4 的 KG release、input hash、prepared input、artifact hash、运行 manifest 和独立 verifier 是一致的。

### 7.3 计算研究可复现性

可复现研究的经典要求包括明确环境、保存原始输入和代码、记录参数与随机性、提供可重复执行脚本，并区分可重复（repeatable）、可复现（reproducible）和可验证（auditable）层级。[R29-R30] 对 LLM 实验还应额外记录 provider、model revision、system prompt、schema、temperature、token budget、重试、修复、fallback 和原始响应。

因此，I4 的研究价值成立，但需要避免把“证据打包”表述成新的 provenance 标准。更准确的贡献是：提出并验证一种适配知识驱动地理工作流的证据合同，将语义哈希、失败留痕、后端 parity、人工复核和研究主张边界放在同一版本化闭环中。

## 8. Benchmark 与评价进展（截至 2026-08-31）

### 8.1 从代码相似度到执行结果

早期 GIS LLM 评价常使用代码相似度、文本评审或单步答案。GeoAnalystBench 使用 50 个真实地理分析任务，评价 workflow validity、结构对齐、语义相似度和 CodeBLEU，并发现空间关系检测和最优选址仍然困难。[R25] 这说明代码质量指标不能单独代表 GIS 任务正确性。

GISAgentBench 将评价推进到 349 个来自 GIS Stack Exchange 的多步任务，绑定真实公共数据、可执行 reference trajectory 和精确 ground-truth output，使用容差感知的确定性输出比对；截至 2026-08-03，其最佳 Agent 严格完成率仅为 32.7%。[R26] 这一结果对本课题有两层意义：一是严格可执行 benchmark 的必要性得到强化；二是任何“Agent 已能自动完成 GIS”表述都需要非常谨慎。

### 8.2 灾害和地球观测专用 benchmark

| Benchmark/工作 | 时间 | 任务范围 | 评价特点 | 对 FusionAgent 的启示 |
| --- | --- | --- | --- | --- |
| GeoAnalystBench [R31] | 2025 | Python GIS 工作流与代码 | 专家验证、validity、CodeBLEU | 增加真实任务和专家 rubric |
| FloodSQL-Bench [R33] | 2025 | 洪水管理多表 Text-to-SQL | 空间/键/混合 join，RAG 条件固定 | 需要 domain-specific、multi-table、空间 join |
| GeoDisaster [R27] | 2026 | 5 类灾害 Geo-Intelligence | 2,921 verified instances、可执行工作流和确定性检查 | 灾害 benchmark 应有工具、状态和证据 ground truth |
| TerraLogic [R28] | 2026 | 545 个层级 EO 推理任务 | 层级空间推理、跨模态、故障容忍 | 增加层级约束和长程失败测试 |
| Obshazard-bench [R34] | 2026 | 8 类灾害、实时观测流 | 生命周期 VQA，预测—演化—影响三阶段 | 对时效性、原始观测和事件生命周期建模 |
| MultiGlobeQA [R29] | 2026 | 46,060 个多语言空间问答 | 三个 KG、执行式 ground truth | 地理覆盖、语言和公平性不能只用单一 AOI |
| GISAgentBench [R26] | 2026 | 349 个真实多步 GIS 任务 | 精确输出文件、容差感知比对 | 将最终 artifact correctness 置于 LLM judge 之上 |

### 8.3 评价范式的共同趋势

截至 2026-08-31，前沿 benchmark 呈现五个共同趋势：

1. 使用真实或可执行数据，而不是仅用文本问答；
2. 评价完整工作流和最终输出，而不是只看单步答案；
3. 采用 deterministic ground truth、容差或规则校验，降低 LLM judge 的主观性；
4. 将工具失败、状态一致性、层级空间关系和时序状态纳入任务；
5. 公开数据、代码、轨迹和复现实验协议，允许独立执行者验证。

这使 FusionAgent 的 benchmark 设计方向是正确的，但也意味着平台 core 的离线合同测试只能算基础设施证据，必须通过新的实例、真实 LLM、人工评价和执行结果才能形成方法证据。

## 9. 代表性研究对照与研究空白

| 研究方向 | 代表工作 | 已解决问题 | 尚未覆盖的组合问题 | FusionAgent 可切入点 |
| --- | --- | --- | --- | --- |
| Geo-KG 数据整合 | KnowWhereGraph [R5] | 异构数据预集成、空间—时间桥接、FAIR/AI-ready | 面向数据产品契约的规划和恢复 | 契约、能力、质量、恢复和证据的一体化 KG |
| 地理问答/RAG | GeoGPT-RAG [R15]、GeoRisk-RAG [R16] | 领域检索、地理层级有效性、选择性回答 | 多源材料化和执行状态闭环 | 地理上下文投影、拒答/降级与执行证据 |
| 灾害 KG + SQL | DisasterLex [R17] | 概念路由、因果规划、schema grounding | GIS 算法、产品交付、质量门和恢复 | 从查询正确性扩展到产品工作流契约 |
| GIS Agent | GeoGPT [R18]、GeoAgent [R21] | 自然语言到工具链、多步代码与搜索 | 统一知识真源、失败因果归因和证据 | KG 约束、validator 和 selected/resolved/executed 分离 |
| EO Agent | OpenEarthAgent [R22]、GeoForge [R23]、TerraLogic [R27] | 工具 registry、轨迹 replay、技能记忆、层级推理 | 产品契约和跨数据源交付状态 | 约束知识、恢复策略和证据合同 |
| 灾害 Agent benchmark | GeoDisaster [R28]、Obshazard-bench [R34] | 多灾种、生命周期、多模态、执行式 ground truth | 产品契约、质量门和可追溯降级 | 将任务正确性与交付状态、gap 和证据绑定 |
| 可复现与 FAIR | PROV-O [R7]、FAIR [R4]、I4 方向 | 来源、标识、元数据和重复运行原则 | 面向 LLM/Geo-KG 规划的统一证据合同 | semantic hash、失败留痕、独立 verifier 和主张边界 |

由此可见，研究空白不是“没有人把 LLM 和 GIS 连接起来”，而是：**在高风险、异构、多步骤地理数据产品任务中，如何让知识约束真正决定规划和交付，并用可执行、可恢复、可审计的证据证明这一点。** 这个空白仍然存在，但已被 2026 年的 benchmark 和 Agent 工作显著压缩，必须以更严格的实验设计占据位置。

## 10. 当前 FusionAgent 实验事实与文献对照

### 10.1 已有 E3 证据

以下判断来自仓库内冻结材料：[`research-charter.md`](docs/current/research-charter.md)、[`research-claim-evidence-ledger.md`](docs/current/research-claim-evidence-ledger.md)、[`research-experiment-ledger.md`](docs/current/research-experiment-ledger.md)、[`research-evidence-supporting-conclusions.md`](docs/current/research-evidence-supporting-conclusions.md) 和 [`research-evidence-non-supporting.md`](docs/current/research-evidence-non-supporting.md)。这些文件是项目证据入口，不属于外部文献。

| 证据 | 当前事实 | 可支撑的研究层级 |
| --- | --- | --- |
| KG v1 P0-K1/K2/K3/K5 | 7 层、71 类、42 类关系、8 项约束、8 个 CQ、241 个稳定对象、来源和 release hash | I1/RQ1 的限定建模与版本化实现 |
| P0-K4/K5 | KG-only 扰动改变选择；缺失知识和未知 ID fail-closed；source fallback 重新材料化 | I2/RQ2 的限定行为绑定 |
| Neo4j/memory parity | 建筑、道路、水体、POI 的 pattern/step/algorithm/source 顺序保持语义一致 | I2/RQ2 的后端语义一致性 |
| P3-G | 完整方法计划有效率 1.0、恢复成功率 0.5；无降级恢复恢复成功率 0.0 | I3/RQ4 的治理状态可观测性与受限机制观察 |
| P4-G | 三 AOI 切片中完整方法关键图层按时交付 6/7，固定优先级 3/7；计划/交付/gap/证据记录均保留 | I3/RQ4 的跨 AOI 过程观察，不是普遍效果证明 |
| Freeze C/P1/P2 | 三次重跑、未解释语义差异 0、独立 verifier 11/11、输入输出和运行清单冻结 | I4/RQ4 的可复现与审计方法 |
| Benchmark Core P7 | BP7 11/11、核心合同测试 64 passed、七项人工复核批准、Provider/judge/实例/正式结果根均为 0 | I4 的离线实现验证，不是方法效果 |

### 10.2 仍未闭环的证据

原六组真实 LLM 条件共完成 90 次调用，自动均值为 `LLM-only=0.908333`、`Full KG=0.908333`、`Capability KG=0.883333`，且有 72 项自动检查失败；180 个双人盲评 item 尚未完成。H07-H09 中方案 B 与 Full KG 均为 `21/21`，LLM-only 为 `17/21`，不能推出 B 的统计非劣或普遍优越。C06 没有出现预注册的自然质量门失败，正式 recovery 尚未运行。

因此，当前项目与最新文献的关系是：

- 已经具备比一般概念型 GIS Agent 更清晰的 KG、契约和证据边界；
- 已经具备 benchmark 平台的离线合同基础；
- 但尚未达到 GISAgentBench/GeoDisaster 所代表的真实执行式 benchmark 证据强度；
- 尚未证明 KG 条件对真实 LLM 规划有稳定增益，也尚未证明闭环恢复改善总体交付结果。

## 11. 研究意义与创新点站立性评价

### 11.1 研究意义评价

**科学意义。** 该问题连接了知识图谱、GeoAI、LLM Agent、规划验证和可复现计算研究。现有工作通常只覆盖其中一个环节：KG 负责整合，LLM 负责生成，GIS 工具负责执行，benchmark 负责打分。灾害数据产品需要把这些环节放在一个受约束状态机中，因此具有跨领域方法价值。

**应用意义。** 灾害场景允许错误拒答、降级交付和延迟更新，但不允许静默接受错误数据。把产品契约、质量门、source availability 和证据链显式化，可减少“看起来成功但不满足交付要求”的风险，并帮助操作员追踪缺口和后续 supersession。

**工程意义。** 多源 GIS 系统最难维护的部分往往是隐藏在代码和配置中的决策规则。KG release、typed contract、validator、manifest 和独立 verifier 为代码、知识和实验之间建立了可追溯边界，有利于跨团队交接和失败复盘。

### 11.2 四项创新点的站立性

| 创新点 | 当前判断 | 站立理由 | 必须收紧的表述 |
| --- | --- | --- | --- |
| I1 契约化七层 KG | **站得住，但需明确垂直边界** | 现有 Geo-KG 强于数据整合，较少把产品契约、能力、质量、恢复和证据作为可执行对象；KG v1 已有真实结构和运行消费证据 | 不说“首次知识图谱”，改为“面向灾害数据产品交付的契约化 KG 切片” |
| I2 KG 约束规划/确定性接地 | **有潜力，效果主张尚未站稳** | 地理幻觉、空间计算和 GIS 多步工作流仍是公开难题；selected/resolved/executed 与 fail-closed 设计有方法价值 | 不说“KG 提升了 LLM 能力”；应证明在哪些机制和案例条件下减少何种错误 |
| I3 质量/证据驱动恢复 | **应用和系统意义成立，比较性效果待证** | GeoDisaster、TerraLogic 和 GeoRisk-RAG 都强化故障、层级和 selective answering，但尚未覆盖本项目的产品契约—质量—降级—supersession 闭环 | 不说“提高总体恢复率/韧性”；先说“在预注册故障机会中保持合法交付状态和证据一致性” |
| I4 可复现实验证据方法 | **站得住，需定位为证据合同而非新标准** | LLM/GeoAI benchmark 对执行式 ground truth、轨迹和复现需求上升；本项目已有哈希、独立审计、失败留痕和冻结闭环 | 不说“证明方法有效”；应说“使方法效果可以被独立重复和审计” |

### 11.3 对核心研究主张的最新评价

当前最稳健的核心主张应表述为：

> 在限定灾害案例和 AOI 范围内，FusionAgent 设计并实现了一个将数据产品契约、数据源语义、算法能力、质量门、合法降级和证据要求统一到版本化知识图谱中的受约束运行框架；现有实验已观察到 KG 对规划/治理行为和证据链的实际影响，但 KG 相对其他规划条件的普遍效果和恢复收益仍需新的执行式 benchmark、人工评价和多 AOI 故障对照验证。

这个表述比“提出一种普遍优于 LLM 的智能规划方法”更符合当前证据，也比“只是一个 GIS Agent 原型”更准确地体现研究贡献。

## 12. 后续研究设计建议

### 12.1 优先级一：完成已有证据闭环

1. 完成原六组 180-item 双人盲评、分歧裁决和统一统计；保留 90-run 自动负结果。
2. 明确人工评价的统计单元、盲 key、通过标准和一致性指标。
3. 以 pre-fallback planning validity、contract satisfaction、forbidden-action rate、grounding、gap F1、plan stability、token/latency/cost 为主指标，单独报告 fallback 后最终状态。

### 12.2 优先级二：建立可归因的新 benchmark

1. 为每个案例建立唯一 `case-to-KG crosswalk`，禁止 Python alias 和静默替换。
2. 从同一 canonical context 生成六组 allowlist projection，确保 `rules-only` 独立存在。
3. 设计成对反事实、语义不变扰动、输入顺序扰动、多任务组合和 source-availability 变化。
4. 将 `selected`、`resolved`、`executed`、`fallback`、artifact hash 和触发阶段拆开记录。
5. 新确认集不得复用 C01-C06、H01-H06、H07-H09 作为独立样本。

### 12.3 优先级三：补足 RQ4 的故障和真实执行

1. 预注册质量门失败、源不可用、部分交付、supersession 和恢复机会。
2. 自然失败不足时使用协议内故障注入，不事后改变 gold、停止条件或分母。
3. 在多个 source-closed AOI 选择能够区分 planning 的案例，执行真实材料化、融合、质量门和最终契约状态。
4. 将最终 artifact correctness、质量损失、恢复成本和证据完整率纳入评价，而不是只看任务是否返回文件。

### 12.4 优先级四：提升 I1 的知识表达证据

1. 为 8 个 CQ 建立可执行查询、期望实体/关系和独立审阅记录。
2. 与分散 schema/策略表做同口径对照，报告覆盖率、一致性、来源可追溯性和版本迁移成本。
3. 让领域专家评价情景、需求、能力、质量、恢复和证据层的可理解性与完整性。

### 12.5 预期表述升级

| 当前证据层 | 完成补充后可采用的表述 |
| --- | --- |
| KG v1 已建立并被限定运行消费 | 在预注册 CQ、专家评价和案例 crosswalk 下，KG v1 对灾害数据产品知识具有可核对的表达覆盖 |
| KG 扰动改变限定决策 | 单变量 contract/source/quality/failure 扰动在多个任务和后端上产生可预测、可解释变化 |
| B 修复特定接口问题 | task-conditioned projection 在新 held-out benchmark 中的收益或无收益得到预注册统计和人工证据支持 |
| C04 观察到 progressive delivery/supersession | 在多 AOI 故障序列中，契约化恢复保持合法交付状态、gap 正确性和证据一致性 |
| 平台 core 离线合同闭环 | 正式 benchmark 结果可由独立执行者依据 manifest、哈希和 verifier 重复与回溯 |

## 13. 结论

截至 2026-08-31，FusionAgent 的研究核心任务仍然具有现实需求和学术价值，四项拟定创新点没有因为近期 GeoAI/LLM Agent 进展而失效，但它们的创新边界必须从“把 KG、LLM 和 GIS 组合起来”提升为“用契约化知识约束真实地理工作流，并以可执行证据证明其规划、恢复和审计行为”。

最稳固的论文主线是 I1 + I4，并以 I2 的限定行为绑定和 I3 的治理闭环作为受控方法贡献。I2 的比较性效果、I3 的恢复收益和任何跨 AOI 外推都不能由当前离线平台测试或少量案例直接推出。2026 年最新 benchmark 已经把严格输出比对、真实数据、工具失败、层级空间推理、人工评价和复现协议设为基本要求；后续工作若能完成这些闭环，研究可形成“垂直领域 KG + 受约束规划 + 交付治理 + 证据合同”的清晰贡献组合；若不能完成，则应把论文定位收敛为“契约化知识图谱与可审计运行原型及限定案例验证”。

## 参考文献

> 新近 arXiv 条目保留预印本标识；正式投稿前应再次核验版本、会议/期刊接收状态和 DOI。

### 基础理论、标准与方法

- [R1] Survey of Multimodal Geospatial Foundation Models: Techniques, Applications, and Challenges. arXiv:2510.22964 (2025). https://arxiv.org/abs/2510.22964
- [R2] Agentic AI for Remote Sensing: Technical Challenges and Research Directions. arXiv:2604.24919 (2026). https://arxiv.org/abs/2604.24919
- [R3] Hogan, A. et al. Knowledge Graphs. *ACM Computing Surveys*, 54(4), 71 (2021). https://doi.org/10.1145/3447772
- [R4] Wilkinson, M. D. et al. The FAIR Guiding Principles for scientific data management and stewardship. *Scientific Data*, 3, 160018 (2016). https://doi.org/10.1038/sdata.2016.18
- [R5] Janowicz, K. et al. GeoAI: spatially explicit artificial intelligence techniques for geographic knowledge discovery and beyond. *International Journal of Geographical Information Science*, 34(4), 625–636 (2020). https://doi.org/10.1080/13658816.2019.1684500
- [R6] Open Geospatial Consortium. GeoSPARQL 1.1: A Geographic Query Language for RDF Data (2024). https://opengeospatial.github.io/ogc-geosparql/
- [R7] Moreau, L. & Missier, P. (eds.). PROV-O: The PROV Ontology. W3C Recommendation (2013). https://www.w3.org/TR/prov-o/
- [R8] Sandve, G. K. et al. Ten Simple Rules for Reproducible Computational Research. *PLoS Computational Biology*, 9(10), e1003285 (2013). https://doi.org/10.1371/journal.pcbi.1003285
- [R9] Peng, R. D. Reproducible Research in Computational Science. *Science*, 334(6060), 1226–1227 (2011). https://doi.org/10.1126/science.1213847
- [R10] Lewis, P. et al. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. arXiv:2005.11401 (2020). https://arxiv.org/abs/2005.11401
- [R11] Yao, S. et al. ReAct: Synergizing Reasoning and Acting in Language Models. arXiv:2210.03629 (2022/2023). https://arxiv.org/abs/2210.03629
- [R12] Schick, T. et al. Toolformer: Language Models Can Teach Themselves to Use Tools. arXiv:2302.04761 (2023). https://arxiv.org/abs/2302.04761
- [R13] Gao, Y. et al. Retrieval-Augmented Generation for Large Language Models: A Survey. arXiv:2312.10997 (2023). https://arxiv.org/abs/2312.10997
- [R14] Edge, D. et al. From Local to Global: A Graph RAG Approach to Query-Focused Summarization. arXiv:2404.16130 (2024). https://arxiv.org/abs/2404.16130

### 地理 KG、GeoAI 与 GIS Agent

- [R15] Manvi, R. et al. GeoLLM: Extracting Geospatial Knowledge from Large Language Models. ICLR 2024; arXiv:2310.06213. https://arxiv.org/abs/2310.06213
- [R16] Bhandari, P., Anastasopoulos, A., & Pfoser, D. Are Large Language Models Geospatially Knowledgeable? arXiv:2310.13002 (2023). https://arxiv.org/abs/2310.13002
- [R17] The KnowWhereGraph: A Large-Scale Geo-Knowledge Graph for Interdisciplinary Knowledge Discovery and Geo-Enrichment. arXiv:2502.13874 (2025). https://arxiv.org/abs/2502.13874
- [R18] GeoGPT: Understanding and Processing Geospatial Tasks through an Autonomous GPT. arXiv:2307.07930 (2023). https://arxiv.org/abs/2307.07930
- [R19] An Autonomous GIS Agent Framework for Geospatial Data Retrieval. arXiv:2407.21024 (2024). https://arxiv.org/abs/2407.21024
- [R20] Hou, S. et al. GeoCode-GPT: A Large Language Model for Geospatial Code Generation Tasks. *International Journal of Applied Earth Observation and Geoinformation* (2025), 104456. https://doi.org/10.1016/j.jag.2025.104456
- [R21] An LLM Agent for Automatic Geospatial Data Analysis. arXiv:2410.18792 (2024). https://arxiv.org/abs/2410.18792
- [R22] OpenEarthAgent: A Unified Framework for Tool-Augmented Geospatial Agents. arXiv:2602.17665 (2026). https://arxiv.org/abs/2602.17665
- [R23] GeoForge: Non-Parametric Self-Evolving Agents for Earth-Observation Reasoning. arXiv:2608.10494 (2026). https://arxiv.org/abs/2608.10494
- [R24] GIScience in the Era of Artificial Intelligence: A Research Agenda Towards Autonomous GIS. arXiv:2503.23633 (2025). https://arxiv.org/abs/2503.23633

### 地理推理、灾害 Agent 与 benchmark

- [R25] GeoAnalystBench: A GeoAI benchmark for assessing large language models for spatial analysis workflow and code generation. arXiv:2509.05881 (2025). https://arxiv.org/abs/2509.05881
- [R26] GISAgentBench: A Practitioner-Sourced Benchmark for Evaluating LLM Agents on GIS Tasks. arXiv:2608.01645 (2026). https://arxiv.org/abs/2608.01645
- [R27] GeoDisaster: Benchmarking Orchestrated Agents for Operational Disaster Geo-Intelligence. arXiv:2606.17246 (2026). https://arxiv.org/abs/2606.17246
- [R28] TerraLogic: A Benchmark for Hierarchical Geospatial Reasoning in Earth Observation. arXiv:2607.12497 (2026). https://arxiv.org/abs/2607.12497
- [R29] MultiGlobeQA: A Multilingual and Globally Diverse Benchmark for Geospatial Reasoning. arXiv:2608.03882 (2026). https://arxiv.org/abs/2608.03882
- [R30] FloodSQL-Bench: A Retrieval-Augmented Benchmark for Geospatially-Grounded Text-to-SQL. arXiv:2512.12084 (2025). https://arxiv.org/abs/2512.12084
- [R31] Obshazard-bench: Benchmarking Multimodal Foundation Models for Real-Time Disaster Intelligence from Raw Earth Observation Streams. arXiv:2608.00012 (2026). https://arxiv.org/abs/2608.00012
- [R32] DisasterLex: An Expert Concept-to-Schema Knowledge Graph for Geospatial Reasoning in Disaster Analytics. arXiv:2605.30538 (2026). https://arxiv.org/abs/2605.30538; dataset DOI: https://doi.org/10.5281/zenodo.20388029
- [R33] GeoRisk-RAG: A Hierarchy-Aware Risk Framework for Improving RAG Reliability through Selective Answering. arXiv:2608.22634 (2026). https://arxiv.org/abs/2608.22634
- [R34] GeoGPT-RAG Technical Report. arXiv:2509.09686 (2025). https://arxiv.org/abs/2509.09686
- [R35] Mitigating Geospatial Knowledge Hallucination in Large Language Models: Benchmarking and Dynamic Factuality Aligning. arXiv:2507.19586 (2025). https://arxiv.org/abs/2507.19586
