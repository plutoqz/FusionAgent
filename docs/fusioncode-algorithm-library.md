# FusionCode Algorithm Library

This document records how `E:\vscode\fusioncode` is represented in FusionAgent without treating the external pipeline as one monolithic function.

## Inventory Mapping

Use the same vocabulary as the capability inventory:

- `status`: `core`, `core_next`, `optional`, `deferred`
- `claim_state`: `runtime_supported`, `bounded_supported`, `kg_only`, `inspect_only`, `reservation_only`, `research_utility`

| Capability | status | claim_state | Note |
| --- | --- | --- | --- |
| `algo.fusion.road.segment_match_topology.v1` | `core` | `runtime_supported` | aligned with the current road runtime slice |
| `algo.fusion.water.line_three_source_priority.v1` | `core` | `runtime_supported` | aligned with the current water runtime family |
| `algo.fusion.water.polygon_priority_merge.v1` | `core` | `runtime_supported` | aligned with the current water polygon slice |
| `algo.fusion.poi.geohash_neighbor_match.v1` | `core` | `bounded_supported` | bounded POI slice only |
| `wp.building.drs4br.decomposed.v1` | `deferred` | `reservation_only` | visible in KG but not part of the current stable runtime claim |
| `algo.fusion.building.multi_source.decomposed.v1` | `deferred` | `reservation_only` | do not describe as stable executable runtime support |
| `algo.validate.building.presence_raster.v1` | `deferred` | `reservation_only` | raster validation remains outside the stable runtime contract |
| `algo.enrich.building.height_from_raster.v1` | `deferred` | `reservation_only` | raster height extraction remains outside the stable runtime contract |

## Architecture

FusionAgent stores FusionCode capabilities as KG-backed algorithm primitives. The `fusion_algorithms/` package wraps or ports the algorithm phases, while `kg/seed.py` registers data types, algorithms, parameter specs, and workflow patterns. `algorithm_adapter.run_full_pipeline()` remains a behavior reference only; KG execution is routed through decomposed nodes.

## Building Workflow

Primary workflow: `wp.building.drs4br.decomposed.v1`

1. `algo.preprocess.building.source_normalize.v1`
2. `algo.enrich.building.obm_attributes.v1`
3. `algo.validate.building.presence_raster.v1`
4. `algo.match.building.v8_candidate_graph.v1`
5. `algo.match.building.v8_component_solver.v1`
6. `algo.fusion.building.cascade_geometry_priority.v1`
7. `algo.resolve.building.residual_priority.v1`
8. `algo.optimize.road.topology_for_buildings.v1`
9. `algo.optimize.building.conflict_graph.v1`
10. `algo.refine.building.post_conflict_shrink.v1`
11. `algo.refine.building.road_tail.v1`
12. `algo.enrich.building.height_from_raster.v1`
13. `algo.assess.building.quality_metrics.v1`

Compatibility composite: `algo.fusion.building.multi_source.decomposed.v1`.

## Other Themes

- Road: `algo.fusion.road.segment_match_topology.v1`
- Water line: `algo.fusion.water.line_three_source_priority.v1`
- Water polygon: `algo.fusion.water.polygon_priority_merge.v1`
- POI: `algo.fusion.poi.geohash_neighbor_match.v1`
- Conflicts: `algo.detect.spatial_conflicts.v1`

## Parameter Groups

KG parameter specs cover the main FusionCode controls:

- V8 matching: `weak_min_cover`, `weak_min_iou`, `thresh_1_to_1`, `thresh_1_to_N`, `thresh_M_to_N`, `source_priority_order`
- Presence raster: `prob_threshold`, `search_dist_m`, confirmed and uncertain score thresholds
- Height raster: `n_jobs`, `height_output_field`, `positive_only`
- Conflict optimization: `global_max_shift`, `overlap_delete_threshold`, `road_buffer_width`, `w_road_expulsion`, `max_outer_iterations`
- Road line fusion: `angle_threshold_deg`, `buffer_dist_m`, `max_hausdorff_m`
- Water polygon fusion: `overlap_threshold`
- POI fusion: `neighbor_rings`, `name_similarity_threshold`

## Runtime Notes

Full FusionCode execution requires the optional geospatial stack declared in `requirements.txt`: `networkx`, `joblib`, `rasterio`, and `python-geohash` in addition to GeoPandas/Shapely/SciPy. Unit tests avoid requiring those heavy modules by testing wrappers, KG metadata, and fallback paths separately.

## Benin National Building Runtime

`scripts/run_benin_multisource_building_fusion.py` remains a research utility for large Benin building experiments. It is not part of the current stable runtime contract.

If you need to inspect the current research utility path:

```powershell
python scripts/run_benin_multisource_building_fusion.py `
  --source-root E:\fyx\data\Benin `
  --output-root runs\benin-national-multisource `
  --target-crs EPSG:32631 `
  --tile-width-m 10000 `
  --tile-height-m 10000 `
  --overlap-m 96 `
  --max-workers 4
```

The script profiles the source root, selects `MS`, `OBM`, `GG`, and `OSM` building vectors, discovers available Google `building_presence` and `building_height` rasters, partitions the Benin bbox into buffered tiles, runs the decomposed multi-source FusionCode flow per tile, and stitches tile-owned features into `runtime_output/fused_buildings.gpkg`. Keep this as a research utility description unless the same capability is promoted through shared runtime evidence, tests, and operations wording.

Height fields are intentionally non-destructive:

- `height_ms`, `height_obm`, `height_google`, `height_osm`: source-specific vector heights when available.
- `height_raster`: Google height raster extraction when a height raster profile exists.
- `height_vector_fused`: maximum valid vector height seen for the fused feature.
- `height_final`: final height used by downstream consumers.
- `height_final_source`: provenance for `height_final`, normally `raster` when a positive raster height is available, otherwise the winning vector height field.

The local `building_presence_2023_benin_4m.tif` can validate building presence. The height raster is optional; if `building_height_2023_benin_4m.tif` is absent, vector heights are still preserved and `height_final` falls back to the best vector value.
