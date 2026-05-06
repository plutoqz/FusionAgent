from __future__ import annotations

from pathlib import Path

import pytest

from scripts.run_benin_multisource_building_fusion import (
    _select_benin_context_vectors,
    _select_benin_rasters,
    _select_benin_vector_sources,
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
