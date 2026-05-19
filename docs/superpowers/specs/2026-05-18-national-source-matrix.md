# 2026-05-18 国家级多源矩阵定版

本文件是 `Track B / B1` 的 live 入口。后续 `B2-B5` 只能在这里已经锁定的
`source_id`、接入方式、裁剪策略、字段映射轮廓和 claim boundary 之上继续实现；
不要再把这些关键约束只留在主计划段落里口头描述。

## B1 锁定规则

- `source_id` 一旦写入本文件，就视为 Track B 当前批次的稳定命名。
- `official_remote_supported` 表示目标是官方或公开远程可物化链路，不等于当前仓库已经实现。
- `manual_preload_required` 表示当前只能靠 repo `Data/` 目录下的本地预载数据进入链路。
- `delivery_stage=current_runtime` 的 source 可以继续支撑现有受限 runtime claim。
- `delivery_stage=next_implementation` 的 source 只代表 B2 的硬目标，不得提前写成 README 或 operations 的既成能力。
- `delivery_stage=deferred` 的 source 只保留命名和映射方向，本轮不抢跑实现。

## B1 冻结结论

- Building 的第一批国家级自动链路固定为 `raw.osm.building + raw.microsoft.building`。
- Road 的第二来源硬目标固定为 `raw.overture.transportation`。
- Water 的第二来源硬目标固定为 `raw.hydrorivers.water + raw.hydrolakes.water`，`raw.overture.water` 降为 deferred 备选。
- POI 当前国家级组合固定为 `raw.osm.poi + raw.gns.poi`，`raw.rh.poi` 继续作为本地参考源，`raw.overture.places` 保留为 deferred 第三源。
- Building 的 `Google / OpenBuildingMap / Google Open Buildings Vector / local Microsoft clip` 都保留为 `manual_preload_required` 参考源，不在 B1 里提升为自动下载承诺。

## 主题矩阵

| Theme | Source ID | Role | Delivery Stage | Source Mode | Format | Clip Strategy | Repo Path | Claim Boundary |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| building | `raw.osm.building` | OSM primary | `current_runtime` | `official_remote_supported` | shapefile bundle | `country_bundle_then_clip` | `Data/buildings/OSM/` | `runtime_supported_now` |
| building | `raw.microsoft.building` | national reference | `current_runtime` | `official_remote_supported` | shapefile bundle | `country_tiles_then_clip` | `Data/buildings/Microsoft/` | `runtime_supported_now` |
| building | `raw.google.building` | local validation reference | `optional_reference` | `manual_preload_required` | shapefile bundle | `local_clip_then_reuse` | `Data/buildings/Google/` | `local_reference_only` |
| building | `raw.openbuildingmap.building` | local validation reference | `optional_reference` | `manual_preload_required` | shapefile bundle | `local_clip_then_reuse` | `Data/buildings/OpenBuildingMap/` | `local_reference_only` |
| building | `raw.google.open_buildings.vector` | local validation reference | `optional_reference` | `manual_preload_required` | shapefile bundle | `local_clip_then_reuse` | `Data/buildings/GoogleOpenBuildingsVector/` | `local_reference_only` |
| building | `raw.local.microsoft.building` | local cached national clip | `optional_reference` | `manual_preload_required` | shapefile bundle | `local_clip_then_reuse` | `Data/buildings/MicrosoftLocal/` | `local_reference_only` |
| road | `raw.osm.road` | OSM primary | `current_runtime` | `official_remote_supported` | shapefile bundle | `country_bundle_then_clip` | `Data/roads/OSM/` | `runtime_supported_now` |
| road | `raw.overture.transportation` | national secondary reference | `next_implementation` | `official_remote_supported` | parquet or geoparquet partitions | `theme_partition_then_clip` | null | `no_runtime_claim_until_b2` |
| water | `raw.osm.water` | OSM primary | `current_runtime` | `official_remote_supported` | shapefile bundle | `country_bundle_then_clip` | `Data/burundi-260127-free.shp/gis_osm_water_a_free_1.shp` | `runtime_supported_now` |
| water | `raw.local.water` | local reference sample | `optional_reference` | `manual_preload_required` | shapefile bundle | `local_clip_then_reuse` | `Data/water/` | `local_reference_only` |
| water | `raw.hydrorivers.water` | line secondary reference | `next_implementation` | `official_remote_supported` | shapefile bundle | `global_bundle_then_clip` | null | `no_runtime_claim_until_b2` |
| water | `raw.hydrolakes.water` | polygon secondary reference | `next_implementation` | `official_remote_supported` | shapefile bundle | `global_bundle_then_clip` | null | `no_runtime_claim_until_b2` |
| water | `raw.overture.water` | deferred alternative reference | `deferred` | `official_remote_supported` | parquet or geoparquet partitions | `theme_partition_then_clip` | null | `deferred_after_b1` |
| poi | `raw.osm.poi` | OSM primary | `current_runtime` | `official_remote_supported` | shapefile bundle | `country_bundle_then_clip` | `Data/burundi-260127-free.shp/gis_osm_pois_free_1.shp` | `bounded_runtime_now` |
| poi | `raw.gns.poi` | national gazetteer reference | `current_runtime` | `manual_preload_required` | shapefile bundle | `recursive_local_clip` | `Data/POI/**/GNS.shp` | `bounded_runtime_now` |
| poi | `raw.rh.poi` | local comparison reference | `optional_reference` | `manual_preload_required` | shapefile bundle | `recursive_local_clip` | `Data/POI/**/RH.shp` | `local_reference_only` |
| poi | `raw.overture.places` | deferred third source | `deferred` | `official_remote_supported` | parquet or geoparquet partitions | `theme_partition_then_clip` | null | `deferred_after_b1` |

## Canonical 字段映射轮廓

机器可消费版本见 `2026-05-18-national-source-matrix.json` 的
`field_mapping_profiles`。这里保留人类可读摘要。

### `building.vector.v1`

- canonical fields:
  - `geometry`
  - `source_feature_id`
  - `source_id`
  - `height_m`
  - `name`
  - `confidence`
- probe policy:
  - OSM 优先探测 `osm_id / osm_way_id / osm_rel_id / height / name`
  - Microsoft 优先探测 `id / height`
  - Google, OpenBuildingMap, Google Open Buildings Vector 统一探测 `id / height / confidence / name`
- 约束:
  - 不因为某个 provider 缺失 `height_m` 就改变 canonical schema。
  - `height_m` 只代表可选属性，不代表 shared runtime 已承诺 raster 或高度增强语义。

### `road.line.v1`

- canonical fields:
  - `geometry`
  - `source_feature_id`
  - `source_id`
  - `road_class`
  - `name`
  - `surface`
  - `lanes`
- probe policy:
  - OSM 优先探测 `osm_id / fclass / highway / name / surface / lanes`
  - Overture Transportation 预留 `id / class / subclass / names.primary / surface / lane_count`
- 约束:
  - `raw.overture.transportation` 在 B2 落地前只锁命名和映射方向，不宣传为已支持。

### `water.line_polygon.v1`

- canonical fields:
  - `geometry`
  - `source_feature_id`
  - `source_id`
  - `feature_kind`
  - `water_class`
  - `name`
  - `perennial_flag`
- probe policy:
  - OSM 优先探测 `osm_id / fclass / waterway / natural / name`
  - HydroRIVERS 预留 `HYRIV_ID / ORD_STRA / DIS_AV_CMS`
  - HydroLAKES 预留 `Hylak_id / Lake_type / Vol_total / Depth_avg`
  - Overture Water 仅保留 deferred 命名，不在本批次展开字段承诺
- 约束:
  - Water 的第二来源必须同时覆盖 line 与 polygon，不允许只补其中一类就宣传“国家级多源 water 已闭环”。

### `poi.point.v1`

- canonical fields:
  - `geometry`
  - `source_feature_id`
  - `source_id`
  - `name`
  - `category`
  - `admin_country`
- probe policy:
  - OSM 优先探测 `osm_id / name / fclass / type`
  - GNS 优先探测 `UFI / UNI / FULL_NAME / DSG / CC1`
  - RH 优先探测 `ID / NAME / CATEGORY`
  - Overture Places 预留 `id / names.primary / categories.primary / country`
- 约束:
  - OSM + GNS 是本轮唯一必须打通的国家级 POI 组合；RH 和 Overture Places 都不能在 B1 被误写成硬承诺。

## B2-B5 执行入口

- B2 只能先实现本文件里 `delivery_stage=next_implementation` 的 source。
- B3 的 national clip / tiling / stitching 设计必须复用这里的 `clip_strategy` 命名。
- B4 的规范化实现必须以这里的 `field_mapping_profile` 为 canonical 入口，而不是每个脚本自行命名字段。
- B5 的 smoke 或 bounded run 只允许引用这里已经锁定的 source ids。

## 非目标

- 不在本文件里提前承诺任何 provider 的法律文本细节；B2 接入时必须补齐 provider attribution 与 README/operations wording。
- 不把 `manual_preload_required` 的本地样例源包装成“自动官方下载”。
- 不额外开启 `trajectory-to-road`、前端 workbench 或图后端迁移相关工作。
