# SPEC-199 大北农官方校园目录

状态：已实现并完成真实验收；SPEC-156固定B组COM0459。

## 目标与范围

接入北京大北农科技集团股份有限公司官网`https://www.dbn.com.cn/`页脚“招聘官网”直接指向的Hotjob租户`SU66ab37a71c240e2e76256280`。门户介绍明确上市代码002385；校园招聘（应届生）与社会、高端人才、实习生栏目分开。输入为`https://wecruit.hotjob.cn/SU66ab37a71c240e2e76256280/pb/school.html`，输出为该校园门户完整目录的岗位、原始实际招聘单位和证据，按公共规则导出未截止正式岗位。

范围为官方统一校园门户，包括分子公司及河南区、湖北区、辽宁区等区域单位；这些区域名称保留原文，不推断其法人。门户没有组织筛选树，不凭组织编码前缀不同就删除目录行。官网直接链接与招聘门户上市主体介绍共同证明入口归属；不声称各公司所有独立渠道均已覆盖，不将门户单位名称解释为经审计的合并报表范围。非目标为其他招聘栏目、登录、投递及报名。

## 已观察契约

公开`listPosition`表单为isFrompb=true、recruitType=1、pageSize=12、currentPage=1，无其他筛选。state=200，pageForm给出dataCount、totalPage、currentPage、pageSize和pageData。2026-10-18探测完整五页12+12+12+12+2，共50个唯一postId；总数和页码必须闭合，不把50硬编码为恒定值。地点树来自同租户listSearchTerm的provinceList，无orgList；多城市保留原文。

详情正常打开`pb/posDetail.html?postId=实际ID&postType=campus`，观察同租户listPositionDetail并复用表单请求。校验postId、recruitType、postName、orgCode和招聘单位与对应列表一致；保留workContent、serviceCondition、education和workPlaceStr。未知字段不猜填。实际样本业务精英首次发布2025-12-22、更新2026-10-15、截止2026-04-09，证明更新不能表示首次发布或有效在招。

发布日期仅取publishFirstDate；缺失保留未知，禁止回退publishDate。截止取endDate，长期招聘标志不覆盖实际明确截止；探测24条未截止、26条已截止仅作开发预期，最终以适配器实采为准。过期行保留列表证据并计skipped_expired，不读取无用详情。其余使用before_detail/remember增量钩子。

## 失败与验收

业务失败、局部筛选、页码/总数/唯一身份矛盾、详情标题或单位错配均明确失败并保留成功记录；空页面不等于零目录。目录变化重新核验，不能静默删除异常行。

复用Hotjob分页、重复页、零目录和增量公共测试，新增本站回放验证首次发布时间缺失不采用更新、近期更新但已截止的行只保留列表、区域单位保留、详情公司/编码/标题错配产生partial。完整质量门禁后临时绑定全量采集；50目录或实采新总数必须闭合，逐来源coverage=complete和交付审计通过后才正式绑定、加入B组快照输入。记录有效、信息、严格与待补全数及真实采集时间。

首轮真实采集发现两条详情orgName是财务综合室/商南场办室等部门名称，而company与列表公司一致，postId、postName、orgCode均匹配。公司身份以company严格匹配，orgName若不同且非空则作为所属部门与公司一起保留，不能仅用部门替代实际招聘公司。首轮collect-dbn因误将部门当公司而partial，不加入汇总；修复后须重新全量验收。

2026-10-18 07:42:10至07:42:40实采collect-dbn-fixed，50条唯一目录、24详情、26已截止，coverage=complete且交付审计通过。24有效/24信息/4严格/20待补全，源字段缺失和多城市保留，不猜填。872项测试、UV/Ruff/ty完整门禁通过；正式启用hotjob-dbn-campus@1，加入固定B组。首轮失败快照仍保留、不参与汇总。
