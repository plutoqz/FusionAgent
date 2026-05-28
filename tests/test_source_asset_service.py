from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from pathlib import Path

import pytest

geopandas = pytest.importorskip("geopandas")
from shapely.geometry import LineString, Point, Polygon

from services.source_asset_service import SourceAssetService
from services.aoi_resolution_service import ResolvedAOI
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


def _write_geofabrik_zip_with_layers(
    zip_path: Path,
    *,
    roads=None,
    buildings=None,
    waters=None,
    waterways=None,
    pois=None,
) -> None:
    root = zip_path.parent / "geofabrik_src_custom"
    root.mkdir(parents=True, exist_ok=True)
    layers = {
        "gis_osm_buildings_a_free_1.shp": buildings
        if buildings is not None
        else geopandas.GeoDataFrame(
            {"osm_id": [1]},
            geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
            crs="EPSG:4326",
        ),
        "gis_osm_roads_free_1.shp": roads
        if roads is not None
        else geopandas.GeoDataFrame({"road_id": [1]}, geometry=[LineString([(0, 0), (1, 1)])], crs="EPSG:4326"),
        "gis_osm_water_a_free_1.shp": waters
        if waters is not None
        else geopandas.GeoDataFrame(
            {"water_id": [1]},
            geometry=[Polygon([(0, 0), (0, 2), (2, 2), (2, 0)])],
            crs="EPSG:4326",
        ),
        "gis_osm_waterways_free_1.shp": waterways
        if waterways is not None
        else geopandas.GeoDataFrame(
            {"waterway_id": [1]},
            geometry=[LineString([(0, 0), (1, 1)])],
            crs="EPSG:4326",
        ),
        "gis_osm_pois_free_1.shp": pois
        if pois is not None
        else geopandas.GeoDataFrame({"poi_id": [1]}, geometry=[Point(0.5, 0.5)], crs="EPSG:4326"),
    }
    for filename, frame in layers.items():
        _write_frame(root / filename, frame)

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


def _write_corrupt_gzip(path: Path, payload: bytes = b"{\"broken\": true}\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    truncated = gzip.compress(payload)[:-8]
    path.write_bytes(truncated)


def _resolved_nairobi_aoi() -> ResolvedAOI:
    return ResolvedAOI(
        query="Nairobi, Kenya",
        display_name="Nairobi, Nairobi County, Kenya",
        country_name="Kenya",
        country_code="ke",
        bbox=(36.65, -1.45, 37.10, -1.10),
        confidence=0.97,
        selection_reason="single_high_confidence_candidate",
        candidates=(),
    )


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


def test_source_asset_service_inspects_local_raster_profile_without_materializing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raster_path = tmp_path / "presence.tif"
    raster_path.write_bytes(b"fake-raster")
    service = SourceAssetService(repo_root=tmp_path, cache_dir=tmp_path / "cache")

    monkeypatch.setattr(
        "services.source_asset_service.gdalinfo_json",
        lambda path: {"bands": [{"description": "building presence"}], "path": str(path)},
    )

    profile = service.inspect_local_raster_profile("raw.google.building_presence.raster", raster_path)

    assert profile["source_id"] == "raw.google.building_presence.raster"
    assert profile["source_form"] == "raster"
    assert profile["runtime_status"] == "reservation_only"
    assert profile["band_count"] == 1


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


def test_source_asset_service_materializes_kenya_osm_and_clips_to_nairobi(tmp_path: Path) -> None:
    archive_path = tmp_path / "fixtures" / "kenya-latest-free.shp.zip"
    roads = geopandas.GeoDataFrame(
        {"road_id": [1, 2]},
        geometry=[
            LineString([(36.80, -1.35), (36.90, -1.25)]),
            LineString([(39.60, -4.10), (39.70, -4.00)]),
        ],
        crs="EPSG:4326",
    )
    _write_geofabrik_zip_with_layers(archive_path, roads=roads)
    index_path = tmp_path / "fixtures" / "geofabrik-index.json"
    index_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "id": "africa/kenya",
                            "parent": "africa",
                            "name": "Kenya",
                            "iso3166-1:alpha2": ["KE"],
                            "urls": {"shp": archive_path.resolve().as_uri()},
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    service = SourceAssetService(
        repo_root=tmp_path,
        cache_dir=tmp_path / "cache",
        geofabrik_index_url=index_path.resolve().as_uri(),
        prefer_local_data=False,
    )

    resolved = service.resolve_raw_source_path("raw.osm.road", aoi=_resolved_nairobi_aoi())
    frame = geopandas.read_file(resolved.path)

    assert resolved.source_mode == "asset_downloaded"
    assert resolved.feature_count == 1
    assert resolved.bbox == pytest.approx((36.8, -1.35, 36.9, -1.25))
    assert len(frame) == 1
    assert frame.iloc[0]["road_id"] == 1


def test_source_asset_service_redownloads_corrupt_geofabrik_cache_before_extracting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "fixtures" / "kenya-latest-free.shp.zip"
    roads = geopandas.GeoDataFrame(
        {"road_id": [1]},
        geometry=[LineString([(36.80, -1.35), (36.90, -1.25)])],
        crs="EPSG:4326",
    )
    _write_geofabrik_zip_with_layers(archive_path, roads=roads)
    index_path = tmp_path / "fixtures" / "geofabrik-index.json"
    index_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "id": "africa/kenya",
                            "parent": "africa",
                            "name": "Kenya",
                            "iso3166-1:alpha2": ["KE"],
                            "urls": {"shp": archive_path.resolve().as_uri()},
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    service = SourceAssetService(
        repo_root=tmp_path,
        cache_dir=tmp_path / "cache",
        geofabrik_index_url=index_path.resolve().as_uri(),
        prefer_local_data=False,
    )
    corrupt_zip = tmp_path / "cache" / "geofabrik" / "kenya" / "kenya-latest-free.shp.zip"
    corrupt_zip.parent.mkdir(parents=True, exist_ok=True)
    corrupt_zip.write_bytes(b"PK\x03\x04not-a-real-zip")
    download_calls: list[str] = []
    original_download = service._download_file

    def tracked_download(url: str, target_path: Path) -> None:
        download_calls.append(url)
        original_download(url, target_path)

    monkeypatch.setattr(service, "_download_file", tracked_download)

    resolved = service.resolve_raw_source_path("raw.osm.road", aoi=_resolved_nairobi_aoi())
    frame = geopandas.read_file(resolved.path)

    assert resolved.source_mode == "asset_downloaded"
    assert resolved.feature_count == 1
    assert len(frame) == 1
    assert download_calls == [archive_path.resolve().as_uri()]


def test_source_asset_service_uses_httpx_for_https_downloads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = SourceAssetService(repo_root=tmp_path, cache_dir=tmp_path / "cache", prefer_local_data=False)
    target_path = tmp_path / "download.bin"
    calls: list[tuple[str, str]] = []

    def fake_http(url: str, temp_path: Path) -> None:
        calls.append(("httpx", url))
        temp_path.write_bytes(b"http")

    def fake_urllib(url: str, temp_path: Path) -> None:
        calls.append(("urllib", url))
        temp_path.write_bytes(b"urllib")

    monkeypatch.setattr(service, "_download_http_stream", fake_http)
    monkeypatch.setattr(service, "_download_via_urllib", fake_urllib)

    service._download_file("https://example.com/data.zip", target_path)

    assert target_path.read_bytes() == b"http"
    assert calls == [("httpx", "https://example.com/data.zip")]


def test_source_asset_service_falls_back_to_curl_when_httpx_https_download_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SourceAssetService(repo_root=tmp_path, cache_dir=tmp_path / "cache", prefer_local_data=False)
    target_path = tmp_path / "download.bin"
    calls: list[tuple[str, str]] = []

    def fake_stream(*args, **kwargs):
        del kwargs
        calls.append(("httpx", str(args[1])))
        raise httpx.ConnectError("boom")

    def fake_curl(url: str, temp_path: Path) -> None:
        calls.append(("curl", url))
        temp_path.write_bytes(b"curl")

    monkeypatch.setattr("services.source_asset_service.httpx.stream", fake_stream)
    monkeypatch.setattr("services.source_asset_service.SourceAssetService._download_http_via_curl", staticmethod(fake_curl))

    service._download_file("https://example.com/data.zip", target_path)

    assert target_path.read_bytes() == b"curl"
    assert calls == [
        ("httpx", "https://example.com/data.zip"),
        ("curl", "https://example.com/data.zip"),
    ]


def test_source_asset_service_falls_back_to_urllib_when_curl_https_download_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SourceAssetService(repo_root=tmp_path, cache_dir=tmp_path / "cache", prefer_local_data=False)
    target_path = tmp_path / "download.bin"
    calls: list[tuple[str, str]] = []

    def fake_stream(*args, **kwargs):
        del kwargs
        calls.append(("httpx", str(args[1])))
        raise httpx.ConnectError("boom")

    def fake_curl(url: str, temp_path: Path) -> None:
        del temp_path
        calls.append(("curl", url))
        raise RuntimeError("curl: (35) schannel: next InitializeSecurityContext failed: CRYPT_E_REVOCATION_OFFLINE")

    def fake_urllib(url: str, temp_path: Path) -> None:
        calls.append(("urllib", url))
        temp_path.write_bytes(b"urllib")

    monkeypatch.setattr("services.source_asset_service.httpx.stream", fake_stream)
    monkeypatch.setattr("services.source_asset_service.SourceAssetService._download_http_via_curl", staticmethod(fake_curl))
    monkeypatch.setattr(service, "_download_via_urllib", fake_urllib)

    service._download_file("https://example.com/data.zip", target_path)

    assert target_path.read_bytes() == b"urllib"
    assert calls == [
        ("httpx", "https://example.com/data.zip"),
        ("curl", "https://example.com/data.zip"),
        ("urllib", "https://example.com/data.zip"),
    ]


def test_source_asset_service_water_prefers_local_source_and_clips_request_bbox(tmp_path: Path) -> None:
    local_shp = tmp_path / "Data" / "burundi-260127-free.shp" / "gis_osm_water_a_free_1.shp"
    _write_frame(
        local_shp,
        geopandas.GeoDataFrame(
            {"water_id": [1, 2]},
            geometry=[
                Polygon([(0.0, 0.0), (0.0, 2.0), (2.0, 2.0), (2.0, 0.0)]),
                Polygon([(5.0, 5.0), (5.0, 6.0), (6.0, 6.0), (6.0, 5.0)]),
            ],
            crs="EPSG:4326",
        ),
    )
    service = SourceAssetService(repo_root=tmp_path, cache_dir=tmp_path / "cache")

    resolved = service.resolve_raw_source_path("raw.osm.water", request_bbox=(0.5, 0.5, 1.5, 1.5))
    frame = geopandas.read_file(resolved.path)

    assert resolved.source_mode == "local_data_clipped"
    assert resolved.cache_hit is False
    assert resolved.feature_count == 1
    assert resolved.bbox == pytest.approx((0.5, 0.5, 1.5, 1.5))
    assert resolved.path.parent.name != "burundi-260127-free.shp"
    assert len(frame) == 1


def test_source_asset_service_water_empty_local_clip_falls_back_to_geofabrik_asset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_shp = tmp_path / "Data" / "burundi-260127-free.shp" / "gis_osm_water_a_free_1.shp"
    _write_frame(
        local_shp,
        geopandas.GeoDataFrame(
            {"water_id": [1]},
            geometry=[Polygon([(0.0, 0.0), (0.0, 2.0), (2.0, 2.0), (2.0, 0.0)])],
            crs="EPSG:4326",
        ),
    )
    archive_path = tmp_path / "fixtures" / "burundi-latest-free.shp.zip"
    waters = geopandas.GeoDataFrame(
        {"water_id": [99]},
        geometry=[Polygon([(10.0, 10.0), (10.0, 11.0), (11.0, 11.0), (11.0, 10.0)])],
        crs="EPSG:4326",
    )
    _write_geofabrik_zip_with_layers(archive_path, waters=waters)

    service = SourceAssetService(
        repo_root=tmp_path,
        cache_dir=tmp_path / "cache",
        geofabrik_burundi_url=archive_path.resolve().as_uri(),
    )
    download_calls: list[str] = []
    original_download = service._download_file

    def tracked_download(url: str, target_path: Path) -> None:
        download_calls.append(url)
        original_download(url, target_path)

    monkeypatch.setattr(service, "_download_file", tracked_download)

    resolved = service.resolve_raw_source_path("raw.osm.water", request_bbox=(10.0, 10.0, 11.0, 11.0))
    frame = geopandas.read_file(resolved.path)

    assert resolved.source_mode == "asset_downloaded"
    assert resolved.cache_hit is False
    assert resolved.feature_count == 1
    assert resolved.bbox == pytest.approx((10.0, 10.0, 11.0, 11.0))
    assert len(frame) == 1
    assert download_calls == [archive_path.resolve().as_uri()]


def test_source_asset_service_materializes_osm_waterways_from_geofabrik_bundle(tmp_path: Path) -> None:
    archive_path = tmp_path / "fixtures" / "kenya-latest-free.shp.zip"
    waterways = geopandas.GeoDataFrame(
        {"waterway_id": [1, 2]},
        geometry=[
            LineString([(36.80, -1.35), (36.90, -1.25)]),
            LineString([(39.60, -4.10), (39.70, -4.00)]),
        ],
        crs="EPSG:4326",
    )
    _write_geofabrik_zip_with_layers(archive_path, waterways=waterways)
    index_path = tmp_path / "fixtures" / "geofabrik-index.json"
    index_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "id": "africa/kenya",
                            "parent": "africa",
                            "name": "Kenya",
                            "iso3166-1:alpha2": ["KE"],
                            "urls": {"shp": archive_path.resolve().as_uri()},
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    service = SourceAssetService(
        repo_root=tmp_path,
        cache_dir=tmp_path / "cache",
        geofabrik_index_url=index_path.resolve().as_uri(),
        prefer_local_data=False,
    )

    resolved = service.resolve_raw_source_path("raw.osm.waterways", aoi=_resolved_nairobi_aoi())
    frame = geopandas.read_file(resolved.path)

    assert resolved.source_mode == "asset_downloaded"
    assert resolved.feature_count == 1
    assert len(frame) == 1
    assert set(frame.geom_type) == {"LineString"}
    assert frame.iloc[0]["waterway_i"] == 1


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


def test_source_asset_service_uses_aoi_bbox_for_kenya_msft_reference_source(tmp_path: Path) -> None:
    inside_feature = {
        "type": "Feature",
        "properties": {"confidence": 0.9, "tile": "inside"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[36.80, -1.35], [36.80, -1.30], [36.85, -1.30], [36.85, -1.35], [36.80, -1.35]]],
        },
    }
    outside_feature = {
        "type": "Feature",
        "properties": {"confidence": 0.5, "tile": "outside"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[39.60, -4.10], [39.60, -4.00], [39.70, -4.00], [39.70, -4.10], [39.60, -4.10]]],
        },
    }

    inside_part = tmp_path / "fixtures" / "nairobi-inside.csv.gz"
    outside_part = tmp_path / "fixtures" / "nairobi-outside.csv.gz"
    _write_msft_part(inside_part, [inside_feature])
    _write_msft_part(outside_part, [outside_feature])

    index_path = tmp_path / "fixtures" / "dataset-links.csv"
    index_path.write_text(
        "\n".join(
                [
                    "Location,QuadKey,Url,Size,UploadDate",
                    f"Kenya,300110102230,{inside_part.resolve().as_uri()},1KB,2026-02-23",
                    f"Kenya,300111202231,{outside_part.resolve().as_uri()},1KB,2026-02-23",
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

    resolved = service.resolve_raw_source_path("raw.microsoft.building", aoi=_resolved_nairobi_aoi())
    frame = geopandas.read_file(resolved.path)

    assert resolved.source_mode == "asset_downloaded"
    assert resolved.feature_count == 1
    assert len(frame) == 1
    assert frame.iloc[0]["tile"] == "inside"


def test_source_asset_service_filters_non_polygon_msft_geometries_before_writing(tmp_path: Path) -> None:
    polygon_feature = {
        "type": "Feature",
        "properties": {"confidence": 0.9, "tile": "polygon"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[36.80, -1.35], [36.80, -1.30], [36.85, -1.30], [36.85, -1.35], [36.80, -1.35]]],
        },
    }
    linestring_feature = {
        "type": "Feature",
        "properties": {"confidence": 0.1, "tile": "line"},
        "geometry": {
            "type": "LineString",
            "coordinates": [[36.80, -1.35], [36.85, -1.30]],
        },
    }

    part_path = tmp_path / "fixtures" / "mixed-geometry.csv.gz"
    _write_msft_part(part_path, [polygon_feature, linestring_feature])

    index_path = tmp_path / "fixtures" / "dataset-links.csv"
    index_path.write_text(
        "\n".join(
            [
                "Location,QuadKey,Url,Size,UploadDate",
                f"Kenya,300110102230,{part_path.resolve().as_uri()},1KB,2026-02-23",
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

    resolved = service.resolve_raw_source_path("raw.microsoft.building", aoi=_resolved_nairobi_aoi())
    frame = geopandas.read_file(resolved.path)

    assert resolved.feature_count == 1
    assert len(frame) == 1
    assert set(frame.geom_type) == {"Polygon"}


def test_source_asset_service_drops_msft_features_that_clip_to_lines(tmp_path: Path) -> None:
    polygon_feature = {
        "type": "Feature",
        "properties": {"confidence": 0.9, "tile": "polygon"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[36.80, -1.35], [36.80, -1.30], [36.85, -1.30], [36.85, -1.35], [36.80, -1.35]]],
        },
    }
    edge_touching_feature = {
        "type": "Feature",
        "properties": {"confidence": 0.2, "tile": "edge"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[36.60, -1.40], [36.60, -1.30], [36.65, -1.30], [36.65, -1.40], [36.60, -1.40]]],
        },
    }

    part_path = tmp_path / "fixtures" / "clip-edge.csv.gz"
    _write_msft_part(part_path, [polygon_feature, edge_touching_feature])

    index_path = tmp_path / "fixtures" / "dataset-links.csv"
    index_path.write_text(
        "\n".join(
            [
                "Location,QuadKey,Url,Size,UploadDate",
                f"Kenya,300110102230,{part_path.resolve().as_uri()},1KB,2026-02-23",
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

    resolved = service.resolve_raw_source_path("raw.microsoft.building", aoi=_resolved_nairobi_aoi())
    frame = geopandas.read_file(resolved.path)

    assert resolved.feature_count == 1
    assert len(frame) == 1


def test_source_asset_service_redownloads_corrupt_msft_part(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inside_feature = {
        "type": "Feature",
        "properties": {"confidence": 0.9, "tile": "inside"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[36.80, -1.35], [36.80, -1.30], [36.85, -1.30], [36.85, -1.35], [36.80, -1.35]]],
        },
    }

    good_part = tmp_path / "fixtures" / "nairobi-good.csv.gz"
    corrupt_part = tmp_path / "fixtures" / "nairobi-corrupt.csv.gz"
    _write_msft_part(good_part, [inside_feature])
    _write_corrupt_gzip(corrupt_part)

    remote_url = "https://example.com/nairobi-part.csv.gz"
    index_path = tmp_path / "fixtures" / "dataset-links.csv"
    index_path.write_text(
        "\n".join(
            [
                "Location,QuadKey,Url,Size,UploadDate",
                f"Kenya,300110102230,{remote_url},1KB,2026-02-23",
            ]
        ),
        encoding="utf-8",
    )

    service = SourceAssetService(
        repo_root=tmp_path,
        cache_dir=tmp_path / "cache",
        msft_dataset_links_url=index_path.resolve().as_uri(),
        prefer_local_data=False,
        http_max_retries=2,
    )

    download_attempts: list[int] = []

    def fake_download(_url: str, target_path: Path) -> None:
        download_attempts.append(1)
        if len(download_attempts) == 1:
            shutil.copyfile(corrupt_part, target_path)
        else:
            shutil.copyfile(good_part, target_path)

    monkeypatch.setattr(service, "_download_file", fake_download)

    resolved = service.resolve_raw_source_path("raw.microsoft.building", aoi=_resolved_nairobi_aoi())
    frame = geopandas.read_file(resolved.path)

    assert len(download_attempts) == 2
    assert resolved.feature_count == 1
    assert len(frame) == 1
    assert frame.iloc[0]["tile"] == "inside"
    assert set(frame.geom_type) == {"Polygon"}


def test_source_asset_service_recognizes_track_b_b2_refs_via_local_tree(tmp_path: Path) -> None:
    _write_frame(
        tmp_path / "Data" / "roads" / "Overture" / "overture_roads.shp",
        geopandas.GeoDataFrame(
            {"segment_id": [1]},
            geometry=[LineString([(36.80, -1.35), (36.90, -1.25)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "water" / "HydroRIVERS" / "hydrorivers.shp",
        geopandas.GeoDataFrame(
            {"river_id": [1]},
            geometry=[LineString([(36.79, -1.36), (36.88, -1.24)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "water" / "HydroLAKES" / "hydrolakes.shp",
        geopandas.GeoDataFrame(
            {"lake_id": [1]},
            geometry=[Polygon([(36.78, -1.34), (36.78, -1.28), (36.84, -1.28), (36.84, -1.34)])],
            crs="EPSG:4326",
        ),
    )

    service = SourceAssetService(repo_root=tmp_path, cache_dir=tmp_path / "cache")

    overture = service.resolve_raw_source_path("raw.overture.transportation")
    hydrorivers = service.resolve_raw_source_path("raw.hydrorivers.water")
    hydrolakes = service.resolve_raw_source_path("raw.hydrolakes.water")

    assert service.can_materialize("raw.overture.transportation") is True
    assert service.can_materialize("raw.hydrorivers.water") is True
    assert service.can_materialize("raw.hydrolakes.water") is True
    assert service.can_materialize("raw.openbuildingmap.building") is True
    assert service.can_materialize("raw.local.microsoft.building") is True
    assert service.can_materialize("raw.google.open_buildings.vector") is True
    assert service.can_materialize("raw.local.water") is True
    assert service.can_materialize("raw.gns.poi") is True
    assert service.can_materialize("raw.rh.poi") is True
    assert overture.path.name == "overture_roads.shp"
    assert hydrorivers.path.name == "hydrorivers.shp"
    assert hydrolakes.path.name == "hydrolakes.shp"
    assert overture.source_mode == "local_data"
    assert hydrorivers.source_mode == "local_data"
    assert hydrolakes.source_mode == "local_data"
    assert overture.feature_count == 1
    assert hydrorivers.feature_count == 1
    assert hydrolakes.feature_count == 1


def test_source_asset_service_resolves_recursive_track_b_poi_preloads_from_aoi_hint(tmp_path: Path) -> None:
    _write_frame(
        tmp_path / "Data" / "POI" / "Kenya" / "GNS.shp",
        geopandas.GeoDataFrame(
            {"gns_id": [1]},
            geometry=[Point(36.817223, -1.286389)],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "POI" / "Kenya" / "RH.shp",
        geopandas.GeoDataFrame(
            {"rh_id": [2]},
            geometry=[Point(36.82, -1.29)],
            crs="EPSG:4326",
        ),
    )

    service = SourceAssetService(repo_root=tmp_path, cache_dir=tmp_path / "cache")

    gns = service.resolve_raw_source_path("raw.gns.poi", aoi=_resolved_nairobi_aoi())
    rh = service.resolve_raw_source_path("raw.rh.poi", aoi=_resolved_nairobi_aoi())

    assert gns.path.name == "GNS.shp"
    assert rh.path.name == "RH.shp"
    assert gns.source_mode == "local_data_clipped"
    assert rh.source_mode == "local_data_clipped"
    assert gns.feature_count == 1
    assert rh.feature_count == 1


def test_source_asset_service_treats_geonames_poi_as_gns_alias(tmp_path: Path) -> None:
    from services.source_asset_service import SourceAssetService

    gns_path = tmp_path / "Data" / "POI" / "Kenya" / "GNS.shp"
    gns_path.parent.mkdir(parents=True, exist_ok=True)
    geopandas.GeoDataFrame(
        {"ufi": [1], "full_name": ["Clinic A"], "desig_cd": ["HSP"]},
        geometry=[Point(36.8, -1.2)],
        crs="EPSG:4326",
    ).to_file(gns_path)
    service = SourceAssetService(repo_root=tmp_path, cache_dir=tmp_path / "cache")

    resolved = service.resolve_raw_source_path("raw.geonames.poi", request_bbox=(36.7, -1.3, 36.9, -1.1))

    assert resolved.source_id == "raw.gns.poi"
    assert resolved.path.exists()
    assert resolved.feature_count == 1


def test_source_asset_service_matches_repo_track_b_water_filenames_to_locked_source_ids(tmp_path: Path) -> None:
    lake_filename = "\u5e03\u9686\u8fea\u6e56\u6cca.shp"
    _write_frame(
        tmp_path / "Data" / "water" / "BDI.shp",
        geopandas.GeoDataFrame(
            {"HYRIV_ID": [1]},
            geometry=[LineString([(29.0, -3.0), (29.2, -2.8)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "water" / lake_filename,
        geopandas.GeoDataFrame(
            {"Hylak_id": [2]},
            geometry=[Polygon([(29.1, -3.1), (29.1, -2.9), (29.3, -2.9), (29.3, -3.1)])],
            crs="EPSG:4326",
        ),
    )

    service = SourceAssetService(repo_root=tmp_path, cache_dir=tmp_path / "cache")

    local_water = service.resolve_raw_source_path("raw.local.water")
    hydrorivers = service.resolve_raw_source_path("raw.hydrorivers.water")
    hydrolakes = service.resolve_raw_source_path("raw.hydrolakes.water")

    assert local_water.path.name == lake_filename
    assert hydrorivers.path.name == "BDI.shp"
    assert hydrolakes.path.name == lake_filename


def test_source_asset_service_materializes_hydrorivers_clip_from_remote_zip(tmp_path: Path) -> None:
    archive_path = tmp_path / "fixtures" / "hydrorivers_kenya.zip"
    lines = geopandas.GeoDataFrame(
        {"HYRIV_ID": [1, 2], "ORD_STRA": [4, 2], "DIS_AV_CMS": [10.0, 2.0]},
        geometry=[
            LineString([(36.80, -1.35), (36.90, -1.25)]),
            LineString([(39.60, -4.10), (39.70, -4.00)]),
        ],
        crs="EPSG:4326",
    )
    _write_frame(tmp_path / "fixtures" / "hydrorivers_src" / "HydroRIVERS_v10_kenya.shp", lines)
    zip_shapefile_bundle(tmp_path / "fixtures" / "hydrorivers_src" / "HydroRIVERS_v10_kenya.shp", archive_path)

    service = SourceAssetService(
        repo_root=tmp_path,
        cache_dir=tmp_path / "cache",
        hydrorivers_global_zip_url=archive_path.resolve().as_uri(),
        prefer_local_data=False,
    )

    resolved = service.resolve_raw_source_path(
        "raw.hydrorivers.water",
        aoi=_resolved_nairobi_aoi(),
    )
    frame = geopandas.read_file(resolved.path)

    assert resolved.source_mode == "asset_downloaded"
    assert resolved.feature_count == 1
    assert len(frame) == 1
    assert frame.iloc[0]["HYRIV_ID"] == 1


def test_source_asset_service_materializes_hydrolakes_clip_from_remote_zip(tmp_path: Path) -> None:
    archive_path = tmp_path / "fixtures" / "hydrolakes_kenya.zip"
    lakes = geopandas.GeoDataFrame(
        {"Hylak_id": [11, 22], "Lake_type": [1, 2], "Depth_avg": [6.5, 1.2]},
        geometry=[
            Polygon([(36.80, -1.35), (36.80, -1.20), (36.95, -1.20), (36.95, -1.35)]),
            Polygon([(39.60, -4.10), (39.60, -4.00), (39.75, -4.00), (39.75, -4.10)]),
        ],
        crs="EPSG:4326",
    )
    _write_frame(tmp_path / "fixtures" / "hydrolakes_src" / "HydroLAKES_polys_v10_kenya.shp", lakes)
    zip_shapefile_bundle(tmp_path / "fixtures" / "hydrolakes_src" / "HydroLAKES_polys_v10_kenya.shp", archive_path)

    service = SourceAssetService(
        repo_root=tmp_path,
        cache_dir=tmp_path / "cache",
        hydrolakes_global_zip_url=archive_path.resolve().as_uri(),
        prefer_local_data=False,
    )

    resolved = service.resolve_raw_source_path(
        "raw.hydrolakes.water",
        aoi=_resolved_nairobi_aoi(),
    )
    frame = geopandas.read_file(resolved.path)

    assert resolved.source_mode == "asset_downloaded"
    assert resolved.feature_count == 1
    assert len(frame) == 1
    assert frame.iloc[0]["Hylak_id"] == 11


def test_source_asset_service_materializes_gns_poi_from_official_country_zip(tmp_path: Path) -> None:
    archive_path = tmp_path / "fixtures" / "Kenya.zip"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    gns_rows = "\n".join(
        [
            "rk\tufi\tuni\tfull_name\tnt\tlat_dd\tlong_dd\tdesig_cd\tfc\tcc_ft\tfull_nm_nd\tgeneric\tdisplay",
            "1\t100\t200\tNairobi\tN\t-1.286389\t36.817223\tPPLA\tP\tKEN\tNAIROBI\t\t",
            "1\t101\t201\tMombasa\tN\t-4.0435\t39.6682\tPPLA\tP\tKEN\tMOMBASA\t\t",
        ]
    )
    import zipfile

    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("Kenya.txt", gns_rows)
        archive.writestr("disclaimer.txt", "test")

    index_path = tmp_path / "fixtures" / "gns-data.json"
    index_path.write_text(
        json.dumps(
            {
                "KEN": (
                    "<tr id='KEN' cc='KEN' cn='Kenya'>"
                    f"<td><a href='{archive_path.resolve().as_uri()}'>KEN</a></td></tr>"
                )
            }
        ),
        encoding="utf-8",
    )

    service = SourceAssetService(
        repo_root=tmp_path,
        cache_dir=tmp_path / "cache",
        gns_data_index_url=index_path.resolve().as_uri(),
        prefer_local_data=False,
    )

    resolved = service.resolve_raw_source_path("raw.gns.poi", aoi=_resolved_nairobi_aoi())
    frame = geopandas.read_file(resolved.path)

    assert resolved.source_mode == "asset_downloaded"
    assert resolved.feature_count == 1
    assert len(frame) == 1
    assert frame.iloc[0]["full_name"] == "Nairobi"
    assert frame.iloc[0]["cc_ft"] == "KEN"


def test_source_asset_service_materializes_overture_transportation_clip_from_remote_geojson(
    tmp_path: Path,
) -> None:
    remote_path = tmp_path / "fixtures" / "overture_transportation_kenya.geojson"
    roads = geopandas.GeoDataFrame(
        {
            "id": ["seg-1", "seg-2"],
            "class": ["primary", "residential"],
            "subclass": ["arterial", "local"],
            "surface": ["paved", "unpaved"],
            "lane_count": [2, 1],
        },
        geometry=[
            LineString([(36.80, -1.35), (36.90, -1.25)]),
            LineString([(39.60, -4.10), (39.70, -4.00)]),
        ],
        crs="EPSG:4326",
    )
    _write_frame(remote_path, roads)

    service = SourceAssetService(
        repo_root=tmp_path,
        cache_dir=tmp_path / "cache",
        overture_transportation_url=remote_path.resolve().as_uri(),
        prefer_local_data=False,
    )

    resolved = service.resolve_raw_source_path(
        "raw.overture.transportation",
        aoi=_resolved_nairobi_aoi(),
    )
    frame = geopandas.read_file(resolved.path)

    assert resolved.source_mode == "asset_downloaded"
    assert resolved.feature_count == 1
    assert len(frame) == 1
    assert frame.iloc[0]["id"] == "seg-1"


def test_source_asset_service_reuses_existing_overture_raw_segment_without_redownload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    request_bbox = (36.65, -1.45, 37.10, -1.10)
    cache_key = hashlib.sha1(repr(tuple(request_bbox)).encode("utf-8")).hexdigest()[:12]
    raw_path = (
        tmp_path
        / "cache"
        / "raw_overture_transportation"
        / cache_key
        / "segment.geojson"
    )
    roads = geopandas.GeoDataFrame(
        {
            "id": ["seg-1", "seg-2"],
            "subtype": ["road", "water"],
            "class": ["primary", "canal"],
        },
        geometry=[
            LineString([(36.80, -1.35), (36.90, -1.25)]),
            LineString([(36.80, -1.35), (36.90, -1.25)]),
        ],
        crs="EPSG:4326",
    )
    _write_frame(raw_path, roads)

    service = SourceAssetService(
        repo_root=tmp_path,
        cache_dir=tmp_path / "cache",
        prefer_local_data=False,
    )

    def _fail_download(**kwargs):
        raise AssertionError(f"unexpected download call: {kwargs}")

    monkeypatch.setattr(service, "_download_overture_transportation_segment", _fail_download)

    resolved = service.resolve_raw_source_path(
        "raw.overture.transportation",
        request_bbox=request_bbox,
    )
    frame = geopandas.read_file(resolved.path)

    assert resolved.source_mode == "asset_downloaded"
    assert resolved.feature_count == 1
    assert len(frame) == 1
    assert frame.iloc[0]["id"] == "seg-1"
