from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


RECOVERABLE_ACTIONS = {
    "redispatch_full_run",
    "redispatch_from_validation",
    "redispatch_from_execution",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class RecoveryLease:
    run_id: str
    action: str
    owner: str
    path: Path
    acquired: bool
    reason: str = ""
    expires_at: str | None = None


@dataclass
class RecoveryLeaseStore:
    runs_root: Path
    lease_seconds: int = 300
    owner: str = field(default_factory=lambda: f"{socket.gethostname()}:{os.getpid()}")

    def acquire(self, run_id: str, action: str) -> RecoveryLease:
        run_dir = Path(self.runs_root) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        lock_path = run_dir / "recovery.lock.json"
        now = _utc_now()
        expires_at = now + timedelta(seconds=max(1, int(self.lease_seconds)))

        if lock_path.exists():
            existing = self._read_json(lock_path)
            existing_expires_at = _parse_time(existing.get("expires_at"))
            if existing_expires_at is not None and existing_expires_at > now:
                return RecoveryLease(
                    run_id=run_id,
                    action=action,
                    owner=str(existing.get("owner") or ""),
                    path=lock_path,
                    acquired=False,
                    reason="lease_active",
                    expires_at=existing_expires_at.isoformat(),
                )
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass

        payload = {
            "run_id": run_id,
            "action": action,
            "owner": self.owner,
            "acquired_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return RecoveryLease(
                run_id=run_id,
                action=action,
                owner="",
                path=lock_path,
                acquired=False,
                reason="lease_active",
            )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        return RecoveryLease(
            run_id=run_id,
            action=action,
            owner=self.owner,
            path=lock_path,
            acquired=True,
            expires_at=expires_at.isoformat(),
        )

    def release(self, lease: RecoveryLease, *, status: str, details: dict[str, Any] | None = None) -> None:
        run_dir = lease.path.parent
        history_path = run_dir / "recovery.history.jsonl"
        record = {
            "run_id": lease.run_id,
            "action": lease.action,
            "owner": lease.owner,
            "status": status,
            "finished_at": _utc_now().isoformat(),
            "details": dict(details or {}),
        }
        with history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        try:
            if lease.path.exists():
                lease.path.unlink()
        except FileNotFoundError:
            pass

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}


class RunRecoveryExecutor:
    def __init__(
        self,
        *,
        runs_root: Path,
        agent_run_service: Any,
        lease_seconds: int = 300,
        owner: str | None = None,
    ) -> None:
        self.runs_root = Path(runs_root)
        self.agent_run_service = agent_run_service
        self.leases = RecoveryLeaseStore(
            runs_root=self.runs_root,
            lease_seconds=lease_seconds,
            owner=owner or f"{socket.gethostname()}:{os.getpid()}",
        )

    def recover_stale_runs(self, *, stale_after_seconds: int = 300, limit: int = 20) -> dict[str, Any]:
        records = self.agent_run_service.collect_recoverable_runs(stale_after_seconds=stale_after_seconds)
        summary: dict[str, Any] = {
            "scanned": len(records),
            "attempted": 0,
            "recovered": 0,
            "failed": 0,
            "skipped": 0,
            "records": [],
        }
        for record in records[: max(0, int(limit))]:
            run_id = str(record.get("run_id") or "").strip()
            action = str(record.get("recovery_action") or "").strip()
            if not run_id or action not in RECOVERABLE_ACTIONS:
                summary["skipped"] += 1
                continue

            result = self.recover_run(run_id=run_id, recovery_action=action)
            summary["records"].append(result)
            if result["status"] == "skipped":
                summary["skipped"] += 1
            else:
                summary["attempted"] += 1
                if result["status"] == "succeeded":
                    summary["recovered"] += 1
                else:
                    summary["failed"] += 1
        return summary

    def recover_run(self, *, run_id: str, recovery_action: str) -> dict[str, Any]:
        if recovery_action not in RECOVERABLE_ACTIONS:
            return {
                "run_id": run_id,
                "recovery_action": recovery_action,
                "status": "skipped",
                "reason": "unsupported_recovery_action",
            }

        lease = self.leases.acquire(run_id, recovery_action)
        if not lease.acquired:
            return {
                "run_id": run_id,
                "recovery_action": recovery_action,
                "status": "skipped",
                "reason": lease.reason,
            }
        try:
            result = self.agent_run_service.resume_run_from_checkpoint(
                run_id=run_id,
                recovery_action=recovery_action,
            )
        except Exception as exc:  # noqa: BLE001
            details = {"error": f"{type(exc).__name__}: {exc}"}
            self.leases.release(lease, status="failed", details=details)
            return {
                "run_id": run_id,
                "recovery_action": recovery_action,
                "status": "failed",
                **details,
            }

        result_payload = dict(result or {})
        self.leases.release(lease, status="succeeded", details=result_payload)
        return {
            "run_id": run_id,
            "recovery_action": recovery_action,
            "status": "succeeded",
            "result": result_payload,
        }
