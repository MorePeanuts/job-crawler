# SPEC-135 上汽集团校招完整目录

状态：已实现并通过 2026-10-15 真实全量目录验收；归属 SPEC-101。

## 目标、输入与输出

从名录 COM0036 上海汽车集团股份有限公司的官方 `https://saic-recruit.saicmotor.com/recruit/pc/#/collegeRecruit` 采集目前公开校招职位，保留源站实际招聘单位，输出公共岗位快照、信息表和严格导入表。

## 非目标

不采社会招聘或实习计划，不登录或投递，不把后台创建或更新时刻当公开发布日期；不把集团子企业岗位写成上市公司本部直招。

## 已观察站点契约

- 无筛选目录 `POST /recruit/api/recruit/position/deliver/list` 初始载荷为 `posCity=[],posType=[1,2],posTypeIds=[],companyId=[],page=1,size=15`。`posType=校园招聘` 为正式校招，`实习计划` 排除。按 `total/current/pages` 和唯一 `posId` 完整遍历。
- 2026-10-15 目录共 190 个唯一职位、184 校招与 6 实习；所有列表 `state=true`。公开公司表 `publishPosition/companyList` 含 35 个招聘公司，列表公司 ID 与名称须匹配，不以集团品牌替代实际单位。
- `GET /recruit/api/recruit/position/get/?id=...` 按 `id,posName,posCompanyId` 与列表核对，读取 `posDesc/posRequire`、地点和类型。`posCreatorDate/posUpdateDate` 属后台时间，不作为发布日期；源未给独立公开发布时间时留空。

## 失败与验收

目录筛选、页数、总数、重复 ID、公司映射、详情身份或正文异常时标记覆盖失败并保留成功记录和证据。回放验证多页、实习排除、公司核对、详情身份及局部失败。真实验收要求 190 个目录 ID 闭合、校招有效数大于零、`coverage=complete`，分别报告严格导入和待补全量。

## 实际验收

`outputs/dev-20261015-COM0036` 于 12:50 上海时间实采 13 页、190 个唯一职位；184 条正式校招逐岗详情核对成功，6 条实习计划排除，`coverage=complete`。选中和信息表 184 条、严格导入 0；站点未单独公开岗位发布时间，保持空值。
