# SPEC-066 创维集团 2027 Hotjob 校招

状态：已实现并真实验收。日期：2026-10-14。归属 SPEC-050。

## 目标与非目标

接入 COM0252 创维集团有限公司的官方 `https://skyworth.hotjob.cn/SU668b8b251c240e2e76ea71d8/pb/school.html`。页面标示“创维集团 2027 届全球校招”，公开校园目录按 `recruitType=1` 给出 138 条（探测计数），记录中 `company` 为“创维集团有限公司”。纳入仍展示且未截止的正式校招，保留括号内业务单位和源分类。

不采社招/实习，不把首页宣传片、单个地区或热招职位当全目录；任何列表 `company` 不匹配名录主体时保留问题，不静默归入创维集团。

## 输入输出与失败行为

页面实际以表单请求同域 `/wecruit/positionInfo/listPosition/<suite>`，参数 `isFrompb=true&recruitType=1&pageSize=15&currentPage=1`，无附加筛选，响应 `pageForm.dataCount`、`totalPage`、`currentPage` 与 `pageData[].postId`。遍历到一致的末页，逐条核对 `recruitType=1` 和详情 `postId`；详情从同租户 `/positionInfo/listPositionDetail/` 获取。地点树来自 `/positionInfo/listSearchTerm/`。使用 `publishFirstDate` 而非更新日，按源 `endDate` 过滤已截止；正文与资格拆分遵循 Hotjob 公共实现。

输出证据化岗位和公共流程产生的两份十三列表。分页重复、总数变更、详情身份/主体不符、正文缺失、预算或网络错误保留已读记录和问题，coverage 非 complete。空目录完整不计入 50 家有岗位企业。

## 可验证验收条件

1. Hotjob 回放覆盖表单、首末页、详情关联、主体匹配、日期、空目录和失败保持。
2. 真实运行证明稳定 `dataCount=listed=unique`，详情或明示过期跳过与唯一数相等，`coverage=complete` 且正式校招有效数大于零。
3. 验收后再写正式来源与绑定、汇总归档遵循 SPEC-050。
