# 研究创新点与核心主张的支持性证据

> 状态：A1 当前证据归纳
> 更新日期：2026-08-31
> 适用范围：依据冻结 KG v1、Freeze C、P1-P4-G、RQ3 规划材料和 P7 平台实现证据整理

本文只汇总能够为预期创新点和研究核心提供支撑的实验、数据及支撑角度。研究主张的最终状态仍以 [`research-claim-evidence-ledger.md`](research-claim-evidence-ledger.md) 为准。

## 1. I1：契约化七层知识图谱

### 1.1 KG v1 模式与实体冻结

**实验/数据：**

- `P0-K2` 模式冻结：7 个知识层、71 个模式类、42 类关系、19 项核心属性、8 项完整性约束和 8 个 competency questions。
- KG v1 冻结实体包：241 个稳定标识静态知识对象、6 个产品契约实体、1 条类型转换边。
- `P0-K1/K3` 知识片段迁移台账：47 个片段覆盖 intent、capability、产品契约、数据源、质量、恢复和证据七条决策链；35 个高风险片段完成唯一真源迁移或执行机制归类。
- `P0-K5` 发布包：`schema.json`、`entities.json`、`policies.json`、来源台账、release identity 和语义哈希。

**支撑内容：**

- 支撑灾害应急数据产品知识可以被组织为统一的七层、版本化、可计算模型。
- 支撑产品契约、数据需求、数据源语义、算法能力、质量策略、恢复策略和证据要求能够共享稳定标识与关系约束。
- 支撑知识对象可以进入机器可读 schema、实体、关系、政策和 competency-question 验证链。

**证据位置：**

- `kg/ontology/v1.0.0/`
- `docs/current/research-charter.md`
- `docs/current/evidence/2026-08-01-freeze-c-p1-audit.json`
- `docs/current/evidence/p2-stability/2026-08-01-freeze-c-p2-stability.json`
- `docs/current/benchmark/v1/freeze_audit.json`

## 2. I2：知识约束规划与确定性接地

### 2.1 KG-only 行为扰动

**实验/数据：**

- `P0-K4` 修改 `wp.flood.building.safe.success_rate` 后，规划从 `wp.flood.building.default` / `algo.fusion.building.v1` 切换到 safe pattern/algorithm。
- 计划上下文记录 `knowledge_identity`、`selected_pattern_id`、排序依据和实际选择理由。
- 删除运行期必需知识、缺失输出 schema、超出冻结灾害词汇和 strict Neo4j 不可用路径均返回明确失败。

**支撑内容：**

- 支撑知识图谱内容能够改变规划和治理行为，而不需要修改执行代码。
- 支撑知识缺失、类型不匹配和后端不可用时，系统能够以 fail-closed 方式停止并保留失败原因。
- 支撑 KG、规划器、确定性 validator 和运行时之间存在可追溯的类型化消费链。

### 2.2 双后端 parity 与 source fallback

**实验/数据：**

- Java 21 + Neo4j 5.26 官方 harness 与 pinned memory 在建筑、道路、水体和 POI 四类任务上通过 pattern、step、algorithm 和 data-source 顺序 parity。
- source fallback 测试确认上游重新材料化，fallback artifact 内容和 SHA-256 与失败源残留不同。
- `P0-K4/K5` 定向组合测试 `47 passed`；独立 verifier `11/11`。

**支撑内容：**

- 支撑同一 KG release 可以被不同后端加载并产生一致语义。
- 支撑源替代不是简单替换 source ID，而是重新材料化并形成可审计的新 artifact。
- 支撑知识约束能够贯穿规划选择、源解析、执行和证据记录。

**证据位置：**

- `docs/current/evidence/p3-governance/`
- `docs/current/evidence/p4-external-validity/`
- `docs/current/research-branch-kg-v1-merge-audit.md`
- `kg/ontology/v1.0.0/release.json`

## 3. I3：质量与证据驱动的闭环恢复

### 3.1 P3-G 治理消融

**实验/数据：**

- 在同一 C02/C04/C06 manifest 和固定环境下比较完整方法、无产品契约、无质量门、无降级恢复和固定优先级。
- 完整方法的计划有效率为 `1.0`，恢复成功率为 `0.5`，最终交付成功率为 `0.3333333333333333`，证据完整率为 `0.3333333333333333`。
- 无降级恢复变体的恢复成功率为 `0.0`，最终交付成功率为 `0.0`。
- 无质量门变体的首次质量门通过率记录为不可用值，质量门绕过率为 `1.0`。

**支撑内容：**

- 支撑质量门、降级恢复、gap 声明、最终交付和证据记录能够作为同一治理链路中的可观测状态。
- 支撑移除降级恢复会改变恢复和最终交付行为。
- 支撑质量门被绕过时可以保持不可用语义，而不是把绕过记录为成功。

### 3.2 P4-G 多 AOI 治理切片

**实验/数据：**

- Caracas、Abidjan 和越南北部沿海走廊纳入同一固定 KG、运行时和输入声明下的 C02/C04 变体运行。
- 完整方法 7 个可比较案例的计划有效率、最终交付成功率、gap 声明正确率和证据完整率均为 `7/7`。
- 完整方法关键图层按时交付率为 `6/7`；固定优先级为 `3/7`；探索性 Cohen h 为 `0.93895`。
- 三个 AOI 均保留计划、交付、gap 和证据记录。

**支撑内容：**

- 支撑上下文任务顺序能够影响关键图层的按时交付行为。
- 支撑契约、质量门、交付状态和证据记录可以在多个 AOI 中沿用同一运行结构。
- 支撑 progressive delivery、degraded/provisional 状态和 supersession 可以进入可审计产物链。

**证据位置：**

- `docs/current/evidence/p3-governance/2026-08-01-freeze-c-p3-governance.md`
- `docs/current/evidence/p4-external-validity/2026-08-01-freeze-c-p4-external-validity.md`
- `docs/current/evidence/p4-external-validity/2026-08-01-freeze-c-p4-paper-materials.md`

## 4. I4：可复现实验证据方法

### 4.1 Freeze C 稳定性与独立审计

**实验/数据：**

- 同一干净 commit、冻结输入和固定环境下完成 3 次独立重跑。
- 字节差异均完成分类，未解释语义差异为 `0`。
- 独立 verifier 对 release identity、schema、实体、政策、输入输出哈希和篡改响应完成 `11/11` 检查。
- Freeze C 保存真实外部输入、源文件及 sidecar、输出、运行配置、manifest 和工作区状态。

**支撑内容：**

- 支撑 KG 版本、输入、prepared input、运行输出、质量报告和证据清单可以被统一冻结。
- 支撑语义稳定哈希能够区分运行元数据波动与知识/结果变化。
- 支撑独立验证器可以在不依赖作者口头解释的情况下复核证据链完整性。

### 4.2 Benchmark Platform Core V1 离线实现闭环

**实验/数据：**

- P0-P6 阶段链全部通过，核心行为合同测试 `64 passed`。
- P7 机器检查 `10/10`，用户七项人工复核全部 `approved`，BP7 总检查 `11/11`。
- implementation manifest、checkpoint、audit、失败尝试和文件 SHA-256 已绑定；本地与远端 tag `benchmark-platform-core-v1` 已冻结。
- Provider、judge、benchmark instances 和 formal result roots 均为 `0`。

**支撑内容：**

- 支撑参数化 benchmark 平台 core 的组件边界、fail-closed、视图隔离、恢复、CLI 和证据合同已经形成可复核的离线实现。
- 支撑平台实现过程可以按阶段 checkpoint、机器审计、人工复核和 tag 冻结进行复现与交接。
- 支撑研究工程能够把代码、测试、状态、哈希、失败和治理入口放入同一证据闭环。

**证据位置：**

- `docs/current/benchmark/platform/v1/implementation/README.md`
- `docs/current/benchmark/platform/v1/implementation/implementation_manifest.json`
- `docs/current/benchmark/platform/v1/implementation/p7_audit.json`
- `docs/current/benchmark/platform/v1/implementation/p7_checkpoint.json`

## 5. 支撑关系总表

| 预期创新点/核心 | 主要实验与数据 | 直接支撑角度 |
| --- | --- | --- |
| I1 / RQ1 | P0-K1/K2/K3/K5、KG v1 release、241 对象、71 类、42 关系、8 约束、8 CQ | 统一知识模型、版本化机器源、契约/质量/恢复/证据语义组织 |
| I2 / RQ2 | P0-K4/K5 KG-only 扰动、缺失知识 fail-closed、source fallback、Neo4j-memory parity | KG 实际参与决策、确定性接地、失败可归因、后端语义一致 |
| I3 / RQ4 | P3-G 治理消融、P4-G 三 AOI C02/C04、C04 supersession、质量门与降级状态 | 质量治理、交付状态、恢复策略和证据链的联动行为 |
| I4 / RQ4 | Freeze C P1/P2、P3-G/P4-G manifest、独立 verifier、P7 platform closure | 冻结、重跑、哈希、失败留痕、独立复核和可交接闭环 |
