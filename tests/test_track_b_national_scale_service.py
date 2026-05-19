from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, Point

from services import tiled_building_runtime_service
from services.track_b_national_scale_service import TrackBNationalScaleService


def _write_frame(path: Path, gdf: gpd.GeoDataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path)


class _NoRemoteSourceAssetService:
    def can_materialize(self, _source_id: str) -> bool:
        return False


def test_track_b_national_scale_service_writes_building_evidence_with_multisource_fusion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    building_geom = Point(29.5, -3.2).buffer(0.01)
    _write_frame(
        tmp_path / "Data" / "buildings" / "OSM" / "osm_buildings.shp",
        gpd.GeoDataFrame(
            {
                "osm_id": [1],
                "height": [4.0],
                "name": ["OSM Building"],
            },
            geometry=[building_geom],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "buildings" / "Microsoft" / "microsoft_buildings.shp",
        gpd.GeoDataFrame(
            {
                "id": ["ms-1"],
                "height": [9.0],
            },
            geometry=[building_geom],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "buildings" / "Google" / "google_buildings.shp",
        gpd.GeoDataFrame(
            {
                "id": ["gg-1"],
                "height": [7.0],
                "confidence": [0.88],
            },
            geometry=[building_geom],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "buildings" / "OpenBuildingMap" / "obm_buildings.shp",
        gpd.GeoDataFrame(
            {
                "id": ["obm-1"],
                "height": [11.0],
            },
            geometry=[building_geom],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "buildings" / "GoogleOpenBuildingsVector" / "gobv_buildings.shp",
        gpd.GeoDataFrame(
            {
                "id": ["gobv-1"],
                "height": [6.0],
                "confidence": [0.81],
            },
            geometry=[building_geom],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "buildings" / "MicrosoftLocal" / "microsoft_local_buildings.shp",
        gpd.GeoDataFrame(
            {
                "id": ["ms-local-1"],
                "height": [8.0],
            },
            geometry=[building_geom],
            crs="EPSG:4326",
        ),
    )

    def fake_multisource(source_map, roads, params, source_priority_order):
        del roads, params
        assert tuple(source_priority_order) == (
            "MS",
            "OBM",
            "GOOGLE_OPEN_BUILDINGS",
            "GOOGLE",
            "OSM",
        )
        reference = next(iter(source_map.values()))
        return gpd.GeoDataFrame(
            {"height_fused": [9.0]},
            geometry=[reference.geometry.iloc[0]],
            crs=reference.crs,
        )

    monkeypatch.setattr(
        tiled_building_runtime_service,
        "run_cascaded_multi_source_fusion",
        fake_multisource,
    )

    service = TrackBNationalScaleService(root_dir=tmp_path, cache_dir=tmp_path / "cache")
    output_root = tmp_path / "evidence" / "building"
    summary = service.build_theme_evidence(
        job_type="building",
        source_id="catalog.earthquake.building",
        request_bbox=(29.0, -3.5, 30.1, -2.8),
        target_crs="EPSG:32735",
        output_root=output_root,
        tile_width_m=40_000.0,
        tile_height_m=40_000.0,
        overlap_m=0.0,
    )

    selected_sources = json.loads((output_root / "selected_sources.json").read_text(encoding="utf-8"))
    normalization_summary = json.loads((output_root / "normalization_summary.json").read_text(encoding="utf-8"))
    stitched_artifact = json.loads((output_root / "stitched_artifact.json").read_text(encoding="utf-8"))
    inspection_summary = json.loads((output_root / "inspection_summary.json").read_text(encoding="utf-8"))
    fused = gpd.read_file(summary["artifact_path"])

    assert summary["claim_state"] == "national_scale_supported"
    assert selected_sources["selected_source_id"] == "catalog.earthquake.building"
    assert selected_sources["component_source_ids"] == ["raw.osm.building", "raw.microsoft.building"]
    assert selected_sources["fusion_summary"]["vector_source_ids"] == [
        "raw.microsoft.building",
        "raw.openbuildingmap.building",
        "raw.google.open_buildings.vector",
        "raw.google.building",
        "raw.osm.building",
    ]
    assert "raw.google.building" in normalization_summary["supplemental_sources"]
    assert float(fused.loc[0, "height_ms"]) == 9.0
    assert float(fused.loc[0, "height_obm"]) == 11.0
    assert float(fused.loc[0, "height_google"]) == 7.0
    assert float(fused.loc[0, "height_final"]) == 11.0
    assert fused.loc[0, "height_final_source"] == "height_obm"
    assert stitched_artifact["fusion_summary"]["source_priority_order"][0] == "MS"
    assert inspection_summary["operator_readable_summary"]["fusion_summary"]["vector_source_ids"][0] == "raw.microsoft.building"


def test_track_b_national_scale_service_writes_poi_evidence_with_real_tiling(tmp_path: Path) -> None:
    _write_frame(
        tmp_path / "Data" / "burundi-260127-free.shp" / "gis_osm_pois_free_1.shp",
        gpd.GeoDataFrame(
            {
                "osm_id": [1, 2],
                "name": ["Clinic A", "Clinic B"],
                "fclass": ["hospital", "school"],
            },
            geometry=[Point(29.2, -3.3), Point(30.1, -2.9)],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "POI" / "Burundi" / "GNS.shp",
        gpd.GeoDataFrame(
            {
                "ufi": [11, 12],
                "full_name": ["Clinic A", "Clinic B"],
                "desig_cd": ["HSP", "SCH"],
            },
            geometry=[Point(29.2, -3.3), Point(30.1, -2.9)],
            crs="EPSG:4326",
        ),
    )

    service = TrackBNationalScaleService(root_dir=tmp_path, cache_dir=tmp_path / "cache")
    output_root = tmp_path / "evidence" / "poi"
    summary = service.build_theme_evidence(
        job_type="poi",
        source_id="catalog.generic.poi",
        request_bbox=(29.0, -3.5, 30.4, -2.7),
        target_crs="EPSG:32735",
        output_root=output_root,
        tile_width_m=50_000.0,
        tile_height_m=50_000.0,
        overlap_m=0.0,
    )

    tile_manifest = json.loads((output_root / "tile_manifest.json").read_text(encoding="utf-8"))
    selected_sources = json.loads((output_root / "selected_sources.json").read_text(encoding="utf-8"))
    normalization_summary = json.loads((output_root / "normalization_summary.json").read_text(encoding="utf-8"))
    stitched_artifact = json.loads((output_root / "stitched_artifact.json").read_text(encoding="utf-8"))
    inspection_summary = json.loads((output_root / "inspection_summary.json").read_text(encoding="utf-8"))

    assert summary["claim_state"] == "national_scale_supported"
    assert tile_manifest["manifest_mode"] == "national_bbox_tiling"
    assert tile_manifest["tile_count"] >= 2
    assert selected_sources["selected_source_id"] == "catalog.generic.poi"
    assert selected_sources["component_source_ids"] == ["raw.osm.poi", "raw.gns.poi"]
    assert normalization_summary["selected_sources"]["raw.gns.poi"]["feature_count"] == 2
    assert "GeoHash" in normalization_summary["selected_sources"]["raw.gns.poi"]["columns"]
    assert stitched_artifact["tile_count"] == tile_manifest["tile_count"]
    assert len(stitched_artifact["tile_outputs"]) == tile_manifest["tile_count"]
    assert stitched_artifact["artifact_metrics"]["artifact_validity"] is True
    assert inspection_summary["claim_state"] == "national_scale_supported"
    assert inspection_summary["evidence"]["stitched_artifact"] == "stitched_artifact.json"
    assert Path(inspection_summary["artifact_path"]).exists()


def test_track_b_national_scale_service_marks_road_evidence_as_partial_when_manual_ref_is_missing(
    tmp_path: Path,
) -> None:
    _write_frame(
        tmp_path / "Data" / "roads" / "OSM" / "clip_road2.shp",
        gpd.GeoDataFrame(
            {
                "osm_id": [1, 2],
                "fclass": ["primary", "secondary"],
                "name": ["RN 1", "RN 2"],
            },
            geometry=[
                LineString([(29.2, -3.3), (29.5, -3.2)]),
                LineString([(29.6, -3.1), (29.9, -3.0)]),
            ],
            crs="EPSG:4326",
        ),
    )

    service = TrackBNationalScaleService(root_dir=tmp_path, cache_dir=tmp_path / "cache")
    service.raw_source_service.source_asset_service = _NoRemoteSourceAssetService()
    output_root = tmp_path / "evidence" / "road"
    summary = service.build_theme_evidence(
        job_type="road",
        source_id="catalog.flood.road",
        request_bbox=(29.0, -3.5, 30.1, -2.8),
        target_crs="EPSG:32735",
        output_root=output_root,
        tile_width_m=40_000.0,
        tile_height_m=40_000.0,
        overlap_m=0.0,
    )

    selected_sources = json.loads((output_root / "selected_sources.json").read_text(encoding="utf-8"))
    stitched_artifact = json.loads((output_root / "stitched_artifact.json").read_text(encoding="utf-8"))
    inspection_summary = json.loads((output_root / "inspection_summary.json").read_text(encoding="utf-8"))

    assert summary["claim_state"] == "national_scale_partial_reference"
    assert selected_sources["component_source_ids"] == ["raw.osm.road", "raw.overture.transportation"]
    assert selected_sources["component_coverage"]["raw.overture.transportation"]["feature_count"] == 0
    assert stitched_artifact["artifact_path"] == summary["artifact_path"]
    assert stitched_artifact["stitched_feature_count"] == inspection_summary["artifact_metrics"]["feature_count"]
    assert inspection_summary["claim_state"] == "national_scale_partial_reference"
    assert inspection_summary["evidence"]["stitched_artifact"] == "stitched_artifact.json"
