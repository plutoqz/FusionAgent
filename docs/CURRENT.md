# Current Project Direction

Status: authoritative navigation, 2026-07-20.

This file defines which documents currently guide the project. Older plans,
freeze reports, evidence ledgers, maturity checks, scenario harness documents,
and staged summaries remain available for traceability, but they no longer
define the active research or application direction.

## Current Research Entry Points

The current research direction is product-contract knowledge graph design for
disaster-response data product delivery:

- `PROJECT.md` (highest-priority research charter)
- `docs/thesis/ontology_schema_v2.md`
- `docs/thesis/product_contract_spec.md`
- `docs/thesis/experiment_case_matrix.md`
- `docs/thesis/experiment_cases.json`
- `docs/thesis/experiment_gold.json` (held out from planners)
- `docs/thesis/stability_protocol.json`
- `docs/thesis/stability_and_audit_protocol.md`
- `docs/thesis/end_to_end_runtime_protocol.md`
- `docs/thesis/research_direction_guide_2026-07-09.md`

These files supersede older thesis framings centered on generic KG+LLM agent
claims, maturity freezes, paper evidence freezes, or scenario harness closure.

When these files disagree, `PROJECT.md` takes precedence. Any change to the
research scope, primary claims, experiment baselines, or LLM/KG responsibility
boundary must update `PROJECT.md` first.

## Current Branch Workflow

- `docs/branch-worktree-workflow.md`

The intended split is:

- `research/product-contract`: product-contract KG, ontology, planning context,
  gap declaration semantics, and experiment design.
- `app/autonomous-fusion`: future practical application work. The application
  implementation may move to a new repository and should not inherit the old
  harness-heavy structure by default.
- `main`: shared stable schemas, stable contracts, and promoted work only.

## Research Runtime Requirement

The research branch still needs to remain runnable for experiments, but the
runnable surface should be minimal and explicit. See:

- `docs/research-runtime-minimum.md`

The research runtime exists to validate ontology-backed planning and product
contract satisfaction. It should not preserve the old freeze/maturity harness
as the main proof path.

## Current Implementation Phase

Phase 1, decision schema and scoring validity, and Phase 2, five-baseline
completion, are implemented in:

- `schemas/product_contract_experiment.py`
- `scripts/run_product_contract_experiment.py`
- `tests/test_product_contract_experiment_runner.py`
- `schemas/product_contract_stability.py`
- `scripts/run_product_contract_stability.py`
- `tests/test_product_contract_stability_runner.py`

The active protocol uses priority tiers, structured delivery sets, grounded
layer decisions, planner gap proposals, and supersession plans. Planner gap
proposals are scored separately from deterministic final gap declarations.
Input-order variants are supported and covered by regression tests.

The runner now supports `fixed`, `kg_only`, `llm_only`,
`llm_capability_kg`, and `llm_full_contract_kg`. The three LLM modes share one
prompt, output schema, model interface, temperature, JSON response mode, and
repair policy. Their declared knowledge profiles are the only experimental
context difference.

Phase 3 infrastructure is now implemented. The frozen protocol is stored in
`docs/thesis/stability_protocol.json`, with its human-readable explanation in
`docs/thesis/stability_and_audit_protocol.md`. Six-case and repeated-C02
development batches have completed with hash-chained audit records.

Phase 4 now has a minimum end-to-end implementation. The experiment runner
explicitly separates `planning_only` and `end_to_end`; the latter connects
planner-selected layers and sources to source materialization, existing domain
fusion runners, the real quality gate, and artifact-registry writeback. C02,
C04, and C06 have development coverage with real vector artifacts, but not yet
with frozen external-data evidence.

The next actions are to commit the protocol, run the formal 150-run Phase 3
matrix from a clean worktree, and execute durable external-data end-to-end runs
for C02, C04, and C06. Development batches remain ineligible for research
claims.

## Historical Material

The following locations are historical unless a current entry point explicitly
references a file for background:

- `docs/superpowers/plans/**`
- `docs/superpowers/specs/**`
- `docs/pasted/**`
- `docs/v2-operations.md`
- `docs/no-ui-agent-operations.md`
- `docs/local-direct-run.md`
- `docs/windows-local-runtime.md`
- `docs/demo/**`

Historical means:

- useful for provenance;
- useful for mining old implementation details;
- not authoritative for current research claims;
- not a required template for future application engineering;
- not a reason to keep the old scenario/freeze/maturity harness as the default
  path.

## Current Document Policy

Plan-like and staged-summary documents should be treated as historical once the
work they describe is complete or superseded. New planning documents should be
short-lived and either:

- promoted into one of the current research entry points; or
- moved/marked as `pasted`, `done`, `historical`, or `superseded`.

Do not create a new long-lived plan hierarchy that competes with the thesis
entry points above.

## Application Direction

Future application work should be allowed to start from a clean near-linear
pipeline:

```text
intent understanding
-> area resolution
-> data download/materialization
-> algorithm invocation
-> result checks
-> simple report
```

The application path should not begin by preserving:

- scenario regression harnesses;
- paper freeze pipelines;
- no-UI maturity checks;
- large evidence ledgers;
- complex planner/healing loops;
- full Neo4j-backed orchestration.

Those may be reintroduced only when the linear pipeline demonstrates a concrete
need for them.
