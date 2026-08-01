from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
from pathlib import Path
from statistics import mean, stdev
from typing import Any

import geopandas as gpd
from shapely.geometry import box, mapping
from shapely.ops import unary_union

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_contract_case_experiments import run_manifest
from scripts.run_governance_ablation import _case_metrics
from services.contract_experiment_service import hash_input_declaration, load_experiment_manifest, sha256_file


EVIDENCE_ROOT = Path(r"D:\code\freeze-c-evidence\p4-external-validity-20260801-v2")
DOC_ROOT = REPO_ROOT / "docs" / "current" / "evidence" / "p4-external-validity"
MANIFEST_ROOT = DOC_ROOT / "manifests"
BASE_MANIFEST = REPO_ROOT / "docs" / "thesis" / "manifests" / "2026-07-20-c02-c04-c06-real-data.json"
METRIC_DEFINITION = REPO_ROOT / "docs" / "thesis" / "contract_case_metrics_v1.json"
SOURCE_ROOT = Path(r"D:\fyx\任务\fusionagent_downloads\raw_source_cache\source_assets")


AOI_SPECS: dict[str, dict[str, Any]] = {
    "caracas": {
        "label": "Caracas 首都区",
        "structure": "山地首都城区，原始 Freeze C 案例",
        "bbox": [-67.17, 10.38, -66.86, 10.57],
        "target_crs": "EPSG:32619",
        "source_mode": "freeze_c_manifest",
        "manifest": BASE_MANIFEST,
        "c06_road_reference_available": True,
    },
    "abidjan": {
        "label": "Abidjan 都市走廊",
        "structure": "高密度沿海都市，水系与建筑密度较高",
        "bbox": [-4.17, 5.23, -3.86, 5.48],
        "target_crs": "EPSG:32630",
        "source_mode": "cached_external",
        "paths": {
            "raw.osm.road": SOURCE_ROOT / "geofabrik_clips/ivory-coast/raw_osm_road/515115cfa3e8/gis_osm_roads_free_1.shp",
            "raw.osm.building": SOURCE_ROOT / "geofabrik_clips/ivory-coast/raw_osm_building/515115cfa3e8/gis_osm_buildings_a_free_1.shp",
            "raw.osm.water": SOURCE_ROOT / "geofabrik_clips/ivory-coast/raw_osm_water/515115cfa3e8/gis_osm_water_a_free_1.shp",
            "raw.osm.waterways": SOURCE_ROOT / "geofabrik_clips/ivory-coast/raw_osm_waterways/515115cfa3e8/gis_osm_waterways_free_1.shp",
            "raw.hydrorivers.water": SOURCE_ROOT / "hydrosheds_clips/raw_hydrorivers_water/515115cfa3e8/HydroRIVERS_v10.shp",
            "raw.hydrolakes.water": SOURCE_ROOT / "hydrosheds_clips/raw_hydrolakes_water/515115cfa3e8/HydroLAKES_polys_v10.shp",
        },
        "c06_road_reference_available": False,
    },
    "vietnam_coastal": {
        "label": "越南北部沿海走廊",
        "structure": "较大沿海走廊，水系密度和覆盖尺度不同",
        "bbox": [106.60, 20.78, 106.78, 20.92],
        "target_crs": "EPSG:32648",
        "source_mode": "cached_external",
        "paths": {
            "raw.osm.road": SOURCE_ROOT / "geofabrik_clips/vietnam/raw_osm_road/767db3e08935/gis_osm_roads_free_1.shp",
            "raw.osm.building": SOURCE_ROOT / "geofabrik_clips/vietnam/raw_osm_building/767db3e08935/gis_osm_buildings_a_free_1.shp",
            "raw.osm.water": SOURCE_ROOT / "geofabrik_clips/vietnam/raw_osm_water/767db3e08935/gis_osm_water_a_free_1.shp",
            "raw.osm.waterways": SOURCE_ROOT / "geofabrik_clips/vietnam/raw_osm_waterways/767db3e08935/gis_osm_waterways_free_1.shp",
            "raw.hydrorivers.water": SOURCE_ROOT / "hydrosheds_clips/raw_hydrorivers_water/767db3e08935/HydroRIVERS_v10.shp",
            "raw.hydrolakes.water": SOURCE_ROOT / "hydrosheds_clips/raw_hydrolakes_water/767db3e08935/HydroLAKES_polys_v10.shp",
        },
        "c06_road_reference_available": False,
    },
}


def _json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _bbox_text(bbox: list[float]) -> str:
    return "bbox(" + ",".join(str(value) for value in bbox) + ")"


def _boundary_path(aoi_id: str) -> Path:
    return MANIFEST_ROOT / f"{aoi_id}_aoi_boundary.geojson"


def _write_boundary(aoi_id: str, bbox_values: list[float]) -> Path:
    boundary = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"aoi_id": aoi_id, "boundary_type": "derived_request_bbox"},
                "geometry": mapping(box(*bbox_values)),
            }
        ],
    }
    path = _boundary_path(aoi_id)
    _json_write(path, boundary)
    return path


def _source_declaration(source_id: str, path: Path, *, product: str, bbox_values: list[float], version: str) -> dict[str, Any]:
    runtime_paths = {
        "raw.osm.road": "Data/roads/OSM/roads.shp",
        "raw.osm.building": "Data/buildings/OSM/buildings.shp",
        "raw.osm.water": "Data/burundi-260127-free.shp/gis_osm_water_a_free_1.shp",
        "raw.osm.waterways": "Data/burundi-260127-free.shp/gis_osm_waterways_free_1.shp",
        "raw.hydrorivers.water": "Data/water/HydroRIVERS_v10.shp",
        "raw.hydrolakes.water": "Data/water/HydroLAKES_polys_v10.shp",
    }
    return {
        "source_id": source_id,
        "product": product,
        "original_path": str(path),
        "runtime_relative_path": runtime_paths[source_id],
        "preparation": "vector_extract",
        "clip_bbox": bbox_values,
        "dataset_version": version,
        "observed_at": "2026-07-01T00:00:00+08:00",
        "freshness_status": "cached_external_snapshot",
        "semantic_status": product,
    }


def _build_external_manifest(aoi_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    bbox_values = spec["bbox"]
    boundary_path = _write_boundary(aoi_id, bbox_values)
    paths = spec["paths"]
    sources = [
        _source_declaration("raw.osm.road", paths["raw.osm.road"], product="road", bbox_values=bbox_values, version=f"{aoi_id}-osm-road-2026-07-01"),
        _source_declaration("raw.osm.building", paths["raw.osm.building"], product="building", bbox_values=bbox_values, version=f"{aoi_id}-osm-building-2026-07-01"),
        _source_declaration("raw.osm.water", paths["raw.osm.water"], product="water_polygon", bbox_values=bbox_values, version=f"{aoi_id}-osm-water-2026-07-01"),
        _source_declaration("raw.osm.waterways", paths["raw.osm.waterways"], product="waterways", bbox_values=bbox_values, version=f"{aoi_id}-osm-waterways-2026-07-01"),
        _source_declaration("raw.hydrorivers.water", paths["raw.hydrorivers.water"], product="waterways", bbox_values=bbox_values, version="HydroRIVERS-v10"),
        _source_declaration("raw.hydrolakes.water", paths["raw.hydrolakes.water"], product="water_polygon", bbox_values=bbox_values, version="HydroLAKES-v10"),
        {
            "source_id": f"aoi.{aoi_id}",
            "product": "aoi_boundary",
            "original_path": str(boundary_path),
            "runtime_relative_path": "Data/admin/OSM/venezuela_capital_district.geojson",
            "preparation": "copy",
            "dataset_version": f"{aoi_id}-derived-request-bbox-2026-08-01",
            "observed_at": "2026-08-01T00:00:00+08:00",
            "freshness_status": "derived_from_declared_request_bbox",
            "semantic_status": "aoi_boundary_envelope",
        },
    ]
    request_common = {
        "disaster_type": "flood",
        "job_types": [],
        "spatial_extent": _bbox_text(bbox_values),
        "force_aoi_resolution": False,
        "target_crs": spec["target_crs"],
        "debug": False,
    }
    c02 = {
        "case_id": "C02",
        "scenario_name": f"C02 {spec['label']} flood water and road priority",
        "description": "Cross-AOI repeat of water, waterways, and road priority with available OSM and HydroSheds sources.",
        "request": {
            **request_common,
            "scenario_name": f"C02 {spec['label']} flood water and road priority",
            "trigger_content": f"{spec['label']} flood response: execute water polygon, waterways, and road fusion in that order.",
            "metadata": {
                "requested_task_kinds": ["water_polygon", "waterways", "road"],
                "requested_layers_present": True,
                "provisional_task_kinds": ["water_polygon"],
            },
        },
        "resource_regime": {"network": "moderate", "time": "tight", "aoi_scale": aoi_id, "source_condition": "OSM and HydroSheds cached external snapshot"},
        "expected_layer_priority": ["water_polygon", "waterways", "road"],
        "expected_delivery_strategy": "Deliver water and road evidence first while retaining explicit source and quality observations.",
        "expected_gap_types": [],
        "stages": [
            {
                "stage_id": "priority_delivery",
                "action": "create",
                "active_source_ids": ["raw.osm.water", "raw.osm.waterways", "raw.hydrorivers.water", "raw.osm.road", f"aoi.{aoi_id}"],
                "expected_phases": ["partial", "partial_provisional", "succeeded"],
                "expected_task_order": ["water_polygon", "waterways", "road"],
                "assertions": {"water_priority": True},
            }
        ],
    }
    c04 = {
        "case_id": "C04",
        "scenario_name": f"C04 {spec['label']} progressive water coverage",
        "description": "Cross-AOI repeat of provisional OSM water delivery followed by HydroLAKES activation and supersession.",
        "request": {
            **request_common,
            "scenario_name": f"C04 {spec['label']} progressive water coverage",
            "trigger_content": f"{spec['label']} storm response: progressively deliver water polygon coverage and supersede provisional output after the reference source arrives.",
            "metadata": {
                "requested_task_kinds": ["water_polygon"],
                "requested_layers_present": True,
                "provisional_task_kinds": ["water_polygon"],
            },
        },
        "resource_regime": {"network": "staged", "time": "tight", "aoi_scale": aoi_id, "source_condition": "HydroLAKES activates after initial OSM delivery"},
        "expected_layer_priority": ["water_polygon"],
        "expected_delivery_strategy": "Persist an OSM provisional product, resume after HydroLAKES activation, and record supersession.",
        "expected_gap_types": ["source_unavailable"],
        "stages": [
            {
                "stage_id": "osm_provisional",
                "action": "create",
                "active_source_ids": ["raw.osm.water", f"aoi.{aoi_id}"],
                "expected_phases": ["partial_provisional"],
                "expected_task_order": ["water_polygon"],
                "assertions": {"provisional_required": True},
            },
            {
                "stage_id": "hydrolakes_resume",
                "action": "resume",
                "active_source_ids": ["raw.osm.water", "raw.hydrolakes.water", f"aoi.{aoi_id}"],
                "retry_failed": True,
                "expected_phases": ["succeeded", "partial"],
                "expected_task_order": ["water_polygon"],
                "assertions": {"supersede_required": True},
            },
        ],
    }
    return {
        "schema_version": "1.0.0",
        "experiment_id": f"p4-{aoi_id}-c02-c04-20260801",
        "title": f"P4 {spec['label']} external validity C02/C04 repeat",
        "data_boundary": {
            "real_external_data": True,
            "real_fusion_algorithms": True,
            "real_llm": False,
            "real_neo4j": False,
            "execution_note": "Cross-AOI P4 slice uses cached external vector snapshots, memory KG, mock LLM, eager execution, and one child worker.",
        },
        "runtime": {
            "kg_backend": "memory",
            "llm_provider": "mock",
            "celery_eager": True,
            "scenario_child_max_workers": 1,
            "local_only": True,
            "artifact_reuse_disabled": True,
            "target_crs": spec["target_crs"],
            "api_path": "/api/v2/scenario-runs",
        },
        "sources": sources,
        "cases": [c02, c04],
        "metric_definition_path": "docs/thesis/contract_case_metrics_v1.json",
    }


def _prepare_caracas_manifest() -> Path:
    payload = json.loads(BASE_MANIFEST.read_text(encoding="utf-8"))
    payload["experiment_id"] = "p4-caracas-c02-c04-c06-20260801"
    payload["title"] = "P4 Caracas external validity C02/C04/C06 repeat"
    path = MANIFEST_ROOT / "caracas_c02_c04_c06.json"
    _json_write(path, payload)
    return path


def prepare() -> dict[str, Any]:
    MANIFEST_ROOT.mkdir(parents=True, exist_ok=True)
    manifests: dict[str, str] = {"caracas": str(_prepare_caracas_manifest().resolve())}
    for aoi_id, spec in AOI_SPECS.items():
        if spec["source_mode"] == "cached_external":
            for source_id, path in spec["paths"].items():
                if not path.exists():
                    raise FileNotFoundError(f"{aoi_id} 缺少外部源 {source_id}: {path}")
            manifest_path = MANIFEST_ROOT / f"{aoi_id}_c02_c04.json"
            _json_write(manifest_path, _build_external_manifest(aoi_id, spec))
            manifests[aoi_id] = str(manifest_path.resolve())

    inventory: list[dict[str, Any]] = []
    for aoi_id, spec in AOI_SPECS.items():
        manifest_path = Path(manifests[aoi_id])
        manifest = load_experiment_manifest(manifest_path)
        inventory.append(
            {
                "aoi_id": aoi_id,
                "label": spec["label"],
                "structure": spec["structure"],
                "bbox": spec["bbox"],
                "manifest_path": str(manifest_path),
                "source_count": len(manifest.sources),
                "case_ids": [case.case_id for case in manifest.cases],
                "c06_road_reference_available": spec["c06_road_reference_available"],
                "input_hashes": [hash_input_declaration(source) for source in manifest.sources if source.enabled],
            }
        )
    payload = {
        "schema_version": "1.0.0",
        "p4_id": "freeze-c-external-validity-v1",
        "prepared_at": "2026-08-01",
        "manifests": manifests,
        "inventory": inventory,
        "limitations": [
            "Burundi 缓存目录存在与越南范围相同的空几何/错配快照，未纳入正式 AOI。",
            "非 Caracas AOI 当前没有独立 Microsoft 道路参考源，因此 C06 只做源可用性审计，不伪造质量门失败重复。",
        ],
    }
    path = DOC_ROOT / "2026-08-01-freeze-c-p4-aoi-input-inventory.json"
    _json_write(path, payload)
    return {"inventory_path": str(path.resolve()), "manifests": manifests}


def run_one(*, aoi_id: str, variant: str, server_port: int) -> dict[str, Any]:
    inventory_path = DOC_ROOT / "2026-08-01-freeze-c-p4-aoi-input-inventory.json"
    if not inventory_path.exists():
        prepare()
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    manifest_path = Path(inventory["manifests"][aoi_id])
    evidence_dir = EVIDENCE_ROOT / f"{aoi_id}_{variant}"
    os.environ["GEOFUSION_P3_VARIANT"] = variant
    os.environ["GEOFUSION_PLAN_GROUNDING_MODE"] = "report"
    result = run_manifest(
        manifest_path=manifest_path,
        experiment_dir=evidence_dir,
        api_base_url=f"http://127.0.0.1:{server_port}",
        start_server=True,
        server_port=server_port,
        poll_seconds=2.0,
        timeout_seconds=1800.0,
    )
    print(json.dumps({"aoi_id": aoi_id, "variant": variant, "result": result}, ensure_ascii=False, indent=2))
    return result


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _metric_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "std": None, "ci95": [None, None], "failure_rate": None}
    avg = mean(values)
    spread = stdev(values) if len(values) > 1 else 0.0
    t_critical = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776}.get(len(values), 1.96)
    margin = t_critical * spread / math.sqrt(len(values))
    return {
        "n": len(values),
        "mean": avg,
        "std": spread,
        "ci95": [max(0.0, avg - margin), min(1.0, avg + margin)],
        "failure_rate": 1.0 - avg,
    }


def _numeric_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "std": None, "ci95": [None, None], "min": None, "max": None}
    avg = mean(values)
    spread = stdev(values) if len(values) > 1 else 0.0
    t_critical = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776}.get(len(values), 1.96)
    margin = t_critical * spread / math.sqrt(len(values))
    return {
        "n": len(values),
        "mean": avg,
        "std": spread,
        "ci95": [avg - margin, avg + margin],
        "min": min(values),
        "max": max(values),
    }


def _cohen_h(left: list[float], right: list[float]) -> float | None:
    if not left or not right:
        return None
    p_left = mean(left)
    p_right = mean(right)
    return 2 * math.asin(math.sqrt(p_left)) - 2 * math.asin(math.sqrt(p_right))


def _reference_sample(*, aoi_id: str, spec: dict[str, Any], max_sample: int = 30) -> dict[str, Any]:
    if spec["source_mode"] == "freeze_c_manifest":
        manifest = load_experiment_manifest(BASE_MANIFEST)
        source_paths = {source.source_id: Path(source.original_path) for source in manifest.sources}
        osm_water = source_paths["raw.osm.water"]
        osm_waterways = source_paths["raw.osm.waterways"]
        hydro_lakes = source_paths["raw.hydrolakes.water"]
        hydro_rivers = source_paths["raw.hydrorivers.water"]
    else:
        paths = spec["paths"]
        osm_water = paths["raw.osm.water"]
        osm_waterways = paths["raw.osm.waterways"]
        hydro_lakes = paths["raw.hydrolakes.water"]
        hydro_rivers = paths["raw.hydrorivers.water"]
    bbox_values = spec["bbox"]
    bbox_geom = box(*bbox_values)

    def load(path: Path) -> gpd.GeoDataFrame:
        frame = gpd.read_file(path, bbox=tuple(bbox_values))
        if frame.crs is None:
            frame = frame.set_crs("EPSG:4326")
        return frame[frame.geometry.notna() & frame.geometry.intersects(bbox_geom)].copy()

    osm_polygon = load(osm_water)
    ref_polygon = load(hydro_lakes)
    osm_line = load(osm_waterways)
    ref_line = load(hydro_rivers)
    local_crs = ref_polygon.estimate_utm_crs() or ref_line.estimate_utm_crs() or "EPSG:3857"
    osm_polygon_local = osm_polygon.to_crs(local_crs)
    ref_polygon_local = ref_polygon.to_crs(local_crs)
    osm_line_local = osm_line.to_crs(local_crs)
    ref_line_local = ref_line.to_crs(local_crs)
    polygon_union = unary_union(list(osm_polygon_local.geometry)) if not osm_polygon_local.empty else None
    line_union = unary_union(list(osm_line_local.geometry)) if not osm_line_local.empty else None

    polygon_rows: list[dict[str, Any]] = []
    for index, geometry in ref_polygon_local.geometry.head(max_sample).items():
        point = geometry.representative_point()
        distance = float(point.distance(polygon_union)) if polygon_union is not None else None
        polygon_rows.append({"source_index": str(index), "distance_m": distance, "matched_within_100m": bool(distance is not None and distance <= 100.0)})
    line_rows: list[dict[str, Any]] = []
    for index, geometry in ref_line_local.geometry.head(max_sample).items():
        point = geometry.interpolate(0.5, normalized=True) if not geometry.is_empty else geometry
        distance = float(point.distance(line_union)) if line_union is not None else None
        line_rows.append({"source_index": str(index), "distance_m": distance, "matched_within_100m": bool(distance is not None and distance <= 100.0)})

    def layer_result(kind: str, osm: gpd.GeoDataFrame, reference: gpd.GeoDataFrame, rows: list[dict[str, Any]]) -> dict[str, Any]:
        reference_union = unary_union(list(reference.geometry)) if not reference.empty else None
        osm_union = unary_union(list(osm.geometry)) if not osm.empty else None
        overlap = None
        if reference_union is not None and osm_union is not None and kind == "polygon":
            denominator = float(reference_union.area)
            overlap = float(reference_union.intersection(osm_union).area / denominator) if denominator else None
        return {
            "osm_feature_count": int(len(osm)),
            "reference_feature_count": int(len(reference)),
            "sample_size": len(rows),
            "matched_count": sum(1 for row in rows if row["matched_within_100m"]),
            "match_rate": mean([1.0 if row["matched_within_100m"] else 0.0 for row in rows]) if rows else None,
            "reference_area_overlap_proxy": overlap,
            "sampling_rule": "first N features in deterministic source order; representative point/line midpoint within 100 m",
        }

    return {
        "aoi_id": aoi_id,
        "bbox": bbox_values,
        "reference_layers": {
            "water_polygon": layer_result("polygon", osm_polygon_local, ref_polygon_local, polygon_rows),
            "waterways": layer_result("line", osm_line_local, ref_line_local, line_rows),
        },
        "samples": {"water_polygon": polygon_rows, "waterways": line_rows},
        "source_paths": {
            "osm_water": str(osm_water),
            "osm_waterways": str(osm_waterways),
            "hydrolakes": str(hydro_lakes),
            "hydrorivers": str(hydro_rivers),
        },
    }


def summarize() -> dict[str, Any]:
    inventory = _load_json(DOC_ROOT / "2026-08-01-freeze-c-p4-aoi-input-inventory.json")
    if not inventory:
        prepare()
        inventory = _load_json(DOC_ROOT / "2026-08-01-freeze-c-p4-aoi-input-inventory.json")
    reference_results = [_reference_sample(aoi_id=aoi_id, spec=spec) for aoi_id, spec in AOI_SPECS.items()]
    reference_path = DOC_ROOT / "2026-08-01-freeze-c-p4-reference-sample-audit.json"
    _json_write(reference_path, {"schema_version": "1.0.0", "sampling": reference_results})

    rows: list[dict[str, Any]] = []
    for aoi_id in AOI_SPECS:
        manifest = load_experiment_manifest(Path(inventory["manifests"][aoi_id]))
        for variant in ("full_method", "fixed_priority"):
            evidence_dir = EVIDENCE_ROOT / f"{aoi_id}_{variant}"
            runtime_result = _load_json(evidence_dir / "experiment_result.json")
            for case in manifest.cases:
                metrics = _case_metrics(case=case, case_dir=evidence_dir / "cases" / case.case_id, experiment_dir=evidence_dir)
                case_result = _load_json(evidence_dir / "cases" / case.case_id / "case_result.json")
                rows.append(
                    {
                        "aoi_id": aoi_id,
                        "variant": variant,
                        "case_metrics": metrics,
                        "case_assertions_passed": case_result.get("passed"),
                        "experiment_all_cases_passed": runtime_result.get("all_cases_passed"),
                    }
                )

    def aggregate(variant: str, metric_name: str) -> dict[str, Any]:
        values = []
        for row in rows:
            if row["variant"] != variant:
                continue
            value = row["case_metrics"].get(metric_name)
            if isinstance(value, bool):
                values.append(1.0 if value else 0.0)
        return _metric_summary(values)

    metrics = [
        "planning_valid",
        "first_quality_gate_passed",
        "final_delivery_success",
        "recovery_success",
        "key_layer_delivered_on_time",
        "gap_declaration_correct",
        "evidence_complete",
    ]
    aggregates = {
        variant: {metric: aggregate(variant, metric) for metric in metrics}
        for variant in ("full_method", "fixed_priority")
    }
    recovery_cost_aggregates = {
        variant: _numeric_summary(
            [
                float(row["case_metrics"].get("recovery_cost_child_retries", 0))
                for row in rows
                if row["variant"] == variant and row["case_metrics"].get("recovery_case") is True
            ]
        )
        for variant in ("full_method", "fixed_priority")
    }
    effect_sizes = {
        metric: {
            "cohen_h_full_vs_fixed_priority": _cohen_h(
                [1.0 if row["case_metrics"].get(metric) else 0.0 for row in rows if row["variant"] == "full_method" and isinstance(row["case_metrics"].get(metric), bool)],
                [1.0 if row["case_metrics"].get(metric) else 0.0 for row in rows if row["variant"] == "fixed_priority" and isinstance(row["case_metrics"].get(metric), bool)],
            ),
            "interpretation": "探索性比例效果量；P4 样本量小，不作为显著性结论。",
        }
        for metric in metrics
    }
    case_coverage = []
    for aoi_id, spec in AOI_SPECS.items():
        case_coverage.append(
            {
                "aoi_id": aoi_id,
                "cases_requested": ["C02", "C04", "C06"],
                "cases_run": ["C02", "C04", "C06"] if aoi_id == "caracas" else ["C02", "C04"],
                "c06_status": "run" if spec["c06_road_reference_available"] else "not_run_missing_independent_road_reference",
            }
        )
    report = {
        "schema_version": "1.0.0",
        "p4_id": "freeze-c-external-validity-v1",
        "fixed_environment": {
            "kg_backend": "memory",
            "llm_provider": "mock",
            "celery_eager": True,
            "scenario_child_max_workers": 1,
            "plan_grounding_mode": "report",
            "local_only": True,
            "artifact_reuse_disabled": True,
        },
        "aoi_inventory_path": str((DOC_ROOT / "2026-08-01-freeze-c-p4-aoi-input-inventory.json").resolve()),
        "reference_sample_path": str(reference_path.resolve()),
        "raw_evidence_root": str(EVIDENCE_ROOT.resolve()),
        "case_coverage": case_coverage,
        "full_method_aggregates": aggregates["full_method"],
        "fixed_priority_aggregates": aggregates["fixed_priority"],
        "full_method_recovery_cost": recovery_cost_aggregates["full_method"],
        "fixed_priority_recovery_cost": recovery_cost_aggregates["fixed_priority"],
        "effect_sizes": effect_sizes,
        "case_rows": rows,
        "reference_results": reference_results,
        "limitations": [
            "当前跨 AOI 重复覆盖 C02/C04；C06 只有 Caracas 具备独立第二道路源，其他 AOI 记录为不可运行。",
            "reference match rate 是外部源一致性/覆盖代理，不等同于人工真值精度、召回率或位置误差完整评价。",
            "每个 AOI/变体只有一次运行；均值、标准差、95% CI 和 Cohen h 仅作探索性统计。",
            "fixed_priority 效果量用于任务顺序敏感性，不证明融合质量提升。",
            "固定优先级 C02 按预期违反水体优先断言；其最终交付指标仍单独统计，不能与 all_cases_passed 混为一谈。",
        ],
    }
    report_json = DOC_ROOT / "2026-08-01-freeze-c-p4-external-validity.json"
    report_md = DOC_ROOT / "2026-08-01-freeze-c-p4-external-validity.md"
    _json_write(report_json, report)
    lines = [
        "# Freeze C P4 外部有效性与论文材料摘要",
        "",
        "本轮覆盖 Caracas、Abidjan 和越南北部沿海走廊。C02/C04 在三个 AOI 各运行完整方法与固定优先级一次；C06 仅在 Caracas 运行，其他 AOI 因缺少独立第二道路源而记录为不可运行。统计结果为探索性结果。",
        "",
        "## 完整方法跨 AOI/案例聚合",
        "",
        "| 指标 | n | 均值 | 样本标准差 | 95% CI | 失败比例 |",
        "| --- | ---: | ---: | ---: | --- | ---: |",
    ]
    labels = {
        "planning_valid": "计划有效",
        "first_quality_gate_passed": "首次质量门通过",
        "final_delivery_success": "最终交付成功",
        "recovery_success": "恢复成功",
        "key_layer_delivered_on_time": "关键图层按时交付",
        "gap_declaration_correct": "gap 声明正确",
        "evidence_complete": "证据完整",
    }
    for metric, summary in aggregates["full_method"].items():
        ci = summary["ci95"]
        lines.append(f"| {labels.get(metric, metric)} | {summary['n']} | {summary['mean']} | {summary['std']} | [{ci[0]}, {ci[1]}] | {summary['failure_rate']} |")
    lines.extend(
        [
            "",
            "## 固定优先级跨 AOI/案例聚合",
            "",
            "| 指标 | n | 均值 | 样本标准差 | 95% CI | 失败比例 |",
            "| --- | ---: | ---: | ---: | --- | ---: |",
        ]
    )
    for metric, summary in aggregates["fixed_priority"].items():
        ci = summary["ci95"]
        lines.append(f"| {labels.get(metric, metric)} | {summary['n']} | {summary['mean']} | {summary['std']} | [{ci[0]}, {ci[1]}] | {summary['failure_rate']} |")
    lines.extend(["", "## 恢复代价", "", "| 变体 | n（有恢复机会案例） | 均值重试 child 数 | 样本标准差 | 95% CI |", "| --- | ---: | ---: | ---: | --- |"])
    for variant, summary in (("full_method", recovery_cost_aggregates["full_method"]), ("fixed_priority", recovery_cost_aggregates["fixed_priority"])):
        ci = summary["ci95"]
        lines.append(f"| {variant} | {summary['n']} | {summary['mean']} | {summary['std']} | [{ci[0]}, {ci[1]}] |")
    lines.extend(["", "## 固定优先级效果量", "", "| 指标 | Cohen h（完整方法 - 固定优先级） |", "| --- | ---: |"])
    for metric, payload in effect_sizes.items():
        lines.append(f"| {labels.get(metric, metric)} | {payload['cohen_h_full_vs_fixed_priority']} |")
    lines.extend(
        [
            "",
            "## 外部参考抽样",
            "",
            "| AOI | 水面 OSM/参考样本匹配率 | 水系 OSM/参考样本匹配率 |",
            "| --- | ---: | ---: |",
        ]
    )
    for item in reference_results:
        layers = item["reference_layers"]
        lines.append(f"| {item['aoi_id']} | {layers['water_polygon']['match_rate']} | {layers['waterways']['match_rate']} |")
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "- 比例型 95% CI 使用小样本 t 临界值并限制到 [0, 1]；每个 AOI/变体只有一次运行，不构成显著性检验。",
            "- 抽样为确定性机器抽样，结果用于外部源一致性审计；不能替代人工标注真值。",
            "- C06 的跨 AOI 缺失独立道路源是数据覆盖缺口，不应解释为系统在其他 AOI 上失败。",
            "",
            f"机器报告：`{report_json}`。原始运行目录：`{EVIDENCE_ROOT}`。",
        ]
    )
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"report_json": str(report_json.resolve()), "report_markdown": str(report_md.resolve())}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare, run, and summarize the minimal P4 external-validity slice.")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--summarize", action="store_true")
    parser.add_argument("--run-aoi", choices=tuple(AOI_SPECS))
    parser.add_argument("--variant", choices=("full_method", "fixed_priority"), default="full_method")
    parser.add_argument("--server-port", type=int, default=8280)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.prepare:
        print(json.dumps(prepare(), ensure_ascii=False, indent=2))
        return 0
    if args.run_aoi:
        result = run_one(aoi_id=args.run_aoi, variant=args.variant, server_port=args.server_port)
        return 0 if result.get("experiment_evidence_manifest_path") or result.get("evidence_manifest_path") else 1
    if args.summarize:
        print(json.dumps(summarize(), ensure_ascii=False, indent=2))
        return 0
    raise SystemExit("请指定 --prepare、--run-aoi 或 --summarize")


if __name__ == "__main__":
    raise SystemExit(main())
