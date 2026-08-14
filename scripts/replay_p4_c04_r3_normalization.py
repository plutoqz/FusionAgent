from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import geopandas as gpd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kg.inmemory_repository import InMemoryKGRepository
from schemas.task_kind import TaskKind
from services.quality_gate_service import QualityGateService
from services.contract_experiment_service import sha256_file
from services.source_semantic_contract_service import SourceSemanticContractService
from services.track_b_source_normalization import normalize_track_b_source_frame


def replay_r3_normalization(*, r3_root: Path, output_root: Path) -> dict[str, Any]:
    r3_root = r3_root.resolve()
    output_root = output_root.resolve()
    if output_root == r3_root or r3_root in output_root.parents:
        raise ValueError("Replay output must not modify the preserved r3 evidence root")
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"Replay output root is not empty: {output_root}")

    failure = _read_json(r3_root / "experiment_failure.json")
    failed_run_id = str(failure["failed_run_id"])
    run_root = r3_root / "runtime" / "runs" / failed_run_id
    prior_contract_path = run_root / "source_semantic_contract.json"
    prior_contract = _read_json(prior_contract_path)
    component_paths = {
        source_id: Path(entry["artifact_path"])
        for source_id, entry in prior_contract["sources"].items()
    }

    contract = SourceSemanticContractService(kg_repo=InMemoryKGRepository()).build_contract(
        run_id=f"{failed_run_id}-normalization-replay",
        job_type="road",
        selected_source_id="catalog.typhoon.road",
        component_paths=component_paths,
        target_crs="EPSG:32619",
    )
    normalized_sources: dict[str, dict[str, Any]] = {}
    for source_id, path in component_paths.items():
        raw = gpd.read_file(path, engine="pyogrio", fid_as_index=True)
        normalized = normalize_track_b_source_frame(
            source_id,
            raw,
            target_crs="EPSG:32619",
            source_semantics=contract.sources[source_id],
        )
        normalized_sources[source_id] = _normalized_summary(normalized)

    artifact_path = run_root / "output" / "road_large_area_fused.repair-1.gpkg"
    quality = QualityGateService().evaluate(
        artifact_path=artifact_path,
        task_kind=TaskKind.road,
        required_fields=[],
        requested_bbox=(-67.17, 10.38, -66.86, 10.57),
        component_coverage={
            source_id: {
                "source_id": source_id,
                "coverage_status": "available",
                "feature_count": contract.sources[source_id].feature_count,
            }
            for source_id in component_paths
        },
        source_artifact_paths=component_paths,
        quality_policy_id="quality.default.road.v1",
        contract_id="contract.road.fused.v1",
    )

    payload = {
        "report_type": "p4_c04_r3_semantic_normalization_replay",
        "source_protocol_id": failure["protocol_id"],
        "source_case_identity": failure["case_identity"],
        "source_failed_run_id": failed_run_id,
        "claim_boundary": "read_only_replay; no r3 result mutation; no fusion execution",
        "execution_counts": {
            "fusion_runs_started": 0,
            "llm_calls": 0,
            "provider_network_calls": 0,
        },
        "preserved_inputs": {
            "experiment_failure": _file_ref(r3_root / "experiment_failure.json"),
            "prior_source_semantic_contract": _file_ref(prior_contract_path),
            "quality_replay_artifact": _file_ref(artifact_path),
            "component_artifacts": {
                source_id: _file_ref(path) for source_id, path in component_paths.items()
            },
        },
        "normalized_contract": contract.to_dict(),
        "normalized_sources": normalized_sources,
        "quality_replay": {
            "accepted": quality.accepted,
            "failure_reasons": quality.failure_reasons,
            "soft_failure_reasons": quality.soft_failure_reasons,
            "feature_count": quality.metrics.get("feature_count"),
            "total_length_km": quality.metrics.get("total_length_km"),
            "dangle_endpoint_count": quality.metrics.get("dangle_endpoint_count"),
            "dangle_endpoint_rate_per_100km": quality.metrics.get("dangle_endpoint_rate_per_100km"),
            "dangle_threshold": quality.checks["dangle_endpoint_rate_per_100km"]["threshold"],
            "knowledge_identity": quality.knowledge_identity,
        },
        "passed": bool(contract.validation["valid"] and quality.accepted),
    }
    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / "replay_report.json", payload)
    _write_json(output_root / "normalized_source_semantic_contract.json", contract.to_dict())
    return payload


def _normalized_summary(frame: gpd.GeoDataFrame) -> dict[str, Any]:
    required = ["source_feature_id", "road_class", "geometry"]
    missing = [field for field in required if field not in frame.columns]
    identifier_values = frame.get("source_feature_id", []).tolist()
    digest = hashlib.sha256()
    for identifier, road_class in zip(identifier_values, frame.get("road_class", []).tolist()):
        digest.update(f"{identifier}\0{road_class}\n".encode("utf-8"))
    return {
        "feature_count": int(len(frame)),
        "crs": str(frame.crs),
        "geometry_types": sorted(str(value) for value in frame.geometry.geom_type.dropna().unique()),
        "missing_required_fields": missing,
        "source_feature_id_unique": len(set(identifier_values)) == len(identifier_values),
        "canonical_field_sha256": "sha256:" + digest.hexdigest(),
        "normalization_profiles": sorted(
            str(value) for value in frame.get("normalization_profile", []).dropna().unique()
        )
        if "normalization_profile" in frame.columns
        else [],
        "provenance_fields": sorted(
            column for column in frame.columns if str(column).endswith("_provenance")
        ),
    }


def _file_ref(path: Path) -> dict[str, Any]:
    return {"path": str(path.resolve()), "sha256": "sha256:" + sha256_file(path)}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay the preserved C04 r3 inputs without fusion execution.")
    parser.add_argument("--r3-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = replay_r3_normalization(r3_root=args.r3_root, output_root=args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
