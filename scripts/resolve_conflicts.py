# -*- coding: utf-8 -*-
"""
分层处理建筑物重叠冲突
  Severe(>=50%): 按优先级直接删除低优先级方
  Moderate(20-50%): 降低阈值重做贪婪1:1匹配
  Mild(<20%): 保留（密集城区正常现象）
优先级: MS_GG > MS > GG > OSM
"""
import os, time, warnings, json
os.environ['PROJ_LIB'] = ''
warnings.filterwarnings('ignore')

import geopandas as gpd, numpy as np, pandas as pd

GPKG = r"D:\fyx\data\委内瑞拉\加拉加斯\fused_buildings.gpkg"
OUT_GPKG = GPKG
OUT_SHP  = os.path.join(os.path.dirname(GPKG), "fused_buildings.shp")
OUT_STATS = os.path.join(os.path.dirname(GPKG), "fused_buildings_stats.json")

T0 = time.time()
def log(msg):
    print(f"[{time.time()-T0:.0f}s] {msg}", flush=True)

# ─── 0. 加载 ────────────────────────────────────────────
log("Loading fused buildings...")
f = gpd.read_file(GPKG)
N0 = len(f)
log(f"  {N0} buildings")

f = f.set_crs('EPSG:4326', allow_override=True)
f_proj = f.to_crs('EPSG:32619')
f_proj['_area_m2'] = f_proj.geometry.area
f_proj['_id'] = np.arange(len(f_proj))

# 源优先级 (数字越小越优先)
PRIORITY = {'MS_GG': 1, 'MS': 2, 'GG': 3, 'OSM': 4}

# ─── 1. sjoin 找所有交集对 ──────────────────────────────
log("sjoin self-intersection...")
L = f_proj[['_id','_area_m2','source','matched','geometry']].rename(
    columns={'_id':'L','_area_m2':'aL','source':'sL','matched':'mL'})
R = f_proj[['_id','_area_m2','source','matched','geometry']].rename(
    columns={'_id':'R','_area_m2':'aR','source':'sR','matched':'mR'})

pairs = gpd.sjoin(L, R, how='inner', predicate='intersects')
pairs = pairs[pairs['L'] < pairs['R']].reset_index(drop=True)
log(f"  {len(pairs)} intersecting pairs")

# ─── 2. 计算 overlap ratio ───────────────────────────────
log("Computing overlap ratios...")
CHUNK = 100000
ov = np.empty(len(pairs), dtype=np.float32)
for start in range(0, len(pairs), CHUNK):
    end = min(start+CHUNK, len(pairs))
    ch = pairs.iloc[start:end]
    a = f_proj.geometry.iloc[ch['L'].values].reset_index(drop=True)
    b = f_proj.geometry.iloc[ch['R'].values].reset_index(drop=True)
    inter = a.intersection(b).area.values
    min_ab = np.minimum(ch['aL'].values, ch['aR'].values)
    min_ab[min_ab==0] = 1e-10
    ov[start:end] = inter / min_ab

pairs['ov_ratio'] = ov
log(f"  computed")

# ─── 3. 分层处理 ─────────────────────────────────────────
log("\n=== Layered Conflict Resolution ===")

to_drop = set()  # _id values to delete from the fused result

# ── 3a. Severe (>=50%): priority-based discarding ──
severe = pairs[pairs['ov_ratio'] >= 0.50].copy()
log(f"\nSevere (>=50%): {len(severe)} pairs")

# Sort by priority: handle highest-priority conflicts first
severe['priL'] = severe['sL'].map(PRIORITY).fillna(99)
severe['priR'] = severe['sR'].map(PRIORITY).fillna(99)

# Different priority: drop the lower one
diff_pri = severe[severe['priL'] != severe['priR']]
for _, row in diff_pri.iterrows():
    if row['priL'] < row['priR']:
        to_drop.add(int(row['R']))
    else:
        to_drop.add(int(row['L']))

# Same priority: keep larger area
same_pri = severe[severe['priL'] == severe['priR']]
for _, row in same_pri.iterrows():
    if row['aL'] >= row['aR']:
        to_drop.add(int(row['R']))
    else:
        to_drop.add(int(row['L']))

log(f"  Severely conflicted buildings to drop: {len(to_drop)}")

# ── 3b. Moderate (20-50%): re-match with greedy 1:1 ──
moderate = pairs[(pairs['ov_ratio'] >= 0.20) & (pairs['ov_ratio'] < 0.50)].copy()
moderate['priL'] = moderate['sL'].map(PRIORITY).fillna(99)
moderate['priR'] = moderate['sR'].map(PRIORITY).fillna(99)
log(f"\nModerate (20-50%): {len(moderate)} pairs")

# Remove pairs where either side is already dropped
moderate = moderate[~moderate['L'].isin(to_drop) & ~moderate['R'].isin(to_drop)]
log(f"  After severe cleanup: {len(moderate)} pairs")

# Greedy 1:1 matching with priority tie-breaking
moderate = moderate.sort_values(['ov_ratio', 'priL', 'priR'], ascending=[False, True, True])
used = set()
mod_drop = set()
for _, row in moderate.iterrows():
    l = int(row['L'])
    r = int(row['R'])
    if l in used or r in used or l in to_drop or r in to_drop:
        continue
    # Keep higher priority, drop lower
    used.add(l)
    used.add(r)
    if row['priL'] < row['priR']:
        mod_drop.add(r)
    else:
        mod_drop.add(l)

to_drop |= mod_drop
log(f"  Moderate conflicts resolved: {len(mod_drop)} additional drops")
log(f"  Total drops: {len(to_drop)}")

# ── 3c. Mild (<20%): keep all ──
mild_count = len(pairs[pairs['ov_ratio'] < 0.20])
log(f"\nMild (<20%): {mild_count} pairs — KEEP ALL")

# ─── 4. 构建清理后结果 ──────────────────────────────────
log(f"\n=== Building Clean Result ===")
keep_mask = ~np.isin(np.arange(len(f)), list(to_drop))
f_clean = f[keep_mask].copy()
log(f"  Original: {N0}")
log(f"  Removed:  {N0 - len(f_clean)} ({(N0-len(f_clean))*100/N0:.1f}%)")
log(f"  Kept:     {len(f_clean)}")

# Source distribution after cleaning
if 'source' in f_clean.columns:
    sc = f_clean['source'].value_counts()
    log(f"\nSource distribution after cleanup:")
    for s, c in sc.items():
        log(f"  {s}: {c}")

# Height stats unchanged?
if 'height' in f_clean.columns:
    h = f_clean['height'].dropna()
    log(f"\nHeight stats:")
    log(f"  coverage: {f_clean['height'].notna().sum()}/{len(f_clean)} ({100*f_clean['height'].notna().sum()/len(f_clean):.1f}%)")
    log(f"  range: {h.min():.2f} ~ {h.max():.2f} m")
    log(f"  mean/median: {h.mean():.2f} / {h.median():.2f} m")

# ─── 5. 写入输出 ────────────────────────────────────────
log(f"\nWriting outputs...")
f_clean = f_clean.loc[:, ~f_clean.columns.duplicated()]
for c in ["fid", "fid_1", "fid_2"]:
    if c in f_clean.columns:
        f_clean = f_clean.drop(columns=[c])

t0 = time.time()
f_clean.to_file(OUT_GPKG, driver="GPKG")
log(f"  GPKG: {os.path.getsize(OUT_GPKG)/1024/1024:.1f} MB ({time.time()-t0:.1f}s)")

f_clean.to_file(OUT_SHP)
log(f"  SHP: {os.path.getsize(OUT_SHP)/1024/1024:.1f} MB")

# Stats
vh = f_clean['height'].dropna() if 'height' in f_clean.columns else pd.Series()
stats = {
    "total_buildings": int(len(f_clean)),
    "removed_by_conflict_resolution": int(N0 - len(f_clean)),
    "source_counts": f_clean["source"].value_counts().to_dict() if "source" in f_clean.columns else {},
    "height_from_raster_pct": round(100*f_clean['height'].notna().sum()/len(f_clean), 1) if 'height' in f_clean.columns else 0,
    "height_min": round(float(vh.min()), 2) if len(vh) > 0 else None,
    "height_max": round(float(vh.max()), 2) if len(vh) > 0 else None,
    "height_mean": round(float(vh.mean()), 2) if len(vh) > 0 else None,
    "height_median": round(float(vh.median()), 2) if len(vh) > 0 else None,
    "height_band": "band2_building_height",
    "crs": "EPSG:4326",
}
with open(OUT_STATS, 'w', encoding='utf-8') as fh:
    json.dump(stats, fh, indent=2, ensure_ascii=False)

log(f"\nDone! Total: {time.time()-T0:.0f}s")
log(f"Final: {len(f_clean)} buildings (removed {N0-len(f_clean)})")
