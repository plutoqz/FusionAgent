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
