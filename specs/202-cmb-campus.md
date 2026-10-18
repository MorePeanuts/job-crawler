# SPEC-202 招商银行应届生完整目录

状态：计划实现；SPEC-156固定A组COM0055。

## 目标与非目标

接入招商银行career.cmbchina.com官网校园首页“梦想靠岸·应届生招聘”链接的全部机构、城市目录：`/positionlist/96574F8D-C7ED-4772-AE7C-BAC896D190C1`。面向全体在校生的实习、数字金融训练营及社会招聘不纳入，不登录或投递。范围为该统一应届生门户，不保证独立招聘渠道全覆盖。

## 输入、输出与契约依据

输入为名录COM0055及上述官网。输出标准Job及Scope，交给公共筛选、补全、导出流程。`/api/campusRecruitmentWebsite/job/getList`以POST提交orgIdList/locationIdList/jobTypeIdList均空、keywords空、recruitmentTypeId为上述ID、pageIndex从1起、pageSize=10；成功码SUC0000，body.total/data。当前完整目录两次实探total=0、data=[]，页面未找到相关职位，recruiting-info/list同时返回空机构与城市。

实际加载的3829.a626c50c列表脚本证明分页递增及字段publishGID/jobDisplay/branchCodeName/locationName/expiredOn/longTermRecruitment，详情链接`/positionDetail/school?publishId=`。630.157952a3详情脚本证明校招详情GET `/api/campusRecruitmentWebsite/job/getDetail?publishId=`，正文jobResponsibility/jobRequirement，项目recruitmentTypeID；这些字段与社招共用展示组件，社招数据仅用于核对结构，不进入校招成果。

本轮历史校招详情B5D72E8D-C2D7-48EA-AC1A-217C96A0BA8F明确返回EZPREC0001、“该职位已过期, 请刷新后重试”、body=null。仅这一精确业务状态可计已关闭；其他失败不得算零或下架。当前没有有效非零校招详情实采样本，未来非零详情仍须通过项目、标题、机构、地点关联及结构校验；离线回放不能冒充非零实采。

## 遍历、字段与失败行为

以publishGID唯一标识；每页总数稳定、实际行数符合10条分页和末页余数，无重复ID。零目录同时核对页面空提示和完整机构/城市空集合。读完总数才标记terminal。逐详情保留成功行和失败，正文附件未处理明确失败。正文HTML转文本，不以页面空壳为详情。

截止使用expiredOn，longTermRecruitment=true时不采用旧截止；发布日期未公开则空，不能把宣讲、系统更新或采集时刻写为发布。学历和具体地址未知留空。使用before_detail/remember，复用时保留新列表日期和证据；显式过期详情保存不可见列表记录。

## 可验证验收条件

- 回放：首/中/末页闭合、零目录双证据、重复页、总数变化、局部筛选拒绝、详情项目或身份错配、已过期与普通业务失败区分、附件拒绝、长期日期、增量钩子。
- 完整UV/Ruff/ty/pytest通过后临时绑定实采；源expected/listed/unique一致、terminal且coverage=complete，并通过只读交付审计才正式启用。
- 当前如仍为零，只计覆盖企业、不计有岗位企业；加入原A组快照输入。文档明确非零校招详情验证限制。
