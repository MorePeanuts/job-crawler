# SPEC-134 舜宇光学校园招聘 Moka 模块目录

状态：开发中；归属 SPEC-101。

## 目标、输入与输出

从名录 COM0353 舜宇光学科技（集团）有限公司的官方 `https://campus.sunnyoptical.cn/` 采集当前公开正式校招职位，输出公共快照、信息表和严格导入表。

## 非目标

不采社会招聘、实习或兼职，不登录或投递；不把网站介绍中的历年数据当当前岗位。不凭列表缺失的地点、发布日期或法人单位猜测字段。

## 已观察目录契约

官方入口跳转至同域 Moka `campus-recruitment/sunnyoptical/45602`。页面招聘模块 `POST /api/outer/ats-apply/website/jobs/module` 的 `orgId=sunnyoptical, siteId=45602, moduleId=0477326749, commitments=["全职"]`，默认无关键词和部门筛选；模块公开总量 99，页面职位类别数之和也为 99。响应加密，按页面 `aesIv` 解码。逐页核对 `jobStats.total`、岗位 ID、组织和公开详情 ID，直到 99 条闭合；列表缺失地点的岗位在详情也缺失时留空。

## 失败与验收

入口、模块、筛选参数、加密格式、目录总数、岗位身份或详情改变即记录覆盖失败，保留成功记录及证据。回放测试覆盖模块无筛选载荷、分页、详情身份和正文缺失。真实验收须 `coverage=complete`、正式校招选中大于零，且 `expected=listed=unique=details`；导入缺项与源站没有的字段分别报告。
