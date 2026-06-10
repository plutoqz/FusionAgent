from __future__ import annotations

from pathlib import Path

from services.windows_runtime_readiness_service import (
    classify_windows_runtime_readiness,
)


def test_windows_runtime_ready_when_required_paths_exist(tmp_path: Path) -> None:
    required = []
    for name in ("start_local.py", "watch_scenario_inbox.py"):
        path = tmp_path / name
        path.write_text("print('ok')", encoding="utf-8")
        required.append(path)
    runs_dir = tmp_path / "runs"

    report = classify_windows_runtime_readiness(
        required_paths=required,
        writable_dirs=[runs_dir],
        free_disk_gb=10.0,
    )

    assert report["status"] == "ready"
    assert report["manual_intervention_required"] is False


def test_windows_runtime_degraded_when_required_script_missing(
    tmp_path: Path,
) -> None:
    report = classify_windows_runtime_readiness(
        required_paths=[tmp_path / "missing.py"],
        writable_dirs=[tmp_path / "runs"],
        free_disk_gb=10.0,
    )

    assert report["status"] == "degraded"
    assert report["manual_intervention_required"] is True
    assert report["missing_paths"] == [str(tmp_path / "missing.py")]
