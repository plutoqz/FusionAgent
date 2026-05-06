from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


def resolve_gdalinfo_executable() -> str:
    explicit = os.getenv("GEOFUSION_GDALINFO")
    if explicit:
        return explicit

    for candidate in ("gdalinfo", "gdalinfo.exe"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved

    probe = subprocess.run(
        ["where", "gdalinfo"],
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode == 0:
        for line in probe.stdout.splitlines():
            text = line.strip()
            if text:
                return text

    raise FileNotFoundError("gdalinfo executable not found on PATH")


def gdalinfo_json(path: Path) -> dict[str, object]:
    raster_path = Path(path)
    completed = subprocess.run(
        [resolve_gdalinfo_executable(), "-json", str(raster_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)
