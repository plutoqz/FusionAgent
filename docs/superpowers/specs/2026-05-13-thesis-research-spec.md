# Thesis Research Specification

## Position Lock

FusionAgent is studied here as a bounded, KG-grounded geospatial vector-fusion runtime for disaster-response workflows. The thesis object is the executable runtime itself, not a general-purpose agent, not a frontend product, and not a detached data-engineering pipeline.

The live runtime boundary stays aligned with the current execution contract:

- stable shared-runtime tasks: `building`, `road`, `water`, and bounded `poi`
- shared evidence contract: `run.json`, `plan.json`, `validation.json`, `audit.jsonl`, and the artifact bundle
- large-AOI `OSM + single-reference` tiled building path is part of the shared runtime claim
- multi-source and raster-assisted building flows remain scale-validation `research_utility`
- `trajectory-to-road` remains reservation-only

## Research Questions

### RQ1

Does `KG-decomposed algorithm primitives` plus runtime validation improve executable planning validity and end-to-end execution success compared with weaker or less structured runtime variants?

Live claim mapping: `C1`

### RQ2

Does `contract-bounded planning and execution with healing` improve robustness under failure without letting the runtime drift outside its bounded acceptance rules?

Live claim mapping: `C3`

### RQ3

Does the `auditable evidence contract` materially improve inspectability, reproducibility, and paper-evidence curation compared with result-only output?

Live claim mapping: `C2`

## Primary Thesis Lines

| Thesis line | Live claim ids | Canonical evidence anchor |
| --- | --- | --- |
| KG-grounded executable planning | `C1` | `docs/superpowers/specs/2026-04-20-evaluation-contract-claim-lock.md`, `docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json`, `docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md` |
| bounded healing and replan | `C3` | `docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json` row `c3_replan_fault_recovery`, related freeze rows, focused recovery tests |
| evidence-first runtime | `C2` | `docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json`, `docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md`, operator inspection and comparison APIs |

## Supporting But Non-Primary Claims

- `C5`: bounded task-driven AOI and source acquisition improve reproducibility for supported official sources.
- `C7`: bounded extensibility is demonstrated only for the current `building / road / water / bounded poi` slices.
- `C4`: durable learning remains supporting runtime evidence for bounded policy hints, not the thesis centerpiece.

## Explicit Non-Claims

- no final-product UI claim
- no production `7x24` operations claim
- no executable `trajectory-to-road` claim
- no autonomous self-evolution claim
- no live external event-feed integration claim
- no Benin-only capability claim
- no promotion of multi-source or raster-assisted building validation utilities into the shared runtime story without new frozen evidence

## Canonical Live Sources

The thesis narrative must grow from these live sources instead of historical roadmap intent:

- `docs/superpowers/specs/2026-04-20-evaluation-contract-claim-lock.md`
- `docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json`
- `docs/superpowers/specs/2026-04-21-paper-evidence-freeze.json`
- `docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md`
- `docs/superpowers/specs/2026-05-06-capability-inventory.md`
- `docs/superpowers/specs/2026-05-06-related-work-gap-matrix.json`
- `docs/superpowers/specs/2026-05-09-kg-closure-gates.md`
- `docs/superpowers/specs/2026-05-10-kg-gates-evidence-summary.md`

If a thesis statement cannot be traced back to those live docs, checked-in tests, or frozen run artifacts, it stays out of the promoted thesis claim set.
