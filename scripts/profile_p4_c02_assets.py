from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import fiona
from shapely.geometry import box, shape

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kg.inmemory_repository import InMemoryKGRepository
from services.source_semantic_contract_service import SourceSemanticContractService


PROTOCOL_ID = "fusionagent.p4.c02-asset-inventory.s2"
AOI_BBOX = (-67.17, 10.38, -66.86, 10.57)
AOI_ID = "caracas-capital-district-v1"
SOURCE_IDS = (
    "raw.osm.water",
    "raw.hydrolakes.water",
    "raw.osm.waterways",
    "raw.hydrorivers.water",
    "raw.osm.road",
    "raw.microsoft.road",
    "aoi.venezuela_capital_district",
)
SOURCE_ROLES = {
    "raw.osm.water": "water_polygon_base",
    "raw.hydrolakes.water": "water_polygon_reference",
    "raw.osm.waterways": "waterways_base",
    "raw.hydrorivers.water": "waterways_reference",
    "raw.osm.road": "road_primary",
    "raw.microsoft.road": "road_reference",
    "aoi.venezuela_capital_district": "aoi_boundary",
}
BUNDLE_SEMANTICS = {
    "catalog.flood.water": {
        "task_kind": "water_polygon",
        "algorithm_id": "algo.fusion.water_polygon.priority_merge.v2",
        "pattern_id": "wp.flood.water.default",
        "component_candidates": ["raw.osm.water", "raw.hydrolakes.water"],
        "required_full_closure": ["raw.osm.water", "raw.hydrolakes.water"],
        "allows_partial_coverage": True,
        "partial_state": "provisional_or_gap",
    },
    "catalog.flood.waterways": {
        "task_kind": "waterways",
        "algorithm_id": "algo.fusion.waterways.conflation.v7",
        "pattern_id": "wp.flood.waterways.fusioncode.conflation.v7",
        "component_candidates": ["raw.osm.waterways", "raw.hydrorivers.water"],
        "required_full_closure": ["raw.osm.waterways", "raw.hydrorivers.water"],
        "allows_partial_coverage": False,
        "partial_state": "gap_or_stop",
    },
    "catalog.flood.road": {
        "task_kind": "road",
        "algorithm_id": "algo.fusion.road.conflation.v7",
        "pattern_id": "wp.flood.road.default",
        "component_candidates": ["raw.osm.road", "raw.microsoft.road"],
        "required_full_closure": ["raw.osm.road", "raw.microsoft.road"],
        "allows_partial_coverage": True,
        "partial_state": "degraded_or_provisional",
    },
}


def profile_assets(*, manifest_path: Path, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing S2 evidence root: {output_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_by_id = {item["source_id"]: item for item in manifest["sources"]}
    missing_manifest_sources = [source_id for source_id in SOURCE_IDS if source_id not in source_by_id]
    if missing_manifest_sources:
        raise ValueError(f"Manifest is missing C02 sources: {missing_manifest_sources}")

    aoi_geom = box(*AOI_BBOX)
    sources: list[dict[str, Any]] = []
    for source_id in SOURCE_IDS:
        source = source_by_id[source_id]
        sources.append(_profile_source(source, aoi_geom=aoi_geom))

    kg_identity = InMemoryKGRepository(experience_policy="pinned_snapshot").get_knowledge_identity()
    semantic_contracts = _build_semantic_contract_probe(source_by_id)
    payload = {
        "inventory_type": "p4_c02_real_asset_inventory",
        "protocol_id": PROTOCOL_ID,
        "claim_eligible": False,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "real_external_data": True,
        "aoi": {
            "aoi_id": AOI_ID,
            "bbox": list(AOI_BBOX),
            "target_crs": "EPSG:32619",
            "spatial_extent": "bbox(-67.17,10.38,-66.86,10.57)",
        },
        "inputs": {
            "case_manifest": _file_ref(manifest_path),
            "case_manifest_version": manifest.get("schema_version"),
        },
        "sources": sources,
        "bundle_semantics": BUNDLE_SEMANTICS,
        "semantic_contracts": semantic_contracts,
        "deferred_layers": {
            "building": {"status": "explicit_gap", "materialize": False},
            "poi": {"status": "explicit_gap", "materialize": False},
        },
        "runtime_calls": {"fusion_runs": 0, "llm_calls": 0, "provider_calls": 0},
        "knowledge_identity": kg_identity,
        "checks": {
            "all_required_assets_exist": all(item["exists"] for item in sources),
            "all_required_assets_intersect_aoi": all(
                item["aoi_intersect_count"] > 0 for item in sources if item["source_id"] != "aoi.venezuela_capital_district"
            ),
            "no_null_or_invalid_geometry": all(
                item["null_geometry_count"] == 0 and item["invalid_geometry_count"] == 0 for item in sources
            ),
            "required_component_semantics_declared": all(
                set(bundle["required_full_closure"]).issubset(set(SOURCE_IDS))
                for bundle in BUNDLE_SEMANTICS.values()
            ),
            "semantic_contracts_valid": all(
                item["validation"].get("valid") is True for item in semantic_contracts.values()
            ),
            "zero_runtime_calls": True,
        },
    }
    payload["passed"] = all(payload["checks"].values())
    output_dir.mkdir(parents=True)
    _write_json(output_dir / "asset_inventory.json", payload)
    return payload


def _build_semantic_contract_probe(source_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    paths = {source_id: Path(source_by_id[source_id]["original_path"]) for source_id in SOURCE_IDS}
    cases = {
        "water_polygon": {
            "job_type": "water",
            "selected_source_id": "catalog.flood.water",
            "component_source_ids": ["raw.osm.water", "raw.hydrolakes.water"],
        },
        "waterways": {
            "job_type": "waterways",
            "selected_source_id": "catalog.flood.waterways",
            "component_source_ids": ["raw.osm.waterways", "raw.hydrorivers.water"],
        },
        "road": {
            "job_type": "road",
            "selected_source_id": "catalog.flood.road",
            "component_source_ids": ["raw.osm.road", "raw.microsoft.road"],
        },
    }
    service = SourceSemanticContractService(
        kg_repo=InMemoryKGRepository(experience_policy="pinned_snapshot")
    )
    probe: dict[str, Any] = {}
    for key, case in cases.items():
        component_paths = {source_id: paths[source_id] for source_id in case["component_source_ids"]}
        contract = service.build_contract(
            run_id="p4-c02-asset-inventory-s2",
            job_type=case["job_type"],
            selected_source_id=case["selected_source_id"],
            component_paths=component_paths,
            target_crs="EPSG:32619",
        )
        probe[key] = {
            "job_type": case["job_type"],
            "selected_source_id": case["selected_source_id"],
            "component_source_ids": case["component_source_ids"],
            "validation": contract.validation,
            "normalization_profiles": {
                source_id: entry.normalization_profile for source_id, entry in contract.sources.items()
            },
            "matched_fields": {
                source_id: {
                    field: matched.to_dict() for field, matched in entry.matched_fields.items()
                }
                for source_id, entry in contract.sources.items()
            },
        }
    return probe


def _profile_source(source: dict[str, Any], *, aoi_geom: Any) -> dict[str, Any]:
    source_id = str(source["source_id"])
    path = Path(source["original_path"])
    result: dict[str, Any] = {
        "source_id": source_id,
        "source_role": SOURCE_ROLES[source_id],
        "original_path": str(path),
        "dataset_version": source.get("dataset_version"),
        "declared_semantic_status": source.get("semantic_status"),
        "exists": path.is_file(),
        "files": [],
    }
    if not path.is_file():
        result.update(
            feature_count=0,
            aoi_intersect_count=0,
            null_geometry_count=0,
            invalid_geometry_count=0,
            bounds=None,
            crs=None,
            geometry_type=None,
            properties=[],
        )
        return result

    result["files"] = [_file_ref(item) for item in _asset_files(path)]
    with fiona.open(path) as collection:
        result.update(
            feature_count=len(collection),
            bounds=list(collection.bounds),
            crs=collection.crs_wkt or dict(collection.crs),
            geometry_type=collection.schema.get("geometry"),
            properties=list(collection.schema.get("properties", {}).keys()),
        )
        null_count = 0
        invalid_count = 0
        aoi_count = 0
        iterator: Iterable[Any]
        if source_id == "raw.hydrolakes.water":
            iterator = collection.items(bbox=AOI_BBOX)
        else:
            iterator = iter(collection)
        for item in iterator:
            feature = item[1] if isinstance(item, tuple) else item
            geometry = feature.get("geometry")
            if geometry is None:
                null_count += 1
                continue
            try:
                candidate = shape(geometry)
                if not candidate.is_valid:
                    invalid_count += 1
                if candidate.intersects(aoi_geom):
                    aoi_count += 1
            except Exception:
                invalid_count += 1
        result["aoi_intersect_count"] = aoi_count
        result["null_geometry_count"] = null_count
        result["invalid_geometry_count"] = invalid_count
    return result


def _asset_files(path: Path) -> list[Path]:
    if path.suffix.lower() != ".shp":
        return [path]
    return sorted(item for item in path.parent.glob(path.stem + ".*") if item.is_file())


def _file_ref(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(path.resolve()), "size_bytes": path.stat().st_size, "sha256": "sha256:" + digest.hexdigest()}


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile real C02 Caracas assets without runtime execution.")
    parser.add_argument("--manifest", type=Path, default=REPO_ROOT / "docs/thesis/manifests/2026-07-20-c02-c04-c06-real-data.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = profile_assets(manifest_path=args.manifest, output_dir=args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
