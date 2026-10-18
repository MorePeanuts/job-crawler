# SPEC-228 百济神州2027应届及全球公开招聘

状态：已确认入口，调查中；尚未实现或验收。SPEC-156固定A组COM0384，不增加已完成数。

## 目标与非目标

将原2024前程无忧入口更新为官网当前实际招聘体系，保持名录公司名“百济神州有限公司”。中国官网https://www.beonemedicines.com.cn/同时提供Moka中国区和Workday全球入口；Moka社会招聘98934的“更多→校园招聘”正常跳转campus-recruitment/beigene/98935，明确“2027校园招聘/应届生职位”，实习单独指向118622。全球官网careers也直接指向https://beigene.wd5.myworkdayjobs.com/en-US/BeiGene，当前无筛选273职位。

覆盖上述中国2027应届目录全部单位及全球公开目录中的明确正式应届职位；不得因中国区入口可读就忽略全球目录，也不把社会招聘、实习、临时外包或人才意向登记当正式校招。官网Contingent Worker Opportunities说明受雇Magnit Global的合同人才，与百济正式招聘分开排除。高校2027公告指向的微信文章当前要求环境验证，未绕过；以官网实际可公开浏览招聘目录为采集来源，不靠搜索缓存填岗位。

## 输入输出及待核对契约

输入COM0384及官网当前校园入口；输出公共Job/Scope、证据、A组快照。Moka orgId=beigene/siteId=98935，沿页面真实无筛选jobs请求验证分页总数、详情ID和当前页面响应解码参数后复用公共Moka契约。98934是社会招聘、118622是实习；2027专题是否额外提供独立职位/附件须核对，不静默忽略。

全球Workday列表POST /wday/cxs/beigene/BeiGene/jobs，实际payload appliedFacets={}、limit=20、offset=0、searchText=''；total与唯一externalPath闭合。实际详情GET为API前缀+对应externalPath，核对jobPostingId、jobReqId、jobPostingSiteId=BeiGene、标题、公开URL、canApply及posted。目前第一条样本Full time，startDate为绝对源发布时间、endDate未提供；不能将postedOn相对时间写成绝对日期。完整目录末端、正文分节、媒体链接、招聘类型和地点缺失边界仍需全量研究后确定。

两个平台使用命名空间区分源身份，并对重复岗位核对实际编号/单位/工作地，不能只按标题去重。每个子目录独立Scope，任何一个分支不完整时整来源partial；保留已成功岗位。逐详情调用公共增量钩子，未提供日期不凭空当旧岗位跳过。公共deepseek-flash分类/必要学历辅助，不能强填学历/类别/地址满足模板。

## 失败行为与验收条件

入口错配、分页循环或漂移、详情身份错配、缺完整职责资格、未知状态/时间类型/媒体附件、登录或访问验证均明确报告，不返回空成功、不硬编码本次273为未来总量。不提交申请、注册、简历或验证码。

完成两平台完整目录研究与去重边界后实现；针对非零分页、详情关联、来源隔离、局部失败保留、日期、正式应届/实习识别及增量复用编写有效回放。UVsync/Ruff/ty/pytest通过后独立状态库真实采集，coverage complete及audit_delivery通过才启用绑定，并重新离线汇总A组；A/B冻结分组不变。
