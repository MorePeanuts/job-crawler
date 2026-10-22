# SPEC-297 蕉内 2027 校园招聘目录

状态：2026-10-22 真实全量验收通过；纳入 SPEC-277 最终 50 家审计。

## 目标与非目标

接入 COM0620 蕉内的独立北森校园站 `bananain.zhiye.com/campus/jobs`。企业 2027 校招公告给出 PC 招聘官网 `bananain.zhiye.com/Campus`，该站首页说明面向 2026 年 12 月至 2027 年 7 月毕业的应届生。采集仍展示、未截止的正式岗位；排除实习和社招，不把同租户其他栏目计入。

## 输入输出与失败行为

已观察无筛选 `GetJobAdPageList`：`Category=[2]`、`PageIndex=0`、`PageSize=20`，源 Count=23；列表含稳定 ID、全职性质、发布日期、地点、职责及要求。遍历第二页至总数闭合，列表正文完整时不额外请求详情。输出逐岗快照、证据、岗位信息、严格导入和待补全报告。总数、性质、正文或分页异常则保留已采记录并报 partial/blocked；源缺字段保持空白。

## 可验证验收

| 需求 | 验证 |
| --- | --- |
| 官方主体和范围 | 2027 校招公告的 PC 入口与北森校园页、Category=2、Kind=全职/实习 |
| 完整目录 | 两页 23 个不同 ID，expected=listed=unique、terminal、coverage=complete |
| 字段和交付 | 列表正文/日期/地点回放断言，真实 selected>0 和累计审计 |
