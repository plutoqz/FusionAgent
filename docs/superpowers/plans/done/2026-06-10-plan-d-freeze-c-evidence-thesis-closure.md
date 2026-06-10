# Plan D Freeze C Evidence Thesis Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the frozen engineering system into reproducible thesis evidence, immutable experiment manifests, generated result tables, and current thesis draft hooks.

**Architecture:** Add an experiment evidence service that hashes outputs, records commit/runtime/seed metadata, verifies frozen directories, and renders thesis-ready tables from machine-readable evidence. Freeze C never mutates old experiment outputs; intentional reruns create new experiment ids.

**Tech Stack:** Python, pytest, JSON, Markdown, Git metadata, SHA-256 file hashing, existing Freeze A/B checks, `scripts/eval_kg_ablation.py`, Windows PowerShell commands.

---

## Entry Conditions

- Freeze A runtime contract suite passes.
- Freeze B benchmark protocol suite passes.
- Plan C ablation metrics and architecture MVP evidence are available.
- Plan D does not change algorithm code, KG selectability, benchmark definitions, or architecture behavior except for evidence collection scripts.

## Sources Consulted

- `docs/superpowers/specs/2026-06-10-fusionagent-reliability-roadmap-design.md`
- `scripts/freeze_paper_evidence.py`
- `scripts/freeze_scenario_evidence.py`
- `scripts/eval_kg_ablation.py`
- `services/evidence_lifecycle_service.py`
- `docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json`
- `docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.json`

## File Structure

- Create: `schemas/experiment_evidence.py`
  - Experiment manifest, file hash, runtime state, and thesis table source schemas.
- Create: `services/experiment_evidence_service.py`
  - Directory hashing, manifest creation, manifest verification, and evidence reference validation.
- Create: `scripts/freeze_experiment_evidence.py`
  - CLI that freezes one experiment output directory into a manifest.
- Create: `scripts/render_thesis_tables.py`
  - CLI that renders Markdown/JSON thesis tables from frozen experiment manifests.
- Create: `tests/test_experiment_evidence_service.py`
  - Hash and integrity tests.
- Create: `tests/test_freeze_experiment_evidence.py`
  - CLI smoke tests.
- Create: `tests/test_render_thesis_tables.py`
  - Table rendering tests.
- Create: `docs/superpowers/specs/2026-06-10-research-contribution-ledger.md`
  - Claim-to-evidence ledger.
- Create: `docs/superpowers/specs/2026-06-10-freeze-c-experiment-matrix.json`
  - Experiment matrix covering reliability, ablation, healing, quality, and Windows operability evidence.
- Create: `docs/thesis/experiment-results-draft.md`
  - Thesis-ready result section draft skeleton linked to generated tables.

---

### Task 1: Add Experiment Evidence Schemas And Hash Service

**Files:**
- Create: `schemas/experiment_evidence.py`
- Create: `services/experiment_evidence_service.py`
- Test: `tests/test_experiment_evidence_service.py`

- [ ] **Step 1: Write failing integrity tests**

Create `tests/test_experiment_evidence_service.py`:

```python
from __future__ import annotations

from pathlib import Path

from services.experiment_evidence_service import build_experiment_manifest, verify_experiment_manifest


def test_experiment_manifest_detects_output_mutation(tmp_path: Path) -> None:
    output_dir = tmp_path / "experiment"
    output_dir.mkdir()
    result = output_dir / "result.json"
    result.write_text('{"ok": true}', encoding="utf-8")

    manifest = build_experiment_manifest(
        experiment_id="exp-test",
        output_dir=output_dir,
        commit_sha="abc123",
        seed_hash="seed",
        runtime_settings_hash="settings",
        metric_definition_hash="metrics",
    )
    assert verify_experiment_manifest(manifest) == []

    result.write_text('{"ok": false}', encoding="utf-8")

    failures = verify_experiment_manifest(manifest)
    assert any("hash changed" in failure for failure in failures)
```

- [ ] **Step 2: Run test to confirm failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_experiment_evidence_service.py -q
```

Expected: FAIL because the evidence service does not exist.

- [ ] **Step 3: Implement schemas and hash service**

Create `schemas/experiment_evidence.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class FrozenFileHash(BaseModel):
    relative_path: str
    sha256: str
    size_bytes: int


class ExperimentEvidenceManifest(BaseModel):
    experiment_id: str
    output_dir: str
    commit_sha: str
    seed_hash: str
    runtime_settings_hash: str
    metric_definition_hash: str
    files: list[FrozenFileHash] = Field(default_factory=list)
```

Create `services/experiment_evidence_service.py`:

```python
from __future__ import annotations

import hashlib
from pathlib import Path

from schemas.experiment_evidence import ExperimentEvidenceManifest, FrozenFileHash


def build_experiment_manifest(
    *,
    experiment_id: str,
    output_dir: Path,
    commit_sha: str,
    seed_hash: str,
    runtime_settings_hash: str,
    metric_definition_hash: str,
) -> ExperimentEvidenceManifest:
    output_dir = Path(output_dir)
    files = [
        FrozenFileHash(
            relative_path=str(path.relative_to(output_dir)).replace("\\", "/"),
            sha256=_sha256_file(path),
            size_bytes=path.stat().st_size,
        )
        for path in sorted(output_dir.rglob("*"))
        if path.is_file()
    ]
    return ExperimentEvidenceManifest(
        experiment_id=experiment_id,
        output_dir=str(output_dir),
        commit_sha=commit_sha,
        seed_hash=seed_hash,
        runtime_settings_hash=runtime_settings_hash,
        metric_definition_hash=metric_definition_hash,
        files=files,
    )


def verify_experiment_manifest(manifest: ExperimentEvidenceManifest) -> list[str]:
    output_dir = Path(manifest.output_dir)
    failures: list[str] = []
    for item in manifest.files:
        path = output_dir / item.relative_path
        if not path.exists():
            failures.append(f"{item.relative_path}: missing")
            continue
        current_hash = _sha256_file(path)
        if current_hash != item.sha256:
            failures.append(f"{item.relative_path}: hash changed")
        if path.stat().st_size != item.size_bytes:
            failures.append(f"{item.relative_path}: size changed")
    return failures


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
```

- [ ] **Step 4: Run integrity tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_experiment_evidence_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit evidence schema and service**

Run:

```powershell
git add schemas/experiment_evidence.py services/experiment_evidence_service.py tests/test_experiment_evidence_service.py
git commit -m "feat: add immutable experiment evidence manifests"
```

---

### Task 2: Add Freeze C Evidence CLI

**Files:**
- Create: `scripts/freeze_experiment_evidence.py`
- Test: `tests/test_freeze_experiment_evidence.py`

- [ ] **Step 1: Write failing CLI test**

Create `tests/test_freeze_experiment_evidence.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from scripts.freeze_experiment_evidence import freeze_experiment


def test_freeze_experiment_writes_manifest(tmp_path: Path) -> None:
    output_dir = tmp_path / "exp"
    output_dir.mkdir()
    (output_dir / "result.json").write_text('{"metric": 1}', encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"

    manifest = freeze_experiment(
        experiment_id="exp-001",
        output_dir=output_dir,
        output_json=manifest_path,
        commit_sha="abc123",
        seed_hash="seed",
        runtime_settings_hash="settings",
        metric_definition_hash="metrics",
    )

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest.experiment_id == "exp-001"
    assert payload["files"][0]["relative_path"] == "result.json"
```

- [ ] **Step 2: Run test to confirm failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_freeze_experiment_evidence.py -q
```

Expected: FAIL because the script does not exist.

- [ ] **Step 3: Implement Freeze C CLI**

Create `scripts/freeze_experiment_evidence.py`:

```python
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from schemas.experiment_evidence import ExperimentEvidenceManifest
from services.experiment_evidence_service import build_experiment_manifest, verify_experiment_manifest


def freeze_experiment(
    *,
    experiment_id: str,
    output_dir: Path,
    output_json: Path,
    commit_sha: str,
    seed_hash: str,
    runtime_settings_hash: str,
    metric_definition_hash: str,
) -> ExperimentEvidenceManifest:
    manifest = build_experiment_manifest(
        experiment_id=experiment_id,
        output_dir=output_dir,
        commit_sha=commit_sha,
        seed_hash=seed_hash,
        runtime_settings_hash=runtime_settings_hash,
        metric_definition_hash=metric_definition_hash,
    )
    failures = verify_experiment_manifest(manifest)
    if failures:
        raise RuntimeError("; ".join(failures))
    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest


def _current_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze an experiment output directory for Freeze C.")
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--seed-hash", required=True)
    parser.add_argument("--runtime-settings-hash", required=True)
    parser.add_argument("--metric-definition-hash", required=True)
    parser.add_argument("--commit-sha", default="")
    args = parser.parse_args(argv)
    manifest = freeze_experiment(
        experiment_id=args.experiment_id,
        output_dir=Path(args.output_dir),
        output_json=Path(args.output_json),
        commit_sha=args.commit_sha or _current_commit(),
        seed_hash=args.seed_hash,
        runtime_settings_hash=args.runtime_settings_hash,
        metric_definition_hash=args.metric_definition_hash,
    )
    print(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run CLI test**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_freeze_experiment_evidence.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Freeze C CLI**

Run:

```powershell
git add scripts/freeze_experiment_evidence.py tests/test_freeze_experiment_evidence.py
git commit -m "feat: add freeze c experiment evidence cli"
```

---

### Task 3: Render Thesis Tables From Evidence

**Files:**
- Create: `scripts/render_thesis_tables.py`
- Test: `tests/test_render_thesis_tables.py`

- [ ] **Step 1: Write failing table rendering test**

Create `tests/test_render_thesis_tables.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from scripts.render_thesis_tables import render_tables


def test_render_tables_references_registered_experiments(tmp_path: Path) -> None:
    manifest = tmp_path / "exp.json"
    manifest.write_text(
        json.dumps(
            {
                "experiment_id": "exp-a2b",
                "output_dir": "runs/exp-a2b",
                "commit_sha": "abc",
                "seed_hash": "seed",
                "runtime_settings_hash": "settings",
                "metric_definition_hash": "metrics",
                "files": [],
            }
        ),
        encoding="utf-8",
    )
    output_md = tmp_path / "tables.md"

    payload = render_tables([manifest], output_markdown=output_md)

    assert payload["experiment_count"] == 1
    assert "| exp-a2b |" in output_md.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to confirm failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_render_thesis_tables.py -q
```

Expected: FAIL because `scripts.render_thesis_tables` does not exist.

- [ ] **Step 3: Implement table renderer**

Create `scripts/render_thesis_tables.py`:

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

from schemas.experiment_evidence import ExperimentEvidenceManifest


def render_tables(manifest_paths: list[Path], *, output_markdown: Path) -> dict[str, Any]:
    manifests = [
        ExperimentEvidenceManifest.model_validate_json(Path(path).read_text(encoding="utf-8"))
        for path in manifest_paths
    ]
    payload = {
        "experiment_count": len(manifests),
        "experiments": [manifest.model_dump(mode="json") for manifest in manifests],
    }
    output_markdown = Path(output_markdown)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.write_text(_render_markdown(payload), encoding="utf-8")
    return payload


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Thesis Evidence Tables",
        "",
        "| Experiment | Commit | Seed Hash | Runtime Settings Hash | Metric Definition Hash | File Count |",
        "| --- | --- | --- | --- | --- | ---: |",
    ]
    for experiment in payload["experiments"]:
        lines.append(
            "| {experiment_id} | {commit_sha} | {seed_hash} | {runtime_settings_hash} | {metric_definition_hash} | {file_count} |".format(
                experiment_id=experiment["experiment_id"],
                commit_sha=experiment["commit_sha"],
                seed_hash=experiment["seed_hash"],
                runtime_settings_hash=experiment["runtime_settings_hash"],
                metric_definition_hash=experiment["metric_definition_hash"],
                file_count=len(experiment["files"]),
            )
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render thesis tables from Freeze C experiment manifests.")
    parser.add_argument("--manifest", action="append", required=True)
    parser.add_argument("--output-markdown", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(render_tables([Path(item) for item in args.manifest], output_markdown=Path(args.output_markdown)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run table tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_render_thesis_tables.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit renderer**

Run:

```powershell
git add scripts/render_thesis_tables.py tests/test_render_thesis_tables.py
git commit -m "feat: render thesis tables from frozen evidence"
```

---

### Task 4: Create Research Contribution Ledger And Experiment Matrix

**Files:**
- Create: `docs/superpowers/specs/2026-06-10-research-contribution-ledger.md`
- Create: `docs/superpowers/specs/2026-06-10-freeze-c-experiment-matrix.json`

- [ ] **Step 1: Create contribution ledger**

Create `docs/superpowers/specs/2026-06-10-research-contribution-ledger.md`:

```markdown
# Research Contribution Ledger

| claim_id | claim_text | engineering_dependencies | baseline | metric | evidence_source | claim_boundary | thesis_section | draft_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | KG-grounded planning and validation reduce invalid plans | Freeze A | A0 | unknown_algorithm_rate, planning_valid_rate | Freeze C ablation manifest | planning validity, not fusion quality | Experiments | draft required |
| C2 | Fail-closed runtime governance improves executable success while exposing fallback | Freeze A, Plan C | A2a | validator_rejection_rate, kg_fallback_rate, final_executable_success_rate | Freeze C ablation manifest | runtime resilience, not LLM optimality | Results | draft required |
| C3 | Policy and healing governance improve resilience under failures | Freeze A, Plan C | A2b | healing_success_rate, policy_sourced_repair_count | repair evidence manifest | existing repair capability boundary | Results | draft required |
| C4 | Fusion outputs have reproducible task-specific quality evidence | Freeze B | fixed_adapter | invalid_geometry_rate, duplicate_geometry_rate, task metrics | Freeze C quality manifest | frozen AOIs only | Benchmark | draft required |
| C5 | Architecture preserves extension contract without promoting future tasks | Freeze A, Plan E | none | reserved_capability_blocked, extension_contract_complete | runtime contract and Windows docs | trajectory-to-road remains reservation-only | Discussion | draft required |
```

- [ ] **Step 2: Create experiment matrix**

Create `docs/superpowers/specs/2026-06-10-freeze-c-experiment-matrix.json`:

```json
{
  "matrix_id": "freeze-c-v1",
  "experiments": [
    {
      "experiment_id": "exp-ablation-a0-a2",
      "claim_ids": ["C1", "C2"],
      "requires_freeze": ["Freeze A", "Freeze B"],
      "runner": "scripts/eval_kg_ablation.py",
      "output_dir": "runs/experiments/exp-ablation-a0-a2",
      "required_metrics": ["unknown_algorithm_rate", "planning_valid_rate", "validator_rejection_rate", "kg_fallback_rate", "execution_success_rate"]
    },
    {
      "experiment_id": "exp-quality-freeze-b",
      "claim_ids": ["C4"],
      "requires_freeze": ["Freeze A", "Freeze B"],
      "runner": "scripts/run_fusion_quality_benchmark.py",
      "output_dir": "runs/experiments/exp-quality-freeze-b",
      "required_metrics": ["invalid_geometry_rate", "duplicate_geometry_rate", "source_contribution_balance"]
    },
    {
      "experiment_id": "exp-windows-operability",
      "claim_ids": ["C5"],
      "requires_freeze": ["Freeze A"],
      "runner": "scripts/windows_runtime_doctor.py",
      "output_dir": "runs/experiments/exp-windows-operability",
      "required_metrics": ["doctor_passed", "recovery_tick_passed", "long_run_smoke_passed"]
    }
  ]
}
```

- [ ] **Step 3: Commit ledger and matrix**

Run:

```powershell
git add docs/superpowers/specs/2026-06-10-research-contribution-ledger.md docs/superpowers/specs/2026-06-10-freeze-c-experiment-matrix.json
git commit -m "docs: add research contribution ledger and freeze c matrix"
```

---

### Task 5: Add Thesis Draft Hooks

**Files:**
- Create: `docs/thesis/experiment-results-draft.md`

- [ ] **Step 1: Create thesis draft section**

Create `docs/thesis/experiment-results-draft.md`:

```markdown
# Experiment Results Draft

## Runtime Governance

Freeze A establishes the runtime contract used by all thesis experiments. Report-only validation and fail-closed validation are separated in A2a and A2b so executable success is not mistaken for raw LLM planning quality.

## Benchmark Protocol

Freeze B fixes AOIs, source versions, baselines, metric definitions, and synthetic-data claim boundaries. Synthetic cases are treated as smoke evidence unless their generation mechanism is independent of the tested fusion algorithm.

## Ablation Results

The ablation table must report pre-fallback plan validity, Validator rejection rate, KG fallback rate, final executable success rate, and fallback plan quality delta.

## Fusion Quality Results

Quality tables report task-family metrics from machine-readable benchmark outputs. Completion-only success is not used as a substitute for fusion quality.

## Limitations

Fusion algorithms remain deterministic GIS implementations. The agentic contribution is constrained planning, runtime governance, repair evidence, recovery, auditability, and evidence lifecycle.
```

- [ ] **Step 2: Commit thesis draft hook**

Run:

```powershell
git add docs/thesis/experiment-results-draft.md
git commit -m "docs: add thesis experiment results draft"
```

---

### Task 6: Final Freeze C Verification

**Files:**
- Verify only.

- [ ] **Step 1: Run carry-forward suites**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_runtime_contract_service.py tests/test_freeze_a_runtime_contract_check.py tests/test_fusion_quality_benchmark_service.py tests/test_freeze_b_benchmark_protocol_check.py tests/test_eval_kg_ablation.py -q
```

Expected: PASS.

- [ ] **Step 2: Run Freeze C evidence suite**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_experiment_evidence_service.py tests/test_freeze_experiment_evidence.py tests/test_render_thesis_tables.py -q
```

Expected: PASS.

- [ ] **Step 3: Create a sample Freeze C manifest for renderer verification**

Run:

```powershell
.venv\Scripts\python.exe -c "from pathlib import Path; p=Path('runs/experiments/freeze-c-sample'); p.mkdir(parents=True, exist_ok=True); (p/'result.json').write_text('{\"sample\": true}', encoding='utf-8')"
.venv\Scripts\python.exe scripts/freeze_experiment_evidence.py --experiment-id freeze-c-sample --output-dir runs/experiments/freeze-c-sample --output-json docs/superpowers/specs/2026-06-10-freeze-c-sample-manifest.json --seed-hash sample-seed --runtime-settings-hash sample-settings --metric-definition-hash sample-metrics --commit-sha sample-commit
```

Expected: PASS and `docs/superpowers/specs/2026-06-10-freeze-c-sample-manifest.json` exists. The manifest is labeled sample evidence and must not be cited as a thesis result.

- [ ] **Step 4: Render current thesis evidence table**

Run:

```powershell
.venv\Scripts\python.exe scripts/render_thesis_tables.py --manifest docs/superpowers/specs/2026-06-10-freeze-c-sample-manifest.json --output-markdown docs/superpowers/specs/2026-06-10-thesis-evidence-tables.md
```

Expected: PASS and output table contains `freeze-c-sample`.

- [ ] **Step 5: Commit final Freeze C verification note**

Create `docs/superpowers/specs/2026-06-10-freeze-c-verification.md`:

```markdown
# Freeze C Verification

- Freeze A carry-forward suite: passed
- Freeze B carry-forward suite: passed
- Freeze C evidence integrity suite: passed
- Thesis table renderer: passed

## Evidence Integrity Rule

Frozen experiment outputs are immutable. Intentional reruns create a new experiment id and a new evidence manifest.
```

Run:

```powershell
git add docs/superpowers/specs/2026-06-10-freeze-c-verification.md docs/superpowers/specs/2026-06-10-freeze-c-sample-manifest.json docs/superpowers/specs/2026-06-10-thesis-evidence-tables.md runs/experiments/freeze-c-sample/result.json
git commit -m "docs: record freeze c verification"
```

---

## Self-Review Checklist

- Spec coverage:
  - Freeze C manifests and content hashes: Tasks 1 and 2.
  - Immutable experiment outputs: Task 1 verification.
  - Thesis tables from evidence: Task 3.
  - Research Contribution Ledger: Task 4.
  - Thesis draft text: Task 5.
  - Carry-forward regression: Task 6.
- Type consistency:
  - `ExperimentEvidenceManifest` is used by freeze and render scripts.
  - File hashes use content SHA-256, not timestamps.
  - Experiment matrix references claim IDs defined in the ledger.
- Scope discipline:
  - This plan freezes and renders evidence; it does not alter runtime behavior or benchmark definitions.
  - Old experiment output directories are verified, not overwritten.
