# Track B National Source Matrix

This live spec locks the first implementation wave for `Track B` in
`docs/superpowers/plans/2026-05-13-fusionagent-master-execution-plan.md`.
It is the contract that B2-B5 must implement against.

## Vocabulary

- `official_remote_supported`: the repository already has a bounded remote or
  semi-remote materialization path for this source family.
- `manual_preload_required`: the source is part of the locked national matrix,
  but the operator must preload or cache the dataset locally before the runtime
  can use it safely.
- `reservation_only`: the source is named and bounded in the contract, but it
  stays deferred until a later Track B phase promotes it.

## Theme Matrix

### Building

Current runtime bundles:

- `catalog.flood.building`
- `catalog.earthquake.building`

Locked source set:

| Source ID | Role | Acquisition | Format | Clip Strategy | Field Mapping | Claim Boundary |
| --- | --- | --- | --- | --- | --- | --- |
| `raw.osm.building` | primary | `official_remote_supported` | `geofabrik_shapefile_bundle` | `country_bundle_then_clip` | `fields.building.osm` | ODbL-derived source; keep attribution in evidence and outputs. |
| `raw.microsoft.building` | primary reference | `official_remote_supported` | `microsoft_global_buildings_tiles` | `country_tiles_then_clip` | `fields.building.microsoft` | Provider-published reference source; claims stay bounded to checked runtime evidence. |
| `raw.google.building` | manual reference | `manual_preload_required` | `shapefile_bundle` | `local_national_clip_then_aoi_clip` | `fields.building.google` | Manual preload only; do not relabel it as remote automation support. |
| `raw.openbuildingmap.building` | manual reference | `manual_preload_required` | `shapefile_bundle` | `local_national_clip_then_aoi_clip` | `fields.building.openbuildingmap` | Locked as preload-only until runtime evidence promotes it. |
| `raw.google.open_buildings.vector` | manual reference | `manual_preload_required` | `shapefile_bundle` | `local_national_clip_then_aoi_clip` | `fields.building.google_open_buildings_vector` | Locked as preload-only until runtime evidence promotes it. |
| `raw.local.microsoft.building` | national cache | `manual_preload_required` | `shapefile_bundle` | `local_cached_national_clip_then_aoi_clip` | `fields.building.microsoft` | Operational cache only; not a distinct public source claim. |

### Road

Current runtime bundles:

- `catalog.flood.road`
- `catalog.earthquake.road`
- `catalog.typhoon.road`

Locked source set:

| Source ID | Role | Acquisition | Format | Clip Strategy | Field Mapping | Claim Boundary |
| --- | --- | --- | --- | --- | --- | --- |
| `raw.osm.road` | primary | `official_remote_supported` | `geofabrik_shapefile_bundle` | `country_bundle_then_clip` | `fields.road.osm` | ODbL-derived source; preserve attribution in fused outputs and evidence. |
| `raw.overture.road` | second-source target | `manual_preload_required` | `parquet_or_geoparquet_extract` | `national_extract_then_aoi_clip` | `fields.road.overture_transportation` | Chosen in B1 as the second national road source, but still deferred until B2 materialization exists. |

Default preload directory for the current B2 slice:

- expected local preload root: `raw.overture.road` -> `Data/roads/Overture/`
- current checked-in snapshot note: no matching Overture Transportation preload bundle is present under that root, so the 2026-05-18 national freeze records `national_scale_partial_reference` instead of full dual-source road support.

### Water

Current runtime bundles:

- `catalog.flood.water`

Locked source set:

| Source ID | Role | Acquisition | Format | Clip Strategy | Field Mapping | Claim Boundary |
| --- | --- | --- | --- | --- | --- | --- |
| `raw.osm.water` | primary | `official_remote_supported` | `geofabrik_shapefile_bundle` | `country_bundle_then_clip` | `fields.water.osm_polygon` | ODbL-derived source; keep line/polygon semantics explicit in claims. |
| `raw.local.water` | current manual reference | `manual_preload_required` | `shapefile_bundle` | `local_national_clip_then_aoi_clip` | `fields.water.local_reference` | Manual local reference only; not a remote automation claim. |
| `raw.hydrorivers.water` | national line reference | `manual_preload_required` | `shapefile_bundle` | `national_line_clip_then_bundle_normalization` | `fields.water.hydrorivers_line` | Locked for B2-B4; preserve upstream hydro attribution. |
| `raw.hydrolakes.water` | national polygon reference | `manual_preload_required` | `shapefile_bundle` | `national_polygon_clip_then_bundle_normalization` | `fields.water.hydrolakes_polygon` | Locked for B2-B4; preserve upstream hydro attribution. |
| `raw.overture.water` | deferred alternative | `reservation_only` | `parquet_or_geoparquet_extract` | `deferred` | `fields.water.overture` | Not part of the first implementation wave. |

Default preload directories for the current B2 slice:

- `raw.local.water` -> `Data/water/布隆迪湖泊.shp`
- `raw.hydrorivers.water` -> `Data/water/BDI.shp`
- `raw.hydrolakes.water` -> `Data/water/布隆迪湖泊.shp`

### POI

Current runtime bundles:

- `catalog.generic.poi`

Locked source set:

| Source ID | Role | Acquisition | Format | Clip Strategy | Field Mapping | Claim Boundary |
| --- | --- | --- | --- | --- | --- | --- |
| `raw.osm.poi` | primary | `official_remote_supported` | `geofabrik_shapefile_bundle` | `country_bundle_then_clip` | `fields.poi.osm` | ODbL-derived source; preserve attribution in normalized and fused POI outputs. |
| `raw.gns.poi` | national reference | `manual_preload_required` | `shapefile_bundle` | `country_shapefile_then_aoi_clip` | `fields.poi.gns` | Manual gazetteer import; keep identifier provenance visible. |
| `raw.rh.poi` | optional manual supplement | `manual_preload_required` | `shapefile_bundle` | `country_shapefile_then_aoi_clip` | `fields.poi.rh` | Local sample only; keep it out of promoted national claims unless explicit evidence is added. |
| `raw.overture.poi` | deferred third source | `reservation_only` | `parquet_or_geoparquet_extract` | `deferred` | `fields.poi.overture_places` | Optional future third source only. |

Default preload paths for the current B2 slice:

- `raw.gns.poi` -> `Data/POI/**/GNS.shp`
- `raw.rh.poi` -> `Data/POI/**/RH.shp`

## Implementation Notes

- B2 must promote the acquisition path, not rewrite this matrix.
- B3 must keep `tile manifest -> source profile -> selected sources ->
  stitched artifact -> inspection summary` consistent across themes.
- B4 must normalize data against the field-mapping profiles named here before
  claiming multi-source fusion parity.
- B5 must produce run evidence against the exact source IDs and claim boundaries
  listed above.
- The current live B5 freeze is `docs/superpowers/specs/2026-05-18-track-b-national-scale-evidence-freeze.json`. It records `road` as `national_scale_partial_reference`, and `water` / `poi` as `national_scale_supported`, with supplemental normalization evidence for `raw.hydrorivers.water`, `raw.hydrolakes.water`, and `raw.rh.poi`.
