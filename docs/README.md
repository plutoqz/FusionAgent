# FusionAgent 文档入口

> 状态：当前权威入口
> 更新日期：2026-07-28

本文件是仓库文档的唯一导航入口。项目状态、论文主张、工作优先级或分支角色发生冲突时，先以 `docs/current/` 为准，再回到具体规范和证据文件核对。

## 当前权威文档

| 文档 | 回答的问题 | 权威级别 |
| --- | --- | --- |
| [当前项目状态](current/project-status.md) | 已经完成什么、尚未证明什么、当前边界在哪里 | A0 |
| [论文主张与优先级](current/claims-and-priorities.md) | 期刊和硕士论文下一步先做什么、验收标准是什么 | A0 |
| [仓库与 Worktree](current/repository-worktrees.md) | 每个分支/worktree 承担什么角色、如何提升稳定成果 | A0 |
| [文档治理规则](current/document-governance.md) | 文档如何分类、归档、去重和判定权威性 | A0 |
| [产品契约规范](thesis/product_contract_spec.md) | 产品契约的工程语义、交付状态和图谱映射 | A1 |
| [实验案例矩阵](thesis/experiment_case_matrix.md) | 契约案例、对照维度和实验输入 | A1 |
| [知识图谱实现快照](research/ontology/2026-07-27/README.md) | 本体类、字段、关系、实体及机器可读导出 | A1 |
| [当前组会汇报](research/presentations/2026-07-27/README.md) | 产品契约本体补充版 PPT 及 QA 记录 | A2 |

`research/product-contract` worktree 已提交研究章程、七层本体 v2、五类基线、稳定性协议和最小 end-to-end runtime。这些内容属于活动研究规范，尚未自动成为 `main` 的共享稳定能力。详情见[仓库与 Worktree](current/repository-worktrees.md)。

## 目录分类

| 目录 | 用途 | 默认状态 |
| --- | --- | --- |
| `docs/current/` | 当前状态、主张边界、优先级和治理规则 | 权威 |
| `docs/research/` | 本体导出、实验材料、当前汇报材料 | 当前研究资产 |
| `docs/thesis/` | 论文规范、案例矩阵和章节材料 | 当前或草案，以文件状态为准 |
| `docs/archive/` | 已被替代但需要保留来源链的文档和演示材料 | 历史/非权威 |
| `docs/pasted/` | 外部粘贴、会话交接和旧论文材料 | 历史/非权威 |
| `docs/superpowers/` | 历史计划、规格、测试夹具和执行记录 | 兼容/历史，不能单独定义当前结论 |
| `docs/demo/` | 演示和项目介绍材料 | 辅助 |

## 当前研究口径

当前最稳妥的论文主线是：

> 面向多源地理空间融合的产品契约治理、渐进式交付与可追溯降级恢复。

产品契约已经成为代码和静态知识图谱中的一等实体，但这只证明了机制闭环已经实现。Freeze C 的 C02/C04/C06 能支持 C2、C3、C4 的受限版本，尚不能证明广泛有效、真实 LLM 规划优越性或生产部署能力。

近期执行顺序固定为：

1. 完成仓库与文档治理收口。
2. 完成 P1 独立审计与篡改失败测试。
3. 完成 P2 三次干净稳定性重跑。
4. 完成最小基线/消融和多 AOI 实验。
5. 自动生成论文表格、时间线和证据索引。

详细验收条件见[论文主张与优先级](current/claims-and-priorities.md)。

## 权威性判定

出现冲突时按以下顺序处理：

1. `docs/current/` 中标记为 A0 的当前文档。
2. 当前分支上明确标记为 active/authoritative 的规范和协议。
3. 代码、测试、机器可读 manifest 与冻结证据。
4. `archive/`、`pasted/`、`superpowers/**/done/` 中的历史材料。

历史文档只说明“当时如何判断”，不能覆盖当前状态。任何百分比、成熟度或论文结论都必须注明时间、证据范围和是否经过重复实验。
