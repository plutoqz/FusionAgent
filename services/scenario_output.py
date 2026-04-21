from __future__ import annotations

import os
from pathlib import Path


DEFAULT_SCENARIO_OUTPUT_ROOT = Path(r"E:\fyx\data\fusionagentTEST")


def resolve_scenario_output_root(requested_output_root: str | None) -> Path:
    if requested_output_root and requested_output_root.strip():
        return Path(requested_output_root).expanduser().resolve()

    configured = os.getenv("GEOFUSION_SCENARIO_OUTPUT_ROOT")
    if configured and configured.strip():
        return Path(configured).expanduser().resolve()

    return DEFAULT_SCENARIO_OUTPUT_ROOT
