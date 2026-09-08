# Method Selection Development Protocol V1

> 状态：P0 baseline captured；template authoring 与 development 执行未开始
> Protocol ID：`fusionagent.method-selection-development.v1`
> 批准依据：`method-selection-freeze-review.v1`

## Scope

本协议只约束下一版本的 development template authoring、离线生成、oracle、projection、relation 和 preflight 验证。它不授权 Provider、judge、confirmation、selective E2E 或正式实验。

## Frozen bindings

- method-selection protocol：`method-selection-protocol.v1`
- KG release：`fusionagent-kg-v1.0.0`
- development partition：`fusionagent-benchmark-v1-development`, master seed `2026081901`
- historical exclusions：C01-C06、H01-H09 及其语义同构副本
- allowed conditions：fixed_workflow、rules_only、kg_only、llm_only、llm_capability_kg、llm_full_contract_kg

## P0 gate

P0 仅记录 branch、commit、冻结输入身份、依赖环境、输出根不存在性和零调用计数。输出根必须 write-new；任何已有 root、KG identity 漂移或未登记字段均 fail closed。

## Next gates

P1 template authoring contract；P2 development candidate generation；P3 oracle/coverage audit；P4 projection and blind-packet audit。每一阶段保留失败和无效尝试，不以运行结果替换模板或 oracle。

## Accounting

`provider_calls=0`、`judge_calls=0`、`benchmark_instances_generated=0`、`formal_result_roots_created=0`、`confirmation_unsealed=false`、`selective_e2e_selected=false`。
