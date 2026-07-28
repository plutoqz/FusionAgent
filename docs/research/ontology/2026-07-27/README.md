# 2026-07-27 可执行知识图谱导出

> 状态：current implementation snapshot
> Seed 哈希：`sha256:5581d43164cd21b488971fe38456ed0d6a9f43f86b1e4c9d5d1d1fbf16288fcb`

本目录描述 2026-07-27 代码和 seed 实际可导出的知识图谱，不等同于 research worktree 中仍在推进的七层研究本体 v2。

当前快照包含 15 个本体类、149 个字段定义、27 种关系、232 个静态实体和 497 条实体关系。其中 6 个 `ProductContract` 已成为可遍历、可检索、可持久化到计划的一等图谱实体。

阅读顺序：

1. `FusionAgent_当前进展与知识图谱说明_20260727.md`
2. `ontology_classes.csv`、`ontology_fields.csv`、`ontology_relationships.csv`
3. `FusionAgent_知识图谱实体说明_20260727.md`
4. `entity_nodes.csv`、`entity_relationships.csv`
5. `FusionAgent_知识图谱本体与实体_20260727.json`
6. `校验摘要.txt`

重新导出：

```powershell
python scripts/export_kg_ontology_docs.py
```

导出会覆盖本日期目录中的同名生成文件。更新 seed 后应创建新的日期目录或同步更新脚本默认目录，不能悄悄改写已用于论文或汇报的冻结快照。
