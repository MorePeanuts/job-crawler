# SPEC-116 拓普集团智联校招页

状态：已实现并通过真实覆盖验收。日期：2026-10-15。归属 SPEC-101。

## 目标与非目标

接入名录 COM0454 宁波拓普集团股份有限公司官方校招页 `https://tuopu.zhaopin.com/school/index.html` 当前公开的正式校招目录。只保留该页面“在招职位”对应的岗位；不采同门户社会招聘页、不发送申请请求、不将更新时间写为发布时间。

## 输入、输出及观察到的契约

官方校招页请求智联公开 `https://fe.zhaopin.com/grace/api/dsc/search-job-list`，请求组织号 `CZ459148810`、`jobSource=1`、`customTags=校招`，其余地区/类型/关键词为空。2026-10-15 页面和接口均显示 1 条岗位，响应 `companyId=45914881`、`slaveDisplayOrgName=拓普集团`，岗位 `positionSourceType=1`、`jobCategories=[校招]`，列表含完整正文。该租户使用社招来源码加明确校招标签，不能套用其他租户的 `jobSource=2`，也不能清空本租户的校招标签。

逐页核对 `pageInfo.totalNum/totalPage/pageIndex/pageSize`，按 `jobNumber` 去重，并验证每条组织 ID、公司显示名称、来源码及校招标签。列表正文拆分职责和要求；`modifiedTime` 只是更新时间，`published` 留空。`unit` 保留公开机构名；缺失截止日期、独立职责或要求均留空并进入待补全流程。输出公共 `Collection`、13 列信息表及严格导入表。

## 失败行为

标签、来源码、组织身份、总数、页码、正文结构改变，或者重复岗位、后续页失败时保留已有记录和证据并标记 partial；源站明确零岗位时不计入 50 家。不能从通用社招目录补位。

## 可验证验收条件

1. 回放证明保留 `customTags=校招`、拒绝其他来源或标签，并核对分页终点及组织身份。
2. 真实全量采集 `coverage=complete`、当前正式校招选中数大于零，报告与页面目录数量一致。
3. 通过后才更新正式绑定和批次进度；日期和缺失字段不推断。

## 真实验收

2026-10-15 10:57（上海时间）以 `--window all`、模型禁用的站点覆盖配置实采到 `outputs/dev-20261015-COM0454-v2`。公开接口 `expected=listed=unique=details=1`、`terminal=true`、`coverage=complete`；正式校招选中和信息表均为 1 条，严格导入 0 条、待补全 1 条。初次运行发现 `orgIds` 空筛选参数，补入允许字段后重新运行完成；初次失败快照保留。源站没有原始发布日期，未用 `modifiedTime` 填补。回放见 `tests/test_tuopu.py`。
