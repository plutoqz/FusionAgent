from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import fiona
from pyproj import CRS, Transformer
from shapely.geometry import box, shape
from shapely.ops import transform

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


PROTOCOL_ID = "fusionagent.p4.multi-aoi-candidate-inventory.v1"
DEFAULT_MANIFESTS = {
    "caracas": REPO_ROOT
    / "docs/current/evidence/p4-external-validity/manifests/caracas_c02_c04_c06.json",
    "abidjan": REPO_ROOT
    / "docs/current/evidence/p4-external-validity/manifests/abidjan_c02_c04.json",
    "vietnam_coastal": REPO_ROOT
    / "docs/current/evidence/p4-external-validity/manifests/vietnam_coastal_c02_c04.json",
}
DEFAULT_HISTORICAL_INVENTORY = (
    REPO_ROOT
    / "docs/current/evidence/p4-external-validity/2026-08-01-freeze-c-p4-aoi-input-inventory.json"
)

CAPABILITY_REQUIREMENTS = {
    "water_polygon_pair": {"raw.osm.water", "raw.hydrolakes.water"},
    "waterways_pair": {"raw.osm.waterways", "raw.hydrorivers.water"},
    "dual_road": {"raw.osm.road", "raw.microsoft.road"},
    "dual_building": {"raw.osm.building", "raw.microsoft.building"},
}
FORMAL_CASE_REQUIREMENTS = {
    "C01": {
        "mechanism": "building_delay_with_road_first",
        "required_sources": {
            "raw.osm.road",
            "raw.osm.building",
            "raw.microsoft.building",
        },
    },
    "C02": {
        "mechanism": "water_waterways_and_dual_road_selected_resolved_workflow",
        "required_sources": {
            "raw.osm.water",
            "raw.hydrolakes.water",
            "raw.osm.waterways",
            "raw.hydrorivers.water",
            "raw.osm.road",
            "raw.microsoft.road",
        },
    },
    "C04": {
        "mechanism": "provisional_osm_road_then_microsoft_arrival_supersession",
        "required_sources": {"raw.osm.road", "raw.microsoft.road"},
    },
    "C05": {
        "mechanism": "osm_geometry_microsoft_attribute_building_conflict",
        "required_sources": {"raw.osm.building", "raw.microsoft.building"},
    },
}


def profile_multi_aoi_candidates(
    *,
    manifest_paths: dict[str, Path],
    output_dir: Path,
    implementation_commit: str,
    historical_inventory_path: Path | None = DEFAULT_HISTORICAL_INVENTORY,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite candidate inventory root: {output_dir}")
    historical = _historical_hashes(historical_inventory_path)
    aois = []
    for aoi_id, manifest_path in manifest_paths.items():
        aois.append(
            _profile_aoi(
                aoi_id=aoi_id,
                manifest_path=manifest_path,
                historical_hashes=historical,
            )
        )
    coverage = _case_coverage(aois)
    checks = {
        "all_manifests_exist": all(aoi["manifest"]["exists"] for aoi in aois),
        "all_declared_assets_exist": all(
            source["exists"] for aoi in aois for source in aoi["sources"]
        ),
        "all_declared_assets_intersect_aoi": all(
            source["aoi_intersect_count"] > 0 for aoi in aois for source in aoi["sources"]
        ),
        "no_null_or_invalid_geometry_in_aoi": all(
            source["aoi_null_geometry_count"] == 0
            and source["aoi_invalid_geometry_count"] == 0
            for aoi in aois
            for source in aoi["sources"]
        ),
        "historical_hashes_match_when_available": all(
            file["historical_sha256_match"] in (True, None)
            for aoi in aois
            for source in aoi["sources"]
            for file in source["files"]
        ),
        "zero_runtime_calls": True,
        "no_case_selected_before_e3_e4": True,
    }
    payload = {
        "inventory_type": "p4_multi_aoi_formal_candidate_universe",
        "protocol_id": PROTOCOL_ID,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "claim_eligible": False,
        "selection_status": "candidate_universe_only_no_case_selected",
        "selection_dependency": "E3 extension gate and E4 agreement audit must reach terminal states",
        "source_basis": (
            "Only repository-declared Caracas, Abidjan, and Vietnam coastal manifests are profiled. "
            "No source was downloaded or added after observing repeated-planning results."
        ),
        "implementation": {
            "commit": implementation_commit,
            "script": _profile_file(Path(__file__), historical_hashes={}),
        },
        "inputs": {
            "manifests": {
                aoi_id: _profile_file(path, historical_hashes={})
                for aoi_id, path in manifest_paths.items()
            },
            "historical_inventory": (
                _profile_file(historical_inventory_path, historical_hashes={})
                if historical_inventory_path is not None and historical_inventory_path.is_file()
                else None
            ),
        },
        "aois": aois,
        "formal_case_source_coverage": coverage,
        "retired_or_excluded_cases": {
            "C03": "negative_control_planning_only",
            "C06": "legacy inevitable-quality-failure mechanism retired after negative screening",
        },
        "e5_multi_aoi_source_coverage_ready": any(
            item["source_closed_aoi_count"] >= 2 for item in coverage
        ),
        "checks": checks,
        "inventory_integrity_passed": all(checks.values()),
        "runtime_calls": {"fusion_runs": 0, "llm_calls": 0, "provider_calls": 0},
        "claim_boundary": (
            "Asset presence and geometry validity establish candidate feasibility only. Historical mock-LLM P4-G "
            "runs and same case labels do not establish formal planning E2E equivalence."
        ),
    }
    output_dir.mkdir(parents=True)
    _write_json(output_dir / "candidate_inventory.json", payload)
    return payload


def _profile_aoi(
    *,
    aoi_id: str,
    manifest_path: Path,
    historical_hashes: dict[str, str],
) -> dict[str, Any]:
    manifest = _read_json(manifest_path)
    bbox_values = _manifest_bbox(manifest)
    source_ids = {source["source_id"] for source in manifest["sources"]}
    capability_coverage = {
        name: {
            "required_sources": sorted(required),
            "available_sources": sorted(required & source_ids),
            "missing_sources": sorted(required - source_ids),
            "source_closed": required.issubset(source_ids),
        }
        for name, required in CAPABILITY_REQUIREMENTS.items()
    }
    sources = [
        _profile_source(
            source,
            bbox_values=bbox_values,
            historical_hashes=historical_hashes,
        )
        for source in manifest["sources"]
    ]
    return {
        "aoi_id": aoi_id,
        "title": manifest.get("title"),
        "bbox": bbox_values,
        "target_crs": manifest.get("runtime", {}).get("target_crs"),
        "historical_case_ids": [case["case_id"] for case in manifest.get("cases", [])],
        "historical_llm_provider": manifest.get("runtime", {}).get("llm_provider"),
        "manifest": _profile_file(manifest_path, historical_hashes={}),
        "source_ids": sorted(source_ids),
        "capability_source_coverage": capability_coverage,
        "sources": sources,
    }


def _profile_source(
    source: dict[str, Any],
    *,
    bbox_values: list[float],
    historical_hashes: dict[str, str],
) -> dict[str, Any]:
    path = Path(source["original_path"])
    result: dict[str, Any] = {
        "source_id": source["source_id"],
        "product": source.get("product"),
        "dataset_version": source.get("dataset_version"),
        "declared_semantic_status": source.get("semantic_status"),
        "original_path": str(path),
        "exists": path.is_file(),
        "files": [],
        "feature_count": 0,
        "aoi_intersect_count": 0,
        "aoi_null_geometry_count": 0,
        "aoi_invalid_geometry_count": 0,
        "crs": None,
        "bounds": None,
        "geometry_type": None,
    }
    if not path.is_file():
        return result
    result["files"] = [
        _profile_file(item, historical_hashes=historical_hashes) for item in _asset_files(path)
    ]
    aoi_wgs84 = box(*bbox_values)
    with fiona.open(path) as collection:
        source_crs = CRS.from_user_input(collection.crs_wkt or collection.crs or "EPSG:4326")
        if source_crs == CRS.from_epsg(4326):
            aoi_source = aoi_wgs84
        else:
            transformer = Transformer.from_crs("EPSG:4326", source_crs, always_xy=True)
            aoi_source = transform(transformer.transform, aoi_wgs84)
        result.update(
            feature_count=len(collection),
            crs=source_crs.to_string(),
            bounds=list(collection.bounds),
            geometry_type=collection.schema.get("geometry"),
        )
        intersect_count = 0
        null_count = 0
        invalid_count = 0
        for item in collection.items(bbox=aoi_source.bounds):
            feature = item[1] if isinstance(item, tuple) else item
            geometry = feature.get("geometry")
            if geometry is None:
                null_count += 1
                continue
            try:
                candidate = shape(geometry)
            except Exception:
                invalid_count += 1
                continue
            if candidate.intersects(aoi_source):
                intersect_count += 1
                if not candidate.is_valid:
                    invalid_count += 1
        result["aoi_intersect_count"] = intersect_count
        result["aoi_null_geometry_count"] = null_count
        result["aoi_invalid_geometry_count"] = invalid_count
    return result


def _case_coverage(aois: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for case_id, definition in FORMAL_CASE_REQUIREMENTS.items():
        per_aoi = []
        required = definition["required_sources"]
        for aoi in aois:
            available = set(aoi["source_ids"])
            per_aoi.append(
                {
                    "aoi_id": aoi["aoi_id"],
                    "available_sources": sorted(required & available),
                    "missing_sources": sorted(required - available),
                    "source_closed": required.issubset(available),
                }
            )
        closed_count = sum(item["source_closed"] for item in per_aoi)
        rows.append(
            {
                "case_id": case_id,
                "mechanism": definition["mechanism"],
                "required_sources": sorted(required),
                "aoi_coverage": per_aoi,
                "source_closed_aoi_count": closed_count,
                "eligible_for_two_aoi_selection": closed_count >= 2,
            }
        )
    return rows


def _manifest_bbox(manifest: dict[str, Any]) -> list[float]:
    bboxes = {
        tuple(source["clip_bbox"])
        for source in manifest.get("sources", [])
        if source.get("clip_bbox") is not None
    }
    if len(bboxes) != 1:
        raise ValueError(f"Manifest must declare one shared clip_bbox, got {sorted(bboxes)}")
    return list(next(iter(bboxes)))


def _historical_hashes(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    payload = _read_json(path)
    hashes = {}
    for aoi in payload.get("inventory", []):
        for source in aoi.get("input_hashes", []):
            for file in source.get("files", []):
                hashes[_path_key(Path(file["path"]))] = _normalize_sha256(file["sha256"])
    return hashes


def _asset_files(path: Path) -> list[Path]:
    if path.suffix.lower() != ".shp":
        return [path]
    return sorted(item for item in path.parent.glob(path.stem + ".*") if item.is_file())


def _profile_file(path: Path, *, historical_hashes: dict[str, str]) -> dict[str, Any]:
    current = _file_hash(path)
    historical = historical_hashes.get(_path_key(path))
    return {
        "path": str(path.resolve()),
        "exists": path.is_file(),
        "size_bytes": path.stat().st_size,
        "sha256": current,
        "historical_sha256": historical,
        "historical_sha256_match": current == historical if historical is not None else None,
    }


def _path_key(path: Path) -> str:
    return str(path.resolve()).replace("/", "\\").lower()


def _normalize_sha256(value: str) -> str:
    return value if value.startswith("sha256:") else "sha256:" + value


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile the predeclared multi-AOI formal E2E candidate universe.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--historical-inventory", type=Path, default=DEFAULT_HISTORICAL_INVENTORY)
    args = parser.parse_args()
    _assert_clean_worktree()
    report = profile_multi_aoi_candidates(
        manifest_paths=DEFAULT_MANIFESTS,
        output_dir=args.output,
        implementation_commit=_git_head(),
        historical_inventory_path=args.historical_inventory,
    )
    print(
        json.dumps(
            {
                "inventory_integrity_passed": report["inventory_integrity_passed"],
                "e5_multi_aoi_source_coverage_ready": report["e5_multi_aoi_source_coverage_ready"],
                "runtime_calls": report["runtime_calls"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["inventory_integrity_passed"] else 2


def _git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()


def _assert_clean_worktree() -> None:
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=REPO_ROOT,
        text=True,
    )
    if status.strip():
        raise RuntimeError("Multi-AOI candidate inventory requires a clean worktree")


if __name__ == "__main__":
    raise SystemExit(main())
