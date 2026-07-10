# FusionAgent Handoff: Visible Dialogue Before The Error

Scope: this file preserves the visible user/assistant dialogue from the previous Claude Code session up to the assistant turn immediately before the API error. Thinking blocks, internal tool results, task notifications, PDF document/base64 payloads, and all post-error content are omitted.

## Continuation Prompt

```text
Continue the original conversation transcribed above.

Important constraint: the previous assistant was about to read `F:\vscode\fusionAgent\文档\Proposal.pdf`. Do not directly use the Claude Code Read tool on this PDF, and do not send the PDF as a document/base64 attachment to the model.

First, safely extract the proposal text with command-line tools. Prefer `pdftotext` if available; otherwise use Python with `pypdf` or `pdfplumber`. Save the extracted text as a plain `.txt` file, then read only the relevant chunks: research background, research objectives, research contents, technical route, innovation points, and experiment/evaluation plan.

After reading those chunks, continue answering the unresolved question from the original conversation: given my master's research positioning, how should the reasonable role of the LLM in FusionAgent be expanded; which responsibilities belong to the knowledge graph and which belong to the LLM; and how should the proposal's research contents, innovation points, and technical route be adjusted so the LLM is not merely a formal add-on.
```

## Transcript

### 1. User

针对这个项目，思考以下问题：
1.怎么体现llm的必要性和作用，当前的系统是否实际使用mock，并未有llm参与？
2.知识图谱的本体怎么优化？这个三元知识图谱是研究的很重要的一部分
3.知识图谱中是否需要存储完整workflow？成功案例的工作流确实应该保存学习，这是自我优化的需要，但是每次的规划应该是由llm根据知识图谱做出的，而不是直接从工作流中读取，这样也失去了灵活性，甚至连知识图谱的其余部分也被削弱了。这个问题实际上设计问题1、2两个方面

这是我认为最关键的几个问题，其他问题我们稍后再探讨。你先不必改动任何代码，这是一次深入的讨论而不是工程指令。

### 2. Assistant

这是很好的三个问题，而且彼此紧密相关。在展开讨论之前，我想先把当前代码的真实状态摸清楚——尤其是问题1（系统是否真在用 mock，LLM 是否真正参与）必须基于事实，不能凭印象。让我并行勘察几个方向。

### 3. Assistant

I've launched three parallel investigations into the codebase. While they run, let me be clear about how I'm approaching this: your three questions are genuinely interconnected, and I want to ground the discussion in what the code *actually* does rather than what it's supposed to do. I'll wait for the findings before responding substantively.

### 4. Assistant

The knowledge graph investigation is complete and very informative. Let me wait for the LLM-usage and workflow/planning investigations before synthesizing — those two are essential to answering questions 1 and 3 accurately.

### 5. Assistant

Two of three are in. The workflow/planning control-flow investigation is still running — that one is critical for question 3. Let me wait for it.

### 6. Assistant

三个调查都回来了，事实基础已经清楚。先给你一个总的判断，再逐题展开——**因为你这三个问题在架构上其实是同一个问题**，我会在最后把它们收束到一起。

先纠正一个比你想象的更严重的事实：

---

## 关于问题 1：当前系统不仅"用了 mock"，而且连 mock 都没真正在跑

调查结果比"是否用 mock"更尖锐：

- LLM 在整个系统里**只有一个职责**——`agent/planner.py` 里调用 `generate_workflow_plan()` 生成一个 workflow 计划(JSON DAG)。检索、意图识别、融合算法、质量门禁、参数绑定**全部是确定性 Python**,没有任何 LLM 参与。
- 默认配置(`.env.example` 第 2 行 `GEOFUSION_LLM_PROVIDER=mock`)走 mock。
- **而这个 mock 是坏的**:`MockLLMProvider` 从 `context.get("candidate_patterns")` 顶层读候选,但 `PlanningContextBuilder.build()` 把候选放在 `context["retrieval"]["candidate_patterns"]` 嵌套层。所以 mock 必然抛 `ValueError`,`create_plan()` 捕获后回落到 `_select_fallback_pattern_from_context()` + `_build_skeleton_plan()`,`planning_source="kg_fallback"`。仓库里的 `_verify_mock.py` 自己记录了这一点。

**也就是说:当前默认跑起来的"LLM 计划",既不是 LLM、也不是 mock 的输出,而是确定性地取排序第一的 KG pattern。** 你现在任何 demo 展示的都是被误标为 LLM 的确定性行为。

但这里有个更深的、你必须直面的问题——**即使换上真 LLM,它也几乎是不必要的**,而且是**被架构设计成不必要的**:

> 检索器 `agent/retriever.py` 已经用一个打分公式
> `0.40·source_quality + 0.35·algorithm_fit + 0.25·workflow_support − 0.25·missing_requirements`
> 把候选 pattern **排好序**了。LLM 拿到的 prompt 是"只能用候选里的算法、优先高成功率 pattern"。于是 LLM 的实际决策空间 ≈ 对一个已排好序的列表做 argmax。而 `kg_fallback` 做的就是取 top-1。**两者输出本质等价——这正是为什么回落逻辑能无缝顶替它。**

所以"LLM 必要性"不是一个调参问题,是一个**决策边界(decision boundary)问题**:只要 KG 把答案预先算成一个标量排序,LLM 干的就是 argmax,任何确定性代码都能替代。要让 LLM 必要,你必须把**确定性排序无法化约的决策**交给它。这直接引出问题 2 和 3。

---

## 关于问题 2:本体现在编码了"能力",但没编码"判断所需的语境"

先澄清术语:你的"三元知识图谱"里的**三元 = 算法-任务-数据(Algorithm-Task-Data)执行三元**,不是 RDF 的 SPO 三元组。它是一个 labeled property graph,~13 类节点 + 15 类边,灾害被上移为 scenario 约束层。这个设计本身是干净的。

问题在于:**当前本体是"执行导向"的——它回答"有什么算法、吃什么吐什么、哪个 pattern 把它们串起来",但几乎不回答"为什么合适、在什么数据条件下会退化、代价与收益的权衡、失败意味着什么"。** 它编码了*能力(capability)*,没编码*理据与语境(rationale & context)*。

这正是 LLM 派不上用场的技术原因:一个只有能力、没有条件语义的图,唯一能做的推理就是"按分数排序"。判断被压缩进了 `0.40/0.35/0.25` 这几个不透明的权重里,而不是留给推理者。

本体优化的方向,应当服务于"给 LLM 留出真正需要判断的地方":

1. **让边携带条件语义,而不只是拓扑。** 现在 `APPLIES_TO_TASK`、`ALTERNATIVE_TO`、算法的 `input_types→output_type` 都是无条件的。应该把"适用条件 / 前置条件 / 失效条件"变成一等公民:某算法在源覆盖率低于 X、几何类型为 Y、AOI 大于 Z 时退化。这样"选哪个算法"从 argmax 变成"在当前条件下推断适用性"——这是 LLM 该做的。
2. **把"能力"和"经验"在本体里分层。** 现在算法节点上直接挂 `success_rate/accuracy/stability` 标量,经验(DurableLearningRecord)又单独一层去 ±0.10 微调这个标量。结果是:静态先验和动态经验都被压成同一个标量,推理者看不到"这个成功率是在什么条件下得到的"。经验应该带着它的**条件维度**(AOI 桶、覆盖率、质量门结果)被检索,而不是被 aggregate 成一个数。
3. **DataType 格(lattice)是你已经做对的部分。** `CAN_TRANSFORM_TO` + `find_transform_path` 是真正的图遍历,`dt.raw.vector → dt.building.bundle`。这是本体里唯一"图结构承载了不可化约推理"的地方——可以把它当作扩展其他部分的范本。
4. **让 scenario 约束层表达冲突与权衡,而非只做激活。** 现在 `ScenarioProfile ACTIVATES_TASK`、`DEFAULTS_TO_QOS` 都是单向映射。真实场景里洪水 vs 地震对"精度 vs 时效"的取舍是冲突的——把这些 trade-off 显式化,LLM 才有东西可权衡。

一句话:**本体要从"可执行的能力网"升级为"可推理的决策空间"。** 优化的判据不是"节点更多",而是"是否把原本压进权重/标量里的判断,重新暴露成推理者能读、能权衡的结构"。

---

## 关于问题 3:你的直觉是对的,而且当前系统正卡在你担心的两个极端之间

你的判断——**成功工作流应当保存以供学习(自我优化),但每次规划应由 LLM 基于 KG 做出,而非直接读取工作流;否则丧失灵活性,甚至削弱 KG 其余部分**——这是一个很准的架构直觉。它对应 CBR(案例推理)里"case 是证据,不是模板"的核心区分。

而当前系统的现状是:它在**两个极端各占了一半的坏处**:

- **好的一半(它没做错):** 系统**确实不 replay 存储的计划**。每次 `create_run` 都 fresh planning,`plan.json` 只落盘做审计,从不被回读。所以你担心的"直接读工作流→丧失灵活性→KG 其余部分退化"这个失败模式,当前**没有发生**。
- **坏的一半(它做错了):** 它为了不 replay,**把成功案例的结构信息整个丢掉了**。运行结束只写 `WorkflowInstance`(链到用了哪个 pattern/algo/source + success 标志 + 失败原因)和 `DurableLearningRecord`,然后 aggregate 成一个 ±0.10 的标量去微调排序。**LLM 当时生成的那个 DAG 结构、参数绑定、步骤顺序——真正值得学习的东西——没有作为可检索的知识存进 KG。** 也就是说:**没有任何机制能捕获一次新颖的成功结构,并在后续运行里复用/改编它。** 自我优化目前只是"给旧模板的分数加减",不是"学到新工作流"。

所以正确的设计,恰恰是你描述的那个中间态,我把它落成**三层知识 + 一条学习回路**:

**知识分三层(planning 时 LLM 对三层一起推理):**
1. **能力层** — algorithm / datatype / transform:*什么是可能的*。
2. **规范层** — WorkflowPattern(模板)/ scenario 约束 / output requirement:*什么是被推荐或被要求的*。
3. **经验层** — 成功与"有教益的失败"案例,**带完整结构 + 条件**:*在什么条件下发生过什么*。

**规划 = LLM 读三层 → 产出 fresh plan;学习 = 新经验进第 3 层,偶尔被抽象进第 2 层。**

这套设计精确地实现了你的两条要求:

- **"成功案例要存来学习"** → 存进经验层,但存的是**结构 + 条件**(不是只存标量,也不是只落盘审计)。检索时按条件相似度取 top-k 案例,作为**exemplar/证据**喂给 LLM 的 planning context。
- **"规划由 LLM 基于 KG 做,而非读取工作流"** → 案例只是**证据**,LLM 仍必须把计划**接地(ground)到当前的能力层与约束层**并逐步用 runtime contract 校验(系统已有这个校验基础)。**案例负责启发,KG 负责验证。** 这样案例永远不会绕过算法/任务/数据/scenario 的推理——你担心的"KG 其余部分被削弱"就不会发生。
- **闭环(真正的自我优化)** → 当某个新颖结构在相似条件下反复成功,**把它抽象成一个新的 WorkflowPattern**(从经验层升格到规范层)。这个升格应当是**审慎的、可由 LLM 或人参与策划的抽象步骤**,不是自动 replay。这就是"学到新工作流"与"丧失灵活性的 replay"之间的分界线。

关键区分,一句话:**workflow-as-evidence(检索来启发 LLM)vs workflow-as-template(直接执行)。** 你的直觉本质上是在要求前者,反对后者。当前系统两者都没有——它把证据也丢了,只留了标量。

---

## 三个问题是同一个问题

把三条合起来看:

> **LLM 之所以显得不必要(Q1),是因为 KG 把答案预先解成了标量排序(Q2 的本体缺陷),而经验又只以标量形式沉淀(Q3 的缺陷)。三个缺陷是同一个根因的三个侧面:判断被系统性地从推理者手里拿走、压进了权重和标量里。**

反过来:**一旦本体编码条件语义(Q2)、成功案例以结构化证据形式入图(Q3),LLM 的任务就从"对排好序的列表做 argmax"变成"在给定约束、能力和一批相似/相异条件下的历史案例中,组合/改编出一个计划"——这才是 LLM 真正不可替代的地方(Q1)。同一个改动,同时让 KG 更丰富、可自我优化,又不塌缩成 replay。**

---

## 给论文/研究定位的两点诚实建议

1. **必须诚实地界定 LLM 挣它工资的地方。** 对已被 pattern 良好覆盖的"常见 happy path",确定性规划其实是*正确*的选择——安全、可审计、可复现。LLM 的价值在**组合泛化与适配**:没有单一 pattern 覆盖的新任务、约束的新颖组合、模糊的自然语言 trigger、需要结构性重规划(而不只是换个替代算法)的失败诊断。一个可辩护、且更诚实的研究立场是:**"KG 让常见情形确定化,LLM 承接长尾的组合与适配"**——但**你必须设计真正会触发这个 regime 的实验**,否则评审会正确地问"LLM 为什么在这里"。目前 mock 坏掉的状态下,LLM 从不触发,这个论证是空的。

2. **先修那个坏 mock**——无论架构怎么演进都要修。它现在让默认配置跑的是被误标为 `llm`/`kg_fallback` 混淆的确定性路径,任何关于"LLM 作用"的实验数据都不可信。这是个几行的嵌套层级修复,但它是所有后续讨论的地基。

---

这是我对三个问题的判断。你说其他问题稍后再谈——我建议下一步我们具体钻一个:**要不要我把"经验层案例结构 + 条件 schema"和"pattern 升格"这条回路,画成一个具体的本体扩展 + 数据流方案**(仍然只是设计,不动代码)?那会把 Q2 和 Q3 的抽象讨论落到可实现的形状。或者你想先展开 Q1 的实验设计——如何构造真正区分"LLM 参与 vs 确定性回落"的对照。你定方向。

### 7. User

把"经验层案例结构 + 条件
  schema"和"pattern 升格"这条回路,画成一个具体的本体扩展 + 数据流方案

### 8. Assistant

这是一个能把前面所有抽象讨论"落形"的关键设计。我把它画成**一张总图 + 四个可实现的部件 + 一条闭环数据流**,并且刻意让它嵌进现有本体(复用你已有的 `WorkflowInstance` / `DurableLearningRecord` / `WorkflowPattern`,而不是另起炉灶)。全程只是设计,不动代码。

---

## 0. 一句话目标

> 让一次成功运行沉淀下来的不再是一个 ±0.10 的标量,而是一个**带条件的、可检索的、可被 LLM 当证据用的结构化案例**;并让反复成功的新结构,能经过一道**审慎的升格闸门**变成新的 WorkflowPattern。案例负责*启发*,KG 负责*验证*,升格负责*固化*。

---

## 1. 总览:三层知识 + 一条回路

```
                    ┌───────────────────────────────────────────────┐
                    │                  PLANNING 时刻                  │
                    │  LLM 同时读三层, 产出 fresh plan (仍需接地校验)  │
                    └───────────────────────────────────────────────┘
                          ▲              ▲                   ▲
           ground/verify  │              │ recommend         │ exemplify (证据)
                          │              │                   │
   ┌──────────────────────┴───┐  ┌───────┴────────┐  ┌───────┴─────────────────┐
   │  ① 能力层 CAPABILITY      │  │ ② 规范层 NORMATIVE│  │ ③ 经验层 EXPERIENCE      │
   │  Algorithm / DataType    │  │ WorkflowPattern │  │ ExecutionCase           │  ← 新
   │  Transform 格 / Source    │  │ Scenario 约束    │  │  + SituationSignature   │  ← 新
   │  (什么是可能的)           │  │ OutputRequirement│  │  + StructuralSignature  │  ← 新
   │                          │  │ (什么被推荐/要求) │  │ (在什么条件下发生过什么) │
   └──────────────────────────┘  └────────▲────────┘  └───────┬─────────────────┘
                                          │                   │
                                   ④ PROMOTE 升格闸门 ◄────────┘
                                   (新颖结构 × 反复成功 × 条件成簇
                                    → 抽象成 PatternCandidate → 审阅 → Pattern)
                                          │
                                          └── 写回 ②
```

现状对照:你现在**只有 ①②**,再加一个被压成标量、绕过整个图的"伪经验"(DurableLearningSummary 的 ±0.10)。本方案把 ③ 做成一等公民,并补上 ④ 这条从 ③→② 的回路。

---

## 2. 本体扩展:新增节点(与现有 `WorkflowInstance` 的关系)

现在的 `WorkflowInstance` 太薄——只链到 pattern/algo/source + `success` + `failureReason`。**我建议把它扩展/替换为 `ExecutionCase`**,它保存 LLM 当时实际产出的**完整 DAG 结构**,而不是只保存"用了哪个 pattern"。

### 2.1 `ExecutionCase`(`:ExecutionCase`,keyed `case.<run_id>`)

| 字段 | 含义 | 来源 |
|---|---|---|
| `case_id` | `case.<run_id>` | run |
| `job_type` / `scenario` | 任务类型 / 灾害场景 | request |
| `planning_source` | `llm` / `kg_fallback` / `promoted` | planner |
| `derived_from_pattern` | 若基于某 pattern 展开则记录;若是 LLM 组合出的新结构则为 null | planner |
| `outcome` | `success` / `repaired` / `failed` | run |
| `quality_metrics` | 质量门禁的**结构化结果**(每 gate 的 pass/score),不是单个 bool | quality_gate_service |
| `cost_metrics` | latency、算力、reuse 命中 | telemetry |
| `situation_ref` → | 指向 `SituationSignature`(见 §3) | 计算 |
| `structure_ref` → | 指向 `StructuralSignature`(见 §4) | 计算 |
| `HAS_CASE_STEP {order}` → | 指向 `CaseStep` 序列 | plan |

### 2.2 `CaseStep`(`:CaseStep`)—— 镜像现有的 `PatternStep`,但记录**具体绑定**

关键区别:`PatternStep` 是模板(带变量),`CaseStep` 是**实例**(带当时真实解出的算法、参数、源、输入输出 datatype)。

```
CaseStep:
  order, algorithm_id, param_binding{k:v},        # 实际参数, 不是 default
  input_data_type, output_data_type,
  resolved_data_source_id,                          # 实际选中的源
  depends_on[], is_transform,
  step_outcome{ok|repaired|failed}, repair_applied  # 步级结果, 供失败案例学习
```

> 设计要点:`CaseStep` 让"参数绑定"和"步骤级失败/修复"成为可学习对象。现在这些信息在 `plan.json` 里落盘但从不回读——等于丢了。

### 2.3 与旧节点的关系

- `ExecutionCase` **取代** `WorkflowInstance` 的角色(或让 `WorkflowInstance` 变成它的瘦别名,平滑迁移)。
- `DurableLearningRecord` / `DurableLearningSummary` **保留但降级**:它们继续做"标量排序微调"这件确实有用的小事(fast path),但不再是经验的*唯一*载体。经验的主载体是 `ExecutionCase`。
- 新边:`Exemplifies`(Case → Pattern,若它验证了某模板)、`DEVIATES_FROM`(Case → Pattern,若它偏离了模板并成功——这是升格的原料)。

---

## 3. 部件核心之一:条件 Schema = `SituationSignature`

**这是整个方案的心脏。** 案例要能被检索,必须有一个可比较的"处境向量"。现在的 condition metadata(aoi bucket、coverage、gate result)零散地挂在 DurableLearningRecord 上、只用于聚合;我把它提升为一个**显式、结构化、可算相似度**的节点。

### 3.1 `SituationSignature`(`:SituationSignature`,keyed `sit.<hash>`)

分三组维度,**类型化**(分类量 vs 分桶数值量),因为相似度检索需要类型感知的距离:

```
── 任务/场景维(categorical) ────────────────────────────
   job_type            : task.building.fusion | task.road.fusion | ...
   scenario            : flood | earthquake | typhoon | default
   output_requirement  : or.building.fused.v1 | ...
   qos_priority        : accuracy_first | latency_first | balanced
   trigger_modality    : structured | nl_freeform      # 自然语言 trigger 与否

── 数据条件维(numeric, 分桶) ─────────────────────────────
   aoi_area_bucket     : xs | s | m | l | xl           # 已有 aoi bucket, 复用
   source_coverage     : {osm:0.9, google:0.4, ms:0.0} # 每源覆盖率
   coverage_class      : single_source | complementary | conflicting
   geometry_mix        : {polygon:0.8, point:0.2}
   input_quality       : hi | mid | lo                 # 源质量分档
   freshness_class     : fresh | stale

── 结果条件维(仅写入时填, 检索时不作为 key) ──────────────
   observed_outcome, observed_quality, observed_cost
```

### 3.2 为什么这样设计

- **前两组是检索键(retrieval key)**,第三组是标签(label)。检索时:"给我在**相似处境**下发生过的案例",而不是"给我用过这个 pattern 的案例"。这正是把经验从"绑定到模板"解绑成"绑定到处境"的关键一步——也是你 Q3 里"不丧失灵活性"的技术落点。
- **coverage_class**(single/complementary/conflicting)这类**派生语义标签**特别重要:它把"三个源覆盖率 {0.9,0.4,0}"翻译成 LLM 能直接推理的语义("这是单源为主、需要补洞的情形")。这也回应 Q2——**把压进权重里的判断,重新暴露成可读结构**。
- 相似度 = 类型感知的加权距离(categorical 用匹配/层级距离,numeric 用分桶后的序距离)。**不需要向量数据库**;在 Neo4j 里对 `SituationSignature` 建索引 + 一个确定性距离函数即可。若日后案例量大,再引入 embedding 作为二级召回。

---

## 4. 部件核心之二:结构签名 = `StructuralSignature`(升格的前提)

要判断"一个**新颖结构反复成功**",必须能回答两个问题:两个案例是不是同一个结构?这个结构是不是已有 pattern 的翻版?为此需要给 DAG 一个**规范化指纹**。

### 4.1 `StructuralSignature`(`:StructuralSignature`,keyed `struct.<hash>`)

```
canonical_form : 对 CaseStep DAG 做规范化后的拓扑
                 = 有序的 (algorithm_id, input_dt→output_dt, depends_on拓扑)
                 抹掉具体 AOI / 具体 source_id / 具体参数值
                 保留 算法身份 + transform 拓扑 + 分支结构
signature_hash : 上述的稳定哈希
novelty_vs_patterns : 与所有现有 WorkflowPattern 的最小结构编辑距离
```

### 4.2 它解决什么

- **"是不是同一个结构"** → 比 `signature_hash`。
- **"是不是新颖"** → `novelty_vs_patterns` 大于阈值 = LLM 组合出了规范层没有的东西。这正是**值得升格的原料**;反之,若某案例结构 == 某现有 pattern,它只是**验证/加固**了该 pattern(走 `Exemplifies` 边,给该 pattern 的置信度加分,不触发升格)。
- 抹掉 AOI/source/参数值,是为了在**结构层面**聚类——把"同一套算法拓扑,在不同城市/不同源上跑成功"识别为同一个可升格候选。

---

## 5. 数据流 · 写路径(run 结束时)

现在 `_record_execution_feedback` 只写一个 WorkflowInstance + 一个标量 DLR。改造后:

```
run 完成
   │
   ├─ 组装 SituationSignature   ← 从 request + retriever 已算出的 coverage/aoi/quality 输入
   │     (处境维在 planning 时其实大多已算出, 顺手固化即可, 几乎零额外成本)
   │
   ├─ 组装 StructuralSignature  ← 规范化 plan 的 CaseStep DAG → hash + novelty
   │
   ├─ 写 ExecutionCase(case.<run_id>)
   │     ├─ HAS_CASE_STEP → CaseStep[]      (完整结构 + 实际参数 + 步级结果)
   │     ├─ situation_ref → SituationSignature
   │     ├─ structure_ref → StructuralSignature
   │     └─ 若 derived_from_pattern:
   │           ├─ 结构相同 → Exemplifies → Pattern     (加固)
   │           └─ 结构偏离 → DEVIATES_FROM → Pattern    (升格原料)
   │
   └─ (保留) 写 DurableLearningRecord 标量  ← fast-path 排序微调, 不变
```

**关键:失败也要写。** `outcome=failed` 的案例,连同它失败在哪一步(`CaseStep.step_outcome`)、什么处境下失败,是"有教益的失败"——检索时作为**反例**喂给 LLM("在这种处境下,X 结构在第 3 步质量门禁挂了")。这比现在只存一个 `failure_reason` 字符串强得多。

---

## 6. 数据流 · 读路径(planning 时,LLM 如何用案例)

这是回答你 Q3"规划由 LLM 基于 KG 做,而非读取工作流"的**具体接口**。

```
PlanningContextBuilder.build(job_type, trigger)
   │
   ├─ (现有) kg_repo.build_context → 能力层 + 规范层候选 + 排序    ← 保留
   │
   ├─ (新) 计算当前 SituationSignature(query 处境)
   │
   ├─ (新) 案例检索 retrieve_cases(query_situation, k):
   │        ├─ 按 situation 相似度取 top-k 成功案例 (positive exemplars)
   │        ├─ 取 top-m 相似处境下的失败案例 (negative exemplars)
   │        └─ 每个案例携带: 结构摘要 + 实际参数 + 结果 + 与当前处境的差异点
   │
   └─ planning_context["case_evidence"] = {
           positives:[...], negatives:[...],
           note: "这些是相似处境下的历史案例, 作为参考证据, 不是必须遵循的模板"
       }
```

然后 planner 的 prompt(现在那句"只能用候选算法")升级为**证据推理**式:

> "以下是与当前处境相似的历史案例(成功/失败)及其条件差异。请**参考**成功案例的结构与参数、**规避**失败案例的路径,但你的计划必须只使用能力层提供的算法、满足规范层的 output requirement 与 scenario 约束,并逐步通过 runtime contract 校验。"

**护栏(直接实现你的"不丧失灵活性 / 不削弱 KG"要求)——三条硬约束,案例永远绕不过:**

1. **接地校验不变。** LLM 产出的每一步仍走现有 runtime-contract / ontology-closure 校验;案例只能启发,不能让一个不合法的计划过关。
2. **案例是证据不是模板。** context 里案例以"positives/negatives + 差异点"呈现,措辞明确其为参考;不存在"取 case[0] 直接展开"的代码路径(这正是你反对的 replay)。
3. **处境不匹配就自然退化。** 当没有相似案例(冷启动 / 新处境),`case_evidence` 为空,系统平滑回到"纯能力层+规范层"规划——**灵活性天然保留**,因为案例从不是必需输入。

---

## 7. 数据流 · 升格回路 ④(经验层 → 规范层)

这是把"学到新工作流"和"危险的 replay"分开的那道闸门。**升格是审慎的、成簇触发的抽象,不是自动回放。**

### 7.1 触发条件(全部满足才生成候选)

```
一个 (StructuralSignature S, SituationCluster C) 配对, 当:
  ① support   : 在处境簇 C 内, 结构 S 的成功案例数 ≥ N        (反复)
  ② confidence: S 在 C 内的成功率 ≥ τ_high                    (可靠)
  ③ novelty   : S.novelty_vs_patterns ≥ δ                     (新颖, 非现有模板翻版)
  ④ coherence : C 是一个紧致的处境簇 (处境相似度内聚, 非大杂烩) (可泛化)
  ⑤ dominance : S 在 C 内优于现有被激活 pattern (质量或代价)   (有增量价值)
→ 生成 PatternCandidate(wpc.<struct_hash>.<cluster_id>)
```

### 7.2 抽象操作(lift:case → template)

把具体案例**参数化**成模板——这是"升格"的实质:

```
CaseStep(具体)                          PatternStep(模板)
  algorithm_id: algo.x.v1        ──►     algorithm_id: algo.x.v1        (保留)
  resolved_data_source: osm_bldg ──►     data_source_id: ⟨由 source-selection 在
                                          该 datatype 上运行时决定⟩       (变量化)
  param_binding: {tol: 0.7}      ──►     parameters: {tol: 0.7}          (作为推荐 default,
                                          可带 conditional_defaults 条件化)
  具体 AOI                        ──►     ⟨AOI 无关⟩                       (抹除)
  ── 附加到 candidate ──
  applicability_condition        ◄──     从 SituationCluster C 的公共维度
                                          反投影出"该模板适用于何种处境"
```

注意最后一行:升格不只产出模板,还产出**这个模板适用于什么处境**——直接回填 §2 里"让边携带条件语义"的 Q2 目标。新 pattern 带着它的适用条件出生。

### 7.3 审阅闸门(critical——别让它全自动)

```
PatternCandidate → 三选一:
  (a) 人工审阅通过        → 提升为 WorkflowPattern(wp.*.learned.v1)
  (b) LLM-as-curator 审阅 → 让一个独立 LLM 评估"这个抽象是否合理、是否与
                            现有 pattern 冗余、适用条件是否被过度泛化",给出建议
  (c) shadow 模式        → 先作为影子 pattern 并行推荐, 累计更多案例再定
写回规范层后:
  - 新 pattern 参与后续 candidate 排序(与 seed pattern 同等身份)
  - 溯源: PROMOTED_FROM → 那批 ExecutionCase(可审计"这个模板从哪些案例学来")
```

> 为什么必须有闸门:自动升格 = 把一次(或几次)偶然成功固化成制度,正是"丧失灵活性"的另一种形态——只不过发生在规范层而非执行时。**闸门是"学习"与"过拟合到近期案例"之间的正则化。** shadow 模式(c)是最稳的默认:让新结构先证明自己跨更多处境仍成立,再固化。

---

## 8. 与现有代码的映射(证明它是可落地的,不是空想)

| 本方案部件 | 嵌入现有的哪里 | 改动性质 |
|---|---|---|
| `SituationSignature` 的处境维 | 大多已在 `retriever` / `agent_run_service` 的 condition metadata 里算出(aoi bucket、coverage、quality) | **固化**已有量,非新算 |
| `ExecutionCase` + `CaseStep` | 扩展 `_record_execution_feedback`(现写 WorkflowInstance 处);结构直接来自已落盘的 `plan.json` | 复用现有数据 |
| `StructuralSignature` | 对 `WorkflowPlan.tasks` 做规范化哈希,新增纯函数 | 新增,但独立无侵入 |
| 案例检索进 context | `PlanningContextBuilder.build` 新增一个 `case_evidence` key | 加法,不动现有 retrieval |
| 标量 fast-path | `DurableLearningSummary` ±0.10 那套**原样保留** | 零改动 |
| 升格闸门 | 新增离线/批处理服务(读 `ExecutionCase` 聚类),不在关键运行路径上 | 旁路,不影响 run 延迟 |

**没有一处要求你推翻现有 ①②。整套是加法。** 这点很重要:它保证了改造过程中系统始终可跑。

---

## 9. 分阶段落地(每阶段都独立可验证)

```
阶段 0  修坏 mock(§前次讨论)+ 让 planning_source 可信         ← 地基, 必须先做
阶段 1  写路径: SituationSignature + ExecutionCase + CaseStep    ← 只写不读, 零风险,
         (先只沉淀, 不改变任何规划行为)                            开始积累案例语料
阶段 2  读路径: case_evidence 进 planning context + prompt 升级   ← LLM 首次真正用上经验;
         做 A/B: 有/无 case_evidence 的规划质量对照                这也是 Q1 实验的天然载体
阶段 3  StructuralSignature + 升格候选检测(只产候选, 不自动升格) ← 观察能否发现新结构
阶段 4  升格闸门(shadow 模式默认)+ 溯源 PROMOTED_FROM            ← 闭环合拢
```

**阶段 2 顺带解决你的 Q1 实验诉求**:关掉 `case_evidence` = 退化到纯 KG 规划(近似当前行为);打开 = LLM 基于经验做组合适配。两者对照,就是"LLM 在长尾组合泛化上到底挣不挣工资"的**直接、可量化的证据**——这比现在 mock 坏掉、LLM 从不触发的状态,强了一个量级。

---

## 10. 一句话收束

> 这条回路把 Q2 和 Q3 焊在了一起:**`SituationSignature` 让本体开始编码"处境"(Q2 的条件语义),`ExecutionCase` 让成功结构以证据而非标量沉淀(Q3 的正确形态),`Promotion` 让反复成功的新结构固化回规范层(自我优化),而三条护栏 + 升格闸门保证案例永远只是启发、KG 永远负责验证(你要的"不丧失灵活性、不削弱 KG")。** 同一套机制,同时让 LLM 变得必要(Q1)——因为它现在要做的是"在带条件的能力/约束/历史证据上做组合与适配",而这恰恰是 argmax 和确定性回落做不到的事。

---

需要的话,下一步我可以任选其一深化:
1. **把 `SituationSignature` 的相似度函数写成具体的、类型感知的距离公式**(categorical 层级距离 + numeric 分桶序距离 + 权重),让阶段 1/2 可直接实现;
2. **设计阶段 2 的 A/B 实验协议**:用什么处境集、什么指标(质量门通过率 / 结构新颖度 / 代价)来证明 LLM+经验 vs 纯 KG 的差异;
3. **把升格的 lift 操作 + 冲突检测**(新 learned pattern 与 seed pattern 语义重叠怎么处理)写成具体算法。

你定。

### 9. User

我想先把精力放在解决更宏观的问题上，你觉得你目前最没有把握的事情是什么？

### 10. Assistant

诚实地回答:我最没有把握的,不是任何技术细节,而是**我一直在替你默认的那个前提本身可能是错的**。

## 我最没把握的一件事

前一轮我花了很大篇幅设计"怎么让 LLM 变得必要"。但**我从头到尾没有验证过'LLM 应该是必要的'这件事本身是不是真的**——我把它当成了给定目标(因为你 Q1 这么问),然后一路造机器去满足它。

这可能是个陷阱。空间数据融合(building/road/water 的多源 conflation)是一个**边界相当清楚**的问题域:调查显示只有 ~6 个 job_type、4 个灾害场景、十几个算法。这种域**很可能本质上就是低多样性的**——也就是说,确定性的 pattern 也许**真的**覆盖了绝大部分情形,而我用来给 LLM 正名的那个"长尾组合泛化"**可能根本不存在,或小到不值得**。

如果是这样,那么最诚实的研究结论恰恰是我上一轮的反面:

> **"LLM 在这个域里对 happy path 不必要,这是一个发现,而不是一个要修的 bug。真正的贡献是 KG 本体和确定性规划让常见情形可靠、可审计、可复现。"**

我上一轮所有精巧的经验回路,有可能是在**抢救一个不该抢救的东西**,甚至把项目从它真正站得住的贡献(本体 + 确定性融合)上带偏。我没把握的是:**我到底是在帮你把 LLM 焊进一个需要它的地方,还是在帮你给一个不需要它的系统制造学术表演。** 我现在无法从代码判断是哪一种。

## 第二件没把握的:我完全看不见"底层到底跑得对不对"

你的 git 状态里全是 `tmp/abidjan-real-test/`、`tmp/diagnostic-runs/`、`run_caracas_building_fusion.py`、`fix_building_heights.py`、`loop-analysis.md`、连续十轮的 "aoi boundary preference" commit。这些信号强烈指向:**真正在消耗你精力的宏观问题,可能根本不在架构层,而在'这个 pipeline 在真实城市上到底能不能产出正确的融合结果'——AOI 解析、源覆盖、建筑高度、质量门禁这些朴素的地方。**

我对**实际输出质量一无所知**。如果系统连 Caracas 的建筑融合都还在反复调 AOI 边界,那么"LLM 必要性 / 经验回路"是一个**过早的**宏观问题——地基还在晃。我没把握前一轮讨论的抽象层级,是不是比你当前真正的痛点高了一两层。

## 第三件(较小):评价与 ground truth

上面两件事都归结到同一个我看不见的东西:**你用什么衡量"融合得好"?** 没有 ground truth 或指标,"LLM 改善了规划""本体优化了"都是不可证伪的。研究要成立,这个必须存在——但我不知道它是否存在、是什么。

---

## 这三件其实是一件

它们收束成一个我无法从代码回答、只有你能回答的问题:

> **这个项目要向谁、证明什么?** 是一篇要辩护某个**主张**的论文(那么主张是什么、LLM 是不是主张的一部分),还是一个要在真实数据上**跑对**的系统(那么当前卡在哪)?这两个目标的优化方向是**相反**的。

在你回答这个之前,我对"下一步该往哪使劲"给出的任何建议,置信度都不高——因为我可能在为错误的目标做正确的设计。

**能最快解除我这个不确定性的,是这几样里的任意一两个**:论文/开题的核心主张句(或 thesis 结构);一次真实运行的实际输出 + 你眼里它哪里对/不对;以及你心里那个"成功"的判据。给我其中一点,我就能判断我们到底该在架构层谈,还是该下沉到 pipeline 正确性——以及"抢救 LLM"是不是根本就是个伪命题。

### 11. User

这个问题我可以回答你。这个项目是我的硕士研究方向，其研究和应用背景是在灾害情境下，无人值守时，实现受灾区域的数据快速产出。如果具备网络条件和时间条件，例如可在可接受的时间内产出融合数据，即调用融合算法进行融合；如果不具备下载全部来源数据的网络和时间条件，就优先下载提供osm等单源数据，但是仍然启动完整融合，融合完成后再提供融合后数据。在研究方面，主要是要产出一个完整的灾害场景知识图谱，并验证该图谱与llm的结合能够胜任并且更好的胜任上述工作。融合算法本身不是我的研究内容，我要做的是将其拆解并将知识存储到知识图谱中，同样评估方法也是。确有后续进行扩展的可能，例如加入轨迹转道路、融合后数据质量评价，但是也是将已有算法保存到知识图谱中的工作。我认可你对“空间”太小的判断，但是我仍然希望保留llm的参与，更倾向于扩大这个llm发挥的空间。



