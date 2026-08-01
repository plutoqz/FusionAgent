# Freeze C P2 稳定性重跑摘要

- 总体结果：**通过**
- commit：`93ebdc51c8732ec466067de760a65f30f3f1155c`
- 运行次数：3
- 字节级稳定：**否**
- 语义级稳定：**是**
- 未解释字节差异：**0**

## 运行状态

- Run 01：通过，退出码 `0`，目录 `D:\code\freeze-c-evidence\p2-stability-20260801-c02-c04-c06\run-01`
- Run 02：通过，退出码 `0`，目录 `D:\code\freeze-c-evidence\p2-stability-20260801-c02-c04-c06\run-02`
- Run 03：通过，退出码 `0`，目录 `D:\code\freeze-c-evidence\p2-stability-20260801-c02-c04-c06\run-03`

## 允许波动分类

- `ZIP/container bytes vary but member content is stable: ('C02', 'outputs', 'water_polygon', 'partial_provisional', 'water_fusion_result.zip')`
- `ZIP/container bytes vary but member content is stable: ('C02', 'outputs', 'waterways', 'partial_provisional', 'water_fusion_result.zip')`
- `ZIP/container bytes vary but member content is stable: ('C02', 'provisional_outputs', 'water_polygon', 'partial_provisional', 'water_fusion_result.zip')`
- `ZIP/container bytes vary but member content is stable: ('C04', 'outputs', 'water_polygon', 'succeeded', 'water_fusion_result.zip')`
- `ZIP/container bytes vary but member content is stable: ('C04', 'provisional_outputs', 'water_polygon', 'partial_provisional', 'water_fusion_result.zip')`
- `ZIP/container bytes vary but member content is stable: ('C04', 'superseded_outputs', 'water_polygon', 'superseded', 'water_fusion_result.zip')`
- `ZIP/container bytes vary but member content is stable: ('C06', 'outputs', 'road', 'partial_provisional', 'road_fusion_result.zip')`
- `ZIP/container bytes vary but member content is stable: ('C06', 'provisional_outputs', 'road', 'partial_provisional', 'road_fusion_result.zip')`

## 比较范围

- 字节级：artifact 原始 SHA-256、9 组/32 个外部输入 SHA-256
- 语义级：以下字段
- all_cases_passed
- case stages
- feature counts
- coverage counts
- quality metrics
- gap declarations
- prepared-input semantic hashes
- task order
- supersession topology

## 字节级差异

- `run-01 vs run-02.artifact_hashes[0].sha256: '1531417053aa1523d5ac6613803d3cb8ca45511a73d4fa40f058313727eb1b79' != 'cdffc317f4ac08bd97f0040ceb2f94723071f95a4cac4c76f75c2dca763f2321'`
- `run-01 vs run-02.artifact_hashes[1].sha256: '68030c86fc92c61e6163336777d3e8380b08f452a73aea04b2a28c4b7c82ff40' != '77ddb34586d5374012d532ea04082b9441389b03bb9ab0dbc7e26c09688f2bef'`
- `run-01 vs run-02.artifact_hashes[2].sha256: '1531417053aa1523d5ac6613803d3cb8ca45511a73d4fa40f058313727eb1b79' != 'cdffc317f4ac08bd97f0040ceb2f94723071f95a4cac4c76f75c2dca763f2321'`
- `run-01 vs run-02.artifact_hashes[3].sha256: '48a11a264d24ee1b07d842de288b46433f68805de612b948594b6a302ade51d5' != '18aa235a68bce2c98bb5fd7d9e246f864307dcc883cffc9c8bce55f16ba7ad27'`
- `run-01 vs run-02.artifact_hashes[4].sha256: '0aa13bed9f313aa19cb9fd9ed648ee88dcc44c914b3423e18e5383be45143626' != 'a9b5239c835c43ae83a09ee6540d2114bcdef0989332cbee837ca3b179eec29d'`
- `run-01 vs run-02.artifact_hashes[5].sha256: '0aa13bed9f313aa19cb9fd9ed648ee88dcc44c914b3423e18e5383be45143626' != 'a9b5239c835c43ae83a09ee6540d2114bcdef0989332cbee837ca3b179eec29d'`
- `run-01 vs run-02.artifact_hashes[6].sha256: 'ae98ac9e645e49d18620aeb385b2c0d1c9f63dfab1bb2542a3d315d9cd8bf3f0' != '5335ad7bf1a1370ad4a3df75b5954d93643672d1544b945e33c9e28b21f229fd'`
- `run-01 vs run-02.artifact_hashes[7].sha256: 'ae98ac9e645e49d18620aeb385b2c0d1c9f63dfab1bb2542a3d315d9cd8bf3f0' != '5335ad7bf1a1370ad4a3df75b5954d93643672d1544b945e33c9e28b21f229fd'`
- `run-01 vs run-03.artifact_hashes[0].sha256: '1531417053aa1523d5ac6613803d3cb8ca45511a73d4fa40f058313727eb1b79' != '55f50452790f77c7dc4cc818ece55ecedfa2cd259ee7a5abb8464c2286fbb356'`
- `run-01 vs run-03.artifact_hashes[1].sha256: '68030c86fc92c61e6163336777d3e8380b08f452a73aea04b2a28c4b7c82ff40' != '72047aca80ab72053148641fb1717371f6d786a15b562807db32a474a657ae99'`
- `run-01 vs run-03.artifact_hashes[2].sha256: '1531417053aa1523d5ac6613803d3cb8ca45511a73d4fa40f058313727eb1b79' != '55f50452790f77c7dc4cc818ece55ecedfa2cd259ee7a5abb8464c2286fbb356'`
- `run-01 vs run-03.artifact_hashes[3].sha256: '48a11a264d24ee1b07d842de288b46433f68805de612b948594b6a302ade51d5' != '9acab020aca7475278bacd2e64869ffc7f968626544b02353325d81300b8ee06'`
- `run-01 vs run-03.artifact_hashes[4].sha256: '0aa13bed9f313aa19cb9fd9ed648ee88dcc44c914b3423e18e5383be45143626' != '8222de9da7d7fa23aec8613d5186071e1daadc193e983b61bc559ed2a323e9f2'`
- `run-01 vs run-03.artifact_hashes[5].sha256: '0aa13bed9f313aa19cb9fd9ed648ee88dcc44c914b3423e18e5383be45143626' != '8222de9da7d7fa23aec8613d5186071e1daadc193e983b61bc559ed2a323e9f2'`
- `run-01 vs run-03.artifact_hashes[6].sha256: 'ae98ac9e645e49d18620aeb385b2c0d1c9f63dfab1bb2542a3d315d9cd8bf3f0' != '9cbdec53ba4de37641cfaab0250bf29b9cc1c16eca5ab33232e770b95eb1c707'`
- `run-01 vs run-03.artifact_hashes[7].sha256: 'ae98ac9e645e49d18620aeb385b2c0d1c9f63dfab1bb2542a3d315d9cd8bf3f0' != '9cbdec53ba4de37641cfaab0250bf29b9cc1c16eca5ab33232e770b95eb1c707'`

允许波动：run/scenario/artifact 标识、绝对路径、时间戳和运行元数据不参与语义稳定判定；它们仍保留在各次原始运行目录中。
