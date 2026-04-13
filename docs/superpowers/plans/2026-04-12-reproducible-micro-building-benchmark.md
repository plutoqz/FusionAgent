# Reproducible Micro Building Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the building micro benchmark reproducible from tracked repository state by teaching manifest-backed evaluation to clip source shapefiles into a micro AOI before zipping and execution.

**Architecture:** Keep the current `eval_harness -> materialized case dir -> local smoke runner` flow intact. Extend manifest cases with an optional clip bbox, materialize clipped OSM/reference shapefiles into the temporary case bundle, and record the micro case directly in the tracked real-data manifest so the benchmark no longer depends on `tmp/micro_building_case/manifest.json`.

**Tech Stack:** Python, GeoPandas, pytest, existing `scripts/eval_harness.py`, existing `utils/vector_clip.py`, JSON/Markdown docs

---

## File Structure

### Existing files to modify

- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\codex-micro-benchmark\scripts\eval_harness.py`
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\codex-micro-benchmark\tests\test_eval_harness.py`
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\codex-micro-benchmark\docs\superpowers\specs\2026-04-07-real-data-eval-manifest.json`
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\codex-micro-benchmark\docs\superpowers\plans\2026-04-08-benchmark-followup-and-runtime-alignment.md`
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\codex-micro-benchmark\docs\superpowers\specs\2026-04-08-building-micro-benchmark-result.json`
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\codex-micro-benchmark\docs\superpowers\specs\2026-04-08-benchmark-followup-summary.md`
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\codex-micro-benchmark\README.md`
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\codex-micro-benchmark\README.en.md`

## Task 1: Add Failing Coverage For Manifest-Driven Micro AOI Clipping

**Files:**
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\codex-micro-benchmark\tests\test_eval_harness.py`

- [x] **Step 1: Write the failing test for a manifest case with `clip_bbox`**

Add a test that creates two small shapefiles, passes a manifest case with:

```python
"clip_bbox": [0.25, 0.25, 0.55, 0.55]
```

and asserts:

- `_materialize_manifest_case(...)` still creates `input/osm.zip` and `input/ref.zip`
- generated `case.json` contains `trigger.spatial_extent == "bbox(0.25,0.25,0.55,0.55)"`
- clipped shapefile bounds inside the zip do not exceed the requested bbox

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_eval_harness.py -k clip_bbox`

Expected: FAIL because `_materialize_manifest_case(...)` currently ignores any clip bbox metadata.

## Task 2: Implement Manifest Input Clipping

**Files:**
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\codex-micro-benchmark\scripts\eval_harness.py`

- [x] **Step 1: Add a small clip-bbox parser and shapefile materialization helper**

Implement a helper that:

- accepts `clip_bbox` as a 4-number list
- clips the source shapefile with `clip_frame_to_request_bbox(...)`
- writes the clipped shapefile to a temp directory
- zips the clipped output with `zip_shapefile_bundle(...)`

- [x] **Step 2: Thread `clip_bbox` into `_materialize_manifest_case(...)`**

When `clip_bbox` is present:

- clip both `inputs.osm` and `inputs.reference`
- set `trigger.spatial_extent` in generated `case.json` to `bbox(minx,miny,maxx,maxy)`

When absent:

- keep current behavior unchanged

- [x] **Step 3: Re-run focused tests**

Run: `python -m pytest -q tests/test_eval_harness.py tests/test_local_smoke_helpers.py`

Expected: PASS

## Task 3: Register A Tracked Micro Benchmark Case And Run It

**Files:**
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\codex-micro-benchmark\docs\superpowers\specs\2026-04-07-real-data-eval-manifest.json`
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\codex-micro-benchmark\docs\superpowers\specs\2026-04-08-building-micro-benchmark-result.json`

- [x] **Step 1: Add `building_gitega_micro_agent` to the tracked manifest**

Use the existing Gitega building inputs and this bbox:

```json
[29.817351, -3.646572, 29.931113, -3.412421]
```

Keep:

- `theme = "building"`
- `execution_mode = "agent"`
- `readiness = "agent-ready"`
- `timeout_sec = 1200`

- [x] **Step 2: Start or reuse an isolated local runtime**

Run: `python scripts/start_local.py --port 8012`

Expected: a clean runtime on `http://127.0.0.1:8012`

- [x] **Step 3: Run the micro benchmark from the tracked manifest**

Run:

```powershell
python scripts/eval_harness.py --manifest docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json --case building_gitega_micro_agent --base-url http://127.0.0.1:8012 --timeout 1200 --output-json docs/superpowers/specs/2026-04-08-building-micro-benchmark-result.json
```

Expected: `total=1` and either a passed case with concrete `run_id`/`duration_ms`, or a concrete failure reason from the actual runtime.

## Task 4: Update Docs To Reflect The Reproducible Path

**Files:**
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\codex-micro-benchmark\docs\superpowers\plans\2026-04-08-benchmark-followup-and-runtime-alignment.md`
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\codex-micro-benchmark\docs\superpowers\specs\2026-04-08-benchmark-followup-summary.md`
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\codex-micro-benchmark\README.md`
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\codex-micro-benchmark\README.en.md`

- [x] **Step 1: Replace the old blocker wording in the benchmark follow-up plan**

Document that the micro case now comes from the tracked manifest rather than `tmp/micro_building_case/manifest.json`.

- [x] **Step 2: Refresh the benchmark summary with the new micro result**

Include:

- official case status
- micro case status
- run ids
- durations
- exact base URL used

- [x] **Step 3: Update both READMEs after re-checking the implemented benchmark workflow**

Add a concise note that:

- real-data manifest now includes a reproducible micro building case
- micro AOI generation is manifest-driven via clip bbox, not local temporary files

## Task 5: Verify, Merge, And Clean Up

**Files:**
- Modify: `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\codex-micro-benchmark\docs\superpowers\plans\2026-04-12-reproducible-micro-building-benchmark.md`

- [x] **Step 1: Run final verification**

Run:

```powershell
python -m pytest -q tests/test_eval_harness.py tests/test_local_smoke_helpers.py
```

and keep the benchmark result JSON as live evidence.

- [x] **Step 2: Commit**

```bash
git add scripts/eval_harness.py tests/test_eval_harness.py docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json docs/superpowers/specs/2026-04-08-building-micro-benchmark-result.json docs/superpowers/plans/2026-04-08-benchmark-followup-and-runtime-alignment.md docs/superpowers/specs/2026-04-08-benchmark-followup-summary.md README.md README.en.md docs/superpowers/plans/2026-04-12-reproducible-micro-building-benchmark.md
git commit -m "feat: make micro building benchmark reproducible"
```

- [x] **Step 3: Push, merge to `main`, and clean local/remote branches**

Use the current repo’s established fast-forward cleanup workflow after verification succeeds.

## Execution Status

- Status: implementation complete; runtime evidence captured.
- Verification on `2026-04-12`: `python -m pytest -q tests/test_eval_harness.py tests/test_local_smoke_helpers.py` -> `16 passed`.
- Reproducibility result: `building_gitega_micro_agent` is now generated from the tracked real-data manifest via `clip_bbox`, without relying on `tmp/micro_building_case/manifest.json`.
- Current runtime result: the full-loop local run still timed out after creating run `8319c5bba5f64dd1a88ace78debaace5`, which remained at `queued`. The remaining blocker is worker/runtime alignment, not manifest/input reproducibility.
- Branch wrap-up on `2026-04-13`: the work was fast-forward merged to `main`, pushed to `origin/main`, local/remote feature branches were removed, and the leftover detached worktree directory was cleaned up after the log handle was released.
