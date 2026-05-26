from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString

from services.track_b_national_scale_service import TrackBNationalScaleService


def _write_frame(path: Path, gdf: gpd.GeoDataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path)


def test_track_b_national_scale_service_road_writes_v7_fusion_stats(tmp_path: Path) -> None:
    _write_frame(
        tmp_path / "Data" / "roads" / "OSM" / "roads.shp",
        gpd.GeoDataFrame(
            {"osm_id": [1], "fclass": ["primary"], "name": ["OSM Road"]},
            geometry=[LineString([(29.2, -3.3), (29.5, -3.2)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "roads" / "Overture" / "roads.shp",
        gpd.GeoDataFrame(
            {"id": ["seg-1"], "class": ["primary"], "names_primary": ["Ref Road"], "lane_count": [2]},
            geometry=[LineString([(29.21, -3.29), (29.49, -3.21)])],
            crs="EPSG:4326",
        ),
    )

    service = TrackBNationalScaleService(root_dir=tmp_path, cache_dir=tmp_path / "cache")
    output_root = tmp_path / "evidence" / "road_v7"
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

    fusion_stats = json.loads((output_root / "fusion_stats.json").read_text(encoding="utf-8"))
    stitched_artifact = json.loads((output_root / "stitched_artifact.json").read_text(encoding="utf-8"))
    inspection_summary = json.loads((output_root / "inspection_summary.json").read_text(encoding="utf-8"))
    fused = gpd.read_file(summary["artifact_path"])

    assert fusion_stats["algorithm_id"] == "algo.fusion.road.conflation.v7"
    assert fusion_stats["stats"]["base_segments"] >= 1
    assert fused.geom_type.isin(["LineString", "MultiLineString"]).all()
    assert stitched_artifact["algorithm_id"] == "algo.fusion.road.conflation.v7"
    assert "config_snapshot" in stitched_artifact
    assert inspection_summary["evidence"]["fusion_stats"] == "fusion_stats.json"
    assert inspection_summary["operator_readable_summary"]["algorithm_id"] == "algo.fusion.road.conflation.v7"


def test_track_b_national_scale_service_supports_waterways_theme_with_line_only_output(tmp_path: Path) -> None:
    _write_frame(
        tmp_path / "Data" / "burundi-260127-free.shp" / "gis_osm_waterways_free_1.shp",
        gpd.GeoDataFrame(
            {"osm_id": [1], "fclass": ["river"], "name": ["OSM River"]},
            geometry=[LineString([(29.2, -3.3), (29.5, -3.2)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "water" / "Pakistan_Waterways_Data.shp",
        gpd.GeoDataFrame(
            {
                "osm_id": [101],
                "waterway": ["stream"],
                "name": ["Local Stream"],
                "name_en": ["Local Stream"],
                "name_ur": ["local_ur"],
                "source": ["manual"],
            },
            geometry=[LineString([(29.3, -3.1), (29.6, -2.9)])],
            crs="EPSG:4326",
        ),
    )

    service = TrackBNationalScaleService(root_dir=tmp_path, cache_dir=tmp_path / "cache")
    output_root = tmp_path / "evidence" / "waterways_v7"
    summary = service.build_theme_evidence(
        job_type="waterways",
        source_id="catalog.flood.waterways",
        request_bbox=(29.0, -3.5, 30.1, -2.8),
        target_crs="EPSG:32735",
        output_root=output_root,
        tile_width_m=40_000.0,
        tile_height_m=40_000.0,
        overlap_m=0.0,
    )

    fusion_stats = json.loads((output_root / "fusion_stats.json").read_text(encoding="utf-8"))
    normalization_summary = json.loads((output_root / "normalization_summary.json").read_text(encoding="utf-8"))
    fused = gpd.read_file(summary["artifact_path"])

    assert fusion_stats["algorithm_id"] == "algo.fusion.waterways.conflation.v7"
    assert normalization_summary["selected_sources"]["raw.osm.waterways"]["source_id"] == "raw.osm.waterways"
    assert normalization_summary["selected_sources"]["raw.local.pakistan.waterways"]["source_id"] == "raw.local.pakistan.waterways"
    assert fused.geom_type.isin(["LineString", "MultiLineString"]).all()
    assert "waterway_class" in fused.columns
