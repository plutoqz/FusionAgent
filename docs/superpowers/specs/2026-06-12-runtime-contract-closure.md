# Runtime Contract Closure Specification

## Purpose

FusionAgent treats autonomous fusion as a contract across five runtime boundaries:

1. KG/source catalog selection
2. Runtime source provider availability
3. Source materialization and component coverage
4. Task-kind-specific execution routing
5. Quality gate acceptance with degradation evidence

No boundary may assume a source, geometry family, credential, or region package is available without explicit evidence.

## Runtime Source Status

- `runtime_ready`: the source can be materialized by the current runtime without extra operator configuration.
- `requires_external_config`: the source is supported but needs credentials, authorization, URL manifests, or similar external configuration.
- `reservation_only`: the source is known to the catalog or raw source service but cannot be used as a task input bundle.
- `missing_provider`: no runtime provider can handle the source.

## Degradation Levels

- `none`: all required runtime inputs are available.
- `partial_source`: some optional or supplemental sources are missing.
- `external_uncontrollable`: missing sources are caused by external availability, credentials, authorization, or upstream coverage.
- `system_failure`: missing sources are caused by runtime implementation gaps such as missing providers or incompatible task routing.

## Hard Boundaries

- Geometry type mismatches remain hard failures.
- Missing required output fields remain hard failures.
- Source lineage remains a hard failure.
- Multi-source lineage may be downgraded only when the quality policy explicitly allows it for a task kind and the degradation context is external-only.

## Regression Regions

Use multiple regions to validate generic behavior:

- A country with direct Geofabrik ISO match.
- A region where Geofabrik package granularity differs from geocoder country metadata.
- A region with one source available and one externally unavailable source.
- A region with no local uploaded data.
