# SPEC-161 泰康集团校园招聘

状态：开发中；SPEC-156 B 组 COM0072。

## 目标与范围

名录泰康保险集团股份有限公司官方招聘门户 jobtaikang.zhiye.com 的校园招聘完整目录。集团下属机构均保留实际 Org，输出企业名使用名录主体。社会招聘、实习生招聘及健康财富规划师招募不在范围内。千人计划页面为培养方案介绍，宣讲行程不是独立岗位目录。

## 观察契约与输入输出

入口 `/custom/campuslist`，观察 POST `/api/Jobad/GetJobAdPageList`，Category=["2"]、SpecialType=0、PageIndex 从 0 开始，原 PageSize=10，无关键词或地区/类别筛选。目录初始 Count=814，按 Id 去重，逐页遍历至唯一条数等于稳定 Count，拒绝重复页、提前空页与总数变化。

列表包含完整 Duty/Require；已观察详情 `/custom/gddetail?hideAll=1&jc=2&jobAdId=<Id>`，抽查 ID/标题/正文与列表一致。沿用已验证 Zhiye listing_complete 契约，保留列表证据，不为每行重复请求相同全文。Org 为机构、LocNames 为地点、Degree 为学历、ClassificationOne 为岗位类别、PostDate 为发布日期、EndTime 为截止；0001/2222 哨兵为空。缺失学历交公共补全，不猜测。Kind 或标题为实习时交公共筛选排除；过期岗位同样由公共筛选处理。

## 失败与验收

非 CategoryId=2、正文缺字段、残留筛选、列表业务错误、分页异常均保留失败，不将其视为零岗位。共享回放验证 21 条两页、字段和哨兵日期、实习类型及详情链接参数。临时绑定全量实采、检查覆盖计数与有效/信息/严格/待补全行数，通过只读审计后启用正式绑定。真实采集和离线测试分别记录。
