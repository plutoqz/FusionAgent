from __future__ import annotations

import json
from pathlib import Path

from scripts.freeze_experiment_evidence import freeze_experiment


def test_freeze_experiment_writes_manifest(tmp_path: Path) -> None:
    output_dir = tmp_path / "exp"
    output_dir.mkdir()
    (output_dir / "result.json").write_text('{"metric": 1}', encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"

    manifest = freeze_experiment(
        experiment_id="exp-001",
        output_dir=output_dir,
        output_json=manifest_path,
        commit_sha="abc123",
        seed_hash="seed",
        runtime_settings_hash="settings",
        metric_definition_hash="metrics",
    )

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest.experiment_id == "exp-001"
    assert payload["files"][0]["relative_path"] == "result.json"
