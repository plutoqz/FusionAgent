# End-to-End Runtime Protocol

Status: Phase 4 minimum implementation, development evidence only, 2026-07-20.

## Purpose

This protocol connects the frozen product-contract planning decision to the
existing geospatial runtime without changing planner scoring. It applies first
to C02, C04, and C06.

The experiment has two non-interchangeable modes:

```text
planning_only
  controlled source-status quality simulation

end_to_end
  real vector materialization, execution, quality evaluation, and writeback
```

End-to-end outcomes never replace, repair, or improve the planning score.

## Execution Boundary

For every planner layer decision, the runtime consumes exactly:

```text
layer
selected_algorithm
selected_sources
delivery_mode
```

Only selected sources may be materialized. A source whose frozen case status is
not `available` is recorded as `skipped_known_unusable`; it is not silently
substituted. An available source that cannot be materialized is recorded as a
runtime failure.

The current deterministic algorithm resolution is:

| Product layer | Complete-source runtime algorithm |
| --- | --- |
| `road` | `algo.fusion.road.conflation.v7` |
| `water_type_1` | `algo.fusion.water_polygon.priority_merge.v2` |
| `water_type_2` | `algo.fusion.waterways.conflation.v7` |
| `building` | existing multi-source building runtime when its source contract is complete |
| `poi` | existing geohash-neighbor POI runtime when its source contract is complete |

The minimum C02/C04/C06 path currently uses explicit single-source materialized
delivery for building and water whenever only one usable source is selected.
This is recorded as `runtime.single_source_passthrough.v1`, not as fusion.

## Quality And Writeback

Every produced GeoPackage is read by `QualityGateService`. Geometry type,
non-empty state, AOI intersection, provenance, duplicate geometry, invalid
geometry, topology, and source contribution metrics are computed from the real
artifact.

Single-source delivery uses an explicit product-contract quality policy that
makes only multi-source lineage and contribution balance soft. All readability,
geometry, AOI, provenance, validity, and topology checks remain enforced.

Accepted artifacts and their quality reports are written to
`ArtifactRegistry`. Rejected artifacts are not registered as fusion results.

## Failure Semantics

The runtime must not:

- substitute an unselected source;
- treat a known unusable source as materialized;
- replace a failed quality result with planning-only simulation;
- report single-source passthrough as a successful fusion algorithm;
- merge polygon water and line waterways semantics.

Expected source or layer failures are returned in `runtime_execution.json` and
feed the deterministic final gap declaration. Unexpected executor exceptions
emit `runtime_failure.json` and remain raised.

## Current Evidence Boundary

Automated development tests cover:

- C06 single-source road fallback with real GeoPackage quality and writeback;
- C04 road, building, and waterways materialized delivery;
- C02 road/building delivery with explicit rejection of mismatched/stale water
  sources;
- dual-source road execution through the existing v7 conflation algorithm;
- materialization failure without simulated quality fallback;
- selected-source-only execution and mode-separated artifacts.

These tests validate implementation behavior. They are not external-data runs,
stability evidence, or paper conclusions. Claim-eligible Phase 4 evidence still
requires durable C02/C04/C06 runs on declared real source assets, a clean commit,
artifact hashes, and a frozen execution manifest.
