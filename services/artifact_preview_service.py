from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import geopandas as gpd

from utils.shp_zip import find_valid_shapefile, safe_extract_zip


def build_artifact_preview(artifact_zip: Path, *, output_dir: Path, max_features: int = 500) -> dict[str, Any]:
    artifact_zip = Path(artifact_zip)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="artifact-preview-") as extract_root:
        extract_dir = Path(extract_root)
        safe_extract_zip(artifact_zip, extract_dir)
        shp_path = find_valid_shapefile(extract_dir)
        frame = gpd.read_file(shp_path)

    preview_frame = _as_wgs84(frame).head(max(0, int(max_features)))
    geojson_path = output_dir / f"{artifact_zip.stem}.preview.geojson"
    preview_frame.to_file(geojson_path, driver="GeoJSON")

    metrics_frame = _as_wgs84(frame)
    bbox = [float(value) for value in metrics_frame.total_bounds] if len(metrics_frame) else None

    return {
        "artifact_zip": str(artifact_zip),
        "output_dir": str(output_dir),
        "shapefile_name": shp_path.name,
        "geojson_path": str(geojson_path),
        "max_features": int(max_features),
        "preview_feature_count": int(len(preview_frame)),
        "feature_count": int(len(frame)),
        "crs": str(frame.crs) if frame.crs is not None else None,
        "geometry_types": sorted(str(value) for value in frame.geometry.geom_type.dropna().unique()),
        "bbox": bbox,
    }


def _as_wgs84(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if frame.empty or frame.crs is None:
        return frame
    return frame.to_crs("EPSG:4326")
