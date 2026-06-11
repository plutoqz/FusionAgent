# Track B National Source Matrix

This live spec preserves the first implementation wave source contract for
`Track B` after the 2026-05-13 master plan was completed and archived. It is the
contract that the current Track B evidence freezes and regression hooks continue
to verify.

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
| `raw.microsoft.road` | Task 6 reference | `manual_preload_required` | `shapefile_bundle` | `local_national_clip_then_aoi_clip` | `fields.road.osm` | Local/provider reference candidate for Task 6 source-attempt evidence; do not claim remote acquisition until a resolver exists. |
| `raw.overture.transportation` | compatibility extra | `reservation_only` | `geojson_extract` | `theme_partition_then_clip` | `fields.road.overture_transportation` | Compatibility source for existing Overture road flows; not official full-closure evidence. |
| `raw.overture.road` | optional local preload alias | `manual_preload_required` | `parquet_or_geoparquet_extract` | `national_extract_then_aoi_clip` | `fields.road.overture_transportation` | Local operator cache alias for compatibility-only Overture road flows. |

Default preload directory for the current B2 slice:

- expected local preload root for the Task 6 reference: `raw.microsoft.road` -> `Data/roads/Microsoft/`
- compatibility cache alias: `raw.overture.road` -> `Data/roads/Overture/`

### Water

Current runtime bundles:

- `catalog.flood.water`

Locked source set:

| Source ID | Role | Acquisition | Format | Clip Strategy | Field Mapping | Claim Boundary |
| --- | --- | --- | --- | --- | --- | --- |
| `raw.osm.water` | primary polygon | `official_remote_supported` | `geofabrik_shapefile_bundle` | `country_bundle_then_clip` | `fields.water.osm_polygon` | ODbL-derived polygon water source; keep polygon semantics explicit in claims. |
| `raw.osm.waterways` | primary line | `official_remote_supported` | `geofabrik_shapefile_bundle` | `country_bundle_then_clip` | `fields.water.osm_line` | ODbL-derived line water source; keep line semantics explicit in claims. |
| `raw.local.water` | local cache fallback | `manual_preload_required` | `shapefile_bundle` | `local_national_clip_then_aoi_clip` | `fields.water.local_reference` | Local operator cache only; not a remote automation claim. |
| `raw.hydrorivers.water` | national line reference | `official_remote_supported` | `shapefile_bundle` | `national_line_clip_then_bundle_normalization` | `fields.water.hydrorivers_line` | Promoted B2 line reference; preserve upstream hydro attribution and line-style evidence boundaries. |
| `raw.hydrolakes.water` | national polygon reference | `official_remote_supported` | `shapefile_bundle` | `national_polygon_clip_then_bundle_normalization` | `fields.water.hydrolakes_polygon` | Promoted B2 polygon reference; preserve upstream hydro attribution and polygon-style evidence boundaries. |
| `raw.overture.water` | deferred alternative | `reservation_only` | `parquet_or_geoparquet_extract` | `deferred` | `fields.water.overture` | Not part of the first implementation wave. |

Local cache paths retained for the current B2 slice:

- `raw.local.water` -> `Data/water/布隆迪湖泊.shp`
- `raw.hydrorivers.water` -> `Data/water/BDI.shp`
- `raw.hydrolakes.water` -> `Data/water/布隆迪湖泊.shp`

### Waterways

Current runtime bundles:

- `catalog.flood.waterways`

Locked source set:

| Source ID | Role | Acquisition | Format | Clip Strategy | Field Mapping | Claim Boundary |
| --- | --- | --- | --- | --- | --- | --- |
| `raw.osm.waterways` | primary line | `official_remote_supported` | `geofabrik_shapefile_bundle` | `country_bundle_then_clip` | `fields.waterways.osm` | ODbL-derived waterways line source; keep line semantics explicit in claims. |
| `raw.local.pakistan.waterways` | manual supplement line | `manual_preload_required` | `shapefile_bundle` | `local_national_clip_then_aoi_clip` | `fields.waterways.local_osm_like` | Pakistan local waterways preload only; do not relabel it as HydroRIVERS or remote automation support. |
| `raw.hydrorivers.water` | optional remote line reference | `official_remote_supported` | `shapefile_bundle` | `national_line_clip_then_bundle_normalization` | `fields.waterways.hydrorivers` | Remote hydro line reference stays semantically separate from the local Pakistan waterways supplement. |

Local cache paths retained for the current V7 waterways slice:

- `raw.local.pakistan.waterways` -> `Data/water/Pakistan_Waterways_Data.shp`
- `raw.hydrorivers.water` -> `Data/water/BDI.shp`

### POI

Current runtime bundles:

- `catalog.generic.poi`

Locked source set:

| Source ID | Role | Acquisition | Format | Clip Strategy | Field Mapping | Claim Boundary |
| --- | --- | --- | --- | --- | --- | --- |
| `raw.osm.poi` | primary | `official_remote_supported` | `geofabrik_shapefile_bundle` | `country_bundle_then_clip` | `fields.poi.osm` | ODbL-derived source; preserve attribution in normalized and fused POI outputs. |
| `raw.gns.poi` | national reference | `official_remote_supported` | `country_zip_tabular_export` | `country_zip_then_aoi_clip` | `fields.poi.gns` | Official GNS country export; keep identifier provenance visible in normalized and fused outputs. |
| `raw.geonames.poi` | national reference alias | `official_remote_supported` | `country_zip_tabular_export` | `country_zip_then_aoi_clip` | `fields.poi.gns` | GeoNames/GNS alias for `raw.gns.poi`; reuse the same official remote support and clip strategy. |
| `raw.rh.poi` | optional manual supplement | `manual_preload_required` | `shapefile_bundle` | `country_shapefile_then_aoi_clip` | `fields.poi.rh` | Local sample only; keep it out of promoted national claims unless explicit evidence is added. |
| `raw.overture.poi` | deferred third source | `reservation_only` | `parquet_or_geoparquet_extract` | `deferred` | `fields.poi.overture_places` | Optional future third source only. |

Remote and local acquisition notes for the current B2 slice:

- `raw.gns.poi` -> official GNS country zip discovered from `https://geonames.nga.mil/geonames/GNSData/data/data.json`
- `raw.rh.poi` -> `Data/POI/**/RH.shp`

## Implementation Notes

- B2 must promote the acquisition path, not rewrite this matrix.
- B3 must keep `tile manifest -> source profile -> selected sources ->
  stitched artifact -> inspection summary` consistent across themes.
- B4 must normalize data against the field-mapping profiles named here before
  claiming multi-source fusion parity.
- B5 must produce run evidence against the exact source IDs and claim boundaries
  listed above.
- The current live B5 freeze is `docs/superpowers/specs/2026-05-18-track-b-national-scale-evidence-freeze.json`. It must reference the promoted source ids (`raw.microsoft.road`, `raw.hydrolakes.water`, `raw.gns.poi`) once refreshed, while preserving bounded claim-state wording if a second-source artifact is still absent at runtime.
