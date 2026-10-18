# SPEC-217 澳门博彩控股公开混合职位目录

状态：已实现并真实验收。SPEC-156固定B组COM0492，sjm-public-jobs@1。

## 目标与非目标

澳门博彩控股官网Human Resources明确指向sjmjob.com的Recruitment。接入其澳娱综合SJM Resorts公开Jobs全目录，覆盖澳门半岛、氹仔/路氹城、香港及全部部门，核对公开正文中明确的应届招聘资格。输入名录澳门博彩控股有限公司，输出公共Job/Scope、证据和筛选报告；公司用名录，招聘单位保留SJM Resorts及部门。不把社招、实习、仅学历或无经验门槛推断为正式校招。不登录、注册、订阅或投递。

## 目录、分页与身份

官网https://www.sjmholdings.com/en/human-resources的Recruitment链接为https://www.sjmjob.com/Home/SetLanguage?culture=en-GB&returnUrl=%2FHome。正常读取此公开语言入口建立英文页面，然后读取/Jobs?page=1&sortedBy=Apply%20Date。排序名Apply Date只用于源站排序，日期业务语义由页面Post Date及中文刊登日期确定。

无筛选状态由locationFilter和departmentFilter各自唯一All选中、空searchBar共同验证。两个/Jobs分页表单含相同page下拉，选项连续1至末页、选中页正确、Next/Previous禁用状态与页码一致。当前21+21+2共44唯一岗位；每个非末页21条，末页1至21条。页数变化、重复ID、短页、空白、缺分页或错误语言不能计零。无真实空目录样本，本版遇到无卡片须报告需核对空状态，不能假定成功。

.post卡片内两个.view-detail链接与申请链接ID必须一致，/Jobs/<id>为只读详情，申请链接仅用于核对、不访问。保存标题、Department编码及文本、Location编码及文本、刊登日期。所有地区及部门均来自完整无筛选目录，不只读主页部门推荐。

## 详情、校招边界与日期

公开详情dl.dl-jobs-detail顺序为Position、Department、Working Location、Post Date、Requirements、Responsibilities。核对标题、部门/地区编码、文本和日期与目录一致，通过/Jobs/Apply/<id>的公开链接核对ID。正文图片、附件、iframe或结构变化必须明确失败，不能忽略。

读取全部岗位正文后确定work_type：实习标题或明确实习招募为实习；标题明确Graduate Trainee/Graduate Programme等，或资格明确fresh/recent/new graduates、graduates welcome等应届招募才为校招；其余为“未明确校招”，不声称均为社招。graduate只用作学历、工作经验为优先条件、N/A均不构成应届身份。含新的校招相关表述但无法按已验证语义确定时应报告范围待核对，不静默推断。此边界与当前默认正式校招一致，不是采集全部社会招聘。

日期解析DD/MM/YYYY的Post Date为ISO日期，未知截止留空，不把排序字段、采集时间或招聘计划届别当发布日期。Requirements/Responsibilities分别保持正文；N/A按源缺失报告，不虚构学历、地址和职责。Working Location保留原文，人才招募中心地址不是工作地址。只有公共筛选判断校招且未截止的岗位进入岗位表，全部混合岗位保留于快照及排除报告。

## 增量、失败与验收

目录实时刷新，详情前before_detail，核对成功后remember；列表指纹含ID、标题、单位、地点、日期。全部范围计数采用混合目录同一口径，details/reused/可靠窗口跳过与unique守恒。详情局部失败保留其他岗位，认证/预算错误停止；不以部分详情成功声明完整。

回放覆盖三页末端、身份和语言错配、页数变化/重复/短页、各地区、缺失资格、学历graduate非校招、合成应届及实习资格、日期、附件、局部失败和增量全量刷新。合成应届仅验证筛选边界，不冒充真实在招。完整UV/Ruff/ty/pytest后临时绑定实采44条（以实时目录为准），逐项核对排除原因与表格，通过审计后启用并加入B组汇总。当前探测44条无明确应届资格，不能在实采前称已验收。

## 验收记录

2026-10-18 11:46:11–11:47:06，collect-sjm真实读取21+21+2、44唯一详情，coverage complete、零问题/警告。44条均未明确校招，公共筛选以outside_campus_scope排除，信息/严格/待补全均0；原始44岗位仍保留于快照及排除报告，审计通过。25项本站回放及全量1184项、UV/Ruff/ty通过。当前真实验收没有合格校招岗位，合成应届回放不作为实际岗位计数。
