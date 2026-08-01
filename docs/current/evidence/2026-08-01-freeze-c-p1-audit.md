# Freeze C P1 独立审计摘要

- 审计结果：**通过**
- 实验：`exp-c02-c04-c06-caracas-real-20260725-final`
- commit：`93ebdc51c8732ec466067de760a65f30f3f1155c`
- 证据目录：`D:\code\freeze-c-evidence\exp-c02-c04-c06-20260725-final-93ebdc5`
- manifest SHA-256：`38225e3a1dff3301c0cd076c871b8fee4b09ecb28b32fb3b0df2e24d589a7a45`

## 检查项

- [通过] manifest SHA-256 (`manifest_hash`)
- [通过] 冻结包逐文件 SHA-256 与 clean 文件集 (`package_hashes`)
- [通过] 原始外部输入逐文件 SHA-256 (`external_input_hashes`)
- [通过] 实验结果与 all_cases_passed 闸门 (`experiment_result`)
- [通过] commit 与冻结 worktree clean 状态 (`commit_and_clean_worktree`)

说明：manifest 自身 SHA-256 已记录；只有命令提供 `--expected-manifest-sha256` 时，才对 manifest 自身做外部信任根比对。
