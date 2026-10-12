# Hotjob 公开校招适配器验收

2026-10-12，SPEC-012。六个租户的来源入口、`recruitType=1`、分页计数、唯一 `postId` 和对应详情均由 Crawl4AI 浏览器会话真实检查。以下是运行时的源目录数，并非所有记录都符合当日导出筛选条件。

| 来源 | 企业 | 全量目录/唯一数 | 详情 | 列表已过期 | 覆盖 | 保存快照 |
| --- | --- | ---: | ---: | ---: | --- | --- |
| COM0155 | 华夏银行 | 858/858 | 858 | 0 | complete | `outputs/hotjob-validation-COM0155` |
| COM0168 | 宁波金田 | 18/18 | 18 | 0 | complete | `outputs/hotjob-validation-small-final` |
| COM0345 | 广发证券 | 39/39 | 38 | 1 | complete | `outputs/hotjob-validation-GF-LiuGong-final` |
| COM0426 | 柳工 | 335/335 | 334 | 1 | complete | `outputs/hotjob-validation-GF-LiuGong-final` |
| COM0460 | 海天味业 | 59/59 | 58 | 1 | complete | `outputs/hotjob-validation-small-final` |
| COM0496 | 敏实 | 7/7 | 7 | 0 | complete | `outputs/hotjob-validation-small-final` |

合计 1316 条源目录记录，覆盖问题均为 0。验证运行刻意关闭 LLM，故 `exported=0` 或很少并不表示采集失败；分类和地点等导入约束会使记录进入待补全表。柳工有 5 个详情未给独立任职要求，程序留空并附字段警告。`publishFirstDate` 用于发布时间；`publishDate` 是更新日期。源站 `listSearchTerm` 有省市树时，单城市按树生成省/市路径；柳工未提供该树，地点保留原文。多城市仍不压缩为单城市。

使用当前代码另做六租户 `day` 验证：华夏 858、金田 18、广发 39、海天 59、敏实 7 均穷尽目录、未发出详情请求，保存于 `outputs/hotjob-daily-location-validation`；柳工 335 条同样零详情请求，保存于 `outputs/hotjob-daily-liugong-validation`。只有源站首次发布时间明确落在窗口外才跳过详情。本轮六站均没有最近一天的新发布岗位，因此两个 `day` 表格为空是筛选结果，不是空目录。五个有地点树的租户共 786 条单城市岗位获得源站省/市路径，其余保持原文。

未启用的同平台来源：COM0308（领益智造）原入口显示“系统正在维护中”；COM0362（宇通）是移动版 `mc/position/campus`，本轮接口明确返回 0 条，路径与表单也不同。二者保留 pending，不用 `pb` 适配器冒充支持。

离线汇总 `outputs/initial26-publication-20261012/岗位信息汇总.xlsx` 包含原 20 家与这 6 家的快照，在汇总时重新筛除到期岗位，共 5894 条信息行、13 列；“企业采集情况”页有 26 个来源及其原始采集时刻。汇总未重访源站，当前 `llm.enabled=false` 的离线配置让大多数新记录保留在待补全表，严格导入表只有 30 行。不能把该混合时刻工作簿视为 26 家在同一秒的实时快照。
