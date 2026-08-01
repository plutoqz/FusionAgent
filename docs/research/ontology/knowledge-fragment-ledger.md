# FusionAgent 知识片段台账

状态：P0-K3 迁移验收台账  
盘点日期：2026-07-28  
状态复核：2026-07-28（P0-K3 高风险知识迁移与第二权威复核完成）  
对应知识发布：`fusionagent-kg-v1.0.0`  
机器可读附件：[`knowledge-fragment-ledger.csv`](knowledge-fragment-ledger.csv)

## 1. 目的与口径

本台账识别所有会改变任务编译、规划检索、数据源选择、质量验收、降级恢复、灾害语义和知识发布行为的知识片段。它回答三个问题：知识目前在哪里、最终应由谁拥有、如何证明迁移后确实改变运行行为。

状态口径如下：

- **已迁移**：知识已经进入冻结发布，且至少一个主要消费者通过 `KnowledgePolicyRegistry` 或 `entities.json` 使用它。该状态不替代 P0-K3、K4、K5 的行为验收。
- **部分迁移**：冻结发布已有目标表达，但仍存在第二份硬编码权威，或消费者尚未全部切换。
- **待迁移**：已确定归属和目标表达，但运行代码仍拥有唯一或主要决策权。
- **需决议**：发现相互冲突的事实或研究范围，不能在没有研究决策的情况下机械合并。
- **保留代码**：属于解析、计算、下载、几何处理或执行机制，不应迁成领域事实；其输入参数和授权关系仍须来自 KG 或运行配置。
- **执行机制已验收**：K3 已确认该片段不拥有领域或策略知识的第二副本，K4 已通过源重新材料化与 artifact/hash 变化测试。
- **归类完成（运行配置）**：属于实验或部署条件，应冻结进实验 manifest，不进入基础 KG 语义哈希。

迁移边界：**领域事实、策略参数、允许关系和选择顺序进入 KG；通用计算与执行机制保留代码；URL、凭据、超时、backend 选择和实验开关进入运行配置。**

## 2. 总体结论

本轮共登记 47 个片段，覆盖七条决策链。P0-K2 已将七层 schema、实体和政策统一到 `kg/ontology/v1.0.0/`；P0-K3 随后关闭了任务包、规划模式、intent 边界、检索权重、计划后选源、源 closure、质量阈值、故障分类、修复授权、Python seed 分叉和 backend 静默回退等高风险第二权威。这里的“已迁移”是知识归属状态，不替代 P0-K4 的行为扰动与真实后端验收。

当前保留的边界是：

1. 字段 probe order 与国家级字段映射仍在兼容 registry 中，属于中风险 `SRC-08`，不得表述为已完成完整字段本体化。
2. artifact reuse TTL、凭据、URL、超时和 backend 选择属于运行/实验配置，不进入基础 KG 语义哈希。
3. memory/Neo4j 的真实实例排序、语义计划一致性和经验快照隔离已由 P0-K4 在四类任务上完成定向验收；该结果不等于生产规模或长期稳定性证据。
4. alternative source 必须来自 KG `fallback_source_ids`；当前发布未授权的 catalog 不会仅因出现在检索上下文中就被重试。

## 3. Mission 决策链

| ID | 知识片段（性质） | 当前位置 | 消费者 | 冲突/风险 | 迁移归属 | 权威 KG 路径/ID | 状态 | 验证方式 |
|---|---|---|---|---|---|---|---|---|
| MIS-01 | 灾害到默认任务集合和任务包（领域/策略） | `policies.json#disaster_vocabulary`；`entities.json#scenario_profiles,task_bundles`；`mission_compiler_service.py` | mission compiler、scenario runner、planner | **高**：固定子任务数已删除，运行按已编译 task bundle 复核 | KG | `disaster_vocabulary[*].default_task_bundle_id`；`task_bundle.*.emergency_vector` | 已迁移 | 改 `task_kinds` 后编译结果随之变化；删除必要关系时 fail closed |
| MIS-02 | TaskKind、JobType、任务族、输出类型、别名和顺序（领域） | `policies.json#task_semantics`；`schemas/task_kind.py` | mission、retriever、source、quality | **中**：枚举只应保留稳定代码符号 | KG | `task_semantics`；`task.*.fusion` | 已迁移 | 变异 alias/output/order 后消费者同步变化；缺项报错 |
| MIS-03 | 未识别的非灾害请求默认 building（策略） | `policies.json#mission_policy.default_direct_task_kind`；`mission_compiler_service.py` | mission compiler | **中**：默认任务已由版本化 mission policy 解释 | KG | `mission.scope.v1.default_direct_task_kind` | 已迁移 | 改默认政策后结果变化；删政策拒绝编译 |
| MIS-04 | water/POI 任务指令后缀（策略） | `policies.json#task_semantics[*].instruction_suffix`；`mission_compiler_service.py` | mission compiler、intent/planner | **低**：需避免把提示文本当成唯一约束 | KG | `task_semantics[*].instruction_suffix` | 已迁移 | 变异后仅 trigger 文本变化，稳定任务 ID 不变 |
| MIS-05 | 场景期望子任务数和能力边界（策略） | `mission_compiler_service.py`；`scenario_run_service.py:validate_mission_child_specs` | scenario runner/report | **高**：固定 5 已删除，期望数来自编译后的 KG task bundle | KG | `TaskBundle -> CONTAINS -> Task`；`C-REF-CLOSED` | 已迁移 | 增删 bundle 成员无需改代码；覆盖 scope 集成测试 |
| MIS-06 | provisional、supersession 及允许任务范围（策略/执行） | `entities.json#product_contracts`；`scenario_run_service.py` | scenario runner、delivery/evidence | **高**：授权和开关均由 ProductContract 决定，代码只执行状态转换 | KG | `contract.product.emergency_vector_bundle.v1.degradation_policy`；`ALLOWS`；`SUPERSEDES` | 已迁移 | 改契约开关后交付行为变化；禁用时不得生成临时/替代关系 |
| MIS-07 | 规划模式、不支持 intent 与能力边界（策略/领域） | `intent_boundary_policy`；`task_semantics`；`disaster_vocabulary`；intent resolver/guard | preflight、retriever、agent run | **高**：原任务、地点和越界关键词分散；现由冻结知识统一解释 | KG/代码 | `intent.boundary.v1`；`task_semantics`；`disaster_vocabulary` | 已迁移 | alias/rule 变异改变识别；未知显式灾种和越界请求 fail closed；地点词不决定任务类型 |

## 4. Retrieval 决策链

| ID | 知识片段（性质） | 当前位置 | 消费者 | 冲突/风险 | 迁移归属 | 权威 KG 路径/ID | 状态 | 验证方式 |
|---|---|---|---|---|---|---|---|---|
| RET-01 | 检索外层权重、缺失惩罚和 tie-break（策略） | `policies.json#decision_policies`；`retriever.py:rank_retrieval_candidates` | retriever、planner | **中**：主要参数已迁移 | KG | `retrieval.candidate.v1` | 已迁移 | 只改政策即可改变排序；缺政策 fail closed |
| RET-02 | algorithm_fit/workflow_support 内部混合和奖惩（策略） | `policies.json#decision_policies[retrieval.candidate.v1]`；`retriever.py` | retriever、planner | **高**：内部权重、源适配和 workflow 调整已由 registry 读取 | KG | `retrieval.candidate.v1.algorithm_fit_weights/source_fit/workflow_adjustments` | 已迁移 | 逐项变异政策；rationale 记录特征值和 policy ID |
| RET-03 | PolicyEngine 权重、缺失值、主指标混合和学习边界（策略） | `decision.candidate.v2`；`agent/policy.py` | planning decisions | **中**：模型校验边界须与政策一致 | KG | `decision.candidate.v2` | 已迁移 | 权重、mix、missing 值变异测试；边界一致性测试 |
| RET-04 | repository 排序和执行反馈修正（策略） | `inmemory_repository.py`；`neo4j_repository.py`；`runtime_gates.experience_policy` | retriever、planner、healing | **高**：两类 repository 已消费 pinned policy；真实双后端 parity 属 K4 | KG/运行配置 | `experience_snapshot_hash`；`C-EXPERIENCE-SEPARATE` | 已迁移 | 固定 KG/经验快照，双后端候选顺序和语义计划哈希一致 |
| RET-05 | KG 计划后的数据源重排和 plan 原地改写（策略） | `agent_run_service.py:_build_data_source_selection_decision` | executor、input acquisition、trace | **高**：后置评分已改为 audit-only，并保留计划中的 source ID | KG | `PlanningDecision -> SELECTS -> DataSource`；`decision.candidate.v2` | 已迁移 | 改 KG 优先级后实际选源变化；计划后评分不得原地改写 |
| RET-06 | artifact reuse TTL、禁用开关和选择机制（运行策略/执行） | `artifact_reuse_policy.py`；`GEOFUSION_DISABLE_ARTIFACT_REUSE` | retriever、artifact registry | **中**：实验条件不应混入基础领域 KG | 运行配置 | `experiment_manifest.artifact_reuse_policy`；相关环境变量 | 归类完成（运行配置） | manifest 固定 TTL/开关；不改变基础 KG semantic hash |

## 5. Source 决策链

| ID | 知识片段（性质） | 当前位置 | 消费者 | 冲突/风险 | 迁移归属 | 权威 KG 路径/ID | 状态 | 验证方式 |
|---|---|---|---|---|---|---|---|---|
| SRC-01 | 任务源角色、几何、完整性和候选顺序（策略） | `policies.json#source_role_policies`；`data_requirement_resolver_service.py` | requirement resolver、acquisition、planner | **高**：条件仍为字符串，需模式约束 | KG | `SourceContract`；`DataNeed -> REQUIRES_TYPE` | 已迁移 | 改 priority 后顺序改变；删 required role/candidate 时 fail closed |
| SRC-02 | bundle 组件、full closure、partial coverage 和 fallback（策略） | `policies.json#source_bundle_policies`；`source_acquisition_policy.py` | bundle catalog、acquisition、degradation | **高**：主字典已迁移 | KG | `source_bundle_policies`；`catalog.*`；`fallback_source_ids` | 已迁移 | 改 edge/closure 后采集路径改变；证据记录 policy ID |
| SRC-03 | DataSource、支持类型、ref/component 拓扑和路径提示（领域） | `entities.json#data_sources`；`kg/source_catalog.py` 兼容投影 | repository、retriever、asset/bundle resolver | **高**：legacy catalog 已改为从冻结实体派生，不再维护第二份实体清单 | KG | `DataSource`；`SUPPORTS`；`catalog.*`；`raw.*` | 已迁移 | 全仓消费审计；改 entities 后 memory/Neo4j 结果一致 |
| SRC-04 | waterways reference source 身份（领域/策略） | `entities.json`；`source_role_policies`；`source_bundle_policies` | bundle、resolver、quality | **高**：HydroRIVERS 为 portable reference，Pakistan local 仅为 AOI supplement；严格 closure 禁止跨 water-polygon fallback | KG | `catalog.flood.waterways`；`reference_river_line -> raw.hydrorivers.water` | 已迁移 | 实体关系、角色政策、采集证据和质量期望统一引用 HydroRIVERS；禁止跨 water-polygon fallback |
| SRC-05 | 本地 bundle stop condition、补充源和空覆盖规则（策略） | `source_role_policies`；`source_bundle_policies`；`local_bundle_catalog.py` | local bundle、track B、acquisition | **高**：已删除 building stop shortcut、任意 partial 兜底和 Overture 自动追加 | KG | `SourceContract`；`AcquisitionStrategy`；role completeness policy | 已迁移 | 只改 KG 即改变选择；严格 closure 失败；空覆盖生成 gap |
| SRC-06 | runtime alias、priority、readiness required sources、quality expected components（策略） | `source_runtime_bindings`；source/readiness/writeback/Track B consumers | runners、readiness、quality、Track B | **高**：alias、priority、readiness、Track B 和 expected components 均从冻结政策派生 | KG | source runtime/role/bundle policies；quality component policies | 已迁移 | 同一 task 的消费者从 KG 查询派生；禁重复 raw source 顺序表 |
| SRC-07 | runner 的 base/supplement、单源 fallback 和 POI priority（策略/执行） | `source_role_policies`；`source_runtime_bindings`；`domain_fusion_runners.py` | adapters、executor、quality | **高**：角色、优先级和降级授权来自 KG；文件读取和算法调用留代码 | KG/代码 | `SourceRoleRequirement`；`AcceptableDegradation`；`AlgorithmParameter` | 已迁移 | 改 KG role/priority 后输入绑定改变；算法实现不变 |
| SRC-08 | 字段映射、probe order、国家 override、URL/路径/凭据/超时（混合） | `source_field_profile_registry.py`；`source_asset_service.py` | semantic contract、quality、asset resolver | **中**：领域事实、运行配置和执行机制混杂 | KG/运行配置/代码 | 待新增 `FieldMappingProfile`；SourceContract；runtime source settings | 部分迁移 | 映射变异无需改代码；manifest 固定数据版本/超时；下载器只测机制 |

## 6. Quality 决策链

| ID | 知识片段（性质） | 当前位置 | 消费者 | 冲突/风险 | 迁移归属 | 权威 KG 路径/ID | 状态 | 验证方式 |
|---|---|---|---|---|---|---|---|---|
| QUA-01 | 输出字段、保留字段、空值阈值和产品契约关联（领域/策略） | `policies.json#output_contracts`；`output_contract_service.py` | quality、repair、writeback | **高**：已由 registry 构造 | KG | `contract.*.fused.v1`；`contract.product.*.v1`；`SPECIFIES_OUTPUT` | 已迁移 | 改字段/阈值后质量结果变化；删契约 fail closed |
| QUA-02 | 默认质量 policy、检查模板、threshold/operator/severity（策略） | `quality_policies`；`quality_check_templates`；`quality_policy_service.py` | quality gate、writeback、report | **高**：计算器留代码，政策已迁移 | KG | `quality.default.*.v1`；`QualityGate` | 已迁移 | 阈值变异改变 pass/fail；缺 policy/template fail closed |
| QUA-03 | 外部降级时软化检查和 balance 调整（策略） | `quality_adaptation_policy`；`adapt_quality_policy_for_degradation` | quality、degradation | **中**：参数已迁移，适配计算留代码 | KG | `quality.external_degradation.v1`；`AcceptableDegradation` | 已迁移 | 改 soft checks 后 adapted policy 变化；记录来源 ID |
| QUA-04 | 期望几何、lineage 字段和多源 lineage（策略/执行） | `output_contracts`；`quality_gate_service.py` | quality gate | **高**：期望几何和 lineage 字段由 output contract 派生，集合/operator 计算留代码 | KG/代码 | `GeometryConstraint`；`FieldRequirement`；`SourceRoleRequirement` | 已迁移 | 变异契约后判定变化；通用集合和 operator 计算保持不变 |
| QUA-05 | sliver、metadata-only、拓扑等 artifact 阈值（策略） | `artifact_evaluation_policy`；`artifact_evaluation_service.py` | artifact evaluator、quality | **中**：阈值和采样授权已进入政策，计算器保留代码 | KG | `artifact_evaluation.default.v1`；`MetricDefinition/Threshold` | 已迁移 | 阈值/采样授权可按 policy ID 查询；边界值测试和来源证据完整 |
| QUA-06 | 质量失败后的自动 repair 和 expected source components（策略/执行） | `quality_component_policies`；`run_writeback_service.py` | writeback、repair、evidence | **高**：expected components 与 repair allow-list 已由 KG/产品契约决定 | KG | ProductContract repair IDs；QualityComponentPolicy；RecoveryRule | 已迁移 | 删除授权后不得 repair；改变 expected sources 后 lineage 同步变化 |

## 7. Healing 决策链

| ID | 知识片段（性质） | 当前位置 | 消费者 | 冲突/风险 | 迁移归属 | 权威 KG 路径/ID | 状态 | 验证方式 |
|---|---|---|---|---|---|---|---|---|
| HEA-01 | 故障集合、状态归一化、可恢复性和退避参数（策略） | `policies.json#fault_policy`；`source_acquisition_policy.py` | acquisition、scenario handler、recovery | **高**：核心参数已迁移，文本分类另存 | KG | `fault_policy`；`FailureClass`；`RetryPolicy` | 已迁移 | 变异 faults/status/retry 后行为变化；缺 policy fail closed |
| HEA-02 | 异常文本到 FailureClass 的映射（领域/解析） | `fault_policy`；`failure_taxonomy.py`；source/agent/scenario consumers | acquisition、handler、recovery | **高**：异常类型、词法 pattern、source mode 和状态归一化集中于 policy，共用分类器 | KG/代码 | `fault_policy.failure_classes,exception_type_matches,message_patterns,source_mode_by_fault` | 已迁移 | 标准语料经各入口分类一致；未知类进入 manual review |
| HEA-03 | phase/checkpoint/failure 到 recovery action（策略） | `recovery_policy`；`run_recovery_service.py` | recovery worker、scenario handler | **高**：矩阵已由 registry 驱动 | KG | `recovery.default.v1`；`RecoveryRule` | 已迁移 | 决策表测试；无匹配走 default；报告 policy ID |
| HEA-04 | executor 的 source/algorithm/transform 策略顺序与前提（策略） | `recovery_policy.executor_strategy_order`；`agent/executor.py` | executor、repair trace | **高**：executor 按 KG 顺序执行产品契约与全局政策共同授权的策略 | KG | `RepairStrategy`；`executor_strategy_order`；authorized IDs | 已迁移 | 改 KG 顺序后 trace 顺序改变；删授权后不得执行 |
| HEA-05 | alternative source 的真实切换（执行算法） | `agent/executor.py`；上游 input acquisition | executor、acquisition | **高**：候选源知识只在 KG；executor 禁止仅改 source ID，并要求上游重新材料化 | 代码 | KG 仅提供 FallbackEdge | 执行机制已验收 | K4 故障注入已验证 fallback 重新材料化新 artifact/hash，旧 artifact 未被重新标注 |
| HEA-06 | schema/name/topology/geometry repair 的顺序和前提（策略/执行） | `recovery_policy.artifact_strategy_order`；`artifact_repair_service.py` | writeback、quality | **高**：策略顺序和适用性由 KG 控制，几何/字段变换保留代码 | KG/代码 | `RepairStrategy`；`artifact_strategy_order`；Precondition | 已迁移 | KG 控制顺序/禁用；变换独立测试；修后重过同一 policy |
| HEA-07 | 产品契约 repair allow-list 的运行绑定（策略） | product contracts；`agent/executor.py`；`run_writeback_service.py` | planner、executor、writeback | **高**：executor/writeback 已对 plan、产品契约和全局政策取授权交集 | KG | `contract.product.*.v1 -> repair.*`；`AUTHORIZES_REPAIR` | 已迁移 | 删除某 contract 的 repair ID 后相应恢复被拒；trace 固化身份和 strategy ID |

## 8. Hazard 决策链

| ID | 知识片段（性质） | 当前位置 | 消费者 | 冲突/风险 | 迁移归属 | 权威 KG 路径/ID | 状态 | 验证方式 |
|---|---|---|---|---|---|---|---|---|
| HAZ-01 | 灾害类型、别名、ScenarioProfile、TaskBundle 和任务集合（领域） | `disaster_vocabulary`；`entities.json` | normalizer、mission、retriever | **高**：四类灾害已进入发布 | KG | `scenario.*.default`；`task_bundle.*.emergency_vector` | 已迁移 | alias 变异影响归一化；删 profile/bundle 时 fail closed |
| HAZ-02 | 地点别名和救援组织（领域） | `place_vocabulary`；`rescue_organization_terms` | normalizer、AOI input | **中**：仅是限定案例词表，不可宣称通用 gazetteer | KG | `PlaceAlias/GazetteerMapping`；相关 policy section | 已迁移 | alias 归一到固定 canonical/country_code；未知地点不伪匹配 |
| HAZ-03 | 死亡、受伤、失踪数量抽取（执行算法） | `scenario_trigger_normalizer.py:_extract_casualties` | normalizer、scenario context | **低**：解析机制可留代码 | 代码 | `DisasterEvent.casualty_summary` 字段 | 保留代码 | 边界/否定/多数字段测试；不改变 KG hash |
| HAZ-04 | AOI 中灾害词剥离和行政区后缀（领域/解析） | `aoi_resolution_policy`；`disaster_vocabulary`；AOI resolver | AOI resolver | **中**：清洗词、行政前后缀和候选类型来自 registry，解析算法留代码 | KG/代码 | `aoi_resolution_policy`；`disaster_vocabulary`；`PlaceAlias/GazetteerMapping` | 已迁移 | AOI 从 registry 获取词；hazard/location 归一结果一致 |
| HAZ-05 | agent run 灾害推断和 source 灾害兼容（领域/策略） | `disaster_vocabulary`；`intent_boundary_policy`；intent/mission/run consumers | source selection、planning | **高**：所有入口只认 registry；未收录灾种明确 fail closed | KG | `disaster_vocabulary`；`intent.boundary.v1`；`DataSource.disaster_types` | 已迁移 | v1 明确排除 hurricane/wildfire/conflict；未知灾种不得静默映射或绕过过滤 |

## 9. Manifest / Backend 决策链

| ID | 知识片段（性质） | 当前位置 | 消费者 | 冲突/风险 | 迁移归属 | 权威 KG 路径/ID | 状态 | 验证方式 |
|---|---|---|---|---|---|---|---|---|
| MAN-01 | release 索引、文件 hash、semantic hash、experience hash（发布治理） | `release.json`；`knowledge_release.py` | registry、seed provider、实验 verifier | **高**：已有校验器，但尚须所有入口强制执行 | KG | `fusionagent-kg-v1.0.0`；`C-RELEASE-IMMUTABLE` | 已迁移 | 正常校验通过；任一字节变化失败；semantic hash 可重算 |
| MAN-02 | 静态实体和 transform edges 的唯一 manifest（领域/治理） | `entities.json#transform_edges`；`seed_provider.py` | memory repository、seed loader | **高**：已取消 Python transform fallback | KG | `CAN_TRANSFORM_TO`；`C-REF-CLOSED` | 已迁移 | 改 edge 后 traversal 变化；hash/端点异常时拒绝加载 |
| MAN-03 | policy 类型化查询和缺失知识 fail-closed（治理/机制） | `policy_registry.py`；`policies.json` | mission、retrieval、source、quality、recovery | **高**：默认路径验证 release；custom path 未验证 | KG/代码 | `KnowledgePolicyRegistry`；`runtime_gates.missing_required_knowledge` | 已迁移 | required section 缺失抛错；证据记录 knowledge identity |
| MAN-04 | Neo4j bootstrap 的知识输入（治理） | `kg/bootstrap.py`；`seed_provider.load_seed_data` | Neo4j bootstrap/repository | **高**：bootstrap 与 memory 均从冻结 entities 加载，不再 import Python seed 真源 | KG | `release:fusionagent-kg-v1.0.0/entities.json` | 已迁移 | bootstrap 只读 release；节点、边、ID、hash 与 memory 一致 |
| MAN-05 | backend 故障和未知值时 fallback（运行策略） | `kg/factory.py`；`runtime_gates.backend_fallback` | 所有 KG consumers | **高**：strict/research 初始化失败和未知 backend 均明确失败，不再静默回退 | 运行配置/代码 | `runtime_gates.backend_fallback`；`GEOFUSION_KG_BACKEND` | 已迁移 | strict/research 下配置/连接/未知 backend 均非零失败 |
| MAN-06 | memory/Neo4j release、version、hash 绑定（治理） | 两个 repository；bootstrap | planner、validator、evidence | **高**：两类 repository 均绑定 release identity；真实 Neo4j parity 属 K4 | KG/代码 | `KnowledgeRelease`；`REFERENCES_RELEASE` | 已迁移 | 双后端 parity；启动校验 ID/hash；不匹配 fail closed |
| MAN-07 | validator/grounding 默认模式（运行策略） | `runtime_gates`；validator；agent run | validator、agent run、executor | **高**：默认从冻结政策读取 `enforce`；`report` 仅显式诊断 | KG/运行配置/代码 | `runtime_gates.validator_mode/grounding_mode`；`C-STRICT-REQUIRED` | 已迁移 | 无环境变量即 enforce；删必要关系时拒绝；report 仅显式诊断 |
| MAN-08 | 动态经验与基础 KG 隔离、双后端一致性（策略/证据） | `experience_snapshot_hash`；repository `experience_policy` | retriever、learning | **高**：strict/research 已隔离自适应反馈；真实双后端一致性属 K4 | KG/运行配置/代码 | `C-EXPERIENCE-SEPARATE`；`runtime_gates.experience_policy` | 已迁移 | 固定 snapshot 的独立进程/双后端语义 hash 一致；反馈不改 semantic hash |

## 10. K3 退出判断

P0-K3 已完成“决策知识迁移”语义验收：七条决策链均有明确归属，35 个高风险片段全部关闭。其中 34 项知识迁移状态为“已迁移”；`HEA-05` 在 K3 验收时为“执行机制已闭合”，现已通过 K4 行为验收。47 项总台账中仍有 `SRC-08` 一项中风险“部分迁移”、`HAZ-03` 一项“保留代码”和 `RET-06` 一项“归类完成（运行配置）”，均已明确归属且不构成高风险第二权威副本。

K3 静态复核进一步关闭了以下残余：POI bounded 双源条件改读 `quality.components.poi.v1`，Microsoft building 空覆盖语义改读 `fault_policy.empty_coverage_status_by_source`，推断缺失故障和 inspection operator guidance 改读 `fault_policy`。provider adapter 返回的固定 `source_id` 被判定为实现到 KG 实体的身份绑定，不是候选、优先级或 fallback 的知识真源。

K3 的工程归因采用独立 HEAD 基线，而不是要求全量测试无条件全绿：基线为 `1197 passed, 17 failed, 2 skipped`；K3 初次全量为 `1249 passed, 34 failed, 2 skipped`。两者共有失败 10 项，K3 新增 24 项；其中 23 项 A/B/C 类已通过定向回归，剩余 1 项为 Neo4j bootstrap 派生文件同步，归 P0-K5 重封。最终 K3 专属模块套件为 `205 passed`，独立 KG verifier 为 11/11 checks passed；最终全量执行与残余归因记录在 A0 项目状态中。

P0-K4/K5 已于 2026-07-29 完成以下定向验收：

1. 只改 KG pattern 成功率即可改变实际选中 pattern/algorithm，不修改运行代码。
2. 删除必需知识、缺失 schema、未知灾害和 strict backend 不可用均 fail closed。
3. 固定 experience snapshot 后，真实 Neo4j 5.26 与 memory 在建筑、道路、水体和 POI 上通过上下文 parity。
4. 注入 source failure 后，alternative source 重新材料化新 artifact/hash，并保留 policy 与 knowledge identity。
5. 最终冻结包通过 11/11 clean 校验及三份受保护文件的逐文件单字节 tamper 校验。
6. `SRC-08` 的字段映射本体化作为已知中风险后续项保留，不伪装为高风险残项已全部消失。

完成迁移后，台账不得直接删除记录；应将状态更新为“已迁移”，并保留验证命令或测试 ID，形成可审计的知识演化历史。
