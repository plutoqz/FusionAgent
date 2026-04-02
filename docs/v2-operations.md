# GeoFusion v2 Operations

## 1. 运行模式

### 本地快速模式

- `GEOFUSION_KG_BACKEND=memory`
- `GEOFUSION_LLM_PROVIDER=mock`
- `GEOFUSION_CELERY_EAGER=1`

适合：

- 单测
- 调接口
- 排查 planner / validator / executor 逻辑

### 接近生产的本地编排

- `GEOFUSION_KG_BACKEND=neo4j`
- `GEOFUSION_LLM_PROVIDER=openai`
- `GEOFUSION_CELERY_EAGER=0`
- 配套启动 `redis + neo4j + worker + scheduler`

适合：

- Celery 编排联调
- live 模型规划验证
- scheduled producer 验证

## 2. Neo4j 初始化

### 生成 bootstrap

```bash
python -m kg.bootstrap
```

输出文件：

- [neo4j_bootstrap.cypher](/E:/vscode/fusionAgent/kg/bootstrap/neo4j_bootstrap.cypher)

### 执行方式

1. 启动 Neo4j。
2. 打开 Neo4j Browser 或 `cypher-shell`。
3. 执行 bootstrap 文件内容。

脚本会创建：

- 约束：`WorkflowPattern`、`Algorithm`、`DataSource`、`DataType`、`StepTemplate`、`WorkflowInstance`
- 全文索引：`wp_search`、`algo_search`、`ds_search`
- building / road 所需的最小 pattern、algorithm、datatype、datasource、transform 图

## 3. Celery / Redis

### worker

```bash
celery -A worker.celery_app.celery_app worker -l info
```

### beat

```bash
celery -A worker.celery_app.celery_app beat -l info
```

### 当前阶段级 task

- `geofusion.plan_run`
- `geofusion.validate_run`
- `geofusion.execute_plan`
- `geofusion.writeback_run`
- `geofusion.execute_run`
- `geofusion.scheduled_tick`

## 4. Live LLM 联调

推荐环境变量：

```bash
set GEOFUSION_LLM_PROVIDER=openai
set GEOFUSION_LLM_BASE_URL=http://fast.jnm.lol/v1
set GEOFUSION_LLM_MODEL=gpt-5.4-mini
set GEOFUSION_LLM_API_KEY=your-key
```

受保护 smoke：

```bash
set GEOFUSION_LIVE_SMOKE=1
python -m pytest tests/test_live_smoke_v2.py -q
```

说明：

- 默认不触发真实网关
- 只验证 live planner 能为 `building` 与 `road` 生成合法 `WorkflowPlan`
- 不会把密钥写入仓库或日志

## 5. Scheduled Runs

`scheduled_tick` 会读取 `GEOFUSION_SCHEDULED_RUNS`，把每一项转成 `RunCreateRequest` 后走统一主链路。

示例：

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

## 6. 故障排查

### `worker` 导入失败

优先检查：

- `celery` 是否安装
- `redis` 地址是否正确

当前仓库已加入本地 fallback；即便未安装 `celery`，单测和本地调试仍可导入 `worker`。

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

检查：

- 输入 ZIP 是否包含 `.shp/.shx/.dbf`
- `output/` 下是否已有 `.shp` bundle
- `repair_records` 是否已经耗尽修复策略

## 7. 数据清理

可按 run 目录清理：

- `runs/<run_id>/input`
- `runs/<run_id>/intermediate`
- `runs/<run_id>/output`
- `runs/<run_id>/logs`

不要把真实 API key 写入：

- 仓库文件
- 测试夹具
- commit 信息
- 运行日志
