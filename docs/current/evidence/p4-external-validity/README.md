# P4 外部有效性证据目录

本目录是 Freeze C P4 的统一研究材料入口，文档以中文为主，机器报告与原始运行证据分开保存。

## 入口文件

| 文件 | 用途 |
| --- | --- |
| `2026-08-01-freeze-c-p4-external-validity-protocol.md` | AOI 选择、固定环境、运行协议、指标和限制 |
| `2026-08-01-freeze-c-p4-external-validity.json` | 机器可读汇总、逐案例指标、效果量和限制 |
| `2026-08-01-freeze-c-p4-external-validity.md` | 结果摘要和论文表格草稿 |
| `2026-08-01-freeze-c-p4-reference-sample-audit.json` | HydroLAKES/HydroRIVERS 与 OSM 的确定性抽样审计 |
| `2026-08-01-freeze-c-p4-aoi-input-inventory.json` | AOI、源声明、输入声明哈希和 C06 可用性 |
| `2026-08-01-freeze-c-p4-paper-materials.md` | 研究问题映射、结果解读、可引用表述和有效性威胁 |
| `manifests/` | 三个 AOI 的正式实验 manifest 和边界文件 |

## 正式原始证据

原始运行目录：

`D:\code\freeze-c-evidence\p4-external-validity-20260801-v2`

包含 `caracas_full_method`、`caracas_fixed_priority`、`abidjan_full_method`、`abidjan_fixed_priority`、`vietnam_coastal_full_method` 和 `vietnam_coastal_fixed_priority` 六个变体目录。每个正式目录均包含 `experiment_evidence_manifest.json`，记录 commit、运行设置、指标定义和文件 SHA-256。

## 固定条件

- commit：`db256d591cc000b9bb1dc1880601da070fe9f74d`
- KG：memory backend，冻结 seed
- LLM：mock provider
- Celery：eager，单 child worker
- `GEOFUSION_PLAN_GROUNDING_MODE=report`
- local-only，禁用 artifact reuse

## 运行命令

```powershell
.venv\Scripts\python.exe scripts\run_p4_external_validity.py --prepare
.venv\Scripts\python.exe scripts\run_p4_external_validity.py --run-aoi caracas --variant full_method --server-port 8284
.venv\Scripts\python.exe scripts\run_p4_external_validity.py --run-aoi caracas --variant fixed_priority --server-port 8285
.venv\Scripts\python.exe scripts\run_p4_external_validity.py --summarize
```

Abidjan 和越南北部沿海走廊的 C02/C04 正式运行目录已保留；重新运行时使用脚本的 `--run-aoi` 和对应空闲端口，并输出到同一原始证据根目录下的变体目录。

## 解释边界

C02/C04 在三个 AOI 重复，C06 仅在 Caracas 重复。外部参考匹配率是源一致性/覆盖代理，不是人工真值精度、召回率或完整位置误差。每个 AOI/变体只运行一次，均值、样本标准差、95% CI 和 Cohen h 仅用于探索性描述。
