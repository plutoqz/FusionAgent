from __future__ import annotations

import json
from pathlib import Path

from schemas.scenario_checkpoint import ScenarioCheckpoint


def checkpoint_path(output_dir: Path) -> Path:
    return output_dir / "scenario_checkpoint.json"


def write_scenario_checkpoint(path: Path, checkpoint: ScenarioCheckpoint) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(checkpoint.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def load_scenario_checkpoint(path: Path) -> ScenarioCheckpoint:
    return ScenarioCheckpoint.model_validate_json(path.read_text(encoding="utf-8"))
