from __future__ import annotations

from pathlib import Path

from schemas.agent import RunPhase, RunStatus, RunTrigger, RunTriggerType
from schemas.fusion import JobType
from services.run_state_store import RunStateStore


def test_run_state_store_persists_status_with_atomic_replace(tmp_path, monkeypatch) -> None:
    store = RunStateStore(tmp_path / "runs")
    status = RunStatus(
        run_id="run-atomic-status",
        job_type=JobType.road,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="road", spatial_extent="bbox(0,0,1,1)"),
        phase=RunPhase.running,
        progress=50,
        target_crs="EPSG:4326",
        created_at="2026-07-02T00:00:00+00:00",
        updated_at="2026-07-02T00:00:00+00:00",
    )
    original_write_text = Path.write_text

    def guarded_write_text(self, *args, **kwargs):
        if self.name == "run.json":
            raise AssertionError("run.json must not be overwritten directly")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", guarded_write_text)

    store.persist_status(status)
    loaded = store.load_status(status.run_id)

    assert loaded is not None
    assert loaded.run_id == status.run_id
    assert loaded.progress == 50
