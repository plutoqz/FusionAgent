# FusionAgent

[English README](./README.en.md)

FusionAgent 是一个面向灾害响应工作流的矢量数据融合智能体原型。当前 `main` 分支已经不再只是算法脚本包装层，而是一个可测试、可审计、可渐进扩展的 agentic runtime。

当前运行时已支持 `building` 与 `road` 两类任务，输入既可以是上传的 `zip shapefile`，也可以是 `task-driven` 自动准备的输入包；运行时已具备 planning、validation、execution、healing、replanning、evidence writeback 与 artifact 输出能力。

## 当前定位

对项目现状最准确的表述是：

- 工程 MVP：已达到
- 研究型迭代原型：已达到
- 最终产品形态：尚未达到

FusionAgent 已经具备可信的运行闭环，但仍不是拥有完整操作界面、成熟长期学习机制的最终产品。

## 论文对齐说明

FusionAgent 当前明确区分：

- 可执行核心本体：`Algorithm - Task - Data`
- 场景约束层：disaster event、`ScenarioProfile`、data need、output requirement、QoS policy

运行时同时支持 `scenario-driven` 和 `task-driven` 两种入口。直接任务请求可以跳过灾害推断，按默认 task 路由执行。

当前智能体模式更准确的描述是：
`Constrained Plan-and-Execute with Reactive Healing`

即 LLM 在 KG 检索候选与运行时约束内部做受限推理，而 validator、policy、audit 与 healing 回路负责约束正确性与鲁棒性。

## 已实现能力

### 核心运行时

- `planner -> validator -> executor -> healing/replan -> writeback`
- 持久化 `run.json`、`plan.json`、`validation.json` 与 `audit.jsonl`
- 持久化 artifact bundle 输出
- 显式 run status、decision records 与 audit trail
- `v2` 运行时支持 `building` 和 `road`
- `task-driven` / `scenario-driven` 双入口意图路由
- 通过 `TaskBundle` 与 `ScenarioProfile` 共享规划上下文

### Phase 1：评测与证据加固

- `scripts/eval_harness.py` 同时支持 golden-case 与 manifest 模式
- harness summary 包含 commit SHA、base URL、timeout、mode 与 environment
- manifest 评测支持 per-case timeout override
- manifest 模式包含 API 与输入 preflight 检查
- real-data manifest 保留了基于 tracked 输入的 `building_gitega_micro_agent` micro case，用于延续历史对齐证据
- real-data manifest 新增 `building_gitega_micro_msft_agent` micro case，可通过 `inputs.osm_source_id` 与 `inputs.reference_source_id` 从官方 Geofabrik / Microsoft 资产自动物化 fresh-checkout 输入
- `scripts/materialize_source_assets.py` 可将上述有界 source id 预取到 `runs/source-assets/` 缓存目录
- 文档已区分快速信心检查与真实证据运行

### Phase 2：搜索空间扩展

- `building` 与 `road` 的灾害场景 workflow pattern 覆盖更广
- 算法元数据更丰富：`accuracy_score`、`stability_score`、`usage_mode`
- 数据源元数据更丰富：freshness、quality、supported-type signals
- 参数规格覆盖增强，支持 `tunable` 与 `optimization_tags`
- 输出 schema policy 元数据已通过 KG 与 planner retrieval 暴露

### Phase 3：策略覆盖扩展

- 已显式建模的决策类型包括：
  - `pattern_selection`
  - `data_source_selection`
  - `artifact_reuse_selection`
  - `parameter_strategy`
  - `output_schema_policy`
  - `replan_or_fail`
- 候选证据形状统一为 `metrics + meta`
- decision trace 会同时落入 `run.json` 与 audit-backed status updates

### Phase 4：Artifact Reuse V2

- 已有 artifact registry，支持运行时 direct reuse 与 clip reuse
- 兼容性检查包含：
  - `output_data_type`
  - `target_crs`
  - job-type freshness policy
- 当前 freshness policy：
  - `building = 3d`
  - `road = 1d`
- clip reuse 包含 CRS、required fields 与 bbox safety 质量门禁
- reuse 不安全或 materialization 失败时会显式回退到 fresh execution

### Phase 4.5：Task-Driven 输入准备

- `POST /api/v2/runs` 支持 `input_strategy=task_driven_auto`
- planner 选出可用数据源后，运行时会解析出具体 `osm.zip` 与 `ref.zip`
- 自然语言区域请求现在可先解析 AOI，再把 `resolved_aoi` 注入 planner context 与运行时输入准备链路
- `task-driven` 请求会在执行前展开为 source resolution、具体输入准备、version-token checks 与 bbox clip reuse
- 输入准备层可通过 version-token checks 与 bbox clip reuse 复用缓存 input bundle
- 已解析输入会作为 `task_inputs_resolved` 写入 audit evidence
- `aoi_resolved` 与 AOI 感知的 `task_inputs_resolved` 都会写入 audit evidence
- benchmark / eval 路径新增了有界 `SourceAssetService`，可对 `raw.osm.building / road / water / poi` 与 `raw.microsoft.building` 走本地 `Data/` 优先、官方下载缓存兜底的物化链路
- `RawVectorSourceService` 已接入上述 source-asset fallback，task-driven runtime 在本地 `Data/` 不完整时可回退到官方缓存下载链路

### Phase 4.6：Source Catalog Expansion

- `task-driven` retrieval 已明确区分 bundle-level source 与 raw-vector source
- building bundle source 已显式记录组件对：`OSM + Google`、`OSM + Microsoft`
- road bundle source 已包含显式 `catalog.flood.road` 路径，并覆盖 earthquake / typhoon road bundles
- raw-vector catalog 当前覆盖 OSM `building / road / water / POI`、Microsoft buildings、Google buildings、本地 water sample 与 `Data/` 下已有 open POI references
- planner retrieval 已暴露这些 source 的 `component_source_ids`、`bundle_strategy`、`provider_family` 与 local path hints

### Phase 4.7：Raw Source Download Chain

- `task-driven` 运行时已能从 raw-vector source spec 物化 bundle 输入，而不再只依赖最终 bundle shapefile
- raw-vector acquisition 支持 directory-first、exact-path 与 recursive-glob locator
- raw source 会在 bundle 组装前通过共享 artifact registry 做 version-aware reuse
- cached raw source 与 cached input bundle 都支持 bbox clip reuse
- clip reuse 会先把 request-space bbox mask 转到缓存数据集 CRS 再裁剪，保证 projected cache 的空间正确性
- `LocalBundleCatalogProvider` 已能通过 `component_source_ids` 组装 `osm.zip` 与 `ref.zip`
- 单源 road bundle 会按需生成空 reference bundle
- runtime 侧现在也能在 local catalog 缺失时回退到 `SourceAssetService`，把官方 Geofabrik / Microsoft 数据下载、裁剪后接入 bundle 组装
- `scripts/smoke_agentic_region.py` 提供了自然语言区域请求的标准本机冒烟入口，推荐用 Nairobi, Kenya 做验证

### Phase 5：长期写回与学习闭环

- 每次 run 都会写入紧凑版 `DurableLearningRecord`
- durable record 会保留 planning mode、profile source 与 task bundle 等规划元数据
- durable record 与冗长 audit log 分离存储
- repository 已能按下列维度聚合 outcome evidence：
  - pattern
  - algorithm
  - data source
- planner retrieval 已暴露 durable learning summary

### Phase 6：产品化与运维

- 提供 operator inspection endpoint：
  - `GET /api/v2/runs/{run_id}/inspection`
- 提供 run comparison endpoint：
  - `GET /api/v2/runs/{left_run_id}/compare/{right_run_id}`
- 已有整理后的 [docs/v2-operations.md](./docs/v2-operations.md) 说明运行约定与 operator 流程

## 每次运行产出的核心证据

每次 run 当前会持久化以下核心证据文件：

- `run.json`
- `plan.json`
- `validation.json`
- `audit.jsonl`
- artifact bundle

## 当前仍然存在的明确缺口

虽然六个 roadmap phase 已经都进入实现范围，但仍然存在这些现实缺口：

- benchmark evidence 还没有上升为更耐久的研究笔记或跟踪文档
- search space 仍然集中在当前 `building` 与 `road` 主题
- durable learning 仍是 first-pass 能力，不是完整 policy auto-tuning
- operator-facing productization 目前仍是窄 API 层，不是完整前端产品
- `raw.google.building` 与部分本地 reference / Excel 类输入仍需要人工准备，不在当前官方自动物化集合内
- AOI 解析当前仍依赖外部 geocoder，可用性与速率受网络条件影响

## 后续控制面文档

当前 v2 roadmap 已经完成其既定范围。下一阶段不应直接无约束扩功能，而应先按 Phase A 控制面推进：

- [Final Gap Matrix](./docs/superpowers/specs/2026-04-20-final-gap-matrix.md)：最终目标缺口、优先级、风险与 gate
- [Evidence Ledger](./docs/superpowers/specs/2026-04-20-evidence-ledger.md)：现有测试、benchmark、运行文档与论文证据索引
- [Long-Chain Decision Roadmap](./docs/superpowers/specs/2026-04-20-long-chain-decision-roadmap.md)：从 Phase A 到 Phase H 的最长合理推进链条与每阶段决策门

## 仓库结构

- `api/`: FastAPI 路由与应用入口
- `services/`: 运行时服务，包括 `AgentRunService`
- `agent/`: planner、retriever、validator、executor 与 policy 逻辑
- `kg/`: KG 模型、repository、seed data 与 bootstrap
- `adapters/`: building / road fusion adapter
- `worker/`: Celery worker 与调度入口
- `llm/`: LLM provider 抽象与实现
- `scripts/`: harness、bootstrap、本地启动与 inspection 脚本
- `tests/`: unit、integration、runtime、API 与 repository tests
- `docs/`: 运维与设计文档

## 本地运行

### 快速本地模式

适合单元测试、API 契约检查与本地调试。

```powershell
python -m pip install -r requirements.txt
$env:GEOFUSION_KG_BACKEND='memory'
$env:GEOFUSION_LLM_PROVIDER='mock'
$env:GEOFUSION_CELERY_EAGER='1'
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 本地全链路模式

适合联调 Neo4j、Redis、Celery 与 live LLM。

```powershell
python scripts/start_local.py --check-only
python scripts/start_local.py --port 8000
python scripts/smoke_agentic_region.py --base-url http://127.0.0.1:8000 --query "fuse building and road data for Nairobi, Kenya" --timeout 1200
```

本地运行约定：

- 日常开发、本机冒烟、手工联调默认使用 `8000`
- 推荐的标准全链路启动方式是 `python scripts/start_local.py --port 8000`
- 本机直跑入口会优先读取仓库根目录 `依赖.txt`；Redis broker / backend 端口以其中的 `Redis端口` 为准，仓库样例当前使用 `6380`
- 只有未提供 `依赖.txt` 时，Celery 才回退到代码中的通用默认值 `redis://localhost:6379/0`
- Neo4j 默认约定为 `bolt://localhost:7687`
- `8011` 预留给隔离的 fast-confidence 检查
- `8010` 预留给隔离的 real-data benchmark
- `8012+` 只建议用于临时排障，不作为常驻默认端口

如需在 setup check 时重置 managed graph：

```powershell
python scripts/start_local.py --check-only --reset-managed-graph
```

### Docker Compose

```powershell
Copy-Item .env.example .env
docker compose up --build
```

说明：

- `docker compose` 路径使用容器内的 `redis://redis:6379/0` 与 API `8000`
- 它不依赖本机 `依赖.txt` 中的 Redis 端口约定

## 评测分层

### Tier 1：Targeted Tests

用于日常回归检查。

### Tier 2：Golden-Case Harness

用于 API 到 runtime 的闭环检查。

### Tier 3：Real-Data Benchmark

用于沉淀可复用的研究级证据。

当前 timeout 建议：

- harness 默认值：`180s`
- real-data building benchmark 不应使用 `180s` 判定
- 当前 real-data building run 建议至少使用 `1200s`
- `building_gitega_micro_agent` 当前仍用于 tracked 输入路径的历史对齐验证
- `building_gitega_micro_msft_agent` 当前已经可以在干净 checkout 上通过官方 source-id 物化输入，并且在隔离的 `8010` full-loop runtime 上验证通过；跟踪证据见 `docs/superpowers/specs/2026-04-16-building-micro-msft-fresh-checkout-result.json`
- 如需预热 fresh-checkout 缓存，可先运行 `python scripts/materialize_source_assets.py --source raw.osm.building --source raw.microsoft.building --bbox 29.817351,-3.646572,29.931113,-3.412421 --prefer-remote`
- `scripts/eval_harness.py` 现在会优先读取 `/api/v2/runtime` 返回的非敏感运行时元数据，因此 summary 中的 `environment` 更接近真实运行时，而不是仅依赖当前 shell 环境变量

## 常用验证命令

运行全量测试：

```powershell
python -m pytest -q
```

常用 runtime-focused 子集：

```powershell
$env:GEOFUSION_KG_BACKEND='memory'
$env:GEOFUSION_LLM_PROVIDER='mock'
$env:GEOFUSION_CELERY_EAGER='1'
python -m pytest -q `
  tests/test_planner_context.py `
  tests/test_agent_run_service_enhancements.py `
  tests/test_input_acquisition_service.py `
  tests/test_source_asset_service.py `
  tests/test_raw_vector_source_service.py `
  tests/test_local_bundle_catalog.py `
  tests/test_eval_harness.py `
  tests/test_policy_engine.py `
  tests/test_artifact_registry.py `
  tests/test_parameter_binding.py `
  tests/test_planner_artifact_reuse.py `
  tests/test_agent_state_models.py `
  tests/test_kg_parameter_specs.py `
  tests/test_neo4j_bootstrap.py `
  tests/test_neo4j_repository.py `
  tests/test_api_v2_integration.py
```

## v2 API

### Create Run

- `POST /api/v2/runs`
- 默认使用上传 bundle；设置 `input_strategy=task_driven_auto` 后，运行时会自动准备输入

### Inspect Run

- `GET /api/v2/runs/{run_id}`
- `GET /api/v2/runs/{run_id}/plan`
- `GET /api/v2/runs/{run_id}/audit`
- `GET /api/v2/runs/{run_id}/artifact`
- `GET /api/v2/runs/{run_id}/inspection`

### Compare Runs

- `GET /api/v2/runs/{left_run_id}/compare/{right_run_id}`
