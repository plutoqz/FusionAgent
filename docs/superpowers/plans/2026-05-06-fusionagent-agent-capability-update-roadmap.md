# FusionAgent Agent Capability Update Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不偏离论文主线和主体目标的前提下，补齐 FusionAgent 智能体本身仍欠缺的关键能力，使其从“能跑的研究原型”进一步提升为“边界清晰、可诊断、可操作、可规模复用的 geospatial fusion agent runtime”。

**Architecture:** 这份计划不主打论文创新点，而主打系统能力成熟度。更新优先级按“直接支撑论文实验与主体目标”排序：先补 planner/executor contract、failure diagnosability、operator observability、input robustness、scenario boundedness，再补可选优化如 retrieval prioritization、front-end evidence surface。所有更新必须服从 thesis research plan，不允许引入新的主题扩张。

**Tech Stack:** Runtime services, KG seed / source catalog / executor / validator / planner / inspection APIs / audit artifacts / pytest / harness scripts / operator docs.

---

## Capability Goal Lock

- 主体目标仍然是：`bounded disaster-response geospatial fusion agent runtime`
- 本计划关注“智能体能力”，不是“论文写作结构”
- 允许增强：
  - planner correctness
  - executor contract enforcement
  - failure diagnosability
  - input robustness
  - operator usability
  - bounded scenario reasoning
- 禁止扩张：
  - 新主题切片
  - 泛领域通用 agent
  - 大规模 UI 产品化改造
  - 脱离论文主线的新 research branch

## Current Capability Gaps

### Gap G1: Tool / Algorithm Contract Discipline Still Incomplete

现有系统已有 decomposed algorithm primitives，但从“KG 节点可选”到“运行时强制按 contract 执行”的闭环还可以更严：

- unknown handler rejection 还应更显式
- parameter spec enforcement 还应更统一
- pre/post-condition checks 还应更系统

### Gap G2: Failure Diagnosis Still Stronger In Artifacts Than In Runtime UX

系统已经有 `audit.jsonl`，但对 operator 和实验者来说：

- 根因标签不一定统一
- failure taxonomy 不一定稳定
- first-failure → diagnosis path 仍可更短

### Gap G3: Input Acquisition Robustness Still Uneven

虽然已有 task-driven input acquisition、source asset fallback、raw source reuse，但：

- source absence / corruption / CRS mismatch 的处理还可更可预期
- 不同数据源族的 bounded fallback 策略还可以更规范化

### Gap G4: Scenario Layer Still Needs Better Boundedness

scenario-driven 已经存在，但还需要更明确：

- scenario 只能驱动哪些 task bundle
- 哪些 dependency reasoning 是 supported
- 哪些场景需求必须 reject / clarify

### Gap G5: Operator-Facing Inspection Still More “Evidence-Rich” Than “Decision-Friendly”

已有 inspection / compare API，但还缺：

- 更清晰的 root-cause summary
- 更紧凑的 step-level state digest
- 更清晰的 “what should operator do next” 建议

### Gap G6: Planner Retrieval Quality Can Still Improve

现有 planner retrieval 已能用 KG 暴露 candidate，但：

- low-noise retrieval
- path prioritization
- source / algorithm ranking transparency

仍然有提升空间。

## Capability Priorities

### P0: Directly Support Thesis And Main Runtime Claim

- `ToolSpec` / handler contract hardening
- machine-readable root cause taxonomy
- per-step grounding artifact generation
- unsupported-intent guard
- checkpoint / stale-run inspection

### P1: Strongly Improve Agent Usability And Robustness

- input acquisition fault taxonomy
- source fallback policy unification
- planner retrieval prioritization
- operator recommendation summary

### P2: Useful But Non-Core Enhancements

- front-end evidence views
- richer artifact preview products
- broader scenario authoring ergonomics

## Desired Capability End-State

### End-State E1: Planner Produces Only Explainable, Contract-Bounded Steps

- every planned step resolves to registered executable unit
- every parameter binding is checkable
- every unsupported request becomes explicit rejection or clarification

### End-State E2: Executor Failures Become Structured Runtime Signals

- failures classified into a stable taxonomy
- healing path chosen against taxonomy, not ad hoc strings
- audit and inspection surfaces expose the same root-cause vocabulary

### End-State E3: Operator Can Understand Run State Without Reading Raw Logs

- inspection endpoint exposes current phase, failed step, root cause, recovery suggestion
- compare endpoint exposes meaningful behavioral delta, not only artifact diff

### End-State E4: Scenario Layer Stays Bounded And Honest

- only supported task bundles are routable
- dependency reasoning is explicit and documented
- out-of-scope scenario requests are rejected early

## Detailed Execution Plan

### Task 1: Harden Tool And Algorithm Contract Enforcement

**Files:**
- Modify: `agent/tooling.py`
- Modify: `agent/executor.py`
- Modify: `agent/validator.py`
- Modify: `kg/seed.py`
- Test: `tests/test_toolspec_contract_enforcement.py`

- [x] **Step 1: Write the failing ToolSpec enforcement test**

```python
import pytest

from agent.tooling import build_default_tool_registry


def test_executor_rejects_unknown_or_schema_invalid_tool() -> None:
    registry = build_default_tool_registry()
    with pytest.raises(ValueError, match="Unknown algorithm in tool registry"):
        registry.require("algo.unknown")
```

- [x] **Step 2: Run test to verify current weak points**

Run: `python -m pytest -q tests/test_toolspec_contract_enforcement.py`
Expected: FAIL where unknown or invalid tool paths are not uniformly rejected.

- [x] **Step 3: Add uniform contract checks**

```python
# expected behaviors
- unknown tool id -> explicit rejection
- invalid parameter binding -> explicit validation error
- input/output type mismatch -> explicit validator failure
```

- [x] **Step 4: Re-run contract tests**

Run: `python -m pytest -q tests/test_toolspec_contract_enforcement.py`
Expected: PASS

- [x] **Step 5: Add a minimal operator-facing note to audit output**

```python
# example metadata
{
  "root_cause": "PARAM_OUT_OF_RANGE",
  "action": "replan",
  "recoverable": true
}
```

### Task 2: Introduce A Stable Failure Taxonomy

**Files:**
- Create: `schemas/failure_taxonomy.py`
- Modify: `services/agent_run_service.py`
- Modify: `agent/executor.py`
- Modify: `agent/validator.py`
- Test: `tests/test_failure_taxonomy.py`

- [ ] **Step 1: Write the failing failure-taxonomy test**

```python
from schemas.failure_taxonomy import classify_failure_category


def test_failures_map_to_machine_readable_categories() -> None:
    assert classify_failure_category("missing source") == "SOURCE_MISSING"
```

- [ ] **Step 2: Run test to verify taxonomy is absent**

Run: `python -m pytest -q tests/test_failure_taxonomy.py`
Expected: FAIL

- [ ] **Step 3: Add stable taxonomy categories**

```python
FAILURE_CATEGORIES = [
    "SOURCE_MISSING",
    "SOURCE_CORRUPTED",
    "CRS_MISMATCH",
    "PARAM_OUT_OF_RANGE",
    "ALGO_RUNTIME_ERROR",
    "ALGO_TIMEOUT",
    "SUSPECT_OUTPUT",
]
```

- [ ] **Step 4: Emit taxonomy in audit / inspection**

```python
# every classified failure writes
{
  "failure_category": "SOURCE_MISSING",
  "recoverable": true,
  "suggested_action": "retry"
}
```

- [ ] **Step 5: Re-run taxonomy tests**

Run: `python -m pytest -q tests/test_failure_taxonomy.py`
Expected: PASS

### Task 3: Improve Input Acquisition Robustness

**Files:**
- Modify: `services/input_acquisition_service.py`
- Modify: `services/raw_vector_source_service.py`
- Modify: `services/source_asset_service.py`
- Modify: `kg/source_catalog.py`
- Test: `tests/test_input_acquisition_faults.py`

- [ ] **Step 1: Write the failing input-fault tests**

```python
from services.source_asset_service import classify_source_fault


def test_missing_or_wrong_crs_source_produces_explicit_fault() -> None:
    assert classify_source_fault(
        source={"source_id": "catalog.building.benin.osm", "crs": "EPSG:4326"},
        expected_crs="EPSG:32631",
    ) == "CRS_MISMATCH"
```

- [ ] **Step 2: Run the fault tests**

Run: `python -m pytest -q tests/test_input_acquisition_faults.py`
Expected: FAIL where faults are implicit or inconsistent.

- [ ] **Step 3: Standardize source fallback policy**

```python
# target policy order example
directory_first -> exact_path -> recursive_glob -> source_asset_fallback -> reject
```

- [ ] **Step 4: Emit uniform fault metadata**

```python
{
  "source_id": "catalog.building.benin.osm",
  "fault": "CRS_MISMATCH",
  "fallback_used": "source_asset_service"
}
```

- [ ] **Step 5: Re-run input fault tests**

Run: `python -m pytest -q tests/test_input_acquisition_faults.py`
Expected: PASS

### Task 4: Add Planner Retrieval Prioritization

**Files:**
- Modify: `agent/retriever.py`
- Modify: `agent/planner.py`
- Test: `tests/test_planner_retrieval_prioritization.py`

- [ ] **Step 1: Write the failing prioritization test**

```python
from agent.retriever import rank_retrieval_candidates


def test_planner_prefers_better_grounded_sources_and_algorithms() -> None:
    grounded_candidate = {"source_quality": 1.0, "algorithm_fit": 1.0, "workflow_support": 1.0}
    weak_candidate = {"source_quality": 0.2, "algorithm_fit": 0.3, "workflow_support": 0.1}
    ranked = rank_retrieval_candidates([grounded_candidate, weak_candidate])
    assert ranked[0] == grounded_candidate
```

- [ ] **Step 2: Run prioritization test**

Run: `python -m pytest -q tests/test_planner_retrieval_prioritization.py`
Expected: FAIL if ranking is still too opaque or flat.

- [ ] **Step 3: Add a bounded ranking function**

```python
# score components example
score = source_quality + algorithm_fit + workflow_support - penalty_for_missing_requirements
```

- [ ] **Step 4: Expose ranking rationale**

```python
{
  "ranking_rationale": {
    "source_quality": 0.8,
    "workflow_support": 1.0
  }
}
```

- [ ] **Step 5: Re-run prioritization test**

Run: `python -m pytest -q tests/test_planner_retrieval_prioritization.py`
Expected: PASS

### Task 5: Make Inspection Output Decision-Friendly

**Files:**
- Modify: `services/agent_run_service.py`
- Modify: `api/routers/runs_v2.py`
- Modify: `docs/v2-operations.md`
- Test: `tests/test_run_inspection_summary.py`

- [ ] **Step 1: Write the failing inspection-summary test**

```python
from services.agent_run_service import build_run_inspection_digest


def test_inspection_exposes_root_cause_and_next_action() -> None:
    digest = build_run_inspection_digest(
        current_phase="planning",
        failed_step="step 3",
        root_cause="PARAM_OUT_OF_RANGE",
        recoverability="replan",
        next_operator_action="adjust bound and rerun",
    )
    assert digest["root_cause"] == "PARAM_OUT_OF_RANGE"
    assert digest["next_operator_action"] == "adjust bound and rerun"
```

- [ ] **Step 2: Run inspection-summary test**

Run: `python -m pytest -q tests/test_run_inspection_summary.py`
Expected: FAIL if inspection is evidence-rich but operator-poor.

- [ ] **Step 3: Add inspection digest fields**

```python
{
  "current_phase": "planning",
  "failed_step": "step 3",
  "root_cause": "PARAM_OUT_OF_RANGE",
  "recoverability": "replan",
  "next_operator_action": "adjust bound and rerun"
}
```

- [ ] **Step 4: Document operator interpretation**

```markdown
Operators should be able to answer:
- what failed
- why it failed
- whether the system can recover
- what to do next
```

- [ ] **Step 5: Re-run inspection-summary test**

Run: `python -m pytest -q tests/test_run_inspection_summary.py`
Expected: PASS

### Task 6: Bound Scenario Reasoning More Explicitly

**Files:**
- Modify: `services/scenario_run_service.py`
- Modify: `services/scenario_trigger_service.py`
- Modify: `README.md`
- Modify: `docs/no-ui-agent-operations.md`
- Test: `tests/test_scenario_scope_guards.py`

- [ ] **Step 1: Write the failing scenario-scope tests**

```python
from services.scenario_run_service import classify_scenario_request


def test_out_of_scope_scenario_request_is_rejected_or_clarified() -> None:
    decision = classify_scenario_request(
        scenario_name="Global traffic telemetry replay",
        trigger_content="simulate live event-feed with full digital twin outputs",
        job_types=["traffic"],
    )
    assert decision["decision"] in {"reject", "clarify"}
```

- [ ] **Step 2: Run scenario-scope tests**

Run: `python -m pytest -q tests/test_scenario_scope_guards.py`
Expected: FAIL where scenario scope is too permissive.

- [ ] **Step 3: Add explicit scenario guardrails**

```python
# examples
- unsupported dependency reasoning -> clarify
- unsupported task bundle -> reject
- unsupported event-feed expectation -> reject
```

- [ ] **Step 4: Align docs with the bounded scenario claim**

```markdown
Scenario layer is bounded orchestration, not full digital twin simulation.
```

- [ ] **Step 5: Re-run scenario-scope tests**

Run: `python -m pytest -q tests/test_scenario_scope_guards.py`
Expected: PASS

## Suggested Execution Order

### Stage 1

- Tool / algorithm contract hardening
- failure taxonomy

### Stage 2

- input acquisition robustness
- planner retrieval prioritization

### Stage 3

- inspection digest improvements
- scenario scope guards

### Stage 4

- optional UI / preview follow-ups only if thesis-critical work is closed

## Expected Impact

- 更强的 planning correctness
- 更低的隐式失败和 diagnosis friction
- 更一致的 source fallback behavior
- 更清晰的 operator decision surface
- 更可信的 scenario boundedness

## Relationship To Thesis Plan

- 这份计划服务于 thesis research roadmap，但不等于 thesis roadmap
- 只有直接支持 RQ / baseline / ablation / Benin scale validation 的能力更新，才应进入近期执行
- 其余增强项可以排到论文之后
