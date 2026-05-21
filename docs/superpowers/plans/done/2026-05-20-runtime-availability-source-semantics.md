# Runtime Availability And Source Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 FusionAgent 从“可检查的 no-UI runtime”提升为 building / road / water / POI 四类融合可 7*24 恢复运行、并在融合前基于 KG 数据图谱源语义自动绑定字段与算法参数的工程运行时。

**Architecture:** 复用现有 `AgentRunService`、Celery worker/beat、Track B source catalog、`SourceProfileService`、`TiledBuildingRuntimeService` 和 Track B national-scale 工具，不引入认证授权、多租户或前端改造。新增一条运行时源语义链路：KG source contract + 实际文件 profiling -> `SourceSemanticContract` -> 字段归一化 -> semantic parameter binding -> execution/audit/inspection。恢复运行通过 checkpoint + request/plan/input artifact + recovery lease 在原 run_id 上重派发。

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, Celery-compatible local task wrapper, GeoPandas, pyogrio, raster/GDAL utilities already present in repo, pytest.

---

## Scope

### In Scope

- building / road / water / POI 四类融合的工程可用性。
- 7*24 运行所需的自动 stale-run 恢复、lease 防重入、heartbeat 和 operator evidence。
- KG 数据图谱源语义驱动的字段匹配、字段含义记录、实际文件字段 profiling、参数绑定和属性保留。
- 建筑物大范围 tiled 融合，包含多源向量融合和可选高度栅格 enrichment。
- trajectory-to-road 继续保留为 reservation-only / preflight rejection，不做实际开发。

### Out Of Scope

- 认证授权、多租户、权限隔离。
- 前端继续完善。
- 任意开放域任务、实时灾害事件 feed、生产 SaaS 口径。
- trajectory-to-road 的真实算法、真实轨迹 ingestion、道路候选生成。
- 数据源远程下载能力的无限扩张；本计划只稳定已在 Track B source contract 中存在的 building / road / water / POI 源集合。

## File Structure

### Create

- `services/run_recovery_executor.py`  
  负责恢复 lease、恢复动作执行、恢复结果摘要。

- `services/source_field_profile_registry.py`  
  运行时字段语义注册表，承接 `docs/superpowers/specs/2026-05-18-national-source-matrix.json` 中的 canonical 字段、字段含义、provider probe order，并对齐现有 `fields.*` profile ids。

- `services/source_semantic_contract_service.py`  
  组合 KG `DataSourceNode.metadata`、Track B source contract、实际 source profile，生成每次 run 的 `SourceSemanticContract`。

- `agent/semantic_parameter_binding.py`  
  根据 `SourceSemanticContract` 绑定 plan task parameters 和必要的 runtime field mappings。

- `scripts/smoke_runtime_stability.py`  
  无前端稳定性 smoke：对 building / road / water / POI 执行小 AOI 或 fixture 级稳定性检查，输出 JSON summary。

- `tests/test_run_recovery_executor.py`
- `tests/test_source_field_profile_registry.py`
- `tests/test_source_semantic_contract_service.py`
- `tests/test_track_b_source_normalization_semantics.py`
- `tests/test_semantic_parameter_binding.py`
- `tests/test_agent_run_service_source_semantics.py`
- `tests/test_agent_run_service_multisource_building_runtime.py`
- `tests/test_worker_recovery_tick.py`
- `tests/test_runtime_stability_smoke.py`

### Modify

- `services/run_recovery_service.py`  
  保留 scanner，补充 recoverable action payload 的完整性字段，不直接执行恢复。

- `services/agent_run_service.py`  
  增加 `resume_run_from_checkpoint()`、运行时 source semantic contract 生成/持久化/审计、semantic binding、multi-source building route。

- `worker/tasks.py`  
  增加 `geofusion.recovery_tick` 和 `geofusion.recover_run` task。

- `worker/celery_app.py`  
  增加 recovery beat schedule。

- `schemas/agent.py`  
  在 `RunStatus` 和 `RunInspectionResponse` 中增加 source semantics / recovery worker evidence 字段，保持默认值兼容旧 run.json。

- `services/track_b_source_normalization.py`  
  支持从 `SourceSemanticContract` 的 matched fields 归一化，不再只依赖硬编码字段列表。

- `services/source_profile_service.py`  
  增加 generic vector/raster profile helper 和 profile serialization helpers，保留 Benin-specific helper。

- `services/tiled_building_runtime_service.py`  
  接受 building semantic contract / raster source binding，并确保输出稳定保留高度字段。

- `services/track_b_national_scale_service.py`  
  复用 source semantic contract 生成 normalized evidence，避免 national-scale utility 与 shared runtime 各走一套字段逻辑。

- `agent/planner.py` / `agent/parameter_binding.py`  
  保留默认参数绑定；在运行时增加 semantic binding 入口，不破坏现有 planner tests。

- `api/routers/runs_v2.py`  
  `GET /operator/recovery` 继续 inspect；新增可选手动恢复 endpoint，inspection 返回 source semantic evidence。

- `docs/no-ui-agent-operations.md` and `docs/v2-operations.md`  
  只更新边界和操作说明：恢复从 inspect-only 提升为可自动 redispatch；不写前端、认证、多租户口径。

---

## Task 1: Recovery Lease Store

**Files:**
- Create: `services/run_recovery_executor.py`
- Test: `tests/test_run_recovery_executor.py`

- [ ] **Step 1: Write failing lease tests**

Add this test file:

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.run_recovery_executor import RecoveryLeaseStore


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
```

Run:

```bash
python -m pytest -q tests/test_run_recovery_executor.py
```

Expected: FAIL because `services.run_recovery_executor` does not exist.

- [ ] **Step 2: Implement `RecoveryLeaseStore`**

Create `services/run_recovery_executor.py` with these public objects:

```python
from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


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
    return parsed


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
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
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
```

- [ ] **Step 3: Run lease tests**

Run:

```bash
python -m pytest -q tests/test_run_recovery_executor.py
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add services/run_recovery_executor.py tests/test_run_recovery_executor.py
git commit -m "feat: add recovery lease store"
```

---

## Task 2: Run Recovery Executor And Agent Resume Hook

**Files:**
- Modify: `services/run_recovery_executor.py`
- Modify: `services/agent_run_service.py`
- Modify: `services/run_recovery_service.py`
- Test: `tests/test_run_recovery_executor.py`
- Test: `tests/test_run_recovery_service.py`

- [ ] **Step 1: Write failing executor tests**

Append to `tests/test_run_recovery_executor.py`:

```python
import json

from services.run_recovery_executor import RunRecoveryExecutor


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
```

Run:

```bash
python -m pytest -q tests/test_run_recovery_executor.py
```

Expected: FAIL because `RunRecoveryExecutor` does not exist.

- [ ] **Step 2: Add `RunRecoveryExecutor`**

Extend `services/run_recovery_executor.py`:

```python
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
        summary = {"scanned": len(records), "attempted": 0, "recovered": 0, "failed": 0, "skipped": 0, "records": []}
        for record in records[: max(0, int(limit))]:
            run_id = str(record.get("run_id") or "").strip()
            action = str(record.get("recovery_action") or "").strip()
            if not run_id or action not in {
                "redispatch_full_run",
                "redispatch_from_validation",
                "redispatch_from_execution",
            }:
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
        self.leases.release(lease, status="succeeded", details=dict(result or {}))
        return {
            "run_id": run_id,
            "recovery_action": recovery_action,
            "status": "succeeded",
            "result": dict(result or {}),
        }
```

- [ ] **Step 3: Write failing `AgentRunService.resume_run_from_checkpoint` tests**

Add to `tests/test_run_recovery_service.py`:

```python
import json

from services.agent_run_service import AgentRunService
from schemas.agent import RunCreateRequest, RunInputStrategy, RunPhase, RunStatus, RunTrigger, RunTriggerType
from schemas.fusion import JobType


def test_agent_run_service_resume_full_run_reuses_existing_request(tmp_path: Path, monkeypatch) -> None:
    base_dir = tmp_path / "runs"
    service = AgentRunService(base_dir=base_dir, dispatch_eager=True)
    run_dir = base_dir / "run-resume"
    for name in ["input", "intermediate", "output", "logs"]:
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    request = RunCreateRequest(
        job_type=JobType.road,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="fuse road", spatial_extent="bbox(0,0,1,1)"),
        input_strategy=RunInputStrategy.task_driven_auto,
    )
    (run_dir / "request.json").write_text(json.dumps(request.model_dump(mode="json")), encoding="utf-8")
    status = RunStatus(
        run_id="run-resume",
        job_type=JobType.road,
        trigger=request.trigger,
        phase=RunPhase.running,
        progress=66,
        target_crs="EPSG:4326",
        checkpoint={"stage": "execution", "plan_revision": 1},
        created_at="2026-05-20T00:00:00+00:00",
        updated_at="2026-05-20T00:00:00+00:00",
    )
    service._persist_status(status)
    captured: dict[str, object] = {}

    def fake_execute_run(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(service, "execute_run", fake_execute_run)

    result = service.resume_run_from_checkpoint("run-resume", "redispatch_from_execution")

    assert result["run_id"] == "run-resume"
    assert result["recovery_action"] == "redispatch_from_execution"
    assert captured["run_id"] == "run-resume"
    assert captured["request"] == request
    assert captured["intermediate_dir"] == run_dir / "intermediate"
    assert captured["output_dir"] == run_dir / "output"
    assert captured["log_dir"] == run_dir / "logs"
```

Run:

```bash
python -m pytest -q tests/test_run_recovery_service.py::test_agent_run_service_resume_full_run_reuses_existing_request
```

Expected: FAIL because `resume_run_from_checkpoint` does not exist.

- [ ] **Step 4: Implement conservative resume hook**

In `services/agent_run_service.py`, add:

```python
    def resume_run_from_checkpoint(self, run_id: str, recovery_action: str) -> dict[str, object]:
        run_dir = self.base_dir / run_id
        request_path = run_dir / "request.json"
        if not request_path.exists():
            raise FileNotFoundError(f"Missing request.json for run {run_id}")
        request = RunCreateRequest.model_validate(json.loads(request_path.read_text(encoding="utf-8")))
        status = self.get_run(run_id)
        if status is None:
            raise KeyError(run_id)
        input_dir = run_dir / "input"
        intermediate_dir = run_dir / "intermediate"
        output_dir = run_dir / "output"
        log_dir = run_dir / "logs"
        for directory in [input_dir, intermediate_dir, output_dir, log_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        uploaded_zips = sorted(input_dir.glob("*.zip"))
        osm_zip_path = uploaded_zips[0] if request.input_strategy == RunInputStrategy.uploaded and uploaded_zips else None
        ref_zip_path = uploaded_zips[1] if request.input_strategy == RunInputStrategy.uploaded and len(uploaded_zips) > 1 else None
        self._update_status(
            run_id,
            RunPhase.queued,
            progress=0,
            checkpoint=self._checkpoint(stage="queued", resume_stage="planning", plan_revision=status.plan_revision),
            event_kind="recovery_redispatch_started",
            event_message="Recovery redispatch started from checkpoint.",
            event_details={"recovery_action": recovery_action, "previous_checkpoint": status.checkpoint},
        )
        runtime_snapshot_id = self._load_run_runtime_snapshot_id(run_id)
        self.execute_run(
            run_id=run_id,
            request=request,
            osm_zip_path=osm_zip_path,
            ref_zip_path=ref_zip_path,
            intermediate_dir=intermediate_dir,
            output_dir=output_dir,
            log_dir=log_dir,
            runtime_snapshot_id=runtime_snapshot_id,
        )
        current = self.get_run(run_id)
        return {
            "run_id": run_id,
            "recovery_action": recovery_action,
            "phase": current.phase.value if current else "unknown",
            "checkpoint": current.checkpoint if current else {},
        }
```

This hook intentionally redispatches the existing run through the normal pipeline for all three recovery actions in the first implementation pass. It preserves the classified action in audit evidence while avoiding partial-stage divergence.

- [ ] **Step 5: Run recovery tests**

Run:

```bash
python -m pytest -q tests/test_run_recovery_executor.py tests/test_run_recovery_service.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/run_recovery_executor.py services/agent_run_service.py services/run_recovery_service.py tests/test_run_recovery_executor.py tests/test_run_recovery_service.py
git commit -m "feat: redispatch recoverable runs from checkpoints"
```

---

## Task 3: Worker Recovery Tick And Manual Recovery API

**Files:**
- Modify: `worker/tasks.py`
- Modify: `worker/celery_app.py`
- Modify: `api/routers/runs_v2.py`
- Modify: `schemas/agent.py`
- Test: `tests/test_worker_recovery_tick.py`
- Test: `tests/test_operator_recovery_api.py`

- [ ] **Step 1: Write failing worker tests**

Create `tests/test_worker_recovery_tick.py`:

```python
from __future__ import annotations

import importlib


def test_recovery_tick_delegates_to_executor(monkeypatch, tmp_path) -> None:
    worker_tasks = importlib.import_module("worker.tasks")
    service_module = importlib.import_module("services.agent_run_service")
    calls: list[dict[str, object]] = []

    class StubService:
        base_dir = tmp_path

        def collect_recoverable_runs(self, stale_after_seconds: int):
            return [{"run_id": "run-1", "recovery_action": "redispatch_full_run"}]

        def resume_run_from_checkpoint(self, run_id: str, recovery_action: str):
            calls.append({"run_id": run_id, "recovery_action": recovery_action})
            return {"run_id": run_id, "phase": "succeeded"}

    monkeypatch.setattr(service_module, "agent_run_service", StubService())
    monkeypatch.setenv("GEOFUSION_RECOVERY_ENABLED", "1")
    monkeypatch.setenv("GEOFUSION_RECOVERY_STALE_SECONDS", "300")

    result = worker_tasks.recovery_tick()

    assert result["enabled"] is True
    assert result["recovered"] == 1
    assert calls == [{"run_id": "run-1", "recovery_action": "redispatch_full_run"}]


def test_recovery_tick_can_be_disabled(monkeypatch) -> None:
    worker_tasks = importlib.import_module("worker.tasks")
    monkeypatch.setenv("GEOFUSION_RECOVERY_ENABLED", "0")

    result = worker_tasks.recovery_tick()

    assert result == {"enabled": False, "reason": "disabled"}


def test_celery_beat_registers_recovery_tick(monkeypatch) -> None:
    module = importlib.import_module("worker.celery_app")

    assert "recovery-run-producer" in module.celery_app.conf["beat_schedule"]
    assert module.celery_app.conf["beat_schedule"]["recovery-run-producer"]["task"] == "geofusion.recovery_tick"
```

Run:

```bash
python -m pytest -q tests/test_worker_recovery_tick.py
```

Expected: FAIL because `recovery_tick` and beat entry do not exist.

- [ ] **Step 2: Add worker tasks**

In `worker/tasks.py`, add:

```python
def _as_bool_env(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@celery_app.task(name="geofusion.recover_run")
def recover_run_task(run_id: str, recovery_action: str) -> Dict[str, Any]:
    from services.agent_run_service import agent_run_service
    from services.run_recovery_executor import RunRecoveryExecutor

    executor = RunRecoveryExecutor(
        runs_root=agent_run_service.base_dir,
        agent_run_service=agent_run_service,
        lease_seconds=int(os.getenv("GEOFUSION_RECOVERY_LEASE_SECONDS", "300")),
    )
    return executor.recover_run(run_id=run_id, recovery_action=recovery_action)


@celery_app.task(name="geofusion.recovery_tick")
def recovery_tick() -> Dict[str, Any]:
    if not _as_bool_env("GEOFUSION_RECOVERY_ENABLED", "1"):
        return {"enabled": False, "reason": "disabled"}
    from services.agent_run_service import agent_run_service
    from services.run_recovery_executor import RunRecoveryExecutor

    executor = RunRecoveryExecutor(
        runs_root=agent_run_service.base_dir,
        agent_run_service=agent_run_service,
        lease_seconds=int(os.getenv("GEOFUSION_RECOVERY_LEASE_SECONDS", "300")),
    )
    result = executor.recover_stale_runs(
        stale_after_seconds=int(os.getenv("GEOFUSION_RECOVERY_STALE_SECONDS", "300")),
        limit=int(os.getenv("GEOFUSION_RECOVERY_LIMIT", "20")),
    )
    return {"enabled": True, **result}
```

- [ ] **Step 3: Add Celery beat schedule**

In `worker/celery_app.py`, extend `beat_schedule`:

```python
        "recovery-run-producer": {
            "task": "geofusion.recovery_tick",
            "schedule": float(os.getenv("GEOFUSION_RECOVERY_INTERVAL_SECONDS", "60")),
            "args": (),
        },
```

- [ ] **Step 4: Add manual recovery endpoint schema and route**

In `schemas/agent.py`, add:

```python
class OperatorRecoveryExecuteRequest(BaseModel):
    run_id: Optional[str] = None
    stale_after_seconds: int = 300
    limit: int = 20


class OperatorRecoveryExecuteResponse(BaseModel):
    enabled: bool = True
    result: Dict[str, Any] = Field(default_factory=dict)
```

In `api/routers/runs_v2.py`, add:

```python
@router.post("/operator/recovery", response_model=OperatorRecoveryExecuteResponse)
async def execute_operator_recovery(request: OperatorRecoveryExecuteRequest) -> OperatorRecoveryExecuteResponse:
    from services.run_recovery_executor import RunRecoveryExecutor

    executor = RunRecoveryExecutor(
        runs_root=agent_run_service.base_dir,
        agent_run_service=agent_run_service,
    )
    if request.run_id:
        status = agent_run_service.get_run(request.run_id)
        if status is None:
            raise HTTPException(status_code=404, detail=f"Run not found: {request.run_id}")
        hint = build_recovery_hint(status.model_dump(mode="json"))
        action = str(hint.get("recovery_action") or "")
        if action == "none":
            return OperatorRecoveryExecuteResponse(enabled=True, result={"status": "skipped", "reason": "not_recoverable"})
        result = executor.recover_run(run_id=request.run_id, recovery_action=action)
    else:
        result = executor.recover_stale_runs(
            stale_after_seconds=request.stale_after_seconds,
            limit=request.limit,
        )
    return OperatorRecoveryExecuteResponse(enabled=True, result=result)
```

Also import `OperatorRecoveryExecuteRequest`, `OperatorRecoveryExecuteResponse`, and `build_recovery_hint`.

- [ ] **Step 5: Add API test**

Extend `tests/test_operator_recovery_api.py`:

```python
def test_operator_recovery_post_executes_recovery(client, monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class StubExecutor:
        def __init__(self, **_kwargs):
            pass

        def recover_stale_runs(self, *, stale_after_seconds: int, limit: int):
            calls.append({"stale_after_seconds": stale_after_seconds, "limit": limit})
            return {"attempted": 1, "recovered": 1}

    monkeypatch.setattr("api.routers.runs_v2.RunRecoveryExecutor", StubExecutor)

    response = client.post("/api/v2/operator/recovery", json={"stale_after_seconds": 300, "limit": 5})

    assert response.status_code == 200
    assert response.json()["result"]["recovered"] == 1
    assert calls == [{"stale_after_seconds": 300, "limit": 5}]
```

If `RunRecoveryExecutor` is imported inside the route rather than module scope, adjust the test to monkeypatch `services.run_recovery_executor.RunRecoveryExecutor`.

- [ ] **Step 6: Run worker/API tests**

Run:

```bash
python -m pytest -q tests/test_worker_recovery_tick.py tests/test_operator_recovery_api.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add worker/tasks.py worker/celery_app.py api/routers/runs_v2.py schemas/agent.py tests/test_worker_recovery_tick.py tests/test_operator_recovery_api.py
git commit -m "feat: schedule automatic run recovery"
```

---

## Task 4: Source Field Profile Registry

**Files:**
- Create: `services/source_field_profile_registry.py`
- Modify: `kg/track_b_source_contract.py`
- Test: `tests/test_source_field_profile_registry.py`

- [ ] **Step 1: Write failing registry tests**

Create `tests/test_source_field_profile_registry.py`:

```python
from __future__ import annotations

from services.source_field_profile_registry import SourceFieldProfileRegistry


def test_registry_resolves_building_height_profile_from_source_specific_id() -> None:
    registry = SourceFieldProfileRegistry()

    profile = registry.get("fields.building.microsoft")

    assert profile.profile_id == "fields.building.microsoft"
    assert profile.theme == "building"
    assert profile.canonical_fields["height_m"].meaning == "building height in meters"
    assert profile.provider_probe_order["height_m"] == ["height", "Height", "HEIGHT", "building_h", "bld_h"]


def test_registry_resolves_road_water_poi_profiles() -> None:
    registry = SourceFieldProfileRegistry()

    assert registry.get("fields.road.overture_transportation").canonical_fields["road_class"].required is True
    assert registry.get("fields.water.hydrorivers_line").canonical_fields["water_class"].meaning == "water classification"
    assert registry.get("fields.poi.gns").canonical_fields["admin_country"].required is False


def test_registry_lists_theme_profile_ids() -> None:
    registry = SourceFieldProfileRegistry()

    assert "fields.building.osm" in registry.profile_ids_for_theme("building")
    assert "fields.poi.gns" in registry.profile_ids_for_theme("poi")
```

Run:

```bash
python -m pytest -q tests/test_source_field_profile_registry.py
```

Expected: FAIL because registry does not exist.

- [ ] **Step 2: Implement registry dataclasses and profiles**

Create `services/source_field_profile_registry.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CanonicalField:
    name: str
    meaning: str
    required: bool = True
    value_type: str = "string"


@dataclass(frozen=True)
class SourceFieldProfile:
    profile_id: str
    theme: str
    canonical_fields: dict[str, CanonicalField]
    provider_probe_order: dict[str, list[str]]


def _field(name: str, meaning: str, *, required: bool = True, value_type: str = "string") -> CanonicalField:
    return CanonicalField(name=name, meaning=meaning, required=required, value_type=value_type)


BUILDING_FIELDS = {
    "source_feature_id": _field("source_feature_id", "stable upstream feature identifier"),
    "height_m": _field("height_m", "building height in meters", required=False, value_type="float"),
    "name": _field("name", "building name", required=False),
    "building_class": _field("building_class", "building class or usage", required=False),
    "confidence": _field("confidence", "source confidence score", required=False, value_type="float"),
}

ROAD_FIELDS = {
    "source_feature_id": _field("source_feature_id", "stable upstream road feature identifier"),
    "road_class": _field("road_class", "road class used for fusion priority"),
    "name": _field("name", "road name", required=False),
    "surface": _field("surface", "road surface material", required=False),
    "lanes": _field("lanes", "lane count", required=False),
}

WATER_FIELDS = {
    "source_feature_id": _field("source_feature_id", "stable upstream water feature identifier"),
    "feature_kind": _field("feature_kind", "line or polygon water feature kind"),
    "water_class": _field("water_class", "water classification"),
    "name": _field("name", "water feature name", required=False),
    "perennial_flag": _field("perennial_flag", "perennial or flow/depth indicator", required=False),
}

POI_FIELDS = {
    "source_feature_id": _field("source_feature_id", "stable upstream POI identifier"),
    "name": _field("name", "primary POI name"),
    "name_alt": _field("name_alt", "alternate POI name", required=False),
    "category": _field("category", "POI category or designation"),
    "admin_country": _field("admin_country", "admin country code", required=False),
    "GeoHash": _field("GeoHash", "geohash used for bounded neighbor matching", required=False),
}


PROFILES: dict[str, SourceFieldProfile] = {
    "fields.building.osm": SourceFieldProfile(
        profile_id="fields.building.osm",
        theme="building",
        canonical_fields=BUILDING_FIELDS,
        provider_probe_order={
            "source_feature_id": ["osm_id", "osm_way_id", "osm_rel_id", "id", "objectid", "fid"],
            "height_m": ["height", "Height", "HEIGHT", "building_h", "bld_h"],
            "name": ["name", "bld_name", "building_n"],
            "building_class": ["building", "type", "class", "use"],
            "confidence": ["confidence"],
        },
    ),
    "fields.building.microsoft": SourceFieldProfile(
        profile_id="fields.building.microsoft",
        theme="building",
        canonical_fields=BUILDING_FIELDS,
        provider_probe_order={
            "source_feature_id": ["id", "quadkey", "sourceid", "OBJECTID", "objectid", "fid"],
            "height_m": ["height", "Height", "HEIGHT", "building_h", "bld_h"],
            "name": ["name", "Name"],
            "building_class": ["type", "class", "CATEGORY"],
            "confidence": ["confidence", "probability", "prob"],
        },
    ),
    "fields.building.google": SourceFieldProfile(
        profile_id="fields.building.google",
        theme="building",
        canonical_fields=BUILDING_FIELDS,
        provider_probe_order={
            "source_feature_id": ["id", "quadkey", "sourceid", "OBJECTID", "objectid", "fid"],
            "height_m": ["height", "Height", "HEIGHT", "building_h", "bld_h"],
            "name": ["name", "Name"],
            "building_class": ["type", "class", "CATEGORY"],
            "confidence": ["confidence", "probability", "prob"],
        },
    ),
    "fields.building.openbuildingmap": SourceFieldProfile(
        profile_id="fields.building.openbuildingmap",
        theme="building",
        canonical_fields=BUILDING_FIELDS,
        provider_probe_order={
            "source_feature_id": ["id", "quadkey", "sourceid", "OBJECTID", "objectid", "fid"],
            "height_m": ["height", "Height", "HEIGHT", "building_h", "bld_h"],
            "name": ["name", "Name"],
            "building_class": ["type", "class", "CATEGORY"],
            "confidence": ["confidence", "probability", "prob"],
        },
    ),
    "fields.building.google_open_buildings_vector": SourceFieldProfile(
        profile_id="fields.building.google_open_buildings_vector",
        theme="building",
        canonical_fields=BUILDING_FIELDS,
        provider_probe_order={
            "source_feature_id": ["id", "quadkey", "sourceid", "OBJECTID", "objectid", "fid"],
            "height_m": ["height", "Height", "HEIGHT", "building_h", "bld_h"],
            "name": ["name", "Name"],
            "building_class": ["type", "class", "CATEGORY"],
            "confidence": ["confidence", "probability", "prob"],
        },
    ),
    "fields.road.osm": SourceFieldProfile(
        profile_id="fields.road.osm",
        theme="road",
        canonical_fields=ROAD_FIELDS,
        provider_probe_order={
            "source_feature_id": ["osm_id", "id", "objectid", "fid"],
            "road_class": ["road_class", "fclass", "highway", "class"],
            "name": ["name", "ref"],
            "surface": ["surface"],
            "lanes": ["lanes"],
        },
    ),
    "fields.road.overture_transportation": SourceFieldProfile(
        profile_id="fields.road.overture_transportation",
        theme="road",
        canonical_fields=ROAD_FIELDS,
        provider_probe_order={
            "source_feature_id": ["id", "segment_id", "road_id", "fid"],
            "road_class": ["road_class", "class", "subclass", "subtype", "type"],
            "name": ["name", "names.primary", "names_primary", "primary_name", "ref"],
            "surface": ["surface"],
            "lanes": ["lane_count", "lanes"],
        },
    ),
    "fields.water.osm_polygon": SourceFieldProfile(
        profile_id="fields.water.osm_polygon",
        theme="water",
        canonical_fields=WATER_FIELDS,
        provider_probe_order={
            "source_feature_id": ["osm_id", "id", "objectid", "fid"],
            "feature_kind": ["geometry_type"],
            "water_class": ["water_class", "fclass", "natural", "waterway"],
            "name": ["name", "waterway", "natural"],
            "perennial_flag": ["perennial_flag", "perennial"],
        },
    ),
    "fields.water.local_reference": SourceFieldProfile(
        profile_id="fields.water.local_reference",
        theme="water",
        canonical_fields=WATER_FIELDS,
        provider_probe_order={
            "source_feature_id": ["Hylak_id", "lake_id", "id", "OBJECTID", "fid"],
            "feature_kind": ["geometry_type"],
            "water_class": ["Lake_type", "type", "class", "fclass"],
            "name": ["Lake_name", "name", "Name"],
            "perennial_flag": ["perennial_flag", "Depth_avg"],
        },
    ),
    "fields.water.hydrorivers_line": SourceFieldProfile(
        profile_id="fields.water.hydrorivers_line",
        theme="water",
        canonical_fields=WATER_FIELDS,
        provider_probe_order={
            "source_feature_id": ["HYRIV_ID", "river_id", "id"],
            "feature_kind": ["line"],
            "water_class": ["ORD_STRA", "fclass"],
            "name": ["name", "River_name", "river_name"],
            "perennial_flag": ["DIS_AV_CMS", "perennial_flag"],
        },
    ),
    "fields.water.hydrolakes_polygon": SourceFieldProfile(
        profile_id="fields.water.hydrolakes_polygon",
        theme="water",
        canonical_fields=WATER_FIELDS,
        provider_probe_order={
            "source_feature_id": ["Hylak_id", "lake_id", "id"],
            "feature_kind": ["polygon"],
            "water_class": ["Lake_type", "fclass"],
            "name": ["Lake_name", "name", "Name"],
            "perennial_flag": ["Depth_avg", "perennial_flag"],
        },
    ),
    "fields.water.overture": SourceFieldProfile(
        profile_id="fields.water.overture",
        theme="water",
        canonical_fields=WATER_FIELDS,
        provider_probe_order={
            "source_feature_id": ["id", "fid"],
            "feature_kind": ["subtype"],
            "water_class": ["class", "subtype"],
            "name": ["name", "names.primary", "names_primary"],
            "perennial_flag": ["perennial_flag"],
        },
    ),
    "fields.poi.osm": SourceFieldProfile(
        profile_id="fields.poi.osm",
        theme="poi",
        canonical_fields=POI_FIELDS,
        provider_probe_order={
            "source_feature_id": ["osm_id", "id", "objectid", "fid"],
            "name": ["name", "alt_name"],
            "name_alt": ["alt_name", "name_en"],
            "category": ["fclass", "amenity", "type", "class"],
            "admin_country": ["admin_country", "country", "addr:country", "iso3166-1"],
            "GeoHash": ["GeoHash", "geohash"],
        },
    ),
    "fields.poi.gns": SourceFieldProfile(
        profile_id="fields.poi.gns",
        theme="poi",
        canonical_fields=POI_FIELDS,
        provider_probe_order={
            "source_feature_id": ["ufi", "uni", "id", "UFI", "UNI"],
            "name": ["full_name", "full_nm_nd", "name", "display", "FULL_NAME"],
            "name_alt": ["full_nm_nd", "generic"],
            "category": ["desig_cd", "fc", "type", "DSG"],
            "admin_country": ["CC1", "cc1", "country", "admin_country", "cc_ft", "cc_nm"],
            "GeoHash": ["GeoHash", "geohash"],
        },
    ),
    "fields.poi.rh": SourceFieldProfile(
        profile_id="fields.poi.rh",
        theme="poi",
        canonical_fields=POI_FIELDS,
        provider_probe_order={
            "source_feature_id": ["id", "sourceid", "ID"],
            "name": ["name", "NAME", "alternaten"],
            "name_alt": ["alternaten"],
            "category": ["type", "class", "label", "CATEGORY"],
            "admin_country": ["admin_country", "country"],
            "GeoHash": ["GeoHash", "geohash"],
        },
    ),
    "fields.poi.overture_places": SourceFieldProfile(
        profile_id="fields.poi.overture_places",
        theme="poi",
        canonical_fields=POI_FIELDS,
        provider_probe_order={
            "source_feature_id": ["id", "sourceid"],
            "name": ["name", "names.primary", "names_primary"],
            "name_alt": ["brand"],
            "category": ["category", "categories.primary", "class", "type"],
            "admin_country": ["admin_country", "country"],
            "GeoHash": ["GeoHash", "geohash"],
        },
    ),
}


class SourceFieldProfileRegistry:
    def __init__(self, profiles: dict[str, SourceFieldProfile] | None = None) -> None:
        self._profiles = dict(profiles or PROFILES)

    def get(self, profile_id: str) -> SourceFieldProfile:
        try:
            return self._profiles[profile_id]
        except KeyError as exc:
            raise KeyError(f"Unknown source field mapping profile={profile_id}") from exc

    def profile_ids_for_theme(self, theme: str) -> list[str]:
        requested = theme.strip().lower()
        return sorted(profile_id for profile_id, profile in self._profiles.items() if profile.theme == requested)
```

- [ ] **Step 3: Run registry tests**

Run:

```bash
python -m pytest -q tests/test_source_field_profile_registry.py
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add services/source_field_profile_registry.py tests/test_source_field_profile_registry.py
git commit -m "feat: register source field semantics"
```

---

## Task 5: Source Semantic Contract Service

**Files:**
- Create: `services/source_semantic_contract_service.py`
- Modify: `services/source_profile_service.py`
- Test: `tests/test_source_semantic_contract_service.py`

- [ ] **Step 1: Write failing source semantic contract tests**

Create `tests/test_source_semantic_contract_service.py`:

```python
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

from kg.source_catalog import build_data_sources
from services.source_semantic_contract_service import SourceSemanticContractService


class _Repo:
    def list_data_sources(self):
        return build_data_sources()


def _write_building(path: Path) -> Path:
    gdf = gpd.GeoDataFrame(
        {
            "id": ["ms-1"],
            "HEIGHT": [12.5],
            "Name": ["clinic"],
        },
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
        crs="EPSG:4326",
    )
    gdf.to_file(path, driver="GPKG")
    return path


def test_semantic_contract_matches_actual_height_field(tmp_path: Path) -> None:
    source_path = _write_building(tmp_path / "microsoft.gpkg")
    service = SourceSemanticContractService(kg_repo=_Repo())

    contract = service.build_contract(
        run_id="run-1",
        job_type="building",
        selected_source_id="catalog.earthquake.building",
        component_paths={"raw.microsoft.building": source_path},
        target_crs="EPSG:4326",
    )

    ms = contract.sources["raw.microsoft.building"]
    assert ms.field_mapping_profile == "fields.building.microsoft"
    assert ms.matched_fields["height_m"].matched_field == "HEIGHT"
    assert ms.height_semantics == "estimated_height"
    assert contract.height_policy["vector_height_fields"]["raw.microsoft.building"] == "HEIGHT"


def test_semantic_contract_marks_required_missing_fields(tmp_path: Path) -> None:
    gdf = gpd.GeoDataFrame(
        {"name": ["nameless-id"]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
        crs="EPSG:4326",
    )
    path = tmp_path / "bad.gpkg"
    gdf.to_file(path, driver="GPKG")
    service = SourceSemanticContractService(kg_repo=_Repo())

    contract = service.build_contract(
        run_id="run-2",
        job_type="building",
        selected_source_id="catalog.earthquake.building",
        component_paths={"raw.microsoft.building": path},
        target_crs="EPSG:4326",
    )

    issues = contract.validation["issues"]
    assert {
        "source_id": "raw.microsoft.building",
        "canonical_field": "source_feature_id",
        "code": "required_field_unmatched",
    } in issues
```

Run:

```bash
python -m pytest -q tests/test_source_semantic_contract_service.py
```

Expected: FAIL because service does not exist.

- [ ] **Step 2: Implement semantic contract dataclasses**

Create `services/source_semantic_contract_service.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from services.source_field_profile_registry import SourceFieldProfileRegistry
from services.source_profile_service import SourceProfileService


@dataclass(frozen=True)
class MatchedField:
    canonical_field: str
    meaning: str
    required: bool
    candidate_fields: list[str]
    matched_field: str | None
    available: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceSemanticEntry:
    source_id: str
    source_name: str
    field_mapping_profile: str
    source_form: str
    artifact_path: str
    crs: str | None
    feature_count: int | None
    field_names: list[str]
    height_fields: list[str]
    height_semantics: str
    matched_fields: dict[str, MatchedField]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["matched_fields"] = {key: value.to_dict() for key, value in self.matched_fields.items()}
        return payload


@dataclass(frozen=True)
class SourceSemanticContract:
    run_id: str
    job_type: str
    selected_source_id: str
    target_crs: str
    component_source_ids: list[str]
    sources: dict[str, SourceSemanticEntry]
    height_policy: dict[str, Any] = field(default_factory=dict)
    parameter_hints: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "job_type": self.job_type,
            "selected_source_id": self.selected_source_id,
            "target_crs": self.target_crs,
            "component_source_ids": list(self.component_source_ids),
            "sources": {key: value.to_dict() for key, value in self.sources.items()},
            "height_policy": dict(self.height_policy),
            "parameter_hints": dict(self.parameter_hints),
            "validation": dict(self.validation),
        }
```

- [ ] **Step 3: Implement service matching logic**

Continue in the same file:

```python
class SourceSemanticContractService:
    def __init__(
        self,
        *,
        kg_repo: Any,
        profile_service: SourceProfileService | None = None,
        registry: SourceFieldProfileRegistry | None = None,
    ) -> None:
        self.kg_repo = kg_repo
        self.profile_service = profile_service or SourceProfileService()
        self.registry = registry or SourceFieldProfileRegistry()

    def build_contract(
        self,
        *,
        run_id: str,
        job_type: str,
        selected_source_id: str,
        component_paths: dict[str, Path],
        target_crs: str,
        raster_paths: dict[str, Path] | None = None,
    ) -> SourceSemanticContract:
        source_index = {source.source_id: source for source in self.kg_repo.list_data_sources()}
        entries: dict[str, SourceSemanticEntry] = {}
        issues: list[dict[str, str]] = []
        vector_height_fields: dict[str, str] = {}

        for source_id, artifact_path in component_paths.items():
            source = source_index[source_id]
            profile_id = str(source.metadata.get("field_mapping_profile") or "")
            field_profile = self.registry.get(profile_id)
            source_profile = self.profile_service.profile_vector_source(
                source_id=source_id,
                source_name=source.source_name,
                path=Path(artifact_path),
                runtime_status=str(source.metadata.get("runtime_status") or "runtime_candidate"),
                selectable_now=bool(source.metadata.get("selectable_now", True)),
                metadata=dict(source.metadata),
            )
            matched = self._match_fields(
                source_id=source_id,
                field_names=source_profile.field_names,
                field_profile=field_profile,
            )
            for canonical, item in matched.items():
                if item.required and not item.available:
                    issues.append(
                        {
                            "source_id": source_id,
                            "canonical_field": canonical,
                            "code": "required_field_unmatched",
                        }
                    )
            height_match = matched.get("height_m")
            if height_match and height_match.matched_field:
                vector_height_fields[source_id] = height_match.matched_field
            entries[source_id] = SourceSemanticEntry(
                source_id=source_id,
                source_name=source.source_name,
                field_mapping_profile=profile_id,
                source_form=source_profile.source_form,
                artifact_path=str(artifact_path),
                crs=source_profile.crs,
                feature_count=source_profile.feature_count,
                field_names=source_profile.field_names,
                height_fields=source_profile.height_fields,
                height_semantics=source_profile.height_semantics,
                matched_fields=matched,
                metadata=dict(source.metadata),
            )

        raster_height_sources: dict[str, str] = {}
        for raster_id, raster_path in dict(raster_paths or {}).items():
            source = source_index.get(raster_id)
            raster_profile = self.profile_service.profile_raster_source(
                source_id=raster_id,
                source_name=source.source_name if source else raster_id,
                path=Path(raster_path),
                runtime_status=str((source.metadata if source else {}).get("runtime_status") or "runtime_candidate"),
                selectable_now=bool((source.metadata if source else {}).get("selectable_now", True)),
                metadata=dict(source.metadata) if source else {},
            )
            if raster_profile.height_semantics == "estimated_height":
                raster_height_sources[raster_id] = str(raster_path)

        parameter_hints = self._parameter_hints(job_type=job_type, entries=entries)
        return SourceSemanticContract(
            run_id=run_id,
            job_type=job_type,
            selected_source_id=selected_source_id,
            target_crs=target_crs,
            component_source_ids=list(component_paths.keys()),
            sources=entries,
            height_policy={
                "vector_height_fields": vector_height_fields,
                "raster_height_sources": raster_height_sources,
                "positive_only": True,
                "height_output_field": "height_raster",
                "canonical_height_field": "height",
            },
            parameter_hints=parameter_hints,
            validation={"valid": not issues, "issues": issues},
        )

    def _match_fields(self, *, source_id: str, field_names: list[str], field_profile) -> dict[str, MatchedField]:
        actual_by_casefold = {name.casefold(): name for name in field_names}
        matched: dict[str, MatchedField] = {}
        for canonical, field in field_profile.canonical_fields.items():
            candidates = list(field_profile.provider_probe_order.get(canonical) or [])
            selected = None
            for candidate in candidates:
                if candidate in {"line", "polygon"}:
                    selected = candidate
                    break
                selected = actual_by_casefold.get(candidate.casefold())
                if selected is not None:
                    break
            matched[canonical] = MatchedField(
                canonical_field=canonical,
                meaning=field.meaning,
                required=field.required,
                candidate_fields=candidates,
                matched_field=selected,
                available=selected is not None or not field.required,
            )
        return matched

    @staticmethod
    def _parameter_hints(*, job_type: str, entries: dict[str, SourceSemanticEntry]) -> dict[str, Any]:
        theme = job_type.strip().lower()
        if theme == "building":
            source_alias = {
                "raw.microsoft.building": "MS",
                "raw.local.microsoft.building": "MICROSOFT_LOCAL",
                "raw.openbuildingmap.building": "OBM",
                "raw.google.open_buildings.vector": "GOOGLE_OPEN_BUILDINGS",
                "raw.google.building": "GOOGLE",
                "raw.osm.building": "OSM",
            }
            ordered = [source_alias[source_id] for source_id in entries if source_id in source_alias]
            return {"source_priority_order": ordered}
        if theme == "poi":
            return {"geohash_precision": 8}
        return {}
```

- [ ] **Step 4: Run source semantic tests**

Run:

```bash
python -m pytest -q tests/test_source_semantic_contract_service.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/source_semantic_contract_service.py services/source_profile_service.py tests/test_source_semantic_contract_service.py
git commit -m "feat: build source semantic contracts"
```

---

## Task 6: Contract-Driven Track B Normalization

**Files:**
- Modify: `services/track_b_source_normalization.py`
- Test: `tests/test_track_b_source_normalization_semantics.py`
- Test: `tests/test_track_b_source_normalization.py`

- [ ] **Step 1: Write failing normalization test**

Create `tests/test_track_b_source_normalization_semantics.py`:

```python
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

from kg.source_catalog import build_data_sources
from services.source_semantic_contract_service import SourceSemanticContractService
from services.track_b_source_normalization import normalize_track_b_source_frame


class _Repo:
    def list_data_sources(self):
        return build_data_sources()


def test_normalization_uses_semantic_contract_matched_height_field(tmp_path: Path) -> None:
    path = tmp_path / "ms.gpkg"
    frame = gpd.GeoDataFrame(
        {
            "quadkey": ["q1"],
            "HEIGHT": [14.0],
            "Name": ["school"],
        },
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
        crs="EPSG:4326",
    )
    frame.to_file(path, driver="GPKG")
    contract = SourceSemanticContractService(kg_repo=_Repo()).build_contract(
        run_id="run-1",
        job_type="building",
        selected_source_id="catalog.earthquake.building",
        component_paths={"raw.microsoft.building": path},
        target_crs="EPSG:4326",
    )

    normalized = normalize_track_b_source_frame(
        "raw.microsoft.building",
        frame,
        target_crs="EPSG:4326",
        source_semantics=contract.sources["raw.microsoft.building"],
    )

    assert list(normalized["source_feature_id"]) == ["q1"]
    assert float(normalized.loc[0, "height_m"]) == 14.0
    assert normalized.loc[0, "field_mapping_profile"] == "fields.building.microsoft"
```

Run:

```bash
python -m pytest -q tests/test_track_b_source_normalization_semantics.py
```

Expected: FAIL because `normalize_track_b_source_frame` has no `source_semantics` argument.

- [ ] **Step 2: Add semantic-aware helpers**

Modify `services/track_b_source_normalization.py`:

```python
def normalize_track_b_source_frame(
    source_id: str,
    frame: gpd.GeoDataFrame,
    *,
    target_crs: str,
    geohash_precision: int = 8,
    source_semantics=None,
) -> gpd.GeoDataFrame:
    contract = get_track_b_source_contract(source_id)
    if contract is None:
        raise KeyError(f"Unknown Track B source_id={source_id}")

    normalized = frame.copy()
    if normalized.crs is None:
        normalized = normalized.set_crs("EPSG:4326")
    normalized = normalized.to_crs(target_crs)
    normalized = normalized[normalized.geometry.notna() & ~normalized.geometry.is_empty].copy()
    normalized = normalized.reset_index(drop=True)
    normalized["source_id"] = source_id
    normalized["track_b_theme"] = contract.theme
    normalized["field_mapping_profile"] = contract.field_mapping_profile

    if source_semantics is not None:
        normalized = _normalize_from_semantics(normalized, source_semantics, contract.theme, geohash_precision)
    else:
        handler = _PROFILE_HANDLERS.get(contract.field_mapping_profile)
        if handler is None:
            raise KeyError(f"Unsupported Track B field mapping profile={contract.field_mapping_profile}")
        normalized = handler(normalized, geohash_precision=geohash_precision)
    return normalized.reset_index(drop=True)


def _semantic_candidates(source_semantics, canonical_field: str) -> list[str]:
    matched = source_semantics.matched_fields.get(canonical_field)
    if matched is None:
        return []
    ordered = []
    if matched.matched_field:
        ordered.append(matched.matched_field)
    ordered.extend(item for item in matched.candidate_fields if item not in ordered)
    return ordered


def _normalize_from_semantics(frame: gpd.GeoDataFrame, source_semantics, theme: str, geohash_precision: int) -> gpd.GeoDataFrame:
    if theme == "building":
        frame["source_feature_id"] = _stringify(_coalesce(frame, _semantic_candidates(source_semantics, "source_feature_id")))
        frame["name"] = _coalesce(frame, _semantic_candidates(source_semantics, "name"))
        frame["height_m"] = _numeric_coalesce(frame, _semantic_candidates(source_semantics, "height_m"))
        frame["building_class"] = _coalesce(frame, _semantic_candidates(source_semantics, "building_class"), default="building")
        frame["confidence"] = _coalesce(frame, _semantic_candidates(source_semantics, "confidence"), default=1.0)
        return _filter_geometry(frame, {"Polygon", "MultiPolygon"})
    if theme == "road":
        frame["source_feature_id"] = _stringify(_coalesce(frame, _semantic_candidates(source_semantics, "source_feature_id")))
        frame["name"] = _coalesce(frame, _semantic_candidates(source_semantics, "name"))
        frame["road_class"] = _stringify(_coalesce(frame, _semantic_candidates(source_semantics, "road_class"), default="road"))
        frame["fclass"] = frame["road_class"]
        frame["surface"] = _coalesce(frame, _semantic_candidates(source_semantics, "surface"))
        frame["lanes"] = _coalesce(frame, _semantic_candidates(source_semantics, "lanes"))
        return _filter_geometry(frame, {"LineString", "MultiLineString"})
    if theme == "water":
        frame["source_feature_id"] = _stringify(_coalesce(frame, _semantic_candidates(source_semantics, "source_feature_id")))
        frame["name"] = _coalesce(frame, _semantic_candidates(source_semantics, "name"))
        feature_kind_candidates = _semantic_candidates(source_semantics, "feature_kind")
        literal_kind = next((item for item in feature_kind_candidates if item in {"line", "polygon"}), None)
        frame["feature_kind"] = literal_kind or _coalesce(frame, feature_kind_candidates, default="water")
        frame["water_class"] = _stringify(_coalesce(frame, _semantic_candidates(source_semantics, "water_class"), default="water"))
        frame["fclass"] = frame["water_class"]
        frame["water_ty"] = frame["feature_kind"]
        frame["perennial_flag"] = _coalesce(frame, _semantic_candidates(source_semantics, "perennial_flag"))
        return _filter_geometry(frame, {"LineString", "MultiLineString", "Polygon", "MultiPolygon"})
    if theme == "poi":
        frame["source_feature_id"] = _stringify(_coalesce(frame, _semantic_candidates(source_semantics, "source_feature_id")))
        frame["name"] = _coalesce(frame, _semantic_candidates(source_semantics, "name"))
        frame["name_alt"] = _coalesce(frame, _semantic_candidates(source_semantics, "name_alt"))
        frame["category"] = _stringify(_coalesce(frame, _semantic_candidates(source_semantics, "category"), default="poi"))
        frame["admin_country"] = _coalesce(frame, _semantic_candidates(source_semantics, "admin_country"))
        frame = _ensure_point_geometry(frame)
        frame["GeoHash"] = _ensure_geohash(frame, precision=geohash_precision)
        return frame
    return frame
```

- [ ] **Step 3: Run normalization tests**

Run:

```bash
python -m pytest -q tests/test_track_b_source_normalization_semantics.py tests/test_track_b_source_normalization.py
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add services/track_b_source_normalization.py tests/test_track_b_source_normalization_semantics.py tests/test_track_b_source_normalization.py
git commit -m "feat: normalize sources from semantic contracts"
```

---

## Task 7: Semantic Parameter Binding

**Files:**
- Create: `agent/semantic_parameter_binding.py`
- Modify: `agent/parameter_binding.py`
- Test: `tests/test_semantic_parameter_binding.py`
- Test: `tests/test_parameter_default_binding.py`

- [ ] **Step 1: Write failing semantic binding tests**

Create `tests/test_semantic_parameter_binding.py`:

```python
from __future__ import annotations

from services.source_semantic_contract_service import SourceSemanticContract
from agent.semantic_parameter_binding import bind_source_semantic_parameters
from schemas.agent import WorkflowPlan


def _plan(job_type: str, algorithm_id: str) -> WorkflowPlan:
    return WorkflowPlan.model_validate(
        {
            "workflow_id": "wf_semantic",
            "run_id": "run-1",
            "job_type": job_type,
            "trigger": {"type": "user_query", "content": job_type},
            "tasks": [
                {
                    "step": 1,
                    "name": "fusion",
                    "description": "fusion",
                    "algorithm_id": algorithm_id,
                    "input": {"data_type_id": f"dt.{job_type}.bundle", "data_source_id": f"catalog.generic.{job_type}", "parameters": {}},
                    "output": {"data_type_id": f"dt.{job_type}.fused"},
                }
            ],
        }
    )


def test_semantic_binding_adds_building_height_and_priority_parameters() -> None:
    contract = SourceSemanticContract(
        run_id="run-1",
        job_type="building",
        selected_source_id="catalog.earthquake.building",
        target_crs="EPSG:4326",
        component_source_ids=["raw.microsoft.building", "raw.osm.building"],
        sources={},
        height_policy={
            "height_output_field": "height_raster",
            "canonical_height_field": "height",
            "positive_only": True,
            "vector_height_fields": {"raw.microsoft.building": "HEIGHT"},
        },
        parameter_hints={"source_priority_order": ["MS", "OSM"]},
        validation={"valid": True, "issues": []},
    )
    plan = _plan("building", "algo.fusion.building.v1")

    bound = bind_source_semantic_parameters(plan, contract)

    params = bound.tasks[0].input.parameters
    assert params["source_semantic_contract_path"] == "source_semantic_contract.json"
    assert params["height_output_field"] == "height_raster"
    assert params["canonical_height_field"] == "height"
    assert params["positive_only"] is True
    assert params["source_priority_order"] == ["MS", "OSM"]


def test_semantic_binding_adds_poi_geohash_precision() -> None:
    contract = SourceSemanticContract(
        run_id="run-1",
        job_type="poi",
        selected_source_id="catalog.generic.poi",
        target_crs="EPSG:4326",
        component_source_ids=["raw.osm.poi", "raw.gns.poi"],
        sources={},
        parameter_hints={"geohash_precision": 8},
        validation={"valid": True, "issues": []},
    )
    plan = _plan("poi", "algo.fusion.poi.v1")

    bound = bind_source_semantic_parameters(plan, contract)

    assert bound.tasks[0].input.parameters["geohash_precision"] == 8
```

Run:

```bash
python -m pytest -q tests/test_semantic_parameter_binding.py
```

Expected: FAIL because `agent.semantic_parameter_binding` does not exist.

- [ ] **Step 2: Implement semantic binder**

Create `agent/semantic_parameter_binding.py`:

```python
from __future__ import annotations

from services.source_semantic_contract_service import SourceSemanticContract
from schemas.agent import WorkflowPlan


def bind_source_semantic_parameters(plan: WorkflowPlan, contract: SourceSemanticContract) -> WorkflowPlan:
    for task in plan.tasks:
        if task.is_transform:
            continue
        params = dict(task.input.parameters or {})
        params["source_semantic_contract_path"] = "source_semantic_contract.json"
        if contract.job_type == "building":
            for key in ["height_output_field", "canonical_height_field", "positive_only"]:
                if key in contract.height_policy:
                    params[key] = contract.height_policy[key]
            priority = contract.parameter_hints.get("source_priority_order")
            if priority:
                params["source_priority_order"] = list(priority)
        elif contract.job_type == "poi":
            precision = contract.parameter_hints.get("geohash_precision")
            if precision is not None:
                params["geohash_precision"] = int(precision)
        task.input.parameters = params
    return plan
```

- [ ] **Step 3: Preserve default binding behavior**

Run existing tests:

```bash
python -m pytest -q tests/test_semantic_parameter_binding.py tests/test_parameter_default_binding.py
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add agent/semantic_parameter_binding.py tests/test_semantic_parameter_binding.py tests/test_parameter_default_binding.py
git commit -m "feat: bind parameters from source semantics"
```

---

## Task 8: Persist Source Semantic Contract In Agent Runs

**Files:**
- Modify: `schemas/agent.py`
- Modify: `services/agent_run_service.py`
- Modify: `api/routers/runs_v2.py`
- Test: `tests/test_agent_run_service_source_semantics.py`

- [ ] **Step 1: Write failing run service test**

Create `tests/test_agent_run_service_source_semantics.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from schemas.agent import RunCreateRequest, RunInputStrategy, RunTrigger, RunTriggerType, WorkflowPlan
from schemas.fusion import JobType
from services.agent_run_service import AgentRunService


def test_agent_run_service_persists_source_semantic_contract(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs", dispatch_eager=False)
    run_id = "run-semantic"
    run_dir = service.base_dir / run_id
    for name in ["input", "intermediate", "output", "logs"]:
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building", spatial_extent="bbox(0,0,1,1)"),
        input_strategy=RunInputStrategy.task_driven_auto,
    )
    plan = WorkflowPlan.model_validate(
        {
            "workflow_id": "wf",
            "run_id": run_id,
            "job_type": "building",
            "trigger": request.trigger.model_dump(mode="json"),
            "tasks": [
                {
                    "step": 1,
                    "name": "building",
                    "description": "building",
                    "algorithm_id": "algo.fusion.building.v1",
                    "input": {"data_type_id": "dt.building.bundle", "data_source_id": "catalog.earthquake.building", "parameters": {}},
                    "output": {"data_type_id": "dt.building.fused"},
                }
            ],
        }
    )
    class Contract:
        job_type = "building"
        height_policy = {"height_output_field": "height_raster", "canonical_height_field": "height", "positive_only": True}
        parameter_hints = {"source_priority_order": ["MS", "OSM"]}
        validation = {"valid": True, "issues": []}
        component_source_ids = ["raw.microsoft.building", "raw.osm.building"]
        def to_dict(self):
            return {
                "job_type": self.job_type,
                "component_source_ids": self.component_source_ids,
                "height_policy": self.height_policy,
                "parameter_hints": self.parameter_hints,
                "validation": self.validation,
                "sources": {},
            }
    contract = Contract()

    updated = service._persist_source_semantics(
        run_id=run_id,
        request=request,
        plan=plan,
        contract=contract,
    )

    contract_path = run_dir / "source_semantic_contract.json"
    assert contract_path.exists()
    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    assert payload["height_policy"]["height_output_field"] == "height_raster"
    assert updated.tasks[0].input.parameters["source_priority_order"] == ["MS", "OSM"]
```

Run:

```bash
python -m pytest -q tests/test_agent_run_service_source_semantics.py
```

Expected: FAIL because `_persist_source_semantics` does not exist.

- [ ] **Step 2: Add schema fields**

In `schemas/agent.py`, add defaults:

```python
class RunStatus(BaseModel):
    ...
    source_semantic_contract_path: Optional[str] = None
    source_semantic_summary: Dict[str, Any] = Field(default_factory=dict)
```

In `RunInspectionResponse`, add:

```python
    source_semantic_contract: Dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 3: Add AgentRunService persistence helper**

In `services/agent_run_service.py`, import `bind_source_semantic_parameters`, then add:

```python
    def _persist_source_semantics(self, *, run_id: str, request: RunCreateRequest, plan: WorkflowPlan, contract) -> WorkflowPlan:
        path = self.base_dir / run_id / "source_semantic_contract.json"
        path.write_text(json.dumps(contract.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        updated_plan = bind_source_semantic_parameters(plan, contract)
        self._persist_plan(self._plan_path(run_id), updated_plan)
        summary = {
            "job_type": contract.job_type,
            "component_source_ids": list(contract.component_source_ids),
            "valid": bool(contract.validation.get("valid")),
            "issue_count": len(contract.validation.get("issues") or []),
            "height_policy": dict(contract.height_policy),
        }
        current = self.get_run(run_id)
        if current is not None:
            current.source_semantic_contract_path = str(path)
            current.source_semantic_summary = summary
            self._runs[run_id] = current
            self._persist_status(current)
        self._update_status(
            run_id,
            RunPhase.running,
            checkpoint=self._checkpoint(stage="execution", plan_revision=self._extract_plan_revision(updated_plan)),
            event_kind="source_semantics_bound",
            event_message="Source semantic contract was bound to runtime parameters.",
            event_details={"source_semantic_contract_path": str(path), **summary},
        )
        return updated_plan
```

- [ ] **Step 4: Integrate contract build into task-driven input resolution**

In `AgentRunService.execute_run`, immediately after `_record_task_inputs_resolved(...)` and before `_should_use_tiled_building_runtime(...)`, build a contract when `request.input_strategy == RunInputStrategy.task_driven_auto` and `resolved_inputs is not None`.

Use component artifact paths from `resolved_inputs`:

```python
component_paths = self._source_component_paths_from_resolved_inputs(resolved_inputs)
contract = self.source_semantic_contract_service.build_contract(
    run_id=run_id,
    job_type=request.job_type.value,
    selected_source_id=resolved_inputs.selected_source_id or resolved_inputs.source_id,
    component_paths=component_paths,
    target_crs=runtime_request.target_crs or target_crs,
    raster_paths=self._raster_paths_for_source_semantics(resolved_inputs),
)
plan = self._persist_source_semantics(run_id=run_id, request=runtime_request, plan=plan, contract=contract)
```

Add helper methods:

```python
    def _source_component_paths_from_resolved_inputs(self, resolved_inputs) -> dict[str, Path]:
        paths: dict[str, Path] = {}
        coverage = dict(resolved_inputs.component_coverage or {})
        for source_id, payload in coverage.items():
            artifact_path = payload.get("artifact_path") if isinstance(payload, dict) else None
            if artifact_path:
                paths[source_id] = Path(str(artifact_path))
        return paths

    def _raster_paths_for_source_semantics(self, resolved_inputs) -> dict[str, Path]:
        return {}
```

If existing `component_coverage` does not include `artifact_path`, extend the input-resolution event payload to include the clipped zip or extracted vector paths used by execution.

- [ ] **Step 5: Add inspection loading**

In `api/routers/runs_v2.py`, update `_build_run_inspection_response`:

```python
source_semantic_contract = {}
semantic_path = getattr(status, "source_semantic_contract_path", None)
if semantic_path and Path(semantic_path).exists():
    source_semantic_contract = json.loads(Path(semantic_path).read_text(encoding="utf-8"))
...
source_semantic_contract=source_semantic_contract,
```

- [ ] **Step 6: Run tests**

Run:

```bash
python -m pytest -q tests/test_agent_run_service_source_semantics.py tests/test_agent_run_service_enhancements.py tests/test_api_integration.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add schemas/agent.py services/agent_run_service.py api/routers/runs_v2.py tests/test_agent_run_service_source_semantics.py
git commit -m "feat: persist source semantic contracts in runs"
```

---

## Task 9: Promote Multi-Source Building With Height Raster Into Shared Runtime

**Files:**
- Modify: `services/agent_run_service.py`
- Modify: `services/tiled_building_runtime_service.py`
- Modify: `services/track_b_national_scale_service.py`
- Test: `tests/test_agent_run_service_multisource_building_runtime.py`
- Test: `tests/test_tiled_multisource_building_runtime_service.py`
- Test: `tests/test_track_b_national_scale_service.py`

- [ ] **Step 1: Write failing route test**

Create `tests/test_agent_run_service_multisource_building_runtime.py`:

```python
from __future__ import annotations

from pathlib import Path

from schemas.agent import RunCreateRequest, RunInputStrategy, RunTrigger, RunTriggerType, WorkflowPlan
from schemas.fusion import JobType
from services.agent_run_service import AgentRunService
from services.tiled_building_runtime_service import TiledMultiSourceBuildingRunResult


def test_large_building_run_routes_to_multisource_runtime_when_semantics_exist(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs", dispatch_eager=False)
    run_id = "run-building"
    run_dir = service.base_dir / run_id
    for name in ["intermediate", "output", "logs"]:
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    output_path = run_dir / "output" / "fused_buildings.gpkg"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"gpkg")
    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building", spatial_extent="bbox(0,0,1,1)"),
        input_strategy=RunInputStrategy.task_driven_auto,
    )
    plan = WorkflowPlan.model_validate(
        {
            "workflow_id": "wf",
            "run_id": run_id,
            "job_type": "building",
            "trigger": request.trigger.model_dump(mode="json"),
            "tasks": [
                {
                    "step": 1,
                    "name": "building",
                    "description": "building",
                    "algorithm_id": "algo.fusion.building.v1",
                    "input": {"data_type_id": "dt.building.bundle", "data_source_id": "catalog.earthquake.building", "parameters": {"source_priority_order": ["MS", "OSM"]}},
                    "output": {"data_type_id": "dt.building.fused"},
                }
            ],
        }
    )
    captured: dict[str, object] = {}

    def fake_multisource(**kwargs):
        captured.update(kwargs)
        return TiledMultiSourceBuildingRunResult(
            output_path=output_path,
            tile_count=1,
            stitched_feature_count=1,
            tile_outputs=[],
            fusion_summary={"source_priority_order": ["MS", "OSM"]},
        )

    monkeypatch.setattr(service.tiled_building_runtime_service, "run_tiled_multisource_building_job", fake_multisource)

    result_path, repairs = service.run_multisource_building_execution_stage(
        run_id=run_id,
        request=request,
        plan=plan,
        intermediate_dir=run_dir / "intermediate",
        output_dir=run_dir / "output",
        vector_sources={"MS": tmp_path / "ms.gpkg", "OSM": tmp_path / "osm.gpkg"},
        raster_sources={"building_height": tmp_path / "height.tif"},
        resolved_aoi=None,
    )

    assert result_path == output_path
    assert repairs == []
    assert captured["source_priority_order"] == ("MS", "OSM")
    assert "building_height" in captured["raster_sources"]
```

Run:

```bash
python -m pytest -q tests/test_agent_run_service_multisource_building_runtime.py
```

Expected: FAIL because `run_multisource_building_execution_stage` does not exist.

- [ ] **Step 2: Add shared runtime multisource execution stage**

In `services/agent_run_service.py`, add:

```python
    def run_multisource_building_execution_stage(
        self,
        *,
        run_id: str,
        request: RunCreateRequest,
        plan: WorkflowPlan,
        intermediate_dir: Path,
        output_dir: Path,
        vector_sources: dict[str, Path],
        raster_sources: dict[str, Path] | None,
        resolved_aoi: ResolvedAOI | None,
        repair_records: Optional[List[RepairRecord]] = None,
    ) -> tuple[Path, List[RepairRecord]]:
        repair_records = repair_records if repair_records is not None else []
        request_bbox = self._resolve_request_bbox(request, resolved_aoi=resolved_aoi)
        if request_bbox is None:
            raise ValueError("Multi-source tiled building runtime requires an AOI bbox.")
        target_crs = self._request_with_effective_target_crs(run_id, request).target_crs
        tile_manifest = self.tile_partition_service.partition_bbox(
            bbox=request_bbox,
            bbox_crs="EPSG:4326",
            working_crs=target_crs,
        )
        manifest_path = intermediate_dir / "tile_manifest.json"
        manifest_path.write_text(json.dumps(tile_manifest.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        parameters = self._extract_step_parameters(plan)
        priority = tuple(parameters.get("source_priority_order") or vector_sources.keys())
        self._update_status(
            run_id,
            RunPhase.running,
            progress=58,
            checkpoint=self._checkpoint(stage="execution", plan_revision=self._extract_plan_revision(plan)),
            event_kind="multisource_building_runtime_started",
            event_message="Multi-source tiled building runtime started.",
            event_details={
                "tile_count": len(tile_manifest.tiles),
                "vector_source_aliases": sorted(vector_sources.keys()),
                "raster_source_aliases": sorted((raster_sources or {}).keys()),
            },
        )
        result = self.tiled_building_runtime_service.run_tiled_multisource_building_job(
            run_id=run_id,
            tile_manifest=tile_manifest,
            vector_sources=vector_sources,
            output_dir=output_dir,
            target_crs=target_crs,
            vector_source_crs=target_crs,
            raster_sources=raster_sources or {},
            source_priority_order=priority,
            parameters=parameters,
            on_event=lambda kind, details: self._record_tiled_runtime_event(
                run_id=run_id,
                plan=plan,
                repair_records=repair_records,
                kind=kind,
                details=details,
            ),
        )
        return result.output_path, repair_records
```

- [ ] **Step 3: Add routing decision**

Add helpers in `AgentRunService`:

```python
    def _should_use_multisource_building_runtime(self, request: RunCreateRequest, plan: WorkflowPlan) -> bool:
        if request.job_type != JobType.building or request.input_strategy != RunInputStrategy.task_driven_auto:
            return False
        parameters = self._extract_step_parameters(plan)
        priority = parameters.get("source_priority_order")
        return isinstance(priority, list) and len(priority) >= 2
```

In `execute_run`, select this path before the old single-reference tiled route when source semantic contract has at least two building vector sources. Keep the old `run_tiled_execution_stage` fallback for `OSM + single-reference` and low-risk compatibility.

- [ ] **Step 4: Bind vector/raster sources from semantic contract**

Add helpers:

```python
    def _building_sources_from_semantic_contract(self, contract) -> tuple[dict[str, Path], dict[str, Path]]:
        alias_by_source = {
            "raw.microsoft.building": "MS",
            "raw.local.microsoft.building": "MICROSOFT_LOCAL",
            "raw.openbuildingmap.building": "OBM",
            "raw.google.open_buildings.vector": "GOOGLE_OPEN_BUILDINGS",
            "raw.google.building": "GOOGLE",
            "raw.osm.building": "OSM",
        }
        vectors: dict[str, Path] = {}
        for source_id, entry in contract.sources.items():
            alias = alias_by_source.get(source_id)
            if alias:
                vectors[alias] = Path(entry.artifact_path)
        rasters = {
            "building_height": Path(path)
            for source_id, path in contract.height_policy.get("raster_height_sources", {}).items()
            if Path(path).exists()
        }
        return vectors, rasters
```

- [ ] **Step 5: Add height raster output assertion**

Extend `tests/test_tiled_multisource_building_runtime_service.py` with a synthetic raster fixture if one is not already present:

```python
def test_tiled_multisource_runtime_prefers_positive_height_raster_when_available(tmp_path: Path, monkeypatch) -> None:
    # Use monkeypatch for enrich_height_from_raster so the test focuses on runtime wiring.
    def fake_enrich(frame, raster, params):
        enriched = frame.copy()
        enriched["height_raster"] = 15.0
        enriched["height_final"] = 15.0
        enriched["height_final_source"] = "raster"
        return enriched

    monkeypatch.setattr("services.tiled_building_runtime_service.enrich_height_from_raster", fake_enrich)
    # Reuse existing fixture pattern in this file to create two vector source gpkg files and one tile manifest.
    # Assert output columns include height_raster, height_final, height_final_source and final source is raster.
```

Replace the comment block with the same vector/tile fixture construction already used in the file, then assert:

```python
assert "height_raster" in output.columns
assert float(output.loc[0, "height_final"]) == 15.0
assert output.loc[0, "height_final_source"] == "raster"
```

- [ ] **Step 6: Run building runtime tests**

Run:

```bash
python -m pytest -q tests/test_agent_run_service_multisource_building_runtime.py tests/test_tiled_multisource_building_runtime_service.py tests/test_track_b_national_scale_service.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add services/agent_run_service.py services/tiled_building_runtime_service.py services/track_b_national_scale_service.py tests/test_agent_run_service_multisource_building_runtime.py tests/test_tiled_multisource_building_runtime_service.py tests/test_track_b_national_scale_service.py
git commit -m "feat: promote multisource building runtime"
```

---

## Task 10: Stability Harness For Building / Road / Water / POI

**Files:**
- Create: `scripts/smoke_runtime_stability.py`
- Test: `tests/test_runtime_stability_smoke.py`

- [ ] **Step 1: Write failing smoke script tests**

Create `tests/test_runtime_stability_smoke.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from scripts import smoke_runtime_stability


def test_smoke_runtime_stability_writes_summary(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []

    class StubService:
        def __init__(self, *, root_dir: Path, cache_dir: Path) -> None:
            self.root_dir = root_dir
            self.cache_dir = cache_dir

        def build_theme_evidence(self, **kwargs):
            job_type = kwargs["job_type"]
            calls.append(job_type)
            output_root = Path(kwargs["output_root"])
            output_root.mkdir(parents=True, exist_ok=True)
            artifact = output_root / f"{job_type}.gpkg"
            artifact.write_bytes(b"gpkg")
            return {
                "job_type": job_type,
                "claim_state": "national_scale_supported",
                "artifact_path": str(artifact),
                "tile_count": 1,
            }

    monkeypatch.setattr(smoke_runtime_stability, "TrackBNationalScaleService", StubService)

    output = smoke_runtime_stability.run_smoke(
        root_dir=tmp_path,
        output_root=tmp_path / "smoke",
        bbox=(0.0, 0.0, 1.0, 1.0),
        target_crs="EPSG:4326",
        themes=["building", "road", "water", "poi"],
    )

    assert calls == ["building", "road", "water", "poi"]
    assert output["overall_status"] == "passed"
    summary_path = tmp_path / "smoke" / "runtime_stability_summary.json"
    assert json.loads(summary_path.read_text(encoding="utf-8"))["overall_status"] == "passed"
```

Run:

```bash
python -m pytest -q tests/test_runtime_stability_smoke.py
```

Expected: FAIL because script does not exist.

- [ ] **Step 2: Implement smoke script**

Create `scripts/smoke_runtime_stability.py`:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from services.track_b_national_scale_service import TrackBNationalScaleService


def _parse_bbox(value: str) -> tuple[float, float, float, float]:
    parts = [float(item.strip()) for item in value.split(",")]
    if len(parts) != 4:
        raise ValueError("--bbox must be minx,miny,maxx,maxy")
    return (parts[0], parts[1], parts[2], parts[3])


def run_smoke(
    *,
    root_dir: Path,
    output_root: Path,
    bbox: tuple[float, float, float, float],
    target_crs: str,
    themes: Iterable[str],
) -> dict[str, object]:
    output_root.mkdir(parents=True, exist_ok=True)
    service = TrackBNationalScaleService(root_dir=root_dir, cache_dir=output_root / "_cache")
    runs = []
    failures = []
    for theme in themes:
        theme_output = output_root / theme
        try:
            summary = service.build_theme_evidence(
                job_type=theme,
                request_bbox=bbox,
                target_crs=target_crs,
                output_root=theme_output,
                tile_width_m=40_000.0,
                tile_height_m=40_000.0,
                overlap_m=0.0,
            )
            runs.append(summary)
            if not Path(str(summary.get("artifact_path") or "")).exists():
                failures.append({"job_type": theme, "reason": "artifact_missing"})
        except Exception as exc:  # noqa: BLE001
            failures.append({"job_type": theme, "reason": f"{type(exc).__name__}: {exc}"})
    payload = {
        "overall_status": "passed" if not failures else "failed",
        "themes": list(themes),
        "runs": runs,
        "failures": failures,
    }
    (output_root / "runtime_stability_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--bbox", required=True)
    parser.add_argument("--target-crs", default="EPSG:4326")
    parser.add_argument("--themes", nargs="+", default=["building", "road", "water", "poi"])
    args = parser.parse_args()
    payload = run_smoke(
        root_dir=args.root_dir,
        output_root=args.output_root,
        bbox=_parse_bbox(args.bbox),
        target_crs=args.target_crs,
        themes=args.themes,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if payload["overall_status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run smoke script test**

Run:

```bash
python -m pytest -q tests/test_runtime_stability_smoke.py
```

Expected: PASS.

- [ ] **Step 4: Add focused Track B stability tests**

Run existing national-scale tests:

```bash
python -m pytest -q tests/test_track_b_national_scale_service.py tests/test_track_b_source_normalization.py tests/test_track_b_source_matrix.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/smoke_runtime_stability.py tests/test_runtime_stability_smoke.py
git commit -m "test: add runtime stability smoke harness"
```

---

## Task 11: Boundary Guards For Deferred Capabilities

**Files:**
- Modify: `api/routers/runs_v2.py`
- Modify: `agent/unsupported_intent.py`
- Test: `tests/test_run_preflight.py`
- Test: `tests/test_capability_inventory_matrix.py`

- [ ] **Step 1: Write/extend preflight tests**

Ensure `tests/test_run_preflight.py` contains cases equivalent to:

```python
def test_preflight_rejects_trajectory_to_road_execution(client) -> None:
    response = client.post(
        "/api/v2/runs/preflight",
        json={
            "job_type": "road",
            "trigger": {
                "type": "user_query",
                "content": "run trajectory to road fusion now",
                "spatial_extent": "bbox(0,0,1,1)",
            },
            "input_strategy": "task_driven_auto",
        },
    )

    payload = response.json()
    assert payload["allowed"] is False
    assert any(item["code"] == "trajectory_to_road_deferred" for item in payload["unsupported_intent"])


def test_preflight_allows_bounded_building_road_water_poi(client) -> None:
    for job_type in ["building", "road", "water", "poi"]:
        response = client.post(
            "/api/v2/runs/preflight",
            json={
                "job_type": job_type,
                "trigger": {
                    "type": "user_query",
                    "content": f"run bounded {job_type} fusion",
                    "spatial_extent": "bbox(0,0,1,1)",
                },
                "input_strategy": "task_driven_auto",
            },
        )
        assert response.status_code == 200
        assert response.json()["allowed"] is True
```

Run:

```bash
python -m pytest -q tests/test_run_preflight.py
```

Expected: FAIL only if the trajectory code or bounded allowlist is missing.

- [ ] **Step 2: Update unsupported-intent classifier**

In `agent/unsupported_intent.py`, ensure trajectory execution requests produce:

```python
{
    "code": "trajectory_to_road_deferred",
    "reason": "trajectory-to-road is reservation-only in this phase",
}
```

Ensure building / road / water / bounded POI are not rejected solely for being task-driven.

- [ ] **Step 3: Keep docs/capability inventory bounded**

Update capability tests if they assert old inspect-only recovery wording. Required claim changes:

- recovery: from inspect-only to automatic redispatch supported when worker/beat is enabled.
- source semantics: runtime-supported for building / road / water / POI selected sources.
- trajectory-to-road: reservation-only.
- frontend/auth/multitenant: out of scope.

Run:

```bash
python -m pytest -q tests/test_run_preflight.py tests/test_capability_inventory_matrix.py
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add agent/unsupported_intent.py api/routers/runs_v2.py tests/test_run_preflight.py tests/test_capability_inventory_matrix.py
git commit -m "test: preserve deferred capability boundaries"
```

---

## Task 12: Operations Evidence And Documentation Refresh

**Files:**
- Modify: `docs/no-ui-agent-operations.md`
- Modify: `docs/v2-operations.md`
- Modify: `docs/superpowers/specs/2026-05-06-capability-inventory.md`
- Test: `tests/test_documentation_contracts.py` or the existing docs/capability tests that cover these files

- [ ] **Step 1: Update operations wording**

In `docs/no-ui-agent-operations.md`, change recovery section from inspect-only to:

```markdown
- Use `GET /api/v2/operator/recovery` to inspect stale non-terminal runs and their checkpoint-derived recovery action.
- With worker beat enabled, `geofusion.recovery_tick` periodically acquires a per-run recovery lease and redispatches recoverable stale runs from the persisted request/checkpoint.
- Use `POST /api/v2/operator/recovery` for a manual recovery sweep or a single-run recovery request.
```

Do not add production SaaS, auth, multitenant, or frontend claims.

- [ ] **Step 2: Update source semantics wording**

In `docs/v2-operations.md`, add a compact runtime evidence note:

```markdown
Each task-driven building / road / water / POI run writes `source_semantic_contract.json` when sources are materialized. The contract records KG source metadata, actual field profiles, canonical field matches, height semantics, and parameter hints used by execution.
```

Keep trajectory-to-road as reservation-only.

- [ ] **Step 3: Update capability inventory**

In `docs/superpowers/specs/2026-05-06-capability-inventory.md`, update only the relevant statuses:

- `evidence.recovery_redispatch`: `core/runtime_supported`
- `source_semantics.runtime_binding`: `core/runtime_supported`
- `building.multisource_height_raster_runtime`: `core/bounded_supported` after Task 9 tests pass
- `trajectory_to_road.seam`: remains `deferred/reservation_only`

- [ ] **Step 4: Run documentation/capability tests**

Run:

```bash
python -m pytest -q tests/test_capability_inventory_matrix.py tests/test_scale_validation_doc_alignment.py tests/test_documentation_contracts.py
```

If `tests/test_documentation_contracts.py` does not exist, run the existing docs tests found by:

```bash
rg -n "capability|v2-operations|no-ui-agent-operations|documentation" tests
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/no-ui-agent-operations.md docs/v2-operations.md docs/superpowers/specs/2026-05-06-capability-inventory.md tests
git commit -m "docs: describe runtime recovery and source semantics"
```

---

## Task 13: Final Verification Matrix

**Files:**
- No code files unless previous tests reveal a bug.

- [ ] **Step 1: Run focused recovery suite**

Run:

```bash
python -m pytest -q tests/test_run_recovery_service.py tests/test_run_recovery_executor.py tests/test_worker_recovery_tick.py tests/test_operator_recovery_api.py
```

Expected: all tests PASS.

- [ ] **Step 2: Run source semantics suite**

Run:

```bash
python -m pytest -q tests/test_source_field_profile_registry.py tests/test_source_semantic_contract_service.py tests/test_track_b_source_normalization_semantics.py tests/test_semantic_parameter_binding.py tests/test_agent_run_service_source_semantics.py
```

Expected: all tests PASS.

- [ ] **Step 3: Run fusion runtime suite**

Run:

```bash
python -m pytest -q tests/test_agent_run_service_multisource_building_runtime.py tests/test_tiled_multisource_building_runtime_service.py tests/test_tiled_building_runtime_service.py tests/test_track_b_national_scale_service.py tests/test_track_b_source_normalization.py
```

Expected: all tests PASS.

- [ ] **Step 4: Run boundary and no-UI API suite**

Run:

```bash
python -m pytest -q tests/test_run_preflight.py tests/test_agent_run_service_enhancements.py tests/test_api_integration.py tests/test_worker_orchestration.py
```

Expected: all tests PASS.

- [ ] **Step 5: Run full test suite**

Run:

```bash
python -m pytest -q
```

Expected: all tests PASS. If the full suite is too slow for the local turn, record the exact subset already run and the first failing command to resume from.

- [ ] **Step 6: Run smoke harness on available local data**

Use a local AOI with available source data. Example:

```bash
python scripts/smoke_runtime_stability.py --root-dir E:\fyx\data --output-root runs\runtime-stability-smoke --bbox 29.0,-4.5,31.0,-2.0 --target-crs EPSG:32735 --themes building road water poi
```

Expected:

- `runs/runtime-stability-smoke/runtime_stability_summary.json` exists.
- `overall_status` is `passed`.
- Each theme has an artifact path.

- [ ] **Step 7: Verify git state**

Run:

```bash
git status --short --branch
```

Expected: only intentional tracked changes remain.

- [ ] **Step 8: Commit final fixes if needed**

If verification required additional tracked edits:

```bash
git add <changed-files>
git commit -m "fix: stabilize runtime source semantics"
```

---

## Review Checklist

- [ ] No auth, multitenant, or frontend work is included.
- [ ] trajectory-to-road remains rejected or reservation-only.
- [ ] building / road / water / POI are the only promoted runtime fusion domains.
- [ ] Recovery performs actual redispatch with lease protection, not just inspection.
- [ ] Every task-driven run can persist `source_semantic_contract.json` when sources are materialized.
- [ ] Field matching uses KG/source-contract semantics and actual file profiles before execution.
- [ ] Building runtime preserves vector heights and optional raster height into `height_final` and `height_final_source`.
- [ ] Road/water/POI normalization preserves canonical semantic fields needed by their algorithms.
- [ ] Stability smoke produces machine-readable evidence.

## User Review Points

Two choices affect implementation behavior but do not block starting the plan:

- Recovery default: this plan enables `GEOFUSION_RECOVERY_ENABLED=1` by default in worker beat. Set it to `0` only when you want inspect-only local runs.
- Height raster source policy: this plan treats height raster as optional. If no valid `estimated_height` raster is found, building fusion must still succeed and use the best vector height.
