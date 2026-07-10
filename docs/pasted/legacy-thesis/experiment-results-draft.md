# Experiment Results Draft

## Runtime Governance

Freeze A establishes the runtime contract used by all thesis experiments. Report-only validation and fail-closed validation are separated in A2a and A2b so executable success is not mistaken for raw LLM planning quality.

## Benchmark Protocol

Freeze B fixes AOIs, source versions, baselines, metric definitions, and synthetic-data claim boundaries. Synthetic cases are treated as smoke evidence unless their generation mechanism is independent of the tested fusion algorithm.

## Ablation Results

The ablation table must report pre-fallback plan validity, Validator rejection rate, KG fallback rate, final executable success rate, and fallback plan quality delta.

## Fusion Quality Results

Quality tables report task-family metrics from machine-readable benchmark outputs. Completion-only success is not used as a substitute for fusion quality.

## Limitations

Fusion algorithms remain deterministic GIS implementations. The agentic contribution is constrained planning, runtime governance, repair evidence, recovery, auditability, and evidence lifecycle.
