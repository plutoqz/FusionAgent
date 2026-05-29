# Targets 1,2,5,7-9 Gap Closure Evidence

## Capability State

- Target 1: unattended local operation is supported through scheduled `task_driven_auto` runs, local scenario inbox processing, recovery tick scanning, and unattended runtime snapshots.
- Target 2: building vector fusion remains the core capability; height raster participation is auditable when raster sources appear in the source semantic contract or component coverage.
- Target 5: POI fusion is AOI-bounded OSM + GNS/GeoNames vector fusion.
- Target 7: automatic data download, cache reuse, clipping, version tokens, provider attempts, and fault classes are recorded through `source_materialization_manifest.json`.
- Target 8: run reports include process evaluation, result evaluation, source coverage, quality summary, evidence readiness, and boundary statements.
- Target 9: recovery hints classify recoverable failures, recovery action, operator action, failure category, and worker history evidence.

## Boundaries

- Target 10 remains bounded policy hints only; no automatic model, policy, or source catalog mutation is claimed.
- AOI-bounded OSM + GNS/GeoNames POI fusion is supported; unbounded POI entity alignment remains unsupported.
- Provider availability is external. Download manifests record cache behavior, retry/fault evidence, and source mode but do not guarantee live provider uptime.
- Long-running operation depends on process supervision and scheduler uptime supplied by the deployment environment.

## Verification Commands

- `py -3.13 -m pytest -q tests/test_unattended_run_monitor_service.py tests/test_worker_orchestration.py tests/test_watch_scenario_inbox.py`
- `py -3.13 -m pytest -q tests/test_report_quality_service.py tests/test_run_report_service.py`
- `py -3.13 -m pytest -q tests/test_source_materialization_manifest_service.py tests/test_input_acquisition_service.py tests/test_input_acquisition_faults.py`
- `py -3.13 -m pytest -q tests/test_run_recovery_service.py tests/test_run_recovery_executor.py tests/test_worker_recovery_tick.py`
- `py -3.13 -m pytest -q tests/test_targets_1_2_5_7_9_gap_closure_evidence.py`
