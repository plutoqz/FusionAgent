# Superpowers Specs 目录说明

> 状态：兼容与历史集合，非当前研究总入口
> 更新日期：2026-07-28

本目录混合保存仍被脚本/测试读取的兼容规格、旧 evidence freeze、历史能力清单和阶段性研究材料。文件存在于 `specs/` 不代表它仍能定义当前论文主张。

当前项目状态、论文主张和优先级以以下文档为准：

- [`docs/current/project-status.md`](../../current/project-status.md)
- [`docs/current/claims-and-priorities.md`](../../current/claims-and-priorities.md)
- [`docs/README.md`](../../README.md)

## 目录规则

- `specs/`：保留仍被代码、测试或复现流程按路径消费的文件，以及尚未迁移的历史材料。
- `specs/done/`：只保留没有活跃副本或内容确实不同的历史快照。
- `specs/` 与 `specs/done/` 中同名且 SHA-256 完全相同的副本不重复保存。
- 新的论文方向、主张账本或长期执行计划不得只写入本目录。
- 历史 freeze 只证明对应日期、commit、输入和协议下的状态，不自动代表当前分支。

当某个旧规格仍被自动化消费时，应在代码或测试中保留明确引用；当依赖解除后，再按 `docs/current/document-governance.md` 迁移或归档。
