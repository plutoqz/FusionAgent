import json
from pathlib import Path

import pytest

from scripts.profile_p4_multi_aoi_candidates import profile_multi_aoi_candidates


ALL_SOURCES = {
    "raw.osm.road",
    "raw.microsoft.road",
    "raw.osm.building",
    "raw.microsoft.building",
    "raw.osm.water",
    "raw.hydrolakes.water",
    "raw.osm.waterways",
    "raw.hydrorivers.water",
}


def _write_geojson(path: Path, bbox: list[float]) -> None:
    x1, y1, x2, y2 = bbox
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "name": path.stem,
                "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"id": 1},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [x1, y1],
                                    [x2, y1],
                                    [x2, y2],
                                    [x1, y2],
                                    [x1, y1],
                                ]
                            ],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _manifest(tmp_path: Path, aoi_id: str, bbox: list[float], sources: set[str]) -> Path:
    asset = tmp_path / f"{aoi_id}.geojson"
    _write_geojson(asset, bbox)
    path = tmp_path / f"{aoi_id}.manifest.json"
    path.write_text(
        json.dumps(
            {
                "title": aoi_id,
                "runtime": {"target_crs": "EPSG:4326", "llm_provider": "mock"},
                "sources": [
                    {
                        "source_id": source_id,
                        "product": source_id,
                        "original_path": str(asset),
                        "clip_bbox": bbox,
                        "dataset_version": "fixture-v1",
                        "semantic_status": "fixture",
                    }
                    for source_id in sorted(sources)
                ],
                "cases": [{"case_id": "C02"}, {"case_id": "C04"}],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_candidate_inventory_finds_two_aoi_source_closure_without_runtime_calls(tmp_path: Path) -> None:
    manifests = {
        "aoi_one": _manifest(tmp_path, "aoi_one", [0.0, 0.0, 1.0, 1.0], ALL_SOURCES),
        "aoi_two": _manifest(tmp_path, "aoi_two", [2.0, 2.0, 3.0, 3.0], ALL_SOURCES),
    }

    report = profile_multi_aoi_candidates(
        manifest_paths=manifests,
        output_dir=tmp_path / "inventory",
        implementation_commit="a" * 40,
        historical_inventory_path=None,
    )

    assert report["inventory_integrity_passed"] is True
    assert report["e5_multi_aoi_source_coverage_ready"] is True
    assert report["runtime_calls"] == {"fusion_runs": 0, "llm_calls": 0, "provider_calls": 0}
    assert all(item["eligible_for_two_aoi_selection"] for item in report["formal_case_source_coverage"])


def test_candidate_inventory_reports_real_source_gap_without_fabricating_candidate(tmp_path: Path) -> None:
    manifests = {
        "aoi_one": _manifest(tmp_path, "aoi_one", [0.0, 0.0, 1.0, 1.0], ALL_SOURCES),
        "aoi_two": _manifest(
            tmp_path,
            "aoi_two",
            [2.0, 2.0, 3.0, 3.0],
            ALL_SOURCES - {"raw.microsoft.road", "raw.microsoft.building"},
        ),
    }

    report = profile_multi_aoi_candidates(
        manifest_paths=manifests,
        output_dir=tmp_path / "inventory",
        implementation_commit="a" * 40,
        historical_inventory_path=None,
    )

    assert report["inventory_integrity_passed"] is True
    assert report["e5_multi_aoi_source_coverage_ready"] is False
    assert all(
        item["source_closed_aoi_count"] == 1 for item in report["formal_case_source_coverage"]
    )


def test_candidate_inventory_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "inventory"
    output.mkdir()

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        profile_multi_aoi_candidates(
            manifest_paths={},
            output_dir=output,
            implementation_commit="a" * 40,
            historical_inventory_path=None,
        )
