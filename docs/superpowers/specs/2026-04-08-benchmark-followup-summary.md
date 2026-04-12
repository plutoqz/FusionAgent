# Benchmark Follow-Up Summary

## Corrected Findings

- Official real-data building case `building_gitega_osm_vs_google_agent` was rerun on `2026-04-12` on an isolated runtime at `http://127.0.0.1:8011`.
- Corrected result: `passed`.
- Corrected run id: `0b4315edf3a8449d940355717ad70fa7`.
- Corrected duration: `612458 ms`.
- Durable summary path: [2026-04-08-building-real-benchmark-result.json](/C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/codex-plan-followup/docs/superpowers/specs/2026-04-08-building-real-benchmark-result.json).
- Live runtime evidence was verified from `GET /api/v2/runs/0b4315edf3a8449d940355717ad70fa7` and `GET /api/v2/runs/0b4315edf3a8449d940355717ad70fa7/plan`.

## Micro AOI Diagnostic

- Diagnostic case `building_gitega_micro_agent` is now reproducible from the tracked manifest rather than `tmp/micro_building_case/manifest.json`.
- The micro case was rerun on `2026-04-12` against `http://127.0.0.1:8012`.
- Harness result: `failed` by timeout after `1200s`.
- Created run id: `8319c5bba5f64dd1a88ace78debaace5`.
- Live API status for that run still shows `phase="queued"` with only the `run_created` audit event.
- Interpretation: the old “missing local-only manifest” blocker is removed; the remaining blocker is full-loop worker/runtime alignment.

## Root Cause Split

- The original timeout conclusion for the official case was false. The corrected rerun confirms the case succeeds when the harness timeout is set to `1200s`.
- A second alignment issue showed up during this follow-up: port `8010` was already occupied by another local process, so a nominal `405` on that port would have been ambiguous evidence. The rerun therefore used a clean isolated port `8011`.
- Current benchmark guidance remains: treat API port alignment, worker freshness, and manifest timeout policy as first-class evidence, not operator assumptions.

## Interpretation

- The official case is viable on the current runtime and no longer supports the earlier “timeout means failure” conclusion.
- Real-data building benchmarks still require an explicit long timeout window. `180s` remains inappropriate for this class of case.
- The micro benchmark path is now reproducible from tracked repository state because manifest-driven clipping can derive the micro AOI from the tracked Gitega building inputs.
- What is still not reliable is the local full-loop execution path: the created run remains queued under the current worker/runtime setup.

## Branch Status

- Active worktree branch: `codex/micro-benchmark`.
- This branch currently contains:
  - refreshed benchmark evidence for the official building case,
  - manifest-driven micro benchmark materialization support,
  - updated `04-08` plan progress,
  - this follow-up summary,
  - explicit evidence that the remaining blocker is queued full-loop execution rather than missing inputs.
- Merge recommendation: merge after committing these code and doc updates, then decide whether to debug Celery/runtime alignment next or temporarily standardize micro validation on a different local execution mode.

## Recommended Next Thread Start

1. Open the worktree at `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\codex-micro-benchmark`.
2. Read:
   - [2026-04-08-benchmark-followup-summary.md](/C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/codex-micro-benchmark/docs/superpowers/specs/2026-04-08-benchmark-followup-summary.md)
   - [2026-04-08-building-real-benchmark-result.json](/C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/codex-micro-benchmark/docs/superpowers/specs/2026-04-08-building-real-benchmark-result.json)
   - [2026-04-08-building-micro-benchmark-result.json](/C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/codex-micro-benchmark/docs/superpowers/specs/2026-04-08-building-micro-benchmark-result.json)
3. If continuing benchmark work, keep using the isolated runtime command:

```powershell
python scripts/start_local.py --port 8012
```

4. If continuing the micro benchmark, inspect why run `8319c5bba5f64dd1a88ace78debaace5` remains queued instead of being consumed by the worker.
