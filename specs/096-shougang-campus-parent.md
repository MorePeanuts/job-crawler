# SPEC-096 首钢集团本级公开校招

状态：已验收。日期：2026-10-14。归属 SPEC-050。

## 目标与非目标

从 COM0134 首钢集团有限公司官方招聘平台 `https://zp.shougang.com.cn/` 采集当前公开校园招聘。平台同时列出多家独立子公司；仅 `rmorg` 精确等于“首钢集团有限公司”的本级岗位纳入，不以平台品牌把其他法人岗位计入本级。不登录、不投递、不采集社招。

## 输入输出与失败行为

平台首页公开 GET `/recruitFront/publish/orginfo?place=2` 提供招聘单位；GET `/recruitFront/publish/publishjob?place=2&page=N&limit=100&...` 返回 `total` 与 `data`，公开目录行本身就是详情页展示的数据，无独立详情接口。遍历全目录，核对稳定总数、岗位 ID 唯一、页长及末页闭合；对每行核对招聘主体，排除其他法人。纳入行以 `pk_publishjob` 为唯一键，保留源站发布日期 `publishdate`、截止日 `enddate`、地点、学历和原始专业要求。`responsibility`、`description` 或 `qualification` 缺失时留空，不从岗位名编造职责。截止日早于运行日的岗位排除。

接口响应、目录分页、机构目录均留证据。总数变化、重复 ID、缺少单位或日期、非成功接口以及分页失败均报告不完整覆盖，保留此前成功岗位。无有效岗位的完整目录不计入本次“有岗位企业”。

## 可验证验收条件

1. 回放测试覆盖多页、本级和子公司混合、末页、重复 ID、总数变化、过期岗位及缺失正文。
2. 独立状态库 `--window all` 实采：全目录 `listed=unique=expected`，末页闭合，本级有效岗位大于零且 `coverage=complete`。
3. 仅实采通过后更新正式绑定与 README；阶段汇总去重审计、归档发布，Ruff、ty、pytest 通过。

## 验收记录

2026-10-14 19:48（上海）独立状态库 `--window all` 实采通过。COM0134：135 条目录岗位、135 个唯一 ID，其中本级有效岗位 3 条，排除其他法人 132 条；`coverage=complete`、严格导入 0 条、待补全 3 条。离线回放覆盖本 spec 边界；全批审计 `.runtime/batches/2026-10-14-stage50-audit.json` 通过，Ruff、ty 和 512 项测试通过。
