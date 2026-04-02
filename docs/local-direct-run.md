# GeoFusion 本机直跑说明

## 前置约定

- 将 Neo4j、Redis、LLM 的本机配置放在仓库根目录的 `依赖.txt`
- 环境变量优先级高于 `依赖.txt`
- 默认本机 Redis 端口按 `依赖.txt` 解析；当前约定为 `6380`
- 默认 Neo4j 使用 `bolt://localhost:7687`
- 默认模型兜底为 `qwen3.5-397b-a17b`

## 启动步骤

1. 先做依赖和 Neo4j 检查：

```bash
python scripts/start_local.py --check-only
```

2. 如果当前 Python 环境还没装齐运行依赖，直接执行：

```bash
python scripts/start_local.py --install-deps
```

3. 脚本会自动完成：

- 从 `依赖.txt` 注入 Neo4j / Redis / LLM 配置
- 检查缺失的 Python 模块
- 在 `WorkflowPattern` seed 缺失时自动执行 `python -m kg.bootstrap --ensure`
- 启动 API / worker / scheduler
- 将日志写到 `runs/local-runtime/`

## 样例冒烟

服务启动后，用仓库自带 golden case 做一次 `/api/v2/runs` 冒烟：

```bash
python scripts/smoke_local_v2.py
```

默认样例为 `tests/golden_cases/building_disaster_flood`，脚本会：

- 上传 `osm.zip` 和 `ref.zip`
- 轮询 `/api/v2/runs/{run_id}`
- 校验 `plan` 中的 pattern / algorithm / output type
- 下载 artifact 并检查 `.shp/.shx/.dbf`

## 关键文件

- 启动脚本: [scripts/start_local.py](/E:/vscode/fusionAgent/scripts/start_local.py)
- 冒烟脚本: [scripts/smoke_local_v2.py](/E:/vscode/fusionAgent/scripts/smoke_local_v2.py)
- bootstrap 工具: [kg/bootstrap.py](/E:/vscode/fusionAgent/kg/bootstrap.py)
- 配置解析: [utils/local_runtime.py](/E:/vscode/fusionAgent/utils/local_runtime.py)
