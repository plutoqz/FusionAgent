# FusionAgent

FusionAgent 是一个面向多源矢量 SHP 数据融合的服务化项目，当前代码库同时保留两条运行链路：

- `v1`：兼容既有 `building` / `road` 融合接口，直接调用现有融合算法适配层。
- `v2`：在 `v1` 之上引入 KG、LLM、校验、自修复和 Celery 编排，用于构建可追踪的智能体执行链路。

仓库内部仍沿用 `GeoFusion` 命名和 `GEOFUSION_*` 环境变量，这是当前实现的一部分，不影响使用。

## 当前状态

当前仓库已经具备可运行原型的基础能力，而不是只停留在设计阶段：

- FastAPI API 已提供 `v1` 和 `v2` 两套接口。
- `building` / `road` 两类任务都已经接入运行链路。
- KG、LLM Provider、Celery Worker、定时任务、Neo4j Bootstrap 已落地到代码。
- 本地测试已通过：`python -m pytest -q` 结果为 `43 passed, 1 skipped`。
- 本地冒烟已通过：`python scripts/smoke_local_v2.py` 能成功产出 ZIP 结果包。

## 目录结构

- `api/`：FastAPI 应用与路由。
- `services/`：`v1` / `v2` 运行服务。
- `agent/`：planner、validator、executor、retriever 等智能体核心逻辑。
- `kg/`：知识图谱仓储、种子数据与 Neo4j bootstrap。
- `llm/`：Mock 与 OpenAI 兼容 Provider。
- `worker/`：Celery app、阶段任务与定时调度入口。
- `adapters/`：现有建筑物 / 道路融合算法适配层。
- `utils/`：CRS、字段映射、ZIP 校验、本地运行时配置等通用能力。
- `scripts/`：本地启动、冒烟验证、测试数据生成脚本。
- `tests/`：单测、集成测试、golden case 与 smoke 测试。
- `docs/`：`v2` 运维说明与本地直跑说明。
- `Algorithm/`：已有融合算法实现。

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

启动后可调用：

- `POST /api/v1/fusion/building`
- `POST /api/v1/fusion/road`
- `POST /api/v2/runs`
- `GET /api/v2/runs/{run_id}`
- `GET /api/v2/runs/{run_id}/plan`
- `GET /api/v2/runs/{run_id}/artifact`

### 2. 本地全链路模式

适合联调 Neo4j、Redis、Celery、真实 LLM Provider。

1. 复制并填写本地私有配置：

```bash
copy 依赖.txt.example 依赖.txt
```

2. 先检查依赖与 Neo4j 种子状态：

```bash
python scripts/start_local.py --check-only
```

3. 如当前 Python 环境缺依赖，可自动安装：

```bash
python scripts/start_local.py --install-deps
```

4. 启动本地 API、worker、scheduler：

```bash
python scripts/start_local.py
```

5. 运行 `v2` 冒烟验证：

```bash
python scripts/smoke_local_v2.py
```

运行日志会输出到 `runs/local-runtime/`。

### 3. Docker Compose

```bash
copy .env.example .env
docker compose up --build
```

默认会启动：

- `api`
- `worker`
- `scheduler`
- `redis`
- `neo4j`

## 测试

### 全量本地测试

```bash
python -m pytest -q
```

### CI 当前关注的基础套件

```bash
python -m pytest \
  tests/test_kg_repository.py \
  tests/test_repair_strategy.py \
  tests/test_workflow_validator.py \
  tests/test_kg_repository_enhancements.py \
  tests/test_planner_context.py \
  tests/test_repair_audit.py \
  tests/test_agent_run_service_enhancements.py \
  tests/test_worker_orchestration.py \
  tests/test_neo4j_bootstrap.py \
  tests/test_openai_provider_defaults.py \
  -q
```

### Live Smoke

默认不会触发真实模型。只有在显式配置在线 Provider 后，才建议执行：

```bash
set GEOFUSION_LIVE_SMOKE=1
set GEOFUSION_LLM_PROVIDER=openai
set GEOFUSION_LLM_BASE_URL=https://www.dmxapi.cn/v1
set GEOFUSION_LLM_MODEL=qwen3.5-397b-a17b
set GEOFUSION_LLM_API_KEY=your-key
python -m pytest tests/test_live_smoke_v2.py -q
```

## 配置说明

### 核心变量

- `GEOFUSION_KG_BACKEND=memory|neo4j`
- `GEOFUSION_LLM_PROVIDER=mock|openai|auto`
- `GEOFUSION_CELERY_EAGER=1|0`
- `GEOFUSION_CELERY_BROKER`
- `GEOFUSION_CELERY_BACKEND`

### Neo4j

- `GEOFUSION_NEO4J_URI`
- `GEOFUSION_NEO4J_USER`
- `GEOFUSION_NEO4J_PASSWORD`
- `GEOFUSION_NEO4J_DATABASE`

### LLM

- `GEOFUSION_LLM_BASE_URL`
- `GEOFUSION_LLM_MODEL`
- `OPENAI_API_KEY` 或 `GEOFUSION_LLM_API_KEY`

### 定时运行

- `GEOFUSION_SCHEDULED_INTERVAL_SECONDS`
- `GEOFUSION_SCHEDULED_RUNS`

`GEOFUSION_SCHEDULED_RUNS` 需要是 JSON 数组，例如：

```json
[
  {
    "job_type": "building",
    "trigger_content": "nightly building refresh",
    "disaster_type": "flood",
    "osm_zip_path": "E:/data/building/osm.zip",
    "ref_zip_path": "E:/data/building/ref.zip",
    "target_crs": "EPSG:32643"
  }
]
```

## 相关文档

- [docs/v2-operations.md](docs/v2-operations.md)
- [docs/local-direct-run.md](docs/local-direct-run.md)
- [系统部署与运行文档.md](系统部署与运行文档.md)
- [文档/完整项目上下文文档.md](文档/完整项目上下文文档.md)

## 发布注意事项

- `依赖.txt` 仅用于本地私有配置，不应提交到仓库。
- `.env`、运行日志、`runs/` 和 `jobs/` 产物均应保持本地使用。
- 仓库文本文件统一使用 UTF-8 保存，以避免中文显示异常。
