from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Iterable

import geopandas as gpd
from shapely.geometry import box

from schemas.contract_experiment import (
    ContractExperimentCase,
    ContractExperimentManifest,
    ExperimentStageDeclaration,
    ExternalSourceDeclaration,
)


SHAPEFILE_SIDECARS = (".shp", ".shx", ".dbf", ".prj", ".cpg", ".qix", ".qmd")


def load_experiment_manifest(path: Path) -> ContractExperimentManifest:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return ContractExperimentManifest.model_validate(payload)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def shapefile_bundle_paths(path: Path) -> list[Path]:
    path = Path(path)
    if path.suffix.lower() != ".shp":
        return [path] if path.exists() else []
    return [path.with_suffix(suffix) for suffix in SHAPEFILE_SIDECARS if path.with_suffix(suffix).exists()]


def hash_input_declaration(source: ExternalSourceDeclaration) -> dict[str, Any]:
    original = Path(source.original_path)
    files = shapefile_bundle_paths(original)
    if not files:
        raise FileNotFoundError(f"External source does not exist: {original}")
    return {
        "source_id": source.source_id,
        "product": source.product,
        "original_path": str(original.resolve()),
        "dataset_version": source.dataset_version,
        "observed_at": source.observed_at,
        "freshness_status": source.freshness_status,
        "semantic_status": source.semantic_status,
        "files": [
            {
                "path": str(path.resolve()),
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
            for path in sorted(files)
        ],
    }


def prepare_stage_sources(
    *,
    manifest: ContractExperimentManifest,
    stage: ExperimentStageDeclaration,
    data_root: Path,
    evidence_dir: Path,
) -> dict[str, Any]:
    data_root = Path(data_root)
    evidence_dir = Path(evidence_dir)
    data_root.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    source_by_id = {source.source_id: source for source in manifest.sources}

    for source in manifest.sources:
        _remove_runtime_target(data_root / source.runtime_relative_path)

    prepared: list[dict[str, Any]] = []
    active = set(stage.active_source_ids)
    for source_id in stage.active_source_ids:
        source = source_by_id[source_id]
        target = data_root / source.runtime_relative_path
        _prepare_one_source(source, target)
        prepared.append(
            {
                "source_id": source.source_id,
                "runtime_path": str(target.resolve()),
                "runtime_relative_path": source.runtime_relative_path,
                "files": _hash_runtime_target(target),
                "active": True,
            }
        )
    inactive = [source.source_id for source in manifest.sources if source.enabled and source.source_id not in active]
    payload = {
        "stage_id": stage.stage_id,
        "active_source_ids": list(stage.active_source_ids),
        "inactive_source_ids": inactive,
        "prepared_sources": prepared,
    }
    (evidence_dir / f"prepared_inputs_{stage.stage_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def build_external_input_evidence(manifest: ContractExperimentManifest) -> list[dict[str, Any]]:
    return [hash_input_declaration(source) for source in manifest.sources if source.enabled]


def evaluate_case_contract(
    *,
    case: ContractExperimentCase,
    stage_records: list[dict[str, Any]],
    experiment_dir: Path,
) -> dict[str, Any]:
    case_dir = Path(experiment_dir) / "cases" / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    final_record = stage_records[-1] if stage_records else {}
    final_summary = _load_stage_summary(final_record)
    task_order = list(((final_summary.get("mission") or {}).get("task_kinds") or []))
    child_runs: list[dict[str, Any]] = []
    stage_evaluations: list[dict[str, Any]] = []
    stage_quality: list[dict[str, Any]] = []
    record_by_stage_id = {str(record.get("stage_id")): record for record in stage_records}
    for stage in case.stages:
        record = record_by_stage_id.get(stage.stage_id, {})
        summary = _load_stage_summary(record)
        stage_task_order = list(((summary.get("mission") or {}).get("task_kinds") or []))
        stage_children = list(summary.get("child_runs") or [])
        child_runs.extend(
            {**item, "_experiment_stage_id": stage.stage_id}
            for item in stage_children
            if isinstance(item, dict)
        )
        observations = _summary_observations(summary, case=case, task_order=stage_task_order)
        declared_assertions = {
            name: _assertion_matches(name, expected, observations)
            for name, expected in stage.assertions.items()
        }
        base_assertions = {
            "task_order_matches": not stage.expected_task_order or stage_task_order == stage.expected_task_order,
            "phase_allowed": not stage.expected_phases or summary.get("phase") in stage.expected_phases,
        }
        stage_passed = all(base_assertions.values()) and all(declared_assertions.values())
        stage_evaluations.append(
            {
                "stage_id": stage.stage_id,
                "phase": summary.get("phase"),
                "task_order": stage_task_order,
                "base_assertions": base_assertions,
                "declared_assertions": declared_assertions,
                "observations": observations,
                "passed": stage_passed,
            }
        )
        stage_summary_quality = dict(summary.get("quality") or {})
        stage_quality.append(
            {
                "stage_id": stage.stage_id,
                "phase": summary.get("phase"),
                "accepted_child_count": stage_summary_quality.get("accepted_child_count", 0),
                "rejected_child_count": stage_summary_quality.get("rejected_child_count", 0),
                "child_reports": stage_summary_quality.get("child_reports", []),
            }
        )
    quality = dict(final_summary.get("quality") or {})
    gaps = _derive_gaps(stage_records, child_runs)
    outputs = list(final_summary.get("final_outputs") or [])
    observed_gap_types = {str(item.get("gap_type")) for item in gaps}
    expected_gap_types_observed = set(case.expected_gap_types).issubset(observed_gap_types)

    product_contract = {
        "case_id": case.case_id,
        "product_id": f"{case.case_id}.real_external",
        "product_type": "multi_source_vector_fusion",
        "required_layers": case.expected_layer_priority,
        "water_products": {
            "water_polygon": "polygonal lakes/reservoirs/ponds",
            "waterways": "linear rivers/streams/canals/drains",
        },
        "quality_gates": ["materialized", "aoi_coverage", "geometry_validity", "provenance", "quality_report"],
        "degradation_policy": "external source gaps are explicit and may yield provisional outputs",
        "evidence_contract": "scenario summary, child audits, source manifests, frozen hashes",
    }
    planning_decision = {
        "case_id": case.case_id,
        "expected_layer_priority": case.expected_layer_priority,
        "actual_task_order": task_order,
        "delivery_strategy": case.expected_delivery_strategy,
        "stage_count": len(stage_records),
        "decision": "allow",
        "decision_source": "declarative_case_manifest",
    }
    resource_regime = {"case_id": case.case_id, **case.resource_regime}
    quality_gate_result = {
        "case_id": case.case_id,
        "accepted_child_count": quality.get("accepted_child_count", 0),
        "rejected_child_count": quality.get("rejected_child_count", 0),
        "child_reports": quality.get("child_reports", []),
        "final_phase": final_summary.get("phase"),
        "stages": stage_quality,
    }
    gap_declaration = {
        "case_id": case.case_id,
        "expected_gap_types": case.expected_gap_types,
        "observed_gaps": gaps,
        "expected_gap_types_observed": expected_gap_types_observed,
        "declaration_complete": all("gap_type" in item and "layer" in item for item in gaps),
    }
    evidence_trace = {
        "case_id": case.case_id,
        "stages": stage_records,
        "stage_contract_evaluations": stage_evaluations,
        "scenario_summary_path": final_record.get("summary_path"),
        "source_evidence_path": str((Path(experiment_dir) / "external_inputs.json").resolve()),
        "runtime_boundary": "real external vector data + real fusion algorithms + memory KG + mock LLM + eager execution",
    }
    delivery_manifest = {
        "case_id": case.case_id,
        "final_phase": final_summary.get("phase"),
        "outputs": outputs,
        "provisional_outputs": [item for item in child_runs if item.get("provisional")],
        "superseded_outputs": list(final_summary.get("superseded_outputs") or []),
    }
    stage_observations = [item["observations"] for item in stage_evaluations]
    assertions = {
        "task_order_matches": all(item["base_assertions"]["task_order_matches"] for item in stage_evaluations),
        "phase_allowed": all(item["base_assertions"]["phase_allowed"] for item in stage_evaluations),
        "declared_stage_assertions_passed": all(
            all(item["declared_assertions"].values()) for item in stage_evaluations
        ),
        "expected_gap_types_observed": expected_gap_types_observed,
        "quality_failure_observed": any(item["quality_failure_observed"] for item in stage_observations),
        "degraded_or_provisional_observed": any(
            item["degraded_success_observed"] or item["provisional_observed"]
            for item in stage_observations
        ),
        "supersede_observed": any(item["supersede_observed"] for item in stage_observations),
    }
    case_result = {
        "case_id": case.case_id,
        "passed": all(item["passed"] for item in stage_evaluations) and expected_gap_types_observed,
        "assertions": assertions,
        "stage_evaluations": stage_evaluations,
        "final_phase": final_summary.get("phase"),
        "final_task_order": task_order,
        "gap_count": len(gaps),
    }
    artifacts = {
        "product_contract.json": product_contract,
        "planning_decision.json": planning_decision,
        "resource_regime.json": resource_regime,
        "quality_gate_result.json": quality_gate_result,
        "gap_declaration.json": gap_declaration,
        "evidence_trace.json": evidence_trace,
        "delivery_manifest.json": delivery_manifest,
        "case_result.json": case_result,
    }
    for filename, payload in artifacts.items():
        (case_dir / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return case_result


def _load_stage_summary(record: dict[str, Any]) -> dict[str, Any]:
    embedded = record.get("summary")
    if isinstance(embedded, dict):
        return embedded
    summary = _load_summary(record.get("summary_path"))
    if summary:
        return summary
    phase = record.get("summary_phase")
    return {"phase": phase} if phase else {}


def _summary_observations(
    summary: dict[str, Any],
    *,
    case: ContractExperimentCase,
    task_order: list[str],
) -> dict[str, bool]:
    child_runs = [item for item in summary.get("child_runs") or [] if isinstance(item, dict)]
    quality = dict(summary.get("quality") or {})
    child_reports = [item for item in quality.get("child_reports") or [] if isinstance(item, dict)]
    phase = str(summary.get("phase") or "")
    provisional_observed = phase == "partial_provisional" or any(item.get("provisional") for item in child_runs)
    degraded_observed = any((item.get("degradation") or {}).get("state") == "degraded" for item in child_runs)
    degraded_observed = degraded_observed or any(item.get("degraded_mode") is True for item in child_reports)
    successful_child_observed = any(
        item.get("phase") in {"succeeded", "partial_provisional"} or item.get("provisional") is True
        for item in child_runs
    )
    quality_failure_observed = (
        phase == "failed"
        or quality.get("rejected_child_count", 0) > 0
        or any(item.get("phase") == "failed" or item.get("error") for item in child_runs)
        or any(item.get("accepted") is False for item in child_reports)
    )
    deferred = set(case.request.metadata.get("deferred_task_kinds") or [])
    return {
        "provisional_observed": provisional_observed,
        "supersede_observed": bool(summary.get("superseded_outputs"))
        or any(item.get("supersedes") for item in child_runs),
        "quality_failure_observed": quality_failure_observed,
        "degraded_success_observed": degraded_observed
        and successful_child_observed
        and phase in {"partial_provisional", "partial", "succeeded"},
        "building_deferred_observed": "building" not in task_order and "building" in deferred,
        "water_priority_observed": task_order[:2] == ["water_polygon", "waterways"],
    }


def _assertion_matches(name: str, expected: Any, observations: dict[str, bool]) -> bool:
    observation_key = {
        "provisional_required": "provisional_observed",
        "supersede_required": "supersede_observed",
        "quality_failure_required": "quality_failure_observed",
        "degraded_success_required": "degraded_success_observed",
        "building_deferred": "building_deferred_observed",
        "water_priority": "water_priority_observed",
    }.get(name)
    if observation_key is None:
        return False
    return observations[observation_key] is bool(expected)


def _prepare_one_source(source: ExternalSourceDeclaration, target: Path) -> None:
    original = Path(source.original_path)
    if not original.exists():
        raise FileNotFoundError(f"External source does not exist: {original}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.preparation == "copy":
        if original.suffix.lower() == ".shp":
            for path in shapefile_bundle_paths(original):
                destination = target.with_suffix(path.suffix)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
        else:
            shutil.copy2(original, target)
        return
    kwargs: dict[str, Any] = {}
    if source.original_layer:
        kwargs["layer"] = source.original_layer
    if source.clip_bbox:
        kwargs["bbox"] = tuple(source.clip_bbox)
    frame = gpd.read_file(original, **kwargs)
    if source.clip_bbox and not frame.empty:
        clip_geometry = box(*source.clip_bbox)
        frame = frame[frame.geometry.notna() & frame.geometry.intersects(clip_geometry)].copy()
    if target.suffix.lower() == ".shp":
        frame.to_file(target, driver="ESRI Shapefile", index=False)
    else:
        frame.to_file(target, driver="GPKG", layer=target.stem, index=False)


def _remove_runtime_target(target: Path) -> None:
    if target.suffix.lower() == ".shp":
        for path in shapefile_bundle_paths(target):
            path.unlink(missing_ok=True)
        return
    target.unlink(missing_ok=True)


def _hash_runtime_target(target: Path) -> list[dict[str, Any]]:
    paths = shapefile_bundle_paths(target)
    if not paths and target.exists():
        paths = [target]
    return [
        {"path": str(path.resolve()), "sha256": sha256_file(path), "size_bytes": path.stat().st_size}
        for path in sorted(paths)
    ]


def _load_summary(path: Any) -> dict[str, Any]:
    if not path:
        return {}
    candidate = Path(str(path))
    if not candidate.exists():
        return {}
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _derive_gaps(stage_records: Iterable[dict[str, Any]], child_runs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for item in child_runs:
        layer = str(item.get("task_kind") or item.get("job_type") or "unknown")
        stage_id = item.get("_experiment_stage_id")
        degradation = item.get("degradation") or {}
        missing = list(degradation.get("degraded_component_source_ids") or []) if isinstance(degradation, dict) else []
        phase = str(item.get("phase") or "")
        if missing:
            gaps.append(
                {
                    "layer": layer,
                    "gap_type": "source_unavailable",
                    "source_ids": missing,
                    "phase": phase,
                    "stage_id": stage_id,
                }
            )
        if phase == "failed" or item.get("error"):
            gaps.append(
                {
                    "layer": layer,
                    "gap_type": "quality_failed",
                    "source_ids": missing,
                    "phase": phase,
                    "stage_id": stage_id,
                    "error": item.get("error"),
                }
            )
    for stage in stage_records:
        for item in stage.get("gaps") or []:
            if item not in gaps:
                gaps.append(dict(item))
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in gaps:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique
