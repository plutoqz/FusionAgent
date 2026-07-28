from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import geopandas as gpd

from kg.source_catalog import get_raw_vector_source_spec
from schemas.degradation import DegradationContext, DegradationLevel
from schemas.product_contract_runtime import (
    ProductContractRuntimeResult,
    RuntimeAlgorithmResult,
    RuntimeLayerExecution,
    RuntimeLayerStatus,
    RuntimeSourceResult,
    RuntimeSourceStatus,
    RuntimeWritebackResult,
)
from schemas.task_kind import TaskKind, task_kind_output_type
from services.artifact_registry import ArtifactRecord, ArtifactRegistry
from services.domain_fusion_runners import (
    run_road_tile,
    run_water_polygon_tile,
    run_waterways_tile,
)
from services.output_contract_service import get_domain_output_contract
from services.quality_gate_service import QualityGateService
from services.raw_vector_source_service import RawVectorSourceService
from services.tile_partition_service import TilePartitionService
from utils.crs import derive_default_target_crs
from utils.shp_zip import validate_zip_has_shapefile


USABLE_SOURCE_STATUSES = {"available"}
PLANNING_ALGORITHM_BY_LAYER = {
    "building": "algo.fusion.building.v1",
    "road": "algo.fusion.road.v1",
    "water_type_1": "algo.fusion.water_type_1.v1",
    "water_type_2": "algo.fusion.water_type_2.v1",
    "poi": "algo.fusion.poi.v1",
}
RUNTIME_ALGORITHM_BY_LAYER = {
    "building": "algo.fusion.building.multi_source.decomposed.v1",
    "road": "algo.fusion.road.conflation.v7",
    "water_type_1": "algo.fusion.water_polygon.priority_merge.v2",
    "water_type_2": "algo.fusion.waterways.conflation.v7",
    "poi": "algo.fusion.poi.geohash_neighbor_match.v1",
}
TASK_KIND_BY_LAYER = {
    "building": TaskKind.building,
    "road": TaskKind.road,
    "water_type_1": TaskKind.water_polygon,
    "water_type_2": TaskKind.waterways,
    "poi": TaskKind.poi,
}


@dataclass(frozen=True)
class MaterializedRuntimeSource:
    artifact_path: Path
    vector_path: Path
    feature_count: int
    coverage_status: str
    source_mode: str


class RuntimeSourceMaterializer(Protocol):
    def materialize(
        self,
        *,
        source_id: str,
        bbox: tuple[float, float, float, float],
        target_dir: Path,
        target_crs: str,
    ) -> MaterializedRuntimeSource: ...


class RepositoryRuntimeSourceMaterializer:
    def __init__(
        self,
        *,
        repo_root: Path,
        registry: ArtifactRegistry,
        cache_dir: Path,
    ) -> None:
        self.raw_source_service = RawVectorSourceService(
            root_dir=Path(repo_root),
            registry=registry,
            cache_dir=Path(cache_dir),
        )

    def materialize(
        self,
        *,
        source_id: str,
        bbox: tuple[float, float, float, float],
        target_dir: Path,
        target_crs: str,
    ) -> MaterializedRuntimeSource:
        get_raw_vector_source_spec(source_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        materialized = self.raw_source_service.resolve(
            source_id=source_id,
            request_bbox=bbox,
            target_path=target_dir / "source.zip",
            target_crs=target_crs,
        )
        extract_dir = target_dir / "extracted"
        vector_path = validate_zip_has_shapefile(materialized.zip_path, extract_dir)
        return MaterializedRuntimeSource(
            artifact_path=materialized.zip_path,
            vector_path=vector_path,
            feature_count=int(materialized.feature_count or 0),
            coverage_status=materialized.coverage_status,
            source_mode=materialized.source_mode,
        )


class ProductContractRuntimeExecutor:
    def __init__(
        self,
        *,
        repo_root: Path,
        artifact_registry_path: Path,
        cache_dir: Path,
        source_materializer: RuntimeSourceMaterializer | None = None,
        quality_gate_service: QualityGateService | None = None,
        target_crs: str | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.registry = ArtifactRegistry(Path(artifact_registry_path))
        self.artifact_registry_path = Path(artifact_registry_path)
        self.cache_dir = Path(cache_dir)
        self.source_materializer = source_materializer or RepositoryRuntimeSourceMaterializer(
            repo_root=self.repo_root,
            registry=self.registry,
            cache_dir=self.cache_dir,
        )
        self.quality_gate_service = quality_gate_service or QualityGateService()
        self.target_crs = target_crs

    def execute(
        self,
        *,
        case: dict[str, Any],
        planning_decision: dict[str, Any],
        output_dir: Path,
    ) -> dict[str, Any]:
        started_at = _utc_now()
        output_dir = Path(output_dir)
        runtime_dir = output_dir / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        bbox = tuple(float(value) for value in case["aoi"]["bbox"])
        target_crs = self.target_crs or derive_default_target_crs(bbox)
        source_observations = {
            str(item["source_id"]): dict(item)
            for item in case["input_sources_status"]
        }

        layer_results: list[RuntimeLayerExecution] = []
        errors: list[str] = []
        for decision in planning_decision["layer_decisions"]:
            layer_result = self._execute_layer(
                case=case,
                decision={**decision, "planner": planning_decision["planner"]},
                source_observations=source_observations,
                bbox=bbox,
                target_crs=target_crs,
                runtime_dir=runtime_dir,
            )
            layer_results.append(layer_result)
            if layer_result.status == RuntimeLayerStatus.FAILED:
                errors.append(
                    f"{layer_result.layer}: "
                    f"{layer_result.algorithm_result.error or 'runtime layer failed'}"
                )

        executed = [item for item in layer_results if item.status != RuntimeLayerStatus.SKIPPED]
        failed = [item for item in executed if item.status == RuntimeLayerStatus.FAILED]
        if failed and len(failed) == len(executed):
            status = "failed"
        elif failed:
            status = "partial"
        else:
            status = "succeeded"
        result = ProductContractRuntimeResult(
            execution_id=(
                f"runtime.{case['case_id']}.{planning_decision['planner']}."
                f"{uuid.uuid4().hex[:12]}"
            ),
            case_id=case["case_id"],
            planner=planning_decision["planner"],
            status=status,
            target_crs=target_crs,
            artifact_registry_path=str(self.artifact_registry_path),
            layer_results=layer_results,
            errors=errors,
            started_at=started_at,
            completed_at=_utc_now(),
        )
        return result.model_dump(mode="json")

    def _execute_layer(
        self,
        *,
        case: dict[str, Any],
        decision: dict[str, Any],
        source_observations: dict[str, dict[str, Any]],
        bbox: tuple[float, float, float, float],
        target_crs: str,
        runtime_dir: Path,
    ) -> RuntimeLayerExecution:
        started_at = _utc_now()
        layer = str(decision["layer"])
        task_kind = TASK_KIND_BY_LAYER[layer]
        layer_dir = runtime_dir / _safe_component(layer)
        layer_dir.mkdir(parents=True, exist_ok=True)
        selected_sources = [str(value) for value in decision["selected_sources"]]
        selected_algorithm = str(decision["selected_algorithm"])
        expected_algorithm = PLANNING_ALGORITHM_BY_LAYER[layer]

        if decision["delivery_mode"] in {"background_pending", "not_delivered"}:
            return RuntimeLayerExecution(
                layer=layer,
                task_kind=task_kind.value,
                delivery_mode=decision["delivery_mode"],
                selected_sources=selected_sources,
                status=RuntimeLayerStatus.SKIPPED,
                algorithm_result=RuntimeAlgorithmResult(
                    selected_algorithm_id=selected_algorithm,
                    execution_kind="not_scheduled",
                    status="skipped",
                    fallback_reason=f"planner_delivery_mode={decision['delivery_mode']}",
                ),
                writeback=RuntimeWritebackResult(status="skipped"),
                started_at=started_at,
                completed_at=_utc_now(),
            )

        if selected_algorithm != expected_algorithm:
            return self._failed_layer(
                layer=layer,
                task_kind=task_kind,
                decision=decision,
                started_at=started_at,
                error=(
                    f"selected algorithm is not executable for layer {layer}: "
                    f"expected={expected_algorithm}, actual={selected_algorithm}"
                ),
            )

        source_results: list[RuntimeSourceResult] = []
        materialized_sources: dict[str, Path] = {}
        for source_id in selected_sources:
            observation = source_observations.get(source_id)
            if observation is None:
                source_results.append(
                    RuntimeSourceResult(
                        source_id=source_id,
                        observed_status="unknown",
                        status=RuntimeSourceStatus.FAILED,
                        error="selected source is absent from case observations",
                    )
                )
                continue
            observed_status = str(observation["status"])
            if observed_status not in USABLE_SOURCE_STATUSES:
                source_results.append(
                    RuntimeSourceResult(
                        source_id=source_id,
                        observed_status=observed_status,
                        status=RuntimeSourceStatus.SKIPPED_KNOWN_UNUSABLE,
                        coverage_status="unusable",
                        source_mode="case_observation_gate",
                    )
                )
                continue
            source_dir = layer_dir / "sources" / _safe_component(source_id)
            try:
                materialized = self.source_materializer.materialize(
                    source_id=source_id,
                    bbox=bbox,
                    target_dir=source_dir,
                    target_crs=target_crs,
                )
                source_results.append(
                    RuntimeSourceResult(
                        source_id=source_id,
                        observed_status=observed_status,
                        status=RuntimeSourceStatus.MATERIALIZED,
                        artifact_path=str(materialized.artifact_path),
                        vector_path=str(materialized.vector_path),
                        feature_count=materialized.feature_count,
                        coverage_status=materialized.coverage_status,
                        source_mode=materialized.source_mode,
                        sha256=_sha256(materialized.artifact_path),
                    )
                )
                if materialized.feature_count > 0:
                    materialized_sources[source_id] = materialized.vector_path
            except Exception as exc:  # noqa: BLE001
                source_results.append(
                    RuntimeSourceResult(
                        source_id=source_id,
                        observed_status=observed_status,
                        status=RuntimeSourceStatus.FAILED,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )

        if not materialized_sources:
            return self._failed_layer(
                layer=layer,
                task_kind=task_kind,
                decision=decision,
                started_at=started_at,
                source_results=source_results,
                error="no selected source produced a non-empty materialized vector",
            )

        try:
            algorithm_result = self._execute_algorithm(
                layer=layer,
                decision=decision,
                bbox=bbox,
                target_crs=target_crs,
                sources=materialized_sources,
                layer_dir=layer_dir,
            )
        except Exception as exc:  # noqa: BLE001
            return self._failed_layer(
                layer=layer,
                task_kind=task_kind,
                decision=decision,
                started_at=started_at,
                source_results=source_results,
                error=f"{type(exc).__name__}: {exc}",
            )

        output_path = Path(str(algorithm_result.output_path))
        component_coverage = _component_coverage(source_results)
        quality_policy_id = None
        if len(materialized_sources) == 1:
            quality_policy_id = f"quality.product_contract.single_source.{task_kind.value}.v1"
        degradation_context = _degradation_context(source_results)
        domain_contract_id = (
            get_domain_output_contract(task_kind).contract_id
            if algorithm_result.execution_kind == "domain_fusion"
            else None
        )
        quality_report = self.quality_gate_service.evaluate(
            artifact_path=output_path,
            task_kind=task_kind,
            required_fields=(
                [] if domain_contract_id is not None else ["source_id"]
            ),
            requested_bbox=bbox,
            component_coverage=component_coverage,
            source_artifact_paths=materialized_sources,
            quality_policy_id=quality_policy_id,
            contract_id=domain_contract_id,
            degradation_context=degradation_context,
        )
        quality_path = layer_dir / "quality_report.json"
        quality_path.write_text(
            json.dumps(quality_report.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if quality_report.accepted:
            writeback = self._register_output(
                case=case,
                layer=layer,
                task_kind=task_kind,
                decision=decision,
                output_path=output_path,
                quality_path=quality_path,
                bbox=bbox,
                target_crs=target_crs,
                algorithm_result=algorithm_result,
            )
            status = RuntimeLayerStatus.SUCCEEDED
        else:
            writeback = RuntimeWritebackResult(
                status="skipped_quality_rejected",
                registry_path=str(self.artifact_registry_path),
            )
            status = RuntimeLayerStatus.FAILED

        return RuntimeLayerExecution(
            layer=layer,
            task_kind=task_kind.value,
            delivery_mode=decision["delivery_mode"],
            selected_sources=selected_sources,
            status=status,
            source_results=source_results,
            algorithm_result=algorithm_result,
            quality_report=quality_report.model_dump(mode="json"),
            quality_report_path=str(quality_path),
            writeback=writeback,
            started_at=started_at,
            completed_at=_utc_now(),
        )

    def _execute_algorithm(
        self,
        *,
        layer: str,
        decision: dict[str, Any],
        bbox: tuple[float, float, float, float],
        target_crs: str,
        sources: dict[str, Path],
        layer_dir: Path,
    ) -> RuntimeAlgorithmResult:
        selected_algorithm = str(decision["selected_algorithm"])
        runtime_algorithm = RUNTIME_ALGORITHM_BY_LAYER[layer]
        output_dir = layer_dir / "algorithm"
        output_dir.mkdir(parents=True, exist_ok=True)

        if _can_run_domain_fusion(layer, sources):
            tile = TilePartitionService().partition_bbox(
                bbox=bbox,
                working_crs=target_crs,
            ).tiles[0]
            runner = {
                "road": run_road_tile,
                "water_type_1": run_water_polygon_tile,
                "water_type_2": run_waterways_tile,
            }[layer]
            output_path, details = runner(
                tile,
                sources,
                output_dir,
                target_crs,
                {},
            )
            return RuntimeAlgorithmResult(
                selected_algorithm_id=selected_algorithm,
                resolved_algorithm_id=runtime_algorithm,
                selected_algorithm_executed=True,
                execution_kind="domain_fusion",
                status="succeeded",
                output_path=str(output_path),
                output_sha256=_sha256(output_path),
                details=details,
            )

        if len(sources) == 1 and (
            len(decision["selected_sources"]) == 1
            or decision["delivery_mode"] in {"provisional", "degraded"}
        ):
            source_id, source_path = next(iter(sources.items()))
            output_path = _write_single_source_passthrough(
                layer=layer,
                source_id=source_id,
                source_path=source_path,
                output_dir=output_dir,
                target_crs=target_crs,
            )
            return RuntimeAlgorithmResult(
                selected_algorithm_id=selected_algorithm,
                resolved_algorithm_id="runtime.single_source_passthrough.v1",
                selected_algorithm_executed=False,
                execution_kind="single_source_passthrough",
                status="succeeded",
                output_path=str(output_path),
                output_sha256=_sha256(output_path),
                fallback_reason=(
                    "The selected fusion algorithm did not have a complete usable source "
                    "set; the planner-authorized single-source delivery was materialized "
                    "and marked explicitly."
                ),
                details={"materialized_source_id": source_id},
            )

        raise RuntimeError(
            f"selected algorithm {selected_algorithm} cannot execute with materialized "
            f"sources={sorted(sources)} and delivery_mode={decision['delivery_mode']}"
        )

    def _register_output(
        self,
        *,
        case: dict[str, Any],
        layer: str,
        task_kind: TaskKind,
        decision: dict[str, Any],
        output_path: Path,
        quality_path: Path,
        bbox: tuple[float, float, float, float],
        target_crs: str,
        algorithm_result: RuntimeAlgorithmResult,
    ) -> RuntimeWritebackResult:
        frame = gpd.read_file(output_path)
        artifact_id = f"product_contract.{case['case_id']}.{layer}.{uuid.uuid4().hex}"
        self.registry.register(
            ArtifactRecord(
                artifact_id=artifact_id,
                artifact_path=str(output_path),
                artifact_role="fusion_result",
                job_type=task_kind.value,
                disaster_type=str(case["scenario"]),
                created_at=_utc_now(),
                output_fields=[str(column) for column in frame.columns],
                output_data_type=task_kind_output_type(task_kind),
                target_crs=target_crs,
                bbox=bbox,
                meta={
                    "case_id": case["case_id"],
                    "layer": layer,
                    "planner": decision.get("planner"),
                    "selected_algorithm_id": decision["selected_algorithm"],
                    "resolved_algorithm_id": algorithm_result.resolved_algorithm_id,
                    "delivery_mode": decision["delivery_mode"],
                    "quality_report_path": str(quality_path),
                    "sha256": _sha256(output_path),
                },
            )
        )
        self.registry.register(
            ArtifactRecord(
                artifact_id=f"{artifact_id}.quality",
                artifact_path=str(quality_path),
                artifact_role="quality_report",
                job_type=task_kind.value,
                disaster_type=str(case["scenario"]),
                created_at=_utc_now(),
                target_crs=target_crs,
                bbox=bbox,
                meta={"case_id": case["case_id"], "layer": layer},
            )
        )
        return RuntimeWritebackResult(
            status="registered",
            artifact_id=artifact_id,
            registry_path=str(self.artifact_registry_path),
        )

    @staticmethod
    def _failed_layer(
        *,
        layer: str,
        task_kind: TaskKind,
        decision: dict[str, Any],
        started_at: str,
        error: str,
        source_results: list[RuntimeSourceResult] | None = None,
    ) -> RuntimeLayerExecution:
        return RuntimeLayerExecution(
            layer=layer,
            task_kind=task_kind.value,
            delivery_mode=decision["delivery_mode"],
            selected_sources=[str(value) for value in decision["selected_sources"]],
            status=RuntimeLayerStatus.FAILED,
            source_results=source_results or [],
            algorithm_result=RuntimeAlgorithmResult(
                selected_algorithm_id=str(decision["selected_algorithm"]),
                resolved_algorithm_id=RUNTIME_ALGORITHM_BY_LAYER.get(layer),
                execution_kind="failed_before_output",
                status="failed",
                error=error,
            ),
            writeback=RuntimeWritebackResult(status="not_registered"),
            started_at=started_at,
            completed_at=_utc_now(),
        )


def _can_run_domain_fusion(layer: str, sources: dict[str, Path]) -> bool:
    source_ids = set(sources)
    if layer == "road":
        return "raw.osm.road" in source_ids and bool(
            source_ids
            & {"raw.microsoft.road", "raw.overture.road", "raw.overture.transportation"}
        )
    if layer == "water_type_1":
        return "raw.osm.water" in source_ids and bool(
            source_ids & {"raw.hydrolakes.water", "raw.local.water"}
        )
    if layer == "water_type_2":
        return "raw.osm.waterways" in source_ids and bool(
            source_ids & {"raw.hydrorivers.water", "raw.local.pakistan.waterways"}
        )
    return False


def _write_single_source_passthrough(
    *,
    layer: str,
    source_id: str,
    source_path: Path,
    output_dir: Path,
    target_crs: str,
) -> Path:
    frame = gpd.read_file(source_path)
    if frame.crs is None:
        frame = frame.set_crs(target_crs)
    frame = frame.to_crs(target_crs)
    frame = frame.copy()
    frame["source_id"] = source_id
    if "source_feature_id" not in frame.columns:
        frame["source_feature_id"] = [f"{source_id}:{index}" for index in range(len(frame))]
    if layer == "water_type_1":
        frame["feature_kind"] = "polygon"
    elif layer == "water_type_2":
        frame["feature_kind"] = "line"
    output_path = output_dir / f"{_safe_component(layer)}_single_source.gpkg"
    frame.to_file(output_path, driver="GPKG")
    return output_path


def _component_coverage(
    source_results: list[RuntimeSourceResult],
) -> dict[str, dict[str, Any]]:
    return {
        item.source_id: {
            "feature_count": int(item.feature_count or 0),
            "coverage_status": item.coverage_status or "missing",
            "status": item.status.value,
            "path": item.vector_path,
        }
        for item in source_results
    }


def _degradation_context(
    source_results: list[RuntimeSourceResult],
) -> DegradationContext | None:
    available = [
        item.source_id
        for item in source_results
        if item.status == RuntimeSourceStatus.MATERIALIZED and int(item.feature_count or 0) > 0
    ]
    missing = [item.source_id for item in source_results if item.source_id not in available]
    if not missing:
        return None
    system_failures = [
        item.source_id for item in source_results if item.status == RuntimeSourceStatus.FAILED
    ]
    return DegradationContext(
        degraded=True,
        level=(
            DegradationLevel.system_failure
            if system_failures
            else DegradationLevel.partial_source
        ),
        reason="One or more planner-selected sources were not usable at execution time.",
        available_sources=available,
        missing_sources=missing,
        system_failure_sources=system_failures,
    )


def _safe_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "item"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
