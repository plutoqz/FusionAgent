# Product Contract Specification

Status: initial working draft, 2026-07-10.

This document freezes the first implementation target for the research-oriented branch. It defines the data products, quality gates, gap declarations, and output artifacts that both the research and application branches should share.

## Scope

The current product scope is fixed-source, multi-source vector fusion data for:

- building
- road
- water_type_1
- water_type_2
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
| water_type_1 | To be named | To be defined | To be defined | To be defined | source provenance, coverage, quality result |
| water_type_2 | To be named | To be defined | To be defined | To be defined | source provenance, coverage, quality result |
| poi | Multi-source POI fusion | Deduplicate nearby/duplicate POIs | Merge names/categories/source fields | Detect duplicate or conflicting POI candidates | source provenance, coverage, quality result |

Open item: define the two water types precisely before implementation. Avoid continuing with a single vague `water` concept.

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

