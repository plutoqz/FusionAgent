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
- `py -3.13 -m pytest -q`
  - Result: stopped after the repository-wide run emitted an early failure marker and continued for several minutes without a final summary.
- `py -3.13 -m pytest -q --maxfail=1`
  - Result: `1 failed in 2.94s`
  - First failure: `tests/test_agent_run_service_enhancements.py::test_agent_run_service_allows_water_task_driven_auto_and_records_task_inputs_resolved`
  - Note: this legacy enhancement test stubs resolved water `.shp` paths with dummy text files. The current shared large-area runtime reads real vector files and fails with `pyogrio.errors.DataSourceError` before the old mocked executor path can succeed. The Task 8 target suite remains passing.

Optional live-source smoke was skipped because it uses `--prefer-remote` against provider-dependent OSM, Microsoft, Overture, HydroLAKES, HydroRIVERS, and GNS downloads. Provider availability should not block the no-network fixture closure.
