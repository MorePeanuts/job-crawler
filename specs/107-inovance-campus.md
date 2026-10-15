# SPEC-107 汇川技术公开校园招聘全目录

状态：真实覆盖已验收。日期：2026-10-15。归属 SPEC-101。

## 目标与非目标

接入 COM0341 深圳市汇川技术股份有限公司招聘官网 `https://recruit.inovance.com/#/campus/jobs`。高校公布的 2027 届招聘简章指向该官网。完整采集页面的校园招聘目录，含集团业务及分子公司业务，保留公开业务板块名称；不把分子公司岗位标作上市主体本部直招。不采集社招、实习、已截止岗位或官网以外的来源。

## 输入、输出与站点契约

2026-10-15 校园职位页显示 327 个在招职位，调用同域 `prod-portal-api/position/ad/search`：`recruitTypes=[1]`、`keyword=""`、`hotOnly=false`、`topOnly=false`、`longTermOnly=false`、`pageNum=1`、`pageSize=20`。入口请求含公开 `X-Portal-Id`，按观察到的原值重放且不记录凭据。返回 `data.total=327`、`hasMore`、`records`，每行带 `adId`、`recruitType`、标题、工作地点、业务板块 `segment`、`publishTime`、`jobDescription`、`jobRequirement` 和学历。分页以实时 `total`、唯一 `adId` 及 `hasMore=false` 闭合，逐行正文直接来自列表；详情页 URL 以同一 `adId` 指向公开职位。源未给截止日期时留空。

## 失败行为

入口、招聘类型、筛选条件、总数、分页标志、唯一 ID 或正文字段变化时保留已成功记录与可复核错误，coverage 不得判为 complete。单位以公开 `segment` 原文输出；未知法人或地点不猜测。

## 可验证验收条件

1. 回放测试覆盖无筛选分页、ID 去重、正文、业务板块、学历、日期和总数/末页异常。
2. 真实 `--window all` 闭合实时总数、唯一 ID 与末页，`coverage=complete` 且有大于零条有效正式校招岗位。
3. 通过后更新正式绑定与 README，并把独立快照纳入 SPEC-101 批次候选。

## 真实验收

`outputs/dev-20261015-COM0341-v3` 的 `--window all` 运行在源端公开门户 ID 参与的请求中验证 `expected=listed=unique=details=327`、末页闭合、`coverage=complete`、选中 327 条。首次测试发现接口要求 `X-Portal-Id`，适配器改为仅复用页面已发送的公开门户 ID。站点覆盖验证时禁用模型，信息表 327 条、严格导入 0、待补全 327；导入缺口不影响目录覆盖结论。原始快照、报告和证据保留于上述目录。
