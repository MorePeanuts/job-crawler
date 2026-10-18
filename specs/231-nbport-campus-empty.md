# SPEC-231 宁波舟山港校园及公告空目录

状态：实现、15项回放及三范围独立实采审计通过。SPEC-156 固定 B 组 COM0438 正式绑定，当前零校园岗位。

## 目标和边界

浙江师范大学就业网公司人力资源部发布的2026招聘公告明确链接 `https://nbport.m.zhiye.com/#/jobs`。当前北森校园频道为 `/#/jobs?jc=2`；GetCompanyInfo 返回 Title=宁波舟山港股份有限公司、TenantId=111157、PortalId=11115700，Alice 为浙江省海港集团，不能因此改公司导出名。FunctionMenu 明确社会1、校园2、实习3和招聘活动/动态入口。

本次覆盖校园目录与两个公开公告栏目，三者均当前明确为空；不将网页加载失败算零。仅实现已实证的零目录合同，未来有岗位、活动或公告时返回 unsupported_scope，待进一步核对正文和分页。

## 输入输出和请求契约

精确来源 URL `https://nbport.m.zhiye.com/#/jobs?jc=2`。校园页正常公开 GET `/LightBoltAPI/JobAd/List`，jc=2，rewardjob=0，From=/jobs?jc=2，其余 jobads/code/c1/c2/ky/c/ct/o/shareid/shopid 均空。响应 Code=200、RedirectUrl=null；Data.pi=1、ps=10、jc=2，各筛选为空；Data.data.RowCount/PageCount/PageSize=0、CurPageSize=1、DataResult=[]。页面明确“这里什么都没有...”。

活动 `/#/activity` 与动态 `/#/micro` 分别触发 `/LightBoltAPI/RecruitEvent/List?pageIndex=1&pageSize=10`、`/LightBoltAPI/Message/List?pageIndex=1&pageSize=10`，Code=200、Data=[]及相同可见空状态。每个范围均保存本轮页面触发响应和一次无筛选重复 GET，全部通过才 terminal。输出三个 expected/listed/unique/details 均0的 Scope，无 Job，不计入有岗位企业。

## 失败和验收

精确入口、公司主体或租户错配，业务/结构失败，隐藏筛选，总数与行数矛盾，二次查询变化，非空目录及缺少可见空状态均不可验收零。使用公共会话、预算和证据；不登录、不申请、不复用会话密钥。测试正常三范围、筛选、主体、响应、非空和局部失败保留。UVsync/Ruff/ty/pytest 后临时绑定独立实采，交付审计通过才更新正式绑定并进入 B 表。

入口依据：https://career.zjnu.edu.cn/campus/view/id/870514 。研究证据位于本批 nbport-current、nbport-activity、nbport-micro，不能冒充正式采集。
