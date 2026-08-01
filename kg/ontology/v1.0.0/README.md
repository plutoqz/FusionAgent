# FusionAgent 契约化灾害知识图谱 v1.0.0

> 状态：P0-K1–K5 已验收的冻结机器基线  
> 发布标识：`fusionagent-kg-v1.0.0`  
> 冻结验收日期：2026-07-29

## 1. 权威边界

本目录是 KG v1.0.0 的唯一机器可读权威来源：

- `schema.json`：七层类、关系、属性、稳定 ID 规则、约束与 competency questions。
- `entities.json`：静态实体、工作流步骤、算法能力、数据源与类型转换边。
- `policies.json`：任务编译、检索评分、输出契约、质量门、源选择、故障与恢复策略。
- `release.json`：发布身份、受保护文件哈希、语义哈希和固定经验快照哈希。
- `verification_report.json`：独立验证器对本发布的派生校验结果。

`kg.seed` 只提供从 `entities.json` 重建的兼容常量，不再是知识真源。运行时事实、执行证据和经验反馈不写回本目录，只能引用本发布的 `release_id` 与 `semantic_hash`。

人类可读说明：

- [本体层说明](../../../docs/research/ontology/ontology-layer.md)
- [实体层说明](../../../docs/research/ontology/entity-layer.md)
- [知识片段迁移台账](../../../docs/research/ontology/knowledge-fragment-ledger.md)

## 2. 七层图景

| 层 | 名称 | 主要对象 |
| --- | --- | --- |
| L1 | 灾害情景层 | 灾害词汇、场景 profile、响应阶段、地点和组织 |
| L2 | 数据产品契约层 | 产品契约、必需图层、字段/几何/质量/证据要求、允许降级 |
| L3 | 数据需求与数据源语义层 | 数据需求、数据类型、数据源、源角色、fallback 与覆盖证据 |
| L4 | 数据-算法-任务能力层 | 任务、任务包、算法、参数、工作流、转换和修复策略 |
| L5 | 受约束规划层 | 规划上下文、采集策略、渐进交付、决策政策和理由 |
| L6 | 执行质量校验层 | 运行步骤、输出 schema、质量门、故障、重试、恢复和运行闸门 |
| L7 | 证据与经验层 | KG 发布、证据、gap、manifest、supersession 与经验记录 |

模式层当前登记 71 个类、42 类关系、19 项核心属性、8 项完整性约束和 8 个 competency questions。`implemented` 表示已有静态知识或运行消费者，`runtime-derived` 表示实例只能由运行产生，`reserved` 表示仅保留模式位置而不宣称当前能力。71 是模式类数量，不等于 71 类静态实例已经全部材料化。

## 3. 静态知识清单

| 分区 | 数量 | 分区 | 数量 |
| --- | ---: | --- | ---: |
| 数据类型 | 27 | 任务 | 11 |
| 场景 profile | 4 | 产品契约 | 6 |
| 任务包 | 7 | 输出要求 | 5 |
| QoS 政策 | 4 | 数据需求 | 12 |
| 修复策略 | 6 | 算法 | 33 |
| 参数规范 | 72 | 工作流模式 | 15 |
| 数据源 | 34 | 输出 schema 政策 | 5 |

上述实体分区共含 241 个具有稳定标识的静态知识对象，另含 1 条类型转换边。运行实例、质量结果、证据项、gap 和 supersession 等属于运行派生对象，不写入静态实体计数。

五类运行任务固定为建筑物、道路、水体面、水系线和 POI。洪水、地震、台风和通用应急词汇均映射到显式 task bundle；未知灾种不进入默认 bundle。hurricane、wildfire 和 conflict 不属于 v1 的可执行灾种，除非后续版本新增 profile、产品契约和数据源闭包。

## 4. 已冻结决议

1. `catalog.flood.waterways` 使用 OSM waterways 作为 base、HydroRIVERS 作为可移植 reference；Pakistan local waterways 仅是 AOI 特定补充。
2. Overture POI 和水体仅登记为 `reservation_only`，不得被当前规划选择。
3. 高度信号引用已有 `raw.google.building_height.raster`，不保留无实体支撑的别名。
4. executor 只能执行当前 plan 与产品契约共同授权、且列入 `recovery.default.v1` 的策略；源切换必须重新材料化，不能只改 source ID。
5. 基础排序使用固定经验快照；动态反馈不能改变本发布语义哈希。

## 5. 验证

当前冻结身份为：

```text
release_id:    fusionagent-kg-v1.0.0
semantic_hash: sha256:50067b9368914c47580707650789c04c78b2e856ccb3ef4d120a31f36c0ad71e
```

```powershell
.\.venv\Scripts\python.exe scripts\build_kg_release.py
.\.venv\Scripts\python.exe scripts\verify_kg_release.py `
  --release-dir kg/ontology/v1.0.0 `
  --report-path tmp/k3-final-verification-report.json
```

第二条命令不导入 `kg.seed`。2026-07-29 的 K5 最终验证为 11/11 checks passed。任一受保护文件发生字节变化、引用不闭合、DAG/算法 I/O 不一致、CQ 缺失或发布状态不是 `frozen` 时均返回非零。最终测试已分别对 `schema.json`、`entities.json`、`policies.json` 做单字节篡改并确认失败；K4 同时完成 KG-only 行为扰动、fail-closed、源重新材料化和真实 Neo4j 5.26 parity。
