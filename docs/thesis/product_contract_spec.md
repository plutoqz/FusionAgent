# Product Contract Specification

Status: Phase 1 decision protocol implemented; water product semantics and ontology mapping frozen, 2026-07-20.

This document freezes the first implementation target for the research-oriented branch. It defines the data products, quality gates, gap declarations, and output artifacts that both the research and application branches should share.

## Scope

The current product scope is fixed-source, multi-source vector fusion data for:

- building
- road
- water_polygon
- waterways
- poi

The system delivers fused vector data itself. It does not decide the downstream emergency use. The fused data should be richer or more reliable than raw single-source data through geometry enrichment, attribute enrichment, and bounded topology-conflict handling.

## Product Contract Fields

```text
product_id
product_type
disaster_type
response_phase
aoi
time_window
resource_regime
required_layers
quality_gates
degradation_policy
gap_declaration_policy
delivery_policy
evidence_contract
```

## Layer Contract Table

| Layer | Fusion objective | Geometry enrichment | Attribute enrichment | Topology handling | Minimum evidence |
| --- | --- | --- | --- | --- | --- |
| building | Multi-source building footprint fusion | Deduplicate and merge complementary footprints | Preserve/source-normalize available attributes | Resolve obvious overlaps and invalid geometries | source provenance, coverage, quality result |
| road | Multi-source road network fusion | Merge complementary road segments | Preserve/source-normalize road attributes when available | Basic snapping/deduplication/conflict reporting | source provenance, coverage, quality result |
| water_polygon | Polygonal surface-water fusion for lakes, reservoirs, ponds, and other bounded water bodies | Deduplicate and merge complementary polygon coverage while preserving valid boundaries | Normalize water-body class, name, area, and source lineage where available | Repair invalid rings, report overlaps/slivers, and preserve polygon geometry | source provenance, AOI coverage, geometry validity, duplicate/sliver checks, quality result |
| waterways | Linear hydrography fusion for rivers, streams, canals, drains, and other watercourse lines | Conflate complementary line networks without converting lines into water-body polygons | Normalize waterway class, name, hierarchy, and source lineage where available | Check zero-length segments, endpoint dangles, duplicate lines, and connectivity conflicts | source provenance, AOI coverage, line topology metrics, quality result |
| poi | Multi-source POI fusion | Deduplicate nearby/duplicate POIs | Merge names/categories/source fields | Detect duplicate or conflicting POI candidates | source provenance, coverage, quality result |

`water_polygon` and `waterways` are separate product contracts even though both use the legacy `water` job family internally. Evidence and delivery manifests must retain the concrete task kind so polygon and line results cannot be conflated.

## Structured Planning Decision

The planner output is machine-readable and uses this protocol:

```text
strategy_id
priority_tiers
initial_delivery_layers
background_completion_layers
not_delivered_layers
layer_decisions
planner_gap_proposal
supersession_plan
rationale
```

Every required layer must appear exactly once across `priority_tiers` and once
in `layer_decisions`. Layers inside one tier are unordered. Initial and
not-delivered sets are disjoint. Background completion may overlap initial
delivery only for provisional or degraded products. Supersession entries must
refer to background-completion layers.

Algorithms, sources, layers, strategy identifiers, delivery modes, gap types,
and supersession triggers are grounded against the planner-visible context.
Natural-language rationale is retained for audit but is not the primary score.

## Quality Gate Levels

### Layer-Level Gates

- source materialized
- AOI coverage checked
- non-empty result or justified empty result
- geometry validity checked
- minimum attribute set checked
- duplicate/conflict rate checked where applicable
- provenance recorded

### Product-Level Gates

- all critical layers delivered or justified
- degraded layers explicitly marked
- provisional outputs marked as provisional
- final outputs can supersede provisional outputs
- gap declarations generated for unmet requirements
- evidence trace complete

### Satisfaction States

```text
fully_satisfied
partially_satisfied
degraded_but_usable
not_satisfied
not_applicable
source_mismatch
```

## Gap Types

```text
data_absent
source_unavailable
quality_failed
source_mismatch
contract_not_satisfied
```

Gap handling is split into three artifacts:

```text
planner_gap_proposal.json
gap_verification.json
gap_declaration.json
```

`planner_gap_proposal.json` contains only gaps proposed by the planner.
`gap_verification.json` checks those proposals against grounded facts and may
report observable omissions. `gap_declaration.json` is the final deterministic
product declaration generated from source and quality evidence. Planner scoring
uses the proposal, never the final declaration. Gap declarations are product
outputs, not error logs.

## Shared Output Artifacts

Machine-readable artifacts:

```text
product_contract.json
planning_context.json
planning_decision.json
resource_regime.json
planner_gap_proposal.json
quality_gate_result.json
gap_verification.json
gap_declaration.json
evidence_trace.json
delivery_manifest.json
experiment_summary.json
evaluation_result.json
```

End-to-end runs additionally emit:

```text
runtime_execution.json
runtime_artifact_index.json
runtime/<layer>/quality_report.json
runtime/<layer>/algorithm/*.gpkg
```

Every summary, quality result, evidence trace, and delivery manifest records
its execution mode. Planning-only quality evidence is labeled
`controlled_status_simulation`; end-to-end quality evidence is labeled
`real_runtime`. These artifacts must not be pooled as if they measured the same
execution surface.

Failed LLM planning attempts emit `planning_failure.json` with non-sensitive
provider metadata, raw model responses when available, grounding errors, and a
failure reason. A failed run does not emit a deterministic planning decision as
an LLM result.

Repeated experiment batches additionally emit:

```text
audit_ledger.jsonl
stability_summary.json
audit_manifest.json
protocol_snapshot.json
schedule.json
implementation_manifest.json
```

The audit ledger is hash chained and contains both successful and failed runs.
Each record includes model and endpoint metadata, prompt/context hashes, token
usage, latency, retry count, evaluation metrics or failure details, normalized
semantic decision fields, and SHA-256 hashes of every run artifact.

User-facing artifact:

```text
run_report.md / run_report.html / run_report.pdf
```

The research runner generates planning decisions with five formal baselines:
`fixed`, `kg_only`, `llm_only`, `llm_capability_kg`, and
`llm_full_contract_kg`. The three LLM baselines share one prompt, schema,
provider interface, temperature, JSON response mode, and repair policy; only
their declared knowledge layers differ. Real LLM schema or grounding failures
are explicit, one repair retry may be recorded, and no deterministic result may
masquerade as a successful LLM plan.

## Knowledge Graph Ontology Mapping

The product contract is a first-class `ProductContract` graph entity rather than a JSON-only runtime artifact.

The initial ontology contains one composite contract and five layer contracts:

```text
contract.product.emergency_vector_bundle.v1
contract.product.building.v1
contract.product.road.v1
contract.product.water_polygon.v1
contract.product.waterways.v1
contract.product.poi.v1
```

Contract properties retain the policy semantics that must travel together:

- disaster types and response phases
- layer requirements and criticality
- quality gates and satisfaction states
- evidence requirements
- degradation policy
- gap declaration policy
- delivery and supersession policy

Graph relationships make the contract traversable across the existing ontology:

```text
ProductContract -[:APPLIES_TO_SCENARIO]-> ScenarioProfile
ProductContract -[:ORCHESTRATED_BY]-> TaskBundle
ProductContract -[:REQUIRES_TASK]-> Task
ProductContract -[:REQUIRES_OUTPUT_REQUIREMENT]-> OutputRequirement
ProductContract -[:USES_QOS_POLICY]-> QoSPolicy
ProductContract -[:USES_REPAIR_STRATEGY]-> RepairStrategy
ProductContract -[:COMPOSED_OF]-> ProductContract
```

The selected layer contract is included in the planner retrieval context and persisted on `WorkflowPlan.product_contract`. This makes contract knowledge available to constrained planning without treating the LLM as the authority for deterministic validation or quality acceptance.
