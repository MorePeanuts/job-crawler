# SPEC-203 华鲁恒升官方校园门户

状态：已配置并完成实时零目录验收；SPEC-156固定B组COM0441。

## 目标、输入和范围

华鲁控股官网2026-03-16的《山东华鲁恒升化工股份有限公司2026年春季招聘简章》直接给出`https://wecruit.hotjob.cn/SU69b20f3e10919a570b6a96a0/pb/school.html`。公告明确山东华鲁恒升股份与其荆州子公司两个单位，报名2026-03-16至03-27已结束；只用该公告证明入口归属，不把历史计划人数400当实时岗位。

接入官方门户recruitType=1的完整校园目录，输出标准岗位与覆盖记录；不含社会招聘、其他华鲁集团兄弟公司或独立渠道，不操作报名和人才储备池。仍保持原B组。

## 已观察契约与失败行为

复用Hotjob公共协议，listPosition表单isFrompb=true、recruitType=1、pageSize=12、currentPage=1，无单位、地点或其他筛选。实时页面在招职位0个，JSON成功state=200、dataCount/totalPage/currentPage/pageSize均0、pageData=[]。同租户listSearchTerm成功data={}，无地点树时保留警告，不猜城市层级。

未来非零目录使用公共分页、postId关联详情、日期及增量流程。本轮未取得非零详情样本，未来需复核租户字段和招聘单位范围；不把公共回放冒充本站非零实采。业务失败、计数矛盾、重复页、租户/类型/范围变更必须明确失败，空白网页不等于零目录。

## 验收条件

配置独立租户名称和入口，复用Hotjob已存在的分页、零目录及失败回放，不添加只验证常量的测试。完整UV/Ruff/ty/pytest通过后临时绑定实采；expected/listed/unique=0、terminal=true、coverage=complete、只读零岗位审计通过才正式启用。加入B组输入，不计有岗位企业。保留公告归属、实时目录、源报告和采集时刻，更新支持范围与两组阶段表。

2026-10-18 08:19实采collect-hualuhengsheng，expected/listed/unique=0、terminal=true、coverage=complete。零岗位审计与922项测试、UV/Ruff/ty通过，启用hotjob-hualuhengsheng-campus@1，加入原B组快照。地点树缺失警告保留；本轮无非零详情样本。
