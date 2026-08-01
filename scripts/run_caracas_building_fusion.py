# -*- coding: utf-8 -*-
"""
委内瑞拉加拉加斯 建筑物融合脚本
=================================
基于 safe adapter (overlap-based matching) 的 3 源级联融合 + 栅格高度提取

数据源优先级: Microsoft (最高) → Google → OSM (最低)
融合逻辑: 逐对 overlap-based 贪婪 1:1 匹配，保留高优先级源几何 + 合并属性
高度提取: 从 Google Open Buildings 栅格瓦片中采样建筑质心点高度

输出: D:\\fyx\\data\\委内瑞拉\\加拉加斯\\fused_buildings.gpkg
"""
import sys, os, time, json, glob, warnings
from datetime import datetime, timedelta

os.environ["PROJ_LIB"] = ""  # suppress proj.db version conflict
warnings.filterwarnings("ignore", category=UserWarning)

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

OUTPUT_DIR = r"D:\fyx\data\委内瑞拉\加拉加斯"
TEMP_DIR = os.path.join(OUTPUT_DIR, "_building_fusion_temp")
os.makedirs(TEMP_DIR, exist_ok=True)

# ─── 日志工具 ─────────────────────────────────────────────
_START = time.time()
_LOG_FILE = os.path.join(TEMP_DIR, "fusion_progress.log")

def log(msg: str):
    elapsed = timedelta(seconds=int(time.time() - _START))
    line = f"[{elapsed}] {msg}"
    print(line, flush=True)
    with open(_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def checkpoint(name: str, gdf: gpd.GeoDataFrame):
    """写入中间产物以便断点续跑和进度检查"""
    path = os.path.join(TEMP_DIR, f"ckpt_{name}.gpkg")
    clean = gdf.copy()
    # 删除 pyogrio 不兼容的 fid 列
    for c in ["fid", "fid_1", "fid_2"]:
        if c in clean.columns:
            clean = clean.drop(columns=[c])
    clean.to_file(path, driver="GPKG")
    log(f"  checkpoint → {path}  ({len(clean)} rows)")

# ─── 1. 加载数据 ──────────────────────────────────────────
log("=" * 60)
log("STEP 1: 加载数据源")
log("=" * 60)

CRS_GEO = "EPSG:4326"
CRS_PROJ = "EPSG:32619"  # UTM 19N

def load_source(name: str, path: str) -> gpd.GeoDataFrame:
    t0 = time.time()
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs(CRS_GEO)
    gdf = gdf.to_crs(CRS_PROJ)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    # explode MultiPolygon → Polygon
    gdf = gdf.explode(index_parts=False).reset_index(drop=True)
    gdf["_src"] = name
    gdf["_area"] = gdf.geometry.area
    gdf = gdf[gdf["_area"] > 1.0].copy()  # 过滤 <1m² 噪点
    log(f"  {name}: {len(gdf)} 个多边形 ({time.time()-t0:.1f}s)")
    return gdf

msft = load_source("MS", r"D:\fyx\任务\委内瑞拉数据整合\output\capital\Microsoft_capital_district.gpkg")
gg   = load_source("GG", r"D:\fyx\任务\委内瑞拉数据整合\output\capital\googlebuildingv3.gpkg")
osm  = load_source("OSM", r"D:\fyx\任务\委内瑞拉数据整合\output\capital\osm\buildings.shp")

# ─── 2. 规范化属性列 ──────────────────────────────────────
log("")
log("STEP 2: 规范化属性列")

# Google: 已有 area_in_meters, confidence, full_plus_code
gg["_confidence"] = pd.to_numeric(gg.get("confidence", pd.NA), errors="coerce").fillna(0.5)
gg["_area_declared"] = pd.to_numeric(gg.get("area_in_meters", pd.NA), errors="coerce")

# OSM: 已有 osm_id, code, fclass, name, type
osm["_osm_id"] = osm.get("osm_id", pd.Series(range(1, len(osm)+1)))
osm["_fclass"] = osm.get("fclass", pd.Series("building"))
osm["_name"] = osm.get("name", pd.NA)
osm["_type"] = osm.get("type", pd.NA)

# Microsoft: 只有 geometry，生成占位列
msft["_confidence"] = 1.0  # MS 几何被认为最精确
msft["_area_declared"] = msft.geometry.area

log(f"  MS: {len(msft)} | GG: {len(gg)} | OSM: {len(osm)}")

# ─── 3. 级联融合 ──────────────────────────────────────────
log("")
log("STEP 3: 级联融合 (重叠面积匹配)")

def pairwise_fuse(
    base: gpd.GeoDataFrame,
    target: gpd.GeoDataFrame,
    base_name: str,
    target_name: str,
    overlap_threshold: float = 0.10,
) -> gpd.GeoDataFrame:
    """
    两源融合: base 优先级高于 target.
    匹配逻辑: sjoin(intersects) → overlap = 交集面积 / min(面积1, 面积2) → 贪婪 1:1
    匹配成功: 保留 base 几何 + 保留 base 属性 + 合并 target 属性
    未匹配: 分别保留
    """
    log(f"  [{base_name} ({len(base)})] vs [{target_name} ({len(target)})] ...")
    t0 = time.time()

    # 添加行索引（用唯一列名避免 sjoin 重命名冲突）
    base = base.copy()
    target = target.copy()
    base["_b_row"] = np.arange(len(base))
    target["_t_row"] = np.arange(len(target))

    # sjoin
    log(f"    sjoin ...")
    candidates = gpd.sjoin(
        base[["_b_row", "geometry"]],
        target[["_t_row", "geometry"]],
        how="inner",
        predicate="intersects",
    )
    log(f"    {len(candidates)} candidate pairs")

    matched_rows = []
    if not candidates.empty:
        b_rows = candidates["_b_row"].to_numpy(dtype=int)
        t_rows = candidates["_t_row"].to_numpy(dtype=int)

        b_geoms = base.geometry.iloc[b_rows].reset_index(drop=True)
        t_geoms = target.geometry.iloc[t_rows].reset_index(drop=True)
        b_areas = b_geoms.area.to_numpy()
        t_areas = t_geoms.area.to_numpy()
        intersection_areas = b_geoms.intersection(t_geoms).area.to_numpy()
        min_areas = np.minimum(b_areas, t_areas)
        min_areas[min_areas == 0] = 1e-10
        overlaps = intersection_areas / min_areas

        df = pd.DataFrame({"_b_row": b_rows, "_t_row": t_rows, "_overlap": overlaps})
        df = df[df["_overlap"] >= overlap_threshold]
        df = df.sort_values("_overlap", ascending=False)
        df = df.drop_duplicates("_b_row", keep="first")
        df = df.drop_duplicates("_t_row", keep="first")
        matched_rows = df
        log(f"    {len(matched_rows)} matched (overlap >= {overlap_threshold})")

    # 构建合并结果
    result_rows = []
    used_b = set(matched_rows["_b_row"].tolist()) if not matched_rows.empty else set()
    used_t = set(matched_rows["_t_row"].tolist()) if not matched_rows.empty else set()

    # --- 已匹配: base 几何 + 合并属性 ---
    if not matched_rows.empty:
        for _, mr in matched_rows.iterrows():
            b_row = int(mr["_b_row"])
            t_row = int(mr["_t_row"])
            b = base.iloc[b_row]
            t = target.iloc[t_row]

            row_data = {"geometry": b.geometry, "_src": base_name, "_matched": True,
                        "_overlap": mr["_overlap"], "_src_secondary": target_name}

            # 合并属性: base 优先，target 补充
            for col in base.columns:
                if col not in ("geometry", "_b_row", "_t_row", "_src", "_matched", "_overlap", "_src_secondary"):
                    row_data[col] = b[col]

            # target 中 base 没有的属性合并过来
            for col in target.columns:
                if col not in ("geometry", "_b_row", "_t_row", "_src", "_matched", "_overlap", "_src_secondary"):
                    if col not in row_data:
                        row_data[col] = t[col]
                    elif pd.isna(row_data.get(col)):
                        row_data[col] = t[col]

            result_rows.append(row_data)

    # --- 未匹配 base ---
    for idx in range(len(base)):
        if idx not in used_b:
            row = base.iloc[idx]
            rd = {"geometry": row.geometry, "_src": base_name, "_matched": False}
            for col in base.columns:
                if col not in ("geometry", "_b_row", "_t_row"):
                    rd[col] = row[col]
            result_rows.append(rd)

    # --- 未匹配 target ---
    for idx in range(len(target)):
        if idx not in used_t:
            row = target.iloc[idx]
            rd = {"geometry": row.geometry, "_src": target_name, "_matched": False}
            for col in target.columns:
                if col not in ("geometry", "_b_row", "_t_row"):
                    rd[col] = row[col]
            result_rows.append(rd)

    result = gpd.GeoDataFrame(result_rows, geometry="geometry", crs=base.crs)
    # 丢弃内部临时列
    result = result.drop(columns=["_b_row", "_t_row"], errors="ignore")
    log(f"    fused: {len(result)} rows ({time.time()-t0:.1f}s)")
    return result

# 第一轮: MS vs GG
log("\n--- Round 1: MS (base) vs GG ---")
fused_r1 = pairwise_fuse(msft, gg, "MS", "GG", overlap_threshold=0.10)
checkpoint("r1_ms_gg", fused_r1)

# 第二轮: (MS+GG) vs OSM
log("\n--- Round 2: (MS+GG) (base) vs OSM ---")
fused_r2 = pairwise_fuse(fused_r1, osm, "MS_GG", "OSM", overlap_threshold=0.10)
checkpoint("r2_ms_gg_osm", fused_r2)

# ─── 4. 高度提取 ──────────────────────────────────────────
log("")
log("STEP 4: 从栅格提取建筑高度")

RASTER_DIR = r"D:\fyx\data\委内瑞拉\加拉加斯\height_rasters\geotiffs"

def extract_heights(gdf: gpd.GeoDataFrame, raster_dir: str) -> gpd.GeoDataFrame:
    """对每个建筑，在其质心处采样高度栅格值（批量采样优化）"""
    import rasterio
    from rasterio import sample

    tiff_files = sorted(glob.glob(os.path.join(raster_dir, "*.tif")))
    log(f"  {len(tiff_files)} raster tiles")

    # 计算质心 (UTM 19N, 与栅格一致)
    centroids = gdf.geometry.centroid
    heights = pd.Series(np.nan, index=gdf.index, dtype=float)

    # 为每个瓦片建立空间范围
    tile_info = []
    for tf in tiff_files:
        with rasterio.open(tf) as src:
            tile_info.append({
                "path": tf,
                "bounds": src.bounds,
                "transform": src.transform,
                "crs_epsg": src.crs.to_epsg() if src.crs else None,
                "width": src.width,
                "height": src.height,
            })

    gdf_crs_epsg = gdf.crs.to_epsg() if gdf.crs else None
    for ti_idx, tile in enumerate(tile_info):
        # CRS 对齐: 如果栅格 CRS 与建筑不同，转换坐标
        if tile["crs_epsg"] and tile["crs_epsg"] != gdf_crs_epsg:
            pt_series = gpd.GeoSeries(centroids, crs=gdf.crs).to_crs(tile["crs_epsg"])
            pts_x = pt_series.x
            pts_y = pt_series.y
        else:
            pts_x = centroids.x
            pts_y = centroids.y

        # 找出该瓦片范围内的建筑质心
        minx, miny, maxx, maxy = tile["bounds"]
        mask = (
            (pts_x >= minx) & (pts_x <= maxx) &
            (pts_y >= miny) & (pts_y <= maxy)
        )
        if not mask.any():
            continue

        hit_indices = centroids[mask].index.tolist()
        hit_coords = [(pts_x[i], pts_y[i]) for i in hit_indices]
        log(f"    tile {ti_idx+1}/{len(tiff_files)}: {len(hit_indices)} buildings in range")

        with rasterio.open(tile["path"]) as src:
            for df_idx, val in zip(hit_indices, src.sample(hit_coords, indexes=1)):
                h = float(val[0]) if val.size > 0 else np.nan
                if not np.isnan(h) and h > 0:
                    heights[df_idx] = h

    gdf["height_raster"] = heights
    valid = heights.notna().sum()
    log(f"  height extracted: {valid}/{len(gdf)} ({100*valid/max(1,len(gdf)):.1f}%)")
    return gdf

fused_with_height = extract_heights(fused_r2, RASTER_DIR)
checkpoint("r3_with_height", fused_with_height)

# ─── 5. 整理输出列 ────────────────────────────────────────
log("")
log("STEP 5: 整理输出")

# 构建最终高度列: raster > declared area
fused_with_height["height_declared"] = pd.to_numeric(fused_with_height.get("_area_declared", pd.NA), errors="coerce")
fused_with_height["height_final"] = fused_with_height["height_raster"].fillna(fused_with_height["height_declared"])

# 转回 WGS84
fused_with_height = fused_with_height.to_crs(CRS_GEO)

# 保留最终列
final_cols = {
    "_src": "source",
    "_matched": "matched",
    "_overlap": "overlap_ratio",
    "_src_secondary": "secondary_source",
    "_confidence": "confidence",
    "_area_declared": "area_declared_m2",
    "_area": "area_m2",
    "_osm_id": "osm_id",
    "_fclass": "fclass",
    "_name": "name",
    "_type": "building_type",
    "height_raster": "height_raster",
    "height_final": "height",
}

output = fused_with_height.rename(columns=final_cols)
keep_cols = list(dict.fromkeys([v for k, v in final_cols.items() if v in output.columns])) + ["geometry"]
output = output[[c for c in keep_cols if c in output.columns]]

log(f"  final columns: {list(output.columns)}")
log(f"  final rows: {len(output)}")

# ─── 6. 输出 ──────────────────────────────────────────────
log("")
log("STEP 6: 写入输出文件")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# GPKG (完整)
gpkg_path = os.path.join(OUTPUT_DIR, "fused_buildings.gpkg")
# 防止 pyogrio 列名冲突
output_clean = output.copy()
for c in ["fid", "fid_1", "fid_2"]:
    if c in output_clean.columns:
        output_clean = output_clean.drop(columns=[c])
# 去重列名
output_clean = output_clean.loc[:, ~output_clean.columns.duplicated()]
output_clean.to_file(gpkg_path, driver="GPKG")
log(f"  GPKG: {gpkg_path}  ({os.path.getsize(gpkg_path)/1024/1024:.1f} MB)")

# SHP (精简，列名 < 10 字符)
shp_out = output_clean.copy()
# 去重列名
shp_out = shp_out.loc[:, ~shp_out.columns.duplicated()]
shp_rename = {}
for c in shp_out.columns:
    if c != "geometry" and len(c) > 10:
        shp_rename[c] = c[:10]
if shp_rename:
    shp_out = shp_out.rename(columns=shp_rename)
shp_path = os.path.join(OUTPUT_DIR, "fused_buildings.shp")
shp_out.to_file(shp_path)
log(f"  SHP: {shp_path}  ({os.path.getsize(shp_path)/1024/1024:.1f} MB)")

# 统计摘要
stats = {
    "total_buildings": int(len(output)),
    "source_counts": output["source"].value_counts().to_dict(),
    "matched_count": int(output["matched"].sum()) if "matched" in output.columns else 0,
    "height_raster_pct": float(output["height_raster"].notna().mean() * 100) if "height_raster" in output.columns else 0,
    "height_final_mean": float(output["height"].mean()) if "height" in output.columns else 0,
    "crs": "EPSG:4326",
    "elapsed": str(timedelta(seconds=int(time.time() - _START))),
}
stats_path = os.path.join(OUTPUT_DIR, "fused_buildings_stats.json")
with open(stats_path, "w", encoding="utf-8") as f:
    json.dump(stats, f, indent=2, ensure_ascii=False)
log(f"  stats: {stats_path}")

# ─── 完成 ─────────────────────────────────────────────────
log("")
log("=" * 60)
log(f"融合完成! 总耗时: {timedelta(seconds=int(time.time() - _START))}")
log(f"输出: {OUTPUT_DIR}")
log("=" * 60)
for k, v in stats.items():
    log(f"  {k}: {v}")
