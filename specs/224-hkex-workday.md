# SPEC-224 港交所 Workday 全租户公开目录

状态：已实现并真实验收；SPEC-156 固定 B 组 COM0486。

## 目标、输入输出与非目标

输入名录香港交易及结算所有限公司。官网 Careers at HKEX 明确链接 https://hkex.wd3.myworkdayjobs.com/HKEXCareerPage，正常跳转 /zh-CN/HKEXCareerPage。读取全部国家地区、公司、部门的无筛选公开目录及详情，按正式应届资格筛选，输出 Job/Scope、证据与 B 组汇总。覆盖包括香港、内地及伦敦等地区，不只采首页或 Graduate 标签。排除实习、兼职与未明确应届岗位，不登录、注册、申请或订阅。

## 真实协议

页面实发 POST /wday/cxs/hkex/HKEXCareerPage/jobs，BASE_QUERY 为 appliedFacets={}、limit20、offset0、searchText空，首total145。后页total0与按首total闭合的协议继承SPEC-222，仍逐租户核对列表末页、重复及详情身份。正常点击Senior DevOps Engineer，实际详情 GET /wday/cxs/hkex/HKEXCareerPage/job/Senior-DevOps-Engineer_R004531，jobPostingSiteId=HKEXCareerPage，jobReqId=R004531，externalUrl严格对应列表路径；timeType=Full time。必须核对标题、postingSlug、业务编号、租户和URL，不按职位名称去重。

网页标题有时已更新而postingSlug仍保留旧标题：例如R004268当前为(Senior) Systems & Testing Engineer，slug仍XMLNAME--Senior--Systems-Analyst…；只核验列表与详情当前标题一致，不能要求slug中的标题拼写等于显示标题。

## 正文与日期

多数正文包含Company Introduction、Job Summary、Job Duties、Responsibilities、Requirements或Job Requirements，尾部为平等机会说明、Location、Shift、Scheduled Weekly Hours、Worker Type。从明确岗位标题开始按明确资格标题拆分，不将公司介绍或隐私声明当职责；未可靠分节的正文完整保留并注明。地点优先详情结构化country/location/additionalLocations，不能把HK-TKO楼层代码猜成街道。公司主体仍为名录，hiringOrganization.name保留实际子单位。正文图片、附件和未核实外链报告缺口，空正文不自动排除为社招。

发布时间使用详情startDate，截止使用endDate；相对postedOn和官方网页更新时间不作发布日期。岗位正文若有更明确截止或与结构字段冲突，保留并核查，不静默覆盖。绝对日期缺失留空，未知字段进入公共待补全流程。

## 应届资格与官方项目核对

官方 Early Careers 当前三个Graduate Associate方向：Business Advancement、Regulatory Excellence、Technology Enablement，24个月项目；2025年8月至2027年7月毕业、少于两年全职经验、本科或以上、GPA3.5/Second Class Upper或相当资格。公开页面明确申请截至2026-10-25，Apply Now指向同Workday租户的jobFamilyGroup筛选。该过滤范围也包括暑期实习，不能将所有筛选结果纳入正式校招。

未带Graduate标题的岗位也可能明确接受fresh graduates，如系统分析/测试及衍生品交易运营岗位，必须完整读取混合目录。仅学历graduate、经验优先或trainee一词不算明确应届。正式全职合同岗保留合同期限原文，不等同实习或永久雇佣。所有应届事实来自本岗位详情或明确对应官方项目，不能给其他职位套通用校招要求。

## 失败与验收

复用SPEC-222分页/身份/增量/局部失败契约；未知目录0、重复页、缺详情、空正文、新附件、毕业生表述不明均保留partial。回放涵盖新租户实际详情、旧slug与新标题、明确应届且原文经验要求并存、正式合同岗、实习排除、多地点、日期及正文分节。完整UVsync/Ruff/ty/pytest后临时绑定实时采集，全目录覆盖与单源审计通过才启用。岗位数以实时证据为准，当前145不能硬编码为永久总量。

完整145目录实证有6条externalPath为/job/slug（省略地点段），对应externalUrl同样省略地点；仅本租户允许此形态，仍逐条核对slug/reqId/site/标题/外部路径。不能给此前仅验证/job/地点/slug的租户无条件放宽。145详情共有5条正式明确应届、3条实习。Graduate Associate仅一个R004464公开岗位，内部三方向/多个职能为候选人志愿，不拆造多个职位；截止2026-10-25与官网一致。正文3处链接Management Functions，实际页面为组织架构/职能介绍，不含独立岗位资格；另1处mailto为公开咨询地址，只保留文本不发送消息。仅允许这两个已验证目标，其余新外链失败。

上述6条详情同时没有country和jobRequisitionLocation字段，location为空，属于源字段缺失而非身份错配。仅本租户允许已核实的country字段缺省，保持地点空值；若国家字段存在但结构异常仍失败，不从公司地址猜工作地点。


## 验收记录

2026-10-18 13:27:40–13:30:36独立实采145全租户目录和详情，coverage complete、0覆盖问题；5正式应届有效/5信息/0严格/5待补全（均为地点需映射），3实习和137未明确校招排除。Graduate Associate保持单一R004464岗位且完整保留三方向，未拆造岗位。单源审计通过，正式绑定hkex-workday@1；该实现通过1290项全量测试及UVsync/Ruff/ty。

B44离线汇总于13:31:30，3966有效/3999信息/367严格/3632待补全，33家有有效岗位企业审计通过。B归档b10738cab138dceaad841f94.zip，SHA256 803aec1c8c66f792336c26862b6192e74c75211b21f2f695d32ba5d1d3abc073。A23/B44归档SHA和四份发布表逐字节一致。
