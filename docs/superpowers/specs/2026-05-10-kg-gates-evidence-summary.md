# KG Gates Evidence Summary (2026-05-10)

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

## Building

### Paper baseline

- Manifest case: `building_gitega_micro_msft_agent`
- Report:
  - [2026-05-09-building-gitega-micro-msft-neo4j-baseline.json](/E:/vscode/fusionAgent/docs/superpowers/specs/2026-05-09-building-gitega-micro-msft-neo4j-baseline.json)
- Result:
  - `passed = 1`
  - `run_id = d6308d853c2d4481bbbfac3fd2b020af`

### Task-driven smoke

- Natural-language query with explicit disambiguation:
  - `need building data for Gitega city, Burundi`
- Inspection:
  - [smoke-building-gitega-inspection.json](/E:/vscode/fusionAgent/runs/smoke-building-gitega-inspection.json)
- Result:
  - `run_id = 86d224bb483b4078b8526c4be24373c2`
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
  - [smoke-road-gilgit-city-inspection.json](/E:/vscode/fusionAgent/runs/smoke-road-gilgit-city-inspection.json)
- Result:
  - `run_id = 9e782dc0f1244f0f8077a10ce4ee3d1a`
  - `phase = succeeded`

## Water

- Query:
  - `need water polygons for Nairobi, Kenya`
- Inspection:
  - [smoke-water-nairobi-inspection.json](/E:/vscode/fusionAgent/runs/smoke-water-nairobi-inspection.json)
- Result:
  - `run_id = 64899f5f4024418087f5e6c5142aa02c`
  - `source_id = catalog.flood.water`
  - `phase = succeeded`

## POI

- Query:
  - `show hospitals in Nairobi, Kenya`
- Inspection:
  - [smoke-poi-nairobi-inspection.json](/E:/vscode/fusionAgent/runs/smoke-poi-nairobi-inspection.json)
- Result:
  - `run_id = 3b6b6ee61d98441aa33ce512b06d30b0`
  - `source_id = catalog.generic.poi`
  - `phase = succeeded`

## Key Fixes Behind These Gates

1. `bootstrap completeness` and `KG contract check` are wired into local startup.
2. Building tile clipping no longer writes boundary-collapsed `LINESTRING` geometries into polygon shapefiles.
3. `catalog.flood.water` and `catalog.generic.poi` now allow partial coverage when the primary OSM-side component is present and the reference-side component is empty.
4. AOI resolution now prefers the more specific nested `city` candidate over a broader same-name administrative candidate, which closes the `Gitega, Burundi` ambiguity case.

## Current Conclusion

截至 `2026-05-10`，默认 `Neo4j` backend 下的以下 gate 已经具备真实运行证据：

- `KG contract pass`
- `building` baseline pass
- `building / road / water / poi` task-driven smoke pass

这意味着继续推进后续更新与论文消融实验已经具备可用基线，不再停留在“图谱代码定义存在但默认 live runtime 漂移”的状态。
