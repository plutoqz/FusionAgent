# FusionAgent Engineering Runtime Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将工程应用侧待实现或待强化项收口为可测试、可审计、可在 no-UI operator 面读取的 v2 runtime 硬化合同。

**Architecture:** 计划不扩张 FusionAgent 的稳定任务边界，而是在现有 `planner -> validator -> executor -> healing/replan -> writeback` 链路上补齐 tool contract、KG grounding、unsupported-intent、telemetry、checkpoint recovery 和边界守护的可读证据。所有新增证据优先进入 `/api/v2/runs/{run_id}/inspection`、`/api/v2/operator/*`、`run.json`/`audit.jsonl` 派生视图和 capability inventory，而不是创建另一套平行观察系统。`building` 多源 raster utility、`poi` 泛化实体对齐、`trajectory-to-road`、生产级多租户和 live digital twin 均保持明确边界，不在本计划中提升 claim。

**Tech Stack:** Python 3.9-3.11, FastAPI, Pydantic, pytest, GeoPandas/Shapely where existing tests require them, existing FusionAgent services under `agent/`, `services/`, `api/routers/`, `schemas/`, `docs/`.

---

## Scope Lock

### In Scope

- 将 `evidence.tool_contracts_grounding_recovery` 从“分散的 core_next 雏形”收口为 operator 可读取的证据面。
- 在 run inspection 中暴露 tool contract report、grounding report、planning/runtime telemetry 和 checkpoint recovery hint。
- 增加 `/api/v2/operator/recovery`，用于列出 stale running/healing/validation runs 的恢复建议。
- 增加 `/api/v2/runs/preflight`，让 unsupported intent 可以在创建 run 目录前被结构化检查。
- 强化 scope guards，拒绝或澄清越界请求：开放域 GDP/人口/社媒、任意 schema customization、live event-feed、digital twin、trajectory-to-road 可执行化、通用 POI entity alignment。
- 更新 capability inventory / matrix / operations docs，使工程声明与代码证据一致。
- 增加 regression tests，保证 `building.multisource_fusion_semantics` 继续是 `research_utility`，`poi.task_driven_auto` 继续是 `bounded_supported`，`trajectory_to_road.seam` 继续是 `reservation_only`。

### Out Of Scope

- 不实现生产级认证、授权、多租户、审计合规后台或 SaaS 化运维。
- 不把 `scripts/run_benin_multisource_building_fusion.py` 提升为 shared runtime 的默认 building 主链。
- 不实现 `trajectory-to-road` 数据 ingestion、地图匹配或执行路径。
- 不把 scenario run 改造成 live event-feed replay、digital twin simulation 或长期自治 agent。
- 不扩展 POI 为通用实体对齐平台。

### Claim-State Rule

本计划完成后，只有当新 API、inspection 字段、docs 和 tests 全部落地时，才允许把 `evidence.tool_contracts_grounding_recovery` 从 `reservation_only` 提升为 `runtime_supported`。其他能力的 claim state 默认保持现状：

- `building.multisource_fusion_semantics`: `research_utility`
- `poi.task_driven_auto`: `bounded_supported`
- `trajectory_to_road.seam`: `reservation_only`
- `operator.web_workbench`: `research_utility`

## File Structure Map

### New Files

- `services/tool_contract_report_service.py`
  - Builds per-plan tool contract evidence from `WorkflowPlan` and `ToolRegistry`.
  - Does not execute tools.
  - Reports known/unknown algorithm ids, expected input/output data types, handler names, timeout, reserved flags, and issue codes.

- `tests/test_tool_contract_report_service.py`
  - Unit tests for the report service.
  - Covers registered algorithms, unknown algorithms, output mismatch, reserved trajectory transform.

- `tests/test_operator_recovery_api.py`
  - API-level tests for `/api/v2/operator/recovery`.
  - Uses temporary `runs/` root and persisted `run.json` records.

- `tests/test_runtime_boundary_guards.py`
  - Regression tests for capability boundary wording and guard behavior.
  - Keeps multi-source building, POI boundedness, trajectory reservation, and scenario non-digital-twin boundaries from drifting.

### Modified Files

- `schemas/agent.py`
  - Add `tool_contract_report`, `telemetry_summary`, and `recovery_hint` fields to `RunInspectionResponse`.
  - Add `RunPreflightResponse` for structured preflight checks.

- `schemas/operator.py`
  - Add `OperatorRecoveryResponse`.

- `services/run_telemetry_service.py`
  - Add `build_run_telemetry_summary`.
  - Keep existing `estimate_json_size_bytes` and `normalize_llm_usage`.

- `services/run_recovery_service.py`
  - Add a single-run helper for inspection-level recovery hints.
  - Keep `collect_recoverable_runs` behavior stable.

- `services/unsupported_intent_guard.py`
  - Extend keyword coverage and reason codes without widening allowed task families.

- `api/routers/runs_v2.py`
  - Add `/runs/preflight` before `/runs/{run_id}`.
  - Add `/operator/recovery`.
  - Extend `_build_run_inspection_response` to include tool contract, telemetry, and recovery hint.

- `services/scenario_run_service.py`
  - Reuse or align unsupported scope classifications for trajectory, digital twin, event-feed, and off-domain requests.

- `docs/superpowers/specs/2026-05-06-capability-inventory.md`
  - Update `evidence.tool_contracts_grounding_recovery` claim only after implementation tests pass.

- `docs/superpowers/specs/2026-05-06-capability-matrix.json`
  - Mirror capability inventory update and preserve existing boundary states.

- `docs/v2-operations.md`
  - Document preflight, recovery API, inspection fields, and scope boundaries.

- `docs/no-ui-agent-operations.md`
  - Add operator workflow notes for preflight and recovery.

- Existing tests to extend:
  - `tests/test_api_v2_integration.py`
  - `tests/test_unsupported_intent_guard.py`
  - `tests/test_scenario_scope_guards.py`
  - `tests/test_capability_inventory_matrix.py`
  - `tests/test_no_ui_maturity_check.py`

---

### Task 1: Tool Contract Report Service

**Files:**
- Create: `services/tool_contract_report_service.py`
- Create: `tests/test_tool_contract_report_service.py`
- Modify: `schemas/agent.py`
- Modify: `api/routers/runs_v2.py`
- Test: `tests/test_tool_contract_report_service.py`

- [ ] **Step 1: Write the failing service tests**

Create `tests/test_tool_contract_report_service.py` with:

```python
from __future__ import annotations

from services.tool_contract_report_service import build_tool_contract_report
from schemas.agent import RunTrigger, RunTriggerType, WorkflowPlan, WorkflowTask, WorkflowTaskInput, WorkflowTaskOutput


def _plan(*, algorithm_id: str = "algo.fusion.building.v1", output_type: str = "dt.building.fused") -> WorkflowPlan:
    return WorkflowPlan(
        workflow_id="wf-tool-contract",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="need building data"),
        context={},
        tasks=[
            WorkflowTask(
                step=1,
                name="building_fusion",
                description="building fusion",
                algorithm_id=algorithm_id,
                input=WorkflowTaskInput(data_type_id="dt.building.bundle", data_source_id="catalog.flood.building"),
                output=WorkflowTaskOutput(data_type_id=output_type),
                is_transform=False,
                kg_validated=True,
            )
        ],
        expected_output="building result",
    )


def test_tool_contract_report_marks_registered_task_as_valid() -> None:
    report = build_tool_contract_report(_plan())

    assert report["valid"] is True
    assert report["known_step_count"] == 1
    assert report["total_step_count"] == 1
    assert report["steps"][0]["algorithm_id"] == "algo.fusion.building.v1"
    assert report["steps"][0]["handler_name"] == "_handle_building"
    assert report["steps"][0]["input_types"] == ["dt.building.bundle"]
    assert report["steps"][0]["output_type"] == "dt.building.fused"
    assert report["steps"][0]["issue_codes"] == []


def test_tool_contract_report_flags_unknown_algorithm() -> None:
    report = build_tool_contract_report(_plan(algorithm_id="algo.fusion.unknown.v1"))

    assert report["valid"] is False
    assert report["known_step_count"] == 0
    assert report["steps"][0]["issue_codes"] == ["UNKNOWN_TOOL"]


def test_tool_contract_report_flags_output_type_mismatch() -> None:
    report = build_tool_contract_report(_plan(output_type="dt.road.fused"))

    assert report["valid"] is False
    assert "TOOL_OUTPUT_TYPE_MISMATCH" in report["steps"][0]["issue_codes"]


def test_tool_contract_report_marks_reserved_trajectory_transform() -> None:
    plan = _plan(algorithm_id="algo.transform.trajectory_to_road_candidate", output_type="dt.road.candidate")
    plan.tasks[0].is_transform = True
    plan.tasks[0].input.data_type_id = "dt.trajectory.raw"

    report = build_tool_contract_report(plan)

    assert report["valid"] is True
    assert report["steps"][0]["reserved"] is True
    assert report["steps"][0]["issue_codes"] == ["RESERVATION_ONLY_TOOL"]
```

- [ ] **Step 2: Run the new test to verify it fails**

Run:

```powershell
python -m pytest -q tests/test_tool_contract_report_service.py
```

Expected: fail with `ModuleNotFoundError: No module named 'services.tool_contract_report_service'`.

- [ ] **Step 3: Add the report service**

Create `services/tool_contract_report_service.py`:

```python
from __future__ import annotations

from typing import Any

from agent.tooling import ToolRegistry, build_default_tool_registry
from schemas.agent import WorkflowPlan, WorkflowTask


UNKNOWN_TOOL = "UNKNOWN_TOOL"
TOOL_INPUT_TYPE_MISMATCH = "TOOL_INPUT_TYPE_MISMATCH"
TOOL_OUTPUT_TYPE_MISMATCH = "TOOL_OUTPUT_TYPE_MISMATCH"
RESERVATION_ONLY_TOOL = "RESERVATION_ONLY_TOOL"


def build_tool_contract_report(
    plan: WorkflowPlan,
    *,
    registry: ToolRegistry | None = None,
) -> dict[str, Any]:
    tool_registry = registry or build_default_tool_registry()
    steps = [
        _build_step_report(task, tool_registry)
        for task in sorted(plan.tasks, key=lambda item: item.step)
    ]
    known_step_count = sum(1 for step in steps if step["known"])
    blocking_issue_codes = {
        UNKNOWN_TOOL,
        TOOL_INPUT_TYPE_MISMATCH,
        TOOL_OUTPUT_TYPE_MISMATCH,
    }
    valid = all(
        not any(code in blocking_issue_codes for code in step["issue_codes"])
        for step in steps
    )
    return {
        "valid": valid,
        "known_step_count": known_step_count,
        "total_step_count": len(steps),
        "steps": steps,
    }


def _build_step_report(task: WorkflowTask, registry: ToolRegistry) -> dict[str, Any]:
    spec = registry.get(task.algorithm_id)
    if spec is None:
        return {
            "step": task.step,
            "algorithm_id": task.algorithm_id,
            "known": False,
            "reserved": False,
            "handler_name": None,
            "input_types": [],
            "output_type": None,
            "timeout_seconds": None,
            "retry_count": None,
            "error_policy": {},
            "issue_codes": [UNKNOWN_TOOL],
            "evidence_refs": [f"plan.task(step={task.step}).algorithm_id", "agent.tooling.ToolRegistry"],
        }

    issue_codes: list[str] = []
    if task.input.data_type_id not in spec.input_types:
        issue_codes.append(TOOL_INPUT_TYPE_MISMATCH)
    if task.output.data_type_id != spec.output_type:
        issue_codes.append(TOOL_OUTPUT_TYPE_MISMATCH)
    reserved = spec.error_policy.get("reserved") == "true"
    if reserved:
        issue_codes.append(RESERVATION_ONLY_TOOL)

    return {
        "step": task.step,
        "algorithm_id": task.algorithm_id,
        "known": True,
        "reserved": reserved,
        "handler_name": spec.handler_name,
        "input_types": list(spec.input_types),
        "output_type": spec.output_type,
        "timeout_seconds": spec.timeout_seconds,
        "retry_count": spec.retry_count,
        "error_policy": dict(spec.error_policy),
        "issue_codes": issue_codes,
        "evidence_refs": [
            f"plan.task(step={task.step}).algorithm_id",
            f"plan.task(step={task.step}).input.data_type_id",
            f"plan.task(step={task.step}).output.data_type_id",
            "agent.tooling.ToolRegistry",
        ],
    }
```

- [ ] **Step 4: Run the service tests**

Run:

```powershell
python -m pytest -q tests/test_tool_contract_report_service.py
```

Expected: `4 passed`.

- [ ] **Step 5: Add the inspection schema field**

Modify `schemas/agent.py` `RunInspectionResponse`:

```python
class RunInspectionResponse(BaseModel):
    run: RunStatus
    plan: Optional[WorkflowPlan] = None
    audit_events: List[RunEvent] = Field(default_factory=list)
    artifact: RunInspectionArtifact = Field(default_factory=RunInspectionArtifact)
    kg_path_trace: Dict[str, Any] = Field(default_factory=dict)
    tool_contract_report: Dict[str, Any] = Field(default_factory=dict)
    telemetry_summary: Dict[str, Any] = Field(default_factory=dict)
    recovery_hint: Dict[str, Any] = Field(default_factory=dict)
    digest: RunInspectionDigest = Field(default_factory=RunInspectionDigest)
```

- [ ] **Step 6: Wire the report into run inspection**

Modify `api/routers/runs_v2.py` imports:

```python
from services.tool_contract_report_service import build_tool_contract_report
```

Modify `_build_run_inspection_response`:

```python
def _build_run_inspection_response(run_id: str, status: RunStatus) -> RunInspectionResponse:
    plan = agent_run_service.get_plan(run_id)
    audit_events = agent_run_service.get_audit_events(run_id)
    artifact_path = agent_run_service.get_artifact_path(run_id)
    artifact = RunInspectionArtifact(
        available=bool(artifact_path and artifact_path.exists()),
        filename=(artifact_path.name if artifact_path and artifact_path.exists() else None),
        path=(str(artifact_path) if artifact_path and artifact_path.exists() else None),
        size_bytes=(artifact_path.stat().st_size if artifact_path and artifact_path.exists() else None),
        download_path=(f"/api/v2/runs/{run_id}/artifact" if artifact_path and artifact_path.exists() else None),
    )
    return RunInspectionResponse(
        run=status,
        plan=plan,
        audit_events=audit_events,
        artifact=artifact,
        kg_path_trace=build_kg_path_trace(plan) if plan is not None else {},
        tool_contract_report=build_tool_contract_report(plan) if plan is not None else {},
        digest=derive_run_inspection_digest(status, audit_events),
    )
```

- [ ] **Step 7: Add API regression coverage**

Extend `tests/test_api_v2_integration.py::test_v2_run_task_driven_auto_input_integration` after `inspection = inspection_resp.json()`:

```python
    tool_contract_report = inspection["tool_contract_report"]
    assert tool_contract_report["valid"] is True
    assert tool_contract_report["steps"][0]["algorithm_id"] == "algo.fusion.building.v1"
    assert tool_contract_report["steps"][0]["handler_name"] == "_handle_building"
    assert tool_contract_report["steps"][0]["issue_codes"] == []
```

- [ ] **Step 8: Run focused tests**

Run:

```powershell
python -m pytest -q tests/test_tool_contract_report_service.py tests/test_api_v2_integration.py::test_v2_run_task_driven_auto_input_integration
```

Expected: all selected tests pass.

- [ ] **Step 9: Commit**

Run:

```powershell
git add services/tool_contract_report_service.py tests/test_tool_contract_report_service.py schemas/agent.py api/routers/runs_v2.py tests/test_api_v2_integration.py
git commit -m "feat: expose tool contract evidence in run inspection"
```

---

### Task 2: Telemetry Summary In Inspection

**Files:**
- Modify: `services/run_telemetry_service.py`
- Modify: `api/routers/runs_v2.py`
- Modify: `tests/test_run_telemetry_service.py`
- Modify: `tests/test_api_v2_integration.py`

- [ ] **Step 1: Write failing telemetry summary tests**

Append to `tests/test_run_telemetry_service.py`:

```python
from schemas.agent import RunEvent, RunPhase, RunStatus, RunTrigger, RunTriggerType, WorkflowPlan
from schemas.fusion import JobType
from services.run_telemetry_service import build_run_telemetry_summary


def test_build_run_telemetry_summary_uses_status_planning_telemetry() -> None:
    status = RunStatus(
        run_id="run-telemetry",
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        phase=RunPhase.succeeded,
        target_crs="EPSG:32643",
        planning_telemetry={"provider": "mock", "model": "mock-model", "elapsed_ms": 12},
        created_at="2026-05-20T00:00:00+00:00",
        updated_at="2026-05-20T00:00:01+00:00",
    )
    events = [
        RunEvent(
            timestamp="2026-05-20T00:00:00+00:00",
            kind="plan_created",
            phase=RunPhase.planning,
            message="plan",
            details={"grounding_score": 1.0},
        ),
        RunEvent(
            timestamp="2026-05-20T00:00:01+00:00",
            kind="run_succeeded",
            phase=RunPhase.succeeded,
            message="ok",
        ),
    ]

    summary = build_run_telemetry_summary(status=status, audit_events=events, plan=None)

    assert summary["planning"]["provider"] == "mock"
    assert summary["planning"]["elapsed_ms"] == 12
    assert summary["audit_event_count"] == 2
    assert summary["event_counts"] == {"plan_created": 1, "run_succeeded": 1}
    assert summary["last_event_kind"] == "run_succeeded"
```

- [ ] **Step 2: Run the telemetry test to verify it fails**

Run:

```powershell
python -m pytest -q tests/test_run_telemetry_service.py::test_build_run_telemetry_summary_uses_status_planning_telemetry
```

Expected: fail with `ImportError` for `build_run_telemetry_summary`.

- [ ] **Step 3: Implement telemetry summary helper**

Append to `services/run_telemetry_service.py`:

```python
def build_run_telemetry_summary(*, status: object, audit_events: list[object], plan: object | None) -> dict[str, Any]:
    plan_context = getattr(plan, "context", {}) if plan is not None else {}
    if not isinstance(plan_context, dict):
        plan_context = {}
    status_planning = getattr(status, "planning_telemetry", {}) or {}
    planning = status_planning if isinstance(status_planning, dict) else {}
    if not planning:
        raw_plan_telemetry = plan_context.get("planning_telemetry", {})
        planning = raw_plan_telemetry if isinstance(raw_plan_telemetry, dict) else {}

    event_counts: dict[str, int] = {}
    last_event_kind: str | None = None
    last_event_at: str | None = None
    for event in audit_events:
        kind = str(getattr(event, "kind", "") or "").strip()
        if not kind:
            continue
        event_counts[kind] = event_counts.get(kind, 0) + 1
        last_event_kind = kind
        last_event_at = str(getattr(event, "timestamp", "") or "") or None

    return {
        "planning": dict(planning),
        "audit_event_count": len(audit_events),
        "event_counts": event_counts,
        "last_event_kind": last_event_kind,
        "last_event_at": last_event_at,
        "plan_revision": getattr(status, "plan_revision", 0),
        "attempt_no": getattr(status, "attempt_no", 0),
        "current_step": getattr(status, "current_step", None),
    }
```

- [ ] **Step 4: Run telemetry unit tests**

Run:

```powershell
python -m pytest -q tests/test_run_telemetry_service.py
```

Expected: all tests pass.

- [ ] **Step 5: Wire telemetry into inspection**

Modify `api/routers/runs_v2.py` imports:

```python
from services.run_telemetry_service import build_run_telemetry_summary
```

Modify `_build_run_inspection_response`:

```python
        telemetry_summary=build_run_telemetry_summary(
            status=status,
            audit_events=audit_events,
            plan=plan,
        ),
```

- [ ] **Step 6: Add API assertion**

Extend `tests/test_api_v2_integration.py::test_v2_run_task_driven_auto_input_integration`:

```python
    telemetry_summary = inspection["telemetry_summary"]
    assert telemetry_summary["audit_event_count"] >= 1
    assert telemetry_summary["event_counts"]["plan_created"] == 1
    assert telemetry_summary["plan_revision"] >= 1
```

- [ ] **Step 7: Run focused tests**

Run:

```powershell
python -m pytest -q tests/test_run_telemetry_service.py tests/test_api_v2_integration.py::test_v2_run_task_driven_auto_input_integration
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit**

Run:

```powershell
git add services/run_telemetry_service.py api/routers/runs_v2.py tests/test_run_telemetry_service.py tests/test_api_v2_integration.py
git commit -m "feat: summarize run telemetry in inspection"
```

---

### Task 3: Recovery Hint And Operator Recovery API

**Files:**
- Modify: `services/run_recovery_service.py`
- Modify: `schemas/operator.py`
- Modify: `api/routers/runs_v2.py`
- Create: `tests/test_operator_recovery_api.py`
- Modify: `tests/test_run_recovery_service.py`

- [ ] **Step 1: Write failing recovery hint test**

Append to `tests/test_run_recovery_service.py`:

```python
from services.run_recovery_service import build_recovery_hint


def test_build_recovery_hint_marks_terminal_runs_not_recoverable() -> None:
    hint = build_recovery_hint(
        {
            "phase": "succeeded",
            "checkpoint": {"stage": "execution"},
            "updated_at": "2026-05-20T00:00:00+00:00",
        }
    )

    assert hint == {
        "recoverable": False,
        "recovery_action": "none",
        "reason": "terminal_or_fresh_run",
        "checkpoint": {"stage": "execution"},
    }


def test_build_recovery_hint_uses_checkpoint_stage_for_running_run() -> None:
    hint = build_recovery_hint(
        {
            "phase": "running",
            "checkpoint": {"stage": "execution", "plan_revision": 1, "current_step": 2},
            "updated_at": "2026-05-20T00:00:00+00:00",
        }
    )

    assert hint["recoverable"] is True
    assert hint["recovery_action"] == "redispatch_from_execution"
    assert hint["checkpoint"]["current_step"] == 2
```

- [ ] **Step 2: Run the recovery hint test to verify it fails**

Run:

```powershell
python -m pytest -q tests/test_run_recovery_service.py::test_build_recovery_hint_marks_terminal_runs_not_recoverable tests/test_run_recovery_service.py::test_build_recovery_hint_uses_checkpoint_stage_for_running_run
```

Expected: fail with `ImportError` for `build_recovery_hint`.

- [ ] **Step 3: Implement recovery hint helper**

Append to `services/run_recovery_service.py`:

```python
def build_recovery_hint(run_payload: dict[str, Any]) -> dict[str, Any]:
    checkpoint = run_payload.get("checkpoint")
    if not isinstance(checkpoint, dict):
        checkpoint = {}
    action = classify_recovery_action(run_payload)
    recoverable = action in {
        "redispatch_full_run",
        "redispatch_from_validation",
        "redispatch_from_execution",
    }
    return {
        "recoverable": recoverable,
        "recovery_action": action if recoverable else "none",
        "reason": "checkpoint_recoverable" if recoverable else "terminal_or_fresh_run",
        "checkpoint": dict(checkpoint),
    }
```

- [ ] **Step 4: Run recovery service tests**

Run:

```powershell
python -m pytest -q tests/test_run_recovery_service.py
```

Expected: all tests pass.

- [ ] **Step 5: Add operator recovery schema**

Modify `schemas/operator.py`:

```python
class OperatorRecoveryResponse(BaseModel):
    records: List[Dict[str, Any]] = Field(default_factory=list)
```

- [ ] **Step 6: Add recovery route**

Modify `api/routers/runs_v2.py` imports:

```python
from schemas.operator import OperatorRecoveryResponse, OperatorRunListResponse, OperatorRuntimeSummaryResponse
from services.run_recovery_service import build_recovery_hint
```

Add this route before `@router.get("/runs/{run_id}", response_model=RunStatus)`:

```python
@router.get("/operator/recovery", response_model=OperatorRecoveryResponse)
async def get_operator_recovery(stale_after_seconds: int = Query(default=300, ge=1, le=86400)) -> OperatorRecoveryResponse:
    records = agent_run_service.collect_recoverable_runs(stale_after_seconds=stale_after_seconds)
    return OperatorRecoveryResponse(records=records)
```

Modify `_build_run_inspection_response` to pass a hint:

```python
        recovery_hint=build_recovery_hint(status.model_dump(mode="json")),
```

- [ ] **Step 7: Write API recovery test**

Create `tests/test_operator_recovery_api.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from api.app import create_app
import api.routers.runs_v2 as runs_v2_router
from services.agent_run_service import AgentRunService


def test_operator_recovery_endpoint_lists_stale_recoverable_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "run-stale"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": "run-stale",
                "phase": "running",
                "job_type": "building",
                "updated_at": "2026-04-23T00:00:00+00:00",
                "checkpoint": {"stage": "execution", "plan_revision": 1, "current_step": 2},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    service = AgentRunService(base_dir=runs_root)
    monkeypatch.setattr(runs_v2_router, "agent_run_service", service)

    response = TestClient(create_app()).get("/api/v2/operator/recovery?stale_after_seconds=300")

    assert response.status_code == 200
    payload = response.json()
    assert payload["records"][0]["run_id"] == "run-stale"
    assert payload["records"][0]["recovery_action"] == "redispatch_from_execution"
```

- [ ] **Step 8: Run focused recovery tests**

Run:

```powershell
python -m pytest -q tests/test_run_recovery_service.py tests/test_operator_recovery_api.py
```

Expected: all selected tests pass.

- [ ] **Step 9: Commit**

Run:

```powershell
git add services/run_recovery_service.py schemas/operator.py api/routers/runs_v2.py tests/test_run_recovery_service.py tests/test_operator_recovery_api.py
git commit -m "feat: expose operator recovery inspection"
```

---

### Task 4: Structured Run Preflight And Unsupported Intent Guard

**Files:**
- Modify: `services/unsupported_intent_guard.py`
- Modify: `schemas/agent.py`
- Modify: `api/routers/runs_v2.py`
- Modify: `tests/test_unsupported_intent_guard.py`
- Modify: `tests/test_api_v2_integration.py`

- [ ] **Step 1: Add failing unsupported-intent tests**

Append to `tests/test_unsupported_intent_guard.py`:

```python
def test_classify_unsupported_intent_flags_trajectory_to_road_execution_request() -> None:
    module = _load_guard_module()

    issues = module.classify_unsupported_intent(
        "please ingest GPS trajectory and build a road network",
        job_type="road",
    )

    assert issues == [
        {
            "code": "RESERVATION_ONLY_TRAJECTORY_TO_ROAD",
            "message": "Trajectory-to-road is reserved metadata only and is not an executable runtime path.",
            "matched_keyword": "trajectory",
            "job_type": "road",
        }
    ]


def test_classify_unsupported_intent_flags_unbounded_poi_entity_alignment() -> None:
    module = _load_guard_module()

    issues = module.classify_unsupported_intent(
        "merge all POI businesses and solve global entity resolution",
        job_type="poi",
    )

    assert issues == [
        {
            "code": "UNBOUNDED_POI_ENTITY_ALIGNMENT",
            "message": "POI fusion is bounded and does not support open-ended entity alignment.",
            "matched_keyword": "entity resolution",
            "job_type": "poi",
        }
    ]
```

- [ ] **Step 2: Run the new guard tests to verify they fail**

Run:

```powershell
python -m pytest -q tests/test_unsupported_intent_guard.py
```

Expected: the two new tests fail because the new issue codes are not emitted.

- [ ] **Step 3: Extend the guard classifier**

Modify `services/unsupported_intent_guard.py` by keeping existing issue behavior and adding ordered keyword groups:

```python
UNSUPPORTED_INTENT_RULES = [
    {
        "code": "RESERVATION_ONLY_TRAJECTORY_TO_ROAD",
        "message": "Trajectory-to-road is reserved metadata only and is not an executable runtime path.",
        "keywords": ("trajectory", "gps trace", "gps trajectory", "轨迹", "轨迹到道路"),
        "job_types": ("road",),
    },
    {
        "code": "UNBOUNDED_POI_ENTITY_ALIGNMENT",
        "message": "POI fusion is bounded and does not support open-ended entity alignment.",
        "keywords": ("entity resolution", "entity alignment", "all businesses", "global entity", "通用实体对齐"),
        "job_types": ("poi",),
    },
    {
        "code": "OFF_DOMAIN_REQUEST",
        "message": "Request includes off-domain content that the fusion workflow does not support.",
        "keywords": ("gdp", "population heatmap", "stock market", "人口热力", "国内生产总值"),
        "job_types": ("building", "road", "water", "poi"),
    },
    {
        "code": "UNSUPPORTED_OUTPUT_SCHEMA_CUSTOMIZATION",
        "message": "Request asks for output schema customization that is not supported.",
        "keywords": ("列名改成中文", "rename all columns", "custom output schema", "schema customization"),
        "job_types": ("building", "road", "water", "poi"),
    },
]


def classify_unsupported_intent(content: str, *, job_type: str) -> list[dict[str, str]]:
    normalized = str(content or "").casefold()
    normalized_job_type = str(job_type or "").casefold()
    for rule in UNSUPPORTED_INTENT_RULES:
        if normalized_job_type not in rule["job_types"]:
            continue
        for keyword in rule["keywords"]:
            if keyword.casefold() in normalized:
                return [
                    {
                        "code": rule["code"],
                        "message": rule["message"],
                        "matched_keyword": keyword,
                        "job_type": normalized_job_type,
                    }
                ]
    return []
```

If the existing file already defines constants, replace its classifier body with the code above and preserve imports.

- [ ] **Step 4: Run unsupported guard tests**

Run:

```powershell
python -m pytest -q tests/test_unsupported_intent_guard.py
```

Expected: all tests pass.

- [ ] **Step 5: Add preflight schemas**

Modify `schemas/agent.py`:

```python
class RunPreflightResponse(BaseModel):
    allowed: bool
    unsupported_intent: List[Dict[str, str]] = Field(default_factory=list)
```

- [ ] **Step 6: Add preflight route**

Modify `api/routers/runs_v2.py` import list from `schemas.agent` to include `RunPreflightResponse`.

Add this route before `@router.get("/runs/{run_id}", response_model=RunStatus)`:

```python
@router.post("/runs/preflight", response_model=RunPreflightResponse)
async def preflight_run(request: RunCreateRequest) -> RunPreflightResponse:
    issues = classify_unsupported_intent(request.trigger.content, job_type=request.job_type)
    return RunPreflightResponse(allowed=not issues, unsupported_intent=issues)
```

- [ ] **Step 7: Add API preflight test**

Append to `tests/test_api_v2_integration.py`:

```python
def test_v2_run_preflight_reports_unsupported_intent_without_creating_run(client: TestClient) -> None:
    response = client.post(
        "/api/v2/runs/preflight",
        json={
            "job_type": "road",
            "trigger": {
                "type": "user_query",
                "content": "please ingest GPS trajectory and build a road network",
            },
            "input_strategy": "task_driven_auto",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "allowed": False,
        "unsupported_intent": [
            {
                "code": "RESERVATION_ONLY_TRAJECTORY_TO_ROAD",
                "message": "Trajectory-to-road is reserved metadata only and is not an executable runtime path.",
                "matched_keyword": "trajectory",
                "job_type": "road",
            }
        ],
    }
```

- [ ] **Step 8: Run focused preflight tests**

Run:

```powershell
python -m pytest -q tests/test_unsupported_intent_guard.py tests/test_api_v2_integration.py::test_v2_run_preflight_reports_unsupported_intent_without_creating_run tests/test_api_v2_integration.py::test_v2_run_rejects_unsupported_intent_with_structured_422
```

Expected: all selected tests pass.

- [ ] **Step 9: Commit**

Run:

```powershell
git add services/unsupported_intent_guard.py schemas/agent.py api/routers/runs_v2.py tests/test_unsupported_intent_guard.py tests/test_api_v2_integration.py
git commit -m "feat: add structured runtime preflight guard"
```

---

### Task 5: Scenario Scope Guard Alignment

**Files:**
- Modify: `services/scenario_run_service.py`
- Modify: `tests/test_scenario_scope_guards.py`

- [ ] **Step 1: Add failing scenario guard tests**

Append to `tests/test_scenario_scope_guards.py`:

```python
def test_scenario_guard_rejects_trajectory_to_road_execution_request() -> None:
    decision = classify_scenario_request(
        scenario_name="Road trajectory ingestion",
        trigger_content="ingest GPS trajectory and produce road network",
        job_types=[JobType.road],
    )

    assert decision["decision"] == "reject"
    assert decision["reason_code"] == "RESERVATION_ONLY_TRAJECTORY_TO_ROAD"


def test_scenario_guard_clarifies_unbounded_poi_entity_alignment() -> None:
    decision = classify_scenario_request(
        scenario_name="Global POI entity alignment",
        trigger_content="merge all POI businesses with global entity resolution",
        job_types=[JobType.poi],
    )

    assert decision["decision"] == "clarify"
    assert decision["reason_code"] == "UNBOUNDED_POI_ENTITY_ALIGNMENT"
```

- [ ] **Step 2: Run scenario guard tests to verify failure**

Run:

```powershell
python -m pytest -q tests/test_scenario_scope_guards.py
```

Expected: the two new tests fail because these exact reason codes are not returned.

- [ ] **Step 3: Align scenario classifier**

Modify `services/scenario_run_service.py` inside `classify_scenario_request` after `combined_text` is computed:

```python
    if any(keyword in combined_text for keyword in ("trajectory", "gps trajectory", "gps trace", "轨迹", "轨迹到道路")):
        return {
            "decision": "reject",
            "reason_code": "RESERVATION_ONLY_TRAJECTORY_TO_ROAD",
            "message": "Trajectory-to-road is reserved metadata only and is not an executable runtime path.",
        }

    if any(keyword in combined_text for keyword in ("entity resolution", "entity alignment", "all poi businesses", "global entity", "通用实体对齐")):
        return {
            "decision": "clarify",
            "reason_code": "UNBOUNDED_POI_ENTITY_ALIGNMENT",
            "message": "POI fusion is bounded and does not support open-ended entity alignment.",
        }
```

Keep the existing event-feed, digital-twin, dependency, and unsupported-layer checks.

- [ ] **Step 4: Run scenario scope tests**

Run:

```powershell
python -m pytest -q tests/test_scenario_scope_guards.py tests/test_scenario_run_service.py
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add services/scenario_run_service.py tests/test_scenario_scope_guards.py
git commit -m "fix: align scenario scope guard boundaries"
```

---

### Task 6: Capability Boundary Regression Tests

**Files:**
- Create: `tests/test_runtime_boundary_guards.py`
- Modify: `tests/test_capability_inventory_matrix.py`

- [ ] **Step 1: Add capability boundary regression tests**

Create `tests/test_runtime_boundary_guards.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from agent.tooling import build_default_tool_registry


def _capability_matrix() -> dict:
    return json.loads(Path("docs/superpowers/specs/2026-05-06-capability-matrix.json").read_text(encoding="utf-8"))


def test_building_multisource_remains_research_utility_boundary() -> None:
    matrix = _capability_matrix()
    item = {
        capability["capability_id"]: capability
        for capability in matrix["themes"]["building"]
    }["building.multisource_fusion_semantics"]

    assert item["status"] == "optional"
    assert item["claim_state"] == "research_utility"
    assert "runtime_output/fused_buildings.gpkg" in item["evidence_contract"]


def test_poi_runtime_claim_remains_bounded_supported() -> None:
    matrix = _capability_matrix()
    item = {
        capability["capability_id"]: capability
        for capability in matrix["themes"]["poi"]
    }["poi.task_driven_auto"]

    assert item["status"] == "core"
    assert item["claim_state"] == "bounded_supported"


def test_trajectory_to_road_tool_is_reserved_only() -> None:
    registry = build_default_tool_registry()
    spec = registry.require("algo.transform.trajectory_to_road_candidate")

    assert spec.error_policy["reserved"] == "true"
    assert spec.handler_name == "_handle_reserved_trajectory_pretransform"
```

- [ ] **Step 2: Run boundary tests**

Run:

```powershell
python -m pytest -q tests/test_runtime_boundary_guards.py
```

Expected: all tests pass before code changes. If any test fails, stop and inspect whether a boundary was already changed by another branch.

- [ ] **Step 3: Extend capability matrix test for evidence hardening item**

Append to `tests/test_capability_inventory_matrix.py`:

```python
def test_capability_matrix_tracks_runtime_hardening_evidence_boundary() -> None:
    payload = json.loads(
        Path("docs/superpowers/specs/2026-05-06-capability-matrix.json").read_text(
            encoding="utf-8"
        )
    )
    evidence = {
        item["capability_id"]: item for item in payload["themes"]["evidence"]
    }

    item = evidence["evidence.tool_contracts_grounding_recovery"]
    assert item["status"] in {"core_next", "core"}
    assert "tool_contract_report" in item["evidence_contract"]
    assert "grounding_report" in item["evidence_contract"]
    assert "recovery_hint" in item["evidence_contract"]
```

- [ ] **Step 4: Run matrix test to verify it fails before docs update**

Run:

```powershell
python -m pytest -q tests/test_capability_inventory_matrix.py::test_capability_matrix_tracks_runtime_hardening_evidence_boundary
```

Expected: fail because the current matrix still lists `future_tests`, `future_inspection_surface`, and `future_operations_wording`.

- [ ] **Step 5: Commit boundary tests after Task 7 updates docs**

This step is intentionally executed after Task 7 changes the capability matrix. Use:

```powershell
git add tests/test_runtime_boundary_guards.py tests/test_capability_inventory_matrix.py
git commit -m "test: guard runtime capability boundaries"
```

---

### Task 7: Capability Inventory And Operations Documentation

**Files:**
- Modify: `docs/superpowers/specs/2026-05-06-capability-inventory.md`
- Modify: `docs/superpowers/specs/2026-05-06-capability-matrix.json`
- Modify: `docs/v2-operations.md`
- Modify: `docs/no-ui-agent-operations.md`
- Modify: `tests/test_capability_inventory_matrix.py`

- [ ] **Step 1: Update capability inventory wording**

Modify the Evidence section in `docs/superpowers/specs/2026-05-06-capability-inventory.md` so `evidence.tool_contracts_grounding_recovery` reads:

```markdown
| `evidence.tool_contracts_grounding_recovery` | `core` | `runtime_supported` | `tool_contract_report`, `grounding_report`, `telemetry_summary`, `recovery_hint`, `/api/v2/operator/recovery`, `/api/v2/runs/preflight`, focused tests, operations wording | `services/tool_contract_report_service.py`, `services/plan_grounding_service.py`, `services/run_telemetry_service.py`, `services/run_recovery_service.py`, `api/routers/runs_v2.py`, `docs/v2-operations.md` |
```

- [ ] **Step 2: Update capability matrix JSON**

In `docs/superpowers/specs/2026-05-06-capability-matrix.json`, replace the `evidence.tool_contracts_grounding_recovery` item with:

```json
{
  "capability_id": "evidence.tool_contracts_grounding_recovery",
  "theme": "evidence",
  "status": "core",
  "claim_state": "runtime_supported",
  "evidence_contract": [
    "tool_contract_report",
    "grounding_report",
    "telemetry_summary",
    "recovery_hint",
    "/api/v2/operator/recovery",
    "/api/v2/runs/preflight",
    "focused_tests",
    "operations_wording"
  ],
  "owner_files": [
    "services/tool_contract_report_service.py",
    "services/plan_grounding_service.py",
    "services/run_telemetry_service.py",
    "services/run_recovery_service.py",
    "api/routers/runs_v2.py",
    "docs/v2-operations.md"
  ]
}
```

- [ ] **Step 3: Document inspection and preflight in operations**

Add this subsection to `docs/v2-operations.md` under `Operator Inspection API`:

```markdown
### Runtime Hardening Evidence

The run inspection payload includes these hardening views:

- `kg_path_trace.grounding_report`: shows whether executable steps are grounded in retrieved workflow patterns, data sources, and output schema policies.
- `tool_contract_report`: shows whether each planned algorithm is registered in `ToolRegistry`, which handler it maps to, which input/output types are expected, and whether the tool is reservation-only.
- `telemetry_summary`: summarizes planning telemetry and audit event counts for the run.
- `recovery_hint`: summarizes whether the current checkpoint can be redispatched or requires manual review.

Preflight checks are available through `POST /api/v2/runs/preflight`. The endpoint returns `allowed=false` with structured `unsupported_intent` records for off-domain requests, unsupported schema customization, trajectory-to-road execution requests, and unbounded POI entity-alignment requests.

Recoverable stale runs are listed through `GET /api/v2/operator/recovery?stale_after_seconds=300`. This endpoint is inspection-only; it does not redispatch runs by itself.
```

- [ ] **Step 4: Document no-UI workflow**

Add this subsection to `docs/no-ui-agent-operations.md` under `Operator APIs`:

```markdown
### Preflight And Recovery

- Use `POST /api/v2/runs/preflight` before creating operator-initiated runs when the request may contain unsupported scope.
- Use `GET /api/v2/operator/recovery` to inspect stale non-terminal runs and their checkpoint-derived recovery action.
- Treat `recovery_hint` and `/operator/recovery` as operator evidence. They do not automatically resume execution.
```

- [ ] **Step 5: Run documentation guard tests**

Run:

```powershell
python -m pytest -q tests/test_capability_inventory_matrix.py tests/test_runtime_boundary_guards.py tests/test_no_ui_maturity_check.py
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit docs and boundary tests**

Run:

```powershell
git add docs/superpowers/specs/2026-05-06-capability-inventory.md docs/superpowers/specs/2026-05-06-capability-matrix.json docs/v2-operations.md docs/no-ui-agent-operations.md tests/test_capability_inventory_matrix.py tests/test_runtime_boundary_guards.py
git commit -m "docs: promote runtime hardening evidence contract"
```

---

### Task 8: Final Verification And Evidence Freeze Check

**Files:**
- No source edits expected unless verification reveals a mismatch.
- Possible generated docs only if existing freeze scripts are intentionally refreshed.

- [ ] **Step 1: Run focused runtime hardening tests**

Run:

```powershell
python -m pytest -q `
  tests/test_tool_contract_report_service.py `
  tests/test_plan_grounding_service.py `
  tests/test_kg_path_trace_service.py `
  tests/test_toolspec_contract_enforcement.py `
  tests/test_run_telemetry_service.py `
  tests/test_run_recovery_service.py `
  tests/test_operator_recovery_api.py `
  tests/test_unsupported_intent_guard.py `
  tests/test_scenario_scope_guards.py `
  tests/test_runtime_boundary_guards.py `
  tests/test_capability_inventory_matrix.py
```

Expected: all selected tests pass.

- [ ] **Step 2: Run API integration slice**

Run:

```powershell
python -m pytest -q tests/test_api_v2_integration.py tests/test_api_operator_read_models.py
```

Expected: all selected tests pass.

- [ ] **Step 3: Run no-UI maturity static gate**

Run:

```powershell
python scripts/run_no_ui_maturity_check.py --require-readme-repositioning
```

Expected: JSON output contains `"passed": true`.

- [ ] **Step 4: Run full test suite if focused tests pass**

Run:

```powershell
python -m pytest -q
```

Expected: full suite passes. If this is too slow for the executing environment, record the skipped reason and keep the focused commands above as the minimum merge gate.

- [ ] **Step 5: Refresh no-UI freeze only if documentation evidence changed**

Run this only after Tasks 1-7 pass and docs wording changed:

```powershell
python scripts/freeze_no_ui_maturity_evidence.py `
  --target docs/superpowers/specs/2026-04-21-no-ui-maturity-target.md `
  --gap-ledger docs/superpowers/specs/2026-04-21-no-ui-maturity-gap-ledger.md `
  --paper-evidence docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md `
  --scenario-evidence docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.md `
  --output-json docs/superpowers/specs/2026-04-21-no-ui-maturity-evidence-freeze.json `
  --output-markdown docs/superpowers/specs/2026-04-21-no-ui-maturity-evidence-freeze.md
```

Expected: command exits `0` and regenerated freeze still describes the bounded no-UI runtime.

- [ ] **Step 6: Commit verification evidence updates**

If freeze files changed:

```powershell
git add docs/superpowers/specs/2026-04-21-no-ui-maturity-evidence-freeze.json docs/superpowers/specs/2026-04-21-no-ui-maturity-evidence-freeze.md
git commit -m "docs: refresh no-ui maturity evidence"
```

If freeze files did not change, do not create an empty commit.

---

## Decision Gates

These gates do not block writing the implementation above. They decide whether follow-up plans are needed.

1. **DG1: Promote `evidence.tool_contracts_grounding_recovery` after implementation**
   - Default decision: promote to `core` + `runtime_supported` only after Tasks 1-7 pass.
   - User decision needed only if you want the claim to remain `core_next` despite the new API evidence.

2. **DG2: Promote multi-source building utility into shared runtime**
   - Default decision: do not promote.
   - Promotion requires a separate plan covering runtime API entry, source-set selection, tiled execution, artifact contract, run inspection parity, real-data freeze, and README wording.

3. **DG3: Productization track**
   - Default decision: do not start auth/multitenant/production ops in this plan.
   - Start a separate plan only if FusionAgent is being turned into a deployable multi-user product.

4. **DG4: `trajectory-to-road` execution**
   - Default decision: keep reservation-only.
   - Promotion requires a separate plan with trajectory data contract, map matching algorithm, KG nodes, ToolSpec handler, validation tests, and real artifact evidence.

5. **DG5: Scenario live event-feed or digital twin**
   - Default decision: keep rejected or clarified.
   - Promotion requires a separate scenario-runtime design and external event source reliability model.

## Self-Review

### Spec Coverage

- Tool contracts: Task 1.
- KG grounding: existing `services/plan_grounding_service.py` remains canonical and is surfaced together with inspection in Tasks 1 and 7.
- Unsupported-intent rejection: Tasks 4 and 5.
- Token/latency/planning telemetry: Task 2.
- Checkpoint recovery inspection: Task 3.
- Ablation/evidence documentation boundary: Task 7 and Task 8.
- Building multi-source boundary: Task 6 and Decision Gate DG2.
- POI boundedness: Tasks 4, 5, and 6.
- `trajectory-to-road` reservation: Tasks 4, 5, and 6.
- Productization and live digital twin non-goals: Scope Lock and Decision Gates DG3/DG5.

### Placeholder Scan

This plan contains no placeholder implementation steps. Every code-changing task includes concrete test code, concrete implementation snippets, exact commands, and expected outcomes.

### Type Consistency

- `RunInspectionResponse.tool_contract_report`, `telemetry_summary`, and `recovery_hint` are all `Dict[str, Any]`.
- `RunPreflightResponse.allowed` is `bool`; `unsupported_intent` is `List[Dict[str, str]]`.
- `OperatorRecoveryResponse.records` is `List[Dict[str, Any]]`.
- API route names do not collide with `/runs/{run_id}` because `/runs/preflight` and `/operator/recovery` are declared before dynamic run routes.

## Completion Criteria

- Focused runtime-hardening tests pass.
- API integration slice passes.
- `python scripts/run_no_ui_maturity_check.py --require-readme-repositioning` passes.
- Capability matrix and inventory agree on claim states.
- No docs or README text promotes multi-source building, trajectory-to-road, unbounded POI, production multi-tenancy, or live digital twin as completed runtime capabilities.
