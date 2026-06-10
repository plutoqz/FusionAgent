# Plan B Benchmark Protocol Quality Evaluation Freeze Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish Freeze B by making fusion output quality measurable, reproducible, task-specific, and separated from completion-only success.

**Architecture:** Add a thin benchmark protocol layer on top of the existing artifact evaluation, quality gate, adapter tests, and run evidence services. The new layer defines benchmark manifests, task-family metric profiles, independence labels, fixed baselines, machine-readable results, and Freeze B regression checks without replacing existing GIS algorithms.

**Tech Stack:** Python, Pydantic, pytest, GeoPandas/Shapely through existing adapters, existing `services.artifact_evaluation_service`, `QualityGateService`, PowerShell commands on Windows, Markdown and JSON evidence files.

---

## Entry Conditions

- Plan A Runtime Contract Freeze is implemented or actively in review.
- Deprecated algorithms remain blocked by Plan A before benchmark evidence is trusted.
- Plan B does not change KG runtime selectability, ToolRegistry registration, Validator fail-closed behavior, or Executor healing policy.
- Plan B does not add task families or remote data-source acquisition paths.

## Sources Consulted

- `docs/superpowers/specs/2026-06-10-fusionagent-reliability-roadmap-design.md`
- `services/artifact_evaluation_service.py`
- `services/quality_gate_service.py`
- `services/report_quality_service.py`
- `tests/test_artifact_evaluation_service.py`
- `tests/test_quality_gate_service.py`
- `tests/test_road_conflation_v7.py`
- `tests/test_waterways_conflation_v7.py`
- `tests/test_poi_adapter.py`
- `tests/test_building_adapter_safe.py`
- `scripts/benchmark_tiled_building.py`
- `scripts/run_benin_multisource_building_fusion.py`

## File Structure

- Create: `schemas/benchmark.py`
  - Pydantic schemas for benchmark manifests, cases, data tiers, independence labels, baselines, metric thresholds, and result rows.
- Create: `services/fusion_quality_benchmark_service.py`
  - Manifest validation, metric profile lookup, case result normalization, threshold evaluation, and summary table rendering.
- Create: `scripts/run_fusion_quality_benchmark.py`
  - CLI runner that reads a manifest, runs selected cases, writes result JSON and Markdown summaries.
- Create: `scripts/freeze_b_benchmark_protocol_check.py`
  - One-command Freeze B check for manifest validity, metric coverage, independence labels, and baseline stability.
- Create: `docs/superpowers/specs/2026-06-10-fusion-quality-benchmark-protocol.md`
  - Human-readable benchmark protocol and claim limits.
- Create: `docs/superpowers/specs/2026-06-10-freeze-b-benchmark-manifest.json`
  - Initial benchmark manifest with real, semi-real, and smoke-only synthetic cases.
- Create: `tests/test_fusion_quality_benchmark_service.py`
  - Unit tests for manifest validation, metric profiles, independence guards, and result summaries.
- Create: `tests/test_run_fusion_quality_benchmark.py`
  - CLI smoke tests using generated tiny GeoPackage fixtures.
- Create: `tests/test_freeze_b_benchmark_protocol_check.py`
  - Regression test for Freeze B check output.
- Modify: `services/artifact_evaluation_service.py`
  - Add small helper functions only if required to expose metrics already computed internally.
- Modify: `tests/test_road_conflation_v7.py`, `tests/test_waterways_conflation_v7.py`, `tests/test_poi_adapter.py`, `tests/test_building_adapter_safe.py`
  - Add algorithm-level golden metric assertions for prior real-test risk areas.

---

### Task 1: Add Benchmark Manifest Schema

**Files:**
- Create: `schemas/benchmark.py`
- Test: `tests/test_fusion_quality_benchmark_service.py`

- [ ] **Step 1: Write failing manifest schema tests**

Create `tests/test_fusion_quality_benchmark_service.py`:

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.benchmark import (
    BenchmarkCase,
    BenchmarkManifest,
    BenchmarkMetricThreshold,
)
from schemas.task_kind import TaskKind


def _case_payload(*, case_id: str = "case.building.real.benin", data_tier: str = "real") -> dict[str, object]:
    return {
        "case_id": case_id,
        "task_kind": "building",
        "data_tier": data_tier,
        "independence_label": "real_source",
        "claim_use": "quality_claim",
        "aoi": {"name": "benin-parakou", "bbox": [2.55, 9.25, 2.75, 9.45]},
        "sources": [{"source_id": "raw.osm.building", "version_token": "frozen-local"}],
        "baselines": [{"baseline_id": "fixed_adapter", "runner": "adapter_direct"}],
        "metrics": [{"metric_name": "invalid_geometry_rate", "operator": "lte", "threshold": 0.0}],
    }


def _case(*, case_id: str = "case.building.real.benin", data_tier: str = "real") -> BenchmarkCase:
    return BenchmarkCase.model_validate(_case_payload(case_id=case_id, data_tier=data_tier))


def test_benchmark_manifest_accepts_real_quality_case() -> None:
    manifest = BenchmarkManifest(
        manifest_id="freeze-b-v1",
        freeze_line="Freeze B",
        cases=[_case()],
    )

    assert manifest.case_count == 1
    assert manifest.cases[0].task_kind == TaskKind.building


def test_synthetic_case_cannot_support_quality_claim_without_independence() -> None:
    synthetic = {
        **_case_payload(case_id="case.building.synthetic.smoke", data_tier="synthetic"),
        "independence_label": "algorithm_generated",
        "claim_use": "quality_claim",
    }

    with pytest.raises(ValidationError, match="synthetic benchmark cases generated by tested algorithms"):
        BenchmarkManifest(manifest_id="bad-synthetic", freeze_line="Freeze B", cases=[synthetic])


def test_duplicate_case_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate benchmark case_id"):
        BenchmarkManifest(
            manifest_id="bad-duplicates",
            freeze_line="Freeze B",
            cases=[_case(case_id="same"), _case(case_id="same")],
        )
```

- [ ] **Step 2: Run test to confirm failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_fusion_quality_benchmark_service.py -q
```

Expected: FAIL because `schemas.benchmark` does not exist.

- [ ] **Step 3: Implement benchmark schema**

Create `schemas/benchmark.py`:

```python
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas.task_kind import TaskKind


class DataTier(str, Enum):
    real = "real"
    semi_real = "semi_real"
    synthetic = "synthetic"


class IndependenceLabel(str, Enum):
    real_source = "real_source"
    perturbation_independent = "perturbation_independent"
    algorithm_independent_synthetic = "algorithm_independent_synthetic"
    algorithm_generated = "algorithm_generated"


class BenchmarkBaseline(BaseModel):
    baseline_id: str
    runner: Literal["adapter_direct", "current_runtime", "a0", "a1", "a2a", "a2b", "a2c"]
    description: str = ""


class BenchmarkMetricThreshold(BaseModel):
    metric_name: str
    operator: Literal["eq", "lte", "lt", "gte", "gt"]
    threshold: float | int | str | bool
    interpretation: str = ""


class BenchmarkCase(BaseModel):
    model_config = ConfigDict(extra="allow")

    case_id: str
    task_kind: TaskKind
    data_tier: DataTier
    independence_label: IndependenceLabel
    claim_use: Literal["quality_claim", "robustness_claim", "smoke_only"]
    aoi: dict[str, Any]
    sources: list[dict[str, Any]] = Field(default_factory=list)
    baselines: list[BenchmarkBaseline] = Field(default_factory=list)
    metrics: list[BenchmarkMetricThreshold] = Field(default_factory=list)
    expected_artifact_roles: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_claim_boundary(self) -> "BenchmarkCase":
        if self.data_tier == DataTier.synthetic and self.claim_use == "quality_claim":
            independent = self.independence_label == IndependenceLabel.algorithm_independent_synthetic
            if not independent:
                raise ValueError(
                    "synthetic benchmark cases generated by tested algorithms must remain smoke_only"
                )
        if self.claim_use != "smoke_only" and not self.baselines:
            raise ValueError("quality or robustness cases must define at least one baseline")
        if self.claim_use != "smoke_only" and not self.metrics:
            raise ValueError("quality or robustness cases must define metric thresholds")
        return self


class BenchmarkManifest(BaseModel):
    manifest_id: str
    freeze_line: Literal["Freeze B"]
    cases: list[BenchmarkCase]
    notes: list[str] = Field(default_factory=list)

    @property
    def case_count(self) -> int:
        return len(self.cases)

    @model_validator(mode="after")
    def _validate_unique_cases(self) -> "BenchmarkManifest":
        seen: set[str] = set()
        duplicates: set[str] = set()
        for case in self.cases:
            if case.case_id in seen:
                duplicates.add(case.case_id)
            seen.add(case.case_id)
        if duplicates:
            raise ValueError(f"duplicate benchmark case_id: {sorted(duplicates)}")
        return self


class BenchmarkCaseResult(BaseModel):
    case_id: str
    task_kind: TaskKind
    baseline_id: str
    artifact_path: str
    metrics: dict[str, Any]
    threshold_results: dict[str, bool] = Field(default_factory=dict)
    accepted_for_claim: bool = False


class BenchmarkRunSummary(BaseModel):
    manifest_id: str
    result_count: int
    quality_claim_case_count: int
    smoke_only_case_count: int
    accepted_quality_claim_count: int
    results: list[BenchmarkCaseResult]
```

- [ ] **Step 4: Run manifest schema tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_fusion_quality_benchmark_service.py -q
```

Expected: PASS for the three schema tests.

- [ ] **Step 5: Commit schema**

Run:

```powershell
git add schemas/benchmark.py tests/test_fusion_quality_benchmark_service.py
git commit -m "feat: add fusion benchmark manifest schema"
```

---

### Task 2: Add Metric Profiles And Independence Guards

**Files:**
- Create: `services/fusion_quality_benchmark_service.py`
- Modify: `tests/test_fusion_quality_benchmark_service.py`

- [ ] **Step 1: Add failing metric profile tests**

Append to `tests/test_fusion_quality_benchmark_service.py`:

```python
from services.fusion_quality_benchmark_service import (
    compare_metrics_to_thresholds,
    metric_profile_for_task,
    summarize_benchmark_results,
)


def test_metric_profile_contains_task_specific_quality_metrics() -> None:
    road_profile = metric_profile_for_task(TaskKind.road)

    assert "zero_length_geometry_count" in road_profile.required_metrics
    assert "dangle_endpoint_count" in road_profile.required_metrics
    assert "network_connectivity_proxy" in road_profile.interpretations


def test_threshold_comparison_reports_each_metric() -> None:
    result = compare_metrics_to_thresholds(
        {"invalid_geometry_rate": 0.0, "duplicate_geometry_rate": 0.05},
        [
            BenchmarkMetricThreshold(metric_name="invalid_geometry_rate", operator="eq", threshold=0.0),
            BenchmarkMetricThreshold(metric_name="duplicate_geometry_rate", operator="lte", threshold=0.10),
        ],
    )

    assert result == {"invalid_geometry_rate": True, "duplicate_geometry_rate": True}


def test_summary_keeps_smoke_only_out_of_quality_claim_count() -> None:
    manifest = BenchmarkManifest(
        manifest_id="freeze-b-v1",
        freeze_line="Freeze B",
        cases=[
            _case(case_id="real-quality", data_tier="real"),
            {
                **_case_payload(case_id="synthetic-smoke", data_tier="synthetic"),
                "independence_label": "algorithm_generated",
                "claim_use": "smoke_only",
                "baselines": [],
                "metrics": [],
            },
        ],
    )

    summary = summarize_benchmark_results(manifest, [])

    assert summary.quality_claim_case_count == 1
    assert summary.smoke_only_case_count == 1
```

- [ ] **Step 2: Run test to confirm failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_fusion_quality_benchmark_service.py -q
```

Expected: FAIL because `services.fusion_quality_benchmark_service` does not exist.

- [ ] **Step 3: Implement metric profile service**

Create `services/fusion_quality_benchmark_service.py`:

```python
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
        required_metrics=("feature_count", "invalid_geometry_rate", "zero_length_geometry_count", "dangle_endpoint_count"),
        interpretations={"dangle_endpoint_count": "Flags fragmented waterway line output."},
    ),
    TaskKind.water_polygon: MetricProfile(
        task_kind=TaskKind.water_polygon,
        required_metrics=("feature_count", "invalid_geometry_rate", "sliver_polygon_count", "duplicate_geometry_rate"),
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
```

- [ ] **Step 4: Run service tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_fusion_quality_benchmark_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit metric profile service**

Run:

```powershell
git add services/fusion_quality_benchmark_service.py tests/test_fusion_quality_benchmark_service.py
git commit -m "feat: add fusion quality benchmark metric profiles"
```

---

### Task 3: Add Algorithm Golden Metric Assertions

**Files:**
- Modify: `tests/test_road_conflation_v7.py`
- Modify: `tests/test_waterways_conflation_v7.py`
- Modify: `tests/test_poi_adapter.py`
- Modify: `tests/test_building_adapter_safe.py`

- [ ] **Step 1: Add road golden metric assertion**

Append to `tests/test_road_conflation_v7.py`:

```python
from services.artifact_evaluation_service import evaluate_vector_artifact


def test_road_conflation_v7_golden_metrics_remain_stable(tmp_path: Path) -> None:
    base = gpd.GeoDataFrame(
        {"osm_id": [1], "fclass": ["primary"], "name": ["Main Road"]},
        geometry=[LineString([(0, 0), (10, 0)])],
        crs="EPSG:3857",
    )
    supplement = gpd.GeoDataFrame(
        {"id": [2], "road_class": ["secondary"]},
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
    output_path = tmp_path / "road_v7.gpkg"
    result.frame.to_file(output_path, driver="GPKG")

    metrics = evaluate_vector_artifact(output_path, required_fields=["fusion_source", "source_layer"])

    assert result.stats["base_segments"] == 1
    assert result.stats["supplement_segments"] == 1
    assert metrics["artifact_validity"] is True
    assert metrics["invalid_geometry_rate"] == 0.0
    assert metrics["zero_length_geometry_count"] == 0
```

- [ ] **Step 2: Add waterways golden metric assertion**

Append to `tests/test_waterways_conflation_v7.py`:

```python
from services.artifact_evaluation_service import evaluate_vector_artifact


def test_waterways_conflation_v7_golden_metrics_remain_stable(tmp_path: Path) -> None:
    base = gpd.GeoDataFrame(
        {"osm_id": [1], "fclass": ["river"], "name": ["Base River"]},
        geometry=[LineString([(0, 0), (10, 0)])],
        crs="EPSG:3857",
    )
    supplement = gpd.GeoDataFrame(
        {"osm_id": [101], "waterway": ["stream"], "name": ["Supplement Stream"]},
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
    output_path = tmp_path / "waterways_v7.gpkg"
    result.frame.to_file(output_path, driver="GPKG")

    metrics = evaluate_vector_artifact(output_path, required_fields=["fusion_source", "source_layer"])

    assert result.stats["base_segments"] == 1
    assert result.stats["supplement_segments"] == 1
    assert metrics["artifact_validity"] is True
    assert metrics["invalid_geometry_rate"] == 0.0
    assert set(metrics["geometry_types"]) <= {"LineString", "MultiLineString"}
```

- [ ] **Step 3: Add POI and building metric assertions**

Append to `tests/test_poi_adapter.py`:

```python
from services.artifact_evaluation_service import evaluate_vector_artifact


def test_poi_fusion_golden_metrics_remain_stable(tmp_path: Path) -> None:
    osm = gpd.GeoDataFrame(
        {"name": ["osm clinic", "osm cafe"], "category": ["clinic", "cafe"]},
        geometry=[Point(0, 0), Point(1000, 1000)],
        crs="EPSG:3857",
    )
    ref = gpd.GeoDataFrame(
        {"name": ["ref clinic", "ref school"], "category": ["clinic", "school"]},
        geometry=[Point(10, 0), Point(2500, 2500)],
        crs="EPSG:3857",
    )
    osm_shp = _write_shapefile(osm, tmp_path / "metric-osm" / "osm_poi.shp")
    ref_shp = _write_shapefile(ref, tmp_path / "metric-ref" / "ref_poi.shp")
    output_shp = run_poi_fusion(
        osm_shp=osm_shp,
        ref_shp=ref_shp,
        output_dir=tmp_path / "metric-output",
        target_crs="EPSG:3857",
    )

    metrics = evaluate_vector_artifact(output_shp, required_fields=["POI_ID", "SRC"])
    assert metrics["artifact_validity"] is True
    assert metrics["invalid_geometry_rate"] == 0.0
    assert metrics["duplicate_geometry_rate"] == 0.0
```

Append to `tests/test_building_adapter_safe.py`:

```python
from services.artifact_evaluation_service import evaluate_vector_artifact


def test_safe_building_fusion_golden_metrics_remain_stable(tmp_path: Path) -> None:
    from adapters.building_adapter import run_building_fusion_safe

    osm_path, ref_path = _build_sample_inputs(tmp_path)
    output_shp = run_building_fusion_safe(
        osm_shp=osm_path,
        ref_shp=ref_path,
        output_dir=tmp_path / "metric-output",
        target_crs="EPSG:3857",
        field_mapping={},
        debug=False,
        parameters={"match_similarity_threshold": 0.3},
    )

    metrics = evaluate_vector_artifact(output_shp, required_fields=["osm_id", "confidence"])

    assert metrics["artifact_validity"] is True
    assert metrics["invalid_geometry_rate"] == 0.0
    assert metrics["duplicate_geometry_rate"] <= 0.25
```

- [ ] **Step 4: Run algorithm regression tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_road_conflation_v7.py tests/test_waterways_conflation_v7.py tests/test_poi_adapter.py tests/test_building_adapter_safe.py -q
```

Expected: PASS. If a metric regression appears, stop and classify it in the Algorithm Trust Matrix before changing assertions.

- [ ] **Step 5: Commit golden metric tests**

Run:

```powershell
git add tests/test_road_conflation_v7.py tests/test_waterways_conflation_v7.py tests/test_poi_adapter.py tests/test_building_adapter_safe.py
git commit -m "test: add golden fusion quality metric assertions"
```

---

### Task 4: Add Benchmark Runner CLI

**Files:**
- Create: `scripts/run_fusion_quality_benchmark.py`
- Test: `tests/test_run_fusion_quality_benchmark.py`

- [ ] **Step 1: Write failing CLI smoke test**

Create `tests/test_run_fusion_quality_benchmark.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

from scripts.run_fusion_quality_benchmark import run_manifest


def test_run_manifest_summarizes_precomputed_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.gpkg"
    gpd.GeoDataFrame(
        [{"source_id": "osm", "source_feature_id": "b1", "geometry": Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])}],
        crs="EPSG:4326",
    ).to_file(artifact, driver="GPKG")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_id": "test-freeze-b",
                "freeze_line": "Freeze B",
                "cases": [
                    {
                        "case_id": "case.precomputed.building",
                        "task_kind": "building",
                        "data_tier": "real",
                        "independence_label": "real_source",
                        "claim_use": "quality_claim",
                        "aoi": {"bbox": [0, 0, 1, 1]},
                        "sources": [{"source_id": "fixture", "version_token": "test"}],
                        "baselines": [{"baseline_id": "fixed_adapter", "runner": "adapter_direct"}],
                        "metrics": [{"metric_name": "invalid_geometry_rate", "operator": "eq", "threshold": 0.0}],
                        "expected_artifact_roles": ["fused_vector"],
                        "precomputed_artifact_path": str(artifact),
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    summary = run_manifest(manifest_path, output_dir=tmp_path / "out")

    assert summary["manifest_id"] == "test-freeze-b"
    assert summary["result_count"] == 1
    assert summary["results"][0]["accepted_for_claim"] is True
```

- [ ] **Step 2: Run test to confirm failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_run_fusion_quality_benchmark.py -q
```

Expected: FAIL because `scripts.run_fusion_quality_benchmark` does not exist.

- [ ] **Step 3: Implement benchmark runner**

Create `scripts/run_fusion_quality_benchmark.py`:

```python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from schemas.benchmark import BenchmarkCaseResult, BenchmarkManifest
from services.artifact_evaluation_service import evaluate_vector_artifact
from services.fusion_quality_benchmark_service import compare_metrics_to_thresholds, summarize_benchmark_results


def run_manifest(manifest_path: Path, *, output_dir: Path) -> dict[str, Any]:
    manifest = BenchmarkManifest.model_validate_json(Path(manifest_path).read_text(encoding="utf-8"))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[BenchmarkCaseResult] = []
    for case in manifest.cases:
        artifact_path = Path(str(case.model_extra.get("precomputed_artifact_path") if case.model_extra else ""))
        if not artifact_path.exists():
            raise FileNotFoundError(f"Benchmark case {case.case_id} has no precomputed artifact at {artifact_path}")
        metrics = evaluate_vector_artifact(artifact_path, required_fields=["geometry"])
        threshold_results = compare_metrics_to_thresholds(metrics, case.metrics)
        accepted = case.claim_use != "smoke_only" and bool(threshold_results) and all(threshold_results.values())
        results.append(
            BenchmarkCaseResult(
                case_id=case.case_id,
                task_kind=case.task_kind,
                baseline_id=case.baselines[0].baseline_id if case.baselines else "smoke",
                artifact_path=str(artifact_path),
                metrics=metrics,
                threshold_results=threshold_results,
                accepted_for_claim=accepted,
            )
        )
    summary = summarize_benchmark_results(manifest, results).model_dump(mode="json")
    (output_dir / "benchmark_results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "benchmark_summary.md").write_text(_render_markdown(summary), encoding="utf-8")
    return summary


def _render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Fusion Quality Benchmark Summary",
        "",
        f"- Manifest: `{summary['manifest_id']}`",
        f"- Results: {summary['result_count']}",
        f"- Quality claim cases: {summary['quality_claim_case_count']}",
        f"- Accepted quality claim cases: {summary['accepted_quality_claim_count']}",
        "",
        "| Case | Task | Baseline | Accepted |",
        "| --- | --- | --- | --- |",
    ]
    for result in summary["results"]:
        lines.append(
            f"| {result['case_id']} | {result['task_kind']} | {result['baseline_id']} | {result['accepted_for_claim']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run FusionAgent quality benchmark manifest.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(run_manifest(Path(args.manifest), output_dir=Path(args.output_dir)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run CLI tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_run_fusion_quality_benchmark.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit runner**

Run:

```powershell
git add scripts/run_fusion_quality_benchmark.py tests/test_run_fusion_quality_benchmark.py
git commit -m "feat: add fusion quality benchmark runner"
```

---

### Task 5: Add Freeze B Manifest, Check Script, And Protocol Doc

**Files:**
- Create: `docs/superpowers/specs/2026-06-10-fusion-quality-benchmark-protocol.md`
- Create: `docs/superpowers/specs/2026-06-10-freeze-b-benchmark-manifest.json`
- Create: `scripts/freeze_b_benchmark_protocol_check.py`
- Test: `tests/test_freeze_b_benchmark_protocol_check.py`

- [ ] **Step 1: Write failing Freeze B check test**

Create `tests/test_freeze_b_benchmark_protocol_check.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from scripts.freeze_b_benchmark_protocol_check import check_freeze_b_manifest


def test_freeze_b_manifest_check_reports_required_coverage(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "manifest_id": "freeze-b-v1",
                "freeze_line": "Freeze B",
                "cases": [
                    {
                        "case_id": "case.building.real",
                        "task_kind": "building",
                        "data_tier": "real",
                        "independence_label": "real_source",
                        "claim_use": "quality_claim",
                        "aoi": {"bbox": [0, 0, 1, 1]},
                        "sources": [{"source_id": "fixture", "version_token": "test"}],
                        "baselines": [{"baseline_id": "fixed_adapter", "runner": "adapter_direct"}],
                        "metrics": [{"metric_name": "invalid_geometry_rate", "operator": "eq", "threshold": 0.0}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = check_freeze_b_manifest(manifest)

    assert report["manifest_id"] == "freeze-b-v1"
    assert report["case_count"] == 1
    assert report["synthetic_quality_claim_violations"] == []
```

- [ ] **Step 2: Run test to confirm failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_freeze_b_benchmark_protocol_check.py -q
```

Expected: FAIL because the script does not exist.

- [ ] **Step 3: Create Freeze B check script**

Create `scripts/freeze_b_benchmark_protocol_check.py`:

```python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from schemas.benchmark import BenchmarkManifest, DataTier, IndependenceLabel


def check_freeze_b_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest = BenchmarkManifest.model_validate_json(Path(manifest_path).read_text(encoding="utf-8"))
    synthetic_violations = [
        case.case_id
        for case in manifest.cases
        if case.data_tier == DataTier.synthetic
        and case.claim_use == "quality_claim"
        and case.independence_label != IndependenceLabel.algorithm_independent_synthetic
    ]
    task_coverage = sorted({case.task_kind.value for case in manifest.cases})
    report = {
        "ok": not synthetic_violations,
        "manifest_id": manifest.manifest_id,
        "case_count": manifest.case_count,
        "task_coverage": task_coverage,
        "synthetic_quality_claim_violations": synthetic_violations,
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Freeze B benchmark manifest.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-json", default="")
    args = parser.parse_args(argv)
    report = check_freeze_b_manifest(Path(args.manifest))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.output_json:
        Path(args.output_json).write_text(text, encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Create protocol doc and initial manifest**

Create `docs/superpowers/specs/2026-06-10-fusion-quality-benchmark-protocol.md` with sections:

```markdown
# Fusion Quality Benchmark Protocol

## Claim Boundary

Fusion quality claims require real or semi-real AOI cases, frozen source versions, fixed baselines, and task-specific metrics. Synthetic cases are smoke-only unless their generation mechanism is independent of the tested algorithm.

## Data Tiers

| Tier | Thesis Use | Required Label |
| --- | --- | --- |
| real | quality claim | real_source |
| semi_real | robustness or quality claim | perturbation_independent |
| synthetic | smoke by default | algorithm_independent_synthetic only if used for quality |

## Task Metrics

Building, road, waterways, water polygon, and POI metrics are evaluated through `services.artifact_evaluation_service` and interpreted by `services.fusion_quality_benchmark_service`.

## Freeze B Rule

Changing AOIs, source versions, baselines, metric definitions, or independence labels after Freeze B creates a new manifest id.
```

Create `docs/superpowers/specs/2026-06-10-freeze-b-benchmark-manifest.json`:

```json
{
  "manifest_id": "freeze-b-v1",
  "freeze_line": "Freeze B",
  "notes": [
    "Real and semi-real cases support thesis quality claims.",
    "Synthetic cases are smoke-only unless independently generated."
  ],
  "cases": [
    {
      "case_id": "case.building.real.benin",
      "task_kind": "building",
      "data_tier": "real",
      "independence_label": "real_source",
      "claim_use": "quality_claim",
      "aoi": {"name": "benin-parakou", "bbox": [2.55, 9.25, 2.75, 9.45]},
      "sources": [{"source_id": "raw.osm.building", "version_token": "freeze-b-local"}],
      "baselines": [{"baseline_id": "fixed_adapter", "runner": "adapter_direct"}],
      "metrics": [
        {"metric_name": "invalid_geometry_rate", "operator": "eq", "threshold": 0.0},
        {"metric_name": "duplicate_geometry_rate", "operator": "lte", "threshold": 0.25}
      ],
      "expected_artifact_roles": ["fused_vector"]
    },
    {
      "case_id": "case.road.semi_real.perturbed",
      "task_kind": "road",
      "data_tier": "semi_real",
      "independence_label": "perturbation_independent",
      "claim_use": "robustness_claim",
      "aoi": {"name": "road-controlled-perturbation", "bbox": [0, 0, 1, 1]},
      "sources": [{"source_id": "fixture.road.base", "version_token": "freeze-b-fixture"}],
      "baselines": [{"baseline_id": "fixed_adapter", "runner": "adapter_direct"}],
      "metrics": [
        {"metric_name": "invalid_geometry_rate", "operator": "eq", "threshold": 0.0},
        {"metric_name": "zero_length_geometry_count", "operator": "eq", "threshold": 0}
      ],
      "expected_artifact_roles": ["fused_vector"]
    },
    {
      "case_id": "case.water_polygon.semi_real.priority_merge",
      "task_kind": "water_polygon",
      "data_tier": "semi_real",
      "independence_label": "perturbation_independent",
      "claim_use": "robustness_claim",
      "aoi": {"name": "water-polygon-controlled", "bbox": [0, 0, 1, 1]},
      "sources": [{"source_id": "fixture.water.polygon", "version_token": "freeze-b-fixture"}],
      "baselines": [{"baseline_id": "fixed_adapter", "runner": "adapter_direct"}],
      "metrics": [
        {"metric_name": "invalid_geometry_rate", "operator": "eq", "threshold": 0.0},
        {"metric_name": "sliver_polygon_count", "operator": "lte", "threshold": 1}
      ],
      "expected_artifact_roles": ["fused_vector"]
    },
    {
      "case_id": "case.waterways.semi_real.line_conflation",
      "task_kind": "waterways",
      "data_tier": "semi_real",
      "independence_label": "perturbation_independent",
      "claim_use": "robustness_claim",
      "aoi": {"name": "waterways-controlled", "bbox": [0, 0, 1, 1]},
      "sources": [{"source_id": "fixture.waterways", "version_token": "freeze-b-fixture"}],
      "baselines": [{"baseline_id": "fixed_adapter", "runner": "adapter_direct"}],
      "metrics": [
        {"metric_name": "invalid_geometry_rate", "operator": "eq", "threshold": 0.0},
        {"metric_name": "zero_length_geometry_count", "operator": "eq", "threshold": 0}
      ],
      "expected_artifact_roles": ["fused_vector"]
    },
    {
      "case_id": "case.poi.semi_real.neighbor_match",
      "task_kind": "poi",
      "data_tier": "semi_real",
      "independence_label": "perturbation_independent",
      "claim_use": "robustness_claim",
      "aoi": {"name": "poi-controlled", "bbox": [0, 0, 1, 1]},
      "sources": [{"source_id": "fixture.poi", "version_token": "freeze-b-fixture"}],
      "baselines": [{"baseline_id": "fixed_adapter", "runner": "adapter_direct"}],
      "metrics": [
        {"metric_name": "invalid_geometry_rate", "operator": "eq", "threshold": 0.0},
        {"metric_name": "duplicate_geometry_rate", "operator": "lte", "threshold": 0.25}
      ],
      "expected_artifact_roles": ["fused_vector"]
    },
    {
      "case_id": "case.building.synthetic.smoke",
      "task_kind": "building",
      "data_tier": "synthetic",
      "independence_label": "algorithm_generated",
      "claim_use": "smoke_only",
      "aoi": {"name": "synthetic-smoke", "bbox": [0, 0, 0.01, 0.01]},
      "sources": [],
      "baselines": [],
      "metrics": [],
      "expected_artifact_roles": ["fused_vector"]
    }
  ]
}
```

- [ ] **Step 5: Run Freeze B check**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_freeze_b_benchmark_protocol_check.py -q
.venv\Scripts\python.exe scripts/freeze_b_benchmark_protocol_check.py --manifest docs/superpowers/specs/2026-06-10-freeze-b-benchmark-manifest.json --output-json docs/superpowers/specs/2026-06-10-freeze-b-benchmark-protocol-report.json
```

Expected: pytest PASS and script output contains `"ok": true`.

- [ ] **Step 6: Commit Freeze B protocol**

Run:

```powershell
git add docs/superpowers/specs/2026-06-10-fusion-quality-benchmark-protocol.md docs/superpowers/specs/2026-06-10-freeze-b-benchmark-manifest.json docs/superpowers/specs/2026-06-10-freeze-b-benchmark-protocol-report.json scripts/freeze_b_benchmark_protocol_check.py tests/test_freeze_b_benchmark_protocol_check.py
git commit -m "docs: freeze benchmark protocol definition"
```

---

### Task 6: Final Freeze B Verification

**Files:**
- Verify only.

- [ ] **Step 1: Run Freeze A carry-forward suite**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_runtime_contract_service.py tests/test_workflow_validator.py tests/test_toolspec_contract_enforcement.py tests/test_planner_runtime_contract.py tests/test_repair_audit.py tests/test_repair_strategy.py tests/test_freeze_a_runtime_contract_check.py -q
```

Expected: PASS. Freeze B evidence is not trusted if Freeze A guardrails are broken.

- [ ] **Step 2: Run Freeze B suite**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_fusion_quality_benchmark_service.py tests/test_run_fusion_quality_benchmark.py tests/test_freeze_b_benchmark_protocol_check.py tests/test_artifact_evaluation_service.py tests/test_quality_gate_service.py tests/test_road_conflation_v7.py tests/test_waterways_conflation_v7.py tests/test_poi_adapter.py tests/test_building_adapter_safe.py -q
```

Expected: PASS.

- [ ] **Step 3: Run no synthetic-claim scan**

Run:

```powershell
rg -n '"data_tier": "synthetic".{0,240}"claim_use": "quality_claim"|synthetic.*quality_claim' docs/superpowers/specs -S
```

Expected: no matches in Freeze B manifest unless the same case has `algorithm_independent_synthetic` and the protocol explains the independence mechanism.

- [ ] **Step 4: Commit final benchmark verification note**

Create `docs/superpowers/specs/2026-06-10-freeze-b-verification.md`:

```markdown
# Freeze B Verification

- Freeze A carry-forward suite: passed
- Freeze B benchmark suite: passed
- Synthetic quality-claim scan: passed
- Manifest: `docs/superpowers/specs/2026-06-10-freeze-b-benchmark-manifest.json`
- Protocol: `docs/superpowers/specs/2026-06-10-fusion-quality-benchmark-protocol.md`

## Thesis Draft Hook

Use this evidence in the benchmark protocol, metric rationale, and threat-to-validity sections. Fusion quality claims remain bounded to the frozen AOIs, source versions, baselines, and metric definitions.
```

Run:

```powershell
git add docs/superpowers/specs/2026-06-10-freeze-b-verification.md
git commit -m "docs: record freeze b verification"
```

---

## Self-Review Checklist

- Spec coverage:
  - Benchmark manifest schema: Tasks 1 and 5.
  - Synthetic independence guard: Tasks 1, 5, and 6.
  - Task-family metrics: Task 2.
  - Algorithm correctness and real-test regression risks: Task 3.
  - Baseline and result schema: Tasks 1 and 4.
  - Freeze B carry-forward: Task 6.
- Type consistency:
  - `BenchmarkManifest`, `BenchmarkCase`, `BenchmarkCaseResult`, and `BenchmarkRunSummary` are defined before use.
  - `TaskKind` is reused rather than duplicating task-family strings.
  - Result summaries separate `quality_claim_case_count` from `smoke_only_case_count`.
- Scope discipline:
  - This plan adds no task family, no remote data-source provider, no frontend claim, and no policy algorithm.
  - This plan measures deterministic GIS outputs; it does not claim AI performs the fusion algorithm.
