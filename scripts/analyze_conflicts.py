# -*- coding: utf-8 -*-
"""分析融合建筑物重叠冲突"""
import os, time, warnings, json
os.environ['PROJ_LIB'] = ''
warnings.filterwarnings('ignore')

import geopandas as gpd
import numpy as np
import pandas as pd

GPKG = r"D:\fyx\data\委内瑞拉\加拉加斯\fused_buildings.gpkg"
OUT = r"D:\fyx\data\委内瑞拉\加拉加斯\conflict_analysis.json"

T0 = time.time()
def log(msg):
    print(f"[{time.time()-T0:.0f}s] {msg}", flush=True)

log("Loading...")
f = gpd.read_file(GPKG)
f = f.set_crs('EPSG:4326', allow_override=True)
f_proj = f.to_crs('EPSG:32619')
f_proj['_area_m2'] = f_proj.geometry.area
f_proj['_id'] = np.arange(len(f_proj))
N = len(f_proj)
log(f"  {N} buildings")

# ---- sjoin ----
log("sjoin ...")
left  = f_proj[['_id','_area_m2','source','matched','geometry']].rename(columns={'_id':'L','_area_m2':'aL','source':'sL','matched':'mL'})
right = f_proj[['_id','_area_m2','source','matched','geometry']].rename(columns={'_id':'R','_area_m2':'aR','source':'sR','matched':'mR'})
pairs = gpd.sjoin(left, right, how='inner', predicate='intersects')
pairs = pairs[pairs['L'] < pairs['R']].reset_index(drop=True)
P = len(pairs)
log(f"  {P} intersecting pairs")

# ---- overlap ratio in chunks ----
log("Computing overlap ratios...")
CHUNK = 100000
ov_ratios = np.empty(P, dtype=np.float32)
ov_areas  = np.empty(P, dtype=np.float32)

for start in range(0, P, CHUNK):
    end = min(start + CHUNK, P)
    chunk = pairs.iloc[start:end]
    idxL = chunk['L'].values
    idxR = chunk['R'].values
    geoL = f_proj.geometry.iloc[idxL].reset_index(drop=True)
    geoR = f_proj.geometry.iloc[idxR].reset_index(drop=True)
    inter = geoL.intersection(geoR).area.values
    min_a = np.minimum(chunk['aL'].values, chunk['aR'].values)
    min_a[min_a == 0] = 1e-10
    ratio = inter / min_a
    ov_ratios[start:end] = ratio
    ov_areas[start:end] = inter
    log(f"  {end}/{P} done")

pairs['ov_ratio'] = ov_ratios
pairs['ov_area_m2'] = ov_areas

# ---- categorize ----
severe   = pairs[pairs['ov_ratio'] >= 0.50]
moderate = pairs[(pairs['ov_ratio'] >= 0.20) & (pairs['ov_ratio'] < 0.50)]
mild     = pairs[(pairs['ov_ratio'] >= 0.05) & (pairs['ov_ratio'] < 0.20)]
trivial  = pairs[pairs['ov_ratio'] < 0.05]

log(f"\nTotal intersecting pairs: {P}")
log(f"  Severe  (>=50% overlap):  {len(severe):>8}  ({100*len(severe)/P:.1f}%)")
log(f"  Moderate(20-50%):         {len(moderate):>8}  ({100*len(moderate)/P:.1f}%)")
log(f"  Mild    (5-20%):          {len(mild):>8}  ({100*len(mild)/P:.1f}%)")
log(f"  Trivial (<5%):            {len(trivial):>8}  ({100*len(trivial)/P:.1f}%)")

# unique buildings involved
def uniq(df):
    return len(set(df['L'].tolist() + df['R'].tolist()))

log(f"\nUnique buildings involved:")
log(f"  Any overlap:     {uniq(pairs)} ({100*uniq(pairs)/N:.1f}%)")
log(f"  Severe:          {uniq(severe)} ({100*uniq(severe)/N:.1f}%)")
log(f"  Moderate+:       {uniq(pd.concat([severe,moderate]))} ({100*uniq(pd.concat([severe,moderate]))/N:.1f}%)")

# ---- source composition ----
def src_pair_label(row):
    a, b = sorted([row['sL'], row['sR']])
    return f"{a} <-> {b}"

for label, df in [('Severe', severe), ('Moderate', moderate), ('Mild', mild), ('Trivial', trivial)]:
    df['pair'] = df.apply(src_pair_label, axis=1)
    cnt = df['pair'].value_counts()
    log(f"\n{label} source pairs:")
    for pair, c in cnt.items():
        log(f"  {pair}: {c} ({100*c/max(1,len(df)):.0f}%)")

# ---- severe: matched vs unmatched ----
log(f"\nSevere: matched status breakdown:")
for st in [(True, True), (True, False), (False, True), (False, False)]:
    sub = severe[(severe['mL'] == st[0]) & (severe['mR'] == st[1])]
    log(f"  mL={st[0]}, mR={st[1]}: {len(sub)} ({100*len(sub)/max(1,len(severe)):.0f}%)")

# ---- area stats for severe ----
if len(severe) > 0:
    log(f"\nSevere overlap area stats:")
    log(f"  overlap_m2: min={severe['ov_area_m2'].min():.1f}, p50={severe['ov_area_m2'].median():.1f}, mean={severe['ov_area_m2'].mean():.1f}, max={severe['ov_area_m2'].max():.1f}")
    sev_a = pd.concat([severe['aL'], severe['aR']])
    log(f"  building area: min={sev_a.min():.1f}, p25={np.percentile(sev_a,25):.1f}, p50={np.percentile(sev_a,50):.1f}, mean={sev_a.mean():.1f}, p95={np.percentile(sev_a,95):.1f}")

# ---- top worst cases ----
log(f"\nTop 20 worst overlaps:")
top = severe.nlargest(20, 'ov_area_m2')
for i, (_, row) in enumerate(top.iterrows()):
    lo = f_proj.iloc[int(row['L'])]
    ro = f_proj.iloc[int(row['R'])]
    log(f"  #{i+1}: ratio={row['ov_ratio']:.2f} overlap={row['ov_area_m2']:.0f}m2  "
        f"L={lo['source']}({lo['_area_m2']:.0f}m2)  R={ro['source']}({ro['_area_m2']:.0f}m2)")

# ---- save stats ----
summary = {
    "total_buildings": N,
    "total_pairs": int(P),
    "severe_pairs": int(len(severe)),
    "severe_buildings": int(uniq(severe)),
    "moderate_pairs": int(len(moderate)),
    "mild_pairs": int(len(mild)),
    "trivial_pairs": int(len(trivial)),
    "total_buildings_with_overlap": int(uniq(pairs)),
}
with open(OUT, 'w', encoding='utf-8') as fh:
    json.dump(summary, fh, indent=2, ensure_ascii=False)
log(f"\nSaved analysis to {OUT}")
log(f"Done. Total time: {time.time()-T0:.0f}s")
