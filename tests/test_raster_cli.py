from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from utils.raster_cli import gdalinfo_json, resolve_gdalinfo_executable


def test_resolve_gdalinfo_executable_prefers_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEOFUSION_GDALINFO", r"C:\tools\gdalinfo.exe")

    assert resolve_gdalinfo_executable() == r"C:\tools\gdalinfo.exe"


def test_gdalinfo_json_invokes_cli_and_parses_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    raster_path = tmp_path / "sample.tif"
    raster_path.write_bytes(b"raster")

    monkeypatch.setattr("utils.raster_cli.resolve_gdalinfo_executable", lambda: "gdalinfo")

    def _run(command, check, capture_output, text):  # noqa: ANN001
        assert command == ["gdalinfo", "-json", str(raster_path)]
        assert check is True
        assert capture_output is True
        assert text is True
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=json.dumps({"bands": [{"description": "building presence"}]}),
            stderr="",
        )

    monkeypatch.setattr("utils.raster_cli.subprocess.run", _run)

    payload = gdalinfo_json(raster_path)

    assert payload["bands"][0]["description"] == "building presence"


def test_resolve_gdalinfo_executable_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEOFUSION_GDALINFO", raising=False)
    monkeypatch.setattr("utils.raster_cli.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "utils.raster_cli.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr=""),
    )

    with pytest.raises(FileNotFoundError):
        resolve_gdalinfo_executable()
