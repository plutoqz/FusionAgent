from __future__ import annotations

import zipfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

from services.artifact_preview_service import build_artifact_preview


def test_build_artifact_preview_writes_capped_geojson(tmp_path: Path) -> None:
    zip_path = _build_single_feature_zip(tmp_path)

    summary = build_artifact_preview(zip_path, output_dir=tmp_path / "preview")

    assert summary["feature_count"] == 1
    assert summary["bbox"] is not None
    assert summary["geojson_path"].endswith(".geojson")
    assert Path(summary["geojson_path"]).exists()


def _build_single_feature_zip(tmp_path: Path) -> Path:
    frame = gpd.GeoDataFrame(
        {"fid": [1], "name": ["sample"]},
        geometry=[Polygon([(0, 0), (0, 0.01), (0.01, 0.01), (0.01, 0)])],
        crs="EPSG:4326",
    )
    shp_path = tmp_path / "sample.shp"
    frame.to_file(shp_path)
    return _zip_bundle(shp_path, tmp_path / "artifact.zip")


def _zip_bundle(shp_path: Path, out_zip: Path) -> Path:
    base = shp_path.with_suffix("")
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in shp_path.parent.glob(f"{base.name}.*"):
            zf.write(file, arcname=file.name)
    return out_zip
