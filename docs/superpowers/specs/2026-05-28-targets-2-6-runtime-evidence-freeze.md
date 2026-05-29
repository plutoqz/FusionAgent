# Targets 2-6 Runtime Evidence Freeze

## Capability State

- Target 2: supported in shared runtime for building vectors plus optional height raster enrichment.
- Target 3: supported in shared runtime for OSM road plus Overture transportation.
- Target 4: supported in shared runtime for water polygons and waterways lines.
- Target 5: supported in shared runtime for bounded OSM POI plus GNS/GeoNames gazetteer fusion.
- Target 6: supported through shared tile, stitch, clip, and evidence outputs.

## Required Evidence

- `tile_manifest.json`
- `selected_sources.json`
- `stitched_artifact.json`
- `fusion_stats.json`
- `source_semantic_contract.json`
- `documents/run_report_summary.json`
- `documents/run_report.zh.md`
- `documents/run_report.en.md`

## Boundaries

- Google/OpenBuildingMap building sources remain manual-preload supplements.
- `raw.rh.poi` remains a manual-preload supplement.
- Unbounded POI entity alignment remains unsupported.
- Target 5 POI support is AOI-bounded OSM + GNS/GeoNames vector fusion; unbounded POI entity alignment, name disambiguation across unrelated regions, and global gazetteer deduplication remain unsupported.
- Trajectory-to-road remains reservation-only and is outside targets 2-6.
- Live source materialization is provider-dependent and is not required for fixture-level closure.

## Verification

This Windows host has a broken bare `python` entrypoint for this repo: `python -c "import sys; print(sys.executable)"` resolves to `C:\Program Files\QGIS 3.40.11\bin\python.exe` and fails during Python startup because the `encodings` module cannot be loaded. All verified commands therefore use `py -3.13`, which resolves to `C:\Users\QDX\AppData\Local\Programs\Python\Python313\python.exe`.

- `py -3.13 -m pytest -q tests/test_smoke_agentic_region.py::test_smoke_summary_accepts_large_area_evidence_fields`
  - Result: `1 passed in 0.56s`
- `py -3.13 -m pytest -q tests/test_smoke_agentic_region.py::test_smoke_summary_accepts_large_area_evidence_fields tests/test_smoke_agentic_region.py::test_smoke_inspection_summary_carries_large_area_evidence_fields tests/test_smoke_agentic_region.py::test_smoke_agentic_region_main_writes_track_b_evidence_bundle tests/test_smoke_agentic_region.py::test_smoke_agentic_region_marks_poi_smoke_as_bounded_supported`
  - Result: `4 passed in 0.59s`
- `py -3.13 -m pytest -q tests/test_smoke_agentic_region.py`
  - Result: `13 passed in 1.26s`
- `py -3.13 -m pytest -q tests/test_large_area_runtime_service.py tests/test_agent_run_service_large_area_runtime.py tests/test_agent_run_service_multisource_building_runtime.py tests/test_tiled_multisource_building_runtime_service.py tests/test_source_semantic_contract_service.py tests/test_source_asset_service.py tests/test_road_conflation_v7.py tests/test_waterways_conflation_v7.py tests/test_fusioncode_poi.py tests/test_run_report_service.py tests/test_track_b_national_scale_service.py tests/test_track_b_national_v7_routes.py`
  - Result: `71 passed, 12 warnings in 52.03s`
- `$env:GEOFUSION_KG_BACKEND='memory'; $env:GEOFUSION_LLM_PROVIDER='mock'; $env:GEOFUSION_CELERY_EAGER='1'; py -3.13 -m pytest -q tests/test_agent_run_service_large_area_runtime.py`
  - Result: `6 passed in 3.28s`
- `py -3.13 -m pytest -q tests/test_agent_run_service_enhancements.py`
  - Result: `36 passed in 4.00s`
- `py -3.13 -m pytest -q tests/test_agent_run_service_large_area_runtime.py tests/test_agent_run_service_enhancements.py tests/test_check_kg_contract.py tests/test_kg_seed_inventory.py tests/test_fusioncode_parity_ledger.py tests/test_track_b_source_matrix.py tests/test_source_coverage_fallback.py`
  - Result: `57 passed in 6.45s`
- `py -3.13 -m pytest -q tests/test_neo4j_bootstrap.py::test_expected_seed_inventory_matches_static_bootstrap_contract tests/test_source_coverage_fallback.py tests/test_local_bundle_catalog.py`
  - Result: `13 passed in 2.12s`
- `py -3.13 -m pytest -q tests/test_ontology_closure.py tests/test_local_bundle_catalog.py tests/test_large_area_runtime_service.py tests/test_agent_run_service_large_area_runtime.py tests/test_agent_run_service_multisource_building_runtime.py tests/test_tiled_multisource_building_runtime_service.py tests/test_source_semantic_contract_service.py tests/test_source_asset_service.py tests/test_road_conflation_v7.py tests/test_waterways_conflation_v7.py tests/test_poi_adapter.py tests/test_fusioncode_poi.py tests/test_run_report_service.py tests/test_track_b_national_scale_service.py tests/test_track_b_national_v7_routes.py tests/test_run_preflight.py`
  - Result: `93 passed, 12 warnings in 56.90s`
- `py -3.13 -m pytest -q`
  - Result after archiving this plan: `1 failed, 704 passed, 1 skipped, 12 warnings in 145.83s`
  - First failure: `tests/test_plan_handshake.py::test_completed_master_plan_is_archived_with_no_active_plan_left`
  - Note: after this plan was moved to `docs/superpowers/plans/done/`, the only active plan left is the unrelated unfinished `2026-05-26-fusionagent-capability-gap-prioritized-plan.md`. The target 2-6 runtime gates above passed.
Optional live-source smoke was skipped because it uses `--prefer-remote` against provider-dependent OSM, Microsoft, Overture, HydroLAKES, HydroRIVERS, and GNS downloads. Provider availability should not block the no-network fixture closure.
