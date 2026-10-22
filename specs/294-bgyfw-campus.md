# SPEC-294 碧桂园服务校园目录

状态：2026-10-22 真实全量验收通过；纳入 SPEC-277 最终 50 家审计。

## 目标与非目标

接入 COM0321 碧桂园服务官方 `bgyfw.com/cn/join.html` 的“校园招聘/了解更多职位”直链 Moka `campus-recruitment/bgyfw/47073/#/jobs`。以碧桂园服务集团招聘品牌纳入该官方站全部在招正式校招；保留源部门及项目，不把同集团地产开发公司的岗位合并。官网新锐力量为应届生管培项目。仅采未截止正式岗位，不纳实习和校园大使等非正式岗位。

## 输入输出与失败

已观察 Moka `/api/outer/ats-apply/website/jobs/v2` orgId=bgyfw、siteId=47073、site=campus、offset=0、limit=30、无筛选；2026-10-22 页面显示 17 结果。使用既有 Moka IV 解码契约遍历全目录、核对详情 ID/组织和项目字段。输出证据、快照、岗位信息、严格导入与待补全报告。入口、分页计数、正文或详情身份变化时报告 partial/blocked，不计入企业数；源字段缺失不猜填。

## 可验证验收

| 需求 | 验证 |
| --- | --- |
| 主体与入口 | 碧桂园服务官网校园按钮直链 Moka 租户和站点 |
| 全目录与岗位性质 | 无筛选 Category=campus、expected=listed=unique、terminal；排除实习/非正式 |
| 详情与交付 | 逐岗 ID/组织/标题和正文、coverage=complete、有效岗位正数、累计审计 |
