# SPEC-151 河钢集团官方校园招聘

## 目标

接入名录 COM0067 河钢集团有限公司的官网 `https://biz.hbisco.com/gf/hrpc/recruit/campus`。2026-10-15 官方校园目录展示 74 个岗位，筛选字典列出集团本部及 15 个成员单位。按官网默认无单位、地点、关键词筛选的全目录分页读取，逐岗关联公开详情，保留源招聘单位、职责、要求、工作地点和截止日。

## 非目标

不采社会招聘、博士后栏目和申请接口，不把筛选字典中的单位数当岗位数，不用 `createtime`、`modifytime` 或岗位生效日冒充发布日期。源没有可确认的岗位发布时间时留空。

## 输入、输出与失败行为

输入为官网 `hbisMediaOutlet=A&hbisRequirementType=A` 的 `filterOptions`、`position/list` 和 `position/detail`。校验默认首屏无局部筛选，按 `totalCount`、页码、`lastPage`、唯一 ID 遍历；岗位单位必须在官方筛选字典中，详情 ID、职位名称及单位与列表一致，并具有公开工作职责。部分详情的 `hbisJobReqs` 为空，但 `hbisProReqs` 提供专业要求；保留该原文字段作为要求，不推断学历。输出快照、岗位信息表、严格导入表及待补全报告。接口业务失败、分页未闭合、单位字典外岗位、身份不匹配或局部详情失败保留已有岗位并把覆盖标为 partial。

## 可验证验收

1. 回放首/次/末页、重复 ID、总数变化、详情身份/单位不符及局部失败；验证日期不被行政字段伪造。
2. 实站 `expected=listed=unique` 且详情/明确跳过数闭合、`coverage=complete`，有效正式校招岗位大于零。
3. Ruff、ty、pytest 通过，记录实采时刻和导入字段限制。

对应测试：`tests/test_hbisco.py`。

## 真实站点验收（2026-10-15）

14:57（上海时间）通过官网公开接口全量采集，快照 `outputs/dev-20261015-COM0067-v2`：`expected=listed=unique=details=74`，`coverage=complete`，正式校招选中 74 条，岗位信息表 74 条。源站未给岗位发布日期，严格导入表 0 条，74 条保留待补全；运行配置禁用模型以单独验证站点覆盖。首次实采发现 28 条详情的 `hbisJobReqs` 为空，随后按源站 `hbisProReqs` 原文保留专业要求并复采通过。
