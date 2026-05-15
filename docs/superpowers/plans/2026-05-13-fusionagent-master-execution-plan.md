# FusionAgent 唯一活跃主计划

**状态**: Active  
**生效日期**: 2026-05-13  
**执行规则**: 从本文件生效起，`docs/superpowers/plans/` 根目录只允许保留这一份活跃计划。后续新增 backlog 必须先并入本文件，再执行；`docs/superpowers/plans/done/` 中的文档只保留历史审计价值，不再作为执行入口。

## 1. 执行宪章

本文件的目标不是重新发散出新的子计划，而是把当前仓库里仍然需要继续完成的工作收敛成一条可持续执行到结束的主线。

执行时必须遵守以下规则：

- 不再新增第二份活跃计划文档。
- `done/` 中的旧计划不能再被当作当前待办清单直接使用；如需吸收内容，只能回写到本文件。
- `docs/superpowers/specs/done/` 可以保留历史快照，但任何被测试、脚本、README、runbook、论文证据链直接消费的规范/证据文件，必须回到 live 路径，而不是继续停留在 `done/`。
- 前端证据面增长、图后端迁移试验、`trajectory-to-road` 可执行化不进入当前执行阶段。

## 2. 已完成基线

以下内容视为当前稳定基线，除非出现新的失败证据，否则不回退为“未完成”：

- 稳定主题边界仍然是 `building`、`road`、`water`、bounded `poi`。
- 共享运行骨架仍然是 `planner -> validator -> executor -> healing/replan -> writeback`。
- 共享证据契约仍然是 `run.json`、`plan.json`、`validation.json`、`audit.jsonl` 与 artifact bundle。
- Phase 1 与 Phase 2 已经关闭；此前复核记录为：
  - focused Phase 2 slice: `57 passed in 2.46s`
  - broader integration/runtime slice: `121 passed, 10 warnings in 13.20s`
- 代码侧已经存在并通过聚焦测试的能力，不应再按“从零实现”规划：
  - `services/run_registry_service.py`
  - `services/operator_read_model_service.py`
  - `services/artifact_preview_service.py`
  - `schemas/scenario_manifest.py` 中的 `capability_checks`
  - `scripts/scenario_eval_harness.py`
  - `services/source_profile_service.py`
  - `services/tile_partition_service.py`
  - `services/tiled_building_runtime_service.py`
  - `fusion_algorithms/` 与 `adapters/fusioncode_*`

### 2026-05-13 现状诊断

本主计划写入时，仓库的主要真实缺口不是“代码骨架不存在”，而是“活跃规范/证据文件被整体归档后，校验入口失效，且能力主张与文档状态不一致”。已确认的直接证据如下：

- `python scripts/run_no_ui_maturity_check.py` 失败，原因是 `docs/superpowers/specs/` 下多份必需 live 文件缺失。
- `python -m pytest -q tests/test_scenario_manifest_service.py tests/test_scenario_eval_harness.py tests/test_run_registry_service.py tests/test_operator_read_model_service.py tests/test_artifact_preview_service.py tests/test_no_ui_maturity_check.py` 的结果是 `34 passed, 1 failed`，唯一失败项是缺失 `docs/superpowers/specs/2026-04-21-scenario-eval-manifest.json`。
- `python -m pytest -q tests/test_source_profile_service.py tests/test_tile_partition_service.py tests/test_tiled_building_runtime_service.py tests/test_raster_cli.py` 的结果是 `10 passed`。
- `python -m pytest -q tests/test_fusioncode_inventory_contract.py tests/test_fusioncode_contracts.py tests/test_fusioncode_building_raster.py tests/test_fusioncode_building_v8_decomposition.py tests/test_fusioncode_linear_water_road.py tests/test_fusioncode_poi.py tests/test_fusioncode_executor_handlers.py tests/test_fusioncode_kg_metadata.py` 的结果是 `24 passed`。

结论：后续工作应优先做 live 规范恢复、证据刷新、能力主张收口与论文资产闭环，而不是盲目重写已经存在的实现。

## 3. 历史计划吸收映射

| 历史计划 | 在本主计划中的归属 |
| --- | --- |
| `2026-05-12-fusionagent-master-execution-plan.md` | 本文件整体吸收，旧文件仅保留历史记录 |
| `2026-04-21-no-ui-mature-agent-plan.md` | Phase A / Phase B |
| `2026-04-21-scenario-regression-set-plan.md` | Phase B |
| `2026-04-23-system-next-improvements.md` | 已完成基线 |
| `2026-05-06-fusionagent-agent-capability-update-roadmap.md` | 已完成基线 |
| `2026-05-09-kg-closure-and-graph-backend-roadmap.md` | 已完成基线 |
| `2026-04-27-benin-building-runtime-preparation.md` | Phase C |
| `2026-04-29-fusioncode-algorithm-library-kg-integration.md` | Phase D |
| `2026-05-06-fusionagent-thesis-research-design-roadmap.md` | Phase E |

## 4. Phase A: live 规范/证据路径恢复

### 目标

把当前误归档到 `docs/superpowers/specs/done/` 的活跃规范、评测清单、freeze 文件与 capability 文档恢复为 live 可消费状态，使测试、脚本、README、runbook、论文证据链重新使用统一根路径。

### 涉及范围

- `docs/superpowers/specs/`
- `docs/superpowers/specs/done/`
- `scripts/run_no_ui_maturity_check.py`
- `scripts/freeze_paper_evidence.py`
- 所有直接读取上述 live spec 路径的测试

### 执行清单

- [x] A1. 明确 `specs` 的 live/archive 规则，并写成一个短说明文件：
  - `docs/superpowers/specs/README.md` 或 `docs/superpowers/specs/active-index.md`
  - 说明哪些文件是当前执行链必需 live 文件，哪些文件只是历史快照
- [x] A2. 从 `docs/superpowers/specs/done/` 非破坏性恢复以下 live 文件集合：
  - no-ui maturity:
    - `2026-04-21-no-ui-maturity-target.md`
    - `2026-04-21-no-ui-maturity-gap-ledger.md`
    - `2026-04-21-no-ui-maturity-evidence-freeze.json`
    - `2026-04-21-no-ui-maturity-evidence-freeze.md`
    - `2026-04-21-operator-read-model-contract.md`
  - scenario:
    - `2026-04-21-scenario-eval-manifest.json`
    - `2026-04-21-scenario-regression-set-design.md`
    - `2026-04-21-scenario-trigger-proof.md`
    - `2026-04-21-scenario-evidence-freeze.json`
    - `2026-04-21-scenario-evidence-freeze.md`
  - paper evidence:
    - `2026-04-21-paper-experiment-matrix.json`
    - `2026-04-21-paper-evidence-freeze.json`
    - `2026-04-21-paper-evidence-freeze.md`
  - capability/thesis baseline:
    - `2026-05-06-capability-consolidation-review.md`
    - `2026-05-06-capability-inventory.md`
    - `2026-05-06-capability-matrix.json`
    - `2026-05-06-consolidation-backlog.md`
    - `2026-05-06-next-execution-sequence.md`
    - `2026-05-06-redundancy-and-drift-ledger.md`
    - `2026-05-06-related-work-gap-matrix.json`
    - `2026-05-06-related-work-gap-matrix.md`
  - KG/paper baseline evidence:
    - `2026-04-20-evaluation-contract-claim-lock.md`
    - `2026-04-20-evidence-ledger.md`
    - `2026-05-09-kg-closure-gates.md`
    - `2026-05-10-kg-gates-evidence-summary.md`
- [x] A3. 检查并修正所有仍然硬编码为旧 live 路径、但内容已经不再对应的脚本/测试；优先选择“恢复 live 文件”而不是“把脚本改去读 `done/`”。
- [x] A4. 对恢复出的 live 文件做内容核对，确认不是落后的历史版本；如 `done/` 中的快照已经明显过时，则直接在 live 路径重写，不复制旧内容。
- [x] A5. 形成一个最小“当前活跃 spec 索引”，让后续执行知道哪些文档继续参与 Phase B-E。

### 验证

- `python scripts/run_no_ui_maturity_check.py`
- `python -m pytest -q tests/test_scenario_manifest_service.py tests/test_related_work_gap_matrix.py tests/test_capability_inventory_matrix.py tests/test_consolidation_backlog.py tests/test_no_ui_maturity_check.py`

### 完成判定

- 上述命令全部通过。
- `docs/superpowers/specs/` 根目录重新具备当前执行链必需的 live 文件。
- `done/` 仅保留历史快照，不再承担当前脚本入口职责。

### 反模式防护

- 不要把当前仍在使用的 manifest/freeze 继续留在 `done/`。
- 不要在 root 与 `done/` 并行维护两份“都宣称是当前版本”的文档。
- 不要为了省事把测试统一改成读 `done/`，从而让 archive 重新变成活跃入口。

## 5. Phase B: no-ui operator / scenario / maturity 收口

### 目标

在 Phase A 恢复 live 路径之后，把 no-ui operator 面、scenario capability regression、trigger proof 与 maturity evidence 刷新到当前代码基线，形成可持续复核的无界面运行时闭环。

### 涉及范围

- `docs/no-ui-agent-operations.md`
- `docs/superpowers/specs/2026-04-21-*`
- `services/run_registry_service.py`
- `services/operator_read_model_service.py`
- `services/artifact_preview_service.py`
- `services/scenario_trigger_service.py`
- `services/scenario_registry_service.py`
- `scripts/scenario_eval_harness.py`
- `scripts/freeze_scenario_evidence.py`
- `scripts/freeze_no_ui_maturity_evidence.py`
- `scripts/run_no_ui_maturity_check.py`

### 执行清单

- [x] B1. 把 live `scenario-eval-manifest` 与当前 capability 语义对齐：
  - 保留 building / road / water / bounded poi 的 5-case 回归集合
  - water / poi 继续保持 planner-level / bounded claim，不得借机升级为未证实执行能力
  - capability checks 继续以 `required_job_types`、`required_workflow_steps`、`require_aoi_resolved`、`require_task_inputs_resolved`、`require_source_coverage` 为准
- [x] B2. 重新运行 scenario harness，刷新：
  - `tmp/eval/scenario-harness-summary.json`
  - `docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.json`
  - `docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.md`
- [x] B3. 复核并刷新 `2026-04-21-scenario-trigger-proof.md`，确认本地 inbox 触发链与当前 `scenario_registry`、idempotency、failed-event 处理仍一致。
- [x] B4. 用当前实际 API/服务收口 operator contract：
  - run listing
  - runtime summary
  - run inspection
  - run compare
  - scenario listing / detail
  - artifact preview
  并同步更新 `docs/no-ui-agent-operations.md` 与 `2026-04-21-operator-read-model-contract.md`
- [x] B5. 重新生成 no-ui maturity freeze：
  - `2026-04-21-no-ui-maturity-evidence-freeze.json`
  - `2026-04-21-no-ui-maturity-evidence-freeze.md`
- [x] B5.a 2026-05-14 CI 回归修复：
  - GitHub `ci` 失败定位到 `mock-inmemory-tests`
  - 根因确认为 scenario building case 为保留 `aoi_resolved` 证据而放宽 AOI 解析触发范围，误伤 direct bbox run
  - 已引入 `force_aoi_resolution` 显式开关，仅对需要 `require_aoi_resolved` 的 scenario+bbox 组合启用，收回全局副作用
  - 本地验证结果：
    - focused AOI slice: `3 passed`
    - CI 对应 mock/in-memory slice: `89 passed, 8 warnings`
    - scenario/integration 扩展 slice: `22 passed, 2 warnings`
    - `python scripts/run_no_ui_maturity_check.py`: `passed=true`, `static_check_passed=true`
- [x] B6. 在 no-ui maturity gate 真实通过之前，不改 README 定位；若 gate 全通过，再决定是否补充 maturity marker 并清理 prototype-only 残余表述。
  - 2026-05-14：README 中英文入口已补充 no-ui maturity marker，后续以 `python scripts/run_no_ui_maturity_check.py --require-readme-repositioning` 作为定位切换验收门槛。

### 验证

- `python -m pytest -q tests/test_scenario_manifest_service.py tests/test_scenario_eval_harness.py tests/test_run_registry_service.py tests/test_operator_read_model_service.py tests/test_artifact_preview_service.py tests/test_no_ui_maturity_check.py`
- `python -m pytest -q tests/test_api_operator_read_models.py tests/test_api_scenario_registry.py tests/test_api_v2_integration.py`
- `python scripts/run_no_ui_maturity_check.py`
- 如准备切换 README 定位，再运行：`python scripts/run_no_ui_maturity_check.py --require-readme-repositioning`

### 完成判定

- scenario capability regression、trigger proof、operator read surface、maturity freeze 都与当前实现同步。
- no-ui maturity check 至少达到静态通过；只有在 README 真正更新后才追求 repositioning gate 通过。

### 反模式防护

- 不要把“文档存在”误当成“freeze 已刷新”。
- 不要让 `partial` 掩盖缺失 capability evidence 的 case。
- 不要用前端 workbench 替代 no-ui operator contract 的闭环证明。

## 6. Phase C: 面向大规模、多源建筑物数据融合能力的收口

### 目标

把旧“Benin scale preparation”重写为通用的大规模、多源建筑物数据融合能力主线。Benin 只作为验证数据来源之一，不再作为国家特化叙事中心。

### 涉及范围

- `services/source_profile_service.py`
- `services/tile_partition_service.py`
- `services/tiled_building_runtime_service.py`
- `services/agent_run_service.py`
- `services/source_asset_service.py`
- `services/input_acquisition_service.py`
- `scripts/profile_benin_sources.py`
- `scripts/run_benin_multisource_building_fusion.py`
- `docs/fusioncode-algorithm-library.md`
- `docs/v2-operations.md`
- `README.md`
- `README.en.md`
- `docs/superpowers/specs/2026-05-06-capability-inventory.md`
- `docs/superpowers/specs/2026-05-06-capability-matrix.json`

### 执行清单

- [x] C1. 先锁定“当前能稳定声称什么”：
  - 哪些 source-set 形式已稳定支持
  - tiled execution 的输入/输出契约是什么
  - clip cache 与 stitch 结果的证据边界是什么
  - raster presence / raster height 分别处于什么 claim 等级
  - 2026-05-14：已在 `README`、`docs/v2-operations.md`、`docs/fusioncode-algorithm-library.md` 与 capability inventory 中锁定共享 runtime 的 large-AOI `OSM + single-reference` tiled building 路径、tile manifest / stitch 证据面，以及 multi-source+raster 仍属于 research utility 的边界。
- [x] C2. 清理所有 Benin 特化措辞，把阶段目标改写为：
  - 大 AOI building runtime scale-up
  - 多源 building source-set 输入建模
  - tiled execution / cache / stitch
  - 大规模 building benchmarking 与 evidence freeze
  - 2026-05-14：高层 README / operations / algorithm-library 口径已切到通用规模化叙事；残余 Benin 特化脚本名与历史文档引用继续保留到后续收口。
  - 2026-05-15：`docs/v2-operations.md`、`docs/fusioncode-algorithm-library.md`、capability inventory / matrix 已统一声明“Benin 只作为校验数据集示例”，脚本名保留但不再承担国家特化能力叙事。
- [x] C3. 对齐“代码已实现”和“文档仍然保守”的冲突：
  - 如果多源 building vector 路径已可稳定运行，提升其 claim_state
  - 如果 raster height 仍缺少稳定证据，则保持可选/有界，不强行升级
  - 保证 `docs/fusioncode-algorithm-library.md`、capability inventory、README、operations 的说法一致
  - 2026-05-15：live capability inventory / matrix 新增 `building.scale_validation_cleanup_rules`，并继续把 multi-source / raster building 维持在 `research_utility`；shared runtime 与 validation utility 的边界已在 operations、algorithm library、parity ledger 中对齐。
- [x] C4. 补齐通用规模化证据，而不是只保留脚本存在：
  - source profile 产物
  - tile manifest
  - tiled runtime summary
  - stitch 后 artifact 合法性
  - inspection / operator 可读证据
  - 2026-05-14：已新增 `tests/test_benchmark_tiled_building.py` 与扩展 `tests/test_run_benin_multisource_building_fusion.py`，把 `source_profile_snapshot.json`、`tile_manifest.json`、`selected_sources.json`、`timing.json`、`benchmark_summary.md` 等规模化验证产物纳入回归护栏；真实 inspection/operator freeze 级证据仍待后续补齐。
  - 2026-05-15：已恢复 `2026-04-08-benchmark-followup-summary.md` 与 `2026-05-12-building-gitega-micro-msft-neo4j-baseline-8012.json` 等被 live 文档引用的基准 spec 资产到 `docs/superpowers/specs/`，修复 live 账本悬空引用。
  - 2026-05-15：`scripts/benchmark_tiled_building.py` 与 `scripts/run_benin_multisource_building_fusion.py` 现已稳定产出 `inspection_summary.json`，把 `source_profile_snapshot.json`、`tile_manifest.json`、`selected_sources.json`、`timing.json`、`benchmark_summary.md` 与 stitch 后 `artifact_validity` 收敛成 operator-readable 规模化摘要；对应测试、operations wording 与 capability inventory 已同步收口。
- [x] C5. 明确“Benin national script”在文档中的角色：
  - 可以作为规模化验证样例
  - 不能再作为“仅 Benin 专用实验脚本”的孤岛能力叙事
  - 2026-05-14：`scripts/run_benin_multisource_building_fusion.py` 与相关文档已改写为“大规模多源 building 验证样例”，并明确 Benin 只是当前仓库示例数据集。

### 验证

- `python -m pytest -q tests/test_source_profile_service.py tests/test_tile_partition_service.py tests/test_tiled_building_runtime_service.py tests/test_raster_cli.py`
- `python -m pytest -q tests/test_tiled_multisource_building_runtime_service.py tests/test_run_benin_multisource_building_fusion.py`
- 如需要补充运行时闭环，再追加与 `agent_run_service` 相关的 building tiled slice 聚焦测试

### 完成判定

- 文档已不再把该阶段描述为 Benin 特化能力。
- 至少一个大规模、多源 building 路径具备测试、运行契约、证据、操作文档四位一体闭环。
- 可选 raster/height 语义的边界被明确标注，而不是被含混地包装成“全支持”。

### 反模式防护

- 不要把国家数据集名字写成能力本体。
- 不要在没有共享证据契约的情况下把研究脚本直接升级为稳定 runtime 主张。
- 不要为了追求“大规模”而绕过已有 validator / audit / inspection 边界。

## 7. Phase D: `fusioncode` 全量算法库集成收口

### 目标

把 `fusioncode` 全量算法库集成从“代码已经有不少 wrapper 和 KG 节点”推进到“范围清晰、证据清晰、claim_state 清晰”的正式收口状态，并纳入主计划而不是继续挂起。

### 涉及范围

- `fusion_algorithms/`
- `adapters/`
- `agent/executor.py`
- `agent/retriever.py`
- `agent/validator.py`
- `kg/seed.py`
- `kg/source_catalog.py`
- `kg/bootstrap/neo4j_bootstrap.cypher`
- `docs/fusioncode-algorithm-library.md`
- `docs/v2-operations.md`
- `tests/test_fusioncode_*`
- `tests/test_planner_context.py`
- `tests/test_kg_repository_enhancements.py`

### 执行清单

- [x] D1. 建立一份 parity ledger，逐项对齐外部 `fusioncode` 能力与本仓库内部落点：
  - building primitives
  - road fusion
  - water line fusion
  - water polygon fusion
  - poi fusion
  - conflict / quality metrics
  - 2026-05-14：已新增 live `docs/superpowers/specs/2026-05-14-fusioncode-parity-ledger.md`，把 building / road / water / poi / conflict-quality 族分别映射到 adapter、KG、parameter spec、executor、retriever 与测试证据。
- [x] D2. 对每个能力族检查 6 个要素是否齐全：
  - wrapper/primitive
  - KG algorithm node
  - parameter specs
  - executor handler
  - planner/retriever 可见性
  - 对应测试
  - 2026-05-14：parity ledger 已显式记录六要素齐备情况；当前主要缺口已收敛到 shared-runtime smoke/inspection evidence 与最终 wording 全量统一，而不是代码挂点缺失。
- [x] D3. 解决当前文档与实现状态冲突：
  - road / water / bounded poi 已有实现与测试的，继续保持或升级为明确支持
  - building decomposed multi-source 若经 Phase C 证据确认可用，则从 `reservation_only` 升级到合适级别
  - 仍无足够运行证据的子能力继续显式标为 bounded / optional / reservation_only
  - 2026-05-14：road / water / bounded poi 已稳定保持 `runtime_supported` / `bounded_supported`；building multi-source、presence raster、height raster 已从早期“仅 reserved seam”口径收敛为 `research_utility`，并在 `docs/fusioncode-algorithm-library.md`、capability inventory 与 parity ledger 中保持一致。
- [x] D4. 增加跨主题 smoke/inspection 证据，证明这些 KG 算法节点不仅“存在于 seed”，还能够被 planner/executor 选中并产生可审计输出。
  - 2026-05-15：已为 task-driven smoke 增加 `preferred_pattern_id` 受控入口，并把实际执行得到的 `selected_pattern_id` 写回 plan / inspection / `kg_path_trace`。
  - 2026-05-15：fresh live smoke 已生成并 checked in：
    - `runs/smoke-road-gilgit-city-fusioncode-inspection-8012.json` -> `wp.road.fusioncode.segment_topology.v1` / `algo.fusion.road.segment_match_topology.v1`
    - `runs/smoke-water-nairobi-fusioncode-inspection-8012.json` -> `wp.water.fusioncode.line_and_polygon.v1` / `algo.fusion.water.polygon_priority_merge.v1`
    - `runs/smoke-poi-nairobi-fusioncode-inspection-8012.json` -> `wp.poi.fusioncode.geohash_priority.v1` / `algo.fusion.poi.geohash_neighbor_match.v1`
  - 结论：road / water / bounded poi 现在不只是“FusionCode candidate 可见”，而是已具备 planner/executor 真实选中后的 run-level 审计证据。
- [x] D5. 更新算法库文档与 operations 文档，禁止继续把“代码已接入、文档却说 deferred”长期并存。
  - 2026-05-15：`docs/fusioncode-algorithm-library.md`、`docs/v2-operations.md`、`docs/superpowers/specs/2026-05-06-capability-inventory.md`、`docs/superpowers/specs/2026-05-14-fusioncode-parity-ledger.md` 已统一 wording，明确 shared runtime claim 与 `research_utility` building flows 的边界。

### 验证

- `python -m pytest -q tests/test_fusioncode_inventory_contract.py tests/test_fusioncode_contracts.py tests/test_fusioncode_building_raster.py tests/test_fusioncode_building_v8_decomposition.py tests/test_fusioncode_linear_water_road.py tests/test_fusioncode_poi.py tests/test_fusioncode_executor_handlers.py tests/test_fusioncode_kg_metadata.py`
- `python -m pytest -q tests/test_planner_context.py tests/test_kg_repository_enhancements.py`
- 如补充 smoke evidence，再运行对应的 bounded live/integration slice

### 完成判定

- `fusioncode` 各主题能力的 claim_state 不再含混。
- 外部算法库存量、KG 节点、执行处理器与测试矩阵形成一一对应或有据可查的 defer 理由。
- 文档不再把已落地实现长期描述为“未来能力”。

### 反模式防护

- 不要把 `fusioncode.algorithm_adapter.run_full_pipeline()` 重新包装成单一黑盒主算法。
- 不要因为 unit tests 已过，就自动宣称所有外部能力都已成为稳定 runtime 主张。
- 不要让 building 大规模能力与 `fusioncode` 全库 claim 混成一个模糊大口号。

## 8. Phase E: 论文研究资产闭环

### 目标

在 Phase A-D 收口后的真实能力边界之上，整理出可答辩、可复核、不会超出 runtime 证据的论文资产集合。

### 涉及范围

- `docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json`
- `docs/superpowers/specs/2026-04-21-paper-evidence-freeze.json`
- `docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md`
- `docs/superpowers/specs/2026-05-06-capability-inventory.md`
- `docs/superpowers/specs/2026-05-06-related-work-gap-matrix.json`
- `docs/superpowers/specs/2026-05-06-related-work-gap-matrix.md`
- 新建 thesis docs，建议统一使用 `2026-05-13-` 前缀

### 建议新增文档

- `docs/superpowers/specs/2026-05-13-thesis-research-spec.md`
- `docs/superpowers/specs/2026-05-13-thesis-claims-ledger.md`
- `docs/superpowers/specs/2026-05-13-thesis-related-work-matrix.md`
- `docs/superpowers/specs/2026-05-13-thesis-related-work-matrix.json`
- `docs/superpowers/specs/2026-05-13-thesis-outline-and-timeline.md`
- `docs/superpowers/specs/2026-05-13-thesis-capability-handshake.md`

### 执行清单

- [x] E1. 写 thesis research spec，锁定：
  - 研究对象
  - RQ1 / RQ2 / RQ3
  - 主 claim 与非主 claim
  - 明确不把前端、运维增强、trajectory seam 写成主创新点
- [x] E2. 写 claims ledger，把每个 claim 映射到当前 live evidence、测试、freeze、run artifact，而不是映射到未来计划。
- [x] E3. 以 `2026-04-21-paper-experiment-matrix.json` 为 canonical matrix，按 Phase B-D 的最终能力边界更新 baseline、ablation、metrics、case pool。
- [x] E4. 基于 `2026-05-06-related-work-gap-matrix.*` 产出论文可直接写作的 related-work matrix 与 narrative，明确：
  - closest overlap
  - our difference
  - borrowed idea
  - 不能类比的边界
- [x] E5. 产出 thesis outline / timeline，确保实验顺序、论文章节、能力边界和 freeze 节奏一致。
- [x] E6. 产出 capability-handshake 文档，明确：
  - thesis plan 负责回答“为什么值得证明、如何证明”
  - runtime/capability plan 负责回答“什么已经能声称、什么必须继续收口”
  - 论文叙事不得超出 Phase A-D 的最终能力主张
  - 2026-05-15：已新增 `2026-05-13-thesis-research-spec.md`、`2026-05-13-thesis-claims-ledger.md`、`2026-05-13-thesis-related-work-matrix.*`、`2026-05-13-thesis-outline-and-timeline.md`、`2026-05-13-thesis-capability-handshake.md`，并把 canonical paper matrix 补充为带 `research_questions`、`baseline_catalog`、`ablation_catalog`、`metric_catalog`、`case_pool_policy` 的 live 研究入口。

### 验证

- 继续保持以下现有文档测试通过：
  - `python -m pytest -q tests/test_related_work_gap_matrix.py tests/test_capability_inventory_matrix.py`
- 为新 thesis docs 增加轻量守护测试，建议新增：
  - `tests/test_thesis_research_spec.py`
  - `tests/test_thesis_related_work_matrix.py`
  - `tests/test_thesis_outline_timeline.py`
  - `tests/test_plan_handshake.py`
- 更新后重新运行 `python scripts/freeze_paper_evidence.py` 的对应验证链，确保 paper freeze 可以从 live matrix 正常生成。

### 完成判定

- thesis 资产已经从 runtime 证据中长出来，而不是独立悬空。
- 所有论文主张都能回链到当前 live docs、tests、freeze 与 run artifacts。
- 论文资产不再依赖 `done/` 目录中的历史计划才能读懂。

### 反模式防护

- 不要拿“计划中未来会做”替代“当前已有证据”。
- 不要为了论文叙事好看而扩大 runtime 声称。
- 不要把 Benin 规模验证写成国家专题本体，而应写成规模化验证样例。

## 9. Final Phase: 总验收与归档卫生

### 目标

在所有活跃阶段完成后，做一次统一验收，确保仓库只保留一条活跃计划线，且 live docs / archive / tests / README 的边界一致。

### 执行清单

- [x] F1. 运行 Phase A-E 的全部聚焦验证命令。
- [x] F2. 刷新所有 live freeze 文档，确认路径不再引用 `done/` 作为活跃入口。
- [x] F3. 核对 `README.md`、`README.en.md`、`docs/v2-operations.md`、`docs/fusioncode-algorithm-library.md`、capability inventory 的术语一致性。
- [x] F4. 检查 `docs/superpowers/plans/` 根目录只剩本文件一份活跃计划。
- [x] F5. 检查 `docs/superpowers/plans/done/` 和 `docs/superpowers/specs/done/` 中的历史文档不再承担当前执行语义。

### 推荐最终验证命令

- `python scripts/run_no_ui_maturity_check.py`
- `python -m pytest -q tests/test_scenario_manifest_service.py tests/test_scenario_eval_harness.py tests/test_run_registry_service.py tests/test_operator_read_model_service.py tests/test_artifact_preview_service.py tests/test_no_ui_maturity_check.py`
- `python -m pytest -q tests/test_source_profile_service.py tests/test_tile_partition_service.py tests/test_tiled_building_runtime_service.py tests/test_raster_cli.py tests/test_tiled_multisource_building_runtime_service.py tests/test_run_benin_multisource_building_fusion.py`
- `python -m pytest -q tests/test_fusioncode_inventory_contract.py tests/test_fusioncode_contracts.py tests/test_fusioncode_building_raster.py tests/test_fusioncode_building_v8_decomposition.py tests/test_fusioncode_linear_water_road.py tests/test_fusioncode_poi.py tests/test_fusioncode_executor_handlers.py tests/test_fusioncode_kg_metadata.py`
- `python -m pytest -q tests/test_related_work_gap_matrix.py tests/test_capability_inventory_matrix.py`

### 2026-05-15 Final Phase closure note

- 已 fresh 运行 `python scripts/run_no_ui_maturity_check.py`，结果 `passed: true`。
- 已 fresh 运行 Final Phase 推荐的 Phase A-E 聚焦测试命令，结果分别为 `36 passed`、`17 passed, 8 warnings`、`24 passed`、`22 passed`。
- 已 fresh 刷新 `paper / scenario / no-ui maturity` 三条 live freeze。
- 已把 live specs 真正恢复到根目录并补充索引：`2026-04-07-real-data-eval-manifest.json`、`2026-04-07-fusion-agent-v2-design.md`、`2026-04-10-thesis-aligned-agent-design.md`、`2026-04-16-building-micro-alignment-result.json`、`2026-04-17-agentic-any-region-fusion-design.md`、`2026-04-23-system-next-improvement-review.md`。
- 已新增守护测试，确保 live paper evidence chain 不再依赖 `docs/superpowers/plans/done/`，且 live spec 引用真实落在 live 根目录。

### 完成判定

- 本计划成为唯一活跃执行入口。
- active spec / evidence / thesis docs 均回到明确的 live 路径。
- 大规模多源 building 能力与 `fusioncode` 全量算法库集成都被纳入正式闭环，而不是继续悬挂为“以后再说”。

## 10. 明确搁置范围

以下内容本轮不进入执行阶段，只保留边界说明：

- 前端证据面增长 / workbench 扩展
- 图后端迁移试验（如 NebulaGraph、AGE、GDB、PolarDB Graph 等）
- `trajectory-to-road` 可执行化路径

### 重新进入计划的条件

- 前端：只有在 no-ui maturity、operator surface、论文证据链都稳定后，才允许单独重开。
- 图后端迁移：只有默认后端出现明确性能、隔离或维护阻塞，才允许立项。
- `trajectory-to-road`：只有出现正式 runtime 设计、数据契约、验证链和证据需求，才允许从 seam 升级为计划项。

## 11. 结束条件

当以下条件同时满足时，本主计划可以视为完成：

- live spec / evidence 路径恢复完成，相关脚本与测试通过；
- no-ui operator / scenario / maturity 证据刷新完成；
- 面向大规模、多源建筑物数据融合能力的边界、证据、文档收口完成；
- `fusioncode` 全量算法库集成的 claim_state、证据与文档收口完成；
- thesis 研究资产形成闭环，且不超出现有 runtime 证据；
- 仓库中仍然只有这一份活跃计划。
