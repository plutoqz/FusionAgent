# FusionAgent

FusionAgent 是一个面向灾害应急场景的矢量数据融合智能体原型。当前系统已经能够围绕上传的 `zip shapefile` 输入，完成 `building` 和 `road` 两类任务的规划、验证、执行、修复、审计和产物输出。

它已经不再只是传统融合脚本的包装层，而是一个带有 KG 检索、LLM/mock 规划、显式执行状态、有限修复与重规划能力的领域受限 agentic workflow MVP。与此同时，它还不是“最终完整形态的矢量数据融合智能体”，目前更准确的定位是“可运行、可验证、可扩展的研究型工程原型”。

## 当前进展

### 已完成能力

当前代码库已经具备以下核心能力：

- `v2` 运行主链路已经成形：`planner -> validator -> executor -> healing/replan -> writeback`
- 已支持的任务类型：
  - `building`
  - `road`
- 已支持的输入输出契约：
  - 输入：上传的 `zip shapefile`
  - 输出：融合结果 shapefile bundle，以及完整的运行状态文件
- 已具备 KG 驱动的候选检索：
  - workflow pattern
  - algorithm
  - data source
  - data type
- 宸插叿澶?Phase 2 鎵╁睍鍚庣殑缁撴瀯鍖?metadata锛?
  - 绠楁硶 `accuracy_score` / `stability_score` / `usage_mode`
  - 鏁版嵁婧?freshness / quality / supported type 淇″彿
  - 绠楁硶 parameter spec 鐨?`tunable` / `optimization_tags`
  - 杈撳嚭 schema policy metadata锛堝瓧娈典繚鐣欍€侀噸鍛藉悕鎻愮ず銆佸吋瀹规€у熀鍑嗭級
- 已具备 LLM 或 mock 驱动的规划生成
- 已具备 validator 校验与 transform 自动插入
- 已具备执行期修复策略：
  - `alternative_source`
  - `alternative_algorithm`
  - `transform_insert`
- 已具备 repair 耗尽后的真实 replan 路径
- 已具备参数默认值绑定与执行期参数下发
- 已具备 artifact registry，以及 direct reuse / clip reuse 第一版执行闭环
- 已具备 Phase 4 第一轮 artifact reuse v2 安全闸门：
  - 按 `job_type` 区分 freshness policy（当前 `building=3d`，`road=1d`）
  - 复用前校验 `output_data_type` 与 `target_crs` 兼容性
  - clip reuse 物化后校验 CRS、必需字段与 bbox 边界，失败则显式回退 fresh execution
- 已具备 decision trace / audit trail 持久化
- 每次 run 已落盘：
- 宸插叿澶?Phase 3 绗竴杞樉寮?policy decision trace锛?
  - `pattern_selection`
  - `data_source_selection`
  - `artifact_reuse_selection`
  - `parameter_strategy`
  - `output_schema_policy`
  - `replan_or_fail`
  - `run.json`
  - `plan.json`
  - `validation.json`
  - `audit.jsonl`
  - artifact bundle
- 已完成一轮真实裁剪建筑数据 benchmark 与相关回归修复

### 最近一轮已收敛工作

最近这轮工程整理已经完成了以下关键事项：

- 将散落在多个脏 worktree 中的 runtime 代码线收敛并合并回 `main`
- 清理混乱的本地分支 / worktree，使主工作区恢复为干净 `main`
- 恢复了初始规划和 replan 阶段的 plan-time parameter binding
- 恢复了 `plan_created` 审计事件里的 `effective_parameters`
- 为以下能力补齐了回归测试：
  - 参数默认值绑定
  - policy engine 打分
  - artifact registry 匹配
  - planner 的 artifact reuse 上下文注入
  - agent run 状态、decision record 与审计落盘

一句话概括当前状态：主线已经从“能跑一些脚本”提升为“有明确运行闭环、可测试、可审计的融合智能体 MVP”。

## 距离最终矢量数据融合智能体还有哪些差距

最终目标不是“一个能跑两个融合任务的 API”，而是“一个可复用、可演化、可长时间稳定运行的矢量数据融合智能体”。相对于这个目标，当前主要还差六类能力。

### 1. 搜索空间仍然偏小

目前系统的可选空间仍然比较窄：

- 任务类型主要还是 `building` / `road`
- pattern 目录还不够丰富
- 算法族谱还偏少
- 数据源选择与质量信号还不够强

最终形态还需要：

- 更多灾种与场景覆盖
- 更多注册算法与 transform operator
- 更强的数据源 freshness / quality 元数据
- 更清晰的输出字段与 schema policy

### 2. Policy 层还只是部分显式化

目前仓库已经有 `PolicyEngine`、`DecisionRecord` 和部分决策追踪，但它还不足以被认为是最终智能体的完整“决策中枢”。

仍然缺少：

- 更广泛的 policy 覆盖面
- 对准确率、稳定性、速度、时效性、成本的更稳定权衡
- 更系统的候选评分证据来源
- 更完整的 policy 评测与消融实验

### 3. Artifact reuse 已形成第一版闭环，但还不够强

当前系统现在已经可以：

- 注册 artifact
- 在规划阶段发现可复用 artifact 候选
- 记录 artifact reuse 决策
- 这已经不只是 planner 阶段的提示。当前 runtime 命中 direct reuse 时会直接短路后续 fresh execution；命中 clip reuse 时会先物化裁剪产物，失败后再回退 fresh execution。
- 在运行阶段直接复用完全匹配 bbox 的历史产物
- 在运行阶段对更大范围的历史产物做 bbox 裁剪复用
- 在复用物化失败时自动回退 fresh execution
- 当前主线还会按 `output_data_type`、`target_crs` 和 `job_type` freshness policy 过滤候选，并把 schema policy / compatibility provenance 写进 artifact registry，避免把“看起来能复用”但实际不安全的历史产物短路进新 run

但这还只是第一版闭环，距离最终目标还需要：

- 更强的空间范围 / schema 兼容判定
- 按任务类型配置 freshness policy
- 更细粒度的 direct / clip / fallback 指标与可观测性
- 更严格的复用产物质量校验与跨 CRS 处理
- 清晰的 reuse 指标与回退策略

### 4. 长期学习与写回还偏弱

目前系统已经会写回反馈、repair 历史和 decision trace，但长期经验积累还比较浅。

最终还需要：

- 更强的 KG 或结构化长期记忆写回
- 跨 run 的执行结果聚合
- 基于历史证据的 policy 调优
- 对“临时运行日志”和“可持续学习知识”的更清晰区分

### 5. 评测体系还不是完整 harness

现在已经有：

- 单元测试 / 集成测试
- 本地 smoke
- benchmark 结果与修正记录

这足够支撑持续工程推进，但距离最终目标还差：

- 更大的 benchmark 矩阵
- 更系统的 fault injection 与 healing 评测
- 更完整的 baseline 对比
- 更稳定的回归追踪机制
- 更清晰的性能 / 质量长期观测

### 6. 产品化层还很薄

现在系统主要通过 API、状态文件、artifact 和本地脚本来使用，适合作为 MVP，但还不适合当作最终的用户产品。

最终还需要：

- 面向操作者的正式前端
- 更好的 run 对比、审查与结果查看流程
- 更稳固的部署与运维姿态
- 更强的多用户 / 长时间运行支撑
- 更清晰的人在回路控制

## 阶段判断

当前最准确的判断是：

> FusionAgent 现在已经是一个可运行、可测试、可审计的矢量数据融合智能体 MVP，但还不是最终完整的矢量数据融合智能体。

如果把最终目标理解为“稳定、可无人值守、可持续学习演化的融合智能体”，那么当前项目大致处于：

- 工程 MVP：已达到
- 有研究价值的智能体原型：已达到
- 最终生产 / 研究完整体：尚未达到

也就是说，最难的系统基础设施阶段已经完成了相当一部分，但后续还需要一个新的阶段，集中补齐：

- 搜索空间扩张
- 显式 policy 完整化
- artifact reuse 能力增强
- 系统化评测 harness
- 产品化与运维层

## 仓库结构

- `api/`：FastAPI 路由与 API 层
- `services/`：运行时编排服务，核心包括 `AgentRunService`
- `agent/`：planner、retriever、validator、executor、policy 等智能体逻辑
- `kg/`：KG repository、bootstrap、seed 与模型定义
- `adapters/`：建筑物 / 道路融合算法适配层
- `worker/`：Celery worker、beat 与任务入口
- `llm/`：LLM provider 抽象与 mock/openai-compatible provider
- `scripts/`：本地运行、smoke、bootstrap、检查脚本
- `tests/`：单元测试、集成测试、golden cases、benchmark 相关测试
- `docs/`：运行与工程文档
- `docs/superpowers/specs/`：设计和 benchmark 过程文档

## 运行方式

### 1. 本地快速 MVP 模式

适合：

- API 调试
- 单测
- planner / validator / executor 逻辑验证

```powershell
python -m pip install -r requirements.txt
$env:GEOFUSION_KG_BACKEND='memory'
$env:GEOFUSION_LLM_PROVIDER='mock'
$env:GEOFUSION_CELERY_EAGER='1'
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 2. 本地全链路模式

适合：

- Neo4j / Redis / Celery 联调
- 更接近真实运行环境的验证

先将仓库中的本地依赖模板文件复制为无 `.example` 后缀的本地私有依赖文件，然后运行：

```powershell
python scripts/start_local.py --check-only
python scripts/start_local.py
```

如需重置受管图再检查：

```powershell
python scripts/start_local.py --check-only --reset-managed-graph
```

### 3. Docker Compose

```powershell
Copy-Item .env.example .env
docker compose up --build
```

## 评测分层

为避免把“快速回归检查”和“慢速真实 benchmark”混在一起，当前仓库默认按三层评测来使用：

### Tier 1：单元测试与定向 runtime 回归

适合：

- 快速验证本地修改是否破坏核心行为
- 校验 planner / validator / executor / policy / artifact reuse 的局部逻辑
- 作为日常开发默认回归入口

产出要求：

- 通过的 `pytest` 输出即可
- 如涉及运行态问题，至少记录失败用例名或对应命令

### Tier 2：golden-case harness 运行

适合：

- 校验 API 到运行时闭环是否仍能跑通
- 验证 golden cases 的 plan、audit 和 artifact 是否仍符合预期
- 作为比单测更接近真实运行的一层工程验证

产出要求：

- 保存 harness summary JSON 或终端摘要
- 保存失败 case 的 `run_id`、错误信息，必要时补 `audit.jsonl`

### Tier 3：真实数据 benchmark

适合：

- 评估真实 building / road 数据上的端到端表现
- 留存研究证据、benchmark 结果和运行时间
- 比较不同实现、参数或 policy 调整后的真实效果

产出要求：

- 保存 benchmark summary JSON
- 保存对应 `run_id`
- 能回溯到 `run.json`、`plan.json`、`audit.jsonl` 和 artifact

当前 timeout 指南：

- `scripts/eval_harness.py` 的默认 `--timeout` 仍是 `180` 秒，这个值只适合快速 harness 检查，不适合作为真实 building benchmark 的判断阈值。
- 对真实数据 building benchmark，当前应显式使用更长 timeout；现阶段推荐至少 `1200` 秒。
- 不要把 `180` 秒超时直接解释为算法失败，先检查是否只是 benchmark 窗口设置过短。

### 推荐命令

推荐把默认回归入口和真实 benchmark 入口固定成两条命令，不要在同一条流水线里混跑。

快速置信命令：

- 先在一个终端启动 mock/in-memory/eager API：

```powershell
$env:GEOFUSION_KG_BACKEND='memory'
$env:GEOFUSION_LLM_PROVIDER='mock'
$env:GEOFUSION_CELERY_EAGER='1'
uvicorn main:app --host 127.0.0.1 --port 8011
```

- 再在第二个终端运行定向 pytest + 窄子集 golden-case harness：

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

真实证据命令：

- 先按 [local-direct-run.md](docs/local-direct-run.md) 或当前 benchmark worktree 的约定启动对齐后的 runtime，再运行 manifest-backed benchmark：

```powershell
python scripts/eval_harness.py `
  --manifest docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json `
  --case building_gitega_osm_vs_google_agent `
  --case building_gitega_osm_vs_msft_clipped_agent `
  --base-url http://127.0.0.1:8010 `
  --timeout 1200 `
  --output-json tmp/eval/real-evidence-summary.json
```

- 默认 PR/CI 继续只跑快路径 pytest，不把真实数据 manifest benchmark 放进默认 gating；Tier 3 只在明确需要研究证据时手动触发。

## API 入口

### v1

- `POST /api/v1/fusion/building/jobs`
- `POST /api/v1/fusion/road/jobs`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/jobs/{job_id}/artifact`

### v2

`v2` 的真实 run 接口是 `multipart/form-data` 上传，而不是原始 JSON。

- `POST /api/v2/runs`
- `GET /api/v2/runs/{run_id}`
- `GET /api/v2/runs/{run_id}/plan`
- `GET /api/v2/runs/{run_id}/audit`
- `GET /api/v2/runs/{run_id}/artifact`

示例：

```powershell
curl -X POST "http://127.0.0.1:8000/api/v2/runs" `
  -F "osm_zip=@tests/golden_cases/building_disaster_flood/input/osm.zip" `
  -F "ref_zip=@tests/golden_cases/building_disaster_flood/input/ref.zip" `
  -F "job_type=building" `
  -F "trigger_type=disaster_event" `
  -F "trigger_content=flood building fusion" `
  -F "disaster_type=flood" `
  -F "field_mapping={}" `
  -F "target_crs=EPSG:32643"
```

## 验证与测试

运行全量测试：

```powershell
python -m pytest -q
```

常用 runtime 子集：

```powershell
$env:GEOFUSION_KG_BACKEND='memory'
$env:GEOFUSION_LLM_PROVIDER='mock'
$env:GEOFUSION_CELERY_EAGER='1'
python -m pytest -q `
  tests/test_planner_context.py `
  tests/test_agent_run_service_enhancements.py `
  tests/test_eval_harness.py `
  tests/test_policy_engine.py `
  tests/test_artifact_registry.py `
  tests/test_parameter_binding.py `
  tests/test_parameter_default_binding.py `
  tests/test_planner_artifact_reuse.py `
  tests/test_agent_state_models.py `
  tests/test_kg_parameter_specs.py `
  tests/test_neo4j_bootstrap.py `
  tests/test_neo4j_repository.py
```

真实模型 live smoke 仍然是显式开启：

```powershell
$env:GEOFUSION_LIVE_SMOKE='1'
$env:GEOFUSION_LLM_PROVIDER='openai'
$env:GEOFUSION_LLM_BASE_URL='https://www.dmxapi.cn/v1'
$env:GEOFUSION_LLM_MODEL='qwen3.5-397b-a17b'
$env:GEOFUSION_LLM_API_KEY='your-key'
python -m pytest tests/test_live_smoke_v2.py -q
```

推荐使用顺序：

1. 默认先跑 Tier 1。
2. 改动涉及 API 闭环、artifact、audit 或运行编排时，再跑 Tier 2。
3. 只有在需要真实证据、性能结论或研究记录时，再跑 Tier 3。

Tier 3 运行前请先确认：

- API、worker 和 scheduler 是当前这次启动的新实例
- 目标 `base_url` 与实际运行端口一致
- 输出目录对应的是当前 runtime，而不是旧线程残留目录
- 依赖文件与输入数据路径和本次 benchmark 预期一致

## 当前边界

为了避免 README 过度承诺，需要明确几点：

- 当前系统还不是通用 GIS agent
- 当前融合能力仍主要围绕 `building` / `road`
- artifact reuse 已具备 direct / clip 第一版执行短路，但仍缺更强兼容性与策略层
- 前端与产品化层仍然很薄
- 一部分 ontology / design 文档描述的是目标态，而不是已全部实现的现状

## 推荐阅读

- [local-direct-run.md](docs/local-direct-run.md)
- [v2-operations.md](docs/v2-operations.md)
- [2026-04-07-fusion-agent-v2-design.md](docs/superpowers/specs/2026-04-07-fusion-agent-v2-design.md)
- [2026-04-08-benchmark-followup-summary.md](docs/superpowers/specs/2026-04-08-benchmark-followup-summary.md)

## 备注

- 由本地依赖模板文件复制得到的私有依赖文件不应提交
- `.env`、运行日志、`runs/`、`jobs/` 等产物应只保留在本地
- 仓库文本文件应统一使用 UTF-8 保存，避免编码混乱
