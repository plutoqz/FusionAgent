# Benchmark Follow-Up And Runtime Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the false timeout conclusion for the first real-data building benchmark, rerun the benchmark on a clean local runtime, and capture a handoff summary for the next thread.

**Architecture:** Reproduce benchmark runs from the isolated worktree on a fresh local runtime bound to a separate port so API, worker, and result directories stay aligned. Persist the corrected official benchmark summary, keep the micro-AOI rerun as a diagnostic artifact, and finish with a written status note that points directly to the evidence files.

**Tech Stack:** Python 3.9+, FastAPI, Celery, existing `scripts/start_local.py`, existing `scripts/eval_harness.py`, GeoPandas, JSON/Markdown artifacts

---

## File Structure

### New Files

- `E:/vscode/fusionAgent/docs/superpowers/plans/2026-04-08-benchmark-followup-and-runtime-alignment.md`
- `E:/vscode/fusionAgent/docs/superpowers/specs/2026-04-08-benchmark-followup-summary.md`
- `E:/vscode/fusionAgent/docs/superpowers/specs/2026-04-08-building-micro-benchmark-result.json`

### Existing Files To Modify

- `E:/vscode/fusionAgent/docs/superpowers/specs/2026-04-08-building-real-benchmark-result.json`

### Runtime / Diagnostic Artifacts

- `E:/vscode/fusionAgent/runs/local-runtime/`
- `E:/vscode/fusionAgent/tmp/micro_building_case/manifest.json`
- `E:/vscode/fusionAgent/tmp/micro_building_case/summary.json`

## Task 1: Align A Fresh Local Runtime

**Files:**
- Use existing: `E:/vscode/fusionAgent/scripts/start_local.py`
- Use existing: `E:/vscode/fusionAgent/runs/local-runtime/`

- [x] **Step 1: Start a new runtime on an isolated port**

Run:

```powershell
python scripts/start_local.py --port 8010
```

Expected: the command prints `API: http://127.0.0.1:8010` and writes fresh `api.log`, `worker.log`, and `scheduler.log` under `runs/local-runtime/`.

Execution note: `8010` was already occupied on `2026-04-12`, so the isolated runtime was started on `http://127.0.0.1:8011` instead to avoid cross-thread contamination.

- [x] **Step 2: Verify the API responds on the new port**

Run:

```powershell
try { (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8010/api/v2/runs -Method GET -TimeoutSec 10).StatusCode } catch { if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { $_.Exception.Message } }
```

Expected: `405`, proving the route exists and the app is serving the v2 API.

- [x] **Step 3: Verify the worker log is fresh**

Run:

```powershell
Get-Content runs/local-runtime/worker.log | Select-Object -Last 20
```

Expected: recent timestamps from the current run startup, not only stale entries from older sessions.

## Task 2: Correct The Official Building Benchmark Result

**Files:**
- Modify: `E:/vscode/fusionAgent/docs/superpowers/specs/2026-04-08-building-real-benchmark-result.json`
- Use existing: `E:/vscode/fusionAgent/docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json`
- Use existing: `E:/vscode/fusionAgent/scripts/eval_harness.py`

- [x] **Step 1: Rerun the official case with a longer timeout**

Run:

```powershell
python scripts/eval_harness.py --manifest docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json --case building_gitega_osm_vs_google_agent --base-url http://127.0.0.1:8010 --timeout 1200 --output-json docs/superpowers/specs/2026-04-08-building-real-benchmark-result.json
```

Expected: the output JSON records the case as `passed` if the runtime and worker are aligned, or a concrete infrastructure / execution failure if not.

- [x] **Step 2: Inspect the generated run status**

Run:

```powershell
Get-ChildItem runs -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
```

Expected: the latest run directory corresponds to the official rerun and contains `run.json`, `logs/run.log`, and an output artifact if execution succeeded.

Execution note: this rerun was verified through the live API status endpoint because the local relative `runs/<run_id>/` tree was not materialized inside this worktree even though the runtime reported persisted artifact paths.

## Task 3: Re-run The Micro AOI Diagnostic Case

**Files:**
- Create: `E:/vscode/fusionAgent/docs/superpowers/specs/2026-04-08-building-micro-benchmark-result.json`
- Use existing: `E:/vscode/fusionAgent/docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json`

- [x] **Step 1: Run the micro case on the same isolated runtime**

Run:

```powershell
python scripts/eval_harness.py --manifest docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json --case building_gitega_micro_agent --base-url http://127.0.0.1:8012 --timeout 1200 --output-json docs/superpowers/specs/2026-04-08-building-micro-benchmark-result.json
```

Expected: either a completed result with a concrete duration, or a clear runtime failure that is no longer ambiguous `queued` behavior.

Execution note: on `2026-04-12` the micro case was rerun from the tracked manifest after adding manifest-driven input clipping. The harness still timed out after `1200s`, but the created run id `8319c5bba5f64dd1a88ace78debaace5` shows that the remaining blocker is runtime queue consumption rather than missing local-only inputs.

Follow-up note on `2026-04-16`: a clean isolated rerun on `http://127.0.0.1:8010` passed in `194896 ms` with `run_id=7117ef6fd95a44aa97d438cb7b3a9bee`, so the earlier queued result should now be treated as historical runtime drift rather than a standing defect in current `main`.

- [x] **Step 2: Cross-check the run phase**

Run:

```powershell
Get-Content -Raw (Join-Path (Get-ChildItem runs -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName) "run.json")
```

Expected: `phase` should be `succeeded` or `failed`; it should not remain indefinitely at `queued` on the fresh runtime.

Execution note: the live API confirmed that run `8319c5bba5f64dd1a88ace78debaace5` remained at `queued` with only a `run_created` audit event, so the micro case is now reproducible from repository state but still blocked by full-loop runtime alignment.

Follow-up note on `2026-04-16`: the clean isolated rerun no longer remained at `queued`; it reached `succeeded`, which closes the specific runtime-alignment uncertainty captured by the `2026-04-12` run.

## Task 4: Write A Handoff Summary

**Files:**
- Create: `E:/vscode/fusionAgent/docs/superpowers/specs/2026-04-08-benchmark-followup-summary.md`

- [x] **Step 1: Summarize corrected findings**

Write a Markdown note that includes:

```text
- official case run id, duration, and corrected verdict
- micro case run id, duration / failure mode, and interpretation
- root cause split between "harness timeout window" and "runtime alignment"
- current branch status and whether the branch should be merged now
- exact next-thread starting commands / files
```

- [x] **Step 2: Verify artifact paths**

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

## Execution Status

- Status: completed as a historical follow-up, with later clean-rerun confirmation.
- Completed on `2026-04-12`:
  - isolated runtime aligned on `http://127.0.0.1:8011`
  - API reachability verified with `405`
  - fresh worker startup confirmed from `runs/local-runtime/worker.log`
  - official case `building_gitega_osm_vs_google_agent` rerun and passed with `run_id=0b4315edf3a8449d940355717ad70fa7`
  - follow-up summary refreshed
  - tracked manifest now includes `building_gitega_micro_agent`
  - manifest-driven clipping can materialize the micro AOI inputs from repository state alone
- Follow-up on `2026-04-16`:
  - clean isolated runtime aligned on `http://127.0.0.1:8010`
  - uploaded smoke run passed on the same runtime
  - micro case `building_gitega_micro_agent` rerun and passed with `run_id=7117ef6fd95a44aa97d438cb7b3a9bee`
  - durable confirmation was saved in `docs/superpowers/specs/2026-04-16-building-micro-alignment-result.json`
  - conclusion updated: the old queued run captured environment drift in that older runtime, not a standing blocker in current `main`
