# 文档治理与归档规则

> 状态：A0 当前权威规则
> 更新日期：2026-07-28

## 1. 治理目标

文档体系必须同时满足四个要求：

1. 读者能在一分钟内找到当前权威结论。
2. 历史证据可追溯，但不会与当前计划竞争权威性。
3. 机器可读本体、实验 manifest 和人类说明保持同版本存放。
4. 临时渲染、诊断输出和会话材料不会进入长期文档入口。

## 2. 权威级别

| 级别 | 定义 | 典型位置 |
| --- | --- | --- |
| A0 | 研究章程、当前项目状态、主张边界和治理规则 | `docs/current/` |
| A1 | 当前工程/研究规范、协议和机器可读清单 | `docs/thesis/`、`docs/research/` |
| A2 | 运行手册、演示说明和辅助材料 | `docs/demo/`、各类 runbook |
| A3 | 历史计划、旧证据、会话交接和已替代版本 | `docs/archive/`、`docs/pasted/`、`docs/superpowers/**/done/` |

每份长期文档应尽量在开头标注 `状态` 和 `更新日期`。常用状态为：

- `authoritative/current`：当前权威。
- `active`：正在使用，但不覆盖 A0 总体口径。
- `draft`：草案，不能写成已实现事实。
- `historical`：历史材料，仅用于追溯。
- `superseded`：已有明确替代文件。

`docs/current/research-charter.md` 是研究对象、目标、研究问题、创新点和非主张的唯一最高权威。其他 A0 文档负责状态和执行治理，不得另行定义相互冲突的研究主体。

## 3. 目录职责

```text
docs/
  README.md                 唯一导航入口
  current/                  当前状态、主张、优先级、工作流和治理
  research/
    ontology/YYYY-MM-DD/    同版本本体 JSON、CSV、Markdown 和校验摘要
    presentations/YYYY-MM-DD/ 当前汇报材料及必要 QA 记录
  thesis/                   论文规范、案例矩阵、实验协议和章节材料
  archive/                  已替代但需保留的版本
  pasted/                   外部粘贴、会话交接和旧草稿
  superpowers/              工具生成的计划、规格、夹具和历史执行材料
```

不立即大规模搬迁全部旧文档。先通过入口和状态解决权威冲突，再在真实使用或修改时逐步迁移。

## 4. 当前材料迁移规则

- 历史知识图谱导出保留在 `docs/research/ontology/YYYY-MM-DD/`；正式冻结版本使用 `kg/ontology/vX.Y.Z/`，并在 `docs/research/ontology/vX.Y.Z/` 保存同版本说明和验证报告。
- 当前产品契约本体 PPT 放入 `docs/research/presentations/2026-07-27/`。
- 仍写有“产品契约尚未成为完整图谱实体”的旧 PPT 放入 `docs/archive/presentations/2026-07-27/superseded/`。
- `.inspect.ndjson` 属于演示材料 QA 记录，不作为主入口；当前版本放 `qa/`，旧版本随旧 PPT 归档。
- PPT 渲染 PNG 仅在需要保留审查快照时进入 archive；构建缓存继续留在 `tmp/`。

## 5. 去重规则

只有满足以下全部条件，才可删除重复副本：

1. 文件名相同。
2. SHA-256 完全相同。
3. 活跃位置已有副本。
4. 删除不会破坏脚本或测试路径。
5. Git 历史仍可追溯原副本。

`docs/superpowers/specs/done/` 中与 `docs/superpowers/specs/` 完全相同的文件不提供额外历史价值，应删除归档副本。`done/` 中没有活跃副本或内容不同的文件继续保留。

## 6. 过时和错误内容处理

对当前文档：直接修正事实、链接和主张边界，并在必要时更新日期。

对历史证据：不批量重写当时内容。采用以下方式：

- 移入 `archive/` 或保留在历史目录。
- 在入口或目录 README 中标明非权威。
- 对高风险误导内容增加 superseded 说明或替代文档链接。

这样既避免错误继续传播，也不破坏历史证据的原貌。

## 7. 命名与版本

- 当前长期文档使用稳定语义名，如 `project-status.md`，通过 Git 记录版本。
- 冻结证据、本体导出和 PPT 使用日期目录，文件名可保留生成日期。
- 正式 KG 使用语义版本目录；已冻结版本不得原地改写，任何语义变化必须创建新版本并记录迁移说明。
- 不再创建 `final-final-v2` 一类名称。
- 同一天同类材料只保留一个 current 版本，其余进入 `superseded/`。

## 8. 临时文件

`tmp/` 用于：

- PPT 构建和渲染缓存。
- 诊断运行、pytest 调试和一次性分析。
- 未纳入正式证据的实验输出。

长期需要引用的内容必须从 `tmp/` 提升到 `docs/research/`、冻结证据目录或正式数据仓库。不能在论文中引用一个未冻结的 `tmp/` 路径。

## 9. 变更检查清单

每次文档整理至少检查：

```powershell
git status --short --branch
git diff --check
rg -n "superseded|historical|authoritative" docs
```

并确认：

- Markdown 相对链接可解析。
- JSON 可解析，CSV 表头和行数可读取。
- 当前 PPT 与旧 PPT 不并列出现在主入口。
- 统计数字注明生成日期和来源。
- “已实现”“已验证”“可推广”三个层级没有混写。
