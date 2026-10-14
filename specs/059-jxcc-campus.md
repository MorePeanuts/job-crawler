# SPEC-059 江西铜业集团校园岗位目录

状态：已实现并实时全量验收。日期：2026-10-14。归属 SPEC-050。

## 目标与非目标

接入 COM0045 江西铜业集团有限公司官网 `https://www.jxcc.com/join/xyJoinList.html` 的公开校园招聘目录。页面探测总数 50 条，正式运行以源站总数为准。源站列出集团本部及所属单位，原样保留各岗位单位；不将外部站点、社招或投递动作纳入爬取。

## 输入输出与遍历

首页 POST `/cebest-cms/cus/search`，参数 `menuCode=M000510`、`page=1`、`limit=10`、无关键词或筛选。逐页核对 `totalElements`、`totalPages`、`number`、`numberOfElements`、`last` 和唯一源岗位 ID，遍历至末页。每条公开响应中有 `id`、`openDataId`、`title`、`single2` 所属单位、`content1` 职责、`content2` 要求、`postTime` 发布时间、`endDate` 截止日、`single8` 地点和 `single10` 详情/申请链接；保存源字段和证据，缺失的不推断。

## 失败与验收

接口、目录筛选、分页总数、唯一 ID 或岗位字段改变时保留已成功记录并报告 partial/blocked，不把首页或空结果算作通过。离线测试覆盖分页、跨单位保留、重复/计数变化与局部失败。实时 `expected=listed=unique=details+reused_details`、`coverage=complete` 且有效岗位大于零才启用绑定；严格导入与待补全分别报告。
