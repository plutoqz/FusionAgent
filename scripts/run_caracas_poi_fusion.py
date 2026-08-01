# -*- coding: utf-8 -*-
"""
委内瑞拉加拉加斯 POI 融合脚本
使用 fusion_algorithms.poi_fusion 中的 run_poi_geohash_priority_fusion 算法
将 geonames POI 和 OSM POI 融合为一个数据集

说明：算法优先使用 GeoHash 列进行邻域匹配，
否则回退到空间距离匹配。本脚本使用 UTM 投影确保距离参数生效。
"""
import sys
import os

sys.path.insert(0, r"D:\code\FusionAgent")

import geopandas as gpd
import pandas as pd
import numpy as np
from fusion_algorithms.poi_fusion import run_poi_geohash_priority_fusion
from fusion_algorithms.contracts import PoiFusionParams

# ---- 输入文件 ----
geonames_path = r"D:\fyx\任务\委内瑞拉数据整合\output\capital\geonames_poi\geonames_capital.gpkg"
osm_path = r"D:\fyx\任务\委内瑞拉数据整合\output\capital\osm\poi.shp"
output_dir = r"D:\fyx\data\委内瑞拉\加拉加斯"

# ---- 加载数据 ----
print("Loading geonames POI...")
gn = gpd.read_file(geonames_path)
print(f"  geonames: {len(gn)} rows, CRS={gn.crs}")

print("Loading OSM POI...")
osm = gpd.read_file(osm_path)
print(f"  OSM: {len(osm)} rows, CRS={osm.crs}")

# ---- 统一 CRS 到 WGS84 ----
gn = gn.set_crs("EPSG:4326", allow_override=True)
osm = osm.set_crs("EPSG:4326", allow_override=True)

# ---- 投影到 UTM 19N (加拉加斯所在区域，单位：米) ----
target_crs = "EPSG:32619"  # WGS 84 / UTM zone 19N
print(f"\nProjecting to {target_crs} (meters)...")
gn_proj = gn.to_crs(target_crs)
osm_proj = osm.to_crs(target_crs)
print(f"  After projection: geonames={len(gn_proj)}, OSM={len(osm_proj)}")

# ---- 构建数据源字典 ----
sources = {
    "GNG": gn_proj,
    "OSM": osm_proj,
}

# ---- 融合参数 ----
params = PoiFusionParams(
    geohash_precision=8,
    neighbor_rings=1,
    name_similarity_threshold=0.75,
    source_priority_order=("GNG", "OSM"),
    duplicate_distance_m=250.0,
)

# ---- 执行融合 ----
print("\nRunning POI fusion...")
fused = run_poi_geohash_priority_fusion(sources, params)
print(f"  Fused result: {len(fused)} rows")
print(f"  SRC distribution: {fused['SRC'].value_counts().to_dict()}")
print(f"  MATCHED distribution: {fused['MATCHED'].value_counts().to_dict()}")

# ---- 清理列名冲突 ----
# 删除可能导致写入问题的列
problematic_cols = ["fid"]
for col in problematic_cols:
    if col in fused.columns:
        fused = fused.drop(columns=[col])

# 清理列名中的特殊字符（shapefile 列名限制 10 字符）
# GPKG 没有此限制，但为了兼容性做清理
rename_map = {}
for col in fused.columns:
    if col != "geometry" and len(col) > 10:
        # 保留原名，GPKG 支持长列名
        pass
print(f"  Output columns: {list(fused.columns)}")

# ---- 转回 WGS84 ----
print("\nConverting back to EPSG:4326...")
fused = fused.to_crs("EPSG:4326")

# ---- 确保输出目录存在 ----
os.makedirs(output_dir, exist_ok=True)

# ---- 输出 GPKG ----
output_gpkg = os.path.join(output_dir, "fused_poi.gpkg")
try:
    fused.to_file(output_gpkg, driver="GPKG")
    print(f"\nGPKG written: {output_gpkg}")
except Exception as e:
    print(f"\nGPKG write failed: {e}")
    # Fallback: try with specific engine
    fused.to_file(output_gpkg, driver="GPKG", engine="fiona")
    print(f"GPKG written (fiona): {output_gpkg}")

# ---- 输出 Shapefile (精简列) ----
# Shapefile 列名限制 10 字符，需要精简
cols_shp = ["SRC", "MATCHED", "name", "geometry"]
# 确保必要列存在
for c in cols_shp:
    if c not in fused.columns:
        fused[c] = ""
fused_shp = fused[cols_shp].copy()
# 截断列名到 10 字符
fused_shp.columns = [c[:10] for c in fused_shp.columns]

output_shp = os.path.join(output_dir, "fused_poi.shp")
try:
    fused_shp.to_file(output_shp)
    print(f"Shapefile written: {output_shp}")
except Exception as e:
    print(f"Shapefile write failed: {e}")

print("\nDone!")
print(f"\nOutput files in {output_dir}:")
for f in os.listdir(output_dir):
    fpath = os.path.join(output_dir, f)
    size_kb = os.path.getsize(fpath) / 1024
    print(f"  {f} ({size_kb:.1f} KB)")
