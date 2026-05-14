# Final Gap Matrix

## Purpose

This document defines the remaining distance between the current FusionAgent repository and the final system target.

Final system target:

```text
FusionAgent is a disaster-response geospatial data fusion agent that accepts natural-language or scenario-triggered requests and, under KG and runtime constraints, performs task understanding, data-source selection, workflow planning, parameter binding, input acquisition, fusion execution, failure repair/replanning, artifact output, and auditable evidence writeback.
```

Current status:

- Engineering MVP: reached.
- Research prototype: reached.
- Final product shape: not reached.
- Current v2 roadmap scope: complete for the previously defined phases.
- Next work class: define and execute the next research/product iteration without losing evidence discipline.

## Phase Vocabulary

| Phase | Name | Confidence Now | Role |
| --- | --- | --- | --- |
| A | Final Gap Matrix + Evidence Ledger | High | Establish control plane and evidence inventory |
| B | Evaluation Contract + Thesis Claim Lock | High | Freeze what the system must prove |
| C | Full Replan Loop V1 | High | Close the most important runtime intelligence gap |
| D | Durable Learning -> Policy Hints V1 | High | Make stored experience operationally consumable |
| E | Minimum Research Ontology Closure | Medium | Close the smallest useful executable/research ontology gap |
| F | One New Data/Task Vertical Slice | Medium | Prove extensibility beyond current building/road center |
| G | Experiment Matrix + Paper Evidence Freeze | Medium | Produce paper-grade comparative evidence |
| H | Thin Productization / Operator Surface | Conditional | Add only the product shell justified by evidence and deadline |

## Control Gap Before Implementation

Before implementing more runtime features, Phase B should lock the evaluation contract. Current evidence is strong for an MVP, but paper-grade claims still need an explicit mapping from claims to metrics, baselines, datasets, and archived artifacts.

Gate:

```text
Do not start Phase C until Phase B states which claims require full replan evidence and which claims can be supported by current healing/fallback behavior.
```

## Gap Matrix

| ID | Gap | Why It Matters | Current Evidence | Recommended Phase | Risk | Gate |
| --- | --- | --- | --- | --- | --- | --- |
| G1 | Full replan loop is incomplete | The claimed agent mode includes reactive healing; a true replan loop is the clearest runtime proof that FusionAgent is more than a static script runner | README and local docs still list incomplete `replan`; repair/healing tests exist, but they do not prove plan replacement and acceptance gates | C | Medium | Continue only if Phase B confirms replan is a thesis-critical claim; otherwise keep current healing as the scoped claim |
| G2 | Durable learning is recorded but not yet a policy input | The final target includes memory and evidence writeback that improves future decisions; recording without consumption is not enough for the strongest claim | `README.md` says durable learning is first-pass; repository aggregation and planner summary exist | D | Medium | Continue if Phase C produces stable decision records that can be summarized without hidden state |
| G3 | Executable ontology and research ontology remain partially separated | The paper needs a defensible bridge between the complete ontology design and what the runtime actually uses | `文档/GeoFusion 知识图谱本体模式层设计方案.md` explicitly distinguishes implemented MVP subset from target-state classes | E | Medium | Continue if Phase B identifies `OutputRequirement`, `QoSPolicy`, or `ScenarioProfile` as required for claims or experiments |
| G4 | Search space is still concentrated on `building` and `road` | A final agent should be extensible across more task/data categories; current coverage may look like a narrow demo if not framed well | README states search space remains concentrated on `building` and `road`; current tests cover many runtime paths but mostly these task types | F | Medium | Continue only after C/D/E are stable enough that a new vertical slice will test architecture rather than mask core instability |
| G5 | Some source/provider paths remain manual-only | Automatic input acquisition is part of the final target; manual-only providers limit reproducibility and operator autonomy | README and operations docs call out `raw.google.building` and local reference/Excel inputs as manual-only | F | Medium | Pick exactly one provider/task slice; do not open multiple source families in the same phase |
| G6 | Experiment matrix is not frozen as a paper artifact | The system has many pieces of evidence, but final research claims need a stable baseline matrix and traceable run artifacts | `scripts/eval_harness.py`, manifest JSON, benchmark result JSON, and tests exist; they are not yet assembled into one final experiment contract | B then G | Medium | Phase B must define claims and metrics before Phase G runs or freezes final evidence |
| G7 | Operator-facing productization is thin | Final product shape needs a human-usable operational layer; current API inspection is useful but narrow | `docs/v2-operations.md` documents inspection and comparison endpoints; no independent frontend product exists | H | Medium to High | Defer until G shows whether a thin operator surface is needed for demonstration or paper narrative |
| G8 | Deployment and observability remain prototype-grade | Server-level reliability, monitoring, and operational runbooks matter for product claims | Docker Compose and local scripts exist; README and deployment docs frame current emphasis as local MVP | H or later | High | Do not prioritize before thesis-critical runtime and evidence gaps unless the final deliverable changes to production deployment |
| G9 | Scenario-driven event autonomy is under-proven | The final target includes scenario-triggered requests, not only direct user task requests | Dual-entry architecture is documented and task bundles exist, but current strongest run evidence is task-driven or API-submitted | B then E or F | Medium | If Phase B keeps scenario-driven claims in scope, add one event-trigger scenario proof before paper evidence freeze |

## Immediate Priorities

The next recommended sequence is:

```text
A -> B -> C -> D
```

Reasons:

- A turns scattered status into durable control-plane documents.
- B prevents implementation from drifting away from thesis/product evidence needs.
- C closes the largest explicit runtime intelligence gap.
- D makes the existing durable-learning foundation operational without jumping to speculative auto-tuning.

## Deferred Decisions

These decisions are intentionally not locked by Phase A:

- Whether Phase E should implement `OutputRequirement`, `QoSPolicy`, or deeper `ScenarioProfile` first.
- Whether Phase F should use `raw.google.building`, `water`, `POI`, or another vertical slice.
- Whether scenario-driven proof should be an ontology slice, a trigger/orchestration slice, or part of the final experiment matrix.
- Whether Phase H should be an API-only operator workflow, a thin dashboard, or a larger product UI.

These must be decided by gates after Phase B-D evidence is available.

## Scope Guardrails

- Do not implement all gaps at once.
- Do not expand ontology before the evaluation contract says which concepts matter.
- Do not add new data/task families before the replan and learning claims are stable.
- Do not build a broad frontend before the paper-grade runtime evidence is frozen.
- Treat every future phase as a separate branch and plan.
