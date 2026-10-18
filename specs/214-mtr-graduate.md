# SPEC-214 港铁2027毕业生发展计划

状态：计划；SPEC-156固定B组COM0310，mtr-graduate@1。

## 目标、非目标与输入输出

接入官网 https://www.mtr.com.hk/graduate-development-programme/index.php 的完整毕业生计划目录，关联页面实际指向的Taleo公开招聘公告260000UY。输入为名录“香港铁路有限公司”，输出8个独立计划Job、公告和计划Scope、字段证据与两类工作簿。保留名录公司名及英文计划名称，不把宣讲、实习、活动报名或一般社招纳入本毕业生项目，不登录、不投递、不登记宣讲会、不调用报名表单。

当前为2027 Graduate Recruitment，页面明确8 different programmes available。sectionOpportunities的8个按钮与8个.opportunities-modal一一对应；按钮名称、modal内独立培养内容和资格构成计划，Taleo一个公告统一开放最多3个计划志愿，不重复额外输出公告岗位。source_key以招聘公告ID及modal ID组合，不以标题或列表序号作为身份。

## 已观察契约与字段

计划modal为公开HTML，按钮data-bs-target指向相同页面内的modal1/2/3/4/6/8/9/10。modal-body h3有计划全名，去掉管理/专业方向前缀、括号缩写和Programme后必须与按钮名称匹配；只允许and与&等已观察的排版差异。正文按唯一的We are looking for:分成培养职责和资格，保存段落及列表内容；附件/图片/未知正文结构不能静默忽略。计划集合、声明数量、modal集合与公告列出的8项需完全一致，新增或缺失不应继续宣称完整。

官网两个Apply Now指向 https://careers.mtr.com.hk/careersection/mtr_graduates_apply/jobdetail.ftl?job=260000UY&lang=en ，该页为无需登录的公开描述，允许只读打开；不点击投递。核对公告ID、2027届标题、Job=Graduates、Schedule=Full-time、计划名称集合和回链官网。公告Job Posting为15/Sep/26 09:03:18 AM，Closing Date为27/Oct/26 11:59:00 PM。官网sectionApplication同时明确15 September 2026 09:00 HKT至27 October 2026 23:59 HKT；该开始时间是报名开始，不替代实际发布时间。截止与Taleo日期时间按HKT核对到分钟，保留Taleo源秒数。页面维护窗口日期不得被误作截止。

公共资格采用公告的final-year university students and recent graduates及官网FAQ关于最近毕业生不超过3年经验的明确回答，追加到各计划资格并标明公共来源。专业、轮岗和流动要求以各modal为准，不把某个计划的要求套给其他计划。没有独立学历字段，保留原文交公共学历流程，不硬编码本科。未给明确工作地点或详细地址，保持空；Hong Kong宣讲地点、页脚地址和轮岗可能性不是岗位工作地点。

## 失败、增量与验收

公告/计划ID、标题、类型、年份、日期、计数或范围不符、登录/网络错误、缺正文、附件或未知弹窗都明确partial/blocked，保留已采集内容；空页不是零岗位。源站明确截止由公共筛选处理，不通过采集日期重开岗位。公告整体与目录每次实时核对，各modal使用公共增量钩子复用已经核验的详情；指纹包含公告日期、标题、公共资格及本计划正文。

回放须覆盖8计划及公告匹配、重名/缺失/额外modal、标题别名关联、职责资格边界、类型和日期错配、维护日期干扰、无地点、不伪造学历、局部正文失败及增量复用。按完整UV/Ruff/ty/pytest门禁后临时绑定实采，核对8计划唯一身份、有效/信息/严格/待补全及单源审计，再启用正式绑定并加入原B组离线汇总。未通过实采不计完成，不因字段缺失虚构信息。
