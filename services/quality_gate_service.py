from __future__ import annotations

from pathlib import Path

from schemas.quality_gate import QualityGateReport
from schemas.task_kind import TaskKind
from services.artifact_evaluation_service import evaluate_vector_artifact

_EXPECTED_GEOMETRIES = {
    TaskKind.building: {"Polygon", "MultiPolygon"},
    TaskKind.road: {"LineString", "MultiLineString"},
    TaskKind.water_polygon: {"Polygon", "MultiPolygon"},
    TaskKind.waterways: {"LineString", "MultiLineString"},
    TaskKind.poi: {"Point", "MultiPoint"},
}


class QualityGateService:
    def evaluate(
        self,
        *,
        artifact_path: Path,
        task_kind: TaskKind,
        required_fields: list[str],
        requested_bbox=None,
        component_coverage: dict[str, object] | None = None,
    ) -> QualityGateReport:
        metrics = evaluate_vector_artifact(
            Path(artifact_path),
            required_fields=required_fields,
            requested_bbox=requested_bbox,
        )
        checks = {
            "readable": {"passed": "error" not in metrics},
            "non_empty": {"passed": int(metrics.get("feature_count") or 0) > 0},
            "required_fields": {"passed": not metrics.get("missing_fields")},
            "geometry_type": {
                "passed": bool(set(metrics.get("geometry_types") or []) & _EXPECTED_GEOMETRIES[task_kind]),
                "expected": sorted(_EXPECTED_GEOMETRIES[task_kind]),
                "actual": metrics.get("geometry_types") or [],
            },
            "aoi_intersection": {
                "passed": bool(metrics.get("aoi_consistency", {}).get("artifact_intersects_aoi", requested_bbox is None)),
            },
            "source_lineage": {
                "passed": "source_id" in required_fields and "source_id" not in metrics.get("missing_fields", []),
            },
            "multi_source_lineage": {
                "passed": _multi_source_lineage_available(component_coverage or {}),
            },
        }
        failure_reasons = [name for name, check in checks.items() if not check["passed"]]
        return QualityGateReport(
            accepted=not failure_reasons,
            task_kind=task_kind,
            artifact_path=str(artifact_path),
            checks=checks,
            metrics=metrics,
            failure_reasons=failure_reasons,
        )


def _multi_source_lineage_available(component_coverage: dict[str, object]) -> bool:
    available = []
    for source_id, payload in component_coverage.items():
        if isinstance(payload, dict):
            count = payload.get("feature_count")
            status = str(payload.get("coverage_status") or "")
            if status in {"available", "unknown_until_materialization"} or (count is not None and int(count) > 0):
                available.append(source_id)
    return len(set(available)) >= 2
