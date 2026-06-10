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

## Recovery

Use the recovery scan before manually deleting or rerunning stale runs. Runs that reference blocked algorithms after Freeze A require manual review.

## Evidence

Doctor and long-run smoke outputs are system operability evidence. They are not fusion quality evidence and should not enter quality tables.
