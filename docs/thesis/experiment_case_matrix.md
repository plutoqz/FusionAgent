# Experiment Case Matrix

Status: Phase 1 protocol aligned, 2026-07-20.

This document defines the first research experiment cases. The cases test
product-contract satisfaction under combined disaster, resource, source, and
quality conditions. They are not demonstrations that merely prove the pipeline
can run.

Machine-readable planner inputs:

```text
docs/thesis/experiment_cases.json
```

Held-out structured evaluation labels:

```text
docs/thesis/experiment_gold.json
```

The planner may receive case inputs but must never receive gold fields. Exact
priority tiers, acceptable strategy identifiers, delivery expectations, and
expected gap proposals exist only in the held-out file and post-planning
evaluator.

## Baselines

The formal comparison target remains:

1. `fixed`
2. `kg_only`
3. `llm_only`
4. `llm_capability_kg`
5. `llm_full_contract_kg`

The minimum runner implements all five modes. The three LLM knowledge
conditions are:

- `llm_only`: common task observations, candidate IDs, and output protocol; no
  KG relations;
- `llm_capability_kg`: the same common context plus L3/L4 data-need, source,
  and algorithm capability relations;
- `llm_full_contract_kg`: the identical capability KG plus L1/L2/L6 disaster,
  product-contract, quality, degradation, evidence, and gap-rule knowledge.

All three LLM conditions use the same model, prompt, output schema,
temperature, JSON response mode, provider interface, and one explicit repair
retry. Exact capability KG content is identical between the capability and
full-contract conditions.

## Scoring Protocol

Machine-readable planner scoring includes:

- pairwise precedence accuracy across gold priority tiers;
- strategy ID match against an acceptable set;
- required initial, background, and not-delivered recall;
- invalid initial, background, and not-delivered rates;
- allowed delivery-mode accuracy;
- required supersession recall;
- planner gap proposal precision, recall, and F1;
- grounding validity;
- internal consistency;
- an aggregate score derived from these components.

Layers inside one priority tier are unordered. The final deterministic gap
declaration is a product-correctness artifact and is not substituted for the
planner's own gap proposal during scoring.

## Input-Order Variants

`--input-variant <int>` deterministically permutes all planner-visible repeated
collections, including required layers, data needs, sources, algorithms, and
quality gates. Semantic conclusions should remain stable across variants even
when serialized order changes.

## Formal Repetition Design

The frozen Phase 3 design uses five repetitions per case-planner pair and
assigns input variants `0, 1, 2, 3, 4` exactly once. The resulting 150-run
schedule is shuffled with a fixed seed before execution. Failed runs remain in
the denominator for success and failure rates; successful-score statistics do
not impute failed values.

The machine-readable protocol and audit rules are defined in:

```text
docs/thesis/stability_protocol.json
docs/thesis/stability_and_audit_protocol.md
```

## Case Template

Planner-visible case files contain only:

```text
case_id
title
scenario
aoi
resource_regime
required_layers
input_sources_status
```

Held-out gold files contain only post-planning labels:

```text
case_id
priority_tiers
acceptable_strategy_ids
delivery_expectations
expected_gap_proposals
```

## Initial Case Set

### C01 Earthquake: tight time, partial source availability

Tests progressive delivery when a usable building source is available but a
second higher-resolution source is delayed. Building, road, and optional POI
are in contract scope.

### C02 Flood: water and road dominate

Tests disaster-specific prioritization under stale or semantically mismatched
water sources, available roads, tight time, and an important building layer.

### C03 Wildfire: sparse built environment

Tests absence-aware planning when road data is available but optional building
and POI baselines are absent in the AOI.

### C04 Typhoon or storm: large AOI, coverage pressure

Tests progressive coverage when one road source is available and another is
delayed while compute and time remain constrained.

### C05 Source conflict: geometry-rich versus attribute-rich

Tests conflict-aware fusion and explicit quality risk when two building sources
offer incompatible strengths.

### C06 Fusion quality gate failure

Tests degraded fallback delivery when a usable road source exists but a second
reference source has failed quality checks.
