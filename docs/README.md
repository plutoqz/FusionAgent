# FusionAgent 文档入口

> 状态：当前权威入口
> 更新日期：2026-08-04

本文件是仓库文档的唯一导航入口。项目状态、论文主张、工作优先级或分支角色发生冲突时，先以 `docs/current/` 为准，再回到具体规范和证据文件核对。

## 当前权威文档

| 文档 | 回答的问题 | 权威级别 |
| --- | --- | --- |
| [当前项目状态](current/project-status.md) | 已经完成什么、尚未证明什么、当前边界在哪里 | A0 |
| [研究章程](current/research-charter.md) | 研究主体、目标、研究问题、创新点和主张边界是什么 | A0 |
| [论文主张与优先级](current/claims-and-priorities.md) | 期刊和硕士论文下一步先做什么、验收标准是什么 | A0 |
| [研究分支与 KG v1 归并审计](current/research-branch-kg-v1-merge-audit.md) | 研究资产分类、KG 对齐缺口、归并约束和讨论闸门 | A0 |
| [仓库与 Worktree](current/repository-worktrees.md) | 每个分支/worktree 承担什么角色、如何提升稳定成果 | A0 |
| [文档治理规则](current/document-governance.md) | 文档如何分类、归档、去重和判定权威性 | A0 |
| [产品契约规范](thesis/product_contract_spec.md) | 产品契约的工程语义、交付状态和图谱映射 | A1 |
| [实验案例矩阵](thesis/experiment_case_matrix.md) | 契约案例、对照维度和实验输入 | A1 |
| [KG v1 冻结发布](../kg/ontology/v1.0.0/README.md) | 当前机器真源、冻结发布身份和独立校验入口 | A1 |
| [知识图谱本体层](research/ontology/ontology-layer.md) | 七层、71 个类、42 类关系、属性、约束和 CQ | A1 |
| [知识图谱实体层](research/ontology/entity-layer.md) | 241 个静态对象、政策记录及运行实例边界 | A1 |
| [知识片段迁移台账](research/ontology/knowledge-fragment-ledger.md) | 分散知识的归属、迁移状态和验证方法 | A1 |
| [历史知识图谱快照](research/ontology/2026-07-27/README.md) | P0 冻结前的导出快照，仅用于追溯 | A3 |
| [当前组会汇报](research/presentations/2026-07-27/README.md) | 产品契约本体补充版 PPT 及 QA 记录 | A2 |

`research/product-contract` worktree 已包含五类规划模式、真实 LLM 实验接口、结构化评分、重复实验审计和最小端到端运行时等开发资产。与当前 KG v1 的归并审计已经完成，结论是禁止整分支合并并按责任边界选择性提升；在适配 KG v1 并形成冻结证据前，其中内容不属于共享稳定规范或正式实验结论。详情见[研究分支与 KG v1 归并审计](current/research-branch-kg-v1-merge-audit.md)。

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

当前冻结的研究主线是：

> 面向灾害应急多源地理空间融合的契约化知识图谱与受约束规划方法。

知识图谱是研究主体；产品契约、质量门、降级恢复和证据链是图谱驱动规划与治理的方法组成。P0-K1–K5 已完成：KG-only 行为扰动、fail-closed、源重新材料化、真实 Neo4j parity 及最终 clean/tamper 发布验收均已有定向证据。现有可执行图谱和 Freeze C 仍不能证明真实 LLM 规划优越性、广泛有效性或生产部署能力。

当前工作顺序调整为（尚不冻结为下一里程碑）：

1. 已完成 P0-R、K1–K5。
2. 已完成 P1 独立审计、P2 三次稳定性重跑、P3-G 最小治理消融和 P4-G 最小多 AOI 治理外部有效性切片。
3. P3-P 真实规划对照和 P4-P 规划外部有效性尚未完成；研究分支与 KG v1 的归并审计已经完成，当前停在讨论闸门，待确认案例、基线、单源质量政策、真实 LLM 协议和选择性端到端范围后再冻结实施批次。

详细验收条件见[论文主张与优先级](current/claims-and-priorities.md)。

## 权威性判定

出现冲突时按以下顺序处理：

1. `docs/current/` 中标记为 A0 的当前文档。
2. 当前分支上明确标记为 active/authoritative 的规范和协议。
3. 代码、测试、机器可读 manifest 与冻结证据。
4. `archive/`、`pasted/`、`superpowers/**/done/` 中的历史材料。

历史文档只说明“当时如何判断”，不能覆盖当前状态。任何百分比、成熟度或论文结论都必须注明时间、证据范围和是否经过重复实验。
