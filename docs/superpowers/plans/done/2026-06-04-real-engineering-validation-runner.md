# Real Engineering Validation Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Prefer `gpt-5.5` workers. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `scripts/run_engineering_validation.py` from a dry-run case lister into a real unattended end-to-end validation runner that executes scenario cases, records a validation session, and emits a pass/fail matrix suitable for regression decisions.

**Architecture:** Reuse the existing scenario API and harness patterns. The runner loads the engineering validation matrix, filters selected cases, creates scenario runs through `/api/v2/scenario-runs`, reads each `scenario_summary.json`, evaluates expected task, quality, failure, and artifact evidence, then writes a validation session package under a deterministic session output directory.

**Tech Stack:** Python, pytest, httpx or stdlib HTTP, existing `ScenarioRunRequest`, `ScenarioRunResponse`, `scenario_eval_harness.py`, `scripts/eval_harness.py`, `docs/superpowers/validation/engineering_validation_matrix.yaml`, and the evidence lifecycle contract from `2026-06-04-artifact-evidence-lifecycle-contract.md`.

---

## Phase 0: Documentation Discovery

### Sources Consulted

- `scripts/run_engineering_validation.py`
  - Currently loads `docs/superpowers/validation/engineering_validation_matrix.yaml`, prints cases, returns on `--dry-run`, and raises for non-dry-run.
- `scripts/scenario_eval_harness.py`
  - Provides `HttpScenarioClient`, `run_manifest_cases()`, summary loading, observed evidence extraction, and pass/fail summary writing.
- `scripts/eval_harness.py`
  - Provides runtime metadata patterns: git commit detection, runtime environment fetch, manifest case filtering, and JSON summary output.
- `docs/superpowers/validation/engineering_validation_matrix.yaml`
  - Current matrix has 4 cases with `case_id`, `region_group`, `aoi_class`, `scenario_name`, `disaster_type`, `spatial_extent`, `default_task_bundle`, and `output_format`.
- `schemas/scenario.py`
  - Defines `ScenarioRunRequest`, `ScenarioRunResponse`, `ScenarioPhase`, and request metadata fields.
- `services/scenario_run_service.py`
  - Scenario evidence is written to `scenario_summary.json` and sibling evidence files under the scenario output directory.
- `docs/no-ui-agent-operations.md`
  - Scenario harness and real-data benchmark commands already use explicit output roots and output JSON summaries.

### Allowed APIs

- Use `POST /api/v2/scenario-runs` to create scenario runs.
- Use returned `ScenarioRunResponse.output_dir` and `scenario_summary.json` as the canonical scenario evidence entry.
- Use explicit runner output root; default to `runs/engineering-validation/<session_id>` when no output root is provided.
- Use `--case` multiple times for selected case IDs.
- Use `--dry-run` for listing without executing.

### Anti-Pattern Guards

- Do not keep non-dry-run as a deliberate `SystemExit`.
- Do not infer pass/fail only from HTTP success.
- Do not hide partial scenarios; record them with failed child details.
- Do not write validation outputs into `tmp/eval/` unless the operator explicitly asks for that output path.
- Do not require live downloads in unit tests; use fake clients and fixture summaries.

## File Structure

- Modify: `scripts/run_engineering_validation.py`
- Create: `schemas/engineering_validation.py`
- Modify: `docs/superpowers/validation/engineering_validation_matrix.yaml`
- Modify: `docs/no-ui-agent-operations.md`
- Test: `tests/test_engineering_validation_runner.py`
- Test: `tests/test_engineering_validation_matrix.py`

---

### Task 1: Add Matrix And Result Schemas

**Files:**
- Create: `schemas/engineering_validation.py`
- Test: `tests/test_engineering_validation_runner.py`

- [ ] **Step 1: Write failing schema tests**

Create `tests/test_engineering_validation_runner.py` with:

```python
from __future__ import annotations

from schemas.engineering_validation import EngineeringValidationCase, EngineeringValidationCaseResult


def test_engineering_validation_case_requires_core_fields() -> None:
    case = EngineeringValidationCase(
        case_id="pakistan_karachi_small_city",
        region_group="pakistan",
        aoi_class="small_city",
        scenario_name="Karachi flood",
        disaster_type="flood",
        spatial_extent="bbox(66.95,24.78,67.20,25.02)",
        default_task_bundle=["building", "road"],
        output_format="GPKG",
    )

    assert case.case_id == "pakistan_karachi_small_city"
    assert case.expected_min_succeeded_children == 1


def test_engineering_validation_result_serializes_failure_reasons() -> None:
    result = EngineeringValidationCaseResult(
        case_id="case-1",
        passed=False,
        phase="partial",
        failure_reasons=["quality_failed"],
    )

    assert result.model_dump(mode="json")["failure_reasons"] == ["quality_failed"]
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_engineering_validation_runner.py::test_engineering_validation_case_requires_core_fields tests/test_engineering_validation_runner.py::test_engineering_validation_result_serializes_failure_reasons -q
```

Expected: FAIL because `schemas.engineering_validation` does not exist.

- [ ] **Step 3: Implement schemas**

Create `schemas/engineering_validation.py`:

```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EngineeringValidationCase(BaseModel):
    case_id: str
    region_group: str
    aoi_class: str
    scenario_name: str
    disaster_type: str
    spatial_extent: str
    default_task_bundle: list[str] = Field(default_factory=list)
    output_format: str = "GPKG"
    purpose: str = ""
    expected_phase: list[str] = Field(default_factory=lambda: ["succeeded", "partial"])
    expected_min_succeeded_children: int = 1
    expected_required_tasks: list[str] = Field(default_factory=list)
    quality_policy_id: str | None = None
    timeout_sec: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EngineeringValidationCaseResult(BaseModel):
    case_id: str
    passed: bool
    phase: str
    scenario_id: str | None = None
    output_dir: str | None = None
    summary_path: str | None = None
    failure_reasons: list[str] = Field(default_factory=list)
    observed: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class EngineeringValidationSummary(BaseModel):
    session_id: str
    matrix_path: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    results: list[EngineeringValidationCaseResult] = Field(default_factory=list)
    output_root: str
    metadata: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 4: Verify**

```powershell
py -3.13 -m pytest tests/test_engineering_validation_runner.py::test_engineering_validation_case_requires_core_fields tests/test_engineering_validation_runner.py::test_engineering_validation_result_serializes_failure_reasons -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add schemas/engineering_validation.py tests/test_engineering_validation_runner.py
git commit -m "feat: add engineering validation schemas"
```

### Task 2: Load, Filter, And Dry-Run Matrix Cases

**Files:**
- Modify: `scripts/run_engineering_validation.py`
- Test: `tests/test_engineering_validation_runner.py`
- Test: `tests/test_engineering_validation_matrix.py`

- [ ] **Step 1: Add failing loader tests**

Append:

```python
import json
from pathlib import Path

from scripts.run_engineering_validation import load_matrix_cases


def test_load_matrix_cases_filters_by_case_id(tmp_path: Path) -> None:
    matrix = tmp_path / "matrix.json"
    matrix.write_text(
        json.dumps(
            {
                "version": "test",
                "cases": [
                    {
                        "case_id": "case-a",
                        "region_group": "africa",
                        "aoi_class": "small_city",
                        "scenario_name": "A",
                        "disaster_type": "flood",
                        "spatial_extent": "bbox(0,0,1,1)",
                        "default_task_bundle": ["building"],
                    },
                    {
                        "case_id": "case-b",
                        "region_group": "pakistan",
                        "aoi_class": "medium_region",
                        "scenario_name": "B",
                        "disaster_type": "flood",
                        "spatial_extent": "bbox(1,1,2,2)",
                        "default_task_bundle": ["road"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    cases = load_matrix_cases(matrix, selected_case_ids=["case-b"])

    assert [case.case_id for case in cases] == ["case-b"]
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_engineering_validation_runner.py::test_load_matrix_cases_filters_by_case_id -q
```

Expected: FAIL because `load_matrix_cases()` does not exist.

- [ ] **Step 3: Implement matrix loader**

In `scripts/run_engineering_validation.py`:

```python
from schemas.engineering_validation import EngineeringValidationCase


def load_matrix_cases(matrix_path: Path, selected_case_ids: list[str] | None = None) -> list[EngineeringValidationCase]:
    payload = json.loads(Path(matrix_path).read_text(encoding="utf-8"))
    raw_cases = payload.get("cases", [])
    selected = set(selected_case_ids or [])
    cases = [EngineeringValidationCase.model_validate(case) for case in raw_cases if isinstance(case, dict)]
    if selected:
        cases = [case for case in cases if case.case_id in selected]
    return cases
```

Update CLI parser:

```python
parser.add_argument("--case", action="append", default=[], help="Case id to run. Can be passed multiple times.")
```

Use `load_matrix_cases()` for dry-run printing.

- [ ] **Step 4: Add matrix contract checks**

Update `tests/test_engineering_validation_matrix.py` to assert every case has:

```python
expected_min_succeeded_children
expected_required_tasks
quality_policy_id
```

Then extend `docs/superpowers/validation/engineering_validation_matrix.yaml` cases with those fields. Keep the file JSON-compatible because the current runner uses `json.loads()`.

- [ ] **Step 5: Verify and commit**

```powershell
py -3.13 -m pytest tests/test_engineering_validation_runner.py tests/test_engineering_validation_matrix.py -q
python scripts/run_engineering_validation.py --dry-run --case africa_nairobi_small_city
git add scripts/run_engineering_validation.py schemas/engineering_validation.py docs/superpowers/validation/engineering_validation_matrix.yaml tests/test_engineering_validation_runner.py tests/test_engineering_validation_matrix.py
git commit -m "feat: load engineering validation matrix cases"
```

### Task 3: Execute Scenario Cases Through API Client

**Files:**
- Modify: `scripts/run_engineering_validation.py`
- Test: `tests/test_engineering_validation_runner.py`

- [ ] **Step 1: Add fake-client execution tests**

Append:

```python
from schemas.scenario import ScenarioPhase, ScenarioRunResponse
from scripts.run_engineering_validation import run_validation_cases


class FakeScenarioClient:
    def create_scenario_run(self, request):
        return ScenarioRunResponse(
            scenario_id="scenario-1",
            phase=ScenarioPhase.succeeded,
            output_dir=str(self.output_dir),
            child_run_ids=["run-a"],
        )


def test_run_validation_cases_reads_summary_and_marks_passed(tmp_path: Path) -> None:
    output_dir = tmp_path / "scenario-1"
    output_dir.mkdir()
    (output_dir / "scenario_summary.json").write_text(
        json.dumps(
            {
                "scenario_id": "scenario-1",
                "phase": "succeeded",
                "child_runs": [{"run_id": "run-a", "task_kind": "building", "phase": "succeeded"}],
                "quality": {"accepted": True, "failed_children_count": 0},
                "failed_children": [],
            }
        ),
        encoding="utf-8",
    )
    client = FakeScenarioClient()
    client.output_dir = output_dir
    case = EngineeringValidationCase(
        case_id="case-a",
        region_group="africa",
        aoi_class="small_city",
        scenario_name="A",
        disaster_type="flood",
        spatial_extent="bbox(0,0,1,1)",
        default_task_bundle=["building"],
        expected_required_tasks=["building"],
    )

    results = run_validation_cases([case], output_root=str(tmp_path), client=client)

    assert results[0].passed is True
    assert results[0].scenario_id == "scenario-1"
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_engineering_validation_runner.py::test_run_validation_cases_reads_summary_and_marks_passed -q
```

Expected: FAIL because `run_validation_cases()` does not exist.

- [ ] **Step 3: Implement `HttpScenarioClient` and request builder**

Copy the `HttpScenarioClient` pattern from `scripts/scenario_eval_harness.py`, adjusted for this runner. Add:

```python
def case_to_scenario_request(case: EngineeringValidationCase, *, output_root: str | None) -> ScenarioRunRequest:
    return ScenarioRunRequest(
        scenario_name=case.scenario_name,
        trigger_content=f"{case.scenario_name}: {case.disaster_type} validation for {case.spatial_extent}",
        disaster_type=case.disaster_type,
        spatial_extent=case.spatial_extent,
        output_root=output_root,
        metadata={
            "case_id": case.case_id,
            "region_group": case.region_group,
            "aoi_class": case.aoi_class,
            "default_task_bundle": case.default_task_bundle,
            "quality_policy_id": case.quality_policy_id,
            "validation_runner": "engineering_validation",
        },
    )
```

Use the actual `ScenarioRunRequest` signature from `schemas/scenario.py`. If required fields differ, copy the existing construction style from `services/scenario_manifest_service.py`.

- [ ] **Step 4: Implement pass/fail evaluator**

Add:

```python
def evaluate_case_summary(case: EngineeringValidationCase, summary: dict[str, object]) -> tuple[bool, list[str], dict[str, object]]:
    child_runs = summary.get("child_runs") if isinstance(summary.get("child_runs"), list) else []
    succeeded_children = [item for item in child_runs if isinstance(item, dict) and item.get("phase") == "succeeded"]
    observed_tasks = sorted({str(item.get("task_kind") or item.get("job_type") or "") for item in child_runs if isinstance(item, dict)})
    failures = []
    phase = str(summary.get("phase") or "")
    if phase not in case.expected_phase:
        failures.append(f"phase expected one of {case.expected_phase}, got {phase}")
    if len(succeeded_children) < case.expected_min_succeeded_children:
        failures.append(f"succeeded children expected at least {case.expected_min_succeeded_children}, got {len(succeeded_children)}")
    missing_tasks = [task for task in case.expected_required_tasks if task not in observed_tasks]
    if missing_tasks:
        failures.append(f"missing required tasks: {missing_tasks}")
    quality = summary.get("quality") if isinstance(summary.get("quality"), dict) else {}
    failed_children = summary.get("failed_children") if isinstance(summary.get("failed_children"), list) else []
    observed = {
        "phase": phase,
        "observed_tasks": observed_tasks,
        "succeeded_child_count": len(succeeded_children),
        "failed_child_count": len(failed_children),
        "quality": quality,
    }
    return not failures, failures, observed
```

- [ ] **Step 5: Verify and commit**

```powershell
py -3.13 -m pytest tests/test_engineering_validation_runner.py -q
git add scripts/run_engineering_validation.py tests/test_engineering_validation_runner.py
git commit -m "feat: execute engineering validation scenario cases"
```

### Task 4: Write Validation Session Outputs

**Files:**
- Modify: `scripts/run_engineering_validation.py`
- Test: `tests/test_engineering_validation_runner.py`

- [ ] **Step 1: Add failing output writer tests**

Append:

```python
from scripts.run_engineering_validation import write_validation_outputs


def test_write_validation_outputs_creates_session_files(tmp_path: Path) -> None:
    result = EngineeringValidationCaseResult(case_id="case-a", passed=True, phase="succeeded")
    summary = write_validation_outputs(
        session_id="validation-test",
        matrix_path=Path("matrix.json"),
        output_root=tmp_path,
        cases=[],
        results=[result],
        metadata={"base_url": "http://127.0.0.1:8000"},
    )

    assert summary.passed_cases == 1
    assert (tmp_path / "validation_session.json").exists()
    assert (tmp_path / "case_results.jsonl").exists()
    assert (tmp_path / "validation_summary.json").exists()
    assert (tmp_path / "validation_summary.md").exists()
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_engineering_validation_runner.py::test_write_validation_outputs_creates_session_files -q
```

Expected: FAIL because `write_validation_outputs()` does not exist.

- [ ] **Step 3: Implement session writers**

Use `ValidationSessionManifest` and `write_validation_session_manifest()` from the artifact lifecycle plan. If that plan has not landed yet, add a local writer now and reconcile when merging.

Write:

- `validation_session.json`
- `matrix_snapshot.json`
- `case_results.jsonl`
- `validation_summary.json`
- `validation_summary.md`

The Markdown table must include:

```markdown
| Case | Region | AOI | Phase | Passed | Failures |
```

- [ ] **Step 4: Wire CLI output root**

Add parser args:

```python
parser.add_argument("--base-url", default="http://127.0.0.1:8000")
parser.add_argument("--output-root", default="")
parser.add_argument("--timeout", type=float, default=1200.0)
parser.add_argument("--session-id", default="")
```

Default session id format:

```text
validation-YYYYMMDD-HHMMSS
```

Default output root:

```text
runs/engineering-validation/<session_id>
```

- [ ] **Step 5: Verify and commit**

```powershell
py -3.13 -m pytest tests/test_engineering_validation_runner.py -q
python scripts/run_engineering_validation.py --dry-run --output-root runs/engineering-validation/test-dry-run
git add scripts/run_engineering_validation.py tests/test_engineering_validation_runner.py
git commit -m "feat: write engineering validation session outputs"
```

### Task 5: Document And Smoke The Real Runner

**Files:**
- Modify: `docs/no-ui-agent-operations.md`
- Modify: `scripts/run_engineering_validation.py`
- Test: `tests/test_engineering_validation_runner.py`

- [ ] **Step 1: Add CLI smoke tests**

Append a test that calls `main()` with `--dry-run`, `--case`, and a fixture matrix. Assert return code 0 and selected case output.

- [ ] **Step 2: Update runbook**

Add to `docs/no-ui-agent-operations.md` under the scenario regression section:

```powershell
python scripts/run_engineering_validation.py `
  --matrix docs/superpowers/validation/engineering_validation_matrix.yaml `
  --base-url http://127.0.0.1:8010 `
  --output-root runs/engineering-validation/manual-20260604 `
  --timeout 1200
```

Document expected outputs:

- `validation_session.json`
- `matrix_snapshot.json`
- `case_results.jsonl`
- `validation_summary.json`
- `validation_summary.md`

- [ ] **Step 3: Ensure failure exits non-zero**

`main()` must return:

- `0` when all selected cases pass
- `1` when any selected case fails
- `2` for malformed matrix or missing selected case

- [ ] **Step 4: Run verification**

```powershell
py -3.13 -m pytest tests/test_engineering_validation_runner.py tests/test_engineering_validation_matrix.py -q
python scripts/run_engineering_validation.py --dry-run --case africa_nairobi_small_city
```

Expected: tests pass; dry-run prints exactly the selected case.

- [ ] **Step 5: Commit**

```powershell
git add scripts/run_engineering_validation.py docs/no-ui-agent-operations.md tests/test_engineering_validation_runner.py
git commit -m "docs: document real engineering validation runner"
```

---

## Final Verification

Run:

```powershell
py -3.13 -m pytest tests/test_engineering_validation_runner.py tests/test_engineering_validation_matrix.py -q
python scripts/run_engineering_validation.py --dry-run
rg -n "Non-dry-run execution is implemented" scripts/run_engineering_validation.py
rg -n "validation_session.json|case_results.jsonl|validation_summary.md" scripts docs tests
$patterns = @('TO'+'DO','TB'+'D','\.'+'\.'+'\.','place'+'holder','FIX'+'ME','X'+'XX')
Select-String -Path docs/superpowers/plans/2026-06-04-real-engineering-validation-runner.md -Pattern $patterns
```

Expected:

- Tests pass.
- Dry-run lists matrix cases.
- The old non-dry-run `SystemExit` message is gone.
- Red-flag scan returns no matches.

## Integration Commit

After all tasks pass:

```powershell
git status --short
git log --oneline -5
```

Then merge and push according to the active superpowers branch-finishing workflow.
