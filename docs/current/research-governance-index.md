# 当前研究文档路由

> 状态：本机兼容入口，不是第二份研究计划
> 更新日期：2026-09-08

## 当前批准入口（2026-09-08）

主线是证明 KG+LLM 相对公平、可运行基线的优越性。权威设计见 `D:\code\FusionAgent-benchmark-platform-dev\docs\current\research-evidence-next-design.md` 的 2026-09-08 节，覆盖下文历史顺序：先修复 LLM-only 适配器、补共同质量评价、确认恢复动作到达执行器，再做 4 条件 x 5 方法 = 20 次开发筛查。正常条件允许打平，困难条件须共享可行方案；后续使用未调试案例独立确认并做协作/知识消融。截止前达标交付为主指标，拒绝不算融合完成，不以接口失败制造优势。本次仅更新文档并提交已有变更，未新增实验。

## 历史进展（保留原时点）

当前状态（覆盖下文历史时点的“尚未运行”）：五方法真实道路缓存首案已完成，见权威实验账本 `E-R3-FIVE-METHOD-SCREEN-20260907`。四组融合道路数及端点 proxy 相同，均未通过质量门；单 LLM 因工具契约问题在执行前失败。没有观察到 KG+LLM 质量/交付优势，且公共工具可用性说明不足，不能把单 LLM 失败当成方法胜负。下一步先修正共同接口并补跑可比首案，再补共同质量评价及真实应急换源/恢复、时限/网络条件。具体顺序见权威计划顶部摘要，不重复历史接线任务。

当前权威研究文档在同仓库工作树 `D:\code\FusionAgent-benchmark-platform-dev`：

- [研究治理入口](../../../FusionAgent-benchmark-platform-dev/docs/current/research-governance-index.md)
- [下一步研究工作计划](../../../FusionAgent-benchmark-platform-dev/docs/current/research-evidence-next-design.md)
- [主张-证据账本](../../../FusionAgent-benchmark-platform-dev/docs/current/research-claim-evidence-ledger.md)
- [实验账本](../../../FusionAgent-benchmark-platform-dev/docs/current/research-experiment-ledger.md)
- [研究章程](../../../FusionAgent-benchmark-platform-dev/docs/current/research-charter.md)

当前下一验收点为 R1-R3 真实闭环最小比较：任务解析、数据下载、任务规划、融合执行、结果审查、重试/降级/发布。旧 Q1 planning-only 方案不再追加；本轮尚未新增调用或真实运行。本工作树的旧项目状态、章程阶段和计划不覆盖上述当前入口。

2026-09-07 继续执行：R1 输入与入口核对完成，R2 已补充下载、质量、修复及重规划 trace。源码确认首次规划早于下载，质量审查位于执行重规划循环之外；下一步接通这两个反馈入口，再做正常条件单案例 smoke 和五方法比较。trace 修改不代表缺失控制流已经实现。

后续实现更新：质量审查现已接入有界重规划，拒绝报告与失败矢量按 revision 归档；未产生新计划则终止，普通 writeback 错误不触发重规划。该路径已有 mock/fixture 测试，尚无真实 Caracas 运行。下载后规划、五方法适配和受扰动比较仍待实现；权威进度见计划 R2b 与实验账本 `E-R2-QUALITY-FEEDBACK-20260907`。

再续进展：已实现显式开关 `plan_after_acquisition=true` 的下载后融合规划，保留获取计划并保存真实材料化观测接口；同输入包约束下经 validator 才执行。127 项 mock/fixture 测试通过，无新真实运行。当前下一动作是真实单案例 smoke；动态换源/下载完全失败恢复、五方法及网络时限实验仍未完成。见权威计划 R2a 与 `E-R2-POST-ACQUISITION-20260907`。

最新：`caracas-road-kg-runtime-smoke-20260907-r3` 已用真实道路缓存执行融合，23,760 条记录，质量拒绝和恢复来源失败，未发布。无真实 LLM（本地配置缺失），不是五方法比较。下一步检查拓扑质量指标及恢复来源约束；详见权威账本 `E-R2-CARACAS-ROAD-SMOKE-20260907`，前三轮失败全部保留。

配置更正：本地 `.env` 配置完整，之前缺少的是进程内 dotenv 加载，不是本地凭据。显式加载后 OpenAICompatibleProvider 初始化成功，尚未调用 API。后续无需用户重新配置，不记录或展示密钥。

最新真实结果：`caracas-road-live-smoke-20260907-r3` 已完成 3 次真实 LLM 调用和两次融合，质量均拒绝、恢复计划执行参数不变、达到版本上限后未发布。245.5115 秒、234,384 tokens。见权威账本 E-R3-LIVE-ROAD-SMOKE-20260907；下一步检查拓扑指标、恢复动作与上下文规模，五方法比较尚未完成。

五方法 r2 回放：公共工具投影已修正，单 LLM 不再触发 `MISSING_RUNTIME_STATUS`，但被实验适配器的严格模式检查停止，未进入融合；KG+LLM 仍质量拒绝、未发布，未观察到优势。下一步修正单 LLM 适配器并补跑可比首案，不能把 r1/r2 单 LLM 失败当作 KG 胜出证据。

当前：真实数据诊断已完成（E-R3-ROAD-DIAGNOSTIC-20260907），原始 OSM 595.16、融合 637.03 的端点 proxy 对分段敏感；不能直接称为真实断连率。历史上下文压缩及相同动作质量重试拦截已实现，134 项测试通过；无新 LLM/融合运行。下一步进入共同道路评价与五方法首案比较。

`main` 当前含未提交实验代码，运行结果位于 `runs/experiments/`；文档树与源码树的 HEAD、未提交文件需分别核对。此路由仅供本机跨工作树导航，不表示已 merge、commit 或 push，也不是可移植的论文证据链接。
