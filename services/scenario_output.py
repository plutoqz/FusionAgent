from __future__ import annotations

from pathlib import Path

from services.runtime_paths import (
    DEFAULT_SCENARIO_OUTPUT_ROOT,
    resolve_scenario_default_output_root,
)


def resolve_scenario_output_root(requested_output_root: str | None) -> Path:
    requested = requested_output_root.strip() if requested_output_root else None
    return resolve_scenario_default_output_root(requested)
