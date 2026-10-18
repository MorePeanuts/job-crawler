# SPEC-229 东方证券当前校园空目录

状态：实现及11项有效回放完成，全项目1365测试通过，等待独立实采验收。固定A组COM0500。

## 目标和范围

官网首页及“信息公开→公司招聘”均明确校园入口为Moka campus_apply/dfzq/4928；社会4927、日常实习5546独立。4928首页提到投行管理委员会实习生链接citiorient/4792，高校企业发布的2027届公告也明确实习，按既定正式校招范围排除。公司招聘栏目无其他独立正式校园公告或附件。公司名保留东方证券股份有限公司。

当前4928使用旧版`/api/outer/ats-apply/website/jobs`，而非公共Moka jobs/v2。原页面正常搜索空关键词后出现“尚无任何相关职位”，当前页面无筛选首屏及重新请求均为total=0、jobs=[]。只对已验证空目录契约实现；未来非零时明确报unsupported_scope，保留源总数，不能假装已有详情支持。

## 输入输出和契约

规范入口`https://app.mokahr.com/campus_apply/dfzq/4928#/jobs`。实际POST JSON为limit15、offset0、siteId4928、orgId=dfzq、site=campus、needStat=true，无其他筛选。使用本轮window.TurboApply.data.aesIv与响应公开解码格式，复用Moka.decode，不记录或复用历史解码参数。

输出独立campus scope expected/listed/unique/details皆0，terminal在两次有效API响应和页面明确空状态同时确认后设置。业务code=0/success=true、jobStats.orgId=dfzq、total整数0、jobs空数组必须同时满足。源网站主体、页面校园入口及请求无筛选必须验证。零有效岗位可以完成该来源当前支持范围，但不计有岗位企业数。

## 失败与验收

错入口、非校园、过滤参数、业务失败、总数/行不一致、页面仅空壳、未知响应结构均partial/blocked；非零目录显式unsupported_scope。无需登录或提交申请。测试上述边界和公开解码复用。完整UVsync/Ruff/ty/pytest通过后用独立状态库真实采集、audit通过，再正式绑定并离线汇入A组。当前不写零完成结论。
