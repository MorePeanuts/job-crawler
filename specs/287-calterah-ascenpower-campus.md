# SPEC-287 加特兰与芯粤能 Moka 校招模块

状态：2026-10-22 真实全量验收通过；纳入 SPEC-277 最终 50 家审计。

## 目标与非目标

接入名录 COM0700 加特兰与 COM0685 芯粤能的企业独立 Moka 校园招聘站，采集仍开放的正式校招岗位。排除实习、社招、已关闭岗位，不把站点介绍、首页卡片或第三方索引当作完整目录。

## 输入与输出

加特兰入口为 `app.mokahr.com/campus_apply/calterah/1109`，校招模块 `moduleId=5441735827`；芯粤能入口为 `app.mokahr.com/campus-recruitment/ascenpower/166280`，校招模块 `moduleId=6198202737`。两站均由企业名称、简介及校招栏目识别主体；源请求分别固定 `orgId/siteId/moduleId`，无关键词、部门、地点筛选，`needGroupType=list`。模块未给 `commitments=[全职]`，必须读取逐岗 `commitment` 和标题，排除实习兼职。输出适配器绑定、源快照、岗位信息表及严格导入表；发布时间仅来自源字段。

## 失败与验收

模块租户、公司身份、总数、分页、详情 ID 或职位性质变化时保留错误和成功记录，coverage 不完整不能计数。缺失学历、地址等导入字段的岗位留待补全。验收要求两站各自独立 `expected=listed=unique=details`、`terminal=true`、`coverage=complete`、有效岗位大于零；用回放和真实运行分别核对模块参数、详情身份、正式性质和最终表格。

| 需求 | 验证 |
| --- | --- |
| 校招主体和模块 | 企业站点文案及源 `orgId/siteId/moduleId` |
| 完整目录 | 总数、分页末端、唯一 ID、逐岗详情 |
| 岗位与导出 | `commitment`、标题、源发布日期、运行报告及累计审计 |
