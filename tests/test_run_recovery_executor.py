from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.run_recovery_executor import RecoveryLeaseStore, RunRecoveryExecutor


def test_recovery_lease_blocks_double_acquire(tmp_path: Path) -> None:
    store = RecoveryLeaseStore(runs_root=tmp_path, lease_seconds=60, owner="worker-a")

    first = store.acquire("run-1", "redispatch_from_execution")
    second = store.acquire("run-1", "redispatch_from_execution")

    assert first.acquired is True
    assert second.acquired is False
    assert second.reason == "lease_active"
    assert (tmp_path / "run-1" / "recovery.lock.json").exists()


def test_recovery_lease_allows_expired_reacquire(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-1"
    run_dir.mkdir(parents=True)
    expired_at = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    (run_dir / "recovery.lock.json").write_text(
        (
            '{"run_id":"run-1","owner":"old","action":"redispatch_from_execution",'
            f'"expires_at":"{expired_at}"}}'
        ),
        encoding="utf-8",
    )
    store = RecoveryLeaseStore(runs_root=tmp_path, lease_seconds=60, owner="worker-b")

    result = store.acquire("run-1", "redispatch_from_execution")

    assert result.acquired is True
    payload = (run_dir / "recovery.lock.json").read_text(encoding="utf-8")
    assert '"owner": "worker-b"' in payload


def test_recovery_lease_release_marks_success(tmp_path: Path) -> None:
    store = RecoveryLeaseStore(runs_root=tmp_path, lease_seconds=60, owner="worker-a")
    lease = store.acquire("run-1", "redispatch_full_run")

    store.release(lease, status="succeeded", details={"phase": "succeeded"})

    assert not (tmp_path / "run-1" / "recovery.lock.json").exists()
    history = (tmp_path / "run-1" / "recovery.history.jsonl").read_text(encoding="utf-8")
    assert '"status": "succeeded"' in history
    assert '"phase": "succeeded"' in history


class _StubRunService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def collect_recoverable_runs(self, stale_after_seconds: int) -> list[dict[str, object]]:
        assert stale_after_seconds == 300
        return [
            {
                "run_id": "run-stale",
                "recovery_action": "redispatch_from_execution",
                "checkpoint": {"stage": "execution", "plan_revision": 1},
            }
        ]

    def resume_run_from_checkpoint(self, run_id: str, recovery_action: str) -> dict[str, object]:
        self.calls.append((run_id, recovery_action))
        return {"run_id": run_id, "phase": "succeeded"}


def test_recovery_executor_resumes_stale_runs(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-stale"
    run_dir.mkdir(parents=True)
    service = _StubRunService()
    executor = RunRecoveryExecutor(
        runs_root=tmp_path,
        agent_run_service=service,
        lease_seconds=60,
        owner="test-worker",
    )

    result = executor.recover_stale_runs(stale_after_seconds=300)

    assert result["attempted"] == 1
    assert result["recovered"] == 1
    assert service.calls == [("run-stale", "redispatch_from_execution")]
    history = (run_dir / "recovery.history.jsonl").read_text(encoding="utf-8")
    assert '"status": "succeeded"' in history


def test_recovery_executor_skips_active_lease(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-stale"
    run_dir.mkdir(parents=True)
    (run_dir / "recovery.lock.json").write_text(
        json.dumps(
            {
                "run_id": "run-stale",
                "owner": "other-worker",
                "action": "redispatch_from_execution",
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    service = _StubRunService()
    executor = RunRecoveryExecutor(runs_root=tmp_path, agent_run_service=service, owner="test-worker")

    result = executor.recover_stale_runs(stale_after_seconds=300)

    assert result["attempted"] == 0
    assert result["skipped"] == 1
    assert service.calls == []
