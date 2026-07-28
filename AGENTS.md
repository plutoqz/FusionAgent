# Agent Instructions

在分析、规划或修改本仓库前, 必须先阅读根目录 `PROJECT.md`。

硬性要求:

- `PROJECT.md` 是当前研究方向、实验协议和非目标边界的最高优先级文档。
- 不得把 `docs/thesis/experiment_gold.json` 的内容传入 planner、prompt、KG retrieval 或 planning context。
- 不得通过 case-specific 规则、输入顺序或 deterministic postprocessor 替 planner 生成可得分答案。
- 真实 LLM 实验不得静默回退为确定性或 oracle 结果。
- 不得提交或输出 `.env.local` 中的密钥。
- 历史 plan、freeze、maturity 和 scenario 文档不能覆盖 `PROJECT.md`。
- 开始实现前应明确任务服务于 `PROJECT.md` 中的哪个 Phase。
