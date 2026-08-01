# FusionAgent 工程化鲁棒性循环测试与优化

> **定位**：本文件是 Codex 主会话的长程任务剧本。每轮循环开始前应重新读入关键段落（Step 0-9），防止上下文漂移遗忘约束。
>
> **最后更新**：2026-07-14

---

## 角色设定

你就是我——FusionAgent 的核心开发者，正在进行真实的工程化鲁棒性测试。你不是在"模拟"一个测试流程，而是在实际工作：启动服务、提交任务、检查证据、发现问题、修复代码、再跑下一轮。

你的风格是务实、严谨、不凑合——每一个暴露的问题都必须追溯到根因，然后做**系统性修复**而非针对本次任务的临时打补丁。你对代码质量有要求，对证据链路有洁癖，对"不知道为什么但这次过了"这种事零容忍。

## 项目背景

FusionAgent 是一个面向有界灾害响应场景的地理空间矢量数据融合智能体运行时。核心链路：

```
planner → validator → executor → healing/replan → writeback
```

支持的任务类型：`building`、`road`、`water`、`poi`（有界）
支持的输入模式：`task_driven_auto`（自然语言 AOI 描述 → Nominatim 地理编码 → admin boundary 匹配 → 矢量裁剪 → 融合）
标准证据输出：`run.json`、`plan.json`、`validation.json`、`audit.jsonl`、`artifact.zip`

**AOI 裁剪机制**：系统通过 Nominatim 解析地点名称为 bbox，然后尝试从本地 `Data/admin/` 目录匹配行政区划边界多边形（`.gpkg` / `.shp` / `.geojson`）。匹配成功时使用精确行政边界裁剪（`degraded_bbox_clip=false`），匹配失败时回退到 bbox 裁剪（`degraded_bbox_clip=true`）。因此选择任务区域时，应使用 Nominatim 可解析的真实行政区划名称。

当前已知的薄弱环节：
- **任务解析**：intent resolution、AOI geocoding、参数绑定、job_type 推断
- **数据下载**：source acquisition 失败/超时、bbox 裁剪异常、数据为空、source 不可用时的 fallback
- **融合流程**：planner 方案生成不合理、executor 调度遗漏、算法内部崩溃
- **失败处理**：healing 未触发、replan 无效、recovery 无法恢复、错误信息不可读

## 核心目标

通过**多轮随机真实任务测试 → 根因分析 → 系统性修复**的循环，逐步提升 FusionAgent 的工程化鲁棒性。

每轮循环的铁律：
1. **不针对本次任务做特判式修补**——如果 Gitega 的 building 融合失败，不要只修 Gitega。找出这类场景的共性，让所有类似 case 都能过。
2. **每次修复消除一类问题**，而非一个实例。
3. **数据生命周期短**——每轮完成后，下载的源数据和运行产物必须清理。
4. **修复必须有测试保护**——为修复的逻辑路径增加 pytest 用例。

---

## 执行架构：主会话 + 子智能体

为避免长程任务中上下文爆炸，采用分层执行架构：

| 层级 | 角色 | 模型 | 职责 |
|------|------|------|------|
| 主会话 | 编排者（你） | 当前模型 | 随机选任务、提交任务、监控状态、收集证据、根因分析、调度子智能体、清理数据、记录历史 |
| 子智能体 | 修复者 | `gpt5.5-xhigh` | 读取相关代码、实施修复、编写/修改测试、运行测试验证 |
| 子智能体 | 审查者（可选） | `gpt5.5-xhigh` | 对修复 diff 做独立 review，检查是否违反特判原则 |

**调度原则**：
- 主会话**不直接读取大文件或编辑代码**——所有代码修改通过子智能体完成
- 主会话只操作轻量文件：`tmp/loop-history.json`、`tmp/loop-analysis.md`、`tmp/current-round/` 下的证据文件
- 子智能体每次只被分配**一个明确的修复任务**（一个根因 → 一个子智能体），完成后返回结果
- 如果一轮有多个不相关的根因，并行派发多个子智能体

**子智能体任务模板**：

```
## 修复任务

**根因**：{从 loop-analysis.md 摘录的根因描述，含文件:行号}
**修复方向**：{P0-P4 优先级和具体方向}
**禁止事项**：不允许针对 {area_name} 做特判；修复必须是通用逻辑

## 执行步骤
1. 阅读涉及的源文件，理解当前逻辑
2. 实施修复（最小改动原则）
3. 运行 `python -m pytest tests/ -q --tb=short -x --ignore=...` 确认不破坏现有测试
4. 为修复路径新增一个测试用例
5. 回报：改了哪些文件、新增了什么测试、测试结果
```

---

# 第一阶段：行政区级小区域快速循环

## 关于任务区域的选择

**关键约束**：FusionAgent 目前只支持基于行政区划的裁剪，不支持任意划定区域。因此选择的区域必须是 Nominatim 能解析到具体行政区划的地名，且该行政区的面积应控制在 **2-15 km²**（对应 OSM admin_level 8-10，即 commune/ward/district 级别）。

**如何选择合法的区域名**：
- ✅ 使用 OSM 中真实存在的行政区划名称：如 `"Gitega (commune), Burundi"`、`"Arrondissement de Parakou, Benin"`
- ✅ 使用 Nominatim 可解析的城区/街区名：如 `"Intramuros, Manila, Philippines"`
- ✅ 在 query 中使用足以让 Nominatim 返回明确行政边界的描述
- ❌ 不要使用任意地理描述如 `"downtown Nairobi 2km²"` —— 这无法匹配到行政边界
- ❌ 不要使用过大的行政区如 `"Bujumbura Mairie Province, Burundi"` —— 面积过大

**Codex 在每轮选区域时应**：
1. 在 query 中给出精确的行政区名（足以让 Nominatim 唯一解析）
2. 提交后检查 audit 中的 `aoi_resolved` 事件，确认 `admin_level` 非空且 `degraded_bbox_clip` 为 false（说明成功匹配了行政边界）
3. 如果 Nominatim 返回的 bbox 面积超过 20 km²，换一个小一级的行政区

---

## 工作流程（单轮循环）

### Step 0 — 前置检查

在启动首轮或每次怀疑环境状态时执行：

```powershell
# 1. 确认 Redis 可连通（端口见 依赖.txt，默认 6380）
python -c "import redis; r=redis.Redis(host='localhost',port=6380); print(r.ping())"

# 2. 确认 Neo4j 可连通
python scripts/inspect_neo4j_state.py --managed-only

# 3. 确认依赖无缺失
python scripts/start_local.py --check-only
```

如果有服务不可用，先修复环境再继续。

如果 API 服务已在运行，验证健康：

```powershell
curl -s http://127.0.0.1:8000/api/v2/runtime | python -m json.tool
```

### Step 1 — 随机选择测试任务

从以下维度**随机**组合。每轮与之前轮次**不重复**（记录在 `tmp/loop-history.json` 中）。

#### 1a. 任务类型（随机选一个）

| 值 | 含义 | 状态 | 随机权重 |
|----|------|------|---------|
| `building` | 建筑物融合 | 稳定支持 | 3 |
| `road` | 道路融合 | 稳定支持 | 3 |
| `water` | 水系融合 | 稳定支持 | 1 |
| `poi` | 兴趣点融合 | 有界支持 | 3 |

> 权重意味着 building/road/poi 各 30% 概率，water 10%。

#### 1b. 灾害类型（随机选一个）

`flood` | `earthquake` | `hurricane` | `wildfire` | `conflict`

均匀分布。注意灾害类型不必与区域地理严格匹配——人道主义响应场景不要求气候学精确。

#### 1c. 目标区域（随机选一个行政单元）

**选择约束**：
- 必须是 Nominatim 可解析的真实行政区划，不能用"某城市中心 2km²"这种描述
- 确保该行政区的 Nominatim bbox 面积在 2-15 km² 范围内
- 必须有 OSM 基础数据覆盖
- **每轮与历史不重复**（按 area_id 去重）

**推荐的行政单元候选池**（带唯一 ID，按大洲分组）：

```
# 非洲 (AF) — admin_level 8-9，多为 commune / sector / ward
AF-01 | Commune de Gitega, Burundi
AF-02 | Commune de Ngozi, Burundi
AF-03 | Sector Nyamirambo, Nyarugenge, Kigali, Rwanda
AF-04 | Nakasero, Kampala Central Division, Uganda
AF-05 | Commune de Parakou, Benin
AF-06 | Arrondissement de Ouando, Porto-Novo, Benin
AF-07 | Arrondissement de Abomey-Calavi, Benin
AF-08 | Kariakoo Ward, Ilala, Dar es Salaam, Tanzania
AF-09 | Commune de Bujumbura Centre, Burundi (仅中心 commune，非全城)
AF-10 | Sector Kimironko, Gasabo, Kigali, Rwanda

# 亚洲 (AS) — admin_level 8-10
AS-01 | Saddar Town, Karachi, Pakistan
AS-02 | Ward 26, Kathmandu Metropolitan City, Nepal
AS-03 | Ward 18, Dhaka North City Corporation, Bangladesh
AS-04 | Barangay 656, Intramuros, Manila, Philippines
AS-05 | 東京都新宿区四谷, Japan
AS-06 | Khet Bang Rak, Bangkok, Thailand
AS-07 | Kelurahan Menteng, Jakarta Pusat, Indonesia
AS-08 | Phường Trúc Bạch, Ba Đình, Hà Nội, Vietnam
AS-09 | Botahtaung Township, Yangon, Myanmar
AS-10 | Mahalle Fatih, Istanbul, Turkey

# 欧洲 (EU)
EU-01 | Quartier Centre, Rennes, France
EU-02 | Stadtteil Altstadt, Heidelberg, Germany
EU-03 | Quartiere Centro Storico, Arezzo, Italy
EU-04 | Freguesia de Sé Nova, Coimbra, Portugal
EU-05 | Deelgemeente Leuven Centrum, Belgium
EU-06 | Mjesna zajednica Baščaršija, Sarajevo, Bosnia

# 美洲 (AM)
AM-01 | Section Communale de Pétion-Ville, Haiti
AM-02 | Colonia Centro, Oaxaca de Juárez, Mexico
AM-03 | Comuna San José, Manizales, Colombia
AM-04 | Distrito de Arequipa Cercado, Peru
AM-05 | Macrodistrito Centro, La Paz, Bolivia
AM-06 | Barrio El Centro, Tegucigalpa, Honduras

# 大洋洲 (OC)
OC-01 | Suva Central Ward, Fiji
OC-02 | Ward 1, Port Moresby, Papua New Guinea
```

**使用方式**：
- 随机时记录 area_id（如 `AF-03`），query 中使用该行政区的 Nominatim 可解析名
- 如果某区域 Nominatim 解析失败（无结果或返回点坐标而非面），标记该 ID 为 `blocked`，换一个
- 如果所有候选池用尽，使用 Nominatim 的 `search` API 自己发掘新的小行政区（query `"commune in Benin"` 或 `"ward in Kathmandu"` 等），确认面积合格后加入候选池

### Step 2 — 启动运行时

如果 API 服务未运行，启动全链路模式：

```powershell
python scripts/start_local.py --port 8000
```

如果已在运行且 `GET /api/v2/runtime` 返回正常，跳过。

### Step 3 — 提交融合任务

构造 query：
```
fuse {task_type} data for {disaster_type} response in {admin_area_full_name}
```

示例：
```
fuse building data for flood response in Commune de Gitega, Burundi
```

提交：

```powershell
python scripts/smoke_agentic_region.py `
  --base-url http://127.0.0.1:8000 `
  --job-type {task_type} `
  --query "{query}" `
  --timeout 600 `
  --output-json tmp/current-round/inspection.json
```

说明：
- `--job-type` 是 `smoke_agentic_region.py` 的 required 参数，传 Step 1a 选出的任务类型
- `--timeout` 600 秒（小行政区应在 5 分钟内完成）
- `--output-json` 保存 inspection 结果，供 Step 5 分析

### Step 4 — 判断结果

`smoke_agentic_region.py` 的退出码：

| 退出码 | 含义 |
|--------|------|
| 0 | 成功（状态 `succeeded`） |
| 非 0 | 失败/超时/状态异常 |

如果脚本超时或异常退出，记录具体错误信息和 run_id，后续手动拉取证据分析。

### Step 5 — 收集证据

无论成功还是失败，收集完整证据链：

```powershell
# 保存 run_id（从 inspection.json 或 smoke 脚本输出中提取）
$run_id = "从上一步输出获取"

# 获取 run 基本信息
curl -s http://127.0.0.1:8000/api/v2/runs/$run_id > tmp/current-round/run.json

# 获取 plan
curl -s http://127.0.0.1:8000/api/v2/runs/$run_id/plan > tmp/current-round/plan.json

# 获取 audit log
curl -s http://127.0.0.1:8000/api/v2/runs/$run_id/audit > tmp/current-round/audit.json

# 获取 inspection 综合视图
curl -s http://127.0.0.1:8000/api/v2/runs/$run_id/inspection > tmp/current-round/inspection.json
```

如果任务成功（`succeeded`），额外检查 artifact：

```powershell
# 下载 artifact
curl -s -o tmp/current-round/artifact.zip http://127.0.0.1:8000/api/v2/runs/$run_id/artifact

# 快速检查 artifact 内容
python -c "
import zipfile
with zipfile.ZipFile('tmp/current-round/artifact.zip') as z:
    names = z.namelist()
    print(f'Files in artifact: {len(names)}')
    for n in sorted(names):
        print(f'  {n} ({z.getinfo(n).file_size} bytes)')
    has_shp = any(n.endswith('.shp') for n in names)
    has_shx = any(n.endswith('.shx') for n in names)
    has_dbf = any(n.endswith('.dbf') for n in names)
    has_prj = any(n.endswith('.prj') for n in names)
    print(f'SHP: {has_shp}, SHX: {has_shx}, DBF: {has_dbf}, PRJ: {has_prj}')
"
```

### Step 6 — 问题分类与根因分析

**仅在非成功或证据异常时执行**。主会话直接读取 `tmp/current-round/` 下的 JSON 文件进行分析——这些文件很小（通常 < 500KB），不会爆上下文。

#### 6a. 阶段定位

根据 audit 事件和 inspection，判断问题属于哪个阶段：

| 阶段 | 典型 audit event | 症状 |
|------|-----------------|------|
| 任务解析 | `aoi_resolved` 缺失或 `admin_level` 为空、`intent_resolved` 缺失 | AOI 未解析、Nominatim 返回点而非面、job_type 推断错误 |
| 数据下载 | `source_acquisition_failed`、`source_materialized` 缺失 | 下载超时、源不可用、裁剪后数据为空、OSM 数据无覆盖 |
| Planner | `plan_generated` 缺失、plan 无候选 | 无可用 pattern、source 不匹配、grounding 拒绝 |
| Validator | `plan_grounding_rejected`、`validation_failed` | 计划被拒绝、校验规则过严或误杀 |
| Executor | `execution_failed`、`algorithm_error` | 算法崩溃、几何异常、OOM、写出失败 |
| Healing/Replan | 失败后无 `healing_attempted` 或 `replan_attempted` | 修复未触发或修复无效 |
| Writeback | `artifact_missing` | 产物不完整、ZIP 损坏 |

#### 6b. 根因分析（必须回答四个问题）

对每个问题，回答：

1. **直接原因**：代码中哪一行 / 哪一个条件导致了失败？（引用具体文件:行号，由子智能体定位）
2. **触发条件**：什么输入组合触发了它？（特定的 admin_level？bbox 形状？数据源组合？AOI 名称格式？）
3. **同类范围**：还有哪些场景会遇到同样的根因？列举至少 3 个。
4. **为什么已有防护没生效**：代码中是否有 try/except、fallback、guard？如果有，为什么没拦住？如果没有，为什么这里缺少防护？

将分析写入 `tmp/loop-analysis.md`（首次创建，后续追加）：

```markdown
## Round {N} 分析 — {ISO timestamp}

- **Area ID**: {area_id}
- **Query**: {query}
- **Job Type**: {task_type} | **Disaster**: {disaster_type}
- **Run ID**: {run_id}
- **Status**: {status} | **Duration**: {duration}s
- **Admin Level**: {resolved admin_level or "N/A"}
- **Clip Mode**: {degraded_bbox_clip or "unknown"}

### 问题 1: {简短标题}

- **阶段**: {阶段名}
- **直接原因**: {文件:行号 — 描述}
- **触发条件**: {输入组合}
- **同类范围**: {≥3 个同类场景}
- **防护失效原因**: {为什么没拦住}

### 问题 2: ...
```

### Step 7 — 系统性修复

**由子智能体执行**。主会话为每个独立根因派发一个子智能体任务。

#### 修复优先级

| 优先级 | 修复方向 | 说明 |
|--------|---------|------|
| P0 | 让失败可预期、可读 | 不支持的能力在 planner/validator 阶段明确拒绝，给出可读原因，不拖到 executor 崩溃 |
| P1 | 增强 fallback 与降级 | 首选源不可用时走 fallback 链，audit 记录降级决策 |
| P2 | 修复通用逻辑 | 改 planner/executor 的通用逻辑，**严禁 `if area == "X"` 特判** |
| P3 | 增加防御性检查 | 数据进入算法前检查几何有效性、CRS 一致性、非空 |
| P4 | 改进错误信息 | audit 中的错误能让 operator 看懂，而非裸 traceback |

#### 子智能体派发

用 `task` 工具派发，模型设为 `gpt5.5-xhigh`。模板见本文档开头的"执行架构"部分。

修复范围限定在：
- `agent/` — planner、executor、retriever、validator、policy
- `services/` — 各 service
- `schemas/` — 数据模型
- `tests/` — 对应测试

#### 提交修复

子智能体返回后，主会话验证测试通过，然后 git commit：

```bash
git add -A
git commit -m "{type}({component}): {简短描述}

Root cause: {根因一句话}
Affected scope: {影响的同类场景}
Round: {N}"
```

Commit type: `fix`（修复）或 `feat`（新增防护/能力）。

### Step 8 — 清理本轮数据

**强制步骤，每轮必做。**

```powershell
# 1. 删除本轮 run 产物目录
Remove-Item -Recurse -Force runs/{run_id}/ -ErrorAction SilentlyContinue

# 2. 清理本轮临时文件
Remove-Item -Recurse -Force tmp/current-round/ -ErrorAction SilentlyContinue

# 3. 清理 source cache（如果存在且不需要跨轮复用）
Remove-Item -Recurse -Force runs/source-assets/ -ErrorAction SilentlyContinue

# 4. 检查 runs/ 目录大小，如果异常增大需深入清理
$size = (Get-ChildItem runs/ -Recurse | Measure-Object -Property Length -Sum).Sum
Write-Host "runs/ total size: $([math]::Round($size/1MB, 2)) MB"
```

**保留**：
- `tmp/loop-analysis.md` — 所有轮次的问题分析（持续追加）
- `tmp/loop-history.json` — 测试历史（断点续跑）
- `tmp/known-limitations.md` — 已知限制清单（如适用）
- git commits — 修复产生的代码变更

### Step 9 — 记录与迭代

#### 9a. 更新历史记录

在 `tmp/loop-history.json` 中追加：

```json
{
  "round": {N},
  "timestamp": "{ISO 8601}",
  "area_id": "AF-02",
  "query": "Commune de Gitega, Burundi",
  "task_type": "building",
  "disaster_type": "flood",
  "run_id": "abc12345",
  "status": "succeeded",
  "admin_level": "commune",
  "clip_mode": "boundary",
  "duration_seconds": 187,
  "issues_found": [],
  "files_changed": [],
  "commit_hashes": [],
  "notes": ""
}
```

#### 9b. 判断是否继续

检查是否满足第一阶段完成标准（见下方）。如果满足，进入第二阶段；否则回到 Step 1。

---

## 第一阶段完成标准

满足**任一**即可停止第一阶段：

### 标准 A：连续成功（首选）

- 连续 **5 轮**随机任务全部 `succeeded`
- 覆盖至少 **3 种**任务类型（`building` 必须包含）
- 覆盖至少 **3 种**灾害类型
- 覆盖至少 **2 个**不同大洲的区域（按 area_id 前缀判断：AF/AS/EU/AM/OC）
- 每轮 artifact 通过完整性检查（SHP/SHX/DBF/PRJ 存在、几何非空）
- 至少 3 轮的 `clip_mode` 为 `boundary`（非 degraded bbox clip）

### 标准 B：成功率达标

- 最近 **12 轮**成功率 ≥ **85%**（即最多 2 次失败）
- 且没有同类问题重复出现（每轮失败根因各不相同）

### 标准 C：收敛停止

- 连续 **4 轮**没有发现新的问题类别（所有失败都是已知未解决、需要架构级变更才能修的问题）
- 输出已知限制清单：
  ```
  tmp/known-limitations.md
  ```

### 标准 D：手动停止

- 你判断继续小区域循环的边际收益已经很低，可以进入第二阶段

---

## 硬性约束（第一阶段）

1. **区域必须是真实行政区划**——使用 Nominatim 可解析的行政名，不能是自定义 bbox 描述
2. **禁止特判代码**——如果你或子智能体在写 `if "Gitega" in area_name`，立即停止并重新思考
3. **每轮数据必须清理**——`runs/{run_id}/`、`tmp/current-round/`、source cache 不能残留
4. **修复必须带测试**——每个修复至少一个 pytest 用例覆盖修复路径
5. **先分析再动手**——不准跳过 Step 6 的根因分析直接改代码
6. **每轮独立 commit**——不堆积修改，message 包含根因和影响范围
7. **主会话不直接读/改大文件**——代码操作全部通过子智能体（gpt5.5-xhigh）完成
8. **断点可续**——`tmp/loop-history.json` 和 `tmp/loop-analysis.md` 保证中断后可从下一轮继续

---

# 第二阶段：大区域压力测试

> **准入条件**：第一阶段完成标准 A/B/C/D 任一满足后方可进入。
> **目标**：验证系统在更大行政区和更大量数据下的鲁棒性。

## 第二阶段目标

从 2-15 km² 的 commune/ward 级别逐步放大到：
- **城市级**（50-500 km²）：整个中等城市的行政区（如 `Bujumbura Mairie, Burundi`）
- **省级**（1000-10000 km²）：一个省的完整辖区
- **国家级**（可选，仅在 city/province 稳定后）：小国全境

验证的核心能力：
- 大区域数据下载的稳定性和超时处理
- 分片（tile）策略正确性
- 内存管理（大几何量下是否 OOM）
- 长时任务的状态轮询和恢复
- artifact 完整性（大量 feature 时 ZIP 是否损坏）

## 第二阶段工作流

### Phase 2A — 城市级（至少 3 轮，每轮不同城市）

区域示例（≤ 500 km²，预期执行时间 5-20 分钟）：

```
CITY-01 | Bujumbura Mairie, Burundi (~120 km²)
CITY-02 | Commune de Cotonou, Benin (~80 km²)
CITY-03 | Kathmandu Metropolitan City, Nepal (~50 km²)
CITY-04 | Commune de Port-au-Prince, Haiti (~70 km²)
CITY-05 | City of Kigali, Rwanda (~70 km²)
```

参数调整（timeout 放宽）：
```powershell
python scripts/smoke_agentic_region.py `
  --base-url http://127.0.0.1:8000 `
  --job-type {task_type} `
  --query "fuse {task_type} data for {disaster_type} response in {city_admin_name}" `
  --timeout 1800
```

### Phase 2B — 省级（至少 2 轮）

区域示例（1000-10000 km²，预期执行时间 10-60 分钟）：

```
PROV-01 | Bujumbura Province, Burundi
PROV-02 | Département de l'Atlantique, Benin
PROV-03 | Bagmati Province, Nepal
```

如果系统触发 tiled 模式，观察：
- 分片数量是否合理
- 各分片是否都能成功
- 最终 merge 是否正确

### Phase 2C — 国家级（可选，至少 1 轮）

仅当前两阶段都稳定后尝试。选择最小国家全境：

```powershell
python scripts/smoke_agentic_region.py `
  --base-url http://127.0.0.1:8000 `
  --job-type building `
  --query "fuse building data for flood preparedness in Burundi" `
  --timeout 3600
```

## 第二阶段额外检查维度

| 维度 | 检查点 |
|------|--------|
| 超时 | 各阶段耗时分布？哪个阶段是瓶颈？ |
| 内存 | Python 进程内存是否线性增长？有无泄漏迹象？ |
| 分片 | Tile 划分是否合理？边界处几何是否正确？ |
| 合并 | 各 tile 合并后有无重复/缺失 feature？ |
| 稳定性 | 同一 city 不同 task type 是否都成功？ |
| 数据覆盖 | 大区域是否触发数据源覆盖不足的问题？ |

## 第二阶段完成标准

- Phase 2A 至少 **3 轮全部成功**（不同城市、不同 task type）
- Phase 2B 至少 **2 轮成功**
- 无 OOM 崩溃
- 大区域 artifact 完整性可验证

## 第二阶段清理

大区域产物更多，清理需更彻底：

```powershell
# 删除所有本轮产生的 run 目录
Get-ChildItem runs/ -Directory | Where-Object { $_.Name -match '^[0-9a-f]{8}' } | Remove-Item -Recurse -Force

# 大区域 source cache 必须清理（可能非常大）
Remove-Item -Recurse -Force runs/source-assets/ -ErrorAction SilentlyContinue

# 清理临时文件
Remove-Item -Recurse -Force tmp/current-round/ -ErrorAction SilentlyContinue

# 报告磁盘使用
Get-ChildItem runs/ -Recurse | Measure-Object -Property Length -Sum | ForEach-Object {
    Write-Host "runs/ after cleanup: $([math]::Round($_.Sum/1MB, 2)) MB"
}
```

---

# 全局约束（两阶段通用）

1. **代码变更必须有测试保护**——无测试的修复等于没修
2. **不特判**——通用逻辑修复，不是 `if area == "X"`
3. **每轮数据必清理**——磁盘不是无限的
4. **先分析后动手**——不理解根因的修复是碰运气
5. **Git 记录清晰**——每轮独立 commit，message 包含根因和影响范围
6. **断点可续**——`tmp/loop-history.json` + `tmp/loop-analysis.md` 保证中断后可继续
7. **架构级问题记录而非强行解决**——需要新增 tiled executor、重构 planner 等大改动，记录到 `tmp/known-limitations.md`，不在当前循环中实现
8. **主会话保轻量**——代码读写一律走子智能体（gpt5.5-xhigh），主会话只做编排、分析和记录
