# SPEC-121 玖龙纸业公开校园招聘

状态：已实现并通过真实覆盖验收。日期：2026-10-15。归属 SPEC-101。

## 目标与非目标

接入名录 COM0275 玖龙纸业（控股）有限公司的公开飞书校招入口 `https://ninedragonspaper.jobs.feishu.cn/502309/position/list`，获取当前仍展示且未截止的正式校招岗位。不采社招、实习和校园宣传大使，不注册或投递。

## 输入与输出

2026-10-15 页面显示 15 个职位，公开 `search/job/posts` 请求为 `portal_type=6`，无关键词、地域、职能或项目筛选。返回 `count`、岗位 ID、职责、要求、地点、发布时间与 `recruit_type`（正式/实习）。按站点签名的 UI 分页遍历，核对总数、唯一 ID 与终点；用源 `recruit_type` 和标题排除实习。输出公共 Collection、信息表、严格导入表和证据报告。

## 失败行为

签名分页、校招类别、总数、字段结构或身份变化时保留成功记录与证据，标记 partial/blocked。零岗位或不完整采集不计入新增家数。

## 可验证验收条件

1. 回放核对 `portal_type=6`、机构路径、正式/实习区分、岗位详情地址和分页契约。
2. 真实全量 expected/listed/unique/details 闭合、coverage=complete，正式校招有效岗位大于零。
3. 验收后更新正式来源、绑定和批次汇总，按名录只计一家。

## 真实验收

2026-10-15 11:31（上海时间）以 `--window all` 和禁用模型的覆盖验证配置运行，快照 `outputs/dev-20261015-COM0275`。公开目录 `count=15`，两页 `expected=listed=unique=details=15`、`terminal=true`、`coverage=complete`；其中 1 条实习/校园宣传大使由公共筛选排除，正式校招选中、信息表及待补全均为 14 条，严格导入 0 条。对应回放见 `tests/test_feishu_campus.py`。
