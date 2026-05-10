# Full Replan Loop V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strengthen Phase C replan evidence by refreshing task-driven inputs when a replanned workflow changes input source/type and by preserving per-revision plan snapshots.

**Architecture:** Keep the existing `plan.json` compatibility path, but add immutable `plan-revision-N.json` snapshots each time a plan revision is persisted. During execution recovery, compare the previous and replanned task-driven input signature; when source or required input type changes, re-run input acquisition and emit another `task_inputs_resolved` audit event for the new revision.

**Tech Stack:** Python, Pydantic runtime models, pytest

**Completion Status:** Completed on 2026-04-20 in branch `codex/full-replan-loop-v1`. Focused verification passed with `33 passed`; final verification used `python -m pytest -q` and passed with `159 passed, 1 skipped, 6 warnings`.

---

## File Map

- Modify: `services/agent_run_service.py`
  Responsibility: re-resolve task-driven inputs after source/type-changing replan; persist per-revision plan snapshots.
- Modify: `tests/test_agent_run_service_enhancements.py`
  Responsibility: prove replan refreshes task-driven inputs and preserves revision snapshots.
- Modify: `docs/superpowers/specs/2026-04-20-evidence-ledger.md`
  Responsibility: record the new Phase C evidence.

---

## Task 1: Refresh Task-Driven Inputs After Source-Changing Replan

**Files:**
- Modify: `tests/test_agent_run_service_enhancements.py`
- Modify: `services/agent_run_service.py`

- [x] **Step 1: Write failing test**

Add `test_task_driven_replan_refreshes_inputs_when_source_changes`.

Expected red result:

```text
assert ['catalog.flood.building'] == ['catalog.flood.building', 'catalog.earthquake.building']
```

- [x] **Step 2: Implement input signature comparison**

Add `_task_driven_input_signature(plan)` returning:

```python
(
    AgentRunService._resolve_task_driven_source_id(plan),
    AgentRunService._extract_required_input_data_type(plan),
)
```

- [x] **Step 3: Re-run input acquisition after replan when signature changes**

After `replan_applied` and validation, if the request uses `task_driven_auto` and the signature changed, call `_resolve_execution_inputs()` with `osm_zip_path=None` and `ref_zip_path=None`.

- [x] **Step 4: Emit second `task_inputs_resolved` event**

Extract `_record_task_inputs_resolved(...)` and reuse it for initial input preparation and replan refresh.

## Task 2: Preserve Per-Revision Plan Evidence

**Files:**
- Modify: `tests/test_agent_run_service_enhancements.py`
- Modify: `services/agent_run_service.py`

- [x] **Step 1: Write failing snapshot assertion**

Extend `test_agent_run_service_replans_after_execution_failure` to assert:

```text
plan-revision-1.json contains wf_initial
plan-revision-2.json contains wf_replanned
```

Expected red result:

```text
FileNotFoundError: plan-revision-1.json
```

- [x] **Step 2: Persist revision snapshots**

Update `_persist_plan(path, plan)` so it still writes `plan.json` and also writes:

```text
plan-revision-N.json
```

when `plan.context["plan_revision"]` is greater than zero.

## Task 3: Verify

**Files:**
- Modify: `docs/superpowers/plans/done/2026-04-20-full-replan-loop-v1.md`

- [x] **Step 1: Run red checks**

Executed before implementation:

```powershell
python -m pytest -q tests/test_agent_run_service_enhancements.py::test_task_driven_replan_refreshes_inputs_when_source_changes
python -m pytest -q tests/test_agent_run_service_enhancements.py::test_agent_run_service_replans_after_execution_failure
```

- [x] **Step 2: Run focused green checks**

Executed after implementation:

```powershell
python -m pytest -q tests/test_agent_run_service_enhancements.py::test_agent_run_service_replans_after_execution_failure tests/test_agent_run_service_enhancements.py::test_task_driven_replan_refreshes_inputs_when_source_changes
```

Result:

```text
2 passed
```

- [x] **Step 3: Run runtime-focused regression subset**

Executed:

```powershell
python -m pytest -q tests/test_agent_run_service_enhancements.py tests/test_api_v2_integration.py tests/test_input_acquisition_service.py tests/test_workflow_validator.py tests/test_repair_strategy.py
```

Result:

```text
33 passed
```

- [x] **Step 4: Run full test suite**

Run:

```powershell
python -m pytest -q
```

Expected:

```text
159 passed, 1 skipped, 6 warnings
```

## Self-Review

- Spec coverage: The two Phase C claims in this slice are covered by failing tests first and then passing implementation.
- Scope control: This slice does not implement all possible replanning behavior; it closes downstream input refresh and per-revision plan evidence.
- Compatibility: Existing `plan.json` remains the latest-plan path for current API consumers.
