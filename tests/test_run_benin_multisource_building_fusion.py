from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import run_benin_multisource_building_fusion
from scripts.run_benin_multisource_building_fusion import (
    _select_benin_context_vectors,
    _select_benin_rasters,
    _select_benin_vector_sources,
)
from services.tile_partition_service import TileManifest, TileSpec
from services.tiled_building_runtime_service import (
    TiledMultiSourceBuildingRunResult,
)


def _profile(source_id: str, path: Path) -> dict[str, object]:
    return {"source_id": source_id, "canonical_path": str(path)}


def test_select_benin_vector_sources_requires_four_building_sources(tmp_path: Path) -> None:
    profile_map = {
        "raw.osm.building": _profile("raw.osm.building", tmp_path / "osm.shp"),
        "raw.local.microsoft.building": _profile("raw.local.microsoft.building", tmp_path / "ms.shp"),
        "raw.openbuildingmap.building": _profile("raw.openbuildingmap.building", tmp_path / "obm.shp"),
        "raw.google.open_buildings.vector": _profile("raw.google.open_buildings.vector", tmp_path / "gg.shp"),
    }

    sources = _select_benin_vector_sources(profile_map)

    assert tuple(sources) == ("MS", "OBM", "GG", "OSM")
    assert sources["MS"] == tmp_path / "ms.shp"
    assert sources["OBM"] == tmp_path / "obm.shp"
    assert sources["GG"] == tmp_path / "gg.shp"
    assert sources["OSM"] == tmp_path / "osm.shp"


def test_select_benin_vector_sources_fails_when_required_source_missing(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="raw.google.open_buildings.vector"):
        _select_benin_vector_sources(
            {
                "raw.osm.building": _profile("raw.osm.building", tmp_path / "osm.shp"),
                "raw.local.microsoft.building": _profile("raw.local.microsoft.building", tmp_path / "ms.shp"),
                "raw.openbuildingmap.building": _profile("raw.openbuildingmap.building", tmp_path / "obm.shp"),
            }
        )


def test_select_benin_rasters_includes_height_only_when_profile_exists(tmp_path: Path) -> None:
    rasters = _select_benin_rasters(
        {
            "raw.google.building_presence.raster": _profile(
                "raw.google.building_presence.raster",
                tmp_path / "presence.tif",
            ),
            "raw.google.building_height.raster": _profile(
                "raw.google.building_height.raster",
                tmp_path / "height.tif",
            ),
        }
    )

    assert rasters == {
        "building_presence": tmp_path / "presence.tif",
        "building_height": tmp_path / "height.tif",
    }


def test_select_benin_context_vectors_includes_optional_roads(tmp_path: Path) -> None:
    road_path = tmp_path / "roads.shp"
    road_path.write_text("placeholder", encoding="utf-8")

    assert _select_benin_context_vectors(road_path) == {"roads": road_path}


def test_select_benin_context_vectors_omits_missing_roads() -> None:
    assert _select_benin_context_vectors(None) == {}


def _single_tile_manifest() -> TileManifest:
    return TileManifest(
        bbox=(0.75, 6.10, 3.90, 12.50),
        bbox_crs="EPSG:4326",
        working_crs="EPSG:32631",
        tile_width_m=10000.0,
        tile_height_m=10000.0,
        overlap_m=96.0,
        tiles=[
            TileSpec(
                tile_id="tile_000_000",
                bbox=(0.75, 6.10, 3.90, 12.50),
                buffered_bbox=(0.74, 6.09, 3.91, 12.51),
                working_bbox=(0.75, 6.10, 3.90, 12.50),
                working_buffered_bbox=(0.74, 6.09, 3.91, 12.51),
                row=0,
                col=0,
            )
        ],
    )


def test_multisource_validation_main_writes_selected_sources_timing_and_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_root = tmp_path / "source-root"
    output_root = tmp_path / "validation-output"
    road_path = tmp_path / "roads.shp"
    road_path.write_text("placeholder", encoding="utf-8")
    output_path = output_root / "runtime_output" / "fused_buildings.gpkg"
    manifest = _single_tile_manifest()

    profile_payload = {
        "profiles": [
            _profile("raw.local.microsoft.building", source_root / "ms.shp"),
            _profile("raw.openbuildingmap.building", source_root / "obm.shp"),
            _profile("raw.google.open_buildings.vector", source_root / "gg.shp"),
            _profile("raw.osm.building", source_root / "osm.shp"),
            _profile("raw.google.building_presence.raster", source_root / "presence.tif"),
            _profile("raw.google.building_height.raster", source_root / "height.tif"),
        ]
    }

    monkeypatch.setattr(
        run_benin_multisource_building_fusion.SourceProfileService,
        "profile_benin_root",
        lambda self, root: profile_payload,
    )
    monkeypatch.setattr(
        run_benin_multisource_building_fusion.TilePartitionService,
        "partition_bbox",
        lambda self, **kwargs: manifest,
    )

    def fake_run_tiled_multisource_building_job(self, **kwargs) -> TiledMultiSourceBuildingRunResult:
        on_event = kwargs["on_event"]
        on_event("tile_execution_started", {"tile_id": "tile_000_000"})
        on_event("tile_execution_completed", {"tile_id": "tile_000_000", "feature_count": 7})
        return TiledMultiSourceBuildingRunResult(
            output_path=output_path,
            tile_count=1,
            stitched_feature_count=7,
            tile_outputs=[],
        )

    monkeypatch.setattr(
        run_benin_multisource_building_fusion.TiledBuildingRuntimeService,
        "run_tiled_multisource_building_job",
        fake_run_tiled_multisource_building_job,
    )
    monkeypatch.setattr(
        run_benin_multisource_building_fusion.sys,
        "argv",
        [
            "run_benin_multisource_building_fusion.py",
            "--source-root",
            str(source_root),
            "--output-root",
            str(output_root),
            "--road-shp",
            str(road_path),
        ],
    )

    run_benin_multisource_building_fusion.main()

    source_profile_snapshot = json.loads(
        (output_root / "source_profile_snapshot.json").read_text(encoding="utf-8")
    )
    selected_sources = json.loads(
        (output_root / "selected_sources.json").read_text(encoding="utf-8")
    )
    tile_manifest = json.loads(
        (output_root / "tile_manifest.json").read_text(encoding="utf-8")
    )
    timing = json.loads((output_root / "timing.json").read_text(encoding="utf-8"))
    summary = (output_root / "benchmark_summary.md").read_text(encoding="utf-8")

    assert len(source_profile_snapshot["profiles"]) == 6
    assert selected_sources["source_priority_order"] == ["MS", "OBM", "GG", "OSM"]
    assert selected_sources["vector_sources"]["MS"].endswith("ms.shp")
    assert selected_sources["raster_sources"]["building_presence"].endswith("presence.tif")
    assert selected_sources["context_vectors"] == {"roads": str(road_path)}
    assert tile_manifest["tiles"][0]["tile_id"] == "tile_000_000"
    assert timing["tile_count"] == 1
    assert timing["stitched_feature_count"] == 7
    assert [event["kind"] for event in timing["events"]] == [
        "tile_execution_started",
        "tile_execution_completed",
    ]
    assert "# Large-AOI Multi-Source Building Validation" in summary
    assert "source priority order" in summary
    assert "raster inputs" in summary
