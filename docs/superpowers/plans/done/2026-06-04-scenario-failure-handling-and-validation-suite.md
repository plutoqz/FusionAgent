# Scenario Failure Handling And Engineering Validation Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Prefer `gpt-5.5` workers. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `partial` operationally useful by requiring failed child tasks to enter structured failure handling, then add an engineering validation suite with small, medium, and bounded-large AOI scenarios for Africa and Pakistan.

**Architecture:** Preserve existing scenario phases. Add child-level failure records with recovery state, retry schedule, attempted sources, and next action. Scenario `partial` means accepted successful outputs plus handled failed children. Validation manifests run through existing scenario and runtime services with fixture-backed or local-preload-friendly tests.

**Tech Stack:** Python, pytest, existing `ScenarioRunService`, `RunRecoveryService`, `RunRecoveryExecutor`, `UnattendedRunMonitorService`, `TilePartitionService`, and Track B large area services.

---

## Phase 0: Documentation Discovery

### Sources Consulted

- `services/scenario_run_service.py`
  - `_phase_from_child_results()` already returns `partial` for mixed success/failure or degraded success.
  - Child exceptions write `child_runs/<task>-failed.json`, but no scenario-level failure handling summary exists.
- `services/run_recovery_service.py`
  - Existing recoverable run categories and `build_recovery_hint()`.
- `services/run_recovery_executor.py`
  - Existing stale run recovery executor.
- `services/unattended_run_monitor_service.py`
  - Existing readiness classifier.
- `services/tile_partition_service.py`
  - Existing bbox partitioning.
- `services/large_area_runtime_service.py`
  - Existing tile run and stitch workflow.
- `services/track_b_national_scale_service.py`
  - Existing bounded large AOI and national-scale style runtime.
- `tests/test_scenario_run_service.py`
  - Existing partial/degraded/full-failed scenario tests.
- `tests/test_run_recovery_service.py`
  - Existing recovery hint tests.
- `tests/test_tile_partition_service.py`, `tests/test_large_area_runtime_service.py`, `tests/test_track_b_national_scale_service.py`
  - Existing split/merge samples.

### Allowed APIs

- Keep `ScenarioPhase.partial`.
- Use existing recovery hint service for run-level action classification.
- Add scenario-level failure records under summary and separate `failed_children.json`.
- Add validation manifests under `tests/fixtures/engineering_validation/` or `docs/superpowers/validation/`.

### Anti-Pattern Guards

- Do not add `ScenarioPhase.recovering`.
- Do not hide successful outputs when another child fails.
- Do not make live downloads mandatory in unit tests.
- Do not choose unbounded national AOIs for routine tests.

## File Structure

- Create: `schemas/scenario_failure.py`
- Create: `services/scenario_failure_handler_service.py`
- Modify: `services/scenario_run_service.py`
- Create: `docs/superpowers/validation/engineering_validation_matrix.yaml`
- Create: `scripts/run_engineering_validation.py`
- Test: `tests/test_scenario_failure_handler_service.py`
- Test: `tests/test_scenario_run_service.py`
- Test: `tests/test_engineering_validation_matrix.py`
- Test: `tests/test_tile_partition_service.py`
- Test: `tests/test_large_area_runtime_service.py`

---

### Task 1: Add Scenario Failure Handler Service

**Files:**
- Create: `schemas/scenario_failure.py`
- Create: `services/scenario_failure_handler_service.py`
- Test: `tests/test_scenario_failure_handler_service.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_scenario_failure_handler_service.py`:

```python
from __future__ import annotations

from services.scenario_failure_handler_service import ScenarioFailureHandlerService


def test_failure_handler_builds_recoverable_download_failure_record() -> None:
    record = ScenarioFailureHandlerService().build_child_failure_record(
        scenario_id="scenario-1",
        child_result={
            "run_id": "run-poi",
            "job_type": "poi",
            "task_kind": "poi",
            "task_family": "poi",
            "phase": "failed",
            "error": "SOURCE_DOWNLOAD_FAILED: timeout",
        },
        recovery_hint={
            "recoverable": True,
            "recovery_action": "retry_source_download",
            "operator_action": "retry",
        },
    )

    assert record.scenario_id == "scenario-1"
    assert record.task_kind == "poi"
    assert record.recovery_state == "retry_scheduled"
    assert record.next_action == "retry_source_download"
    assert record.recoverable is True


def test_failure_handler_marks_manual_review_when_not_recoverable() -> None:
    record = ScenarioFailureHandlerService().build_child_failure_record(
        scenario_id="scenario-1",
        child_result={
            "run_id": "run-waterways",
            "job_type": "water",
            "task_kind": "waterways",
            "task_family": "water",
            "phase": "failed",
            "error": "schema mismatch",
        },
        recovery_hint={"recoverable": False, "recovery_action": "none", "operator_action": "manual_review"},
    )

    assert record.recovery_state == "blocked"
    assert record.next_action == "manual_review"
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_scenario_failure_handler_service.py -q
```

Expected: FAIL because service does not exist.

- [ ] **Step 3: Implement schemas**

Create `schemas/scenario_failure.py`:

```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ScenarioChildFailureRecord(BaseModel):
    scenario_id: str
    run_id: str | None = None
    job_type: str
    task_kind: str
    task_family: str
    error: str | None = None
    recoverable: bool = False
    recovery_state: str
    next_action: str
    retry_after_seconds: int | None = None
    attempted_sources: list[dict[str, Any]] = Field(default_factory=list)
```

- [ ] **Step 4: Implement service**

Create `services/scenario_failure_handler_service.py`:

```python
from __future__ import annotations

from schemas.scenario_failure import ScenarioChildFailureRecord


class ScenarioFailureHandlerService:
    def build_child_failure_record(
        self,
        *,
        scenario_id: str,
        child_result: dict[str, object],
        recovery_hint: dict[str, object],
    ) -> ScenarioChildFailureRecord:
        recoverable = bool(recovery_hint.get("recoverable"))
        action = str(recovery_hint.get("recovery_action") or "")
        operator_action = str(recovery_hint.get("operator_action") or "")
        if recoverable and action not in {"", "none"}:
            state = "retry_scheduled"
            next_action = action
        elif operator_action:
            state = "blocked"
            next_action = operator_action
        else:
            state = "exhausted"
            next_action = "manual_review"
        return ScenarioChildFailureRecord(
            scenario_id=scenario_id,
            run_id=child_result.get("run_id"),
            job_type=str(child_result.get("job_type") or ""),
            task_kind=str(child_result.get("task_kind") or child_result.get("job_type") or ""),
            task_family=str(child_result.get("task_family") or child_result.get("job_type") or ""),
            error=str(child_result.get("error") or ""),
            recoverable=recoverable,
            recovery_state=state,
            next_action=next_action,
            retry_after_seconds=_retry_after_seconds(child_result),
            attempted_sources=_attempted_sources(child_result),
        )


def _retry_after_seconds(child_result: dict[str, object]) -> int | None:
    for event in child_result.get("audit_events") or []:
        details = getattr(event, "details", {})
        for attempt in details.get("provider_attempts", []) if isinstance(details, dict) else []:
            if isinstance(attempt, dict) and attempt.get("next_retry_after_seconds") is not None:
                return int(attempt["next_retry_after_seconds"])
    return None


def _attempted_sources(child_result: dict[str, object]) -> list[dict[str, object]]:
    attempts = []
    for event in child_result.get("audit_events") or []:
        details = getattr(event, "details", {})
        if isinstance(details, dict):
            attempts.extend(item for item in details.get("provider_attempts", []) if isinstance(item, dict))
    return attempts
```

- [ ] **Step 5: Verify and commit**

```powershell
py -3.13 -m pytest tests/test_scenario_failure_handler_service.py -q
git add schemas/scenario_failure.py services/scenario_failure_handler_service.py tests/test_scenario_failure_handler_service.py
git commit -m "feat: add scenario child failure handler"
```

### Task 2: Require Handled Failed Children For Partial Scenarios

**Files:**
- Modify: `services/scenario_run_service.py`
- Test: `tests/test_scenario_run_service.py`

- [ ] **Step 1: Add failing partial failure summary test**

In `tests/test_scenario_run_service.py`, add:

```python
def test_partial_scenario_records_failed_child_recovery_state(tmp_path, monkeypatch):
    monkeypatch.setattr(ScenarioRunService, "CHILD_RUN_POLL_INTERVAL_SECONDS", 0)
    service = ScenarioRunService(agent_run_service=_OneSucceededOneFailedAgentRunService(tmp_path))

    response = service.create_scenario_run(
        ScenarioRunRequest(
            scenario_name="Karachi flood",
            trigger_content="巴基斯坦卡拉奇市发生洪涝灾害，请执行地理空间矢量数据融合。",
            disaster_type="flood",
            spatial_extent="Karachi, Pakistan",
            output_root=str(tmp_path / "scenarios"),
        )
    )

    summary = json.loads((Path(response.output_dir) / "scenario_summary.json").read_text(encoding="utf-8"))

    assert response.phase == ScenarioPhase.partial
    assert summary["failed_children"]
    assert summary["failed_children"][0]["recovery_state"] in {"retry_scheduled", "blocked", "exhausted"}
    assert (Path(response.output_dir) / "failed_children.json").exists()
    assert summary["final_outputs"]
```

Add this fake service near `_FailedDegradedAgentRunService`:

```python
class _OneSucceededOneFailedAgentRunService(_FakeAgentRunService):
    def create_run(self, *, request, osm_zip_name, osm_zip_bytes, ref_zip_name, ref_zip_bytes):
        status = super().create_run(
            request=request,
            osm_zip_name=osm_zip_name,
            osm_zip_bytes=osm_zip_bytes,
            ref_zip_name=ref_zip_name,
            ref_zip_bytes=ref_zip_bytes,
        )
        task_key = _task_key_from_request(request)
        if task_key != "poi":
            return status
        failed = status.model_copy(
            update={
                "phase": RunPhase.failed,
                "progress": 80,
                "error": "SOURCE_DOWNLOAD_FAILED: timeout",
                "failure_summary": "SOURCE_DOWNLOAD_FAILED: timeout",
                "finished_at": "2026-06-03T00:00:03+00:00",
            }
        )
        self.statuses[status.run_id] = failed
        self.artifacts.pop(status.run_id, None)
        return failed
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_scenario_run_service.py::test_partial_scenario_records_failed_child_recovery_state -q
```

Expected: FAIL because no `failed_children` summary exists.

- [ ] **Step 3: Integrate handler**

In `services/scenario_run_service.py`, import:

```python
from services.run_recovery_service import build_recovery_hint
from services.scenario_failure_handler_service import ScenarioFailureHandlerService
```

Add `self.failure_handler = ScenarioFailureHandlerService()` in `ScenarioRunService.__init__`.

In `_build_summary()`, compute:

```python
failed_children = [
    self.failure_handler.build_child_failure_record(
        scenario_id=scenario_id,
        child_result=result,
        recovery_hint=build_recovery_hint(_run_payload_for_recovery(result)),
    ).model_dump(mode="json")
    for result in child_results
    if str(result.get("phase")) in {RunPhase.failed.value, ScenarioPhase.failed.value}
]
```

Add `"failed_children": failed_children` to the summary.

In `_write_summary_files()`, add:

```python
"failed_children.json": summary.get("failed_children", []),
```

- [ ] **Step 4: Verify**

```powershell
py -3.13 -m pytest tests/test_scenario_failure_handler_service.py tests/test_scenario_run_service.py tests/test_run_recovery_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add services/scenario_run_service.py tests/test_scenario_run_service.py
git commit -m "feat: record handled failed scenario children"
```

### Task 3: Add Engineering Validation Matrix

**Files:**
- Create: `docs/superpowers/validation/engineering_validation_matrix.yaml`
- Create: `tests/test_engineering_validation_matrix.py`

- [ ] **Step 1: Create matrix test first**

Create `tests/test_engineering_validation_matrix.py`:

```python
from __future__ import annotations

from pathlib import Path

import yaml


MATRIX = Path("docs/superpowers/validation/engineering_validation_matrix.yaml")


def test_engineering_validation_matrix_has_required_aoi_classes_and_regions() -> None:
    payload = yaml.safe_load(MATRIX.read_text(encoding="utf-8"))
    cases = payload["cases"]

    assert {case["aoi_class"] for case in cases} == {"small_city", "medium_region", "bounded_large"}
    assert {"pakistan", "africa"} <= {case["region_group"] for case in cases}
    for case in cases:
        assert case["default_task_bundle"] == ["building", "road", "water_polygon", "waterways", "poi"]
        assert case["output_format"] == "GPKG"
        assert "bbox" in case or "spatial_extent" in case
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_engineering_validation_matrix.py -q
```

Expected: FAIL because matrix file does not exist.

- [ ] **Step 3: Add matrix**

Create `docs/superpowers/validation/engineering_validation_matrix.yaml`:

```yaml
version: 2026-06-04.v1
cases:
  - case_id: pakistan_karachi_small_city
    region_group: pakistan
    aoi_class: small_city
    scenario_name: Karachi flood
    disaster_type: flood
    spatial_extent: "bbox(66.95,24.78,67.20,25.02)"
    default_task_bundle: [building, road, water_polygon, waterways, poi]
    output_format: GPKG
    purpose: "Validate unattended small-city full mission expansion and source materialization."
  - case_id: africa_nairobi_small_city
    region_group: africa
    aoi_class: small_city
    scenario_name: Nairobi flood
    disaster_type: flood
    spatial_extent: "bbox(36.65,-1.45,37.10,-1.10)"
    default_task_bundle: [building, road, water_polygon, waterways, poi]
    output_format: GPKG
    purpose: "Validate Africa AOI source materialization and quality reports."
  - case_id: pakistan_sindh_medium_region
    region_group: pakistan
    aoi_class: medium_region
    scenario_name: Sindh flood bounded region
    disaster_type: flood
    spatial_extent: "bbox(67.0,24.0,68.0,25.5)"
    default_task_bundle: [building, road, water_polygon, waterways, poi]
    output_format: GPKG
    purpose: "Validate larger downloads, clipping, and retry evidence."
  - case_id: africa_kenya_bounded_large
    region_group: africa
    aoi_class: bounded_large
    scenario_name: Kenya bounded flood validation
    disaster_type: flood
    spatial_extent: "bbox(36.0,-2.0,38.0,0.0)"
    default_task_bundle: [building, road, water_polygon, waterways, poi]
    output_format: GPKG
    purpose: "Validate split, parallel tile processing, merge, and quality aggregation."
```

- [ ] **Step 4: Verify**

```powershell
py -3.13 -m pytest tests/test_engineering_validation_matrix.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add docs/superpowers/validation/engineering_validation_matrix.yaml tests/test_engineering_validation_matrix.py
git commit -m "test: add engineering validation matrix"
```

### Task 4: Add Validation Runner Skeleton

**Files:**
- Create: `scripts/run_engineering_validation.py`
- Test: `tests/test_engineering_validation_matrix.py`

- [ ] **Step 1: Add runner dry-run test**

Append:

```python
def test_engineering_validation_runner_dry_run_lists_cases(capsys) -> None:
    from scripts.run_engineering_validation import main

    exit_code = main(["--matrix", str(MATRIX), "--dry-run"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "pakistan_karachi_small_city" in captured.out
    assert "africa_kenya_bounded_large" in captured.out
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_engineering_validation_matrix.py::test_engineering_validation_runner_dry_run_lists_cases -q
```

Expected: FAIL because runner does not exist.

- [ ] **Step 3: Implement dry-run runner**

Create `scripts/run_engineering_validation.py`:

```python
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import yaml


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", default="docs/superpowers/validation/engineering_validation_matrix.yaml")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    payload = yaml.safe_load(Path(args.matrix).read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    for case in cases:
        print(f"{case['case_id']}: {case['scenario_name']} [{case['aoi_class']}]")
    if args.dry_run:
        return 0
    raise SystemExit("Non-dry-run execution is implemented in the next validation runner slice.")


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Verify and commit**

```powershell
py -3.13 -m pytest tests/test_engineering_validation_matrix.py -q
git add scripts/run_engineering_validation.py tests/test_engineering_validation_matrix.py
git commit -m "feat: add engineering validation dry-run runner"
```

### Task 5: Final Verification

- [ ] **Step 1: Focused tests**

```powershell
py -3.13 -m pytest tests/test_scenario_failure_handler_service.py tests/test_scenario_run_service.py tests/test_run_recovery_service.py tests/test_engineering_validation_matrix.py tests/test_tile_partition_service.py tests/test_large_area_runtime_service.py -q
```

Expected: PASS.

- [ ] **Step 2: Anti-pattern scans**

```powershell
rg -n "ScenarioPhase\\.recovering|recovering =" schemas services tests
```

Expected: no output.

```powershell
rg -n "failed_children|recovery_state|retry_scheduled" services tests docs/superpowers/validation
```

Expected: scenario failure records are present.

- [ ] **Step 3: Commit verification fixes if needed**

```powershell
git add schemas/scenario_failure.py services/scenario_failure_handler_service.py services/scenario_run_service.py docs/superpowers/validation/engineering_validation_matrix.yaml scripts/run_engineering_validation.py tests/test_scenario_failure_handler_service.py tests/test_scenario_run_service.py tests/test_engineering_validation_matrix.py
git commit -m "test: lock scenario failure handling validation"
```

## Self-Review

- `partial` semantics remain unchanged at scenario phase level.
- Failed child records become explicit and inspectable.
- Successful child outputs remain published.
- Validation matrix covers Pakistan and Africa across small, medium, and bounded-large AOIs.
