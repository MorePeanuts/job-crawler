# SPEC-162 中国石化校园招聘

状态：已实现并通过完整实采和只读审计；SPEC-156 B 组 COM0003。

## 目标与非目标

完整遍历 job.sinopec.com 当前校园招聘的招聘单位和招聘岗位。覆盖优培计划及所有板块，不以首页精选岗位代替全量。招聘单位保留源字段，企业导出名使用名录主体。只读公开目录，不登录、收藏或投递，不采社会招聘。

## 观察契约与输入输出

入口 `/#/school/recruitmentPositions` 默认展示招聘单位。POST `/api/upgrade/homepage/selectYpList`，随后通过页面“招聘岗位”标签观察 `/api/upgrade/homepage/selectPositionList`；两者无筛选请求均为 page=1、limit=20、keyword=""，分页从 1 开始。响应 code=S000000，data.records/total/size/current/pages；初始单位 132、岗位 1234。不得沿用首页 panelId 精选筛选。

单位稳定身份 jobId，deptId 对应岗位 deptCode，postNum 是职位条数而非人数。完整读取两类目录并核对单位岗位计数、唯一身份和元数据。详情路由 `/#/school/recruitmentPositionsDetail?postId=<id>`；本轮点击详情使用列表全文，无独立详情请求。岗位 id、jobPosition、deptName、workAddr、educationNorm、positionType 对应身份、名称、单位、地点、学历、分类候选；specialtyNorm/foreignNorm/otherNorm 为专业、外语和其他要求。timeEnd 为截止。源站无发布时间和独立职责字段，保持为空，不把截止、发现时间、职位名或要求冒充职责/发布日期。公共流程分类并导出。

## 失败行为与验收

残留关键词/单位/板块筛选、业务失败、总数或页码变化、重复身份、提前空页、未知单位或单位计数不闭合均标记覆盖失败并保留已读岗位。正文必需字段缺失按行记录，不静默忽略。

离线测试覆盖两类目录分页、全文与日期缺失、重复页、单位身份/数量不符、业务失败及筛选拒绝。临时绑定完整实采并检查所有单位、岗位范围和导出数量，运行只读审计后启用。若实时目录契约与本 spec 不符，先记录证据并修正规范，不绕过覆盖检查。
