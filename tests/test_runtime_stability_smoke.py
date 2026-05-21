from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts import smoke_runtime_stability


def test_smoke_runtime_stability_writes_summary(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []

    class StubService:
        def __init__(self, *, root_dir: Path, cache_dir: Path) -> None:
            self.root_dir = root_dir
            self.cache_dir = cache_dir

        def build_theme_evidence(self, **kwargs):
            job_type = kwargs["job_type"]
            calls.append(job_type)
            output_root = Path(kwargs["output_root"])
            output_root.mkdir(parents=True, exist_ok=True)
            artifact = output_root / f"{job_type}.gpkg"
            artifact.write_bytes(b"gpkg")
            return {
                "job_type": job_type,
                "claim_state": "national_scale_supported",
                "artifact_path": str(artifact),
                "tile_count": 1,
            }

    monkeypatch.setattr(smoke_runtime_stability, "TrackBNationalScaleService", StubService)

    output = smoke_runtime_stability.run_smoke(
        root_dir=tmp_path,
        output_root=tmp_path / "smoke",
        bbox=(0.0, 0.0, 1.0, 1.0),
        target_crs="EPSG:4326",
        themes=["building", "road", "water", "poi"],
    )

    assert calls == ["building", "road", "water", "poi"]
    assert output["overall_status"] == "passed"
    summary_path = tmp_path / "smoke" / "runtime_stability_summary.json"
    assert json.loads(summary_path.read_text(encoding="utf-8"))["overall_status"] == "passed"


def test_smoke_runtime_stability_cli_imports_from_repo_root() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/smoke_runtime_stability.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--root-dir" in result.stdout
