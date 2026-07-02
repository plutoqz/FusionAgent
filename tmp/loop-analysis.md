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
