# FusionAgent Capability Consolidation Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不偏离“有界灾害响应场景下的 KG-grounded 矢量数据融合智能体运行时”这一主体目标的前提下，系统梳理 FusionAgent 已完成工作、应固化能力、创新定位、可借鉴方向、冗余或偏离部分，并形成后续实现与论文对齐的执行路线。

**Architecture:** 先把“系统是什么、已经做到什么、不能宣称什么、下一步只做什么”四层边界冻结，再把后续工作拆成 capability consolidation、evidence hardening、operatorization、research alignment 四条受约束子链。所有新增工作都必须以现有 runtime backbone 为中心，优先补 ToolSpec 契约、grounding evidence、unsupported-intent guard、telemetry、recovery 等能增强可信度的能力，而不是扩散到新的大主题。

**Tech Stack:** Markdown planning docs, existing README / operations docs / KG seed metadata / runtime services / pytest / eval artifacts / paper evidence freezes.

---

## Scope And Goal Lock

- 主体目标锁定为：`KG-grounded executable geospatial fusion runtime for bounded disaster-response workflows`
- 当前允许增强的是：
  - runtime contract clarity
  - capability consolidation
  - execution evidence
  - operator observability
  - bounded scenario reasoning
  - related-work and thesis alignment
- 当前不允许扩张的是：
  - 泛化成“全领域通用智能体”
  - 把 deferred seam 提前宣称为 runtime-supported
  - 把 bounded learning 说成 autonomous self-evolution
  - 为了“研究看起来更大”而增加不服务主线的新子系统

## Current-State Summary To Preserve

### Core Runtime Baseline

- 当前主线已经形成 `planner -> validator -> executor -> healing/replan -> writeback`
- 当前稳定对外口径已经覆盖 `building`、`road`、`water`、bounded `poi`
- 当前主证据契约已经包括 `run.json`、`plan.json`、`validation.json`、`audit.jsonl` 与 artifact bundle
- 当前已经具备 `task-driven` / `scenario-driven` 双入口
- 当前已经形成 no-UI operator workflow、inspection / compare API、scenario harness 与 evidence freeze 路径

### Main Differentiators Already Present

- 不把外部融合算法库当单一黑盒，而是拆成 KG 可调度算法原语
- 不只做 QA / RAG，而是直接产出可审计地理融合 artifact
- 不只做 planner demo，而是具备 validator、healing、replan、writeback、operator read surface
- 不只做论文式 reasoning chain，而是具备可运行的 input acquisition、artifact reuse、scenario registry

## Suspected Redundancy / Drift To Audit

### Redundancy Candidates

- artifact reuse 相关分支过多，但 claim 与 operator 价值未完全聚焦
- 规划文档、README、operations、spec freeze 之间存在重复叙述风险
- Benin 专项脚本族已快速增长，部分脚本可能是一次性研究工件而非 runtime 核心能力
- multi-source / raster / post-processing 能力横跨 runtime、bench、cleanup script、paper evidence，多处重复维护

### Drift Candidates

- trajectory-to-road seam 容易被误读为已执行能力
- durable learning 容易被误读为 autonomous learning
- scenario 层如果继续扩张，可能从“受约束任务编排”漂移成“泛灾害数字孪生推演系统”
- Benin national workflow 若继续堆脚本，可能从“验证 runtime capability”漂移成“专题数据工程仓库”
- front-end 若继续加页面而不补 operator evidence，可能偏离 no-UI maturity 主线

## Capability Freeze Recommendation

### Must Solidify As First-Class Runtime Capabilities

- `ToolSpec` registry and handler contract
- per-step KG grounding report
- unsupported-intent rejection with machine-readable reasons
- token / latency / phase telemetry
- checkpoint and stale-run recovery inspection
- bounded scenario-level evidence aggregation
- decomposed algorithm primitive registry with explicit parameter specs
- operator-facing inspection summary for run / scenario / evidence state

### Keep But Demote In Claim Priority

- generic artifact reuse variants
- broader scenario orchestration ergonomics
- front-end polish and richer visualization
- durable learning expansion
- trajectory-related reserved seams

### Explicitly Keep Out Of The Near-Term Core

- unbounded domain expansion
- fully autonomous tool invocation without contracts
- live event-feed integration claims
- full production HA / 7x24 claims
- trajectory-to-road executable ingestion

## Related-Work Positioning Guidance

### Innovation Claim To Keep

- 系统创新主张应聚焦于：`KG-grounded, contract-bounded, executable geospatial fusion runtime`
- 创新不应主打为“更强的通用 LLM reasoning”
- 论文叙事应强调：
  - 从自然语言 / scenario request 到可执行任务链
  - 从 KG candidate retrieval 到 contract-bounded planning
  - 从 execution 到 auditable evidence and artifacts
  - 从 run-level evidence 到 operator inspection and freezeable research proof

### Borrowing Directions To Adopt Carefully

- 借鉴 `CyVerACT`：schema-aware deterministic verification、structured error metadata、evaluator-optimizer loop
- 借鉴 `PathMind`：path prioritization、低噪声 retrieval、token-efficiency
- 借鉴 `UniAI-GraphRAG`：ontology-guided extraction、dual-channel retrieval、community/global reporting
- 借鉴 `OntoLLM`：ontology-grounded digression prevention、structured/unstructured dual handlers
- 借鉴 `Geo-Agent`：空间意图分层解析、图结构检索、自然语言 GIS interaction
- 借鉴地下站洪水级联论文：设施依赖、级联传播、scenario dependency reasoning

### Things Not To Copy Blindly

- 不要为了“像 GraphRAG”而把系统重心转成文本问答
- 不要为了“像 agentic workflow 论文”而引入高成本多轮 planner 自我对话
- 不要为了“像 ontology 系统”而引入与当前任务无关的大型本体工程
- 不要为了“像数字孪生”而把 scenario layer 扩成实时仿真平台

## Detailed Execution Plan

### Task 1: Freeze The Main Claim And Boundary Ledger

**Files:**
- Create: `docs/superpowers/specs/2026-05-06-capability-consolidation-review.md`
- Modify: `README.md`
- Modify: `docs/v2-operations.md`
- Modify: `docs/no-ui-agent-operations.md`
- Test: `tests/test_capability_claim_boundaries.py`

- [x] **Step 1: Write the failing boundary test**

```python
from pathlib import Path


def test_runtime_claims_do_not_exceed_locked_boundary() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    ops = Path("docs/v2-operations.md").read_text(encoding="utf-8")
    assert "trajectory-to-road remains reservation-only" in ops
    assert "registered tool contracts" in readme
    assert "unsupported-intent rejection" in readme
    assert "checkpoint recovery inspection" in readme
```

- [x] **Step 2: Run test to verify it fails if wording drifts**

Run: `python -m pytest -q tests/test_capability_claim_boundaries.py`
Expected: FAIL if the locked wording or next-step boundary is absent or inconsistent.

- [x] **Step 3: Write the boundary review document**

```markdown
# Capability Consolidation Review

## Locked Goal

- FusionAgent is a bounded, KG-grounded, executable geospatial fusion runtime.

## Forbidden Claim Drift

- no autonomous self-evolving learning claims
- no executable trajectory-to-road claim
- no 7x24 production HA claim
- no off-domain general-purpose agent claim
```

- [x] **Step 4: Align README and operations wording**

```markdown
Keep only one stable wording for:
- current runtime position
- stability contract
- Benin preparation boundary
- authorized next additions
```

- [x] **Step 5: Re-run boundary test**

Run: `python -m pytest -q tests/test_capability_claim_boundaries.py`
Expected: PASS

Task 1 execution note: added `tests/test_capability_claim_boundaries.py`, created `docs/superpowers/specs/2026-05-06-capability-consolidation-review.md`, tightened README and operations wording around registered tool contracts / unsupported-intent rejection / checkpoint recovery inspection, and demoted Benin multi-source or raster wording back to bounded preparation or reservation-only language where the stable runtime proof is not yet frozen.

### Task 2: Build A Canonical Capability Inventory

**Files:**
- Create: `docs/superpowers/specs/2026-05-06-capability-inventory.md`
- Create: `docs/superpowers/specs/2026-05-06-capability-matrix.json`
- Modify: `docs/fusioncode-algorithm-library.md`
- Test: `tests/test_capability_inventory_matrix.py`

- [x] **Step 1: Write the failing inventory test**

```python
import json
from pathlib import Path


def test_capability_matrix_tracks_status_and_evidence() -> None:
    payload = json.loads(Path("docs/superpowers/specs/2026-05-06-capability-matrix.json").read_text(encoding="utf-8"))
    assert "building" in payload["themes"]
    assert "core_next" in payload["status_vocab"]
    assert "evidence_contract" in payload["required_fields"]
```

- [x] **Step 2: Run test to verify matrix does not exist yet**

Run: `python -m pytest -q tests/test_capability_inventory_matrix.py`
Expected: FAIL with missing file or missing fields.

- [x] **Step 3: Create the canonical inventory artifacts**

```json
{
  "status_vocab": ["core", "core_next", "optional", "deferred"],
  "required_fields": ["capability_id", "theme", "status", "claim_state", "evidence_contract", "owner_files"],
  "themes": {
    "building": [],
    "road": [],
    "water": [],
    "poi": [],
    "operator": [],
    "evidence": []
  }
}
```

- [x] **Step 4: Map algorithm-library document to the same vocabulary**

```markdown
For each major capability, record:
- runtime status
- whether it is executable or reservation-only
- whether it is core, core_next, optional, or deferred
```

- [x] **Step 5: Re-run inventory test**

Run: `python -m pytest -q tests/test_capability_inventory_matrix.py`
Expected: PASS

### Task 3: Separate Core, Redundant, And Off-Axis Work

**Files:**
- Create: `docs/superpowers/specs/2026-05-06-redundancy-and-drift-ledger.md`
- Modify: `docs/superpowers/specs/2026-04-23-complexity-boundary-ledger.md`
- Test: `tests/test_redundancy_drift_ledger.py`

- [x] **Step 1: Write the failing redundancy test**

```python
from pathlib import Path


def test_redundancy_ledger_lists_action_for_each_drift_candidate() -> None:
    text = Path("docs/superpowers/specs/2026-05-06-redundancy-and-drift-ledger.md").read_text(encoding="utf-8")
    assert "artifact reuse branches" in text
    assert "Benin script sprawl" in text
    assert "trajectory-to-road wording" in text
    assert "Action:" in text
```

- [x] **Step 2: Run test to verify ledger is missing**

Run: `python -m pytest -q tests/test_redundancy_drift_ledger.py`
Expected: FAIL

- [x] **Step 3: Create the redundancy and drift ledger**

```markdown
## Drift Item
- Item: Benin script sprawl
- Risk: research scripts start replacing runtime interfaces
- Action: keep runtime entrypoints, mark one-off cleanup scripts as research utilities

## Drift Item
- Item: trajectory-to-road wording
- Risk: metadata seam misread as executable capability
- Action: preserve reservation-only wording everywhere
```

- [x] **Step 4: Link core-next vs optional decisions back into the boundary ledger**

```markdown
Update the ledger so each suspect subsystem gets one of:
- keep and strengthen
- keep but demote
- freeze
- archive / no new investment
```

- [x] **Step 5: Re-run redundancy test**

Run: `python -m pytest -q tests/test_redundancy_drift_ledger.py`
Expected: PASS

### Task 4: Define The Capability Consolidation Backlog

**Files:**
- Create: `docs/superpowers/specs/2026-05-06-consolidation-backlog.md`
- Modify: `docs/superpowers/specs/2026-04-23-system-next-improvement-review.md`
- Test: `tests/test_consolidation_backlog.py`

- [x] **Step 1: Write the failing backlog test**

```python
from pathlib import Path


def test_consolidation_backlog_prioritizes_core_next_work() -> None:
    text = Path("docs/superpowers/specs/2026-05-06-consolidation-backlog.md").read_text(encoding="utf-8")
    assert "P0" in text
    assert "ToolSpec registry" in text
    assert "KG grounding report" in text
    assert "unsupported-intent rejection" in text
    assert "telemetry" in text
    assert "checkpoint recovery inspection" in text
```

- [x] **Step 2: Run test to verify backlog is missing**

Run: `python -m pytest -q tests/test_consolidation_backlog.py`
Expected: FAIL

- [x] **Step 3: Create the prioritized consolidation backlog**

```markdown
## P0
- ToolSpec registry
- per-step grounding artifacts
- unsupported-intent guard
- run telemetry
- checkpoint / stale-run recovery scanner

## P1
- scenario dependency enrichment
- path prioritization for planner retrieval
- operator summary consolidation

## P2
- front-end evidence views
- richer ablation automation
- research utility cleanup
```

- [x] **Step 4: Update the challenge-to-evidence map with any missing proof hooks**

```markdown
Each P0 item must map to:
- tests
- runtime artifact
- inspection surface
- operations wording
```

- [x] **Step 5: Re-run backlog test**

Run: `python -m pytest -q tests/test_consolidation_backlog.py`
Expected: PASS

### Task 5: Produce A Related-Work Gap Matrix For The Paper

**Files:**
- Create: `docs/superpowers/specs/2026-05-06-related-work-gap-matrix.md`
- Create: `docs/superpowers/specs/2026-05-06-related-work-gap-matrix.json`
- Test: `tests/test_related_work_gap_matrix.py`

- [x] **Step 1: Write the failing related-work test**

```python
import json
from pathlib import Path


def test_related_work_matrix_covers_target_papers_and_gap_fields() -> None:
    payload = json.loads(Path("docs/superpowers/specs/2026-05-06-related-work-gap-matrix.json").read_text(encoding="utf-8"))
    assert "Geo-Agent" in payload["papers"]
    assert "CyVerACT" in payload["papers"]
    assert "OntoLLM" in payload["papers"]
    assert "PathMind" in payload["papers"]
    assert "UniAI-GraphRAG" in payload["papers"]
    assert "our_advantage" in payload["fields"]
    assert "borrow_direction" in payload["fields"]
```

- [x] **Step 2: Run test to verify matrix is missing**

Run: `python -m pytest -q tests/test_related_work_gap_matrix.py`
Expected: FAIL

- [x] **Step 3: Create the gap matrix artifacts**

```json
{
  "fields": ["paper", "problem_focus", "system_type", "our_advantage", "our_gap", "borrow_direction", "non_goal"],
  "papers": ["Geo-Agent", "CyVerACT", "OntoLLM", "PathMind", "UniAI-GraphRAG", "地下车站洪水脆弱性级联效应分析"]
}
```

- [x] **Step 4: Write paper-facing narrative guidance**

```markdown
For each paper:
- what it does well
- what FusionAgent already exceeds
- what FusionAgent still lacks
- what should be borrowed without changing the main thesis
```

- [x] **Step 5: Re-run related-work test**

Run: `python -m pytest -q tests/test_related_work_gap_matrix.py`
Expected: PASS

### Task 6: Define The Next Execution Sequence Without Scope Drift

**Files:**
- Create: `docs/superpowers/specs/2026-05-06-next-execution-sequence.md`
- Test: `tests/test_next_execution_sequence.py`

- [x] **Step 1: Write the failing sequence test**

```python
from pathlib import Path


def test_next_sequence_orders_work_from_core_next_to_optional() -> None:
    text = Path("docs/superpowers/specs/2026-05-06-next-execution-sequence.md").read_text(encoding="utf-8")
    assert "Stage 1" in text
    assert "Stage 2" in text
    assert "Stage 3" in text
    assert "Do not start P1 before P0 evidence closes" in text
```

- [x] **Step 2: Run test to verify sequence doc is missing**

Run: `python -m pytest -q tests/test_next_execution_sequence.py`
Expected: FAIL

- [x] **Step 3: Create the next execution sequence**

```markdown
## Stage 1: Claim Freeze And Capability Inventory
- close wording drift
- publish capability matrix
- publish redundancy / drift ledger

## Stage 2: Core-Next Runtime Hardening
- ToolSpec registry
- grounding report
- unsupported-intent guard
- telemetry
- recovery scanner

## Stage 3: Research And Operator Alignment
- ablation evidence
- related-work matrix
- operator summary hardening
```

- [x] **Step 4: Encode explicit stop conditions**

```markdown
Stop and re-review if:
- a task introduces new domain scope
- a task adds a claim without evidence
- a task duplicates an existing runtime interface with a one-off script
```

- [x] **Step 5: Re-run sequence test**

Run: `python -m pytest -q tests/test_next_execution_sequence.py`
Expected: PASS

## Review Checklist For This Plan

- 是否始终围绕“有界、可执行、KG-grounded、可审计”主线，而没有扩成泛化智能体工程
- 是否先补证据与契约，再扩功能
- 是否把已有冗余和偏离风险显式落成 ledger，而不是只在口头提醒
- 是否把相关工作借鉴限制在“增强主线”而不是“改写主线”
- 是否把后续任务按 `core next -> optional` 排序，而不是按“看起来更炫”排序

## Expected Deliverables From Executing This Plan

- 一套冻结后的 claim / boundary / capability inventory 文档
- 一套冗余与偏离审查 ledger
- 一套后续实现 backlog 与执行顺序
- 一套论文 related-work gap matrix
- 一组对应的轻量测试，防止文档与口径再次漂移

## Non-Goals Of This Plan

- 本计划不直接新增 runtime 功能实现
- 本计划不直接扩展新的主题切片
- 本计划不直接修改论文正文
- 本计划不把 research utility scripts 自动并入 runtime contract
