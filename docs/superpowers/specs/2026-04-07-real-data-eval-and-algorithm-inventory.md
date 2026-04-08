# FusionAgent Real-Data Evaluation and Algorithm Inventory

## Purpose

This note turns the current codebase and `Data/` folder into a concrete next-step artifact:

- an inventory of what algorithms are actually implemented,
- which ones are already agent-connectable,
- which parameters are truly exposed in code versus only modeled in KG,
- and a real-data evaluation matrix that can guide the next implementation stage.

The inventory below is based on actual code under `Algorithm/`, current adapters under `adapters/`, runtime plumbing under `agent/executor.py`, and the datasets already present under `Data/`.

## Current Integration Status

| Family | Primary code entrypoints | Current agent integration | Parameterization status | Immediate judgment |
| --- | --- | --- | --- | --- |
| `building` | `Algorithm/build.py`, `adapters/building_adapter.py` | Connected | Partial | Usable now, but runtime parameters are still hard-coded in behavior |
| `road` | `Algorithm/line.py`, `adapters/road_adapter.py` | Connected | Partial | Usable now, but runtime parameters are still hard-coded in behavior |
| `water_line` | `Algorithm/water_line.py` | Not connected | None | Legacy algorithm exists; adapter/KG/pattern are missing |
| `water_polygon` | `Algorithm/water_polygon.py` | Not connected | None | Legacy algorithm exists; adapter/KG/pattern are missing |
| `poi` | `Algorithm/code/Process_GNS.py`, `Algorithm/code/OSM_zhenghe.py`, `Algorithm/code/RH_GNS_OSM.py` | Not connected | None | Pipeline exists, but it is still Excel-script oriented rather than agent-ready |

Two structural facts matter:

- `agent/executor.py` already passes `task.input.parameters` into handlers via `ExecutionContext.step_parameters`.
- Current adapters only exist for `building` and `road`, and both accept `parameters`, but neither actually applies those parameter values to the legacy algorithm yet.

## Algorithm Inventory

### 1. Building Fusion

- Code:
  - `Algorithm/build.py`
  - `adapters/building_adapter.py`
- Main callable path in agent:
  - `adapters.building_adapter.run_building_fusion(...)`
- Legacy functions actually used:
  - `add_index_column`
  - `add_index_column1`
  - `remove_duplicate_geometries_direct`
  - `find_non_intersecting_buildings`
  - `calculate_similarity`
  - `get_data_var`
  - `split_relations`
  - `get_sim`
  - `attribute_fusion1/2/3/4/5`
  - `filter_non_intersecting_osm`

Expected inputs:

- OSM building polygons with fields normalized to `osm_id`, `fclass`, `name`, `type`, `geometry`
- Reference building polygons with fields normalized to `longitude`, `latitude`, `area_in_me`, `confidence`, `geometry`
- The adapter can absorb heterogeneous source schemas through `field_mapping`

Main stages:

1. Read and normalize OSM/reference polygons.
2. Add synthetic IDs and remove duplicate geometries.
3. Identify non-intersecting OSM buildings directly retained.
4. Compute pair similarity.
5. Mark matched pairs using a similarity threshold.
6. Split matched relations into `1:1`, `1:n`, `n:1`, `n:m`.
7. Apply different attribute fusion rules per relation type.
8. Concatenate retained OSM, non-matched results, and fused outputs into the final shapefile.

Clearly exposed thresholds in code:

- In `adapters/building_adapter.py`:
  - `similarity > 0.3` marks a pair as matched.
  - In `1:1` results, `sim_area >= 0.3`, `sim_shape >= 0.3`, `sim_overlap >= 0.3` selects the stronger one-to-one fusion path.
- In `Algorithm/build.py`:
  - `sim_location = 1 - distance / 70`
  - shape/orientation/overlap metrics are explicitly computed in `get_sim(...)`

Output:

- Shapefile `fused_buildings.shp`
- Geometry remains polygonal
- Output columns are the merged union of retained and fused building attributes after dropping temporary IDs

Notable risks:

- Thresholds are hard-coded in adapter logic, not driven by `parameters`.
- Similarity design assumes projected CRS for geometry-based comparison; incorrect CRS handling will distort scores.
- Large reference sets, especially the national Microsoft building layer, will be memory-heavy.
- The adapter uses centroid extraction on geographic CRS before reprojection fallback paths in some branches, which is already producing warnings elsewhere in tests.

Agent parameterization assessment:

- `partial`
- Good news: the interface is ready and KG already models building parameter specs in `kg/seed.py`.
- Gap: the adapter does not yet read values like `match_similarity_threshold` or the three `one_to_one_min_*` thresholds from `parameters`.

### 2. Road Fusion

- Code:
  - `Algorithm/line.py`
  - `adapters/road_adapter.py`
- Main callable path in agent:
  - `adapters.road_adapter.run_road_fusion(...)`
- Legacy functions actually used:
  - `process_osm_data`
  - `process_msft_data`
  - `split_features_in_gdf`
  - `match_and_fuse`
  - `process_roads`

Expected inputs:

- OSM road lines, normalized to include `osm_id`, `fclass`, `geometry`
- Reference road lines, normalized to include `FID_1`, `geometry`
- Mixed `LineString` and `MultiLineString` are accepted

Main stages:

1. Normalize schema and CRS.
2. Split roads at sharp turns.
3. Match OSM/reference lines using buffer search plus Hausdorff and angle constraints.
4. Persist raw fused result to intermediate shapefile.
5. Run post-fusion deduplication with road containment/buffer logic.
6. Write final `fused_roads.shp`.

Clearly exposed thresholds in code:

- `Algorithm/line.py`
  - `ANGLE_THRESHOLD = 135`
  - `BUFFER_DIST = 20`
  - `MAX_HAUSDORFF = 15`
  - Matching also requires `len_sim > 0.2` and `angle_diff < 45`
  - `adjust_road_endpoints(..., buffer_radius=15)`
  - `process_roads(..., buffer_distance=10)` by default
- `adapters/road_adapter.py`
  - Uses `legacy_line.ANGLE_THRESHOLD`
  - Calls `process_roads(..., buffer_distance=15)` in the current adapter path

Output:

- Shapefile `fused_roads.shp`
- Geometry is line-based
- Intermediate artifacts are written under sibling `intermediate/`

Notable risks:

- Threshold values are split between legacy constants and adapter overrides.
- The adapter accepts `parameters` but ignores them today.
- Deduplication behavior is sensitive to `buffer_distance`; changing it may materially alter topology.
- The function naming still reflects a Microsoft reference source (`process_msft_data`), but the repo currently does not clearly expose a second authoritative road source in `Data/roads/`.

Agent parameterization assessment:

- `partial`
- Good news: KG parameter specs already exist in `kg/seed.py` for angle, snap tolerance, match buffer, Hausdorff, and dedupe buffer.
- Gap: the adapter does not yet bind those specs into legacy constants or function arguments.

### 3. Water Line Fusion

- Code:
  - `Algorithm/water_line.py`
- No current adapter under `adapters/`
- No current KG `AlgorithmNode`, `DataTypeNode`, or workflow pattern

Primary functions:

- `process_osm_data`
- `process_water_data`
- `split_features_in_gdf`
- `match_and_fuse_optimized`
- `merge_by_fid_and_code`
- `erase_lines_by_polygon`

Expected inputs:

- OSM-like water line features
- Reference hydro line features
- Optional polygon layer for erasing/cleaning line segments

Main stages:

1. Normalize and preprocess OSM/reference water lines.
2. Split at sharp turns.
3. Match by spatial buffer, Hausdorff distance, angle difference, and line-length similarity.
4. Merge by identifiers and codes.
5. Optionally erase lines by polygon masks.
6. Repair invalid geometry with `buffer(0)` in some branches.

Clearly exposed thresholds in code:

- `ANGLE_THRESHOLD = 135`
- `BUFFER_DIST = 20`
- `MAX_HAUSDORFF = 15`
- Matching requires `len_sim > 0.2` and `angle_diff < 45`
- Geohash is not involved here; this is geometry-first matching

Output:

- Fused line shapefile, but no repo-level adapter currently standardizes output naming or schema

Notable risks:

- No agent adapter, so current runtime cannot call it through the orchestration path.
- No standardized field normalization layer.
- Extra geometry repair and erase logic means integration needs a more careful contract than building/road.

Agent parameterization assessment:

- `none`
- The implementation is legacy-script capable but not yet agent-ready.

### 4. Water Polygon Fusion

- Code:
  - `Algorithm/water_polygon.py`
- No current adapter under `adapters/`
- No current KG `AlgorithmNode`, `DataTypeNode`, or workflow pattern

Primary functions:

- `add_index_to_gdf`
- `spatial_match_with_rtree`
- `add_unmatched_new_water`

Expected inputs:

- OSM water polygons with `OSM_ID`
- Reference water polygons with `NEW_ID`

Main stages:

1. Add explicit IDs to both polygon layers.
2. Match polygons with R-tree candidate retrieval.
3. Compute overlap ratio against OSM polygon area.
4. Attach attributes from matched new polygons into `NEW_*` columns.
5. Append unmatched reference polygons into the final result.

Clearly exposed thresholds in code:

- `overlap_threshold=0.1` in `spatial_match_with_rtree(...)`

Output:

- Polygon shapefile containing matched OSM polygons plus unmatched reference polygons
- Output schema includes `MATCHED_NEW_ID`, `OVERLAP_RATIO`, `MATCH_COUNT`, and prefixed `NEW_*` attributes

Notable risks:

- Attribute aggregation uses string concatenation for repeated matches, which can get messy quickly.
- No adapter means no schema normalization, no field mapping, and no runtime parameter binding.
- The algorithm is simple enough to wrap quickly, but it still needs a formal output contract.

Agent parameterization assessment:

- `none`
- The only explicit threshold is easy to expose, but no runtime plumbing exists yet.

### 5. POI Fusion Pipeline

- Code:
  - `Algorithm/code/Process_GNS.py`
  - `Algorithm/code/OSM_zhenghe.py`
  - `Algorithm/code/RH_GNS_OSM.py`
  - `Algorithm/code/RongHe_GN_GNS.py`
  - `Algorithm/code/add_dam.py`
- No current adapter under `adapters/`
- No current KG `AlgorithmNode`, `DataTypeNode`, or workflow pattern

Primary callable stages:

- `Process_GNS.GNS_to_RH(fileGNS, fileout)`
- `OSM_zhenghe.osm_poi_to_excel(current_folder)`
- `OSM_zhenghe.merge_xlsx_files(input_folder, output_file)`
- `RH_GNS_OSM.PIPEI_PUBLIC(GNS_file, OSM_file, label_file, PIPEI_file, RH_file)`
- optional `RH_GNS_OSM.excel_to_shapefile(input_excel, output_shp)`

Expected inputs:

- GNS source in shapefile/Excel-converted form
- OSM POI shapefiles converted to Excel
- label taxonomy file `CengCi_Label_End_mm.xlsx`

Main stages:

1. Normalize GNS into RH-like tabular schema.
2. Convert OSM POI shapefiles to Excel and merge all POI tables.
3. Build geohash-based neighborhood candidates.
4. Filter by type/class compatibility.
5. Match names with edit distance and Soundex.
6. Export pair results (`PiPei.xlsx`) and merged/fused result (`RH.xlsx`), then optionally convert back to shapefile.

Clearly exposed thresholds in code:

- `geohash.encode(..., precision=7)`
- In `RH_GNS_OSM.Is_Same_Name(...)`: `LevenshteinDis / NameLength <= 0.35`

Output:

- Primarily Excel outputs today: `GNS_to_RH.xlsx`, `OSM.xlsx`, `PiPei.xlsx`, `RH.xlsx`
- Optional shapefile conversion exists, but the current pipeline is still table-first rather than geometry-first

Notable risks:

- The pipeline is multi-script and Excel-heavy, so reproducibility and runtime contract are weaker than for shapefile-based building/road.
- Matching quality depends on label file completeness and multilingual naming quality.
- There is no current adapter or agent-safe transactional boundary for intermediate files.

Agent parameterization assessment:

- `none`
- The algorithm family is valuable, but it first needs to be wrapped into a stable adapter with explicit file contracts.

## Real Data Inventory

The following datasets are already in the repo workspace and are immediately useful for implementation and evaluation.

| Dataset | Path | Geometry | Approx. feature count | Role |
| --- | --- | --- | ---: | --- |
| Gitega OSM buildings | `Data/buildings/OSM/吉特加建筑物.shp` | Polygon | 87,957 | Building source A |
| Gitega Google buildings | `Data/buildings/Google/Google吉特加clip.shp` | Polygon | 279,967 | Building source B |
| Burundi Microsoft buildings | `Data/buildings/Microsoft/微软建筑物面矢量.shp` | Polygon | 2,013,383 | Building source B, national-scale |
| Gitega roads | `Data/roads/OSM/clip_road2.shp` | LineString / MultiLineString | 3,863 | Road source A |
| Burundi OSM roads | `Data/burundi-260127-free.shp/gis_osm_roads_free_1.shp` | Line | 167,758 | Road baseline coverage |
| Burundi HydroRIVERS-like lines | `Data/water/BDI.shp` | Line | 1,244 | Water-line source B |
| Burundi OSM waterways | `Data/burundi-260127-free.shp/gis_osm_waterways_free_1.shp` | Line | 18,644 | Water-line source A |
| Burundi lakes | `Data/water/布隆迪湖泊.shp` | Polygon / MultiPolygon | 16 | Water-polygon source B |
| Burundi OSM water polygons | `Data/burundi-260127-free.shp/gis_osm_water_a_free_1.shp` | Polygon | 1,147 | Water-polygon source A |
| Burundi GNS POI | `Data/POI/布隆迪/GNS.shp` | Point | 13,887 | POI source A |
| Burundi RH POI | `Data/POI/布隆迪/RH.shp` | Point | 24,913 | POI merged/fused output or prior baseline |
| Burundi OSM POI | `Data/burundi-260127-free.shp/gis_osm_pois_free_1.shp` | Point | 2,284 | POI source B |

Useful POI intermediate tables already exist:

- `Data/POI/布隆迪/GNS.xlsx`
- `Data/POI/布隆迪/GNS_to_RH.xlsx`
- `Data/POI/布隆迪/OSM.xlsx`
- `Data/POI/布隆迪/PiPei.xlsx`
- `Data/POI/布隆迪/RH.xlsx`
- `Data/POI/CengCi_Label_End_mm.xlsx`

## Recommended Real-Data Evaluation Matrix

### Tier A: Run First

These scenarios are the best next-step candidates because they either already fit the agent architecture or are one adapter away from it.

| Scenario ID | Job type | Source pair | Goal | Readiness |
| --- | --- | --- | --- | --- |
| `A1_building_gitega_google` | building | OSM Gitega + Google Gitega clip | End-to-end agent accuracy/stability baseline | Ready now |
| `A2_building_gitega_msft_clip` | building | OSM Gitega + Microsoft buildings after clipping | Stress test large-source preprocessing and parameter sensitivity | Ready after clipping helper |
| `A3_water_line_burundi` | water_line | OSM waterways + `BDI.shp` | Validate first non-building/road adapter | Ready after adapter/KG hookup |
| `A4_water_polygon_burundi` | water_polygon | OSM water polygons + lakes | Validate second non-building/road adapter | Ready after adapter/KG hookup |
| `A5_poi_burundi` | poi | `GNS_to_RH.xlsx` + `OSM.xlsx` + label taxonomy | Validate Excel-first pipeline wrapping | Ready after adapter/pipeline wrapper |

### Tier B: Use for Robustness, Not Main Accuracy Claim

| Scenario ID | Job type | Why not primary yet |
| --- | --- | --- |
| `B1_road_gitega_local` | road | A clear second authoritative road source is not visible in the current `Data/roads/` subtree, so this is currently better for runtime/splitting/repair testing than for a strong fusion-quality claim |
| `B2_building_burundi_national_msft` | building | National Microsoft layer is large enough to test memory and stability, but it should not be the first eval because failures may be dominated by engineering scale issues |

## What The Agent Can Honestly Claim Right Now

After the current implementation round:

- It can claim a complete `Model + Instructions + Tools + State + Loop + Policy` core for the connected building/road path.
- It can claim a first usable `Harness`, but mostly for golden/smoke and engineering reliability, not yet for real-data scientific evaluation.
- It cannot honestly claim that runtime parameter optimization is already effective, because parameters are modeled and transmitted, but not yet applied inside the building/road adapters.
- It cannot honestly claim support for water or POI in the main agent path yet.

## Immediate Engineering Priorities

### Priority 1. Make Existing Parameters Actually Effective

Apply `task.input.parameters` in:

- `adapters/building_adapter.py`
- `adapters/road_adapter.py`

Minimum expected binding:

- building:
  - `match_similarity_threshold`
  - `one_to_one_min_area_similarity`
  - `one_to_one_min_shape_similarity`
  - `one_to_one_min_overlap_similarity`
- road:
  - `angle_threshold_deg`
  - `snap_tolerance_m`
  - `match_buffer_m`
  - `max_hausdorff_m`
  - `dedupe_buffer_m`

### Priority 2. Expand the Executable Core Beyond Building/Road

Add new executable-core entries for:

- `water_line`
- `water_polygon`
- `poi`

That means all of the following, not just legacy scripts:

- adapter
- algorithm handler registration
- KG `AlgorithmNode`
- KG `DataTypeNode`
- workflow pattern
- parameter specs where thresholds exist
- at least one real-data eval case

### Priority 3. Promote Real Data Into Harness Inputs

The existing `scripts/eval_harness.py` is good enough to evaluate multiple cases, but the current case set is still golden-case oriented.

Next harness extension should support:

- external case manifests pointing to local `Data/` paths,
- optional preprocessing steps such as clipping or shapefile zipping,
- and per-case metric recording beyond pass/fail.

## Required User Inputs Before The Next Implementation Round

The repo is already sufficient to start, but three confirmations will remove ambiguity:

1. Building benchmark preference:
   choose whether `Google吉特加clip` or clipped Microsoft buildings should be the primary reference set for the first accuracy claim.
2. Road reference source:
   if you have a non-OSM authoritative road layer outside the current workspace, provide it; otherwise road should stay a secondary engineering scenario.
3. POI output contract:
   confirm whether the wrapped POI agent output should be treated as:
   - Excel-first (`RH.xlsx` as canonical), or
   - shapefile-first via `excel_to_shapefile(...)`.

## Recommended Next Execution Order

1. Make building/road parameter binding real.
2. Wrap `water_polygon` first.
   Reason: the algorithm is simpler, the threshold surface is small, and the output contract is cleaner than `water_line`.
3. Wrap `water_line`.
4. Wrap POI pipeline.
5. Add real-data case manifests to the harness.

This order maximizes confidence per unit of engineering effort and keeps the paper narrative coherent:

- first prove explicit policy and parameter binding matter,
- then show search-space expansion across new algorithm families,
- then show the harness can evaluate real data rather than only synthetic goldens.
