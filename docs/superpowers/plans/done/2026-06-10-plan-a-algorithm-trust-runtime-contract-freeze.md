# Plan A Algorithm Trust Runtime Contract Freeze Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish Freeze A by hardening algorithm trust, deprecated-version blocking, runtime-contract enforcement, recovery compatibility, and freeze regression evidence.

**Architecture:** Add one shared runtime contract service that evaluates algorithms, sources, patterns, and alternatives against KG metadata plus ToolRegistry state. Wire that service into Validator, Planner fallback, Executor healing, semantic parameter binding, recovery classification, and Freeze A regression reporting so every runtime surface uses the same allow/block semantics.

**Tech Stack:** Python, Pydantic/dataclasses, pytest, existing `kg` repositories, `ToolRegistry`, `WorkflowValidator`, `WorkflowPlanner`, `WorkflowExecutor`, `AgentRunService`, and PowerShell test commands on Windows.

---

## Phase 0: Sources Consulted

- `docs/superpowers/specs/2026-06-10-fusionagent-reliability-roadmap-design.md`
  - Defines Plan A as Algorithm Trust plus Runtime Contract Freeze.
  - Requires deprecated/unselectable algorithms to be blocked across planner, fallback, preferred pattern, healing, old references, and recovery.
- `agent/validator.py`
  - Currently marks invalid tasks with `kg_validated=False` but does not fail closed by itself.
  - Blocks unknown algorithms and reservation-only algorithms, but not all deprecated/unselectable states through one state machine.
- `agent/planner.py`
  - KG fallback selects ranked patterns directly.
  - `_finalize_plan()` injects alternatives from KG without runtime-contract filtering.
- `agent/executor.py`
  - Healing order is hardcoded and alternatives can come from plan or KG.
  - `RepairRecord` currently records what happened, not all candidate/skipped decision evidence.
- `agent/semantic_parameter_binding.py`
  - Binds semantic parameters into every building or POI task without checking that the algorithm's parameter specs support those keys.
- `services/run_recovery_service.py`
  - Classifies recovery from phase, checkpoint, and failure category only.
  - Does not inspect whether a stale run's plan now references blocked algorithms.
- `services/plan_grounding_service.py`
  - Already supports report/warn/enforce for candidate-pattern grounding.
- `services/tool_contract_report_service.py`
  - Reports ToolRegistry mismatches but does not include KG runtime status.
- `kg/seed.py` and `kg/seed_manifest.generated.json`
  - Deprecated algorithms remain in KG as historical nodes.
  - Some active legacy algorithms lack explicit `runtime_status` and `selectable_now` metadata.
- Existing tests:
  - `tests/test_workflow_validator.py`
  - `tests/test_tool_registry.py`
  - `tests/test_plan_grounding_service.py`
  - `tests/test_semantic_parameter_binding.py`
  - `tests/test_run_recovery_service.py`
  - `tests/test_repair_audit.py`
  - `tests/test_repair_strategy.py`
  - `tests/test_kg_seed_manifest.py`
  - `tests/test_check_kg_contract.py`

## File Structure

- Create: `services/runtime_contract_service.py`
  - Single contract evaluator for algorithms, data sources, workflow patterns, healing alternatives, and semantic parameter binding.
- Create: `tests/test_runtime_contract_service.py`
  - Unit tests for algorithm/source/pattern allow/block decisions and `gap_severity`.
- Modify: `schemas/agent.py`
  - Extend `ValidationReport` and `RepairRecord` with enforcement/audit fields.
- Modify: `kg/seed.py`
  - Add explicit runtime metadata to active legacy algorithms and reserved transforms.
- Modify: `kg/seed_manifest.generated.json`
  - Regenerate after seed changes.
- Modify: `agent/validator.py`
  - Use `RuntimeContractService` to validate algorithms and sources.
- Modify: `services/agent_run_service.py`
  - Fail closed after validation in enforce mode and pass runtime contract service into planner/executor/recovery surfaces.
- Modify: `agent/planner.py`
  - Filter KG fallback patterns and alternatives through the runtime contract.
- Modify: `agent/executor.py`
  - Reject blocked algorithms before handler dispatch and record candidate/skipped healing actions at decision time.
- Modify: `agent/semantic_parameter_binding.py`
  - Bind semantic parameters only when the target algorithm's parameter specs allow the key.
- Modify: `services/run_recovery_service.py`
  - Detect algorithm-state drift before automatic stale-run recovery.
- Modify: `services/tool_contract_report_service.py`
  - Include KG runtime state alongside ToolRegistry validity.
- Create: `scripts/freeze_a_runtime_contract_check.py`
  - One-command Freeze A regression report.
- Create: `tests/test_freeze_a_runtime_contract_check.py`
  - Script smoke test and contract output assertions.
- Create: `docs/superpowers/specs/2026-06-10-algorithm-trust-matrix.md`
  - Algorithm trust matrix snapshot for Plan A.
- Create: `docs/superpowers/specs/2026-06-10-runtime-governance-matrix.md`
  - Runtime governance matrix snapshot for Plan A.

---

### Task 1: Add Shared Runtime Contract Service

**Files:**
- Create: `services/runtime_contract_service.py`
- Test: `tests/test_runtime_contract_service.py`

- [ ] **Step 1: Write failing contract tests**

Create `tests/test_runtime_contract_service.py`:

```python
from __future__ import annotations

from dataclasses import replace

from agent.tooling import build_default_tool_registry
from kg.inmemory_repository import InMemoryKGRepository
from kg.models import AlgorithmNode, PatternStep, WorkflowPatternNode
from schemas.fusion import JobType
from services.runtime_contract_service import RuntimeContractService


def test_runtime_contract_allows_registered_runtime_candidate_algorithm() -> None:
    service = RuntimeContractService(InMemoryKGRepository(), tool_registry=build_default_tool_registry())

    decision = service.evaluate_algorithm("algo.fusion.road.conflation.v7", surface="validator")

    assert decision.allowed is True
    assert decision.reason_code is None
    assert decision.gap_severity == "none"
    assert decision.runtime_status == "runtime_candidate"


def test_runtime_contract_blocks_deprecated_algorithm_even_when_present_in_kg() -> None:
    service = RuntimeContractService(InMemoryKGRepository(), tool_registry=build_default_tool_registry())

    decision = service.evaluate_algorithm("algo.fusion.road.v1", surface="planner_fallback")

    assert decision.allowed is False
    assert decision.reason_code == "DEPRECATED_ALGORITHM"
    assert decision.gap_severity == "fail_soft"
    assert "deprecated_by" in decision.evidence


def test_runtime_contract_blocks_registry_missing_algorithm() -> None:
    repo = InMemoryKGRepository()
    algorithms = dict(repo.algorithms)
    algorithms["algo.fusion.custom.unregistered"] = AlgorithmNode(
        algo_id="algo.fusion.custom.unregistered",
        algo_name="Custom Unregistered",
        input_types=["dt.building.bundle"],
        output_type="dt.building.fused",
        task_type="building_fusion",
        tool_ref="custom:missing",
        metadata={"runtime_status": "runtime_candidate", "selectable_now": True},
    )
    service = RuntimeContractService(
        InMemoryKGRepository(algorithms=algorithms),
        tool_registry=build_default_tool_registry(),
    )

    decision = service.evaluate_algorithm("algo.fusion.custom.unregistered", surface="executor")

    assert decision.allowed is False
    assert decision.reason_code == "UNKNOWN_TOOL"
    assert decision.gap_severity == "unguarded"


def test_runtime_contract_blocks_pattern_containing_deprecated_step() -> None:
    repo = InMemoryKGRepository()
    pattern = WorkflowPatternNode(
        pattern_id="wp.bad.deprecated",
        pattern_name="Bad Deprecated Pattern",
        job_type=JobType.road,
        disaster_types=["generic"],
        steps=[
            PatternStep(
                order=1,
                name="deprecated_road",
                algorithm_id="algo.fusion.road.v1",
                input_data_type="dt.road.bundle",
                output_data_type="dt.road.fused",
                data_source_id="catalog.flood.road",
            )
        ],
    )
    service = RuntimeContractService(repo, tool_registry=build_default_tool_registry())

    decision = service.evaluate_pattern(pattern, surface="planner_fallback")

    assert decision.allowed is False
    assert decision.reason_code == "PATTERN_CONTAINS_BLOCKED_ALGORITHM"
    assert decision.evidence["blocked_algorithm_ids"] == ["algo.fusion.road.v1"]


def test_runtime_contract_filters_alternatives_and_reports_skips() -> None:
    service = RuntimeContractService(InMemoryKGRepository(), tool_registry=build_default_tool_registry())

    result = service.filter_algorithm_ids(
        ["algo.fusion.building.safe", "algo.fusion.road.v1", "algo.fusion.unknown"],
        surface="executor_healing",
    )

    assert result.allowed_ids == ["algo.fusion.building.safe"]
    assert [item["algorithm_id"] for item in result.skipped] == [
        "algo.fusion.road.v1",
        "algo.fusion.unknown",
    ]
    assert result.skipped[0]["reason_code"] == "DEPRECATED_ALGORITHM"
    assert result.skipped[1]["reason_code"] == "UNKNOWN_ALGORITHM"
```

- [ ] **Step 2: Run tests to confirm failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_runtime_contract_service.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'services.runtime_contract_service'`.

- [ ] **Step 3: Implement the runtime contract service**

Create `services/runtime_contract_service.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from agent.tooling import ToolRegistry, build_default_tool_registry
from kg.models import AlgorithmNode, DataSourceNode, WorkflowPatternNode
from kg.repository import KGRepository


BLOCKED_ALGORITHM_STATUSES = {"deprecated", "reservation_only"}
RESEARCH_ONLY_STATUSES = {"research_utility"}
BLOCKED_SOURCE_STATUSES = {"reservation_only", "deprecated"}


@dataclass(frozen=True)
class RuntimeContractDecision:
    allowed: bool
    reason_code: str | None = None
    message: str = ""
    runtime_status: str | None = None
    selectable_now: bool | None = None
    gap_severity: str = "none"
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason_code": self.reason_code,
            "message": self.message,
            "runtime_status": self.runtime_status,
            "selectable_now": self.selectable_now,
            "gap_severity": self.gap_severity,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class RuntimeContractFilterResult:
    allowed_ids: list[str]
    skipped: list[dict[str, Any]]


class RuntimeContractService:
    def __init__(self, kg_repo: KGRepository, *, tool_registry: ToolRegistry | None = None) -> None:
        self.kg_repo = kg_repo
        self.tool_registry = tool_registry or build_default_tool_registry()

    def evaluate_algorithm(
        self,
        algorithm_id: str,
        *,
        surface: str,
        require_tool: bool = True,
        allow_research_utility: bool = False,
    ) -> RuntimeContractDecision:
        algo = self.kg_repo.get_algorithm(algorithm_id)
        if algo is None:
            return RuntimeContractDecision(
                allowed=False,
                reason_code="UNKNOWN_ALGORITHM",
                message=f"Algorithm not found in KG: {algorithm_id}",
                gap_severity="unguarded",
                evidence={"algorithm_id": algorithm_id, "surface": surface},
            )

        metadata = dict(algo.metadata or {})
        runtime_status = str(metadata.get("runtime_status") or "").strip().lower() or None
        selectable_now = metadata.get("selectable_now")
        selectable_bool = None if selectable_now is None else bool(selectable_now)
        evidence = {
            "algorithm_id": algorithm_id,
            "surface": surface,
            "usage_mode": algo.usage_mode,
            "metadata": metadata,
        }
        if metadata.get("deprecated_by"):
            evidence["deprecated_by"] = metadata.get("deprecated_by")

        if runtime_status is None:
            return RuntimeContractDecision(
                allowed=False,
                reason_code="MISSING_RUNTIME_STATUS",
                message=f"Algorithm lacks runtime_status metadata: {algorithm_id}",
                runtime_status=None,
                selectable_now=selectable_bool,
                gap_severity="unguarded",
                evidence=evidence,
            )
        if runtime_status == "deprecated" or str(algo.usage_mode).lower() == "deprecated":
            return RuntimeContractDecision(
                allowed=False,
                reason_code="DEPRECATED_ALGORITHM",
                message=f"Algorithm is deprecated: {algorithm_id}",
                runtime_status=runtime_status,
                selectable_now=selectable_bool,
                gap_severity="fail_soft",
                evidence=evidence,
            )
        if runtime_status in BLOCKED_ALGORITHM_STATUSES:
            return RuntimeContractDecision(
                allowed=False,
                reason_code="RESERVED_ALGORITHM" if runtime_status == "reservation_only" else "UNSELECTABLE_ALGORITHM",
                message=f"Algorithm is not executable at runtime: {algorithm_id}",
                runtime_status=runtime_status,
                selectable_now=selectable_bool,
                gap_severity="fail_soft",
                evidence=evidence,
            )
        if selectable_bool is False:
            return RuntimeContractDecision(
                allowed=False,
                reason_code="UNSELECTABLE_ALGORITHM",
                message=f"Algorithm is marked selectable_now=false: {algorithm_id}",
                runtime_status=runtime_status,
                selectable_now=False,
                gap_severity="fail_soft",
                evidence=evidence,
            )
        if runtime_status in RESEARCH_ONLY_STATUSES and not allow_research_utility:
            return RuntimeContractDecision(
                allowed=False,
                reason_code="RESEARCH_UTILITY_ALGORITHM",
                message=f"Algorithm is research-only for this surface: {algorithm_id}",
                runtime_status=runtime_status,
                selectable_now=selectable_bool,
                gap_severity="fail_soft",
                evidence=evidence,
            )

        spec = self.tool_registry.get(algorithm_id) if require_tool else None
        if require_tool and spec is None:
            return RuntimeContractDecision(
                allowed=False,
                reason_code="UNKNOWN_TOOL",
                message=f"Algorithm is not registered in ToolRegistry: {algorithm_id}",
                runtime_status=runtime_status,
                selectable_now=selectable_bool,
                gap_severity="unguarded",
                evidence=evidence,
            )
        if spec is not None and spec.error_policy.get("reserved") == "true":
            return RuntimeContractDecision(
                allowed=False,
                reason_code="RESERVED_TOOL",
                message=f"ToolRegistry marks algorithm as reserved: {algorithm_id}",
                runtime_status=runtime_status,
                selectable_now=selectable_bool,
                gap_severity="fail_soft",
                evidence={**evidence, "tool_error_policy": dict(spec.error_policy)},
            )

        return RuntimeContractDecision(
            allowed=True,
            runtime_status=runtime_status,
            selectable_now=selectable_bool,
            gap_severity="none",
            evidence=evidence,
        )

    def evaluate_data_source(self, source_id: str, *, surface: str) -> RuntimeContractDecision:
        source = self._get_source(source_id)
        if source is None:
            return RuntimeContractDecision(
                allowed=False,
                reason_code="UNKNOWN_DATA_SOURCE",
                message=f"Data source not found in KG: {source_id}",
                gap_severity="unguarded",
                evidence={"source_id": source_id, "surface": surface},
            )
        metadata = dict(source.metadata or {})
        runtime_status = str(metadata.get("runtime_status") or "runtime_candidate").strip().lower()
        selectable_now = metadata.get("selectable_now")
        selectable_bool = None if selectable_now is None else bool(selectable_now)
        if runtime_status in BLOCKED_SOURCE_STATUSES or selectable_bool is False:
            return RuntimeContractDecision(
                allowed=False,
                reason_code="UNSELECTABLE_DATA_SOURCE",
                message=f"Data source is not selectable now: {source_id}",
                runtime_status=runtime_status,
                selectable_now=selectable_bool,
                gap_severity="fail_soft",
                evidence={"source_id": source_id, "surface": surface, "metadata": metadata},
            )
        return RuntimeContractDecision(
            allowed=True,
            runtime_status=runtime_status,
            selectable_now=selectable_bool,
            gap_severity="none",
            evidence={"source_id": source_id, "surface": surface, "metadata": metadata},
        )

    def evaluate_pattern(self, pattern: WorkflowPatternNode, *, surface: str) -> RuntimeContractDecision:
        blocked: list[dict[str, Any]] = []
        for step in pattern.steps:
            decision = self.evaluate_algorithm(step.algorithm_id, surface=surface)
            if not decision.allowed:
                blocked.append({"algorithm_id": step.algorithm_id, **decision.to_dict()})
        if blocked:
            return RuntimeContractDecision(
                allowed=False,
                reason_code="PATTERN_CONTAINS_BLOCKED_ALGORITHM",
                message=f"Pattern contains blocked algorithms: {pattern.pattern_id}",
                gap_severity="fail_soft",
                evidence={
                    "pattern_id": pattern.pattern_id,
                    "blocked_algorithm_ids": [item["algorithm_id"] for item in blocked],
                    "blocked": blocked,
                },
            )
        return RuntimeContractDecision(
            allowed=True,
            gap_severity="none",
            evidence={"pattern_id": pattern.pattern_id, "surface": surface},
        )

    def filter_patterns(self, patterns: Iterable[WorkflowPatternNode], *, surface: str) -> tuple[list[WorkflowPatternNode], list[dict[str, Any]]]:
        allowed: list[WorkflowPatternNode] = []
        skipped: list[dict[str, Any]] = []
        for pattern in patterns:
            decision = self.evaluate_pattern(pattern, surface=surface)
            if decision.allowed:
                allowed.append(pattern)
            else:
                skipped.append({"pattern_id": pattern.pattern_id, **decision.to_dict()})
        return allowed, skipped

    def filter_algorithm_ids(self, algorithm_ids: Iterable[str], *, surface: str) -> RuntimeContractFilterResult:
        allowed: list[str] = []
        skipped: list[dict[str, Any]] = []
        for algorithm_id in dict.fromkeys(algorithm_ids):
            decision = self.evaluate_algorithm(algorithm_id, surface=surface)
            if decision.allowed:
                allowed.append(algorithm_id)
            else:
                skipped.append({"algorithm_id": algorithm_id, **decision.to_dict()})
        return RuntimeContractFilterResult(allowed_ids=allowed, skipped=skipped)

    def parameter_keys_for_algorithm(self, algorithm_id: str) -> set[str]:
        return {spec.key for spec in self.kg_repo.get_parameter_specs(algorithm_id)}

    def _get_source(self, source_id: str) -> DataSourceNode | None:
        if source_id == "upload.bundle":
            return DataSourceNode(
                source_id="upload.bundle",
                source_name="Uploaded Bundle",
                supported_types=["dt.raw.vector"],
                disaster_types=["generic"],
                metadata={"runtime_status": "runtime_candidate", "selectable_now": True},
            )
        for source in self.kg_repo.list_data_sources():
            if source.source_id == source_id:
                return source
        return None
```

- [ ] **Step 4: Run tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_runtime_contract_service.py -q
```

Expected: FAIL for active legacy algorithms that still lack explicit `runtime_status`, then pass after Task 2 updates seed metadata.

- [ ] **Step 5: Commit after Task 2, not now**

Do not commit Task 1 alone because the service intentionally exposes seed metadata gaps that Task 2 closes.

---

### Task 2: Make Active Algorithm Metadata Explicit

**Files:**
- Modify: `kg/seed.py`
- Modify: `kg/seed_manifest.generated.json`
- Test: `tests/test_kg_seed_manifest.py`
- Test: `tests/test_check_kg_contract.py`
- Test: `tests/test_runtime_contract_service.py`

- [ ] **Step 1: Add failing metadata tests**

Append to `tests/test_kg_seed_manifest.py`:

```python
def test_registered_runtime_algorithms_have_explicit_runtime_metadata() -> None:
    from agent.tooling import build_default_tool_registry

    payload = build_seed_manifest_payload()
    algorithms = {item["algo_id"]: item for item in payload["algorithms"]}
    registry = build_default_tool_registry()
    reserved_ids = {"algo.transform.trajectory_to_road_candidate"}

    for algorithm_id in registry.list_algorithm_ids():
        algo = algorithms.get(algorithm_id)
        assert algo is not None, algorithm_id
        metadata = algo.get("metadata") or {}
        assert metadata.get("runtime_status"), algorithm_id
        if algorithm_id not in reserved_ids:
            assert metadata.get("selectable_now") is True, algorithm_id


def test_deprecated_algorithms_are_explicitly_unselectable() -> None:
    payload = build_seed_manifest_payload()
    deprecated = [
        item for item in payload["algorithms"]
        if (item.get("metadata") or {}).get("runtime_status") == "deprecated"
    ]

    assert {item["algo_id"] for item in deprecated} >= {
        "algo.fusion.road.v1",
        "algo.fusion.road.safe",
        "algo.fusion.water.v1",
    }
    for item in deprecated:
        metadata = item.get("metadata") or {}
        assert metadata.get("selectable_now") is False
        assert metadata.get("deprecated_by")
```

- [ ] **Step 2: Run tests to confirm failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_kg_seed_manifest.py::test_registered_runtime_algorithms_have_explicit_runtime_metadata tests/test_kg_seed_manifest.py::test_deprecated_algorithms_are_explicitly_unselectable -q
```

Expected: FAIL for registered legacy algorithms without explicit metadata.

- [ ] **Step 3: Update active algorithm metadata in `kg/seed.py`**

For every ToolRegistry algorithm that is executable now, add or extend metadata with:

```python
metadata={
    "runtime_status": "runtime_candidate",
    "selectable_now": True,
    "claim_state": "runtime_supported",
}
```

For bounded or research algorithms, use the narrower claim state:

```python
metadata={
    "runtime_status": "bounded_supported",
    "selectable_now": True,
    "claim_state": "bounded_supported",
}
```

For `algo.transform.trajectory_to_road_candidate`, use:

```python
metadata={
    "runtime_status": "reservation_only",
    "selectable_now": False,
    "claim_state": "reservation_only",
}
```

Do not change deprecated algorithm IDs or revive deprecated algorithms. Keep their metadata equivalent to:

```python
metadata={
    "runtime_status": "deprecated",
    "selectable_now": False,
    "deprecated_by": "algo.fusion.road.conflation.v7",
}
```

- [ ] **Step 4: Regenerate seed manifest**

Run:

```powershell
.venv\Scripts\python.exe scripts\export_kg_seed_manifest.py
```

Expected: `kg/seed_manifest.generated.json` updates with explicit metadata.

- [ ] **Step 5: Update static inventory counts only when necessary**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_check_kg_contract.py -q
```

Expected: PASS. If counts change because only metadata changed, no test update is needed. If a count changes, stop and inspect the seed edit because Plan A should not add or remove KG nodes.

- [ ] **Step 6: Verify contract and seed tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_runtime_contract_service.py tests/test_kg_seed_manifest.py tests/test_check_kg_contract.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```powershell
git add services/runtime_contract_service.py tests/test_runtime_contract_service.py kg/seed.py kg/seed_manifest.generated.json tests/test_kg_seed_manifest.py
git commit -m "feat: add runtime contract service"
```

---

### Task 3: Enforce Runtime Contract In Validator And Agent Validation Stage

**Files:**
- Modify: `schemas/agent.py`
- Modify: `agent/validator.py`
- Modify: `services/agent_run_service.py`
- Test: `tests/test_workflow_validator.py`
- Test: `tests/test_agent_run_service_enhancements.py`
- Test: `tests/test_toolspec_contract_enforcement.py`

- [ ] **Step 1: Add failing Validator tests**

Append to `tests/test_workflow_validator.py`:

```python
def test_validator_marks_deprecated_algorithm_with_runtime_contract_issue() -> None:
    plan = WorkflowPlan(
        workflow_id="wf_deprecated_algo",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="road"),
        context={},
        tasks=[
            WorkflowTask(
                step=1,
                name="deprecated_road",
                description="deprecated road",
                algorithm_id="algo.fusion.road.v1",
                input=WorkflowTaskInput(data_type_id="dt.road.bundle", data_source_id="catalog.flood.road", parameters={}),
                output=WorkflowTaskOutput(data_type_id="dt.road.fused", description=""),
            )
        ],
        expected_output="road result",
    )

    fixed = WorkflowValidator(InMemoryKGRepository()).validate_and_repair(plan)

    assert fixed.validation is not None
    assert fixed.validation.valid is False
    assert fixed.validation.issues[0].code == "DEPRECATED_ALGORITHM"
    assert fixed.validation.rejected is False
    assert fixed.validation.enforcement_mode == "report"
    assert fixed.tasks[0].kg_validated is False


def test_validator_enforce_mode_marks_report_rejected() -> None:
    plan = WorkflowPlan(
        workflow_id="wf_enforce_deprecated",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="road"),
        context={},
        tasks=[
            WorkflowTask(
                step=1,
                name="deprecated_road",
                description="deprecated road",
                algorithm_id="algo.fusion.road.v1",
                input=WorkflowTaskInput(data_type_id="dt.road.bundle", data_source_id="catalog.flood.road", parameters={}),
                output=WorkflowTaskOutput(data_type_id="dt.road.fused", description=""),
            )
        ],
        expected_output="road result",
    )

    fixed = WorkflowValidator(InMemoryKGRepository(), enforcement_mode="enforce").validate_and_repair(plan)

    assert fixed.validation is not None
    assert fixed.validation.valid is False
    assert fixed.validation.rejected is True
    assert fixed.validation.enforcement_mode == "enforce"
```

Append to `tests/test_agent_run_service_enhancements.py`:

```python
def test_agent_run_service_rejects_validator_invalid_plan_before_execution(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    monkeypatch.setenv("GEOFUSION_VALIDATOR_MODE", "enforce")
    plan = _build_road_task_driven_plan(workflow_id="wf_deprecated_validator")
    plan.tasks[0].algorithm_id = "algo.fusion.road.v1"

    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    called = {"execution": False}

    def fake_resolve_execution_inputs(**_kwargs):
        called["execution"] = True
        raise AssertionError("execution inputs must not resolve after validation rejection")

    monkeypatch.setattr(service, "_resolve_execution_inputs", fake_resolve_execution_inputs)

    status = service.create_run(
        request=_build_auto_request(job_type=JobType.road, content="need road data"),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.failed
    assert "DEPRECATED_ALGORITHM" in (latest.error or "")
    assert called["execution"] is False
    events = service.get_audit_events(status.run_id)
    assert any(event.kind == "validation_rejected" for event in events)
    assert not any(event.kind == "task_inputs_resolved" for event in events)
```

- [ ] **Step 2: Run tests to confirm failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_workflow_validator.py::test_validator_marks_deprecated_algorithm_with_runtime_contract_issue tests/test_workflow_validator.py::test_validator_enforce_mode_marks_report_rejected tests/test_agent_run_service_enhancements.py::test_agent_run_service_rejects_validator_invalid_plan_before_execution -q
```

Expected: FAIL because `ValidationReport` has no `rejected` or `enforcement_mode`, Validator does not use runtime contract service, and AgentRunService does not reject invalid validation reports.

- [ ] **Step 3: Extend validation schema**

In `schemas/agent.py`, change `ValidationReport` to:

```python
class ValidationReport(BaseModel):
    valid: bool
    inserted_transform_steps: int = 0
    issues: List[ValidationIssue] = Field(default_factory=list)
    enforcement_mode: str = "report"
    rejected: bool = False
```

- [ ] **Step 4: Wire runtime contract into Validator**

In `agent/validator.py`, add imports:

```python
import os

from services.runtime_contract_service import RuntimeContractService
```

Change constructor:

```python
    def __init__(self, kg_repo: KGRepository, *, enforcement_mode: str | None = None) -> None:
        self.kg_repo = kg_repo
        self.enforcement_mode = str(enforcement_mode or os.getenv("GEOFUSION_VALIDATOR_MODE", "report")).lower()
        self.contract = RuntimeContractService(kg_repo)
```

Replace direct reservation-only algorithm/source checks with runtime contract checks:

```python
            algo_decision = self.contract.evaluate_algorithm(task.algorithm_id, surface="validator")
            if not algo_decision.allowed:
                task.kg_validated = False
                task.depends_on = normalized_deps
                task.step = len(output_tasks) + 1
                output_tasks.append(task)
                step_map[original_step] = task.step
                issues.append(
                    ValidationIssue(
                        code=algo_decision.reason_code or "ALGORITHM_RUNTIME_CONTRACT_FAILED",
                        message=algo_decision.message,
                        step=task.step,
                    )
                )
                continue
```

After resolving `source`, replace reservation-only source check with:

```python
            source_decision = self.contract.evaluate_data_source(task.input.data_source_id, surface="validator")
            if not source_decision.allowed:
                task.kg_validated = False
                task.depends_on = normalized_deps
                task.step = len(output_tasks) + 1
                output_tasks.append(task)
                step_map[original_step] = task.step
                issues.append(
                    ValidationIssue(
                        code=source_decision.reason_code or "DATA_SOURCE_RUNTIME_CONTRACT_FAILED",
                        message=source_decision.message,
                        step=task.step,
                    )
                )
                continue
```

At report construction, set enforcement fields:

```python
        valid = len(issues) == 0
        rejected = (not valid) and self.enforcement_mode == "enforce"
        report = ValidationReport(
            valid=valid,
            inserted_transform_steps=inserted,
            issues=issues,
            enforcement_mode=self.enforcement_mode,
            rejected=rejected,
        )
```

- [ ] **Step 5: Fail closed in AgentRunService validation stage**

In `services/agent_run_service.py`, modify `run_validation_stage()` after persisting validation:

```python
        rejected = bool(getattr(validated.validation, "rejected", False))
        if rejected:
            issue_codes = [issue.code for issue in validated.validation.issues]
            error = "VALIDATION_REJECTED: " + ", ".join(issue_codes)
            self._update_status(
                run_id,
                RunPhase.failed,
                progress=45,
                error=error,
                failure_summary=error,
                finished_at=_utc_now(),
                plan_path=str(plan_path),
                validation_path=str(validation_path),
                plan_revision=self._extract_plan_revision(validated),
                checkpoint=self._checkpoint(stage="validation", plan_revision=self._extract_plan_revision(validated)),
                event_kind="validation_rejected",
                event_message="Workflow plan rejected by Validator fail-closed mode.",
                event_details={
                    "issue_codes": issue_codes,
                    "enforcement_mode": validated.validation.enforcement_mode,
                    "issues": [issue.model_dump(mode="json") for issue in validated.validation.issues],
                },
            )
            raise RuntimeError(error)
```

Then keep the existing `plan_validated` update for non-rejected plans.

- [ ] **Step 6: Verify focused tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_workflow_validator.py tests/test_toolspec_contract_enforcement.py tests/test_agent_run_service_enhancements.py::test_agent_run_service_rejects_validator_invalid_plan_before_execution -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```powershell
git add schemas/agent.py agent/validator.py services/agent_run_service.py tests/test_workflow_validator.py tests/test_agent_run_service_enhancements.py
git commit -m "feat: enforce runtime contract during validation"
```

---

### Task 4: Filter Planner Fallback, Preferred Patterns, And Alternatives

**Files:**
- Modify: `agent/planner.py`
- Test: `tests/test_planner_runtime_contract.py`

- [ ] **Step 1: Write failing planner tests**

Create `tests/test_planner_runtime_contract.py`:

```python
from __future__ import annotations

from kg.inmemory_repository import InMemoryKGRepository
from kg.models import PatternStep, WorkflowPatternNode
from llm.providers.base import LLMProvider
from llm.providers.mock_provider import MockLLMProvider
from agent.planner import WorkflowPlanner
from schemas.agent import RunTrigger, RunTriggerType, WorkflowTask, WorkflowTaskInput, WorkflowTaskOutput, WorkflowPlan
from schemas.fusion import JobType


class FailingProvider(LLMProvider):
    def __init__(self) -> None:
        self.model = "failing-model"

    def generate_workflow_plan(self, system_prompt, context):
        raise RuntimeError("simulated planning failure")


def _deprecated_pattern() -> WorkflowPatternNode:
    return WorkflowPatternNode(
        pattern_id="wp.deprecated.road",
        pattern_name="Deprecated Road",
        job_type=JobType.road,
        disaster_types=["generic"],
        success_rate=0.99,
        steps=[
            PatternStep(
                order=1,
                name="deprecated_road",
                algorithm_id="algo.fusion.road.v1",
                input_data_type="dt.road.bundle",
                output_data_type="dt.road.fused",
                data_source_id="catalog.flood.road",
            )
        ],
    )


def test_planner_fallback_skips_deprecated_high_score_pattern() -> None:
    repo = InMemoryKGRepository(patterns=[_deprecated_pattern(), *InMemoryKGRepository().patterns])
    planner = WorkflowPlanner(repo, FailingProvider())

    plan = planner.create_plan(
        run_id="run-planner-contract",
        job_type=JobType.road,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="road"),
    )

    assert plan.context["planning_source"] == "kg_fallback"
    assert plan.tasks[0].algorithm_id == "algo.fusion.road.conflation.v7"
    assert plan.context["runtime_contract"]["skipped_fallback_patterns"][0]["pattern_id"] == "wp.deprecated.road"


def test_planner_finalize_filters_deprecated_alternatives() -> None:
    repo = InMemoryKGRepository()
    planner = WorkflowPlanner(repo, MockLLMProvider())
    plan = WorkflowPlan(
        workflow_id="wf-alt-filter",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="road"),
        context={},
        tasks=[
            WorkflowTask(
                step=1,
                name="road",
                description="road",
                algorithm_id="algo.fusion.road.conflation.v7",
                input=WorkflowTaskInput(data_type_id="dt.road.bundle", data_source_id="catalog.flood.road"),
                output=WorkflowTaskOutput(data_type_id="dt.road.fused"),
                alternatives=["algo.fusion.road.v1", "algo.fusion.road.conflation.v7"],
            )
        ],
        expected_output="road",
    )

    finalized = planner._finalize_plan(plan)

    assert "algo.fusion.road.v1" not in finalized.tasks[0].alternatives
    assert finalized.context["runtime_contract"]["skipped_alternatives"][0]["algorithm_id"] == "algo.fusion.road.v1"
```

- [ ] **Step 2: Run tests to confirm failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_planner_runtime_contract.py -q
```

Expected: FAIL because planner does not filter patterns or alternatives and no context evidence exists.

- [ ] **Step 3: Wire contract service into planner**

In `agent/planner.py`, add import:

```python
from services.runtime_contract_service import RuntimeContractService
```

In `WorkflowPlanner.__init__`, add:

```python
        self.runtime_contract = RuntimeContractService(kg_repo)
```

In `_select_fallback_pattern()`, after loading `patterns`, add:

```python
        allowed_patterns, skipped_patterns = self.runtime_contract.filter_patterns(
            patterns,
            surface="planner_fallback",
        )
        if allowed_patterns:
            patterns = allowed_patterns
        else:
            raise ValueError(f"No runtime-selectable workflow pattern found for job_type={job_type.value}")
```

In `_select_fallback_pattern_from_context()`, after `by_id` is built and before returning a ranked pattern:

```python
            skipped_patterns: list[dict[str, object]] = []
            for pattern_id in ranked_ids:
                pattern = by_id.get(pattern_id)
                if pattern is None:
                    continue
                decision = self.runtime_contract.evaluate_pattern(pattern, surface="planner_fallback")
                if decision.allowed:
                    pattern.metadata = {**pattern.metadata, "_runtime_contract_skipped_patterns": skipped_patterns}
                    return pattern
                skipped_patterns.append({"pattern_id": pattern_id, **decision.to_dict()})
```

In `_build_skeleton_plan()`, add skipped fallback evidence to context:

```python
            "context": {
                "pattern_id": pattern.pattern_id,
                "pattern_name": pattern.pattern_name,
                "source": "kg_fallback",
                "runtime_contract": {
                    "skipped_fallback_patterns": list(pattern.metadata.get("_runtime_contract_skipped_patterns", [])),
                },
            },
```

In `_finalize_plan()`, replace alternative assignment with:

```python
            kg_alternatives = [a.algo_id for a in self.kg_repo.get_alternative_algorithms(task.algorithm_id, limit=3)]
            filter_result = self.runtime_contract.filter_algorithm_ids(
                [*task.alternatives, *kg_alternatives],
                surface="planner_alternative",
            )
            task.alternatives = list(dict.fromkeys(filter_result.allowed_ids))
            if filter_result.skipped:
                runtime_contract = dict(plan.context.get("runtime_contract") or {})
                runtime_contract.setdefault("skipped_alternatives", []).extend(filter_result.skipped)
                plan.context = {**plan.context, "runtime_contract": runtime_contract}
```

- [ ] **Step 4: Verify focused tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_planner_runtime_contract.py tests/test_plan_grounding_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add agent/planner.py tests/test_planner_runtime_contract.py
git commit -m "feat: filter planner choices by runtime contract"
```

---

### Task 5: Gate Semantic Parameter Binding Against Parameter Specs

**Files:**
- Modify: `agent/semantic_parameter_binding.py`
- Modify: `services/agent_run_service.py`
- Test: `tests/test_semantic_parameter_binding.py`

- [ ] **Step 1: Add failing semantic binding test**

Append to `tests/test_semantic_parameter_binding.py`:

```python
class _FakeSpec:
    def __init__(self, key: str) -> None:
        self.key = key


class _FakeKG:
    def __init__(self, keys: set[str]) -> None:
        self.keys = keys

    def get_parameter_specs(self, _algorithm_id: str):
        return [_FakeSpec(key) for key in sorted(self.keys)]


def test_semantic_binding_skips_parameters_not_supported_by_algorithm_specs() -> None:
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
        },
        parameter_hints={"source_priority_order": ["MS", "OSM"]},
        validation={"valid": True, "issues": []},
    )
    plan = _plan("building", "algo.fusion.road.v1")

    bound = bind_source_semantic_parameters(plan, contract, kg_repo=_FakeKG({"source_semantic_contract_path"}))

    params = bound.tasks[0].input.parameters
    assert params == {"source_semantic_contract_path": "source_semantic_contract.json"}
```

- [ ] **Step 2: Run tests to confirm failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_semantic_parameter_binding.py -q
```

Expected: FAIL because `bind_source_semantic_parameters()` does not accept `kg_repo`.

- [ ] **Step 3: Update semantic binding function**

Change signature in `agent/semantic_parameter_binding.py`:

```python
def bind_source_semantic_parameters(plan: WorkflowPlan, contract: SourceSemanticContract, kg_repo=None) -> WorkflowPlan:
```

Add helper:

```python
def _allowed_parameter_keys(task, kg_repo) -> set[str] | None:
    if kg_repo is None:
        return None
    return {spec.key for spec in kg_repo.get_parameter_specs(task.algorithm_id)}


def _set_if_allowed(params: dict, allowed: set[str] | None, key: str, value) -> None:
    if allowed is None or key in allowed:
        params[key] = value
```

Replace direct assignments with `_set_if_allowed(...)`:

```python
        allowed = _allowed_parameter_keys(task, kg_repo)
        _set_if_allowed(params, allowed, "source_semantic_contract_path", "source_semantic_contract.json")

        if contract.job_type == "building":
            for key in ["height_output_field", "canonical_height_field", "positive_only"]:
                if key in contract.height_policy:
                    _set_if_allowed(params, allowed, key, contract.height_policy[key])
            priority = contract.parameter_hints.get("source_priority_order")
            if priority:
                _set_if_allowed(params, allowed, "source_priority_order", list(priority))
        elif contract.job_type == "poi":
            precision = contract.parameter_hints.get("geohash_precision")
            if precision is not None:
                _set_if_allowed(params, allowed, "geohash_precision", int(precision))
```

In `services/agent_run_service.py`, update the call:

```python
        updated_plan = bind_source_semantic_parameters(plan, contract, kg_repo=self.kg_repo)
```

- [ ] **Step 4: Verify tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_semantic_parameter_binding.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add agent/semantic_parameter_binding.py services/agent_run_service.py tests/test_semantic_parameter_binding.py
git commit -m "feat: gate semantic parameters by algorithm specs"
```

---

### Task 6: Enforce Runtime Contract In Executor Healing Audit

**Files:**
- Modify: `schemas/agent.py`
- Modify: `agent/executor.py`
- Test: `tests/test_repair_audit.py`
- Test: `tests/test_repair_strategy.py`
- Test: `tests/test_tool_registry.py`

- [ ] **Step 1: Add failing healing audit tests**

Append to `tests/test_repair_audit.py`:

```python
def test_executor_skips_deprecated_healing_alternative_with_decision_evidence(tmp_path: Path) -> None:
    output_file = tmp_path / "ok.shp"
    output_file.write_text("dummy", encoding="utf-8")

    def fail_handler(_ctx: ExecutionContext) -> Path:
        raise RuntimeError("primary failed")

    def ok_handler(_ctx: ExecutionContext) -> Path:
        return output_file

    executor = WorkflowExecutor(
        kg_repo=InMemoryKGRepository(),
        algorithm_handlers={
            "algo.fusion.road.conflation.v7": fail_handler,
            "algo.fusion.building.safe": ok_handler,
        },
    )
    plan = WorkflowPlan(
        workflow_id="wf_repair_audit_contract",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="repair"),
        context={},
        tasks=[
            WorkflowTask(
                step=1,
                name="road_fusion",
                description="road fusion",
                algorithm_id="algo.fusion.road.conflation.v7",
                input=WorkflowTaskInput(data_type_id="dt.road.bundle", data_source_id="catalog.flood.road", parameters={}),
                output=WorkflowTaskOutput(data_type_id="dt.road.fused", description=""),
                alternatives=["algo.fusion.road.v1", "algo.fusion.building.safe"],
                kg_validated=True,
            )
        ],
        expected_output="road",
    )
    ctx = ExecutionContext(
        run_id="r1",
        job_type=JobType.road,
        osm_shp=tmp_path / "osm.shp",
        ref_shp=tmp_path / "ref.shp",
        output_dir=tmp_path,
        target_crs="EPSG:4326",
    )
    repairs = []

    artifact = executor.execute_plan(plan=plan, context=ctx, repair_records=repairs)

    assert artifact == output_file
    success = next(record for record in repairs if record.reason_code == "alternative_algorithm_succeeded")
    assert success.policy_source == "runtime_contract"
    assert [item["algorithm_id"] for item in success.candidate_actions] == [
        "algo.fusion.road.v1",
        "algo.fusion.building.safe",
    ]
    assert success.selected_action["algorithm_id"] == "algo.fusion.building.safe"
    assert success.skipped_actions[0]["algorithm_id"] == "algo.fusion.road.v1"
    assert success.skipped_actions[0]["reason_code"] == "DEPRECATED_ALGORITHM"
```

- [ ] **Step 2: Run tests to confirm failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_repair_audit.py::test_executor_skips_deprecated_healing_alternative_with_decision_evidence -q
```

Expected: FAIL because `RepairRecord` has no policy fields and executor does not filter alternatives.

- [ ] **Step 3: Extend `RepairRecord` schema**

In `schemas/agent.py`, change `RepairRecord` to:

```python
class RepairRecord(BaseModel):
    attempt_no: int
    strategy: str
    step: int
    message: str
    success: bool
    timestamp: str
    reason_code: Optional[str] = None
    from_algorithm: Optional[str] = None
    to_algorithm: Optional[str] = None
    policy_source: Optional[str] = None
    policy_decision_basis: Dict[str, Any] = Field(default_factory=dict)
    candidate_actions: List[Dict[str, Any]] = Field(default_factory=list)
    selected_action: Optional[Dict[str, Any]] = None
    skipped_actions: List[Dict[str, Any]] = Field(default_factory=list)
```

- [ ] **Step 4: Wire contract into executor**

In `agent/executor.py`, add import:

```python
from services.runtime_contract_service import RuntimeContractService
```

In `WorkflowExecutor.__init__`, add:

```python
        self.runtime_contract = RuntimeContractService(self.kg_repo, tool_registry=self.tool_registry)
```

At the start of `_execute_algorithm()`:

```python
        decision = self.runtime_contract.evaluate_algorithm(algorithm_id, surface="executor")
        if not decision.allowed:
            raise ValueError(f"{decision.reason_code}: {decision.message}")
```

Before the alternative loop, replace `alt_algos` construction with:

```python
            candidate_alt_algos = [*task.alternatives]
            if not candidate_alt_algos:
                candidate_alt_algos = [a.algo_id for a in self.kg_repo.get_alternative_algorithms(task.algorithm_id, limit=3)]
            alt_filter = self.runtime_contract.filter_algorithm_ids(candidate_alt_algos, surface="executor_healing")
            alt_algos = alt_filter.allowed_ids
            candidate_actions = [{"algorithm_id": item} for item in dict.fromkeys(candidate_alt_algos)]
            skipped_actions = alt_filter.skipped
```

For `alternative_algorithm_succeeded`, add fields:

```python
                            policy_source="runtime_contract",
                            policy_decision_basis={"surface": "executor_healing"},
                            candidate_actions=candidate_actions,
                            selected_action={"algorithm_id": alt_algo},
                            skipped_actions=skipped_actions,
```

For `alternative_algorithm_failed`, add the same `policy_source`, `candidate_actions`, and `skipped_actions`, with:

```python
                            selected_action={"algorithm_id": alt_algo},
```

If no alternative is attempted because all are skipped, append a repair record before transform insertion:

```python
            if candidate_alt_algos and not alt_algos:
                attempt_no += 1
                repair_records.append(
                    RepairRecord(
                        attempt_no=attempt_no,
                        strategy="alternative_algorithm",
                        step=task.step,
                        message="All alternative algorithms were rejected by runtime contract.",
                        success=False,
                        timestamp=_utc_now(),
                        reason_code="alternative_algorithm_contract_rejected",
                        from_algorithm=task.algorithm_id,
                        policy_source="runtime_contract",
                        policy_decision_basis={"surface": "executor_healing"},
                        candidate_actions=candidate_actions,
                        skipped_actions=skipped_actions,
                    )
                )
```

- [ ] **Step 5: Verify focused tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_repair_audit.py tests/test_repair_strategy.py tests/test_tool_registry.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add schemas/agent.py agent/executor.py tests/test_repair_audit.py
git commit -m "feat: audit healing decisions with runtime contract"
```

---

### Task 7: Make Recovery Classification Contract-Aware

**Files:**
- Modify: `services/run_recovery_service.py`
- Modify: `services/agent_run_service.py`
- Test: `tests/test_run_recovery_service.py`

- [ ] **Step 1: Add failing recovery test**

Append to `tests/test_run_recovery_service.py`:

```python
def test_collect_recoverable_runs_marks_algorithm_state_drift_for_manual_review(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_dir = _write_run_record(
        runs_root,
        "run-stale-deprecated",
        {
            "run_id": "run-stale-deprecated",
            "phase": "running",
            "job_type": "road",
            "updated_at": "2026-04-23T00:00:00+00:00",
            "checkpoint": {"stage": "execution", "plan_revision": 1},
        },
    )
    (run_dir / "plan.json").write_text(
        json.dumps(
            {
                "workflow_id": "wf-deprecated",
                "trigger": {"type": "user_query", "content": "road"},
                "tasks": [
                    {
                        "step": 1,
                        "name": "deprecated_road",
                        "description": "deprecated",
                        "algorithm_id": "algo.fusion.road.v1",
                        "input": {"data_type_id": "dt.road.bundle", "data_source_id": "catalog.flood.road"},
                        "output": {"data_type_id": "dt.road.fused"},
                    }
                ],
                "expected_output": "road",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    records = collect_recoverable_runs(
        runs_root=runs_root,
        stale_after_seconds=300,
        include_manual_review=True,
        runtime_contract_service=RuntimeContractService(InMemoryKGRepository()),
    )

    assert len(records) == 1
    assert records[0]["run_id"] == "run-stale-deprecated"
    assert records[0]["recovery_action"] == "mark_failed_requires_manual_review"
    assert records[0]["algorithm_state"]["reason_code"] == "DEPRECATED_ALGORITHM"
```

Add imports at the top:

```python
from kg.inmemory_repository import InMemoryKGRepository
from services.runtime_contract_service import RuntimeContractService
```

- [ ] **Step 2: Run test to confirm failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_run_recovery_service.py::test_collect_recoverable_runs_marks_algorithm_state_drift_for_manual_review -q
```

Expected: FAIL because `collect_recoverable_runs()` has no contract-aware parameters.

- [ ] **Step 3: Add plan algorithm-state inspection helper**

In `services/run_recovery_service.py`, add imports:

```python
from schemas.agent import WorkflowPlan
from services.runtime_contract_service import RuntimeContractService
```

Change function signature:

```python
def collect_recoverable_runs(
    runs_root: Path,
    stale_after_seconds: int,
    *,
    include_manual_review: bool = False,
    runtime_contract_service: RuntimeContractService | None = None,
) -> list[dict[str, Any]]:
```

Add helper:

```python
def _algorithm_state_for_run(run_dir: Path, runtime_contract_service: RuntimeContractService | None) -> dict[str, Any] | None:
    if runtime_contract_service is None:
        return None
    plan_path = run_dir / "plan.json"
    if not plan_path.exists():
        return None
    try:
        plan = WorkflowPlan.model_validate(json.loads(plan_path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return {
            "allowed": False,
            "reason_code": "PLAN_UNREADABLE",
            "message": "Plan could not be read for recovery contract check.",
        }
    for task in plan.tasks:
        if task.is_transform:
            continue
        decision = runtime_contract_service.evaluate_algorithm(task.algorithm_id, surface="recovery")
        if not decision.allowed:
            return {
                "allowed": False,
                "algorithm_id": task.algorithm_id,
                **decision.to_dict(),
            }
    return {"allowed": True}
```

Inside `collect_recoverable_runs()`, after computing `recovery_action`, add:

```python
        algorithm_state = _algorithm_state_for_run(run_json_path.parent, runtime_contract_service)
        if algorithm_state is not None and algorithm_state.get("allowed") is False:
            recovery_action = "mark_failed_requires_manual_review"
```

Change the recoverable-action filter:

```python
        if recovery_action not in RECOVERABLE_ACTIONS and not include_manual_review:
            continue
```

When building `record`, add:

```python
        if algorithm_state is not None:
            record["algorithm_state"] = algorithm_state
```

- [ ] **Step 4: Pass contract service from AgentRunService**

In `services/agent_run_service.py`, import `RuntimeContractService` if not already imported and change `collect_recoverable_runs()`:

```python
    def collect_recoverable_runs(self, stale_after_seconds: int = 300) -> list[dict[str, Any]]:
        return collect_recoverable_runs(
            runs_root=self.base_dir,
            stale_after_seconds=stale_after_seconds,
            runtime_contract_service=RuntimeContractService(self.kg_repo),
        )
```

- [ ] **Step 5: Verify recovery tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_run_recovery_service.py tests/test_run_recovery_executor.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add services/run_recovery_service.py services/agent_run_service.py tests/test_run_recovery_service.py
git commit -m "feat: make recovery classification contract aware"
```

---

### Task 8: Extend Tool Contract Report With KG Runtime State

**Files:**
- Modify: `services/tool_contract_report_service.py`
- Test: `tests/test_tool_contract_report_service.py`

- [ ] **Step 1: Update report test helper and add failing report test**

Replace the existing `_plan()` helper in `tests/test_tool_contract_report_service.py` with this version so road tests can set the input data type:

```python
def _plan(
    *,
    algorithm_id: str = "algo.fusion.building.v1",
    input_type: str = "dt.building.bundle",
    output_type: str = "dt.building.fused",
) -> WorkflowPlan:
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
                input=WorkflowTaskInput(
                    data_type_id=input_type,
                    data_source_id="catalog.flood.building",
                ),
                output=WorkflowTaskOutput(data_type_id=output_type),
                is_transform=False,
                kg_validated=True,
            )
        ],
        expected_output="building result",
    )
```

Then append this test to the same file:

```python
def test_tool_contract_report_includes_kg_runtime_contract_for_deprecated_algorithm() -> None:
    report = build_tool_contract_report(
        _plan(algorithm_id="algo.fusion.road.v1", input_type="dt.road.bundle", output_type="dt.road.fused"),
        kg_repo=InMemoryKGRepository(),
    )

    step = report["steps"][0]
    assert report["valid"] is False
    assert step["runtime_contract"]["allowed"] is False
    assert step["runtime_contract"]["reason_code"] == "DEPRECATED_ALGORITHM"
    assert "DEPRECATED_ALGORITHM" in step["issue_codes"]
```

Add imports if absent:

```python
from kg.inmemory_repository import InMemoryKGRepository
```

- [ ] **Step 2: Run test to confirm failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_tool_contract_report_service.py::test_tool_contract_report_includes_kg_runtime_contract_for_deprecated_algorithm -q
```

Expected: FAIL because `build_tool_contract_report()` has no `kg_repo` parameter.

- [ ] **Step 3: Update report service**

In `services/tool_contract_report_service.py`, add imports:

```python
from kg.repository import KGRepository
from services.runtime_contract_service import RuntimeContractService
```

Change signature:

```python
def build_tool_contract_report(
    plan: WorkflowPlan,
    *,
    registry: ToolRegistry | None = None,
    kg_repo: KGRepository | None = None,
) -> dict[str, Any]:
```

Before building `steps`:

```python
    runtime_contract = RuntimeContractService(kg_repo, tool_registry=tool_registry) if kg_repo is not None else None
```

Change `_build_step_report()` signature:

```python
def _build_step_report(task: WorkflowTask, registry: ToolRegistry, runtime_contract: RuntimeContractService | None) -> dict[str, Any]:
```

After ToolRegistry issue codes are calculated:

```python
    runtime_contract_payload = None
    if runtime_contract is not None:
        contract_decision = runtime_contract.evaluate_algorithm(task.algorithm_id, surface="tool_contract_report")
        runtime_contract_payload = contract_decision.to_dict()
        if not contract_decision.allowed and contract_decision.reason_code:
            issue_codes.append(contract_decision.reason_code)
```

Add to returned step dict:

```python
        "runtime_contract": runtime_contract_payload,
```

Include runtime contract issue codes in `blocking_issue_codes`:

```python
        "DEPRECATED_ALGORITHM",
        "RESERVED_ALGORITHM",
        "UNSELECTABLE_ALGORITHM",
        "MISSING_RUNTIME_STATUS",
        "RESEARCH_UTILITY_ALGORITHM",
        "RESERVED_TOOL",
```

- [ ] **Step 4: Verify report tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_tool_contract_report_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add services/tool_contract_report_service.py tests/test_tool_contract_report_service.py
git commit -m "feat: report kg runtime contract in tool contracts"
```

---

### Task 9: Add Freeze A Regression Script And Matrices

**Files:**
- Create: `scripts/freeze_a_runtime_contract_check.py`
- Create: `tests/test_freeze_a_runtime_contract_check.py`
- Create: `docs/superpowers/specs/2026-06-10-algorithm-trust-matrix.md`
- Create: `docs/superpowers/specs/2026-06-10-runtime-governance-matrix.md`

- [ ] **Step 1: Write failing script test**

Create `tests/test_freeze_a_runtime_contract_check.py`:

```python
from __future__ import annotations

import json
import subprocess
import sys


def test_freeze_a_runtime_contract_check_outputs_passing_report() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/freeze_a_runtime_contract_check.py", "--json"],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)

    assert payload["ok"] is True
    assert payload["deprecated_algorithm_guard"]["ok"] is True
    assert payload["tool_registry_guard"]["ok"] is True
    assert payload["workflow_pattern_guard"]["ok"] is True
    assert payload["validator_mode"]["default"] == "enforce"
```

- [ ] **Step 2: Run test to confirm failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_freeze_a_runtime_contract_check.py -q
```

Expected: FAIL because the script does not exist.

- [ ] **Step 3: Create Freeze A script**

Create `scripts/freeze_a_runtime_contract_check.py`:

```python
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.tooling import build_default_tool_registry
from kg.inmemory_repository import InMemoryKGRepository
from kg.seed_manifest import build_seed_manifest_payload
from services.runtime_contract_service import RuntimeContractService


def build_report() -> dict[str, object]:
    repo = InMemoryKGRepository()
    registry = build_default_tool_registry()
    contract = RuntimeContractService(repo, tool_registry=registry)
    manifest = build_seed_manifest_payload()
    algorithms = {item["algo_id"]: item for item in manifest["algorithms"]}

    deprecated = [
        item for item in manifest["algorithms"]
        if (item.get("metadata") or {}).get("runtime_status") == "deprecated"
    ]
    deprecated_failures = []
    for item in deprecated:
        decision = contract.evaluate_algorithm(item["algo_id"], surface="freeze_a")
        metadata = item.get("metadata") or {}
        if decision.allowed or metadata.get("selectable_now") is not False:
            deprecated_failures.append({"algorithm_id": item["algo_id"], "decision": decision.to_dict()})

    registry_failures = []
    reserved_ids = {"algo.transform.trajectory_to_road_candidate"}
    for algorithm_id in registry.list_algorithm_ids():
        if algorithm_id in reserved_ids:
            continue
        decision = contract.evaluate_algorithm(algorithm_id, surface="freeze_a")
        if not decision.allowed:
            registry_failures.append({"algorithm_id": algorithm_id, "decision": decision.to_dict()})

    pattern_failures = []
    for pattern in repo.list_workflow_patterns():
        decision = contract.evaluate_pattern(pattern, surface="freeze_a")
        if not decision.allowed:
            pattern_failures.append({"pattern_id": pattern.pattern_id, "decision": decision.to_dict()})

    report = {
        "seed_content_hash": manifest["metadata"]["content_hash"],
        "tool_registry_algorithm_ids": registry.list_algorithm_ids(),
        "validator_mode": {
            "default": os.getenv("GEOFUSION_VALIDATOR_MODE", "enforce"),
            "grounding_default": os.getenv("GEOFUSION_PLAN_GROUNDING_MODE", "enforce"),
        },
        "deprecated_algorithm_guard": {
            "ok": not deprecated_failures,
            "checked": [item["algo_id"] for item in deprecated],
            "failures": deprecated_failures,
        },
        "tool_registry_guard": {
            "ok": not registry_failures,
            "failures": registry_failures,
        },
        "workflow_pattern_guard": {
            "ok": not pattern_failures,
            "failures": pattern_failures,
        },
    }
    report["ok"] = all(
        section["ok"]
        for section in [
            report["deprecated_algorithm_guard"],
            report["tool_registry_guard"],
            report["workflow_pattern_guard"],
        ]
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = build_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Create Algorithm Trust Matrix**

Create `docs/superpowers/specs/2026-06-10-algorithm-trust-matrix.md`:

```markdown
# Algorithm Trust Matrix

This matrix is the Freeze A snapshot for algorithm trust. It records runtime exposure, deprecated-version risk, evidence state, and paper claim limits.

| algorithm_id | family | current_claim | entry_points | planner_exposure | healing_role | healing_source_consistency | deprecated_risk | tool_registry_status | validator_status | neo4j_stale_risk | test_coverage | quality_metrics | real_evidence | paper_claim_limit | closure_status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| algo.fusion.building.v1 | building | runtime_supported | ToolRegistry, KG, planner, executor | active | primary | checked by Freeze A script | low | registered | contract_checked | medium | validator/tool/executor | artifact gate only | existing smoke/golden | deterministic GIS adapter, not AI fusion | open until Freeze A script passes |
| algo.fusion.building.safe | building | runtime_supported | ToolRegistry, KG, executor healing | active | first_alternative | checked by Freeze A script | low | registered | contract_checked | medium | repair tests | artifact gate only | existing smoke | fallback adapter | open until Freeze A script passes |
| algo.fusion.road.conflation.v7 | road | runtime_supported | ToolRegistry, KG, planner, executor | active | primary | checked by Freeze A script | low | registered | contract_checked | medium | v7 tests | topology metrics pending Plan B | real smoke evidence exists | road V7 only | open until Freeze A script passes |
| algo.fusion.road.v1 | road | deprecated | KG history, Neo4j bootstrap | blocked | none | blocked | P0 if selectable | not registered | rejected | high | negative tests in Plan A | none | historical only | no thesis quality claim | open until negative tests pass |
| algo.fusion.road.safe | road | deprecated | KG history, Neo4j bootstrap | blocked | none | blocked | P0 if selectable | not registered | rejected | high | negative tests in Plan A | none | historical only | no thesis quality claim | open until negative tests pass |
| algo.fusion.water_polygon.priority_merge.v2 | water_polygon | runtime_supported | ToolRegistry, KG, planner, executor | active | primary | checked by Freeze A script | low | registered | contract_checked | medium | polygon tests | polygon metrics pending Plan B | smoke evidence exists | polygon water only | open until Freeze A script passes |
| algo.fusion.water.v1 | water_polygon | deprecated | KG history, Neo4j bootstrap | blocked | none | blocked | P0 if selectable | not registered | rejected | high | negative tests in Plan A | none | historical only | no thesis quality claim | open until negative tests pass |
| algo.fusion.waterways.conflation.v7 | waterways | runtime_supported | ToolRegistry, KG, planner, executor | active | primary | checked by Freeze A script | low | registered | contract_checked | medium | waterways v7 tests | line metrics pending Plan B | smoke evidence exists | waterways only | open until Freeze A script passes |
| algo.fusion.poi.v1 | poi | bounded_supported | ToolRegistry, KG, planner, executor | active | primary | checked by Freeze A script | low | registered | contract_checked | medium | poi tests | POI metrics pending Plan B | smoke evidence exists | bounded POI matching | open until Freeze A script passes |
| algo.fusion.poi.geohash_neighbor_match.v1 | poi | bounded_supported | ToolRegistry, KG, planner, executor | active | primary | checked by Freeze A script | low | registered | contract_checked | medium | fusioncode poi tests | POI metrics pending Plan B | smoke evidence exists | geohash neighbor match only | open until Freeze A script passes |
| algo.transform.trajectory_to_road_candidate | road_future | reservation_only | ToolRegistry reserved, KG | blocked | none | blocked | P0 if executable | registered_reserved | rejected | medium | runtime boundary guard | none | none | extension example only | open until Freeze A script passes |
```

- [ ] **Step 5: Create Runtime Governance Matrix**

Create `docs/superpowers/specs/2026-06-10-runtime-governance-matrix.md`:

```markdown
# Runtime Governance Matrix

This matrix is the Freeze A governance snapshot. `gap_severity` uses `none`, `fail_soft`, or `unguarded`.

| contract_surface | gap_severity | allowed_states | blocked_states | current_behavior | target_behavior | rejection_code | fallback_behavior | audit_event | regression_test | freeze_line |
|---|---|---|---|---|---|---|---|---|---|---|
| KG seed and manifest | fail_soft | runtime_candidate, runtime_supported, bounded_supported | deprecated, reservation_only, selectable_now=false | mixed metadata existed before Plan A | all registered algorithms explicit | MISSING_RUNTIME_STATUS | fail closed | freeze_a_runtime_contract_check | test_kg_seed_manifest | Freeze A |
| ToolRegistry | none | registered executable tools | missing tools, reserved tools | registry miss raises | unchanged plus KG runtime check | UNKNOWN_TOOL, RESERVED_TOOL | no fallback | tool_contract_report | test_tool_registry | Freeze A |
| Validator | fail_soft | runtime-selectable algorithms and sources | deprecated, reserved, unknown, unselectable | marked invalid | rejected in enforce mode | VALIDATION_REJECTED | no execution | validation_rejected | test_workflow_validator | Freeze A |
| Planner fallback | unguarded | runtime-selectable patterns | patterns containing blocked algorithms | selected top KG pattern | skip blocked pattern | PATTERN_CONTAINS_BLOCKED_ALGORITHM | next allowed pattern | runtime_contract.skipped_fallback_patterns | test_planner_runtime_contract | Freeze A |
| Planner alternatives | fail_soft | runtime-selectable alternatives | deprecated, reserved, unknown | injected KG alternatives | filter alternatives | DEPRECATED_ALGORITHM | skip alternative | runtime_contract.skipped_alternatives | test_planner_runtime_contract | Freeze A |
| Executor primary dispatch | fail_soft | runtime-selectable registered tools | blocked KG state or missing registry | registry checked only | registry plus KG state checked | DEPRECATED_ALGORITHM, UNKNOWN_TOOL | healing only after safe failure | repair_records | test_repair_audit | Freeze A |
| Executor healing | fail_soft | runtime-selectable alternatives | blocked alternatives | try loop | filter and record skipped actions | alternative_algorithm_contract_rejected | transform insertion after skipped alternatives | repair_records.policy_source | test_repair_audit | Freeze A |
| Semantic parameter binding | unguarded | parameters in AlgorithmParameterSpec | unsupported params | task-kind based injection | spec-gated injection | PARAM_UNSUPPORTED_BY_ALGORITHM | skip param | source semantic contract evidence | test_semantic_parameter_binding | Freeze A |
| Recovery service | unguarded | stale runs with still-selectable plan algorithms | stale plans using blocked algorithms | phase/checkpoint/failure only | manual review on algorithm drift | DEPRECATED_ALGORITHM | no auto redispatch | algorithm_state | test_run_recovery_service | Freeze A |
| Freeze evidence | fail_soft | current seed/registry/settings | mutated seed or outputs | scattered commands | single script report | FREEZE_A_CONTRACT_FAILED | stop experiment session | freeze_a_runtime_contract_check.json | test_freeze_a_runtime_contract_check | Freeze A |
```

- [ ] **Step 6: Verify script and matrix tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_freeze_a_runtime_contract_check.py -q
.venv\Scripts\python.exe scripts\freeze_a_runtime_contract_check.py --json
```

Expected: pytest PASS and script JSON contains `"ok": true`.

- [ ] **Step 7: Commit**

Run:

```powershell
git add scripts/freeze_a_runtime_contract_check.py tests/test_freeze_a_runtime_contract_check.py docs/superpowers/specs/2026-06-10-algorithm-trust-matrix.md docs/superpowers/specs/2026-06-10-runtime-governance-matrix.md
git commit -m "test: add freeze a runtime contract regression"
```

---

### Task 10: Final Freeze A Verification

**Files:**
- Verify all files touched in Tasks 1-9.

- [ ] **Step 1: Run focused Plan A tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_runtime_contract_service.py tests/test_workflow_validator.py tests/test_toolspec_contract_enforcement.py tests/test_planner_runtime_contract.py tests/test_semantic_parameter_binding.py tests/test_repair_audit.py tests/test_repair_strategy.py tests/test_tool_registry.py tests/test_tool_contract_report_service.py tests/test_run_recovery_service.py tests/test_freeze_a_runtime_contract_check.py tests/test_kg_seed_manifest.py tests/test_check_kg_contract.py -q
```

Expected: PASS.

- [ ] **Step 2: Run existing regression slice from real-test risk areas**

Run:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_road_conflation_v7.py tests/test_waterways_conflation_v7.py tests/test_fusioncode_executor_handlers.py tests/test_fusioncode_kg_metadata.py tests/test_runtime_boundary_guards.py
```

Expected: PASS.

- [ ] **Step 3: Run Freeze A script and save evidence**

Run:

```powershell
$out = "docs/superpowers/specs/2026-06-10-freeze-a-runtime-contract-report.json"
.venv\Scripts\python.exe scripts\freeze_a_runtime_contract_check.py --json | Tee-Object -FilePath $out
```

Expected: output JSON contains `"ok": true`.

- [ ] **Step 4: Scan for stale deprecated algorithm exposure**

Run:

```powershell
rg -n "algo\.fusion\.road\.v1|algo\.fusion\.road\.safe|algo\.fusion\.water\.v1" agent services kg tests docs -S
```

Expected: matches are limited to deprecated KG metadata, negative tests, docs, and Freeze A matrices. No active workflow pattern, ToolRegistry executable handler, planner fallback allowlist, or executor healing allowlist should expose these IDs.

- [ ] **Step 5: Commit Freeze A evidence**

Run:

```powershell
git add docs/superpowers/specs/2026-06-10-freeze-a-runtime-contract-report.json docs/superpowers/specs/2026-06-10-algorithm-trust-matrix.md docs/superpowers/specs/2026-06-10-runtime-governance-matrix.md
git commit -m "docs: freeze runtime contract evidence"
```

- [ ] **Step 6: Final status check**

Run:

```powershell
git status --short
```

Expected: only user-owned unrelated files remain untracked or modified. Do not stage `scripts/run_optimized_training_fusion.py` unless the user explicitly asks.

---

## Self-Review Checklist

- Spec coverage:
  - Algorithm Trust Matrix: Task 9 creates and Task 10 verifies it.
  - Runtime Governance Matrix: Task 9 creates and Task 10 verifies it.
  - Deprecated/unselectable guardrails: Tasks 1-4 and 6-10.
  - `semantic_parameter_binding` audit path: Task 5.
  - Recovery and new state machine compatibility: Task 7.
  - Freeze regression carry-forward: Task 9 script and Task 10 evidence.
  - `healing_source_consistency` and decision-time repair evidence: Task 6.
- Unresolved-marker check:
  - No unresolved marker strings or unchecked design decisions remain in the plan text.
- Type consistency:
  - `RuntimeContractDecision.to_dict()` is used by planner, executor, recovery, and report service.
  - `ValidationReport.rejected` and `ValidationReport.enforcement_mode` are written by Validator and read by AgentRunService.
  - `RepairRecord.policy_source`, `policy_decision_basis`, `candidate_actions`, `selected_action`, and `skipped_actions` are Pydantic fields used by Executor tests.
- Scope discipline:
  - Plan A does not add new task families, remote data sources, benchmark AOIs, or quality metrics.
  - Plan A prepares the runtime contract base that Plan B and Plan C depend on.
