from rtree import index
import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon, Point
from shapely.geometry import Point, LineString, MultiPoint
import numpy as np
from shapely.geometry import box
import logging
import sys

"""
   建筑物融合的最终代码
   作者:陈诺
   联系方式:13627482865
"""

def add_index_column(gdf):
    """
    为 GeoDataFrame 添加索引列。

    参数:
    gdf (GeoDataFrame): 要添加索引列的 GeoDataFrame。

    返回:
    GeoDataFrame: 添加了索引列的 GeoDataFrame。
    """
    if gdf is None:
        raise ValueError("传入的 GeoDataFrame 不能为空。")

    gdf['idx'] = range(0, len(gdf))
    return gdf


def add_index_column1(gdf):
    """
    为 GeoDataFrame 添加索引列。

    参数:
    gdf (GeoDataFrame): 要添加索引列的 GeoDataFrame。

    返回:
    GeoDataFrame: 添加了索引列的 GeoDataFrame。
    """
    if gdf is None:
        raise ValueError("传入的 GeoDataFrame 不能为空。")

    gdf['idx1'] = range(0, len(gdf))
    return gdf


def find_non_intersecting_buildings(gdf1, gdf2):
    """
    查找gdf1中与gdf2中所有建筑物都不相交的建筑物

    参数:
    gdf1 (GeoDataFrame): 第一个包含建筑物几何信息的GeoDataFrame
    gdf2 (GeoDataFrame): 第二个包含建筑物几何信息的GeoDataFrame

    返回:
    GeoDataFrame: 包含所有在gdf1中但与gdf2中所有建筑物都不相交的建筑物
    """
    # 为gdf2创建空间索引
    sindex = gdf2.sindex

    # 创建一个空的GeoDataFrame用于存储结果
    non_intersecting = gpd.GeoDataFrame(columns=gdf1.columns, crs=gdf1.crs)

    # 遍历gdf1中的每一个建筑物
    for idx, building in gdf1.iterrows():
        # 获取当前建筑物的边界框
        bbox = building.geometry.bounds

        # 使用空间索引查找可能与当前建筑物相交的gdf2中的建筑物索引
        possible_matches_index = list(sindex.intersection(bbox))

        # 获取可能匹配的建筑物
        possible_matches = gdf2.iloc[possible_matches_index]

        # 初始化相交标志
        intersects = False

        # 检查是否有实际相交的建筑物
        for _, match in possible_matches.iterrows():
            if building.geometry.intersects(match.geometry):
                intersects = True
                break

        # 如果没有相交的建筑物，则将其添加到结果中
        if not intersects:
            non_intersecting = pd.concat([non_intersecting, gdf1.loc[[idx]]])
        non_intersecting['idx1'] = 0
        gdf_osm_nomatch1 =  non_intersecting[['idx', 'idx1', 'osm_id', 'fclass', 'name', 'type', 'geometry']]

    return gdf_osm_nomatch1


def find_non_intersecting_buildings1(gdf1, gdf2):
    """
    查找gdf1中与gdf2中所有建筑物都不相交的建筑物

    参数:
    gdf1 (GeoDataFrame): 第一个包含建筑物几何信息的GeoDataFrame
    gdf2 (GeoDataFrame): 第二个包含建筑物几何信息的GeoDataFrame

    返回:
    GeoDataFrame: 包含所有在gdf1中但与gdf2中所有建筑物都不相交的建筑物
    """
    # 为gdf2创建空间索引
    sindex = gdf2.sindex

    # 创建一个空的GeoDataFrame用于存储结果
    non_intersecting = gpd.GeoDataFrame(columns=gdf1.columns, crs=gdf1.crs)

    # 遍历gdf1中的每一个建筑物
    for idx, building in gdf1.iterrows():
        # 获取当前建筑物的边界框
        bbox = building.geometry.bounds

        # 使用空间索引查找可能与当前建筑物相交的gdf2中的建筑物索引
        possible_matches_index = list(sindex.intersection(bbox))

        # 获取可能匹配的建筑物
        possible_matches = gdf2.iloc[possible_matches_index]

        # 初始化相交标志
        intersects = False

        # 检查是否有实际相交的建筑物
        for _, match in possible_matches.iterrows():
            if building.geometry.intersects(match.geometry):
                intersects = True
                break

        # 如果没有相交的建筑物，则将其添加到结果中
        if not intersects:
            non_intersecting = pd.concat([non_intersecting, gdf1.loc[[idx]]])
        non_intersecting['idx'] = 0
        gdf_ms_nomatch1 =  non_intersecting[['idx', 'idx1', 'Height', 'geometry']]

    return gdf_ms_nomatch1


def calculate_similarity(gdf2, gdf3):
    """
    计算 gdf3 中每个几何体与 gdf2 中相交几何体的叠加相似度。

    参数:
    gdf2 (GeoDataFrame): 第一个矢量数据集，包含 'idx' 列。
    gdf3 (GeoDataFrame): 第二个矢量数据集，包含 'idx1' 列。

    返回:
    list: 每个 gdf3 几何体的相似度列表，格式为 (gdf3_idx, gdf2_idx, similarity)。
    """
    similarities = []

    # 创建 R 树索引
    rtree_index = index.Index()
    for idx, geometry in enumerate(gdf2.geometry):
        rtree_index.insert(idx, geometry.bounds)

    for idx1 in gdf3['idx1']:  # 修改为 idx1
        geom3 = gdf3.geometry[gdf3['idx1'] == idx1].values[0]  # 修改为 idx1

        # 查询与 geom3 相交的 gdf2 中的几何体
        bounds = geom3.bounds
        intersecting_indices = list(rtree_index.intersection(bounds))

        for idx2 in intersecting_indices:
            geom2 = gdf2.geometry[idx2]

            # 计算相交区域
            intersection = geom3.intersection(geom2)
            if not intersection.is_empty:
                area_intersection = intersection.area
                area_gdf3 = geom3.area
                area_gdf2 = geom2.area

                # 计算相似度
                similarity = area_intersection / min(area_gdf3, area_gdf2)
                similarities.append((idx1, gdf2['idx'].iloc[idx2], similarity, area_intersection))

    similarity_gdf = gpd.GeoDataFrame(similarities, columns=['idx1', 'idx', 'similarity', 'overlap_area'])
    return similarities, similarity_gdf


def calculate_similarity(gdf2, gdf3):
    """
    计算 gdf3 中每个几何体与 gdf2 中相交几何体的叠加相似度。

    参数:
    gdf2 (GeoDataFrame): 第一个矢量数据集，包含 'idx' 列。
    gdf3 (GeoDataFrame): 第二个矢量数据集，包含 'idx1' 列。

    返回:
    list: 每个 gdf3 几何体的相似度列表，格式为 (gdf3_idx, gdf2_idx, similarity)。
    """
    similarities = []

    # 创建R树索引，使用行号作为索引ID
    rtree_index = index.Index()
    for i, (idx, geometry) in enumerate(zip(gdf2['idx'], gdf2.geometry)):
        rtree_index.insert(i, geometry.bounds)  # 使用行号i作为索引ID

    for idx1 in gdf3['idx1']:
        # 获取当前几何体
        geom3 = gdf3.geometry[gdf3['idx1'] == idx1].values[0]

        # 查询与geom3相交的gdf2中的几何体
        bounds = geom3.bounds
        intersecting_indices = list(rtree_index.intersection(bounds))

        for i in intersecting_indices:  # 这里i是行号，不是gdf2['idx']的值
            # 使用iloc按行号访问几何体
            geom2 = gdf2.geometry.iloc[i]
            gdf2_idx = gdf2['idx'].iloc[i]  # 获取对应的idx值

            # 计算相交区域
            intersection = geom3.intersection(geom2)
            if not intersection.is_empty:
                area_intersection = intersection.area
                area_gdf3 = geom3.area
                area_gdf2 = geom2.area

                # 计算相似度
                similarity = area_intersection / min(area_gdf3, area_gdf2)
                similarities.append((idx1, gdf2_idx, similarity, area_intersection))

    # 创建结果GeoDataFrame
    similarity_gdf = gpd.GeoDataFrame(similarities, columns=['idx1', 'idx', 'similarity', 'overlap_area'])
    return similarities, similarity_gdf


def attribute_fusion(gdf):
    """
   修改融合后的属性表
   参数:
   gdf：融合后的地理数据框
   若匹配成功保留osm几何特征
   若未匹配成功保留gg建筑物属性特征
   """
    gdf_attr = gdf[
        ['idx', 'idx1', 'similarity', 'overlap_area', 'label', 'longitude', 'latitude', 'area_in_me', 'geometry_x',
         'fclass', 'type',
         'osm_id', 'geometry_y']]
    # 若匹配成果（label==1），则将gg的几何列赋值为osm的几何列
    gdf_attr.loc[gdf_attr['label'] == '1', 'geometry_y'] = gdf_attr.loc[gdf_attr['label'] == '1', 'geometry_x']
    # 删除 geometry_x 列
    gdf_attr = gdf_attr.drop(columns=['geometry_x'])
    # 删除未匹配成功的列
    gdf_attr = gdf_attr[~(gdf_attr['osm_id'].notna() & gdf_attr['idx1'].isna())]
    # 将 geometry_y 重命名为 geometry
    gdf_attr = gdf_attr.rename(columns={'geometry_y': 'geometry'})
    # 设置 geometry 列为地理空间列
    gdf_attr = gdf_attr.set_geometry('geometry')
    return gdf_attr


def get_b_data_var(shp_B):
    shp_B = shp_B.reset_index(drop=True)
    shp_B['B_MLeng'] = None;
    shp_B['B_MWide'] = None;
    shp_B['B_orient'] = None  # 初始化新字段
    for i in range(len(shp_B.geometry)):
        x, y = shp_B.geometry[i].minimum_rotated_rectangle.exterior.coords.xy
        MBR_length = (Point(x[0], y[0]).distance(Point(x[1], y[1])), Point(x[1], y[1]).distance(Point(x[2], y[2])))
        shp_B.loc[i, 'B_MLeng'] = max(MBR_length)  # 短边
        shp_B.loc[i, 'B_MWide'] = min(MBR_length)  # 长边
        coords = [c for c in shp_B.geometry[i].minimum_rotated_rectangle.boundary.coords]
        segments = [LineString([a, b]) for a, b in
                    zip(coords, coords[1:])]  # 变成这样了[((x1,y1),(x2,y2)),((x2,y2),(x3,y3))]
        longest_segment = max(segments, key=lambda x: x.length)  # 找到最长的边
        p1, p2 = [c for c in longest_segment.coords]
        angle = 1000 if p2[0] == p1[0] else np.divide(p2[1] - p1[1], p2[0] - p1[0])
        shp_B.loc[i, 'B_orient'] = angle  # 直接赋值，不调用 copy()
    shp_B['centroid'] = shp_B.centroid
    shp_B['B_x'] = shp_B.centroid.x
    shp_B['B_y'] = shp_B.centroid.y
    shp_B['B_area'] = shp_B.area
    shp_B['B_perime'] = shp_B.length
    shp_B['MABR_area'] = pd.DataFrame([shp_B.geometry[i].minimum_rotated_rectangle.area for i in range(len(shp_B))])
    shp_B['MABR_len'] = pd.DataFrame([shp_B.geometry[i].minimum_rotated_rectangle.length for i in range(len(shp_B))])
    BGeOut = gpd.GeoDataFrame(shp_B, crs=shp_B.crs, geometry=shp_B.geometry)
    return shp_B, BGeOut

def get_data_var(shp_G):
    """
    计算GeoDataFrame中两种几何形状的多种几何特征

    参数:
    shp_G (GeoDataFrame): 输入数据，包含'geometry_x'和'geometry_y'两列几何形状

    返回:
    GeoDataFrame: 包含所有计算的几何特征
    """
    shp_G = shp_G.reset_index(drop=True)

    # 为geometry_x计算特征 (G_前缀)
    for i, row in shp_G.iterrows():
        geom_x = row['geometry_x']

        # 计算最小旋转矩形的长宽
        x, y = geom_x.minimum_rotated_rectangle.exterior.coords.xy
        mbr_lengths = (Point(x[0], y[0]).distance(Point(x[1], y[1])),
                       Point(x[1], y[1]).distance(Point(x[2], y[2])))
        shp_G.loc[i, 'G_MLeng'] = max(mbr_lengths)
        shp_G.loc[i, 'G_MWide'] = min(mbr_lengths)

        # 计算方向角
        coords = [c for c in geom_x.minimum_rotated_rectangle.boundary.coords]
        segments = [LineString([a, b]) for a, b in zip(coords, coords[1:])]
        longest_segment = max(segments, key=lambda x: x.length)
        p1, p2 = [c for c in longest_segment.coords]
        angle = 1000 if p2[0] == p1[0] else np.divide(p2[1] - p1[1], p2[0] - p1[0])
        shp_G.loc[i, 'G_orient'] = angle

    # 为geometry_x计算其他特征
    shp_G['G_centroid'] = shp_G['geometry_x'].centroid
    shp_G['G_x'] = shp_G['G_centroid'].x
    shp_G['G_y'] = shp_G['G_centroid'].y
    shp_G['G_area'] = shp_G['geometry_x'].area
    shp_G['G_perime'] = shp_G['geometry_x'].length
    shp_G['G_MABR_area'] = shp_G['geometry_x'].apply(lambda g: g.minimum_rotated_rectangle.area)
    shp_G['G_MABR_length'] = shp_G['geometry_x'].apply(lambda g: g.minimum_rotated_rectangle.length)

    # 为geometry_y计算特征 (B_前缀)
    for i, row in shp_G.iterrows():
        geom_y = row['geometry_y']

        # 计算最小旋转矩形的长宽
        x, y = geom_y.minimum_rotated_rectangle.exterior.coords.xy
        mbr_lengths = (Point(x[0], y[0]).distance(Point(x[1], y[1])),
                       Point(x[1], y[1]).distance(Point(x[2], y[2])))
        shp_G.loc[i, 'B_MLeng'] = max(mbr_lengths)
        shp_G.loc[i, 'B_MWide'] = min(mbr_lengths)

        # 计算方向角
        coords = [c for c in geom_y.minimum_rotated_rectangle.boundary.coords]
        segments = [LineString([a, b]) for a, b in zip(coords, coords[1:])]
        longest_segment = max(segments, key=lambda x: x.length)
        p1, p2 = [c for c in longest_segment.coords]
        angle = 1000 if p2[0] == p1[0] else np.divide(p2[1] - p1[1], p2[0] - p1[0])
        shp_G.loc[i, 'B_orient'] = angle

    # 为geometry_y计算其他特征
    shp_G['B_centroid'] = shp_G['geometry_y'].centroid
    shp_G['B_x'] = shp_G['B_centroid'].x
    shp_G['B_y'] = shp_G['B_centroid'].y
    shp_G['B_area'] = shp_G['geometry_y'].area
    shp_G['B_perime'] = shp_G['geometry_y'].length
    shp_G['B_MABR_area'] = shp_G['geometry_y'].apply(lambda g: g.minimum_rotated_rectangle.area)
    shp_G['B_MABR_length'] = shp_G['geometry_y'].apply(lambda g: g.minimum_rotated_rectangle.length)

    # 返回单个GeoDataFrame，保留原始几何列
    return shp_G

def get_a_data_var(shp_G):
    shp_G = shp_G.reset_index(drop=True)
    shp_G['G_MLeng'] = None
    shp_G['G_MWide'] = None
    shp_G['G_orient'] = None
    for i in range(len(shp_G.geometry)):
        x, y = shp_G.geometry[i].minimum_rotated_rectangle.exterior.coords.xy
        MBR_length = (Point(x[0], y[0]).distance(Point(x[1], y[1])), Point(x[1], y[1]).distance(Point(x[2], y[2])))
        shp_G.loc[i, 'G_MLeng'] = max(MBR_length)
        shp_G.loc[i, 'G_MWide'] = min(MBR_length)
        coords = [c for c in shp_G.geometry[i].minimum_rotated_rectangle.boundary.coords]
        segments = [LineString([a, b]) for a, b in zip(coords, coords[1:])]
        longest_segment = max(segments, key=lambda x: x.length)
        p1, p2 = [c for c in longest_segment.coords]
        angle = 1000 if p2[0] == p1[0] else np.divide(p2[1] - p1[1], p2[0] - p1[0])
        shp_G.loc[i, 'G_orient'] = angle
    shp_G['centroid'] = shp_G.centroid
    shp_G['G_x'] = shp_G.centroid.x
    shp_G['G_y'] = shp_G.centroid.y
    shp_G['G_area'] = shp_G.area
    shp_G['G_perime'] = shp_G.length
    shp_G['MABR_area'] = pd.DataFrame([shp_G.geometry[i].minimum_rotated_rectangle.area for i in range(len(shp_G))])
    shp_G['MABR_length'] = pd.DataFrame([shp_G.geometry[i].minimum_rotated_rectangle.length for i in range(len(shp_G))])
    # 修改形状相似度
    GGeOut = gpd.GeoDataFrame(shp_G, crs=shp_G.crs, geometry=shp_G.geometry)
    return shp_G, GGeOut

def get_sim(filterd_gdf):
    filterd_gdf = filterd_gdf.copy()
    G_x = filterd_gdf['G_x']
    G_y = filterd_gdf['G_y']
    G_area = filterd_gdf['G_area']
    G_orient = filterd_gdf['G_orient'].convert_dtypes()
    B_x = filterd_gdf['B_x']
    B_y = filterd_gdf['B_y']
    B_area = filterd_gdf['B_area']
    B_orient = filterd_gdf['B_orient'].convert_dtypes()
    area_overlap = filterd_gdf['overlap_area']
    B_L_W_Ratio = np.divide(filterd_gdf['B_MLeng'], filterd_gdf['B_MWide'])
    G_L_W_Ratio = np.divide(filterd_gdf['G_MLeng'], filterd_gdf['G_MWide'])
    filterd_gdf['sim_location'] = np.sqrt(np.square(G_x - B_x) + np.square(G_y - B_y))
    filterd_gdf['sim_location'] = 1 - (filterd_gdf['sim_location'] / 70)
    filterd_gdf['sim_area'] = np.divide(np.amin([[G_area, B_area]], axis=1),
                                        np.amax([[G_area, B_area]], axis=1)).flatten()
    filterd_gdf['sim_overlap'] = np.divide(area_overlap, np.maximum(G_area, B_area))
    filterd_gdf['sim_orient'] = np.abs(np.arctan(np.divide(abs(G_orient - B_orient), (1 + G_orient * B_orient))))
    filterd_gdf['sim_shape'] = np.divide(np.amin([[B_L_W_Ratio, G_L_W_Ratio]], axis=1),
                                         np.amax([[B_L_W_Ratio, G_L_W_Ratio]], axis=1)).flatten()
    # filterd_gdf['sim_shape'] = 1 - (np.divide(abs(B_L_W_Ratio - G_L_W_Ratio), (B_L_W_Ratio + G_L_W_Ratio)))
    filterd_gdf['sim_shape'] = filterd_gdf['sim_shape'].astype('float64')
    GB_sim = gpd.GeoDataFrame(filterd_gdf)

    return GB_sim


def get_feature(gdf1, gdf2):
    gdf1 = gdf1.to_crs(epsg=32643)
    gdf2 = gdf2.to_crs(epsg=32643)
    add_index_column(gdf1)
    add_index_column1(gdf2)
    shp_a, a_c = get_a_data_var(gdf1)
    shp_b, b_c = get_b_data_var(gdf2)
    similarity1, similarity_gdf = calculate_similarity(a_c, b_c)
    merged_gdf = similarity_gdf.merge(b_c, left_on='idx', right_on='idx1', how='left', suffixes=('', '_gdf1'))
    merged_gdf = merged_gdf.merge(a_c, left_on='idx1', right_on='idx', how='left', suffixes=('', '_gdf2'))
    filtered_gdf = merged_gdf[merged_gdf['similarity'] >= 0.4]
    sim_gdf = get_sim(filtered_gdf)
    train = sim_gdf[['idx1', 'idx', 'sim_location', 'sim_area', 'sim_orient', 'sim_shape', 'sim_overlap']]
    return train


def split_relations(gdf):
    """
    将 GeoDataFrame 按 idx 和 idx1 的对应关系分成四类：
    1:1、1:N、N:1、M:N
    """
    # Step 1: 计算每个 idx 和 idx1 的对应数量
    gdf['idx_count'] = gdf.groupby('idx')['idx1'].transform('nunique')  # 每个 idx 对应的 idx1 数量
    gdf['idx1_count'] = gdf.groupby('idx1')['idx'].transform('nunique')  # 每个 idx1 对应的 idx 数量

    # Step 2: 判断是否为 1:1 关系
    mask_1to1 = (gdf['idx_count'] == 1) & (gdf['idx1_count'] == 1)
    gdf_1to1 = gdf[mask_1to1].copy()

    # Step 3: 判断是否为 1:N 关系
    # 每个 idx 对应的所有 idx1 必须只被该 idx 指向
    idx_1n_mask = gdf.groupby('idx')['idx1_count'].transform(lambda x: (x == 1).all())
    mask_1ton = (gdf['idx_count'] > 1) & idx_1n_mask
    gdf_1ton = gdf[mask_1ton].copy()

    # Step 4: 判断是否为 N:1 关系
    # 每个 idx1 对应的所有 idx 必须只指向该 idx1
    idx1_n1_mask = gdf.groupby('idx1')['idx_count'].transform(lambda x: (x == 1).all())
    mask_nto1 = (gdf['idx1_count'] > 1) & idx1_n1_mask
    gdf_nto1 = gdf[mask_nto1].copy()

    # Step 5: 剩余为 M:N 关系
    mask_mton = ~mask_1to1 & ~mask_1ton & ~mask_nto1
    gdf_mton = gdf[mask_mton].copy()

    return gdf_1to1, gdf_1ton, gdf_nto1, gdf_mton


def add_relation_columns(gdf_1ton, gdf_nto1, gdf_mton):
    """
    为三种关系类型的GeoDataFrame添加关联ID列
    参数:
        gdf_1ton: 1:N关系的GeoDataFrame
        gdf_nto1: N:1关系的GeoDataFrame
        gdf_mton: M:N关系的GeoDataFrame
    返回:
        处理后的三个GeoDataFrame
    """

    # 处理1:N关系 - 添加related_idx1列
    if not gdf_1ton.empty:
        gdf_1ton['related_idx1'] = gdf_1ton.groupby('idx')['idx1'] \
            .transform(lambda x: ','.join(map(str, x.unique())))

    # 处理N:1关系 - 添加related_idx列
    if not gdf_nto1.empty:
        gdf_nto1['related_idx'] = gdf_nto1.groupby('idx1')['idx'] \
            .transform(lambda x: ','.join(map(str, x.unique())))

    # 处理M:N关系 - 添加两列
    if not gdf_mton.empty:
        gdf_mton['related_idx'] = gdf_mton.groupby('idx1')['idx'] \
            .transform(lambda x: ','.join(map(str, x.unique())))
        gdf_mton['related_idx1'] = gdf_mton.groupby('idx')['idx1'] \
            .transform(lambda x: ','.join(map(str, x.unique())))

    return gdf_1ton, gdf_nto1, gdf_mton


def one_to_one_filter(gpd):
    filter_1to1_gdf = gpd[(gdf_1to1_result['sim_area'] < 0.3) |
                          (gdf_1to1_result['sim_shape'] < 0.3) |
                          (gdf_1to1_result['sim_overlap'] < 0.3)]
    gdf_1to1_result1 = gpd[(gdf_1to1_result['sim_area'] >= 0.3) &
                           (gdf_1to1_result['sim_shape'] >= 0.3) &
                           (gdf_1to1_result['sim_overlap'] >= 0.3)]
    return filter_1to1_gdf, gdf_1to1_result1


def attribute_fusion1(gdf):
    """
   修改融合后的属性表
   参数:
   gdf：融合后的地理数据框
   若匹配成功保留osm几何特征
   若未匹配成功保留gg建筑物属性特征
   """
    gdf_attr = gdf[
        ['idx', 'idx1', 'label', 'longitude', 'latitude', 'area_in_me', 'confidence', 'fclass', 'type', 'name',
         'geometry_y']]
    # 将 geometry_y 重命名为 geometry
    gdf_attr = gdf_attr.rename(columns={'geometry_y': 'geometry'})
    # 设置 geometry 列为地理空间列
    gdf_attr = gdf_attr.set_geometry('geometry')
    return gdf_attr


def attribute_fusion2(gdf):
    # 是否需要删除重复
    gdf_attr = gdf[
        ['idx', 'idx1', 'label', 'longitude', 'latitude', 'area_in_me', 'confidence', 'fclass', 'type', 'name',
         'geometry_y']]
    # 将 geometry_y 重命名为 geometry
    gdf_attr = gdf_attr.rename(columns={'geometry_y': 'geometry'})
    # 设置 geometry 列为地理空间列
    gdf_attr = gdf_attr.set_geometry('geometry')
    return gdf_attr


def attribute_fusion3(gdf):
    """
    可以选择(予以修改，保留gg数据)
    # 一个谷歌对应多个osm，保留osm。（是否还要计算一个变量，计算位移量）
    :param gdf:
    :return:
    """
    gdf_attr = gdf[
        ['idx', 'idx1', 'label', 'longitude', 'latitude', 'area_in_me', 'confidence', 'fclass', 'type', 'name',
         'geometry_y']] # 若是要保留微软建筑，使用geomerty_x即可
    # 将 geometry_y 重命名为 geometry
    gdf_attr = gdf_attr.rename(columns={'geometry_y': 'geometry'})
    # 设置 geometry 列为地理空间列
    gdf_attr = gdf_attr.set_geometry('geometry')
    return gdf_attr


def attribute_fusion4(gdf):
    """
    一个谷歌对应多个osm，保留osm。（是否还要计算一个变量，计算位移量）
    :param gdf:
    :return:
    """
    gdf_attr = gdf[
        ['idx', 'idx1', 'label', 'longitude', 'latitude', 'area_in_me', 'confidence', 'fclass', 'type', 'name',
         'geometry_y']]
    # 将 geometry_y 重命名为 geometry
    gdf_attr = gdf_attr.rename(columns={'geometry_y': 'geometry'})
    # 设置 geometry 列为地理空间列
    gdf_attr = gdf_attr.set_geometry('geometry')
    return gdf_attr


def attribute_fusion5(gdf):
    """
    一个谷歌对应多个osm，保留osm。（是否还要计算一个变量，计算位移量）
    :param gdf:
    :return:
    """
    gdf_attr = gdf[
        ['idx', 'idx1', 'label', 'longitude', 'latitude', 'area_in_me', 'confidence', 'fclass', 'type', 'name',
         'geometry_y']]
    # 将 geometry_y 重命名为 geometry
    gdf_attr = gdf_attr.rename(columns={'geometry_y': 'geometry'})
    # 设置 geometry 列为地理空间列
    # 清空 fclass 和 type 列
    gdf_attr['fclass'] = np.nan
    gdf_attr['type'] = np.nan
    gdf_attr['idx'] = np.nan
    gdf_attr['name'] = np.nan
    gdf_attr = gdf_attr.set_geometry('geometry')
    return gdf_attr


def attribute_fusion6(gdf):
    """
     补全高度属性
   """
    gdf_attr = gdf[
        ['idx', 'idx1', 'longitude', 'latitude', 'area_in_me', 'confidence', 'fclass', 'type', 'name', 'Height',
         'geometry_x']]
    # 将 geometry_y 重命名为 geometry
    gdf_attr = gdf_attr.rename(columns={'geometry_x': 'geometry'})
    # 设置 geometry 列为地理空间列
    gdf_attr = gdf_attr.set_geometry('geometry')
    return gdf_attr


def attribute_fusion7(gdf):
    gdf_attr = gdf[
        ['idx', 'idx1', 'longitude', 'latitude', 'area_in_me', 'confidence', 'fclass', 'type', 'name', 'Height',
         'geometry_x']]
    # 将 geometry_y 重命名为 geometry
    gdf_attr = gdf_attr.rename(columns={'geometry_x': 'geometry'})
    # 设置 geometry 列为地理空间列
    # 清空 fclass 和 type 列
    gdf_attr['fclass'] = np.nan
    gdf_attr['type'] = np.nan
    gdf_attr['idx'] = np.nan
    gdf_attr['name'] = np.nan
    gdf_attr['Height'] = np.nan
    gdf_attr = gdf_attr.set_geometry('geometry')
    return gdf_attr


def attribute_fusion8(gdf):
    """
    多个建筑匹配上一个3d建筑，高度补全,多对1，高度取平均值
    """
    # 选择需要的列
    gdf_attr = gdf[
        ['idx', 'idx1', 'label', 'longitude', 'latitude', 'area_in_me', 'confidence', 'fclass', 'type', 'name',
         'Height', 'geometry_x']]

    # 按idx分组，并计算Height的平均值
    grouped = gdf_attr.groupby('idx').agg({
        'Height': 'mean',
        'idx1': 'first',
        'label': 'first',
        'longitude': 'first',
        'latitude': 'first',
        'area_in_me': 'first',
        'confidence': 'first',
        'fclass': 'first',
        'type': 'first',
        'name': 'first',
        'geometry_x': 'first'
    }).reset_index()

    # 将 geometry_y 重命名为 geometry
    grouped = grouped.rename(columns={'geometry_x': 'geometry'})

    # 设置 geometry 列为地理空间列
    gdf_attr = grouped.set_geometry('geometry')

    return gdf_attr


def attribute_fusion9(gdf):
    """
    一个3d匹配多个几何，当数量小于3时赋值高度
    """
    gdf_attr = gdf[
        ['idx', 'idx1', 'longitude', 'latitude', 'area_in_me', 'confidence', 'fclass', 'type', 'name', 'Height',
         'geometry_x', 'idx1_count']]
    gdf_attr.loc[gdf_attr['idx1_count'] > 3, 'Height'] = float('nan')
    # 将 geometry_y 重命名为 geometry
    gdf_attr = gdf_attr.rename(columns={'geometry_x': 'geometry'})
    # 设置 geometry 列为地理空间列
    gdf_attr = gdf_attr.set_geometry('geometry')
    gdf_attr = gdf_attr.drop(columns='idx1_count')
    return gdf_attr


def attribute_fusion10(gdf):
    """
    过多的匹配不融合，视为异常，再保留其中之一
    """
    gdf_attr = gdf[
        ['idx', 'idx1', 'label', 'longitude', 'latitude', 'area_in_me', 'confidence', 'fclass', 'type', 'name',
         'Height', 'geometry_x', 'idx_count', 'idx1_count']]

    # 根据idx1_count条件处理Height
    gdf_attr.loc[gdf_attr['idx1_count'] > 3, 'Height'] = float('nan')

    # 按idx分组，对Height求平均，其他列取第一个值
    grouped = gdf_attr.groupby('idx').agg({
        'Height': 'mean',
        'idx1': 'first',
        'label': 'first',
        'longitude': 'first',
        'latitude': 'first',
        'area_in_me': 'first',
        'confidence': 'first',
        'fclass': 'first',
        'type': 'first',
        'name': 'first',
        'geometry_x': 'first',
        'idx_count': 'first',  # 保留用于后续删除
        'idx1_count': 'first'  # 保留用于后续删除
    }).reset_index()

    # 将 geometry_y 重命名为 geometry
    grouped = grouped.rename(columns={'geometry_x': 'geometry'})

    # 设置 geometry 列为地理空间列
    gdf_attr = grouped.set_geometry('geometry')

    # 删除idx_count和idx1_count列
    gdf_attr = gdf_attr.drop(columns=['idx_count', 'idx1_count'])

    return gdf_attr


def remove_duplicate_geometries_direct(gdf, keep='first'):
    """
    通过直接比较几何值删除重复行
    （注意：仅当几何对象内存中完全相同时生效）
    """
    return gdf.drop_duplicates(subset=['geometry'], keep=keep)


def filter_non_intersecting_osm(unadjusted_buildings):
    """
    此函数用于从 unadjusted_buildings 中筛选出 osm_id 不为空的数据，
    以及 idx1 不为空的数据，然后找出 osm 数据中与 gdf2_idx1 数据都不相交的部分。

    参数:
    unadjusted_buildings (GeoDataFrame): 包含 osm_id、idx1 和 geometry 列的 GeoDataFrame
    gdf2_idx1 (GeoDataFrame): 用于相交判断的 GeoDataFrame
    idx: R 树索引

    返回:
    GeoDataFrame: 与 gdf2_idx1 数据都不相交的 osm 数据
    GeoDataFrame: 筛选出的 idx1 不为空的数据
    """
    # gdf_osm_nomatch = unadjusted_buildings[unadjusted_buildings['osm_id'].notna()]  # 筛选出OSM数据
    gdf_gg_nomatch = unadjusted_buildings[unadjusted_buildings['idx1'].notna()]  # 筛选出的gg数据

    # 筛选出所需列并设置几何列
    gdf_gg_nomatch = gdf_gg_nomatch[['idx', 'idx1', 'latitude', 'longitude', 'area_in_me', 'confidence', 'geometry_y']]
    gdf_gg_nomatch = gdf_gg_nomatch.rename(columns={'geometry_y': 'geometry'})
    gdf_gg_nomatch = gdf_gg_nomatch.set_geometry('geometry')

    # gdf_osm_nomatch = gdf_osm_nomatch[['idx', 'idx1', 'osm_id', 'fclass', 'name', 'type', 'geometry_x']]
    # gdf_osm_nomatch = gdf_osm_nomatch.rename(columns={'geometry_x': 'geometry'})
    # gdf_osm_nomatch = gdf_osm_nomatch.set_geometry('geometry')

    # # 为 gdf2_idx1 建立 R 树索引
    # for i, row in gdf2_idx1.iterrows():
    #     idx.insert(i, row.geometry.bounds)
    #
    # # 用于存储没有相交的数据
    # non_intersecting_osm = []
    #
    # # 遍历 gdf_osm_nomatch 中的数据
    # for index, osm_row in gdf_osm_nomatch.iterrows():
    #     osm_geometry = osm_row.geometry
    #     # 通过 R 树索引查找可能相交的 gdf2_idx1 数据
    #     possible_matches = list(idx.intersection(osm_geometry.bounds))
    #     is_intersecting = False
    #     for match_index in possible_matches:
    #         try:
    #             # 使用 iloc 索引
    #             gg_geometry = gdf2_idx1.iloc[match_index].geometry
    #         except IndexError:
    #             continue
    #         if osm_geometry.intersects(gg_geometry):
    #             is_intersecting = True
    #             break
    #     if not is_intersecting:
    #         non_intersecting_osm.append(osm_row)
    #
    # # 将筛选结果转换为 GeoDataFrame
    # gdf_osm_non_intersecting = gpd.GeoDataFrame(non_intersecting_osm)

    return  gdf_gg_nomatch


def filter_non_intersecting_3d(unadjusted_buildings):
    """
    此函数用于从 unadjusted_buildings 中筛选出 osm_id 不为空的数据，
    以及 idx1 不为空的数据，然后找出 osm 数据中与 gdf2_idx1 数据都不相交的部分。

    参数:
    unadjusted_buildings (GeoDataFrame): 包含 为达成匹配条件的行
    gdf2_idx1 (GeoDataFrame): 用于相交判断的 GeoDataFrame，为3d数据集
    idx: R 树索引

    返回:
    GeoDataFrame: 与 gdf3_idx2 数据都不相交的 osm 数据
    GeoDataFrame: 筛选出的 idx1 不为空的数据
    """
    gdf_fusion_nomatch = unadjusted_buildings[unadjusted_buildings['idx'].notna()].copy()

    # # 筛选出 idx1 不为空的数据
    # gdf_3d_nomatch = unadjusted_buildings[unadjusted_buildings['idx1'].notna()].copy()  # 筛选出的数据，最后要保留的数据1

    # 筛选出所需列并设置几何列
    gdf_fusion_nomatch = gdf_fusion_nomatch[
        ['idx', 'idx1', 'label', 'longitude', 'latitude', 'area_in_me', 'confidence', 'fclass', 'type', 'name',
         'Height', 'geometry_x']]
    gdf_fusion_nomatch = gdf_fusion_nomatch.rename(columns={'geometry_x': 'geometry'})
    gdf_fusion_nomatch = gdf_fusion_nomatch.set_geometry('geometry')  # 保留的fusion数据

    # gdf_3d_nomatch = gdf_3d_nomatch[
    #     ['idx', 'idx1', 'label', 'longitude', 'latitude', 'area_in_me', 'confidence', 'fclass', 'type', 'name',
    #      'Height', 'geometry_y']]
    # gdf_3d_nomatch = gdf_3d_nomatch.rename(columns={'geometry_y': 'geometry'})
    # gdf_3d_nomatch = gdf_3d_nomatch.set_geometry('geometry')

    # # 为 gdf2_idx1 建立 R 树索引
    # for i, row in gdf2_idx1.iterrows():
    #     idx.insert(i, row.geometry.bounds)
    #
    # # 用于存储没有相交的数据
    # non_intersecting_3d = []
    #
    # # 遍历 gdf_osm_nomatch 中的数据
    # for index, three_d_row in gdf_3d_nomatch.iterrows():
    #     three_d_geometry = three_d_row.geometry
    #     # 通过 R 树索引查找可能相交的 gdf2_idx1 数据
    #     possible_matches = list(idx.intersection(three_d_geometry.bounds))
    #     is_intersecting = False
    #     for match_index in possible_matches:
    #         try:
    #             # 使用 iloc 索引
    #             gg_geometry = gdf2_idx1.iloc[match_index].geometry
    #         except IndexError:
    #             continue
    #         if three_d_geometry.intersects(gg_geometry):
    #             is_intersecting = True
    #             break
    #     if not is_intersecting:
    #         non_intersecting_3d.append(three_d_row)
    #
    #     # 将筛选结果转换为 GeoDataFrame
    # gdf_3d_non_intersecting = gpd.GeoDataFrame(non_intersecting_3d)

    return gdf_fusion_nomatch  # 新增


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("data_fusion.log"),
        logging.StreamHandler()
    ]
)


def check_empty(gdf, name, critical=True):
    """检查GeoDataFrame是否为空，并根据critical参数决定是否终止程序"""
    if gdf.empty:
        logging.error(f"错误：{name} 为空")
        if critical:
            sys.exit(1)  # 终止程序
        return False
    return True


if __name__ == '__main__':
    try:
        # 建筑物数据输入如
        """
        融合顺序：OSM与GG数据融合确定几何框架得到fusion_data1
                fusion_data与3d数据融合补全高度属性    
        """
        gdf1 = gpd.read_file("G:/演示数据/走廊数据/%名称%.shp")
        gdf2 = gpd.read_file("G:/演示数据/走廊数据/bjstgg5.shp")
        # gdf3 = gpd.read_file("G:/项目数据/建筑物融合后数据/分块边界/1665/threedbuilding.shp")
        # gdf1 = gpd.read_file("data/osm_modified.shp")
        # gdf2 = gpd.read_file("data/gg_modified.shp")
        # gdf3 = gpd.read_file("data/3d_modified.shp")
        # 检查输入数据
        # if not check_empty(gdf1, "OSM数据") or not check_empty(gdf2, "GG数据") or not check_empty(gdf3, "3D数据"):
        #     sys.exit(1)
        # osm数据预处理
        # gg数据预处理方法
        print("confidence类型：", gdf2['confidence'].dtype)
        print("area_in_me类型：", gdf2['area_in_me'].dtype)
        gdf2 = gdf2[~(((gdf2['confidence'] > 0.01) & (gdf2['confidence'] < 0.7)) &
                      (gdf2['area_in_me'] < 20))]

        logging.info("数据读取成功")
        gdf1 = gdf1.to_crs(epsg=32643)
        gdf2 = gdf2.to_crs(epsg=32643)
        # 定义索引序号
        gdf1_idx = add_index_column(gdf1)
        gdf2_idx1 = add_index_column1(gdf2)
        # 删除重复的idx
        gdf1_idx = remove_duplicate_geometries_direct(gdf1_idx)
        gdf2_idx1 = remove_duplicate_geometries_direct(gdf2_idx1)
        new_osm_gdf = find_non_intersecting_buildings(gdf1_idx, gdf2_idx1)  # 新增的osm建筑物

        similarity, similarity_gdf = calculate_similarity(gdf1_idx, gdf2_idx1)
        # 获取待匹配的建筑物对
        matched_gdf = similarity_gdf.loc[similarity_gdf['similarity'] > 0.3, 'label'] = '1'
        matched_gdf = similarity_gdf.loc[similarity_gdf['label'] == '1'].copy()  # 选择的都是>0.3的建筑物
        merged_gdf = gdf1_idx.merge(matched_gdf, on='idx', how='outer')
        merged_gdf = merged_gdf.merge(gdf2_idx1, on='idx1', how='outer')
        merged_gdf1 = merged_gdf[(merged_gdf['label'] == '1')]  # 所有匹配的数据
        merged_gdf1 = get_data_var(merged_gdf1)
        logging.info("相似性计算完成")
        # 保留不变的部分（这里要把空去掉，后续才能够处理）
        # 计算新增osm数据
        unadjusted_buildings = merged_gdf[(merged_gdf['label'] != '1')]
        save_gg_gdf = filter_non_intersecting_osm(unadjusted_buildings)  # 这是要合并的未匹配的osm和原始的gg，这里的逻辑没问题
        # 合并属性表
        gdf_1to1, gdf_1ton, gdf_nto1, gdf_mton = split_relations(merged_gdf1)
        gdf_1ton_related, gdf_nto1_related, gdf_mton_related = add_relation_columns(gdf_1ton, gdf_nto1, gdf_mton)
        logging.info("待匹配对和属性计算完成")
        logging.info("1to1_fusion")
        sim_1to1_gdf = get_sim(gdf_1to1)
        gdf_1to1_result = sim_1to1_gdf[
            ['idx1', 'idx', 'sim_location', 'sim_area', 'sim_orient', 'sim_shape', 'sim_overlap', 'fclass', 'name',
             'type', 'geometry_x', 'label', 'latitude', 'longitude', 'confidence', 'geometry_y', 'area_in_me']]
        filter_1to1_gdf, gdf_1to1_result1 = one_to_one_filter(gdf_1to1_result)
        gdf_1to1_result2 = attribute_fusion1(gdf_1to1_result1)
        gdf_1to1_result3 = attribute_fusion5(filter_1to1_gdf)
        logging.info("1ton_fusion")  # 1osm_to_ngg ,attribute_fusion,no_polygon_fusion
        gdf_1ton_result = attribute_fusion2(gdf_1ton)
        logging.info("nto1_fusion")  # 保留osm的形状
        gdf_nto1_result = attribute_fusion3(gdf_nto1)
        logging.info("nton_fusion")  # 保留谷歌的形状，融合osm的属性
        gdf_ntom_result = attribute_fusion4(gdf_mton)
        # 相似度计算与属性融合
        combined_gdf = pd.concat(
            [new_osm_gdf, save_gg_gdf, gdf_1to1_result3, gdf_1to1_result2, gdf_1ton_result, gdf_nto1_result,
             gdf_ntom_result], ignore_index=True)
        combined_gdf = combined_gdf.to_crs(epsg=32643)
        combined_gdf.to_file('G:/演示数据/走廊数据/data/buildings.shp')
        前半段融合
        combined_gdf = combined_gdf.drop(['idx', 'idx1', 'osm_id', 'label'], axis=1)

        # 几何融合数据与属性融合
        """
           处理3d数据与几何形状 stage2
        """
        combined_gdf = combined_gdf.to_crs(epsg=32643)
        gdf3 = gdf3.to_crs(epsg=32643)
        # 处理序号
        gdf4_idx = add_index_column(combined_gdf)
        gdf3_idx2 = add_index_column1(gdf3)
        # 匹配
        # 进行新增数据筛选
        new_ms_gdf = find_non_intersecting_buildings1(gdf3_idx2.copy(), gdf4_idx.copy())
        similarity1, similarity_gdf1 = calculate_similarity(gdf4_idx, gdf3_idx2)
        # 提出符合匹配的建筑
        matched_gdf_attr = similarity_gdf1.loc[similarity_gdf1['similarity'] > 0.3]
        matched_gdf_attr['label'] = '1'
        merged_gdf_attr = gdf4_idx.merge(matched_gdf_attr, on='idx', how='outer')
        merged_gdf_attr = merged_gdf_attr.merge(gdf3_idx2, on='idx1', how='outer')
        # 提出匹配的部分
        matched_gdf_attr1 = merged_gdf_attr[(merged_gdf_attr['label'] == '1')]
        matched_gdf_attr1 = get_data_var(matched_gdf_attr1)
        unadjusted_buildings1 = merged_gdf_attr[(merged_gdf_attr['label'] != '1')]
        # 处理新增数据
        save_fusion_gdf = filter_non_intersecting_3d(unadjusted_buildings1)  # 只保留未匹配的融合数据
        # 按照匹配关系分类
        gdf_1to1_attr, gdf_1ton_attr, gdf_nto1_attr, gdf_mton_attr = split_relations(matched_gdf_attr1)
        logging.info("------1to1_fusion_attr------")
        sim_1to1_gdf_attr = get_sim(gdf_1to1_attr)
        gdf_1to1_result = sim_1to1_gdf_attr[
            ['idx1', 'idx', 'sim_location', 'sim_area', 'sim_orient', 'sim_shape', 'sim_overlap', 'fclass', 'name',
             'type',
             'geometry_x', 'label', 'latitude', 'longitude', 'confidence', 'area_in_me', 'Height']]  # 不需要额外的几何融合
        filter_1to1_gdf_attr, gdf_1to1_result1_attr = one_to_one_filter(gdf_1to1_result)  # 前者为不容和高度，后者融合高度
        gdf_1to1_result1_attr = attribute_fusion6(gdf_1to1_result1_attr)  # 匹配的
        filter_1to1_gdf_attr = attribute_fusion7(filter_1to1_gdf_attr)  # 不匹配的
        logging.info("----------1ton---------")
        gdf_1ton_attr_result = attribute_fusion8(gdf_1ton_attr)  # 1ton 取平均值
        logging.info("----------nto1---------")
        gdf_nto1_attr_result = attribute_fusion9(gdf_nto1_attr)  # >3幢建筑不赋值高度
        logging.info("-----------nton--------")
        gdf_mton_attr_result = attribute_fusion10(gdf_mton_attr)
        # 合并最终结果
        combined_gdf_attr = pd.concat(
            [new_ms_gdf, save_fusion_gdf, gdf_1to1_result1_attr, filter_1to1_gdf_attr, gdf_1ton_attr_result,
             gdf_nto1_attr_result,
             gdf_mton_attr_result], ignore_index=True)
        combined_gdf_attr = combined_gdf_attr.drop(['idx', 'idx1', 'label'], axis=1)
        combined_gdf_attr = combined_gdf_attr.to_crs(epsg=32643)
        combined_gdf_attr.to_file('G:/项目数据/建筑物融合后数据/分块边界/1665/fusionbuilding.shp')
        # combined_gdf_attr.to_file('data/ceshiyong.shp')
    except Exception as e:
        logging.error(f"程序运行时捕获到异常: {str(e)}", exc_info=True)
        sys.exit(1)
