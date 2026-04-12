# Benchmark Follow-Up Summary

## Corrected Findings

- Official real-data building case `building_gitega_osm_vs_google_agent` was rerun on `2026-04-12` on an isolated runtime at `http://127.0.0.1:8011`.
- Corrected result: `passed`.
- Corrected run id: `0b4315edf3a8449d940355717ad70fa7`.
- Corrected duration: `612458 ms`.
- Durable summary path: [2026-04-08-building-real-benchmark-result.json](/C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/codex-plan-followup/docs/superpowers/specs/2026-04-08-building-real-benchmark-result.json).
- Live runtime evidence was verified from `GET /api/v2/runs/0b4315edf3a8449d940355717ad70fa7` and `GET /api/v2/runs/0b4315edf3a8449d940355717ad70fa7/plan`.

## Micro AOI Diagnostic

- Planned diagnostic case `building_gitega_micro_agent` was not rerun in this worktree.
- Blocker: the plan expected an existing local-only file `tmp/micro_building_case/manifest.json`, but that file is absent in the current repository state.
- The micro benchmark JSON has been refreshed to record this blocked status instead of preserving stale success output from an older worktree.

## Root Cause Split

- The original timeout conclusion for the official case was false. The corrected rerun confirms the case succeeds when the harness timeout is set to `1200s`.
- A second alignment issue showed up during this follow-up: port `8010` was already occupied by another local process, so a nominal `405` on that port would have been ambiguous evidence. The rerun therefore used a clean isolated port `8011`.
- Current benchmark guidance remains: treat API port alignment, worker freshness, and manifest timeout policy as first-class evidence, not operator assumptions.

## Interpretation

- The official case is viable on the current runtime and no longer supports the earlier “timeout means failure” conclusion.
- Real-data building benchmarks still require an explicit long timeout window. `180s` remains inappropriate for this class of case.
- The micro benchmark path is not reproducible from tracked repository state alone; it depends on local-only inputs that must be restored before that part of the plan can be completed honestly.

## Branch Status

- Active worktree branch: `codex/plan-followup`.
- This branch currently contains:
  - refreshed benchmark evidence for the official building case,
  - updated `04-08` plan progress,
  - this follow-up summary,
  - explicit recording that the micro diagnostic rerun is blocked on missing local-only inputs.
- Merge recommendation: merge after committing these refreshed docs and evidence updates, then decide in a later thread whether to restore/regenerate the micro benchmark inputs.

## Recommended Next Thread Start

1. Open the worktree at `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\codex-plan-followup`.
2. Read:
   - [2026-04-08-benchmark-followup-summary.md](/C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/codex-plan-followup/docs/superpowers/specs/2026-04-08-benchmark-followup-summary.md)
   - [2026-04-08-building-real-benchmark-result.json](/C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/codex-plan-followup/docs/superpowers/specs/2026-04-08-building-real-benchmark-result.json)
   - [2026-04-08-building-micro-benchmark-result.json](/C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/codex-plan-followup/docs/superpowers/specs/2026-04-08-building-micro-benchmark-result.json)
3. If continuing benchmark work, keep using the isolated runtime command:

```powershell
python scripts/start_local.py --port 8011
```

4. Before claiming the micro benchmark is reproducible, first restore or regenerate `tmp/micro_building_case/manifest.json`.
