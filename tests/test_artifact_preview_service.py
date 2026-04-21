from __future__ import annotations

import json
import warnings
import zipfile
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from services.artifact_preview_service import build_artifact_preview


def test_build_artifact_preview_writes_capped_geojson(tmp_path: Path) -> None:
    zip_path = _build_single_feature_zip(tmp_path)

    summary = build_artifact_preview(zip_path, output_dir=tmp_path / "preview")

    assert summary["feature_count"] == 1
    assert summary["bbox"] is not None
    assert summary["geojson_path"].endswith(".geojson")
    assert Path(summary["geojson_path"]).exists()


def test_build_artifact_preview_fails_clearly_when_shapefile_has_no_crs(tmp_path: Path) -> None:
    zip_path = _build_polygon_zip(tmp_path, count=1, crs=None)

    with pytest.raises(ValueError, match="artifact shapefile must define CRS"):
        build_artifact_preview(zip_path, output_dir=tmp_path / "preview")

    assert not list((tmp_path / "preview").glob("*.geojson"))


def test_build_artifact_preview_does_not_overwrite_existing_preview(tmp_path: Path) -> None:
    zip_path = _build_single_feature_zip(tmp_path)
    output_dir = tmp_path / "preview"
    output_dir.mkdir()
    existing_preview = output_dir / "artifact.preview.geojson"
    existing_content = '{"type":"FeatureCollection","features":[]}'
    existing_preview.write_text(existing_content, encoding="utf-8")

    summary = build_artifact_preview(zip_path, output_dir=output_dir)

    assert Path(summary["geojson_path"]) != existing_preview
    assert existing_preview.read_text(encoding="utf-8") == existing_content
    assert Path(summary["geojson_path"]).exists()


def test_build_artifact_preview_caps_geojson_without_changing_source_count(tmp_path: Path) -> None:
    zip_path = _build_polygon_zip(tmp_path, count=3, crs="EPSG:4326")

    summary = build_artifact_preview(zip_path, output_dir=tmp_path / "preview", max_features=2)

    with Path(summary["geojson_path"]).open(encoding="utf-8") as fp:
        geojson = json.load(fp)
    assert summary["feature_count"] == 3
    assert summary["preview_feature_count"] == 2
    assert len(geojson["features"]) == 2


def _build_single_feature_zip(tmp_path: Path) -> Path:
    return _build_polygon_zip(tmp_path, count=1, crs="EPSG:4326")


def _build_polygon_zip(tmp_path: Path, *, count: int, crs: str | None) -> Path:
    frame = gpd.GeoDataFrame(
        {"fid": list(range(count)), "name": [f"sample-{idx}" for idx in range(count)]},
        geometry=[
            Polygon(
                [
                    (idx, idx),
                    (idx, idx + 0.01),
                    (idx + 0.01, idx + 0.01),
                    (idx + 0.01, idx),
                ]
            )
            for idx in range(count)
        ],
        crs=crs,
    )
    shp_path = tmp_path / "sample.shp"
    if crs is None:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="'crs' was not provided.*", category=UserWarning)
            frame.to_file(shp_path)
    else:
        frame.to_file(shp_path)
    return _zip_bundle(shp_path, tmp_path / "artifact.zip")


def _zip_bundle(shp_path: Path, out_zip: Path) -> Path:
    base = shp_path.with_suffix("")
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in shp_path.parent.glob(f"{base.name}.*"):
            zf.write(file, arcname=file.name)
    return out_zip
