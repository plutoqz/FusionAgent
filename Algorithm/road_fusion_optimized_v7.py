# -*- coding: utf-8 -*-
"""
道路融合优化版完整脚本
======================

用途
----
将 OSM 道路与 Microsoft 道路进行匹配、补全和保守去重，重点解决：
1. 运行速度慢；
2. 道路丢失；
3. 100 条道路与 1000000 条道路匹配时，因为逻辑写法导致的极慢问题。

与原始版本相比的关键变化
----------------------
1. 不再使用 FID_1 / osm_id 作为空间索引键。分割后这些字段可能重复，容易造成道路丢失。
2. 分割后重新生成唯一 osm_uid、msft_uid，同时保留 osm_old、original_FID_1 作为来源追踪字段。
3. 不在循环里执行 gdf[gdf['FID_1'] == fid] 这种全表扫描。
4. 不在循环里逐条 pd.concat，所有补充道路一次性合并。
5. 默认不做全局 planarize + linemerge，因为它会改变网络结构并造成属性回填困难，容易误删/漏保道路。
6. 只把 Microsoft 补充道路端点吸附到 OSM 主网络，不反向移动 OSM 主道路。
7. 重复删除采用覆盖率、方向角、中心线距离和长度关系的保守组合判断，避免把辅路、匝道、平行路误删。
8. 推荐输出 GeoPackage，避免 Shapefile 字段名截断和百万级数据 I/O 变慢。
9. V7 增加列裁剪读取、交集 bbox 预裁剪、匹配阶段廉价过滤前置、残段提取延迟构建 buffer、清理模式选择和预处理缓存。

依赖
----
pip install geopandas shapely pandas numpy pyogrio rtree

运行
----
直接修改 main() 里的三个路径，然后运行：
python road_fusion_optimized_v7.py

建议输出 .gpkg。如果必须输出 shp，也可以把 OUTPUT_PATH 改成 .shp。
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple, Union

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import GeometryCollection, LineString, MultiLineString, Point
from shapely.ops import substring, unary_union


# =============================================================================
# 参数配置
# =============================================================================

@dataclass
class RoadFusionConfig:
    # 研究区投影坐标系。你的原代码使用巴基斯坦 UTM 43N。
    target_crs: str = "EPSG:32643"

    # 是否按折角分割道路。建议开启，可以减少长线匹配造成的局部误判。
    do_split_by_angle: bool = True
    angle_threshold: float = 135.0

    # 是否按最大长度继续分割道路。这个主要解决长直线 buffer 过大导致候选集过多的问题。
    # 设为 0 或 None 表示不按长度分割。
    max_segment_length: Optional[float] = 800.0

    # 匹配参数
    match_buffer_dist: float = 20.0       # OSM 道路缓冲搜索半径，单位米
    max_hausdorff: float = 15.0          # 高置信匹配的 Hausdorff 距离阈值，单位米
    loose_angle_threshold: float = 45.0  # 宽松匹配方向差阈值，单位度
    min_len_similarity: float = 0.05     # 长度相似性下限，防止完全不相关的线进入匹配
    min_msft_coverage_for_matched: float = 0.80
    # 上面这个很重要：只有当微软线段有足够比例落入 OSM 缓冲区时，才认为它“已被 OSM 覆盖”。
    # 覆盖率不足的微软线段会整体作为补充道路保留。

    # 对已经判定为匹配的微软线段，是否继续保留其未被 OSM 缓冲区覆盖的残段。
    # 这一步用于解决“80% 重合、20% 是真实延伸段”时的漏保问题。
    preserve_matched_msft_residuals: bool = True
    min_residual_length: float = 10.0

    # 如果输入数据没有 CRS，默认直接报错，避免把经纬度数据误当投影坐标处理。
    # 临时测试时确实需要强制假定，可改为 True。
    assume_missing_crs_as_target: bool = False

    # 重复删除参数。为了避免道路丢失，默认偏保守。
    duplicate_buffer_dist: float = 10.0
    duplicate_coverage_threshold: float = 0.92
    duplicate_angle_threshold: float = 25.0
    duplicate_max_centerline_dist: float = 8.0

    # 组级重复删除参数。用于解决“单条 MSFT 被多条 OSM 分段共同覆盖，
    # 但没有被任意单条 OSM 覆盖充分，因此作为新增道路保留下来”的问题。
    # 这里比 duplicate_buffer_dist 更窄，目的是删除几何上几乎重合的重复线，
    # 同时尽量保留真实平行辅路、匝道和服务道路。
    enable_group_duplicate_removal: bool = True
    group_duplicate_buffer_dist: float = 6.0
    group_duplicate_coverage_threshold: float = 0.90
    group_duplicate_angle_threshold: float = 18.0
    group_duplicate_mean_distance: float = 4.0
    group_duplicate_p90_distance: float = 7.0
    duplicate_sample_step: float = 30.0

    # 近主网回接线清理参数。
    # 用于处理“MSFT 比 OSM 短/略偏移，从 OSM 中伸出一点又接回 OSM”的情况。
    # 只有当 ms_road 两端都靠近 OSM 主网络，且整条线大部分都贴着 OSM 走时才删除。
    # 如果研究目标需要保留双向分隔道路、辅路或服务道路，可将该开关设为 False，
    # 或适当降低 near_base_return_* 阈值。
    enable_near_base_return_pruning: bool = True
    near_base_return_endpoint_radius: float = 12.0
    near_base_return_corridor_dist: float = 12.0
    near_base_return_coverage_threshold: float = 0.85
    near_base_return_mean_distance: float = 6.0
    near_base_return_p90_distance: float = 10.0
    near_base_return_max_distance: float = 16.0
    near_base_return_sample_step: float = 30.0

    # 交叉错位重复线清理参数。
    # 用于处理“MSFT 与 OSM 主线大体同向、整体贴近，但局部轻微穿插/交叉”的情况。
    # 与真实路口不同，这类线通常大部分长度都处在 OSM corridor 内，并且与候选 OSM 线方向相近。
    enable_crossing_duplicate_pruning: bool = True
    crossing_corridor_dist: float = 12.0
    crossing_coverage_threshold: float = 0.82
    crossing_mean_distance: float = 6.0
    crossing_p90_distance: float = 10.0
    crossing_max_distance: float = 18.0
    crossing_angle_threshold: float = 22.0
    crossing_touch_tolerance: float = 1.0
    crossing_sample_step: float = 30.0

    # 端点吸附参数。只吸附 ms_road 到 OSM 主网络。
    endpoint_snap_radius: float = 10.0
    min_length_after_snap: float = 1.0
    max_endpoint_snap_bend_angle: float = 35.0

    # 悬挂短线清理参数。只删除很短、且明显没有接入网络的 ms_road，
    # 避免把真实死胡同、独立小路和新建道路误删。
    enable_dangle_cleanup: bool = True
    dangle_connect_radius: float = 10.0
    dangle_delete_two_free_max_length: float = 30.0
    dangle_delete_one_free_max_length: float = 12.0

    # 过滤极短线，避免异常几何影响计算。
    min_line_length: float = 0.05

    # 日志进度间隔
    log_every_n: int = 1000

    # 清理模式。
    # quality：保持 V6 的双轮高质量清理；
    # balanced：吸附前跑普通/组级/近主网/交叉，吸附后只跑普通/组级；
    # fast：吸附前只跑普通/组级，吸附后只跑近主网/交叉，适合全量速度优先。
    cleanup_mode: str = "quality"

    # 兼容旧参数：当 cleanup_mode 为空字符串时，才使用 run_second_clean_pass 控制。
    # 新代码建议优先使用 cleanup_mode。
    run_second_clean_pass: bool = True

    # 是否使用 pyogrio 读写。大数据量通常比默认 Fiona 更快；环境没有 pyogrio 时会自动回退。
    use_pyogrio_io: bool = True

    # 读取时是否只保留必要属性字段。大数据量下建议 True。
    read_only_needed_columns: bool = True
    osm_read_columns: Tuple[str, ...] = ("osm_id", "fclass")
    msft_read_columns: Tuple[str, ...] = ("FID_1",)

    # 读取前是否按两源 total_bounds 交集做 bbox 预裁剪。
    # 两套数据范围差异较大时可明显减少计算量；边界外扩用于避免提前截断边界道路。
    preclip_to_bounds_intersection: bool = False
    preclip_margin_degrees: float = 0.02

    # 是否缓存预处理后的分段结果。调试清理阈值时很有用。
    # 注意：如果修改 target_crs、分段阈值、输入 bbox，应重新生成缓存。
    use_prepared_cache: bool = False
    prepared_cache_dir: Optional[str] = None
    overwrite_prepared_cache: bool = False

    # 输出坐标系。None 表示保持 target_crs 输出；如果需要经纬度展示，可设为 "EPSG:4326"。
    output_crs: Optional[str] = None


CONFIG = RoadFusionConfig()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("road_fusion_optimized_v7")


# =============================================================================
# 基础几何函数
# =============================================================================

def calculate_angle(p1, p2, p3) -> float:
    """计算 p1-p2-p3 形成的夹角，单位为度。"""
    v1 = (p1[0] - p2[0], p1[1] - p2[1])
    v2 = (p3[0] - p2[0], p3[1] - p2[1])
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    m1 = math.hypot(v1[0], v1[1])
    m2 = math.hypot(v2[0], v2[1])
    if m1 == 0 or m2 == 0:
        return 180.0
    cos_theta = max(min(dot / (m1 * m2), 1.0), -1.0)
    return math.degrees(math.acos(cos_theta))


def line_angle(line: LineString) -> float:
    """用首尾点计算道路总体方向，返回 0~180 度。"""
    coords = list(line.coords)
    if len(coords) < 2:
        return 0.0
    dx = coords[-1][0] - coords[0][0]
    dy = coords[-1][1] - coords[0][1]
    return math.degrees(math.atan2(dy, dx)) % 180.0


def angle_diff(angle_a: float, angle_b: float) -> float:
    """计算两条无向线的方向差，范围 0~90 或 0~180 内的较小差值。"""
    d = abs(angle_a - angle_b) % 180.0
    return min(d, 180.0 - d)


def angle_between_points(p1, p2) -> float:
    """用两个点计算线段方向，返回 0~180 度。"""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    if dx == 0 and dy == 0:
        return 0.0
    return math.degrees(math.atan2(dy, dx)) % 180.0


def length_similarity(len_a: float, len_b: float) -> float:
    """长度相似性，取短/长。"""
    if len_a <= 0 or len_b <= 0:
        return 0.0
    return min(len_a, len_b) / max(len_a, len_b)


def bounds_around_point(point: Point, radius: float) -> Tuple[float, float, float, float]:
    return (point.x - radius, point.y - radius, point.x + radius, point.y + radius)


def expanded_bounds(bounds: Tuple[float, float, float, float], radius: float) -> Tuple[float, float, float, float]:
    """将几何 bounds 向四周扩展 radius，用于空间索引查询，避免仅为取 bounds 反复创建 buffer。"""
    minx, miny, maxx, maxy = bounds
    return (minx - radius, miny - radius, maxx + radius, maxy + radius)


def split_line_by_sharp_turns(line: LineString, cfg: RoadFusionConfig) -> List[LineString]:
    """
    按已有折点分割 LineString。

    原代码使用 shapely.ops.split 反复切割，比较慢。这里直接按坐标索引切片，速度更快，
    也不会因为切割点精度问题导致 split 失败。
    """
    coords = list(line.coords)
    if len(coords) <= 2:
        return [line] if line.length > cfg.min_line_length else []

    cut_indices = [0]
    for i in range(1, len(coords) - 1):
        if calculate_angle(coords[i - 1], coords[i], coords[i + 1]) < cfg.angle_threshold:
            cut_indices.append(i)
    cut_indices.append(len(coords) - 1)

    parts: List[LineString] = []
    for start, end in zip(cut_indices[:-1], cut_indices[1:]):
        if end <= start:
            continue
        part = LineString(coords[start:end + 1])
        if not part.is_empty and part.length > cfg.min_line_length:
            parts.append(part)
    return parts


def split_line_by_max_length(line: LineString, cfg: RoadFusionConfig) -> List[LineString]:
    """
    将过长 LineString 按最大长度继续切分。

    只按折角分割时，长直线不会被切开，空间索引候选范围仍可能很大。
    这里按线性参考距离切分，不改变线的整体走向，只减少单段长度。
    """
    max_len = cfg.max_segment_length
    if max_len is None or max_len <= 0 or line.length <= max_len:
        return [line] if line.length > cfg.min_line_length else []

    parts: List[LineString] = []
    start = 0.0
    total = float(line.length)
    while start < total:
        end = min(start + float(max_len), total)
        try:
            part = substring(line, start, end)
        except Exception:
            # substring 极少数情况下可能失败，失败时保留原线，避免道路丢失。
            return [line] if line.length > cfg.min_line_length else []

        if isinstance(part, LineString) and (not part.is_empty) and part.length > cfg.min_line_length:
            parts.append(part)
        start = end

    return parts


def split_line_by_angle_and_length(line: LineString, cfg: RoadFusionConfig) -> List[LineString]:
    """先按折角分割，再按最大长度分割。"""
    if cfg.do_split_by_angle:
        angle_parts = split_line_by_sharp_turns(line, cfg)
    else:
        angle_parts = [line] if line.length > cfg.min_line_length else []

    final_parts: List[LineString] = []
    for part in angle_parts:
        final_parts.extend(split_line_by_max_length(part, cfg))
    return final_parts


def extract_line_parts(geom, min_length: float) -> List[LineString]:
    """从 difference 结果中提取有效线段。"""
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [geom] if geom.length > min_length else []
    if isinstance(geom, MultiLineString):
        return [g for g in geom.geoms if isinstance(g, LineString) and g.length > min_length]
    if isinstance(geom, GeometryCollection):
        parts: List[LineString] = []
        for g in geom.geoms:
            parts.extend(extract_line_parts(g, min_length))
        return parts
    return []


# =============================================================================
# 数据读取与预处理
# =============================================================================

def ensure_projected(gdf: gpd.GeoDataFrame, cfg: RoadFusionConfig, name: str) -> gpd.GeoDataFrame:
    """确保数据处于投影坐标系。缓冲、长度、距离都必须在米制投影下做。"""
    if gdf.crs is None:
        if not cfg.assume_missing_crs_as_target:
            raise ValueError(
                f"{name} 没有 CRS。请先确认原始数据坐标系，"
                f"不要直接把未知 CRS 当作 {cfg.target_crs} 处理。"
            )
        logger.warning("%s 没有 CRS，已按 %s 强制设置。正式实验前请确认原始数据坐标系。", name, cfg.target_crs)
        gdf = gdf.set_crs(cfg.target_crs)
    elif str(gdf.crs) != cfg.target_crs:
        gdf = gdf.to_crs(cfg.target_crs)

    # 如果仍然是地理坐标系，直接报错，避免拿经纬度做米制缓冲。
    if gdf.crs is not None and gdf.crs.is_geographic:
        raise ValueError(f"{name} 当前为地理坐标系 {gdf.crs}，不能直接做米制缓冲，请设置正确的投影坐标系。")
    return gdf


def explode_to_lines(gdf: gpd.GeoDataFrame, cfg: RoadFusionConfig) -> gpd.GeoDataFrame:
    """将 MultiLineString 拆为 LineString，并删除空几何、非线几何和极短线。"""
    gdf = gdf.copy()
    gdf = gdf[gdf.geometry.notna() & (~gdf.geometry.is_empty)].copy()
    if gdf.empty:
        return gdf

    gdf = gdf.explode(index_parts=False, ignore_index=True)
    gdf = gdf[gdf.geometry.geom_type == "LineString"].copy()
    gdf = gdf[gdf.geometry.length > cfg.min_line_length].copy()
    return gdf.reset_index(drop=True)


def split_gdf_by_angle(gdf: gpd.GeoDataFrame, cfg: RoadFusionConfig) -> gpd.GeoDataFrame:
    """按折角和最大长度分割道路，并保留原属性。"""

    cols = list(gdf.columns)
    geom_col = gdf.geometry.name
    geom_idx = cols.index(geom_col)

    rows: List[dict] = []
    for values in gdf.itertuples(index=False, name=None):
        record = dict(zip(cols, values))
        geom = values[geom_idx]
        if not isinstance(geom, LineString):
            continue
        parts = split_line_by_angle_and_length(geom, cfg)
        for part in parts:
            new_record = record.copy()
            new_record[geom_col] = part
            rows.append(new_record)

    if not rows:
        return gpd.GeoDataFrame(columns=gdf.columns, geometry=geom_col, crs=gdf.crs)
    return gpd.GeoDataFrame(rows, geometry=geom_col, crs=gdf.crs).reset_index(drop=True)


def prepare_osm(gdf_osm: gpd.GeoDataFrame, cfg: RoadFusionConfig) -> gpd.GeoDataFrame:
    """预处理 OSM 道路。"""
    osm = ensure_projected(gdf_osm, cfg, "OSM")
    osm = explode_to_lines(osm, cfg)

    # 保留原始 OSM ID，但分割后的 osm_id 必须重新唯一化。
    if "osm_id" in osm.columns:
        osm["osm_old"] = osm["osm_id"]
    else:
        osm["osm_old"] = pd.NA

    osm = split_gdf_by_angle(osm, cfg)
    osm = osm.reset_index(drop=True)
    osm["osm_uid"] = np.arange(1, len(osm) + 1, dtype=np.int64)
    osm["osm_id"] = osm["osm_uid"]

    # 如果原始 OSM 有 fclass，则保留原值；如果没有，则补一个标识。
    if "fclass" not in osm.columns:
        osm["fclass"] = "osm_road"
    else:
        osm["fclass"] = osm["fclass"].fillna("osm_road")

    osm["source_layer"] = "osm"
    return osm


def prepare_msft(gdf_msft: gpd.GeoDataFrame, cfg: RoadFusionConfig) -> gpd.GeoDataFrame:
    """预处理 Microsoft 道路。"""
    ms = ensure_projected(gdf_msft, cfg, "MSFT")
    ms = explode_to_lines(ms, cfg)

    # 保留原始 FID_1，但分割后的 FID_1 必须重新唯一化。
    if "FID_1" in ms.columns:
        ms["original_FID_1"] = ms["FID_1"]
    else:
        ms["original_FID_1"] = np.arange(1, len(ms) + 1, dtype=np.int64)

    ms = split_gdf_by_angle(ms, cfg)
    ms = ms.reset_index(drop=True)
    ms["msft_uid"] = np.arange(1, len(ms) + 1, dtype=np.int64)
    ms["FID_1"] = ms["msft_uid"]
    ms["source_layer"] = "msft"
    return ms


# =============================================================================
# 匹配与融合
# =============================================================================

def msft_coverage_in_osm_buffer(ms_line: LineString, osm_buffer) -> float:
    """计算微软线段被 OSM 缓冲区覆盖的长度比例。"""
    if ms_line.length <= 0 or not ms_line.intersects(osm_buffer):
        return 0.0
    try:
        covered_len = ms_line.intersection(osm_buffer).length
    except Exception:
        return 0.0
    return covered_len / max(ms_line.length, 1e-9)


def build_residual_msft_segments(
    ms: gpd.GeoDataFrame,
    osm: gpd.GeoDataFrame,
    matched_ms_osm_pos: Dict[int, List[int]],
    cfg: RoadFusionConfig,
) -> gpd.GeoDataFrame:
    """
    对已经匹配的 Microsoft 道路，提取未被 OSM 缓冲区覆盖的残段。

    这样可以避免“整条 MSFT 线段 80% 重合、20% 是真实新增延伸段”时，
    因为整线被标为 matched 而漏掉新增残段。
    """
    if not cfg.preserve_matched_msft_residuals or not matched_ms_osm_pos:
        return gpd.GeoDataFrame(columns=ms.columns, geometry=ms.geometry.name, crs=ms.crs)

    geom_col = ms.geometry.name
    records: List[dict] = []
    osm_geoms = osm.geometry.to_numpy()

    for mi, osm_positions in matched_ms_osm_pos.items():
        ms_line = ms.geometry.iloc[mi]
        if not isinstance(ms_line, LineString) or ms_line.is_empty or ms_line.length <= cfg.min_line_length:
            continue

        try:
            # V7 不在匹配阶段保存大量 Polygon buffer 对象，而是只保存 OSM 行号。
            # 这里真正需要提取残段时，才延迟构建相关 OSM buffer，降低全量运行的内存压力。
            buffers = []
            for oi in sorted(set(osm_positions)):
                if 0 <= oi < len(osm_geoms):
                    base_line = osm_geoms[oi]
                    if base_line is not None and not base_line.is_empty:
                        buffers.append(base_line.buffer(cfg.match_buffer_dist))
            if not buffers:
                continue
            cover_geom = unary_union(buffers) if len(buffers) > 1 else buffers[0]
            residual_geom = ms_line.difference(cover_geom)
        except Exception:
            continue

        parts = extract_line_parts(residual_geom, cfg.min_residual_length)
        if not parts:
            continue

        for part_no, part in enumerate(parts, start=1):
            rec = ms.iloc[mi].to_dict()
            rec[geom_col] = part
            rec["residual_from_matched"] = True
            rec["residual_part"] = part_no
            rec["residual_parent_FID_1"] = rec.get("FID_1", pd.NA)
            records.append(rec)

    if not records:
        return gpd.GeoDataFrame(columns=ms.columns, geometry=geom_col, crs=ms.crs)

    return gpd.GeoDataFrame(records, geometry=geom_col, crs=ms.crs).reset_index(drop=True)


def match_and_fuse_fast(
    osm: gpd.GeoDataFrame,
    ms: gpd.GeoDataFrame,
    cfg: RoadFusionConfig
) -> Tuple[gpd.GeoDataFrame, Dict[str, int]]:
    """
    快速匹配并融合 OSM 与 Microsoft 道路。

    关键点：
    - 空间索引返回的是行位置，不是 FID_1。
    - 不再用 gdf[gdf['FID_1']==fid] 反复全表查询。
    - 覆盖率不足的 MSFT 线段整体保留为补充道路。
    - 覆盖率达到阈值而被判定为匹配的 MSFT 线段，也会继续提取未覆盖残段。
      这样能减少“部分重合、部分新增”的道路漏保。
    """
    if osm.crs != ms.crs:
        ms = ms.to_crs(osm.crs)

    osm = osm.copy().reset_index(drop=True)
    ms = ms.copy().reset_index(drop=True)

    ms_sindex = ms.sindex
    ms_geoms = ms.geometry.to_numpy()
    ms_lengths = ms.geometry.length.to_numpy()
    ms_angles = np.array([line_angle(g) for g in ms_geoms], dtype=float)
    ms_ids = ms["FID_1"].astype(str).to_numpy() if "FID_1" in ms.columns else np.arange(len(ms)).astype(str)

    osm_geoms = osm.geometry.to_numpy()
    label1: List[List[str]] = [[] for _ in range(len(osm))]  # 高置信匹配
    label2: List[List[str]] = [[] for _ in range(len(osm))]  # 宽松匹配
    matched_ms_pos: Set[int] = set()
    matched_ms_osm_pos: Dict[int, List[int]] = {}

    t0 = time.time()
    for oi, osm_line in enumerate(osm_geoms):
        if osm_line is None or osm_line.is_empty or osm_line.length <= cfg.min_line_length:
            continue

        candidate_pos = list(ms_sindex.intersection(expanded_bounds(osm_line.bounds, cfg.match_buffer_dist)))
        if not candidate_pos:
            continue

        osm_len = osm_line.length
        osm_ang = line_angle(osm_line)
        osm_buffer = None

        for mi in candidate_pos:
            ms_line = ms_geoms[mi]
            if ms_line is None or ms_line.is_empty or ms_lengths[mi] <= cfg.min_line_length:
                continue

            # V7：把方向差和长度相似性这类廉价过滤提前。
            # 城市密集区 bbox 候选里大量是交叉路、垂直路，先过滤能少做很多 intersects/intersection。
            a_diff = angle_diff(osm_ang, ms_angles[mi])
            if a_diff > cfg.loose_angle_threshold:
                continue
            len_sim = length_similarity(osm_len, ms_lengths[mi])
            if len_sim < cfg.min_len_similarity:
                continue

            if osm_buffer is None:
                osm_buffer = osm_line.buffer(cfg.match_buffer_dist)
            if not ms_line.intersects(osm_buffer):
                continue

            # 覆盖率用于判断整条 MSFT 是否可以视为被 OSM 覆盖。
            # 覆盖率不足时，不加入 matched_ms_pos，后面会整体作为补充道路保留。
            coverage = msft_coverage_in_osm_buffer(ms_line, osm_buffer)
            if coverage < cfg.min_msft_coverage_for_matched:
                continue

            hd = osm_line.hausdorff_distance(ms_line)
            if hd <= cfg.max_hausdorff:
                label1[oi].append(ms_ids[mi])
                matched_ms_pos.add(mi)
                matched_ms_osm_pos.setdefault(mi, []).append(oi)
            else:
                # 宽松匹配：方向、长度、覆盖率都满足，但 Hausdorff 稍大。
                label2[oi].append(ms_ids[mi])
                matched_ms_pos.add(mi)
                matched_ms_osm_pos.setdefault(mi, []).append(oi)

        if cfg.log_every_n > 0 and (oi + 1) % cfg.log_every_n == 0:
            logger.info(
                "匹配进度 OSM %s/%s，已匹配 MSFT 片段 %s，耗时 %.1fs",
                oi + 1, len(osm), len(matched_ms_pos), time.time() - t0
            )

    osm["label1"] = [",".join(v) for v in label1]
    osm["label2"] = [",".join(v) for v in label2]
    osm["label3"] = ""

    unmatched_mask = np.ones(len(ms), dtype=bool)
    if matched_ms_pos:
        unmatched_mask[list(matched_ms_pos)] = False
    unmatched_ms = ms.loc[unmatched_mask].copy()
    unmatched_ms["residual_from_matched"] = False
    unmatched_ms["residual_part"] = pd.NA
    unmatched_ms["residual_parent_FID_1"] = pd.NA

    residual_ms = build_residual_msft_segments(ms, osm, matched_ms_osm_pos, cfg)

    supplement_frames = []
    if len(unmatched_ms) > 0:
        supplement_frames.append(unmatched_ms)
    if len(residual_ms) > 0:
        supplement_frames.append(residual_ms)

    if supplement_frames:
        supplements = pd.concat(supplement_frames, ignore_index=True)
        supplements = gpd.GeoDataFrame(supplements, geometry=ms.geometry.name, crs=ms.crs)

        supplements["osm_id"] = pd.NA
        supplements["osm_uid"] = pd.NA
        supplements["label1"] = ""
        supplements["label2"] = ""
        supplements["label3"] = supplements["FID_1"].astype(str)

        if "residual_from_matched" in supplements.columns:
            residual_mask = supplements["residual_from_matched"].fillna(False).astype(bool)
            supplements.loc[residual_mask, "label3"] = (
                supplements.loc[residual_mask, "FID_1"].astype(str)
                + "_res"
                + supplements.loc[residual_mask, "residual_part"].fillna(1).astype(int).astype(str)
            )

        supplements["fclass"] = "ms_road"

        # 对齐字段，一次性合并，避免循环里 pd.concat。
        all_cols = list(dict.fromkeys(list(osm.columns) + list(supplements.columns)))
        for col in all_cols:
            if col not in osm.columns:
                osm[col] = pd.NA
            if col not in supplements.columns:
                supplements[col] = pd.NA
        fused = pd.concat([osm[all_cols], supplements[all_cols]], ignore_index=True)
        fused = gpd.GeoDataFrame(fused, geometry=osm.geometry.name, crs=osm.crs)
    else:
        fused = osm

    stats = {
        "osm_segments": int(len(osm)),
        "msft_segments": int(len(ms)),
        "matched_msft_segments": int(len(matched_ms_pos)),
        "unmatched_msft_segments": int(len(unmatched_ms)),
        "residual_msft_segments": int(len(residual_ms)),
        "supplemented_msft_segments": int(len(unmatched_ms) + len(residual_ms)),
        "residual_msft_total_length": float(residual_ms.geometry.length.sum()) if len(residual_ms) > 0 else 0.0,
        "fused_before_duplicate_removal": int(len(fused)),
    }
    return fused, stats

# =============================================================================
# 保守重复删除
# =============================================================================

def is_duplicate_supplement(
    base_geom: LineString,
    sup_geom: LineString,
    base_angle: float,
    sup_angle: float,
    cfg: RoadFusionConfig,
    coverage_threshold: Optional[float] = None,
    max_centerline_dist: Optional[float] = None,
) -> bool:
    """判断一条 Microsoft 补充道路是否是 OSM 主道路的重复。"""
    if sup_geom.length <= cfg.min_line_length or base_geom.length <= cfg.min_line_length:
        return False

    if angle_diff(base_angle, sup_angle) > cfg.duplicate_angle_threshold:
        return False

    dist_threshold = cfg.duplicate_max_centerline_dist if max_centerline_dist is None else max_centerline_dist
    if sup_geom.distance(base_geom) > dist_threshold:
        return False

    threshold = cfg.duplicate_coverage_threshold if coverage_threshold is None else coverage_threshold
    base_buffer = base_geom.buffer(cfg.duplicate_buffer_dist)
    if not sup_geom.intersects(base_buffer):
        return False

    try:
        covered_len = sup_geom.intersection(base_buffer).length
    except Exception:
        return False

    coverage = covered_len / max(sup_geom.length, 1e-9)
    if coverage < threshold:
        return False

    # 避免长的 MSFT 补充道路因局部覆盖被删除。
    # 如果 sup 比 base 长很多，只有覆盖率接近完整才删除。
    if sup_geom.length <= base_geom.length * 1.5 or coverage >= 0.98:
        return True
    return False


def remove_duplicate_ms_roads_fast(
    fused: gpd.GeoDataFrame,
    cfg: RoadFusionConfig,
    coverage_threshold: Optional[float] = None,
    max_centerline_dist: Optional[float] = None,
) -> Tuple[gpd.GeoDataFrame, int]:
    """
    快速、保守删除 ms_road 重复道路。

    为解决 100 条道路 vs 1000000 条道路这种规模问题：
    - 如果 OSM 主道路少、MSFT 补充道路多，就索引 MSFT，循环 OSM；
    - 如果 MSFT 补充道路少，就索引 OSM，循环 MSFT。
    """
    if "fclass" not in fused.columns:
        return fused, 0

    gdf = fused.copy().reset_index(drop=True)
    base = gdf[gdf["fclass"] != "ms_road"].copy()
    sup = gdf[gdf["fclass"] == "ms_road"].copy()

    if base.empty or sup.empty:
        return gdf, 0

    base = base[base.geometry.notna() & (~base.geometry.is_empty) & (base.geometry.geom_type == "LineString")].copy()
    sup = sup[sup.geometry.notna() & (~sup.geometry.is_empty) & (sup.geometry.geom_type == "LineString")].copy()
    if base.empty or sup.empty:
        return gdf, 0

    delete_indices: Set[int] = set()

    if len(base) <= len(sup):
        # 大数据场景常见：base 100，sup 1000000。索引大表，循环小表。
        sup_sindex = sup.sindex
        sup_geoms = sup.geometry.to_numpy()
        sup_angles = np.array([line_angle(g) for g in sup_geoms], dtype=float)
        sup_global_idx = sup.index.to_numpy()

        for bi, base_row in enumerate(base.itertuples()):
            base_geom = base_row.geometry
            if base_geom is None or base_geom.is_empty:
                continue
            base_ang = line_angle(base_geom)
            search_bounds = expanded_bounds(base_geom.bounds, cfg.duplicate_buffer_dist)
            candidate_sup_pos = list(sup_sindex.intersection(search_bounds))

            for sp in candidate_sup_pos:
                global_idx = int(sup_global_idx[sp])
                if global_idx in delete_indices:
                    continue
                sup_geom = sup_geoms[sp]
                if is_duplicate_supplement(
                    base_geom, sup_geom, base_ang, sup_angles[sp], cfg,
                    coverage_threshold=coverage_threshold,
                    max_centerline_dist=max_centerline_dist,
                ):
                    delete_indices.add(global_idx)

            if cfg.log_every_n > 0 and (bi + 1) % cfg.log_every_n == 0:
                logger.info("重复检查进度 base %s/%s，待删除 %s", bi + 1, len(base), len(delete_indices))
    else:
        # 反向场景：sup 较少，循环 sup 更快。
        base_sindex = base.sindex
        base_geoms = base.geometry.to_numpy()
        base_angles = np.array([line_angle(g) for g in base_geoms], dtype=float)

        for sup_row in sup.itertuples():
            sup_geom = sup_row.geometry
            if sup_geom is None or sup_geom.is_empty:
                continue
            sup_ang = line_angle(sup_geom)
            candidate_base_pos = list(base_sindex.intersection(expanded_bounds(sup_geom.bounds, cfg.duplicate_buffer_dist)))

            for bp in candidate_base_pos:
                base_geom = base_geoms[bp]
                if is_duplicate_supplement(
                    base_geom, sup_geom, base_angles[bp], sup_ang, cfg,
                    coverage_threshold=coverage_threshold,
                    max_centerline_dist=max_centerline_dist,
                ):
                    delete_indices.add(int(sup_row.Index))
                    break

    if not delete_indices:
        return gdf, 0

    cleaned = gdf.drop(index=sorted(delete_indices)).reset_index(drop=True)
    return gpd.GeoDataFrame(cleaned, geometry=gdf.geometry.name, crs=gdf.crs), len(delete_indices)



# =============================================================================
# 组级重复删除：解决“几乎重合道路仍被作为新增道路加入”的问题
# =============================================================================

def sampled_distance_stats_to_geoms(
    line: LineString,
    candidate_geoms: Sequence[LineString],
    sample_step: float,
) -> Tuple[float, float]:
    """沿补充道路采样，统计采样点到候选主道路集合的平均距离和 90 分位距离。"""
    if not candidate_geoms or line.length <= 0:
        return float("inf"), float("inf")

    step = max(float(sample_step), 1.0)
    n = max(int(math.ceil(line.length / step)) + 1, 3)
    distances = np.linspace(0.0, float(line.length), n)
    sampled_dists: List[float] = []

    for d in distances:
        p = line.interpolate(float(d))
        best = min(p.distance(g) for g in candidate_geoms if g is not None and not g.is_empty)
        sampled_dists.append(float(best))

    if not sampled_dists:
        return float("inf"), float("inf")

    arr = np.asarray(sampled_dists, dtype=float)
    return float(arr.mean()), float(np.percentile(arr, 90))


def is_duplicate_against_base_group(
    sup_geom: LineString,
    candidate_base_geoms: Sequence[LineString],
    cfg: RoadFusionConfig,
    coverage_threshold: Optional[float] = None,
    mean_distance_threshold: Optional[float] = None,
    p90_distance_threshold: Optional[float] = None,
) -> bool:
    """
    判断一条 ms_road 是否被附近多条 OSM 主道路共同覆盖。

    单条道路比较只能处理“一个 MSFT 对一个 OSM”的重复；
    如果 OSM 被切成多段，而 MSFT 分段边界不同，就会出现看起来完全重合，
    但没有被任意一条 OSM 单独删除的情况。这里用候选 OSM 的缓冲区并集来判断。
    """
    if sup_geom is None or sup_geom.is_empty or sup_geom.length <= cfg.min_line_length:
        return False
    if not candidate_base_geoms:
        return False

    sup_ang = line_angle(sup_geom)
    angle_threshold = cfg.group_duplicate_angle_threshold
    directional_geoms: List[LineString] = []

    for g in candidate_base_geoms:
        if g is None or g.is_empty or g.length <= cfg.min_line_length:
            continue
        if angle_diff(sup_ang, line_angle(g)) <= angle_threshold:
            directional_geoms.append(g)

    if not directional_geoms:
        return False

    buf_dist = cfg.group_duplicate_buffer_dist
    threshold = cfg.group_duplicate_coverage_threshold if coverage_threshold is None else coverage_threshold
    mean_th = cfg.group_duplicate_mean_distance if mean_distance_threshold is None else mean_distance_threshold
    p90_th = cfg.group_duplicate_p90_distance if p90_distance_threshold is None else p90_distance_threshold

    try:
        cover_geom = unary_union([g.buffer(buf_dist) for g in directional_geoms])
        covered_len = sup_geom.intersection(cover_geom).length
    except Exception:
        return False

    coverage = covered_len / max(sup_geom.length, 1e-9)
    if coverage < threshold:
        return False

    mean_dist, p90_dist = sampled_distance_stats_to_geoms(
        sup_geom, directional_geoms, cfg.duplicate_sample_step
    )

    # coverage 负责判断“长度上基本被覆盖”，距离统计负责避免误删平行辅路。
    if mean_dist <= mean_th and p90_dist <= p90_th:
        return True
    return False


def remove_duplicate_ms_roads_group_fast(
    fused: gpd.GeoDataFrame,
    cfg: RoadFusionConfig,
    coverage_threshold: Optional[float] = None,
    mean_distance_threshold: Optional[float] = None,
    p90_distance_threshold: Optional[float] = None,
) -> Tuple[gpd.GeoDataFrame, int]:
    """基于 OSM 候选组的重复删除，专门清理“看起来已匹配却又作为新增加入”的 ms_road。"""
    if not cfg.enable_group_duplicate_removal or "fclass" not in fused.columns:
        return fused, 0

    gdf = fused.copy().reset_index(drop=True)
    base = gdf[gdf["fclass"] != "ms_road"].copy()
    sup = gdf[gdf["fclass"] == "ms_road"].copy()

    if base.empty or sup.empty:
        return gdf, 0

    base = base[base.geometry.notna() & (~base.geometry.is_empty) & (base.geometry.geom_type == "LineString")].copy()
    sup = sup[sup.geometry.notna() & (~sup.geometry.is_empty) & (sup.geometry.geom_type == "LineString")].copy()
    if base.empty or sup.empty:
        return gdf, 0

    base_sindex = base.sindex
    base_geoms = base.geometry.to_numpy()
    base_angles = np.array([line_angle(g) for g in base_geoms], dtype=float)
    delete_indices: Set[int] = set()

    search_dist = max(cfg.group_duplicate_buffer_dist, cfg.group_duplicate_p90_distance)
    angle_threshold = cfg.group_duplicate_angle_threshold

    for row_no, sup_row in enumerate(sup.itertuples(), start=1):
        sup_geom = sup_row.geometry
        if sup_geom is None or sup_geom.is_empty or sup_geom.length <= cfg.min_line_length:
            continue

        candidate_pos = list(base_sindex.intersection(expanded_bounds(sup_geom.bounds, search_dist)))
        if not candidate_pos:
            continue

        sup_ang = line_angle(sup_geom)
        directional_pos = [pos for pos in candidate_pos if angle_diff(sup_ang, base_angles[pos]) <= angle_threshold]
        if not directional_pos:
            continue

        candidate_geoms = [base_geoms[pos] for pos in directional_pos]
        if is_duplicate_against_base_group(
            sup_geom,
            candidate_geoms,
            cfg,
            coverage_threshold=coverage_threshold,
            mean_distance_threshold=mean_distance_threshold,
            p90_distance_threshold=p90_distance_threshold,
        ):
            delete_indices.add(int(sup_row.Index))

        if cfg.log_every_n > 0 and row_no % cfg.log_every_n == 0:
            logger.info("组级重复检查进度 ms_road %s/%s，待删除 %s", row_no, len(sup), len(delete_indices))

    if not delete_indices:
        return gdf, 0

    cleaned = gdf.drop(index=sorted(delete_indices)).reset_index(drop=True)
    return gpd.GeoDataFrame(cleaned, geometry=gdf.geometry.name, crs=gdf.crs), len(delete_indices)


# =============================================================================
# 近主网回接线清理：处理“从 OSM 伸出一点、略有偏移、又接回 OSM”的 MSFT 残留线
# =============================================================================

def point_distance_to_base(
    point: Point,
    base_geoms: Sequence[LineString],
    base_sindex,
    radius: float,
) -> float:
    """计算端点到附近 OSM 主道路的最小距离。若半径内没有候选，返回 inf。"""
    candidate_pos = list(base_sindex.intersection(bounds_around_point(point, radius)))
    if not candidate_pos:
        return float("inf")

    best = float("inf")
    for pos in candidate_pos:
        geom = base_geoms[pos]
        if geom is None or geom.is_empty:
            continue
        dist = point.distance(geom)
        if dist < best:
            best = float(dist)
    return best


def sampled_distance_profile_to_geoms(
    line: LineString,
    candidate_geoms: Sequence[LineString],
    sample_step: float,
) -> Tuple[float, float, float]:
    """沿线采样，返回采样点到候选主道路集合的平均距离、90 分位距离和最大距离。"""
    valid_geoms = [g for g in candidate_geoms if g is not None and not g.is_empty]
    if not valid_geoms or line.length <= 0:
        return float("inf"), float("inf"), float("inf")

    step = max(float(sample_step), 1.0)
    n = max(int(math.ceil(line.length / step)) + 1, 3)
    distances = np.linspace(0.0, float(line.length), n)
    sampled_dists: List[float] = []

    for d in distances:
        p = line.interpolate(float(d))
        best = min(p.distance(g) for g in valid_geoms)
        sampled_dists.append(float(best))

    if not sampled_dists:
        return float("inf"), float("inf"), float("inf")

    arr = np.asarray(sampled_dists, dtype=float)
    return float(arr.mean()), float(np.percentile(arr, 90)), float(arr.max())


def line_coverage_by_base_corridor(
    line: LineString,
    candidate_geoms: Sequence[LineString],
    corridor_dist: float,
) -> float:
    """计算线段落入附近 OSM 主道路 corridor 缓冲区的长度比例。"""
    valid_geoms = [g for g in candidate_geoms if g is not None and not g.is_empty]
    if not valid_geoms or line.length <= 0:
        return 0.0
    try:
        cover_geom = unary_union([g.buffer(corridor_dist) for g in valid_geoms])
        covered_len = line.intersection(cover_geom).length
    except Exception:
        return 0.0
    return float(covered_len / max(line.length, 1e-9))


def prune_near_base_return_ms_roads(
    fused: gpd.GeoDataFrame,
    cfg: RoadFusionConfig,
    coverage_threshold: Optional[float] = None,
    mean_distance_threshold: Optional[float] = None,
    p90_distance_threshold: Optional[float] = None,
    max_distance_threshold: Optional[float] = None,
) -> Tuple[gpd.GeoDataFrame, int]:
    """
    删除“近主网回接型” MSFT 补充线。

    这类线通常表现为：
    - 起点和终点都靠近 OSM 主道路；
    - 中间略微偏出 OSM，但整体仍贴着 OSM 主道路走；
    - 宏观看是 MSFT 对 OSM 的偏移表达、简化表达或短段错位，不是真正新增道路。

    该模块只删除 fclass == 'ms_road' 的对象，不移动 OSM 主道路。
    为避免误删真实新增支路，必须同时满足“两端回接 + 高 corridor 覆盖 + 采样距离较小”。
    """
    if not cfg.enable_near_base_return_pruning or "fclass" not in fused.columns:
        return fused, 0

    gdf = fused.copy().reset_index(drop=True)
    base = gdf[gdf["fclass"] != "ms_road"].copy()
    sup = gdf[gdf["fclass"] == "ms_road"].copy()

    if base.empty or sup.empty:
        return gdf, 0

    base = base[base.geometry.notna() & (~base.geometry.is_empty) & (base.geometry.geom_type == "LineString")].copy()
    sup = sup[sup.geometry.notna() & (~sup.geometry.is_empty) & (sup.geometry.geom_type == "LineString")].copy()
    if base.empty or sup.empty:
        return gdf, 0

    endpoint_radius = cfg.near_base_return_endpoint_radius
    corridor_dist = cfg.near_base_return_corridor_dist
    coverage_th = cfg.near_base_return_coverage_threshold if coverage_threshold is None else coverage_threshold
    mean_th = cfg.near_base_return_mean_distance if mean_distance_threshold is None else mean_distance_threshold
    p90_th = cfg.near_base_return_p90_distance if p90_distance_threshold is None else p90_distance_threshold
    max_th = cfg.near_base_return_max_distance if max_distance_threshold is None else max_distance_threshold
    sample_step = cfg.near_base_return_sample_step

    base_sindex = base.sindex
    base_geoms = base.geometry.to_numpy()
    delete_indices: Set[int] = set()

    # search_dist 要覆盖 corridor 和采样最大距离阈值，否则候选主道路可能取不全。
    search_dist = max(endpoint_radius, corridor_dist, max_th)

    for row_no, sup_row in enumerate(sup.itertuples(), start=1):
        line = sup_row.geometry
        if not isinstance(line, LineString) or line.is_empty or line.length <= cfg.min_line_length:
            continue

        coords = list(line.coords)
        if len(coords) < 2:
            continue
        start = Point(coords[0])
        end = Point(coords[-1])

        start_dist = point_distance_to_base(start, base_geoms, base_sindex, endpoint_radius)
        end_dist = point_distance_to_base(end, base_geoms, base_sindex, endpoint_radius)
        if start_dist > endpoint_radius or end_dist > endpoint_radius:
            # 只有两端都回接 OSM 主网络时，才按“近主网回接线”删除。
            # 这样可以保护一端悬挂的真实新增支路和死胡同。
            continue

        candidate_pos = list(base_sindex.intersection(expanded_bounds(line.bounds, search_dist)))
        if not candidate_pos:
            continue
        candidate_geoms = [base_geoms[pos] for pos in candidate_pos]

        coverage = line_coverage_by_base_corridor(line, candidate_geoms, corridor_dist)
        if coverage < coverage_th:
            continue

        mean_dist, p90_dist, max_dist = sampled_distance_profile_to_geoms(
            line, candidate_geoms, sample_step
        )

        if mean_dist <= mean_th and p90_dist <= p90_th and max_dist <= max_th:
            delete_indices.add(int(sup_row.Index))

        if cfg.log_every_n > 0 and row_no % cfg.log_every_n == 0:
            logger.info(
                "近主网回接线检查进度 ms_road %s/%s，待删除 %s",
                row_no, len(sup), len(delete_indices)
            )

    if not delete_indices:
        return gdf, 0

    cleaned = gdf.drop(index=sorted(delete_indices)).reset_index(drop=True)
    return gpd.GeoDataFrame(cleaned, geometry=gdf.geometry.name, crs=gdf.crs), len(delete_indices)



# =============================================================================
# 交叉错位重复线清理：处理局部穿插/轻微交叉的近重复 ms_road
# =============================================================================

def line_has_parallel_contact_or_crossing(
    line: LineString,
    candidate_geoms: Sequence[LineString],
    sup_angle: float,
    angle_threshold: float,
    touch_tolerance: float,
) -> bool:
    """
    判断 ms_road 是否与方向相近的 OSM 主线存在接触、穿插或极近距离交会。

    这里不把所有交叉都当成重复。只有当候选 OSM 与 ms_road 总体方向相近时，
    才认为这种交会可能是“同一条道路的错位表达”。
    真实路口通常方向差较大，不应被这个函数命中。
    """
    tol = max(float(touch_tolerance), 0.0)
    for geom in candidate_geoms:
        if geom is None or geom.is_empty:
            continue
        if angle_diff(sup_angle, line_angle(geom)) > angle_threshold:
            continue
        try:
            if line.intersects(geom):
                return True
            if tol > 0 and line.distance(geom) <= tol:
                return True
        except Exception:
            continue
    return False


def prune_crossing_duplicate_ms_roads(
    fused: gpd.GeoDataFrame,
    cfg: RoadFusionConfig,
    coverage_threshold: Optional[float] = None,
    mean_distance_threshold: Optional[float] = None,
    p90_distance_threshold: Optional[float] = None,
    max_distance_threshold: Optional[float] = None,
) -> Tuple[gpd.GeoDataFrame, int]:
    """
    删除“交叉错位型” MSFT 补充线。

    典型场景是：OSM 已经有一条较完整的道路，MSFT 在局部与其轻微穿插、交叉，
    或者沿着 OSM 附近来回摆动。宏观看它不是新增道路，而是同一条路的偏移表达。

    为避免误删真实交叉路口，本模块必须同时满足：
    1. ms_road 大部分长度落在附近 OSM corridor 内；
    2. 采样点到 OSM 的平均/90 分位/最大距离都不大；
    3. ms_road 与方向相近的 OSM 主线存在接触、穿插或极近距离交会。
    """
    if not cfg.enable_crossing_duplicate_pruning or "fclass" not in fused.columns:
        return fused, 0

    gdf = fused.copy().reset_index(drop=True)
    base = gdf[gdf["fclass"] != "ms_road"].copy()
    sup = gdf[gdf["fclass"] == "ms_road"].copy()

    if base.empty or sup.empty:
        return gdf, 0

    base = base[base.geometry.notna() & (~base.geometry.is_empty) & (base.geometry.geom_type == "LineString")].copy()
    sup = sup[sup.geometry.notna() & (~sup.geometry.is_empty) & (sup.geometry.geom_type == "LineString")].copy()
    if base.empty or sup.empty:
        return gdf, 0

    corridor_dist = cfg.crossing_corridor_dist
    coverage_th = cfg.crossing_coverage_threshold if coverage_threshold is None else coverage_threshold
    mean_th = cfg.crossing_mean_distance if mean_distance_threshold is None else mean_distance_threshold
    p90_th = cfg.crossing_p90_distance if p90_distance_threshold is None else p90_distance_threshold
    max_th = cfg.crossing_max_distance if max_distance_threshold is None else max_distance_threshold
    angle_th = cfg.crossing_angle_threshold
    touch_tol = cfg.crossing_touch_tolerance
    sample_step = cfg.crossing_sample_step

    base_sindex = base.sindex
    base_geoms = base.geometry.to_numpy()
    base_angles = np.array([line_angle(g) for g in base_geoms], dtype=float)
    delete_indices: Set[int] = set()

    search_dist = max(corridor_dist, max_th, touch_tol)

    for row_no, sup_row in enumerate(sup.itertuples(), start=1):
        line = sup_row.geometry
        if not isinstance(line, LineString) or line.is_empty or line.length <= cfg.min_line_length:
            continue

        sup_ang = line_angle(line)
        candidate_pos = list(base_sindex.intersection(expanded_bounds(line.bounds, search_dist)))
        if not candidate_pos:
            continue

        # 只使用方向相近的 OSM 线作为“重复表达”的候选参照。
        # 这一步可以保护真实路口中的横向交叉道路。
        directional_pos = [pos for pos in candidate_pos if angle_diff(sup_ang, base_angles[pos]) <= angle_th]
        if not directional_pos:
            continue
        parallel_geoms = [base_geoms[pos] for pos in directional_pos if base_geoms[pos] is not None and not base_geoms[pos].is_empty]
        if not parallel_geoms:
            continue

        if not line_has_parallel_contact_or_crossing(
            line, parallel_geoms, sup_ang, angle_th, touch_tol
        ):
            continue

        coverage = line_coverage_by_base_corridor(line, parallel_geoms, corridor_dist)
        if coverage < coverage_th:
            continue

        mean_dist, p90_dist, max_dist = sampled_distance_profile_to_geoms(
            line, parallel_geoms, sample_step
        )
        if mean_dist <= mean_th and p90_dist <= p90_th and max_dist <= max_th:
            delete_indices.add(int(sup_row.Index))

        if cfg.log_every_n > 0 and row_no % cfg.log_every_n == 0:
            logger.info(
                "交叉错位重复线检查进度 ms_road %s/%s，待删除 %s",
                row_no, len(sup), len(delete_indices)
            )

    if not delete_indices:
        return gdf, 0

    cleaned = gdf.drop(index=sorted(delete_indices)).reset_index(drop=True)
    return gpd.GeoDataFrame(cleaned, geometry=gdf.geometry.name, crs=gdf.crs), len(delete_indices)


# =============================================================================
# 悬挂短线清理：只清理明显孤立且很短的 ms_road
# =============================================================================

def endpoint_connected_to_other_roads(
    point: Point,
    all_geoms: Sequence[LineString],
    all_indices: Sequence[int],
    all_sindex,
    self_idx: int,
    radius: float,
) -> bool:
    """判断端点是否在半径内接入任意其他道路。"""
    candidate_pos = list(all_sindex.intersection(bounds_around_point(point, radius)))
    for pos in candidate_pos:
        other_idx = int(all_indices[pos])
        if other_idx == self_idx:
            continue
        geom = all_geoms[pos]
        if geom is None or geom.is_empty:
            continue
        if point.distance(geom) <= radius:
            return True
    return False


def cleanup_dangling_ms_roads(
    fused: gpd.GeoDataFrame,
    cfg: RoadFusionConfig,
) -> Tuple[gpd.GeoDataFrame, int]:
    """
    清理明显的悬挂短线。

    只删除两类对象：
    1. 两端都没有接入任何道路，且长度很短的 ms_road；
    2. 只有一端接入道路，另一端悬挂，且长度极短的 ms_road。

    较长的死胡同、独立道路和新增支路会保留，避免过度清理导致道路丢失。
    """
    if not cfg.enable_dangle_cleanup or "fclass" not in fused.columns:
        return fused, 0

    gdf = fused.copy().reset_index(drop=True)
    valid = gdf[gdf.geometry.notna() & (~gdf.geometry.is_empty) & (gdf.geometry.geom_type == "LineString")].copy()
    if valid.empty:
        return gdf, 0

    all_sindex = valid.sindex
    all_geoms = valid.geometry.to_numpy()
    all_indices = valid.index.to_numpy()

    ms = valid[valid["fclass"] == "ms_road"].copy()
    if ms.empty:
        return gdf, 0

    delete_indices: Set[int] = set()
    radius = cfg.dangle_connect_radius

    for row in ms.itertuples():
        line = row.geometry
        if not isinstance(line, LineString) or line.is_empty or line.length <= cfg.min_line_length:
            continue

        coords = list(line.coords)
        start = Point(coords[0])
        end = Point(coords[-1])

        start_connected = endpoint_connected_to_other_roads(start, all_geoms, all_indices, all_sindex, int(row.Index), radius)
        end_connected = endpoint_connected_to_other_roads(end, all_geoms, all_indices, all_sindex, int(row.Index), radius)

        if (not start_connected) and (not end_connected):
            if line.length <= cfg.dangle_delete_two_free_max_length:
                delete_indices.add(int(row.Index))
        elif start_connected != end_connected:
            if line.length <= cfg.dangle_delete_one_free_max_length:
                delete_indices.add(int(row.Index))

    if not delete_indices:
        return gdf, 0

    cleaned = gdf.drop(index=sorted(delete_indices)).reset_index(drop=True)
    return gpd.GeoDataFrame(cleaned, geometry=gdf.geometry.name, crs=gdf.crs), len(delete_indices)

# =============================================================================
# 端点吸附：只调整补充道路，不移动 OSM 主道路
# =============================================================================

def endpoint_snap_allowed_by_bend(
    old_endpoint: Point,
    inner_point: Point,
    new_endpoint: Point,
    cfg: RoadFusionConfig,
) -> bool:
    """限制端点吸附后首段/末段方向的突变，避免出现很硬的异常连接。"""
    if old_endpoint.distance(new_endpoint) <= 1e-9:
        return True
    old_ang = angle_between_points((old_endpoint.x, old_endpoint.y), (inner_point.x, inner_point.y))
    new_ang = angle_between_points((new_endpoint.x, new_endpoint.y), (inner_point.x, inner_point.y))
    return angle_diff(old_ang, new_ang) <= cfg.max_endpoint_snap_bend_angle


def nearest_projection_on_base(
    point: Point,
    base_geoms: Sequence[LineString],
    base_sindex,
    radius: float,
) -> Tuple[Point, float]:
    """查找 point 在附近主道路上的最近投影点。"""
    candidate_pos = list(base_sindex.intersection(bounds_around_point(point, radius)))
    if not candidate_pos:
        return point, float("inf")

    best_point = point
    best_dist = float("inf")
    for pos in candidate_pos:
        geom = base_geoms[pos]
        if geom is None or geom.is_empty:
            continue
        proj = geom.interpolate(geom.project(point))
        dist = point.distance(proj)
        if dist < best_dist:
            best_dist = dist
            best_point = proj
    return best_point, best_dist


def adjust_ms_endpoints_to_base(fused: gpd.GeoDataFrame, cfg: RoadFusionConfig) -> gpd.GeoDataFrame:
    """将 ms_road 的起终点吸附到 OSM 主网络附近，不反向移动 OSM。"""
    if "fclass" not in fused.columns:
        return fused

    gdf = fused.copy().reset_index(drop=True)
    geom_col = gdf.geometry.name
    base = gdf[gdf["fclass"] != "ms_road"].copy()
    ms_mask = gdf["fclass"] == "ms_road"

    if base.empty or not ms_mask.any():
        return gdf

    base = base[base.geometry.notna() & (~base.geometry.is_empty) & (base.geometry.geom_type == "LineString")].copy()
    if base.empty:
        return gdf

    base_sindex = base.sindex
    base_geoms = base.geometry.to_numpy()

    ms_indices = gdf.index[ms_mask].to_list()
    adjusted = []

    for idx in ms_indices:
        line = gdf.at[idx, geom_col]
        if not isinstance(line, LineString) or line.is_empty or line.length <= cfg.min_line_length:
            adjusted.append(line)
            continue

        coords = list(line.coords)
        start = Point(coords[0])
        end = Point(coords[-1])

        start_proj, start_dist = nearest_projection_on_base(start, base_geoms, base_sindex, cfg.endpoint_snap_radius)
        end_proj, end_dist = nearest_projection_on_base(end, base_geoms, base_sindex, cfg.endpoint_snap_radius)

        if start_dist <= cfg.endpoint_snap_radius and endpoint_snap_allowed_by_bend(start, Point(coords[1]), start_proj, cfg):
            new_start = start_proj
        else:
            new_start = start

        if end_dist <= cfg.endpoint_snap_radius and endpoint_snap_allowed_by_bend(end, Point(coords[-2]), end_proj, cfg):
            new_end = end_proj
        else:
            new_end = end

        new_coords = [(new_start.x, new_start.y)] + coords[1:-1] + [(new_end.x, new_end.y)]
        new_line = LineString(new_coords)

        # 防止起终点吸附后把短道路压扁。
        if new_line.length >= cfg.min_length_after_snap:
            adjusted.append(new_line)
        else:
            adjusted.append(line)

    gdf.loc[ms_indices, geom_col] = gpd.GeoSeries(adjusted, index=ms_indices, crs=gdf.crs)
    return gpd.GeoDataFrame(gdf, geometry=geom_col, crs=fused.crs)


# =============================================================================
# 输出与主流程
# =============================================================================

def safe_existing_columns(path: str, requested_columns: Optional[Sequence[str]], cfg: RoadFusionConfig) -> Optional[List[str]]:
    """返回数据中实际存在的字段，避免列裁剪时因为字段缺失报错。"""
    if not requested_columns:
        return None
    try:
        if cfg.use_pyogrio_io:
            import pyogrio
            info = pyogrio.read_info(path)
            fields = set(info.get("fields") or [])
        else:
            raise RuntimeError("skip pyogrio info")
    except Exception:
        try:
            import fiona
            with fiona.open(path) as src:
                fields = set(src.schema.get("properties", {}).keys())
        except Exception:
            # 无法读取字段信息时，让 geopandas 自己处理；失败后 read_gdf 会回退全字段读取。
            return list(requested_columns)
    cols = [c for c in requested_columns if c in fields]
    return cols if cols else []


def get_dataset_bounds_and_crs(path: str, cfg: RoadFusionConfig):
    """尽量不读取全量数据，获取数据集 total_bounds 和 CRS。"""
    try:
        if cfg.use_pyogrio_io:
            import pyogrio
            info = pyogrio.read_info(path)
            bounds = info.get("total_bounds")
            crs = info.get("crs")
            if bounds is not None:
                return tuple(float(v) for v in bounds), str(crs) if crs is not None else None
    except Exception:
        pass

    try:
        import fiona
        with fiona.open(path) as src:
            bounds = tuple(float(v) for v in src.bounds)
            crs = src.crs_wkt or src.crs
            return bounds, str(crs) if crs is not None else None
    except Exception as exc:
        logger.warning("无法快速读取 bounds，跳过预裁剪：%s", exc)
        return None, None


def bounds_intersection_with_margin(
    bounds_a: Tuple[float, float, float, float],
    bounds_b: Tuple[float, float, float, float],
    margin: float,
) -> Optional[Tuple[float, float, float, float]]:
    """计算两个 bbox 的交集，并按 margin 外扩。"""
    minx = max(bounds_a[0], bounds_b[0])
    miny = max(bounds_a[1], bounds_b[1])
    maxx = min(bounds_a[2], bounds_b[2])
    maxy = min(bounds_a[3], bounds_b[3])
    if minx >= maxx or miny >= maxy:
        return None
    return (minx - margin, miny - margin, maxx + margin, maxy + margin)


def get_preclip_bbox(osm_path: str, msft_path: str, cfg: RoadFusionConfig) -> Optional[Tuple[float, float, float, float]]:
    """如果两源 CRS 一致，返回原始坐标系下的交集 bbox；否则跳过预裁剪。"""
    if not cfg.preclip_to_bounds_intersection:
        return None
    osm_bounds, osm_crs = get_dataset_bounds_and_crs(osm_path, cfg)
    ms_bounds, ms_crs = get_dataset_bounds_and_crs(msft_path, cfg)
    if osm_bounds is None or ms_bounds is None:
        return None
    if osm_crs and ms_crs and osm_crs != ms_crs:
        logger.warning("两源 CRS 描述不一致，跳过 bbox 交集预裁剪：OSM=%s, MSFT=%s", osm_crs, ms_crs)
        return None
    bbox = bounds_intersection_with_margin(osm_bounds, ms_bounds, cfg.preclip_margin_degrees)
    if bbox is None:
        logger.warning("两源 bounds 无交集，跳过 bbox 交集预裁剪。")
        return None
    logger.info("启用 bbox 交集预裁剪：%s", bbox)
    return bbox


def read_gdf(
    path: str,
    cfg: RoadFusionConfig,
    columns: Optional[Sequence[str]] = None,
    bbox: Optional[Tuple[float, float, float, float]] = None,
) -> gpd.GeoDataFrame:
    """读取矢量数据。支持 pyogrio、字段列裁剪和 bbox 裁剪；失败时自动回退。"""
    kwargs = {}
    selected_columns = safe_existing_columns(path, columns, cfg) if columns else None
    if selected_columns is not None:
        kwargs["columns"] = selected_columns
    if bbox is not None:
        kwargs["bbox"] = bbox

    if cfg.use_pyogrio_io:
        try:
            return gpd.read_file(path, engine="pyogrio", **kwargs)
        except Exception as exc:
            logger.warning("pyogrio 读取失败，回退默认引擎：%s", exc)

    try:
        return gpd.read_file(path, **kwargs)
    except TypeError:
        # 兼容旧版 geopandas/fiona 不支持 columns 的情况。
        fallback_kwargs = {}
        if bbox is not None:
            fallback_kwargs["bbox"] = bbox
        gdf = gpd.read_file(path, **fallback_kwargs)
        if selected_columns is not None:
            keep_cols = [c for c in selected_columns if c in gdf.columns]
            geom_col = gdf.geometry.name
            keep_cols = list(dict.fromkeys(keep_cols + [geom_col]))
            gdf = gdf[keep_cols].copy()
        return gdf


def prepared_cache_path(
    raw_path: str,
    kind: str,
    cfg: RoadFusionConfig,
    bbox: Optional[Tuple[float, float, float, float]],
) -> Path:
    """生成预处理缓存路径。"""
    base_dir = Path(cfg.prepared_cache_dir) if cfg.prepared_cache_dir else Path(raw_path).parent / "_road_fusion_cache"
    base_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(raw_path).stem
    bbox_tag = "full"
    if bbox is not None:
        bbox_tag = "bbox_" + "_".join(f"{v:.5f}" for v in bbox)
    safe_crs = cfg.target_crs.replace(":", "")
    max_len = "none" if cfg.max_segment_length is None else str(int(cfg.max_segment_length))
    name = f"{kind}_{stem}_{safe_crs}_angle{int(cfg.angle_threshold)}_max{max_len}_{bbox_tag}.parquet"
    return base_dir / name


def load_or_prepare_roads(
    raw_gdf: gpd.GeoDataFrame,
    raw_path: str,
    kind: str,
    cfg: RoadFusionConfig,
    bbox: Optional[Tuple[float, float, float, float]],
) -> gpd.GeoDataFrame:
    """可选读取/写入预处理缓存。kind 只能是 osm 或 msft。"""
    cache_path = prepared_cache_path(raw_path, kind, cfg, bbox)
    if cfg.use_prepared_cache and cache_path.exists() and not cfg.overwrite_prepared_cache:
        logger.info("读取预处理缓存：%s", cache_path)
        return gpd.read_parquet(cache_path)

    if kind == "osm":
        prepared = prepare_osm(raw_gdf, cfg)
    elif kind == "msft":
        prepared = prepare_msft(raw_gdf, cfg)
    else:
        raise ValueError(f"未知道路类型：{kind}")

    if cfg.use_prepared_cache:
        logger.info("写入预处理缓存：%s", cache_path)
        prepared.to_parquet(cache_path)
    return prepared


def write_gdf(gdf: gpd.GeoDataFrame, output_path: str, layer: str = "roads", cfg: RoadFusionConfig = CONFIG) -> None:
    """写出结果。推荐 GeoPackage。"""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    suffix = out.suffix.lower()
    if suffix == ".gpkg":
        if cfg.use_pyogrio_io:
            try:
                gdf.to_file(out, layer=layer, driver="GPKG", engine="pyogrio")
                return
            except Exception as exc:
                logger.warning("pyogrio 写出失败，回退默认引擎：%s", exc)
        gdf.to_file(out, layer=layer, driver="GPKG")
    elif suffix == ".parquet":
        gdf.to_parquet(out)
    else:
        logger.warning("当前输出不是 .gpkg/.parquet。Shapefile 可能截断字段名，且百万级数据写出较慢。")
        if cfg.use_pyogrio_io:
            try:
                gdf.to_file(out, engine="pyogrio")
                return
            except Exception as exc:
                logger.warning("pyogrio 写出失败，回退默认引擎：%s", exc)
        gdf.to_file(out)


def write_stats(stats: Dict[str, int], output_path: str, cfg: RoadFusionConfig) -> None:
    """将统计信息写为 JSON。"""
    stat_path = str(Path(output_path).with_suffix(".stats.json"))
    payload = {
        "stats": stats,
        "config": asdict(cfg),
    }
    with open(stat_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info("统计信息已写出：%s", stat_path)


def resolved_cleanup_mode(cfg: RoadFusionConfig) -> str:
    """解析清理模式，并兼容 V6 的 run_second_clean_pass。"""
    mode = (cfg.cleanup_mode or "").strip().lower()
    if mode in {"quality", "balanced", "fast"}:
        return mode
    return "quality" if cfg.run_second_clean_pass else "fast"


def fuse_roads_pipeline(
    osm_path: str,
    msft_path: str,
    output_path: str,
    cfg: RoadFusionConfig = CONFIG,
) -> Tuple[gpd.GeoDataFrame, Dict[str, int]]:
    """完整道路融合流程。"""
    t0 = time.time()

    preclip_bbox = get_preclip_bbox(osm_path, msft_path, cfg)

    osm_columns = cfg.osm_read_columns if cfg.read_only_needed_columns else None
    msft_columns = cfg.msft_read_columns if cfg.read_only_needed_columns else None

    logger.info("读取 OSM 数据：%s", osm_path)
    raw_osm = read_gdf(osm_path, cfg, columns=osm_columns, bbox=preclip_bbox)
    logger.info("读取 MSFT 数据：%s", msft_path)
    raw_ms = read_gdf(msft_path, cfg, columns=msft_columns, bbox=preclip_bbox)

    logger.info("预处理 OSM 道路...")
    osm = load_or_prepare_roads(raw_osm, osm_path, "osm", cfg, preclip_bbox)
    logger.info("OSM 原始读取 %s 条，预处理后 %s 条", len(raw_osm), len(osm))

    logger.info("预处理 MSFT 道路...")
    ms = load_or_prepare_roads(raw_ms, msft_path, "msft", cfg, preclip_bbox)
    logger.info("MSFT 原始读取 %s 条，预处理后 %s 条", len(raw_ms), len(ms))

    logger.info("开始快速匹配与融合...")
    fused, stats = match_and_fuse_fast(osm, ms, cfg)

    cleanup_mode = resolved_cleanup_mode(cfg)
    logger.info("当前清理模式：%s", cleanup_mode)

    logger.info("第一次保守重复删除...")
    fused, removed_before_snap = remove_duplicate_ms_roads_fast(fused, cfg)
    stats["duplicate_removed_before_snap"] = int(removed_before_snap)

    logger.info("第一次组级重复删除，清理多段 OSM 共同覆盖的重复 ms_road...")
    fused, removed_group_before_snap = remove_duplicate_ms_roads_group_fast(fused, cfg)
    stats["group_duplicate_removed_before_snap"] = int(removed_group_before_snap)

    stats["near_base_return_removed_before_snap"] = 0
    stats["crossing_duplicate_removed_before_snap"] = 0
    stats["duplicate_removed_after_snap"] = 0
    stats["group_duplicate_removed_after_snap"] = 0
    stats["near_base_return_removed_after_snap"] = 0
    stats["crossing_duplicate_removed_after_snap"] = 0

    if cleanup_mode in {"quality", "balanced"}:
        logger.info("吸附前清理近主网回接型 ms_road...")
        fused, removed_near_base_before_snap = prune_near_base_return_ms_roads(fused, cfg)
        stats["near_base_return_removed_before_snap"] = int(removed_near_base_before_snap)

        logger.info("吸附前清理交叉错位型 ms_road...")
        fused, removed_crossing_before_snap = prune_crossing_duplicate_ms_roads(fused, cfg)
        stats["crossing_duplicate_removed_before_snap"] = int(removed_crossing_before_snap)
    else:
        logger.info("fast 模式：跳过吸附前近主网/交叉错位高级清理。")

    logger.info("开始端点吸附，仅调整 ms_road 到 OSM 主网络...")
    fused = adjust_ms_endpoints_to_base(fused, cfg)

    if cleanup_mode in {"quality", "balanced"}:
        logger.info("吸附后保守重复删除，阈值更严格，防止端点吸附后残留重复...")
        fused, removed_after_snap = remove_duplicate_ms_roads_fast(
            fused,
            cfg,
            coverage_threshold=max(cfg.duplicate_coverage_threshold, 0.95),
            max_centerline_dist=min(cfg.duplicate_max_centerline_dist, 5.0),
        )
        stats["duplicate_removed_after_snap"] = int(removed_after_snap)

        logger.info("吸附后组级重复删除，进一步清理端点吸附后的近重合 ms_road...")
        fused, removed_group_after_snap = remove_duplicate_ms_roads_group_fast(
            fused,
            cfg,
            coverage_threshold=max(cfg.group_duplicate_coverage_threshold, 0.95),
            mean_distance_threshold=min(cfg.group_duplicate_mean_distance, 3.0),
            p90_distance_threshold=min(cfg.group_duplicate_p90_distance, 5.0),
        )
        stats["group_duplicate_removed_after_snap"] = int(removed_group_after_snap)

    if cleanup_mode in {"quality", "fast"}:
        logger.info("吸附后清理近主网回接型 ms_road...")
        fused, removed_near_base_after_snap = prune_near_base_return_ms_roads(
            fused,
            cfg,
            coverage_threshold=max(cfg.near_base_return_coverage_threshold, 0.90),
            mean_distance_threshold=min(cfg.near_base_return_mean_distance, 5.0),
            p90_distance_threshold=min(cfg.near_base_return_p90_distance, 8.0),
            max_distance_threshold=min(cfg.near_base_return_max_distance, 14.0),
        )
        stats["near_base_return_removed_after_snap"] = int(removed_near_base_after_snap)

        logger.info("吸附后清理交叉错位型 ms_road...")
        fused, removed_crossing_after_snap = prune_crossing_duplicate_ms_roads(
            fused,
            cfg,
            coverage_threshold=max(cfg.crossing_coverage_threshold, 0.88),
            mean_distance_threshold=min(cfg.crossing_mean_distance, 5.0),
            p90_distance_threshold=min(cfg.crossing_p90_distance, 8.0),
            max_distance_threshold=min(cfg.crossing_max_distance, 14.0),
        )
        stats["crossing_duplicate_removed_after_snap"] = int(removed_crossing_after_snap)
    elif cleanup_mode == "balanced":
        logger.info("balanced 模式：吸附后跳过近主网/交叉错位高级清理。")

    logger.info("清理明显孤立的悬挂短线...")
    fused, removed_dangles = cleanup_dangling_ms_roads(fused, cfg)
    stats["dangling_ms_road_removed"] = int(removed_dangles)

    stats["final_count"] = int(len(fused))
    stats["elapsed_seconds"] = int(time.time() - t0)

    if cfg.output_crs is not None:
        logger.info("输出前重投影到 %s", cfg.output_crs)
        fused_to_write = fused.to_crs(cfg.output_crs)
    else:
        fused_to_write = fused

    logger.info("写出融合结果：%s", output_path)
    write_gdf(fused_to_write, output_path, cfg=cfg)
    write_stats(stats, output_path, cfg)

    logger.info("处理完成：%s", stats)
    return fused, stats


def main() -> None:
    """主入口：只需要改这里的路径。"""

    # -------------------------------------------------------------------------
    # 1. 修改为你的输入输出路径
    # -------------------------------------------------------------------------
    OSM_PATH = r"G:/演示数据/走廊数据/gis_osm_roads_free_1.shp"
    MSFT_PATH = r"G:/演示数据/走廊数据/MS_PK_Road.shp"

    # 建议输出 GeoPackage，字段不会像 Shapefile 那样被截断。
    OUTPUT_PATH = r"G:/演示数据/走廊数据/data/final_processed_roads_optimized.gpkg"

    # -------------------------------------------------------------------------
    # 2. 如需微调参数，在这里改
    # -------------------------------------------------------------------------
    cfg = RoadFusionConfig(
        target_crs="EPSG:32643",
        do_split_by_angle=True,
        angle_threshold=135.0,
        max_segment_length=800.0,
        match_buffer_dist=20.0,
        max_hausdorff=15.0,
        loose_angle_threshold=45.0,
        min_len_similarity=0.05,
        # 这里保留 0.80：低于 0.80 的 MSFT 整体补充；
        # 高于 0.80 但仍有未覆盖部分的 MSFT，会通过残段提取继续补充。
        min_msft_coverage_for_matched=0.80,
        preserve_matched_msft_residuals=True,
        min_residual_length=10.0,
        assume_missing_crs_as_target=False,
        duplicate_buffer_dist=10.0,
        duplicate_coverage_threshold=0.92,
        duplicate_angle_threshold=25.0,
        duplicate_max_centerline_dist=8.0,
        enable_group_duplicate_removal=True,
        group_duplicate_buffer_dist=6.0,
        group_duplicate_coverage_threshold=0.90,
        group_duplicate_angle_threshold=18.0,
        group_duplicate_mean_distance=4.0,
        group_duplicate_p90_distance=7.0,
        duplicate_sample_step=30.0,
        enable_near_base_return_pruning=True,
        near_base_return_endpoint_radius=12.0,
        near_base_return_corridor_dist=12.0,
        near_base_return_coverage_threshold=0.85,
        near_base_return_mean_distance=6.0,
        near_base_return_p90_distance=10.0,
        near_base_return_max_distance=16.0,
        near_base_return_sample_step=30.0,
        enable_crossing_duplicate_pruning=True,
        crossing_corridor_dist=12.0,
        crossing_coverage_threshold=0.82,
        crossing_mean_distance=6.0,
        crossing_p90_distance=10.0,
        crossing_max_distance=18.0,
        crossing_angle_threshold=22.0,
        crossing_touch_tolerance=1.0,
        crossing_sample_step=30.0,
        cleanup_mode="fast",
        run_second_clean_pass=False,
        use_pyogrio_io=True,
        read_only_needed_columns=True,
        preclip_to_bounds_intersection=True,
        preclip_margin_degrees=0.02,
        use_prepared_cache=False,
        endpoint_snap_radius=10.0,
        max_endpoint_snap_bend_angle=35.0,
        enable_dangle_cleanup=True,
        dangle_connect_radius=10.0,
        dangle_delete_two_free_max_length=30.0,
        dangle_delete_one_free_max_length=12.0,
        output_crs=None,  # 如果你需要经纬度输出，改为 "EPSG:4326"
    )

    fuse_roads_pipeline(
        osm_path=OSM_PATH,
        msft_path=MSFT_PATH,
        output_path=OUTPUT_PATH,
        cfg=cfg,
    )


if __name__ == "__main__":
    main()
