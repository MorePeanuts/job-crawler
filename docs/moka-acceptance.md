# Moka 公开校招适配器验收

2026-10-12，SPEC-013。以下十三个租户分别经公开入口、无筛选列表、`jobStats.total`、唯一岗位 ID、对应详情和分页终点实跑核验。数值是源站目录数，后续筛选会排除实习、兼职、已关闭等记录；真实运行关闭了 LLM，因此严格导入表可能没有可导入行，不能据此推断采集失败。

| 来源 | 企业 | 目录/唯一数 | 详情 | 覆盖 | 保存快照 |
| --- | --- | ---: | ---: | --- | --- |
| COM0066 | 宁德时代 | 27/27 | 27 | complete | `outputs/moka-validation-CATL-Huaqin-final` |
| COM0151 | 华勤技术 | 25/25 | 25 | complete | `outputs/moka-validation-CATL-Huaqin-final` |
| COM0215 | 阳光电源 | 208/208 | 208 | complete | `outputs/moka-validation-Sungrow-STO` |
| COM0268 | 晶科能源 | 22/22 | 22 | complete | `outputs/moka-validation-Jinko` |
| COM0289 | 申通快递 | 56/56 | 56 | complete | `outputs/moka-validation-Sungrow-STO` |
| COM0349 | 华东医药 | 75/75 | 75 | complete | `outputs/moka-validation-four-more` |
| COM0369 | 力勤资源 | 36/36 | 36 | complete | `outputs/moka-validation-Lygend-exact-retry` |
| COM0389 | 世纪华通 | 14/14 | 14 | complete | `outputs/moka-validation-Lygend-Digiloong` |
| COM0398 | 雅迪 | 210/210 | 210 | complete | `outputs/moka-validation-four-more` |
| COM0403 | 远东宏信 | 2/2 | 2 | complete | `outputs/moka-validation-four-more` |
| COM0404 | 禾丰食品 | 9/9 | 9 | complete | `outputs/moka-validation-HFSP-Sanhua` |
| COM0439 | 三花智控 | 95/95 | 95 | complete | `outputs/moka-validation-HFSP-Sanhua` |
| COM0478 | 大参林 | 154/154 | 154 | complete | `outputs/moka-validation-four-more` |

合计 933 条目录记录，各来源覆盖问题为 0。COM0369 的页面同时请求 `website/jobs/v2` 与 `website/jobs/v2/filterFieldsAggregations`；早期子串匹配误选后一接口，已改为完整路径精确匹配并重跑 36/36。源站的 `publishedAt` 为发布时间；`updatedAt` 不作发布时间。详情没有可分辨任职要求时原样保留职责，缺失字段进入报告。单城市地点按源站省市形成路径，多城市保留原文。COM0151 本轮目录主要是实习或兼职，仍保存真实目录和来源覆盖，但不作为全职校招输出。COM0349、COM0478 的移动链接公开跳转至同租户桌面页面；COM0398、COM0403 使用 `campus_apply` 路由，其 `site=campus` 的列表与详情均经逐站验证。

增量实跑 `outputs/moka-daily-validation` 中，雅迪 210 条与大参林 154 条目录仍完整核对，详情请求均为 0；雅迪 210 条均由公开发布时间判定在窗口外，大参林 148 条如此判定、6 条从既有快照复用。两站均无本日可导出岗位。这验证了列表日期与基线复用的请求节省；无日期记录仍按 SPEC-009 处理，不把本次发现时间伪装成发布时间。

离线汇总 `outputs/initial39-publication-20261012/岗位信息汇总.xlsx` 选取 39 个已验收来源的独立快照，按本次汇总时刻重新筛选，保留 6749 条十三列待补全岗位信息，其中 6124 条有发布时间，来源页有 39 行。汇总关闭 LLM，且分类、学历、地点、要求等字段有严格导入约束，故严格导入页为 0 行；这份表可作采集检查，不能直接作为完整可导入文件。各来源采集时刻不相同，见工作簿来源页；未重访所有旧站。

尚未启用的 Moka 入口：COM0172 是链接到多个 siteId 的首页门户，需遍历并去重后才能报告整家企业覆盖；COM0198、COM0202 的 `#/jobs` 路由未呈现可验证职位目录；COM0465 返回页面不存在；COM0500 的当前 `#/jobs` 页面明确显示无相关职位，且采用不同的旧接口。它们不能仅凭同域名沿用这十三站的绑定。
