# SPEC-165 盛屯矿业 2027 校园招聘板块

状态：开发中；SPEC-156 A 组 COM0450。

## 目标与非目标

从盛屯集团 2027 校园招聘 shengtun2027.zhaopin.com 完整目录中，提取名录上市主体“盛屯矿业”板块及其下属招聘单位。排除盛新锂能、盛屯集团直属，不将集团兄弟公司的职位归为盛屯矿业集团股份有限公司。原 m.600711.com 校招介绍页没有实际职位，新活动的招聘须知明确面向 2027 应届生及毕业 1–3 年学子。

## 观察契约、输入输出

入口 `/index.html`，公开智联 `/grace/api/dsc/search-job-list`，orgNumbers="105807"、jobSource=2、pageIndex=1、pageSize=12，无部门/地点/类别/关键词过滤。初始全目录 126 条。聚合 `/get-search-aggregation`，orgNumber="105807"、jobSource=2、facetFields=["SOU_XY_ORG_ID"]、orgDepartmentIds=""、sortType=1：盛屯矿业 code=10133771、number=KA0538004527D90000102000、54 条；盛新锂能 48 条、集团直属 24 条。三者 parentId 均为 105807。

遍历根目录，按 company.companyNumber 与聚合 number、campusOrgName 与聚合 name、campusDepartment.parentId 与聚合 code 交叉核对；矿业计入，其他两类计 skipped_out_of_scope。总数和三板块分布须闭合。实际单位为 campusDepartment.name。岗位 jobNumber 为身份，detail 为正文，minEducationName 学历、jobTypeName 分类、address 地点；modifiedTime 是更新时间，不写入发布日期，缺失截止保持空。复用 Zhaopin 正文拆分、增量及公共分类导出。

## 失败与验收

未知或重复板块、集团主体不符、岗位单位错配、聚合计数不闭合、分页重复/提前结束和正文缺失均不能算覆盖完整。增加默认不改变既有租户的单位纳入钩子；回放证明仅矿业行纳入，兄弟板块排除且仍计入覆盖，新增未知单位和错误 parentId 失败。临时绑定实采，审计完整范围和导出行数，质量检查通过后更新正式来源和绑定。
