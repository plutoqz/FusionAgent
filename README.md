# FusionAgent

FusionAgent 是一个面向灾害应急场景的多源矢量数据融合服务，当前聚焦 `zip shapefile` 输入、`building` / `road` 两类任务，并通过 API 方式输出运行状态、计划和融合产物。

仓库内部仍沿用 `GeoFusion` 命名和 `GEOFUSION_*` 环境变量。这是当前工程实现的一部分，不影响使用。

## 当前系统定位

当前代码库已经不是单纯的算法脚本集合，而是一个“领域受限的 agentic workflow 原型”：

- 已有 `v1` 直接融合链路，复用 [Algorithm](/E:/vscode/fusionAgent/Algorithm) 中的既有算法。
- 已有 `v2` 规划、验证、执行、有限修复、状态持久化和 artifact 下载闭环。
- 已接入 KG、LLM provider、Celery、Neo4j bootstrap、本地启动脚本和测试集。
- 已有修复策略：`alternative_source`、`alternative_algorithm`、`transform_insert`。
- 当前还没有真正的 `replan` 闭环，也没有完整前端产品形态。

一句话概括：现在它已经具备初步应用价值，但仍属于本机可用 MVP，而不是最终完整形态。

## 当前已实现的 MVP 子集

- 输入：`zip shapefile`，要求至少包含 `.shp/.shx/.dbf`
- 任务：`building`、`road`
- 交付：FastAPI API + ZIP 结果产物
- KG 落地子集：
  - `WorkflowPattern`
  - `StepTemplate`
  - `Algorithm`
  - `DataSource`
  - `DataType`
  - `WorkflowInstance`
- 本机验收方式：
  - `python -m pytest -q`
  - `python scripts/start_local.py --check-only`
  - `python scripts/smoke_local_v2.py`

## 完整目标形态

文档中的完整研究目标仍然保留，包括更丰富的灾害类型、更多任务类型、更强的重规划能力、更完整的 KG 写回与执行审计，以及最终服务器部署形态。
当前工程并未全部落地这些能力，请不要把目标态文档等同于当前实现状态。

## 目录结构

- `api/`：FastAPI 应用与路由
- `services/`：`v1` / `v2` 运行服务
- `agent/`：planner、validator、executor、retriever
- `kg/`：知识图谱 seed、bootstrap、Neo4j / memory repository
- `llm/`：Mock 与 OpenAI-compatible provider
- `worker/`：Celery app、阶段任务、定时调度
- `adapters/`：建筑物 / 道路融合算法适配层
- `scripts/`：本地启动、Neo4j 检查、smoke、测试数据脚本
- `tests/`：单测、集成测试、golden cases
- `docs/`：运行与运维说明
- `文档/`：研究上下文与目标态设计文档

## 运行方式

### 1. 本地快速模式

适合调接口、跑测试、验证主流程，不依赖真实 Neo4j / Redis / 在线模型。

```bash
python -m pip install -r requirements.txt
set GEOFUSION_KG_BACKEND=memory
set GEOFUSION_LLM_PROVIDER=mock
set GEOFUSION_CELERY_EAGER=1
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 2. 本地全链路模式

适合联调 Neo4j、Redis、Celery 和真实 LLM provider。

1. 复制并填写本地私有配置：

```bash
copy 依赖.txt.example 依赖.txt
```

2. 做本地依赖与 Neo4j 检查：

```bash
python scripts/start_local.py --check-only
```

3. 如需重置 FusionAgent 自己管理的 Neo4j 子图再重建：

```bash
python scripts/start_local.py --check-only --reset-managed-graph
```

4. 启动 API / worker / scheduler：

```bash
python scripts/start_local.py
```

5. 跑本地 smoke：

```bash
python scripts/smoke_local_v2.py
```

### 3. Neo4j 检查命令

当前本机 Neo4j 若为 Community Edition，FusionAgent 会自动探测当前 home database，并通过 `:FusionAgentManaged` 标签命名空间隔离自己的子图，而不是依赖多数据库。

只读检查当前图状态：

```bash
python scripts/inspect_neo4j_state.py
python scripts/inspect_neo4j_state.py --managed-only
```

### 4. Docker Compose

```bash
copy .env.example .env
docker compose up --build
```

## API 使用

### `v1`

- `POST /api/v1/fusion/building/jobs`
- `POST /api/v1/fusion/road/jobs`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/jobs/{job_id}/artifact`

### `v2`

`/api/v2/runs` 的真实接口为 `multipart/form-data` 上传，不是 JSON 直接提交。

- `POST /api/v2/runs`
- `GET /api/v2/runs/{run_id}`
- `GET /api/v2/runs/{run_id}/plan`
- `GET /api/v2/runs/{run_id}/artifact`

示例：

```bash
curl -X POST "http://127.0.0.1:8000/api/v2/runs" ^
  -F "osm_zip=@tests/golden_cases/building_disaster_flood/input/osm.zip" ^
  -F "ref_zip=@tests/golden_cases/building_disaster_flood/input/ref.zip" ^
  -F "job_type=building" ^
  -F "trigger_type=disaster_event" ^
  -F "trigger_content=flood building fusion" ^
  -F "disaster_type=flood" ^
  -F "field_mapping={}" ^
  -F "target_crs=EPSG:32643"
```

## 测试

运行全量测试：

```bash
python -m pytest -q
```

运行 live smoke 前，需要显式开启真实模型：

```bash
set GEOFUSION_LIVE_SMOKE=1
set GEOFUSION_LLM_PROVIDER=openai
set GEOFUSION_LLM_BASE_URL=https://www.dmxapi.cn/v1
set GEOFUSION_LLM_MODEL=qwen3.5-397b-a17b
set GEOFUSION_LLM_API_KEY=your-key
python -m pytest tests/test_live_smoke_v2.py -q
```

## 前端说明

当前阶段不启动完整前端工程，优先保障本机可用 MVP、接口稳定性和 KG / 文档一致性。
如需展示，优先使用：

- FastAPI `/docs`
- `runs/<run_id>/run.json`、`plan.json`、artifact
- 轻量只读页面或脚本输出

## 相关文档

- [docs/local-direct-run.md](/E:/vscode/fusionAgent/docs/local-direct-run.md)
- [docs/v2-operations.md](/E:/vscode/fusionAgent/docs/v2-operations.md)
- [系统部署与运行文档.md](/E:/vscode/fusionAgent/系统部署与运行文档.md)
- [完整项目上下文文档.md](/E:/vscode/fusionAgent/文档/完整项目上下文文档.md)
- [GeoFusion 知识图谱本体模式层设计方案.md](/E:/vscode/fusionAgent/文档/GeoFusion%20知识图谱本体模式层设计方案.md)

## 发布注意事项

- `依赖.txt` 仅用于本地私有配置，不应提交到仓库。
- `文档/Proposal.pdf` 已从版本库移除，不再作为仓库内容维护。
- `.env`、运行日志、`runs/`、`jobs/` 产物只应保留在本地。
- 仓库文本文件统一使用 UTF-8 保存，避免中文乱码。
