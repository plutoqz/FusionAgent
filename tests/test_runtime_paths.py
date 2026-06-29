from pathlib import Path

from services.runtime_paths import (
    DEFAULT_DATA_REPOSITORY_ROOT,
    DEFAULT_DOWNLOAD_ROOT,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_RUNS_ROOT,
    DEFAULT_SCENARIO_OUTPUT_ROOT,
    resolve_data_repository_root,
    resolve_download_root,
    resolve_output_root,
    resolve_runs_root,
    resolve_scenario_default_output_root,
)


def test_default_engineering_storage_roots_are_on_fyx_roots(monkeypatch) -> None:
    for key in [
        "GEOFUSION_DATA_REPOSITORY_ROOT",
        "GEOFUSION_DOWNLOAD_ROOT",
        "GEOFUSION_OUTPUT_ROOT",
        "GEOFUSION_RUNS_ROOT",
        "GEOFUSION_SCENARIO_OUTPUT_ROOT",
    ]:
        monkeypatch.delenv(key, raising=False)

    assert resolve_data_repository_root() == DEFAULT_DATA_REPOSITORY_ROOT
    assert resolve_download_root() == DEFAULT_DOWNLOAD_ROOT
    assert resolve_output_root() == DEFAULT_OUTPUT_ROOT
    assert resolve_runs_root() == DEFAULT_RUNS_ROOT
    assert resolve_scenario_default_output_root() == DEFAULT_SCENARIO_OUTPUT_ROOT


def test_output_root_override_moves_run_and_scenario_defaults(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GEOFUSION_RUNS_ROOT", raising=False)
    monkeypatch.delenv("GEOFUSION_SCENARIO_OUTPUT_ROOT", raising=False)
    monkeypatch.setenv("GEOFUSION_OUTPUT_ROOT", str(tmp_path / "outputs"))

    assert resolve_runs_root() == tmp_path / "outputs" / "fusionagent_runs"
    assert resolve_scenario_default_output_root() == tmp_path / "outputs" / "fusionagent_scenarios"


def test_download_root_defaults_to_repository_subfolder(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GEOFUSION_DOWNLOAD_ROOT", raising=False)
    monkeypatch.setenv("GEOFUSION_DATA_REPOSITORY_ROOT", str(tmp_path / "repo"))

    assert resolve_download_root() == tmp_path / "repo" / "fusionagent_downloads"
