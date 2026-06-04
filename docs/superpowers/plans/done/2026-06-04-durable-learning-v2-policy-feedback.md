# Durable Learning V2 Policy Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Prefer `gpt-5.5` workers. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade durable learning from global count summaries plus ad hoc policy adjustment into condition-aware, time-decayed, quality-aware feedback that can safely bias future policy selection.

**Architecture:** Keep existing `DurableLearningRecord` persistence and `KGRepository.summarize_durable_learning_records()` entry point. Extend record metadata with optional quality and latency evidence, extend summaries with condition keys and policy-ready adjustment fields, and update `AgentRunService` to consume summary-provided adjustments before falling back to the current count-based calculation.

**Tech Stack:** Python, dataclasses, pytest, existing `kg.models`, `KGRepository`, `InMemoryKGRepository`, `Neo4jKGRepository`, `AgentRunService`, `PolicyEngine`, and quality gate audit events.

---

## Phase 0: Documentation Discovery

### Sources Consulted

- `kg/models.py`
  - `DurableLearningRecord` stores run, job, trigger, success, disaster, pattern, algorithm, data source, output type, target CRS, repair info, failure reason, plan revision, metadata, and created time.
  - `DurableLearningSummary` currently stores entity kind, entity id, job type, disaster type, run counts, repaired count, last run time, and last failure reason.
- `kg/repository.py`
  - `summarize_durable_learning_records()` filters by job and disaster, aggregates by pattern, algorithm, and selected data source, then sorts by total count.
- `kg/inmemory_repository.py`
  - `build_context()` injects durable summaries into `KGContext`.
- `kg/neo4j_repository.py`
  - Stores and lists durable learning records for Neo4j-backed contexts.
- `services/agent_run_service.py`
  - `_record_feedback()` writes durable records after execution.
  - `_pattern_learning_adjustment()` currently derives a bounded adjustment from `total_runs` and `success_count`.
  - `_build_pattern_selection_decision()` attaches durable summaries as candidate metadata and passes `learning_adjustment` to `PolicyEngine`.
- `services/quality_gate_service.py`
  - Emits quality gate accepted and failure reasons before final artifact writeback.
- `tests/test_kg_repository_enhancements.py`
  - Existing tests cover durable record persistence and summary counts.
- `tests/test_policy_engine.py`
  - Existing tests verify learning adjustment affects candidate scoring and is emitted in evidence.

### Allowed APIs

- Extend dataclasses with optional fields to preserve backward compatibility.
- Keep `summarize_durable_learning_records()` returning `patterns`, `algorithms`, and `data_sources`.
- Continue supporting current `total_runs` and `success_count` consumers.
- Store quality and latency as record metadata first; promote typed fields only when they are stable.
- Clamp policy adjustment to `[-0.10, 0.10]`.

### Anti-Pattern Guards

- Do not claim autonomous self-optimization beyond bounded policy hints.
- Do not remove the current count fields.
- Do not require Neo4j for durable learning tests.
- Do not let one failed run create a large negative adjustment.
- Do not make old durable records invalid because they lack quality or latency metadata.

## File Structure

- Modify: `kg/models.py`
- Modify: `kg/repository.py`
- Modify: `kg/neo4j_repository.py`
- Modify: `services/agent_run_service.py`
- Modify: `services/artifact_evaluation_service.py`
- Modify: `docs/no-ui-agent-operations.md`
- Test: `tests/test_kg_repository_enhancements.py`
- Test: `tests/test_neo4j_repository.py`
- Test: `tests/test_agent_run_service_enhancements.py`
- Test: `tests/test_artifact_evaluation_service.py`

---

### Task 1: Extend Durable Learning Summary Model

**Files:**
- Modify: `kg/models.py`
- Test: `tests/test_kg_repository_enhancements.py`

- [ ] **Step 1: Add failing model test**

Append to `tests/test_kg_repository_enhancements.py`:

```python
def test_durable_learning_summary_exposes_policy_feedback_fields() -> None:
    summary = DurableLearningSummary(
        entity_kind="pattern",
        entity_id="wp.building",
        job_type=JobType.building,
        disaster_type="flood",
        condition_key="building|flood|small_city",
        time_decayed_score=0.75,
        quality_gate_pass_rate=1.0,
        avg_latency_seconds=12.5,
        recent_success_rate=0.8,
        trend="stable",
        adjustment=0.06,
    )

    assert summary.condition_key == "building|flood|small_city"
    assert summary.adjustment == 0.06
    assert summary.trend == "stable"
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_kg_repository_enhancements.py::test_durable_learning_summary_exposes_policy_feedback_fields -q
```

Expected: FAIL because the new fields do not exist.

- [ ] **Step 3: Extend dataclass**

In `kg/models.py`, add optional fields to `DurableLearningSummary`:

```python
condition_key: str = ""
time_decayed_score: float = 0.0
quality_gate_pass_rate: float = 0.0
avg_latency_seconds: float = 0.0
recent_success_rate: float = 0.0
trend: str = "stable"
adjustment: float = 0.0
```

Keep all existing fields unchanged.

- [ ] **Step 4: Verify**

```powershell
py -3.13 -m pytest tests/test_kg_repository_enhancements.py::test_durable_learning_summary_exposes_policy_feedback_fields -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add kg/models.py tests/test_kg_repository_enhancements.py
git commit -m "feat: extend durable learning summaries"
```

### Task 2: Add Condition Keys And Time-Decayed Aggregation

**Files:**
- Modify: `kg/repository.py`
- Test: `tests/test_kg_repository_enhancements.py`

- [ ] **Step 1: Add failing aggregation tests**

Append:

```python
def test_durable_learning_summary_uses_condition_key_and_time_decay() -> None:
    repo = InMemoryKGRepository()
    repo.record_durable_learning_record(
        DurableLearningRecord(
            record_id="old-failure",
            run_id="old",
            job_type=JobType.building,
            trigger_type="user_query",
            success=False,
            disaster_type="flood",
            pattern_id="wp.building",
            selected_data_source="raw.osm.building",
            metadata={"aoi_class": "small_city", "region_group": "africa"},
            created_at="2026-05-01T00:00:00+00:00",
        )
    )
    repo.record_durable_learning_record(
        DurableLearningRecord(
            record_id="new-success",
            run_id="new",
            job_type=JobType.building,
            trigger_type="user_query",
            success=True,
            disaster_type="flood",
            pattern_id="wp.building",
            selected_data_source="raw.osm.building",
            metadata={"aoi_class": "small_city", "region_group": "africa"},
            created_at="2026-06-01T00:00:00+00:00",
        )
    )

    summary = repo.summarize_durable_learning_records(
        job_type=JobType.building,
        disaster_type="flood",
        limit=5,
    )["patterns"][0]

    assert summary.condition_key == "building|flood|africa|small_city|wp.building"
    assert 0.0 < summary.time_decayed_score <= 1.0
    assert summary.recent_success_rate == 0.5
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_kg_repository_enhancements.py::test_durable_learning_summary_uses_condition_key_and_time_decay -q
```

Expected: FAIL because condition keys and decayed scores are not computed.

- [ ] **Step 3: Implement helpers**

In `kg/repository.py`, add helpers:

```python
def _learning_condition_key(record: DurableLearningRecord, entity_id: str) -> str:
    region = str(record.metadata.get("region_group") or "global") if isinstance(record.metadata, dict) else "global"
    aoi_class = str(record.metadata.get("aoi_class") or "unknown_aoi") if isinstance(record.metadata, dict) else "unknown_aoi"
    disaster = record.disaster_type or "none"
    return f"{record.job_type.value}|{disaster}|{region}|{aoi_class}|{entity_id}"
```

Add time-decay helper using ISO timestamps already stored in records:

```python
def _time_decay_weight(created_at: str | None, newest_at: str | None, *, half_life_days: float = 30.0) -> float:
    created = _parse_learning_timestamp(created_at)
    newest = _parse_learning_timestamp(newest_at)
    if created is None or newest is None or half_life_days <= 0:
        return 1.0
    age_days = max(0.0, (newest - created).total_seconds() / 86_400.0)
    return 0.5 ** (age_days / half_life_days)
```

Use a deterministic fallback weight of `1.0` when timestamps are missing.

- [ ] **Step 4: Update aggregation**

In `_aggregate_learning_dimension()`:

- set `summary.condition_key`
- compute `time_decayed_score`
- compute `recent_success_rate` from the records used in that summary
- compute `adjustment = clamp((time_decayed_score - 0.5) * 0.2, -0.10, 0.10)` only when `total_runs >= 2`
- set `trend` to `improving`, `stable`, or `degrading` based on recent success rate versus total success rate with a small threshold of `0.15`

- [ ] **Step 5: Verify and commit**

```powershell
py -3.13 -m pytest tests/test_kg_repository_enhancements.py -q
git add kg/repository.py tests/test_kg_repository_enhancements.py
git commit -m "feat: compute conditioned durable learning scores"
```

### Task 3: Record Quality And Latency Evidence

**Files:**
- Modify: `services/agent_run_service.py`
- Test: `tests/test_agent_run_service_enhancements.py`

- [ ] **Step 1: Add failing durable metadata test**

Add a focused test that simulates a successful run with a quality report and timestamps, then asserts the recorded `DurableLearningRecord.metadata` includes:

- `quality_gate_accepted`
- `quality_gate_failure_reasons`
- `latency_seconds`
- `aoi_class`
- `region_group`

Use the existing in-memory KG repo and `_record_feedback()` patterns in `tests/test_agent_run_service_enhancements.py`.

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_agent_run_service_enhancements.py::test_record_feedback_includes_quality_and_latency_metadata -q
```

Expected: FAIL because the metadata is not recorded yet.

- [ ] **Step 3: Extract run quality metadata**

In `AgentRunService._record_feedback()`, augment `durable_metadata` with:

```python
"quality_gate_accepted": quality_gate_accepted,
"quality_gate_failure_reasons": quality_gate_failure_reasons,
"latency_seconds": latency_seconds,
"aoi_class": aoi_class,
"region_group": region_group,
```

Preferred sources:

- quality gate audit event details for acceptance and failure reasons
- `RunStatus.started_at` and `RunStatus.finished_at` or current time for latency
- `plan.context["intent"]` or request metadata-like context for AOI and region labels

If a value cannot be derived, omit it rather than writing an invented value.

- [ ] **Step 4: Add summary aggregation for quality and latency**

In `kg/repository.py`, compute:

- `quality_gate_pass_rate`
- `avg_latency_seconds`

Ignore records that do not include those metadata fields.

- [ ] **Step 5: Verify and commit**

```powershell
py -3.13 -m pytest tests/test_agent_run_service_enhancements.py tests/test_kg_repository_enhancements.py -q
git add services/agent_run_service.py kg/repository.py tests/test_agent_run_service_enhancements.py tests/test_kg_repository_enhancements.py
git commit -m "feat: record quality aware durable learning metadata"
```

### Task 4: Consume Summary-Provided Adjustment In Policy Selection

**Files:**
- Modify: `services/agent_run_service.py`
- Modify: `services/artifact_evaluation_service.py`
- Test: `tests/test_agent_run_service_enhancements.py`
- Test: `tests/test_artifact_evaluation_service.py`

- [ ] **Step 1: Add failing policy consumption test**

Add or update a test near the current learning adjustment tests:

```python
def test_pattern_selection_uses_summary_adjustment_before_count_fallback(tmp_path):
    service = AgentRunService(base_dir=tmp_path / "runs")
    decision = service._build_pattern_selection_decision(
        _plan_with_retrieval(
            durable_learning_summaries={
                "patterns": [
                    {
                        "entity_id": "wp.preferred",
                        "total_runs": 10,
                        "success_count": 1,
                        "adjustment": 0.08,
                    }
                ]
            }
        )
    )

    selected = next(candidate for candidate in decision.candidates if candidate.candidate_id == "wp.preferred")
    assert selected.evidence["metrics"]["learning_adjustment"] == 0.08
```

Adapt helper names to existing local tests. The intent is to assert summary-provided `adjustment` wins over count-derived fallback.

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_agent_run_service_enhancements.py::test_pattern_selection_uses_summary_adjustment_before_count_fallback -q
```

Expected: FAIL because `_pattern_learning_adjustment()` ignores summary adjustment.

- [ ] **Step 3: Update `_pattern_learning_adjustment()`**

In `services/agent_run_service.py`:

1. If `summary["adjustment"]` exists and is numeric, clamp and return it.
2. Otherwise fall back to the current `total_runs` and `success_count` calculation.

Keep the existing minimum total run guard for fallback calculation.

- [ ] **Step 4: Update agentic metrics**

In `services/artifact_evaluation_service.py`, preserve current self-evolution metrics and add:

- `self_evolution_trend`
- `self_evolution_quality_gate_pass_rate`

Read them from candidate durable learning summary evidence when present.

- [ ] **Step 5: Verify and commit**

```powershell
py -3.13 -m pytest tests/test_agent_run_service_enhancements.py tests/test_artifact_evaluation_service.py tests/test_policy_engine.py -q
git add services/agent_run_service.py services/artifact_evaluation_service.py tests/test_agent_run_service_enhancements.py tests/test_artifact_evaluation_service.py
git commit -m "feat: consume durable learning policy adjustments"
```

### Task 5: Neo4j Mapping And Operations Documentation

**Files:**
- Modify: `kg/neo4j_repository.py`
- Modify: `docs/no-ui-agent-operations.md`
- Test: `tests/test_neo4j_repository.py`
- Test: `tests/test_no_ui_operations_docs.py`

- [ ] **Step 1: Add failing Neo4j metadata mapping test**

Update `tests/test_neo4j_repository.py` so fake rows containing durable metadata fields round-trip into `DurableLearningRecord.metadata`, then summary code can use them.

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_neo4j_repository.py::test_list_durable_learning_records_maps_rows_from_fake_driver -q
```

Expected: FAIL if new metadata fields are dropped.

- [ ] **Step 3: Update Neo4j write and read mapping**

In `kg/neo4j_repository.py`, ensure `record_durable_learning_record()` writes `metadata` as a JSON-compatible property and `list_durable_learning_records()` restores it. If metadata is already stored, add coverage for the new quality and latency keys.

- [ ] **Step 4: Document bounded learning claims**

Update `docs/no-ui-agent-operations.md`:

- durable learning summary is a bounded policy hint
- summary fields include condition key, time-decayed score, quality pass rate, latency, trend, and adjustment
- this is not autonomous self-optimization

- [ ] **Step 5: Verify and commit**

```powershell
py -3.13 -m pytest tests/test_neo4j_repository.py tests/test_kg_repository_enhancements.py tests/test_no_ui_operations_docs.py -q
git add kg/neo4j_repository.py docs/no-ui-agent-operations.md tests/test_neo4j_repository.py tests/test_no_ui_operations_docs.py
git commit -m "feat: persist durable learning v2 evidence"
```

---

## Final Verification

Run:

```powershell
py -3.13 -m pytest tests/test_kg_repository_enhancements.py tests/test_neo4j_repository.py tests/test_agent_run_service_enhancements.py tests/test_artifact_evaluation_service.py tests/test_policy_engine.py tests/test_no_ui_operations_docs.py -q
rg -n "condition_key|time_decayed_score|quality_gate_pass_rate|avg_latency_seconds|recent_success_rate|adjustment" kg services tests docs
$patterns = @('TO'+'DO','TB'+'D','\.'+'\.'+'\.','place'+'holder','FIX'+'ME','X'+'XX')
Select-String -Path docs/superpowers/plans/2026-06-04-durable-learning-v2-policy-feedback.md -Pattern $patterns
```

Expected:

- Focused tests pass.
- Durable summaries remain backward compatible with existing count fields.
- Policy candidates use summary-provided adjustments when available.
- Documentation keeps the bounded policy-hint claim.

## Integration Commit

After all tasks pass:

```powershell
git status --short
git log --oneline -5
```

Then merge and push according to the active superpowers branch-finishing workflow.
