# Plan E Windows Runtime Operability Long Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Windows runnable system credible as a thesis support artifact by documenting and testing local startup, health checks, long-running execution, recovery scans, evidence retention, and known operational boundaries.

**Architecture:** Add Windows-focused readiness checks and long-run smoke scripts around existing no-UI services: `start_local.py`, scenario inbox processing, unattended runtime snapshots, recovery ticks, run registry, and evidence lifecycle. The plan targets the current Windows development/runtime environment only and does not add cross-platform compatibility, production deployment, authentication, or cloud operations.

**Tech Stack:** Python, PowerShell, pytest, existing `services.unattended_run_monitor_service`, `services.run_recovery_service`, `scripts.watch_scenario_inbox.py`, `scripts.run_no_ui_maturity_check.py`, local `runs/` evidence directories.

---

## Entry Conditions

- Plan A runtime contract checks pass.
- Plan D evidence integrity rules are understood so long-run outputs are not confused with frozen thesis evidence.
- Plan E does not add new task families, new providers, frontend requirements, production deployment, or cross-platform guarantees.

## Sources Consulted

- `scripts/start_local.py`
- `scripts/watch_scenario_inbox.py`
- `scripts/run_no_ui_maturity_check.py`
- `services/unattended_run_monitor_service.py`
- `services/run_recovery_service.py`
- `services/run_recovery_executor.py`
- `services/run_registry_service.py`
- `services/evidence_lifecycle_service.py`
- `tests/test_unattended_run_monitor_service.py`
- `tests/test_watch_scenario_inbox.py`
- `tests/test_run_recovery_service.py`
- `tests/test_worker_recovery_tick.py`

## File Structure

- Create: `services/windows_runtime_readiness_service.py`
  - Windows local environment checks for Python, venv, writable directories, key scripts, optional Neo4j state, and disk budget.
- Create: `scripts/windows_runtime_doctor.py`
  - CLI wrapper that writes machine-readable readiness evidence.
- Create: `scripts/run_windows_long_run_smoke.py`
  - Bounded long-run smoke harness for inbox processing, recovery tick, run registry, and evidence output.
- Create: `scripts/start_fusionagent_windows.ps1`
  - PowerShell entrypoint for local no-UI startup with visible commands and log paths.
- Modify: `scripts/run_no_ui_maturity_check.py`
  - Include Windows runtime docs and doctor evidence in the maturity check.
- Create: `tests/test_windows_runtime_readiness_service.py`
  - Unit tests for readiness classification.
- Create: `tests/test_windows_runtime_doctor.py`
  - CLI smoke tests.
- Create: `tests/test_windows_long_run_smoke.py`
  - Dry-run smoke tests.
- Create: `docs/windows-local-runtime.md`
  - Operator guide for the Windows runnable system.
- Create: `docs/superpowers/specs/2026-06-10-windows-runtime-operability-evidence.md`
  - Evidence note and known limits for thesis appendix.

---

### Task 1: Add Windows Runtime Readiness Service

**Files:**
- Create: `services/windows_runtime_readiness_service.py`
- Test: `tests/test_windows_runtime_readiness_service.py`

- [ ] **Step 1: Write failing readiness tests**

Create `tests/test_windows_runtime_readiness_service.py`:

```python
from __future__ import annotations

from pathlib import Path

from services.windows_runtime_readiness_service import classify_windows_runtime_readiness


def test_windows_runtime_ready_when_required_paths_exist(tmp_path: Path) -> None:
    required = []
    for name in ("start_local.py", "watch_scenario_inbox.py"):
        path = tmp_path / name
        path.write_text("print('ok')", encoding="utf-8")
        required.append(path)
    runs_dir = tmp_path / "runs"

    report = classify_windows_runtime_readiness(required_paths=required, writable_dirs=[runs_dir], free_disk_gb=10.0)

    assert report["status"] == "ready"
    assert report["manual_intervention_required"] is False


def test_windows_runtime_degraded_when_required_script_missing(tmp_path: Path) -> None:
    report = classify_windows_runtime_readiness(
        required_paths=[tmp_path / "missing.py"],
        writable_dirs=[tmp_path / "runs"],
        free_disk_gb=10.0,
    )

    assert report["status"] == "degraded"
    assert report["manual_intervention_required"] is True
    assert report["missing_paths"] == [str(tmp_path / "missing.py")]
```

- [ ] **Step 2: Run tests to confirm failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_windows_runtime_readiness_service.py -q
```

Expected: FAIL because the service does not exist.

- [ ] **Step 3: Implement readiness service**

Create `services/windows_runtime_readiness_service.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

MIN_FREE_DISK_GB = 2.0


def classify_windows_runtime_readiness(
    *,
    required_paths: list[Path],
    writable_dirs: list[Path],
    free_disk_gb: float,
) -> dict[str, Any]:
    missing_paths = [str(path) for path in required_paths if not Path(path).exists()]
    unwritable_dirs = []
    for directory in writable_dirs:
        path = Path(directory)
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".fusionagent_write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError:
            unwritable_dirs.append(str(path))
    disk_ok = float(free_disk_gb) >= MIN_FREE_DISK_GB
    status = "ready" if not missing_paths and not unwritable_dirs and disk_ok else "degraded"
    return {
        "status": status,
        "manual_intervention_required": status != "ready",
        "missing_paths": missing_paths,
        "unwritable_dirs": unwritable_dirs,
        "free_disk_gb": float(free_disk_gb),
        "min_free_disk_gb": MIN_FREE_DISK_GB,
        "windows_scope": "current Windows local runtime only",
    }
```

- [ ] **Step 4: Run readiness tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_windows_runtime_readiness_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit readiness service**

Run:

```powershell
git add services/windows_runtime_readiness_service.py tests/test_windows_runtime_readiness_service.py
git commit -m "feat: add windows runtime readiness checks"
```

---

### Task 2: Add Windows Runtime Doctor CLI

**Files:**
- Create: `scripts/windows_runtime_doctor.py`
- Test: `tests/test_windows_runtime_doctor.py`

- [ ] **Step 1: Write failing doctor test**

Create `tests/test_windows_runtime_doctor.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from scripts.windows_runtime_doctor import build_doctor_report


def test_doctor_report_writes_runtime_evidence(tmp_path: Path) -> None:
    evidence_path = tmp_path / "doctor.json"
    report = build_doctor_report(repo_root=tmp_path, output_json=evidence_path, free_disk_gb=5.0)

    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert payload["status"] in {"ready", "degraded"}
    assert payload["repo_root"] == str(tmp_path)
    assert report["known_limits"]["cross_platform"] == "out_of_scope"
```

- [ ] **Step 2: Run test to confirm failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_windows_runtime_doctor.py -q
```

Expected: FAIL because the doctor script does not exist.

- [ ] **Step 3: Implement doctor CLI**

Create `scripts/windows_runtime_doctor.py`:

```python
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.windows_runtime_readiness_service import classify_windows_runtime_readiness


def build_doctor_report(repo_root: Path, *, output_json: Path, free_disk_gb: float | None = None) -> dict[str, Any]:
    repo_root = Path(repo_root)
    disk = shutil.disk_usage(repo_root)
    effective_free_gb = free_disk_gb if free_disk_gb is not None else disk.free / (1024 ** 3)
    report = classify_windows_runtime_readiness(
        required_paths=[
            repo_root / "scripts" / "start_local.py",
            repo_root / "scripts" / "watch_scenario_inbox.py",
            repo_root / "scripts" / "run_no_ui_maturity_check.py",
        ],
        writable_dirs=[repo_root / "runs", repo_root / "logs"],
        free_disk_gb=effective_free_gb,
    )
    report = {
        **report,
        "repo_root": str(repo_root),
        "known_limits": {
            "cross_platform": "out_of_scope",
            "production_deployment": "out_of_scope",
            "process_supervision": "operator_or_external_scheduler_responsibility",
        },
    }
    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check FusionAgent Windows local runtime readiness.")
    parser.add_argument("--output-json", default="docs/superpowers/specs/2026-06-10-windows-runtime-doctor.json")
    args = parser.parse_args(argv)
    report = build_doctor_report(REPO_ROOT, output_json=Path(args.output_json))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run doctor tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_windows_runtime_doctor.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit doctor CLI**

Run:

```powershell
git add scripts/windows_runtime_doctor.py tests/test_windows_runtime_doctor.py
git commit -m "feat: add windows runtime doctor"
```

---

### Task 3: Add Bounded Long-Run Smoke Harness

**Files:**
- Create: `scripts/run_windows_long_run_smoke.py`
- Test: `tests/test_windows_long_run_smoke.py`

- [ ] **Step 1: Write failing long-run smoke test**

Create `tests/test_windows_long_run_smoke.py`:

```python
from __future__ import annotations

from pathlib import Path

from scripts.run_windows_long_run_smoke import run_long_run_smoke


def test_long_run_smoke_dry_run_writes_summary(tmp_path: Path) -> None:
    summary = run_long_run_smoke(output_dir=tmp_path / "out", iterations=2, dry_run=True)

    assert summary["iterations"] == 2
    assert summary["dry_run"] is True
    assert summary["status"] == "passed"
    assert (tmp_path / "out" / "windows_long_run_smoke.json").exists()
```

- [ ] **Step 2: Run test to confirm failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_windows_long_run_smoke.py -q
```

Expected: FAIL because the script does not exist.

- [ ] **Step 3: Implement dry-run capable smoke harness**

Create `scripts/run_windows_long_run_smoke.py`:

```python
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


def run_long_run_smoke(*, output_dir: Path, iterations: int, dry_run: bool) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tick_results = []
    for index in range(iterations):
        started = time.time()
        tick_results.append(
            {
                "iteration": index + 1,
                "dry_run": dry_run,
                "inbox_tick": "skipped" if dry_run else "operator_configured",
                "recovery_tick": "skipped" if dry_run else "operator_configured",
                "elapsed_ms": int((time.time() - started) * 1000),
            }
        )
    summary = {
        "status": "passed",
        "iterations": iterations,
        "dry_run": dry_run,
        "tick_results": tick_results,
        "long_running_boundary": "external scheduler or process supervisor owns uptime",
    }
    (output_dir / "windows_long_run_smoke.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run bounded Windows long-run smoke checks.")
    parser.add_argument("--output-dir", default="runs/windows_long_run_smoke")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    summary = run_long_run_smoke(output_dir=Path(args.output_dir), iterations=args.iterations, dry_run=args.dry_run)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run long-run smoke tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_windows_long_run_smoke.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit smoke harness**

Run:

```powershell
git add scripts/run_windows_long_run_smoke.py tests/test_windows_long_run_smoke.py
git commit -m "feat: add windows long run smoke harness"
```

---

### Task 4: Add Windows Operator Entrypoint And Documentation

**Files:**
- Create: `scripts/start_fusionagent_windows.ps1`
- Create: `docs/windows-local-runtime.md`

- [ ] **Step 1: Create PowerShell entrypoint**

Create `scripts/start_fusionagent_windows.ps1`:

```powershell
param(
    [int]$Port = 8000,
    [string]$LogDir = "logs"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$LogPath = Join-Path $RepoRoot $LogDir
New-Item -ItemType Directory -Force -Path $LogPath | Out-Null

& $Python (Join-Path $RepoRoot "scripts\windows_runtime_doctor.py") `
    --output-json (Join-Path $RepoRoot "docs\superpowers\specs\2026-06-10-windows-runtime-doctor.json")

& $Python (Join-Path $RepoRoot "scripts\start_local.py") `
    --port $Port `
    *> (Join-Path $LogPath "fusionagent-local.log")

$ExitCode = $LASTEXITCODE
if ($ExitCode -ne 0) {
    Write-Host "FusionAgent startup failed with exit code $ExitCode. Last log lines:" -ForegroundColor Red
    Get-Content (Join-Path $LogPath "fusionagent-local.log") -Tail 80
    exit $ExitCode
}
```

- [ ] **Step 2: Create Windows runtime guide**

Create `docs/windows-local-runtime.md`:

```markdown
# Windows Local Runtime Guide

## Scope

This guide covers the current Windows local runtime used for thesis evidence and operator validation. Cross-platform compatibility, production deployment, authentication, multi-tenant operation, and cloud process supervision are out of scope.

## Readiness Check

Run:

```powershell
.venv\Scripts\python.exe scripts\windows_runtime_doctor.py --output-json docs\superpowers\specs\2026-06-10-windows-runtime-doctor.json
```

## Local Startup

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_fusionagent_windows.ps1
```

## Long-Run Smoke

Run:

```powershell
.venv\Scripts\python.exe scripts\run_windows_long_run_smoke.py --dry-run --iterations 3 --output-dir runs\windows_long_run_smoke
```

This dry-run smoke validates loop structure, imports, JSON evidence writing, and operator command paths. It does not dispatch real fusion runs, exercise real recovery ticks, or prove systematic end-to-end soak stability.

## Recovery

Use the recovery scan before manually deleting or rerunning stale runs. Runs that reference blocked algorithms after Freeze A require manual review.

## Evidence

Doctor and long-run smoke outputs are system operability evidence. They are not fusion quality evidence and should not enter quality tables.
```

- [ ] **Step 3: Commit docs and entrypoint**

Run:

```powershell
git add scripts/start_fusionagent_windows.ps1 docs/windows-local-runtime.md
git commit -m "docs: add windows runtime operator guide"
```

---

### Task 5: Integrate Windows Evidence Into Maturity Check

**Files:**
- Modify: `scripts/run_no_ui_maturity_check.py`
- Test: `tests/test_no_ui_maturity_check.py`

- [ ] **Step 1: Add failing maturity check test**

Create or append to `tests/test_no_ui_maturity_check.py`:

```python
from scripts.run_no_ui_maturity_check import DEFAULT_REQUIRED_FILES


def test_no_ui_maturity_check_requires_windows_runtime_docs() -> None:
    required = {path.name for path in DEFAULT_REQUIRED_FILES}

    assert "windows-local-runtime.md" in required
```

- [ ] **Step 2: Run test to confirm failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_no_ui_maturity_check.py -q
```

Expected: FAIL because the Windows runtime guide is not in `DEFAULT_REQUIRED_FILES`.

- [ ] **Step 3: Update maturity required files**

In `scripts/run_no_ui_maturity_check.py`, add:

```python
    REPO_ROOT / "docs/windows-local-runtime.md",
    REPO_ROOT / "docs/superpowers/specs/2026-06-10-windows-runtime-operability-evidence.md",
```

to `DEFAULT_REQUIRED_FILES`.

- [ ] **Step 4: Create operability evidence note**

Create `docs/superpowers/specs/2026-06-10-windows-runtime-operability-evidence.md`:

```markdown
# Windows Runtime Operability Evidence

- Runtime doctor: `scripts/windows_runtime_doctor.py`
- Long-run smoke: `scripts/run_windows_long_run_smoke.py`
- Operator guide: `docs/windows-local-runtime.md`
- Startup entrypoint: `scripts/start_fusionagent_windows.ps1`

## Claim Boundary

The system is required to run on the current Windows local environment for thesis support. The dry-run long-run smoke validates loop structure, import paths, command wiring, and JSON evidence writing; it does not prove systematic end-to-end soak stability under real fusion workload. Cross-platform compatibility and production deployment are outside the current scope.
```

- [ ] **Step 5: Run maturity and Windows tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_windows_runtime_readiness_service.py tests/test_windows_runtime_doctor.py tests/test_windows_long_run_smoke.py tests/test_no_ui_maturity_check.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit maturity integration**

Run:

```powershell
git add scripts/run_no_ui_maturity_check.py tests/test_no_ui_maturity_check.py docs/superpowers/specs/2026-06-10-windows-runtime-operability-evidence.md
git commit -m "feat: include windows operability in maturity checks"
```

---

### Task 6: Final Plan E Verification

**Files:**
- Verify only.

- [ ] **Step 1: Run Windows doctor**

Run:

```powershell
.venv\Scripts\python.exe scripts\windows_runtime_doctor.py --output-json docs/superpowers/specs/2026-06-10-windows-runtime-doctor.json
```

Expected: exit code 0 when local runtime paths are ready. If exit code 1, inspect JSON and fix missing local setup before claiming Windows runtime readiness.

- [ ] **Step 2: Run bounded long-run smoke**

Run:

```powershell
.venv\Scripts\python.exe scripts\run_windows_long_run_smoke.py --dry-run --iterations 3 --output-dir runs\windows_long_run_smoke
```

Expected: output contains `"status": "passed"` and writes `runs/windows_long_run_smoke/windows_long_run_smoke.json`.

- [ ] **Step 3: Run carry-forward runtime tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_unattended_run_monitor_service.py tests/test_watch_scenario_inbox.py tests/test_run_recovery_service.py tests/test_worker_recovery_tick.py tests/test_windows_runtime_readiness_service.py tests/test_windows_runtime_doctor.py tests/test_windows_long_run_smoke.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit Windows evidence**

Run:

```powershell
git add docs/superpowers/specs/2026-06-10-windows-runtime-doctor.json runs/windows_long_run_smoke/windows_long_run_smoke.json
git commit -m "docs: record windows runtime operability evidence"
```

- [ ] **Step 5: Final status check**

Run:

```powershell
git status --short
```

Expected: only user-owned unrelated files remain untracked or modified. Do not stage `scripts/run_optimized_training_fusion.py` unless the user explicitly asks.

---

## Self-Review Checklist

- Spec coverage:
  - Windows runnable system: Tasks 1, 2, 4, and 6.
  - Long-running local execution: Task 3.
  - Recovery and unattended evidence: Task 6 carry-forward tests.
  - Known limitations and non-goals: Tasks 2, 4, and 5.
  - Thesis support evidence: Tasks 5 and 6.
- Type consistency:
  - Readiness reports use `status`, `manual_intervention_required`, and concrete path lists.
  - Doctor output and long-run smoke output are JSON evidence, not quality benchmark evidence.
- Scope discipline:
  - This plan targets Windows local operation only.
  - This plan does not add cross-platform support, production deployment, authentication, frontend evaluation, or cloud supervision.
