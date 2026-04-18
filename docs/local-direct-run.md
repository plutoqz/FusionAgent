# FusionAgent 本机直跑说明

## 文档定位

这份文档只描述“当前已实现的本机可用 MVP”，不描述最终完整目标形态。
当前重点是先在你的电脑上稳定跑通 `building` / `road` 两类矢量融合任务。

## 前提条件

- Python 3.9 - 3.11
- 可用的 Redis
- 可用的 Neo4j 5.x
- `requirements.txt` 里的 Python 依赖

本地私有配置写在仓库根目录的 `依赖.txt`，可由 [依赖.txt.example](/E:/vscode/fusionAgent/依赖.txt.example) 复制得到。

## 端口与依赖约定

- 日常本机开发、本机冒烟、手工联调默认使用 API `8000`
- 推荐的标准启动方式是 `python scripts/start_local.py --port 8000`
- `scripts/start_local.py`、`main.py` 和 `worker/celery_app.py` 会优先读取仓库根目录 `依赖.txt`
- 本机 broker / backend 以 `依赖.txt` 中的 `Redis端口` 为准；仓库样例当前使用 `6380`
- 只有未提供本地依赖文件时，Celery 才回退到通用默认值 `redis://localhost:6379/0`
- Neo4j 默认约定为 `bolt://localhost:7687`
- `8011` 预留给隔离的 fast-confidence 检查
- `8010` 预留给隔离的 real-data benchmark
- `8012+` 只建议用于临时排障，不作为常驻默认端口

## Neo4j 隔离约定

- 如果 Neo4j 是 Enterprise 并且支持多数据库，可以通过 `GEOFUSION_NEO4J_DATABASE` 指向专用数据库。
- 如果 Neo4j 是 Community Edition，FusionAgent 会自动探测当前 home database，并通过 `:FusionAgentManaged` 标签隔离自己的子图。
- 当前仓库默认兼容 Community Edition，因此“本机可用”优先保证的是“查询与管理隔离”，不是强依赖多数据库。

只读检查当前图状态：

```bash
python scripts/inspect_neo4j_state.py
python scripts/inspect_neo4j_state.py --managed-only
```

## 启动步骤

### 1. 检查本地依赖与 Neo4j

```bash
python scripts/start_local.py --check-only
```

输出会包含：

- Neo4j edition
- 当前隔离模式：`database` 或 `managed-label`
- 是否检测到外部标签
- 是否已经存在 FusionAgent 的 seed 数据

### 2. 如需重建 FusionAgent 自己管理的子图

```bash
python scripts/start_local.py --check-only --reset-managed-graph
```

这只会删除 `:FusionAgentManaged` 节点，不会删除其他业务图数据。

### 3. 启动本地 API / worker / scheduler

```bash
python scripts/start_local.py --port 8000
```

日志会输出到 `runs/local-runtime/`：

- `api.log`
- `worker.log`
- `scheduler.log`

## 本机冒烟

```bash
python scripts/smoke_local_v2.py --base-url http://127.0.0.1:8000
python scripts/smoke_agentic_region.py --base-url http://127.0.0.1:8000 --query "fuse building and road data for Nairobi, Kenya" --timeout 1200
```

默认使用 `tests/golden_cases/building_disaster_flood` 作为样例，脚本会：

- 上传 `osm.zip` 和 `ref.zip`
- 轮询 `/api/v2/runs/{run_id}`
- 校验 plan 中的 pattern / algorithm / output type
- 下载 artifact 并检查 `.shp/.shx/.dbf`

`smoke_agentic_region.py` 用于新的自然语言地区入口，脚本会：

- 提交 `input_strategy=task_driven_auto` 的 AOI 感知请求
- 轮询 `/api/v2/runs/{run_id}`
- 输出 `run_id`、解析到的 AOI、实际 source id 与 artifact path
- 建议优先用 `Nairobi, Kenya` 做标准验证

## 当前真实边界

当前本机链路已具备：

- `v1` 直接融合
- `v2` 规划、验证、执行、有限修复
- artifact 下载与状态文件落盘
- 自然语言地区名 -> AOI 解析 -> 自动下载/裁剪/组装输入 bundle

当前本机链路尚未具备：

- 完整 `replan`
- `raw.google.building` 自动官方下载
- 完整经验学习写回
- 独立前端产品界面

## 常用命令

```bash
python -m pytest -q
python scripts/start_local.py --check-only
python scripts/start_local.py --check-only --reset-managed-graph
python scripts/start_local.py --port 8000
python scripts/smoke_local_v2.py --base-url http://127.0.0.1:8000
python scripts/start_local.py --port 8010
python scripts/inspect_neo4j_state.py --managed-only
```
