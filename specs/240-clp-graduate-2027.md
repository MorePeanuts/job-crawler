# SPEC-240 中电控股 2027 见习工程师计划

状态：已实现并于 2026-10-20 真实验收。属于仍在进行中的 SPEC-238，COM0228 已启用正式绑定。

## 目标、输入与非目标

采集中电控股有限公司官网 `https://www.clpgroup.com/en/careers/working-at-clp/graduate-trainee.html` 的 2027 Engineering Graduate Trainee Programme。官网职位页明确最终学年学生或毕业不超过三年者可申请，截止 2026-12-06，Apply Now 链接 `https://e.clp.com.hk/gt2027` 正常跳至 Oracle 公开职位 1125；Oracle 详情的 LegalEmployerId 对应 CLP Holdings Limited。

输入为官网当前项目正文、申请短链接公开跳转及 Oracle `recruitingCEJobRequisitionDetails` 详情。仅接入这个正式大学毕业生项目，不把官网有经验社招、技工训练、实习或 Oracle 全职位搜索中的其他公司职位算入。不得点击投递、接受 Cookie 或创建账户。

## 输出与契约

- 核对官网主体、项目名、唯一 `gt2027` Apply Now 链接和公开截止日期；官网项目正文没有直接标注 2027 年份，以申请链接及 Oracle 职位标题共同确认。Oracle 跳转仍指向同站点职位 1125，详情 ID、标题、Programme、Full time、LegalEmployerId 及公开状态一致。
- 当前范围是一项项目岗位，以 Oracle Id 为稳定源键。职位正文按明确的 “Who are we looking for?” 标题拆分职责及资格，不把投递说明填入要求；学历最低为学士，地点仅保留源站 Hong Kong 原文。发布时间取 Oracle `ExternalPostedStartDate`，截止取 `ExternalPostedEndDate`，保留源时区；不使用网页修改时间。
- Oracle 详情的 `ExternalPostedEndDate` 应与官网公开的 2026-12-06 截止日期一致。源页面出现额外正式毕业生项目时必须扩展范围，不能仍宣称整家公司校园岗位完整。

## 失败行为和验收

入口、项目数、申请链接、Oracle 详情身份或日期矛盾时输出 partial/blocked，不将范围缩成页面上一个可见卡片。缺正文、要求或发布时间时保留已读取信息并报告。回放测试覆盖主体与项目身份、唯一链接、跳转关联、日期和正文拆分、异常及局部失败；临时绑定实采后核对 source count=1、有效=1 和完整 coverage，方可进入本批汇总。
