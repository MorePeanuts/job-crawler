# SPEC-094 宁波银行 2027 校招本体及分支机构

状态：已实现并实采验收。日期：2026-10-14。归属 SPEC-050。

## 目标与非目标

从 COM0185 宁波银行股份有限公司招聘官网 `https://zhaopin.nbcb.com.cn/` 采集当前展示的 2027 届校园招聘岗位。仅纳入总行、分行、支行及其营业部；站内同时列出的永赢金租、宁银理财、宁银消金属于独立主体，按范围外记录。不进入登录或投递流程，不把岗位更新时刻当发布日期。

## 输入输出与失败行为

官网校园招聘页调用 `POST /api/position/schoolByPage/list`，参数 `recruitmentType=1`、空筛选项、页码和页大小，返回 `total`、`list`、末页标记。明确遍历到末页，核对总数、唯一 `id` 和页号；列表的 `compName` 判定法人边界，其他机构不纳入。通过公开 `GET /api/dict/getDictList` 将 `workLocation` 和 `education` 代码还原成站点原文。对范围内岗位用 `POST /api/position/selectOne` 取得详情，核对 ID、标题、机构、招聘类别、代码及截止日。`posDuty`、`posRequiRement`、`deptName` 来自详情；`publishTime` 若为空则保留空，不使用 `operateTime` 补写。

目录总数、分页、机构、字典或详情身份异常时报告受影响范围，保留已经成功采集的岗位，不能以空结果算完整。截止早于采集日的岗位排除，尚未到期但缺少职位正文字段的岗位保留为待补全或局部失败，按实际情况报告。

## 可验证验收条件

1. 离线回放覆盖总行、分支行与三类子公司排除、跨页唯一 ID、详情身份错配、截止边界和无发布日期。
2. 独立状态库 `--window all` 真实采集，目录总数与末页闭合，至少一条本体或分支岗位有效且 `coverage=complete`。
3. 实采成功后更新来源、绑定与 README；阶段汇总经起点企业去重审计、归档发布，并通过 Ruff、ty、pytest。

## 验收记录

2026-10-14 18:22（上海）独立状态库 `--window all` 实采官网 `recruitmentType=1` 无筛选目录，单页 `total=90`、返回 90 个唯一 ID、末页闭合。按 `compName` 排除永赢金租 2、宁银理财 1、宁银消金 3 条；其余总行及分支机构 84 条逐岗 `selectOne` 核对 ID、机构编码、地点、学历、截止日、职责和要求。`coverage=complete`、有效校招 84 条、严格导入 0 条、待补全 84 条；站点 `publishTime` 均为空，未将 `operateTime` 伪作发布日期，地点字典原文也未猜成省市区模板路径。离线回放见 `tests/test_nbcb.py`。

阶段 45 汇总审计 `.runtime/batches/2026-10-14-stage45-audit.json`：45 家、源采 6,277 条、有效及信息表 6,249 行、严格导入 459 行、待补全 5,790 行；`as_of=2026-10-14 18:26:06+08:00`。与本批起点 `e094360^:sites/bindings.toml` 的企业集合交集为空。两份工作簿已按 `新增45家-阶段汇总` 发布，后台快照归档。`uv sync --locked`、Ruff format/check、ty 及 pytest（494 项）均通过。
