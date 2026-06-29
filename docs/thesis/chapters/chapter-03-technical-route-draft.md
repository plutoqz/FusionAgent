# Chapter 3 Draft: Technical Route

## Runtime Overview

FusionAgent follows a bounded runtime route:

```text
user or scenario intent
  -> task and AOI interpretation
  -> KG-grounded retrieval and algorithm primitive selection
  -> parameter binding and source acquisition
  -> plan validation
  -> execution
  -> bounded healing or replan when allowed
  -> evidence writeback and operator inspection
```

The technical route is designed to make agentic decisions executable and auditable. The runtime does not merely return a fused dataset; it records the plan, validation result, execution trace, recovery decisions, and output artifact bundle.

## KG-Grounded Planning

The knowledge graph provides bounded task, source, algorithm, parameter, and contract context. Planning is treated as a constrained selection problem rather than open-ended text generation. The planner must choose task-compatible primitives and produce a plan that can survive validation before execution.

Key method points:

- task families are limited to `building`, `road`, `water`, and bounded `poi`
- unsupported or reserved tasks must fail closed
- decomposed algorithm primitives are preferred over opaque task-to-handler jumps
- KG fallback and validator decisions are evidence-bearing events

## Contract-Bounded Validation

Validation acts as the runtime gate between a proposed plan and executable work. It checks that the selected task, sources, parameters, and artifact expectations remain within the accepted runtime contract. This gate is central to `RQ1` and `RQ3` because it links planning validity to later evidence.

The chapter should present validation as a research mechanism, not merely defensive engineering:

- it prevents unsupported algorithm calls
- it separates planning success from execution success
- it creates auditable rejection or acceptance evidence
- it limits claim drift when the runtime encounters unsupported inputs

## Execution And Healing

Execution runs the validated workflow and records run artifacts. If bounded failure modes occur, the runtime may apply repair or replan logic. The important thesis point is not that the system can recover from every failure, but that allowed recovery is constrained, revisioned, and visible.

For `RQ2`, the method section should emphasize:

- recovery is bounded by policy and runtime contracts
- source-changing replans must refresh task-driven inputs
- plan revisions must remain inspectable
- unsupported recovery paths must fail closed rather than silently widening capability

## Evidence Contract

Every promoted run should expose:

- `run.json`
- `plan.json`
- `validation.json`
- `audit.jsonl`
- artifact bundle

This contract supports `RQ3` by making the workflow inspectable after execution. It also supports paper writing because frozen evidence can be traced back to machine-readable files instead of ad hoc screenshots or narrative summaries.

## Chapter To-Do

- Add a compact architecture figure or Mermaid diagram once the final section order is fixed.
- Cross-reference exact services and tests only in footnotes or appendix-style paragraphs.
- Keep multi-source and raster-assisted building utilities framed as validation utilities unless a later freeze promotes them.
