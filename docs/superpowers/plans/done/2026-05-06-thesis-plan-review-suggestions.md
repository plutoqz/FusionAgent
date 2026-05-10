# FusionAgent Thesis Plan Review: Suggested Refinements

> Review of `2026-05-06-fusionagent-thesis-research-design-roadmap.md`
> Focus areas: RQ1 experimental design, statistical framework, metric formalization, failure injection taxonomy, LLM version strategy.

---

## 1. RQ1 Experimental Design: Dimension Confounding Fix

### Current Issue

The three-level comparison (A0: no KG → A1: KG retrieval only → A2: full decomposition) conflates two distinct interventions: "having KG-structured algorithm knowledge" and "granularity of primitive decomposition." Without explicitly separating these, a reviewer can challenge whether A2's gains come from the KG itself or from the decomposition.

### Suggested Fix

Keep the three-level design but add an explicit two-step comparison logic in the Experiment Group A description:

| Comparison | Isolated Variable | Question Answered |
|---|---|---|
| A0 → A1 | Presence/absence of KG-structured algorithm knowledge | Value of KG itself |
| A1 → A2 | Coarse vs. fine-grained primitive decomposition | Incremental value of decomposition granularity |

### A1 Baseline Specification

Define A1 precisely to ensure a meaningful contrast with A2:

> A1: KG contains algorithm entries registered as **monolithic single-node handlers** — no workflow pattern decomposition, no per-step parameter specs, no pre/post-condition constraints. The planner can look up *which* algorithm to call but cannot reason about intermediate steps, partial results, or parameter-level binding.

This ensures A1→A2 measures the real value of decomposition, not a strawman.

### Recommended Text to Add to the Plan

```markdown
### RQ1 Comparison Logic

A0→A1 isolates the value of KG-structured algorithm knowledge.
A1→A2 isolates the incremental value of primitive decomposition granularity.
Together they answer RQ1: whether KG-decomposed primitives improve planning validity
and execution success beyond what either KG alone or no-KG approaches can achieve.
```

---

## 2. Statistical Analysis Framework

### 2.1 Sample Size

Each experiment group requires at least 30 independent test cases for meaningful statistical inference. Cases should cover all four supported task types (building, road, water, poi), with a minimum of 5 cases per type.

Target case inventory across the full baseline/ablation matrix:

| Layer | Cases | Notes |
|---|---|---|
| Core test case pool | 30–40 | Each case has frozen inputs, expected task type, golden output snapshot |
| Per-configuration runs | 30–40 × N | Same cases run under each configuration (paired design) |
| Failure injection cases | 30 | 6 types × 5 cases, mixed with normal cases |

### 2.2 Statistical Tests by Metric Type

| Metric Type | Examples | Recommended Test |
|---|---|---|
| Binary success/failure rates | executable-plan rate, repair success rate, run success rate | McNemar test (paired binary outcomes) |
| Rate/ratio metrics (non-normal) | unknown-algorithm rate, invalid-step rate, silent failure rate | Wilcoxon signed-rank test |
| Continuous scores (approximately normal) | grounding completeness score, artifact trace completeness | Paired t-test; fallback to Wilcoxon if normality violated |

### 2.3 Multiple Comparison Correction

Three research questions (RQ1, RQ2, RQ3) each produce multiple metrics tested on the same case pool.

- **Primary correction**: Bonferroni adjustment across the 3 RQs (α = 0.05/3 ≈ 0.0167)
- **Alternative (less conservative)**: Holm-Bonferroni step-down procedure
- **Within each RQ**: Report raw p-values alongside corrected thresholds; clearly distinguish primary metrics (used for hypothesis testing) from secondary metrics (exploratory/descriptive)

### 2.4 Effect Sizes

Report effect sizes alongside p-values for all primary comparisons:

| Metric Type | Effect Size | Interpretation |
|---|---|---|
| Proportions | Cohen's h | Small=0.2, Medium=0.5, Large=0.8 |
| Continuous metrics | Cohen's d or Cliff's δ (non-parametric) | Small=0.2, Medium=0.5, Large=0.8 |

### 2.5 Pre-registration

To prevent p-hacking, freeze the experiment protocol before running any comparisons:
- Lock the case pool
- Lock the metric computation code
- Lock the comparison sequence
- Document any post-hoc analyses as exploratory

---

## 3. Metric Operationalization

### 3.1 Grounding Completeness Score

For each plan step `s`:

```
g1(s): s references a KG-registered algorithm primitive node? (0/1)
g2(s): parameter bindings satisfy the primitive's parameter spec? (0/1)
g3(s): input/output data types consistent with the data type ontology? (0/1)

step_score(s) = (g1 + g2 + g3) / 3
run_grounding_score = mean(step_score(s) for s in plan.steps)
```

Report: mean ± std across all runs in the configuration.

### 3.2 Artifact Trace Completeness

For each run, check 5 expected artifacts:

```
items = [run.json, plan.json, validation.json, audit.jsonl, artifact_bundle/]

For each item:
  exists: file/directory is present on disk
  non_empty: file size > 0, or directory contains ≥1 file

completeness = count(item.exists and item.non_empty for item in items) / 5
```

Report: mean ± std across all runs.

### 3.3 Evidence Freeze Reproducibility

Run the same frozen inputs twice independently (R1, R2). Compare three dimensions:

| Dimension | Metric | Method |
|---|---|---|
| Plan consistency | Step sequence match rate | Sequence alignment: (# matching steps) / max(len(R1), len(R2)) |
| Output fidelity | Per-record Jaccard or F1 | Compare fused output geometries/attributes |
| Audit consistency | Event type match rate | Set comparison of event types in audit.jsonl |

### 3.4 Silent Failure Rate — Replacement

"Silent failure rate" cannot be reliably detected automatically (by definition, the system reports success). Replace with two measurable proxies:

- **Output validity rate**: (# runs where output passes schema validation AND sanity checks) / (total # runs). Sanity checks are domain-specific (e.g., "fused building count > 0 and < 3× max input source count").
- **Unhandled exception rate**: (# runs terminated by uncaught exception) / (total # runs). Configurations with healing should show a lower rate.

### 3.5 Operator-Debug Turnaround Proxy — Replacement

A full human-subject study is likely infeasible within a 6–8 month thesis window. Replace with automated proxies:

- **Failure-to-diagnosis step count**: number of audit events from first failure signal to first explicit error classification entry in audit.jsonl. Lower = faster diagnosis.
- **Root-cause visibility rate**: proportion of failed steps whose audit entry contains a machine-readable root cause tag (e.g., `PARAM_OUT_OF_RANGE`, `SOURCE_MISSING`, `ALGO_TIMEOUT`).

---

## 4. Failure Injection Taxonomy

### 4.1 Failure Categories

| # | Category | Injection Mechanism | Expected Healing | Cases |
|---|---|---|---|---|
| F1 | Input absence | Remove or rename a source data file | Replan with alternative source or report SOURCE_MISSING | 5 |
| F2 | Input corruption | Replace source with wrong-CRS or wrong-encoding file | Validator detects CRS/encoding mismatch → replan | 5 |
| F3 | Parameter violation | Inject parameter value outside the algorithm's declared valid range | Validator rejects → parameter healing or replan | 5 |
| F4 | Algorithm runtime error | Modify environment so algorithm call throws (e.g., missing dependency) | Executor captures exception → retry or skip with audit entry | 5 |
| F5 | Resource exhaustion | Set tight memory/timeout limits for specific steps | Timeout detection → tile splitting or graceful degradation | 5 |
| F6 | Silent wrong output | Algorithm returns technically valid but semantically empty/nonsensical result | Post-execution sanity check → flag in audit as SUSPECT_OUTPUT | 5 |
| **Total** | | | | **30** |

### 4.2 Injection Protocol

1. For each failure case, define: the target step, the injection mechanism, the expected healing path, and the success criterion.
2. Use a dedicated injection harness (e.g., a pytest fixture that wraps the executor and injects failures deterministically based on a case manifest).
3. Each injection case must be reproducible — re-running with the same manifest produces the same failure.

### 4.3 Experiment B Test Set Composition

Mix injected and normal cases so the system cannot distinguish them a priori:

| Subset | Count | Purpose |
|---|---|---|
| Normal cases (no injection) | 20 | Measure false-positive healing and silent failure rate |
| Injected failure cases | 30 | Measure repair success rate and healing behavior |
| **Total per configuration** | **50** | |

### 4.4 Healing Success Criteria

| Healing Path | Success Criterion |
|---|---|
| Retry | Same step re-executes and produces valid output on retry N ≤ 3 |
| Replan | Planner generates alternative steps that successfully execute |
| Graceful degradation | Step is skipped with explicit audit entry; run continues and produces partial but valid output |
| Explicit failure | Run terminates with machine-readable error classification (not a crash) |

A case where the run crashes or hangs without audit entry is a **healing failure** regardless.

---

## 5. LLM Version Strategy

### 5.1 Primary Experiment LLM

- **Model**: Claude Sonnet 4.5 (already integrated in the codebase) or GPT-4o-2024-11-20
- **Temperature**: 0 for all experiments (maximize determinism)
- **Documentation**: Record full model identifier, API endpoint, call date range, and all inference hyperparameters in the thesis Experimental Setup section

### 5.2 Cross-Model Ablation (Promoted to Mandatory)

The current plan lists ablation E (weak-LLM substitution) as optional. This should be **mandatory**:

- Re-run the core comparisons (RQ1 A0/A1/A2 and RQ2 B0/B1) on at least **2 model families** (e.g., Claude Sonnet + GPT-4o)
- Purpose: demonstrate that the system architecture improvements (KG decomposition, healing loop) produce gains *independent of LLM quality*, not merely because a stronger LLM was used

### 5.3 Planner Sensitivity Analysis (Extended Ablation)

Run the same experiment across 3 capability tiers within a single model family:

| Tier | Example (Claude family) | Purpose |
|---|---|---|
| Strong | Opus 4.5 | Upper-bound planner quality |
| Medium | Sonnet 4.5 | Primary experiment LLM |
| Weak | Haiku 4.5 | Stress test: does KG structure compensate for weaker planning? |

If A2 (full FusionAgent) under Haiku still outperforms A0 (no KG) under Opus, this is a strong argument that the KG structure itself is doing meaningful work.

### 5.4 Reproducibility Commitments

- Freeze all LLM prompts in the thesis appendix
- Record all LLM API call parameters (model, temperature, max_tokens, etc.)
- Archive the exact model version identifier (or snapshot date for continuously updated models)
- Acknowledge that LLM behavior drift is a limitation in the Threats to Validity section

---

## 6. Additional Gap: Threats to Validity

The current plan lacks a threats-to-validity framework. Add before the timeline section:

### Internal Validity
- Are metrics measuring what they claim? (addressed by formal operationalization in §3)
- Is the LLM a confound? (addressed by cross-model ablation in §5)
- Are test cases representative? (addressed by case pool design in §2.1)

### External Validity
- Do results generalize beyond the four task types (building/road/water/poi)?
- Do results generalize beyond the specific geographic regions in the case pool?
- Do results depend on the specific LLM version used?

### Construct Validity
- Does "executable-plan rate" actually capture planning validity?
- Does "grounding completeness score" actually capture explainability?
- Does "artifact trace completeness" actually capture auditability?

### Recommended Text

```markdown
## Threats to Validity

### Internal Validity
- LLM non-determinism: mitigated by temperature=0 and cross-model replication
- Metric construct validity: each metric is formally defined with an operational computation
- Case selection bias: cases are sampled across all four supported task types

### External Validity
- Geographic generalizability is limited to the regions represented in the case pool
- Task-type generalizability is limited to building/road/water/poi
- LLM version drift means exact numbers may not replicate on future model versions

### Construct Validity
- We acknowledge that "grounding completeness" and "artifact trace completeness" are
  proxy measures for explainability and auditability, not direct measures of human understanding
- Where human judgment would be the gold standard (e.g., operator-debug turnaround),
  we report automated proxies and note the limitation
```

---

## 7. Summary of Recommended Document Changes

| # | Addition | Priority |
|---|---|---|
| 1 | RQ1 two-step comparison logic (A0→A1 / A1→A2) | High |
| 2 | Statistical analysis plan (sample size, tests, correction, effect sizes) | High |
| 3 | Formal metric definitions (grounding score, trace completeness, etc.) | High |
| 4 | Failure injection taxonomy (6 categories × 5 cases) | High |
| 5 | LLM freeze + mandatory cross-model ablation + sensitivity analysis | High |
| 6 | Threats to validity section | Medium |
| 7 | Silent failure rate and operator-debug proxy replacements | Medium |
