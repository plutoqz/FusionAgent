# FusionAgent 知识图谱本体模式层设计 v2

状态: draft  
分支定位: `research/product-contract`  
用途: 论文表述、知识图谱建模、LLM 规划上下文组织、后续实现对齐

## 1. 设计目标

本文档定义 FusionAgent 面向灾害应急数据产品交付的知识图谱本体模式层。该本体不是单纯的算法目录, 也不是只服务于运行日志记录的工程 schema, 而是用于表达:

- 灾害情景如何影响数据产品需求。
- 数据产品应满足哪些图层、质量、证据和缺口声明要求。
- 数据源、数据类型、算法、任务和 workflow pattern 如何构成可执行能力空间。
- LLM 在何种约束下进行获取、融合、交付和重规划。
- 运行结果如何通过质量门、证据链和经验案例回写到知识图谱。

核心定位:

> 面向灾害应急数据产品交付的契约化知识图谱, 以数据-算法-任务为执行核心, 以灾害情景、产品契约、质量门、证据链、缺口声明和经验案例为决策约束, 支撑 LLM 进行受约束的无人值守规划。

## 2. 建模原则

### 2.1 保留数据-算法-任务三元核心

原有三元结构仍然是执行层核心:

```text
数据类型 / 数据源 -> 算法能力 -> 任务 / 工作流步骤 -> 数据产品输出
```

但该三元结构只回答"系统能做什么", 不能完整回答"为什么这样做、什么条件下这样做、质量是否可接受、缺口如何声明"。因此本文将三元核心放入更大的本体分层结构中。

### 2.2 灾害不是执行三元之一, 而是情景约束层

灾害类型不应直接建模为"洪水使用算法 A"或"地震使用数据源 B"。更合理的表达是:

```text
<洪水情景, 提高, 道路现势性要求>
<洪水情景, 提高, 水体图层紧急度>
<弱网络资源处境, 约束, 多源下载策略>
<短时限响应阶段, 偏好, 渐进式交付策略>
```

具体算法选择由 LLM 在 KG 约束下结合当前数据覆盖、资源条件、产品契约和历史证据完成, 再由确定性校验器验证合法性。

### 2.3 本体编码约束和证据, 不直接编码结论

应避免:

```text
<洪水, 必须使用, OSM道路数据>
<地震, 必须使用, 建筑物融合算法A>
```

应改为:

```text
<洪水情景, 强化, 道路通达性数据需求>
<道路通达性数据需求, 要求, 道路融合产品>
<道路融合产品, 受约束于, 时效优先质量策略>
<OSM道路源, 可满足, 道路原始数据需求>
<OSM道路源, 具有, 静态/准静态现势性属性>
```

这样 KG 提供约束空间, LLM 负责在具体处境中做取舍, validator 负责接地和校验。

### 2.4 英文实现标识与中文本体表述并存

代码和 JSON contract 中保留稳定英文标识, 文档和论文中使用中文本体名称。本文档所有节点均采用:

```text
中文名称 / EnglishId
```

例如:

```text
质量门 / QualityGate
缺口声明 / GapDeclaration
证据链 / EvidenceTrace
```

## 3. 本体分层

建议将 FusionAgent 知识图谱抽象为七层:

| 层级 | 中文名称 | 英文分组 | 主要职责 |
|---|---|---|---|
| L1 | 灾害情景层 | Disaster Context Layer | 表达灾害类型、响应阶段、受影响区域、资源处境和决策目标 |
| L2 | 数据产品契约层 | Data Product Contract Layer | 表达需要交付什么数据产品, 以及交付、质量、证据和降级规则 |
| L3 | 数据需求与数据源语义层 | Data Need and Source Semantics Layer | 表达数据需求、数据源能力、覆盖率、现势性、可信度和缺失状态 |
| L4 | 数据-算法-任务能力层 | Data-Algorithm-Task Capability Layer | 表达数据类型格、算法输入输出、任务、参数和 workflow pattern |
| L5 | 受约束规划层 | Constrained Planning Layer | 表达 LLM 规划策略、获取策略、渐进式交付、重规划和 rationale |
| L6 | 执行质量校验层 | Execution and Validation Layer | 表达运行实例、质量门、schema 校验、runtime contract 和执行状态 |
| L7 | 证据与经验层 | Evidence and Experience Layer | 表达证据链、缺口声明、历史案例、处境签名、结构签名和 pattern 升格 |

## 4. 节点表

### 4.1 L1 灾害情景层

| 中文节点 | EnglishId | 说明 | 关键属性 |
|---|---|---|---|
| 灾害事件 | DisasterEvent | 一次具体灾害或预警事件 | event_id, disaster_type, time, affected_area |
| 用户请求 | UserRequest | 用户自然语言或结构化任务请求 | request_id, modality, requested_area, requested_layers |
| 灾害情景 | DisasterContext | 经过归一化后的情景约束对象 | context_id, disaster_type, response_phase, objective |
| 响应阶段 | ResponsePhase | 应急响应所处阶段 | phase_id, phase_name, urgency_level |
| 资源处境 | ResourceRegime | 网络、时间、计算、预算等资源状态 | network_level, time_budget, compute_budget, priority |
| 图层紧急度 | LayerUrgency | 某灾害情景下不同数据图层的重要性 | layer_type, urgency_score, rationale |
| 冲突轴 | ConflictAxis | 规划时需要权衡的目标冲突 | axis_id, left_goal, right_goal, dominance |
| 处境签名 | SituationSignature | 当前或历史案例的可比较处境向量 | job_type, scenario, aoi_bucket, coverage_class, resource_regime |

### 4.2 L2 数据产品契约层

| 中文节点 | EnglishId | 说明 | 关键属性 |
|---|---|---|---|
| 数据产品契约 | DataProductContract | 一次任务最终要交付的数据产品要求集合 | contract_id, product_type, target_aoi, deadline |
| 数据产品 | DataProduct | 可交付的数据产品类型或实例 | product_id, product_name, output_type, delivery_state |
| 必需图层 | RequiredLayer | 契约中必须或优先交付的图层 | layer_type, required_level, min_quality |
| 输出要求 | OutputRequirement | 输出 schema、字段、格式、CRS 等要求 | output_type, schema_policy_id, required_fields |
| 质量要求 | QualityRequirement | 产品需要达到的质量条件 | metric_name, threshold, severity |
| 证据要求 | EvidenceRequirement | 交付时必须伴随的来源、处理和质量证据 | evidence_type, required, retention_policy |
| 可接受降级 | AcceptableDegradation | 资源不足或数据缺失时允许的降级边界 | degradation_type, allowed_condition, user_visible |
| 缺口声明规则 | GapDeclarationRule | 何时必须生成缺口声明 | trigger_condition, severity, message_template |

### 4.3 L3 数据需求与数据源语义层

| 中文节点 | EnglishId | 说明 | 关键属性 |
|---|---|---|---|
| 数据需求 | DataNeed | 从产品契约派生出的数据输入需求 | need_id, data_type_id, required, direction |
| 数据类型 | DataType | 数据的语义和几何类型 | type_id, theme, geometry_type |
| 数据源 | DataSource | 可获取或可复用的数据来源 | source_id, source_kind, freshness_category, quality_tier |
| 源语义契约 | SourceContract | 数据源的能力、限制和材料化方式 | contract_id, supported_types, materialization_mode |
| 覆盖证据 | CoverageEvidence | 数据源在 AOI 上的覆盖情况 | source_id, coverage_ratio, coverage_class |
| 现势性属性 | FreshnessProfile | 数据源的时间敏感性和更新状态 | freshness_hours, freshness_score, stale_risk |
| 源可信度 | SourceConfidence | 在当前情景下的数据源可信度 | base_score, contextual_adjustment, reason |
| 数据缺失状态 | DataAbsence | 区分未下载、源无数据、任务无关等状态 | absence_type, reason, recoverable |

### 4.4 L4 数据-算法-任务能力层

| 中文节点 | EnglishId | 说明 | 关键属性 |
|---|---|---|---|
| 任务 | Task | 可规划和可执行的任务语义对象 | task_id, category, input_data_types, output_data_type |
| 任务包 | TaskBundle | 一次请求归一化后的任务集合 | bundle_id, requested_tasks, qos_policy_id |
| 算法 | Algorithm | 可执行的算法能力 | algo_id, input_types, output_type, tool_ref |
| 算法参数 | AlgorithmParameter | 算法可配置参数 | key, default, range, tunable, conditional_defaults |
| 工作流模式 | WorkflowPattern | 可复用的规范层 workflow 模板 | pattern_id, job_type, steps, applicability_condition |
| 工作流步骤 | PatternStep | workflow pattern 中的模板步骤 | order, algorithm_id, input_data_type, output_data_type |
| 数据类型转换 | DataTransform | 数据类型之间可达转换关系 | from_type, to_type, transform_algorithm |
| 修复策略 | RepairStrategy | 失败或质量不达标时可使用的修复方案 | reason_codes, from_algorithm_id, to_algorithm_id |

### 4.5 L5 受约束规划层

| 中文节点 | EnglishId | 说明 | 关键属性 |
|---|---|---|---|
| 规划上下文 | PlanningContext | 提供给 LLM 的 KG 检索、约束和证据集合 | context_id, retrieval, constraints, case_evidence |
| 获取策略 | AcquisitionStrategy | 数据下载、复用和优先级策略 | strategy_id, mode, priority_order |
| 渐进式交付策略 | ProgressiveDeliveryStrategy | 先交付临时产品、后台继续融合的策略 | initial_delivery, background_completion, replacement_rule |
| 规划决策 | PlanningDecision | LLM 或 KG planner 生成的规划选择 | decision_id, selected_pattern, rationale, alternatives |
| 规划理由 | PlanningRationale | 对关键取舍的自然语言或结构化解释 | reason_type, evidence_refs, tradeoff |
| 重规划建议 | ReplanningProposal | 条件变化或执行失败后的新计划建议 | trigger_reason, proposed_change, expected_effect |

### 4.6 L6 执行质量校验层

| 中文节点 | EnglishId | 说明 | 关键属性 |
|---|---|---|---|
| 运行实例 | RunInstance | 一次实际执行过程 | run_id, trigger_type, job_type, status |
| 工作流实例 | WorkflowInstance | 一次运行中实际执行的 workflow | workflow_id, pattern_id, planning_source |
| 执行步骤 | ExecutionStep | 实际执行步骤 | step_id, algorithm_id, status, input_ref, output_ref |
| 运行时契约 | RuntimeContract | 执行前必须满足的输入输出和源材料化约束 | contract_id, required_inputs, output_type |
| 质量门 | QualityGate | 判定某项质量要求是否通过的验收节点 | gate_id, metric_name, threshold, pass_state |
| 质量门结果 | QualityGateResult | 某次运行的质量门实测结果 | gate_id, score, passed, evidence_ref |
| Schema 策略 | OutputSchemaPolicy | 输出字段保留、重命名和兼容性规则 | policy_id, required_fields, retention_mode |
| 执行状态 | ExecutionStatus | 成功、失败、修复、降级、后台补交等状态 | status_code, severity, recoverable |

### 4.7 L7 证据与经验层

| 中文节点 | EnglishId | 说明 | 关键属性 |
|---|---|---|---|
| 证据链 | EvidenceTrace | 记录产品从源到输出的来源、处理、质量和决策证据 | trace_id, evidence_items, provenance_refs |
| 证据项 | EvidenceItem | 一条具体证据 | item_id, evidence_type, source_ref, confidence |
| 缺口声明 | GapDeclaration | 对未满足需求、未通过质量门或不可用数据的正式声明 | gap_id, gap_type, severity, impact, mitigation |
| 交付清单 | DeliveryManifest | 用户可见交付物和机器可读产物清单 | manifest_id, artifacts, delivery_state |
| 执行案例 | ExecutionCase | 一次运行沉淀的结构化案例 | case_id, outcome, planning_source, quality_metrics |
| 案例步骤 | CaseStep | 执行案例中的具体步骤绑定 | order, algorithm_id, param_binding, step_outcome |
| 结构签名 | StructuralSignature | workflow DAG 的规范化结构指纹 | signature_hash, canonical_form, novelty_vs_patterns |
| 模式候选 | PatternCandidate | 多次成功案例可能升格出的新 workflow pattern | candidate_id, support, confidence, applicability_condition |
| 持久学习记录 | DurableLearningRecord | 轻量级运行反馈记录 | record_id, success, condition_key, adjustment |

## 5. 关系表

### 5.1 灾害情景关系

| 中文三元关系 | English Relation | 说明 |
|---|---|---|
| `<灾害事件, 归一化为, 灾害情景>` | DisasterEvent NORMALIZED_TO DisasterContext | 将原始事件或用户描述转成可规划情景 |
| `<灾害情景, 处于, 响应阶段>` | DisasterContext HAS_PHASE ResponsePhase | 表达当前应急阶段 |
| `<灾害情景, 具有, 资源处境>` | DisasterContext HAS_RESOURCE_REGIME ResourceRegime | 表达网络、时间和计算限制 |
| `<灾害情景, 提高, 图层紧急度>` | DisasterContext RAISES LayerUrgency | 某灾害情景提高某类图层优先级 |
| `<灾害情景, 激活, 冲突轴>` | DisasterContext ACTIVATES ConflictAxis | 指出当前主导权衡, 如时效 vs 完整度 |
| `<处境签名, 描述, 灾害情景>` | SituationSignature DESCRIBES DisasterContext | 将情景、资源和数据条件压缩为可比较签名 |

### 5.2 产品契约关系

| 中文三元关系 | English Relation | 说明 |
|---|---|---|
| `<灾害情景, 触发, 数据产品契约>` | DisasterContext TRIGGERS DataProductContract | 情景驱动需要交付的数据产品 |
| `<用户请求, 编译为, 数据产品契约>` | UserRequest COMPILED_TO DataProductContract | task-driven 请求也可生成契约 |
| `<数据产品契约, 要求, 数据产品>` | DataProductContract REQUIRES DataProduct | 契约要求交付的产品 |
| `<数据产品契约, 包含, 必需图层>` | DataProductContract INCLUDES RequiredLayer | 产品所需图层 |
| `<数据产品契约, 规定, 输出要求>` | DataProductContract SPECIFIES OutputRequirement | 输出 schema、格式和字段要求 |
| `<数据产品契约, 规定, 质量要求>` | DataProductContract SPECIFIES QualityRequirement | 产品验收门槛 |
| `<数据产品契约, 规定, 证据要求>` | DataProductContract SPECIFIES EvidenceRequirement | 交付时必须提供的证据 |
| `<数据产品契约, 允许, 可接受降级>` | DataProductContract ALLOWS AcceptableDegradation | 资源不足时允许的临时交付边界 |
| `<数据产品契约, 规定, 缺口声明规则>` | DataProductContract SPECIFIES GapDeclarationRule | 何时需要声明缺口 |

### 5.3 数据需求与数据源关系

| 中文三元关系 | English Relation | 说明 |
|---|---|---|
| `<必需图层, 派生, 数据需求>` | RequiredLayer DERIVES DataNeed | 图层需求转成具体数据需求 |
| `<数据需求, 要求, 数据类型>` | DataNeed REQUIRES DataType | 输入或输出数据类型要求 |
| `<数据源, 支持, 数据类型>` | DataSource SUPPORTS DataType | 数据源可提供的数据类型 |
| `<数据源, 受约束于, 源语义契约>` | DataSource GOVERNED_BY SourceContract | 源能力和材料化规则 |
| `<数据源, 产生, 覆盖证据>` | DataSource PRODUCES CoverageEvidence | 某 AOI 下的覆盖情况 |
| `<数据源, 具有, 现势性属性>` | DataSource HAS_FRESHNESS FreshnessProfile | 数据更新和过时风险 |
| `<灾害情景, 调整, 源可信度>` | DisasterContext ADJUSTS SourceConfidence | 情景对源可信度产生修正 |
| `<数据需求, 遇到, 数据缺失状态>` | DataNeed HAS_ABSENCE DataAbsence | 缺数据、不可下载或任务无关 |
| `<数据缺失状态, 触发, 缺口声明规则>` | DataAbsence TRIGGERS GapDeclarationRule | 数据缺失是否需要声明 |

### 5.4 数据-算法-任务能力关系

| 中文三元关系 | English Relation | 说明 |
|---|---|---|
| `<任务包, 包含, 任务>` | TaskBundle CONTAINS Task | 一次请求包含的任务集合 |
| `<任务, 消耗, 数据类型>` | Task CONSUMES DataType | 任务输入数据类型 |
| `<任务, 产出, 数据类型>` | Task PRODUCES DataType | 任务输出数据类型 |
| `<算法, 输入, 数据类型>` | Algorithm HAS_INPUT DataType | 算法输入类型 |
| `<算法, 输出, 数据类型>` | Algorithm HAS_OUTPUT DataType | 算法输出类型 |
| `<算法, 实现, 任务>` | Algorithm IMPLEMENTS Task | 算法可完成某任务 |
| `<算法, 具有, 算法参数>` | Algorithm HAS_PARAMETER AlgorithmParameter | 参数规范 |
| `<数据类型, 可转换为, 数据类型>` | DataType CAN_TRANSFORM_TO DataType | 数据类型格中的可达转换 |
| `<工作流模式, 适用于, 任务>` | WorkflowPattern APPLIES_TO Task | pattern 支持某任务 |
| `<工作流模式, 包含, 工作流步骤>` | WorkflowPattern HAS_STEP PatternStep | pattern 的步骤组成 |
| `<工作流步骤, 使用, 算法>` | PatternStep USES Algorithm | 步骤绑定算法 |
| `<修复策略, 替代, 算法>` | RepairStrategy SUBSTITUTES Algorithm | 失败时替换算法 |

### 5.5 规划关系

| 中文三元关系 | English Relation | 说明 |
|---|---|---|
| `<数据产品契约, 构建, 规划上下文>` | DataProductContract BUILDS PlanningContext | 契约进入规划上下文 |
| `<规划上下文, 检索, 工作流模式>` | PlanningContext RETRIEVES WorkflowPattern | KG 检索候选 pattern |
| `<规划上下文, 检索, 执行案例>` | PlanningContext RETRIEVES ExecutionCase | 检索相似正反案例 |
| `<资源处境, 约束, 获取策略>` | ResourceRegime CONSTRAINS AcquisitionStrategy | 资源限制影响数据获取 |
| `<获取策略, 满足, 数据需求>` | AcquisitionStrategy SATISFIES DataNeed | 获取策略服务于数据需求 |
| `<规划决策, 选择, 工作流模式>` | PlanningDecision SELECTS WorkflowPattern | 选择或改编 pattern |
| `<规划决策, 采用, 获取策略>` | PlanningDecision USES AcquisitionStrategy | 规划包含获取策略 |
| `<规划决策, 生成, 规划理由>` | PlanningDecision HAS_RATIONALE PlanningRationale | 关键取舍解释 |
| `<规划决策, 参考, 执行案例>` | PlanningDecision REFERENCES ExecutionCase | 历史案例作为证据, 不作为直接模板 |
| `<执行状态, 触发, 重规划建议>` | ExecutionStatus TRIGGERS ReplanningProposal | 失败、降级或质量未通过时驱动重规划 |

### 5.6 执行、质量和交付关系

| 中文三元关系 | English Relation | 说明 |
|---|---|---|
| `<规划决策, 实例化为, 工作流实例>` | PlanningDecision INSTANTIATES WorkflowInstance | 规划转成实际 workflow |
| `<工作流实例, 包含, 执行步骤>` | WorkflowInstance HAS_EXECUTION_STEP ExecutionStep | 实际执行步骤 |
| `<执行步骤, 调用, 算法>` | ExecutionStep INVOKES Algorithm | 执行具体算法 |
| `<执行步骤, 消耗, 数据源>` | ExecutionStep CONSUMES DataSource | 使用实际源或 artifact |
| `<工作流实例, 受约束于, 运行时契约>` | WorkflowInstance GOVERNED_BY RuntimeContract | 执行合法性校验 |
| `<质量要求, 实现为, 质量门>` | QualityRequirement REALIZED_AS QualityGate | 把抽象质量要求转成验收 gate |
| `<质量门, 评估, 数据产品>` | QualityGate EVALUATES DataProduct | 质量门作用对象 |
| `<质量门, 产生, 质量门结果>` | QualityGate PRODUCES QualityGateResult | 运行后的实测结果 |
| `<质量门结果, 支撑, 交付清单>` | QualityGateResult SUPPORTS DeliveryManifest | 质量结果进入交付说明 |
| `<执行状态, 标记, 工作流实例>` | ExecutionStatus LABELS WorkflowInstance | 成功、失败、降级、后台补交 |

### 5.7 证据、缺口和经验关系

| 中文三元关系 | English Relation | 说明 |
|---|---|---|
| `<工作流实例, 生成, 证据链>` | WorkflowInstance GENERATES EvidenceTrace | 执行过程产生证据 |
| `<证据链, 包含, 证据项>` | EvidenceTrace CONTAINS EvidenceItem | 证据链由证据项组成 |
| `<证据项, 证明, 数据源>` | EvidenceItem PROVES DataSource | 来源证据 |
| `<证据项, 证明, 执行步骤>` | EvidenceItem PROVES ExecutionStep | 处理证据 |
| `<证据项, 证明, 质量门结果>` | EvidenceItem PROVES QualityGateResult | 质量证据 |
| `<缺口声明规则, 生成, 缺口声明>` | GapDeclarationRule GENERATES GapDeclaration | 根据规则生成缺口声明 |
| `<缺口声明, 解释, 数据缺失状态>` | GapDeclaration EXPLAINS DataAbsence | 解释数据缺失 |
| `<缺口声明, 解释, 质量门结果>` | GapDeclaration EXPLAINS QualityGateResult | 解释质量未通过 |
| `<交付清单, 包含, 数据产品>` | DeliveryManifest CONTAINS DataProduct | 用户可见交付物 |
| `<交付清单, 包含, 缺口声明>` | DeliveryManifest CONTAINS GapDeclaration | 缺口随交付可见 |
| `<工作流实例, 沉淀为, 执行案例>` | WorkflowInstance RECORDED_AS ExecutionCase | 运行经验入图 |
| `<执行案例, 具有, 处境签名>` | ExecutionCase HAS_SITUATION SituationSignature | 案例发生条件 |
| `<执行案例, 具有, 结构签名>` | ExecutionCase HAS_STRUCTURE StructuralSignature | workflow 结构指纹 |
| `<执行案例, 包含, 案例步骤>` | ExecutionCase HAS_CASE_STEP CaseStep | 具体步骤绑定 |
| `<执行案例, 例证, 工作流模式>` | ExecutionCase EXEMPLIFIES WorkflowPattern | 成功案例加固 pattern |
| `<执行案例, 偏离, 工作流模式>` | ExecutionCase DEVIATES_FROM WorkflowPattern | 新颖成功结构作为升格原料 |
| `<结构签名, 聚合为, 模式候选>` | StructuralSignature PROMOTES_TO PatternCandidate | 多次成功后生成候选 |
| `<模式候选, 升格为, 工作流模式>` | PatternCandidate PROMOTED_TO WorkflowPattern | 审阅后进入规范层 |

## 6. 关键三元组示例

以下示例用于论文和文档中的可读表达。

### 6.1 灾害情景到产品契约

```text
<洪水应急情景, 处于, 黄金救援响应阶段>
<洪水应急情景, 具有, 弱网络资源处境>
<洪水应急情景, 提高, 道路图层紧急度>
<洪水应急情景, 提高, 水体图层紧急度>
<洪水应急情景, 激活, 时效-完整度冲突轴>
<洪水应急情景, 触发, 洪水应急矢量数据产品契约>
```

### 6.2 产品契约到数据需求

```text
<洪水应急矢量数据产品契约, 包含, 道路必需图层>
<洪水应急矢量数据产品契约, 包含, 水体必需图层>
<洪水应急矢量数据产品契约, 规定, 时效优先输出要求>
<洪水应急矢量数据产品契约, 规定, 道路连通性质量要求>
<洪水应急矢量数据产品契约, 规定, 来源证据要求>
<洪水应急矢量数据产品契约, 允许, 单源临时交付降级>
<道路必需图层, 派生, 道路融合数据需求>
```

### 6.3 数据源、算法和任务

```text
<道路融合数据需求, 要求, 道路融合输入数据类型>
<OSM道路源, 支持, 道路原始数据类型>
<道路原始数据类型, 可转换为, 道路融合输入数据类型>
<道路融合算法, 输入, 道路融合输入数据类型>
<道路融合算法, 输出, 道路融合数据产品类型>
<道路融合算法, 实现, 道路融合任务>
<道路融合工作流模式, 适用于, 道路融合任务>
<道路融合工作流模式, 包含, 道路融合步骤>
<道路融合步骤, 使用, 道路融合算法>
```

### 6.4 质量门、证据链和缺口声明

```text
<道路连通性质量要求, 实现为, 道路连通性质量门>
<道路连通性质量门, 评估, 道路融合数据产品>
<道路连通性质量门, 产生, 道路连通性质量门结果>
<道路连通性质量门结果, 支撑, 交付清单>
<工作流实例, 生成, 证据链>
<证据链, 包含, 来源证据项>
<证据链, 包含, 处理证据项>
<证据链, 包含, 质量证据项>
<缺口声明规则, 生成, 道路覆盖不足缺口声明>
<道路覆盖不足缺口声明, 解释, OSM道路覆盖不足状态>
<交付清单, 包含, 道路覆盖不足缺口声明>
```

### 6.5 历史经验作为证据而非模板

```text
<工作流实例, 沉淀为, 执行案例>
<执行案例, 具有, 处境签名>
<执行案例, 具有, 结构签名>
<执行案例, 包含, 案例步骤>
<执行案例, 例证, 道路融合工作流模式>
<规划上下文, 检索, 执行案例>
<规划决策, 参考, 执行案例>
```

注意: 最后一组关系表达"参考", 不表达"直接复用"。执行案例进入 planning context 的作用是提供正反例证据, 不是绕过 KG 校验的 workflow replay。

## 7. LLM、KG 与确定性执行层的职责边界

### 7.1 KG 负责什么

KG 负责存储和检索:

- 灾害情景约束。
- 数据产品契约。
- 数据源、数据类型、算法、任务和 workflow pattern。
- 质量门、证据要求和缺口声明规则。
- 历史执行案例和正反经验。

KG 还负责为 LLM 输出提供 grounding 检查依据, 包括数据类型可达性、算法输入输出合法性、source contract 和 runtime contract。

### 7.2 LLM 负责什么

LLM 负责在 KG 给出的约束空间中生成或修正计划:

- 将自然语言请求转译为候选数据产品契约。
- 在时效、完整度、精度、资源限制之间提出取舍。
- 决定先交付哪些图层、后台补交哪些图层、哪些缺口必须声明。
- 参考相似成功和失败案例, 但生成 fresh plan。
- 为关键取舍生成可审计的规划理由。

LLM 不负责:

- 发明 KG 中不存在的数据源或算法。
- 绕过 runtime contract。
- 替代质量门判断结果好坏。
- 直接 replay 历史 workflow。

### 7.3 确定性层负责什么

确定性层负责:

- 校验计划中每个步骤是否接地到 KG。
- 校验数据类型转换路径是否存在。
- 执行算法和数据材料化。
- 运行质量门。
- 生成证据链、交付清单和缺口声明。
- 将运行结果写回经验层。

## 8. 与现有实现的对齐

当前代码中已经具备或部分具备以下对象:

| 已有/接近已有对象 | 对应中文本体 | 状态 |
|---|---|---|
| `TaskNode` | 任务 | 已有 |
| `ScenarioProfileNode` | 灾害情景/场景画像 | 已有, 需要增强冲突和资源语义 |
| `TaskBundleNode` | 任务包 | 已有 |
| `OutputRequirementNode` | 输出要求 | 已有 |
| `QoSPolicyNode` | 质量/服务优先策略 | 已有 |
| `DataNeedNode` | 数据需求 | 已有 |
| `AlgorithmNode` | 算法 | 已有 |
| `DataSourceNode` | 数据源 | 已有 |
| `WorkflowPatternNode` | 工作流模式 | 已有 |
| `DurableLearningRecord` | 持久学习记录 | 已有, 但偏标量化 |

建议新增或显式化:

| 建议新增对象 | 中文本体 | 优先级 | 说明 |
|---|---|---|---|
| `DataProductContract` | 数据产品契约 | 高 | 研究主线核心 |
| `QualityGate` / `QualityGateResult` | 质量门 / 质量门结果 | 高 | 从运行结果提升为本体节点 |
| `EvidenceTrace` / `EvidenceItem` | 证据链 / 证据项 | 高 | 支撑无人值守可审计交付 |
| `GapDeclaration` / `GapDeclarationRule` | 缺口声明 / 缺口声明规则 | 高 | 支撑部分满足和降级交付 |
| `ResourceRegime` | 资源处境 | 高 | 给 LLM 提供非平凡取舍空间 |
| `SituationSignature` | 处境签名 | 中高 | 支撑案例检索 |
| `ExecutionCase` / `CaseStep` | 执行案例 / 案例步骤 | 中高 | 经验层主载体 |
| `StructuralSignature` | 结构签名 | 中 | 支撑 pattern 升格 |
| `PatternCandidate` | 模式候选 | 中 | 支撑自我优化闭环 |

## 9. 分阶段实现建议

### 阶段 1: 本体文档与公共契约对齐

- 固定本文档中的中文节点表和关系表。
- 将 `DataProductContract`, `QualityGateResult`, `GapDeclaration`, `EvidenceTrace`, `DeliveryManifest` 对应到 JSON contract。
- 明确哪些字段是论文概念, 哪些字段已经进入运行时。

### 阶段 2: 规划上下文接入产品契约和资源处境

- 在 planning context 中显式加入产品契约、资源处境、质量门和缺口规则。
- 让 LLM 的输出从"选择算法"升级为"生成获取-融合-交付计划"。
- 保持 validator 对算法、数据类型和 runtime contract 的硬校验。

### 阶段 3: 质量门、证据链和缺口声明入图

- 每次运行后生成质量门结果、证据链和缺口声明。
- 用户报告使用中文可读表述。
- 机器可读 JSON 保留英文稳定标识。

### 阶段 4: 经验案例层

- 将运行后的 workflow、参数、数据源、质量结果和处境签名写为 `ExecutionCase`。
- planning 时检索相似正反案例作为 evidence。
- 禁止直接 replay 历史 workflow。

### 阶段 5: pattern 升格

- 统计反复成功且结构新颖的 `StructuralSignature`。
- 生成 `PatternCandidate`。
- 经人工、LLM curator 或 shadow 模式审阅后升格为 `WorkflowPattern`。

## 10. 论文表述建议

论文中不宜只称"算法-数据-任务三元知识图谱", 因为这会低估本体的研究贡献。建议表述为:

> 本研究构建了一个面向灾害应急数据产品交付的契约化知识图谱。该图谱以数据-算法-任务三元结构作为可执行能力核心, 并进一步引入灾害情景、数据产品契约、资源处境、质量门、证据链、缺口声明和经验案例等本体层, 从而将灾害场景下的数据生产问题转化为受约束、可校验、可解释的智能体规划问题。

对应可读三元组示例:

```text
<灾害情景, 触发, 数据产品契约>
<数据产品契约, 包含, 必需图层>
<必需图层, 派生, 数据需求>
<数据需求, 要求, 数据类型>
<数据源, 支持, 数据类型>
<算法, 输入, 数据类型>
<算法, 输出, 数据类型>
<算法, 实现, 任务>
<工作流模式, 适用于, 任务>
<质量要求, 实现为, 质量门>
<质量门, 评估, 数据产品>
<工作流实例, 生成, 证据链>
<缺口声明规则, 生成, 缺口声明>
<工作流实例, 沉淀为, 执行案例>
<执行案例, 作为证据支持, 规划决策>
```

这组表述既能保持知识图谱论文常见的三元关系表达, 也能准确体现本项目中 KG 给智能体提供的约束、证据和可审计交付能力。
