# R1 真实闭环数据与入口核对

> 状态：`bounded_observation`
> 日期：2026-09-07
> 目的：为真实灾害应急矢量融合最小比较确认可复用数据、实际运行入口和已知前置问题
> 非主张：本文件不证明任何方法优越，也不代表新实验已经运行

## 1. 数据来源

本次核对使用项目已登记的 Caracas manifest：

`D:\code\FusionAgent\docs\thesis\manifests\2026-07-20-c02-c04-c06-real-data.json`

文件存在且可由 GeoPandas 读取的主要输入如下：

| 输入 | 要素数 | CRS | 几何类型 | 备注 |
| --- | ---: | --- | --- | --- |
| OSM roads | 16,279 | WGS84 经纬度 | LineString/MultiLineString | 可用于道路双源融合 |
| Microsoft roads | 11,809 | EPSG:4326 | MultiLineString | 有独立道路参考源 |
| OSM water polygons | 38 | WGS84 经纬度 | Polygon/MultiPolygon | 水面候选源 |
| OSM waterways | 156 | WGS84 经纬度 | LineString/MultiLineString | 水系候选源 |
| HydroRIVERS | 22 | EPSG:4326 | MultiLineString | 已裁剪 Caracas 参考源 |
| HydroLAKES 原始文件 | 1,427,688 | EPSG:4326 | Polygon | 当前是全球原始文件，需裁剪 |
| OSM buildings | 13,858 | WGS84 经纬度 | Polygon/MultiPolygon | 建筑候选源 |
| Microsoft buildings | 124,108 | EPSG:4326 | Polygon | 建筑参考源 |
| Caracas AOI | 1 | EPSG:4326 | Polygon | bounds 与 manifest 一致 |

主要路径由 manifest 的 `original_path` 字段给出。运行时使用前必须再次检查 manifest 中的版本、观测时间、sidecar 和 SHA-256，不得仅以文件存在作为输入有效。

## 2. 已确认的实际调用链

当前 `main` 工作树的运行服务入口为：

1. `services.agent_run_service.AgentRunService.execute_run`
2. `run_planning_stage`
   - AOI 解析：`aoi_resolution_service.resolve`
   - 目标 CRS 解析：`resolve_target_crs`
   - KG/规划器：`WorkflowPlanner.create_plan`
   - grounding gate 和计划持久化
3. `run_validation_stage`
4. 原始矢量材料化：`services.raw_vector_source_service.RawVectorSourceService`
5. `run_execution_stage`
   - 建立 `ExecutionContext`
   - 调用 `WorkflowExecutor.execute_plan`
   - 写入执行步骤事件
6. 输出 schema 与质量校验
   - `evaluate_vector_artifact`
   - `run_writeback_stage`
7. 运行状态、artifact、报告和 repair records 写回

现有服务还包含多源建筑和分块水体执行入口，但需要在正式比较前确认它们是否由同一计划路径触发，以及是否能记录每个来源的下载开始/结束、失败时刻和重规划版本。

## 3. 当前阻塞与处理要求

1. HydroLAKES 原始全球文件不能直接作为 Caracas 运行输入；应使用 AOI 裁剪后的派生输入，并记录裁剪命令、bounds、要素数和哈希。
2. 当前历史 C02/C04/C06 运行是真实数据与真实融合算法，但使用 mock LLM、memory KG、缓存源和 eager 执行；只能作为执行链回放或数据基线。
3. 新比较必须禁用跨方法 artifact reuse，或为每个方法使用隔离的运行目录和输入快照。
4. 四种网络/时限条件必须在下载层真实产生观测：正常、截止时间紧、限速/断连、截止时间紧且网络波动；不能只把失败状态写入规划输入。
5. 需要确认 C06 的质量失败是可稳定重现的自然失败还是应使用受控故障注入；如果使用注入，必须把“质量失败”和“外部来源失败”分开记录。

## 4. R1 结论

Caracas 具备作为第一轮真实闭环比较起点的输入条件，尤其适合 C02 类多图层任务、C04 类渐进交付和 C06 类道路双源质量/恢复任务。R1 尚未完成下载扰动、五组方法接入或真实新运行；下一步进入 R2，共同执行器和受控资源轨迹准备。

## 5. 后续核对修正（2026-09-07）

- 已有机器记录位于 `D:\code\FusionAgent\runs\research\r2-caracas-input-audit-20260907\input_audit.json`。HydroLAKES 已生成 bbox clip，但 bbox 候选 1 个、严格行政 AOI 相交 0 个；上文“具备起点条件”不代表水面双源在严格 AOI 内闭合。
- `AgentRunService.execute_run` 的实际顺序是规划、验证、材料化、执行循环、writeback。writeback 内质量拒绝及 artifact repair 失败不进入执行循环的 `replan_from_error`。此前“质量失败可再进入上层 replan”的推断撤回。
- 来源材料化同样在执行重规划循环外。已有 source fallback 和 scenario retry 不能自动视为五个方法各自根据下载反馈重规划；必须分清公共恢复与方法特有决策。
- `RuntimeDependencies` 提供串行 eager 的 planner 注入点；异步 worker 不传递该进程内对象。首轮适配器以 eager 模式运行并记录身份。
- R1 输入/入口核对完成；R2 正在补 trace 和规划/反馈接入。没有新增 live LLM、下载或融合结果，也未证明方法优势。
