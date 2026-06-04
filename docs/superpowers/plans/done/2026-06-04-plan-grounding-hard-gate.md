# Plan Grounding Hard Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Prefer `gpt-5.5` workers. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote plan grounding from a passive report to a configurable execution gate so hallucinated algorithms, sources, or output types cannot proceed into validation and execution when enforcement is enabled.

**Architecture:** Keep `services/plan_grounding_service.py` as the canonical report builder. Add a small policy layer that evaluates the report in `report`, `warn`, or `enforce` mode. `AgentRunService.run_planning_stage()` writes the same `grounding_report` as today, then applies the policy before the plan reaches validation. In enforce mode, ungrounded plans fail early with audit evidence and durable feedback.

**Tech Stack:** Python, pytest, existing `WorkflowPlan`, `ValidationIssue`, `RunPhase.failed`, `AgentRunService`, `build_plan_grounding_report()`, and run audit events.

---

## Phase 0: Documentation Discovery

### Sources Consulted

- `services/plan_grounding_service.py`
  - Produces `grounded`, `grounded_step_count`, `total_step_count`, `grounding_score`, and per-step `issue_codes`.
- `services/agent_run_service.py`
  - Calls `ensure_plan_grounding_report(plan)` in `run_planning_stage()`, persists `plan.json`, and writes `plan_created` audit details.
  - Later calls `run_validation_stage()`, then execution and writeback.
  - Uses `RunPhase.failed` and `run_failed` audit event for early terminal failures.
- `schemas/agent.py`
  - `RunPhase` has no rejected phase; use `failed` for enforced grounding rejection.
  - `ValidationIssue` and `ValidationReport` already model validation failures.
- `tests/test_plan_grounding_service.py`
  - Existing tests cover full grounding, unknown source, output mismatch, and step mismatch.
- `tests/test_agent_run_service_enhancements.py`
  - Existing patterns assert failed runs, audit event kinds, and early unsupported-intent behavior.
- `docs/v2-operations.md`
  - Documents `kg_path_trace.grounding_report` as evidence visibility.

### Allowed APIs

- Keep `ensure_plan_grounding_report(plan)` as the report writer.
- Add a new policy evaluator rather than changing the report shape incompatibly.
- Use environment variable `GEOFUSION_PLAN_GROUNDING_MODE` with values `report`, `warn`, and `enforce`.
- Use `RunPhase.failed` when enforcement rejects the plan.
- Emit a dedicated audit event such as `plan_grounding_rejected`.

### Anti-Pattern Guards

- Do not add a new `RunPhase.rejected`.
- Do not remove grounding reports in report or warn mode.
- Do not make all historical tests enforce mode by default.
- Do not reject transform-only plans with zero executable steps.
- Do not hide the specific grounding issue codes from the audit log.

## File Structure

- Create: `schemas/plan_grounding.py`
- Modify: `services/plan_grounding_service.py`
- Modify: `services/agent_run_service.py`
- Modify: `docs/no-ui-agent-operations.md`
- Modify: `docs/v2-operations.md`
- Test: `tests/test_plan_grounding_service.py`
- Test: `tests/test_agent_run_service_enhancements.py`

---

### Task 1: Add Grounding Gate Policy Schema

**Files:**
- Create: `schemas/plan_grounding.py`
- Test: `tests/test_plan_grounding_service.py`

- [ ] **Step 1: Write failing policy schema tests**

Append to `tests/test_plan_grounding_service.py`:

```python
from schemas.plan_grounding import PlanGroundingGateDecision


def test_plan_grounding_gate_decision_serializes_rejection() -> None:
    decision = PlanGroundingGateDecision(
        mode="enforce",
        allowed=False,
        reason_code="PLAN_GROUNDING_FAILED",
        issue_codes=["DATA_SOURCE_NOT_IN_RETRIEVAL"],
    )

    payload = decision.model_dump(mode="json")

    assert payload["allowed"] is False
    assert payload["reason_code"] == "PLAN_GROUNDING_FAILED"
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_plan_grounding_service.py::test_plan_grounding_gate_decision_serializes_rejection -q
```

Expected: FAIL because `schemas.plan_grounding` does not exist.

- [ ] **Step 3: Implement schema**

Create `schemas/plan_grounding.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class PlanGroundingGateDecision(BaseModel):
    mode: str
    allowed: bool
    reason_code: str | None = None
    message: str = ""
    grounding_score: float | None = None
    issue_codes: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Verify**

```powershell
py -3.13 -m pytest tests/test_plan_grounding_service.py::test_plan_grounding_gate_decision_serializes_rejection -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add schemas/plan_grounding.py tests/test_plan_grounding_service.py
git commit -m "feat: add plan grounding gate schema"
```

### Task 2: Implement Grounding Gate Evaluation

**Files:**
- Modify: `services/plan_grounding_service.py`
- Test: `tests/test_plan_grounding_service.py`

- [ ] **Step 1: Add failing evaluator tests**

Append:

```python
from services.plan_grounding_service import evaluate_plan_grounding_gate


def test_grounding_gate_allows_report_mode_when_ungrounded() -> None:
    decision = evaluate_plan_grounding_gate(
        {"grounded": False, "grounding_score": 0.0, "steps": [{"issue_codes": ["DATA_SOURCE_NOT_IN_RETRIEVAL"]}]},
        mode="report",
    )

    assert decision.allowed is True
    assert decision.reason_code is None


def test_grounding_gate_rejects_enforce_mode_when_ungrounded() -> None:
    decision = evaluate_plan_grounding_gate(
        {"grounded": False, "grounding_score": 0.0, "steps": [{"issue_codes": ["DATA_SOURCE_NOT_IN_RETRIEVAL"]}]},
        mode="enforce",
    )

    assert decision.allowed is False
    assert decision.reason_code == "PLAN_GROUNDING_FAILED"
    assert decision.issue_codes == ["DATA_SOURCE_NOT_IN_RETRIEVAL"]
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_plan_grounding_service.py::test_grounding_gate_allows_report_mode_when_ungrounded tests/test_plan_grounding_service.py::test_grounding_gate_rejects_enforce_mode_when_ungrounded -q
```

Expected: FAIL because `evaluate_plan_grounding_gate()` does not exist.

- [ ] **Step 3: Implement evaluator**

In `services/plan_grounding_service.py`, import `PlanGroundingGateDecision` and add:

```python
def evaluate_plan_grounding_gate(report: dict[str, Any], *, mode: str = "report") -> PlanGroundingGateDecision:
    normalized_mode = str(mode or "report").strip().lower()
    if normalized_mode not in {"report", "warn", "enforce"}:
        normalized_mode = "report"
    grounded = bool(report.get("grounded"))
    issue_codes = _report_issue_codes(report)
    allowed = grounded or normalized_mode in {"report", "warn"}
    return PlanGroundingGateDecision(
        mode=normalized_mode,
        allowed=allowed,
        reason_code=None if allowed else "PLAN_GROUNDING_FAILED",
        message=(
            "Plan grounding passed."
            if grounded
            else "Plan grounding failed; enforcement rejected execution."
            if not allowed
            else "Plan grounding failed but current mode does not enforce rejection."
        ),
        grounding_score=float(report.get("grounding_score") or 0.0),
        issue_codes=issue_codes,
    )


def _report_issue_codes(report: dict[str, Any]) -> list[str]:
    ordered: list[str] = []
    for step in _as_list(report.get("steps")):
        if not isinstance(step, dict):
            continue
        for code in _as_list(step.get("issue_codes")):
            text = str(code).strip()
            if text and text not in ordered:
                ordered.append(text)
    return ordered
```

- [ ] **Step 4: Verify**

```powershell
py -3.13 -m pytest tests/test_plan_grounding_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add services/plan_grounding_service.py tests/test_plan_grounding_service.py
git commit -m "feat: evaluate plan grounding gate policy"
```

### Task 3: Enforce Gate In Planning Stage

**Files:**
- Modify: `services/agent_run_service.py`
- Test: `tests/test_agent_run_service_enhancements.py`

- [ ] **Step 1: Add failing enforcement test**

Append to `tests/test_agent_run_service_enhancements.py`:

```python
def test_agent_run_service_enforces_plan_grounding_before_validation(tmp_path, monkeypatch):
    service = AgentRunService(base_dir=tmp_path / "runs")
    monkeypatch.setenv("GEOFUSION_PLAN_GROUNDING_MODE", "enforce")

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(type=RunTriggerType.user_query, content="fuse buildings", spatial_extent="bbox(0,0,1,1)"),
            input_strategy=RunInputStrategy.task_driven_auto,
        ),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    latest = service.get_run(status.run_id)
    assert latest.phase == RunPhase.failed
    assert "PLAN_GROUNDING_FAILED" in (latest.error or "")
    events = service.get_audit_events(status.run_id)
    assert any(event.kind == "plan_grounding_rejected" for event in events)
```

Adapt the test setup to use the local helpers already present in this large test file. The key requirement is to force a plan whose `grounding_report["grounded"]` is false, then assert validation and execution do not run.

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_agent_run_service_enhancements.py::test_agent_run_service_enforces_plan_grounding_before_validation -q
```

Expected: FAIL because enforce mode is not applied.

- [ ] **Step 3: Wire policy in `run_planning_stage()`**

In `services/agent_run_service.py`, import `evaluate_plan_grounding_gate`. After:

```python
grounding_report = ensure_plan_grounding_report(plan)
```

evaluate the mode:

```python
grounding_gate = evaluate_plan_grounding_gate(
    grounding_report,
    mode=os.getenv("GEOFUSION_PLAN_GROUNDING_MODE", "report"),
)
plan.context = {
    **plan.context,
    "grounding_gate": grounding_gate.model_dump(mode="json"),
}
```

Persist the plan with the gate decision before raising. If `grounding_gate.allowed` is false:

- update status to `RunPhase.failed`
- checkpoint stage `planning`
- emit `plan_grounding_rejected`
- set error to `PLAN_GROUNDING_FAILED: <issue codes>`
- raise a `RuntimeError` so the normal create-run path stops

If existing `create_run()` failure handling already catches exceptions and records `run_failed`, reuse it. Avoid duplicate terminal events if a clear `plan_grounding_rejected` event already marks the reason.

- [ ] **Step 4: Verify default compatibility**

Add or update a test that sets no environment variable and confirms an ungrounded test plan still records `grounding_gate.mode == "report"` and does not fail solely because of grounding.

- [ ] **Step 5: Verify and commit**

```powershell
py -3.13 -m pytest tests/test_plan_grounding_service.py tests/test_agent_run_service_enhancements.py -q
git add services/agent_run_service.py tests/test_agent_run_service_enhancements.py
git commit -m "feat: enforce plan grounding gate when configured"
```

### Task 4: Add Replan-Or-Fail Behavior For Healing Contexts

**Files:**
- Modify: `services/agent_run_service.py`
- Test: `tests/test_agent_run_service_enhancements.py`

- [ ] **Step 1: Add failing replan grounding test**

Add a test covering the existing replan path:

- initial execution fails
- `replan_after_failure()` returns a replacement plan
- replacement plan has `grounded=False`
- enforce mode rejects the replacement before validation
- audit contains `replan_requested`, then `plan_grounding_rejected`

Use existing tests around `replan_requested` and `replan_rejected` in `tests/test_agent_run_service_enhancements.py` as the pattern to copy.

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_agent_run_service_enhancements.py::test_replan_result_is_rejected_when_grounding_enforcement_fails -q
```

Expected: FAIL because replans are not gated.

- [ ] **Step 3: Extract helper**

Create an internal helper in `AgentRunService`:

```python
def _apply_plan_grounding_gate(self, run_id: str, plan: WorkflowPlan, *, stage: str) -> None:
    grounding_report = ensure_plan_grounding_report(plan)
    decision = evaluate_plan_grounding_gate(
        grounding_report,
        mode=os.getenv("GEOFUSION_PLAN_GROUNDING_MODE", "report"),
    )
    plan.context = {**plan.context, "grounding_gate": decision.model_dump(mode="json")}
    if not decision.allowed:
        self._reject_ungrounded_plan(run_id=run_id, plan=plan, decision=decision, stage=stage)
```

Use it from both the initial planning stage and the replan path. Include `stage` in audit details so operators can distinguish `planning` from `replan`.

- [ ] **Step 4: Ensure persisted plan includes failed gate**

The rejected replacement plan must still be written to `plan.json` or `plan-revision-<n>.json` with `context["grounding_gate"]` and `context["grounding_report"]` so the rejection is inspectable.

- [ ] **Step 5: Verify and commit**

```powershell
py -3.13 -m pytest tests/test_agent_run_service_enhancements.py::test_replan_result_is_rejected_when_grounding_enforcement_fails tests/test_plan_grounding_service.py -q
git add services/agent_run_service.py tests/test_agent_run_service_enhancements.py
git commit -m "feat: gate replanned workflows by grounding"
```

### Task 5: Document Modes And Validation Runner Usage

**Files:**
- Modify: `docs/no-ui-agent-operations.md`
- Modify: `docs/v2-operations.md`
- Test: `tests/test_no_ui_operations_docs.py`

- [ ] **Step 1: Add failing docs test**

Update `tests/test_no_ui_operations_docs.py`:

```python
def test_no_ui_runbook_documents_grounding_gate_modes() -> None:
    text = Path("docs/no-ui-agent-operations.md").read_text(encoding="utf-8")

    assert "GEOFUSION_PLAN_GROUNDING_MODE" in text
    assert "`report`" in text
    assert "`warn`" in text
    assert "`enforce`" in text
    assert "plan_grounding_rejected" in text
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_no_ui_operations_docs.py::test_no_ui_runbook_documents_grounding_gate_modes -q
```

Expected: FAIL because the mode docs are missing.

- [ ] **Step 3: Update runbook**

Add under full-loop or engineering validation:

```powershell
$env:GEOFUSION_PLAN_GROUNDING_MODE='enforce'
```

Document:

- `report`: write evidence only
- `warn`: write evidence and warning event, but allow execution
- `enforce`: fail before validation or replan validation when ungrounded

- [ ] **Step 4: Update detailed operations doc**

In `docs/v2-operations.md`, clarify that `kg_path_trace.grounding_report` is evidence, while `grounding_gate` is the runtime admission decision.

- [ ] **Step 5: Verify and commit**

```powershell
py -3.13 -m pytest tests/test_no_ui_operations_docs.py tests/test_plan_grounding_service.py -q
git add docs/no-ui-agent-operations.md docs/v2-operations.md tests/test_no_ui_operations_docs.py
git commit -m "docs: document plan grounding gate modes"
```

---

## Final Verification

Run:

```powershell
py -3.13 -m pytest tests/test_plan_grounding_service.py tests/test_agent_run_service_enhancements.py tests/test_no_ui_operations_docs.py -q
$env:GEOFUSION_PLAN_GROUNDING_MODE='enforce'
python scripts/run_engineering_validation.py --dry-run
Remove-Item Env:GEOFUSION_PLAN_GROUNDING_MODE
rg -n "plan_grounding_rejected|GEOFUSION_PLAN_GROUNDING_MODE|grounding_gate" services schemas docs tests
$patterns = @('TO'+'DO','TB'+'D','\.'+'\.'+'\.','place'+'holder','FIX'+'ME','X'+'XX')
Select-String -Path docs/superpowers/plans/2026-06-04-plan-grounding-hard-gate.md -Pattern $patterns
```

Expected:

- Focused tests pass.
- Dry-run still works with enforce mode set.
- Code and docs expose the new gate decision.
- Red-flag scan returns no matches.

## Integration Commit

After all tasks pass:

```powershell
git status --short
git log --oneline -5
```

Then merge and push according to the active superpowers branch-finishing workflow.
