# FusionAgent 知识图谱版本

本目录保存运行时可消费的版本化知识图谱发布包。

- 每个 `vX.Y.Z/` 目录一经标记为 `frozen` 后不得原地修改。
- `schema.json` 定义七层本体、关系、约束和 competency questions。
- `entities.json` 保存静态实体、工作流与类型转换图。
- `policies.json` 保存会改变任务编译、规划、质量验收和恢复行为的声明性知识。
- `release.json` 保存发布身份、文件哈希和规范化语义哈希。
- 运行产生的案例、质量结果和经验快照不写回冻结包，只能引用 `release_id` 和 `semantic_hash`。

当前默认版本由 `kg.knowledge_release.DEFAULT_RELEASE_DIR` 指定。

