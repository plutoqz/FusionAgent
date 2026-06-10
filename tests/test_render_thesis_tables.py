from __future__ import annotations

import json
from pathlib import Path

from scripts.render_thesis_tables import render_tables


def test_render_tables_references_registered_experiments(tmp_path: Path) -> None:
    manifest = tmp_path / "exp.json"
    manifest.write_text(
        json.dumps(
            {
                "experiment_id": "exp-a2b",
                "output_dir": "runs/exp-a2b",
                "commit_sha": "abc",
                "seed_hash": "seed",
                "runtime_settings_hash": "settings",
                "metric_definition_hash": "metrics",
                "files": [],
            }
        ),
        encoding="utf-8",
    )
    output_md = tmp_path / "tables.md"

    payload = render_tables([manifest], output_markdown=output_md)

    assert payload["experiment_count"] == 1
    assert "| exp-a2b |" in output_md.read_text(encoding="utf-8")
