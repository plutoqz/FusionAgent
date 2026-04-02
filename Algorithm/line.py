import numpy as np
import geopandas as gpd
from scipy.spatial.distance import directed_hausdorff
from shapely.geometry import LineString, Point, MultiPoint, MultiLineString
from shapely.ops import split, linemerge
from rtree import index
import logging
import math
import time
import pandas as pd

"""
   道路融合的最终代码
   作者:陈诺
   联系方式:13627482865
"""

# ----------------------
# 配置参数
# ----------------------
PAKISTAN_CRS = "EPSG:32643"  # 巴基斯坦 UTM Zone 43N
OSM_ID_START = 10000  # OSM ID 起始编号
TOLERANCE = 0.5  # 坐标容差（米）
SNAP_TOLERANCE = 1.0  # 端点捕捉容差（米）
ANGLE_THRESHOLD = 135  # 分割角度阈值（度）
BUFFER_DIST = 20  # 缓冲区半径（米），宽松匹配可适当增大
MAX_HAUSDORFF = 15  # 最大Hausdorff距离（米）

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ----------------------
# 分割相关函数
# ----------------------
def calculate_angle(p1, p2, p3):
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


# ----------------------
# 几何处理工具函数
# ----------------------
def snap_lines(lines, snap_tolerance):
    idx = index.Index()
    for i, line in enumerate(lines):
        idx.insert(i, line.bounds)

    snapped = []
    for i, line in enumerate(lines):
        coords = list(line.coords)
        start, end = Point(coords[0]), Point(coords[-1])

        near_start = list(idx.intersection(start.buffer(snap_tolerance).bounds))
        for j in near_start:
            if j == i:
                continue
            other_line = lines[j]
            if start.distance(other_line) <= snap_tolerance:
                new_start = other_line.interpolate(other_line.project(start))
                coords[0] = (new_start.x, new_start.y)

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
    idx = index.Index()
    for i, line in enumerate(lines):
        idx.insert(i, line.bounds)

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

    unique_points = []
    seen = set()
    for p in intersection_points:
        key = (round(p.x / tolerance), round(p.y / tolerance))
        if key not in seen:
            seen.add(key)
            unique_points.append(p)

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
        logger.error(f"合并失败: {e}")
        return lines


# ----------------------
# 数据处理主函数
# ----------------------
def process_osm_data(gdf):
    attr_records = []
    for _, row in gdf.iterrows():
        if not row.geometry.is_empty and isinstance(row.geometry, LineString):
            orig_attrs = row.to_dict()
            orig_attrs['original_geometry'] = orig_attrs['geometry']  # 原始几何
            # 记录原始 osm_id（如果存在）
            orig_attrs['osm_old'] = orig_attrs.get('osm_id')  # 新增：保存原始osm_id到osm_old
            attr_records.append(orig_attrs)

    if not attr_records:
        return gpd.GeoDataFrame(columns=['osm_id', 'osm_old', 'geometry'], crs=PAKISTAN_CRS)  # 新增osm_old列

    lines = [LineString(geom) for geom in gdf.geometry if not geom.is_empty and isinstance(geom, LineString)]
    lines = snap_lines(lines, SNAP_TOLERANCE)
    lines = planarize(lines, TOLERANCE)
    lines = merge_lines(lines)

    sindex = index.Index()
    for idx, orig_attr in enumerate(attr_records):
        sindex.insert(idx, orig_attr['original_geometry'].bounds)

    processed_data = []
    for new_osm_id, line in enumerate(lines, start=OSM_ID_START):
        max_overlap_ratio = 0.0
        matched_orig_idx = -1

        candidate_indices = list(sindex.intersection(line.bounds))
        for orig_idx in candidate_indices:
            orig_attr = attr_records[orig_idx]
            orig_line = orig_attr['original_geometry']

            if not line.intersects(orig_line):
                continue
            overlap = line.intersection(orig_line)
            overlap_length = overlap.length if overlap.geom_type in ['LineString', 'MultiLineString'] else 0.0
            current_line_length = line.length if line.length > 0 else 1e-9
            overlap_ratio = overlap_length / current_line_length

            if overlap_ratio > max_overlap_ratio:
                max_overlap_ratio = overlap_ratio
                matched_orig_idx = orig_idx

        if matched_orig_idx != -1:
            attrs = attr_records[matched_orig_idx].copy()
            attrs['geometry'] = line
            attrs['osm_id'] = new_osm_id  # 新生成的osm_id
            # 保留原始osm_id到osm_old（若原始记录有osm_id）
            attrs['osm_old'] = attrs.get('osm_old')  # 新增：从原始记录中获取osm_old
            attrs.pop('original_geometry')
        else:
            default_attrs = {k: None for k in attr_records[0].keys() if k != 'original_geometry'}
            default_attrs['geometry'] = line
            default_attrs['osm_id'] = new_osm_id
            default_attrs['osm_old'] = None  # 无原始OSM ID时设为None
            default_attrs['fclass'] = 'new_road'
            attrs = default_attrs

        processed_data.append(attrs)

    return gpd.GeoDataFrame(processed_data, crs=PAKISTAN_CRS)  # 输出包含osm_old列


def process_msft_data(gdf):
    original_records = []
    for _, row in gdf.iterrows():
        if not row.geometry.is_empty and isinstance(row.geometry, LineString):
            original_records.append({
                'original_FID_1': row['FID_1'],
                'original_geometry': row.geometry
            })

    if not original_records:
        return gpd.GeoDataFrame(columns=['FID_1', 'original_FID_1', 'geometry'], crs=PAKISTAN_CRS)

    lines = [LineString(geom) for geom in gdf.geometry if not geom.is_empty and isinstance(geom, LineString)]
    lines = snap_lines(lines, SNAP_TOLERANCE)
    lines = planarize(lines, TOLERANCE)
    lines = merge_lines(lines)

    sindex = index.Index()
    for idx, record in enumerate(original_records):
        sindex.insert(idx, record['original_geometry'].bounds)

    processed_data = []
    for new_fid, line in enumerate(lines, start=1):
        max_overlap_ratio = 0.0
        matched_original_FID = None

        candidate_indices = list(sindex.intersection(line.bounds))
        for orig_idx in candidate_indices:
            orig_record = original_records[orig_idx]
            orig_line = orig_record['original_geometry']

            if not line.intersects(orig_line):
                continue
            overlap = line.intersection(orig_line)
            overlap_length = overlap.length if overlap.geom_type in ['LineString', 'MultiLineString'] else 0.0
            current_line_length = line.length if line.length > 0 else 1e-9
            overlap_ratio = overlap_length / current_line_length

            if overlap_ratio > max_overlap_ratio:
                max_overlap_ratio = overlap_ratio
                matched_original_FID = orig_record['original_FID_1']

        processed_data.append({
            'FID_1': new_fid,
            'original_FID_1': matched_original_FID if matched_original_FID is not None else 'new',
            'geometry': line
        })

    return gpd.GeoDataFrame(processed_data, crs=PAKISTAN_CRS)


# ----------------------
# 几何计算工具函数
# ----------------------
def line_angle(line):
    coords = list(line.coords)
    dx = coords[-1][0] - coords[0][0]
    dy = coords[-1][1] - coords[0][1]
    return math.degrees(math.atan2(dy, dx)) % 180


def hausdorff_distance(line1, line2):
    coords1 = np.array(line1.coords)
    coords2 = np.array(line2.coords)
    return max(
        directed_hausdorff(coords1, coords2)[0],
        directed_hausdorff(coords2, coords1)[0]
    )


# ----------------------
# 匹配与融合主逻辑
# ----------------------
def match_and_fuse(gdf_osm, gdf_msft, idx):
    for fid in gdf_msft['FID_1']:
        geom = gdf_msft[gdf_msft['FID_1'] == fid].geometry.iloc[0]
        idx.insert(int(fid), geom.buffer(BUFFER_DIST).bounds)

    gdf_osm['label1'] = ''
    gdf_osm['label2'] = ''
    gdf_osm['label3'] = ''
    matched_msft_fids = set()

    for osm_id in gdf_osm['osm_id']:
        osm_row = gdf_osm[gdf_osm['osm_id'] == osm_id].iloc[0]
        osm_line = osm_row.geometry
        buffer_geom = osm_line.buffer(BUFFER_DIST)

        candidate_fids = list(idx.intersection(buffer_geom.bounds))
        for fid in candidate_fids:
            msft_road = gdf_msft[gdf_msft['FID_1'] == fid].iloc[0]
            msft_line = msft_road.geometry

            if buffer_geom.intersects(msft_line):
                hd = hausdorff_distance(osm_line, msft_line)
                if hd <= MAX_HAUSDORFF:
                    if gdf_osm.at[osm_row.name, 'label1']:
                        gdf_osm.at[osm_row.name, 'label1'] += f",{fid}"
                    else:
                        gdf_osm.at[osm_row.name, 'label1'] = str(fid)
                    matched_msft_fids.add(fid)
                else:
                    len_osm = osm_line.length
                    len_msft = msft_line.length
                    len_sim = min(len_osm, len_msft) / max(len_osm, len_msft)
                    angle_diff = abs(line_angle(osm_line) - line_angle(msft_line)) % 180
                    angle_diff = min(angle_diff, 180 - angle_diff)

                    if len_sim > 0.2 and angle_diff < 45:
                        if gdf_osm.at[osm_row.name, 'label2']:
                            gdf_osm.at[osm_row.name, 'label2'] += f",{fid}"
                        else:
                            gdf_osm.at[osm_row.name, 'label2'] = str(fid)
                        matched_msft_fids.add(fid)

    unmatched_msft = gdf_msft[~gdf_msft['FID_1'].isin(matched_msft_fids)]
    num_unmatched = len(unmatched_msft)
    num_matched = len(matched_msft_fids)
    num_completed = len(unmatched_msft)

    for index, row in unmatched_msft.iterrows():
        new_row = row.copy()
        new_row['osm_id'] = None
        new_row['label1'] = ''
        new_row['label2'] = ''
        new_row['label3'] = row['FID_1']
        new_row['fclass'] = 'ms_road'
        for col in gdf_osm.columns:
            if col not in new_row.index:
                new_row[col] = 0 if pd.api.types.is_numeric_dtype(gdf_osm[col]) else ''
        gdf_osm = pd.concat([gdf_osm, pd.DataFrame([new_row])], ignore_index=True)

    return gdf_osm, num_unmatched, num_matched, num_completed


# 后处理调整拓扑关系
def adjust_road_endpoints(gdfa, gdfb, buffer_radius=15):
    if gdfa.crs != gdfb.crs:
        gdfb = gdfb.to_crs(gdfa.crs)
    if gdfa.crs.is_geographic:
        raise ValueError("错误：数据必须为投影坐标系（单位：米）")

    sindex = gdfa.sindex
    new_features = []

    for index, row in gdfb.iterrows():
        line = row.geometry
        if line.geom_type != 'LineString':
            print(f"警告：要素 {index} 非线状几何，跳过调整")
            new_features.append(row)
            continue

        start_point = Point(line.coords[0])
        end_point = Point(line.coords[-1])

        def get_nearest_projection(point):
            buffer_geom = point.buffer(buffer_radius)
            intersect_ids = list(sindex.intersection(buffer_geom.bounds))
            candidates = gdfa.iloc[intersect_ids]
            candidates = candidates[candidates.geometry.intersects(buffer_geom)]

            if candidates.empty:
                return point, float('inf')

            min_dist = float('inf')
            nearest_proj = point
            for _, candidate in candidates.iterrows():
                proj_dist = candidate.geometry.project(point)
                proj_point = candidate.geometry.interpolate(proj_dist)
                dist = point.distance(proj_point)
                if dist < min_dist:
                    min_dist = dist
                    nearest_proj = proj_point
            return nearest_proj, min_dist

        start_proj, start_dist = get_nearest_projection(start_point)
        adjusted_start = start_proj if start_dist <= buffer_radius else start_point

        end_proj, end_dist = get_nearest_projection(end_point)
        adjusted_end = end_proj if end_dist <= buffer_radius else end_point

        new_coords = [adjusted_start] + list(line.coords[1:-1]) + [adjusted_end]
        new_line = LineString(new_coords)

        new_row = row.copy()
        new_row.geometry = new_line
        new_features.append(new_row)

    return gpd.GeoDataFrame(new_features, geometry='geometry', crs=gdfb.crs)


# 删除重复的道路
def process_roads(input_path, output_path, buffer_distance=10):
    print("正在读取数据...")
    start_time = time.time()
    gdf = gpd.read_file(input_path)

    gdfa = gdf[gdf['fclass'] != 'ms_road'].copy()
    gdfb = gdf[gdf['fclass'] == 'ms_road'].copy()
    print(f"原始数据：{len(gdf)}条，gdfa：{len(gdfa)}条，gdfb：{len(gdfb)}条")

    print("正在构建空间索引...")
    idx = index.Index()
    for fid, geometry in zip(gdfb['FID_1'], gdfb.geometry):
        idx.insert(int(fid), geometry.bounds)

    removed_fids = set()

    print("开始处理要素...")
    for i, a_feature in enumerate(gdfa.itertuples()):
        buffer_geom = a_feature.geometry.buffer(buffer_distance)
        candidate_ids = list(idx.intersection(buffer_geom.bounds))

        for fid in candidate_ids:
            b_feature = gdfb[gdfb['FID_1'] == fid].iloc[0]
            if buffer_geom.contains(b_feature.geometry) and \
               b_feature.geometry.length < a_feature.geometry.length:
                removed_fids.add(fid)

        if (i+1) % 100 == 0:
            print(f"已处理 {i+1}/{len(gdfa)} 要素，发现待删除：{len(removed_fids)}")

    print(f"共发现待删除要素：{len(removed_fids)}")
    gdfb_clean = gdfb[~gdfb['FID_1'].isin(removed_fids)]

    print("保存结果...")
    result_gdf = pd.concat([gdfa, gdfb_clean], ignore_index=True)

    if result_gdf.crs is None:
        print("警告：输入数据没有定义坐标系，默认使用假设的原始坐标系 EPSG:32643")
        result_gdf = result_gdf.set_crs("EPSG:32643")
    result_gdf = result_gdf.to_crs("EPSG:4326")

    result_gdf.to_file(output_path)

    print("\n被删除的FID_1列表：")
    print('\n'.join(map(str, sorted(removed_fids))))
    print(f"总耗时：{time.time()-start_time:.2f}秒")


def merge_connected_ms_roads(gdf, tolerance=SNAP_TOLERANCE):
    """合并fclass=ms_road中起点终点相连的线"""
    if 'fclass' not in gdf.columns:
        raise ValueError("缺少'fclass'字段，无法识别ms_road")

    # 筛选ms_road并提取几何
    ms_roads = gdf[gdf['fclass'] == 'ms_road'].copy()
    if len(ms_roads) == 0:
        return gdf

    # 捕捉端点（确保相连的端点在容差内）
    lines = [line for line in ms_roads.geometry if isinstance(line, LineString)]
    snapped_lines = snap_lines(lines, tolerance)  # 使用现有的snap_lines函数

    # 合并连续相连的线
    merged_lines = merge_lines(snapped_lines)  # 使用现有的merge_lines函数

    # 创建合并后的GeoDataFrame（保留必要属性）
    merged_ms = gpd.GeoDataFrame(
        data={'fclass': ['ms_road'] * len(merged_lines)},
        geometry=merged_lines,
        crs=gdf.crs
    )

    # 合并回原数据（删除原ms_road，添加合并后的）
    non_ms_roads = gdf[gdf['fclass'] != 'ms_road']
    final_gdf = pd.concat([non_ms_roads, merged_ms], ignore_index=True)
    return final_gdf


if __name__ == "__main__":
    start_time = time.time()
    # 加载数据
    gdf_osm = gpd.read_file("G:/演示数据/走廊数据/gis_osm_roads_free_1.shp").to_crs(PAKISTAN_CRS)
    gdf_msft = gpd.read_file("G:/演示数据/走廊数据/MS_PK_Road.shp").to_crs(PAKISTAN_CRS)

    # 处理 OSM 数据
    logger.info("开始处理 OSM 数据...")
    osm_processed = process_osm_data(gdf_osm)
    osm_processed.to_file("G:/演示数据/走廊数据/osm_preprocessed.shp")
    logger.info(f"OSM 处理完成：原始 {len(gdf_osm)} 条 → 处理后 {len(osm_processed)} 条")
    logger.info(f"osm_id 范围: {osm_processed['osm_id'].min()}~{osm_processed['osm_id'].max()}")

    # 分割 OSM 数据
    logger.info("开始分割 OSM 数据...")
    if 'centroid' in osm_processed.columns:
        osm_processed = osm_processed.drop(columns=['centroid'], errors='ignore')
        logger.info("已删除 OSM 数据中的 'centroid' 列")
    osm_processed = osm_processed.set_geometry('geometry')
    osm_split = split_features_in_gdf(osm_processed, angle_threshold=ANGLE_THRESHOLD)
    osm_split_output = "G:/演示数据/走廊数据/split_osm_roads.shp"
    osm_split.to_file(osm_split_output)
    logger.info(f"OSM 分割完成：处理后 {len(osm_split)} 条")
    logger.info(f"分割结果已保存至：{osm_split_output}")

    # 处理微软数据
    logger.info("开始处理微软数据...")
    msft_processed = process_msft_data(gdf_msft)
    msft_processed.to_file("G:/演示数据/走廊数据/msft_preprocessed.shp")
    logger.info(f"微软处理完成：原始 {len(gdf_msft)} 条 → 处理后 {len(msft_processed)} 条")
    logger.info(f"FID_1 范围: {msft_processed['FID_1'].min()}~{msft_processed['FID_1'].max()}")

    # 分割微软数据
    logger.info("开始分割微软数据...")
    if 'centroid' in msft_processed.columns:
        msft_processed = msft_processed.drop(columns=['centroid'], errors='ignore')
        logger.info("已删除微软数据中的 'centroid' 列")
    msft_processed = msft_processed.set_geometry('geometry')
    msft_split = split_features_in_gdf(msft_processed, angle_threshold=ANGLE_THRESHOLD)
    msft_split_output = "G:/演示数据/走廊数据/split_msft_roads.shp"
    msft_split.to_file(msft_split_output)
    logger.info(f"微软分割完成：处理后 {len(msft_split)} 条")
    logger.info(f"分割结果已保存至：{msft_split_output}")

    # 匹配
    gdf_osm = gpd.read_file("G:/演示数据/走廊数据/split_osm_roads.shp")
    gdf_msft = gpd.read_file("G:/演示数据/走廊数据/split_msft_roads.shp")

    num_original_osm = len(gdf_osm)
    num_original_ms = len(gdf_msft)
    idx = index.Index()
    # 执行匹配融合
    fused_roads, num_unmatched, num_matched, num_completed = match_and_fuse(gdf_osm, gdf_msft, idx)

    # 输出结果（保持OSM属性结构）
    fused_roads.to_file("G:/演示数据/走廊数据/fused_roads_final.shp")

    print(f"原始OSM道路数量: {num_original_osm}")
    print(f"原始微软道路数量: {num_original_ms}")
    print(f"匹配的微软道路数量: {num_matched}")
    print(f"未匹配的微软道路数量: {num_unmatched}")
    print(f"补全的道路数量: {num_completed}")
    end_time = time.time()
    run_time = end_time - start_time
    print(f"程序运行时间: {run_time:.2f} 秒")

    # 处理重复的道路
    input_file = "G:/演示数据/走廊数据/fused_roads_final.shp"
    output_file = "G:/演示数据/走廊数据/data/processed_roads.shp"

    process_roads(
        input_path=input_file,
        output_path=output_file,
        buffer_distance=15
    )
    logger.info(f"重复道路已处理")

    try:
        file_path = r'G:/演示数据/走廊数据/data/processed_roads.shp'
        gdf = gpd.read_file(file_path)
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:32643")  # 修改为43N坐标系
        gdfa = gdf[gdf['fclass'] != 'ms_road']
        gdfb = gdf[gdf['fclass'] == 'ms_road']

        target_crs = "EPSG:32643"  # 修改为43N坐标系
        gdfa = gdfa.to_crs(target_crs)
        gdfb = gdfb.to_crs(target_crs)

        gdfb_adjusted = adjust_road_endpoints(gdfa, gdfb, buffer_radius=15)
        gdfa_adjusted = adjust_road_endpoints(gdfb_adjusted, gdfa, buffer_radius=15)
        print('开始删除')

        buffer_distance = 10
        gdfa_buffer = gdfa_adjusted.copy()
        gdfa_buffer.geometry = gdfa_adjusted.geometry.buffer(buffer_distance)
        gdfa_buffer_sindex = gdfa_buffer.sindex

        to_delete = []
        for index_b, row_b in gdfb_adjusted.iterrows():
            line_b = row_b.geometry
            possible_matches_index = list(gdfa_buffer_sindex.intersection(line_b.bounds))
            possible_matches = gdfa_buffer.iloc[possible_matches_index]
            for index_a, row_a in possible_matches.iterrows():
                buffer_a = row_a.geometry
                if line_b.within(buffer_a) and line_b.length < gdfa_adjusted.loc[index_a].geometry.length:
                    to_delete.append(index_b)
                    break

        gdfb_adjusted = gdfb_adjusted.drop(to_delete)

        final_gdf = pd.concat([gdfa_adjusted, gdfb_adjusted], ignore_index=True)
        final_output_file = r'G:/演示数据/走廊数据/data/final_processed_roads.shp'
        final_gdf.to_file(final_output_file)

        print(f"已完成处理，最终结果保存至：{final_output_file}")
        print(f"最终要素数量：{len(final_gdf)}")

    except FileNotFoundError:
        print(f"错误：未找到文件 {file_path}")
    except KeyError:
        print("错误：缺少 'fclass' 字段")
    except Exception as e:
        print(f"处理失败：{str(e)}")