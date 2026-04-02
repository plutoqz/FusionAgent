# FusionAgent v2 运维说明

## 当前定位

`v2` 是当前仓库里的 agentic workflow 原型链路，不是最终完整智能体平台。
它已经有 KG 检索、LLM 规划、验证、执行、有限修复和反馈落盘，但还没有完整的重规划与前端产品层。

## 运行模式

### 本地快速模式

- `GEOFUSION_KG_BACKEND=memory`
- `GEOFUSION_LLM_PROVIDER=mock`
- `GEOFUSION_CELERY_EAGER=1`

适合：

- 单测
- API 联调
- planner / validator / executor 逻辑排查

### 本地全链路模式

- `GEOFUSION_KG_BACKEND=neo4j`
- `GEOFUSION_LLM_PROVIDER=openai`
- `GEOFUSION_CELERY_EAGER=0`

适合：

- Celery 联调
- live planner smoke
- scheduled runs 验证

## Neo4j 管理

### 1. 生成 bootstrap

```bash
python -m kg.bootstrap
```

输出文件：

- [kg/bootstrap/neo4j_bootstrap.cypher](/E:/vscode/fusionAgent/kg/bootstrap/neo4j_bootstrap.cypher)

### 2. 本地准备当前图

```bash
python -m kg.bootstrap --prepare-local --json
python -m kg.bootstrap --prepare-local --reset-managed --json
```

说明：

- Enterprise：优先使用 `GEOFUSION_NEO4J_DATABASE`
- Community：自动探测当前 home database，并通过 `:FusionAgentManaged` 标签隔离子图

### 3. 只读检查

```bash
python -m kg.bootstrap --inspect --json
python -m kg.bootstrap --inspect --managed-only --json
```

### 4. 当前受管 KG 子集

- `WorkflowPattern`
- `StepTemplate`
- `Algorithm`
- `DataSource`
- `DataType`
- `WorkflowInstance`

### 5. 当前尚未完整落地的目标类

以下仍属于目标态设计，不应视为当前工程全部实现：

- `ExecutionFeedback`
- `RepairRecord`
- `DataArtifact`
- 更完整的场景层与事件层本体
- 基于执行反馈的自动经验学习闭环

## Celery / Redis

### worker

```bash
celery -A worker.celery_app.celery_app worker -l info
```

### beat

```bash
celery -A worker.celery_app.celery_app beat -l info
```

### 当前任务

- `geofusion.plan_run`
- `geofusion.validate_run`
- `geofusion.execute_plan`
- `geofusion.writeback_run`
- `geofusion.execute_run`
- `geofusion.scheduled_tick`

## Live LLM 联调

```bash
set GEOFUSION_LLM_PROVIDER=openai
set GEOFUSION_LLM_BASE_URL=https://www.dmxapi.cn/v1
set GEOFUSION_LLM_MODEL=qwen3.5-397b-a17b
set GEOFUSION_LLM_API_KEY=your-key
set GEOFUSION_LIVE_SMOKE=1
python -m pytest tests/test_live_smoke_v2.py -q
```

说明：

- 默认不会触发真实模型
- 当前只验证 live planner 能否为 `building` / `road` 生成合法 `WorkflowPlan`
- 不应把真实密钥写进仓库或日志

## Scheduled Runs

`GEOFUSION_SCHEDULED_RUNS` 仍采用 JSON 数组配置，例如：

```json
[
  {
    "job_type": "road",
    "trigger_content": "hourly road refresh",
    "disaster_type": "earthquake",
    "osm_zip_path": "E:/data/road/osm.zip",
    "ref_zip_path": "E:/data/road/ref.zip",
    "target_crs": "EPSG:32643"
  }
]
```

## 故障排查

### `worker` 导入失败

优先检查：

- 是否安装 `celery`
- Redis 地址是否可达

### Neo4j 查询结果异常

先检查：

```bash
python scripts/inspect_neo4j_state.py
python scripts/inspect_neo4j_state.py --managed-only
```

如果看到了大量外部标签，不代表 FusionAgent 无法工作；重点看 `managed-only` 视图是否完整。

### run 卡在 `planning` / `validating`

检查：

- `runs/<run_id>/plan.json`
- `runs/<run_id>/validation.json`
- `runs/<run_id>/run.json`

重点字段：

- `phase`
- `plan_revision`
- `failure_summary`
- `healing_summary`

### artifact 未生成

优先检查：

- 输入 ZIP 是否包含 `.shp/.shx/.dbf`
- 输出目录是否生成 `.shp` bundle
- `repair_records` 是否已经耗尽当前修复策略
