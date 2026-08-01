# -*- coding: utf-8 -*-
"""
为 buildingfusion.shp 从 Google Open Buildings 栅格 Band 2 提取高度。
数据 CRS: EPSG:32643 -> 重投影到 EPSG:32619 匹配栅格 -> 提取高度 -> 写回
"""
import os, time, glob, warnings, json
os.environ['PROJ_LIB'] = ''
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.transform import rowcol
from datetime import timedelta

INPUT_SHP  = r"D:\fyx\data\委内瑞拉\加拉加斯\building\buildingfusion.shp"
RASTER_DIR = r"D:\fyx\data\委内瑞拉\加拉加斯\height_rasters\geotiffs"
HEIGHT_MIN = 0.5
HEIGHT_MAX = 200.0

_START = time.time()
def log(msg):
    elapsed = timedelta(seconds=int(time.time() - _START))
    print(f"[{elapsed}] {msg}", flush=True)

# ─── 1. 加载 ─────────────────────────────────────────────
log(f"Loading {INPUT_SHP} ...")
t0 = time.time()
src = gpd.read_file(INPUT_SHP)
log(f"  {len(src)} buildings, CRS={src.crs}, cols={len(src.columns)} ({time.time()-t0:.1f}s)")

# ─── 2. 重投影到 UTM 19N (栅格 CRS) ──────────────────────
log("Reprojecting to EPSG:32619 (raster CRS)...")
t0 = time.time()
buildings_proj = src.to_crs("EPSG:32619")
centroids = buildings_proj.geometry.centroid
c_x = centroids.x.values
c_y = centroids.y.values
log(f"  done ({time.time()-t0:.1f}s)")

# ─── 3. 扫描栅格瓦片 ─────────────────────────────────────
tiffs = sorted(glob.glob(os.path.join(RASTER_DIR, "*.tif")))
log(f"{len(tiffs)} raster tiles")

tile_info = []
for tf in tiffs:
    with rasterio.open(tf) as r:
        tile_info.append({
            "path": tf,
            "bounds": r.bounds,
            "transform": r.transform,
            "h": r.height, "w": r.width,
        })

# ─── 4. 逐瓦片提取高度 (Band 2) ───────────────────────────
heights = np.full(len(src), np.nan, dtype=np.float32)

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

    with rasterio.open(tile["path"]) as r:
        rows, cols = rowcol(tile["transform"], hit_x, hit_y)
        rows = np.array(rows, dtype=np.int32)
        cols = np.array(cols, dtype=np.int32)

        in_bounds = (rows >= 0) & (rows < tile["h"]) & (cols >= 0) & (cols < tile["w"])
        if not in_bounds.any():
            continue
        b_rows = rows[in_bounds]
        b_cols = cols[in_bounds]
        b_indices = hit_indices[in_bounds]

        # 裁剪窗口
        r_min = max(0, int(b_rows.min()) - 5)
        r_max = min(tile["h"], int(b_rows.max()) + 6)
        c_min = max(0, int(b_cols.min()) - 5)
        c_max = min(tile["w"], int(b_cols.max()) + 6)

        band2 = r.read(2, window=((r_min, r_max), (c_min, c_max)))
        off_rows = b_rows - r_min
        off_cols = b_cols - c_min
        vals = band2[off_rows, off_cols]

        h_valid = (vals >= HEIGHT_MIN) & (vals <= HEIGHT_MAX)
        heights[b_indices[h_valid]] = vals[h_valid]

    valid_in_tile = (~np.isnan(heights[hit_indices])).sum()
    log(f"    valid heights: {valid_in_tile}/{n_hits} ({time.time()-t0:.1f}s)")

# ─── 5. 更新列 ───────────────────────────────────────────
total = len(src)
valid = int((~np.isnan(heights)).sum())
log(f"\nHeight extraction: {valid}/{total} ({100*valid/max(1,total):.1f}%)")

vh = heights[~np.isnan(heights)]
if len(vh) > 0:
    log(f"  Range: {vh.min():.2f} ~ {vh.max():.2f} m")
    log(f"  Mean/Median: {vh.mean():.2f} / {np.median(vh):.2f} m")
    log(f"  p5/p95: {np.percentile(vh,5):.1f} / {np.percentile(vh,95):.1f} m")

src["H_Raster"] = np.where(~np.isnan(heights), heights, 0.0)
src["height"] = np.where(~np.isnan(heights), heights, 0.0)

# ─── 6. 写回 ─────────────────────────────────────────────
log(f"\nWriting back to {INPUT_SHP} ...")
t0 = time.time()
# 去重列名
src = src.loc[:, ~src.columns.duplicated()]
src.to_file(INPUT_SHP)
log(f"  Done ({time.time()-t0:.1f}s, {os.path.getsize(INPUT_SHP)/1024/1024:.1f} MB)")

log(f"\n=== Complete ===")
log(f"Total: {len(src)} buildings, {valid} with height ({100*valid/max(1,total):.1f}%)")
log(f"Elapsed: {timedelta(seconds=int(time.time() - _START))}")
