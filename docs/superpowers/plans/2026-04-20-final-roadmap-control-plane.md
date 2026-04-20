# Final Roadmap Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the Phase A control plane that turns FusionAgent's final-goal gaps, evidence, and long-chain execution route into durable project documents.

**Architecture:** Keep Phase A as documentation and evidence infrastructure, not runtime code. The control plane is split into a gap matrix, an evidence ledger, and a long-chain decision roadmap, with README pointers so future implementation phases can use these files as the starting gate.

**Tech Stack:** Markdown, existing pytest verification, existing superpowers plan/spec folders

**Completion Status:** Completed on 2026-04-20 in branch `codex/final-roadmap-phase-a`. Baseline and final verification: `python -m pytest -q` passed with `158 passed, 1 skipped, 6 warnings`.

---

## File Map

- Create: `docs/superpowers/specs/2026-04-20-final-gap-matrix.md`
  Responsibility: define the remaining final-goal gaps, why each matters, current evidence, recommended phase, risk, and gate.
- Create: `docs/superpowers/specs/2026-04-20-evidence-ledger.md`
  Responsibility: index durable evidence artifacts, verification commands, supported claims, and evidence gaps.
- Create: `docs/superpowers/specs/2026-04-20-long-chain-decision-roadmap.md`
  Responsibility: define the longest currently reasonable execution chain and the gate logic between phases.
- Modify: `README.md`
  Responsibility: make the Phase A control plane discoverable from the main project entry point.

---

## Task 1: Establish Phase A Control Plane Scope

**Files:**
- Create: `docs/superpowers/specs/2026-04-20-final-gap-matrix.md`
- Create: `docs/superpowers/specs/2026-04-20-evidence-ledger.md`
- Create: `docs/superpowers/specs/2026-04-20-long-chain-decision-roadmap.md`

- [x] **Step 1: Record the final-goal interpretation**

Use this definition consistently across all Phase A documents:

```text
FusionAgent's final target is a disaster-response geospatial data fusion agent that accepts natural-language or scenario-triggered requests and, under KG and runtime constraints, performs task understanding, data-source selection, workflow planning, parameter binding, input acquisition, fusion execution, failure repair/replanning, artifact output, and auditable evidence writeback.
```

- [x] **Step 2: Split the control plane into three documents**

Create:

```text
docs/superpowers/specs/2026-04-20-final-gap-matrix.md
docs/superpowers/specs/2026-04-20-evidence-ledger.md
docs/superpowers/specs/2026-04-20-long-chain-decision-roadmap.md
```

Each document must be useful on its own, but the three documents must agree on the same phase identifiers:

```text
A. Final Gap Matrix + Evidence Ledger
B. Evaluation Contract + Thesis Claim Lock
C. Full Replan Loop V1
D. Durable Learning -> Policy Hints V1
E. Minimum Research Ontology Closure
F. One New Data/Task Vertical Slice
G. Experiment Matrix + Paper Evidence Freeze
H. Thin Productization / Operator Surface
```

- [x] **Step 3: Keep Phase A non-invasive**

Do not change runtime code, tests, schemas, KG models, or scripts in this phase. Phase A is allowed to update documentation only.

## Task 2: Build Final Gap Matrix

**Files:**
- Create: `docs/superpowers/specs/2026-04-20-final-gap-matrix.md`

- [x] **Step 1: Add the gap table**

The matrix must include these gaps:

```text
G1: full replan loop
G2: durable learning used by planning/policy
G3: executable/research ontology closure
G4: search-space expansion beyond building/road
G5: manual-only source/provider gaps
G6: experiment matrix and thesis evidence freeze
G7: productization and operator surface
G8: deployment/observability hardening
```

- [x] **Step 2: Add decision gates**

For every gap, record:

```text
final-goal relevance
current evidence
recommended phase
risk level
gate condition
```

- [x] **Step 3: Preserve scope discipline**

The matrix must explicitly state that Phase A does not authorize implementing all gaps at once. It prioritizes Phase B and Phase C next.

## Task 3: Build Evidence Ledger

**Files:**
- Create: `docs/superpowers/specs/2026-04-20-evidence-ledger.md`

- [x] **Step 1: Record repository verification evidence**

Include:

```text
python -m pytest -q
158 passed, 1 skipped, 6 warnings
```

Also record the warning profile as known non-blocking baseline noise from pyproj/numpy deprecations in building adapter tests.

- [x] **Step 2: Index roadmap and benchmark artifacts**

The ledger must reference:

```text
README.md
docs/v2-operations.md
docs/local-direct-run.md
docs/superpowers/plans/*.md
docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json
docs/superpowers/specs/2026-04-16-building-micro-msft-fresh-checkout-result.json
scripts/eval_harness.py
scripts/smoke_agentic_region.py
```

- [x] **Step 3: Classify evidence durability**

Use these durability labels:

```text
strong
medium
weak
missing
```

## Task 4: Build Long-Chain Decision Roadmap

**Files:**
- Create: `docs/superpowers/specs/2026-04-20-long-chain-decision-roadmap.md`

- [x] **Step 1: Define the longest reasonable current route**

Record the route:

```text
A -> B -> C -> D -> E -> F -> G -> H
```

Mark A-D as high-confidence, E-H as conditional.

- [x] **Step 2: Add gate review rules**

Each phase must have:

```text
entry condition
minimum deliverable
verification
continue condition
stop or pivot condition
```

- [x] **Step 3: Add execution rules**

Record that future implementation phases should use:

```text
codex/* branches
global worktrees under C:\Users\QDX\.config\superpowers\worktrees\fusionAgent
subagents for independent read-only inventory or bounded implementation tasks
verification-before-completion before any completion claim
finishing-a-development-branch before merge/push/cleanup decisions
```

## Task 5: Make Control Plane Discoverable

**Files:**
- Modify: `README.md`

- [x] **Step 1: Add a control-plane section**

Add a concise README section pointing to the three Phase A documents.

- [x] **Step 2: Keep current positioning intact**

Do not weaken or rewrite the existing README statement that engineering MVP and research prototype are reached, while final product shape is not.

## Task 6: Verify And Close Phase A

**Files:**
- Modify: `docs/superpowers/plans/2026-04-20-final-roadmap-control-plane.md`

- [x] **Step 1: Run full tests**

Run:

```powershell
python -m pytest -q
```

Expected:

```text
158 passed, 1 skipped, 6 warnings
```

- [x] **Step 2: Scan Phase A docs for placeholders**

Run:

```powershell
Select-String -LiteralPath docs/superpowers/specs/2026-04-20-final-gap-matrix.md,docs/superpowers/specs/2026-04-20-evidence-ledger.md,docs/superpowers/specs/2026-04-20-long-chain-decision-roadmap.md -Pattern 'placeholder'
```

Expected: no matches.

- [x] **Step 3: Commit**

Run:

```powershell
git add README.md docs/superpowers/plans/2026-04-20-final-roadmap-control-plane.md docs/superpowers/specs/2026-04-20-final-gap-matrix.md docs/superpowers/specs/2026-04-20-evidence-ledger.md docs/superpowers/specs/2026-04-20-long-chain-decision-roadmap.md
git commit -m "docs: add final roadmap control plane"
```

## Self-Review

- Spec coverage: Phase A covers final-goal gap matrix, evidence ledger, long-chain route, decision gates, and README discoverability.
- Placeholder scan: The plan contains no incomplete execution steps and no vague handoffs.
- Type consistency: Phase identifiers A-H are consistent across all Phase A documents.
