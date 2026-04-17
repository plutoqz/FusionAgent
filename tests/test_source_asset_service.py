from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

geopandas = pytest.importorskip("geopandas")
from shapely.geometry import LineString, Point, Polygon

from services.source_asset_service import SourceAssetService
from utils.shp_zip import zip_shapefile_bundle


def _write_frame(path: Path, frame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(path)


def _write_geofabrik_zip(zip_path: Path) -> None:
    root = zip_path.parent / "geofabrik_src"
    _write_frame(
        root / "gis_osm_buildings_a_free_1.shp",
        geopandas.GeoDataFrame({"osm_id": [1]}, geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])], crs="EPSG:4326"),
    )
    _write_frame(
        root / "gis_osm_roads_free_1.shp",
        geopandas.GeoDataFrame({"road_id": [1]}, geometry=[LineString([(0, 0), (1, 1)])], crs="EPSG:4326"),
    )
    _write_frame(
        root / "gis_osm_water_a_free_1.shp",
        geopandas.GeoDataFrame({"water_id": [1]}, geometry=[Polygon([(0, 0), (0, 2), (2, 2), (2, 0)])], crs="EPSG:4326"),
    )
    _write_frame(
        root / "gis_osm_pois_free_1.shp",
        geopandas.GeoDataFrame({"poi_id": [1]}, geometry=[Point(0.5, 0.5)], crs="EPSG:4326"),
    )

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    import zipfile

    with zipfile.ZipFile(zip_path, "w") as archive:
        for file in root.glob("*"):
            archive.write(file, arcname=file.name)


def _write_msft_part(path: Path, features: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for feature in features:
            handle.write(json.dumps(feature, ensure_ascii=False))
            handle.write("\n")


def test_source_asset_service_prefers_existing_local_data_tree(tmp_path: Path) -> None:
    local_shp = tmp_path / "Data" / "burundi-260127-free.shp" / "gis_osm_buildings_a_free_1.shp"
    _write_frame(
        local_shp,
        geopandas.GeoDataFrame({"osm_id": [1]}, geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])], crs="EPSG:4326"),
    )

    service = SourceAssetService(repo_root=tmp_path, cache_dir=tmp_path / "cache")

    resolved = service.resolve_raw_source_path("raw.osm.building")

    assert resolved.path == local_shp
    assert resolved.source_mode == "local_data"
    assert resolved.cache_hit is True


def test_source_asset_service_downloads_and_extracts_geofabrik_bundle_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive_path = tmp_path / "fixtures" / "burundi-latest-free.shp.zip"
    _write_geofabrik_zip(archive_path)
    service = SourceAssetService(
        repo_root=tmp_path,
        cache_dir=tmp_path / "cache",
        geofabrik_burundi_url=archive_path.resolve().as_uri(),
        prefer_local_data=False,
    )

    download_calls: list[str] = []
    original = service._download_file

    def tracked_download(url: str, target_path: Path) -> None:
        download_calls.append(url)
        original(url, target_path)

    monkeypatch.setattr(service, "_download_file", tracked_download)

    first = service.resolve_raw_source_path("raw.osm.road")
    second = service.resolve_raw_source_path("raw.osm.road")

    assert first.path == second.path
    assert first.path.name == "gis_osm_roads_free_1.shp"
    assert download_calls == [archive_path.resolve().as_uri()]
    assert second.cache_hit is True


def test_source_asset_service_skips_incomplete_local_shapefile_and_uses_remote_asset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local_dir = tmp_path / "Data" / "buildings" / "Microsoft"
    local_dir.mkdir(parents=True, exist_ok=True)
    (local_dir / "broken.shp").write_bytes(b"broken")
    (local_dir / "broken.dbf").write_bytes(b"broken")

    inside_feature = {
        "type": "Feature",
        "properties": {"confidence": 0.9},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[29.0, -3.0], [29.0, -2.9], [29.1, -2.9], [29.1, -3.0], [29.0, -3.0]]],
        },
    }
    inside_part = tmp_path / "fixtures" / "inside.csv.gz"
    _write_msft_part(inside_part, [inside_feature])
    index_path = tmp_path / "fixtures" / "dataset-links.csv"
    index_path.write_text(
        "\n".join(
            [
                "Location,QuadKey,Url,Size,UploadDate",
                f"Burundi,3,{inside_part.resolve().as_uri()},1KB,2026-02-23",
            ]
        ),
        encoding="utf-8",
    )

    service = SourceAssetService(
        repo_root=tmp_path,
        cache_dir=tmp_path / "cache",
        msft_dataset_links_url=index_path.resolve().as_uri(),
    )

    resolved = service.resolve_raw_source_path("raw.microsoft.building", request_bbox=(28.9, -3.1, 29.2, -2.8))

    assert resolved.source_mode == "asset_downloaded"
    assert resolved.path.exists()


def test_source_asset_service_builds_msft_burundi_clip_from_geojsonl_parts(tmp_path: Path) -> None:
    inside_feature = {
        "type": "Feature",
        "properties": {"confidence": 0.9},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[29.0, -3.0], [29.0, -2.9], [29.1, -2.9], [29.1, -3.0], [29.0, -3.0]]],
        },
    }
    outside_feature = {
        "type": "Feature",
        "properties": {"confidence": 0.5},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-120.0, 40.0], [-120.0, 40.1], [-119.9, 40.1], [-119.9, 40.0], [-120.0, 40.0]]],
        },
    }

    inside_part = tmp_path / "fixtures" / "inside.csv.gz"
    outside_part = tmp_path / "fixtures" / "outside.csv.gz"
    _write_msft_part(inside_part, [inside_feature])
    _write_msft_part(outside_part, [outside_feature])

    index_path = tmp_path / "fixtures" / "dataset-links.csv"
    index_path.write_text(
        "\n".join(
            [
                "Location,QuadKey,Url,Size,UploadDate",
                f"Burundi,3,{inside_part.resolve().as_uri()},1KB,2026-02-23",
                f"Burundi,0,{outside_part.resolve().as_uri()},1KB,2026-02-23",
            ]
        ),
        encoding="utf-8",
    )

    service = SourceAssetService(
        repo_root=tmp_path,
        cache_dir=tmp_path / "cache",
        msft_dataset_links_url=index_path.resolve().as_uri(),
        prefer_local_data=False,
    )

    resolved = service.resolve_raw_source_path("raw.microsoft.building", request_bbox=(28.9, -3.1, 29.2, -2.8))
    frame = geopandas.read_file(resolved.path)

    assert resolved.path.exists()
    assert len(frame) == 1
    assert "confidence" in frame.columns
