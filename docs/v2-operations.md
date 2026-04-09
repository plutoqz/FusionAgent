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

## 评测分层与证据要求

当前建议把评测分成三层，避免把“快速回归”与“研究证据”混为一谈。

### Tier 1：单元测试与定向 runtime 回归

使用时机：

- 日常开发后的默认检查
- 修改局部逻辑后验证没有破坏已有契约
- 排查 planner / validator / executor / policy / artifact reuse 的局部回归

最低证据要求：

- 记录执行命令
- 记录通过或失败的 `pytest` 输出
- 如果失败，至少记录失败用例名和错误摘要

### Tier 2：golden-case harness

使用时机：

- 需要验证 API 到运行时的闭环是否仍然成立
- 需要确认 plan、audit、artifact 的结构化产出没有回归
- 需要比单测更接近真实运行，但又不想进入慢速真实 benchmark

最低证据要求：

- 保存 harness summary JSON 或等价摘要
- 保存失败 case 的 `case_id`、`run_id` 和错误信息
- 必要时补充 `runs/<run_id>/audit.jsonl`

### Tier 3：真实数据 benchmark

使用时机：

- 需要形成可复查的研究证据
- 需要比较真实数据上的运行时间、成功率或产物质量
- 需要确认 building / road 真实数据链路在当前 runtime 上的行为

最低证据要求：

- 保存 benchmark summary JSON
- 保存对应 `run_id`
- 能回溯到 `run.json`、`plan.json`、`audit.jsonl` 和 artifact bundle
- 记录使用的 `base_url`、timeout 和关键环境变量

## Timeout 指南

- `scripts/eval_harness.py` 当前默认 `--timeout` 是 `180` 秒。
- 这个默认值只适合快速 harness 检查，不适合作为真实 building benchmark 的失败阈值。
- 真实数据 building benchmark 当前不应期待在 `180` 秒内完成。
- 对真实数据 building benchmark，现阶段推荐显式使用至少 `1200` 秒的 timeout。
- 先看到 timeout，不要立即归因到算法失败，优先检查 timeout 窗口是否设置过短，以及 runtime 是否对齐。

## 推荐执行命令

把快路径回归和慢路径证据分开执行，不要让真实数据 benchmark 混进默认 PR 检查。

### 快速置信命令

在终端 A 启动 mock/in-memory/eager API：

```powershell
$env:GEOFUSION_KG_BACKEND='memory'
$env:GEOFUSION_LLM_PROVIDER='mock'
$env:GEOFUSION_CELERY_EAGER='1'
uvicorn main:app --host 127.0.0.1 --port 8011
```

在终端 B 运行定向 pytest + 窄子集 golden-case harness：

```powershell
$env:GEOFUSION_KG_BACKEND='memory'
$env:GEOFUSION_LLM_PROVIDER='mock'
$env:GEOFUSION_CELERY_EAGER='1'
python -m pytest -q `
  tests/test_eval_harness.py `
  tests/test_api_v2_integration.py `
  tests/test_agent_run_service_enhancements.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python scripts/eval_harness.py `
  --base-url http://127.0.0.1:8011 `
  --timeout 180 `
  --case building_disaster_flood `
  --case road_disaster_earthquake `
  --output-json tmp/eval/fast-confidence-summary.json
```

- 这条命令是默认本地回归入口，适合 PR 前自检和日常开发回归。
- 当前默认 CI 仍保持 pytest-only 快路径，不会自动触发这条 harness 命令或 Tier 3 manifest benchmark。

### 真实证据命令

先按 [local-direct-run.md](local-direct-run.md) 或当前 benchmark worktree 约定启动对齐后的 runtime，然后运行：

```powershell
python scripts/eval_harness.py `
  --manifest docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json `
  --case building_gitega_osm_vs_google_agent `
  --case building_gitega_osm_vs_msft_clipped_agent `
  --base-url http://127.0.0.1:8010 `
  --timeout 1200 `
  --output-json tmp/eval/real-evidence-summary.json
```

- 这条命令只用于保留真实运行证据，不应塞进默认 PR gating。
- 如果这次结果要作为正式 benchmark 结论，除了 summary JSON，还要把 `run_id` 和对应 `runs/<run_id>/` 证据路径一起记下来。

## Runtime Alignment Checklist

在跑 Tier 2 或 Tier 3 之前，先完成以下检查：

### 1. API 端口对齐

- 本次运行使用的 `base_url` 必须和实际 API 监听端口一致
- 不要沿用旧线程留下的端口假设
- 启动后可先用只读请求或健康检查确认 API 已响应

### 2. worker 新鲜度

- `worker.log` 应该有本次启动的新时间戳
- 如果 log 只有旧记录，不要信任后续 benchmark 结果
- API 可用但 worker 未真正消费任务时，常见表象是 run 长时间停在 `queued`

### 3. 输出目录对齐

- 当前 benchmark 结果应写入本次 runtime 对应的 `runs/` 目录
- 不要把旧 runtime 目录中的 `run.json` 误当作本次证据
- 保存 benchmark 结果时，最好同时记录 `run_id` 和 summary JSON 路径

### 4. 依赖文件与输入路径对齐

- 确认依赖文件指向的是本次预期使用的版本
- 确认 manifest 或本地输入路径存在且对应当前 case
- 不要混用不同 worktree、不同数据目录或旧临时目录的输入

### 5. 证据保存对齐

- Tier 2 至少保存 harness summary 和失败 case 的 `run_id`
- Tier 3 除 summary 外，还应能回溯到 `run.json`、`plan.json`、`audit.jsonl` 和 artifact
- 如果这次运行的证据无法回溯，就不应把结果写成正式 benchmark 结论

## Manifest Preflight

`eval_harness` 在 manifest 模式下现在会先做 preflight，再进入真正的长时间运行等待。

### API preflight

- 只要 manifest 中存在 `execution_mode=agent` 且 `readiness=agent-ready` 的 case，就会先检查 `base_url` 对应的 `/api/v2/runs` 是否可达
- 这个检查的目的不是判断业务成功，而是尽早发现 API 根本不可达、端口错误或 runtime 没起来
- 如果 API preflight 失败，相关 runnable case 会直接标记为 `failed`，并返回明确的 preflight 错误，而不是等到长 timeout 后才报模糊超时

### Input preflight

- 对每个 `agent-ready` 的 runnable case，在真正提交 run 之前会先检查 `inputs.osm` 和 `inputs.reference`
- 如果路径缺失或文件不存在，该 case 会直接标记为 `failed`
- 这类失败应被视为输入配置问题，而不是算法或 runtime 问题

### Preflight failure interpretation

- `failed` 且错误中带有 `Manifest preflight` 字样时，优先修配置或 runtime，不要先看算法
- `skipped` 仍只表示 case 当前不该被 agent harness 执行，例如 `legacy-script`、`blocked` 或 `agent-ready-with-prep`
- 只有 preflight 通过后的 case，才值得用 timeout、plan、artifact 或 audit 去分析运行时行为

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
- `last_event`
- `event_count`

如果需要完整时间线，直接读取：

- `runs/<run_id>/audit.jsonl`
- `GET /api/v2/runs/{run_id}/audit`

### artifact 未生成

优先检查：

- 输入 ZIP 是否包含 `.shp/.shx/.dbf`
- 输出目录是否生成 `.shp` bundle
- `repair_records` 是否已经耗尽当前修复策略
