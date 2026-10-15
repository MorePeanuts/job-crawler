# SPEC-132 中国电子集团校招职位目录

状态：已实现并通过 2026-10-15 真实全量目录验收；归属 SPEC-101。

## 目标、输入与输出

从名录 COM0110 中国电子信息产业集团有限公司的官方 `https://campus.cec.com.cn/position?positionType=0` 完整采集当前公开校园招聘正式岗位，按集团机构树核对实际招聘单位，导出公共岗位快照、信息表和严格导入表。

## 非目标

不采社会招聘与实习生、不投递或登录；不调用点击量或申请等有副作用接口；不把更新日期、截止日期或采集时间当岗位发布日期。公开详情是列表卡片的展开，列表接口已含职责与资格，无需逐岗点击。

## 已观察目录契约

- `common/info/464790010986497` 与 `common/listOrg` 确认集团主体及机构树。目录的 `POST position/search` 原始无筛选请求为 `page=1,size=10,name="",positionType="0",degree=null,orgId=[]`。分页核对 `total/current/size/pages` 与各页身份 `id`，直到末页，不把首屏 10 条算全站。
- 2026-10-15 探测源站共 846 条、85 页，846 个唯一岗位 ID；机构树含 332 个不同单位名称，目录所有 `org` 均存在树中。`positionType=0`，其中 845 条为全职正式岗位、1 条为实习；全职岗位的 `canDeliver=true`。`expireFlag` 在 202 条即将截止岗位中也为 true，页面仍显示“即将截止”且 `canDeliver=true`，不能据此直接排除。按 `closeDate` 做日期边界判断，2026-10-15 无已过期日期。
- 列表字段 `jobDescription/jobRequirements` 分别为职责与资格，`cityName` 为地点，`org` 为实际招聘单位，`closeDate` 为日期级截止；列表没有岗位发布时间，保持空值。`positionNo` 与 `id` 可双重核对身份。

## 失败与验收

主体或无筛选载荷变化、分页总数不稳定、重复 ID、单位不在树中、岗位类别/正文异常均标记 partial，保留成功记录与证据。回放测试验证首/次/末页、实习排除、即将截止仍保留、重复身份和错误单位。只有全目录闭合、`coverage=complete`、正式校招选中大于零才计入本批新增企业；另报告信息表与严格导入待补全量。

## 实际验收

`outputs/dev-20261015-COM0110` 于 12:35 上海时间实采 85 页、846 个唯一岗位，`expected=listed=unique=details=846`、`coverage=complete`。公共筛选排除 1 条实习，正式校招选中与信息表 845 条；严格导入 0，分类、地点格式和源未给的岗位发布日期保持待补全。回放见 `tests/test_cec.py`。
