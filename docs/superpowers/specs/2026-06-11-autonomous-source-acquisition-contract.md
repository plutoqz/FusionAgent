# Autonomous Source Acquisition Contract

## Scope

FusionAgent's near-term engineering target is autonomous city/county-to-national fusion for buildings, roads, POI, water lines, and water polygons. The runtime must acquire all configured candidate sources without external intervention, classify every source attempt, select a fusion path from available coverage, and write auditable evidence. Network outages, upstream provider failures, missing credentials, missing authorization, and official no-coverage states are external-uncontrollable conditions; CRS errors, field mapping errors, cache corruption, missing internal evidence, and unsupported parameter bindings are system failures.

This contract does not add a new slot abstraction or source-planning module. `AlgorithmParameterSpec` remains the canonical parameter/slot contract, and `InputAcquisitionService` remains the owner of runtime source acquisition evidence.

## KG Parameter Policy

`AlgorithmParameterSpec` must support static defaults, conditional defaults, and provenance. Conditional defaults may depend on source combination, region, AOI scale, quality outcome, or durable-learning feedback. Effective parameters must be resolved before algorithm execution and written into task parameters with `parameter_provenance`.

Do not introduce `FusionSlotContract`. If a frontend field, backend parameter, or automatic source requirement needs to be represented, extend the existing KG parameter/source metadata instead.

## Input Acquisition Policy

`InputAcquisitionService` and existing provider services must attempt every configured candidate source for the requested task. They must continue when optional sources are unavailable, degrade only when the missing source is externally uncontrollable, and fail the autonomous-closure claim when a required source is absent for internal reasons.

Do not introduce `SourceAttemptPlanner`. Source attempt recording, coverage aggregation, degradation classification, and evidence writing belong in `InputAcquisitionService`, `SourceAssetService`, `LocalBundleCatalogProvider`, and existing source policy helpers.

## Source Attempt Statuses

Source attempts use normalized statuses:

| Status | Meaning |
| --- | --- |
| `available` | Source was resolved and contains usable features for the AOI. |
| `materialized` | Source was downloaded or generated and written to cache/output. |
| `cache_reused` | Source was available from an existing cache artifact. |
| `empty` | Source resolved successfully but contains zero AOI features. |
| `no_coverage` | Provider officially has no coverage for the AOI or country. |
| `network_failed` | Network, DNS, timeout, or connection failure prevented acquisition. |
| `provider_failed` | Provider returned an error unrelated to local code correctness. |
| `unauthorized` | Required credential, license, or authorization manifest is absent or invalid. |
| `internal_failed` | Local parsing, CRS, schema, path, or algorithm integration failed. |

Each attempt should include `source_id`, `status`, `fault_class`, `feature_count`, `coverage_status`, `selected_for_fusion`, `external_uncontrollable`, `path`, and `message` when available.

## Required Full-Closure Sources

| Task | Required sources for full closure | Optional/supplemental sources |
| --- | --- | --- |
| Building fusion | `raw.google.building`, `raw.microsoft.building`, `raw.osm.building`, `raw.osm.road` | `raw.openbuildingmap.building`, height raster, existence raster, attribute sources |
| Road fusion | `raw.osm.road`, `raw.microsoft.road` | Existing `raw.overture.transportation` may remain as a compatibility/extra source, but it is not the requested full-closure road contract |
| Water line/polygon fusion | `raw.osm.waterways`, `raw.hydrorivers.water`, `raw.osm.water`, `raw.hydrolakes.water` | Local water datasets when explicitly configured |
| Lake/water polygon fusion | `raw.osm.water`, `raw.hydrolakes.water` | Local lake/water polygon datasets |
| POI fusion | `raw.gns.poi`, `raw.google.poi`, `raw.osm.poi` | Existing local POI supplements such as `raw.rh.poi` |

## Frontend And Backend Field Mapping

| Task | User-facing inputs | Runtime parameters/sources |
| --- | --- | --- |
| Building fusion | Multi-source building geometry files, road input, optional attributes, optional existence raster, optional height raster | New UI may use `geometry_sources`; legacy fields remain `ms_building`, `google_building`, `osm_building`; server/PostGIS path maps to Google building, MS building, OSM building, optional OBM building, and required OSM road |
| Road fusion | OSM road input, MS road input | `params["osm_road"]` and `params["ms_road"]`; canonical source ids `raw.osm.road` and `raw.microsoft.road` |
| Water line/polygon fusion | OSM water line, new water line, water-area features | `params["osm_line"]`, `params["new_line"]`, `params["water_area"]`; canonical sources include OSM waterways, HydroRIVERS, OSM water polygons, and HydroLAKES |
| Lake fusion | OSM lake input, new lake input | Separate lake/water-polygon path, not a replacement for the line/polygon water main task |
| POI fusion | GeoNames/GNS, OSM POI, Google POI | Algorithm order is `GNG`, `GOOGLE`, `OSM`; canonical source ids `raw.gns.poi`, `raw.google.poi`, `raw.osm.poi` |

## Google Sources

Google building must be part of the automatic source acquisition loop. The preferred engineering source is Google Open Buildings where official coverage and license terms allow local materialization, clipping, persistence, and evidence generation.

Google POI must also be part of the automatic source acquisition loop. It requires `GOOGLE_PLACES_API_KEY` and a local authorization manifest confirming the project is allowed to persist, export, and fuse Google POI results with non-Google sources. Without that authorization manifest, `raw.google.poi` is classified as `unauthorized`, and POI full closure must fail or degrade as externally uncontrollable according to the readiness policy.

Track B national evidence CLI runs expose Google source configuration through `--google-open-buildings-url`, `--google-poi-authorization`, `--google-places-api-key-env`, and `--google-places-cache-key`. API key values are read from the named environment variable and must not be written to evidence files.

## Fusion Path Selection

The runtime should first attempt all required and optional candidates for the task. It may proceed with a degraded fusion path only when missing required sources are classified as external-uncontrollable and the evidence states the missing source ids. It must not claim `full_autonomous_closure` unless every required source for that task is available with non-empty AOI coverage.

For building fusion, Google/MS/OSM are the core geometry sources and OSM road is the required conflict constraint. OBM is optional supplemental evidence.

For POI fusion, the adapter must preserve algorithm input order `GNG`, `GOOGLE`, `OSM`. Missing Google POI cannot be silently treated as a full POI success.

## Evidence Files

Each autonomous run should expose:

- `source_attempts.json`
- `source_materialization_manifest.json`
- `selected_sources.json`
- `source_profile_snapshot.json`
- `normalization_summary.json`
- `tile_manifest.json` for tiled or large-area runs
- `stitched_artifact.json` for stitched outputs
- `quality_report.json` when available
- `autonomous_readiness.json`

`autonomous_readiness.json` uses:

| Status | Meaning |
| --- | --- |
| `full_autonomous_closure` | Every required source is available and non-empty, and the fusion path completed. |
| `degraded_external` | One or more required sources are missing only for external-uncontrollable reasons, with evidence. |
| `system_failure` | A required source or fusion stage failed for an internal reason, or evidence is missing. |

The evidence CLI option `--require-full-autonomous-closure` is a strict gate for claim-building runs. When set, the command must read `inspection_summary.json`, inspect `autonomous_readiness.status`, print missing required source ids, and return non-zero unless the status is `full_autonomous_closure`.

## Long-Running Follow-Up Boundary

This contract creates the evidence and source-attempt foundation for long-running autonomous operation. Checkpoint/resume, watchdogs, retry budgets, run leasing, and crash recovery should be handled in a follow-up plan after source closure is implemented and verified.
