# -*- coding: utf-8 -*-
"""
修复高度提取 v2: 读取已融合 GPKG，从 Google Open Buildings 栅格
Band 2 (building_height) 全波段读取 + 向量化提取高度。
"""
import sys, os, time, glob, warnings, json
from datetime import datetime, timedelta

os.environ["PROJ_LIB"] = ""
warnings.filterwarnings("ignore", category=UserWarning)

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.transform import rowcol

OUTPUT_DIR = r"D:\fyx\data\委内瑞拉\加拉加斯"
RASTER_DIR = r"D:\fyx\data\委内瑞拉\加拉加斯\height_rasters\geotiffs"
INPUT_GPKG  = os.path.join(OUTPUT_DIR, "fused_buildings.gpkg")
OUTPUT_GPKG = os.path.join(OUTPUT_DIR, "fused_buildings.gpkg")
OUTPUT_SHP  = os.path.join(OUTPUT_DIR, "fused_buildings.shp")
STATS_PATH  = os.path.join(OUTPUT_DIR, "fused_buildings_stats.json")

HEIGHT_MIN = 0.5
HEIGHT_MAX = 200.0

_START = time.time()
def log(msg):
    elapsed = timedelta(seconds=int(time.time() - _START))
    print(f"[{elapsed}] {msg}", flush=True)

# ─── 1. 加载 ─────────────────────────────────────────────
log(f"Loading {INPUT_GPKG} ...")
buildings = gpd.read_file(INPUT_GPKG)
log(f"  {len(buildings)} buildings loaded")

buildings_proj = buildings.to_crs("EPSG:32619")
centroids = buildings_proj.geometry.centroid
c_x = centroids.x.values
c_y = centroids.y.values

# 删旧高度列
for col in ["height_raster", "height_final", "height_declared", "height_src"]:
    if col in buildings.columns:
        buildings = buildings.drop(columns=[col])

# ─── 2. 扫描瓦片 ─────────────────────────────────────────
tiffs = sorted(glob.glob(os.path.join(RASTER_DIR, "*.tif")))
log(f"{len(tiffs)} raster tiles found")

tile_info = []
for tf in tiffs:
    with rasterio.open(tf) as src:
        tile_info.append({
            "path": tf,
            "bounds": src.bounds,
            "transform": src.transform,
            "h": src.height, "w": src.width,
        })

# ─── 3. 逐瓦片提取高度（裁剪窗口读取） ──────────────────
heights = np.full(len(buildings), np.nan, dtype=np.float32)

for ti_idx, tile in enumerate(tile_info):
    minx, miny, maxx, maxy = tile["bounds"]
    mask = (c_x >= minx) & (c_x <= maxx) & (c_y >= miny) & (c_y <= maxy)
    n_hits = mask.sum()
    if n_hits == 0:
        continue

    t0 = time.time()
    hit_indices = np.where(mask)[0]
    hit_x = c_x[hit_indices]
    hit_y = c_y[hit_indices]

    log(f"  tile {ti_idx+1}/{len(tiffs)}: {os.path.basename(tile['path'])} -> {n_hits} buildings")

    with rasterio.open(tile["path"]) as src:
        # 计算命中点的行/列
        rows, cols = rowcol(tile["transform"], hit_x, hit_y)
        rows = np.array(rows, dtype=np.int32)
        cols = np.array(cols, dtype=np.int32)

        # 过滤越界
        in_bounds = (rows >= 0) & (rows < tile["h"]) & (cols >= 0) & (cols < tile["w"])
        if not in_bounds.any():
            continue
        b_rows = rows[in_bounds]
        b_cols = cols[in_bounds]
        b_indices = hit_indices[in_bounds]

        # 确定裁剪窗口（加 5px 边距）
        r_min = max(0, int(b_rows.min()) - 5)
        r_max = min(tile["h"], int(b_rows.max()) + 6)
        c_min = max(0, int(b_cols.min()) - 5)
        c_max = min(tile["w"], int(b_cols.max()) + 6)

        window = ((r_min, r_max), (c_min, c_max))
        band2 = src.read(2, window=window)  # 仅读取窗口
        w_pixels = band2.size
        log(f"    window rows={r_min}:{r_max} cols={c_min}:{c_max}, pixels={w_pixels/1e6:.1f}M")

        # 偏移坐标到窗口
        off_rows = b_rows - r_min
        off_cols = b_cols - c_min
        vals = band2[off_rows, off_cols]

        h_valid = (vals >= HEIGHT_MIN) & (vals <= HEIGHT_MAX)
        heights[b_indices[h_valid]] = vals[h_valid]

    valid_in_tile = (~np.isnan(heights[hit_indices])).sum()
    log(f"    valid heights: {valid_in_tile}/{n_hits} ({time.time()-t0:.1f}s)")

# ─── 4. 统计 ─────────────────────────────────────────────
total = len(buildings)
valid = int((~np.isnan(heights)).sum())
log(f"\nResults: {valid}/{total} ({100*valid/max(1,total):.1f}%) with valid height")

vh = heights[~np.isnan(heights)]
if len(vh) > 0:
    log(f"  Range: {vh.min():.2f} ~ {vh.max():.2f} m")
    log(f"  Mean/Median: {vh.mean():.2f} / {np.median(vh):.2f} m")
    log(f"  p5/p95: {np.percentile(vh,5):.1f} / {np.percentile(vh,95):.1f} m")

# ─── 5. 更新 ─────────────────────────────────────────────
buildings["height"] = heights
buildings["height_src"] = "raster_band2"
log(f"Columns: {list(buildings.columns)}")

# ─── 6. 写入 ─────────────────────────────────────────────
log(f"\nWriting outputs ...")
buildings = buildings.loc[:, ~buildings.columns.duplicated()]
for c in ["fid", "fid_1", "fid_2"]:
    if c in buildings.columns:
        buildings = buildings.drop(columns=[c])

t0 = time.time()
buildings.to_file(OUTPUT_GPKG, driver="GPKG")
log(f"  GPKG: {OUTPUT_GPKG} ({os.path.getsize(OUTPUT_GPKG)/1024/1024:.1f} MB, {time.time()-t0:.1f}s)")

buildings.to_file(OUTPUT_SHP)
log(f"  SHP: {OUTPUT_SHP} ({os.path.getsize(OUTPUT_SHP)/1024/1024:.1f} MB)")

# ─── 7. Stats ────────────────────────────────────────────
stats = {
    "total_buildings": total,
    "source_counts": buildings["source"].value_counts().to_dict() if "source" in buildings.columns else {},
    "height_from_raster_pct": round(100*valid/max(1,total), 1),
    "height_min": round(float(vh.min()), 2) if len(vh) > 0 else None,
    "height_max": round(float(vh.max()), 2) if len(vh) > 0 else None,
    "height_mean": round(float(vh.mean()), 2) if len(vh) > 0 else None,
    "height_median": round(float(np.median(vh)), 2) if len(vh) > 0 else None,
    "height_band": "band2_building_height",
    "height_valid_range": f"[{HEIGHT_MIN}, {HEIGHT_MAX}]",
    "crs": "EPSG:4326",
    "elapsed": str(timedelta(seconds=int(time.time() - _START))),
}
with open(STATS_PATH, "w", encoding="utf-8") as f:
    json.dump(stats, f, indent=2, ensure_ascii=False)

log(f"\nDone! Elapsed: {stats['elapsed']}")
log(f"Height coverage: {stats['height_from_raster_pct']}%")
