# FusionAgent

[English README](./README.en.md)

简历/演示项目说明见 [FusionAgent Resume Project Brief](./docs/demo/fusionagent-resume-project-brief.md)。

FusionAgent 是一个面向有界灾害响应工作流的成熟矢量数据融合智能体运行时，并在当前代码基线上提供面向 operator 的 Web 工作台基础面。当前代码已经不再只是算法脚本包装层，而是一个可测试、可审计、可渐进扩展的 KG-grounded、contract-bounded agentic runtime。

当前运行时已稳定支持 `building`、`road`、`water`，并新增了有界的 `poi` 自动融合垂直切片；四者共享同一条 task-driven runtime backbone，并具备 planning、validation、execution、healing、replanning、evidence writeback 与 artifact 输出能力。

## 当前定位

对项目现状最准确的表述是：

- 工程 MVP：已达到
- 研究原型：已达到
- 无界面的成熟矢量数据融合智能体：已达到
- 最终可视化产品形态：尚未达到

FusionAgent 当前已经达到工程 MVP、研究原型与无界面的成熟矢量数据融合智能体门槛，但不应被表述为最终可视化产品，也不应被表述为无边界通用智能体。

FusionAgent 当前可以作为成熟矢量数据融合智能体运行：它具备自然语言与本地场景触发入口、KG 约束规划、任务驱动数据获取、执行/修复/重规划/学习证据、场景级证据冻结、operator read API、本地运维 runbook，以及面向 operator 的 v2 Web 工作台基础面。最终产品化可视化界面仍是后续工作。

下一工程增量聚焦于可运营性与证据加固，而不是改写产品定位：注册工具契约（registered tool contracts）、KG grounding reports、unsupported-intent rejection、token/latency telemetry、checkpoint recovery inspection、ablation evidence。

## Web 工作台

当前仓库已经提供一个面向 operator 的前端工作台基础面：

- 首页总览、run 创建、run 列表、run 详情、run 对比
- 场景报告浏览、GeoJSON 地图预览、KG 总览、运行路径图
- LLM 设置读写与连通性校验
- 默认语言为简体中文，可在侧边栏切换 `English`，语言选择会写入浏览器 `localStorage`

这个前端的目标是补齐控制面与 operator 工作流，不宣称已经达到最终产品化 UI。

## Stability Contract

当前对外口径冻结为：

- `building: task_driven_auto supported`
- `road: task_driven_auto supported`
- `water: task_driven_auto supported after Phase 1`
- `poi: bounded task_driven_auto supported after Phase 3`
- 四者共享同一套 evidence contract：`run.json`、`plan.json`、`validation.json`、`audit.jsonl` 与 artifact bundle

## Benin Building Runtime Preparation

当前针对贝宁建筑物大数据量准备态的口径如下：

| Capability | Status |
| --- | --- |
| 当前 `OSM + single-ref` building runtime 的分块并行执行 | supported |
| Benin canonical source profiling | supported |
| OpenBuildingMap / local Microsoft / Google Open Buildings 的 KG 暴露 | supported in KG, not executable |
| Google building-presence raster 检查与画像 | inspect-only |
| 基于栅格的建筑物高度提取 | reserved |
| 真正的 4 源建筑物融合语义 | reserved |

Benin 准备态命令：

```powershell
python scripts/profile_benin_sources.py --source-root E:\fyx\data\Benin --output runs\benin-source-profile.json
python scripts/benchmark_tiled_building.py --source-root E:\fyx\data\Benin --bbox 2.48,9.23,2.77,9.44 --target-crs EPSG:32631 --output-root runs\benin-benchmark
```

当前 Benin 相关的清洗、剖析与研究脚本应被视为有界研究工件或准备能力，不能单独上升为“已稳定支持的主运行时能力”口径。

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
- `v2` 运行时稳定支持 `building`、`road`、`water` 与 bounded `poi`
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

### Phase 4.8：Trajectory-To-Road Seam Reservation

- KG 已预留 `dt.trajectory.raw -> dt.road.candidate -> dt.road.bundle` 的 transform seam，用于后续 trajectory pretransform 研究
- planner retrieval 现可暴露 `task.trajectory_to_road` 与 `algo.transform.trajectory_to_road_candidate` 等 metadata
- 当前实现刻意保持为 reservation only：默认 road runtime 仍以 `dt.road.bundle` 为执行输入，不自动启用 trajectory ingestion 或 road candidate inference

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

### Phase F：Water Vertical Slice

- `water` polygon fusion 垂直切片已接入 shared runtime backbone
- planner、KG seed、executor dispatch、adapter 输出、artifact writeback 与 Neo4j bootstrap 已形成闭环
- `water` 在 Phase 1 稳定化后已支持 `task_driven_auto`，并共享相同 evidence contract
- 跟踪文档见 [2026-04-20-water-vertical-slice.md](./docs/superpowers/plans/2026-04-20-water-vertical-slice.md)

### Phase F.1：POI Vertical Slice

- `poi` 自动融合垂直切片已接入 shared runtime backbone
- 当前范围刻意保持有界：`raw.osm.poi + raw.gns.poi -> catalog.generic.poi -> algo.fusion.poi.v1`
- planner、KG seed、executor dispatch、task-driven input acquisition、adapter 输出与 Neo4j bootstrap 已形成首个可测试闭环
- 该切片当前主打 deterministic、bounded、可回归，不宣称已覆盖复杂实体对齐或多源 POI 归一化

### Phase G：Experiment Matrix + Paper Evidence Freeze

- `scripts/eval_harness.py` 的 manifest 结果现在会保留 matrix-ready metadata 和 evidence 字段
- 新增 `scripts/freeze_paper_evidence.py`，可把 harness summary JSON 与历史 single-case durable result JSON 统一冻结为 paper-facing JSON/Markdown
- 追踪产物包括：
  - [paper experiment matrix](./docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json)
  - [paper evidence freeze JSON](./docs/superpowers/specs/2026-04-21-paper-evidence-freeze.json)
  - [paper evidence freeze Markdown](./docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md)

### Phase H：Scenario Evidence And Reporting

- 新增 `POST /api/v2/scenario-runs`，可用一个场景请求驱动多个 `task_driven_auto` 子 run，例如 building + road 灾害响应场景
- 场景输出 root 支持请求级 `output_root`、环境变量 `GEOFUSION_SCENARIO_OUTPUT_ROOT`，默认回退到 `E:\fyx\data\fusionagentTEST`
- 场景 evidence 会额外写入 `scenario_summary.json`、`kg_path_trace.json`、`workflow_trace.json`、`source_coverage.json`、`evaluation.json`
- 场景报告同时生成中文与英文 Markdown：`documents/scenario_report.zh.md`、`documents/scenario_report.en.md`
- 场景层显式呈现 KG 关系链、实际执行 workflow trace、source coverage / fallback、数据融合指标、智能体指标和 self-evolution evidence

## 每次运行产出的核心证据

每次 run 当前会持久化以下核心证据文件：

- `run.json`
- `plan.json`
- `validation.json`
- `audit.jsonl`
- artifact bundle

场景级 run 会在上述单 run 证据之外额外持久化：

- `scenario_summary.json`
- `kg_path_trace.json`
- `workflow_trace.json`
- `source_coverage.json`
- `evaluation.json`
- `documents/scenario_report.zh.md`
- `documents/scenario_report.en.md`

## 当前仍然存在的明确缺口

即使已经达到 no-ui maturity，FusionAgent 仍然存在这些明确的产品与研究边界：

- 最终产品级前端与最终可视化产品形态尚未完成；当前已有 operator Web 工作台基础面，但仍以运行态查看、证据浏览和设置管理为主
- 外部 provider event feeds 尚未集成；当前场景触发与运行入口不应被表述为已打通外部事件生态
- 当前不宣称 production deployment、线上认证授权、租户隔离或完整生产运维完备性
- 当前不宣称生产级 7x24 运行、不宣称可处理任意 off-domain 请求，也不宣称 UI 已最终完成
- search space 仍然集中在当前 `building`、`road`、`water` 与 bounded `poi` 范围
- `water` 与 bounded `poi` 已进入 shared task-driven backbone，但不应被表述为已证明“任意新任务族都能零成本扩展”
- trajectory-to-road 当前仅完成 seam reservation，不应被表述为已支持真实轨迹摄取、地图匹配、live trajectory-to-road ingestion 或 road candidate 推断
- durable learning 仍是 first-pass 能力，不是完整 policy auto-tuning
- `raw.google.building` 与部分本地 reference / Excel 类输入仍需要人工准备，不在当前官方自动物化集合内
- AOI 解析当前仍依赖外部 geocoder，可用性与速率受网络条件影响

## 后续控制面文档

当前 v2 roadmap 已经完成其既定范围。下一阶段不应直接无约束扩功能，而应先按 Phase A 控制面推进：

- [Final Gap Matrix](./docs/superpowers/specs/2026-04-20-final-gap-matrix.md)：最终目标缺口、优先级、风险与 gate
- [Evidence Ledger](./docs/superpowers/specs/2026-04-20-evidence-ledger.md)：现有测试、benchmark、运行文档与论文证据索引
- [Long-Chain Decision Roadmap](./docs/superpowers/specs/2026-04-20-long-chain-decision-roadmap.md)：从 Phase A 到 Phase H 的最长合理推进链条与每阶段决策门
- [Evaluation Contract And Thesis Claim Lock](./docs/superpowers/specs/2026-04-20-evaluation-contract-claim-lock.md)：论文/产品 claim、指标、baseline 与 Phase C-D gate
- [Phase G Experiment Matrix](./docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json)：冻结后的 claim/baseline/case contract
- [Phase G Paper Evidence Freeze](./docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md)：paper-facing summary、failure analysis 与 qualitative evidence

## 仓库结构

- `api/`: FastAPI 路由与应用入口
- `services/`: 运行时服务，包括 `AgentRunService`
- `agent/`: planner、retriever、validator、executor 与 policy 逻辑
- `kg/`: KG 模型、repository、seed data 与 bootstrap
- `adapters/`: building / road / water / poi fusion adapter
- `worker/`: Celery worker 与调度入口
- `llm/`: LLM provider 抽象与实现
- `scripts/`: harness、paper evidence freeze、bootstrap、本地启动与 inspection 脚本
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

### 前端工作台

适合本地 UI 开发与联调。

Terminal A:

```powershell
$env:GEOFUSION_KG_BACKEND='memory'
$env:GEOFUSION_LLM_PROVIDER='mock'
$env:GEOFUSION_CELERY_EAGER='1'
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Terminal B:

```powershell
Set-Location frontend
npm install
npm run dev
```

约定：

- Vite 默认入口：`http://127.0.0.1:5173/`
- 前端默认显示简体中文，可在侧边栏切换 `English`
- Vite 开发服务器通过 `/api` 代理到 `http://127.0.0.1:8000`
- FastAPI 默认允许 `http://127.0.0.1:5173` 与 `http://localhost:5173` 的跨域访问；如需自定义，可设置 `GEOFUSION_CORS_ORIGINS`

如需由 FastAPI 同源托管构建产物：

```powershell
Set-Location frontend
npm run build
Set-Location ..
uvicorn main:app --host 127.0.0.1 --port 8000
```

构建完成后访问 `http://127.0.0.1:8000/`；非 `/api/*` 路由会自动回退到 `frontend/dist/index.html`，用于支持 SPA 子路由直达。

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

如需聚焦 system-next 改进链路，优先运行：

```powershell
python -m pytest -q tests/test_tool_registry.py tests/test_plan_grounding_service.py tests/test_unsupported_intent_guard.py tests/test_run_telemetry_service.py tests/test_run_recovery_service.py tests/test_eval_kg_ablation.py
```

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
- 默认使用上传 bundle；设置 `input_strategy=task_driven_auto` 后，`building`、`road`、`water` 与 bounded `poi` 都会走共享输入准备链路

### Create Scenario Run

- `POST /api/v2/scenario-runs`
- 用于场景级编排与报告生成，不替代单 run API
- 输出目录遵循 `output_root -> GEOFUSION_SCENARIO_OUTPUT_ROOT -> E:\fyx\data\fusionagentTEST`

### Inspect Run

- `GET /api/v2/runs/{run_id}`
- `GET /api/v2/runs/{run_id}/plan`
- `GET /api/v2/runs/{run_id}/audit`
- `GET /api/v2/runs/{run_id}/artifact`
- `GET /api/v2/runs/{run_id}/inspection`

### Compare Runs

- `GET /api/v2/runs/{left_run_id}/compare/{right_run_id}`
