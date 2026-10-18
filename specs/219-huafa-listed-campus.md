# SPEC-219 华发股份校园招聘双渠道

状态：开发中，尚未真实验收。SPEC-156固定B组COM0223。

## 目标与范围

接入珠海华发实业股份有限公司独立Hotjob校园门户sc.hotjob.cn/wt/huafa/web/index/campus，联合核对华发集团现行campus.51job.com/huafa/明确指向的SU67b2e3bb1eb80555b7a457f7校园目录。官网cnhuafas.com主体、600325与独立门户逐岗位orgName一致。输出名录主体Job/Scope、证据和最终岗位表，不把母集团其他上市主体的岗位归入华发股份，不采社招和实习，不操作申请/注册/推荐。

## 独立门户已验证契约

复用ClassicHotjobCampus GET完整正文协议。实际列表/wt/huafa/web/json/position/list，brandCode1、recruitType1、page1、lanType1；positionType/comPart/sicCorpCode/releaseTime/useForm/projectId/workPlace/site/keyWord为空。req_state9200，rowCount9、rowSize10、pageCount1；目录9个postId唯一，表格及接口ID/标题/单位/地点/发布时间一致。

postList直接含workContent、serviceCondition、education、workPlace、orgName、deptOrgName、publishDate、publishDateTime、endDate。orgName与deptOrgName均为名录主体，orgId0，不能凭0猜单位。未知新单位明确报范围需核对。公开详情webPositionN310!getOnePosition由页面postDetail脚本生成，postId323812/recruitType1/brandCode1/importPost0/columnId1；标题、职责、资格、本科及以上、珠海与列表一致。列表已含全文，无需逐条重复请求详情。

source_url按实际公开脚本组合，不使用postIdToken，不复制会话字段。publishDate为页面发布时间，publishDateTime仅用于校验同日；不用lastEditDate替代。endDate为公开业务截止字段，本轮9条均2026-02-26已截止；网页仍显示不代表有效。workType本轮空，校园recruitType1为正式校招口径，标题明确实习则排除；缺详细地址保留空值。每次刷新完整内联正文，按共同过滤处理过期，保留原始9条及排除证据。

## 集团当前渠道

51job集团介绍中房地产板块明确华发股份600325，职位目录指向wecruit.hotjob.cn/SU67b2e3bb1eb80555b7a457f7/pb/school.html。正常页面显示在招0及明确暂无职位，所属机构/地点/学历/职位类别均全部。实请求listPosition表单isFrompb=true、recruitType1、pageSize15、currentPage1，无局部筛选；state200，pageForm totalPage/pageSize/currentPage/dataCount均0，pageData[]、positonNum0，搜索条件data{}。零目录可证明此渠道当前无新增，但不根据集团混合范围猜未来单位归属。

本版对集团目录只验证当前零状态；未来出现非零需要核验单位树、上市主体边界及跨门户重复，报告unsupported_scope并保留独立门户已成功记录，不能误报全公司完成。集团目录每次实时刷新，不缓存永久零结果。

## 验收与失败

首轮临时绑定全采，两Scope守恒，9条过期、0确定有效为当前探测预期，不提前计验收。真实完成后才正式绑定、审计、加入B组汇总。回放验证完整9行正文、身份/日期错误、过期过滤、集团零计数/筛选/业务错误及非零不冒充成功。完整UVsync/Ruff/ty/pytest；空白、认证、预算或任一范围失败保留partial/blocked。当前非零集团范围明确未实现，不以独立门户成功覆盖缺口。
