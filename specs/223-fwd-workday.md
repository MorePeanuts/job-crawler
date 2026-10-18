# SPEC-223 富卫公开 Workday 目录

状态：已实现并真实验收；SPEC-156 固定 B 组 COM0417。复用 SPEC-222 公开目录协议，仅在本租户真实验证后启用。

## 目标与输入输出

官方 https://www.fwd.com/zh/join-us/ 明确链接 https://fwd.wd3.myworkdayjobs.com/zh-CN/FWDcareersite/。遍历该租户所有国家/公司/部门，输出名录富卫集团有限公司下的 Job/Scope 和独立 B 组汇总。排除实习、兼职及未明确应届的社会招聘；不访问投递、用户资料、人才社区写入接口。

## 实测契约

页面公开 POST /wday/cxs/fwd/FWDcareersite/jobs，JSON appliedFacets={}、limit20、offset0、searchText空；首总数210，11页20×10+10，后页total0，越界会重置首页。按首总数闭合且复核首页，不请求越界作终态。正常点击首个岗位，观察 /job/Assistant-Manager--Business-Development--Northern_JR-0028352；详情的jobPostingSiteId必须FWDcareersite，bulletFields包含真实jobReqId，externalUrl必须对应本租户加列表externalPath，标题及postingSlug一致。首屏仅一国或职位类型不能代表全集团。继承SPEC-222全部身份、分页、增量、异常契约。

详情 timeType 当前中文“全职”；确认其来源语义后按正式全职处理，不能要求英文值导致整站失败。招聘范围以正文明确 fresh graduate 等表述为准；合同期六个月但全职且非实习的岗位保留原合同描述，不虚构永久劳动合同。发布时间只取startDate，截止只取endDate，缺值空，不能拿相对postedOn或页脚年份替代。

## 正文解析与非岗位链接

本租户正文以 About FWD Group 开头，部分带地区公司简介。正文中的公司主页、保险监管机构统计来源与Talocity隐私政策链接仅是背景/隐私说明，不是岗位附件：仅允许逐个已观察的完整 URL 白名单，保留原文字；新外链、图片、附件必须阻断核查。不得打开Talocity进行画像或申请。

以实际明确标题 Job Summary、PURPOSE、The Job 等定位岗位部分；没有明确起点则保留全文并注明。The Person、QUALIFICATIONS / EXPERIENCE、Skills & Experience Required、Job Requirements 等分节后是资格；Privacy Notice及之后的隐私说明可从岗位字段去掉但仍保留原始证据。无法可靠拆分时保留完整原文至requirements，不伪造职责。Financial Solutions Consultant、Life Pricing Executive、Recruitment Partner等已有明确应届原文，完整目录结束前不固定最终数量。

## 失败与验收

缺正文、身份不符、目录数量变化、未知链接或新语言招聘范围需复核，保留成功记录及partial，不以无日期或无严格导入行误判零岗位。新租户回放须使用真实脱敏详情，覆盖中文全职、多个地区、公开背景链接白名单、资格分节/隐私尾注、实习排除、合同岗原文与日期缺失；复用分页及增量回放。全量质量门禁通过后临时绑定实时210目录/详情，审计complete才启用正式来源并离线汇总B组。实际数量变化按运行证据记录。

完整210详情进一步核对：日本目录【2027年度新卒】内定者 登録用明确仅供已获录用者登记，不是公开新招岗位，应单独排除；其他日本岗位福利段的“新卒入社時研修”不能作为应届招聘证据。限定这一已核对登记标题与正文双重匹配，未来其他新卒招聘需重新确认，不能一律忽略。


## 真实验收

2026-10-18 13:10:27–13:15:10独立临时绑定实采210目录/详情，coverage complete、0覆盖错误；正常空壳恢复警告保留。189未明确校招、17实习、1内定者登记排除；3有效/3信息/0严格/3待补全，均因境外location_needs_mapping留待核验，不虚构中国地址。单源expected-companies=1审计通过；24项Workday回放、1288全量测试与UVsync/Ruff/ty通过，正式启用fwd-workday@1。

B43离线汇总于13:15:49，3961有效/3994信息/367严格/3627待补全、32家有有效岗位，审计通过。A23与B43两份归档SHA和4份发布工作簿字节校验通过。B43归档d554b05e00706a9cdbd480d7.zip，SHA256 3c2257af30c6a8eeb796697e70cf9f728c461d104dd194f1d41a5c9c55f01975。
