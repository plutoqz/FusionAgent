from __future__ import annotations

from pathlib import Path
from typing import Any

MIN_FREE_DISK_GB = 2.0


def classify_windows_runtime_readiness(
    *,
    required_paths: list[Path],
    writable_dirs: list[Path],
    free_disk_gb: float,
) -> dict[str, Any]:
    missing_paths = [str(path) for path in required_paths if not Path(path).exists()]
    unwritable_dirs = []
    for directory in writable_dirs:
        path = Path(directory)
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".fusionagent_write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError:
            unwritable_dirs.append(str(path))
    disk_ok = float(free_disk_gb) >= MIN_FREE_DISK_GB
    status = "ready" if not missing_paths and not unwritable_dirs and disk_ok else "degraded"
    return {
        "status": status,
        "manual_intervention_required": status != "ready",
        "missing_paths": missing_paths,
        "unwritable_dirs": unwritable_dirs,
        "free_disk_gb": float(free_disk_gb),
        "min_free_disk_gb": MIN_FREE_DISK_GB,
        "windows_scope": "current Windows local runtime only",
    }
