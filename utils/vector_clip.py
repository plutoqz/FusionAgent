from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional, Tuple

import geopandas as gpd
from shapely.geometry import box

from utils.crs import normalize_target_crs
from utils.shp_zip import validate_zip_has_shapefile, zip_shapefile_bundle


BBox = Tuple[float, float, float, float]
REQUEST_BBOX_CRS = "EPSG:4326"


def ensure_frame_crs(gdf: gpd.GeoDataFrame, *, default_crs: str = REQUEST_BBOX_CRS) -> gpd.GeoDataFrame:
    if gdf.crs is not None:
        return gdf
    return gdf.set_crs(default_crs)


def clip_frame_to_request_bbox(
    gdf: gpd.GeoDataFrame,
    request_bbox: Optional[BBox],
    *,
    request_crs: str = REQUEST_BBOX_CRS,
) -> gpd.GeoDataFrame:
    frame = ensure_frame_crs(gdf, default_crs=request_crs)
    if request_bbox is None:
        return frame

    mask = gpd.GeoDataFrame(geometry=[box(*request_bbox)], crs=request_crs)
    dataset_crs = normalize_target_crs(str(frame.crs))
    if normalize_target_crs(request_crs) != dataset_crs:
        mask = mask.to_crs(dataset_crs)

    clipped = frame.clip(mask.geometry.iloc[0])
    clipped = clipped[~clipped.geometry.is_empty & clipped.geometry.notna()].copy()
    if clipped.empty:
        return frame.iloc[0:0].copy()
    return clipped


def frame_bbox_in_crs(gdf: gpd.GeoDataFrame, *, bbox_crs: str = REQUEST_BBOX_CRS) -> Optional[BBox]:
    if gdf.empty:
        return None

    frame = ensure_frame_crs(gdf, default_crs=bbox_crs)
    target_crs = normalize_target_crs(bbox_crs)
    if normalize_target_crs(str(frame.crs)) != target_crs:
        frame = frame.to_crs(target_crs)
    minx, miny, maxx, maxy = [float(value) for value in frame.total_bounds.tolist()]
    return (minx, miny, maxx, maxy)


def clip_zip_to_request_bbox(
    source_zip: Path,
    output_zip: Path,
    *,
    request_bbox: BBox,
    request_crs: str = REQUEST_BBOX_CRS,
) -> Path:
    extract_dir = output_zip.parent / f"_clip_src_{source_zip.stem}_{uuid.uuid4().hex[:8]}"
    shp_path = validate_zip_has_shapefile(source_zip, extract_dir)
    gdf = gpd.read_file(shp_path)
    clipped = clip_frame_to_request_bbox(gdf, request_bbox, request_crs=request_crs)

    out_dir = output_zip.parent / f"_clip_dst_{source_zip.stem}_{uuid.uuid4().hex[:8]}"
    out_dir.mkdir(parents=True, exist_ok=True)
    clipped_shp = out_dir / shp_path.name
    clipped.to_file(clipped_shp)
    return zip_shapefile_bundle(clipped_shp, output_zip)


def bundle_bbox_from_zip(zip_path: Path, *, bbox_crs: str = REQUEST_BBOX_CRS) -> Optional[BBox]:
    extract_dir = zip_path.parent / f"_inspect_{zip_path.stem}_{uuid.uuid4().hex[:8]}"
    shp_path = validate_zip_has_shapefile(zip_path, extract_dir)
    gdf = gpd.read_file(shp_path)
    return frame_bbox_in_crs(gdf, bbox_crs=bbox_crs)
