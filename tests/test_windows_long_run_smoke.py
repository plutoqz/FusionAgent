from __future__ import annotations

from pathlib import Path

from scripts.run_windows_long_run_smoke import run_long_run_smoke


def test_long_run_smoke_dry_run_writes_summary(tmp_path: Path) -> None:
    summary = run_long_run_smoke(output_dir=tmp_path / "out", iterations=2, dry_run=True)

    assert summary["iterations"] == 2
    assert summary["dry_run"] is True
    assert summary["status"] == "passed"
    assert (tmp_path / "out" / "windows_long_run_smoke.json").exists()
