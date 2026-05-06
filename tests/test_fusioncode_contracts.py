from __future__ import annotations

from pathlib import Path

from fusion_algorithms.contracts import (
    BuildingMatchParams,
    BuildingRasterPresenceParams,
    RasterSpec,
    SourceSpec,
)


def test_source_spec_normalizes_labels() -> None:
    spec = SourceSpec(name=" ms ", path=Path("a.gpkg"), priority=10)
    assert spec.name == "MS"
    assert spec.path == Path("a.gpkg")
    assert spec.priority == 10


def test_raster_spec_requires_kind() -> None:
    spec = RasterSpec(kind="Building_Height", path=Path("height.vrt"))
    assert spec.kind == "building_height"
    assert spec.path == Path("height.vrt")


def test_building_match_defaults_mirror_fusioncode_config() -> None:
    params = BuildingMatchParams()
    assert params.weak_min_cover == 0.05
    assert params.weak_min_iou == 0.05
    assert params.thresh_1_to_1 == 0.40
    assert params.thresh_1_to_N == 0.44
    assert params.thresh_M_to_N == 0.47


def test_presence_defaults_mirror_fusioncode_config() -> None:
    params = BuildingRasterPresenceParams()
    assert params.prob_threshold == 0.20
    assert params.search_dist_m == 4.0
    assert params.confirmed_score_threshold == 0.55
    assert params.uncertain_score_threshold == 0.30
