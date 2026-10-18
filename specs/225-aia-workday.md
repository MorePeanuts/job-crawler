# SPEC-225 友邦 Workday 公开招聘目录

状态：已实现并通过独立实时采集验收，正式绑定已启用；SPEC-156 固定 B 组 COM0094。

## 目标、范围与输入输出

友邦集团官网公司职位入口已实际链接 https://aia.wd3.myworkdayjobs.com/External，页面正常重定向到 /zh-CN/External。读取全部国家、地区与部门的无筛选公开目录及详情，保留名录主体、实际招聘单位和原始字段；仅明确正式应届资格进入B组岗位汇总。不能只采香港或首屏20条；不进入保险代理人注册、申请、个人资料、订阅或人才社区流程。

## 已验证契约

实际 POST /wday/cxs/aia/External/jobs，appliedFacets={}、limit20、offset0、searchText空；首总数1015，51页，最后15条，后续total0。正常点击Manager, Cloud Solution Architect，详情实际GET /wday/cxs/aia/External/job/Manager--Cloud-Solution-Architect_JR-71464-1，jobPostingSiteId=External，jobReqId=JR-71464，externalUrl与列表路径相符。复用SPEC-222的完整分页、首屏复核、唯一身份和增量规则；仍在完成全部详情核对，不能将1015列表视作验收。

/External与实际/zh-CN/External路径不一致会阻止导航恢复；应使用实际公开语言路径及已观察jobs端点，而非修改反爬身份或绕过站点限制。ready_endpoints业务成功后仍须核对全部字段。

## 原始字段与正文

详情timeType已观察Full time、Part time和空字符串；空值保留未知，不虚构全职。标题实习或明确Part time排除。日期只用绝对startDate/endDate，空日期留空；位置用country/location/additionalLocations，不能将香港市场岗位误当工作地香港（例如马来西亚团队支持香港市场）。保存实际hiringOrganization.name，不推断名录外主体。

正文常见About the Role、Roles and Responsibilities、Minimum Job Requirements、Job Requirements、Requirements以及中文岗位职责/任职要求。按实际明确标题拆分，从About the Role开始保留角色说明，末尾通用申请个人信息声明不当岗位资格；无法可靠分节时保留全文并注明。保留资格中的经验要求和应届例外原文，不把学历graduate或零经验自动等同校招。某Bancassurance Sales岗位同时写5年经验和欢迎fresh graduates，候选记录须保留该冲突，不声称免经验。

已观察泰国官方链接 https://www.aia.co.th/th/about-aia/privacy/candidate，实际为候选人个人信息收集声明，非岗位附件；仅将其作为已核实背景链接保留，不提交个人数据。其他外链、图片、附件或未知内容形态需核验，不能泛放行。

## 失败与验收

缺正文、跨租户、身份/路径错配、分页数量变化、重复、未知语言应届表述或新附件保持partial，详情失败保留已成功结果；认证或预算耗尽停止。增量详情前刷新完整列表，未知发布日期首次读取，不从相对postedOn推断时间。全量所有详情完成后再定最终应届数量；回放要覆盖实际混合语言正文、空timeType、支持市场与工作地点差异、实习、应届经验冲突、隐私链接白名单。完整质量门禁和独立实采审计通过后启用正式绑定及B组汇总；不能用研究缓存冒充正式实时采集。

JR-69187的Fresh graduates明确资格位于角色说明We welcome段，后面的Job Requirements未重复该句。应届筛选须同时核对已去除公司通用介绍后的角色说明与资格，不只扫描Requirements分节；两段原文均保留。

完整1015详情核对后：JR-6136采用/job/slug、缺country且location为空，正文完整；本租户允许已核实的省略地点/国家缺省，保留原始空值。JR-48678明确Fresh Graduate只在岗位标题，正文不重复，因此资格判定同时核对标题、角色说明和Requirements。JR-46698-1标题为Expression of Interest，属于人才意向登记；即使正文列出应届资格，也保留快照并排除正式招聘表，不将意向征集当成确定在招空缺。


## 实现进度

完整研究1015详情均可解析：970未明确应届、32实习、10明确正式应届、2人才意向登记、1临时/兼职。研究不冒充正式实采；aia-workday@1已实现并通过1298项全量测试及UVsync/Ruff/ty，正在使用独立状态库执行collect-aia，须等实时覆盖和审计结果才能加入B组与正式绑定。

## 真实验收

2026-10-18 13:36:45–13:57:33 使用独立状态库全量实采1015唯一岗位及1015详情，51页目录和首屏复核完整，coverage complete、零覆盖问题。保留导航恢复警告及原始证据，不将早期SPA空壳认定为零。10正式应届有效/信息、0严格/10待补全，1005其他范围排除；全部存在地点映射缺口，3条学历仍待补全（其中1条模型未提供有效原文引证，未强填）。单源审计通过。实现前1298项全量测试及完整门禁通过，后续建滔回归总1315项通过；加入B组汇总。

2026-10-18 13:58:04 B46离线汇总通过35家有效岗位企业审计并发布；归档948787a7bda698666d3fde57.zip与发布工作簿逐字节一致，A23原表及归档同时复核通过。
