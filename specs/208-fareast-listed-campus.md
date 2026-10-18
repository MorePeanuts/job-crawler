# SPEC-208 远东智慧能源上市分支校园目录

状态：已实现并于2026-10-18真实验收；SPEC-156 固定 A 组 COM0470，hotjob-fareast-listed-campus@1。

## 目标与非目标

名录主体为远东智慧能源股份有限公司。旧 fe-nm.com 入口失效后，由大连海事大学企业招聘公告 https://myjob.dlmu.edu.cn/teachinOnline/view/id/148803 确认远东统一 Hotjob 门户 SU641d034b2f9d246c37bb1704。门户首页为远东控股集团，不能将集团全部岗位归上市主体。

输入 https://wecruit.hotjob.cn/SU641d034b2f9d246c37bb1704/pb/school.html。公开机构树根 0/9 为远东控股集团有限公司，55 条；其 0/9/39 子分支明确为远东智慧能源股份有限公司，52 条，含 11 个子公司节点共 40 条及上市公司直属部门 12 条。目录五页 12+12+12+12+7，与机构树逐层计数核对。纳入 0/9/39 及后代，排除母集团 3 条；不包含社招、实习、投递、登录及未在本统一目录发布的独立渠道。

## 契约、字段与输出

校园页面观察到 POST /wecruit/positionInfo/listPosition/SU641d034b2f9d246c37bb1704，表单 isFrompb=true、recruitType=1、pageSize=12、currentPage=1，无地区/单位/岗位筛选。业务 state="200"，pageForm.dataCount=55、totalPage=5。复用公共 Hotjob 分页、稳定总数、唯一 postId、末页和详情关联检查，不按相同标题去重。

listSearchTerm.data.orgList 给出完整带计数的层级。先校验根与上市分支名称和编码，再保存每个节点的名称及 positionsNum；逐条 orgCode 必须属于根，company 必须与最长已知机构前缀对应名称一致。部门不在机构树中时沿用其最近的法人节点。逐节点累计所有后代目录行，最终与每个 positionsNum 相等，不能只用根总数掩盖分支漏采。0/9/39 分支以外明确计 skipped_out_of_scope；出现身份漂移、重复节点或计数不符则覆盖不完整。

正常点击列表岗位进入 pb/posDetail.html?postId=列表ID&postType=campus 后观察 listPositionDetail 请求；每条详情须核对 postId、recruitType、postName、company、orgCode。公开详情 orgName 是部门，例如安徽电缆公司对应“西北片区”，输出 unit 同时保留公司和不同的部门。首屏三条“技术营销精英班（安缆-2027届）”属于不同部门和 ID，全部保留。

workContent 和 serviceCondition 使用公共正文处理；无明确要求小标题时保留原文并报告字段缺失，不猜分。education 使用原学历，workPlaceStr 保留原省市区文字，省市树只做无歧义映射；全国轮岗描述保留正文，不猜详细地址。publishFirstDate 为首次发布，publishDate 是页面“更新日期”，首次发布日期缺失时留空；endDate 保留明确下线时间。复用 before_detail/remember、公共筛选、分类补全与模板导出。

## 失败行为与验收条件

分页重复、提前空页、源总数变化、未知单位、树计数不闭合、详情身份漂移及访问拒绝均不得算成功或零岗位；保留已成功岗位和证据。实时零目录只有根和上市分支均有明确零计数且列表闭合才能接受。

回放验证多页含同名不同 ID、直属部门与子公司、母集团排除、每级计数、单位错配、未知分支、详情身份、首次发布缺失不取更新日期及详情局部失败。执行完整 UV/Ruff/ty/pytest 后临时绑定真实采集，核对 55 目录与 52 纳入/3 排除及每级计数，审计后启用正式绑定、加入 A 组快照并离线汇总发布。实际岗位筛选和最终表行数以采集报告为准，不以探测代替验收。


## 真实验收

2026-10-18 09:32:40–09:33:59实采collect-fareast，55目录/55唯一，读取上市分支52详情、排除母集团3条，每个机构节点的positionsNum全部闭合；coverage=complete且无覆盖问题。52有效/52信息/10严格/42待补全，通过expected-companies=1交付审计。无明确要求小标题的正文保留并警告；部分地点和学历缺口、一个多方向岗位分类不确定均待核验，不手工补齐。

989项测试和完整UV/Ruff/ty门禁通过，新增12项本站范围/身份/字段测试。正式启用绑定，快照加入固定A组，09:34:37离线汇总20家：1743有效/1773信息/106严格/1667待补全，14家有有效岗位审计通过，归档发布两份工作簿并逐字节核对。真实来源时间保留，不称其他快照重新采集。
