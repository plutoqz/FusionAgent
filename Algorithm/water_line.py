from scipy.spatial.distance import directed_hausdorff
from shapely.geometry import LineString, Point, MultiPoint, MultiLineString, Polygon, GeometryCollection
from shapely.ops import split
from rtree import index
import logging
import math
import pandas as pd
from shapely.ops import linemerge
import geopandas as gpd
import numpy as np
from shapely.ops import unary_union

ANGLE_THRESHOLD = 135  # 分割角度阈值（度）
PAKISTAN_CRS = "EPSG:32643"  # 巴基斯坦 UTM Zone 43N
OSM_ID_START = 10000  # OSM ID 起始编号
TOLERANCE = 0.5  # 坐标容差（米）
SNAP_TOLERANCE = 1.0  # 端点捕捉容差（米）
ANGLE_THRESHOLD = 135  # 分割角度阈值（度）
BUFFER_DIST = 20  # 缓冲区半径（米），宽松匹配可适当增大
MAX_HAUSDORFF = 15  # 最大Hausdorff距离（米）

def snap_lines(lines, snap_tolerance):
    """确保相邻线段端点精确对齐"""
    idx = index.Index()
    for i, line in enumerate(lines):
        idx.insert(i, line.bounds)

    snapped = []
    for i, line in enumerate(lines):
        coords = list(line.coords)
        start, end = Point(coords[0]), Point(coords[-1])

        # 捕捉起点
        near_start = list(idx.intersection(start.buffer(snap_tolerance).bounds))
        for j in near_start:
            if j == i:
                continue
            other_line = lines[j]
            if start.distance(other_line) <= snap_tolerance:
                new_start = other_line.interpolate(other_line.project(start))
                coords[0] = (new_start.x, new_start.y)

        # 捕捉终点
        near_end = list(idx.intersection(end.buffer(snap_tolerance).bounds))
        for j in near_end:
            if j == i:
                continue
            other_line = lines[j]
            if end.distance(other_line) <= snap_tolerance:
                new_end = other_line.interpolate(other_line.project(end))
                coords[-1] = (new_end.x, new_end.y)

        snapped.append(LineString(coords))
    return snapped


def planarize(lines, tolerance):
    """在交点处打断所有线段"""
    idx = index.Index()
    for i, line in enumerate(lines):
        idx.insert(i, line.bounds)

    # 收集所有交点
    intersection_points = []
    for i, line1 in enumerate(lines):
        for j in list(idx.intersection(line1.bounds)):
            if j <= i:
                continue
            line2 = lines[j]
            intersect = line1.intersection(line2)
            if not intersect.is_empty:
                if intersect.geom_type == 'Point':
                    intersection_points.append(intersect)
                elif intersect.geom_type == 'MultiPoint':
                    intersection_points.extend(list(intersect.geoms))

    # 去重（基于容差）
    unique_points = []
    seen = set()
    for p in intersection_points:
        key = (round(p.x / tolerance), round(p.y / tolerance))
        if key not in seen:
            seen.add(key)
            unique_points.append(p)

    # 打断线段
    split_geoms = []
    for line in lines:
        cut_points = [p for p in unique_points if line.distance(p) <= tolerance]
        if cut_points:
            splitter = MultiPoint(cut_points)
            segments = split(line, splitter)
            for seg in segments.geoms:
                if isinstance(seg, LineString):
                    split_geoms.append(seg)
                elif isinstance(seg, MultiLineString):
                    split_geoms.extend(list(seg.geoms))
        else:
            split_geoms.append(line)
    return split_geoms


def merge_lines(lines):
    """合并相邻线段"""
    try:
        merged = linemerge(lines)
        final = []

        if merged.is_empty:
            return []

        if merged.geom_type == 'MultiLineString':
            final.extend(list(merged.geoms))
        elif merged.geom_type == 'LineString':
            final.append(merged)
        else:
            for geom in merged.geoms:
                if geom.geom_type == 'LineString':
                    final.append(geom)
        return final
    except Exception as e:
        return lines


def process_osm_data(gdf, id_start=1):
    """处理 OSM 数据：保留所有属性，重新编号 osm_id，将name重命名为name_osm
    特别处理：将所有线段拆分为独立要素，即使它们存储在同一个要素中

    Args:
        gdf (GeoDataFrame): 输入的OSM数据
        id_start (int): 起始编号，默认为1

    Returns:
        GeoDataFrame: 处理后的数据，所有线段均为独立要素，name字段重命名为name_osm
    """
    processed_data = []
    current_id = id_start

    for _, row in gdf.iterrows():
        geom = row.geometry

        # 跳过空几何
        if geom.is_empty:
            continue

        # 提取原始属性字典（后续重命名name）
        original_props = row.to_dict()
        # 重命名name为name_osm（如果存在）
        if 'name' in original_props:
            original_props['name_osm'] = original_props.pop('name')

        # 处理LineString - 直接保留
        if isinstance(geom, LineString):
            new_row = original_props  # 使用已重命名的属性字典
            new_row['geometry'] = geom
            new_row['osm_id'] = current_id
            processed_data.append(new_row)
            current_id += 1

        # 处理MultiLineString - 拆分为独立线段
        elif isinstance(geom, MultiLineString):
            for line in geom.geoms:
                new_row = original_props.copy()  # 复制重命名后的属性
                new_row['geometry'] = line
                new_row['osm_id'] = current_id
                processed_data.append(new_row)
                current_id += 1

        # 处理Polygon - 转为边界线
        elif isinstance(geom, Polygon):
            boundary = geom.exterior
            new_row = original_props.copy()
            new_row['geometry'] = boundary
            new_row['osm_id'] = current_id
            processed_data.append(new_row)
            current_id += 1

        # 处理GeometryCollection - 提取所有线段
        elif isinstance(geom, GeometryCollection):
            for part in geom.geoms:
                # 复制原始属性（已重命名name→name_osm）
                part_props = original_props.copy()

                if isinstance(part, LineString):
                    new_row = part_props
                    new_row['geometry'] = part
                    new_row['osm_id'] = current_id
                    processed_data.append(new_row)
                    current_id += 1
                elif isinstance(part, MultiLineString):
                    for line in part.geoms:
                        new_row = part_props.copy()
                        new_row['geometry'] = line
                        new_row['osm_id'] = current_id
                        processed_data.append(new_row)
                        current_id += 1
                elif isinstance(part, Polygon):
                    boundary = part.exterior
                    new_row = part_props.copy()
                    new_row['geometry'] = boundary
                    new_row['osm_id'] = current_id
                    processed_data.append(new_row)
                    current_id += 1

        # 处理其他几何类型 - 跳过或自定义处理
        else:
            print(f"警告: 跳过未处理的几何类型: {geom.type}")

    return gpd.GeoDataFrame(processed_data)


def process_water_data(gdf):
    """处理微软数据：保留 FID_1、name、fclass(原waterway) 和几何，重新编号"""
    processed_data = []
    current_fid = 1  # 用于生成FID_1的自增编号

    # 遍历原始数据，逐个处理每个有效几何
    for idx, row in gdf.iterrows():
        geom = row.geometry

        # 跳过空几何或非LineString类型
        if geom.is_empty or not isinstance(geom, LineString):
            continue

        # 提取原始属性
        original_props = {
            'name': row.get('name', ''),
            'fclass_waterway': row.get('waterway', '')  # waterway重命名为fclass
        }

        # 对当前几何进行平面化打断（仅处理当前几何，避免与其他几何交叉影响）
        # 注意：这里传入的是包含当前几何的列表，确保打断仅针对当前几何
        lines = planarize([geom], TOLERANCE)

        # 遍历打断后的线段，关联原始属性
        for line in lines:
            # 跳过空几何（可能因打断失败导致）
            if line.is_empty:
                continue

            # 为当前线段分配FID_1（自增）
            processed_data.append({
                'FID_1': current_fid,
                'name': original_props['name'],
                'fclass_waterway': original_props['fclass_waterway'],
                'geometry': line
            })
            current_fid += 1  # 自增FID

    return gpd.GeoDataFrame(processed_data)

def calculate_angle(p1, p2, p3):
    """
    计算三个连续点形成的转角角度（单位：度）
    :param p1: 前一点坐标 (x,y)
    :param p2: 当前点坐标
    :param p3: 后一点坐标
    :return: 角度值（0-180度）
    """
    vec1 = (p1[0] - p2[0], p1[1] - p2[1])
    vec2 = (p3[0] - p2[0], p3[1] - p2[1])
    dot_product = vec1[0] * vec2[0] + vec1[1] * vec2[1]
    mod1 = math.hypot(vec1[0], vec1[1])
    mod2 = math.hypot(vec2[0], vec2[1])
    if mod1 == 0 or mod2 == 0:
        return 180.0
    cos_theta = dot_product / (mod1 * mod2)
    angle = math.degrees(math.acos(max(min(cos_theta, 1.0), -1.0)))
    return angle


def split_at_sharp_turns(line, angle_threshold=ANGLE_THRESHOLD):
    """
    在转角超过阈值的位置断开线要素
    :param line: LineString 几何对象
    :param angle_threshold: 角度阈值（小于该值时触发切割）
    :return: 分割后的 MultiLineString
    """
    if line.geom_type == 'MultiLineString':
        parts = [split_at_sharp_turns(part, angle_threshold) for part in line.geoms]
        return MultiLineString(
            [geom for part in parts for geom in (part.geoms if part.geom_type == 'MultiLineString' else [part])])

    if line.geom_type != 'LineString':
        return line

    coords = list(line.coords)
    split_points = []
    for i in range(1, len(coords) - 1):
        p1 = coords[i - 1]
        p2 = coords[i]
        p3 = coords[i + 1]
        angle = calculate_angle(p1, p2, p3)
        if angle < angle_threshold:
            split_point = Point(p2)
            split_points.append(split_point)

    if not split_points:
        return MultiLineString([line])

    split_lines = line
    for point in sorted(split_points, key=lambda p: line.project(p)):
        split_result = split(split_lines, point)
        split_lines = MultiLineString([geom for geom in split_result.geoms if geom.length > 0])
    return split_lines


def split_features_in_gdf(gdf, angle_threshold=ANGLE_THRESHOLD):
    """处理整个 GeoDataFrame 中的线要素"""
    new_rows = []

    for idx, row in gdf.iterrows():
        geom = row.geometry
        if geom.geom_type not in ['LineString', 'MultiLineString']:
            new_rows.append(row)
            continue

        split_geom = split_at_sharp_turns(geom, angle_threshold)
        if split_geom.geom_type == 'MultiLineString':
            for part in split_geom.geoms:
                new_row = row.copy()
                new_row.geometry = part
                new_rows.append(new_row)
        else:
            new_rows.append(row)

    return gpd.GeoDataFrame(new_rows, crs=gdf.crs)


def hausdorff_distance(line1, line2):
    """计算双向Hausdorff距离"""
    coords1 = np.array(line1.coords)
    coords2 = np.array(line2.coords)
    return max(
        directed_hausdorff(coords1, coords2)[0],
        directed_hausdorff(coords2, coords1)[0]
    )


def line_angle(line):
    """计算线段方向角度（基于起点-终点连线）"""
    coords = list(line.coords)
    dx = coords[-1][0] - coords[0][0]
    dy = coords[-1][1] - coords[0][1]
    return math.degrees(math.atan2(dy, dx)) % 180


def match_and_fuse_optimized(gdf_osm, gdf_msft, idx):
    """优化版：基于R-tree索引的高效水系匹配融合（保留微软属性）"""

    # 1. 预处理：构建微软数据的ID到几何和属性的映射（同时存储属性）
    msft_fid_to_geom = {row['FID_1']: row.geometry for _, row in gdf_msft.iterrows()}
    msft_fid_to_attr = {row['FID_1']: row.to_dict() for _, row in gdf_msft.iterrows()}  # 存储完整属性字典

    # 2. 预计算OSM缓冲区（批量处理）
    osm_osm_id_to_geom = {row['osm_id']: row.geometry for _, row in gdf_osm.iterrows()}
    osm_buffers = {osm_id: geom.buffer(BUFFER_DIST) for osm_id, geom in osm_osm_id_to_geom.items()}

    # 3. 初始化匹配结果存储（新增属性存储列表）
    label1 = [''] * len(gdf_osm)
    label2 = [''] * len(gdf_osm)
    matched_fids = set()
    msft_attrs = [{} for _ in range(len(gdf_osm))]  # 存储每一行匹配的微软属性

    # 4. 空间匹配主循环（优化查询与计算）
    osm_rows = list(gdf_osm.iterrows())  # 预加载所有行，避免重复索引
    for i, (osm_idx, osm_row) in enumerate(osm_rows):
        osm_id = osm_row['osm_id']
        osm_line = osm_row.geometry
        buffer_geom = osm_buffers[osm_id]

        # 4.1 R-tree查询候选FID（使用空间索引过滤）
        candidate_fids = list(idx.intersection(buffer_geom.bounds))

        # 4.2 批量计算匹配指标（向量化优化）
        for fid in candidate_fids:
            if fid not in msft_fid_to_geom:
                continue

            msft_line = msft_fid_to_geom[fid]
            msft_attr = msft_fid_to_attr[fid]  # 获取当前FID的微软属性

            # 4.2.1 精确匹配（Hausdorff距离）
            if buffer_geom.intersects(msft_line):
                hd = hausdorff_distance(osm_line, msft_line)
                if hd <= MAX_HAUSDORFF:
                    label1[i] = f"{label1[i]},{fid}" if label1[i] else str(fid)
                    matched_fids.add(fid)
                    msft_attrs[i] = msft_attr  # 记录匹配的微软属性

                else:
                    # 4.2.2 相似度匹配（长度+角度）
                    len_osm = osm_line.length
                    len_msft = msft_line.length
                    len_sim = min(len_osm, len_msft) / max(len_osm, len_msft)

                    angle_osm = line_angle(osm_line)
                    angle_msft = line_angle(msft_line)
                    angle_diff = abs(angle_osm - angle_msft) % 180
                    angle_diff = min(angle_diff, 180 - angle_diff)

                    if len_sim > 0.2 and angle_diff < 45:
                        label2[i] = f"{label2[i]},{fid}" if label2[i] else str(fid)
                        matched_fids.add(fid)
                        msft_attrs[i] = msft_attr  # 记录匹配的微软属性

    # 5. 更新OSM数据的匹配标签及微软属性（关键修改：合并微软属性）
    gdf_osm['label1'] = label1
    gdf_osm['label2'] = label2

    # 将微软属性合并到OSM数据（按原列名新增）
    if not gdf_msft.empty:
        # 获取微软数据的所有列名（排除几何列，避免重复）
        msft_cols = [col for col in gdf_msft.columns if col != 'geometry']
        for col in msft_cols:
            # 从msft_attrs中提取对应列的值（无匹配时为None）
            gdf_osm[col] = [attr.get(col, None) for attr in msft_attrs]

    # 6. 处理未匹配的微软数据（原有逻辑保留，属性已随数据添加）
    unmatched_msft = gdf_msft[~gdf_msft['FID_1'].isin(matched_fids)]
    if not unmatched_msft.empty:
        new_rows = []
        osm_cols = gdf_osm.columns  # 预先获取OSM列名（包含新增的微软列）
        for _, row in unmatched_msft.iterrows():
            new_row = row.to_dict()  # 直接使用微软的完整属性
            new_row['osm_id'] = None
            new_row['label3'] = row['FID_1']

            # 处理fclass（与原逻辑一致）
            original_fclass = new_row.get('fclass', None)
            if pd.isna(original_fclass) or (isinstance(original_fclass, str) and original_fclass.strip() == ""):
                new_row['fclass'] = 'fusion_water'

            # 填充OSM缺失列（确保列对齐）
            for col in osm_cols:
                if col not in new_row:
                    dtype = gdf_osm[col].dtype
                    new_row[col] = 0 if 'int' in str(dtype) or 'float' in str(dtype) else ''

            new_rows.append(new_row)

        # 一次性拼接（保持列一致性）
        gdf_osm = pd.concat([gdf_osm, pd.DataFrame(new_rows)], ignore_index=True)

    return gdf_osm




def merge_by_fid_and_code(gdf):
    """
    处理线段数据：
    1. 对code=0且FID_1相同的线段进行合并
    2. 保留code≠0的所有原始线段
    3. 将两部分结果合并

    参数:
    gdf (GeoDataFrame): 输入地理数据框，需包含FID_1和code字段

    返回:
    GeoDataFrame: 合并后的地理数据框
    """
    # 检查必要字段
    if gdf.empty or 'FID_1' not in gdf.columns or 'code' not in gdf.columns:
        return gdf

    # 1. 筛选需要合并的记录 (code=0且FID_1有效)
    merge_condition = (gdf['code'] == 0) & (gdf['FID_1'].notna())
    merge_gdf = gdf[merge_condition].copy()

    # 2. 筛选不需要合并的记录 (code≠0)
    keep_gdf = gdf[~merge_condition].copy()

    # 3. 处理需要合并的部分
    merged_data = []
    if not merge_gdf.empty:
        # 按FID_1分组
        grouped = merge_gdf.groupby('FID_1')

        for fid, group in grouped:
            # 合并几何
            merged_geom = linemerge(list(group.geometry))

            # 处理合并结果
            if merged_geom.is_empty:
                continue

            if merged_geom.geom_type == 'MultiLineString':
                for part in merged_geom.geoms:
                    if not part.is_empty:
                        record = group.iloc[0].to_dict()
                        record['geometry'] = part
                        record['merged'] = True
                        merged_data.append(record)
            elif merged_geom.geom_type == 'LineString':
                record = group.iloc[0].to_dict()
                record['geometry'] = merged_geom
                record['merged'] = True
                merged_data.append(record)

    # 4. 创建合并后的GeoDataFrame
    merged_gdf = gpd.GeoDataFrame(merged_data) if merged_data else gpd.GeoDataFrame()

    # 5. 处理不需要合并的部分
    if not keep_gdf.empty:
        keep_gdf['merged'] = False

    # 6. 合并两部分结果
    if not merged_gdf.empty and not keep_gdf.empty:
        result = gpd.GeoDataFrame(pd.concat([merged_gdf, keep_gdf], ignore_index=True))
    elif not merged_gdf.empty:
        result = merged_gdf
    elif not keep_gdf.empty:
        result = keep_gdf
    else:
        result = gpd.GeoDataFrame(columns=gdf.columns)

    # 7. 确保原始字段类型一致
    for col in gdf.columns:
        if col in result.columns and col != 'geometry':
            result[col] = result[col].astype(gdf[col].dtype)

    return result


from shapely.validation import make_valid

def erase_lines_by_polygon(lines_gdf, polygon_gdf):
    """
    使用面数据裁剪线数据，保留线在面外的部分（取反裁剪）
    返回完全位于面外部的线段
    """
    if lines_gdf.empty:
        print("警告: 线数据为空")
        return lines_gdf
    if polygon_gdf.empty:
        print("警告: 多边形数据为空")
        return lines_gdf

    # ---------- 1. 统一坐标系 ----------
    # 确保多边形数据有有效CRS
    if polygon_gdf.crs is None:
        raise ValueError("多边形数据CRS为None，请先设置正确的坐标系")

    # 将线数据转换为多边形的CRS（真正的坐标转换）
    if lines_gdf.crs != polygon_gdf.crs:
        print(f"坐标系不一致: 线数据CRS={lines_gdf.crs}, 多边形CRS={polygon_gdf.crs}")
        if lines_gdf.crs is None:
            lines_gdf = lines_gdf.set_crs("EPSG:4326")  # 先标记实际CRS
            lines_gdf = lines_gdf.to_crs(polygon_gdf.crs)  # 再转换到目标CRS

    # ---------- 2. 预处理多边形 ----------
    # 修复无效多边形（.buffer(0) 是常见的几何修复方法）
    polygon_gdf = polygon_gdf.copy()
    polygon_gdf['geometry'] = polygon_gdf.geometry.apply(
        lambda g: g.buffer(0) if not g.is_valid else g
    )
    polygon_gdf = polygon_gdf[~polygon_gdf.geometry.is_empty]  # 过滤空几何
    if polygon_gdf.empty:
        print("警告: 所有多边形几何无效或为空")
        return lines_gdf

    # 合并所有多边形为一个复合面（关键步骤）
    combined_poly = polygon_gdf.geometry.union_all()  # 修正：通过geometry列调用union_all()
    if combined_poly.is_empty:
        print("警告: 合并后的多边形为空")
        return lines_gdf

    # ---------- 3. 空间索引加速查询 ----------
    # 创建线数据的R-tree索引（加速空间查询）
    idx = index.Index()
    for i, geom in enumerate(lines_gdf.geometry):
        idx.insert(i, geom.bounds)

    # 查找与合并后面相交的线（通过包围盒快速过滤）
    candidate_indices = list(idx.intersection(combined_poly.bounds))
    print(f"找到 {len(candidate_indices)} 条可能与多边形相交的线")

    # ---------- 4. 精确裁剪：保留面外的线部分 ----------
    # 验证是否真的存在相交（避免处理不相交的线）
    candidate_lines = lines_gdf.iloc[candidate_indices]
    has_real_intersection = any(
        line.intersects(combined_poly) for line in candidate_lines.geometry
    )
    if not has_real_intersection:
        print("警告: 未找到与多边形实际相交的线，所有线保留")
        return lines_gdf

    # 处理每条候选线（裁剪取反）
    erased_lines = []
    for _, row in candidate_lines.iterrows():
        line = row.geometry
        if not line.is_valid:
            line = line.buffer(0)  # 修复线几何（可能因转换CRS导致无效）
            if line.is_empty:
                continue

        try:
            # 计算线与面的差集（结果为线在面外的部分）
            line_outside = line.difference(combined_poly)
        except Exception as e:
            print(f"裁剪出错（线ID={row.get('osm_id', '未知')}）: {e}，尝试简化几何后重试")
            line_simplified = line.simplify(0.5)  # 简化几何以避免拓扑错误
            line_outside = line_simplified.difference(combined_poly)

        if line_outside.is_empty:
            continue  # 线完全在面内，无保留部分

        # 拆解多重线（MultiLineString → 多个LineString）
        if line_outside.geom_type == 'MultiLineString':
            for part in line_outside.geoms:
                new_row = row.copy()
                new_row.geometry = part
                erased_lines.append(new_row)
        else:
            new_row = row.copy()
            new_row.geometry = line_outside
            erased_lines.append(new_row)

    # ---------- 5. 合并结果（面外线 + 完全不相交的线） ----------
    # 完全不相交的线（直接保留）
    non_intersect_indices = set(range(len(lines_gdf))) - set(candidate_indices)
    non_intersect_lines = lines_gdf.iloc[list(non_intersect_indices)]

    # 合并面外线和不相交线
    if erased_lines:
        erased_gdf = gpd.GeoDataFrame(erased_lines, crs=lines_gdf.crs)
        # 过滤无效几何
        erased_gdf = erased_gdf[erased_gdf.geometry.is_valid]
        result = gpd.GeoDataFrame(
            pd.concat([non_intersect_lines, erased_gdf], ignore_index=True),
            crs=lines_gdf.crs
        )
    else:
        result = non_intersect_lines.copy()

    # 最终过滤空几何
    result = result[~result.geometry.is_empty]
    print(f"裁剪完成，保留 {len(result)} 条线（面外部分）")
    return result


if __name__ == "__main__":
    # 定义目标坐标系
    TARGET_CRS = "EPSG:32643"  # 巴基斯坦UTM Zone 43N

    # 加载并处理OSM水系数据
    water_osm = gpd.read_file("G:/应急数据/巴基斯坦洪水7-13/water/GB_waterways.shp")
    # 确保数据有CRS，如果没有则设置
    if water_osm.crs is None:
        print("警告：OSM水系数据没有CRS，设置为", TARGET_CRS)
        water_osm = water_osm.set_crs(TARGET_CRS)
    # 转换为目标CRS
    water_osm = water_osm.to_crs(TARGET_CRS)
    water_osm = process_osm_data(water_osm)
    print(f"OSM数据CRS: {water_osm.crs}")
    water_osm.to_file("G:/应急数据/巴基斯坦洪水7-13/water/osm中间状态—final_rivers.shp")

    # 加载并处理水域面数据
    water_area = gpd.read_file("G:/应急数据/巴基斯坦洪水7-13/water/GB_water.shp")
    # 确保数据有CRS，如果没有则设置
    if water_area.crs is None:
        print("警告：水域面数据没有CRS，设置为", TARGET_CRS)
        water_area = water_area.set_crs(TARGET_CRS)
    # 转换为目标CRS
    water_area = water_area.to_crs(TARGET_CRS)
    print(f"水域面数据CRS: {water_area.crs}")

    # 加载并处理巴基斯坦水系数据
    water = gpd.read_file("G:/应急数据/巴基斯坦洪水7-13/water/waterways.shp")
    # 确保数据有CRS，如果没有则设置
    if water.crs is None:
        print("警告：巴基斯坦水系数据没有CRS，设置为", TARGET_CRS)
        water = water.set_crs(TARGET_CRS)
    # 转换为目标CRS
    water = water.to_crs(TARGET_CRS)
    print(f"巴基斯坦水系数据CRS: {water.crs}")

    water = process_water_data(water)
    # 确保处理后的数据仍有CRS
    water.crs = TARGET_CRS
    broken_water = split_features_in_gdf(water)
    print(f"打断后的水系数据CRS: {broken_water.crs}")
    broken_water.to_file("G:/应急数据/巴基斯坦洪水7-13/water/中间状态2—final_rivers.shp")

    # 创建空间索引
    idx = index.Index()
    # 融合数据
    fused_water = match_and_fuse_optimized(water_osm, broken_water, idx)
    # 确保融合后的数据有CRS
    fused_water.crs = TARGET_CRS
    fused_water_merge = merge_by_fid_and_code(fused_water)
    # 确保合并后的数据有CRS
    fused_water_merge.crs = TARGET_CRS
    print(f"融合并合并后的数据CRS: {fused_water_merge.crs}")
    fused_water_merge.to_file("G:/应急数据/巴基斯坦洪水7-13/water/final_rivers_alone.shp")

    # 裁剪并最终保存
    final_rivers = erase_lines_by_polygon(fused_water_merge, water_area)
    # 确保最终数据有CRS
    if final_rivers.crs is None:
        final_rivers = final_rivers.set_crs(TARGET_CRS)
    print(f"最终输出数据的CRS: {final_rivers.crs}")
    final_rivers.to_file("G:/应急数据/巴基斯坦洪水7-13/water/final_rivers.shp")
    print("处理完成! 湖泊外的河流已保存。")