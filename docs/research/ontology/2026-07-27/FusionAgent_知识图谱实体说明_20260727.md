# FusionAgent 知识图谱实体说明

> 共 232 个静态实体。每个实体的完整结构化属性见同目录 JSON 或 `entity_nodes.csv` 的 `properties_json` 列。

## 产品契约（`product_contract`，6 个）

把数据产品要求建模为一等图谱实体，统一表达图层要求、质量门、满足状态、证据要求、降级、缺口声明、交付和产品组成策略。

| 实体 ID | 名称 | 说明 |
| --- | --- | --- |
| contract.product.building.v1 | Fused Building Footprint Product | Fused Building Footprint Product 是图层产品契约，产品类型为 building_multi_source_vector_fusion；覆盖 building，适用灾种 generic、flood、earthquake、typhoon，包含 7 个质量门和 6 类证据要求。 |
| contract.product.emergency_vector_bundle.v1 | Emergency Multi-Layer Vector Product Bundle | Emergency Multi-Layer Vector Product Bundle 是组合产品契约，产品类型为 emergency_multi_layer_vector_fusion_bundle；覆盖 building、road、water_polygon、waterways、poi，适用灾种 generic、flood、earthquake、typhoon，包含 5 个质量门和 7 类证据要求。 |
| contract.product.poi.v1 | Fused Point-of-Interest Product | Fused Point-of-Interest Product 是图层产品契约，产品类型为 poi_multi_source_vector_fusion；覆盖 poi，适用灾种 generic，包含 8 个质量门和 6 类证据要求。 |
| contract.product.road.v1 | Fused Road Network Product | Fused Road Network Product 是图层产品契约，产品类型为 road_multi_source_vector_fusion；覆盖 road，适用灾种 generic、flood、earthquake、typhoon，包含 8 个质量门和 6 类证据要求。 |
| contract.product.water_polygon.v1 | Fused Polygonal Surface-Water Product | Fused Polygonal Surface-Water Product 是图层产品契约，产品类型为 water_polygon_multi_source_vector_fusion；覆盖 water_polygon，适用灾种 generic、flood、typhoon，包含 8 个质量门和 6 类证据要求。 |
| contract.product.waterways.v1 | Fused Linear Hydrography Product | Fused Linear Hydrography Product 是图层产品契约，产品类型为 waterways_multi_source_vector_fusion；覆盖 waterways，适用灾种 generic、flood、typhoon，包含 9 个质量门和 6 类证据要求。 |

## 任务（`task`，11 个）

表示规划和执行要完成的业务任务，是场景、契约、数据需求、算法能力和工作流模式之间的枢纽。

| 实体 ID | 名称 | 说明 |
| --- | --- | --- |
| task.building.fusion | Building Fusion | Fuse multiple building vector sources into one output. |
| task.clip.raster.by_tile | Raster Clip By Tile | Reserved tiled raster clipping task for future building enrichment workflows. |
| task.enrich.building.height.reserved | Enrich Building Height | Reserved seam for future raster-backed building height enrichment. |
| task.merge.building.tiles.reserved | Merge Building Tiles | Reserved seam for future tile-level building artifact stitching. |
| task.partition.aoi | AOI Partition | Reserved AOI partition task for future tiled execution workflows. |
| task.poi.fusion | POI Fusion | Fuse multiple point-of-interest sources into one output. |
| task.road.fusion | Road Fusion | Fuse multiple road vector sources into one output. |
| task.trajectory_to_road | Trajectory To Road Candidate | Reserved seam for future trajectory-to-road candidate pretransform before road fusion. |
| task.vector.download | Vector Data Download | Acquire vector data required by downstream fusion or enrichment tasks. |
| task.water.fusion | Water Fusion | Fuse multiple water polygon sources into one output. |
| task.waterways.fusion | Waterways Fusion | Fuse multiple waterways line sources into one output. |

## 任务编排包（`task_bundle`，4 个）

将一组任务、输出要求、QoS、数据需求和修复策略组合成可检索、可规划的编排单元。

| 实体 ID | 名称 | 说明 |
| --- | --- | --- |
| task_bundle.direct_request | Direct Task Request Bundle | Direct Task Request Bundle 编排 task.building.fusion、task.road.fusion、task.water.fusion、task.waterways.fusion、task.poi.fusion；目标输出要求为 由请求决定，声明 5 项数据需求。 |
| task_bundle.earthquake.building_road | Earthquake Building And Road Bundle | Earthquake Building And Road Bundle 编排 task.building.fusion、task.road.fusion；目标输出要求为 or.building.fused.v1，声明 2 项数据需求。 |
| task_bundle.flood.building_road | Flood Building And Road Bundle | Flood Building And Road Bundle 编排 task.building.fusion、task.road.fusion；目标输出要求为 or.building.fused.v1，声明 2 项数据需求。 |
| task_bundle.typhoon.building_road | Typhoon Building And Road Bundle | Typhoon Building And Road Bundle 编排 task.building.fusion、task.road.fusion；目标输出要求为 or.building.fused.v1，声明 2 项数据需求。 |

## 修复策略（`repair_strategy`，2 个）

描述执行失败后的替代数据源、替代算法或其他恢复路径，并绑定原因码和适用任务。

| 实体 ID | 名称 | 说明 |
| --- | --- | --- |
| repair.alternative_algorithm.v1 | Alternative Algorithm Fallback | Alternative Algorithm Fallback，针对原因码 primary_execution_failed、alternative_algorithm_succeeded；适用任务 task.building.fusion、task.road.fusion、task.waterways.fusion。 |
| repair.source_fallback.v1 | Alternative Source Fallback | Alternative Source Fallback，针对原因码 source_fallback_selected、fallback_when_no_safe_reuse_candidate；适用任务 task.building.fusion、task.road.fusion、task.water.fusion、task.waterways.fusion、task.poi.fusion。 |

## 参数规范（`parameter_spec`，72 个）

规定算法参数的类型、默认值、范围、单位、可选值、可调性和默认值来源。

| 实体 ID | 名称 | 说明 |
| --- | --- | --- |
| ps.algo.enrich.building.height_from_raster.v1.height_output_field | Height Output Field | FusionCode parameter `height_output_field` for algo.enrich.building.height_from_raster.v1. 默认值为 'H_Raster'，类型为 string。 |
| ps.algo.enrich.building.height_from_raster.v1.n_jobs | N Jobs | FusionCode parameter `n_jobs` for algo.enrich.building.height_from_raster.v1. 默认值为 -1，类型为 int。 |
| ps.algo.enrich.building.height_from_raster.v1.positive_only | Positive Only | FusionCode parameter `positive_only` for algo.enrich.building.height_from_raster.v1. 默认值为 True，类型为 bool。 |
| ps.algo.fusion.building.safe.match_similarity_threshold | Match Similarity Threshold | Conservative match threshold for safe mode. 默认值为 0.4，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.fusion.building.safe.one_to_one_min_area_similarity | One-to-One Min Area Similarity | Conservative area similarity threshold for safe mode. 默认值为 0.45，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.fusion.building.safe.one_to_one_min_overlap_similarity | One-to-One Min Overlap Similarity | Conservative one-to-one overlap threshold for safe mode. 默认值为 0.4，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.fusion.building.safe.one_to_one_min_shape_similarity | One-to-One Min Shape Similarity | Conservative shape similarity threshold for safe mode. 默认值为 0.45，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.fusion.building.v1.match_similarity_threshold | Match Similarity Threshold | Pairs with similarity > this value are treated as matched (legacy label=1). 默认值为 0.3，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.fusion.building.v1.one_to_one_min_area_similarity | One-to-One Min Area Similarity | For 1:1 matches, sim_area must be >= this value to fuse as one-to-one. 默认值为 0.3，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.fusion.building.v1.one_to_one_min_overlap_similarity | One-to-One Min Overlap Similarity | For 1:1 matches, sim_overlap must be >= this value to fuse as one-to-one. 默认值为 0.3，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.fusion.building.v1.one_to_one_min_shape_similarity | One-to-One Min Shape Similarity | For 1:1 matches, sim_shape must be >= this value to fuse as one-to-one. 默认值为 0.3，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.fusion.poi.geohash_neighbor_match.v1.name_similarity_threshold | Name Similarity Threshold | FusionCode parameter `name_similarity_threshold` for algo.fusion.poi.geohash_neighbor_match.v1. 默认值为 0.75，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.fusion.poi.geohash_neighbor_match.v1.neighbor_rings | Neighbor Rings | FusionCode parameter `neighbor_rings` for algo.fusion.poi.geohash_neighbor_match.v1. 默认值为 1，类型为 int；最小值 0.0。 |
| ps.algo.fusion.road.conflation.v7.angle_threshold | Angle Threshold | FusionCode parameter `angle_threshold` for algo.fusion.road.conflation.v7. 默认值为 135，类型为 int；最小值 0.0，最大值 180.0。 |
| ps.algo.fusion.road.conflation.v7.cleanup_mode | Cleanup Mode | FusionCode parameter `cleanup_mode` for algo.fusion.road.conflation.v7. 默认值为 'quality'，类型为 string。 |
| ps.algo.fusion.road.conflation.v7.crossing_coverage_threshold | Crossing Coverage Threshold | FusionCode parameter `crossing_coverage_threshold` for algo.fusion.road.conflation.v7. 默认值为 0.82，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.fusion.road.conflation.v7.duplicate_buffer_dist | Duplicate Buffer Dist | FusionCode parameter `duplicate_buffer_dist` for algo.fusion.road.conflation.v7. 默认值为 10.0，类型为 float；最小值 0.0。 |
| ps.algo.fusion.road.conflation.v7.duplicate_coverage_threshold | Duplicate Coverage Threshold | FusionCode parameter `duplicate_coverage_threshold` for algo.fusion.road.conflation.v7. 默认值为 0.92，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.fusion.road.conflation.v7.loose_angle_threshold | Loose Angle Threshold | FusionCode parameter `loose_angle_threshold` for algo.fusion.road.conflation.v7. 默认值为 45.0，类型为 float；最小值 0.0，最大值 180.0。 |
| ps.algo.fusion.road.conflation.v7.match_buffer_dist | Match Buffer Dist | FusionCode parameter `match_buffer_dist` for algo.fusion.road.conflation.v7. 默认值为 20.0，类型为 float；最小值 0.0。 |
| ps.algo.fusion.road.conflation.v7.max_hausdorff | Max Hausdorff | FusionCode parameter `max_hausdorff` for algo.fusion.road.conflation.v7. 默认值为 15.0，类型为 float；最小值 0.0。 |
| ps.algo.fusion.road.conflation.v7.max_segment_length | Max Segment Length | FusionCode parameter `max_segment_length` for algo.fusion.road.conflation.v7. 默认值为 800.0，类型为 float；最小值 0.0。 |
| ps.algo.fusion.road.conflation.v7.min_len_similarity | Min Len Similarity | FusionCode parameter `min_len_similarity` for algo.fusion.road.conflation.v7. 默认值为 0.05，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.fusion.road.conflation.v7.min_residual_length | Min Residual Length | FusionCode parameter `min_residual_length` for algo.fusion.road.conflation.v7. 默认值为 10.0，类型为 float；最小值 0.0。 |
| ps.algo.fusion.road.conflation.v7.min_supplement_coverage_for_matched | Min Supplement Coverage For Matched | FusionCode parameter `min_supplement_coverage_for_matched` for algo.fusion.road.conflation.v7. 默认值为 0.8，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.fusion.road.conflation.v7.near_base_return_coverage_threshold | Near Base Return Coverage Threshold | FusionCode parameter `near_base_return_coverage_threshold` for algo.fusion.road.conflation.v7. 默认值为 0.85，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.fusion.road.conflation.v7.output_crs | Output Crs | FusionCode parameter `output_crs` for algo.fusion.road.conflation.v7. 默认值为 None，类型为 string。 |
| ps.algo.fusion.road.conflation.v7.preserve_matched_supplement_residuals | Preserve Matched Supplement Residuals | FusionCode parameter `preserve_matched_supplement_residuals` for algo.fusion.road.conflation.v7. 默认值为 True，类型为 bool。 |
| ps.algo.fusion.road.conflation.v7.profile | Profile | FusionCode parameter `profile` for algo.fusion.road.conflation.v7. 默认值为 'balanced'，类型为 string。 |
| ps.algo.fusion.road.conflation.v7.target_crs | Target Crs | FusionCode parameter `target_crs` for algo.fusion.road.conflation.v7. 默认值为 'EPSG:32643'，类型为 string。 |
| ps.algo.fusion.road.safe.angle_threshold_deg | Split Angle Threshold | Conservative split angle threshold for safe mode. 默认值为 120，类型为 int；最小值 0.0，最大值 180.0。 |
| ps.algo.fusion.road.safe.dedupe_buffer_m | Dedupe Buffer Distance | Conservative dedupe buffer for safe mode. 默认值为 12.0，类型为 float；最小值 0.0，最大值 100.0。 |
| ps.algo.fusion.road.safe.match_buffer_m | Match Buffer Distance | Conservative match buffer for safe mode. 默认值为 15.0，类型为 float；最小值 0.0，最大值 100.0。 |
| ps.algo.fusion.road.safe.max_hausdorff_m | Max Hausdorff Distance | Conservative Hausdorff threshold for safe mode. 默认值为 10.0，类型为 float；最小值 0.0，最大值 100.0。 |
| ps.algo.fusion.road.safe.snap_tolerance_m | Snap Tolerance | Conservative endpoint snap tolerance for safe mode. 默认值为 0.75，类型为 float；最小值 0.0，最大值 10.0。 |
| ps.algo.fusion.road.v1.angle_threshold_deg | Split Angle Threshold | Split lines at sharp turns: angles below this threshold trigger a split. 默认值为 135，类型为 int；最小值 0.0，最大值 180.0。 |
| ps.algo.fusion.road.v1.dedupe_buffer_m | Dedupe Buffer Distance | Buffer distance used during post-fusion deduplication. 默认值为 15.0，类型为 float；最小值 0.0，最大值 100.0。 |
| ps.algo.fusion.road.v1.match_buffer_m | Match Buffer Distance | Buffer radius for candidate matching between OSM and reference lines. 默认值为 20.0，类型为 float；最小值 0.0，最大值 100.0。 |
| ps.algo.fusion.road.v1.max_hausdorff_m | Max Hausdorff Distance | Maximum Hausdorff distance allowed to consider two lines as a match. 默认值为 15.0，类型为 float；最小值 0.0，最大值 100.0。 |
| ps.algo.fusion.road.v1.snap_tolerance_m | Snap Tolerance | Endpoint snap tolerance used when normalizing line endpoints. 默认值为 1.0，类型为 float；最小值 0.0，最大值 10.0。 |
| ps.algo.fusion.water_polygon.priority_merge.v2.overlap_threshold | Overlap Threshold | FusionCode parameter `overlap_threshold` for algo.fusion.water_polygon.priority_merge.v2. 默认值为 0.1，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.fusion.waterways.conflation.v7.angle_threshold | Angle Threshold | FusionCode parameter `angle_threshold` for algo.fusion.waterways.conflation.v7. 默认值为 135，类型为 int；最小值 0.0，最大值 180.0。 |
| ps.algo.fusion.waterways.conflation.v7.cleanup_mode | Cleanup Mode | FusionCode parameter `cleanup_mode` for algo.fusion.waterways.conflation.v7. 默认值为 'fast'，类型为 string。 |
| ps.algo.fusion.waterways.conflation.v7.crossing_corridor_dist | Crossing Corridor Dist | FusionCode parameter `crossing_corridor_dist` for algo.fusion.waterways.conflation.v7. 默认值为 15.0，类型为 float；最小值 0.0。 |
| ps.algo.fusion.waterways.conflation.v7.duplicate_buffer_dist | Duplicate Buffer Dist | FusionCode parameter `duplicate_buffer_dist` for algo.fusion.waterways.conflation.v7. 默认值为 12.0，类型为 float；最小值 0.0。 |
| ps.algo.fusion.waterways.conflation.v7.loose_angle_threshold | Loose Angle Threshold | FusionCode parameter `loose_angle_threshold` for algo.fusion.waterways.conflation.v7. 默认值为 50.0，类型为 float；最小值 0.0，最大值 180.0。 |
| ps.algo.fusion.waterways.conflation.v7.match_buffer_dist | Match Buffer Dist | FusionCode parameter `match_buffer_dist` for algo.fusion.waterways.conflation.v7. 默认值为 25.0，类型为 float；最小值 0.0。 |
| ps.algo.fusion.waterways.conflation.v7.max_hausdorff | Max Hausdorff | FusionCode parameter `max_hausdorff` for algo.fusion.waterways.conflation.v7. 默认值为 20.0，类型为 float；最小值 0.0。 |
| ps.algo.fusion.waterways.conflation.v7.max_segment_length | Max Segment Length | FusionCode parameter `max_segment_length` for algo.fusion.waterways.conflation.v7. 默认值为 1000.0，类型为 float；最小值 0.0。 |
| ps.algo.fusion.waterways.conflation.v7.min_len_similarity | Min Len Similarity | FusionCode parameter `min_len_similarity` for algo.fusion.waterways.conflation.v7. 默认值为 0.03，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.fusion.waterways.conflation.v7.min_residual_length | Min Residual Length | FusionCode parameter `min_residual_length` for algo.fusion.waterways.conflation.v7. 默认值为 20.0，类型为 float；最小值 0.0。 |
| ps.algo.fusion.waterways.conflation.v7.min_supplement_coverage_for_matched | Min Supplement Coverage For Matched | FusionCode parameter `min_supplement_coverage_for_matched` for algo.fusion.waterways.conflation.v7. 默认值为 0.8，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.fusion.waterways.conflation.v7.near_base_return_corridor_dist | Near Base Return Corridor Dist | FusionCode parameter `near_base_return_corridor_dist` for algo.fusion.waterways.conflation.v7. 默认值为 15.0，类型为 float；最小值 0.0。 |
| ps.algo.fusion.waterways.conflation.v7.output_crs | Output Crs | FusionCode parameter `output_crs` for algo.fusion.waterways.conflation.v7. 默认值为 None，类型为 string。 |
| ps.algo.fusion.waterways.conflation.v7.target_crs | Target Crs | FusionCode parameter `target_crs` for algo.fusion.waterways.conflation.v7. 默认值为 'EPSG:32643'，类型为 string。 |
| ps.algo.match.building.v8_component_solver.v1.source_priority_order | Source Priority Order | FusionCode parameter `source_priority_order` for algo.match.building.v8_component_solver.v1. 默认值为 ['MS', 'GG', 'OSM']，类型为 list。 |
| ps.algo.match.building.v8_component_solver.v1.thresh_1_to_1 | Thresh 1 To 1 | FusionCode parameter `thresh_1_to_1` for algo.match.building.v8_component_solver.v1. 默认值为 0.4，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.match.building.v8_component_solver.v1.thresh_1_to_N | Thresh 1 To N | FusionCode parameter `thresh_1_to_N` for algo.match.building.v8_component_solver.v1. 默认值为 0.44，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.match.building.v8_component_solver.v1.thresh_M_to_N | Thresh M To N | FusionCode parameter `thresh_M_to_N` for algo.match.building.v8_component_solver.v1. 默认值为 0.47，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.match.building.v8_component_solver.v1.weak_min_cover | Weak Min Cover | FusionCode parameter `weak_min_cover` for algo.match.building.v8_component_solver.v1. 默认值为 0.05，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.match.building.v8_component_solver.v1.weak_min_iou | Weak Min Iou | FusionCode parameter `weak_min_iou` for algo.match.building.v8_component_solver.v1. 默认值为 0.05，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.optimize.building.conflict_graph.v1.global_max_shift | Global Max Shift | FusionCode parameter `global_max_shift` for algo.optimize.building.conflict_graph.v1. 默认值为 4.0，类型为 float；最小值 0.0。 |
| ps.algo.optimize.building.conflict_graph.v1.max_outer_iterations | Max Outer Iterations | FusionCode parameter `max_outer_iterations` for algo.optimize.building.conflict_graph.v1. 默认值为 3，类型为 int；最小值 1.0。 |
| ps.algo.optimize.building.conflict_graph.v1.overlap_delete_threshold | Overlap Delete Threshold | FusionCode parameter `overlap_delete_threshold` for algo.optimize.building.conflict_graph.v1. 默认值为 0.75，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.optimize.building.conflict_graph.v1.road_buffer_width | Road Buffer Width | FusionCode parameter `road_buffer_width` for algo.optimize.building.conflict_graph.v1. 默认值为 0.1，类型为 float；最小值 0.0。 |
| ps.algo.optimize.building.conflict_graph.v1.w_road_expulsion | W Road Expulsion | FusionCode parameter `w_road_expulsion` for algo.optimize.building.conflict_graph.v1. 默认值为 4267.96，类型为 float；最小值 0.0。 |
| ps.algo.refine.building.post_conflict_shrink.v1.post_shrink_scale_cap_pct | Post Shrink Scale Cap Pct | FusionCode parameter `post_shrink_scale_cap_pct` for algo.refine.building.post_conflict_shrink.v1. 默认值为 0.05，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.refine.building.post_conflict_shrink.v1.post_shrink_threshold_m2 | Post Shrink Threshold M2 | FusionCode parameter `post_shrink_threshold_m2` for algo.refine.building.post_conflict_shrink.v1. 默认值为 5.0，类型为 float；最小值 0.0。 |
| ps.algo.validate.building.presence_raster.v1.confirmed_score_threshold | Confirmed Score Threshold | FusionCode parameter `confirmed_score_threshold` for algo.validate.building.presence_raster.v1. 默认值为 0.55，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.validate.building.presence_raster.v1.prob_threshold | Prob Threshold | FusionCode parameter `prob_threshold` for algo.validate.building.presence_raster.v1. 默认值为 0.2，类型为 float；最小值 0.0，最大值 1.0。 |
| ps.algo.validate.building.presence_raster.v1.search_dist_m | Search Dist M | FusionCode parameter `search_dist_m` for algo.validate.building.presence_raster.v1. 默认值为 4.0，类型为 float；最小值 0.0。 |
| ps.algo.validate.building.presence_raster.v1.uncertain_score_threshold | Uncertain Score Threshold | FusionCode parameter `uncertain_score_threshold` for algo.validate.building.presence_raster.v1. 默认值为 0.3，类型为 float；最小值 0.0，最大值 1.0。 |

## 场景处境（`scenario_profile`，4 个）

描述灾种、响应阶段和任务处境，给出激活任务、输出字段偏好与默认 QoS，是契约选择和规划检索的上层语境。

| 实体 ID | 名称 | 说明 |
| --- | --- | --- |
| scenario.default.task | Default Direct Task Profile | Default Direct Task Profile，适用灾种为 generic；激活任务 task.building.fusion、task.road.fusion、task.water.fusion、task.waterways.fusion、task.poi.fusion、task.vector.download；默认 QoS 为 qos.task.default.v1。 |
| scenario.earthquake.default | Earthquake Default Scenario | Earthquake Default Scenario，适用灾种为 earthquake；激活任务 task.building.fusion、task.road.fusion；默认 QoS 为 qos.scenario.earthquake.v1。 |
| scenario.flood.default | Flood Default Scenario | Flood Default Scenario，适用灾种为 flood；激活任务 task.building.fusion、task.road.fusion；默认 QoS 为 qos.scenario.flood.v1。 |
| scenario.typhoon.default | Typhoon Default Scenario | Typhoon Default Scenario，适用灾种为 typhoon；激活任务 task.building.fusion、task.road.fusion；默认 QoS 为 qos.scenario.typhoon.v1。 |

## 工作流模式（`workflow_pattern`，15 个）

定义面向作业类型和灾种的多步骤算法执行模式，包含步骤依赖、数据源、参数和成功率。

| 实体 ID | 名称 | 说明 |
| --- | --- | --- |
| wp.building.drs4br.decomposed.v1 | FusionCode DRS4BR Decomposed Building Fusion | FusionCode DRS4BR Decomposed Building Fusion 面向 building 作业和 flood、earthquake、typhoon、generic；包含 13 个步骤：source_normalize、obm_attributes、presence_raster、v8_candidate_graph、v8_component_solver、cascade_geometry_priority、residual_priority、road_topology、conflict_graph、post_conflict_shrink、road_tail、height_from_raster、quality_metrics；基线成功率为 0.84。 |
| wp.earthquake.building.default | Earthquake Building Fusion | Earthquake Building Fusion 面向 building 作业和 earthquake；包含 1 个步骤：building_fusion_earthquake；基线成功率为 0.91。 |
| wp.earthquake.building.safe | Earthquake Building Fusion Safe Route | Earthquake Building Fusion Safe Route 面向 building 作业和 earthquake；包含 1 个步骤：building_fusion_safe；基线成功率为 0.85。 |
| wp.flood.building.default | Flood Building Fusion | Flood Building Fusion 面向 building 作业和 flood、typhoon、generic；包含 1 个步骤：building_fusion；基线成功率为 0.88。 |
| wp.flood.building.safe | Flood Building Fusion Safe Route | Flood Building Fusion Safe Route 面向 building 作业和 flood、generic；包含 1 个步骤：building_fusion_safe；基线成功率为 0.82。 |
| wp.flood.road.default | Flood Road Conflation V7 | Flood Road Conflation V7 面向 road 作业和 flood、earthquake、generic；包含 1 个步骤：road_conflation_v7；基线成功率为 0.86。 |
| wp.flood.water.default | Flood Water Polygon Fusion | Flood Water Polygon Fusion 面向 water 作业和 flood、generic；包含 1 个步骤：water_polygon_priority_merge；基线成功率为 0.84。 |
| wp.flood.water_polygon.default | Flood Water Polygon Priority Merge | Flood Water Polygon Priority Merge 面向 water 作业和 flood、generic；包含 1 个步骤：water_polygon_priority_merge；基线成功率为 0.79。 |
| wp.flood.waterways.default | Flood Waterways Conflation V7 | Flood Waterways Conflation V7 面向 water 作业和 flood、generic；包含 1 个步骤：waterways_conflation_v7；基线成功率为 0.8。 |
| wp.generic.poi.default | Generic POI Fusion | Generic POI Fusion 面向 poi 作业和 generic；包含 1 个步骤：poi_fusion；基线成功率为 0.8。 |
| wp.poi.fusioncode.geohash_priority.v1 | FusionCode POI Geohash Priority Fusion | FusionCode POI Geohash Priority Fusion 面向 poi 作业和 generic；包含 1 个步骤：poi_geohash_neighbor_match；基线成功率为 0.8。 |
| wp.road.fusioncode.conflation.v7 | FusionCode V7 Road Conflation | FusionCode V7 Road Conflation 面向 road 作业和 flood、earthquake、typhoon、generic；包含 1 个步骤：road_conflation_v7；基线成功率为 0.86。 |
| wp.typhoon.road.default | Typhoon Road Conflation V7 | Typhoon Road Conflation V7 面向 road 作业和 typhoon；包含 1 个步骤：road_conflation_v7_typhoon；基线成功率为 0.9。 |
| wp.water_polygon.fusioncode.priority_merge.v2 | FusionCode Water Polygon Priority Merge | FusionCode Water Polygon Priority Merge 面向 water 作业和 flood、generic；包含 1 个步骤：water_polygon_priority_merge；基线成功率为 0.83。 |
| wp.waterways.fusioncode.conflation.v7 | FusionCode V7 Waterways Conflation | FusionCode V7 Waterways Conflation 面向 water 作业和 flood、generic；包含 1 个步骤：waterways_conflation_v7；基线成功率为 0.82。 |

## 数据源（`data_source`，32 个）

表示可获取或上传的数据来源，记录支持的数据类型、灾种、作业类型、几何类型、新鲜度和质量。

| 实体 ID | 名称 | 说明 |
| --- | --- | --- |
| catalog.earthquake.building | Earthquake Building Bundle (OSM + Microsoft) | Earthquake Building Bundle (OSM + Microsoft) 是 catalog 类型数据源，支持 dt.building.bundle；适用灾种 earthquake、generic，质量评分为 0.88，新鲜度类别为 event_snapshot。 |
| catalog.earthquake.road | Earthquake Road Bundle (OSM + Microsoft) | Earthquake Road Bundle (OSM + Microsoft) 是 catalog 类型数据源，支持 dt.road.bundle；适用灾种 earthquake、generic，质量评分为 0.85，新鲜度类别为 event_snapshot。 |
| catalog.flood.building | Flood Building Bundle (OSM + Microsoft) | Flood Building Bundle (OSM + Microsoft) 是 catalog 类型数据源，支持 dt.building.bundle；适用灾种 flood、generic，质量评分为 0.86，新鲜度类别为 event_snapshot。 |
| catalog.flood.road | Flood Road Bundle (OSM + Microsoft) | Flood Road Bundle (OSM + Microsoft) 是 catalog 类型数据源，支持 dt.road.bundle；适用灾种 flood、generic，质量评分为 0.86，新鲜度类别为 event_snapshot。 |
| catalog.flood.water | Flood Water Bundle (OSM + HydroLAKES) | Flood Water Bundle (OSM + HydroLAKES) 是 catalog 类型数据源，支持 dt.water.bundle；适用灾种 flood、generic，质量评分为 0.84，新鲜度类别为 event_snapshot。 |
| catalog.flood.water_polygon | Flood Water Polygon Bundle (OSM + HydroLAKES) | Flood Water Polygon Bundle (OSM + HydroLAKES) 是 catalog 类型数据源，支持 dt.water.bundle；适用灾种 flood、generic，质量评分为 0.84，新鲜度类别为 event_snapshot。 |
| catalog.flood.waterways | Flood Waterways Bundle (OSM + Pakistan Local Waterways) | Flood Waterways Bundle (OSM + Pakistan Local Waterways) 是 catalog 类型数据源，支持 dt.waterways.bundle；适用灾种 flood、generic，质量评分为 0.8，新鲜度类别为 event_snapshot。 |
| catalog.generic.poi | Generic POI Bundle (OSM + GNS) | Generic POI Bundle (OSM + GNS) 是 catalog 类型数据源，支持 dt.poi.bundle；适用灾种 generic，质量评分为 0.82，新鲜度类别为 sample_snapshot。 |
| catalog.typhoon.road | Typhoon Road Bundle (OSM + Microsoft) | Typhoon Road Bundle (OSM + Microsoft) 是 catalog 类型数据源，支持 dt.road.bundle；适用灾种 typhoon、generic，质量评分为 0.88，新鲜度类别为 event_snapshot。 |
| raw.gns.poi | GNS Place Names | GNS Place Names 是 open_data 类型数据源，支持 dt.raw.vector；适用灾种 generic、flood、earthquake、typhoon，质量评分为 0.81，新鲜度类别为 sample_snapshot。 |
| raw.google.building | Google Open Buildings | Google Open Buildings 是 open_data 类型数据源，支持 dt.raw.vector；适用灾种 generic、flood、earthquake、typhoon，质量评分为 0.87，新鲜度类别为 sample_snapshot。 |
| raw.google.building_height.raster | Google Building Height Raster | Google Building Height Raster 是 open_data 类型数据源，支持 dt.raster.building_height；适用灾种 generic、flood、earthquake、typhoon，质量评分为 0.76，新鲜度类别为 sample_snapshot。 |
| raw.google.building_presence.raster | Google Building Presence Raster | Google Building Presence Raster 是 open_data 类型数据源，支持 dt.raster.building_presence；适用灾种 generic、flood、earthquake、typhoon，质量评分为 0.78，新鲜度类别为 sample_snapshot。 |
| raw.google.open_buildings.vector | Google Open Buildings Vector | Google Open Buildings Vector 是 open_data 类型数据源，支持 dt.raw.vector；适用灾种 generic、flood、earthquake、typhoon，质量评分为 0.87，新鲜度类别为 sample_snapshot。 |
| raw.google.poi | Google Places POI | Google Places POI 是 authorized_data 类型数据源，支持 dt.raw.vector；适用灾种 generic、flood、earthquake、typhoon，质量评分为 0.84，新鲜度类别为 runtime_query。 |
| raw.hydrolakes.water | HydroLAKES | HydroLAKES 是 open_data 类型数据源，支持 dt.raw.vector；适用灾种 generic、flood、earthquake、typhoon，质量评分为 0.82，新鲜度类别为 sample_snapshot。 |
| raw.hydrorivers.water | HydroRIVERS | HydroRIVERS 是 open_data 类型数据源，支持 dt.raw.vector；适用灾种 generic、flood、earthquake、typhoon，质量评分为 0.83，新鲜度类别为 sample_snapshot。 |
| raw.local.microsoft.building | Local Microsoft Building Footprints | Local Microsoft Building Footprints 是 open_data 类型数据源，支持 dt.raw.vector；适用灾种 generic、flood、earthquake、typhoon，质量评分为 0.89，新鲜度类别为 sample_snapshot。 |
| raw.local.pakistan.waterways | Pakistan Local Waterways | Pakistan Local Waterways 是 open_data 类型数据源，支持 dt.raw.vector；适用灾种 generic、flood、earthquake、typhoon，质量评分为 0.77，新鲜度类别为 sample_snapshot。 |
| raw.local.water | Local Open Water Sample | Local Open Water Sample 是 open_data 类型数据源，支持 dt.raw.vector；适用灾种 generic、flood、earthquake、typhoon，质量评分为 0.79，新鲜度类别为 sample_snapshot。 |
| raw.microsoft.building | Microsoft Building Footprints | Microsoft Building Footprints 是 open_data 类型数据源，支持 dt.raw.vector；适用灾种 generic、flood、earthquake、typhoon，质量评分为 0.88，新鲜度类别为 sample_snapshot。 |
| raw.microsoft.road | Microsoft Road Network | Microsoft Road Network 是 provider_data 类型数据源，支持 dt.raw.vector；适用灾种 generic、flood、earthquake、typhoon，质量评分为 0.8，新鲜度类别为 sample_snapshot。 |
| raw.openbuildingmap.building | OpenBuildingMap Building Footprints | OpenBuildingMap Building Footprints 是 open_data 类型数据源，支持 dt.raw.vector；适用灾种 generic、flood、earthquake、typhoon，质量评分为 0.9，新鲜度类别为 sample_snapshot。 |
| raw.osm.building | OSM Building Footprints | OSM Building Footprints 是 open_data 类型数据源，支持 dt.raw.vector；适用灾种 generic、flood、earthquake、typhoon，质量评分为 0.84，新鲜度类别为 sample_snapshot。 |
| raw.osm.poi | OSM Points Of Interest | OSM Points Of Interest 是 open_data 类型数据源，支持 dt.raw.vector；适用灾种 generic、flood、earthquake、typhoon，质量评分为 0.78，新鲜度类别为 sample_snapshot。 |
| raw.osm.road | OSM Road Network | OSM Road Network 是 open_data 类型数据源，支持 dt.raw.vector；适用灾种 generic、flood、earthquake、typhoon，质量评分为 0.82，新鲜度类别为 sample_snapshot。 |
| raw.osm.water | OSM Water Features | OSM Water Features 是 open_data 类型数据源，支持 dt.raw.vector；适用灾种 generic、flood、earthquake、typhoon，质量评分为 0.8，新鲜度类别为 sample_snapshot。 |
| raw.osm.waterways | OSM Waterways | OSM Waterways 是 open_data 类型数据源，支持 dt.raw.vector；适用灾种 generic、flood、earthquake、typhoon，质量评分为 0.8，新鲜度类别为 sample_snapshot。 |
| raw.overture.road | Overture Transportation Extract | Overture Transportation Extract 是 open_data 类型数据源，支持 dt.raw.vector；适用灾种 generic、flood、earthquake、typhoon，质量评分为 0.86，新鲜度类别为 sample_snapshot。 |
| raw.overture.transportation | Overture Transportation Segments | Overture Transportation Segments 是 open_data 类型数据源，支持 dt.raw.vector；适用灾种 generic、flood、earthquake、typhoon，质量评分为 0.81，新鲜度类别为 sample_snapshot。 |
| raw.rh.poi | RH Points Of Interest | RH Points Of Interest 是 open_data 类型数据源，支持 dt.raw.vector；适用灾种 generic、flood、earthquake、typhoon，质量评分为 0.76，新鲜度类别为 sample_snapshot。 |
| upload.bundle | Uploaded Bundle | Uploaded Bundle 是 local_upload 类型数据源，支持 dt.building.bundle、dt.building.source_set、dt.building.normalized_set、dt.building.presence_validated_set、dt.building.fused_raw、dt.building.conflict_optimized、dt.raster.building_presence、dt.raster.building_height、dt.road.network、dt.road.bundle、dt.waterways.bundle、dt.trajectory.raw、dt.road.candidate、dt.water.bundle、dt.poi.bundle、dt.raw.vector；适用灾种 generic、flood、earthquake、typhoon，质量评分为 1.0，新鲜度类别为 request_bound。 |

## 数据类型（`data_type`，27 个）

定义图谱中可被算法、数据源和工作流消费或产生的数据语义、主题和几何类型。

| 实体 ID | 名称 | 说明 |
| --- | --- | --- |
| dt.building.bundle | dt.building.bundle | Prepared building fusion input bundle. |
| dt.building.conflict_optimized | dt.building.conflict_optimized | Fused buildings after spatial conflict graph optimization. |
| dt.building.fused | dt.building.fused | Fused building output. |
| dt.building.fused_raw | dt.building.fused_raw | Raw cascaded building fusion rows before conflict optimization. |
| dt.building.height_enriched | dt.building.height_enriched | Fused buildings enriched with height raster values. |
| dt.building.match_candidate_graph | dt.building.match_candidate_graph | FusionCode V8 candidate edge graph for a pair of building sources. |
| dt.building.match_components | dt.building.match_components | Accepted V8 building match components and relationship groups. |
| dt.building.normalized_set | dt.building.normalized_set | Normalized named building sources after CRS, geometry and source-label preparation. |
| dt.building.presence_validated_set | dt.building.presence_validated_set | Building sources enriched with presence-raster support and existence status. |
| dt.building.quality_report | dt.building.quality_report | Quality and conflict metrics for the building fusion run. |
| dt.building.road_topology_adjusted | dt.building.road_topology_adjusted | Fused buildings after road-aware topology adjustment. |
| dt.building.source_set | dt.building.source_set | Reserved multi-source building input set for future fusion algorithms. |
| dt.partition.tile_manifest | dt.partition.tile_manifest | Reserved deterministic AOI tile partition manifest. |
| dt.poi.bundle | dt.poi.bundle | Prepared point-of-interest fusion input bundle. |
| dt.poi.fused | dt.poi.fused | Fused point-of-interest output. |
| dt.raster.building_height | dt.raster.building_height | Building height raster input. |
| dt.raster.building_presence | dt.raster.building_presence | Reserved building-presence raster input. |
| dt.raw.vector | dt.raw.vector | Uploaded raw vector bundle. |
| dt.road.bundle | dt.road.bundle | Prepared road fusion input bundle. |
| dt.road.candidate | dt.road.candidate | Reserved intermediate road candidates derived from trajectory pretransform. |
| dt.road.fused | dt.road.fused | Fused road output. |
| dt.road.network | dt.road.network | Road network used as contextual constraint for building fusion. |
| dt.trajectory.raw | dt.trajectory.raw | Reserved pretransform trajectory observations for future road candidate generation. |
| dt.water.bundle | dt.water.bundle | Prepared water polygon fusion input bundle. |
| dt.water.fused | dt.water.fused | Fused water polygon output. |
| dt.waterways.bundle | dt.waterways.bundle | Prepared waterways line fusion input bundle. |
| dt.waterways.fused | dt.waterways.fused | Fused waterways line output. |

## 数据需求（`data_need`，12 个）

明确任务所需或产生的数据类型、方向和必需性，将任务语义连接到数据类型。

| 实体 ID | 名称 | 说明 |
| --- | --- | --- |
| dn.task.building.fusion.input | dn.task.building.fusion.input | Building fusion consumes prepared building bundles in the shared runtime path. |
| dn.task.building.fusion.output | dn.task.building.fusion.output | Building fusion produces fused building output. |
| dn.task.poi.fusion.input | dn.task.poi.fusion.input | POI fusion consumes prepared POI bundles. |
| dn.task.poi.fusion.output | dn.task.poi.fusion.output | POI fusion produces fused POI output. |
| dn.task.road.fusion.input | dn.task.road.fusion.input | Road fusion consumes prepared road bundles. |
| dn.task.road.fusion.output | dn.task.road.fusion.output | Road fusion produces fused road output. |
| dn.task.trajectory_to_road.input | dn.task.trajectory_to_road.input | Reserved trajectory seam consumes raw trajectories. |
| dn.task.trajectory_to_road.output | dn.task.trajectory_to_road.output | Reserved trajectory seam produces road candidates. |
| dn.task.water.fusion.input | dn.task.water.fusion.input | Water fusion consumes prepared water bundles. |
| dn.task.water.fusion.output | dn.task.water.fusion.output | Water fusion produces fused water polygons. |
| dn.task.waterways.fusion.input | dn.task.waterways.fusion.input | Waterways fusion consumes prepared waterways bundles. |
| dn.task.waterways.fusion.output | dn.task.waterways.fusion.output | Waterways fusion produces fused waterways output. |

## 服务质量策略（`qos_policy`，4 个）

表达时延、成功率及质量维度权重，用于场景默认、产品契约和任务编排的质量权衡。

| 实体 ID | 名称 | 说明 |
| --- | --- | --- |
| qos.scenario.earthquake.v1 | Earthquake Default QoS | Earthquake Default QoS，最大时延为 900 秒，最小成功率为 0.78；质量权重为 {"accuracy": 0.4, "freshness": 0.15, "speed": 0.15, "stability": 0.3}。 |
| qos.scenario.flood.v1 | Flood Default QoS | Flood Default QoS，最大时延为 900 秒，最小成功率为 0.75；质量权重为 {"accuracy": 0.35, "freshness": 0.25, "speed": 0.15, "stability": 0.25}。 |
| qos.scenario.typhoon.v1 | Typhoon Default QoS | Typhoon Default QoS，最大时延为 900 秒，最小成功率为 0.74；质量权重为 {"accuracy": 0.3, "freshness": 0.3, "speed": 0.15, "stability": 0.25}。 |
| qos.task.default.v1 | Direct Task Default QoS | Direct Task Default QoS，最大时延为 900 秒，最小成功率为 0.72；质量权重为 {"accuracy": 0.35, "freshness": 0.2, "speed": 0.2, "stability": 0.25}。 |

## 算法能力（`algorithm`，33 个）

描述算法可接受的输入、产生的输出、解决的任务、工具实现、可靠性和替代算法。

| 实体 ID | 名称 | 说明 |
| --- | --- | --- |
| algo.assess.building.quality_metrics.v1 | FusionCode Building Quality Metrics | FusionCode Building Quality Metrics 用于 assessment，将 dt.building.height_enriched、dt.building.conflict_optimized 转换为 dt.building.quality_report；工具引用为 fusion_algorithms:_handle_building_quality_metrics，基线成功率为 0.82。 |
| algo.clip.raster.tile.v1 | Raster Tile Clip Reserved | Raster Tile Clip Reserved 用于 raster_clip，将 dt.raster.building_presence 转换为 dt.raster.building_presence；工具引用为 reserved:raster_tile_clip，基线成功率为 0.0。 |
| algo.detect.spatial_conflicts.v1 | FusionCode Spatial Conflict Detection | FusionCode Spatial Conflict Detection 用于 assessment，将 dt.building.fused、dt.water.fused、dt.road.fused 转换为 dt.building.quality_report；工具引用为 fusion_algorithms:_handle_spatial_conflicts，基线成功率为 0.82。 |
| algo.enrich.building.height_from_raster.reserved | Building Height Enrichment From Raster Reserved | Building Height Enrichment From Raster Reserved 用于 enrichment，将 dt.raster.building_presence 转换为 dt.building.fused；工具引用为 reserved:building_height_from_raster，基线成功率为 0.0。 |
| algo.enrich.building.height_from_raster.v1 | FusionCode Building Height From Raster | FusionCode Building Height From Raster 用于 enrichment，将 dt.building.conflict_optimized、dt.raster.building_height 转换为 dt.building.height_enriched；工具引用为 fusion_algorithms:_handle_building_height_from_raster，基线成功率为 0.82。 |
| algo.enrich.building.obm_attributes.v1 | FusionCode OBM Attribute Enrichment | FusionCode OBM Attribute Enrichment 用于 enrichment，将 dt.building.normalized_set 转换为 dt.building.normalized_set；工具引用为 fusion_algorithms:_handle_building_obm_attributes，基线成功率为 0.82。 |
| algo.fusion.building.cascade_geometry_priority.v1 | FusionCode Cascaded Geometry Priority Building Fusion | FusionCode Cascaded Geometry Priority Building Fusion 用于 building_fusion，将 dt.building.match_components、dt.building.normalized_set 转换为 dt.building.fused_raw；工具引用为 fusion_algorithms:_handle_building_cascade_fusion，基线成功率为 0.82。 |
| algo.fusion.building.multi_source.decomposed.v1 | FusionCode Decomposed Multi-Source Building Fusion | FusionCode Decomposed Multi-Source Building Fusion 用于 building_fusion，将 dt.building.source_set、dt.building.bundle 转换为 dt.building.fused；工具引用为 fusion_algorithms:_handle_building_multi_source_decomposed，基线成功率为 0.82。 |
| algo.fusion.building.multi_source.reserved | Multi-Source Building Fusion Reserved | Multi-Source Building Fusion Reserved 用于 building_fusion，将 dt.building.source_set 转换为 dt.building.fused；工具引用为 reserved:multi_source_building_fusion，基线成功率为 0.0。 |
| algo.fusion.building.safe | Building Fusion Safe Fallback | Building Fusion Safe Fallback 用于 building_fusion，将 dt.building.bundle 转换为 dt.building.fused；工具引用为 adapters.building_adapter:run_building_fusion，基线成功率为 0.75。 |
| algo.fusion.building.v1 | Building Fusion Legacy | Building Fusion Legacy 用于 building_fusion，将 dt.building.bundle 转换为 dt.building.fused；工具引用为 adapters.building_adapter:run_building_fusion，基线成功率为 0.92。 |
| algo.fusion.poi.geohash_neighbor_match.v1 | FusionCode POI Geohash Neighbor Match | FusionCode POI Geohash Neighbor Match 用于 poi_fusion，将 dt.poi.bundle 转换为 dt.poi.fused；工具引用为 fusion_algorithms:_handle_poi_geohash_neighbor_match，基线成功率为 0.82。 |
| algo.fusion.poi.v1 | POI Fusion | POI Fusion 用于 poi_fusion，将 dt.poi.bundle 转换为 dt.poi.fused；工具引用为 adapters.poi_adapter:run_poi_fusion，基线成功率为 0.8。 |
| algo.fusion.road.conflation.v7 | FusionCode V7 Road Conflation | FusionCode V7 Road Conflation 用于 road_fusion，将 dt.road.bundle 转换为 dt.road.fused；工具引用为 fusion_algorithms:_handle_road_conflation_v7，基线成功率为 0.82。 |
| algo.fusion.road.safe | Road Fusion Safe Fallback (Deprecated) | Road Fusion Safe Fallback (Deprecated) 用于 road_fusion，将 dt.road.bundle 转换为 dt.road.fused；工具引用为 adapters.road_adapter:run_road_fusion，基线成功率为 0.72。 |
| algo.fusion.road.v1 | Road Fusion Legacy (Deprecated) | Road Fusion Legacy (Deprecated) 用于 road_fusion，将 dt.road.bundle 转换为 dt.road.fused；工具引用为 adapters.road_adapter:run_road_fusion，基线成功率为 0.9。 |
| algo.fusion.water.v1 | Water Polygon Fusion (Deprecated) | Water Polygon Fusion (Deprecated) 用于 water_fusion，将 dt.water.bundle 转换为 dt.water.fused；工具引用为 adapters.water_adapter:run_water_fusion，基线成功率为 0.84。 |
| algo.fusion.water_polygon.priority_merge.v2 | FusionCode Water Polygon Priority Merge | FusionCode Water Polygon Priority Merge 用于 water_fusion，将 dt.water.bundle 转换为 dt.water.fused；工具引用为 fusion_algorithms:_handle_water_polygon_priority_merge，基线成功率为 0.82。 |
| algo.fusion.waterways.conflation.v7 | FusionCode V7 Waterways Conflation | FusionCode V7 Waterways Conflation 用于 water_fusion，将 dt.waterways.bundle 转换为 dt.waterways.fused；工具引用为 fusion_algorithms:_handle_waterways_conflation_v7，基线成功率为 0.82。 |
| algo.match.building.v8_candidate_graph.v1 | FusionCode V8 Building Candidate Graph | FusionCode V8 Building Candidate Graph 用于 building_matching，将 dt.building.presence_validated_set、dt.building.normalized_set 转换为 dt.building.match_candidate_graph；工具引用为 fusion_algorithms:_handle_building_v8_candidate_graph，基线成功率为 0.82。 |
| algo.match.building.v8_component_solver.v1 | FusionCode V8 Building Component Solver | FusionCode V8 Building Component Solver 用于 building_matching，将 dt.building.match_candidate_graph 转换为 dt.building.match_components；工具引用为 fusion_algorithms:_handle_building_v8_component_solver，基线成功率为 0.82。 |
| algo.merge.building.tiles.reserved | Building Tile Merge Reserved | Building Tile Merge Reserved 用于 runtime_merge，将 dt.partition.tile_manifest 转换为 dt.building.fused；工具引用为 reserved:building_tile_merge，基线成功率为 0.0。 |
| algo.optimize.building.conflict_graph.v1 | FusionCode Building Conflict Graph Optimization | FusionCode Building Conflict Graph Optimization 用于 building_optimization，将 dt.building.road_topology_adjusted、dt.building.fused_raw 转换为 dt.building.conflict_optimized；工具引用为 fusion_algorithms:_handle_building_conflict_graph，基线成功率为 0.82。 |
| algo.optimize.road.topology_for_buildings.v1 | FusionCode Road Topology For Buildings | FusionCode Road Topology For Buildings 用于 building_optimization，将 dt.building.fused_raw、dt.road.network 转换为 dt.building.road_topology_adjusted；工具引用为 fusion_algorithms:_handle_building_road_topology，基线成功率为 0.82。 |
| algo.partition.aoi.grid.v1 | AOI Grid Partition Reserved | AOI Grid Partition Reserved 用于 runtime_partition，将 dt.raw.vector 转换为 dt.partition.tile_manifest；工具引用为 reserved:aoi_grid_partition，基线成功率为 0.0。 |
| algo.preprocess.building.source_normalize.v1 | FusionCode Building Source Normalize | FusionCode Building Source Normalize 用于 building_fusion，将 dt.building.source_set、dt.building.bundle 转换为 dt.building.normalized_set；工具引用为 fusion_algorithms:_handle_building_source_normalize，基线成功率为 0.82。 |
| algo.refine.building.post_conflict_shrink.v1 | FusionCode Building Post Conflict Shrink | FusionCode Building Post Conflict Shrink 用于 building_optimization，将 dt.building.conflict_optimized 转换为 dt.building.conflict_optimized；工具引用为 fusion_algorithms:_handle_building_post_conflict_shrink，基线成功率为 0.82。 |
| algo.refine.building.road_tail.v1 | FusionCode Road Tail Building Refinement | FusionCode Road Tail Building Refinement 用于 building_optimization，将 dt.building.conflict_optimized、dt.road.network 转换为 dt.building.conflict_optimized；工具引用为 fusion_algorithms:_handle_building_road_tail，基线成功率为 0.82。 |
| algo.resolve.building.residual_priority.v1 | FusionCode Residual Priority Conflict Resolution | FusionCode Residual Priority Conflict Resolution 用于 building_fusion，将 dt.building.fused_raw 转换为 dt.building.fused_raw；工具引用为 fusion_algorithms:_handle_building_residual_priority，基线成功率为 0.82。 |
| algo.transform.raw_to_building_bundle | Raw Vector to Building Bundle | Raw Vector to Building Bundle 用于 transform，将 dt.raw.vector 转换为 dt.building.bundle；工具引用为 builtin:transform，基线成功率为 0.98。 |
| algo.transform.raw_to_road_bundle | Raw Vector to Road Bundle | Raw Vector to Road Bundle 用于 transform，将 dt.raw.vector 转换为 dt.road.bundle；工具引用为 builtin:transform，基线成功率为 0.98。 |
| algo.transform.trajectory_to_road_candidate | Trajectory To Road Candidate Reserved Seam | Trajectory To Road Candidate Reserved Seam 用于 transform，将 dt.trajectory.raw 转换为 dt.road.candidate；工具引用为 builtin:trajectory_pretransform_reserved，基线成功率为 0.0。 |
| algo.validate.building.presence_raster.v1 | FusionCode Building Presence Raster Validation | FusionCode Building Presence Raster Validation 用于 validation，将 dt.building.normalized_set、dt.raster.building_presence 转换为 dt.building.presence_validated_set；工具引用为 fusion_algorithms:_handle_building_presence_raster，基线成功率为 0.82。 |

## 输出模式策略（`output_schema_policy`，5 个）

规定输出字段保留、必需字段、可选字段、重命名提示和兼容性判断方式。

| 实体 ID | 名称 | 说明 |
| --- | --- | --- |
| osp.building.fused.v1 | osp.building.fused.v1 | 约束 building 作业的 dt.building.fused 输出；保留模式为 preserve_listed，必须字段 geometry，兼容性依据为 field_names。 |
| osp.poi.fused.v1 | osp.poi.fused.v1 | 约束 poi 作业的 dt.poi.fused 输出；保留模式为 preserve_listed，必须字段 geometry，兼容性依据为 field_names。 |
| osp.road.fused.v1 | osp.road.fused.v1 | 约束 road 作业的 dt.road.fused 输出；保留模式为 preserve_listed，必须字段 geometry，兼容性依据为 field_names。 |
| osp.water.fused.v1 | osp.water.fused.v1 | 约束 water 作业的 dt.water.fused 输出；保留模式为 preserve_listed，必须字段 geometry，兼容性依据为 field_names。 |
| osp.waterways.fused.v1 | osp.waterways.fused.v1 | 约束 water 作业的 dt.waterways.fused 输出；保留模式为 preserve_listed，必须字段 geometry、fusion_source、match_role、waterway_class、source_layer，兼容性依据为 field_names。 |

## 输出要求（`output_requirement`，5 个）

规定任务必须交付的输出类型、字段层级和对应模式策略，为产品契约和工作流提供可验证的交付目标。

| 实体 ID | 名称 | 说明 |
| --- | --- | --- |
| or.building.fused.v1 | or.building.fused.v1 | 面向 building 作业的 dt.building.fused 输出要求；必须字段为 geometry，由 osp.building.fused.v1 约束模式。 |
| or.poi.fused.v1 | or.poi.fused.v1 | 面向 poi 作业的 dt.poi.fused 输出要求；必须字段为 geometry，由 osp.poi.fused.v1 约束模式。 |
| or.road.fused.v1 | or.road.fused.v1 | 面向 road 作业的 dt.road.fused 输出要求；必须字段为 geometry，由 osp.road.fused.v1 约束模式。 |
| or.water.fused.v1 | or.water.fused.v1 | 面向 water 作业的 dt.water.fused 输出要求；必须字段为 geometry，由 osp.water.fused.v1 约束模式。 |
| or.waterways.fused.v1 | or.waterways.fused.v1 | 面向 water 作业的 dt.waterways.fused 输出要求；必须字段为 geometry、fusion_source、match_role、waterway_class、source_layer，由 osp.waterways.fused.v1 约束模式。 |

## 运行期派生实体

`durable_learning_summary` 当前没有 seed 实体。它在系统运行后根据执行记录动态聚合，字段定义已收录在本体 JSON 和 `ontology_fields.csv` 中。
