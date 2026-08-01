# Freeze C P2 稳定性重跑协议

## 运行协议

三次运行均从以下干净 worktree 执行：

```text
worktree: D:\code\FusionAgent-freeze-c-93ebdc5
commit:   93ebdc51c8732ec466067de760a65f30f3f1155c
manifest: docs\thesis\manifests\2026-07-20-c02-c04-c06-real-data.json
```

固定环境为 memory KG、mock LLM、eager Celery、单 child worker、local-only 和禁用 artifact reuse。每次运行使用独立目录：

```text
D:\code\freeze-c-evidence\p2-stability-20260801-c02-c04-c06\run-01
D:\code\freeze-c-evidence\p2-stability-20260801-c02-c04-c06\run-02
D:\code\freeze-c-evidence\p2-stability-20260801-c02-c04-c06\run-03
```

重新运行命令：

```powershell
.venv\Scripts\python.exe scripts\run_freeze_c_stability.py `
  --worktree "D:\code\FusionAgent-freeze-c-93ebdc5" `
  --evidence-root "D:\code\freeze-c-evidence\p2-stability-20260801-c02-c04-c06" `
  --python-executable "D:\code\FusionAgent\.venv\Scripts\python.exe" `
  --run-count 3 `
  --server-port 8219 `
  --timeout-seconds 1800 `
  --report-json "docs\current\evidence\p2-stability\2026-08-01-freeze-c-p2-stability.json" `
  --summary-markdown "docs\current\evidence\p2-stability\2026-08-01-freeze-c-p2-stability.md"
```

已有三次原始运行只重建比较报告时，使用 `--reuse-existing`，不会重新执行实验。

## 比较范围

- 字节级：交付 artifact 原始 SHA-256；9 组/32 个外部输入 SHA-256；prepared-input 原始哈希保留在机器报告中。
- 语义级：C02/C04/C06 的阶段、最终阶段、要素数、覆盖计数、质量指标、gap、task order、provisional 和 supersession 拓扑，以及去除路径后的 prepared-input 语义哈希。
- 允许波动：run/scenario/artifact 标识、绝对路径、时间戳、运行元数据，以及 ZIP 容器字节；ZIP 解压后的成员内容哈希不属于允许波动。

## 本次结果

机器报告：`2026-08-01-freeze-c-p2-stability.json`

人工摘要：`2026-08-01-freeze-c-p2-stability.md`

结果为：3/3 运行通过，语义级稳定通过，9 组/32 个外部输入哈希一致。artifact 原始字节级稳定为否，但 8 组 ZIP 差异均被分类为“容器字节变化、成员内容稳定”；未解释差异为 0，因此 P2 总体通过。

C06 中“全融合质量门失败”是案例设计的预期中间阶段；三次均完成受控恢复并通过最终案例契约。该结果支持指定 commit、输入和环境下的可重复语义行为，不支持跨 AOI 的广泛有效性或性能主张。
