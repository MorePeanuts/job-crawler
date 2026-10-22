# SPEC-282 上汽官网按企业分支接入智己汽车与享道出行校园岗位

状态：2026-10-22 真实全量验收通过；纳入 SPEC-277 最终 50 家审计。

## 目标与非目标

从上汽集团官方招聘站公开的公司分支接入 COM0538 智己汽车和 COM0785 享道出行的在招正式校招岗位。仅计名录对应公司，不混入上汽其他子公司、实习或社招；不将集团全站岗位算入两家公司。

## 输入输出与范围

上汽官网 `saic-recruit.saicmotor.com/recruit/pc/#/collegeRecruit` 的公司下拉明确列出两家公司。公开 `publishPosition/companyList` 给出各自 ID，`position/deliver/list` 以 `companyId` 和 `posType=[1]` 分页，源总数分别为 2 和 8；`position/get/?id=` 提供职位职责、要求和身份。完整输出适配器、来源绑定、逐页/逐岗证据、当日快照、岗位信息与严格导入表。`posCreatorDate` 是后台创建时间，不当作源站岗位发布时间；发布日期保持空值。

## 失败行为与验收

公司 ID 与名称变化、列表混入其他公司、页码断裂、总数不一致、详情 ID/公司不匹配或职位正文缺失时，保留已有数据与错误，coverage 不得为 complete；零正式岗位不得计数。缺少学历、详细地址等导入字段时留待补全。两家公司分别验证 `expected=listed=unique=details`、`terminal=true`、`coverage=complete`、有效岗位大于零，随后纳入累计审计与归档。

| 需求 | 验证 |
| --- | --- |
| 企业主体和正式校招 | 官网公司列表、`companyId`、列表与详情 `posCompanyName/Id`、`posType` |
| 全目录和详情身份 | 源总数、首末页、唯一 ID、逐条详情与 Scope |
| 日期和表格 | 后台创建日期不得写入发布时间、回放、实采报告、批次审计及程序导出 |
