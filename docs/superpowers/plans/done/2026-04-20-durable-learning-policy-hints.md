# Durable Learning Policy Hints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make durable learning operationally consumable by applying a bounded, auditable policy hint to `pattern_selection`.

**Architecture:** Add a small `learning_adjustment` score component to policy candidates, capped to `[-0.10, +0.10]`. Derive that adjustment only from durable pattern summaries already exposed in planner context, emit it in candidate evidence, and keep all behavior deterministic and explainable.

**Tech Stack:** Python, Pydantic, pytest

**Completion Status:** Completed on 2026-04-20 in branch `codex/durable-learning-policy-hints`. Focused verification passed with `43 passed`; final verification used `python -m pytest -q` and passed with `161 passed, 1 skipped, 6 warnings`.

---

## File Map

- Modify: `agent/policy.py`
  Responsibility: score and explain bounded `learning_adjustment`.
- Modify: `services/agent_run_service.py`
  Responsibility: derive pattern-level learning hints from `context.retrieval.durable_learning_summaries.patterns`.
- Modify: `tests/test_policy_engine.py`
  Responsibility: prove policy scoring applies and emits `learning_adjustment`.
- Modify: `tests/test_agent_run_service_enhancements.py`
  Responsibility: prove pattern selection consumes durable summaries as policy hints.
- Modify: `docs/superpowers/specs/2026-04-20-evidence-ledger.md`
  Responsibility: record Phase D evidence.

---

## Task 1: Add Policy-Level Learning Adjustment

**Files:**
- Modify: `tests/test_policy_engine.py`
- Modify: `agent/policy.py`

- [x] **Step 1: Write failing policy test**

Add `test_policy_engine_applies_learning_adjustment_and_emits_it_in_evidence`.

Expected red result:

```text
historically_weak selected instead of historically_strong
```

- [x] **Step 2: Add bounded candidate field**

Add `learning_adjustment: Optional[float] = None` to `CandidateScoreInput`.

Validation:

```text
-0.10 <= learning_adjustment <= 0.10
```

- [x] **Step 3: Add adjustment to score and evidence**

Add the adjustment to `_score_one()` and include it in:

```text
candidate.reason
candidate.evidence["metrics"]["learning_adjustment"]
record.rationale
```

## Task 2: Derive Pattern Hints From Durable Summaries

**Files:**
- Modify: `tests/test_agent_run_service_enhancements.py`
- Modify: `services/agent_run_service.py`

- [x] **Step 1: Write failing service test**

Add `test_pattern_selection_uses_durable_learning_summaries_as_policy_hints`.

Expected red result:

```text
wp.historically.weak selected instead of wp.historically.strong
```

- [x] **Step 2: Index pattern summaries by entity id**

Read:

```text
plan.context["retrieval"]["durable_learning_summaries"]["patterns"]
```

- [x] **Step 3: Derive capped adjustment**

Use:

```text
adjustment = clamp((success_count / total_runs - 0.5) * 0.2, -0.10, 0.10)
```

Only apply when `total_runs >= 2`.

- [x] **Step 4: Emit evidence ref**

When any candidate has a learning adjustment, append:

```text
context.retrieval.durable_learning_summaries.patterns
```

to the `pattern_selection` decision evidence refs.

## Task 3: Verify

**Files:**
- Modify: `docs/superpowers/plans/done/2026-04-20-durable-learning-policy-hints.md`

- [x] **Step 1: Run red checks**

Executed before implementation:

```powershell
python -m pytest -q tests/test_policy_engine.py::test_policy_engine_applies_learning_adjustment_and_emits_it_in_evidence tests/test_agent_run_service_enhancements.py::test_pattern_selection_uses_durable_learning_summaries_as_policy_hints
```

Result:

```text
2 failed
```

- [x] **Step 2: Run focused green checks**

Executed after implementation:

```powershell
python -m pytest -q tests/test_policy_engine.py::test_policy_engine_applies_learning_adjustment_and_emits_it_in_evidence tests/test_agent_run_service_enhancements.py::test_pattern_selection_uses_durable_learning_summaries_as_policy_hints
```

Result:

```text
2 passed
```

- [x] **Step 3: Run policy/runtime focused subset**

Executed:

```powershell
python -m pytest -q tests/test_policy_engine.py tests/test_agent_run_service_enhancements.py tests/test_planner_context.py tests/test_kg_repository_enhancements.py
```

Result:

```text
43 passed
```

- [x] **Step 4: Run full test suite**

Run:

```powershell
python -m pytest -q
```

Expected:

```text
161 passed, 1 skipped, 6 warnings
```

## Self-Review

- Scope control: This is not auto-tuning. It is a deterministic, bounded policy hint for one decision type.
- Evidence: The decision records expose both the score adjustment and the durable-learning evidence reference.
- Risk control: Missing or low-volume summaries do not affect scores.
