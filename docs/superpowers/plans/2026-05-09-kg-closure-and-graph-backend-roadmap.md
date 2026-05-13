# KG Closure And Graph Backend Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不继续扩大系统边界的前提下，先把 FusionAgent 的知识图谱从“代码定义完整但默认 live Neo4j 漂移严重、关键约束未完全落地”补齐为“默认运行态可复现、可校验、可支撑论文消融实验”的稳定基线，并给出是否迁出 Neo4j 的工程决策。

**Completion Status:** Closed on 2026-05-12. Task 1-6 are implemented and re-verified under the default Neo4j backend. Fresh gate evidence is recorded in [2026-05-09-kg-closure-gates.md](/E:/vscode/fusionAgent/docs/superpowers/specs/2026-05-09-kg-closure-gates.md) and [2026-05-10-kg-gates-evidence-summary.md](/E:/vscode/fusionAgent/docs/superpowers/specs/2026-05-10-kg-gates-evidence-summary.md).

**Architecture:** 先做 `P0: KG 闭环`，把 seed、bootstrap、默认 Neo4j、planner/retriever/validator、artifact schema gate 串成一条一致的约束链；再做 `P0.5: 项目隔离`，优先用独立实例或独立端口解决社区版单数据库带来的混图问题；只有在上述 gate 全部通过后，才允许进入 `P1: 图数据库替代 spike`。对论文时间线而言，必须优先保证“默认后端下的 KG 与实验结论一致”，而不是先迁库。

**Tech Stack:** Python, Neo4j driver, existing `kg/*` repository layer, `agent/*`, `services/*`, `scripts/start_local.py`, `scripts/inspect_neo4j_state.py`, `pytest`, local runtime env from `依赖.txt`, optional Docker or dedicated Neo4j DBMS instance.

---

## Current Baseline

The drift snapshot in this section is the historical starting state that motivated the work. Use the completion status and linked gate docs above for the current verified runtime state.

### Live KG Drift Snapshot

当前代码种子定义的静态 KG 本体规模为：

- `DataType = 27`
- `Task = 10`
- `Algorithm = 33`
- `AlgorithmParameterSpec = 44`
- `DataSource = 22`
- `ScenarioProfile = 4`
- `OutputSchemaPolicy = 4`
- `WorkflowPattern = 14`

当前默认 local Neo4j（`Neo4j Community 5.23.0`, home database = `zmn`）的 live managed inventory 只有：

- managed nodes = `38`
- `Algorithm = 6`
- `DataType = 5`
- `DataSource = 3`
- `WorkflowPattern = 4`
- `StepTemplate = 4`
- `WorkflowInstance = 8`
- `DurableLearningRecord = 8`
- `Task = 0`
- `ScenarioProfile = 0`
- `AlgorithmParameterSpec = 0`
- `OutputSchemaPolicy = 0`

这意味着现在的默认运行态已经不是“KG 不够丰富”这么简单，而是：

1. **默认 KG 后端与代码本体不一致**
2. **water / poi / decomposed workflow 在默认 live Neo4j 下并不完整可见**
3. **后续论文消融实验如果继续基于这个漂移状态推进，证据不可信**

### Root Cause

关键根因已经定位为：

- `kg/bootstrap.py` 中的 `ensure_bootstrap_data()` 只检查是否存在 managed `WorkflowPattern`
- 一旦已有少量 pattern，就会跳过后续 seed
- 因此新增的 `Task / ScenarioProfile / ParameterSpec / OutputSchemaPolicy / patterns` 不会自动补齐

### Decision Summary

对当前系统的总判断保持如下：

1. KG 已经是真正参与规划、校验、learning writeback 的运行时约束层，不是展示性图谱。
2. 真正的论文阻塞点不是“再加节点”，而是“让默认 live KG 和代码定义严格同步，并把关键节点约束落到执行结果”。
3. **近期不建议先迁库。** 先修 `P0 KG 闭环`，再决定是否迁库，才能避免把漂移问题错误归因到数据库产品本身。

## Execution Priority

### Must Finish Before Any New Thesis Ablation

- `P0.1` live Neo4j 与 seed inventory 一致
- `P0.2` default Neo4j backend 下 `building / road / water / poi` 至少完成 contract smoke
- `P0.3` `ScenarioProfile / ParameterSpec / OutputSchemaPolicy` 从 retrieval metadata 提升为稳定生效约束
- `P0.4` 输出 artifact 的 schema gate 与 KG policy 对齐
- `P0.5` 项目隔离策略固定，避免后续 run 与其他项目混图

### Explicitly Deferred Until P0 Passes

- NebulaGraph / GDB / PolarDB Graph 正式迁移
- 更换 repository query dialect
- 重写 full-text search 与 shortest path 适配
- 大规模 ontology 扩展

## Backend Recommendation

### Recommended Route For The Current Paper Timeline

**推荐路线：继续使用 Neo4j，但先补齐闭环，不立即迁库。**

原因：

1. 当前最大风险来自 **seed/live drift**，不是来自 Neo4j 查询能力本身。
2. 你的代码已经深度依赖 `Neo4jKGRepository`、Bolt 驱动、Cypher 标签查询、full-text query、shortest path 与现有 bootstrap 逻辑。
3. 先把默认 live KG 修正为可靠基线，能直接支撑论文消融；迁库会同时引入“数据库差异”和“KG 语义补齐”两个变量，难以解释实验结果。

### Isolation Recommendation

优先级从高到低如下：

1. **首选：每个项目独立 Neo4j 实例或独立端口**
   - 最少改代码
   - 直接解决“一个数据库里混别的项目图”的可视与运维问题
   - 与论文时间线最兼容
2. **次选：保留同一实例，但强化 `graphNamespace` 与 startup gate**
   - 需要补代码查询过滤
   - 不能替代独立实例的物理隔离
3. **最后才是迁库**
   - 成本和不确定性显著更高

### Replacement Feasibility

#### Option A: Neo4j Continue + Dedicated Instance

- 可行性：`高`
- 工作量：`小到中`
- 风险：`低`
- 适用条件：你主要是想解决社区版单数据库和项目混图问题，而不是 Neo4j 功能缺失

#### Option B: NebulaGraph

- 可行性：`中`
- 工作量：`大`
- 风险：`高`
- 关键原因：
  - 官方文档说明 `nGQL` 仅兼容部分 openCypher，且**不计划兼容 Bolt Protocol**
  - full-text search 依赖 **Elasticsearch + Listener**
  - path 查询、DDL、driver、query 语义都要重写
  - 更像“重做 repository 适配层 + 运维层”，不是替换一个连接串

#### Option C: Alibaba Cloud GDB

- 可行性：`中`
- 工作量：`中到大`
- 风险：`中到高`
- 关键原因：
  - 官方文档说明支持 `bolt-v3`，表面上比 NebulaGraph 更接近现有栈
  - 但 **不支持多 Label**，而当前代码普遍依赖 `:EntityType:FusionAgentManaged` 双标签模式
  - **不支持 `USE` 多图语义**
  - 多个 Cypher 4.x 特性不支持，兼容性不是“原样可跑”
  - GDB FAQ 说明索引由系统自动维护，当前 bootstrap 的显式 schema/DDL 路径需要重设计

#### Option D: PolarDB Graph (Apache AGE)

- 可行性：`中`
- 工作量：`大`
- 风险：`中到高`
- 关键原因：
  - 官方文档说明底层是 PostgreSQL `age` 扩展，Cypher 是通过 `cypher()` SQL 函数执行
  - 这意味着你不再使用 Neo4j/Bolt 模式，而要改成 PostgreSQL 连接 + SQL wrapper
  - repository、driver、query execution、测试基建都会重写
  - 更适合你明确需要“图 + 关系库同集群”的长期架构，而不是当前的论文止血阶段

## Acceptance Gates

在宣布“KG gap 已补齐，可以继续做更新和论文消融”之前，必须全部满足：

1. `python scripts/inspect_neo4j_state.py --managed-only` 输出的静态实体计数与 `kg.seed` 一致
2. `ScenarioProfile / ParameterSpec / OutputSchemaPolicy` 在 planner context、validator、artifact gate 中都可见且生效
3. `task_driven_auto` 的 `building / road / water / poi` 至少各有 1 条 Neo4j backend smoke 证据
4. 论文 manifest 中任意一条基线 case 可以在默认 Neo4j backend 下复现
5. 项目隔离方案固定，不再和其他项目共用同一个图实例视图

## Detailed Execution Plan

### Task 1: Make Bootstrap Completeness Explicit And Testable

**Files:**
- Modify: `kg/bootstrap.py`
- Modify: `scripts/inspect_neo4j_state.py`
- Modify: `tests/test_neo4j_bootstrap.py`
- Create: `tests/test_kg_seed_inventory.py`

- [x] **Step 1: Write the failing seed inventory test**

```python
from kg.seed import (
    ALGORITHMS,
    DATA_SOURCES,
    DATA_TYPES,
    OUTPUT_SCHEMA_POLICIES,
    PARAMETER_SPECS,
    SCENARIO_PROFILES,
    TASKS,
    WORKFLOW_PATTERNS,
)


def test_seed_inventory_matches_expected_static_counts() -> None:
    assert len(DATA_TYPES) == 27
    assert len(TASKS) == 10
    assert len(ALGORITHMS) == 33
    assert sum(len(items) for items in PARAMETER_SPECS.values()) == 44
    assert len(DATA_SOURCES) == 22
    assert len(SCENARIO_PROFILES) == 4
    assert len(OUTPUT_SCHEMA_POLICIES) == 4
    assert len(WORKFLOW_PATTERNS) == 14
```

- [x] **Step 2: Run the focused inventory tests**

Run: `python -m pytest -q tests/test_kg_seed_inventory.py tests/test_neo4j_bootstrap.py`

Expected: current tests pass only on generator parity, but there is still no completeness check for live Neo4j.

- [x] **Step 3: Replace "pattern exists => already seeded" with inventory-based completeness**

```python
def expected_seed_inventory() -> dict[str, int]:
    return {
        "DataType": len(DATA_TYPES),
        "Task": len(TASKS),
        "Algorithm": len(ALGORITHMS),
        "AlgorithmParameterSpec": sum(len(items) for items in PARAMETER_SPECS.values()),
        "DataSource": len(DATA_SOURCES),
        "ScenarioProfile": len(SCENARIO_PROFILES),
        "OutputSchemaPolicy": len(OUTPUT_SCHEMA_POLICIES),
        "WorkflowPattern": len(WORKFLOW_PATTERNS),
    }


def ensure_bootstrap_data(...):
    live = inspect_graph_state(..., managed_only=True)
    live_counts = {item["label"]: item["count"] for item in live["label_counts"]}
    expected = expected_seed_inventory()
    missing = {label: expected[label] for label in expected if live_counts.get(label, 0) < expected[label]}
    if not missing:
        return False
    apply_bootstrap_cypher(...)
    return True
```

- [x] **Step 4: Extend inspect output so drift is visible in one command**

```python
report = {
    **resolved,
    "managed_label": MANAGED_LABEL,
    "inventory": inventory,
    "expected_seed_inventory": expected_seed_inventory(),
    "missing_seed_labels": missing_seed_labels,
}
```

- [x] **Step 5: Add regression tests for partial-live reseed**

```python
def test_ensure_bootstrap_data_applies_seed_when_task_and_policy_nodes_are_missing(monkeypatch) -> None:
    # Fake live graph still has WorkflowPattern, but Task/ScenarioProfile/OutputSchemaPolicy are missing.
    # Expected: ensure_bootstrap_data() returns True and applies bootstrap cypher.
    ...
```

- [x] **Step 6: Re-run the focused tests**

Run: `python -m pytest -q tests/test_kg_seed_inventory.py tests/test_neo4j_bootstrap.py`

Expected: PASS

### Task 2: Add A First-Class KG Contract Check For Local Runtime

**Files:**
- Create: `scripts/check_kg_contract.py`
- Modify: `scripts/start_local.py`
- Modify: `tests/test_local_runtime.py`
- Create: `tests/test_check_kg_contract.py`

- [x] **Step 1: Write the failing contract-script test**

```python
from kg.bootstrap import expected_seed_inventory


def test_expected_seed_inventory_exposes_static_kg_contract() -> None:
    inventory = expected_seed_inventory()
    assert inventory["Task"] == 10
    assert inventory["ScenarioProfile"] == 4
    assert inventory["OutputSchemaPolicy"] == 4
```

- [x] **Step 2: Implement a reusable local contract script**

```python
# scripts/check_kg_contract.py
summary = {
    "expected_seed_inventory": expected_seed_inventory(),
    "live_inventory": inspect_graph_state(..., managed_only=True),
    "ok": missing == {},
}
if not summary["ok"]:
    raise SystemExit(1)
```

- [x] **Step 3: Wire the contract check into local startup**

```python
neo4j_summary = _prepare_neo4j(...)
if not neo4j_summary.get("kg_contract_ok", False):
    raise RuntimeError("Neo4j managed graph does not satisfy the FusionAgent KG contract.")
```

- [x] **Step 4: Verify runtime check-only path**

Run: `python scripts/start_local.py --check-only`

Expected: startup prints Neo4j edition, isolation mode, bootstrap status, and explicit KG contract pass/fail.

- [x] **Step 5: Run focused tests**

Run: `python -m pytest -q tests/test_check_kg_contract.py tests/test_local_runtime.py`

Expected: PASS

### Task 3: Promote ScenarioProfile And OutputSchemaPolicy From Metadata To Active Constraints

**Files:**
- Modify: `agent/retriever.py`
- Modify: `agent/planner.py`
- Modify: `agent/validator.py`
- Modify: `services/agent_run_service.py`
- Modify: `services/artifact_evaluation_service.py`
- Modify: `tests/test_planner_context.py`
- Modify: `tests/test_workflow_validator.py`
- Modify: `tests/test_agent_run_service_enhancements.py`

- [x] **Step 1: Write failing tests for profile activation and schema enforcement**

```python
def test_planner_context_selects_effective_scenario_profile_id() -> None:
    ...
    assert plan.context["intent"]["effective_scenario_profile_id"] == "scenario.flood.default"


def test_artifact_evaluation_fails_when_required_output_fields_are_missing(tmp_path: Path) -> None:
    metrics = evaluate_vector_artifact(shp_path, required_fields=["geometry", "confidence"])
    assert metrics["artifact_validity"] is False
    assert metrics["missing_fields"] == ["confidence"]
```

- [x] **Step 2: Persist an effective scenario profile into plan context**

```python
intent["effective_scenario_profile_id"] = selected_profile.profile_id if selected_profile else None
intent["effective_activated_tasks"] = selected_profile.activated_tasks if selected_profile else []
intent["effective_preferred_output_fields"] = selected_profile.preferred_output_fields if selected_profile else []
```

- [x] **Step 3: Add validator checks that use active scenario/profile semantics**

```python
if effective_tasks and f"task.{job_type}.fusion" not in effective_tasks:
    issues.append(
        ValidationIssue(
            code="SCENARIO_PROFILE_TASK_MISMATCH",
            message="Selected ScenarioProfile does not activate the requested task bundle.",
        )
    )
```

- [x] **Step 4: Turn OutputSchemaPolicy into a post-execution gate**

```python
policy = self.kg_repo.get_output_schema_policy(output_data_type)
metrics = evaluate_vector_artifact(shp_path, required_fields=policy.required_fields if policy else ["geometry"])
if not metrics["artifact_validity"]:
    raise RuntimeError(
        f"Artifact schema validation failed: missing_fields={metrics['missing_fields']}"
    )
```

- [x] **Step 5: Record explicit audit/decision evidence**

```python
event_kind="output_schema_validated"
event_message=f"Artifact validated against policy {policy.policy_id}."
```

- [x] **Step 6: Re-run focused runtime tests**

Run: `python -m pytest -q tests/test_planner_context.py tests/test_workflow_validator.py tests/test_agent_run_service_enhancements.py`

Expected: PASS

### Task 4: Keep ParameterSpec And Decomposed Workflow Truly Reachable Under Neo4j Backend

**Files:**
- Modify: `kg/neo4j_repository.py`
- Modify: `agent/retriever.py`
- Modify: `tests/test_neo4j_repository.py`
- Modify: `tests/test_planner_context.py`

- [x] **Step 1: Write a failing repository test for full static retrieval**

```python
def test_build_context_includes_parameter_specs_and_decomposed_algorithms_from_neo4j_fake_driver() -> None:
    ...
    assert "algo.match.building.v8_component_solver.v1" in context.algorithms
    assert context.parameter_specs["algo.match.building.v8_component_solver.v1"]
```

- [x] **Step 2: Ensure candidate build_context is not accidentally narrowed to stale top-pattern slices**

```python
for algo in self.algorithms.values():
    if algo.task_type != "transform":
        continue
    ...
```

- [x] **Step 3: Add Neo4j-backed context assertions for water / poi / decomposed slices**

```python
assert "wp.water.fusioncode.line_and_polygon.v1" in pattern_ids
assert "wp.poi.fusioncode.geohash_priority.v1" in pattern_ids
assert "wp.building.drs4br.decomposed.v1" in building_pattern_ids
```

- [x] **Step 4: Re-run focused tests**

Run: `python -m pytest -q tests/test_neo4j_repository.py tests/test_planner_context.py`

Expected: PASS

### Task 5: Fix Project Isolation Without Immediate Migration

**Files:**
- Modify: `utils/local_runtime.py`
- Modify: `kg/factory.py`
- Modify: `kg/bootstrap.py`
- Modify: `kg/neo4j_repository.py`
- Modify: `tests/test_local_runtime.py`
- Modify: `tests/test_neo4j_repository.py`
- Modify: `README.md`
- Modify: `docs/v2-operations.md`

- [x] **Step 1: Write failing env/config tests**

```python
def test_local_dependency_config_reads_optional_graph_namespace(tmp_path: Path) -> None:
    dependency_file.write_text("图命名空间:fusionagent\\n...", encoding="utf-8")
    config = read_local_dependency_config(dependency_file)
    assert config.graph_namespace == "fusionagent"
```

- [x] **Step 2: Add configurable graph namespace**

```python
graph_namespace = (
    _search_optional(r"图命名空间\\s*[:：]\\s*([^\\s]+)", text)
    or _search_optional(r"GEOFUSION_GRAPH_NAMESPACE\\s*[:：=]\\s*([^\\s]+)", text)
    or "fusionagent"
)
```

- [x] **Step 3: Filter all Neo4j reads/writes by namespace as a second guard**

```python
MATCH (wp:WorkflowPattern:FusionAgentManaged)
WHERE wp.graphNamespace = $graph_namespace
```

- [x] **Step 4: Document the operational recommendation as dedicated instance first**

```markdown
Recommended local isolation:
1. one Neo4j DBMS instance per project, each on its own port
2. keep `GEOFUSION_GRAPH_NAMESPACE=fusionagent` as an application-level guard
3. do not use a shared miscellaneous graph for paper evidence runs
```

- [x] **Step 5: Re-run config and repository tests**

Run: `python -m pytest -q tests/test_local_runtime.py tests/test_neo4j_repository.py`

Expected: PASS

### Task 6: Freeze The Paper-Ready KG Gates Before Any New Ablation

**Files:**
- Modify: `docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json`
- Modify: `docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md`
- Modify: `README.md`
- Create: `docs/superpowers/specs/2026-05-09-kg-closure-gates.md`

- [x] **Step 1: Add a KG closure gate document**

```markdown
Required before any new ablation:
- live managed inventory matches seed inventory
- Neo4j backend smoke passes for building/road/water/poi
- output schema gate is active
- project isolation mode is fixed and documented
```

- [x] **Step 2: Run the local gate commands**

Run:

```powershell
python scripts/start_local.py --check-only
python scripts/inspect_neo4j_state.py --managed-only
python scripts/check_kg_contract.py
```

Expected:

- `KG contract: PASS`
- managed static labels equal seed counts
- no missing `Task / ScenarioProfile / AlgorithmParameterSpec / OutputSchemaPolicy`

- [x] **Step 3: Run a bounded Neo4j smoke set**

Run:

```powershell
python scripts/smoke_agentic_region.py --base-url http://127.0.0.1:8012 --job-type building --query "need building data for Gitega city, Burundi" --timeout 1200 --output-json runs/smoke-building-gitega-city-inspection-8012.json
python scripts/smoke_agentic_region.py --base-url http://127.0.0.1:8012 --job-type road --query "need road data for Gilgit city, Pakistan" --timeout 1200 --output-json runs/smoke-road-gilgit-city-inspection-8012.json
python scripts/smoke_agentic_region.py --base-url http://127.0.0.1:8012 --job-type water --query "need water polygons for Nairobi, Kenya" --timeout 1200 --output-json runs/smoke-water-nairobi-inspection-8012.json
python scripts/smoke_agentic_region.py --base-url http://127.0.0.1:8012 --job-type poi --query "show hospitals in Nairobi, Kenya" --timeout 1200 --output-json runs/smoke-poi-nairobi-inspection-8012.json
```

Expected: four successful runs with complete `run.json`, `plan.json`, `validation.json`, `audit.jsonl`.

- [x] **Step 4: Re-run one paper manifest case under default Neo4j backend**

Run:

```powershell
python scripts/eval_harness.py --manifest docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json --case building_gitega_micro_msft_agent --base-url http://127.0.0.1:8012 --timeout 1200 --output-json docs/superpowers/specs/2026-05-12-building-gitega-micro-msft-neo4j-baseline-8012.json
```

Observed:

- `all_passed = true`
- `run_id = 07ebbedd856b43a09ad3bf62ee55a440`
- fresh summary saved to [2026-05-12-building-gitega-micro-msft-neo4j-baseline-8012.json](/E:/vscode/fusionAgent/docs/superpowers/specs/2026-05-12-building-gitega-micro-msft-neo4j-baseline-8012.json)

## Conditional Migration Spike Plan

只有在 Task 1-6 全部通过后，才允许进入迁库 spike。

### Spike A: NebulaGraph Compatibility Spike

**Files:**
- Create: `kg/nebula_repository.py`
- Modify: `kg/repository.py`
- Modify: `kg/factory.py`
- Create: `tests/test_nebula_repository_contract.py`
- Create: `docs/superpowers/specs/2026-05-09-nebula-spike-notes.md`

**Scope:**

- 重写 driver 接入，不再使用 Bolt
- 重写 full-text search
- 重写 shortest path 与 schema bootstrap
- 只验证 `list_* / get_* / search_knowledge / find_transform_path / build_context`

**Stop Rule:** 任一核心 query 语义无法在一周内达到与 Neo4j contract 等价，就终止迁移。

### Spike B: Alibaba Cloud GDB Compatibility Spike

**Files:**
- Create: `kg/gdb_repository.py`
- Modify: `kg/factory.py`
- Create: `tests/test_gdb_repository_contract.py`
- Create: `docs/superpowers/specs/2026-05-09-gdb-spike-notes.md`

**Scope:**

- 先验证单 label 模型是否可承载当前 `FusionAgentManaged + EntityType` 双标签写法
- 如果不行，评估改写为 `label=EntityType` + `managed=true` 属性过滤
- 验证 Bolt v3 与现有 Python driver 的最小连接可行性

**Stop Rule:** 如果 dual-label 改写会波及全部 Cypher 查询、测试和 bootstrap 约束，则终止迁移并回到 Neo4j dedicated instance 路线。

### Spike C: PolarDB Graph / Apache AGE Compatibility Spike

**Files:**
- Create: `kg/polardb_age_repository.py`
- Modify: `kg/factory.py`
- Create: `tests/test_polardb_age_repository_contract.py`
- Create: `docs/superpowers/specs/2026-05-09-polardb-age-spike-notes.md`

**Scope:**

- 将一个最小的 repository contract 改写为 PostgreSQL `cypher()` 访问模式
- 只验证是否能完成静态 seed 读取与 shortest-path contract

**Stop Rule:** 如果 query adapter 与现有 Neo4j contract 无法保持可维护的一一对应，则不进入正式迁移。

## Engineering Recommendation

### Final Recommendation

按优先级执行：

1. **先完成 Task 1-6，不迁库**
2. **运行时隔离优先采用独立 Neo4j 实例/端口**
3. **保留 `graphNamespace` 作为应用级二次防护**
4. **只有当 P0 gate 全部通过后，再做条件性迁移 spike**

### Workload And Risk Estimate

- `P0 KG 闭环`: `中等工作量 / 低到中风险 / 高收益`
- `P0.5 项目隔离`: `小到中工作量 / 低风险 / 直接止血`
- `NebulaGraph 迁移`: `大工作量 / 高风险`
- `Alibaba Cloud GDB 迁移`: `中到大工作量 / 中到高风险`
- `PolarDB Graph / AGE 迁移`: `大工作量 / 中到高风险`

### Paper-Time Decision Rule

如果目标是“尽快恢复后续更新、继续论文消融、保证实验解释性”，则：

- **现在不要先迁库**
- **先让默认 Neo4j 成为可信 truth source**
- **把数据库替代放到 P0 完成后的 spike，而不是放到论文主干之前**

## Self Review

- Spec coverage: 本计划覆盖了 KG 完整性、运行时作用与地位差距、默认 Neo4j 漂移修复、项目隔离、论文 gate，以及 NebulaGraph / 阿里云图数据库 / PolarDB Graph 的替代路线。
- Placeholder scan: 无 `TODO/TBD/implement later` 类型占位；所有任务都给出了文件、测试或命令。
- Type consistency: 计划统一围绕现有 `KGRepository`, `Neo4jKGRepository`, `PlanningContextBuilder`, `WorkflowValidator`, `AgentRunService` 与现有脚本入口，不引入新的主干抽象名称漂移。

Plan complete and saved to `docs/superpowers/plans/2026-05-09-kg-closure-and-graph-backend-roadmap.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
