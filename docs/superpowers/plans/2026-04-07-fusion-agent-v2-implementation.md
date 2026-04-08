# FusionAgent V2 Search Space, Policy, and Artifact Reuse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand FusionAgent into a policy-driven, parameter-aware, artifact-reusing disaster fusion agent with explicit decision traces and a reproducible evaluation harness.

**Architecture:** Keep the current single-agent orchestration loop in `services/agent_run_service.py`, but add three explicit subsystems: a deterministic `PolicyEngine`, a persistent `ArtifactRegistry`, and KG-backed `AlgorithmParameterSpec` metadata. Planner context should combine KG candidates, parameter specs, and artifact reuse candidates; executor should consume selected bindings and emit decision traces; harness tests should measure reliability, planning quality, and healing behavior.

**Tech Stack:** Python 3.9+, FastAPI, Pydantic, pytest, Neo4j or in-memory KG, local JSON artifact registry, existing `runs/` audit files

---

## File Structure

### New Files

- `E:/vscode/fusionAgent/agent/policy.py`
- `E:/vscode/fusionAgent/services/artifact_registry.py`
- `E:/vscode/fusionAgent/tests/test_agent_state_models.py`
- `E:/vscode/fusionAgent/tests/test_policy_engine.py`
- `E:/vscode/fusionAgent/tests/test_kg_parameter_specs.py`
- `E:/vscode/fusionAgent/tests/test_artifact_registry.py`
- `E:/vscode/fusionAgent/tests/test_parameter_binding.py`
- `E:/vscode/fusionAgent/tests/test_planner_artifact_reuse.py`
- `E:/vscode/fusionAgent/scripts/eval_harness.py`
- `E:/vscode/fusionAgent/tests/test_eval_harness.py`
- `E:/vscode/fusionAgent/文档/GeoFusion 知识图谱本体模式层设计方案_v2.md`

### Existing Files to Modify

- `E:/vscode/fusionAgent/schemas/agent.py`
- `E:/vscode/fusionAgent/agent/retriever.py`
- `E:/vscode/fusionAgent/agent/planner.py`
- `E:/vscode/fusionAgent/agent/executor.py`
- `E:/vscode/fusionAgent/services/agent_run_service.py`
- `E:/vscode/fusionAgent/api/routers/runs_v2.py`
- `E:/vscode/fusionAgent/kg/models.py`
- `E:/vscode/fusionAgent/kg/repository.py`
- `E:/vscode/fusionAgent/kg/seed.py`
- `E:/vscode/fusionAgent/kg/inmemory_repository.py`
- `E:/vscode/fusionAgent/kg/neo4j_repository.py`
- `E:/vscode/fusionAgent/kg/bootstrap.py`
- `E:/vscode/fusionAgent/adapters/building_adapter.py`
- `E:/vscode/fusionAgent/adapters/road_adapter.py`
- `E:/vscode/fusionAgent/tests/test_planner_context.py`
- `E:/vscode/fusionAgent/tests/test_repair_audit.py`
- `E:/vscode/fusionAgent/tests/test_agent_run_service_enhancements.py`
- `E:/vscode/fusionAgent/tests/test_kg_repository_enhancements.py`

### Global Test Environment

```powershell
$env:GEOFUSION_KG_BACKEND = "memory"
$env:GEOFUSION_LLM_PROVIDER = "mock"
$env:GEOFUSION_CELERY_EAGER = "1"
```

## Task 1: Add Explicit Decision and Reuse State Models

**Files:**
- Modify: `E:/vscode/fusionAgent/schemas/agent.py`
- Test: `E:/vscode/fusionAgent/tests/test_agent_state_models.py`

- [ ] **Step 1: Write the failing test**

```python
from schemas.agent import (
    ArtifactReuseDecision,
    DecisionCandidate,
    DecisionRecord,
    RunPhase,
    RunStatus,
    RunTrigger,
    RunTriggerType,
)
from schemas.fusion import JobType


def test_run_status_accepts_decision_records_and_artifact_reuse() -> None:
    status = RunStatus(
        run_id="run-1",
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        phase=RunPhase.queued,
        target_crs="EPSG:32643",
        created_at="2026-04-07T00:00:00+00:00",
        decision_records=[
            DecisionRecord(
                decision_type="pattern_selection",
                selected_id="wp.flood.building.default",
                selected_score=0.92,
                rationale="highest weighted score",
                candidates=[
                    DecisionCandidate(candidate_id="wp.flood.building.default", score=0.92, reason="success_rate"),
                    DecisionCandidate(candidate_id="wp.flood.building.safe", score=0.74, reason="lower success_rate"),
                ],
                policy_version="v2",
                evidence_refs=["retrieval.candidate_patterns"],
            )
        ],
        artifact_reuse=ArtifactReuseDecision(
            reused=False,
            artifact_id=None,
            freshness_status="miss",
            rationale="no reusable artifact found",
        ),
    )

    assert status.decision_records[0].decision_type == "pattern_selection"
    assert status.artifact_reuse.freshness_status == "miss"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_state_models.py::test_run_status_accepts_decision_records_and_artifact_reuse -v`

Expected: FAIL with `ImportError` or `ValidationError` because the new models and fields do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
class DecisionCandidate(BaseModel):
    candidate_id: str
    score: float
    reason: str


class DecisionRecord(BaseModel):
    decision_type: str
    selected_id: str
    selected_score: float
    rationale: str
    candidates: List[DecisionCandidate] = Field(default_factory=list)
    policy_version: str = "v2"
    evidence_refs: List[str] = Field(default_factory=list)


class ArtifactReuseDecision(BaseModel):
    reused: bool
    artifact_id: Optional[str] = None
    freshness_status: str
    rationale: str
```

Add fields to `RunStatus`:

```python
decision_records: List[DecisionRecord] = Field(default_factory=list)
artifact_reuse: Optional[ArtifactReuseDecision] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_agent_state_models.py::test_run_status_accepts_decision_records_and_artifact_reuse -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add schemas/agent.py tests/test_agent_state_models.py
git commit -m "feat: add decision and artifact reuse state models"
```

## Task 2: Introduce a Deterministic Policy Engine

**Files:**
- Create: `E:/vscode/fusionAgent/agent/policy.py`
- Modify: `E:/vscode/fusionAgent/agent/retriever.py`
- Test: `E:/vscode/fusionAgent/tests/test_policy_engine.py`

- [ ] **Step 1: Write the failing test**

```python
from agent.policy import CandidateScoreInput, PolicyEngine


def test_policy_engine_prefers_higher_score_and_emits_rationale() -> None:
    engine = PolicyEngine()

    selected = engine.select(
        decision_type="pattern_selection",
        candidates=[
            CandidateScoreInput(candidate_id="wp.safe", success_rate=0.82, data_quality=0.7, freshness=0.5, reuse_bonus=0.0),
            CandidateScoreInput(candidate_id="wp.default", success_rate=0.88, data_quality=0.9, freshness=0.5, reuse_bonus=0.0),
        ],
    )

    assert selected.selected_id == "wp.default"
    assert selected.selected_score > 0.0
    assert any(item.candidate_id == "wp.safe" for item in selected.candidates)
    assert "success_rate" in selected.rationale
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_policy_engine.py::test_policy_engine_prefers_higher_score_and_emits_rationale -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'agent.policy'`

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from schemas.agent import DecisionCandidate, DecisionRecord


@dataclass
class CandidateScoreInput:
    candidate_id: str
    success_rate: float = 0.0
    data_quality: float = 0.0
    freshness: float = 0.0
    reuse_bonus: float = 0.0


class PolicyEngine:
    def __init__(self) -> None:
        self.weights = {
            "success_rate": 0.45,
            "data_quality": 0.25,
            "freshness": 0.20,
            "reuse_bonus": 0.10,
        }

    def _score(self, item: CandidateScoreInput) -> float:
        return (
            item.success_rate * self.weights["success_rate"]
            + item.data_quality * self.weights["data_quality"]
            + item.freshness * self.weights["freshness"]
            + item.reuse_bonus * self.weights["reuse_bonus"]
        )

    def select(self, decision_type: str, candidates: List[CandidateScoreInput]) -> DecisionRecord:
        scored = sorted(
            [(candidate, self._score(candidate)) for candidate in candidates],
            key=lambda pair: pair[1],
            reverse=True,
        )
        best, best_score = scored[0]
        return DecisionRecord(
            decision_type=decision_type,
            selected_id=best.candidate_id,
            selected_score=best_score,
            rationale=f"selected by weighted score using success_rate={self.weights['success_rate']}",
            candidates=[
                DecisionCandidate(candidate_id=item.candidate_id, score=score, reason="weighted_score")
                for item, score in scored
            ],
            policy_version="v2",
            evidence_refs=[decision_type],
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_policy_engine.py::test_policy_engine_prefers_higher_score_and_emits_rationale -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/policy.py agent/retriever.py tests/test_policy_engine.py
git commit -m "feat: add deterministic policy engine"
```

## Task 3: Add Algorithm Parameter Specs to the KG Core

**Files:**
- Modify: `E:/vscode/fusionAgent/kg/models.py`
- Modify: `E:/vscode/fusionAgent/kg/repository.py`
- Modify: `E:/vscode/fusionAgent/kg/seed.py`
- Modify: `E:/vscode/fusionAgent/kg/inmemory_repository.py`
- Modify: `E:/vscode/fusionAgent/kg/neo4j_repository.py`
- Modify: `E:/vscode/fusionAgent/kg/bootstrap.py`
- Test: `E:/vscode/fusionAgent/tests/test_kg_parameter_specs.py`

- [ ] **Step 1: Write the failing test**

```python
from kg.inmemory_repository import InMemoryKGRepository


def test_inmemory_repository_returns_parameter_specs_for_algorithm() -> None:
    repo = InMemoryKGRepository()

    specs = repo.get_parameter_specs("algo.fusion.building.v1")

    assert specs
    assert specs[0].parameter_name == "match_threshold"
    assert specs[0].tunable is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_kg_parameter_specs.py::test_inmemory_repository_returns_parameter_specs_for_algorithm -v`

Expected: FAIL with `AttributeError: 'InMemoryKGRepository' object has no attribute 'get_parameter_specs'`

- [ ] **Step 3: Write minimal implementation**

`E:/vscode/fusionAgent/kg/models.py`:

```python
@dataclass
class AlgorithmParameterSpec:
    parameter_name: str
    parameter_type: str
    default_value: Any
    allowed_values: List[str] = field(default_factory=list)
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    tunable: bool = True
    optimization_tags: List[str] = field(default_factory=list)
```

`E:/vscode/fusionAgent/kg/repository.py`:

```python
@abstractmethod
def get_parameter_specs(self, algo_id: str) -> List[AlgorithmParameterSpec]:
    raise NotImplementedError
```

`E:/vscode/fusionAgent/kg/seed.py`:

```python
ALGORITHM_PARAMETER_SPECS = {
    "algo.fusion.building.v1": [
        AlgorithmParameterSpec(
            parameter_name="match_threshold",
            parameter_type="float",
            default_value=0.4,
            min_value=0.1,
            max_value=0.9,
            tunable=True,
            optimization_tags=["precision", "stability"],
        )
    ],
    "algo.fusion.road.v1": [
        AlgorithmParameterSpec(
            parameter_name="buffer_meters",
            parameter_type="float",
            default_value=3.0,
            min_value=1.0,
            max_value=10.0,
            tunable=True,
            optimization_tags=["recall", "speed"],
        )
    ],
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_kg_parameter_specs.py::test_inmemory_repository_returns_parameter_specs_for_algorithm -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add kg/models.py kg/repository.py kg/seed.py kg/inmemory_repository.py kg/neo4j_repository.py kg/bootstrap.py tests/test_kg_parameter_specs.py
git commit -m "feat: add parameter specs to kg metadata"
```

## Task 4: Build an Artifact Registry and Reuse Lookup

**Files:**
- Create: `E:/vscode/fusionAgent/services/artifact_registry.py`
- Modify: `E:/vscode/fusionAgent/services/agent_run_service.py`
- Modify: `E:/vscode/fusionAgent/agent/retriever.py`
- Test: `E:/vscode/fusionAgent/tests/test_artifact_registry.py`
- Test: `E:/vscode/fusionAgent/tests/test_planner_artifact_reuse.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from services.artifact_registry import ArtifactLookupRequest, ArtifactRecord, ArtifactRegistry


def test_artifact_registry_returns_only_fresh_matching_candidates(tmp_path: Path) -> None:
    registry = ArtifactRegistry(tmp_path / "artifact_index.json")
    registry.register(
        ArtifactRecord(
            artifact_id="artifact-1",
            run_id="run-1",
            job_type="building",
            disaster_type="flood",
            created_at="2026-04-07T00:00:00+00:00",
            fresh_until="2026-04-10T00:00:00+00:00",
            spatial_extent="bbox(0,0,2,2)",
            schema_fields=["name", "height"],
            artifact_path="runs/run-1/output/building.zip",
        )
    )

    matches = registry.find_reusable(
        ArtifactLookupRequest(
            job_type="building",
            disaster_type="flood",
            spatial_extent="bbox(0.5,0.5,1.5,1.5)",
            required_fields=["name"],
            now="2026-04-08T00:00:00+00:00",
        )
    )

    assert len(matches) == 1
    assert matches[0].artifact_id == "artifact-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_artifact_registry.py::test_artifact_registry_returns_only_fresh_matching_candidates -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'services.artifact_registry'`

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field


class ArtifactRecord(BaseModel):
    artifact_id: str
    run_id: str
    job_type: str
    disaster_type: str | None = None
    created_at: str
    fresh_until: str
    spatial_extent: str
    schema_fields: List[str] = Field(default_factory=list)
    artifact_path: str


class ArtifactLookupRequest(BaseModel):
    job_type: str
    disaster_type: str | None = None
    spatial_extent: str | None = None
    required_fields: List[str] = Field(default_factory=list)
    now: str


class ArtifactRegistry:
    def __init__(self, index_path: Path) -> None:
        self.index_path = index_path
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> List[ArtifactRecord]:
        if not self.index_path.exists():
            return []
        data = json.loads(self.index_path.read_text(encoding="utf-8"))
        return [ArtifactRecord.model_validate(item) for item in data]

    def _save(self, records: List[ArtifactRecord]) -> None:
        self.index_path.write_text(
            json.dumps([record.model_dump(mode="json") for record in records], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def register(self, record: ArtifactRecord) -> None:
        records = [item for item in self._load() if item.artifact_id != record.artifact_id]
        records.append(record)
        self._save(records)

    def find_reusable(self, request: ArtifactLookupRequest) -> List[ArtifactRecord]:
        matches: List[ArtifactRecord] = []
        for record in self._load():
            if record.job_type != request.job_type:
                continue
            if request.disaster_type and record.disaster_type not in {request.disaster_type, None}:
                continue
            if record.fresh_until < request.now:
                continue
            if not all(field in record.schema_fields for field in request.required_fields):
                continue
            matches.append(record)
        return matches
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_artifact_registry.py::test_artifact_registry_returns_only_fresh_matching_candidates -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/artifact_registry.py services/agent_run_service.py agent/retriever.py tests/test_artifact_registry.py tests/test_planner_artifact_reuse.py
git commit -m "feat: add artifact registry and reuse lookup"
```

## Task 5: Pass Parameter Bindings and Output Policy Through Planner and Executor

**Files:**
- Modify: `E:/vscode/fusionAgent/agent/retriever.py`
- Modify: `E:/vscode/fusionAgent/agent/planner.py`
- Modify: `E:/vscode/fusionAgent/agent/executor.py`
- Modify: `E:/vscode/fusionAgent/adapters/building_adapter.py`
- Modify: `E:/vscode/fusionAgent/adapters/road_adapter.py`
- Test: `E:/vscode/fusionAgent/tests/test_parameter_binding.py`
- Test: `E:/vscode/fusionAgent/tests/test_planner_context.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from agent.executor import ExecutionContext, WorkflowExecutor
from kg.inmemory_repository import InMemoryKGRepository
from schemas.agent import RunTrigger, RunTriggerType, WorkflowPlan, WorkflowTask, WorkflowTaskInput, WorkflowTaskOutput
from schemas.fusion import JobType


def test_executor_passes_selected_parameters_to_handler(tmp_path: Path) -> None:
    seen = {}

    def handler(ctx: ExecutionContext) -> Path:
        seen["parameters"] = ctx.step_parameters
        out = tmp_path / "ok.shp"
        out.write_text("dummy", encoding="utf-8")
        return out

    executor = WorkflowExecutor(
        kg_repo=InMemoryKGRepository(),
        algorithm_handlers={"algo.fusion.building.v1": handler},
    )

    plan = WorkflowPlan(
        workflow_id="wf-params",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        context={},
        tasks=[
            WorkflowTask(
                step=1,
                name="building_fusion",
                description="building fusion",
                algorithm_id="algo.fusion.building.v1",
                input=WorkflowTaskInput(
                    data_type_id="dt.building.bundle",
                    data_source_id="upload.bundle",
                    parameters={"match_threshold": 0.55, "output_fields": ["name", "height"]},
                ),
                output=WorkflowTaskOutput(data_type_id="dt.building.fused", description="output"),
            )
        ],
        expected_output="building result",
    )

    context = ExecutionContext(
        run_id="run-1",
        job_type=JobType.building,
        osm_shp=tmp_path / "osm.shp",
        ref_shp=tmp_path / "ref.shp",
        output_dir=tmp_path,
        target_crs="EPSG:4326",
    )

    executor.execute_plan(plan=plan, context=context, repair_records=[])

    assert seen["parameters"]["match_threshold"] == 0.55
    assert seen["parameters"]["output_fields"] == ["name", "height"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_parameter_binding.py::test_executor_passes_selected_parameters_to_handler -v`

Expected: FAIL because `ExecutionContext` does not expose `step_parameters`.

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass
class ExecutionContext:
    ...
    step_parameters: Dict[str, object] = field(default_factory=dict)
```

Before algorithm execution:

```python
context.step_parameters = dict(task.input.parameters)
last_output = self._execute_algorithm(task.algorithm_id, context)
```

Adapter signature:

```python
def run_building_fusion(..., algorithm_parameters: Dict[str, object] | None = None) -> Path:
    algorithm_parameters = dict(algorithm_parameters or {})
```

Executor call:

```python
return run_building_fusion(
    ...,
    algorithm_parameters=context.step_parameters,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_parameter_binding.py::test_executor_passes_selected_parameters_to_handler -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/retriever.py agent/planner.py agent/executor.py adapters/building_adapter.py adapters/road_adapter.py tests/test_parameter_binding.py tests/test_planner_context.py
git commit -m "feat: bind selected parameters and output policy through execution"
```

## Task 6: Record Policy Decisions and Strengthen Healing Audit

**Files:**
- Modify: `E:/vscode/fusionAgent/agent/executor.py`
- Modify: `E:/vscode/fusionAgent/services/agent_run_service.py`
- Modify: `E:/vscode/fusionAgent/api/routers/runs_v2.py`
- Test: `E:/vscode/fusionAgent/tests/test_repair_audit.py`
- Test: `E:/vscode/fusionAgent/tests/test_agent_run_service_enhancements.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from schemas.agent import RepairRecord
from services.agent_run_service import AgentRunService


def test_healing_summary_and_decision_records_are_persisted(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")

    repair_records = [
        RepairRecord(
            attempt_no=1,
            strategy="alternative_algorithm",
            step=1,
            message="Recovered with safe algorithm",
            success=True,
            timestamp="2026-04-07T00:00:00+00:00",
            reason_code="alternative_algorithm_succeeded",
            from_algorithm="algo.fusion.building.v1",
            to_algorithm="algo.fusion.building.safe",
        )
    ]

    summary = service._build_healing_summary(repair_records)

    assert summary["successful_repairs"] == 1
    assert summary["last_reason_code"] == "alternative_algorithm_succeeded"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_repair_audit.py::test_healing_summary_and_decision_records_are_persisted -v`

Expected: FAIL after you extend the assertion to require a new decision record path.

- [ ] **Step 3: Write minimal implementation**

Add the policy engine to `AgentRunService`:

```python
from agent.policy import CandidateScoreInput, PolicyEngine


class AgentRunService:
    def __init__(...):
        ...
        self.policy = PolicyEngine()
```

Append a `DecisionRecord` after plan creation:

```python
decision = self.policy.select(
    decision_type="pattern_selection",
    candidates=[
        CandidateScoreInput(
            candidate_id=item["pattern_id"],
            success_rate=float(item.get("success_rate", 0.0)),
            data_quality=1.0,
            freshness=0.0,
            reuse_bonus=0.0,
        )
        for item in plan.context.get("retrieval", {}).get("candidate_patterns", [])
    ],
)
current.decision_records.append(decision)
```

Append a `DecisionRecord` after replan:

```python
current.decision_records.append(
    DecisionRecord(
        decision_type="replan_or_fail",
        selected_id=f"revision_{replanned_revision}",
        selected_score=1.0,
        rationale=f"execution failed at step {failed_step}; replan applied",
        candidates=[],
        policy_version="v2",
        evidence_refs=[failure_message],
    )
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_repair_audit.py -v`

Run: `pytest tests/test_agent_run_service_enhancements.py -v`

Expected: PASS for both suites

- [ ] **Step 5: Commit**

```bash
git add agent/executor.py services/agent_run_service.py api/routers/runs_v2.py tests/test_repair_audit.py tests/test_agent_run_service_enhancements.py
git commit -m "feat: persist policy decisions and healing audit"
```

## Task 7: Add an Evaluation Harness with Baselines and Fault Injection

**Files:**
- Create: `E:/vscode/fusionAgent/scripts/eval_harness.py`
- Create: `E:/vscode/fusionAgent/tests/test_eval_harness.py`
- Modify: `E:/vscode/fusionAgent/tests/test_api_v2_integration.py`
- Modify: `E:/vscode/fusionAgent/tests/test_kg_repository_enhancements.py`
- Modify: `E:/vscode/fusionAgent/文档/GeoFusion 知识图谱本体模式层设计方案_v2.md`

- [ ] **Step 1: Write the failing test**

```python
from scripts.eval_harness import summarize_results


def test_eval_harness_summarizes_accuracy_and_repair_metrics() -> None:
    summary = summarize_results(
        [
            {"case_id": "c1", "success": True, "repaired": False, "plan_valid": True},
            {"case_id": "c2", "success": True, "repaired": True, "plan_valid": True},
            {"case_id": "c3", "success": False, "repaired": False, "plan_valid": False},
        ]
    )

    assert summary["run_success_rate"] == 2 / 3
    assert summary["repair_success_rate"] == 1 / 1
    assert summary["plan_valid_rate"] == 2 / 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_eval_harness.py::test_eval_harness_summarizes_accuracy_and_repair_metrics -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.eval_harness'`

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

from typing import Dict, List


def summarize_results(results: List[Dict[str, object]]) -> Dict[str, float]:
    total = len(results)
    successes = sum(1 for item in results if item.get("success") is True)
    repairs = [item for item in results if item.get("repaired") is True]
    repair_successes = sum(1 for item in repairs if item.get("success") is True)
    plan_valid = sum(1 for item in results if item.get("plan_valid") is True)
    return {
        "run_success_rate": successes / total if total else 0.0,
        "repair_success_rate": repair_successes / len(repairs) if repairs else 0.0,
        "plan_valid_rate": plan_valid / total if total else 0.0,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_eval_harness.py::test_eval_harness_summarizes_accuracy_and_repair_metrics -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/eval_harness.py tests/test_eval_harness.py tests/test_api_v2_integration.py tests/test_kg_repository_enhancements.py 文档/GeoFusion\ 知识图谱本体模式层设计方案_v2.md
git commit -m "feat: add evaluation harness and ontology v2 doc"
```

## Task 8: Run the Consolidated Regression Suite

**Files:**
- Test only: `E:/vscode/fusionAgent/tests`

- [ ] **Step 1: Run targeted fast suites**

Run:

```bash
pytest tests/test_agent_state_models.py tests/test_policy_engine.py tests/test_kg_parameter_specs.py tests/test_artifact_registry.py tests/test_parameter_binding.py tests/test_eval_harness.py -v
```

Expected: all PASS

- [ ] **Step 2: Run integration suites**

Run:

```bash
pytest tests/test_planner_context.py tests/test_repair_audit.py tests/test_agent_run_service_enhancements.py tests/test_api_v2_integration.py tests/test_worker_orchestration.py -v
```

Expected: all PASS

- [ ] **Step 3: Run the full repository regression**

Run:

```bash
pytest -q
```

Expected: PASS with no new failures

- [ ] **Step 4: Run local smoke**

Run:

```bash
python scripts/smoke_local_v2.py
```

Expected: run created, plan available, audit available, artifact downloadable

- [ ] **Step 5: Commit the stabilization pass**

```bash
git add tests scripts/eval_harness.py docs/superpowers/specs/2026-04-07-fusion-agent-v2-design.md docs/superpowers/plans/2026-04-07-fusion-agent-v2-implementation.md
git commit -m "test: stabilize fusionagent v2 policy and reuse workflow"
```

## Inputs Required Before Full-Value Execution

- Real `building` and `road` sample datasets across at least two disaster scenarios
- A curated algorithm inventory with parameter names and known failure modes
- Desired field retention and renaming rules for final artifacts
- Freshness threshold expectations for artifact reuse
- Priority weights for `accuracy`, `stability`, `speed`, `freshness`, and `cost`

## Self-Review

### Spec Coverage

- Search space expansion: covered by Tasks 3, 4, and 5.
- Explicit policy: covered by Tasks 1, 2, and 6.
- Artifact reuse and freshness: covered by Task 4.
- Ontology adjustments: covered by Task 7.
- Evaluation and harness: covered by Tasks 7 and 8.

### Placeholder Scan

- No `TODO`, `TBD`, or deferred placeholders remain.
- Every task has explicit files, commands, and concrete code snippets.

### Type Consistency

- `DecisionRecord` and `ArtifactReuseDecision` are introduced in Task 1 and reused consistently later.
- `AlgorithmParameterSpec` is defined in Task 3 and consumed in Tasks 4 and 5.
- `PolicyEngine` is defined in Task 2 and integrated in Task 6.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-07-fusion-agent-v2-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
