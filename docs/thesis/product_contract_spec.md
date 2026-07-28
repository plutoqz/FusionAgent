# Product Contract Specification

Status: water product semantics frozen, 2026-07-20.

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
skip
data_absent
source_unavailable
quality_failed
source_mismatch
contract_not_satisfied
```

Gap declarations are product outputs, not error logs.

## Shared Output Artifacts

Machine-readable artifacts:

```text
product_contract.json
planning_decision.json
resource_regime.json
quality_gate_result.json
gap_declaration.json
evidence_trace.json
delivery_manifest.json
```

User-facing artifact:

```text
run_report.md / run_report.html / run_report.pdf
```

Application branch may generate these artifacts with fixed rules first. Research branch should later generate the planning decision with KG-constrained LLM orchestration.

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
