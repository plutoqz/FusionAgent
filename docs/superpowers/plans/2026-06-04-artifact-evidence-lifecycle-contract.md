# Artifact Evidence Lifecycle Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Prefer `gpt-5.5` workers. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent real engineering validation and later unattended application runs from producing unmanaged artifacts by adding one explicit evidence lifecycle contract across run, scenario, validation session, cache, frozen evidence, and cleanup surfaces.

**Architecture:** Keep existing `runs/<run_id>/` and scenario output behavior as the source of truth. Add typed manifest models and small services that index existing files without moving current outputs. The validation runner and operator reports will consume these manifests in later plans.

**Tech Stack:** Python, Pydantic v2, pytest, existing `AgentRunService`, `ScenarioRunService`, `ArtifactRegistry`, `docs/no-ui-agent-operations.md`, and `docs/v2-operations.md`.

---

## Phase 0: Documentation Discovery

### Sources Consulted

- `services/agent_run_service.py`
  - Persists `run.json`, `plan.json`, `validation.json`, `audit.jsonl`, output artifacts, `quality_report.json`, and run documents under `base_dir / run_id`.
  - Uses `GEOFUSION_RUNS_ROOT` with default `runs`.
- `services/scenario_run_service.py`
  - Persists `request.json`, `scenario_summary.json`, `evaluation.json`, `kg_path_trace.json`, `workflow_trace.json`, `source_coverage.json`, and `failed_children.json` under each scenario output directory.
- `services/scenario_output.py`
  - Resolves scenario output root from request, `GEOFUSION_SCENARIO_OUTPUT_ROOT`, or `E:\fyx\data\fusionagentTEST`.
- `services/artifact_registry.py`
  - Provides the JSON-backed artifact registry with `artifact_role`, `artifact_path`, `job_type`, `disaster_type`, `target_crs`, `output_data_type`, and `bbox`.
- `services/input_acquisition_service.py`
  - Writes `input/source_materialization_manifest.json` and registers `input_bundle` records.
- `docs/no-ui-agent-operations.md`
  - Defines cleanup and retention guidance: do not commit raw `runs/`, `Data/`, downloaded source caches, or transient inbox directories.
- `.gitignore`
  - Ignores `runs/*` while keeping `runs/.gitkeep`.

### Allowed APIs

- Read run evidence from existing `AgentRunService` path conventions.
- Read scenario evidence from existing scenario summary files.
- Reuse `ArtifactRegistry` records rather than inventing a second artifact reuse index.
- Store durable validation-session manifests under an explicit output root chosen by the runner.
- Keep frozen evidence in tracked JSON/Markdown files under `docs/superpowers/specs/` or `docs/superpowers/validation/`.

### Anti-Pattern Guards

- Do not move current run output directories in this plan.
- Do not make scenario output depend on the repo-local `runs/` root.
- Do not commit raw run directories, source caches, or downloaded raw datasets.
- Do not treat previews, reports, or frozen pointers as replacements for canonical artifact bundles.
- Do not create a database dependency for the first lifecycle contract.

## File Structure

- Create: `schemas/evidence_lifecycle.py`
- Create: `services/evidence_lifecycle_service.py`
- Modify: `services/scenario_run_service.py`
- Modify: `docs/no-ui-agent-operations.md`
- Modify: `docs/v2-operations.md`
- Test: `tests/test_evidence_lifecycle_service.py`
- Test: `tests/test_scenario_run_service.py`
- Test: `tests/test_no_ui_operations_docs.py`

---

### Task 1: Add Evidence Lifecycle Schemas

**Files:**
- Create: `schemas/evidence_lifecycle.py`
- Test: `tests/test_evidence_lifecycle_service.py`

- [ ] **Step 1: Write failing schema tests**

Create `tests/test_evidence_lifecycle_service.py` with:

```python
from __future__ import annotations

from schemas.evidence_lifecycle import EvidenceArtifactRef, EvidenceBundleManifest


def test_evidence_bundle_manifest_serializes_roles() -> None:
    manifest = EvidenceBundleManifest(
        bundle_id="run-1",
        bundle_kind="run",
        source_of_truth=["run.json", "plan.json", "audit.jsonl"],
        artifacts=[
            EvidenceArtifactRef(
                role="canonical_output",
                path="runs/run-1/output/building_fusion_result.zip",
                required=True,
                retention_class="durable_evidence",
            )
        ],
    )

    payload = manifest.model_dump(mode="json")

    assert payload["bundle_kind"] == "run"
    assert payload["artifacts"][0]["role"] == "canonical_output"
    assert payload["artifacts"][0]["retention_class"] == "durable_evidence"
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_evidence_lifecycle_service.py::test_evidence_bundle_manifest_serializes_roles -q
```

Expected: FAIL because `schemas.evidence_lifecycle` does not exist.

- [ ] **Step 3: Implement schemas**

Create `schemas/evidence_lifecycle.py`:

```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EvidenceArtifactRef(BaseModel):
    role: str
    path: str
    required: bool = True
    exists: bool = False
    retention_class: str = "transient"
    content_sha256: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceBundleManifest(BaseModel):
    bundle_id: str
    bundle_kind: str
    source_of_truth: list[str] = Field(default_factory=list)
    artifacts: list[EvidenceArtifactRef] = Field(default_factory=list)
    related_run_ids: list[str] = Field(default_factory=list)
    related_scenario_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 4: Verify**

```powershell
py -3.13 -m pytest tests/test_evidence_lifecycle_service.py::test_evidence_bundle_manifest_serializes_roles -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add schemas/evidence_lifecycle.py tests/test_evidence_lifecycle_service.py
git commit -m "feat: add evidence lifecycle schemas"
```

### Task 2: Build Run Evidence Manifest Service

**Files:**
- Create: `services/evidence_lifecycle_service.py`
- Test: `tests/test_evidence_lifecycle_service.py`

- [ ] **Step 1: Add failing run manifest tests**

Append:

```python
from pathlib import Path

from services.evidence_lifecycle_service import build_run_evidence_manifest


def test_build_run_evidence_manifest_marks_existing_core_files(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    output_dir = run_dir / "output"
    output_dir.mkdir(parents=True)
    for name in ["run.json", "plan.json", "validation.json", "audit.jsonl"]:
        (run_dir / name).write_text("{}", encoding="utf-8")
    (output_dir / "quality_report.json").write_text("{}", encoding="utf-8")
    (output_dir / "building_fusion_result.zip").write_bytes(b"zip")

    manifest = build_run_evidence_manifest(run_dir)

    assert manifest.bundle_id == "run-1"
    assert manifest.bundle_kind == "run"
    assert "run.json" in manifest.source_of_truth
    assert any(item.role == "quality_report" and item.exists for item in manifest.artifacts)
    assert any(item.role == "canonical_output" and item.exists for item in manifest.artifacts)
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_evidence_lifecycle_service.py::test_build_run_evidence_manifest_marks_existing_core_files -q
```

Expected: FAIL because the service does not exist.

- [ ] **Step 3: Implement run manifest builder**

Create `services/evidence_lifecycle_service.py` with:

```python
from __future__ import annotations

import hashlib
from pathlib import Path

from schemas.evidence_lifecycle import EvidenceArtifactRef, EvidenceBundleManifest


RUN_SOURCE_OF_TRUTH = ["request.json", "run.json", "plan.json", "validation.json", "audit.jsonl"]


def build_run_evidence_manifest(run_dir: Path) -> EvidenceBundleManifest:
    run_dir = Path(run_dir)
    artifacts = [
        _ref(run_dir, "request", "request.json", required=False, retention_class="durable_evidence"),
        _ref(run_dir, "run_status", "run.json", retention_class="durable_evidence"),
        _ref(run_dir, "plan", "plan.json", retention_class="durable_evidence"),
        _ref(run_dir, "validation", "validation.json", retention_class="durable_evidence"),
        _ref(run_dir, "audit", "audit.jsonl", retention_class="durable_evidence"),
        _ref(run_dir, "quality_report", "output/quality_report.json", required=False, retention_class="durable_evidence"),
    ]
    artifacts.extend(_canonical_outputs(run_dir))
    return EvidenceBundleManifest(
        bundle_id=run_dir.name,
        bundle_kind="run",
        source_of_truth=[name for name in RUN_SOURCE_OF_TRUTH if (run_dir / name).exists()],
        artifacts=artifacts,
        related_run_ids=[run_dir.name],
    )


def _canonical_outputs(run_dir: Path) -> list[EvidenceArtifactRef]:
    output_dir = run_dir / "output"
    if not output_dir.exists():
        return []
    paths = sorted(output_dir.glob("*_fusion_result.zip")) + sorted(output_dir.glob("*.gpkg"))
    return [
        EvidenceArtifactRef(
            role="canonical_output",
            path=str(path),
            required=True,
            exists=path.exists(),
            retention_class="durable_evidence",
            content_sha256=_sha256(path) if path.is_file() else None,
        )
        for path in paths
    ]


def _ref(
    root: Path,
    role: str,
    relative_path: str,
    *,
    required: bool = True,
    retention_class: str = "transient",
) -> EvidenceArtifactRef:
    path = root / relative_path
    return EvidenceArtifactRef(
        role=role,
        path=str(path),
        required=required,
        exists=path.exists(),
        retention_class=retention_class,
        content_sha256=_sha256(path) if path.is_file() else None,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
```

- [ ] **Step 4: Verify**

```powershell
py -3.13 -m pytest tests/test_evidence_lifecycle_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add services/evidence_lifecycle_service.py tests/test_evidence_lifecycle_service.py
git commit -m "feat: build run evidence manifests"
```

### Task 3: Add Scenario Artifact Manifest

**Files:**
- Modify: `services/evidence_lifecycle_service.py`
- Modify: `services/scenario_run_service.py`
- Test: `tests/test_evidence_lifecycle_service.py`
- Test: `tests/test_scenario_run_service.py`

- [ ] **Step 1: Add failing scenario manifest service test**

Append:

```python
import json

from services.evidence_lifecycle_service import build_scenario_evidence_manifest


def test_build_scenario_evidence_manifest_links_child_runs(tmp_path: Path) -> None:
    scenario_dir = tmp_path / "scenario_1"
    scenario_dir.mkdir()
    (scenario_dir / "scenario_summary.json").write_text(
        json.dumps(
            {
                "scenario_id": "scenario_1",
                "child_runs": [{"run_id": "run-a"}, {"run_id": "run-b"}],
                "final_outputs": ["runs/run-a/output/building_fusion_result.zip"],
            }
        ),
        encoding="utf-8",
    )

    manifest = build_scenario_evidence_manifest(scenario_dir)

    assert manifest.bundle_id == "scenario_1"
    assert manifest.related_run_ids == ["run-a", "run-b"]
    assert any(item.role == "scenario_summary" for item in manifest.artifacts)
    assert any(item.role == "child_output" for item in manifest.artifacts)
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_evidence_lifecycle_service.py::test_build_scenario_evidence_manifest_links_child_runs -q
```

Expected: FAIL because the scenario manifest builder does not exist.

- [ ] **Step 3: Implement scenario manifest builder**

Add to `services/evidence_lifecycle_service.py`:

```python
import json


SCENARIO_SOURCE_OF_TRUTH = [
    "request.json",
    "scenario_summary.json",
    "evaluation.json",
    "kg_path_trace.json",
    "workflow_trace.json",
    "source_coverage.json",
    "failed_children.json",
]


def build_scenario_evidence_manifest(scenario_dir: Path) -> EvidenceBundleManifest:
    scenario_dir = Path(scenario_dir)
    summary = _load_json(scenario_dir / "scenario_summary.json")
    child_runs = summary.get("child_runs") if isinstance(summary, dict) else []
    related_run_ids = []
    if isinstance(child_runs, list):
        for child in child_runs:
            if isinstance(child, dict):
                run_id = str(child.get("run_id") or "").strip()
                if run_id and run_id not in related_run_ids:
                    related_run_ids.append(run_id)
    artifacts = [
        _ref(scenario_dir, "request", "request.json", required=False, retention_class="durable_evidence"),
        _ref(scenario_dir, "scenario_summary", "scenario_summary.json", retention_class="durable_evidence"),
        _ref(scenario_dir, "evaluation", "evaluation.json", retention_class="durable_evidence"),
        _ref(scenario_dir, "kg_path_trace", "kg_path_trace.json", retention_class="durable_evidence"),
        _ref(scenario_dir, "workflow_trace", "workflow_trace.json", retention_class="durable_evidence"),
        _ref(scenario_dir, "source_coverage", "source_coverage.json", retention_class="durable_evidence"),
        _ref(scenario_dir, "failed_children", "failed_children.json", required=False, retention_class="durable_evidence"),
    ]
    final_outputs = summary.get("final_outputs") if isinstance(summary, dict) else []
    if isinstance(final_outputs, list):
        for raw_path in final_outputs:
            path = Path(str(raw_path))
            artifacts.append(
                EvidenceArtifactRef(
                    role="child_output",
                    path=str(path),
                    required=False,
                    exists=path.exists(),
                    retention_class="external_reference",
                    content_sha256=_sha256(path) if path.is_file() else None,
                )
            )
    return EvidenceBundleManifest(
        bundle_id=str(summary.get("scenario_id") or scenario_dir.name) if isinstance(summary, dict) else scenario_dir.name,
        bundle_kind="scenario",
        source_of_truth=[name for name in SCENARIO_SOURCE_OF_TRUTH if (scenario_dir / name).exists()],
        artifacts=artifacts,
        related_run_ids=related_run_ids,
        related_scenario_ids=[str(summary.get("scenario_id") or scenario_dir.name)] if isinstance(summary, dict) else [scenario_dir.name],
    )


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
```

- [ ] **Step 4: Write manifest during scenario summary persistence**

In `services/scenario_run_service.py`, import `build_scenario_evidence_manifest` and update `_write_summary_files()` after the existing files are written:

```python
        manifest = build_scenario_evidence_manifest(output_dir)
        (output_dir / "scenario_artifact_manifest.json").write_text(
            json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
```

Add or update a scenario service test to assert `scenario_artifact_manifest.json` exists after scenario execution.

- [ ] **Step 5: Verify and commit**

```powershell
py -3.13 -m pytest tests/test_evidence_lifecycle_service.py tests/test_scenario_run_service.py -q
git add services/evidence_lifecycle_service.py services/scenario_run_service.py tests/test_evidence_lifecycle_service.py tests/test_scenario_run_service.py
git commit -m "feat: write scenario evidence manifests"
```

### Task 4: Add Validation Session Manifest Contract

**Files:**
- Modify: `schemas/evidence_lifecycle.py`
- Modify: `services/evidence_lifecycle_service.py`
- Test: `tests/test_evidence_lifecycle_service.py`

- [ ] **Step 1: Add failing validation session tests**

Append:

```python
from schemas.evidence_lifecycle import ValidationSessionManifest


def test_validation_session_manifest_tracks_matrix_and_outputs() -> None:
    manifest = ValidationSessionManifest(
        session_id="validation-20260604-120000",
        matrix_path="docs/superpowers/validation/engineering_validation_matrix.yaml",
        output_root="runs/engineering-validation/validation-20260604-120000",
        case_result_paths=["case_results.jsonl"],
        summary_path="validation_summary.json",
    )

    payload = manifest.model_dump(mode="json")

    assert payload["session_id"].startswith("validation-")
    assert payload["case_result_paths"] == ["case_results.jsonl"]
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_evidence_lifecycle_service.py::test_validation_session_manifest_tracks_matrix_and_outputs -q
```

Expected: FAIL because `ValidationSessionManifest` does not exist.

- [ ] **Step 3: Implement validation session schema**

Add to `schemas/evidence_lifecycle.py`:

```python
class ValidationSessionManifest(BaseModel):
    session_id: str
    matrix_path: str
    output_root: str
    case_result_paths: list[str] = Field(default_factory=list)
    summary_path: str | None = None
    markdown_summary_path: str | None = None
    created_at: str | None = None
    git_commit: str | None = None
    runtime: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 4: Add writer utility**

Add to `services/evidence_lifecycle_service.py`:

```python
from schemas.evidence_lifecycle import ValidationSessionManifest


def write_validation_session_manifest(path: Path, manifest: ValidationSessionManifest) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    return path
```

- [ ] **Step 5: Verify and commit**

```powershell
py -3.13 -m pytest tests/test_evidence_lifecycle_service.py -q
git add schemas/evidence_lifecycle.py services/evidence_lifecycle_service.py tests/test_evidence_lifecycle_service.py
git commit -m "feat: define validation session evidence manifests"
```

### Task 5: Document Retention And Cleanup Rules

**Files:**
- Modify: `docs/no-ui-agent-operations.md`
- Modify: `docs/v2-operations.md`
- Test: `tests/test_no_ui_operations_docs.py`

- [ ] **Step 1: Add failing documentation contract tests**

Create or update `tests/test_no_ui_operations_docs.py`:

```python
from pathlib import Path


def test_no_ui_runbook_documents_evidence_lifecycle_contract() -> None:
    text = Path("docs/no-ui-agent-operations.md").read_text(encoding="utf-8")

    assert "Evidence Lifecycle Contract" in text
    assert "scenario_artifact_manifest.json" in text
    assert "validation_session.json" in text
    assert "raw source caches are disposable" in text
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_no_ui_operations_docs.py -q
```

Expected: FAIL because the new section is missing.

- [ ] **Step 3: Update `docs/no-ui-agent-operations.md`**

Add a section after `Evidence Freeze`:

```markdown
## Evidence Lifecycle Contract

Single-run evidence is rooted at `runs/<run_id>/`. The source of truth is `run.json`, `plan.json`, `validation.json`, `audit.jsonl`, `output/quality_report.json`, and the canonical artifact bundle.

Scenario evidence is rooted at `<scenario_output_root>/<scenario_id>/`. The source of truth is `scenario_summary.json`, `evaluation.json`, `kg_path_trace.json`, `workflow_trace.json`, `source_coverage.json`, `failed_children.json`, and `scenario_artifact_manifest.json`.

Validation evidence is rooted at the validation session output directory. The source of truth is `validation_session.json`, `matrix_snapshot.json`, `case_results.jsonl`, `validation_summary.json`, and `validation_summary.md`.

Raw source caches are disposable unless a frozen evidence file explicitly references them. Frozen JSON and Markdown records are the tracked evidence surface; raw run and cache directories stay untracked.
```

- [ ] **Step 4: Update `docs/v2-operations.md`**

Add matching references near the run/scenario evidence sections. Keep the detailed document aligned with the no-UI runbook and avoid duplicating unrelated operational guidance.

- [ ] **Step 5: Verify and commit**

```powershell
py -3.13 -m pytest tests/test_no_ui_operations_docs.py tests/test_evidence_lifecycle_service.py -q
git add docs/no-ui-agent-operations.md docs/v2-operations.md tests/test_no_ui_operations_docs.py
git commit -m "docs: define evidence lifecycle retention contract"
```

---

## Final Verification

Run:

```powershell
py -3.13 -m pytest tests/test_evidence_lifecycle_service.py tests/test_scenario_run_service.py tests/test_no_ui_operations_docs.py -q
rg -n "scenario_artifact_manifest.json|validation_session.json|Evidence Lifecycle Contract" docs services schemas tests
$patterns = @('TO'+'DO','TB'+'D','\.'+'\.'+'\.','place'+'holder','FIX'+'ME','X'+'XX')
Select-String -Path docs/superpowers/plans/2026-06-04-artifact-evidence-lifecycle-contract.md -Pattern $patterns
```

Expected:

- All tests pass.
- Evidence lifecycle references exist in code and docs.
- Red-flag scan returns no matches.

## Integration Commit

After all tasks pass:

```powershell
git status --short
git log --oneline -5
```

Then merge and push according to the active superpowers branch-finishing workflow.
