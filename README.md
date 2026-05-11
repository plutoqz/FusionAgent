# FusionAgent

[English README](./README.en.md)

简历/演示项目说明见 [FusionAgent Resume Project Brief](./docs/demo/fusionagent-resume-project-brief.md)。

FusionAgent 是一个面向有界灾害响应场景的地理空间矢量数据融合智能体运行时。当前仓库同时包含后端运行时、知识图谱约束层、任务与场景编排、证据写回链路，以及面向 operator 的 Web 工作台。

项目的目标不是提供一个无边界的通用 Agent，而是在明确任务边界内，把“任务理解、数据获取、规划约束、执行融合、失败修复、证据留存”组织成可测试、可审计、可复现实验的工程系统。

## 项目内容

当前代码基线主要覆盖以下能力：

- 支持 `building`、`road`、`water` 以及有界 `poi` 四类融合任务
- 支持两类入口：
  - 上传 `osm.zip` / `ref.zip` 的显式输入模式
  - `task_driven_auto` 的任务驱动自动输入准备模式
- 支持单次 run 和 scenario run 两种执行形态
- 支持运行产物、审计日志、场景报告、预览 GeoJSON 等证据输出
- 提供运行查看、对比、知识图谱概览、LLM 设置等 operator 能力

## 适用范围

FusionAgent 适用于以下类型的问题：

- 有明确任务类型和输出目标的灾害响应矢量融合
- 需要保留规划、验证、执行与证据链条的研究原型或工程 MVP
- 需要在本地环境中复现实验、回归运行和场景报告的项目

当前仓库不以这些目标为范围：

- 通用开放域 Agent
- 最终产品级可视化平台
- 完整生产级多租户部署与 7x24 运维体系
- 无边界的数据源自动接入与任意任务族扩展

## 技术路线与方法

### 运行时方法

核心运行链采用受约束的 `Plan-and-Execute with Reactive Healing` 模式：

1. `planner` 根据任务、场景、知识图谱和 source catalog 生成候选方案
2. `validator` 对计划、参数、输入约束和能力边界做校验
3. `executor` 调度具体融合算法与数据准备过程
4. `healing / replan` 在失败或约束不满足时执行有限修复或重规划
5. `writeback` 持久化运行状态、计划、审计日志、artifact 和场景证据

### 知识与数据方法

- 使用知识图谱表达任务、算法、数据源、输出约束与场景关系
- 使用 source catalog、artifact registry 和 AOI 解析支持任务驱动输入准备
- 使用统一 evidence contract 固化 run 级与 scenario 级证据
- 使用 operator read model、报告文档和 GeoJSON 预览支撑检查与复核

### 证据契约

单次 run 默认写出以下核心产物：

- `run.json`
- `plan.json`
- `validation.json`
- `audit.jsonl`
- artifact bundle

scenario run 会在此基础上额外写出：

- `scenario_summary.json`
- `kg_path_trace.json`
- `workflow_trace.json`
- `source_coverage.json`
- `evaluation.json`
- `documents/scenario_report.zh.md`
- `documents/scenario_report.en.md`

## 系统架构

### 后端运行时

- `FastAPI` 提供 `v1` / `v2` API
- `Celery + Redis` 负责 worker 与 scheduler 执行
- `Neo4j` 或内存后端承担知识图谱存储
- `Pydantic` 承载请求、响应与运行时 schema

### GIS 与融合计算

- `GeoPandas`
- `Shapely`
- `Fiona`
- `PyProj`
- `Rasterio`
- `NetworkX`
- `SciPy`
- `NumPy`
- `Pandas`

### 前端工作台

- `React 18`
- `Vite`
- `TypeScript`
- `React Router`
- `TanStack Query`
- `MapLibre GL`
- `Cytoscape`

## 仓库结构

```text
fusionAgent/
├─ agent/                 # planner / executor / retriever 等运行时核心
├─ api/                   # FastAPI 应用与路由
├─ frontend/              # React + Vite operator 工作台
├─ kg/                    # 知识图谱构建、查询与 bootstrap
├─ services/              # 运行编排、场景服务、设置服务、预览服务
├─ schemas/               # Pydantic schema 与响应模型
├─ scripts/               # 本地启动、冒烟、评测、证据冻结等脚本
├─ tests/                 # 单元测试、集成测试、golden cases
├─ docs/                  # 运行文档、计划、规格与说明
├─ worker/                # Celery app 与后台任务
├─ Data/                  # 本地原始数据与参考数据目录
└─ runs/                  # 本地运行产物与日志输出目录
```

## 环境准备

建议准备以下环境：

- Python 3.9 - 3.11
- Node.js 与 npm（前端开发需要）
- Redis
- Neo4j 5.x
- PowerShell 7 或其他可用 Shell

安装 Python 依赖：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

安装前端依赖：

```powershell
Set-Location frontend
npm install
Set-Location ..
```

## 配置说明

仓库提供两类本地配置入口：

- [依赖.txt.example](./依赖.txt.example)：本机直跑时的私有依赖配置模板
- [.env.example](./.env.example)：环境变量示例

推荐先复制私有依赖模板：

```powershell
Copy-Item 依赖.txt.example 依赖.txt
```

`依赖.txt` 通常用于声明本机 Redis、Neo4j 和 LLM 连接信息；`scripts/start_local.py`、`main.py`、`worker/celery_app.py` 会优先读取这份配置。

## 本地部署方案

### 方案 A：快速模式

适用于接口联调、单元测试、前端开发和轻量冒烟。

```powershell
$env:GEOFUSION_KG_BACKEND='memory'
$env:GEOFUSION_LLM_PROVIDER='mock'
$env:GEOFUSION_CELERY_EAGER='1'
uvicorn main:app --host 127.0.0.1 --port 8000
```

前端开发模式：

```powershell
Set-Location frontend
npm run dev
```

默认前端开发地址为 `http://127.0.0.1:5173`，FastAPI 默认允许本地开发跨域访问。

### 方案 B：本地全链路模式

适用于 Redis、Neo4j、worker、scheduler 和真实 LLM 配置都需要参与的联调。

先做依赖检查和 Neo4j bootstrap：

```powershell
python scripts/start_local.py --check-only
```

通过检查后启动全链路：

```powershell
python scripts/start_local.py --port 8000
```

默认行为：

- API 启动在 `http://127.0.0.1:8000`
- 日志输出到 `runs/local-runtime/`
- 启动 API、worker、scheduler 三个进程
- 当知识图谱后端为 `neo4j` 时，自动完成本地 seed 检查与 bootstrap

### 方案 C：前后端同源部署

当 `frontend/dist/` 存在时，FastAPI 会自动托管构建后的前端静态资源。

```powershell
Set-Location frontend
npm run build
Set-Location ..
uvicorn main:app --host 127.0.0.1 --port 8000
```

### 方案 D：Docker Compose

仓库提供完整的容器化编排文件：

```powershell
docker compose up --build
```

默认会启动以下服务：

- `api`
- `worker`
- `scheduler`
- `redis`
- `neo4j`

默认端口：

- API: `8000`
- Redis: `6379`
- Neo4j HTTP: `7474`
- Neo4j Bolt: `7687`

容器部署默认使用 `redis://redis:6379/0` 与 `bolt://neo4j:7687`，与本机 `依赖.txt` 方案是两套独立约定。

## API 概览

### 运行与检查

- `GET /api/v2/runs`
- `POST /api/v2/runs`
- `GET /api/v2/runs/{run_id}`
- `GET /api/v2/runs/{run_id}/plan`
- `GET /api/v2/runs/{run_id}/audit`
- `GET /api/v2/runs/{run_id}/inspection`
- `GET /api/v2/runs/{run_id}/kg-graph`
- `GET /api/v2/runs/{run_id}/preview`
- `GET /api/v2/runs/{run_id}/preview.geojson`
- `GET /api/v2/runs/{run_id}/artifact`
- `GET /api/v2/runs/{left_run_id}/compare/{right_run_id}`

### 运行时与总览

- `GET /api/v2/runtime`
- `GET /api/v2/operator/summary`
- `GET /api/v2/kg/overview`

### 场景运行

- `GET /api/v2/scenario-runs`
- `POST /api/v2/scenario-runs`
- `GET /api/v2/scenario-runs/{scenario_id}`
- `GET /api/v2/scenario-runs/{scenario_id}/documents`
- `GET /api/v2/scenario-runs/{scenario_id}/documents/{filename}`

### LLM 设置

- `GET /api/v2/settings/llm`
- `PUT /api/v2/settings/llm`
- `POST /api/v2/settings/llm/validate`

## 本地验证与测试

后端测试：

```powershell
python -m pytest -q
```

前端测试：

```powershell
Set-Location frontend
npm test
Set-Location ..
```

本地 run 冒烟：

```powershell
python scripts/smoke_local_v2.py --base-url http://127.0.0.1:8000
```

任务驱动 AOI 冒烟：

```powershell
python scripts/smoke_agentic_region.py --base-url http://127.0.0.1:8000 --query "fuse building data for Nairobi, Kenya" --timeout 1200
```

## 当前边界

为了避免误读，这里明确列出当前实现边界：

- `poi` 仍是有界能力，不宣称已解决通用多源实体对齐
- trajectory-to-road 相关内容仅是预留接缝，不是现行可执行主链路
- 外部事件源生态、生产级认证授权、多租户治理和长期自治学习不在当前交付范围
- 前端工作台面向 operator 检查与操作，不等同于最终产品化 UI

## 参考文档

- [docs/v2-operations.md](./docs/v2-operations.md)
- [docs/local-direct-run.md](./docs/local-direct-run.md)
- [docs/no-ui-agent-operations.md](./docs/no-ui-agent-operations.md)
- [docs/demo/fusionagent-resume-project-brief.md](./docs/demo/fusionagent-resume-project-brief.md)
