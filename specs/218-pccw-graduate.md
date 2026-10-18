# SPEC-218 电讯盈科与香港电讯毕业生招聘

状态：开发中，尚未真实验收。SPEC-156固定B组COM0395。

## 目标、输入输出与边界

名录电讯盈科有限公司，官网careers/index.page指向job.pccw.com/pccw/content/Graduate-Development-Programmes-v2/?locale=en_US。接入PCCW及HKT共同毕业生计划和两个Graduate Hiring职位栏目，输出公共Job/Scope、证据、筛选与岗位表。保留名录主体，招聘单位保留实际businessunit。专业招聘、实习、订阅和投递不在目标内；公开专业招聘样本仅验证相同站点列表与详情协议，不计校招验收。

## 完整范围与项目状态

两个站点首页分别明确新版计划和Graduate-Hiring_pccw/7939210、Graduate-Hiring_hkt/7939110。检查导航仍与这两类入口一致；旧版Graduate-Development-Programmes不是当前入口。两个新版计划都有Technology和Business流，技术五方向、业务七方向，逐页读取两个站点全部24项目页面，检查导航闭合、正文资格及邀请链接。两处菜单把Information Technology、Consumer Business写为空格路径，与其他菜单规范路径及当前激活标题核对后归一。项目底部隐藏的2024联系表单只记录、不访问；Digital Ventures三品牌介绍链接不是招聘目录。HKT和PCCW版本的邀请ID全部一致，正文除Media/Meida拼写差异外一致；同一方向不计两份岗位。

当前技术五方向指向/job-invite/58548/，业务七方向指向/job-invite/58547/。正常公开访问重定向至HKT职位1329370866和1329371066，og:title与流名称一致，页面明确“Sorry, this position has been filled.”。以12个项目方向为scope口径，只有全部页面与两个招满详情验证后计12 skipped_closed；不会把培养介绍导出为在招岗位。两邀请每次重新读取，不缓存永久关闭。项目旧隐藏2024关闭文字不是2026状态依据。

根页招聘时间表公开CSS图片fb27d656-fa7c-4102-8538-9.png已人工核对：申请Oct2025、面试Jan2026、offerMar2026、入职July2026，为流程而非具体发布/截止日期，不据此补日期。新项目、邀请ID或开放状态需重新验证公告展开关系；本版遇到这种变化报告unsupported_scope，不声称未来非零项目已验收。

## Graduate Hiring目录与公开详情

当前两目录均明确noresults/attention为空提示、noresults-message说明0，且无职位行；空白、身份不符、搜索筛选或推荐非零不能当零。未来非零目录采用已验证的同站SuccessFactors HTML协议：searchresults的data-row，桌面/移动重复链接一致、源数字postingID唯一、日期和地点从明确列读取。分页20行，paginationLabel为Results起止of总数；按真实Page链接逐页读取，首尾与总数守恒，最多100页。20+8的真实专业目录用于回放，不作为校园在招证明。

公开详情canonical中的postingID必须与列表一致；title、location和meta datePosted与列表核对。adcode为内部编号，不能替换postingID。详情已关闭可计skipped_closed；开放详情读取jobdescription，按独立英文Requirements标题拆分资格，其他正文保留职责，不猜补。datePosted显式UTC转上海时间，仅在与列表日历日期一致时接收；未知截止/详细地址留空，岗位类别来自正式Graduate Hiring目录，标题明确实习则排除。新附件/图片或未知资格分段明确失败，不漏读。

项目邀请未来开放时不套用专业招聘详情来虚构12方向展开；项目范围报告待验证，即使职位栏目有成功行也不视为整源覆盖成功。两门户出现相同postingID只有所有业务字段一致才合并输出，否则报告范围冲突。

## 失败、增量与验收

页面使用共同BrowserSession及预算。目录每次刷新，详情前before_detail，成功后remember，证据保留真实列表和详情。局部失败保留成功数据，认证/预算停止；重复页、变动总数、身份错误、未知项目导航、缺失正文不得计完整。

回放覆盖真实双零目录、24项目和两招满公告、20+8专业分页协议、开放详情日期/身份/正文、项目状态变化、重复短页/筛选、局部失败及增量复用。完整UV/Ruff/ty/pytest后临时绑定真实采集，核对目录、12方向和排除计数，审计通过才启用并加入固定B组。当前预期零岗位仍需正式实采证明，不计有岗位企业。
