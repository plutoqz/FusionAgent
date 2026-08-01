# Freeze C P4 外部有效性与论文材料协议

## 1. 目的

P4 用于检验 Freeze C 中观察到的契约治理行为是否能在结构不同的 AOI 上重复，并把结果转成可审计的论文材料。本轮保持 KG、运行时和案例逻辑固定，只改变 AOI 与相应的外部数据快照。

## 2. AOI 设计

| AOI | 结构差异 | 数据条件 | 案例覆盖 |
| --- | --- | --- | --- |
| Caracas 首都区 | 山地首都城区，Freeze C 原始案例 | OSM、HydroSheds 和独立 Microsoft 参考源 | C02/C04/C06 |
| Abidjan 都市走廊 | 高密度沿海都市，水系与建筑密度较高 | Geofabrik OSM 与 HydroSheds 缓存快照 | C02/C04；C06 因无独立道路参考源不运行 |
| 越南北部沿海走廊 | 较大沿海走廊，水系密度和覆盖尺度不同 | Geofabrik OSM 与 HydroSheds 缓存快照 | C02/C04；C06 因无独立道路参考源不运行 |

Burundi 缓存目录未纳入正式 AOI：检查发现其几何为空，且 Hydro 数据范围与越南快照错配。

## 3. 运行协议

所有正式变体使用同一 commit：`db256d591cc000b9bb1dc1880601da070fe9f74d`。固定条件为 memory KG、mock LLM、eager Celery、单 child worker、local-only、禁用 artifact reuse 和 `GEOFUSION_PLAN_GROUNDING_MODE=report`。每个 AOI 运行 `full_method` 与 `fixed_priority` 各一次，单独保存原始目录和 evidence manifest。本轮不运行全量测试。

固定优先级不是“预期仍通过原始优先级断言”的成功组，而是用静态执行顺序替代上下文优先级的行为对照。因此，固定优先级 C02 预期会把顺序改为 `road -> water_polygon -> waterways`，并在原始“水体优先”断言上失败；最终交付、gap 和证据完整性仍单独计量。

## 4. 案例与指标

- C02：比较水体面、水系线和道路的任务顺序、建筑延期、质量失败和 provisional/degraded 证据。
- C04：比较 OSM provisional 交付、HydroLAKES 激活、最终交付和 supersession。
- C06：在有独立第二道路源的 Caracas 比较全量道路质量门失败和 OSM-only 降级恢复。
- 计划有效率：初始计划验证通过。
- 首次质量门通过率：初始阶段质量门通过；不把质量门禁用解释为通过。
- 最终交付成功率：最终阶段存在案例允许的交付 artifact。
- 恢复成功率：有恢复机会且产生新 child run 和最终 artifact。
- 恢复代价：恢复机会案例新增的 child retry 数。
- 关键图层按时交付率：初始阶段首个任务满足案例关键图层要求并已交付。
- gap 声明正确率：观测 gap 覆盖 manifest 声明。
- 证据完整率：案例结果、child 计划/验证/审计和主要证据文件齐全。

## 5. 外部参考抽样

对每个 AOI 使用 OSM 水体面/水系线与 HydroLAKES/HydroRIVERS 参考。按确定性源顺序最多抽取 30 个参考要素：水面使用代表点，水系使用线中点；在投影坐标系中与 OSM 几何距离不超过 100 m 记为匹配。水面同时报告参考面与 OSM 面的覆盖重叠代理。

该过程是外部源一致性审计，不等同于人工真值精度、召回率、拓扑正确性或完整位置误差评价。

## 6. 结果口径

完整方法和固定优先级各有 7 个可比较案例。完整方法关键图层按时交付率为 `6/7`，固定优先级为 `3/7`，探索性 Cohen h 为 `0.93895`。两种变体的计划有效率、最终交付成功率、gap 声明正确率和证据完整率在本轮均为 `1.0`；这只描述冻结运行切片，不构成显著性结论。

## 7. 证据路径

- 统一材料目录：`docs/current/evidence/p4-external-validity/`
- AOI 与输入声明：`2026-08-01-freeze-c-p4-aoi-input-inventory.json`
- 机器汇总：`2026-08-01-freeze-c-p4-external-validity.json`
- 参考抽样：`2026-08-01-freeze-c-p4-reference-sample-audit.json`
- 原始证据：`D:\code\freeze-c-evidence\p4-external-validity-20260801-v2`
