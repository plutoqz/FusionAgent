from __future__ import annotations

import os
from pathlib import Path


DEFAULT_DATA_REPOSITORY_ROOT = Path("D:/fyx/\u4efb\u52a1")
DEFAULT_DOWNLOAD_ROOT = DEFAULT_DATA_REPOSITORY_ROOT / "fusionagent_downloads"
DEFAULT_OUTPUT_ROOT = Path("D:/fyx/data")
DEFAULT_RUNS_ROOT = DEFAULT_OUTPUT_ROOT / "fusionagent_runs"
DEFAULT_SCENARIO_OUTPUT_ROOT = DEFAULT_OUTPUT_ROOT / "fusionagent_scenarios"


def resolve_data_repository_root(requested_root: str | Path | None = None) -> Path:
    return _resolve_path(
        requested_root,
        env_name="GEOFUSION_DATA_REPOSITORY_ROOT",
        default=DEFAULT_DATA_REPOSITORY_ROOT,
    )


def resolve_download_root(
    requested_root: str | Path | None = None,
    *,
    data_repository_root: str | Path | None = None,
) -> Path:
    data_root = Path(data_repository_root) if data_repository_root is not None else resolve_data_repository_root()
    return _resolve_path(
        requested_root,
        env_name="GEOFUSION_DOWNLOAD_ROOT",
        default=data_root / DEFAULT_DOWNLOAD_ROOT.name,
    )


def resolve_output_root(requested_root: str | Path | None = None) -> Path:
    return _resolve_path(
        requested_root,
        env_name="GEOFUSION_OUTPUT_ROOT",
        default=DEFAULT_OUTPUT_ROOT,
    )


def resolve_runs_root(requested_root: str | Path | None = None) -> Path:
    if requested_root is not None:
        return Path(requested_root).expanduser().resolve()

    configured = _env_path("GEOFUSION_RUNS_ROOT")
    if configured is not None:
        return configured

    return resolve_output_root() / DEFAULT_RUNS_ROOT.name


def resolve_scenario_default_output_root(requested_root: str | Path | None = None) -> Path:
    if requested_root is not None:
        return Path(requested_root).expanduser().resolve()

    configured = _env_path("GEOFUSION_SCENARIO_OUTPUT_ROOT")
    if configured is not None:
        return configured

    return resolve_output_root() / DEFAULT_SCENARIO_OUTPUT_ROOT.name


def _resolve_path(requested_root: str | Path | None, *, env_name: str, default: Path) -> Path:
    if requested_root is not None:
        return Path(requested_root).expanduser().resolve()

    configured = _env_path(env_name)
    if configured is not None:
        return configured

    return default


def _env_path(name: str) -> Path | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return Path(value.strip()).expanduser().resolve()
