# FusionAgent Single-Plan Consolidation Design

## Goal

把当前分散在 `docs/superpowers/plans/` 下的多份活跃/半活跃/延期计划，收敛为**唯一一份后续执行主计划**，并明确规定：

- 后续执行只依据这一个计划文档推进
- 其他计划文档全部移入 `docs/superpowers/plans/done/`
- 已完成历史能力保留为精简基线，不再以旧计划作为执行入口
- 明确搁置项只保留为边界说明，不作为当前执行步骤

本设计只定义“如何收敛计划体系”，不直接改 runtime 能力边界，不新增产品能力。

## Problem

当前仓库虽然已经有 [2026-05-12-fusionagent-master-execution-plan.md](/E:/vscode/fusionAgent/docs/superpowers/plans/2026-05-12-fusionagent-master-execution-plan.md:1) 作为主排序文档，但它仍然依赖多份旧计划作为“详细任务来源”。这带来三个持续问题：

1. 判断当前待办时，必须反复横跳多个计划文件。
2. 旧计划中的未勾选框容易和“当前活跃 backlog”混淆。
3. 新工作如果继续沿用多文档模式，很快又会回到计划分散、状态漂移的局面。

用户的新要求是把后续工作集中到单一文档中，并在以后只依据这份文档执行。

## Constraints

本次收敛必须遵守以下约束：

- 保留单一计划目标，不再保留多个平行活跃计划。
- 保留一段**精简已完成基线**，避免丢失当前稳定能力边界。
- 当前明确搁置项不进入执行阶段：
  - 前端证据面增长
  - 图后端迁移试验
  - `trajectory-to-road` 可执行化
- `fusioncode` 全量算法库集成必须纳入唯一计划。
- 原“Benin scale”工作必须重写为**面向大规模、多源建筑物数据融合能力**的规模化能力主线，而不是针对 Benin 的国家特化能力。
- 计划文档必须足够详细，能够持续执行直到全部完成。

## Options

### Option A: Create A Brand-New Unified Plan File

新增一份新的唯一主计划文件，把现有 master plan 和所有后续阶段全部吸收进去；旧 master plan 也移入 `done/`。

优点：

- 语义最干净，历史与未来完全切开。
- 可以从零开始设计新的阶段结构。

缺点：

- 会引入新的活跃文件路径。
- 现有对 master plan 的引用会变成历史引用。

### Option B: Rewrite The Existing Master Plan In Place

保留 [2026-05-12-fusionagent-master-execution-plan.md](/E:/vscode/fusionAgent/docs/superpowers/plans/2026-05-12-fusionagent-master-execution-plan.md:1) 作为唯一活跃计划文件，但把它重写为真正自足的详细总计划；所有其他计划移动到 `done/`。

优点：

- 保留当前唯一活跃入口，不新增路径心智负担。
- 与现有主计划状态衔接最自然。
- 历史引用和 README 中如果已有 master plan 指针，变更成本最低。

缺点：

- 需要重写现有 master plan 的大部分正文。
- 需要在文内清理“引用别的计划当详细任务来源”的旧组织方式。

### Option C: Keep A Thin Master Plan Plus Detailed Appendices

保留一个薄总纲，再把详细步骤分散到多个附录计划文件里，但形式上都移入 `done/` 或附录区。

优点：

- 主文档更短。

缺点：

- 本质上仍然依赖多文档。
- 不满足“后续只依据这个计划文档执行”的目标。

## Recommendation

采用 **Option B: Rewrite The Existing Master Plan In Place**。

原因：

1. 当前仓库已经把该 master plan 识别为唯一活跃排序入口，继续沿用它能减少路径切换和引用迁移。
2. 用户要的是“唯一执行计划”，不是“再创建一个新的总纲文档”。
3. 就地重写 master plan，可以把“已完成基线 + 当前剩余工作 + 明确搁置项 + 文档归档规则”一次性固定下来。

## Proposed Architecture

唯一活跃计划文件继续使用：

- `docs/superpowers/plans/2026-05-12-fusionagent-master-execution-plan.md`

该文件重写后的职责分为四层：

1. **Execution Charter**
   - 声明这是唯一活跃计划
   - 声明以后新增任务必须先并入此文档
   - 声明其他计划文件仅作历史归档，不再作为执行入口

2. **Completed Baseline**
   - 精简记录已稳定实现的 runtime 主张、证据契约、接口面和已关闭阶段
   - 只保留后续执行必需的上下文，不复述历史细节

3. **Remaining Execution Phases**
   - 详细列出后续全部未完成工作
   - 每个阶段都直接包含“要做什么、涉及文件、验证标准、边界约束”
   - 不再依赖其他计划文件作为详细任务来源

4. **Parked Scope**
   - 记录明确搁置项
   - 说明为什么搁置、何时才允许重新进入计划
   - 这些内容只作为边界说明，不出现在执行步骤中

## Unified Plan Shape

重写后的唯一主计划应当按以下结构组织。

### Section 1: Charter

- 该文档是唯一活跃计划
- 以后不得再新增平行活跃计划文档
- 任何新增 backlog 必须先并入本文件再执行

### Section 2: Completed Baseline

只保留执行仍需依赖的稳定基线：

- 稳定主题边界：`building / road / water / bounded poi`
- 共享运行骨架：`planner -> validator -> executor -> healing/replan -> writeback`
- 共享证据契约：
  - `run.json`
  - `plan.json`
  - `validation.json`
  - `audit.jsonl`
  - artifact bundle
- 已关闭阶段摘要：
  - KG closure
  - core-next runtime hardening
  - 已落地的 no-UI/operator/evidence 资产
- 不能倒退的边界约束

### Section 3: Remaining Phase A

原 Phase 3 的真正剩余项，写成自足步骤：

- scenario capability regression 收口
- harness-side capability validation
- checked-in scenario manifest 刷新
- scenario evidence freeze 刷新
- operator read surface 缺口收口
- artifact preview / no-UI maturity evidence / runbook 对齐

### Section 4: Remaining Phase B

原 thesis research asset closure，直接吸收为唯一计划中的论文资产阶段：

- thesis research spec
- claims ledger
- experiment matrix
- related-work matrix
- outline and timeline
- research-plan / capability-plan handshake

### Section 5: Remaining Phase C

把原“Benin scale preparation”重写为**大规模、多源建筑物数据融合能力**阶段，而不是地理区域特化阶段。

此阶段的目标应明确为：

- 面向大 AOI 的 building runtime scale-up
- 面向多源 building source-set 的输入建模
- 面向 tiled execution 的可复现切片、缓存和拼接
- 面向大规模 building benchmarking 的证据冻结

此阶段仍允许使用 Benin 作为验证数据来源之一，但不能把阶段叙事写成“为 Benin 定制”。

### Section 6: Remaining Phase D

纳入 `fusioncode` 全量算法库集成，直接作为唯一计划正式阶段，而不是 Conditional Phase 6：

- algorithm primitive layer
- parameter decoupling
- KG algorithm/data-type/workflow metadata
- adapters and executor handlers
- planner and validator integration
- parity tests, smoke tests, regression tests
- docs and evidence updates

### Section 7: Final Verification And Archive Hygiene

- 全仓 focused + broader verification
- evidence freeze refresh
- README / docs 术语一致性检查
- 所有旧计划状态归档与说明一致

### Section 8: Parked Scope

以下内容只保留在唯一计划的“搁置范围”章节中，不进入执行阶段：

- 前端证据面增长
- 图后端迁移试验
- `trajectory-to-road` 可执行化

其中：

- 前端工作台仍可作为 operator surface 存在，但当前不作为执行路线
- 图后端迁移只在默认后端出现明确性能/隔离阻塞后再单独重开
- `trajectory-to-road` 继续保持 reservation-only seam

## File Migration Rules

在设计被确认并进入实施后，计划文件迁移规则如下：

1. 保留 `docs/superpowers/plans/2026-05-12-fusionagent-master-execution-plan.md` 为唯一活跃计划。
2. 将以下文件全部移入 `docs/superpowers/plans/done/`：
   - `2026-04-21-no-ui-mature-agent-plan.md`
   - `2026-04-21-scenario-regression-set-plan.md`
   - `2026-04-23-system-next-improvements.md`
   - `2026-04-27-benin-building-runtime-preparation.md`
   - `2026-04-29-fusioncode-algorithm-library-kg-integration.md`
   - `2026-05-06-fusionagent-agent-capability-update-roadmap.md`
   - `2026-05-06-fusionagent-thesis-research-design-roadmap.md`
   - `2026-05-09-kg-closure-and-graph-backend-roadmap.md`
3. 已经在 `done/` 中的文件保持不动。
4. 主计划中必须有一个“absorbed historical plans”映射表，说明每一份旧计划被吸收到哪个章节。
5. 旧计划不再承载未来待办语义，只承载历史审计价值。

## Required Detail Level

新的唯一主计划必须比当前 master plan 更细，至少达到以下粒度：

- 每个阶段都直接写出任务链，而不是只写标题
- 每个阶段都有：
  - 目标
  - 涉及文件或模块
  - 验证标准
  - anti-pattern guards
- 对长期阶段（大规模多源 building、fusioncode integration）必须写成可以连续执行的分任务序列，而不是保留抽象方向

## Anti-Patterns

重写唯一计划时，必须避免以下反模式：

- 继续把“详细步骤见其他计划文件”写进新 master plan
- 把搁置项写成当前阶段的待办步骤
- 继续使用地域特化叙事来描述通用规模化 building 能力
- 在唯一计划中保留多个平行“active”入口
- 把历史未勾选框继续当作当前 backlog 的来源

## Acceptance Criteria

本设计实施完成后，应满足：

1. `docs/superpowers/plans/` 根目录下只剩一份活跃计划 Markdown。
2. 后续执行只需要阅读这一份文档即可知道全部剩余工作。
3. 其他计划文档全部进入 `done/`，不再作为执行入口。
4. 唯一主计划同时包含：
   - 精简已完成基线
   - 全部剩余执行阶段
   - 明确搁置范围
5. `fusioncode` 全量集成被纳入唯一计划。
6. 原“Benin scale”被改写为通用的大规模、多源建筑物数据融合能力阶段。

## Scope Check

这个设计仍然是**单一子项目范围**，因为它解决的是一个明确问题：计划体系收敛与后续执行入口统一。它不会要求把其他独立产品能力一起设计进去。

## Next Step

在本设计得到用户复核确认后，下一步应当是：

1. 重写唯一 master plan
2. 迁移其他计划到 `done/`
3. 校验目录下只剩唯一活跃计划
4. 后续所有推进只更新该主计划
