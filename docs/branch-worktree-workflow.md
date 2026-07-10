# Branch and Worktree Workflow

Status: active workflow, 2026-07-10.

This repository now uses one shared repository with multiple local worktrees:

```text
D:\code\FusionAgent
  branch: main
  role: shared integration baseline

D:\code\FusionAgent-worktrees\app
  branch: app/autonomous-fusion
  role: application-oriented autonomous fusion implementation

D:\code\FusionAgent-worktrees\research
  branch: research/product-contract
  role: research-oriented product-contract KG and LLM orchestration work
```

## Working Rules

### Main Worktree

Use `D:\code\FusionAgent` for shared, stable changes only:

- shared schemas
- shared output JSON contracts
- documentation that both branches should follow
- stable code promoted from app or research branches

Do not use `main` for exploratory app/runtime fixes or research-only prompt/schema experiments.

### App Worktree

Use `D:\code\FusionAgent-worktrees\app` for fast application work:

- fixed-source autonomous fusion flow
- source acquisition and caching
- runner stability
- failure recovery
- batch execution
- practical report generation

The app branch may initially use deterministic rules, but it should emit the shared artifacts:

```text
product_contract.json
planning_decision.json
resource_regime.json
quality_gate_result.json
gap_declaration.json
evidence_trace.json
delivery_manifest.json
run_report.md/html/pdf
```

### Research Worktree

Use `D:\code\FusionAgent-worktrees\research` for research work:

- product-contract KG
- disaster context constraints
- KG-constrained LLM orchestration
- planning rationale
- experiment case matrix
- baseline comparison and scoring rubric
- gap declaration semantics

The research branch may use simulated or fixed experiment cases before full runtime integration, but it must stay compatible with the shared JSON contracts.

## Promotion Flow

Do not merge app and research branches directly into each other.

Preferred flow:

```text
main
  -> merge/sync into app
  -> merge/sync into research

app stable runtime capability
  -> main

research stable contract/evaluation capability
  -> main
```

If a branch discovers that a shared schema must change:

1. Pause branch-specific work.
2. Make the schema/documentation change in `main`.
3. Commit it on `main`.
4. Merge `main` into both `app/autonomous-fusion` and `research/product-contract`.
5. Continue branch work.

## Current Caution

At the time this workflow was created, `main` still had unrelated uncommitted code/test/tmp changes that predated the document cleanup. They were intentionally not included in the shared documentation commit.

Before doing code work in `main`, inspect:

```powershell
git status --short --branch
```

Prefer doing new implementation work in the clean app/research worktrees.

