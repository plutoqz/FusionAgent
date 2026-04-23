# System Next Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `文档/问题、回答和改进方向.txt` into the next concrete engineering increment: enforceable algorithm tool contracts, KG-grounded plan evidence, unsupported-request control, runtime telemetry, recovery inspection, and KG ablation evidence.

**Architecture:** Preserve the existing `planner -> validator -> executor -> healing/replan -> writeback` spine. Add small, testable control layers around it: a `ToolSpec` registry for algorithm dispatch, a plan-grounding report for KG proof, a deterministic unsupported-intent guard, telemetry/checkpoint helpers for long-running runs, and an ablation harness for research evidence. Do not expand into arbitrary LLM tool calling, production SaaS guarantees, external disaster feeds, or final UI work in this increment.

**Tech Stack:** Python 3.9+, Pydantic, FastAPI, pytest, existing KG repository interfaces, existing `AgentRunService`, existing Celery worker entrypoint, JSON/Markdown evidence artifacts.

---

## Review Position

The document raises ten risks. The next system increment should answer them in this order:

1. **Defensibility first:** prove every plan step is grounded in KG context and that KG improves planning by ablation.
2. **Safety second:** turn algorithm handlers into registered tools with schemas and fail-closed dispatch.
3. **Scope control third:** reject off-domain or unsupported natural-language requests instead of silently ignoring them.
4. **Operations fourth:** add token/latency telemetry, step progress, and checkpoint-based recovery inspection.
5. **Complexity discipline last:** document what is core, optional, or deferred so the system is not marketed beyond evidence.

---

## File Map

Create:

- `agent/tooling.py`: `ToolSpec`, `ToolRegistry`, default executable algorithm tool contracts.
- `services/plan_grounding_service.py`: computes per-step KG grounding evidence from `WorkflowPlan.context`.
- `services/unsupported_intent_guard.py`: deterministic classifier for off-domain and unsupported schema-customization requests.
- `services/run_telemetry_service.py`: normalizes LLM usage and planning context-size metadata.
- `services/run_recovery_service.py`: scans persisted `runs/*/run.json` for stale nonterminal runs and classifies recovery actions.
- `scripts/eval_kg_ablation.py`: summarizes and optionally runs KG ablation variants.
- `docs/superpowers/specs/2026-04-23-system-next-improvement-review.md`: claim-to-evidence review document.
- `docs/superpowers/specs/2026-04-23-complexity-boundary-ledger.md`: core/optional/deferred complexity ledger.
- `tests/test_tool_registry.py`
- `tests/test_plan_grounding_service.py`
- `tests/test_unsupported_intent_guard.py`
- `tests/test_run_telemetry_service.py`
- `tests/test_run_recovery_service.py`
- `tests/test_eval_kg_ablation.py`

Modify:

- `schemas/agent.py`: add optional telemetry, grounding, checkpoint, and unsupported-intent models/fields.
- `agent/executor.py`: dispatch through `ToolRegistry` while preserving existing handlers.
- `agent/planner.py`: record planning source, elapsed time, context size, and provider usage when available.
- `agent/validator.py`: keep KG validation behavior and expose evidence codes where grounding/reporting needs them.
- `llm/providers/base.py`: expose optional `last_usage`.
- `llm/providers/openai_compatible.py`: capture response `usage` and model metadata.
- `llm/providers/mock_provider.py`: remain compatible with empty usage.
- `services/agent_run_service.py`: call guards, persist telemetry/grounding/checkpoints, and emit step-level progress events.
- `services/kg_path_trace_service.py`: include grounding report in inspection traces.
- `services/workflow_trace_service.py`: map step-level events into workflow trace.
- `api/routers/runs_v2.py`: reject unsupported requests and expose telemetry/grounding through existing responses.
- `worker/tasks.py`: preserve worker mode compatibility with checkpoint-aware status.
- `README.md`, `README.en.md`, `docs/v2-operations.md`: update claim boundaries and operation commands after tests pass.

---

## Task 1: Lock The Review Spec And Complexity Boundary

**Files:**
- Create: `docs/superpowers/specs/2026-04-23-system-next-improvement-review.md`
- Create: `docs/superpowers/specs/2026-04-23-complexity-boundary-ledger.md`
- Modify: `docs/v2-operations.md`

- [ ] **Step 1: Write the improvement review spec**

Create `docs/superpowers/specs/2026-04-23-system-next-improvement-review.md` with a table mapping each challenge from `文档/问题、回答和改进方向.txt` to evidence:

```markdown
# System Next Improvement Review

| Challenge | Required Evidence |
| --- | --- |
| Algorithms are registered tools, not free-form LLM calls | `ToolSpec` registry tests and executor dispatch tests |
| LLM planning is KG-grounded | per-step grounding report in `plan.json`, `audit.jsonl`, and inspection |
| KG improves accuracy | ablation JSON/Markdown with validity and success metrics |
| Unsupported requests are controlled | API/service guard tests for GDP, Chinese schema rename, and off-domain requests |
| Long-running runs are observable | planning telemetry, step-level audit events, and checkpoint metadata |
| Recovery is bounded and honest | stale-run scanner returns explicit recovery actions without claiming full 7x24 HA |
```

- [ ] **Step 2: Write the complexity boundary ledger**

Create `docs/superpowers/specs/2026-04-23-complexity-boundary-ledger.md`:

```markdown
# Complexity Boundary Ledger

| Area | Classification | Decision | Reason |
| --- | --- | --- | --- |
| planner -> validator -> executor -> healing/replan -> writeback | core | keep | main runtime claim |
| KG context and validator | core | keep | required for constrained planning |
| audit/run/plan/validation artifacts | core | keep | required for no-UI observability |
| ToolSpec registry | core next | add | converts handlers into enforceable contracts |
| plan grounding report | core next | add | proves KG evidence per step |
| unsupported request guard | core next | add | prevents silent misuse |
| step heartbeat and recovery scanner | core next | add | minimum credible long-run operations layer |
| trajectory-to-road seam | deferred | metadata only | not executable at runtime |
| durable learning | optional | simplify claims | bounded policy hints, not autonomous self-evolution |
| artifact reuse branches | optional | keep but document | useful, but not the core proof |
```

- [ ] **Step 3: Verify**

Run:

```powershell
Select-String -Path docs/superpowers/specs/2026-04-23-system-next-improvement-review.md -Pattern "Algorithms are registered tools"
Select-String -Path docs/superpowers/specs/2026-04-23-complexity-boundary-ledger.md -Pattern "ToolSpec registry"
```

Expected: both commands print matches.

---

## Task 2: Add ToolSpec Registry For Algorithm Dispatch

**Files:**
- Create: `agent/tooling.py`
- Modify: `agent/executor.py`
- Test: `tests/test_tool_registry.py`
- Test: `tests/test_worker_orchestration.py`

- [ ] **Step 1: Write failing registry tests**

Create `tests/test_tool_registry.py` with tests that assert `build_default_tool_registry()` includes `algo.fusion.building.v1`, `algo.fusion.building.safe`, `algo.fusion.road.v1`, `algo.fusion.road.safe`, `algo.fusion.water.v1`, and `algo.fusion.poi.v1`; each spec must expose `input_types`, `output_type`, `handler_name`, `timeout_seconds`, and fail-closed error policy.

- [ ] **Step 2: Implement `agent/tooling.py`**

Implement:

```python
@dataclass(frozen=True)
class ToolSpec:
    algorithm_id: str
    input_types: tuple[str, ...]
    output_type: str
    handler_name: str
    timeout_seconds: int = 600
    retry_count: int = 0
    error_policy: dict[str, str] = field(default_factory=lambda: {"missing_handler": "fail_closed"})
```

Also implement `ToolRegistry.get()`, `ToolRegistry.require()`, `ToolRegistry.list_algorithm_ids()`, and `build_default_tool_registry()`.

- [ ] **Step 3: Wire executor dispatch**

Modify `WorkflowExecutor` so `_execute_algorithm()` first requires a `ToolSpec`, then resolves `spec.handler_name` against existing handler functions. Unknown algorithms must fail before execution with a clear `ValueError`.

- [ ] **Step 4: Verify**

Run:

```powershell
python -m pytest -q tests/test_tool_registry.py tests/test_worker_orchestration.py tests/test_agent_run_service_enhancements.py
```

Expected: all pass.

---

## Task 3: Add Plan Grounding Report

**Files:**
- Create: `services/plan_grounding_service.py`
- Modify: `schemas/agent.py`
- Modify: `services/agent_run_service.py`
- Modify: `services/kg_path_trace_service.py`
- Test: `tests/test_plan_grounding_service.py`
- Test: `tests/test_kg_path_trace_service.py`

- [ ] **Step 1: Write failing grounding tests**

Create tests proving:

- algorithm in candidate pattern is grounded
- algorithm not in candidate pattern yields `ALGORITHM_NOT_IN_CANDIDATE_PATTERNS`
- data source not in retrieval yields `DATA_SOURCE_NOT_IN_RETRIEVAL`
- output type different from `intent.expected_output_type` yields `OUTPUT_TYPE_MISMATCH`

- [ ] **Step 2: Implement grounding service**

Create `build_plan_grounding_report(plan: WorkflowPlan) -> dict[str, Any]`.

Each step result must include:

- `step`
- `algorithm_id`
- `algorithm_grounded`
- `algorithm_known`
- `data_source_known`
- `output_type_matches_intent`
- `schema_policy_known`
- `pattern_ids`
- `issue_codes`
- `evidence_refs`

Top-level report must include `grounded`, `grounded_step_count`, `total_step_count`, `grounding_score`, and `steps`.

- [ ] **Step 3: Persist and expose report**

In `AgentRunService.run_planning_stage()`, write `plan.context["grounding_report"] = build_plan_grounding_report(plan)` before persisting `plan.json`. Add `grounded` and `grounding_score` to `plan_created` audit details. In `build_kg_path_trace(plan)`, include `grounding_report`.

- [ ] **Step 4: Verify**

Run:

```powershell
python -m pytest -q tests/test_plan_grounding_service.py tests/test_kg_path_trace_service.py tests/test_planner_context.py tests/test_api_v2_integration.py
```

Expected: all pass.

---

## Task 4: Add Unsupported Intent Guard

**Files:**
- Create: `services/unsupported_intent_guard.py`
- Modify: `schemas/agent.py`
- Modify: `api/routers/runs_v2.py`
- Modify: `services/agent_run_service.py`
- Test: `tests/test_unsupported_intent_guard.py`
- Test: `tests/test_api_v2_integration.py`

- [ ] **Step 1: Write failing guard tests**

Create tests for:

- `"请融合建筑数据，同时给我某国家GDP数据"` -> `OFF_DOMAIN_REQUEST`
- `"请把融合后属性表列名改成中文"` -> `UNSUPPORTED_OUTPUT_SCHEMA_CUSTOMIZATION`
- `"need building data for Nairobi"` -> no issues

- [ ] **Step 2: Implement deterministic classifier**

Create `classify_unsupported_intent(content: str, *, job_type: str) -> list[dict[str, str]]`.

Initial keyword groups:

- off-domain: `gdp`, `gross domestic product`, `国内生产总值`, `人口`
- unsupported schema customization: `中文列名`, `列名改成中文`, `属性表列名`, `rename columns`

- [ ] **Step 3: Wire API and service**

In `api/routers/runs_v2.py`, reject with:

```python
HTTPException(status_code=422, detail={"unsupported_intent": issues})
```

In `AgentRunService.create_run()`, raise `ValueError` for non-API callers.

- [ ] **Step 4: Verify**

Run:

```powershell
python -m pytest -q tests/test_unsupported_intent_guard.py tests/test_api_v2_integration.py tests/test_agent_run_service_enhancements.py
```

Expected: unsupported requests fail deterministically; normal requests are unchanged.

---

## Task 5: Capture LLM Usage, Planning Latency, And Context Size

**Files:**
- Create: `services/run_telemetry_service.py`
- Modify: `schemas/agent.py`
- Modify: `llm/providers/base.py`
- Modify: `llm/providers/openai_compatible.py`
- Modify: `agent/planner.py`
- Modify: `services/agent_run_service.py`
- Test: `tests/test_run_telemetry_service.py`
- Test: `tests/test_planner_context.py`

- [ ] **Step 1: Write telemetry tests**

Create tests for `estimate_json_size_bytes()` and `normalize_llm_usage()`. `normalize_llm_usage()` must accept OpenAI-style `{"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}`.

- [ ] **Step 2: Implement telemetry helpers**

Create:

```python
def estimate_json_size_bytes(payload: object) -> int:
    return len(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def normalize_llm_usage(raw: object) -> dict[str, int | None]:
    ...
```

- [ ] **Step 3: Capture provider usage**

Add optional `last_usage` to `LLMProvider`. In `OpenAICompatibleProvider.generate_workflow_plan()`, store response `usage` and model. Mock provider remains empty.

- [ ] **Step 4: Persist telemetry**

In `WorkflowPlanner.create_plan()` and `replan_from_error()`, store `planning_telemetry` in `plan.context`: elapsed ms, context size bytes, provider, model, and normalized token usage. In `AgentRunService`, copy it into `RunStatus` and `plan_created` audit details.

- [ ] **Step 5: Verify**

Run:

```powershell
python -m pytest -q tests/test_run_telemetry_service.py tests/test_planner_context.py tests/test_agent_state_models.py tests/test_agent_run_service_enhancements.py
```

Expected: all pass.

---

## Task 6: Add Step-Level Progress And Heartbeat Events

**Files:**
- Modify: `agent/executor.py`
- Modify: `services/agent_run_service.py`
- Modify: `services/workflow_trace_service.py`
- Test: `tests/test_agent_run_service_enhancements.py`
- Test: `tests/test_workflow_trace_service.py`

- [ ] **Step 1: Add executor callback**

Extend `WorkflowExecutor.execute_plan()` with optional `on_step_event`. Emit `started`, `succeeded`, and `failed` for executable tasks only.

- [ ] **Step 2: Wire status updates**

In `AgentRunService.run_execution_stage()`, pass a callback that writes audit events:

- `step_started`
- `step_succeeded`
- `step_failed`

Each event includes `algorithm_id`, `data_source_id`, and current step.

- [ ] **Step 3: Update trace mapping**

Add step events to `services/workflow_trace_service.py` so operator inspection can reconstruct progress beyond coarse phases.

- [ ] **Step 4: Verify**

Run:

```powershell
python -m pytest -q tests/test_agent_run_service_enhancements.py tests/test_workflow_trace_service.py
```

Expected: step-level events appear without changing terminal success/failure behavior.

---

## Task 7: Add Checkpoint-Based Pending Run Recovery Scanner

**Files:**
- Create: `services/run_recovery_service.py`
- Modify: `schemas/agent.py`
- Modify: `services/agent_run_service.py`
- Test: `tests/test_run_recovery_service.py`
- Test: `tests/test_worker_orchestration.py`

- [ ] **Step 1: Write stale-run scanner tests**

Create tests that write a stale `runs/<id>/run.json` with `phase="running"`, `updated_at`, and `checkpoint`, then assert `collect_recoverable_runs()` returns it.

- [ ] **Step 2: Implement scanner**

Create:

- `collect_recoverable_runs(runs_root: Path, stale_after_seconds: int) -> list[dict[str, Any]]`
- `classify_recovery_action(record: dict[str, Any]) -> str`

Initial actions:

- `redispatch_full_run`
- `redispatch_from_validation`
- `redispatch_from_execution`
- `mark_failed_requires_manual_review`

- [ ] **Step 3: Add status checkpoint fields**

Add `checkpoint: Dict[str, Any]` and `updated_at: Optional[str]` to `RunStatus`. Update them from `_update_status()` and stage methods.

- [ ] **Step 4: Expose safe inspection**

Add `AgentRunService.collect_recoverable_runs(stale_after_seconds=300)` but do not auto-resume by default. The first increment should make recovery inspectable before automatic replay.

- [ ] **Step 5: Verify**

Run:

```powershell
python -m pytest -q tests/test_run_recovery_service.py tests/test_agent_state_models.py tests/test_worker_orchestration.py
```

Expected: all pass.

---

## Task 8: Add KG Ablation Harness

**Files:**
- Create: `scripts/eval_kg_ablation.py`
- Test: `tests/test_eval_kg_ablation.py`
- Modify: `docs/superpowers/specs/2026-04-23-system-next-improvement-review.md`

- [ ] **Step 1: Write summary tests**

Create tests for `summarize_ablation_results(rows)` with variants `kg_llm` and `no_kg_llm`. Assert rates for planning validity, unknown algorithms, execution success, average grounding score, and case count.

- [ ] **Step 2: Implement summary core**

Create `scripts/eval_kg_ablation.py` with CLI args:

- `--input-json`
- `--output-json`
- `--output-markdown`

The summary must not invent live metrics; it only aggregates supplied rows.

- [ ] **Step 3: Add variant labels**

Supported labels:

- `kg_llm`: current full system
- `kg_top_pattern`: KG skeleton fallback
- `no_schema_hints`: removes data/source/parameter/schema hints
- `no_kg_llm`: experimental baseline, marked skipped unless fixture/provider rows are supplied

- [ ] **Step 4: Verify**

Run:

```powershell
python -m pytest -q tests/test_eval_kg_ablation.py tests/test_eval_harness.py
```

Expected: all pass.

---

## Task 9: Update Claims And Operations Docs

**Files:**
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/v2-operations.md`

- [ ] **Step 1: Add next-scope wording**

In both READMEs, add that the next engineering increment focuses on registered tool contracts, KG grounding reports, unsupported-intent rejection, token/latency telemetry, checkpoint recovery inspection, and ablation evidence.

- [ ] **Step 2: Keep boundaries explicit**

Do not claim:

- production 7x24 operation
- arbitrary off-domain requests
- final UI completion
- external event-feed integration
- live trajectory-to-road ingestion

- [ ] **Step 3: Add operation commands**

Add focused test command to `docs/v2-operations.md`:

```powershell
python -m pytest -q tests/test_tool_registry.py tests/test_plan_grounding_service.py tests/test_unsupported_intent_guard.py tests/test_run_telemetry_service.py tests/test_run_recovery_service.py tests/test_eval_kg_ablation.py
```

- [ ] **Step 4: Verify**

Run:

```powershell
Select-String -Path README.md -Pattern "工具契约","KG"
Select-String -Path README.en.md -Pattern "registered tool contracts","KG grounding"
Select-String -Path docs/v2-operations.md -Pattern "test_tool_registry.py"
```

Expected: matches appear.

---

## Final Verification

Run focused tests:

```powershell
python -m pytest -q `
  tests/test_tool_registry.py `
  tests/test_plan_grounding_service.py `
  tests/test_unsupported_intent_guard.py `
  tests/test_run_telemetry_service.py `
  tests/test_run_recovery_service.py `
  tests/test_eval_kg_ablation.py
```

Run integration tests:

```powershell
python -m pytest -q `
  tests/test_planner_context.py `
  tests/test_workflow_validator.py `
  tests/test_kg_path_trace_service.py `
  tests/test_agent_run_service_enhancements.py `
  tests/test_api_v2_integration.py `
  tests/test_worker_orchestration.py
```

Run full suite:

```powershell
python -m pytest -q
```

Generate ablation summary after fixture or live rows are available:

```powershell
python scripts/eval_kg_ablation.py `
  --input-json tmp/eval/kg-ablation-rows.json `
  --output-json tmp/eval/kg-ablation-summary.json `
  --output-markdown docs/superpowers/specs/2026-04-23-kg-ablation-summary.md
```

Expected final status:

```text
focused tests pass
integration tests pass
full pytest suite passes
plan.json includes grounding_report and planning_telemetry
audit.jsonl includes grounding/telemetry and step-level events
unsupported GDP/schema-rename requests fail with structured 422 at API level
ToolRegistry covers executable algorithms
recoverable stale runs can be listed for operator action
ablation summary computes metrics from rows and labels unsupported variants honestly
```

---

## Self-Review

- Spec coverage: Covers all ten questions in `文档/问题、回答和改进方向.txt`.
- Scope control: Does not claim production-grade HA; recovery starts as inspectable operator action.
- Risk order: Grounding, guard, and telemetry land before runtime dispatch/recovery changes.
- Type consistency: Run-visible fields go in `schemas/agent.py`; pure computations stay in `services/*`.
- Test discipline: Every new service starts with isolated pytest coverage before integration wiring.
