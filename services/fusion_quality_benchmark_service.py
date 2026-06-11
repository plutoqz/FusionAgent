from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from schemas.benchmark import (
    BenchmarkCaseResult,
    BenchmarkManifest,
    BenchmarkMetricThreshold,
    BenchmarkRunSummary,
)
from schemas.task_kind import TaskKind


@dataclass(frozen=True)
class MetricProfile:
    task_kind: TaskKind
    required_metrics: tuple[str, ...]
    interpretations: dict[str, str]


_PROFILES: dict[TaskKind, MetricProfile] = {
    TaskKind.building: MetricProfile(
        task_kind=TaskKind.building,
        required_metrics=(
            "feature_count",
            "invalid_geometry_rate",
            "duplicate_geometry_rate",
            "source_contribution_balance",
            "aoi_consistency",
        ),
        interpretations={
            "source_contribution_balance": "Checks whether one source dominates fused building output.",
            "duplicate_geometry_rate": "Detects duplicate footprints introduced by fusion.",
        },
    ),
    TaskKind.road: MetricProfile(
        task_kind=TaskKind.road,
        required_metrics=(
            "feature_count",
            "invalid_geometry_rate",
            "zero_length_geometry_count",
            "dangle_endpoint_count",
            "duplicate_geometry_rate",
        ),
        interpretations={
            "network_connectivity_proxy": "Use dangle endpoints and zero-length geometries as a lightweight connectivity proxy.",
        },
    ),
    TaskKind.waterways: MetricProfile(
        task_kind=TaskKind.waterways,
        required_metrics=(
            "feature_count",
            "invalid_geometry_rate",
            "zero_length_geometry_count",
            "dangle_endpoint_count",
        ),
        interpretations={"dangle_endpoint_count": "Flags fragmented waterway line output."},
    ),
    TaskKind.water_polygon: MetricProfile(
        task_kind=TaskKind.water_polygon,
        required_metrics=(
            "feature_count",
            "invalid_geometry_rate",
            "sliver_polygon_count",
            "duplicate_geometry_rate",
        ),
        interpretations={"sliver_polygon_count": "Flags polygon artifacts from overlay or priority merge."},
    ),
    TaskKind.poi: MetricProfile(
        task_kind=TaskKind.poi,
        required_metrics=("feature_count", "duplicate_geometry_rate", "source_contribution_balance"),
        interpretations={"duplicate_geometry_rate": "Flags unmerged nearby duplicate POIs."},
    ),
}


def metric_profile_for_task(task_kind: TaskKind) -> MetricProfile:
    return _PROFILES[task_kind]


def compare_metrics_to_thresholds(
    metrics: dict[str, Any],
    thresholds: list[BenchmarkMetricThreshold],
) -> dict[str, bool]:
    return {
        threshold.metric_name: _compare(
            metrics.get(threshold.metric_name),
            operator=threshold.operator,
            threshold=threshold.threshold,
        )
        for threshold in thresholds
    }


def summarize_benchmark_results(
    manifest: BenchmarkManifest,
    results: list[BenchmarkCaseResult],
) -> BenchmarkRunSummary:
    quality_cases = [case for case in manifest.cases if case.claim_use == "quality_claim"]
    smoke_cases = [case for case in manifest.cases if case.claim_use == "smoke_only"]
    return BenchmarkRunSummary(
        manifest_id=manifest.manifest_id,
        result_count=len(results),
        quality_claim_case_count=len(quality_cases),
        smoke_only_case_count=len(smoke_cases),
        accepted_quality_claim_count=sum(1 for result in results if result.accepted_for_claim),
        results=results,
    )


def _compare(actual: Any, *, operator: str, threshold: Any) -> bool:
    if operator == "eq":
        return actual == threshold
    if actual is None:
        return False
    actual_value = float(actual)
    threshold_value = float(threshold)
    if operator == "lte":
        return actual_value <= threshold_value
    if operator == "lt":
        return actual_value < threshold_value
    if operator == "gte":
        return actual_value >= threshold_value
    if operator == "gt":
        return actual_value > threshold_value
    return False
