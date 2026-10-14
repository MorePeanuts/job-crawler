# SPEC-054 理想汽车正式校园岗位

状态：已实现并实时全量验收。日期：2026-10-14。归属 SPEC-050。

## 目标与非目标

接入 COM0191 理想汽车官方 `https://www.lixiang.com/employ/campus/list.html?fromJob=1`，从混合“校园招聘与实习”页面采集招聘类型“正式”的岗位，并以详情招聘项目剔除实习。页面当前总列表 1017 条，点击“正式”后显示 633 条；这些是探测时数值，运行时以源 API 稳定总数为准。

不采实习、社会招聘、推荐职位、投递接口或需要登录的内容。不将列表位置或标题用作身份；源站没有发布日期/截止日期时留空，不以发现时间或更新时间代替。

## 已观察输入输出与结束条件

公开 GET API `https://api-web.lixiang.com/osd-hr-recruitment-website/v1/recruit/school/job-page`：首页原始请求 `page=1&page_size=10`，用户选择“正式”后携带 `job_mode=1`。已验证该筛选下 `page_size=100` 返回 100 条、`total_count=633`、`total_pages=7`，每条有 `id`、`code`、`title`、`job_mode_name=正式`、`hire_mode=2`、地点与职能。适配器固定源站已验证的正式校园筛选，逐页遍历至稳定 `total_count`，核对页码、页数、唯一 ID 和末页；超过页量、重复、空页提前出现或计数漂移均不算完整。

列表卡片公开链接为 `/employ/detail/<id>.html?jobCode=<code>&fromJob=1`。打开一条详情观察到 GET `https://api-web.lixiang.com/osd-hr-recruitment-website/v1/recruit/job/detail?job_id=<id>`；同页还有 `/detail/recommend`，不能用前缀误匹配。详情返回 `data.id`、`code`、`description`、`requirements`、`subject_name`、岗位类型。逐条核对 ID/代码及正式类型后保存职责、要求、招聘项目、职能与地点。实采显示正式筛选中的招聘项目有 `2027校园招聘`、`2026校园招聘`、`2027“理想+”` 和 `实习生招聘`；“理想+”是官方 2027 校园专项，最后一类明确标为实习并由公共筛选排除。未知项目类型失败待核，不擅自纳入。列表和详情没有可靠发布日期、截止日期或详细地址字段时留空；学历只保留源字段或经公共补全层有引证的结果。

## 失败行为与验收

列表访问受限或总数无法穷尽为 blocked/partial；任一详情失败、身份错配、招聘类型改变、正文缺失或预算触顶时保留已成功记录和可复核错误，使 coverage 为 partial。源站明确 `total_count=0`、无条目且页数一致可验收为完整零岗位，但不计入 50 家。

离线测试应覆盖正式筛选、分页/末页、重复、总数变化、详情身份、实习混入和局部失败。实时运行以 `expected=listed=unique=details+reused_details`、`coverage=complete`、有效岗位大于零及真实采集时刻为启用绑定条件；公共分类及严格导入待补全分开报告。结果依 SPEC-050 汇总。
