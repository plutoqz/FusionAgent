from __future__ import annotations

import hashlib
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
        shapefile_name = shp_path.name
        frame = gpd.read_file(shp_path)

    wgs84_frame = _as_wgs84(frame)
    preview_frame = wgs84_frame.head(max(0, int(max_features)))
    geojson_path = _preview_geojson_path(artifact_zip, output_dir)
    preview_frame.to_file(geojson_path, driver="GeoJSON")

    bbox = [float(value) for value in wgs84_frame.total_bounds] if len(wgs84_frame) else None

    return {
        "artifact_zip": str(artifact_zip),
        "output_dir": str(output_dir),
        "shapefile_name": shapefile_name,
        "geojson_path": str(geojson_path),
        "max_features": int(max_features),
        "preview_feature_count": int(len(preview_frame)),
        "feature_count": int(len(frame)),
        "crs": str(frame.crs) if frame.crs is not None else None,
        "geometry_types": sorted(str(value) for value in frame.geometry.geom_type.dropna().unique()),
        "bbox": bbox,
    }


def _as_wgs84(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if frame.crs is None:
        raise ValueError("artifact shapefile must define CRS to build a WGS84 preview")
    return frame.to_crs("EPSG:4326")


def _preview_geojson_path(artifact_zip: Path, output_dir: Path) -> Path:
    digest = _artifact_digest(artifact_zip)
    target = output_dir / f"{artifact_zip.stem}.{digest}.preview.geojson"
    if not target.exists():
        return target

    index = 1
    while True:
        candidate = output_dir / f"{artifact_zip.stem}.{digest}.{index}.preview.geojson"
        if not candidate.exists():
            return candidate
        index += 1


def _artifact_digest(artifact_zip: Path) -> str:
    digest = hashlib.sha256()
    with artifact_zip.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:12]
