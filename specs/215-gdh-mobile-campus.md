# SPEC-215 粤海集团移动校园招聘全目录

状态：计划。SPEC-156冻结A组COM0324，拟实现gdh-mobile-campus@1。

## 目标与边界

输入名录广东粤海控股集团有限公司。旧gdh.zhiye.com校园页明确给出gdhchina.m.zhiye.com移动入口，经校园导航xzsy.html的图片按钮到segment.html?jc=2，再到全部职位recruitment.html?c2=3_-1&k=all。覆盖集团总部、水务环境、城建运营、食品生物、产业投资五板块的全部校园岗位；公司导出名用名录，招聘子单位保留原字段。排除实习、社招。不登录、收藏、投递或提交简历。

## 公开目录及分页

页面请求GET /JobAd/_SearchJobAd，参数in=1、jc=2、ky空、c1=-1、c2=3_-1、c=-1、d=-1、pi=1、ps=1000。校园类别与无筛选条件必须逐次验证，不将移动首页社招当校园。当前RowCount140，但服务端单页上限100；网页滚动仍请求ps1000，不能完整取得140条。独立只读验证ps100时第一页100、第二页40，第三页DataResult空且RowCount0。故适配器以100分页，每个非空页RowCount一致且应有页长，ID唯一，累计必须等于声明总数，再验证下一空页。PageCount/PageSize为0、CurPageSize为1，不充当可靠分页元数据。总数变化、重页、短页或末端非空均失败，不以第一屏100条计完成。

JobAdId为唯一身份，TenantId固定603372，CategoryId必须2，KindId=1全职/3实习。校园目录可能含实习（当前客服专员），按工作性质排除，不按标题猜测。各岗位Categories的TypeId3招聘区域及Department/OrgName保留，明确的全部板块入口覆盖下属单位，不根据水务首屏推断集团仅有水务。

## 详情与字段

页面公开详情details.html?adId=<JobAdId>&jc=2，由目录a.item给出，实际调用/JobAd/_Info?adid=<JobAdId>&in=1。核对TenantId、JobAdId、JobAdName、Kind、Department、Categories招聘区域及PostDateStr。源详情Category=0、IsEmpty=true等默认字段不能误当社招、空记录或下架；校园类型来自已验证列表与页面标签，身份和正文必须完整关联。

DutyStr与RequireStr分别职责和资格，附件/图片未解析需明确失败；DegreeStr、LocName、DetailAddress保持原值，SalaryName仅保留于原始证据（现有岗位模型没有薪资列）。日期用PostDateStr，核对列表ToPostDate，不采用CreateDate/ModifiedDate/ChangeDate。EndTimeStr为“-”且列表ToEndDate为2222-02-02时代表未知截止，导出留空；明确截止则需日期一致。不猜填详细地址，列表县区不提升为城市。没有投递链接时保留公开详情页，不请求投递接口。

## 失败、增量及验收

入口、范围、身份、分页、附件或访问问题保留partial/blocked及已成功岗位，不能转零。公开零必须有完整目录与明确空状态；初始空白不算零。目录每次实读，详情使用公共before_detail/remember，列表指纹含业务字段，日期可靠时允许公共窗口预筛选。预算沿用公共配置，分页另设硬上限。

回放覆盖100+40+空页、服务端虚假分页元数据、首屏上限、重复/短页/变总数/未知类别、不同板块子单位、实习排除、ID/租户/单位/日期/正文变化、局部失败与增量复用。完整UV/Ruff/ty/pytest后临时绑定全量实采，核对140目录（以实采实时总数为准）、正式/实习计数、独立详情、信息/严格/待补全与审计。通过后才启用、加入A组快照并更新汇总；当前只是探测，尚未计完成。
