# Benchmark Follow-Up Summary

## Corrected Findings

- Official real-data building case `building_gitega_osm_vs_google_agent` has now been re-run on the isolated runtime at `http://127.0.0.1:8010`.
- Corrected result: `passed`.
- Corrected run id: `769d9740741b45b98dbb28f89c8586d0`.
- Corrected duration: `565720 ms` from [2026-04-08-building-real-benchmark-result.json](C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/parameter-defaults-benchmark/docs/superpowers/specs/2026-04-08-building-real-benchmark-result.json).
- Runtime evidence: [run.json](C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/parameter-defaults-benchmark/runs/769d9740741b45b98dbb28f89c8586d0/run.json).

## Micro AOI Diagnostic

- Diagnostic case `building_gitega_micro_agent` also passed on the same isolated runtime.
- Diagnostic run id: `29a05db92d144f7bb60bbbdb280344c6`.
- Diagnostic duration: `56345 ms`.
- Diagnostic artifact size: `6240282` bytes.
- Runtime evidence: [run.json](C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/parameter-defaults-benchmark/runs/29a05db92d144f7bb60bbbdb280344c6/run.json).
- The diagnostic micro-AOI inputs were materialized under a local-only `tmp/micro_building_case/` workspace during the rerun. Those temporary shapefile artifacts are intentionally not retained in git; the durable evidence is the benchmark result JSON plus the recorded runtime run id above.

## Root Cause Split

- The original timeout conclusion for run `57e88999357149d2a48f3164a409aa2c` was false. The run actually succeeded after about `579s`; the failure was the harness timeout window being only `180s`.
- The later micro-case timeout was a different issue. The worker had received the task but failed before execution because `AgentRunService._build_logger(...)` created a `FileHandler` before ensuring the `logs/` directory existed.
- That logger-directory bug is now covered by a regression test in [test_agent_run_service_enhancements.py](C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/parameter-defaults-benchmark/tests/test_agent_run_service_enhancements.py) and fixed in [agent_run_service.py](C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/parameter-defaults-benchmark/services/agent_run_service.py).

## Interpretation

- The official case is already clipped data, not a national-scale full-layer run.
- Small-area clipping does materially reduce runtime in the current building pipeline: roughly `565.7s` down to `56.3s` in this follow-up.
- The first engineering change still needed for stable benchmarking is not algorithm refactoring; it is adopting a realistic harness timeout for real-data building cases and keeping API / worker / output directories aligned.
- That timeout should now live in the manifest itself for known slow real-data building cases, instead of depending only on operator memory.

## 2026-04-09 Continuation

- The same official case `building_gitega_osm_vs_google_agent` was rerun again in `codex/phase1-task1-1` after restoring the local `E:\vscode\fusionAgent\Data` workspace inputs.
- Result: `passed`.
- Run id: `92fa35b6f1014d67a8e15fe2a1fe5db3`.
- Duration: `592549 ms`.
- Harness summary path: `tmp/eval/real-evidence-summary.json`.
- This rerun also exposed and fixed a second timeout-budget bug: `utils/local_smoke.py` had been hard-coding `urllib` request timeouts to `30s`, which could still break real-data evidence runs even when the manifest timeout was correctly set to `1200`.
- That HTTP-timeout fix is now covered by `tests/test_local_smoke_helpers.py`.

## Branch Status

- Active worktree branch: `codex/parameter-defaults-benchmark`.
- This branch now contains:
  - the earlier parameter-binding / harness changes,
  - the corrected official benchmark result,
  - the micro benchmark result,
  - the logger-directory bug fix and regression test,
  - this handoff summary,
  - the harness follow-up needed to keep the fail-fast benchmark test injectable and stable.
- Merge recommendation right now: merge only after the follow-up is committed, the temporary micro-AOI artifacts are cleaned out of the worktree, and the targeted benchmark-related tests are rerun cleanly.

## Recommended Next Thread Start

1. Open the worktree at `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent\parameter-defaults-benchmark`.
2. Read:
   - [2026-04-08-benchmark-followup-summary.md](C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/parameter-defaults-benchmark/docs/superpowers/specs/2026-04-08-benchmark-followup-summary.md)
   - [2026-04-08-building-real-benchmark-result.json](C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/parameter-defaults-benchmark/docs/superpowers/specs/2026-04-08-building-real-benchmark-result.json)
   - [2026-04-08-building-micro-benchmark-result.json](C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/parameter-defaults-benchmark/docs/superpowers/specs/2026-04-08-building-micro-benchmark-result.json)
3. Check `git status` and confirm the worktree is clean except for any intentional new follow-up edits before deciding whether to:
   - commit this follow-up as a separate benchmark-correction commit, or
   - squash it into the benchmark branch before review.
4. If continuing benchmark work, keep using the isolated runtime command:

```powershell
$env:GEOFUSION_DEPENDENCY_FILE='E:\vscode\fusionAgent\依赖.txt'
python scripts/start_local.py --port 8010
```

5. For future real-data building runs, keep the real-data manifest `timeout_sec` at `1200` for the known slow building cases unless you intentionally want to test a stricter SLA.
6. If you override the CLI `--timeout`, remember that manifest case-level `timeout_sec` is now the authoritative value for those explicitly configured cases.
