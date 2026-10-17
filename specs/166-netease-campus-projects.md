# SPEC-166 网易应届生项目联合目录

状态：已实现并完成本轮真实验证；SPEC-156 A 组 COM0190。

## 目标与边界

读取 campus.163.com 首页 `/api/campuspc/project/navigation/list` 的“应届生”四个子入口：互娱 2027（projectId=102）、互联网 2027（103）、雷火 2027（77）与星火计划。精英实习及日常实习目录排除。星火页面唯一岗位链接 id=4788/projectId=103，是互联网目录的别名，需核对存在并只计一次。项目集合变化须显式报告，不遗漏新增项目。

## 观察契约、输入输出

互娱 campus.game.163.com 与互联网 campus.163.com：`/app/job/position?id=<project>` 观察 GET `/api/campuspc/position/getJobList`，pageSize=10/currentPage=1/projectId，无关键词/类别/城市过滤。code=200，data.total/pages/list；当前 40/4 页和 81/9 页。列表 updateTime 是更新时间；详情 `/app/detail/index?id=<id>&projectId=<project>` 观察 `getJobDetails`，必须使用详情 publishTime（例如系统策划 2026-07-19，列表更新 2026-10-14）作为发布日期。

雷火 `https://leihuo.163.com/campus/#/full?channel=iSfFmJe` 观察 `https://xiaozhao.leihuo.netease.com/api/apply/job/list/show`，project_id=77/page_size=10/page_number=1/job_name=""；status=200，data.count_number/pages_count/last_page/apply_job_list，当前 30 条/3 页。ehr_project_id、ehr_job_type=1/type_name=全职、target=2027届应届毕业生核对；job_detail_url 指向 campus.163.com 上对应详情。

雷火列表请求须在 leihuo.163.com 页面上下文执行；详情进入 campus.163.com 后，下一页需返回雷火入口，并在新页详情前重新切换到详情页面，避免跨域请求失败。

三个项目均按项目+岗位 ID 稳定去重、详情核对 ID/项目/标题，读取 positionDescription/positionRequirement、workPlaceName、positionTypeName、publishTime。缺失学历交公共补全；缺失地址留空，不用项目名猜测用人部门。目录分类为应届生，任职要求中的可提前实习不自动改为实习岗位。

雷火当前页面明确“10月15日网申截止”，未给年份。保存原截止文本 `10月15日`，交公共日期筛选产生 unparsed_deadline 待核验，不将这批岗位计为已确认有效，也不凭采集年份补造截止日期。互娱和互联网未公开截止则为空。新页面明确完整日期时依源更新规范与解析。

## 失败行为与验收

未知项目、别名无法归并、筛选残留、数量/页数变化、重复页、提前空页、身份错配或详情失败均保留部分结果与覆盖缺口。不能仅采互娱即宣称网易完成。详情继承 before_detail/remember，源列表证据和详情证据关联。

回放验证三个项目分页、四入口去重、发布日期与更新时间分离、雷火截止待核验、详情局部失败、目录重复和未知项目。临时绑定实采核对三目录 151 条与四入口范围，公共分类与表格审计后启用；有效岗位与日期待核验信息行分别统计。
