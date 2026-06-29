from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.geometry import LineString, Point, box

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fusion_algorithms.contracts import PoiFusionParams, WaterPolygonFusionParams
from fusion_algorithms.poi_fusion import run_poi_geohash_priority_fusion
from fusion_algorithms.road_conflation_v7 import RoadConflationV7Config, run_road_conflation_v7
from fusion_algorithms.water_fusion import fuse_water_polygons
from fusion_algorithms.waterways_conflation_v7 import WaterwaysConflationV7Config, run_waterways_conflation_v7


def materialize_controlled_quality_artifacts(*, output_dir: Path, manifest_path: Path) -> dict[str, Any]:
    output_dir = Path(output_dir)
    artifact_dir = output_dir / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    lineage: list[dict[str, Any]] = []
    cases = [
        _road_case(artifact_dir, lineage),
        _water_polygon_case(artifact_dir, lineage),
        _waterways_case(artifact_dir, lineage),
        _poi_case(artifact_dir, lineage),
    ]
    payload = {
        "manifest_id": "freeze-b-controlled-supplement-v1",
        "freeze_line": "Freeze B",
        "notes": [
            "Controlled semi-real supplement for Freeze B quality execution.",
            "Does not replace case.building.real.benin from freeze-b-v1.",
            "Artifacts are generated from checked-in deterministic fixtures in scripts/materialize_controlled_quality_artifacts.py.",
        ],
        "cases": cases,
    }
    manifest_path = Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lineage_path = output_dir / "artifact_lineage.json"
    lineage_path.write_text(json.dumps({"artifacts": lineage}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"manifest": payload, "lineage_path": str(lineage_path), "artifact_count": len(lineage)}


def _write_gpkg(frame: gpd.GeoDataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(path, driver="GPKG")
    return path


def _road_case(artifact_dir: Path, lineage: list[dict[str, Any]]) -> dict[str, Any]:
    base = gpd.GeoDataFrame(
        {
            "osm_id": [1],
            "road_class": ["primary"],
            "source_id": ["fixture.road.base"],
        },
        geometry=[LineString([(0, 0), (10, 0)])],
        crs="EPSG:3857",
    )
    supplement = gpd.GeoDataFrame(
        {
            "id": [2],
            "road_class": ["secondary"],
            "source_id": ["fixture.road.supplement"],
        },
        geometry=[LineString([(0, 30), (10, 30)])],
        crs="EPSG:3857",
    )
    result = run_road_conflation_v7(
        base,
        supplement,
        config=RoadConflationV7Config(
            target_crs="EPSG:3857",
            do_split_by_angle=False,
            max_segment_length=None,
            enable_dangle_cleanup=False,
        ),
    )
    frame = result.frame.copy()
    frame["source_id"] = frame["source_layer"].map(
        {"base": "fixture.road.base", "supplement": "fixture.road.supplement"}
    ).fillna("fixture.road.unknown")
    artifact = _write_gpkg(frame, artifact_dir / "road_controlled.gpkg")
    lineage.append(
        {
            "case_id": "case.road.semi_real.perturbed",
            "artifact_path": str(artifact).replace("\\", "/"),
            "algorithm": "run_road_conflation_v7",
            "stats": result.stats,
        }
    )
    return {
        "case_id": "case.road.semi_real.perturbed",
        "task_kind": "road",
        "data_tier": "semi_real",
        "independence_label": "perturbation_independent",
        "claim_use": "robustness_claim",
        "aoi": {"name": "road-controlled-perturbation", "bbox": [0, 0, 1, 1]},
        "sources": [{"source_id": "fixture.road.base", "version_token": "controlled-v1"}],
        "baselines": [{"baseline_id": "fixed_adapter", "runner": "adapter_direct"}],
        "metrics": [
            {"metric_name": "invalid_geometry_rate", "operator": "eq", "threshold": 0.0},
            {"metric_name": "zero_length_geometry_count", "operator": "eq", "threshold": 0},
        ],
        "expected_artifact_roles": ["fused_vector"],
        "precomputed_artifact_path": str(artifact).replace("\\", "/"),
    }


def _water_polygon_case(artifact_dir: Path, lineage: list[dict[str, Any]]) -> dict[str, Any]:
    base = gpd.GeoDataFrame(
        {"id": [1], "source_id": ["fixture.water.polygon.base"]},
        geometry=[box(0, 0, 100, 100)],
        crs="EPSG:3857",
    )
    target = gpd.GeoDataFrame(
        {"id": [2], "source_id": ["fixture.water.polygon.reference"]},
        geometry=[box(200, 200, 260, 260)],
        crs="EPSG:3857",
    )
    frame = fuse_water_polygons(
        base,
        target,
        WaterPolygonFusionParams(overlap_threshold=0.2, preserve_unmatched_osm=True, preserve_unmatched_new=True),
    )
    artifact = _write_gpkg(frame, artifact_dir / "water_polygon_controlled.gpkg")
    lineage.append(
        {
            "case_id": "case.water_polygon.semi_real.priority_merge",
            "artifact_path": str(artifact).replace("\\", "/"),
            "algorithm": "fuse_water_polygons",
            "feature_count": len(frame),
        }
    )
    return {
        "case_id": "case.water_polygon.semi_real.priority_merge",
        "task_kind": "water_polygon",
        "data_tier": "semi_real",
        "independence_label": "perturbation_independent",
        "claim_use": "robustness_claim",
        "aoi": {"name": "water-polygon-controlled", "bbox": [0, 0, 1, 1]},
        "sources": [{"source_id": "fixture.water.polygon", "version_token": "controlled-v1"}],
        "baselines": [{"baseline_id": "fixed_adapter", "runner": "adapter_direct"}],
        "metrics": [
            {"metric_name": "invalid_geometry_rate", "operator": "eq", "threshold": 0.0},
            {"metric_name": "sliver_polygon_count", "operator": "lte", "threshold": 1},
        ],
        "expected_artifact_roles": ["fused_vector"],
        "precomputed_artifact_path": str(artifact).replace("\\", "/"),
    }


def _waterways_case(artifact_dir: Path, lineage: list[dict[str, Any]]) -> dict[str, Any]:
    base = gpd.GeoDataFrame(
        {
            "osm_id": [1],
            "fclass": ["river"],
            "name": ["Base River"],
            "source_id": ["fixture.waterways.base"],
        },
        geometry=[LineString([(0, 0), (10, 0)])],
        crs="EPSG:3857",
    )
    supplement = gpd.GeoDataFrame(
        {
            "osm_id": [101],
            "waterway": ["stream"],
            "name": ["Supplement Stream"],
            "source": ["controlled"],
            "source_id": ["fixture.waterways.supplement"],
        },
        geometry=[LineString([(0, 40), (10, 40)])],
        crs="EPSG:3857",
    )
    result = run_waterways_conflation_v7(
        base,
        supplement,
        config=WaterwaysConflationV7Config(
            target_crs="EPSG:3857",
            do_split_by_angle=False,
            max_segment_length=None,
            enable_dangle_cleanup=False,
        ),
    )
    frame = result.frame.copy()
    frame["source_id"] = frame["source_layer"].map(
        {"base": "fixture.waterways.base", "supplement": "fixture.waterways.supplement"}
    ).fillna("fixture.waterways.unknown")
    artifact = _write_gpkg(frame, artifact_dir / "waterways_controlled.gpkg")
    lineage.append(
        {
            "case_id": "case.waterways.semi_real.line_conflation",
            "artifact_path": str(artifact).replace("\\", "/"),
            "algorithm": "run_waterways_conflation_v7",
            "stats": result.stats,
        }
    )
    return {
        "case_id": "case.waterways.semi_real.line_conflation",
        "task_kind": "waterways",
        "data_tier": "semi_real",
        "independence_label": "perturbation_independent",
        "claim_use": "robustness_claim",
        "aoi": {"name": "waterways-controlled", "bbox": [0, 0, 1, 1]},
        "sources": [{"source_id": "fixture.waterways", "version_token": "controlled-v1"}],
        "baselines": [{"baseline_id": "fixed_adapter", "runner": "adapter_direct"}],
        "metrics": [
            {"metric_name": "invalid_geometry_rate", "operator": "eq", "threshold": 0.0},
            {"metric_name": "zero_length_geometry_count", "operator": "eq", "threshold": 0},
        ],
        "expected_artifact_roles": ["fused_vector"],
        "precomputed_artifact_path": str(artifact).replace("\\", "/"),
    }


def _poi_case(artifact_dir: Path, lineage: list[dict[str, Any]]) -> dict[str, Any]:
    gns = gpd.GeoDataFrame(
        {"name": ["Clinic"], "category": ["health"], "source_id": ["fixture.poi.gns"]},
        geometry=[Point(0, 0)],
        crs="EPSG:3857",
    )
    google = gpd.GeoDataFrame(
        {"name": ["School"], "category": ["education"], "source_id": ["fixture.poi.google"]},
        geometry=[Point(100, 100)],
        crs="EPSG:3857",
    )
    osm = gpd.GeoDataFrame(
        {"name": ["Clinic"], "category": ["health"], "source_id": ["fixture.poi.osm"]},
        geometry=[Point(1, 0)],
        crs="EPSG:3857",
    )
    frame = run_poi_geohash_priority_fusion(
        {"GNG": gns, "GOOGLE": google, "OSM": osm},
        PoiFusionParams(duplicate_distance_m=5.0, source_priority_order=("GNG", "GOOGLE", "OSM")),
    )
    artifact = _write_gpkg(frame, artifact_dir / "poi_controlled.gpkg")
    lineage.append(
        {
            "case_id": "case.poi.semi_real.neighbor_match",
            "artifact_path": str(artifact).replace("\\", "/"),
            "algorithm": "run_poi_geohash_priority_fusion",
            "feature_count": len(frame),
        }
    )
    return {
        "case_id": "case.poi.semi_real.neighbor_match",
        "task_kind": "poi",
        "data_tier": "semi_real",
        "independence_label": "perturbation_independent",
        "claim_use": "robustness_claim",
        "aoi": {"name": "poi-controlled", "bbox": [0, 0, 1, 1]},
        "sources": [{"source_id": "fixture.poi", "version_token": "controlled-v1"}],
        "baselines": [{"baseline_id": "fixed_adapter", "runner": "adapter_direct"}],
        "metrics": [
            {"metric_name": "invalid_geometry_rate", "operator": "eq", "threshold": 0.0},
            {"metric_name": "duplicate_geometry_rate", "operator": "lte", "threshold": 0.25},
        ],
        "expected_artifact_roles": ["fused_vector"],
        "precomputed_artifact_path": str(artifact).replace("\\", "/"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize controlled quality benchmark artifacts.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    result = materialize_controlled_quality_artifacts(
        output_dir=Path(args.output_dir),
        manifest_path=Path(args.manifest),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
