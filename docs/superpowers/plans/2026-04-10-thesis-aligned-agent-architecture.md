# Thesis-Aligned Agent Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align FusionAgent's executable runtime with the thesis narrative by introducing explicit task-centric ontology primitives, dual-entry intent routing, and scenario-constraint metadata without breaking the current runtime loop.

**Architecture:** Keep the current `planner -> validator -> executor -> healing -> writeback` runtime intact, and layer the thesis-aligned concepts around it. Add minimal new KG and planning objects first, then route both scenario-driven and task-driven inputs into a shared `TaskBundle`, then expose the new constraints to planning context and audit.

**Tech Stack:** Python, Pydantic, FastAPI runtime models, in-memory KG seed data, Neo4j bootstrap, pytest, markdown docs

---

## File Structure

### Existing files to modify

- Modify: `E:\vscode\fusionAgent\kg\models.py`
- Modify: `E:\vscode\fusionAgent\kg\seed.py`
- Modify: `E:\vscode\fusionAgent\kg\repository.py`
- Modify: `E:\vscode\fusionAgent\kg\inmemory_repository.py`
- Modify: `E:\vscode\fusionAgent\kg\neo4j_repository.py`
- Modify: `E:\vscode\fusionAgent\kg\bootstrap.py`
- Modify: `E:\vscode\fusionAgent\schemas\agent.py`
- Modify: `E:\vscode\fusionAgent\agent\retriever.py`
- Modify: `E:\vscode\fusionAgent\agent\planner.py`
- Modify: `E:\vscode\fusionAgent\services\agent_run_service.py`

### New files to create

- Create: `E:\vscode\fusionAgent\agent\intent_resolver.py`
- Create: `E:\vscode\fusionAgent\tests\test_intent_resolver.py`
- Create: `E:\vscode\fusionAgent\tests\test_task_bundle_context.py`

### Docs to update

- Modify: `E:\vscode\fusionAgent\README.md`
- Modify: `E:\vscode\fusionAgent\文档\GeoFusion 知识图谱本体模式层设计方案.md`
- Modify: `E:\vscode\fusionAgent\文档\完整项目上下文文档.md`

---

### Task 1: Add Minimal Thesis-Aligned Ontology Primitives

**Files:**
- Modify: `E:\vscode\fusionAgent\kg\models.py`
- Modify: `E:\vscode\fusionAgent\kg\seed.py`
- Modify: `E:\vscode\fusionAgent\kg\repository.py`
- Modify: `E:\vscode\fusionAgent\kg\inmemory_repository.py`
- Modify: `E:\vscode\fusionAgent\kg\neo4j_repository.py`
- Modify: `E:\vscode\fusionAgent\kg\bootstrap.py`
- Test: `E:\vscode\fusionAgent\tests\test_kg_repository_enhancements.py`

- [x] **Step 1: Write the failing test for explicit task and scenario-profile retrieval**

```python
from kg.inmemory_repository import InMemoryKGRepository
from schemas.fusion import JobType


def test_build_context_exposes_task_nodes_and_scenario_profiles() -> None:
    repo = InMemoryKGRepository()

    context = repo.build_context(job_type=JobType.building, disaster_type="flood")

    assert context.task_nodes
    assert any(task.task_id == "task.building.fusion" for task in context.task_nodes)
    assert context.scenario_profiles
    assert any(profile.profile_id == "scenario.flood.default" for profile in context.scenario_profiles)
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_kg_repository_enhancements.py -k task_nodes_and_scenario_profiles`

Expected: FAIL with missing `task_nodes` or `scenario_profiles` fields on `KGContext`

- [x] **Step 3: Add minimal new KG dataclasses**

```python
@dataclass
class TaskNode:
    task_id: str
    task_name: str
    category: str
    description: str = ""


@dataclass
class ScenarioProfileNode:
    profile_id: str
    profile_name: str
    disaster_types: List[str]
    activated_tasks: List[str] = field(default_factory=list)
    preferred_output_fields: List[str] = field(default_factory=list)
    qos_priority: Dict[str, float] = field(default_factory=dict)
```

- [x] **Step 4: Extend `KGContext` to carry the new entities**

```python
@dataclass
class KGContext:
    patterns: List[WorkflowPatternNode]
    algorithms: Dict[str, AlgorithmNode]
    parameter_specs: Dict[str, List[AlgorithmParameterSpec]] = field(default_factory=dict)
    data_sources: List[DataSourceNode] = field(default_factory=list)
    output_schema_policies: Dict[str, OutputSchemaPolicy] = field(default_factory=dict)
    durable_learning_summaries: Dict[str, List[DurableLearningSummary]] = field(default_factory=dict)
    task_nodes: List[TaskNode] = field(default_factory=list)
    scenario_profiles: List[ScenarioProfileNode] = field(default_factory=list)
    disaster_type: Optional[str] = None
```

- [x] **Step 5: Seed one explicit task layer and one explicit scenario-profile layer**

```python
TASKS: Dict[str, TaskNode] = {
    "task.building.fusion": TaskNode(
        task_id="task.building.fusion",
        task_name="Building Fusion",
        category="fusion",
        description="Fuse multiple building vector sources into one output.",
    ),
    "task.road.fusion": TaskNode(
        task_id="task.road.fusion",
        task_name="Road Fusion",
        category="fusion",
        description="Fuse multiple road vector sources into one output.",
    ),
}

SCENARIO_PROFILES: List[ScenarioProfileNode] = [
    ScenarioProfileNode(
        profile_id="scenario.flood.default",
        profile_name="Flood Default Scenario",
        disaster_types=["flood"],
        activated_tasks=["task.building.fusion", "task.road.fusion"],
        preferred_output_fields=["geometry", "confidence", "timestamp"],
        qos_priority={"accuracy": 0.35, "stability": 0.25, "freshness": 0.25, "speed": 0.15},
    )
]
```

- [x] **Step 6: Return the new entities from both repository backends**

```python
return KGContext(
    patterns=patterns,
    algorithms=algorithms,
    parameter_specs=parameter_specs,
    data_sources=list(sources.values()),
    output_schema_policies=output_schema_policies,
    durable_learning_summaries=self.summarize_durable_learning_records(
        job_type=job_type,
        disaster_type=disaster_type,
        limit=5,
    ),
    task_nodes=list(TASKS.values()),
    scenario_profiles=_filter_scenario_profiles(disaster_type),
    disaster_type=disaster_type,
)
```

- [x] **Step 7: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_kg_repository_enhancements.py -k task_nodes_and_scenario_profiles`

Expected: PASS

- [x] **Step 8: Commit**

```bash
git add kg/models.py kg/seed.py kg/repository.py kg/inmemory_repository.py kg/neo4j_repository.py kg/bootstrap.py tests/test_kg_repository_enhancements.py
git commit -m "feat: add thesis-aligned task and scenario profile primitives"
```

### Task 2: Introduce Dual-Entry Intent Resolution

**Files:**
- Create: `E:\vscode\fusionAgent\agent\intent_resolver.py`
- Modify: `E:\vscode\fusionAgent\schemas\agent.py`
- Modify: `E:\vscode\fusionAgent\agent\retriever.py`
- Test: `E:\vscode\fusionAgent\tests\test_intent_resolver.py`

- [ ] **Step 1: Write the failing tests for scenario-driven and task-driven routing**

```python
from agent.intent_resolver import resolve_planning_mode
from schemas.agent import RunTrigger, RunTriggerType


def test_resolve_planning_mode_prefers_scenario_when_disaster_type_present() -> None:
    trigger = RunTrigger(
        type=RunTriggerType.disaster_event,
        content="flood response for building fusion",
        disaster_type="flood",
    )
    resolved = resolve_planning_mode(trigger)
    assert resolved["planning_mode"] == "scenario_driven"


def test_resolve_planning_mode_prefers_task_when_user_specifies_data_request() -> None:
    trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="need building and road data for Gilgit, Pakistan",
    )
    resolved = resolve_planning_mode(trigger)
    assert resolved["planning_mode"] == "task_driven"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_intent_resolver.py`

Expected: FAIL with missing module or missing function

- [ ] **Step 3: Add a small resolver with explicit heuristics**

```python
from __future__ import annotations

from typing import Dict

from schemas.agent import RunTrigger


TASK_HINTS = ("need", "download", "data", "building", "road", "gilgit", "pakistan")


def resolve_planning_mode(trigger: RunTrigger) -> Dict[str, object]:
    content = (trigger.content or "").lower()
    if trigger.disaster_type:
        return {"planning_mode": "scenario_driven", "profile_source": "disaster_type"}
    if any(token in content for token in TASK_HINTS):
        return {"planning_mode": "task_driven", "profile_source": "direct_task"}
    return {"planning_mode": "task_driven", "profile_source": "default_task"}
```

- [ ] **Step 4: Extend `RunStatus`-visible plan context to include planning mode**

```python
normalized = {
    "intent": planning_context["intent"],
    "retrieval": planning_context["retrieval"],
    "selection_reason": selection_reason,
    "llm_provider": self.llm_provider.provider_name,
    "plan_revision": revision,
    "planning_mode": planning_context["intent"]["planning_mode"],
}
```

- [ ] **Step 5: Wire resolver output into retriever intent extraction**

```python
resolved = resolve_planning_mode(trigger)
return {
    "job_type": job_type.value,
    "trigger": trigger.model_dump(),
    "expected_output_type": f"dt.{job_type.value}.fused",
    "spatial_extent": trigger.spatial_extent,
    "temporal_start": trigger.temporal_start,
    "temporal_end": trigger.temporal_end,
    "planning_mode": resolved["planning_mode"],
    "profile_source": resolved["profile_source"],
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_intent_resolver.py tests/test_planner_context.py -k planning_mode`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add agent/intent_resolver.py schemas/agent.py agent/retriever.py tests/test_intent_resolver.py tests/test_planner_context.py
git commit -m "feat: add dual-entry planning mode resolution"
```

### Task 3: Introduce Shared TaskBundle Context For Planning

**Files:**
- Modify: `E:\vscode\fusionAgent\agent\retriever.py`
- Modify: `E:\vscode\fusionAgent\agent\planner.py`
- Create: `E:\vscode\fusionAgent\tests\test_task_bundle_context.py`

- [ ] **Step 1: Write the failing test for task bundle exposure**

```python
from agent.retriever import PlanningContextBuilder
from kg.inmemory_repository import InMemoryKGRepository
from schemas.agent import RunTrigger, RunTriggerType
from schemas.fusion import JobType


def test_retrieval_payload_contains_task_bundle_for_task_driven_request() -> None:
    builder = PlanningContextBuilder(InMemoryKGRepository())
    trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="need building and road data for Gilgit, Pakistan",
    )

    context, _reason = builder.build(job_type=JobType.building, trigger=trigger)

    assert "task_bundle" in context["intent"]
    assert context["intent"]["task_bundle"]["bundle_id"] == "task_bundle.direct_request"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_task_bundle_context.py`

Expected: FAIL because `task_bundle` is absent

- [ ] **Step 3: Add a minimal task bundle payload in retriever intent extraction**

```python
if resolved["planning_mode"] == "task_driven":
    task_bundle = {
        "bundle_id": "task_bundle.direct_request",
        "requested_tasks": [f"task.{job_type.value}.fusion"],
        "requires_disaster_profile": False,
    }
else:
    task_bundle = {
        "bundle_id": f"task_bundle.{trigger.disaster_type or 'default'}",
        "requested_tasks": [f"task.{job_type.value}.fusion"],
        "requires_disaster_profile": True,
    }
```

- [ ] **Step 4: Surface scenario profiles and task nodes in retrieval payload**

```python
payload: Dict[str, Any] = {
    "candidate_patterns": [self._pattern_to_dict(pattern) for pattern in kg_context.patterns],
    "algorithms": {algo_id: self._algo_to_dict(algo) for algo_id, algo in kg_context.algorithms.items()},
    "task_nodes": [self._task_node_to_dict(task) for task in kg_context.task_nodes],
    "scenario_profiles": [self._scenario_profile_to_dict(item) for item in kg_context.scenario_profiles],
    "parameter_specs": {
        algo_id: [self._parameter_spec_to_dict(spec) for spec in specs]
        for algo_id, specs in kg_context.parameter_specs.items()
    },
}
```

- [ ] **Step 5: Preserve the new fields when normalizing planner context**

```python
plan.context = self._normalize_plan_context(
    planning_context=planning_context,
    selection_reason=selection_reason,
    revision=1,
)
```

Use the existing normalization path and verify the new `intent.task_bundle`, `retrieval.task_nodes`, and `retrieval.scenario_profiles` survive round-trip unchanged.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_task_bundle_context.py tests/test_planner_context.py -k task_bundle`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add agent/retriever.py agent/planner.py tests/test_task_bundle_context.py tests/test_planner_context.py
git commit -m "feat: add task bundle context for dual-entry planning"
```

### Task 4: Persist Planning Mode And Constraint Profile In Runtime Evidence

**Files:**
- Modify: `E:\vscode\fusionAgent\services\agent_run_service.py`
- Modify: `E:\vscode\fusionAgent\schemas\agent.py`
- Test: `E:\vscode\fusionAgent\tests\test_agent_run_service_enhancements.py`

- [ ] **Step 1: Write the failing test for planning-mode visibility in run status**

```python
def test_run_status_records_planning_mode_and_profile_source(client):
    # Existing fixture setup omitted; use the current run creation helper
    inspection = response.json()
    assert inspection["run"]["decision_records"]
    assert inspection["plan"]["context"]["planning_mode"] in {"scenario_driven", "task_driven"}
    assert inspection["plan"]["context"]["intent"]["profile_source"] in {"disaster_type", "direct_task", "default_task"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_agent_run_service_enhancements.py -k planning_mode`

Expected: FAIL because runtime evidence does not yet assert the new fields

- [ ] **Step 3: Include planning-mode details in planning-stage audit details**

```python
event_details = {
    "workflow_id": plan.workflow_id,
    "effective_parameters": self._extract_effective_parameters(plan),
    "selected_decisions": {
        decision.decision_type: decision.selected_id for decision in planning_decisions
    },
    "planning_mode": plan.context.get("planning_mode"),
    "profile_source": plan.context.get("intent", {}).get("profile_source"),
    "task_bundle": plan.context.get("intent", {}).get("task_bundle"),
}
```

- [ ] **Step 4: Record the same fields in durable learning metadata**

```python
durable_record = DurableLearningRecord(
    record_id=f"dlr.{run_id}",
    run_id=run_id,
    job_type=request.job_type,
    trigger_type=request.trigger.type.value,
    success=success,
    disaster_type=request.trigger.disaster_type,
    pattern_id=feedback.pattern_id,
    algorithm_id=feedback.algorithm_id,
    selected_data_source=feedback.selected_data_source,
    output_data_type=output_data_type,
    target_crs=normalize_target_crs(request.target_crs),
    repaired=bool(repair_records),
    repair_count=len(repair_records),
    failure_reason=failure_reason,
    plan_revision=self._extract_plan_revision(plan),
    created_at=_utc_now(),
)
```

Keep the existing record shape, but add the planning-mode fields into the record metadata JSON if you add one. Do not break repository readers by renaming existing attributes.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_agent_run_service_enhancements.py -k planning_mode`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/agent_run_service.py schemas/agent.py tests/test_agent_run_service_enhancements.py
git commit -m "feat: persist planning mode in runtime evidence"
```

### Task 5: Align Docs And Evaluation Story With The New Architecture

**Files:**
- Modify: `E:\vscode\fusionAgent\README.md`
- Modify: `E:\vscode\fusionAgent\文档\GeoFusion 知识图谱本体模式层设计方案.md`
- Modify: `E:\vscode\fusionAgent\文档\完整项目上下文文档.md`
- Test: documentation review plus targeted smoke tests

- [ ] **Step 1: Add a concise architecture note to `README.md`**

```md
## Thesis Alignment Note

FusionAgent now distinguishes:

- executable core ontology: algorithm, task, data, workflow pattern, artifact, decision record
- scenario constraint layer: disaster event, scenario profile, data need, output requirement, QoS policy

The runtime supports both scenario-driven and task-driven entry modes.
```

- [ ] **Step 2: Add an explicit “paper ontology vs executable ontology” section to the Chinese ontology doc**

```md
## 执行本体与论文本体映射

- 执行本体：当前代码直接消费的对象
- 论文本体：论文方法完整表达所需对象
- 映射原则：先保证可执行，再逐步补足语义层
```

- [ ] **Step 3: Update the project context doc to replace “algorithm-disaster-data” wording**

```md
后续统一采用“算法-任务-数据”作为核心执行三元，灾害通过 `ScenarioProfile` 进入系统，影响任务激活、数据需求、参数偏好、输出要求与评测权重。
```

- [ ] **Step 4: Run targeted smoke and doc-consistency checks**

Run:

```powershell
python -m pytest -q tests/test_planner_context.py tests/test_intent_resolver.py tests/test_task_bundle_context.py
```

Expected: PASS

Then manually verify that:

- `README.md` and the Chinese docs use the same terms for `task-driven`, `scenario-driven`, `TaskBundle`, and `ScenarioProfile`
- no doc still claims the core triad is “algorithm-disaster-data”

- [ ] **Step 5: Commit**

```bash
git add README.md 文档/GeoFusion\ 知识图谱本体模式层设计方案.md 文档/完整项目上下文文档.md tests/test_planner_context.py tests/test_intent_resolver.py tests/test_task_bundle_context.py
git commit -m "docs: align thesis narrative with executable architecture"
```

## Self-Review

### Spec coverage

- Core triad change is covered by Task 1 and Task 5.
- Dual-entry mode is covered by Task 2 and Task 3.
- Memory/state/evidence alignment is covered by Task 4.
- Thesis/documentation alignment is covered by Task 5.

### Placeholder scan

- No `TODO`, `TBD`, or “similar to above” instructions remain.
- Every coding task includes exact file paths, code snippets, and test commands.

### Type consistency

- New type names are consistent across tasks:
  - `TaskNode`
  - `ScenarioProfileNode`
  - `task_bundle`
  - `planning_mode`
  - `profile_source`
- Runtime terminology is consistent with the design doc:
  - `scenario_driven`
  - `task_driven`

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-10-thesis-aligned-agent-architecture.md`.

Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
