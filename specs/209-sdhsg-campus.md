# SPEC-209 山东高速集团公开校园目录

状态：计划；SPEC-156 固定B组COM0090，拟用sdhsg-campus@1。

## 目标、输入输出及非目标

接入 https://zhaopin.sdhsg.com/#/centralizedRecruitment，覆盖山东高速集团全部单位、地点、专业的公开校园目录。页面页脚主体为山东高速集团有限公司，校园表格和公开前端模块21明确recruitType=1，社招为独立social路由。输入为固定B组来源，输出公共Job/Scope、证据与模板表；不包含社招、内部招聘、登录、注册、验证码、收藏或投递操作。

## 已观察契约

校园页面GET /sdhsghr/hr/job/weblist，query为recruitType=1、startTime/endTime/areaId/orgId/jobType/specialty/sidx均空、page=1、limit=10、status=1、order=desc，另有缓存时间戳_t。无公司、地区、关键词和日期筛选；仅改变页码，核对code=0、page.currPage/pageSize/totalCount/totalPage/list，分页10行、稳定总数、唯一id与末页。实探页面“共0条”“暂无数据”与totalCount=0、totalPage=0、list=[]一致，不用空DOM单独证明零。

公开前端app与11详情模块定义点击行为/#/jobInfo?jobid=目录id，GET /sdhsghr/hr/job/queryJob?id=同一id返回job；GET /sdhsghr/hr/upload/getUploadFile?jobId=同一id返回uploadList。详情须核对id、name、orgName及recruitType=1；status=1为招聘进行中，0为招聘已结束，2为招聘预览，其他状态不猜测。只允许明确0作为已关闭；未知或预览视为覆盖异常。附件非空或正文嵌入未解析附件时不声称详情完整，报告待处理。

jobExplain对应“岗位职责”，jobRequirement对应“其他要求”。保留educationName、specialtyValue、experience、年龄、政治面貌、考试等源字段；联系方式不采入岗位要求。orgName为实际招聘单位，orgNameParent为上级单位。地点按页面逻辑组合provinceName、areaName；areaId=991414时使用areaInfo，不猜省市；district=1时保留districtInfo。无明确详细地址则不填。startTime是开始报名时间，不作为发布日期；endTime为终止时间，published保持未知，不用createTime/采集时间代替。

新增非零流程依据公开前端契约实现，当前公开校园和社会目录均零，尚无当前非零详情实采样本。未来恢复岗位时若返回字段不满足契约应明确partial，不默认为零。

## 失败与验收

请求拒绝、业务失败、局部筛选、页码/总数/大小变化、重复ID、详情身份不符、附件未解析均保留问题及已成功记录；不能启用为成功空目录。非零使用before_detail/remember，未知发布日期不得按旧日期跳过。全量UV/Ruff/ty/pytest通过后临时绑定实采，零目录还需页面与接口双证据，审计后才正式绑定并加入B组汇总。零岗位只计目录覆盖完成，不计有岗位企业。测试覆盖分页、明确零与空壳、重复/缺页、状态和校园类型、详情关联、日期语义、地点及局部失败；合成非零回放不能冒充真实非零验收。
