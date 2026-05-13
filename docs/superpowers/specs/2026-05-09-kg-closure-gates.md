# KG Closure Gates

**Status:** Closed with fresh verification on 2026-05-12.

## Required Before New Ablation

- live managed inventory matches seed inventory
- default Neo4j backend smoke passes for `building / road / water / poi`
- `ScenarioProfile` and `OutputSchemaPolicy` are active runtime constraints
- `graphNamespace` isolation is configurable and enforced as an application-level guard
- local operator commands report contract state explicitly

## Fresh Verification Snapshot (2026-05-12)

### Static Gates

- `python scripts/start_local.py --check-only`
  - `KG contract: PASS`
  - `Neo4j edition: community`
  - `Neo4j isolation: managed-label`
  - `Neo4j database: zmn`
  - `Neo4j namespace guard: fusionagent`
- `python scripts/inspect_neo4j_state.py --managed-only`
  - `expected_seed_inventory` matches managed seed labels
  - `missing_seed_labels = {}`
- `python scripts/check_kg_contract.py`
  - `ok = true`

### Focused Regression

- `python -m pytest -q tests/test_smoke_agentic_region.py tests/test_local_runtime.py tests/test_check_kg_contract.py tests/test_kg_seed_inventory.py tests/test_neo4j_bootstrap.py tests/test_planner_context.py tests/test_workflow_validator.py tests/test_agent_run_service_enhancements.py tests/test_neo4j_repository.py`
  - `87 passed, 8 warnings`

### Bounded Default-Backend Smoke

- building
  - query: `need building data for Gitega city, Burundi`
  - inspection: [smoke-building-gitega-city-inspection-8012.json](/E:/vscode/fusionAgent/runs/smoke-building-gitega-city-inspection-8012.json)
  - `run_id = b4ffaa523fed45629600cfd935989c38`
  - `source_id = catalog.earthquake.building`
- road
  - query: `need road data for Gilgit city, Pakistan`
  - inspection: [smoke-road-gilgit-city-inspection-8012.json](/E:/vscode/fusionAgent/runs/smoke-road-gilgit-city-inspection-8012.json)
  - `run_id = de2ee0d67d854b7bb5da2c28b44a1e0f`
  - `source_id = catalog.typhoon.road`
- water
  - query: `need water polygons for Nairobi, Kenya`
  - inspection: [smoke-water-nairobi-inspection-8012.json](/E:/vscode/fusionAgent/runs/smoke-water-nairobi-inspection-8012.json)
  - `run_id = ccd5e86f91724fa1a331e9b306202276`
  - `source_id = catalog.flood.water`
- poi
  - query: `show hospitals in Nairobi, Kenya`
  - inspection: [smoke-poi-nairobi-inspection-8012.json](/E:/vscode/fusionAgent/runs/smoke-poi-nairobi-inspection-8012.json)
  - `run_id = c4d1c293ddd5407e993b845991cf67c5`
  - `source_id = catalog.generic.poi`

### Paper Baseline Reproduction

- manifest case: `building_gitega_micro_msft_agent`
- report: [2026-05-12-building-gitega-micro-msft-neo4j-baseline-8012.json](/E:/vscode/fusionAgent/docs/superpowers/specs/2026-05-12-building-gitega-micro-msft-neo4j-baseline-8012.json)
- result:
  - `all_passed = true`
  - `run_id = 07ebbedd856b43a09ad3bf62ee55a440`

## Operational Decision

Recommended local isolation order:

1. one Neo4j instance or port per project
2. keep `GEOFUSION_GRAPH_NAMESPACE=fusionagent` as the application-level guard
3. do not reuse a miscellaneous shared graph view for paper evidence runs
