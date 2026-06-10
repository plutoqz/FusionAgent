# FusionAgent Reliability Roadmap Design

## Purpose

This design defines the next 2-3 month roadmap for FusionAgent after the real-test reflection and architecture-philosophy review. The goal is not to expand the product surface. The goal is to close the exposed credibility gaps in algorithm trust, runtime governance, fusion-quality evaluation, minimal architecture innovation, and thesis evidence.

The final delivery is a thesis supported by a Windows-runnable system. The system must be usable on the current Windows development/runtime environment, support long-running local execution, recovery, repeatable experiments, and auditable evidence. Cross-platform compatibility, production multi-tenancy, authentication, cloud deployment, and production security hardening are out of scope.

This document is the living design record. It intentionally captures decisions before the later implementation plan so that context compaction does not erase agreed constraints. The implementation plan is written only after this design is reviewed and approved.

## Design Principles

1. Treat algorithm correctness as the first-order risk.
2. Treat KG, ToolRegistry, Validator, Executor, and Neo4j state as one runtime contract, not independent metadata islands.
3. Separate "the LLM planned well" from "the runtime constrained and recovered from a bad plan."
4. Use freeze lines so thesis experiments always point to a reproducible system state.
5. Keep architecture innovation measurable and bounded to the thesis claims.
6. Make every engineering closure produce a corresponding thesis paragraph or table.
7. Preserve extension contracts for future capabilities without widening the current thesis claim.

## Dual-Ledger Structure

The roadmap is organized around two linked ledgers.

### Engineering Reliability Ledger

This ledger records every engineering gap, risk tier, owner surface, closure condition, and verification artifact. It covers algorithm trust, deprecated-version prevention, runtime governance, quality metrics, benchmark protocol, recovery behavior, and evidence integrity.

### Research Contribution Ledger

This ledger maps each engineering closure to thesis value. Each entry records the supported claim, experiment metric, baseline, claim boundary, evidence source, and thesis section draft status.

The two ledgers are not independent. Research entries are measured only after their engineering dependencies are frozen.

### Ledger Row Shape

Engineering reliability rows should contain:

- `id`
- `risk_tier`
- `surface`
- `current_evidence`
- `failure_mode`
- `closure_condition`
- `verification_artifact`
- `freeze_dependency`
- `thesis_mapping`

Research contribution rows should contain:

- `claim_id`
- `claim_text`
- `engineering_dependencies`
- `baseline`
- `metric`
- `evidence_source`
- `claim_boundary`
- `thesis_section`
- `draft_status`

The ledgers may start as Markdown tables. They do not need a custom database unless the Markdown form becomes too hard to maintain.

## Five Workstreams

### Workstream 1: Algorithm Trust Hardening

Goal: prove that each fusion algorithm is in a known trust state, old algorithms cannot silently re-enter execution, and core outputs have measurable quality evidence.

Primary artifact: `Algorithm Trust Matrix`.

Scope:

- Building: legacy/default adapter, safe fallback, multi-source decomposed workflow, raster presence/height primitives, conflict/quality primitives.
- Road: V7 road conflation, deprecated `road.v1` / `road.safe`, old segment-topology evidence and wrappers.
- Waterways: V7 waterways conflation, old line-three-source path, Pakistan/local waterways semantics, HydroRIVERS boundary.
- Water polygon: polygon priority merge and deprecated `water.v1`.
- POI: default POI fusion and bounded geohash neighbor match.
- Cross-task quality: invalid geometry, duplicate geometry, out-of-AOI leakage, conflict detection, source contribution balance.

### Workstream 2: Runtime Governance Hardening

Goal: make KG seed, manifest, ToolRegistry, Validator, Planner, Executor, RepairStrategy, and Neo4j graph state fail closed when the runtime contract is violated.

Primary artifact: `Runtime Governance Matrix`.

Scope:

- Algorithm state machine: `runtime_supported`, `bounded_supported`, `research_utility`, `reservation_only`, `deprecated`, and unselectable states.
- Validator fail-closed behavior for unknown, deprecated, unselectable, reserved, and non-candidate algorithms.
- Planner and KG fallback safety.
- Neo4j stale graph detection and reset/inspection guidance.
- Preferred pattern safety.
- Tool contract reporting.
- RepairStrategy policy-source tracing.

Current code reading:

- `ToolRegistry.require()` already fails closed when an algorithm is absent from the registry.
- `WorkflowValidator` rejects unknown algorithms and reservation-only algorithms by setting `kg_validated=False`, but it currently does not provide a single fail-closed state machine for deprecated, unselectable, or non-candidate algorithms.
- `PlanGroundingGate` already has report, warn, and enforce modes; this is a good enforcement surface but must be reconciled with Validator semantics.
- `Executor` healing currently uses a fixed order: primary failure record, alternative source metadata switch, alternative algorithm loop, transform insertion.
- KG `RepairStrategy` nodes exist, but runtime ordering and applicability are not yet strategy-driven.
- Deprecated algorithm nodes remain in the seed and generated Neo4j bootstrap, including legacy road and water IDs. Keeping them is acceptable only if they are unselectable and can never enter execution through planner, preferred pattern, fallback, old plan, healing, or stale graph state.

Runtime state-machine target:

- `runtime_supported` or `runtime_candidate`: may be selected only if registered, candidate-grounded, selectable, and schema-compatible. If both terms remain in legacy metadata, Freeze A must define one canonical meaning and one compatibility mapping.
- `bounded_supported`: may be executed only within explicit capability bounds recorded in evidence.
- `research_utility`: may run only through explicit research or benchmark harnesses, not normal planning.
- `reservation_only`: may appear as future capability metadata but cannot be selected or executed.
- `deprecated`: may remain as historical metadata but cannot be selected or executed.
- missing state: treated as untrusted unless allowlisted as legacy active support during migration.

Governance risks:

- P0: a deprecated, unselectable, reserved, or stale algorithm reaches execution.
- P0: Validator records issues but the run proceeds as if valid.
- P0: KG fallback rescues a bad plan without recording that fallback was responsible.
- P1: Neo4j live graph differs from the seed/manifest but the operator cannot see the difference.
- P1: preferred pattern or old plan replay bypasses current selectability rules.
- P1: healing alternatives include algorithms that normal planning would not allow.
- P2: output schema policy, QoS policy, output requirement, and scenario profile remain advisory JSON rather than explicit constraints.

Runtime Governance Matrix fields:

- `contract_surface`: seed, manifest, Neo4j, ToolRegistry, Planner, Validator, Executor, RepairStrategy, QualityGate.
- `allowed_states`
- `blocked_states`
- `current_behavior`
- `target_behavior`
- `rejection_code`
- `fallback_behavior`
- `audit_event`
- `regression_test`
- `freeze_line`

Closure for Workstream 2:

1. The runtime state machine is documented and applied consistently to algorithms, sources, workflow patterns, preferred patterns, fallback patterns, and healing alternatives.
2. Validator has an explicit enforcement mode. Report-only behavior remains available for A2a ablation, but Freeze A default behavior is fail-closed.
3. Validator fail-closed does not silently improve metrics: rejection, replan, and KG fallback are counted separately.
4. Deprecated, unselectable, reservation-only, unknown, non-candidate, and registry-missing algorithms have negative tests.
5. Preferred pattern replay and old plan replay are checked against current runtime state before execution.
6. Neo4j stale graph inspection reports managed-node drift and gives a reset or re-bootstrap instruction.
7. RepairStrategy-driven healing records the policy source and decision basis at decision time.
8. Thesis draft text exists for runtime contract, fail-closed semantics, and the distinction between LLM planning quality and runtime recovery.

### Workstream 3: Fusion Quality Evaluation

Goal: move from "the run completed" to "the fusion result quality is measured, comparable, and reproducible."

Primary artifact: `Fusion Quality Benchmark Protocol`.

Scope:

- Real, semi-real, and synthetic AOI tiers.
- Clear independence rules for synthetic data. Synthetic data is smoke evidence by default and may support thesis quality claims only when the data generation mechanism is independent of the tested algorithm.
- Task-family metrics for building, road, waterways, water polygon, and POI.
- Baseline definitions.
- Quality report extensions.
- Benchmark manifest and result schemas.

Current code reading:

- `QualityGateService` evaluates readability, non-empty output, required fields, geometry type, AOI intersection, source lineage, and multi-source lineage.
- `artifact_evaluation_service.evaluate_vector_artifact()` already reports feature count, CRS, geometry types, bbox, area/length, duplicate geometry rate, invalid geometry rate, source feature counts, source contribution balance, zero-length geometries, self-intersections, sliver polygons, and dangle endpoints.
- These checks are strong product-safety gates, but they are not yet a complete fusion-quality benchmark. Benchmark metrics must compare outputs against baselines, references, or task-specific proxy targets.

Benchmark tiers:

- Real AOI: real source data and real geographic target. Supports thesis quality claims if source versions, AOI, and baseline are frozen.
- Semi-real AOI: real geometry with controlled perturbation, masking, or source removal. Supports stress and robustness claims when perturbation is independent of the tested algorithm.
- Synthetic AOI: generated geometry. Used for smoke and invariant tests unless the generation mechanism is explicitly independent of the tested algorithm.

Task-family metrics:

- Building: footprint validity, duplicate rate, out-of-AOI leakage, source contribution balance, height-field preservation when applicable, conflict rate with roads/water, optional IoU/precision/recall where reference labels exist.
- Road: geometry validity, zero-length count, dangle endpoint count, length preservation, duplicate segment rate, network connectivity proxy, matched/supplemental contribution split.
- Waterways: geometry validity, waterway class preservation, length preservation, dangle endpoint count, line-source contribution split, HydroRIVERS/local boundary clarity.
- Water polygon: polygon validity, sliver count, overlap/duplicate rate, area preservation, priority-source contribution, optional IoU where reference polygons exist.
- POI: duplicate point rate, geohash-neighbor match stability, category/name preservation, source contribution, optional precision/recall where reference labels exist.

Baseline policy:

- Fixed-script baseline: deterministic adapter call without KG/LLM/policy orchestration.
- Current-runtime baseline: existing FusionAgent behavior before Freeze A governance changes.
- Ablation baselines: A0, A1, A2a, A2b, A2c as defined below.
- Quality baselines must be frozen at Freeze B. Re-running them after algorithm changes creates a new experiment family.

Closure for Workstream 3:

1. Benchmark manifest schema defines AOI, task family, source versions, data tier, independence label, baseline, metrics, and expected artifact roles.
2. Each thesis-used metric has a clear interpretation and known failure mode.
3. Synthetic cases are labeled smoke-only unless independence is proven.
4. Each active task family has at least one real or semi-real quality case.
5. Benchmark output writes machine-readable result JSON and thesis-ready summary tables.
6. Freeze B locks AOIs, source versions, baselines, metric definitions, and manifest schema.
7. Thesis draft text exists for benchmark protocol, metric rationale, synthetic-data limitations, and threat-to-validity.

### Workstream 4: Minimal Measurable Architecture Innovation

Goal: implement only the architecture improvements needed to answer the most likely thesis-review objections.

MVP scope for Freeze A:

1. KG hard constraints: Validator/grounding gate can reject unknown, deprecated, unselectable, reserved, or non-candidate algorithms instead of merely marking tasks as invalid.
2. KG-driven RepairStrategy: the existing healing capability boundary remains the same, but enabled strategies, ordering, applicable tasks, and reason-code matching come from policy/KG data and are recorded in audit evidence.
3. Conditional Durable Learning evidence: summaries are conditioned by task, algorithm or pattern, AOI-size bucket, source-coverage bucket, failure category, and quality outcome. The goal is evidence and policy-hint traceability, not a claim of significant autonomous learning improvement.

Extended ideas such as transform cost/quality loss, learned policy weights, bandits, reinforcement learning, and richer graph reasoning are future work unless time remains after the MVP and thesis evidence are stable.

The graduation boundary for Workstream 4 is not "all innovation ideas are complete." It is "the system has answered the most likely thesis-review objections with measurable behavior."

Reviewer objection targets:

- Objection 1: The KG is only prompt context, not a runtime constraint.
- Objection 2: Healing is hardcoded engineering, not KG-policy-driven architecture.
- Objection 3: Durable Learning is a decorative claim with sparse feedback.

MVP acceptance:

- For Objection 1, Freeze A must show that KG/manifest state can reject bad plans, and A2a/A2b must separate report-only from fail-closed behavior.
- For Objection 2, Freeze A must show that repair strategy ordering, applicability, and reason-code matching are loaded from policy/KG data while keeping the existing healing capability boundary.
- For Objection 3, Freeze A must show conditional learning summaries flowing into policy evidence, without claiming significant decision-quality improvement.

Conditional Durable Learning key:

- `task_kind`
- `algorithm_id` or `pattern_id`
- `aoi_size_bucket`
- `source_coverage_bucket`
- `failure_category`
- `quality_outcome`

Durable Learning claim boundary:

- Allowed claim: the runtime records condition-specific historical evidence and exposes it to deterministic policy scoring.
- Disallowed claim: the system autonomously learns an optimal policy or significantly improves decisions from sparse local usage.

Architecture Innovation Ledger fields:

- `innovation_id`
- `reviewer_objection`
- `current_gap`
- `MVP_behavior`
- `metric`
- `evidence_file`
- `claim_boundary`
- `future_work`

Closure for Workstream 4:

1. The three MVP items are either included in Freeze A or explicitly downgraded before Freeze A.
2. Each MVP has an on/off metric so its contribution is measurable.
3. No MVP widens the current thesis task-family scope.
4. Extended ideas are documented as future work, not mixed into core claims.
5. Thesis draft text exists for architecture contribution, limitation, and ablation interpretation.

### Workstream 5: Thesis Evidence And Contribution Closure

Goal: convert the engineering system into reproducible thesis evidence.

Primary artifacts:

- `Research Contribution Ledger`
- A0/A1/A2 ablation matrix
- Freeze C evidence manifests
- thesis result tables
- thesis section drafts

The thesis must distinguish planning quality, validation hard-gate effects, KG fallback effects, policy/healing governance effects, and final end-to-end success.

Primary thesis position:

FusionAgent should be argued as reliability engineering for bounded disaster-response geospatial fusion, not as AI replacing GIS fusion algorithms. The fusion algorithms remain deterministic GIS operations; the agentic contribution is constrained planning, runtime governance, recovery, auditability, evidence lifecycle, and measurable extensibility.

Core claims:

- C1: KG-grounded planning and validation reduce invalid or hallucinated plans compared with unconstrained LLM planning.
- C2: Fail-closed runtime governance improves executable end-to-end success, but its effect must be separated from raw LLM planning quality.
- C3: Policy/healing governance improves resilience under source, parameter, schema, and execution failures.
- C4: Fusion outputs can be evaluated with task-specific, reproducible quality evidence rather than completion-only success.
- C5: The architecture preserves an extension contract for future capabilities without promoting unimplemented tasks into current claims.

Evidence rules:

- Every result table must cite a Freeze C experiment manifest.
- Every experiment manifest must cite commit SHA, KG seed or manifest hash, ToolRegistry hash or algorithm list, runtime settings, source versions, AOIs, artifact hashes, and metric definitions.
- Re-running an experiment after Freeze C creates a new experiment ID rather than mutating the old one.
- Paper tables are generated or checked against machine-readable evidence, not manually copied from ad hoc logs.

Closure for Workstream 5:

1. Research Contribution Ledger is complete and each claim has an evidence source or a stated limitation.
2. A0/A1/A2a/A2b/A2c ablation tables are populated.
3. Reliability metrics and quality metrics are reported separately.
4. Freeze C evidence manifests exist and pass integrity checks.
5. Thesis sections for system design, runtime governance, experiments, results, discussion, limitations, and future work have current drafts.
6. The Windows runnable system has a documented local run path, expected environment, long-run/recovery behavior, and known limitations.

## Freeze Lines

### Freeze A: Runtime Contract Freeze

Locks:

- KG seed or manifest hash
- ToolRegistry algorithm list
- algorithm state-machine semantics
- Validator fail-closed rules
- Planner fallback safety rules
- RepairStrategy policy model
- deprecated and reservation-only guardrails

Required regression suite:

- KG seed/manifest parity and hash checks
- ToolRegistry registration checks
- deprecated/unselectable algorithms cannot be selected by planner, fallback, preferred pattern, or healing
- Validator fails closed for runtime-contract violations
- golden cases still execute
- Neo4j stale graph detection or reset path is verified

Freeze A regression is carried forward after Freeze B and Freeze C. Later benchmark or evidence changes must not weaken the runtime contract.

### Freeze B: Benchmark Protocol Freeze

Locks:

- AOI list and task-family coverage
- data sources and source versions
- baseline definitions
- quality metric definitions
- synthetic-data independence labels
- benchmark manifest schema

Required regression suite:

- benchmark manifest validates
- quality metric smoke tests pass
- synthetic-only cases are not promoted to thesis quality claims unless explicitly independent
- baseline runners and result schemas are stable

Freeze B regression is carried forward after Freeze C. Later experiment execution must not silently change AOIs, baselines, metric definitions, or source-version assumptions.

### Freeze C: Experiment Evidence Freeze

Locks:

- experiment outputs
- commit SHA
- seed or manifest hash
- runtime settings hash
- artifact hashes
- quality reports
- thesis table source data

Required regression suite:

- `evidence_integrity_manifest.json` records experiment id, output directory, file list, content hashes, commit SHA, seed hash, and runtime settings hash.
- A directory-hash integrity test fails if frozen experiment outputs are changed or overwritten.
- thesis tables only reference experiments registered in Freeze C.

Freeze C integrity checks should hash file contents, not depend on timestamps. Any intentional rerun creates a new experiment id and a new manifest rather than modifying frozen evidence in place.

## Ablation Design Notes

The A2 variants must separate LLM planning quality from runtime constraint and fallback behavior.

- A2a: KG context plus Validator report-only.
- A2b: KG context plus Validator fail-closed plus KG fallback.
- A2c: A2b plus policy/healing governance.

A2b metrics must include:

- `validator_rejection_rate`
- `kg_fallback_rate`
- `fallback_plan_quality_delta`
- `llm_plan_valid_before_fallback`
- `final_executable_success_rate`
- `fallback_plan_selected_algorithm_id`
- `pre_fallback_plan_selected_algorithm_id`

If `kg_fallback_rate` is high, the thesis should state that constrained runtime recovery stabilized LLM planning, not that the LLM planner itself became reliably optimal.

Fallback can mask poor LLM planning. Therefore A2b must report both pre-fallback plan validity and final executable success. If the fallback plan succeeds but is lower-scoring, lower-quality, or less preferred than the rejected LLM plan would have been after repair, the result should be counted as runtime resilience rather than planning optimality.

## Algorithm Trust Matrix

Each algorithm or algorithm family gets one row.

Fields:

- `algorithm_id`
- `family`
- `current_claim`
- `entry_points`
- `planner_exposure`
- `healing_role`: one of `primary`, `first_alternative`, `kg_fallback_alternative`, `transform_dependency`, `none`
- `healing_source_consistency`: whether plan alternatives and KG alternatives agree
- `deprecated_risk`
- `tool_registry_status`
- `validator_status`
- `neo4j_stale_risk`
- `test_coverage`
- `quality_metrics`
- `real_evidence`
- `paper_claim_limit`
- `closure_status`

Risk tiers:

- P0: old or wrong algorithm can still enter planner fallback, preferred pattern, old plan, healing, Neo4j stale graph, or execution.
- P1: algorithm can run but lacks sufficient quality evidence for thesis use.
- P2: algorithm is a research utility or reserved capability and must be downgraded or bounded in claims.
- P3: naming, wrapper, historical evidence, or documentation can confuse audit or thesis wording.

P0 must be expressed as concrete scenarios:

- Scenario A: planner KG fallback selects a deprecated or stale pattern.
- Scenario B: Validator marks an invalid plan but does not reject it before execution.
- Scenario C: Neo4j contains stale managed nodes or step templates that are absent from the current seed.

## Algorithm Audit Protocol

The algorithm audit must start from entry points, not from claims. For each algorithm family, enumerate every path that can call it:

- `ToolRegistry` registration
- `kg.seed` and `kg/seed_manifest.generated.json`
- Neo4j bootstrap Cypher
- workflow pattern steps
- algorithm alternatives
- task alternatives in plans
- Executor handler method
- adapter function
- compatibility wrapper
- benchmark script
- old run plan replay
- healing fallback
- preferred pattern request

Then classify the actual algorithm implementation:

- Active thesis algorithm: can support current claims if quality evidence exists.
- Bounded runtime algorithm: can run, but the claim must mention its scope and known limits.
- Research utility: useful for analysis or benchmark support, not normal planning.
- Deprecated historical algorithm: retained only for audit history and must be blocked at runtime.
- Reservation-only future capability: documented extension point, not executable.

Deprecated-version hardening:

- Deprecated algorithms may remain in KG history but must be absent from active candidate patterns.
- Deprecated algorithms must have `selectable_now=false` or equivalent blocked state.
- Validator, Planner, KG fallback, preferred pattern selection, and Executor healing must all reject deprecated algorithms through the same contract service.
- Compatibility wrappers that redirect old names to new algorithms must be documented as audit aliases, not independent algorithm evidence.
- Neo4j live graph must be checked for stale deprecated nodes and stale step templates before Freeze A evidence is generated.

Algorithm evidence minimum:

- Smoke test: the adapter produces a readable non-empty artifact on a small controlled case.
- Negative test: invalid geometry, missing source, wrong data type, or deprecated ID is rejected or classified.
- Golden test: one known case has stable output-level metrics.
- Quality test: at least one real or semi-real AOI metric row exists before the algorithm is used in thesis quality tables.
- Evidence link: each run records the effective algorithm ID, not only the planned algorithm ID.

## Workstream 1 Closure

Independent closure for Workstream 1:

1. `Algorithm Trust Matrix` is complete for all active, bounded, research, reserved, and deprecated algorithm families.
2. All P0 risks are either closed or explicitly moved to Workstream 2 with a blocking dependency.
3. Deprecated/unselectable guardrails are designed as one cross-task atomic mechanism, not task-family-specific patches.
4. Synthetic smoke, golden regression, and negative tests exist for core algorithm families.
5. Evidence manifests include `algorithm_ids` used by each run and verify those IDs against the Freeze A seed or manifest hash.
6. Thesis draft text exists for algorithm trust, trust-tier classification, and claim boundaries.

Joint closure with Workstream 3:

1. Core task families have real or semi-real AOI quality evaluation under the Freeze B benchmark protocol.
2. Thesis quality tables use only Freeze C evidence.

## Repair Strategy Audit Requirements

Repair evidence must be captured at decision time, not reconstructed afterward.

Each repair decision should record:

- `strategy`
- `reason_code`
- `policy_source`
- `policy_decision_basis`
- `candidate_actions`
- `selected_action`
- `skipped_actions`

`candidate_actions` and `skipped_actions` must be populated inside the Executor healing loop while the runtime still knows the actual system state, availability checks, exceptions, and ordering decisions.

## Capability Extension Contract

The current thesis does not promote trajectory-to-road or any new task family to runtime support. However, the system should demonstrate a clean extension contract.

Adding a future capability should require:

1. KG or manifest entries for data types, algorithms, parameter specs, workflow patterns, source contracts, output schema policy, and claim state.
2. ToolRegistry handler registration.
3. Validator state-machine behavior.
4. Retriever exposure rules that do not leak reserved or deprecated capabilities into active planning.
5. Executor dispatch through ToolSpec.
6. Evidence surfaces for tool contract, policy source, quality report, and algorithm IDs.
7. Documentation and claim-ledger updates.

Trajectory-to-road may be used as the extension-design example, but it remains reservation-only in this roadmap.

## Planning Gate

This roadmap intentionally separates three document layers:

1. Design spec: this file. It fixes philosophy, scope, risks, workstreams, freeze lines, and claim boundaries.
2. Implementation plan: written after this design is reviewed and approved. It breaks the roadmap into ordered tasks, owners, commands, tests, and checkpoints.
3. Execution logs and evidence manifests: produced while implementing and running experiments.

The implementation plan should not wait until every future discussion is exhausted. It should be written when this design contains enough stable decisions to protect against context loss. After approval, the plan can still be split into phase plans for Workstream 1/2, Workstream 3, Workstream 4 MVP, and Workstream 5 evidence closure.

Recommended plan split:

- Plan A: Algorithm Trust plus Runtime Contract Freeze.
- Plan B: Benchmark Protocol plus Quality Evaluation Freeze.
- Plan C: Architecture MVP plus Ablation Harness.
- Plan D: Freeze C Evidence plus Thesis Closure.

## Non-Goals

- Do not add new task families such as land use or transportation hubs.
- Do not add new remote data-source acquisition types beyond the current thesis scope.
- Do not treat the frontend as a thesis-evaluated component.
- Do not promote trajectory-to-road from reservation-only.
- Do not add reinforcement learning, bandits, or a new policy algorithm.
- Do not claim autonomous self-optimization from Durable Learning.
- Do not pursue cross-platform compatibility beyond the current Windows platform.
- Do not implement multi-tenant operation, authentication, production deployment, or cloud-native operations.
- Do not build a general community benchmark framework beyond what the thesis evidence needs.

## Thesis Closing Rule

Every workstream closes only when the engineering artifacts, verification evidence, claim boundaries, and corresponding thesis draft text are all present.

Engineering completion without thesis text is not considered complete for this roadmap.
