# SPEC-055 英特集团校园招聘组织树

状态：已实现并实时全量验收。日期：2026-10-14。归属 SPEC-050。

## 目标与非目标

接入 COM0421 浙江英特集团股份有限公司所列 `https://recruit.zibchina.com/campus.html` 中，公开校园招聘目录里属于英特集团组织树的岗位。该入口由浙江省国际贸易集团共享，不能将其他成员企业岗位归为英特集团；不采社会招聘、实习招聘或需要登录的投递流程。

## 输入、输出与边界

页面调用 POST `/server/recruitpositionapply/listPage`，入参 `conds.channel=1` 为校园招聘，页码从 1 起。初次探测总量 78 条，运行时以稳定的 `total`、`pages`、`current` 和唯一岗位 ID 判定分页结束。GET `/server/recruitpositionapply/org/list/all` 返回组织树；以全称“浙江英特集团股份有限公司”为唯一根，只选择 `orgId` 的父级链包含该根的岗位。组织树缺根、重名、循环、岗位所属组织缺失或分页变化均失败，不以名称包含“英特”代替层级验证。

逐条 GET `/server/recruitpositionapply/getInfo/{id}`，核对岗位 ID、组织 ID、校园渠道、岗位名、职责和要求。输出部门/法人、学历、城市、详细地址、职责、要求、结束时间及源证据。`startTime` 仅为开放时间，不当作发布日期；源站未给发布日期时留空。结束时间由源站 `endTime` 给出，过期岗位由公共筛选处理。

## 失败与验收

列表或组织树不可读、分页未穷尽、详情错配、正文缺失时保留已成功记录和错误，覆盖标为 partial/blocked。单条截止或不可见记录不计有效岗位。离线测试验证跨集团排除、子公司包含、分页计数、详情身份和局部失败。实时 `expected=listed=unique=details+reused_details`、`coverage=complete` 且有效岗位大于零才启用 COM0421 绑定；导入字段待补全另行统计。
