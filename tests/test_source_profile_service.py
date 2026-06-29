from __future__ import annotations

from pathlib import Path

import pytest

geopandas = pytest.importorskip("geopandas")
from shapely.geometry import Point, Polygon

from services.source_profile_service import SourceProfileService, classify_height_semantics


def _write_frame(path: Path, frame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(path)


def test_classify_height_semantics_prefers_presence_only_for_google_presence_raster() -> None:
    assert (
        classify_height_semantics(
            source_name="google building presence",
            field_names=[],
            raster_band_description="building presence",
        )
        == "presence_only"
    )


def test_profile_vector_source_reads_feature_count_crs_and_fields(tmp_path: Path) -> None:
    profile = SourceProfileService().profile_vector_source(
        source_id="raw.openbuildingmap.building",
        path=tmp_path / "openbuildingmap_benin.shp",
        feature_count=5673640,
        crs="EPSG:4326",
        field_names=["id", "floorspace", "occupancy", "height"],
    )

    assert profile.source_form == "vector"
    assert profile.feature_count == 5673640
    assert profile.height_fields == ["height"]
    assert profile.height_semantics == "estimated_height"


def test_profile_raster_source_degrades_when_gdalinfo_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    raster_path = tmp_path / "height_8c2a4_2023_06_30_tile.tif"
    raster_path.write_bytes(b"fake-height")
    monkeypatch.setattr(
        "services.source_profile_service.gdalinfo_json",
        lambda _path: (_ for _ in ()).throw(FileNotFoundError("gdalinfo executable not found on PATH")),
    )

    profile = SourceProfileService().profile_raster_source(
        source_id="raw.google.open_buildings_2_5d.height_raster",
        source_name="Open Buildings 2.5D Height Raster",
        path=raster_path,
        runtime_status="runtime_candidate",
        selectable_now=True,
    )

    assert profile.source_form == "raster"
    assert profile.height_semantics == "estimated_height"
    assert profile.metadata["profile_degraded"] is True


def test_profile_benin_root_prefers_non_empty_microsoft_candidate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_frame(
        tmp_path / "final_shp" / "openstreetmap" / "openstreetmap_benin.shp",
        geopandas.GeoDataFrame(
            {"osm_id": [1], "fclass": ["building"]},
            geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "final_shp" / "openbuildingmap" / "openbuildingmap_benin.shp",
        geopandas.GeoDataFrame(
            {"id": [1], "height": [12.5]},
            geometry=[Polygon([(0, 0), (0, 2), (2, 2), (2, 0)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "final_shp" / "google_open_buildings_v3" / "google_open_buildings_v3_benin.shp",
        geopandas.GeoDataFrame(
            {"confidence": [0.91]},
            geometry=[Polygon([(0, 0), (0, 3), (3, 3), (3, 0)])],
            crs="EPSG:4326",
        ),
    )
    msft_dir = tmp_path / "final_shp" / "microsoft_global_ml_building_footprints"
    _write_frame(
        msft_dir / "Microsoft_benin.shp",
        geopandas.GeoDataFrame(
            {"height": [8.0], "confidence": [0.7]},
            geometry=[Polygon([(0, 0), (0, 4), (4, 4), (4, 0)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        msft_dir / "microsoft_global_ml_building_footprints_benin.shp",
        geopandas.GeoDataFrame(
            {"height": [], "confidence": []},
            geometry=[],
            crs="EPSG:4326",
        ),
    )

    raster_path = (
        tmp_path
        / "_processing"
        / "google_open_buildings_temporal_2023"
        / "building_presence_2023_benin_4m.tif"
    )
    raster_path.parent.mkdir(parents=True, exist_ok=True)
    raster_path.write_bytes(b"fake-raster")

    monkeypatch.setattr(
        "services.source_profile_service.gdalinfo_json",
        lambda path: {
            "description": str(path),
            "bands": [{"description": "building presence", "type": "Float32"}],
            "coordinateSystem": {"wkt": "EPSG:32631"},
            "size": [10, 20],
        },
    )

    payload = SourceProfileService().profile_benin_root(tmp_path)
    profiles = {item["source_id"]: item for item in payload["profiles"]}

    assert profiles["raw.local.microsoft.building"]["canonical_path"].endswith("Microsoft_benin.shp")
    assert profiles["raw.local.microsoft.building"]["feature_count"] == 1
    assert profiles["raw.local.microsoft.building"]["metadata"]["rejected_candidate_paths"]
    assert profiles["raw.openbuildingmap.building"]["height_fields"] == ["height"]
    assert profiles["raw.google.building_presence.raster"]["height_semantics"] == "presence_only"
    assert profiles["raw.google.building_presence.raster"]["source_form"] == "raster"


def test_profile_benin_root_includes_optional_height_raster_when_present(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_frame(
        tmp_path / "final_shp" / "openstreetmap" / "openstreetmap_benin.shp",
        geopandas.GeoDataFrame({"osm_id": [1]}, geometry=[Point(0, 0).buffer(1)], crs="EPSG:4326"),
    )
    _write_frame(
        tmp_path / "final_shp" / "openbuildingmap" / "openbuildingmap_benin.shp",
        geopandas.GeoDataFrame({"height": [11.0]}, geometry=[Point(0, 0).buffer(1)], crs="EPSG:4326"),
    )
    _write_frame(
        tmp_path / "final_shp" / "google_open_buildings_v3" / "google_open_buildings_v3_benin.shp",
        geopandas.GeoDataFrame({"confidence": [0.9]}, geometry=[Point(0, 0).buffer(1)], crs="EPSG:4326"),
    )
    _write_frame(
        tmp_path / "final_shp" / "microsoft_global_ml_building_footprints" / "Microsoft_benin.shp",
        geopandas.GeoDataFrame({"height": [8.0]}, geometry=[Point(0, 0).buffer(1)], crs="EPSG:4326"),
    )
    raster_dir = tmp_path / "_processing" / "google_open_buildings_temporal_2023"
    raster_dir.mkdir(parents=True, exist_ok=True)
    (raster_dir / "building_presence_2023_benin_4m.tif").write_bytes(b"fake-presence")
    (raster_dir / "building_height_2023_benin_4m.tif").write_bytes(b"fake-height")

    def fake_gdalinfo(path):
        return {
            "description": str(path),
            "bands": [
                {
                    "description": "building height" if "height" in str(path) else "building presence",
                    "type": "Float32",
                }
            ],
            "coordinateSystem": {"wkt": "EPSG:32631"},
            "size": [10, 20],
        }

    monkeypatch.setattr("services.source_profile_service.gdalinfo_json", fake_gdalinfo)

    profiles = {item["source_id"]: item for item in SourceProfileService().profile_benin_root(tmp_path)["profiles"]}

    assert profiles["raw.google.building_height.raster"]["source_form"] == "raster"
    assert profiles["raw.google.building_height.raster"]["height_semantics"] == "estimated_height"

