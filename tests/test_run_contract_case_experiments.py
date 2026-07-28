from __future__ import annotations

from pathlib import Path

from scripts import run_contract_case_experiments as runner


def test_runtime_environment_snapshot_freezes_reproducibility_context(tmp_path: Path) -> None:
    experiment_dir = tmp_path / "experiment"
    runtime_dir = experiment_dir / "runtime"
    runtime_dir.mkdir(parents=True)

    snapshot = runner._runtime_environment_snapshot(
        experiment_dir=experiment_dir,
        runtime_dir=runtime_dir,
    )

    assert snapshot["python"]["executable"]
    assert snapshot["python"]["version"]
    assert snapshot["operating_system"]["system"]
    assert "proj_runtime" in snapshot["geospatial_runtime"] or "proj_runtime_error" in snapshot["geospatial_runtime"]
    assert "gdal_runtime" in snapshot["geospatial_runtime"] or "gdal_runtime_error" in snapshot["geospatial_runtime"]
    assert snapshot["python_distributions"]
    assert snapshot["requirements"]["sha256"]
    assert snapshot["server_environment"]["GEOFUSION_KG_BACKEND"] == "memory"
    assert snapshot["server_environment"]["GEOFUSION_LLM_PROVIDER"] == "mock"


def test_git_worktree_state_treats_untracked_files_as_dirty(monkeypatch) -> None:
    def fake_check_output(command, **kwargs):
        if command[1] == "status":
            return "?? untracked.txt\n"
        return b""

    monkeypatch.setattr(runner.subprocess, "check_output", fake_check_output)

    state = runner._git_worktree_state()

    assert state["dirty"] is True
    assert state["diff_sha256"]
    assert state["status_porcelain"] == ["?? untracked.txt"]


def test_main_returns_nonzero_when_contract_cases_fail(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(runner, "run_manifest", lambda **_kwargs: {"all_cases_passed": False})

    exit_code = runner.main(["--experiment-dir", str(tmp_path)])

    assert exit_code == 1
