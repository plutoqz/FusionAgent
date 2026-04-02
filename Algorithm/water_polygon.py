import geopandas as gpd
from rtree import index
import pandas as pd

def add_index_to_gdf(gdf, prefix=''):
    """
    Add an index column to a GeoDataFrame starting from 1.

    Args:
        gdf (GeoDataFrame): Input GeoDataFrame
        prefix (str): Optional prefix for the index column name

    Returns:
        GeoDataFrame: GeoDataFrame with added index column
    """
    # Reset index to get a default 0-based index
    gdf = gdf.reset_index(drop=True)
    # Add 1 to make it 1-based, and add prefix if provided
    gdf[f'{prefix}ID'] = gdf.index + 1
    return gdf


import geopandas as gpd
from rtree import index


def spatial_match_with_rtree(osm_gdf, new_gdf, overlap_threshold=0.1):
    """
    Match polygons between two GeoDataFrames based on area overlap percentage,
    using custom ID fields OSM_ID and NEW_ID.

    Args:
        osm_gdf (GeoDataFrame): OSM water polygons with OSM_ID field
        new_gdf (GeoDataFrame): New water polygons with NEW_ID field
        overlap_threshold (float): Minimum overlap ratio (default 10%)

    Returns:
        GeoDataFrame: OSM polygons with matched attributes and match records
    """
    # Create R-tree index for OSM polygons
    idx = index.Index()
    for i, geom in enumerate(osm_gdf.geometry):
        idx.insert(i, geom.bounds)

    # Prepare output GeoDataFrame (copy of OSM data)
    result_gdf = osm_gdf.copy()

    # Initialize columns for match information
    result_gdf['MATCHED_NEW_ID'] = None  # 存储匹配的NEW_ID
    result_gdf['OVERLAP_RATIO'] = None  # 存储重叠比例
    result_gdf['MATCH_COUNT'] = 0  # 存储匹配次数

    # Track matched NEW_IDs to avoid duplicate processing
    matched_new_ids = set()

    # Iterate through new polygons
    for new_idx, new_row in new_gdf.iterrows():
        new_geom = new_row.geometry
        new_id = new_row['NEW_ID']
        new_area = new_geom.area

        # Find potential matches using R-tree
        potential_matches = list(idx.intersection(new_geom.bounds))

        for osm_idx in potential_matches:
            osm_geom = osm_gdf.iloc[osm_idx].geometry
            osm_id = osm_gdf.iloc[osm_idx]['OSM_ID']
            osm_area = osm_geom.area

            # Calculate intersection area
            try:
                intersection = new_geom.intersection(osm_geom)
                intersection_area = intersection.area

                # Check overlap ratio
                overlap_ratio = intersection_area / osm_area

                # If significant overlap with OSM polygon (≥threshold)
                if overlap_ratio >= overlap_threshold:
                    # Record match information
                    if result_gdf.at[osm_idx, 'MATCHED_NEW_ID'] is None:
                        result_gdf.at[osm_idx, 'MATCHED_NEW_ID'] = str(new_id)
                    else:
                        result_gdf.at[osm_idx, 'MATCHED_NEW_ID'] += f";{new_id}"

                    result_gdf.at[osm_idx, 'OVERLAP_RATIO'] = max(
                        overlap_ratio,
                        result_gdf.at[osm_idx, 'OVERLAP_RATIO'] or 0
                    )
                    result_gdf.at[osm_idx, 'MATCH_COUNT'] += 1

                    # Transfer attributes (excluding geometry and ID fields)
                    for col in new_gdf.columns:
                        if col not in ['geometry', 'NEW_ID']:
                            col_name = f"NEW_{col}"
                            if col_name not in result_gdf.columns:
                                result_gdf[col_name] = None

                            if result_gdf.at[osm_idx, col_name] is None:
                                result_gdf.at[osm_idx, col_name] = new_row[col]
                            else:
                                result_gdf.at[osm_idx, col_name] += f";{new_row[col]}"

                    matched_new_ids.add(new_id)
            except Exception as e:
                print(f"Error processing OSM_ID:{osm_id} and NEW_ID:{new_id}: {str(e)}")
                continue

    print(f"匹配完成: {len(matched_new_ids)}个新水体要素匹配到{result_gdf['MATCH_COUNT'].sum()}个OSM要素")
    return result_gdf


def add_unmatched_new_water(matched_gdf, osm_gdf, new_gdf):
    """
    将未匹配的新水体要素添加到结果GeoDataFrame中

    Args:
        matched_gdf (GeoDataFrame): 已匹配的结果数据
        osm_gdf (GeoDataFrame): 原始OSM数据
        new_gdf (GeoDataFrame): 新水体数据

    Returns:
        GeoDataFrame: 包含匹配和未匹配要素的完整结果
    """
    # 获取所有已匹配的NEW_ID
    matched_ids = set()
    for ids in matched_gdf['MATCHED_NEW_ID'].dropna():
        matched_ids.update(map(int, ids.split(';')))

    # 找出未匹配的新要素
    unmatched_new = new_gdf[~new_gdf['NEW_ID'].isin(matched_ids)].copy()

    if len(unmatched_new) == 0:
        print("没有未匹配的新水体要素")
        return matched_gdf

    # 为未匹配要素准备数据行
    for col in matched_gdf.columns:
        if col not in unmatched_new.columns and col != 'geometry':
            unmatched_new[col] = None

    # 设置匹配信息字段
    unmatched_new['MATCH_COUNT'] = 0
    unmatched_new['OVERLAP_RATIO'] = 0.0
    unmatched_new['MATCHED_NEW_ID'] = unmatched_new['NEW_ID'].astype(str)

    # 确保字段顺序一致
    unmatched_new = unmatched_new[matched_gdf.columns]

    # 合并数据
    combined_gdf = gpd.GeoDataFrame(
        pd.concat([matched_gdf, unmatched_new], ignore_index=True),
        crs=matched_gdf.crs
    )

    print(f"新增了 {len(unmatched_new)} 个未匹配的水体要素")
    return combined_gdf


if __name__ == "__main__":
    # 加载数据并只保留需要的字段
    osm_water = gpd.read_file("G:/项目数据/建筑物融合后数据/water/st/osm_WATERAREA_ST.shp")
    new_water = gpd.read_file("G:/项目数据/建筑物融合后数据/water/st/polygon.shp")
    new_water1 = new_water[
        ['Lake_name', 'Pour_long', 'Pour_lat', 'geometry', 'Lake_area', 'Depth_avg', 'Res_time', 'Elevation']]

    # 统一投影坐标系
    new_water1 = new_water1.to_crs(epsg=32643)
    osm_water = osm_water.to_crs(epsg=32643)

    # 添加索引编号
    osm_water = add_index_to_gdf(osm_water, prefix='OSM_')
    new_water1 = add_index_to_gdf(new_water1, prefix='NEW_')

    # 执行空间匹配
    matched_water = spatial_match_with_rtree(osm_water, new_water1)

    # 添加未匹配的新要素
    final_result = add_unmatched_new_water(matched_water, osm_water, new_water1)

    # 保存结果
    output_path = "G:/项目数据/建筑物融合后数据/water/st/matched_water_with_ids.shp"
    final_result.to_file(output_path)

    print(f"融合完成，结果已保存至 {output_path}")
    print("匹配统计:")
    print(f"- 总OSM要素数: {len(osm_water)}")
    print(f"- 匹配的OSM要素数: {len(matched_water[matched_water['MATCH_COUNT'] > 0])}")
    print(f"- 总NEW要素数: {len(new_water1)}")
    print(f"- 匹配的NEW要素数: {matched_water['MATCH_COUNT'].sum()}")
    print(f"- 新增的未匹配NEW要素数: {len(final_result) - len(matched_water)}")


