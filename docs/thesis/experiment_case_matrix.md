# Experiment Case Matrix

Status: initial working draft, 2026-07-10.

This document defines the first research experiment cases. The cases should test product-contract satisfaction under complex combinations, not just demonstrate that the pipeline can run.

## Baselines

Evaluate each case against:

1. Fixed priority strategy.
2. KG-only deterministic strategy.
3. LLM-only strategy.
4. LLM + capability KG.
5. LLM + full product-contract KG.

## Scoring Rubric

Each case should score:

- product contract satisfaction
- critical layer prioritization
- delivery strategy correctness
- gap declaration correctness
- evidence completeness
- invalid or prohibited behavior
- acceptable alternative handling

Case standard answers are allowed for evaluation. They must not be converted into global fixed rules used by the system at runtime.

## Case Template

```text
case_id:
scenario:
aoi:
resource_regime:
input_sources_status:
expected_layer_priority:
expected_delivery_strategy:
expected_gap_declaration:
must_not_do:
acceptable_alternatives:
scoring_rubric:
```

## Initial Case Set

### C01 Earthquake: tight time, partial source availability

```text
scenario: earthquake
resource_regime: limited network, tight time
input_sources_status: OSM available; high-resolution building source incomplete or delayed
expected_layer_priority: building and road critical; water layers skip or low priority; POI important/optional depending contract
expected_delivery_strategy: deliver provisional usable vector product first, continue full fusion in background
expected_gap_declaration: delayed source or degraded completeness explicitly declared
must_not_do: spend critical budget on skipped water layers; mark provisional output as final
```

### C02 Flood: water and road dominate

```text
scenario: flood
resource_regime: moderate network, tight time
input_sources_status: water sources partially stale or semantically mismatched; roads available
expected_layer_priority: water_polygon/waterways and road critical; building important
expected_delivery_strategy: prioritize water/road fusion and evidence; building can be delayed or degraded
expected_gap_declaration: source freshness or source mismatch declared where applicable
must_not_do: use generic building-first ordering
```

### C03 Wildfire: sparse built environment

```text
scenario: wildfire
resource_regime: limited network, tight time
input_sources_status: building/POI likely absent in AOI; road source available
expected_layer_priority: road critical; building/POI may be data_absent; water depends contract
expected_delivery_strategy: focus budget on road product; declare absent layers
expected_gap_declaration: data_absent for layers with no baseline features, not system error
must_not_do: repeatedly retry absent layers without new evidence
```

### C04 Typhoon or storm: large AOI, coverage pressure

```text
scenario: typhoon_or_storm
resource_regime: large AOI, tight time
input_sources_status: multiple sources available but slow to fully materialize
expected_layer_priority: coverage and progressive delivery dominate
expected_delivery_strategy: chunked or staged delivery; final fusion supersedes provisional products
expected_gap_declaration: partial coverage and pending completion visible
must_not_do: wait indefinitely for full fusion before any usable delivery
```

### C05 Source conflict: geometry-rich vs attribute-rich

```text
scenario: generic_disaster_response
resource_regime: moderate
input_sources_status: one source has better geometry; another has richer attributes
expected_layer_priority: depends product contract, but fusion rationale must state tradeoff
expected_delivery_strategy: produce fused product with provenance and conflict report
expected_gap_declaration: quality risk or unresolved conflict declared when not fully resolved
must_not_do: silently overwrite richer attributes or geometry without evidence
```

### C06 Fusion quality gate failure

```text
scenario: any
resource_regime: tight
input_sources_status: full fusion attempted, quality gate fails; single-source product usable
expected_layer_priority: critical layer still delivered as degraded product if acceptable
expected_delivery_strategy: degraded delivery with failed quality evidence; retry or supersede if possible
expected_gap_declaration: quality_failed and degraded_but_usable
must_not_do: mark failed fusion as fully_satisfied
```
