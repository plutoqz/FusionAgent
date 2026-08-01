# Freeze C P1 独立审计协议

## 审计命令

在仓库根目录执行：

```powershell
.venv\Scripts\python.exe scripts\audit_freeze_c_evidence.py `
  --evidence-dir "D:\code\freeze-c-evidence\exp-c02-c04-c06-20260725-final-93ebdc5" `
  --manifest "D:\code\freeze-c-evidence\exp-c02-c04-c06-20260725-final-93ebdc5\experiment_evidence_manifest.json" `
  --worktree "D:\code\FusionAgent-freeze-c-93ebdc5" `
  --expected-commit "93ebdc51c8732ec466067de760a65f30f3f1155c" `
  --expected-manifest-sha256 "sha256:38225e3a1dff3301c0cd076c871b8fee4b09ecb28b32fb3b0df2e24d589a7a45" `
  --report-json "docs\current\evidence\2026-08-01-freeze-c-p1-audit.json" `
  --summary-markdown "docs\current\evidence\2026-08-01-freeze-c-p1-audit.md"
```

命令只依赖 Python 标准库，不导入 FusionAgent 运行模块。退出码为 `0` 才表示审计通过；报告输出文件已存在时拒绝覆盖。

## 验证范围

- manifest 声明的 638 个包内文件逐字节 SHA-256、文件大小和 clean 文件集；包内 manifest 本身作为唯一允许的控制文件保留。
- 9 组、32 个原始外部输入逐文件 SHA-256 和文件大小。
- 包内 5 个 `prepared_inputs_*.json`、49 个运行 input、106 个运行 output 及 317 个原始包文件均纳入分组统计和哈希核验。
- `experiment_result.json` 的 `all_cases_passed` 必须为 `true`，且 C02/C04/C06 均通过。
- Freeze C worktree 必须位于 commit `93ebdc51c8732ec466067de760a65f30f3f1155c`，并且 `git status --porcelain` 为空。
- 实验 runner 对已存在且非空的 `experiment-dir` 直接拒绝，避免覆盖旧证据。

## 本次结果

机器报告：`2026-08-01-freeze-c-p1-audit.json`

人工摘要：`2026-08-01-freeze-c-p1-audit.md`

本次真实冻结包审计通过。manifest SHA-256 为 `38225e3a1dff3301c0cd076c871b8fee4b09ecb28b32fb3b0df2e24d589a7a45`。输入篡改、输出篡改、manifest 锚定篡改、非空目录保护和 `all_cases_passed=false` 均有定向自动化测试覆盖；未重跑 Freeze C 全量业务实验。
