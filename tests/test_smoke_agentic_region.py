from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import smoke_agentic_region
from scripts.smoke_agentic_region import build_create_run_form, parse_args, run_smoke


def test_smoke_agentic_region_parses_nairobi_request() -> None:
    parsed = parse_args(
        [
            "--base-url",
            "http://127.0.0.1:8010",
            "--query",
            "fuse building and road data for Nairobi, Kenya",
            "--job-type",
            "building",
        ]
    )

    assert parsed.base_url == "http://127.0.0.1:8010"
    assert parsed.query == "fuse building and road data for Nairobi, Kenya"
    assert parsed.job_type == "building"


def test_smoke_agentic_region_cli_help_runs_as_script() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "smoke_agentic_region.py"

    completed = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--evidence-dir" in completed.stdout


def test_smoke_agentic_region_builds_task_driven_form_payload() -> None:
    parsed = parse_args(
        [
            "--base-url",
            "http://127.0.0.1:8010",
            "--query",
            "fuse building and road data for Nairobi, Kenya",
            "--job-type",
            "road",
            "--target-crs",
            "EPSG:4326",
        ]
    )

    payload = build_create_run_form(parsed)

    assert payload["job_type"] == "road"
    assert payload["trigger_type"] == "user_query"
    assert payload["trigger_content"] == "fuse building and road data for Nairobi, Kenya"
    assert payload["input_strategy"] == "task_driven_auto"
    assert payload["target_crs"] == "EPSG:4326"


def test_smoke_agentic_region_omits_target_crs_when_not_provided() -> None:
    parsed = parse_args(
        [
            "--base-url",
            "http://127.0.0.1:8010",
            "--query",
            "fuse building and road data for Nairobi, Kenya",
            "--job-type",
            "building",
        ]
    )

    payload = build_create_run_form(parsed)

    assert payload["job_type"] == "building"
    assert payload["trigger_type"] == "user_query"
    assert payload["trigger_content"] == "fuse building and road data for Nairobi, Kenya"
    assert payload["input_strategy"] == "task_driven_auto"
    assert "target_crs" not in payload


def test_smoke_agentic_region_accepts_water_and_poi_job_types() -> None:
    water = parse_args(
        [
            "--base-url",
            "http://127.0.0.1:8010",
            "--query",
            "need water polygons for Nairobi, Kenya",
            "--job-type",
            "water",
        ]
    )
    poi = parse_args(
        [
            "--base-url",
            "http://127.0.0.1:8010",
            "--query",
            "show hospitals in Nairobi, Kenya",
            "--job-type",
            "poi",
        ]
    )

    assert build_create_run_form(water)["job_type"] == "water"
    assert build_create_run_form(poi)["job_type"] == "poi"


def test_smoke_agentic_region_accepts_evidence_dir_argument(tmp_path: Path) -> None:
    parsed = parse_args(
        [
            "--base-url",
            "http://127.0.0.1:8010",
            "--query",
            "need water polygons for Nairobi, Kenya",
            "--job-type",
            "water",
            "--evidence-dir",
            str(tmp_path),
        ]
    )

    assert parsed.evidence_dir == str(tmp_path)


def test_smoke_summary_accepts_large_area_evidence_fields() -> None:
    summary = {
        "job_type": "road",
        "phase": "succeeded",
        "large_area_runtime": {"tile_count": 2, "stitched_feature_count": 5},
        "source_semantic_contract": {"component_source_ids": ["raw.osm.road", "raw.microsoft.road"]},
        "documents": {"summary": "run_report_summary.json"},
    }

    assert summary["large_area_runtime"]["tile_count"] >= 1
    assert summary["source_semantic_contract"]["component_source_ids"]
    assert summary["documents"]["summary"].endswith(".json")


def test_smoke_inspection_summary_carries_large_area_evidence_fields() -> None:
    inspection = _sample_smoke_inspection(
        job_type="road",
        source_id="catalog.flood.road",
        pattern_id="wp.road.fusioncode.segment_topology.v1",
        component_source_ids=["raw.osm.road", "raw.microsoft.road"],
    )
    inspection["large_area_runtime"] = {"tile_count": 2, "stitched_feature_count": 5}
    inspection["source_semantic_contract"] = {
        "component_source_ids": ["raw.osm.road", "raw.microsoft.road"]
    }
    inspection["documents"] = {"summary": "documents/run_report_summary.json"}

    summary = smoke_agentic_region._build_inspection_summary(inspection)

    assert summary["large_area_runtime"]["tile_count"] == 2
    assert summary["source_semantic_contract"]["component_source_ids"] == [
        "raw.osm.road",
        "raw.microsoft.road",
    ]
    assert summary["documents"]["summary"].endswith("run_report_summary.json")


def test_smoke_agentic_region_includes_preferred_pattern_id_when_provided() -> None:
    parsed = parse_args(
        [
            "--base-url",
            "http://127.0.0.1:8010",
            "--query",
            "need road data for Gilgit city, Pakistan",
            "--job-type",
            "road",
            "--preferred-pattern-id",
            "wp.road.fusioncode.segment_topology.v1",
        ]
    )

    payload = build_create_run_form(parsed)

    assert payload["preferred_pattern_id"] == "wp.road.fusioncode.segment_topology.v1"


def test_smoke_agentic_region_requires_explicit_job_type() -> None:
    with pytest.raises(SystemExit):
        parse_args(
            [
                "--base-url",
                "http://127.0.0.1:8010",
                "--query",
                "need road data for Gilgit, Pakistan",
            ]
        )


def test_smoke_agentic_region_uses_total_timeout_for_create_request(monkeypatch: pytest.MonkeyPatch) -> None:
    timeouts: list[float] = []

    def fake_json_request(method: str, url: str, *, form_data=None, timeout_sec: float = 30.0):
        timeouts.append(timeout_sec)
        if method == "POST":
            return {"run_id": "run-1"}
        if url.endswith("/api/v2/runs/run-1"):
            return {"phase": "succeeded"}
        if url.endswith("/api/v2/runs/run-1/inspection"):
            return {"audit_events": [], "artifact": {}}
        raise AssertionError(url)

    monkeypatch.setattr("scripts.smoke_agentic_region._json_request", fake_json_request)

    result = run_smoke(
        base_url="http://127.0.0.1:8011",
        query="need road data for Gilgit city, Pakistan",
        job_type="road",
        target_crs="",
        preferred_pattern_id="",
        timeout_sec=1200.0,
        poll_interval_sec=0.2,
    )

    assert result["run_id"] == "run-1"
    assert timeouts[0] == 1200.0


def _sample_smoke_inspection(
    *,
    job_type: str = "water",
    source_id: str = "catalog.flood.water",
    pattern_id: str = "wp.flood.water.default",
    component_source_ids: list[str] | None = None,
) -> dict[str, object]:
    if component_source_ids is None:
        component_source_ids = ["raw.osm.water", "raw.local.water"]
    source_name = {
        "water": "Flood Water Bundle (OSM + Local Water)",
        "road": "Typhoon Road Bundle (OSM + Microsoft)",
        "poi": "Generic POI Bundle (OSM + GNS)",
        "building": "Building Bundle",
    }[job_type]
    output_type = {
        "water": "dt.water.fused",
        "road": "dt.road.fused",
        "poi": "dt.poi.fused",
        "building": "dt.building.fused",
    }[job_type]
    policy_id = {
        "water": "osp.water.fused.v1",
        "road": "osp.road.fused.v1",
        "poi": "osp.poi.fused.v1",
        "building": "osp.building.fused.v1",
    }[job_type]
    return {
        "run": {
            "run_id": "run-1",
            "job_type": job_type,
            "phase": "succeeded",
            "target_crs": "EPSG:32737",
            "trigger": {
                "type": "user_query",
                "content": "need water polygons for Nairobi, Kenya",
            },
            "artifact": {
                "filename": f"{job_type}_fusion_result.zip",
                "path": f"runs\\run-1\\output\\{job_type}_fusion_result.zip",
                "size_bytes": 123,
            },
        },
        "plan": {
            "workflow_id": f"wf_{pattern_id}_1234",
            "context": {
                "intent": {
                    "job_type": job_type,
                    "resolved_aoi": {
                        "query": "Nairobi, Kenya",
                        "display_name": "Nairobi, Kenya",
                        "country_name": "Kenya",
                        "country_code": "ke",
                        "bbox": [36.6647016, -1.4448822, 37.1048735, -1.1606749],
                    },
                },
                "retrieval": {
                    "data_sources": [
                        {
                            "source_id": source_id,
                            "source_name": source_name,
                            "supported_types": [f"dt.{job_type}.bundle"],
                            "metadata": {
                                "component_source_ids": component_source_ids,
                                "bundle_strategy": "osm_ref_pair",
                            },
                        },
                        {
                            "source_id": component_source_ids[0],
                            "source_name": "OSM fallback source",
                            "supported_types": ["dt.raw.vector"],
                            "metadata": {
                                "source_form": "vector",
                            },
                        },
                    ]
                },
            },
        },
        "audit_events": [
            {
                "kind": "aoi_resolved",
                "details": {
                    "display_name": "Nairobi, Kenya",
                    "country_code": "ke",
                    "country_name": "Kenya",
                    "bbox": [36.6647016, -1.4448822, 37.1048735, -1.1606749],
                },
            },
            {
                "kind": "task_inputs_resolved",
                "details": {
                    "input_strategy": "task_driven_auto",
                    "source_mode": "cache_reused",
                    "source_id": source_id,
                    "requested_source_id": source_id,
                    "selected_source_id": source_id,
                    "fallback_from_source_id": None,
                    "component_coverage": {
                        component_source_ids[0]: "full",
                        component_source_ids[-1]: "partial",
                    },
                    "cache_hit": True,
                    "target_crs": "EPSG:32737",
                    "resolved_aoi": {
                        "display_name": "Nairobi, Kenya",
                        "country_code": "ke",
                        "country_name": "Kenya",
                        "bbox": [36.6647016, -1.4448822, 37.1048735, -1.1606749],
                    },
                },
            },
            {
                "kind": "output_schema_validated",
                "details": {
                    "output_data_type": output_type,
                    "policy_id": policy_id,
                    "required_fields": ["geometry"],
                    "missing_fields": [],
                    "artifact_validity": True,
                },
            },
        ],
        "artifact": {
            "available": True,
            "filename": f"{job_type}_fusion_result.zip",
            "path": f"runs\\run-1\\output\\{job_type}_fusion_result.zip",
            "size_bytes": 123,
            "download_path": "/api/v2/runs/run-1/artifact",
        },
        "kg_path_trace": {
            "workflow_id": f"wf_{pattern_id}_1234",
            "selected_pattern_id": pattern_id,
        },
    }


def test_smoke_agentic_region_main_writes_track_b_evidence_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspection = _sample_smoke_inspection()

    def fake_run_smoke(**kwargs):
        del kwargs
        return {
            "run_id": "run-1",
            "status": {"phase": "succeeded"},
            "inspection": inspection,
        }

    monkeypatch.setattr(smoke_agentic_region, "run_smoke", fake_run_smoke)

    exit_code = smoke_agentic_region.main(
        [
            "--base-url",
            "http://127.0.0.1:8010",
            "--query",
            "need water polygons for Nairobi, Kenya",
            "--job-type",
            "water",
            "--evidence-dir",
            str(tmp_path),
        ]
    )

    selected_sources = json.loads((tmp_path / "selected_sources.json").read_text(encoding="utf-8"))
    source_profile_snapshot = json.loads(
        (tmp_path / "source_profile_snapshot.json").read_text(encoding="utf-8")
    )
    tile_manifest = json.loads((tmp_path / "tile_manifest.json").read_text(encoding="utf-8"))
    inspection_summary = json.loads(
        (tmp_path / "inspection_summary.json").read_text(encoding="utf-8")
    )
    saved_inspection = json.loads((tmp_path / "inspection.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert saved_inspection["run"]["run_id"] == "run-1"
    assert selected_sources["requested_source_id"] == "catalog.flood.water"
    assert selected_sources["selected_source_id"] == "catalog.flood.water"
    assert selected_sources["source_mode"] == "cache_reused"
    assert selected_sources["cache_hit"] is True
    assert selected_sources["component_source_ids"] == ["raw.osm.water", "raw.local.water"]
    assert selected_sources["component_coverage"] == {
        "raw.osm.water": "full",
        "raw.local.water": "partial",
    }
    assert source_profile_snapshot["selected_source_id"] == "catalog.flood.water"
    assert source_profile_snapshot["selected_profile"]["metadata"]["component_source_ids"] == [
        "raw.osm.water",
        "raw.local.water",
    ]
    assert [item["source_id"] for item in source_profile_snapshot["profiles"]] == [
        "catalog.flood.water",
        "raw.osm.water",
    ]
    assert tile_manifest["manifest_mode"] == "single_request_aoi"
    assert tile_manifest["tile_count"] == 1
    assert tile_manifest["bbox"] == [36.6647016, -1.4448822, 37.1048735, -1.1606749]
    assert tile_manifest["tiles"][0]["tile_id"] == "tile_000_000"
    assert inspection_summary["mode"] == "task_driven_smoke_inspection"
    assert inspection_summary["claim_state"] == "runtime_supported"
    assert inspection_summary["job_type"] == "water"
    assert inspection_summary["selected_pattern_id"] == "wp.flood.water.default"
    assert inspection_summary["evidence"]["inspection"] == "inspection.json"
    assert inspection_summary["evidence"]["selected_sources"] == "selected_sources.json"
    assert inspection_summary["operator_readable_summary"]["selected_source_id"] == "catalog.flood.water"
    assert inspection_summary["operator_readable_summary"]["artifact_validity"] is True


def test_smoke_agentic_region_marks_poi_smoke_as_bounded_supported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspection = _sample_smoke_inspection(
        job_type="poi",
        source_id="catalog.generic.poi",
        pattern_id="wp.generic.poi.default",
        component_source_ids=["raw.osm.poi", "raw.gns.poi"],
    )

    def fake_run_smoke(**kwargs):
        del kwargs
        return {
            "run_id": "run-1",
            "status": {"phase": "succeeded"},
            "inspection": inspection,
        }

    monkeypatch.setattr(smoke_agentic_region, "run_smoke", fake_run_smoke)

    smoke_agentic_region.main(
        [
            "--base-url",
            "http://127.0.0.1:8010",
            "--query",
            "show hospitals in Nairobi, Kenya",
            "--job-type",
            "poi",
            "--evidence-dir",
            str(tmp_path),
        ]
    )

    inspection_summary = json.loads(
        (tmp_path / "inspection_summary.json").read_text(encoding="utf-8")
    )

    assert inspection_summary["job_type"] == "poi"
    assert inspection_summary["claim_state"] == "bounded_supported"
    assert inspection_summary["selected_pattern_id"] == "wp.generic.poi.default"
