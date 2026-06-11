from __future__ import annotations

from pathlib import Path

from services.experiment_evidence_service import (
    build_experiment_manifest,
    verify_experiment_manifest,
)


def test_experiment_manifest_detects_output_mutation(tmp_path: Path) -> None:
    output_dir = tmp_path / "experiment"
    output_dir.mkdir()
    result = output_dir / "result.json"
    result.write_text('{"ok": true}', encoding="utf-8")

    manifest = build_experiment_manifest(
        experiment_id="exp-test",
        output_dir=output_dir,
        commit_sha="abc123",
        seed_hash="seed",
        runtime_settings_hash="settings",
        metric_definition_hash="metrics",
    )
    assert verify_experiment_manifest(manifest) == []

    result.write_text('{"ok": false}', encoding="utf-8")

    failures = verify_experiment_manifest(manifest)
    assert any("hash changed" in failure for failure in failures)
