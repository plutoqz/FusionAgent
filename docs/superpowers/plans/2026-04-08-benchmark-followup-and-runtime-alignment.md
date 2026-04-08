# Benchmark Follow-Up And Runtime Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the false timeout conclusion for the first real-data building benchmark, rerun the benchmark on a clean local runtime, and capture a handoff summary for the next thread.

**Architecture:** Reproduce benchmark runs from the isolated worktree on a fresh local runtime bound to a separate port so API, worker, and result directories stay aligned. Persist the corrected official benchmark summary, keep the micro-AOI rerun as a diagnostic artifact, and finish with a written status note that points directly to the evidence files.

**Tech Stack:** Python 3.9+, FastAPI, Celery, existing `scripts/start_local.py`, existing `scripts/eval_harness.py`, GeoPandas, JSON/Markdown artifacts

---

## File Structure

### New Files

- `C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/parameter-defaults-benchmark/docs/superpowers/plans/2026-04-08-benchmark-followup-and-runtime-alignment.md`
- `C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/parameter-defaults-benchmark/docs/superpowers/specs/2026-04-08-benchmark-followup-summary.md`
- `C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/parameter-defaults-benchmark/docs/superpowers/specs/2026-04-08-building-micro-benchmark-result.json`

### Existing Files To Modify

- `C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/parameter-defaults-benchmark/docs/superpowers/specs/2026-04-08-building-real-benchmark-result.json`

### Runtime / Diagnostic Artifacts

- `C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/parameter-defaults-benchmark/runs/local-runtime/`
- `C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/parameter-defaults-benchmark/tmp/micro_building_case/manifest.json`
- `C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/parameter-defaults-benchmark/tmp/micro_building_case/summary.json`

## Task 1: Align A Fresh Local Runtime

**Files:**
- Use existing: `C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/parameter-defaults-benchmark/scripts/start_local.py`
- Use existing: `C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/parameter-defaults-benchmark/runs/local-runtime/`

- [ ] **Step 1: Start a new runtime on an isolated port**

Run:

```powershell
python scripts/start_local.py --port 8010
```

Expected: the command prints `API: http://127.0.0.1:8010` and writes fresh `api.log`, `worker.log`, and `scheduler.log` under `runs/local-runtime/`.

- [ ] **Step 2: Verify the API responds on the new port**

Run:

```powershell
try { (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8010/api/v2/runs -Method GET -TimeoutSec 10).StatusCode } catch { if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { $_.Exception.Message } }
```

Expected: `405`, proving the route exists and the app is serving the v2 API.

- [ ] **Step 3: Verify the worker log is fresh**

Run:

```powershell
Get-Content runs/local-runtime/worker.log | Select-Object -Last 20
```

Expected: recent timestamps from the current run startup, not only stale entries from older sessions.

## Task 2: Correct The Official Building Benchmark Result

**Files:**
- Modify: `C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/parameter-defaults-benchmark/docs/superpowers/specs/2026-04-08-building-real-benchmark-result.json`
- Use existing: `C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/parameter-defaults-benchmark/docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json`
- Use existing: `C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/parameter-defaults-benchmark/scripts/eval_harness.py`

- [ ] **Step 1: Rerun the official case with a longer timeout**

Run:

```powershell
python scripts/eval_harness.py --manifest docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json --case building_gitega_osm_vs_google_agent --base-url http://127.0.0.1:8010 --timeout 1200 --output-json docs/superpowers/specs/2026-04-08-building-real-benchmark-result.json
```

Expected: the output JSON records the case as `passed` if the runtime and worker are aligned, or a concrete infrastructure / execution failure if not.

- [ ] **Step 2: Inspect the generated run status**

Run:

```powershell
Get-ChildItem runs -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
```

Expected: the latest run directory corresponds to the official rerun and contains `run.json`, `logs/run.log`, and an output artifact if execution succeeded.

## Task 3: Re-run The Micro AOI Diagnostic Case

**Files:**
- Create: `C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/parameter-defaults-benchmark/docs/superpowers/specs/2026-04-08-building-micro-benchmark-result.json`
- Use existing: `C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/parameter-defaults-benchmark/tmp/micro_building_case/manifest.json`

- [ ] **Step 1: Run the micro case on the same isolated runtime**

Run:

```powershell
python scripts/eval_harness.py --manifest tmp/micro_building_case/manifest.json --case building_gitega_micro_agent --base-url http://127.0.0.1:8010 --timeout 1200 --output-json docs/superpowers/specs/2026-04-08-building-micro-benchmark-result.json
```

Expected: either a completed result with a concrete duration, or a clear runtime failure that is no longer ambiguous `queued` behavior.

- [ ] **Step 2: Cross-check the run phase**

Run:

```powershell
Get-Content -Raw (Join-Path (Get-ChildItem runs -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName) "run.json")
```

Expected: `phase` should be `succeeded` or `failed`; it should not remain indefinitely at `queued` on the fresh runtime.

## Task 4: Write A Handoff Summary

**Files:**
- Create: `C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/parameter-defaults-benchmark/docs/superpowers/specs/2026-04-08-benchmark-followup-summary.md`

- [ ] **Step 1: Summarize corrected findings**

Write a Markdown note that includes:

```text
- official case run id, duration, and corrected verdict
- micro case run id, duration / failure mode, and interpretation
- root cause split between "harness timeout window" and "runtime alignment"
- current branch status and whether the branch should be merged now
- exact next-thread starting commands / files
```

- [ ] **Step 2: Verify artifact paths**

Run:

```powershell
Get-ChildItem docs/superpowers/specs/2026-04-08-* | Select-Object Name,Length | Format-Table -AutoSize
```

Expected: the corrected real benchmark result, micro benchmark result, and follow-up summary all exist.

## Self-Review

### Spec coverage

- Runtime alignment is covered in Task 1.
- Official benchmark correction is covered in Task 2.
- Small-area diagnostic rerun is covered in Task 3.
- New-thread handoff is covered in Task 4.

### Placeholder scan

- No `TODO`, `TBD`, or vague "investigate later" steps remain.
- Every task has an exact command or output structure.

### Type consistency

- All file paths resolve inside the isolated worktree.
- Both benchmark commands target the same isolated base URL `http://127.0.0.1:8010`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-08-benchmark-followup-and-runtime-alignment.md`. Execution mode selected by the user: inline execution in this session.
