# Evaluation Contract And Thesis Claim Lock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lock the next evaluation contract so future implementation is driven by provable thesis/product claims instead of opportunistic feature expansion.

**Architecture:** Keep Phase B as a documentation and decision-gate phase. Create one claim-lock specification that maps claims to metrics, baselines, datasets, verification commands, current evidence, missing evidence, and the next implementation phases it authorizes.

**Tech Stack:** Markdown, existing pytest verification, existing eval harness and benchmark manifest

**Completion Status:** Completed on 2026-04-20 in branch `codex/evaluation-contract-claim-lock`. Baseline and final verification: `python -m pytest -q` passed with `158 passed, 1 skipped, 6 warnings`.

---

## File Map

- Create: `docs/superpowers/specs/2026-04-20-evaluation-contract-claim-lock.md`
  Responsibility: define scoped claims, metrics, baselines, datasets, commands, missing evidence, and gates for Phase C-D.
- Modify: `README.md`
  Responsibility: make the Phase B evaluation contract discoverable from the main project entry point.
- Modify: `docs/superpowers/specs/2026-04-20-evidence-ledger.md`
  Responsibility: add the Phase B contract as the current claim/evaluation index.

---

## Task 1: Define Claim Scope

**Files:**
- Create: `docs/superpowers/specs/2026-04-20-evaluation-contract-claim-lock.md`

- [x] **Step 1: Add scoped claim classes**

Record these claim classes:

```text
C1: KG-constrained planning and validation
C2: Auditable execution and evidence trace
C3: Reactive healing and full replan V1
C4: Durable learning as policy hints
C5: Task-driven AOI and source acquisition
C6: Ontology/runtime alignment
C7: Extensibility beyond building/road
C8: Operator observability
```

- [x] **Step 2: Mark claim disposition**

For each claim, mark one of:

```text
in_scope_now
requires_next_phase
conditional
boundary_only
```

- [x] **Step 3: Lock Phase C decision**

State explicitly:

```text
Full Replan Loop V1 is required before FusionAgent can claim robust reactive healing beyond bounded repair/fallback behavior.
```

## Task 2: Define Metrics And Baselines

**Files:**
- Create: `docs/superpowers/specs/2026-04-20-evaluation-contract-claim-lock.md`

- [x] **Step 1: Add metrics**

Include:

```text
planning_validity_rate
execution_success_rate
recovery_success_rate
evidence_completeness_rate
reproducibility_status
runtime_duration_ms
artifact_validity
decision_trace_completeness
```

- [x] **Step 2: Add baseline matrix**

Include:

```text
full_system
kg_top_pattern_only
weak_llm_without_runtime_constraints
no_repair_or_replan
no_durable_learning_hints
manual_input_baseline
```

- [x] **Step 3: Classify feasibility**

Each baseline must state whether it is executable now, requires a harness switch, requires Phase C/D implementation, or remains narrative only.

## Task 3: Define Dataset And Command Contract

**Files:**
- Create: `docs/superpowers/specs/2026-04-20-evaluation-contract-claim-lock.md`

- [x] **Step 1: Add evaluation tiers**

Use the existing tiers:

```text
Tier 1: targeted tests
Tier 2: golden-case harness
Tier 3: real-data benchmark
Tier 4: fault-injection and ablation matrix
```

- [x] **Step 2: Add exact commands**

Include exact commands for:

```text
python -m pytest -q
python -m pytest -q tests/test_eval_harness.py tests/test_api_v2_integration.py tests/test_agent_run_service_enhancements.py
python scripts/eval_harness.py --base-url http://127.0.0.1:8000 --timeout 180 --case building_disaster_flood --case road_disaster_earthquake --output-json tmp/eval/fast-confidence-summary.json
python scripts/eval_harness.py --manifest docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json --case building_gitega_micro_msft_agent --base-url http://127.0.0.1:8010 --timeout 1200 --output-json tmp/eval/fresh-checkout-micro-msft.json
```

- [x] **Step 3: Clarify tracked versus untracked evidence**

State that raw `runs/`, cache, and large artifacts stay untracked unless explicitly curated, while summary JSON and paper-grade tables should be tracked under `docs/superpowers/specs/` or a later dedicated evidence folder.

## Task 4: Make Contract Discoverable

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-04-20-evidence-ledger.md`

- [x] **Step 1: Add README link**

Add `Evaluation Contract And Thesis Claim Lock` to the control-plane section.

- [x] **Step 2: Add ledger reference**

Add a row in the evidence ledger pointing to the Phase B claim/evaluation contract.

## Task 5: Verify And Commit

**Files:**
- Modify: `docs/superpowers/plans/2026-04-20-evaluation-contract-claim-lock.md`

- [x] **Step 1: Run full tests**

Run:

```powershell
python -m pytest -q
```

Expected:

```text
158 passed, 1 skipped, 6 warnings
```

- [x] **Step 2: Scan Phase B docs for unfinished markers**

Run:

```powershell
Select-String -LiteralPath docs/superpowers/specs/2026-04-20-evaluation-contract-claim-lock.md,docs/superpowers/plans/2026-04-20-evaluation-contract-claim-lock.md -Pattern 'unfinished-marker'
```

Expected: no matches.

- [x] **Step 3: Commit**

Run:

```powershell
git add README.md docs/superpowers/specs/2026-04-20-evidence-ledger.md docs/superpowers/specs/2026-04-20-evaluation-contract-claim-lock.md docs/superpowers/plans/2026-04-20-evaluation-contract-claim-lock.md
git commit -m "docs: lock evaluation contract and claims"
```

## Self-Review

- Spec coverage: Phase B covers claim scope, metrics, baselines, datasets, commands, evidence tracking, and C/D gates.
- Marker scan: The plan contains no incomplete execution steps.
- Type consistency: Claim IDs C1-C8 and phase IDs A-H are consistent with Phase A documents.
