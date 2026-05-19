from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, Point

from services.track_b_national_scale_service import TrackBNationalScaleService


def _write_frame(path: Path, gdf: gpd.GeoDataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path)


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
