# SPEC-043 建发、美的、快手公开完整正文目录

状态：已实现并验收。依据：`outputs/batch6-follow-probes` 的 Crawl4AI 页面、原始请求和响应。

## 目标与范围

- COM0032：建发原入口导航“应届生招聘” `/extcampushr/graduates`，GET `queryJobBasebyyjs`。响应 `result.records` 已含逐岗位职责、要求、学历、地点和发布时间；按 `current/size/pages/total` 核对完整目录。来源范围为该入口公开的建发股份应届招聘，保留实际招聘主体，不扩展至无入口证据的其他集团业务。
- COM0057：美的 `/schoolOut/post`。从公开 `project/list` 枚举 status=1、employementCategory=1 的正式应届项目（本硕、博士），排除 employment=4 实习。POST `position/list` 的 projectRuleId 来自项目目录；逐项目独立分页、计数和唯一键。正文位于 `projectPositionDto`，地点为 `workplaceDtoList`；若发现列表省略正文或详情另有岗位分支，必须补充详情后验收。
- COM0174：快手官网“应届招聘”当前指向 2027 应届项目 `20271779425607`。POST `positions/simple`，请求只带项目代码和分页，目录返回完整 description/positionDemand；从公开 dictionary/batch 校验项目名称、岗位类别、工作地点。逐页核对 total/pageNum/pages/isLastPage；不读取实习项目。releaseTime 为发布日期，updateTime 不参与时间筛选。

## 输入输出及失败行为

输入为明确绑定的名录来源；输出 Job、Scope、逐请求证据、标准交付报告及十三列表格。建发岗位使用源 id；美的使用项目 ID+positionId；快手使用 code。申请入口若没有核实的逐岗位公开永久链接则保留可定位目录，不编造 URL。源站未给的发布时间或截止日期留空。

业务失败、总数变化、重复页、缺少正文、请求项目与响应不符、错误页码均报告 partial；零岗位只有有效项目目录和零计数成立时接受，但不计入 SPEC-042 的 50 家有岗位企业。

## 验收

回放涵盖多页、跨项目、排除实习、重复页、总数变化、错项目和原字段映射；每家当日全量实采核对源总数与 unique/details。通过 Ruff、ty、pytest，真实采集结果独立记录。

## 验收记录

2026-10-13 真实范围与数量见 [50家交付验收](../docs/adapter-batch6-acceptance.md)。相关离线合同见 `tests/test_batch6_contracts.py`，原平台测试保留；完整门禁365项通过。正文、截图或空壳探测不算实采验收，绑定仅包含完成的来源。
