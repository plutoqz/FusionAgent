# KG Gates Evidence Summary (2026-05-10, refreshed 2026-05-12)

## Scope

本页汇总 `Task 1 + Task 2` 落地后的默认 `Neo4j` backend 证据，用于回答两个问题：

1. 当前 KG contract 是否已经进入默认运行态
2. `building / road / water / poi` 的 task-driven 主链是否已经具备真实 smoke 证据

## Runtime Contract

- Local startup command: `python scripts/start_local.py --port 8000`
- Observed result: `KG contract: PASS`
- Runtime mode:
  - `Neo4j edition: community`
  - `Neo4j isolation: managed-label`
  - `Neo4j database: zmn`
  - `Neo4j namespace guard: fusionagent`

## Building

### Paper baseline

- Manifest case: `building_gitega_micro_msft_agent`
- Report:
  - [2026-05-12-building-gitega-micro-msft-neo4j-baseline-8012.json](/E:/vscode/fusionAgent/docs/superpowers/specs/2026-05-12-building-gitega-micro-msft-neo4j-baseline-8012.json)
- Result:
  - `passed = 1`
  - `run_id = 07ebbedd856b43a09ad3bf62ee55a440`

### Task-driven smoke

- Natural-language query with explicit disambiguation:
  - `need building data for Gitega city, Burundi`
- Inspection:
  - [smoke-building-gitega-city-inspection-8012.json](/E:/vscode/fusionAgent/runs/smoke-building-gitega-city-inspection-8012.json)
- Result:
  - `run_id = b4ffaa523fed45629600cfd935989c38`
  - `source_id = catalog.earthquake.building`
  - `phase = succeeded`

### AOI ambiguity regression fix

- Raw query:
  - `need building data for Gitega, Burundi`
- Inspection:
  - [smoke-building-gitega-raw-inspection.json](/E:/vscode/fusionAgent/runs/smoke-building-gitega-raw-inspection.json)
- Result:
  - `run_id = be933f08aa694d6c9eb4c73ed100aa52`
  - `source_id = catalog.earthquake.building`
  - `phase = succeeded`

## Road

- Query:
  - `need road data for Gilgit city, Pakistan`
- Inspection:
  - [smoke-road-gilgit-city-inspection-8012.json](/E:/vscode/fusionAgent/runs/smoke-road-gilgit-city-inspection-8012.json)
- Result:
  - `run_id = de2ee0d67d854b7bb5da2c28b44a1e0f`
  - `phase = succeeded`

## Water

- Query:
  - `need water polygons for Nairobi, Kenya`
- Inspection:
  - [smoke-water-nairobi-inspection-8012.json](/E:/vscode/fusionAgent/runs/smoke-water-nairobi-inspection-8012.json)
- Result:
  - `run_id = ccd5e86f91724fa1a331e9b306202276`
  - `source_id = catalog.flood.water`
  - `phase = succeeded`

## POI

- Query:
  - `show hospitals in Nairobi, Kenya`
- Inspection:
  - [smoke-poi-nairobi-inspection-8012.json](/E:/vscode/fusionAgent/runs/smoke-poi-nairobi-inspection-8012.json)
- Result:
  - `run_id = c4d1c293ddd5407e993b845991cf67c5`
  - `source_id = catalog.generic.poi`
  - `phase = succeeded`

## Key Fixes Behind These Gates

1. `bootstrap completeness` and `KG contract check` are wired into local startup.
2. `ScenarioProfile`, `ParameterSpec`, and `OutputSchemaPolicy` are active in planner, validator, and post-execution artifact checks.
3. `Neo4jKGRepository` keeps decomposed workflow and parameter-spec retrieval reachable under the default backend.
4. `graphNamespace` is now configurable from local runtime config and enforced in Neo4j read/write paths as a second guard.
5. Building tile clipping no longer writes boundary-collapsed `LINESTRING` geometries into polygon shapefiles.
6. `catalog.flood.water` and `catalog.generic.poi` now allow partial coverage when the primary OSM-side component is present and the reference-side component is empty.
7. AOI resolution now prefers the more specific nested `city` candidate over a broader same-name administrative candidate, which closes the `Gitega, Burundi` ambiguity case.

## Current Conclusion

截至 `2026-05-12`，默认 `Neo4j` backend 下的以下 gate 已经具备 fresh 运行证据：

- `KG contract pass`
- `graphNamespace` guard active
- `building` baseline pass
- `building / road / water / poi` task-driven smoke pass

这意味着继续推进后续更新与论文消融实验已经具备可用基线，不再停留在“图谱代码定义存在但默认 live runtime 漂移”的状态。

## FusionCode Selection Follow-up (2026-05-15)

在不改变默认 bounded runtime claim 的前提下，task-driven smoke 现在支持受控 `preferred_pattern_id` 入口，用于验证某个已注册 KG workflow pattern 是否真的会被 planner/executor 选中并留下审计证据。fresh 结果如下：

- Road
  - inspection: [smoke-road-gilgit-city-fusioncode-inspection-8012.json](/E:/vscode/fusionAgent/runs/smoke-road-gilgit-city-fusioncode-inspection-8012.json)
  - `run_id = d7b3d61a48644fc18edf1064c272bb7d`
  - `selected_pattern_id = wp.road.fusioncode.segment_topology.v1`
  - `algorithm_id = algo.fusion.road.segment_match_topology.v1`
- Water
  - inspection: [smoke-water-nairobi-fusioncode-inspection-8012.json](/E:/vscode/fusionAgent/runs/smoke-water-nairobi-fusioncode-inspection-8012.json)
  - `run_id = 471ae06f16404713af1b0f23ac9ffad3`
  - `selected_pattern_id = wp.water.fusioncode.line_and_polygon.v1`
  - `algorithm_id = algo.fusion.water.polygon_priority_merge.v1`
- POI
  - inspection: [smoke-poi-nairobi-fusioncode-inspection-8012.json](/E:/vscode/fusionAgent/runs/smoke-poi-nairobi-fusioncode-inspection-8012.json)
  - `run_id = 0ed6dfa8baf249ecb87082df08f5f89d`
  - `selected_pattern_id = wp.poi.fusioncode.geohash_priority.v1`
  - `algorithm_id = algo.fusion.poi.geohash_neighbor_match.v1`

结论：road / water / bounded poi 的 FusionCode KG 节点已经具备“live 可选中、可执行、可审计”的额外验证证据，不再只是 retrieval candidate 可见。
