# FusionAgent Thesis Research Design Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 形成一份面向硕士论文的主计划，明确 FusionAgent 的研究问题、创新点定位、实验设计、对照与消融矩阵、Benin 规模验证角色、论文章节结构与时间安排，使现有工程基础能够转化为可答辩的研究证据。

**Architecture:** 本计划不再停留在 capability consolidation，而是把现有 runtime 资产重组为一个“研究问题 → 系统主张 → 实验验证 → 论文叙事”的闭环。主线围绕 `KG-decomposed algorithm primitives + contract-bounded planning/execution + auditable evidence contract` 三个研究主张展开；工程增强项如 ToolSpec、telemetry、recovery 只作为可信度支撑，不作为论文主创新点。

**Tech Stack:** Markdown research planning docs, existing runtime and evaluation harness, pytest-based evidence guards, paper evidence freezes, Benin multi-source building workflow, related-work PDF set under Zotero storage.

---

## Thesis Position Lock

- 论文对象不是“通用大模型智能体”，而是：`面向有界灾害响应场景的 KG-grounded 矢量数据融合智能体运行时`
- 论文核心贡献不是“新增前端”或“运维增强项”，而是：
  - `KG-decomposed algorithm primitives`
  - `contract-bounded planning and execution with healing`
  - `auditable geospatial evidence contract`
- 工程增强项只承担 supporting evidence 角色：
  - `ToolSpec registry`
  - `grounding report`
  - `unsupported-intent rejection`
  - `telemetry`
  - `checkpoint recovery inspection`

## Research Problem Statement

### Problem P1

现有 geospatial LLM / multi-agent / GraphRAG 工作大多停留在：

- GeoQA
- data discovery
- spatial query generation
- code generation for GIS analysis
- hazard text understanding

但缺少一个能够把 **算法、数据、参数、约束、执行与证据** 统一纳入同一受约束运行时的系统。

### Problem P2

现有方法往往存在以下断裂：

- KG 只参与检索，不参与可执行调度
- planner 能生成步骤，但无法确保算法可执行、参数受限、错误可修复
- 输出是答案、查询语句或代码片段，而不是可审计的地理融合 artifact
- 缺少 run-level evidence contract，难以支撑 operator inspection 与论文证据冻结

### Problem P3

在真实大尺度地理融合任务中，尤其是多源建筑物融合与灾害响应任务，系统不仅要“答对”，还要：

- 能拿到正确输入
- 能选择正确算法链
- 能在失败时 bounded healing
- 能给出审计证据
- 能在规模任务上保持可运行

## Research Questions

### RQ1

`KG-decomposed algorithm primitives` 是否比“黑盒式算法调用”或“弱结构 planner”更能提升规划有效性与执行成功率？

**Why this needs a two-step comparison**

如果不拆开比较，`KG` 是否存在和 `primitive decomposition` 粒度是否足够细会被混在一起，A2 的提升就很难解释清楚。

**What to prove**

- 更低的 unknown-algorithm / invalid-step rate
- 更高的 executable-plan rate
- 更高的 end-to-end success rate

### RQ1 Comparison Logic

| Comparison | Isolated variable | Question answered |
| --- | --- | --- |
| `A0 -> A1` | 是否存在 KG-structured algorithm knowledge | KG 本身是否带来规划收益 |
| `A1 -> A2` | 粗粒度单节点登记 vs. 细粒度 primitive decomposition | 分解粒度是否带来额外收益 |

两步比较合起来回答 RQ1：收益究竟来自 KG 本身，还是来自分解粒度，还是两者叠加。

### RQ1 Baseline Semantics

- `A0`: 无 KG decomposition，仅 coarse task-to-handler mapping
- `A1`: KG 中仅存在 monolithic single-node algorithm handlers；没有 workflow pattern decomposition、没有 per-step parameter specs、没有 pre/post-condition constraints；planner 只能决定“调用哪个算法”，不能围绕中间步骤、部分结果和参数级绑定做推理；`A1` 与 `A2` 复用同一套 planner、KG、数据源和 case pool，只关闭分解能力
- `A2`: full FusionAgent planning，使用 decomposed primitives + validator constraints + workflow pattern expansion

### RQ2

`contract-bounded planning and execution with healing` 是否比“无 healing 的一次性执行”更鲁棒？

**What to prove**

- 失败 case 中更高的 repair / completion rate
- 更低的 silent failure rate
- 更可控的 retry / replan behavior

### RQ3

`auditable evidence contract` 是否能显著提升系统的可解释性、可运营性与论文证据冻结能力，而不是只输出一个最终结果？

**What to prove**

- run inspection completeness
- step grounding visibility
- artifact / audit trace completeness
- paper evidence freeze reproducibility

## Main Thesis Claims

### Claim C1: KG-Decomposed Execution

FusionAgent 不是把外部融合算法当单一黑盒函数，而是把算法原语拆解为 KG 中可调度的节点，使 planner 可以围绕任务、数据类型、参数规格和工作流模式进行受约束选择。

### Claim C2: Bounded Plan-and-Execute With Healing

FusionAgent 的核心不只是 planning，而是 `planner -> validator -> executor -> healing/replan -> writeback` 的 bounded runtime，使失败路径可显式修复而非静默崩溃。

### Claim C3: Evidence-First Geospatial Agent Runtime

FusionAgent 的输出不是单纯答案，而是包含 `run.json / plan.json / validation.json / audit.jsonl / artifact bundle` 的 run-level evidence contract，使 operator inspection、benchmark freeze 与论文证据冻结成为系统内建能力。

## Non-Core Claims To Avoid

- 不把 telemetry / recovery 说成主创新点
- 不把 front-end 说成论文核心系统
- 不把 trajectory-to-road reservation seam 说成可执行能力
- 不把 durable learning 说成 autonomous evolution
- 不把 scenario layer 说成完整数字孪生推演平台

## Related-Work Positioning

### Closest Comparison Buckets

- `CyVerACT`：schema-aware deterministic verification，但输出是 Text-to-Cypher query correctness
- `Geo-Agent`：自然语言 GIS 交互与空间思维链，但偏交互式 GIS agent
- `GeoJSON Agents`：多智能体 geospatial analysis，比对 function calling 与 code generation
- `Barrier-free GeoQA Portal`：多智能体 GeoQA + semantic search + visualization
- `Towards Intelligent Geospatial Data Discovery`：KG-driven geospatial metadata discovery
- `OntoLLM` / `UniAI-GraphRAG` / `PathMind`：ontology grounding、dual-channel retrieval、path prioritization
- `MoRA-RAG multi-hazard`：hazard-domain agentic RAG 与 verification loop

### Our Distinct Position

- 不以 GeoQA 为终点，而以可执行融合 artifact 为终点
- 不以 metadata discovery 为终点，而以 runtime execution 为终点
- 不把 KG 仅用于 schema retrieval，而用于算法原语、参数和 workflow dispatch
- 不止有 query / code generation，而有 bounded execution + healing + evidence writeback

## Experimental Design Overview

### Experiment Group A: Planning Validity And Execution Success

**Purpose:** answer RQ1

**Compared systems**

- A0: weak baseline — no KG decomposition, only coarse task-to-handler mapping
- A1: KG-structured algorithm knowledge with monolithic single-node handlers only
- A2: full FusionAgent planning — decomposed primitives + validator constraints

**Metrics**

- executable-plan rate
- unknown-algorithm rate
- invalid-step rate
- end-to-end run success rate
- grounding completeness score

### Experiment Group A Statistical Unit

- 使用 paired design：同一 case pool 在 A0/A1/A2 三个配置下重复运行
- 每个 case 的 planning / execution 输出都保留独立 run artifact，便于配对比较
- 最低 case pool 目标：30–40 个独立 case，四个任务类型都覆盖，每类至少 5 个

### Experiment Group B: Healing And Robustness

**Purpose:** answer RQ2

**Compared systems**

- B0: full runtime with healing disabled
- B1: full runtime with healing/replan enabled

**Metrics**

- completion rate under injected failure cases
- repair success rate
- output validity rate
- unhandled exception rate
- mean retry count
- failure-to-explicit-status latency
- failure-to-diagnosis step count
- root-cause visibility rate

### Experiment Group C: Evidence Contract And Inspection

**Purpose:** answer RQ3

**Compared systems**

- C0: result-only output mode
- C1: full evidence-contract output mode

**Metrics**

- run inspection completeness
- per-step grounding presence
- artifact trace completeness
- evidence freeze reproducibility
- failure-to-diagnosis step count
- root-cause visibility rate

### Experiment Group D: Benin Scale Validation

**Purpose:** prove system scale relevance, not just toy-case correctness

**Role of Benin workflow**

- 不是偏离主线的专题脚本，而是论文中的规模验证实验
- 用于证明：
  - multi-source tiled execution is feasible
  - decomposed building workflow can run on large national-scale inputs
  - raster enrichment and vector-source preservation work under scale
  - evidence artifacts remain available under large jobs

**Metrics**

- tile completion rate
- stitched output validity
- runtime duration by stage
- source coverage and field preservation
- large-run artifact completeness

## Baseline And Ablation Matrix

### Mandatory Baselines

- baseline 1: no-KG / coarse handler runtime
- baseline 2: no-decomposition / monolithic algorithm selection
- baseline 3: no-healing runtime
- baseline 4: result-only output without full evidence contract

### Mandatory Ablations

- ablation A: remove decomposed primitive expansion
- ablation B: remove grounding report visibility
- ablation C: remove healing/replan
- ablation D: remove artifact / audit contract
- ablation E: optional weak-LLM substitution for planner sensitivity

### Optional Extended Ablations

- path prioritization on/off in planner retrieval
- ontology/metadata normalization on/off for source discovery
- source reuse on/off in task-driven input acquisition

### Mandatory Cross-Model Replication

- 核心比较至少在 2 个 model family 上重复一次
- 目的不是比较谁更强，而是验证架构收益不是某个单一 LLM 的偶然产物
- 最小要求：
  - 主实验 LLM：`Claude Sonnet 4.5` 或 `GPT-4o-2024-11-20`
  - cross-model replication：另一个 model family 上重复 RQ1 和 RQ2 核心比较

### Planner Sensitivity Analysis

- 在同一模型家族内，增加 3-tier capability analysis
- 例如：
  - strong: `Opus 4.5`
  - medium: `Sonnet 4.5`
  - weak: `Haiku 4.5`
- 目标：验证 KG structure 是否能在 weaker planner 条件下仍产生稳定收益

## Statistical Analysis Framework

### Case Pool And Sample Size

- full baseline / ablation matrix 的核心 case pool 目标：30–40 个独立 case
- 每个 case 必须冻结：
  - input bundle
  - task type
  - expected output contract
  - sanity-check rules
- 所有 baseline / ablation / replication 配置复用同一 frozen case pool，不允许跑完某个配置后再增删 case
- failure injection case：30 个，按 6 类失败 × 每类 5 个
- healing experiment 每个配置总 case 数建议为 50：
  - normal cases: 20
  - injected failure cases: 30

### Statistical Tests By Metric Type

- binary outcomes：
  - executable-plan rate
  - repair success rate
  - run success rate
  - output validity rate
  - 建议使用 `McNemar test`
- non-normal rates / ratios：
  - unknown-algorithm rate
  - invalid-step rate
  - unhandled exception rate
  - 建议使用 `Wilcoxon signed-rank test`
- continuous metrics：
  - grounding completeness score
  - artifact trace completeness
  - failure-to-explicit-status latency
  - 建议使用 `paired t-test`，若正态性不满足则回退 `Wilcoxon`
- 主文只用 primary metrics 做假设检验，secondary metrics 只做描述性或辅助分析，不单独支撑核心结论

### Multiple Comparison Correction

- primary correction：跨 3 个 RQ 使用 `Bonferroni`，α = 0.05 / 3 ≈ 0.0167
- 可报告 `Holm-Bonferroni` 作为补充
- 每个 RQ 中明确 primary metrics 与 secondary metrics，避免事后挑指标

### Effect Sizes

- proportion metrics：报告 `Cohen's h`
- continuous metrics：报告 `Cohen's d`
- non-parametric continuous / ordinal metrics：报告 `Cliff's δ`

### Pre-Registration Discipline

- 在正式实验前冻结：
  - case pool
  - metric computation code
  - baseline / ablation matrix
  - comparison sequence
- 所有新增分析若不在冻结清单内，必须标记为 exploratory

## Metric Operationalization

### Grounding Completeness Score

对每个 planning step `s` 计算：

- `g1(s)`: 是否引用 KG 注册算法原语节点
- `g2(s)`: 参数绑定是否满足 parameter spec
- `g3(s)`: input/output data type 是否与 ontology 一致

定义：

```text
step_score(s) = (g1 + g2 + g3) / 3
run_grounding_score = mean(step_score(s) for s in plan.steps)
```

### Artifact Trace Completeness

对每个 run 检查 5 个对象：

- `run.json`
- `plan.json`
- `validation.json`
- `audit.jsonl`
- `artifact bundle`

定义：

```text
completeness = count(item.exists and item.non_empty) / 5
```

### Evidence Freeze Reproducibility

同一 frozen input 独立运行两次，比较：

- plan consistency：step sequence match rate
- output fidelity：per-record Jaccard / F1
- audit consistency：event type match rate

### Output Validity Rate

用于替代“silent failure rate”这一难以直接自动测量的指标：

- 输出必须通过 schema validation
- 同时通过 domain-specific sanity checks
- 示例：
  - fused building count > 0
  - fused building count < 3 × max input source count
- 主文不再把 silent failure rate 作为直接主指标，只保留上述 proxy。

### Root-Cause Visibility Rate

失败 step 中，audit entry 含 machine-readable root cause tag 的比例，例如：

- `PARAM_OUT_OF_RANGE`
- `SOURCE_MISSING`
- `ALGO_TIMEOUT`
- `SUSPECT_OUTPUT`

## Failure Injection Taxonomy

### Injection Categories

- `F1`: input absence
- `F2`: input corruption
- `F3`: parameter violation
- `F4`: algorithm runtime error
- `F5`: resource exhaustion
- `F6`: silent wrong output / semantically suspect output

### Injection Design

- 每类 5 个 case，共 30 个 injected failure cases
- 每个 injected case 必须冻结：
  - target step
  - injection mechanism
  - expected healing path
  - success criterion

### Healing Success Criteria

- retry success：同一步骤在 N ≤ 3 次 retry 内产生 valid output
- replan success：planner 生成 alternative steps 并完成执行
- graceful degradation success：显式部分降级，但 run 保持 valid partial output
- explicit failure success：machine-readable error classification，非 crash / hang

## LLM Version Strategy

### Primary Experiment LLM

- primary experiment LLM 选一个主模型固定使用
- temperature = 0
- 记录：
  - full model identifier
  - endpoint / provider
  - call date range
  - max tokens
  - all inference hyperparameters

### Mandatory Cross-Model Ablation

- cross-model replication 不是 optional，提升为 mandatory
- 至少覆盖 2 个 model family
- 目的：证明收益来自 architecture，而不是单个模型能力
- 这不是 exploratory appendix，而是主实验的一部分；若无法复现，应写入 threats to validity，而不是删除

### Reproducibility Commitments

- 冻结 planner prompts 到 appendix / spec
- 记录全部 API 参数
- 归档模型版本或 snapshot 日期
- 在 threats to validity 里承认 LLM drift 风险

## Threats To Validity

### Internal Validity

- LLM non-determinism：通过 temperature=0 与 cross-model replication 缓解
- metric construct validity：通过 formal operationalization 缓解
- case selection bias：通过跨四类任务的 case pool 覆盖缓解

### External Validity

- geographic generalizability 受限于 case pool 覆盖区域
- task-type generalizability 受限于 building / road / water / poi
- 不同 LLM 版本上具体数值可能漂移

### Construct Validity

- `executable-plan rate` 是 planning validity 的 proxy，不是 planning quality 的全部
- `grounding completeness score` 是 explainability proxy，不是 human understanding 的直接测量
- `artifact trace completeness` 是 auditability proxy，不是 operator efficiency 的直接测量
- human judgment 仍然是 gold standard，但在论文窗口内只能用可重复 proxy 近似

## Datasets And Evaluation Assets

### Primary Assets Already Available

- existing unit tests and integration tests
- golden-case harness
- real-data manifest
- `building_gitega_micro_agent`
- `building_gitega_micro_msft_agent`
- Benin national multi-source building workflow
- scenario harness outputs
- paper evidence freeze assets

### New Assets To Define

- thesis experiment manifest
- baseline / ablation run manifest
- failure-injection cases for healing experiments
- evidence-contract completeness rubric

## Detailed Execution Plan

### Task 1: Write The Thesis Research Specification

**Files:**
- Create: `docs/superpowers/specs/2026-05-06-thesis-research-spec.md`
- Create: `docs/superpowers/specs/2026-05-06-thesis-claims-ledger.md`
- Test: `tests/test_thesis_research_spec.py`

- [ ] **Step 1: Write the failing thesis-spec test**

```python
from pathlib import Path


def test_thesis_spec_contains_rqs_claims_and_non_claims() -> None:
    text = Path("docs/superpowers/specs/2026-05-06-thesis-research-spec.md").read_text(encoding="utf-8")
    assert "RQ1" in text
    assert "RQ2" in text
    assert "RQ3" in text
    assert "KG-decomposed algorithm primitives" in text
    assert "contract-bounded planning and execution with healing" in text
    assert "auditable evidence contract" in text
```

- [ ] **Step 2: Run test to verify the spec does not exist yet**

Run: `python -m pytest -q tests/test_thesis_research_spec.py`
Expected: FAIL with missing file.

- [ ] **Step 3: Write the thesis research specification**

```markdown
# Thesis Research Specification

## Research Questions
- RQ1: Does KG-decomposed execution improve planning validity and execution success?
- RQ2: Does bounded healing improve robustness under failure?
- RQ3: Does the evidence contract improve inspectability and reproducibility?

## Main Claims
- KG-decomposed execution
- bounded plan-and-execute with healing
- evidence-first runtime

## Explicit Non-Claims
- no general-purpose agent claim
- no trajectory-to-road executable claim
- no autonomous self-evolution claim
```

- [ ] **Step 4: Write the thesis claims ledger**

```markdown
For each claim, record:
- required evidence
- dependent modules
- baseline comparison
- disallowed overstatement
```

- [ ] **Step 5: Re-run thesis-spec test**

Run: `python -m pytest -q tests/test_thesis_research_spec.py`
Expected: PASS

### Task 2: Define Baselines, Ablations, And Metrics

**Files:**
- Create: `docs/superpowers/specs/2026-05-06-thesis-experiment-matrix.json`
- Create: `docs/superpowers/specs/2026-05-06-thesis-experiment-design.md`
- Test: `tests/test_thesis_experiment_matrix.py`

- [ ] **Step 1: Write the failing experiment-matrix test**

```python
import json
from pathlib import Path


def test_experiment_matrix_tracks_baselines_ablations_and_metrics() -> None:
    payload = json.loads(Path("docs/superpowers/specs/2026-05-06-thesis-experiment-matrix.json").read_text(encoding="utf-8"))
    assert "RQ1" in payload["research_questions"]
    assert "A0" in payload["baselines"]
    assert "B1" in payload["baselines"]
    assert "ablation_A" in payload["ablations"]
    assert "executable_plan_rate" in payload["metrics"]
```

- [ ] **Step 2: Run test to verify matrix is missing**

Run: `python -m pytest -q tests/test_thesis_experiment_matrix.py`
Expected: FAIL

- [ ] **Step 3: Create the experiment matrix**

```json
{
  "research_questions": ["RQ1", "RQ2", "RQ3"],
  "baselines": {
    "A0": "coarse handler runtime",
    "A1": "KG retrieval without decomposition; monolithic single-node handlers only",
    "B0": "healing disabled",
    "B1": "healing enabled",
    "C0": "result-only output",
    "C1": "full evidence contract"
  },
  "ablations": {
    "ablation_A": "remove primitive decomposition",
    "ablation_B": "remove grounding visibility",
    "ablation_C": "remove healing",
    "ablation_D": "remove evidence contract"
  },
  "metrics": [
    "executable_plan_rate",
    "unknown_algorithm_rate",
    "run_success_rate",
    "repair_success_rate",
    "grounding_completeness_score",
    "artifact_trace_completeness"
  ]
}
```

- [ ] **Step 4: Write the experiment design narrative**

```markdown
For each RQ, define:
- hypothesis
- compared systems
- metrics
- expected conclusion
- minimum acceptance evidence
```

- [ ] **Step 5: Re-run experiment-matrix test**

Run: `python -m pytest -q tests/test_thesis_experiment_matrix.py`
Expected: PASS

### Task 3: Turn Benin Workflow Into Scale-Validation Evidence

**Files:**
- Create: `docs/superpowers/specs/2026-05-06-benin-scale-validation-plan.md`
- Modify: `docs/fusioncode-algorithm-library.md`
- Modify: `docs/v2-operations.md`
- Test: `tests/test_benin_scale_validation_plan.py`

- [ ] **Step 1: Write the failing Benin-plan test**

```python
from pathlib import Path


def test_benin_plan_explicitly_positions_benin_as_scale_validation() -> None:
    text = Path("docs/superpowers/specs/2026-05-06-benin-scale-validation-plan.md").read_text(encoding="utf-8")
    assert "scale-validation experiment" in text
    assert "tiled multi-source building workflow" in text
    assert "not a side utility" in text
```

- [ ] **Step 2: Run test to verify Benin plan is missing**

Run: `python -m pytest -q tests/test_benin_scale_validation_plan.py`
Expected: FAIL

- [ ] **Step 3: Write the Benin scale-validation plan**

```markdown
# Benin Scale Validation Plan

- Position: scale-validation experiment
- Target: national tiled multi-source building fusion
- Proof:
  - large-run execution feasibility
  - raster + vector height preservation
  - output stitching validity
  - evidence artifact completeness
- Non-goal:
  - not a separate data engineering thesis
  - not a new thematic expansion
```

- [ ] **Step 4: Align operations and algorithm-library docs to this role**

```markdown
The Benin workflow should be described as:
- scale validation for the decomposed runtime
- evidence-bearing experimental asset
```

- [ ] **Step 5: Re-run Benin-plan test**

Run: `python -m pytest -q tests/test_benin_scale_validation_plan.py`
Expected: PASS

### Task 4: Build The Related-Work Comparison Matrix For Writing

**Files:**
- Create: `docs/superpowers/specs/2026-05-06-thesis-related-work-matrix.md`
- Create: `docs/superpowers/specs/2026-05-06-thesis-related-work-matrix.json`
- Test: `tests/test_thesis_related_work_matrix.py`

- [ ] **Step 1: Write the failing related-work test**

```python
import json
from pathlib import Path


def test_related_work_matrix_covers_new_geospatial_agent_papers() -> None:
    payload = json.loads(Path("docs/superpowers/specs/2026-05-06-thesis-related-work-matrix.json").read_text(encoding="utf-8"))
    assert "CyVerACT" in payload["papers"]
    assert "Geo-Agent" in payload["papers"]
    assert "GeoJSON Agents" in payload["papers"]
    assert "Barrier-free GeoQA Portal" in payload["papers"]
    assert "GeoEvolve" in payload["papers"]
    assert "MoRA-RAG Multi-Hazard" in payload["papers"]
    assert "our_difference" in payload["fields"]
```

- [ ] **Step 2: Run test to verify matrix is missing**

Run: `python -m pytest -q tests/test_thesis_related_work_matrix.py`
Expected: FAIL

- [ ] **Step 3: Create the related-work matrix**

```json
{
  "fields": [
    "paper",
    "task_type",
    "output_type",
    "uses_kg_for_execution",
    "has_healing",
    "has_run_evidence_contract",
    "our_difference",
    "borrowed_idea"
  ],
  "papers": [
    "CyVerACT",
    "Geo-Agent",
    "GeoJSON Agents",
    "Barrier-free GeoQA Portal",
    "GeoEvolve",
    "OntoLLM",
    "PathMind",
    "UniAI-GraphRAG",
    "Intelligent Geospatial Data Discovery",
    "MoRA-RAG Multi-Hazard"
  ]
}
```

- [ ] **Step 4: Write the paper-facing comparison narrative**

```markdown
For each paper:
- closest overlap
- where FusionAgent is weaker
- where FusionAgent is categorically different
- whether to cite as baseline, adjacent system, or supporting method
```

- [ ] **Step 5: Re-run related-work test**

Run: `python -m pytest -q tests/test_thesis_related_work_matrix.py`
Expected: PASS

### Task 5: Produce The Thesis Outline And Timeline

**Files:**
- Create: `docs/superpowers/specs/2026-05-06-thesis-outline-and-timeline.md`
- Test: `tests/test_thesis_outline_timeline.py`

- [ ] **Step 1: Write the failing outline/timeline test**

```python
from pathlib import Path


def test_thesis_outline_and_timeline_cover_chapters_and_stages() -> None:
    text = Path("docs/superpowers/specs/2026-05-06-thesis-outline-and-timeline.md").read_text(encoding="utf-8")
    assert "Chapter 1" in text
    assert "Chapter 2" in text
    assert "Chapter 3" in text
    assert "Chapter 4" in text
    assert "Chapter 5" in text
    assert "Stage 1" in text
    assert "Stage 2" in text
    assert "Stage 3" in text
```

- [ ] **Step 2: Run test to verify outline file is missing**

Run: `python -m pytest -q tests/test_thesis_outline_timeline.py`
Expected: FAIL

- [ ] **Step 3: Write the thesis outline**

```markdown
## Chapter 1 Introduction
- problem definition
- research gaps
- research questions
- contributions

## Chapter 2 Related Work
- GeoQA / geospatial agents
- KG / ontology grounding
- hazard agentic RAG
- geospatial execution systems

## Chapter 3 Method
- runtime architecture
- KG-decomposed primitives
- bounded planning / healing
- evidence contract

## Chapter 4 Experiments
- baselines
- ablations
- Benin scale validation
- result analysis

## Chapter 5 Conclusion
- summary
- limitations
- future work
```

- [ ] **Step 4: Write the execution timeline**

```markdown
## Stage 1
- freeze claims and research design

## Stage 2
- run baselines and ablations

## Stage 3
- run Benin scale validation and freeze evidence

## Stage 4
- draft thesis chapters and polish figures/tables
```

- [ ] **Step 5: Re-run outline/timeline test**

Run: `python -m pytest -q tests/test_thesis_outline_timeline.py`
Expected: PASS

### Task 6: Define The Handshake Between Research Plan And Capability Plan

**Files:**
- Modify: `docs/superpowers/plans/2026-05-06-fusionagent-capability-consolidation-roadmap.md`
- Create: `docs/superpowers/specs/2026-05-06-plan-handshake.md`
- Test: `tests/test_plan_handshake.py`

- [ ] **Step 1: Write the failing handshake test**

```python
from pathlib import Path


def test_handshake_doc_separates_research_plan_and_capability_plan() -> None:
    text = Path("docs/superpowers/specs/2026-05-06-plan-handshake.md").read_text(encoding="utf-8")
    assert "research plan answers why and how to prove" in text
    assert "capability plan answers what to freeze and what to harden" in text
```

- [ ] **Step 2: Run test to verify handshake doc is missing**

Run: `python -m pytest -q tests/test_plan_handshake.py`
Expected: FAIL

- [ ] **Step 3: Write the handshake document**

```markdown
# Plan Handshake

- research plan answers why and how to prove the thesis contribution
- capability plan answers what to freeze, harden, or deprioritize so the thesis stays on-axis
- capability work is subordinate to research proof
```

- [ ] **Step 4: Link the capability plan back to this document**

```markdown
Add one section to the capability roadmap stating:
- execute capability hardening only insofar as it supports the thesis experiment chain
```

- [ ] **Step 5: Re-run handshake test**

Run: `python -m pytest -q tests/test_plan_handshake.py`
Expected: PASS

## Review Checklist For This Plan

- 是否把“元计划”和“研究计划”明确分离
- 是否把工程增强项降为 supporting evidence，而非主创新点
- 是否提出了可回答的 2–3 个研究问题
- 是否给出了能做出结论的 baseline / ablation 设计
- 是否把 Benin national workflow 重新定位为规模验证证据
- 是否把论文结构与实验链路提前对齐
- 是否明确标注了哪些指标是 primary、哪些只是 proxy
- 是否把 cross-model replication 纳入主实验，而不是附录

## Expected Deliverables From Executing This Plan

- thesis research spec
- thesis claims ledger
- experiment matrix and baseline/ablation design
- Benin scale-validation plan
- thesis related-work matrix
- thesis outline and timeline
- research-plan / capability-plan handshake note

## Non-Goals Of This Plan

- 本计划不直接实现新的 runtime 功能
- 本计划不直接运行全部实验
- 本计划不直接写完整论文正文
- 本计划不把所有工程增强项都升级为论文贡献
