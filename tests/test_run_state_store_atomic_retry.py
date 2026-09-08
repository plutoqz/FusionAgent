from pathlib import Path

import pytest

from services.run_state_store import _atomic_write_text


@pytest.mark.parametrize("transient", [True, False])
def test_windows_replace_retry_is_bounded(tmp_path, monkeypatch, transient):
    target = tmp_path / "run.json"
    target.write_text("old")
    original = Path.replace
    calls = []
    monkeypatch.setattr("services.run_state_store.time.sleep", lambda seconds: None)

    def replace(path, destination):
        calls.append(path)
        if not transient or len(calls) < 3:
            error = PermissionError("simulated file lock")
            error.winerror = 5
            raise error
        return original(path, destination)

    monkeypatch.setattr(Path, "replace", replace)
    if transient:
        _atomic_write_text(target, "new")
        assert target.read_text() == "new"
        assert len(calls) == 3
    else:
        with pytest.raises(PermissionError):
            _atomic_write_text(target, "new")
        assert target.read_text() == "old"
        assert len(calls) == 4
    assert not list(tmp_path.glob("*.tmp"))


def test_other_permission_error_is_not_retried(tmp_path, monkeypatch):
    calls = []

    def replace(path, destination):
        calls.append(path)
        raise PermissionError("not a Windows sharing error")

    monkeypatch.setattr(Path, "replace", replace)
    with pytest.raises(PermissionError):
        _atomic_write_text(tmp_path / "run.json", "new")
    assert len(calls) == 1
