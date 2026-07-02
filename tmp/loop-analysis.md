## Round 1 analysis - 2026-07-02T19:03:39+08:00

- **Area ID**: AS-10
- **Query**: fuse building data for conflict response in Mahalle Fatih, Istanbul, Turkey
- **Job Type**: building | **Disaster**: conflict
- **Original Run ID**: 57ea69646885462cb752fbd5ca9698c9
- **Fixed Verification Run ID**: e0cfcef334f8497faedf8bd0d8197bce
- **Status**: succeeded after fixes | **Duration**: 27s
- **Admin Level**: country
- **Clip Mode**: degraded bbox (`degraded_bbox_clip=true`)

### Issue 1: Humanitarian response phrase leaked into AOI query

- **Stage**: task parsing / AOI resolution
- **Direct Cause**: `services/aoi_resolution_service.py:225` extracts location candidates from the original query and `_clean_location_phrase` previously did not remove phrases like `{disaster} response in ...`; `services/agent_run_service.py:1025` then passed the contaminated AOI query into `AOIResolutionService.resolve`.
- **Trigger Conditions**: `task_driven_auto` user query with no explicit bbox, shaped like `fuse {task_type} data for {disaster_type} response in {admin_area}`.
- **Similar Scope**: `conflict response in ...`; `wildfire relief near ...`; `drought recovery within ...`; `emergency operations around ...`.
- **Why Guards Failed**: existing disaster prefix/suffix cleanup only covered simple `flood in ...` or suffix forms, so `response/relief/recovery/operations` phrases were treated as location text and sent to geocoding.
- **Fix**: generalized disaster/context terms and response-prefix cleanup in `services/aoi_resolution_service.py`, with regression coverage in `tests/test_aoi_resolution_service.py`.

### Issue 2: Source acquisition could run without readable progress or bounded timeout

- **Stage**: data download / input acquisition
- **Direct Cause**: after `data_requirements_resolved`, `services/agent_run_service.py:1557` entered task-driven input materialization without a reliable external progress watchdog; the first thread-based watchdog could still starve or block in the same process. `services/source_asset_service.py:1797` also allowed curl fallback downloads without a subprocess hard timeout.
- **Trigger Conditions**: task-driven source materialization using catalog/raw sources that may download or parse external source assets while the API request waits synchronously.
- **Similar Scope**: `catalog.earthquake.building`; `catalog.flood.building`; OSM/Geofabrik building/road/water; Microsoft building; Google/GNS/HydroSHEDS/Overture remote acquisition paths.
- **Why Guards Failed**: lower-level requests had partial timeouts, but orchestration wrote audit events only after the blocking call returned; curl fallback lacked a hard subprocess timeout; a same-process watchdog could be delayed by acquisition work and service locks.
- **Fix**: added source acquisition started/heartbeat/materialized/failed audit events, a process-based watchdog in `services/source_acquisition_watchdog.py`, timeout markers that prevent late success from overwriting a terminal timeout, and curl hard timeout enforcement in `services/source_asset_service.py`; tests cover normal blocking and lock-held watchdog paths.

### Evidence Note: Area Boundary Degraded

- **Observation**: the successful verification run resolved `Mahalle Fatih, Istanbul, Turkey` to a node/suburb result in Tuzla with `admin_level=country` and `degraded_bbox_clip=true`.
- **Impact**: this round verifies the system fixes and artifact generation, but it does not count as a successful administrative boundary clip sample for the first-stage completion criteria.
- **Follow-up**: avoid reusing AS-10 as a boundary-success candidate unless the query is refined to a Nominatim administrative boundary result.

## Round 2 analysis - 2026-07-02T20:10:30+08:00

- **Area ID**: AS-01
- **Query**: fuse building data for flood response in Saddar Town, Karachi, Pakistan
- **Job Type**: building | **Disaster**: flood
- **Original Run ID**: eb567ec0434849f2ae2ad00a4444d950
- **Fixed Verification Run ID**: eac4b961985d41c6a1978890a484457c
- **Status**: succeeded after fix | **Duration**: 465s
- **Admin Level**: city
- **Clip Mode**: degraded bbox (`degraded_bbox_clip=true`)

### Issue 1: Normalizer overrode a more specific administrative AOI phrase

- **Stage**: task parsing / AOI resolution
- **Direct Cause**: `services/aoi_resolution_service.py:259` returned `normalize_scenario_trigger_text(...).normalized_location` before parsing and cleaning explicit `for/in/near/around` location phrases. `services/scenario_trigger_normalizer.py:96` recognized only the broader city/country alias (`Karachi, Pakistan`), so the more specific `Saddar Town` qualifier was dropped.
- **Trigger Conditions**: `task_driven_auto` user query where a humanitarian response prefix is followed by a specific administrative unit containing a known broader city/country alias.
- **Similar Scope**: `Saddar Town, Karachi, Pakistan`; `Ward 26, Kathmandu, Nepal`; `Barangay 656, Intramuros, Manila, Philippines`; `Kariakoo Ward, Ilala, Dar es Salaam, Tanzania`.
- **Why Guards Failed**: `_clean_location_phrase` could correctly remove `flood response in`, but it was bypassed by the normalizer early return whenever the normalizer found a broader alias.
- **Fix**: `extract_location_query` now compares explicit cleaned phrases against normalized aliases and preserves the more specific administrative phrase when the normalized location is only a subset; tests cover Town/Ward/Barangay qualifiers.

### Evidence Note: Area Boundary Degraded

- **Observation**: the successful verification run resolved `Saddar Town, Karachi, Pakistan`, but boundary matching still fell back to bbox (`degraded_bbox_clip=true`).
- **Impact**: artifact integrity and geometry checks passed, but this round does not count as a boundary-clip success sample for the first-stage completion criteria.

## Round 3 analysis - 2026-07-02T22:07:12+08:00

- **Area ID**: AM-04
- **Query**: fuse building data for flood response in Distrito de Arequipa Cercado, Peru
- **Job Type**: building | **Disaster**: flood
- **Original Run ID**: bf45ae67485d46d0a6e767f0e87c1c1c
- **Intermediate Run IDs**: 70368c72cbec4e56b4bd6533675469f5, 6e31b34a184a43d7a63ebd12847150b5
- **Fixed Verification Run ID**: 43ea545db82e4865a57a6c07551f7e7c
- **Status**: succeeded after fixes | **Duration**: 28s
- **Admin Level**: city
- **Clip Mode**: degraded bbox (`degraded_bbox_clip=true`)

### Issue 1: Administrative prefix exact query produced no AOI candidates

- **Stage**: task parsing / AOI resolution
- **Direct Cause**: `services/aoi_resolution_service.py:337` resolved only the extracted location string against the geocoder. When Nominatim had no exact result for an administrative prefix form like `Distrito de Arequipa Cercado, Peru`, the service raised `AOI_RESOLUTION_FAILED` before trying reasonable administrative aliases.
- **Trigger Conditions**: task-driven location phrases that include localized administrative type prefixes plus qualifiers, especially `Distrito de ...`, `Freguesia de ...`, `Comuna ...`, `Quartier ...`, and similar OSM/Nominatim naming variants.
- **Similar Scope**: `Distrito de Arequipa Cercado, Peru`; `Freguesia de Se, Sao Paulo, Brazil`; `Quartier Centre, Rennes, France`; `Comuna San Jose, Manizales, Colombia`.
- **Why Guards Failed**: earlier phrase cleanup preserved the specific AOI text, but the geocoder layer had no alias expansion for administrative unit prefixes or trailing qualifiers such as `Cercado`/`Centro`.
- **Fix**: `_geocoder_query_candidates` and `_administrative_location_aliases` now generate ordered administrative aliases while preserving the original query; tests cover Spanish and Portuguese prefix forms.

### Issue 2: Alias result could still be rejected as ambiguous

- **Stage**: task parsing / AOI resolution
- **Direct Cause**: `_select_candidate` raises `AOIAmbiguityError` at `services/aoi_resolution_service.py:486`; after alias expansion, `resolve` still stopped on the first alias whose candidate set was ambiguous instead of trying the next alias query.
- **Trigger Conditions**: an exact administrative alias returns multiple plausible candidates, but a later alias form is specific enough to return a single administrative candidate.
- **Similar Scope**: `Arequipa Cercado` vs `Cercado de Arequipa`; `Centro de ...` variants; localized district names where the qualifier can appear before or after the parent city.
- **Why Guards Failed**: ambiguity handling treated a single geocoder query as terminal, so the broader alias blocked later, more discriminating aliases in the same location expression.
- **Fix**: `resolve` now keeps the last ambiguity but continues through remaining geocoder query candidates; only raises ambiguity if no alias resolves successfully. Regression coverage is in `tests/test_aoi_resolution_service.py`.

### Issue 3: Source candidate selection ignored disaster text and timeout fallback

- **Stage**: data download / input acquisition
- **Direct Cause**: `_filter_disaster_compatible_sources` used only structured `plan.trigger.disaster_type`; task-driven plans carried `disaster_type=null` even when the user query contained `flood response`, so `_resolve_execution_inputs` at `services/agent_run_service.py:1515` selected `catalog.earthquake.building` first. On timeout, the `SourceAcquisitionTimeoutError` handler at `services/agent_run_service.py:1590` recorded failure with `will_try_next_candidate=false` and raised instead of trying the second candidate.
- **Trigger Conditions**: task-driven source materialization where the disaster is present in natural-language content or workflow id but not bound to `RunTrigger.disaster_type`, and the first selected source is slow/unavailable while another compatible source exists.
- **Similar Scope**: flood/earthquake/hurricane/wildfire/conflict/typhoon queries with null structured disaster type; road/building/water/poi source candidates with provider timeout; catalog source fallback when the top source is stale, missing, or outside coverage.
- **Why Guards Failed**: source fallback handled some `SOURCE_MISSING`/empty coverage errors, but timeout was treated as terminal; disaster-aware filtering did not infer from query text or selected workflow pattern.
- **Fix**: timeout and fallback-class acquisition failures now continue to the next candidate when present; watchdog timeout events accurately report `will_try_next_candidate`; `_plan_disaster_type` infers common disaster types from trigger/content/workflow/pattern text. Tests cover source timeout fallback and null structured disaster with `flood response` text.

### Evidence Note: Area Boundary Degraded

- **Observation**: the successful verification run resolved to `Arequipa, Peru` with `admin_level=city` and `degraded_bbox_clip=true`.
- **Impact**: artifact integrity and geometry checks passed with 19,823 non-empty building geometries, but this round does not count as a boundary-clip success sample for the first-stage completion criteria.

## Round 4 analysis - 2026-07-02T22:42:31+08:00

- **Area ID**: AF-06
- **Query**: fuse road data for flood response in Arrondissement de Ouando, Porto-Novo, Benin
- **Job Type**: road | **Disaster**: flood
- **Original Run ID**: efdd2a5bacd14e348a64d3b578b8044d
- **Fixed Verification Run ID**: 6bb9aadfcdb04311ac1b31e5c6874cbf
- **Status**: succeeded after fixes | **Verification Duration**: 12s
- **Admin Level**: neighbourhood
- **Clip Mode**: degraded bbox (`degraded_bbox_clip=true`)

### Issue 1: AOI selection preferred a POI over the requested administrative place

- **Stage**: task parsing / AOI resolution
- **Direct Cause**: `services/aoi_resolution_service.py:652` derived `admin_level=city` from the POI's address context instead of the candidate's own Nominatim category/type, and `services/aoi_resolution_service.py:453` accepted the higher-importance `amenity/library` result via `top_confidence_margin` before considering the lower-importance `place/neighbourhood` candidate.
- **Trigger Conditions**: task-driven queries with an administrative prefix such as `Arrondissement de ...` where Nominatim returns a named amenity inside the requested place with higher importance than the actual place/neighbourhood result.
- **Similar Scope**: `District ...` queries returning hospitals or universities; `Ward ...` queries returning schools; `Quartier ...` queries returning museums or public buildings; `Freguesia ...` queries returning churches inside the parish.
- **Why Guards Failed**: alias expansion preserved the administrative phrase, but candidate ranking had no POI-vs-place guard and the admin-level normalizer treated containment address fields as if they described the candidate itself.
- **Fix**: AOI candidate normalization now distinguishes area candidates (`boundary`/`place` and administrative-like types) from POIs, avoids deriving admin level from POI containment addresses, and prefers area candidates when the query uses an administrative unit prefix. Regression coverage is in `tests/test_aoi_resolution_service.py`.

### Issue 2: Successful GPKG writeback produced a non-standard artifact ZIP

- **Stage**: writeback / artifact packaging
- **Direct Cause**: `services/agent_run_service.py:2480` bypassed `zip_shapefile_bundle` for `.gpkg` outputs and wrote the GeoPackage as the only ZIP member.
- **Trigger Conditions**: shared large-area runtime or repaired output produces a `.gpkg` final artifact, especially road/building/water/poi large-area writeback paths.
- **Similar Scope**: repaired road GeoPackage outputs; tiled building stitched GeoPackages; water or POI runners that emit GeoPackage; any future domain runner using the common `_write(..., driver="GPKG")` path.
- **Why Guards Failed**: schema and quality validation read the GeoPackage successfully, but artifact integrity validation in the loop expects a Shapefile bundle; no writeback guard converted GPKG results to the public Shapefile ZIP contract.
- **Fix**: `.gpkg` writeback now converts to a Shapefile bundle before zipping, with sanitized stems for repaired filenames such as `.repair-1.gpkg`. Regression coverage is in `tests/test_agent_run_service_multisource_building_runtime.py`.

### Evidence Note: Boundary Still Degraded

- **Observation**: final verification selected `Ouando, Porto-Novo, Porto Novo, Oueme, Benin` with `admin_level=neighbourhood`, not the POI library, and artifact integrity passed with `.shp/.shx/.dbf/.prj`, 600 non-empty geometries, and CRS `EPSG:32631`.
- **Impact**: this round verifies AOI candidate preference and artifact packaging, but still does not count as a boundary-clip success sample because local administrative boundary matching fell back to bbox.

## Round 5 analysis - 2026-07-02T23:10:42+08:00

- **Area ID**: AF-01
- **Query**: fuse poi data for earthquake response in Commune de Gitega, Burundi
- **Job Type**: poi | **Disaster**: earthquake
- **Original Run ID**: c5bf58e9fd044976b3d745bf70d89711
- **Fixed Verification Run ID**: 672849e9026b478d9f485c1740122722
- **Status**: succeeded after fix | **Verification Duration**: 44s
- **Admin Level**: city
- **Clip Mode**: degraded bbox (`degraded_bbox_clip=true`)

### Issue 1: Administrative alias chain stopped on a single POI candidate

- **Stage**: task parsing / AOI resolution
- **Direct Cause**: `services/aoi_resolution_service.py:468` filters area candidates only when they exist, but `services/aoi_resolution_service.py:474` still accepts a single non-area `amenity/townhall` candidate with `selection_reason=single_candidate`; this prevents `_geocoder_query_candidates` at `services/aoi_resolution_service.py:189` from trying the generated alias `Gitega, Burundi`.
- **Trigger Conditions**: administrative-unit queries such as `Commune de ...`, `District ...`, or `Ward ...` where the exact prefixed form returns one POI/amenity and a later alias would resolve to the actual place or boundary.
- **Similar Scope**: town halls for communes; schools for wards; churches for freguesias; municipal offices for districts.
- **Why Guards Failed**: Round 4 added a preference when area candidates are present, but there was no rejection path when an administrative query returns only unsuitable POI candidates.
- **Fix**: administrative-unit queries now reject all-POI candidate sets so `resolve` continues through later geocoder aliases; regression coverage is in `tests/test_aoi_resolution_service.py`.

### Evidence Note: Boundary Still Degraded

- **Observation**: final verification selected `Gitega, Burundi` (`place/city`) instead of the townhall POI, and artifact integrity passed with `.shp/.shx/.dbf/.prj`, 966 non-empty geometries, and CRS `EPSG:32735`.
- **Impact**: this round verifies the alias-chain fallback for single-POI administrative hits, but still does not count as a boundary-clip success sample because local administrative boundary matching fell back to bbox.

## Round 6 analysis - 2026-07-02T23:35:12+08:00

- **Area ID**: EU-01
- **Query**: fuse building data for flood response in Quartier Centre, Rennes, France
- **Job Type**: building | **Disaster**: flood
- **Original Run ID**: 0d19311b59aa4683bb45df86cb580a95
- **Intermediate Run ID**: 73ceb5b36e024fbd8de1f18ec0bc12de
- **Fixed Verification Run ID**: 5b0f484ebb9f45acbada06a31edade9c
- **Status**: succeeded after fixes | **Verification Duration**: 55s
- **Admin Level**: suburb
- **Clip Mode**: degraded bbox (`degraded_bbox_clip=true`)

### Issue 1: Local runtime kept the internal source acquisition timeout at 600s

- **Stage**: data download / input acquisition
- **Direct Cause**: `services/agent_run_service.py:2005` reads `GEOFUSION_INPUT_ACQUISITION_TIMEOUT_SECONDS` and falls back to `DEFAULT_INPUT_ACQUISITION_TIMEOUT_SECONDS=600`, while `scripts/start_local.py` had no CLI argument to set that env var for long loop runs. The smoke command used `--timeout 1800`, but the server-side watchdog still emitted `source_acquisition_failed` at 600s.
- **Trigger Conditions**: task-driven source materialization for a slow but still-running source download, especially building bundles whose external provider fetch can exceed 600s while the operator has intentionally allowed a longer end-to-end run budget.
- **Similar Scope**: large/slow building downloads; cold Geofabrik/OSM source cache; any remote catalog materialization where the outer smoke/API timeout is larger than the internal source acquisition watchdog.
- **Why Guards Failed**: heartbeat/watchdog observability worked, but the runtime startup path did not expose the supported timeout knob, so operator intent to allow longer runs was not propagated into the API/worker environment.
- **Fix**: `scripts/start_local.py` now accepts `--input-acquisition-timeout` and writes `GEOFUSION_INPUT_ACQUISITION_TIMEOUT_SECONDS` into the local runtime environment. Regression coverage is in `tests/test_local_runtime.py`.

### Issue 2: Registry cache hit reused an incomplete physical bundle

- **Stage**: data download / input acquisition
- **Direct Cause**: `services/input_acquisition_service.py:196` and related cache-hit branches call `_copy_cached_bundle(...)` after the artifact registry reports a reusable source version, but `_copy_cached_bundle` at `services/input_acquisition_service.py:486` blindly copies `osm.zip` and `ref.zip`. The stale cache entry for `catalog.flood.building` pointed at `input_bundle_cache/catalog_flood_building/v_469c590b2ef48bba/bae15f071e05`, where `osm.zip` was missing, so the run failed with `FileNotFoundError`.
- **Trigger Conditions**: a previous source acquisition times out or is cleaned after registry metadata has been written, leaving a bundle directory or registry record without both physical ZIP members.
- **Similar Scope**: any cached task-driven source bundle for building/road/water/poi; clipped cached bundle reuse; provider fallback bundles whose registry entry survives but one ZIP file is deleted, zero-byte, or corrupt.
- **Why Guards Failed**: source version matching verified only metadata freshness. The cache reuse path had no physical completeness or ZIP validity check before copying/clipping cached inputs, so a recoverable stale cache became a terminal source acquisition failure.
- **Fix Direction**: treat incomplete or invalid cached bundles as cache misses before copy/clip reuse, then materialize a fresh bundle from the provider and cover the path with a regression test.
- **Fix**: cache reuse now requires both `osm.zip` and `ref.zip` to exist, be non-empty, and be readable ZIP archives before copy/clip reuse; incomplete bundles are treated as cache misses and refreshed. Regression coverage is in `tests/test_input_acquisition_service.py`.

### Evidence Note: Boundary Still Degraded

- **Observation**: final verification selected `Centre, Quartiers Centre, Rennes, Ille-et-Vilaine, Bretagne, France metropolitaine, France` with `admin_level=suburb`; source acquisition used `timeout_seconds=1800.0`, materialized fresh inputs with `source_mode=downloaded` and `cache_hit=false`, and completed in 22.6s.
- **Artifact Integrity**: `building_fusion_result.zip` contains `.shp/.shx/.dbf/.prj` plus `.cpg`; 3,916 building geometries are non-empty; CRS is `EPSG:32630`.
- **Impact**: this round verifies long acquisition timeout propagation and stale cache invalidation, but still does not count as a boundary-clip success sample because local administrative boundary matching fell back to bbox.

## Round 7 analysis - 2026-07-03T00:22:10+08:00

- **Area ID**: OC-02
- **Query**: fuse poi data for flood response in Ward 1, Port Moresby, Papua New Guinea
- **Job Type**: poi | **Disaster**: flood
- **Original Run ID**: f0ebad14283a4bf2adaa38fa15c94fe1
- **Fixed Verification Run ID**: 6c4e31f3ae2542e1ac5c38667e544c8e
- **Status**: blocked after fix (`AOIAmbiguityError`) | **Original Duration**: 157s
- **Admin Level**: city
- **Clip Mode**: degraded bbox (`degraded_bbox_clip=true`)

### Issue 1: Numbered administrative unit query was widened to the parent city

- **Stage**: task parsing / AOI resolution
- **Direct Cause**: `services/aoi_resolution_service.py:468` treats any area-like candidate as acceptable for an administrative query; `_is_area_candidate` accepts `place/city`, and the single-candidate branch at `services/aoi_resolution_service.py:480` returned Port Moresby even though the requested primary unit was `Ward 1`.
- **Trigger Conditions**: administrative-unit queries with a numbered unit name, such as `Ward 1, ...`, where Nominatim returns only the parent city/place candidate instead of a ward-level candidate.
- **Similar Scope**: `Ward 26, Kathmandu, Nepal`; `District 1, ...`; `Barangay 656, ...`; numeric sectors/zones where the geocoder falls back to a parent city.
- **Why Guards Failed**: prior POI-vs-area guards checked candidate type, but not whether an administrative prefix query preserved the requested numbered unit. A parent city is an area, so it passed the administrative preference filter and the loop ran against an oversized bbox.
- **Fix Direction**: for numbered administrative-unit queries, require the selected area candidate to preserve both the administrative kind and number (for example `ward` + `1`) in its own name/type/address evidence; otherwise treat the result as unresolved/ambiguous and continue aliases or fail early.
- **Fix**: numbered administrative-unit queries now reject parent area candidates unless the candidate evidence preserves the requested kind and number; candidate admin-level derivation also prefers the candidate's own `type/addresstype` over parent address context. Regression coverage is in `tests/test_aoi_resolution_service.py`.

### Evidence Note: Correctly Blocked Invalid AOI

- **Observation**: fixed verification run `6c4e31f3ae2542e1ac5c38667e544c8e` fails at AOI resolution with `AOIAmbiguityError: Ambiguous AOI query: Ward 1, Port Moresby, Papua New Guinea` instead of running against the parent Port Moresby city bbox.
- **Artifact Integrity**: original anomalous run produced a valid POI Shapefile bundle with 366 non-empty geometries and CRS `EPSG:32755`, but the AOI was too broad and should not count as a valid loop success.
- **Impact**: this fixes the silent broadening class for numbered wards/districts/barangays. `OC-02` should be treated as blocked for the current candidate pool unless a ward-level geocoder result becomes available.

## Round 8 analysis - 2026-07-03T00:35:10+08:00

- **Area ID**: EU-05
- **Query**: fuse poi data for flood response in Deelgemeente Leuven Centrum, Belgium
- **Job Type**: poi | **Disaster**: flood
- **Run ID**: 0d9a874e60fd4818bfc8783814a50322
- **Status**: blocked (`AOI_RESOLUTION_FAILED`) | **Duration**: 4s
- **Admin Level**: N/A
- **Clip Mode**: unknown

### Blocked Candidate: Nominatim has no administrative AOI for the provided name

- **Stage**: task parsing / AOI resolution
- **Direct Cause**: the geocoder returned no candidates for `Deelgemeente Leuven Centrum, Belgium`, so `services/aoi_resolution_service.py:391` raised `AOI_RESOLUTION_FAILED`.
- **Trigger Conditions**: candidate-pool area names that are not resolvable as OSM/Nominatim administrative areas and whose reasonable aliases either return no result or only POIs / broader city results.
- **Similar Scope**: localized or unofficial district labels absent from OSM; translated administrative labels not used by Nominatim; city-centre labels that resolve only to amenities.
- **Why Guards Worked**: after Round 7, the resolver does not silently broaden unsafe administrative queries; this run failed before source acquisition or execution.
- **Disposition**: treat `EU-05` as blocked for the current loop candidate pool; no code fix is required unless future evidence shows a resolvable administrative alias should have been generated.

## Round 9 analysis - 2026-07-03T00:46:30+08:00

- **Area ID**: AS-03
- **Query**: fuse poi data for flood response in Ward 18, Dhaka North City Corporation, Bangladesh
- **Job Type**: poi | **Disaster**: flood
- **Run ID**: 07d44d1e1f8c4578a522f1d098e73150
- **Status**: blocked (`AOIAmbiguityError`) | **Duration**: 2s
- **Admin Level**: N/A
- **Clip Mode**: unknown

### Blocked Candidate: Nominatim has no ward-level administrative AOI for Ward 18

- **Stage**: task parsing / AOI resolution
- **Direct Cause**: the exact geocoder query `Ward 18, Dhaka North City Corporation, Bangladesh` returned zero candidates; the generated alias `Dhaka North City Corporation, Bangladesh` returned only an `office/government` POI, so `services/aoi_resolution_service.py:481` raised `AOIAmbiguityError` after the administrative-area filter found no acceptable ward-level area candidate.
- **Trigger Conditions**: numbered administrative-unit queries where the geocoder lacks the requested unit geometry/name and either returns no result or returns a parent-city / municipal-office substitute.
- **Similar Scope**: `Ward 1, Port Moresby, Papua New Guinea`; `Ward 26, Kathmandu Metropolitan City, Nepal`; numeric barangay/sector/district labels when OSM/Nominatim only indexes a parent city or an amenity with the administrative name.
- **Why Guards Worked**: the Round 7 numbered-unit guard requires the selected candidate to preserve both the requested administrative kind and number. That prevented silent broadening to Dhaka city or a municipal-office POI and failed before source acquisition.
- **Disposition**: treat `AS-03` as blocked for the current loop candidate pool; no code fix is required unless future evidence shows a stable ward-level alias that should be generated generically.
