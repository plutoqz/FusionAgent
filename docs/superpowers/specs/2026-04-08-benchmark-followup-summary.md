# Benchmark Follow-Up Summary

## Corrected Findings

- Official real-data building case `building_gitega_osm_vs_google_agent` was rerun on `2026-04-12` on an isolated runtime at `http://127.0.0.1:8011`.
- Corrected result: `passed`.
- Corrected run id: `0b4315edf3a8449d940355717ad70fa7`.
- Corrected duration: `612458 ms`.
- Durable summary path: [2026-04-08-building-real-benchmark-result.json](/E:/vscode/fusionAgent/docs/superpowers/specs/2026-04-08-building-real-benchmark-result.json).
- Live runtime evidence was verified from `GET /api/v2/runs/0b4315edf3a8449d940355717ad70fa7` and `GET /api/v2/runs/0b4315edf3a8449d940355717ad70fa7/plan`.

## Micro AOI Diagnostic

- Diagnostic case `building_gitega_micro_agent` is now reproducible from the tracked manifest rather than `tmp/micro_building_case/manifest.json`.
- The micro case was rerun on `2026-04-12` against `http://127.0.0.1:8012`.
- Harness result: `failed` by timeout after `1200s`.
- Created run id: `8319c5bba5f64dd1a88ace78debaace5`.
- Live API status for that run still shows `phase="queued"` with only the `run_created` audit event.
- Historical interpretation on `2026-04-12`: the old “missing local-only manifest” blocker was removed, but that specific local runtime still had a worker/runtime alignment problem.

## Clean Rerun On `2026-04-16`

- The same micro case was rerun on a clean isolated runtime at `http://127.0.0.1:8010`.
- Runtime shape: `python scripts/start_local.py --port 8010` with `GEOFUSION_KG_BACKEND=neo4j`, `GEOFUSION_LLM_PROVIDER=openai`, and `GEOFUSION_CELERY_EAGER=0`.
- Result: `passed`.
- New run id: `7117ef6fd95a44aa97d438cb7b3a9bee`.
- Duration: `194896 ms`.
- Durable result path: [2026-04-16-building-micro-alignment-result.json](/E:/vscode/fusionAgent/docs/superpowers/specs/2026-04-16-building-micro-alignment-result.json).

## Root Cause Split

- The original timeout conclusion for the official case was false. The corrected rerun confirms the case succeeds when the harness timeout is set to `1200s`.
- A second alignment issue showed up during this follow-up: port `8010` was already occupied by another local process, so a nominal `405` on that port would have been ambiguous evidence. The rerun therefore used a clean isolated port `8011`.
- The later clean rerun on `2026-04-16` shows the micro task-driven path is not permanently broken in current `main`; the earlier queued state was a runtime alignment drift in that older local setup, not a standing defect in the manifest-driven micro benchmark path.
- Current benchmark guidance remains: treat API port alignment, worker freshness, and manifest timeout policy as first-class evidence, not operator assumptions.

## Interpretation

- The official case is viable on the current runtime and no longer supports the earlier “timeout means failure” conclusion.
- Real-data building benchmarks still require an explicit long timeout window. `180s` remains inappropriate for this class of case.
- The micro benchmark path is now reproducible from tracked repository state because manifest-driven clipping can derive the micro AOI from the tracked Gitega building inputs.
- The micro benchmark also passes on a clean isolated `8010` runtime in current `main`, so the earlier queued run should now be treated as historical environment drift rather than the current expected outcome.

## Current Repo Status

- The benchmark evidence and manifest-driven micro benchmark support are now merged into `main`.
- Durable tracked artifacts for this follow-up live under `docs/superpowers/specs/` in the main repo rather than an isolated worktree.
- The `2026-04-12` queued micro run remains useful as a historical alignment failure, but it is no longer the current repo-level blocker after the clean `2026-04-16` rerun passed.

## Recommended Next Thread Start

1. Open the repo at `E:\vscode\fusionAgent`.
2. Read:
   - [2026-04-08-benchmark-followup-summary.md](/E:/vscode/fusionAgent/docs/superpowers/specs/2026-04-08-benchmark-followup-summary.md)
   - [2026-04-08-building-real-benchmark-result.json](/E:/vscode/fusionAgent/docs/superpowers/specs/2026-04-08-building-real-benchmark-result.json)
   - [2026-04-08-building-micro-benchmark-result.json](/E:/vscode/fusionAgent/docs/superpowers/specs/2026-04-08-building-micro-benchmark-result.json)
   - [2026-04-16-building-micro-alignment-result.json](/E:/vscode/fusionAgent/docs/superpowers/specs/2026-04-16-building-micro-alignment-result.json)
3. If continuing benchmark work, keep using the isolated runtime command:

```powershell
python scripts/start_local.py --port 8010
```

4. If continuing the micro benchmark, treat run `8319c5bba5f64dd1a88ace78debaace5` as a historical misalignment case and use the `2026-04-16` clean rerun as the current baseline.
