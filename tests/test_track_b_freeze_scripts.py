from __future__ import annotations

import json
from pathlib import Path

from scripts import build_track_b_national_evidence as evidence_cli
from scripts.freeze_track_b_national_evidence import freeze_track_b_national_evidence
from scripts.freeze_track_b_smoke_evidence import SmokeSnapshot, freeze_track_b_smoke_evidence
from services.track_b_national_scale_service import TrackBNationalScaleService


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_build_track_b_national_evidence_parse_args_accepts_google_source_options() -> None:
    args = evidence_cli.parse_args(
        [
            "--job-type",
            "poi",
            "--bbox",
            "36.7,-1.3,36.9,-1.1",
            "--target-crs",
            "EPSG:32737",
            "--output-root",
            "runs/evidence",
            "--google-open-buildings-url",
            "file:///tmp/google-open-buildings-1.csv",
            "--google-open-buildings-url",
            "file:///tmp/google-open-buildings-2.csv",
            "--google-poi-authorization",
            "config/google-poi-authorization.json",
            "--google-places-api-key-env",
            "TEST_GOOGLE_PLACES_API_KEY",
            "--require-full-autonomous-closure",
        ]
    )

    assert args.google_open_buildings_url == [
        "file:///tmp/google-open-buildings-1.csv",
        "file:///tmp/google-open-buildings-2.csv",
    ]
    assert args.google_poi_authorization == "config/google-poi-authorization.json"
    assert args.google_places_api_key_env == "TEST_GOOGLE_PLACES_API_KEY"
    assert args.require_full_autonomous_closure is True


def test_build_track_b_national_evidence_requires_full_autonomous_closure(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    captured_init: dict[str, object] = {}

    class _FakeTrackBNationalScaleService:
        def __init__(self, **kwargs) -> None:
            captured_init.update(kwargs)

        def build_theme_evidence(self, **kwargs) -> dict:
            output_root = Path(kwargs["output_root"])
            _write_json(
                output_root / "inspection_summary.json",
                {
                    "autonomous_readiness": {
                        "status": "system_failure",
                        "missing_required_source_ids": ["raw.google.poi", "raw.gns.poi"],
                    }
                },
            )
            return {
                "claim_state": "national_scale_partial_reference",
                "tile_count": 1,
                "artifact_path": str(output_root / "poi_national_scale_fused.gpkg"),
            }

    monkeypatch.setenv("TEST_GOOGLE_PLACES_API_KEY", "secret-test-key")
    monkeypatch.setattr(evidence_cli, "TrackBNationalScaleService", _FakeTrackBNationalScaleService)

    result = evidence_cli.main(
        [
            "--job-type",
            "poi",
            "--bbox",
            "36.7,-1.3,36.9,-1.1",
            "--target-crs",
            "EPSG:32737",
            "--output-root",
            str(tmp_path / "evidence"),
            "--google-open-buildings-url",
            "file:///tmp/google-open-buildings.csv",
            "--google-poi-authorization",
            str(tmp_path / "google-poi-authorization.json"),
            "--google-places-api-key-env",
            "TEST_GOOGLE_PLACES_API_KEY",
            "--google-places-cache-key",
            "places-fixture-v1",
            "--require-full-autonomous-closure",
        ]
    )

    assert result == 2
    assert captured_init["google_open_buildings_urls"] == ["file:///tmp/google-open-buildings.csv"]
    assert captured_init["google_poi_authorization_path"] == tmp_path / "google-poi-authorization.json"
    assert captured_init["google_places_api_key"] == "secret-test-key"
    assert captured_init["google_places_cache_key"] == "places-fixture-v1"

    output = capsys.readouterr().out
    assert "full_autonomous_closure_required" in output
    assert "status=system_failure" in output
    assert "raw.google.poi" in output
    assert "raw.gns.poi" in output


def test_track_b_national_scale_service_threads_google_source_options(tmp_path: Path) -> None:
    auth_path = tmp_path / "google-poi-authorization.json"
    service = TrackBNationalScaleService(
        root_dir=tmp_path,
        cache_dir=tmp_path / "cache",
        google_open_buildings_urls=["file:///tmp/google-open-buildings.csv"],
        google_poi_authorization_path=auth_path,
        google_places_api_key="secret-test-key",
        google_places_cache_key="places-fixture-v1",
    )

    source_asset_service = service.raw_source_service.source_asset_service
    assert source_asset_service.google_open_buildings_urls == ["file:///tmp/google-open-buildings.csv"]
    assert source_asset_service.google_poi_authorization_path == auth_path
    assert source_asset_service.google_places_api_key == "secret-test-key"
    assert source_asset_service.google_places_cache_key == "places-fixture-v1"


def test_freeze_track_b_national_evidence_builds_repo_relative_freeze(tmp_path: Path) -> None:
    evidence_root = tmp_path / "runs" / "2026-05-18-track-b-national-evidence"

    for theme, claim_state in (
        ("road", "national_scale_partial_reference"),
        ("water", "national_scale_supported"),
        ("poi", "national_scale_supported"),
    ):
        theme_dir = evidence_root / theme
        artifact_path = theme_dir / f"{theme}_artifact.gpkg"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("placeholder", encoding="utf-8")
        _write_json(
            theme_dir / "tile_manifest.json",
            {
                "manifest_mode": "national_bbox_tiling",
                "tile_count": 3,
                "tile_width_m": 20_000.0 if theme == "road" else 50_000.0,
                "tile_height_m": 20_000.0 if theme == "road" else 50_000.0,
                "overlap_m": 0.0,
                "bbox_crs": "EPSG:4326",
                "working_crs": "EPSG:32735",
            },
        )
        (theme_dir / "timing.json").write_text("{}", encoding="utf-8")
        (theme_dir / "source_profile_snapshot.json").write_text("{}", encoding="utf-8")
        _write_json(
            theme_dir / "selected_sources.json",
            {
                "job_type": theme,
                "selected_source_id": f"catalog.{theme}",
                "component_source_ids": ["raw.osm", "raw.ref"],
                "component_coverage": {
                    "raw.osm": {
                        "source_id": "raw.osm",
                        "path": str(theme_dir / "input_bundle" / "osm.zip"),
                    },
                    "raw.ref": {
                        "source_id": "raw.ref",
                        "path": str(theme_dir / "input_bundle" / "ref.zip"),
                    },
                },
            },
        )
        _write_json(
            theme_dir / "inspection_summary.json",
            {
                "claim_state": claim_state,
                "artifact_path": str(artifact_path),
                "tile_count": 3,
                "artifact_metrics": {"artifact_validity": True, "feature_count": 5},
            },
        )
        _write_json(
            theme_dir / "stitched_artifact.json",
            {"artifact_path": str(artifact_path), "tile_count": 3},
        )
        _write_json(
            theme_dir / "normalization_summary.json",
            {
                "selected_sources": {
                    "raw.osm": {
                        "source_id": "raw.osm",
                        "artifact_path": str(theme_dir / "normalized" / "raw_osm.gpkg"),
                        "feature_count": 5,
                        "columns": ["geometry"],
                    }
                },
                "supplemental_sources": {
                    "raw.ref": {
                        "source_id": "raw.ref",
                        "artifact_path": str(theme_dir / "normalized" / "supplemental" / "raw_ref.gpkg"),
                        "feature_count": 0,
                        "columns": [],
                    }
                },
            },
        )

    output_json = tmp_path / "freeze.json"
    payload = freeze_track_b_national_evidence(
        evidence_root=evidence_root,
        output_json=output_json,
        captured_at="2026-05-20",
        request_bbox=(28.0, -4.0, 30.0, -2.0),
        target_crs="EPSG:32735",
        repo_root=tmp_path,
    )

    assert output_json.exists()
    assert payload["captured_at"] == "2026-05-20"
    assert payload["evidence_root"].startswith("runs/")
    assert payload["tile_config_scope"] == "per_theme"
    assert payload["theme_tile_metadata"]["road"]["tile_width_m"] == 20_000.0
    assert payload["theme_tile_metadata"]["water"]["tile_width_m"] == 50_000.0
    assert [item["theme"] for item in payload["runs"]] == ["road", "water", "poi"]
    assert payload["runs"][0]["tile_width_m"] == 20_000.0
    assert payload["runs"][0]["manifest_mode"] == "national_bbox_tiling"
    assert payload["runs"][0]["artifact_path"].startswith("runs/")
    assert payload["runs"][0]["selected_normalized_sources"]["raw.osm"]["artifact_path"].startswith("runs/")


def test_freeze_track_b_smoke_evidence_rebuilds_repo_local_bundles(tmp_path: Path) -> None:
    evidence_root = tmp_path / "runs" / "2026-05-18-smoke-evidence"
    inspections_dir = tmp_path / "inspections"

    def _inspection(job_type: str, run_id: str, source_id: str, component_ids: list[str]) -> dict:
        return {
            "run": {
                "run_id": run_id,
                "job_type": job_type,
                "phase": "succeeded",
                "target_crs": "EPSG:32735",
                "artifact": {"path": f"runs/{run_id}/output/{job_type}_fusion_result.zip"},
            },
            "artifact": {"path": f"runs/{run_id}/output/{job_type}_fusion_result.zip"},
            "kg_path_trace": {"selected_pattern_id": f"wp.{job_type}.default", "workflow_id": f"wf-{job_type}"},
            "plan": {
                "context": {
                    "retrieval": {
                        "data_sources": [
                            {
                                "source_id": source_id,
                                "metadata": {"component_source_ids": component_ids},
                            }
                        ]
                    }
                }
            },
            "audit_events": [
                {
                    "kind": "task_inputs_resolved",
                    "details": {
                        "requested_source_id": source_id,
                        "selected_source_id": source_id,
                        "source_mode": "cache_reused",
                        "cache_hit": True,
                        "component_coverage": {component_id: "available" for component_id in component_ids},
                        "resolved_aoi": {
                            "display_name": "Example AOI",
                            "bbox": [28.0, -4.0, 30.0, -2.0],
                        },
                    },
                },
                {
                    "kind": "output_schema_validated",
                    "details": {"artifact_validity": True, "feature_count": 3},
                },
            ],
        }

    snapshots = []
    for theme, dir_name, source_id, component_ids in (
        ("building", "building", "catalog.earthquake.building", ["raw.osm.building", "raw.microsoft.building"]),
        ("poi", "poi", "catalog.generic.poi", ["raw.osm.poi", "raw.gns.poi"]),
    ):
        inspection_path = inspections_dir / f"{theme}.json"
        _write_json(inspection_path, _inspection(theme, f"run-{theme}", source_id, component_ids))
        snapshots.append(SmokeSnapshot(theme, inspection_path, dir_name))

    output_json = tmp_path / "smoke-freeze.json"
    payload = freeze_track_b_smoke_evidence(
        evidence_root=evidence_root,
        output_json=output_json,
        captured_at="2026-05-20",
        snapshots=tuple(snapshots),
        repo_root=tmp_path,
    )

    assert output_json.exists()
    assert payload["evidence_root"].startswith("runs/")
    assert [item["theme"] for item in payload["runs"]] == ["building", "poi"]
    assert (evidence_root / "building" / "inspection_summary.json").exists()
    assert (evidence_root / "poi" / "selected_sources.json").exists()
