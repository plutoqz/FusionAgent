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
python scripts/start_local.py
```

日志会输出到 `runs/local-runtime/`：

- `api.log`
- `worker.log`
- `scheduler.log`

## 本机冒烟

```bash
python scripts/smoke_local_v2.py
```

默认使用 `tests/golden_cases/building_disaster_flood` 作为样例，脚本会：

- 上传 `osm.zip` 和 `ref.zip`
- 轮询 `/api/v2/runs/{run_id}`
- 校验 plan 中的 pattern / algorithm / output type
- 下载 artifact 并检查 `.shp/.shx/.dbf`

## 当前真实边界

当前本机链路已具备：

- `v1` 直接融合
- `v2` 规划、验证、执行、有限修复
- artifact 下载与状态文件落盘

当前本机链路尚未具备：

- 完整 `replan`
- 动态外部数据接入
- 完整经验学习写回
- 独立前端产品界面

## 常用命令

```bash
python -m pytest -q
python scripts/start_local.py --check-only
python scripts/start_local.py --check-only --reset-managed-graph
python scripts/start_local.py
python scripts/smoke_local_v2.py
python scripts/inspect_neo4j_state.py --managed-only
```
