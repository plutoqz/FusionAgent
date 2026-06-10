# Plan C Architecture MVP Ablation Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the architecture contribution measurable by producing MVP evidence for KG hard constraints, KG/policy-driven repair strategy, conditional durable learning, and A0/A1/A2 ablation variants.

**Architecture:** Reuse the runtime contract and repair audit fields from Plan A, then add evidence aggregation and ablation toggles that separate raw LLM planning quality from Validator fail-closed behavior, KG fallback, policy/healing governance, and durable-learning hints. Keep the policy algorithm deterministic and do not introduce reinforcement learning, bandits, or new task families.

**Tech Stack:** Python, pytest, existing KG repositories, `PolicyEngine`, `WorkflowPlanner`, `WorkflowValidator`, `WorkflowExecutor`, `scripts/eval_kg_ablation.py`, JSON and Markdown evidence files.

---

## Entry Conditions

- Plan A has implemented runtime contract enforcement and repair decision audit fields.
- Plan B has either frozen or clearly defined benchmark metrics used by A2c quality outcomes.
- This plan can begin after Freeze A for harness work, but final thesis evidence waits for Freeze B and Plan D.

## Sources Consulted

- `docs/superpowers/specs/2026-06-10-fusionagent-reliability-roadmap-design.md`
- `agent/policy.py`
- `kg/repository.py`
- `kg/models.py`
- `agent/planner.py`
- `agent/executor.py`
- `services/agent_run_service.py`
- `scripts/eval_kg_ablation.py`
- `tests/test_eval_kg_ablation.py`
- `tests/test_policy_engine.py`
- `tests/test_repair_strategy.py`
- `tests/test_repair_audit.py`

## File Structure

- Modify: `kg/repository.py`
  - Expand durable-learning condition keys to include task, algorithm or pattern, AOI-size bucket, source-coverage bucket, failure category, and quality outcome.
- Modify: `services/agent_run_service.py`
  - Record the new durable-learning metadata fields when writing `DurableLearningRecord`.
- Create: `services/architecture_mvp_evidence_service.py`
  - Aggregate evidence for the three architecture MVP objections.
- Modify: `scripts/eval_kg_ablation.py`
  - Support A0/A1/A2a/A2b/A2c variants and metrics that expose fallback masking.
- Create: `tests/test_durable_learning_condition_keys.py`
  - Unit tests for condition key construction and policy evidence flow.
- Create: `tests/test_architecture_mvp_evidence_service.py`
  - Evidence aggregation tests.
- Modify: `tests/test_eval_kg_ablation.py`
  - Variant and metric coverage tests.
- Create: `docs/superpowers/specs/2026-06-10-architecture-innovation-ledger.md`
  - Architecture MVP ledger with objection, metric, evidence, claim boundary, and future-work fields.
- Create: `docs/superpowers/specs/2026-06-10-architecture-mvp-evidence-sample.json`
  - Machine-readable sample evidence for review before final experiments.

---

### Task 1: Expand Durable-Learning Condition Keys

**Files:**
- Modify: `kg/repository.py`
- Test: `tests/test_durable_learning_condition_keys.py`

- [ ] **Step 1: Write failing condition-key tests**

Create `tests/test_durable_learning_condition_keys.py`:

```python
from __future__ import annotations

from kg.models import DurableLearningRecord
from kg.repository import _learning_condition_key
from schemas.fusion import JobType


def test_learning_condition_key_includes_architecture_mvp_dimensions() -> None:
    record = DurableLearningRecord(
        record_id="dlr-1",
        run_id="run-1",
        job_type=JobType.road,
        trigger_type="user_query",
        success=False,
        disaster_type="flood",
        pattern_id="wp.road.v7",
        algorithm_id="algo.fusion.road.conflation.v7",
        failure_reason="SOURCE_DOWNLOAD_FAILED",
        metadata={
            "task_kind": "road",
            "aoi_size_bucket": "medium",
            "source_coverage_bucket": "partial",
            "failure_category": "SOURCE_DOWNLOAD_FAILED",
            "quality_outcome": "quality_gate_failed",
        },
    )

    key = _learning_condition_key(record, "wp.road.v7")

    assert key == (
        "task=road|entity=wp.road.v7|aoi=medium|source_coverage=partial|"
        "failure=SOURCE_DOWNLOAD_FAILED|quality=quality_gate_failed"
    )


def test_learning_condition_key_has_stable_defaults_for_legacy_records() -> None:
    record = DurableLearningRecord(
        record_id="dlr-legacy",
        run_id="run-legacy",
        job_type=JobType.building,
        trigger_type="user_query",
        success=True,
        algorithm_id="algo.fusion.building.v1",
        metadata={},
    )

    key = _learning_condition_key(record, "algo.fusion.building.v1")

    assert key == (
        "task=building|entity=algo.fusion.building.v1|aoi=unknown|"
        "source_coverage=unknown|failure=none|quality=unknown"
    )
```

- [ ] **Step 2: Run tests to confirm failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_durable_learning_condition_keys.py -q
```

Expected: FAIL because `_learning_condition_key()` still uses the older job/disaster/region/AOI format.

- [ ] **Step 3: Update condition-key function**

In `kg/repository.py`, replace `_learning_condition_key()` with:

```python
def _learning_condition_key(record: DurableLearningRecord, entity_id: str) -> str:
    metadata = record.metadata if isinstance(record.metadata, dict) else {}
    task = str(metadata.get("task_kind") or record.job_type.value)
    aoi_size = str(metadata.get("aoi_size_bucket") or metadata.get("aoi_class") or "unknown")
    source_coverage = str(metadata.get("source_coverage_bucket") or "unknown")
    failure_category = str(metadata.get("failure_category") or record.failure_reason or "none")
    quality_outcome = str(metadata.get("quality_outcome") or "unknown")
    return (
        f"task={task}|entity={entity_id}|aoi={aoi_size}|"
        f"source_coverage={source_coverage}|failure={failure_category}|quality={quality_outcome}"
    )
```

- [ ] **Step 4: Run durable-learning tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_durable_learning_condition_keys.py tests/test_policy_engine.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit condition-key change**

Run:

```powershell
git add kg/repository.py tests/test_durable_learning_condition_keys.py
git commit -m "feat: condition durable learning summaries for architecture evidence"
```

---

### Task 2: Record Condition Metadata At Runtime

**Files:**
- Modify: `services/agent_run_service.py`
- Test: `tests/test_agent_run_service_durable_learning_conditions.py`

- [ ] **Step 1: Write failing metadata helper test**

Create `tests/test_agent_run_service_durable_learning_conditions.py`:

```python
from __future__ import annotations

from services.agent_run_service import _build_durable_learning_condition_metadata


def test_durable_learning_condition_metadata_buckets_runtime_context() -> None:
    metadata = _build_durable_learning_condition_metadata(
        task_kind="road",
        requested_bbox=[0.0, 0.0, 0.4, 0.4],
        component_coverage={
            "raw.osm.road": {"coverage_status": "available"},
            "raw.overture.transportation": {"coverage_status": "missing"},
        },
        failure_category="SOURCE_MISSING",
        quality_gate_accepted=False,
    )

    assert metadata["task_kind"] == "road"
    assert metadata["aoi_size_bucket"] in {"small", "medium", "large"}
    assert metadata["source_coverage_bucket"] == "partial"
    assert metadata["failure_category"] == "SOURCE_MISSING"
    assert metadata["quality_outcome"] == "quality_gate_failed"
```

- [ ] **Step 2: Run test to confirm failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_agent_run_service_durable_learning_conditions.py -q
```

Expected: FAIL because `_build_durable_learning_condition_metadata()` does not exist.

- [ ] **Step 3: Add metadata helper**

In `services/agent_run_service.py`, add a module-level helper near durable-learning writeback helpers:

```python
def _build_durable_learning_condition_metadata(
    *,
    task_kind: str,
    requested_bbox: list[float] | tuple[float, float, float, float] | None,
    component_coverage: dict[str, object] | None,
    failure_category: str | None,
    quality_gate_accepted: bool | None,
) -> dict[str, object]:
    return {
        "task_kind": task_kind,
        "aoi_size_bucket": _aoi_size_bucket(requested_bbox),
        "source_coverage_bucket": _source_coverage_bucket(component_coverage or {}),
        "failure_category": failure_category or "none",
        "quality_outcome": (
            "quality_gate_passed"
            if quality_gate_accepted is True
            else "quality_gate_failed"
            if quality_gate_accepted is False
            else "quality_unknown"
        ),
        "quality_gate_accepted": quality_gate_accepted,
    }


def _aoi_size_bucket(bbox: list[float] | tuple[float, float, float, float] | None) -> str:
    if bbox is None or len(bbox) != 4:
        return "unknown"
    minx, miny, maxx, maxy = [float(value) for value in bbox]
    area = max(0.0, maxx - minx) * max(0.0, maxy - miny)
    if area <= 0.05:
        return "small"
    if area <= 1.0:
        return "medium"
    return "large"


def _source_coverage_bucket(component_coverage: dict[str, object]) -> str:
    if not component_coverage:
        return "unknown"
    statuses = []
    for payload in component_coverage.values():
        if isinstance(payload, dict):
            statuses.append(str(payload.get("coverage_status") or "unknown"))
    if statuses and all(status == "available" for status in statuses):
        return "complete"
    if any(status == "available" for status in statuses):
        return "partial"
    return "missing"
```

When constructing `DurableLearningRecord`, merge this helper output into `metadata` using the current task kind, resolved AOI bbox, component coverage, failure category, and quality gate result available in the run context.

- [ ] **Step 4: Run metadata tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_agent_run_service_durable_learning_conditions.py tests/test_agent_run_service_enhancements.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit runtime metadata writeback**

Run:

```powershell
git add services/agent_run_service.py tests/test_agent_run_service_durable_learning_conditions.py
git commit -m "feat: write durable learning condition metadata"
```

---

### Task 3: Add Architecture MVP Evidence Aggregator

**Files:**
- Create: `services/architecture_mvp_evidence_service.py`
- Test: `tests/test_architecture_mvp_evidence_service.py`

- [ ] **Step 1: Write failing evidence aggregation tests**

Create `tests/test_architecture_mvp_evidence_service.py`:

```python
from __future__ import annotations

from services.architecture_mvp_evidence_service import build_architecture_mvp_evidence


def test_architecture_mvp_evidence_maps_objections_to_metrics() -> None:
    evidence = build_architecture_mvp_evidence(
        validation_events=[
            {"enforcement_mode": "enforce", "rejected": True, "reason_code": "DEPRECATED_ALGORITHM"}
        ],
        repair_records=[
            {
                "policy_source": "repair.alternative_algorithm.v1",
                "candidate_actions": [{"action": "alternative_algorithm"}],
                "selected_action": {"action": "alternative_algorithm"},
                "skipped_actions": [],
            }
        ],
        durable_learning_summaries=[
            {
                "condition_key": "task=road|entity=wp.road.v7|aoi=medium|source_coverage=partial|failure=none|quality=quality_gate_passed",
                "adjustment": 0.04,
            }
        ],
    )

    assert evidence["kg_hard_constraints"]["validator_rejection_count"] == 1
    assert evidence["repair_strategy_policy"]["policy_sourced_repair_count"] == 1
    assert evidence["conditional_learning"]["conditioned_summary_count"] == 1
    assert evidence["claim_boundary"]["learning"] == "condition-specific policy hints, not autonomous optimization"
```

- [ ] **Step 2: Run test to confirm failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_architecture_mvp_evidence_service.py -q
```

Expected: FAIL because the service does not exist.

- [ ] **Step 3: Implement evidence service**

Create `services/architecture_mvp_evidence_service.py`:

```python
from __future__ import annotations

from typing import Any


def build_architecture_mvp_evidence(
    *,
    validation_events: list[dict[str, Any]],
    repair_records: list[dict[str, Any]],
    durable_learning_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    rejected = [event for event in validation_events if event.get("rejected") is True]
    policy_sourced_repairs = [record for record in repair_records if record.get("policy_source")]
    conditioned = [
        summary
        for summary in durable_learning_summaries
        if _condition_key_has_required_dimensions(str(summary.get("condition_key") or ""))
    ]
    return {
        "kg_hard_constraints": {
            "validator_rejection_count": len(rejected),
            "reason_codes": sorted({str(event.get("reason_code")) for event in rejected if event.get("reason_code")}),
        },
        "repair_strategy_policy": {
            "policy_sourced_repair_count": len(policy_sourced_repairs),
            "policy_sources": sorted({str(record.get("policy_source")) for record in policy_sourced_repairs}),
        },
        "conditional_learning": {
            "conditioned_summary_count": len(conditioned),
            "nonzero_adjustment_count": sum(1 for summary in conditioned if float(summary.get("adjustment") or 0.0) != 0.0),
        },
        "claim_boundary": {
            "kg": "KG state acts as runtime constraint, not only prompt context",
            "repair": "existing healing capabilities ordered and explained by policy/KG evidence",
            "learning": "condition-specific policy hints, not autonomous optimization",
        },
    }


def _condition_key_has_required_dimensions(condition_key: str) -> bool:
    required = ("task=", "entity=", "aoi=", "source_coverage=", "failure=", "quality=")
    return all(item in condition_key for item in required)
```

- [ ] **Step 4: Run evidence service tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_architecture_mvp_evidence_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit evidence service**

Run:

```powershell
git add services/architecture_mvp_evidence_service.py tests/test_architecture_mvp_evidence_service.py
git commit -m "feat: aggregate architecture mvp evidence"
```

---

### Task 4: Extend Ablation Aggregator For A0/A1/A2 Variants

**Files:**
- Modify: `scripts/eval_kg_ablation.py`
- Modify: `tests/test_eval_kg_ablation.py`

- [ ] **Step 1: Add failing ablation metrics test**

Append to `tests/test_eval_kg_ablation.py`:

```python
from scripts.eval_kg_ablation import summarize_ablation_results


def test_ablation_summary_reports_fallback_masking_metrics() -> None:
    rows = [
        {
            "variant": "A2b",
            "planning_valid": False,
            "unknown_algorithms": ["algo.fake"],
            "execution_success": True,
            "grounding_score": 0.5,
            "validator_rejected": True,
            "kg_fallback_used": True,
            "llm_plan_valid_before_fallback": False,
            "fallback_plan_quality_delta": -0.1,
        },
        {
            "variant": "A2b",
            "planning_valid": True,
            "unknown_algorithms": [],
            "execution_success": True,
            "grounding_score": 1.0,
            "validator_rejected": False,
            "kg_fallback_used": False,
            "llm_plan_valid_before_fallback": True,
            "fallback_plan_quality_delta": 0.0,
        },
    ]

    summary = summarize_ablation_results(rows)
    a2b = next(item for item in summary["variants"] if item["variant"] == "A2b")

    assert a2b["kg_fallback_rate"] == 0.5
    assert a2b["validator_rejection_rate"] == 0.5
    assert a2b["llm_plan_valid_before_fallback_rate"] == 0.5
```

- [ ] **Step 2: Run test to confirm failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_eval_kg_ablation.py -q
```

Expected: FAIL because `A2b` is not yet in the supported variant set or the fallback metrics are absent.

- [ ] **Step 3: Update ablation variant definitions**

In `scripts/eval_kg_ablation.py`, replace `SUPPORTED_VARIANTS` with:

```python
SUPPORTED_VARIANTS: tuple[tuple[str, str], ...] = (
    ("A0", "unconstrained LLM planning baseline"),
    ("A1", "KG retrieval context without fail-closed validation"),
    ("A2a", "KG context plus Validator report-only"),
    ("A2b", "KG context plus Validator fail-closed plus KG fallback"),
    ("A2c", "A2b plus policy and healing governance"),
)
```

Add optional metrics to each evaluated variant summary:

```python
        validator_values = [bool(row.get("validator_rejected", False)) for row in variant_rows]
        fallback_values = [bool(row.get("kg_fallback_used", False)) for row in variant_rows]
        pre_fallback_values = [bool(row.get("llm_plan_valid_before_fallback", row["planning_valid"])) for row in variant_rows]
        quality_delta_values = [
            float(row.get("fallback_plan_quality_delta", 0.0))
            for row in variant_rows
            if row.get("fallback_plan_quality_delta") is not None
        ]
```

Add these fields to the evaluated variant dictionary:

```python
                "validator_rejection_rate": _rate(validator_values),
                "kg_fallback_rate": _rate(fallback_values),
                "llm_plan_valid_before_fallback_rate": _rate(pre_fallback_values),
                "average_fallback_plan_quality_delta": _average(quality_delta_values),
```

- [ ] **Step 4: Run ablation tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_eval_kg_ablation.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit ablation aggregator**

Run:

```powershell
git add scripts/eval_kg_ablation.py tests/test_eval_kg_ablation.py
git commit -m "feat: report a2 fallback masking metrics"
```

---

### Task 5: Add Architecture Ledger And Evidence Sample

**Files:**
- Create: `docs/superpowers/specs/2026-06-10-architecture-innovation-ledger.md`
- Create: `docs/superpowers/specs/2026-06-10-architecture-mvp-evidence-sample.json`

- [ ] **Step 1: Create architecture innovation ledger**

Create `docs/superpowers/specs/2026-06-10-architecture-innovation-ledger.md`:

```markdown
# Architecture Innovation Ledger

| innovation_id | reviewer_objection | current_gap | MVP_behavior | metric | evidence_file | claim_boundary | future_work |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AI-1 | KG is only prompt context | Validator and planner could report issues without hard rejection | Runtime contract rejects blocked algorithms and records fallback | validator_rejection_rate, kg_fallback_rate | Freeze A and A2b evidence | KG constrains runtime; it does not make LLM planning optimal | richer graph constraints |
| AI-2 | Healing is hardcoded engineering | Executor order was embedded in code | Repair decisions include policy_source, candidate_actions, selected_action, skipped_actions | policy_sourced_repair_count, healing_success_rate | repair audit records | Policy governs existing repair capabilities | learned repair cost model |
| AI-3 | Durable Learning is decorative | Summary key was too coarse for decision evidence | Conditioned summaries enter candidate evidence | conditioned_summary_count, nonzero_adjustment_count | architecture MVP evidence | Bounded policy hints only | causal learning and online policy tuning |
```

- [ ] **Step 2: Create sample evidence JSON**

Create `docs/superpowers/specs/2026-06-10-architecture-mvp-evidence-sample.json`:

```json
{
  "kg_hard_constraints": {
    "validator_rejection_count": 1,
    "reason_codes": ["DEPRECATED_ALGORITHM"]
  },
  "repair_strategy_policy": {
    "policy_sourced_repair_count": 1,
    "policy_sources": ["repair.alternative_algorithm.v1"]
  },
  "conditional_learning": {
    "conditioned_summary_count": 1,
    "nonzero_adjustment_count": 1
  },
  "claim_boundary": {
    "kg": "KG state acts as runtime constraint, not only prompt context",
    "repair": "existing healing capabilities ordered and explained by policy/KG evidence",
    "learning": "condition-specific policy hints, not autonomous optimization"
  }
}
```

- [ ] **Step 3: Commit architecture docs**

Run:

```powershell
git add docs/superpowers/specs/2026-06-10-architecture-innovation-ledger.md docs/superpowers/specs/2026-06-10-architecture-mvp-evidence-sample.json
git commit -m "docs: add architecture mvp ledger"
```

---

### Task 6: Final Plan C Verification

**Files:**
- Verify only.

- [ ] **Step 1: Run architecture MVP suite**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_durable_learning_condition_keys.py tests/test_agent_run_service_durable_learning_conditions.py tests/test_architecture_mvp_evidence_service.py tests/test_eval_kg_ablation.py tests/test_policy_engine.py tests/test_repair_strategy.py tests/test_repair_audit.py -q
```

Expected: PASS.

- [ ] **Step 2: Run claim-boundary scan**

Run:

```powershell
rg -n "autonomous optimization|optimal policy|reinforcement learning|bandit" docs/superpowers/specs docs/superpowers/plans -S
```

Expected: matches, if any, appear only in disallowed-claim or future-work statements.

- [ ] **Step 3: Record verification note**

Create `docs/superpowers/specs/2026-06-10-plan-c-verification.md`:

```markdown
# Plan C Verification

- Conditional durable learning key suite: passed
- Architecture MVP evidence suite: passed
- Ablation fallback-masking metrics suite: passed
- Claim-boundary scan: passed

## Thesis Draft Hook

Architecture claims are bounded to runtime constraints, policy-sourced repair evidence, and condition-specific policy hints. A2b and A2c results must report `kg_fallback_rate` separately from final end-to-end success.
```

Run:

```powershell
git add docs/superpowers/specs/2026-06-10-plan-c-verification.md
git commit -m "docs: record architecture mvp verification"
```

---

## Self-Review Checklist

- Spec coverage:
  - KG hard constraints: inherited from Plan A and measured in Task 3.
  - RepairStrategy policy evidence: Task 3 and Plan A repair fields.
  - Conditional Durable Learning: Tasks 1 and 2.
  - A2a/A2b/A2c separation: Task 4.
  - Review objection ledger: Task 5.
- Type consistency:
  - `DurableLearningRecord.metadata` carries condition fields without schema migration.
  - `learning_adjustment` remains bounded by `CandidateScoreInput`.
  - Ablation rows remain JSON dictionaries consumed by `scripts/eval_kg_ablation.py`.
- Scope discipline:
  - This plan adds no new policy algorithm, no RL/bandit method, and no new task family.
  - This plan does not claim statistically significant learning improvement from sparse local runs.

