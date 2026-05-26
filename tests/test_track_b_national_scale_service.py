from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon, mapping

from services.aoi_resolution_service import ResolvedAOI
from services.source_asset_service import SourceAssetService
from services import tiled_building_runtime_service
from services.track_b_national_scale_service import TrackBNationalScaleService


def _write_frame(path: Path, gdf: gpd.GeoDataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path)


class _NoRemoteSourceAssetService:
    def can_materialize(self, _source_id: str) -> bool:
        return False


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


def test_track_b_national_scale_service_uses_hydrolakes_as_selected_water_reference(
    tmp_path: Path,
) -> None:
    _write_frame(
        tmp_path / "Data" / "burundi-260127-free.shp" / "gis_osm_water_a_free_1.shp",
        gpd.GeoDataFrame(
            {"osm_id": [1]},
            geometry=[Polygon([(29.2, -3.3), (29.2, -3.0), (29.5, -3.0), (29.5, -3.3)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "burundi-260127-free.shp" / "gis_osm_waterways_free_1.shp",
        gpd.GeoDataFrame(
            {"osm_id": [2], "fclass": ["river"]},
            geometry=[LineString([(29.18, -3.29), (29.47, -3.03)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "water" / "布隆迪湖泊.shp",
        gpd.GeoDataFrame(
            {"Hylak_id": [11], "Lake_name": ["Rweru"], "Lake_type": [1], "Depth_avg": [6.5]},
            geometry=[Polygon([(29.25, -3.25), (29.25, -3.05), (29.45, -3.05), (29.45, -3.25)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "water" / "BDI.shp",
        gpd.GeoDataFrame(
            {"HYRIV_ID": [101], "ORD_STRA": [4], "DIS_AV_CMS": [10.0]},
            geometry=[LineString([(29.2, -3.28), (29.48, -3.02)])],
            crs="EPSG:4326",
        ),
    )

    service = TrackBNationalScaleService(root_dir=tmp_path, cache_dir=tmp_path / "cache")
    output_root = tmp_path / "evidence" / "water"
    summary = service.build_theme_evidence(
        job_type="water",
        source_id="catalog.flood.water",
        request_bbox=(29.0, -3.5, 29.8, -2.9),
        target_crs="EPSG:32735",
        output_root=output_root,
        tile_width_m=40_000.0,
        tile_height_m=40_000.0,
        overlap_m=0.0,
    )

    selected_sources = json.loads((output_root / "selected_sources.json").read_text(encoding="utf-8"))
    normalization_summary = json.loads((output_root / "normalization_summary.json").read_text(encoding="utf-8"))
    inspection_summary = json.loads((output_root / "inspection_summary.json").read_text(encoding="utf-8"))

    assert summary["claim_state"] == "national_scale_supported"
    assert selected_sources["component_source_ids"] == ["raw.osm.water", "raw.hydrolakes.water"]
    assert normalization_summary["selected_sources"]["raw.hydrolakes.water"]["feature_count"] == 1
    assert normalization_summary["supplemental_sources"]["raw.hydrorivers.water"]["feature_count"] == 1
    assert "raw.hydrorivers.water" in inspection_summary["operator_readable_summary"]["supplemental_source_ids"]


def test_track_b_national_scale_service_includes_hydrorivers_lines_in_water_output(
    tmp_path: Path,
) -> None:
    _write_frame(
        tmp_path / "Data" / "burundi-260127-free.shp" / "gis_osm_water_a_free_1.shp",
        gpd.GeoDataFrame(
            {"osm_id": [1]},
            geometry=[Polygon([(29.2, -3.3), (29.2, -3.0), (29.5, -3.0), (29.5, -3.3)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "burundi-260127-free.shp" / "gis_osm_waterways_free_1.shp",
        gpd.GeoDataFrame(
            {"osm_id": [2], "fclass": ["river"]},
            geometry=[LineString([(29.18, -3.29), (29.47, -3.03)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "water" / "布隆迪湖泊.shp",
        gpd.GeoDataFrame(
            {"Hylak_id": [11], "Lake_name": ["Rweru"], "Lake_type": [1], "Depth_avg": [6.5]},
            geometry=[Polygon([(29.25, -3.25), (29.25, -3.05), (29.45, -3.05), (29.45, -3.25)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "water" / "BDI.shp",
        gpd.GeoDataFrame(
            {"HYRIV_ID": [101], "ORD_STRA": [4], "DIS_AV_CMS": [10.0]},
            geometry=[LineString([(29.2, -3.28), (29.48, -3.02)])],
            crs="EPSG:4326",
        ),
    )

    service = TrackBNationalScaleService(root_dir=tmp_path, cache_dir=tmp_path / "cache")
    output_root = tmp_path / "evidence" / "water_lines"
    summary = service.build_theme_evidence(
        job_type="water",
        source_id="catalog.flood.water",
        request_bbox=(29.0, -3.5, 29.8, -2.9),
        target_crs="EPSG:32735",
        output_root=output_root,
        tile_width_m=40_000.0,
        tile_height_m=40_000.0,
        overlap_m=0.0,
    )

    fused = gpd.read_file(summary["artifact_path"])
    feature_kinds = {str(value) for value in fused.get("feature_kind", []) if str(value)}
    geom_types = {str(value) for value in fused.geom_type.unique()}

    assert "line" in feature_kinds
    assert any("Line" in value for value in geom_types)
    assert any("Polygon" in value for value in geom_types)


def test_track_b_national_scale_service_includes_osm_waterways_lines_in_water_output(
    tmp_path: Path,
) -> None:
    _write_frame(
        tmp_path / "Data" / "burundi-260127-free.shp" / "gis_osm_water_a_free_1.shp",
        gpd.GeoDataFrame(
            {"osm_id": [1]},
            geometry=[Polygon([(29.2, -3.3), (29.2, -3.0), (29.5, -3.0), (29.5, -3.3)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "burundi-260127-free.shp" / "gis_osm_waterways_free_1.shp",
        gpd.GeoDataFrame(
            {"osm_id": [2], "fclass": ["river"]},
            geometry=[LineString([(29.18, -3.29), (29.47, -3.03)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "water" / "布隆迪湖泊.shp",
        gpd.GeoDataFrame(
            {"Hylak_id": [11], "Lake_name": ["Rweru"], "Lake_type": [1], "Depth_avg": [6.5]},
            geometry=[Polygon([(29.25, -3.25), (29.25, -3.05), (29.45, -3.05), (29.45, -3.25)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "water" / "BDI.shp",
        gpd.GeoDataFrame(
            {"HYRIV_ID": [101], "ORD_STRA": [4], "DIS_AV_CMS": [10.0]},
            geometry=[LineString([(29.2, -3.28), (29.48, -3.02)])],
            crs="EPSG:4326",
        ),
    )

    service = TrackBNationalScaleService(root_dir=tmp_path, cache_dir=tmp_path / "cache")
    output_root = tmp_path / "evidence" / "water_osm_lines"
    summary = service.build_theme_evidence(
        job_type="water",
        source_id="catalog.flood.water",
        request_bbox=(29.0, -3.5, 29.8, -2.9),
        target_crs="EPSG:32735",
        output_root=output_root,
        tile_width_m=40_000.0,
        tile_height_m=40_000.0,
        overlap_m=0.0,
    )

    fused = gpd.read_file(summary["artifact_path"])
    osm_line_rows = fused[
        (fused.get("source_id") == "raw.osm.waterways")
        | (fused.get("feature_kind") == "line")
    ].copy()

    assert not osm_line_rows.empty
    assert any("Line" in value for value in osm_line_rows.geom_type.unique())


def test_track_b_national_scale_service_clips_water_output_to_country_boundary_when_country_hint_available(
    tmp_path: Path,
) -> None:
    _write_frame(
        tmp_path / "Data" / "burundi-260127-free.shp" / "gis_osm_water_a_free_1.shp",
        gpd.GeoDataFrame(
            {"osm_id": [1]},
            geometry=[Polygon([(0.5, 0.5), (0.5, 1.5), (1.5, 1.5), (1.5, 0.5)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "burundi-260127-free.shp" / "gis_osm_waterways_free_1.shp",
        gpd.GeoDataFrame(
            {"osm_id": [2], "fclass": ["river"]},
            geometry=[LineString([(0.2, 0.2), (1.8, 1.8)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "water" / "布隆迪湖泊.shp",
        gpd.GeoDataFrame(
            {"Hylak_id": [11], "Lake_name": ["Inner Lake"], "Lake_type": [1], "Depth_avg": [6.5]},
            geometry=[Polygon([(0.1, 0.1), (0.1, 0.8), (0.8, 0.8), (0.8, 0.1)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "water" / "BDI.shp",
        gpd.GeoDataFrame(
            {"HYRIV_ID": [101], "ORD_STRA": [4], "DIS_AV_CMS": [10.0]},
            geometry=[LineString([(0.2, 0.2), (1.8, 1.8)])],
            crs="EPSG:4326",
        ),
    )

    boundary = Polygon([(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)])
    geofabrik_index = tmp_path / "fixtures" / "geofabrik-index.json"
    geofabrik_index.parent.mkdir(parents=True, exist_ok=True)
    geofabrik_index.write_text(
        json.dumps(
            {
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "id": "testland",
                            "name": "Testland",
                            "iso3166-1:alpha2": ["tl"],
                            "urls": {"shp": "https://example.com/testland-latest-free.shp.zip"},
                        },
                        "geometry": mapping(boundary),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    service = TrackBNationalScaleService(root_dir=tmp_path, cache_dir=tmp_path / "cache")
    service.raw_source_service.source_asset_service = SourceAssetService(
        repo_root=tmp_path,
        cache_dir=tmp_path / "cache" / "source_assets",
        geofabrik_index_url=geofabrik_index.resolve().as_uri(),
    )
    output_root = tmp_path / "evidence" / "water_boundary"
    summary = service.build_theme_evidence(
        job_type="water",
        source_id="catalog.flood.water",
        request_bbox=(0.0, 0.0, 2.0, 2.0),
        target_crs="EPSG:32631",
        output_root=output_root,
        tile_width_m=50_000.0,
        tile_height_m=50_000.0,
        overlap_m=0.0,
        resolved_aoi=ResolvedAOI(
            query="Testland",
            display_name="Testland",
            country_name="Testland",
            country_code="tl",
            bbox=(0.0, 0.0, 2.0, 2.0),
            confidence=1.0,
            selection_reason="test_fixture",
            candidates=(),
        ),
    )

    fused = gpd.read_file(summary["artifact_path"]).to_crs("EPSG:4326")
    assert all(boundary.buffer(1e-9).covers(geom) for geom in fused.geometry if geom is not None and not geom.is_empty)


def test_track_b_national_scale_service_can_materialize_remote_gns_reference_with_country_hint(
    tmp_path: Path,
) -> None:
    _write_frame(
        tmp_path / "Data" / "burundi-260127-free.shp" / "gis_osm_pois_free_1.shp",
        gpd.GeoDataFrame(
            {
                "osm_id": [1, 2],
                "name": ["Clinic A", "Clinic B"],
                "fclass": ["hospital", "school"],
            },
            geometry=[Point(36.82, -1.29), Point(36.88, -1.24)],
            crs="EPSG:4326",
        ),
    )

    archive_path = tmp_path / "fixtures" / "Kenya.zip"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    gns_rows = "\n".join(
        [
            "rk\tufi\tuni\tfull_name\tnt\tlat_dd\tlong_dd\tdesig_cd\tfc\tcc_ft\tfull_nm_nd\tgeneric\tdisplay",
            "1\t100\t200\tClinic A\tN\t-1.286389\t36.817223\tHSP\tP\tKEN\tCLINIC A\t\t",
            "1\t101\t201\tClinic B\tN\t-1.240000\t36.880000\tSCH\tP\tKEN\tCLINIC B\t\t",
            "1\t102\t202\tFar Away\tN\t-4.0435\t39.6682\tPPLA\tP\tKEN\tFAR AWAY\t\t",
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

    service = TrackBNationalScaleService(root_dir=tmp_path, cache_dir=tmp_path / "cache")
    service.raw_source_service.source_asset_service = SourceAssetService(
        repo_root=tmp_path,
        cache_dir=tmp_path / "cache" / "source_assets",
        gns_data_index_url=index_path.resolve().as_uri(),
    )
    output_root = tmp_path / "evidence" / "poi_remote"
    summary = service.build_theme_evidence(
        job_type="poi",
        source_id="catalog.generic.poi",
        request_bbox=(36.65, -1.45, 37.10, -1.10),
        target_crs="EPSG:32737",
        output_root=output_root,
        tile_width_m=20_000.0,
        tile_height_m=20_000.0,
        overlap_m=0.0,
        resolved_aoi=_resolved_nairobi_aoi(),
    )

    selected_sources = json.loads((output_root / "selected_sources.json").read_text(encoding="utf-8"))
    normalization_summary = json.loads((output_root / "normalization_summary.json").read_text(encoding="utf-8"))
    inspection_summary = json.loads((output_root / "inspection_summary.json").read_text(encoding="utf-8"))

    assert summary["claim_state"] == "national_scale_supported"
    assert selected_sources["component_source_ids"] == ["raw.osm.poi", "raw.gns.poi"]
    assert normalization_summary["selected_sources"]["raw.gns.poi"]["feature_count"] == 2
    assert inspection_summary["claim_state"] == "national_scale_supported"
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


def test_track_b_national_scale_service_uses_non_empty_overture_reference_when_available(
    tmp_path: Path,
) -> None:
    _write_frame(
        tmp_path / "Data" / "roads" / "OSM" / "clip_road2.shp",
        gpd.GeoDataFrame(
            {
                "osm_id": [1],
                "fclass": ["primary"],
                "name": ["RN 1"],
            },
            geometry=[LineString([(29.2, -3.3), (29.5, -3.2)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "roads" / "Overture" / "road_segments.shp",
        gpd.GeoDataFrame(
            {
                "id": ["seg-1"],
                "class": ["primary"],
                "subtype": ["road"],
                "names_primary": ["Overture RN 1"],
                "lane_count": [2],
            },
            geometry=[LineString([(29.21, -3.29), (29.49, -3.21)])],
            crs="EPSG:4326",
        ),
    )

    service = TrackBNationalScaleService(root_dir=tmp_path, cache_dir=tmp_path / "cache")
    output_root = tmp_path / "evidence" / "road_non_empty_ref"
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
    normalization_summary = json.loads((output_root / "normalization_summary.json").read_text(encoding="utf-8"))
    inspection_summary = json.loads((output_root / "inspection_summary.json").read_text(encoding="utf-8"))

    assert summary["claim_state"] == "national_scale_supported"
    assert selected_sources["component_coverage"]["raw.overture.transportation"]["feature_count"] == 1
    assert normalization_summary["selected_sources"]["raw.overture.transportation"]["feature_count"] == 1
    assert inspection_summary["claim_state"] == "national_scale_supported"
