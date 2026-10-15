# SPEC-122 中国中车集团 2027 校园招聘

状态：已实现并通过真实覆盖验收。日期：2026-10-15。归属 SPEC-101。

## 目标与非目标

接入名录 COM0095 中国中车集团有限公司的公开 Hotjob 统一校招门户 `https://crrc.hotjob.cn/SU64d47c466202cc36e27a52d4/pb/school.html`。遍历集团成员单位完整目录，逐岗保留实际招聘单位。不采社招、实习、已截止岗位，不将成员单位改写为集团总部，不登录或投递。

## 输入与输出

2026-10-15 门户公开 `recruitType=1` 无局部筛选 `listPosition` 首屏 574 条、48 页、每页 12 条；`listSearchTerm` 的 55 个顶层机构 `positionsNum` 合计 574。岗位列表包含 `postId`、`orgCode`、`company`、`projectName`、`publishFirstDate`、`endDate`。逐页核对总数、唯一 ID 和末页，逐岗调用 `listPositionDetail` 核对 ID、标题、实际招聘单位、完整机构码和项目。部分顶层机构未展开子节点，以机构码顶层归属核对其范围；首次发布时间不以更新日期替代。输出公共 Collection、信息表、严格导入表和覆盖证据。

## 失败行为

机构树岗位合计与目录总数不一致、岗位机构不属于顶层机构、详情身份错配、分页重复或中断、源站访问失败时保留成功记录和证据，标记 partial/blocked。未闭合目录或零有效岗位不计入新增 50 家。

## 可验证验收条件

1. 回放覆盖多机构、分页终点、详情身份与正式/实习区分。
2. 真实 `expected=listed=unique` 与详情或明确已截止数闭合、`coverage=complete`，有效正式校招岗位大于零。
3. 验收后更新正式来源、绑定与进度，按名录只计一家。

## 真实验收

2026-10-15 11:37（上海时间）以 `--window all` 和禁用模型的覆盖验证配置运行，快照 `outputs/dev-20261015-COM0095`。55 个顶层机构岗位数合计 574，48 页 `expected=listed=unique=574`、`terminal=true`，其中 30 条源站已截止跳过详情，余下 `details=544`；`coverage=complete`。选中、信息表及待补全 544 条，严格导入 0 条。回放见 `tests/test_hotjob.py`。
