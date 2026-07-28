# FusionAgent 当前进展与知识图谱本体说明

> 生成日期：2026-07-27T16:57:47.905572+08:00
> Seed 内容哈希：`sha256:5581d43164cd21b488971fe38456ed0d6a9f43f86b1e4c9d5d1d1fbf16288fcb`
> 当前静态实体：**232**；实体关系：**497**；本体类：**15**；关系类型：**27**。

## 1. 当前进展结论

FusionAgent 已从“能力目录型知识图谱”推进到“产品契约驱动的决策知识图谱”。此前质量门、交付策略、降级规则、缺口声明和证据要求主要分散在配置、规划产物和执行代码中；当前这些内容已经由 `ProductContract` 统一建模，并进入种子清单、仓库、Neo4j 启动、知识检索、规划结果和图谱 API。

当前实现形成以下闭环：

1. 场景处境确定灾种、任务和质量优先级，产品契约进一步限定适用响应阶段。
2. 产品契约规定要交付的产品、图层、质量门、证据、降级和缺口策略。
3. 任务、数据、算法、参数和工作流提供可执行能力。
4. 输出要求、模式策略、QoS、修复策略和运行学习完成验收、恢复与审计。

## 2. 产品契约核心缺口的补齐

本轮新增 6 个产品契约实体，其中 1 个是多图层应急矢量组合契约，5 个是建筑、道路、水体面、水系线和兴趣点图层契约。契约通过 `applies_to_scenario`、`orchestrated_by`、`requires_task`、`requires_output_requirement`、`uses_qos_policy`、`uses_repair_strategy` 和 `composed_of` 与现有图谱连接。

| 契约实体 | 名称 | 说明 |
| --- | --- | --- |
| contract.product.building.v1 | Fused Building Footprint Product | Fused Building Footprint Product 是图层产品契约，产品类型为 building_multi_source_vector_fusion；覆盖 building，适用灾种 generic、flood、earthquake、typhoon，包含 7 个质量门和 6 类证据要求。 |
| contract.product.emergency_vector_bundle.v1 | Emergency Multi-Layer Vector Product Bundle | Emergency Multi-Layer Vector Product Bundle 是组合产品契约，产品类型为 emergency_multi_layer_vector_fusion_bundle；覆盖 building、road、water_polygon、waterways、poi，适用灾种 generic、flood、earthquake、typhoon，包含 5 个质量门和 7 类证据要求。 |
| contract.product.poi.v1 | Fused Point-of-Interest Product | Fused Point-of-Interest Product 是图层产品契约，产品类型为 poi_multi_source_vector_fusion；覆盖 poi，适用灾种 generic，包含 8 个质量门和 6 类证据要求。 |
| contract.product.road.v1 | Fused Road Network Product | Fused Road Network Product 是图层产品契约，产品类型为 road_multi_source_vector_fusion；覆盖 road，适用灾种 generic、flood、earthquake、typhoon，包含 8 个质量门和 6 类证据要求。 |
| contract.product.water_polygon.v1 | Fused Polygonal Surface-Water Product | Fused Polygonal Surface-Water Product 是图层产品契约，产品类型为 water_polygon_multi_source_vector_fusion；覆盖 water_polygon，适用灾种 generic、flood、typhoon，包含 8 个质量门和 6 类证据要求。 |
| contract.product.waterways.v1 | Fused Linear Hydrography Product | Fused Linear Hydrography Product 是图层产品契约，产品类型为 waterways_multi_source_vector_fusion；覆盖 waterways，适用灾种 generic、flood、typhoon，包含 9 个质量门和 6 类证据要求。 |

## 3. 工程接入状态

- **模型与种子**：新增 `ProductContractNode` 和 6 个静态契约，完整记录质量门、证据要求、满足状态及策略对象。
- **仓库层**：内存仓库和 Neo4j 仓库均支持按灾种读取产品契约。
- **图数据库启动**：Python bootstrap 与静态 Cypher 均创建契约节点及跨层关系。
- **清单层**：产品契约已进入 `kg/seed_manifest.generated.json`，可进行哈希校验和跨运行加载。
- **检索与规划**：检索上下文选择产品契约，`WorkflowPlan.product_contract` 保存规划所消费的契约。
- **图谱 API**：KG overview 返回产品契约节点及相关边，支持浏览和路径审计。
- **规范文档**：`docs/thesis/product_contract_spec.md` 已加入本体实体与关系映射。
- **汇报材料**：组会 PPT 已补充四层本体闭环、六节点本体全景和运行消费说明。

## 4. 当前图谱规模

| 本体类 | 中文名称 | 静态实体数 | 生命周期 |
| --- | --- | --- | --- |
| algorithm | 算法能力 | 33 | seed |
| data_need | 数据需求 | 12 | seed |
| data_source | 数据源 | 32 | seed |
| data_type | 数据类型 | 27 | seed |
| durable_learning_summary | 持久学习摘要 | 0 | runtime-derived |
| output_requirement | 输出要求 | 5 | seed |
| output_schema_policy | 输出模式策略 | 5 | seed |
| parameter_spec | 参数规范 | 72 | seed |
| product_contract | 产品契约 | 6 | seed |
| qos_policy | 服务质量策略 | 4 | seed |
| repair_strategy | 修复策略 | 2 | seed |
| scenario_profile | 场景处境 | 4 | seed |
| task | 任务 | 11 | seed |
| task_bundle | 任务编排包 | 4 | seed |
| workflow_pattern | 工作流模式 | 15 | seed |

## 5. 四层本体视图

### 灾害场景与资源处境

回答当前是什么灾种、处于什么响应阶段、需要激活哪些任务以及采用何种质量优先级。

包含本体：场景处境、任务编排包。

### 产品契约与产品组成

回答要交付什么产品、包含哪些图层、满足什么质量门、允许怎样降级以及如何声明缺口。

包含本体：产品契约、输出要求、输出模式策略、服务质量策略。

### 数据、算法与任务能力

回答需要什么数据、从哪里获得、采用什么算法和参数、以何种工作流完成任务。

包含本体：任务、数据需求、数据类型、数据源、算法能力、参数规范、工作流模式。

### 验收、修复与运行证据

回答如何验收输出、失败后怎样恢复、如何记录证据以及怎样用运行结果反哺规划。

包含本体：产品契约、输出要求、输出模式策略、服务质量策略、修复策略、持久学习摘要。

## 6. 五层 Agent 运行视图

| 运行层 | 名称 | 消费的本体 | 代码模块 |
| --- | --- | --- | --- |
| perception | Perception | 场景处境、产品契约、任务编排包 | schemas/agent.py::RunTrigger<br>services/scenario_trigger_service.py::normalize_trigger_event<br>services/unsupported_intent_guard.py::classify_unsupported_intent |
| reasoning_planning | Reasoning and Planning | 任务、工作流模式、算法能力、任务编排包 | agent/retriever.py::PlanningContextBuilder<br>agent/planner.py::WorkflowPlanner |
| validation_policy | Validation and Policy | 产品契约、数据需求、服务质量策略、输出要求、输出模式策略、参数规范 | agent/validator.py::WorkflowValidator<br>agent/policy.py::PolicyEngine |
| action_healing | Action and Healing | 修复策略、数据源、数据类型 | agent/executor.py::WorkflowExecutor<br>services/input_acquisition_service.py::InputAcquisitionService |
| audit_evolution | Audit and Evolution | 工作流模式、算法能力、数据源、持久学习摘要 | services/agent_run_service.py::AgentRunService<br>services/kg_path_trace_service.py::build_kg_path_trace |

## 7. 本体类完整说明

| 本体 ID | 名称 | 说明 | 主标识 | 实体数 |
| --- | --- | --- | --- | --- |
| algorithm | 算法能力 | 描述算法可接受的输入、产生的输出、解决的任务、工具实现、可靠性和替代算法。 | algo_id | 33 |
| data_need | 数据需求 | 明确任务所需或产生的数据类型、方向和必需性，将任务语义连接到数据类型。 | need_id | 12 |
| data_source | 数据源 | 表示可获取或上传的数据来源，记录支持的数据类型、灾种、作业类型、几何类型、新鲜度和质量。 | source_id | 32 |
| data_type | 数据类型 | 定义图谱中可被算法、数据源和工作流消费或产生的数据语义、主题和几何类型。 | type_id | 27 |
| durable_learning_summary | 持久学习摘要 | 由运行记录聚合得到的动态实体，表达条件化成功率、质量门通过率、时延、趋势和规划调整量。当前 seed 中无静态实例。 | entity_kind + entity_id + condition_key | 0 |
| output_requirement | 输出要求 | 规定任务必须交付的输出类型、字段层级和对应模式策略，为产品契约和工作流提供可验证的交付目标。 | requirement_id | 5 |
| output_schema_policy | 输出模式策略 | 规定输出字段保留、必需字段、可选字段、重命名提示和兼容性判断方式。 | policy_id | 5 |
| parameter_spec | 参数规范 | 规定算法参数的类型、默认值、范围、单位、可选值、可调性和默认值来源。 | spec_id | 72 |
| product_contract | 产品契约 | 把数据产品要求建模为一等图谱实体，统一表达图层要求、质量门、满足状态、证据要求、降级、缺口声明、交付和产品组成策略。 | contract_id | 6 |
| qos_policy | 服务质量策略 | 表达时延、成功率及质量维度权重，用于场景默认、产品契约和任务编排的质量权衡。 | policy_id | 4 |
| repair_strategy | 修复策略 | 描述执行失败后的替代数据源、替代算法或其他恢复路径，并绑定原因码和适用任务。 | strategy_id | 2 |
| scenario_profile | 场景处境 | 描述灾种、响应阶段和任务处境，给出激活任务、输出字段偏好与默认 QoS，是契约选择和规划检索的上层语境。 | profile_id | 4 |
| task | 任务 | 表示规划和执行要完成的业务任务，是场景、契约、数据需求、算法能力和工作流模式之间的枢纽。 | task_id | 11 |
| task_bundle | 任务编排包 | 将一组任务、输出要求、QoS、数据需求和修复策略组合成可检索、可规划的编排单元。 | bundle_id | 4 |
| workflow_pattern | 工作流模式 | 定义面向作业类型和灾种的多步骤算法执行模式，包含步骤依赖、数据源、参数和成功率。 | pattern_id | 15 |

每个本体的完整字段、字段类型、是否必需及字段说明见 `ontology_fields.csv` 和 JSON 的 `ontology.classes[].fields`。

## 8. 关系本体完整说明

| 关系 ID | 名称 | 源本体 | 目标本体 | 实例数 | 说明 |
| --- | --- | --- | --- | --- | --- |
| activates_task | 激活任务 | scenario_profile | task | 12 | 场景处境激活需要进入规划空间的任务。 |
| applies_to_output_type | 适用于输出类型 | output_schema_policy | data_type | 5 | 输出模式策略适用于指定的数据输出类型。 |
| applies_to_scenario | 适用于场景 | product_contract | scenario_profile | 19 | 产品契约适用于指定灾害场景处境。 |
| applies_to_task | 适用于任务 | repair_strategy | task | 8 | 修复策略适用于指定任务。 |
| can_transform_to | 可转换为 | data_type | data_type | 6 | 一种数据类型可通过已注册能力转换为另一种数据类型。 |
| composed_of | 由产品契约组成 | product_contract | product_contract | 5 | 组合产品契约由一个或多个图层产品契约组成。 |
| consumes_data_type | 消费数据类型 | algorithm | data_type | 45 | 算法消费指定输入数据类型。 |
| declares_data_need | 声明数据需求 | task_bundle | data_need | 11 | 任务编排包显式声明需要满足的数据需求。 |
| defaults_to_qos | 默认服务质量策略 | scenario_profile | qos_policy | 4 | 场景处境默认使用指定 QoS 策略。 |
| emits_output_type | 输出数据类型 | workflow_pattern | data_type | 23 | 工作流模式在一个或多个步骤中产生指定输出数据类型。 |
| enforces_schema_policy | 执行输出模式策略 | output_requirement | output_schema_policy | 5 | 输出要求通过指定模式策略约束字段结构。 |
| has_data_need | 具有数据需求 | task | data_need | 12 | 任务具有指定数据需求。 |
| has_parameter_spec | 具有参数规范 | algorithm | parameter_spec | 72 | 算法具有指定参数规范。 |
| orchestrated_by | 由任务包编排 | product_contract | task_bundle | 12 | 产品契约由指定任务编排包组织执行。 |
| produces_data_type | 产出数据类型 | algorithm | data_type | 33 | 算法能够产出指定数据类型。 |
| refers_to_data_type | 指向数据类型 | data_need | data_type | 12 | 数据需求引用指定数据类型。 |
| requests_task | 请求任务 | task_bundle | task | 11 | 任务编排包请求执行指定任务。 |
| requires_input_type | 需要输入类型 | workflow_pattern | data_type | 23 | 工作流模式的步骤需要指定输入数据类型。 |
| requires_output_requirement | 需要输出要求 | product_contract | output_requirement | 10 | 产品契约必须满足指定输出要求。 |
| requires_task | 需要任务 | product_contract | task | 10 | 产品契约要求执行指定任务。 |
| solves_task | 解决任务 | workflow_pattern | task | 15 | 工作流模式能够解决指定任务。 |
| supports_data_type | 支持数据类型 | data_source | data_type | 47 | 数据源能够提供指定数据类型。 |
| targets_output_requirement | 目标输出要求 | task_bundle、workflow_pattern | output_requirement | 17 | 工作流模式或任务编排包以指定输出要求为交付目标。 |
| uses_algorithm | 使用算法 | workflow_pattern | algorithm | 27 | 工作流模式在一个或多个步骤中使用指定算法。 |
| uses_data_source | 使用数据源 | workflow_pattern | data_source | 15 | 工作流模式在一个或多个步骤中使用指定数据源。 |
| uses_qos_policy | 使用服务质量策略 | product_contract、task_bundle | qos_policy | 20 | 产品契约或任务编排包使用指定 QoS 策略。 |
| uses_repair_strategy | 使用修复策略 | product_contract、task_bundle | repair_strategy | 18 | 产品契约或任务编排包允许使用指定修复策略。 |

## 9. 运行消费链路

```text
ScenarioProfile
  -> ProductContract
  -> TaskBundle / Task / OutputRequirement / QoSPolicy / RepairStrategy
  -> WorkflowPattern / Algorithm / ParameterSpec / DataSource / DataType
  -> WorkflowPlan.product_contract
  -> 执行、质量门、缺口声明、证据与持久学习摘要
```

这意味着 `ProductContract` 已不再只是运行后生成的 JSON，而是可以被检索、选择、遍历、绑定到计划并通过 Neo4j/API 审计的一等图谱实体。

## 10. 验证状态

- 产品契约、仓库、Neo4j、清单、规划上下文和 KG API 的定向测试共 90 项通过。
- Seed manifest 哈希一致性检查通过。
- 组会 PPT 的溢出、模板忠实度和 PPTX 空占位符检查通过。
- 本文档导出时再次检查实体唯一性、关系端点完整性、本体数量和关系说明覆盖率。

## 11. 尚未完成的研究问题

1. **复杂处境下的决策空间仍偏小**：候选排序仍可能使智能规划退化为选择最高分方案。
2. **模拟规划路径仍有接口问题**：需要保证模拟规划读取与真实检索上下文一致。
3. **增量价值尚未实验性证明**：需要完成固定规则、纯知识图谱、大模型、能力图谱和完整契约图谱五类基线。
4. **本体规范性仍可加强**：当前本体是工程可执行本体，后续可补充 SHACL/OWL 约束或专家验证。
5. **运行学习实体尚未静态化**：`durable_learning_summary` 由运行记录动态生成，当前 seed 无实例。

## 12. 文档包文件说明

- `FusionAgent_当前进展与知识图谱说明_20260727.md`：当前文件，说明进展、全景和后续问题。
- `FusionAgent_知识图谱实体说明_20260727.md`：按本体逐一列出全部实体及说明。
- `FusionAgent_知识图谱本体与实体_20260727.json`：完整机器可读本体层、实体层和架构层。
- `ontology_classes.csv`：本体类及说明。
- `ontology_fields.csv`：每个本体的字段定义。
- `ontology_relationships.csv`：关系本体及说明。
- `entity_nodes.csv`：全部实体、说明和完整属性 JSON。
- `entity_relationships.csv`：全部实体关系及逐条说明。
- `architecture_layers.csv`：四层业务视图和五层 Agent 视图。
- `校验摘要.txt`：本次导出的计数和完整性检查结果。

## 13. 依据文件

- `kg/models.py`
- `kg/seed.py`
- `kg/seed_manifest.generated.json`
- `services/kg_graph_service.py`
- `agent/retriever.py`
- `agent/planner.py`
- `schemas/agent.py`
- `docs/thesis/product_contract_spec.md`
