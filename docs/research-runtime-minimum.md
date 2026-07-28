# Research Runtime Minimum

Status: draft operating boundary, 2026-07-10.

The research branch must remain runnable enough to support experiments, but it
does not need to preserve the old harness-heavy proof system as the default
execution path.

## Purpose

The research runtime exists to test whether the product-contract KG improves
planning, delivery validation, and gap declaration under disaster-response data
production constraints.

It should support experiments such as:

- product contract generation from a disaster/task request;
- KG retrieval of data needs, sources, algorithms, quality gates, and gap rules;
- LLM or deterministic planner proposal under the same contract;
- execution or simulated execution of a bounded task;
- quality gate evaluation;
- evidence trace and gap declaration generation;
- baseline comparison against a fixed-rule planner or KG-only planner.

## Minimum Runnable Chain

The minimum research chain is:

```text
request
-> product_contract
-> planning_context
-> plan
-> execution_or_simulation
-> quality_gate_result
-> evidence_trace
-> gap_declaration
-> delivery_manifest
```

For early experiments, `execution_or_simulation` may be a controlled fixture.
The key research object is not raw algorithm performance; it is whether the
contract, KG constraints, and planner decision satisfy the product-delivery
semantics.

## Required Machine Outputs

Each experimental run should produce:

```text
product_contract.json
resource_regime.json
planning_context.json
planning_decision.json
quality_gate_result.json
evidence_trace.json
gap_declaration.json
delivery_manifest.json
experiment_summary.json
run_report.md
```

These are the current research outputs. Older files such as paper freeze
reports, no-UI maturity freezes, and large scenario evidence bundles are
historical unless explicitly selected as comparison material.

## Minimum Experiment Types

### Contract Satisfaction

Question:

```text
Given a disaster context and resource regime, can the system produce a data
product contract and determine whether the output satisfies it?
```

Required comparison:

- fixed rules;
- KG-only deterministic retrieval;
- LLM + product-contract KG.

### Resource-Constrained Planning

Question:

```text
Under weak network or short time budget, can the planner choose temporary
delivery, background completion, and gap declarations correctly?
```

Required output:

- selected acquisition strategy;
- declared degradation;
- gap declaration;
- rationale.

### Evidence and Gap Correctness

Question:

```text
Can every delivered product be accompanied by source, process, and quality
evidence, and can unmet requirements be explained as explicit gaps?
```

Required output:

- evidence trace;
- quality gate result;
- gap declaration;
- delivery manifest.

## What Is Out Of Scope For The Research Runtime

The research runtime does not need to keep these as default paths:

- scenario regression harness;
- no-UI maturity check;
- paper evidence freeze;
- national-scale evidence freeze;
- complex multi-phase proof matrices;
- full application workbench;
- Celery-based long-running orchestration;
- Neo4j as a required dependency for every experiment.

These can remain available as historical or optional tools, but they should not
define the current research path.

## Suggested Implementation Boundary

Prefer a small runner or test harness dedicated to product-contract experiments:

```text
scripts/run_product_contract_experiment.py
```

The runner should accept:

```text
--case <case_id>
--planner fixed|kg_only|llm_only|llm_capability_kg|llm_full_contract_kg
--output-dir <path>
```

The runner should load cases from:

```text
docs/thesis/experiment_case_matrix.md
```

or from a future machine-readable companion:

```text
docs/thesis/experiment_cases.json
```

The runner should avoid depending on old `docs/superpowers/specs/*freeze*`
artifacts except when an experiment explicitly uses them as historical baseline
evidence.

## Current Minimum Runner

The first minimum runner is now:

```powershell
python scripts/run_product_contract_experiment.py `
  --case C02 `
  --planner llm_full_contract_kg `
  --output-dir <output-dir>
```

The machine-readable cases live in:

```text
docs/thesis/experiment_cases.json
```

Supported planner modes:

```text
fixed
kg_only
llm_only
llm_capability_kg
llm_full_contract_kg
```

All three LLM modes call the configured OpenAI-compatible endpoint through the
same prompt, structured output schema, temperature, JSON response mode, and
explicit repair policy. They differ only in planner-visible knowledge:

```text
llm_only
  common task observations + candidate IDs + output protocol

llm_capability_kg
  common context + L3/L4 data/source/algorithm capability KG

llm_full_contract_kg
  identical capability KG + L1/L2/L6 disaster/product/quality contract KG
```

Returned decisions are grounded against the candidate layers, algorithms,
sources, delivery modes, gap facts, and internal consistency rules. Ungrounded
outputs fail closed and emit `planning_failure.json`; deterministic fallback is
not used to represent an LLM result.

Local credentials are read from `.env.local`, which is explicitly ignored by
Git. Gold labels are stored separately in `docs/thesis/experiment_gold.json`
and are loaded only after planning for offline evaluation. They are never added
to the planner context.

In the current Windows sandbox, pytest may not be able to write its cache under
the research worktree. Use:

```powershell
python -m pytest -q tests/test_product_contract_experiment_runner.py -p no:cacheprovider
```

## End-to-End Runtime Mode

Phase 4 adds an explicit execution mode without changing the default planning
experiment:

```powershell
python scripts/run_product_contract_experiment.py `
  --case C06 `
  --planner llm_full_contract_kg `
  --execution-mode end_to_end `
  --runtime-repo-root <declared-data-root> `
  --output-dir <output-dir>
```

Optional `--runtime-cache-dir`, `--runtime-artifact-index`, and `--target-crs`
arguments make the data repository and writeback locations explicit. When they
are omitted, cache and registry artifacts are stored under the run output and
the target CRS is derived from the AOI.

`planning_only` continues to derive controlled quality facts from the frozen
case observations. `end_to_end` never uses those simulated quality results. It
materializes only planner-selected sources whose observed status is usable,
executes an existing domain algorithm when its source contract is complete,
evaluates the actual vector artifact with `QualityGateService`, and registers
accepted outputs through `ArtifactRegistry`.

If only one selected source is usable and the planner permits a provisional or
degraded delivery, the runtime may emit
`runtime.single_source_passthrough.v1`. This is not reported as fusion: the
selected fusion algorithm is recorded as not executed, with an explicit
fallback reason and a single-source quality policy. Algorithm exceptions and
materialization failures remain failed runtime evidence; there is no simulated
fallback in end-to-end mode.

Additional end-to-end artifacts are:

```text
runtime_execution.json
runtime_artifact_index.json
runtime/<layer>/quality_report.json
runtime/<layer>/algorithm/*.gpkg
```

The water mapping is fixed at the execution boundary:

```text
water_type_1 -> water_polygon
water_type_2 -> waterways
```

See `docs/thesis/end_to_end_runtime_protocol.md` for the frozen development
contract and current evidence boundary.

## Repeated Stability Runner

Phase 3 repeated experiments use:

```text
scripts/run_product_contract_stability.py
```

The frozen formal protocol is:

```text
docs/thesis/stability_protocol.json
```

A development subset can be run with:

```powershell
python scripts/run_product_contract_stability.py `
  --scope development `
  --cases C02 `
  --planners fixed,kg_only,llm_only,llm_capability_kg,llm_full_contract_kg `
  --repetitions 2 `
  --output-dir <output-dir>
```

Formal mode executes the complete 150-run frozen matrix and requires a clean
Git worktree:

```powershell
python scripts/run_product_contract_stability.py `
  --scope formal `
  --output-dir <durable-output-dir>
```

The batch output contains `audit_ledger.jsonl`, `stability_summary.json`,
`audit_manifest.json`, a protocol snapshot, a deterministic schedule, an
implementation hash manifest, and per-run artifacts. `--resume` verifies the
existing hash chain and refuses to continue after implementation drift.
